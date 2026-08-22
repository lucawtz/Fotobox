import html
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import re
import secrets
import shutil
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional
from urllib.parse import quote
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from flask import (Flask, Response, abort, jsonify, redirect, request,
                   send_file, session)

import camera as camera_mod
import collage as collage_mod
import config
import disk_monitor
import events

logger = logging.getLogger(__name__)


def _load_or_create_secret_key() -> bytes:
    """Persistenter Flask-Secret-Key. Sonst werden alle Admin-Sessions
    invalidiert wenn der Service neu startet."""
    key_path = os.path.join(config.BASE_DIR, ".flask_secret")
    try:
        if os.path.isfile(key_path):
            with open(key_path, "rb") as f:
                data = f.read().strip()
                if len(data) >= 32:
                    return data
        key = secrets.token_bytes(48)
        # 0600 — nur der Service-User darf lesen
        with open(key_path, "wb") as f:
            f.write(key)
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass
        return key
    except OSError as exc:
        logger.warning("Secret-Key-Datei nicht beschreibbar (%s) — Fallback auf RAM", exc)
        return secrets.token_bytes(48)


app = Flask(__name__)
app.secret_key = _load_or_create_secret_key()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # Ohne das ist der Cookie ein reiner Browser-Session-Cookie: einmal Safari
    # weggewischt und der Owner tippt die PIN erneut, nur um ein Foto zu
    # loeschen. 30 Tage decken eine Vermietungssaison ab; /api/admin/logout
    # bleibt der Weg raus.
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    # 16 MB für Logo-Uploads — alles drüber wird von Flask abgewiesen,
    # ohne dass der Request gelesen wird.
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,
)

_EXTS = {".jpg", ".jpeg", ".png"}
_thumb_lock = threading.Lock()

# Throttle fuer das zeitbasierte Foto-Cleanup. main.py macht das vor jeder
# Aufnahme — falls aber niemand mehr knipst, wuerden abgelaufene Bilder ewig
# in der Galerie haengen. Deshalb beim Galerie-API-Aufruf max 1x pro 5 Min.
_age_cleanup_lock = threading.Lock()
_age_cleanup_last = 0.0
_AGE_CLEANUP_INTERVAL_S = 300


def _maybe_cleanup_old_photos():
    global _age_cleanup_last
    max_age = int(config.cfg.get("photo_max_age_days", 0))
    if max_age <= 0:
        return
    now = time.time()
    with _age_cleanup_lock:
        if now - _age_cleanup_last < _AGE_CLEANUP_INTERVAL_S:
            return
        _age_cleanup_last = now
    try:
        disk_monitor.enforce_photo_max_age(_pic_dir(), max_age)
    except Exception as exc:
        logger.warning("Photo-Age-Cleanup im Galerie-Server: %s", exc)

# ── Brute-Force-Schutz für Admin-Login ───────────────────────────────────────
# Per-IP Lockout: nach 5 Fehlversuchen 5 Minuten Sperre.
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_LOCKOUT_S    = 300
_LOGIN_WINDOW_S     = 600
_login_lock = threading.Lock()
_login_attempts: dict[str, deque] = {}
_login_locked_until: dict[str, float] = {}

SPA_DIST  = os.path.join(config.BASE_DIR, "frontend", "dist")
SPA_INDEX = os.path.join(SPA_DIST, "index.html")


def _spa_enabled() -> bool:
    return os.path.isfile(SPA_INDEX)


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def _thumb_dir() -> str:
    return config.cfg.get("thumbnail_dir", os.path.join(config.BASE_DIR, "thumbnails"))


def _pic_dir() -> str:
    return config.cfg["picture_dir"]


def _safe_filename(name: str) -> bool:
    return bool(name) and "/" not in name and os.sep not in name and ".." not in name


def _safe_path(event: str, filename: str) -> Optional[str]:
    if not events.is_safe_event(event) or not _safe_filename(filename):
        return None
    path = os.path.join(_pic_dir(), event, filename)
    return path if os.path.isfile(path) else None


def _photo_list(event_filter: Optional[str] = None) -> list[tuple[str, str]]:
    """Liefert (event_folder, filename) Paare, neueste zuerst."""
    base = _pic_dir()
    if not os.path.isdir(base):
        return []
    out: list[tuple[str, str, float]] = []
    try:
        entries = os.listdir(base)
    except OSError:
        return []
    for entry in entries:
        if event_filter and entry != event_filter:
            continue
        if not events.is_safe_event(entry):
            continue
        ev_path = os.path.join(base, entry)
        if not os.path.isdir(ev_path):
            continue
        try:
            files = os.listdir(ev_path)
        except OSError:
            continue
        for f in files:
            if os.path.splitext(f)[1].lower() not in _EXTS:
                continue
            try:
                mt = os.path.getmtime(os.path.join(ev_path, f))
            except OSError:
                continue
            out.append((entry, f, mt))
    out.sort(key=lambda x: x[2], reverse=True)
    return [(e, f) for e, f, _ in out]


def _make_thumb(event: str, filename: str) -> Optional[str]:
    td = os.path.join(_thumb_dir(), event)
    thumb = os.path.join(td, filename)
    with _thumb_lock:
        if os.path.exists(thumb):
            return thumb
        src = _safe_path(event, filename)
        if src is None:
            return None
        try:
            from PIL import Image
            os.makedirs(td, exist_ok=True)
            with Image.open(src) as img:
                img.thumbnail((400, 400))
                # quality=75 + progressive: ~50% kleiner, schnelles Anzeigen
                img.save(thumb, "JPEG", quality=75,
                         progressive=True, optimize=True)
            return thumb
        except Exception as exc:
            logger.warning("Thumbnail '%s/%s': %s", event, filename, exc)
            return None


def _preview_dir() -> str:
    return os.path.join(_thumb_dir(), "_preview")


def _make_preview(event: str, filename: str) -> Optional[str]:
    """Mid-Size-Vorschau (~1280px lange Seite, ~150-300 KB) für die Detail-
    Ansicht. Spart Faktor 10-20 ggü. Originalfoto auf langsamen Hotspots.
    """
    pd = os.path.join(_preview_dir(), event)
    preview = os.path.join(pd, filename)
    with _thumb_lock:
        if os.path.exists(preview):
            return preview
        src = _safe_path(event, filename)
        if src is None:
            return None
        try:
            from PIL import Image
            os.makedirs(pd, exist_ok=True)
            with Image.open(src) as img:
                img.thumbnail((1280, 1280))
                img.save(preview, "JPEG", quality=80,
                         progressive=True, optimize=True)
            return preview
        except Exception as exc:
            logger.warning("Preview '%s/%s': %s", event, filename, exc)
            return None


# ── Captive-Portal-Detection ───────────────────────────────────────────────────
# Wenn dnsmasq alle DNS-Anfragen auf den Pi umleitet, landen die Probe-URLs
# der Phone-Betriebssysteme bei uns. Wir schicken einen 302-Redirect auf die
# Galerie zurück → iOS/Android öffnen automatisch das Captive-Portal-Popup
# mit unserer Galerie. Sehr UX-freundlich für Gäste — kein "URL eintippen".
#
# Erkannt wird das am Host-Header, nicht an einer Liste bekannter Probe-Pfade:
# jede Anfrage, deren Host keine IP ist, kann nur ueber die DNS-Umleitung hier
# gelandet sein. Das deckt auch Probe-URLs ab, die wir nicht kennen.

def _looks_like_ip(host: str) -> bool:
    """Reine IPv4-Adresse? — IP-Aufrufe sind nie Captive-Portal-Probes."""
    parts = host.split(".")
    if len(parts) != 4:
        return False
    return all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)


@app.before_request
def _captive_portal_redirect():
    """Captive-Portal: nur ein Request mit DNS-Hostnamen (nicht IP) wird
    umgeleitet. Damit funktionieren BEIDE Wege:
    - Phone tippt apple.com (DNS-Hijack zum Pi) → Redirect zur Galerie
    - Browser tippt 192.168.4.1 oder 192.168.2.140 → kein Redirect
    """
    host = (request.host or "").split(":")[0]
    if not host or _looks_like_ip(host) or host == "localhost" or host.endswith(".local"):
        return None
    # Hierher kommen wir nur via DNS-Hijack (Hostname statt IP).
    # gallery_url enthält Port (oder lässt 80 weg) — entscheidend wenn
    # der Server beim preflight() auf 5000 zurückgefallen ist.
    target = config.cfg.get("gallery_url") or (
        f"http://{config.cfg.get('hotspot_ip', '192.168.4.1')}")
    from flask import redirect
    return redirect(f"{target.rstrip('/')}/", code=302)


# ── Galerie-Routen ─────────────────────────────────────────────────────────────

_NO_SPA_HTML = (
    "<!doctype html><meta charset=utf-8>"
    "<title>Fotobox</title>"
    "<style>body{font:16px system-ui;max-width:36rem;margin:4rem auto;padding:0 1rem;"
    "color:#333}h1{color:#1a73e8}code{background:#f1f3f4;padding:.15rem .35rem;"
    "border-radius:4px}</style>"
    "<h1>Fotobox – Frontend nicht gebaut</h1>"
    "<p>Die SPA unter <code>frontend/dist/</code> fehlt. "
    "Bitte ausführen:</p>"
    "<pre><code>cd frontend && npm install && npm run build</code></pre>"
    "<p>Oder die Fotobox via <code>install.sh</code> neu installieren.</p>"
)


def _no_spa_response(code: int = 503):
    return Response(_NO_SPA_HTML, status=code, mimetype="text/html; charset=utf-8")


@app.route("/")
def gallery():
    if _spa_enabled():
        return send_file(SPA_INDEX)
    return _no_spa_response()


@app.route("/photo/<path:_filename>")
def photo(_filename):
    if _spa_enabled():
        return send_file(SPA_INDEX)
    return _no_spa_response()


@app.route("/event/<path:_folder>")
def event_gallery(_folder):
    """Client-Route der SPA (frontend/src/App.tsx). Ohne diese Regel liefert
    Flask ein nacktes 404, sobald ein Gast die Event-Seite neu laedt oder den
    Link teilt — der React-Router bekommt den Pfad dann nie zu sehen."""
    if _spa_enabled():
        return send_file(SPA_INDEX)
    return _no_spa_response()


@app.route("/assets/<path:fname>")
def spa_assets(fname: str):
    if not _spa_enabled():
        abort(404)
    full = os.path.normpath(os.path.join(SPA_DIST, "assets", fname))
    if not full.startswith(os.path.abspath(SPA_DIST)) or not os.path.isfile(full):
        abort(404)
    # Vite-Bundles haben Hash im Dateinamen → 1 Tag Cache ist sicher
    response = send_file(full)
    response.headers["Cache-Control"] = "public, max-age=86400, immutable"
    return response


# Statisches Top-Level: Favicons, manifest, robots.txt etc.
# Vite legt die `public/` Dateien beim Build flach in `dist/` ab.
_TOP_LEVEL_STATIC = {
    "favicon.svg":            "image/svg+xml",
    "favicon-32.png":         "image/png",
    "favicon-192.png":        "image/png",
    "favicon-512.png":        "image/png",
    "apple-touch-icon.png":   "image/png",
    "manifest.webmanifest":   "application/manifest+json",
}


def _serve_top_level(fname: str):
    if not _spa_enabled() or fname not in _TOP_LEVEL_STATIC:
        abort(404)
    full = os.path.normpath(os.path.join(SPA_DIST, fname))
    if not full.startswith(os.path.abspath(SPA_DIST)) or not os.path.isfile(full):
        abort(404)
    response = send_file(full, mimetype=_TOP_LEVEL_STATIC[fname])
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response


# Eine Route pro Dateiname — `any`-Converter würgt an Bindestrichen.
for _name in _TOP_LEVEL_STATIC:
    app.add_url_rule(
        f"/{_name}",
        endpoint=f"static_{_name.replace('.', '_').replace('-', '_')}",
        view_func=lambda _n=_name: _serve_top_level(_n),
    )


# ── Kurzlinks fuer die QR-Codes am Box-Screen ─────────────────────────────────
#
# Der Boxbildschirm ist kein Touchscreen: der einzige Weg von der Box aufs
# Handy des Gastes ist ein QR-Code. Ein QR mit der nackten Ziel-URL bricht
# aber genau fuer die Gaeste, die gerade im Fotobox-WLAN haengen — hotspot.py
# schreibt 'address=/#/<ip>' in die dnsmasq-Config und biegt damit jede
# DNS-Anfrage auf die Box um. Ein https-Aufruf landet dann auf Port 443 der
# Box, den niemand bedient, und der Gast sieht nur einen Verbindungsfehler.
#
# Deshalb zeigen die Mini-QRs (ui.py: _draw_social_links) auf diese Route:
# eine reine IP-URL ueber http, die ohne DNS und ohne Internet immer aufgeht.
# Die Seite prueft im Browser, ob das Handy nach draussen kommt, leitet dann
# selbst weiter — und erklaert sonst den Weg, statt den Gast im Fehler stehen
# zu lassen.

# slug → (config-Key mit der URL, config-Key mit dem Label, Fallback-Label)
_GO_LINKS = {
    "termin":    ("booking_url",   "booking_label", "Termin buchen"),
    "instagram": ("instagram_url", None,            "Instagram"),
}

# Instagram lieber in der App oeffnen als im Handy-Browser: dort ist der Gast
# schon eingeloggt und folgt mit einem Tap, waehrend die Web-Ansicht ihn erst
# hinter eine Login-Wand schiebt. Ein normaler https-Link genuegt dafuer
# nicht — iOS oeffnet die App nur bei einem echten Fingertipp auf einen Link,
# nicht bei einem Redirect aus JS heraus, und Android braucht intent://.
# Beide Varianten baut der Server, das Handy sucht sich in _GO_PAGE_TMPL die
# passende aus.
_INSTAGRAM_HANDLE_RE = re.compile(
    r"^https?://(?:www\.)?instagram\.com/(@?[A-Za-z0-9._]{1,30})(?:[/?#]|$)")


def _app_targets(slug: str, target: str) -> dict:
    """App-Sprungziele fuer die /go/-Seite. Leer = nur die Web-URL."""
    if slug != "instagram":
        return {}
    match = _INSTAGRAM_HANDLE_RE.match(target)
    if not match:
        return {}
    handle = match.group(1).lstrip("@")
    # Reserviert von Instagram selbst — /explore/ ist kein Profil, und ein
    # App-Sprung darauf landet im Nichts.
    if handle in {"explore", "reels", "p", "accounts", "direct"}:
        return {}
    return {
        # iOS: eigenes Schema. Fehlt die App, zeigt Safari einen Fehler-
        # dialog — deshalb faellt die Seite nach kurzer Zeit selbst auf die
        # Web-URL zurueck (siehe Timer in _GO_PAGE_TMPL).
        "ios": "instagram://user?username=" + handle,
        # Android: Chrome kennt den Fallback selbst, wenn die App fehlt.
        "android": ("intent://instagram.com/_u/" + handle
                    + "#Intent;package=com.instagram.android;scheme=https;"
                    + "S.browser_fallback_url=" + quote(target, safe="")
                    + ";end"),
    }


# Wie lange die Erreichbarkeitspruefung im Browser laufen darf, bevor die
# Seite auf den Erklaertext zurueckfaellt. Kurz halten — auf einem
# hijackten DNS scheitert der Request meist sofort, und laenger als ~2,5 s
# wartet niemand auf einen Redirect.
_GO_PROBE_MS = 2500

# Wie lange die Seite dem App-Sprung auf iOS Zeit gibt, bevor sie doch die
# Web-URL nimmt. Ist die App da, ist sie in deutlich unter einer Sekunde
# vorn; laenger zu warten heisst nur, dass ein Gast ohne App laenger auf
# eine tote Seite guckt.
_GO_APP_MS = 1200

# Icon + Farbflaeche pro Ziel. Inline-SVG statt einer Datei aus dist/: die
# Seite muss auch dann vollstaendig aussehen, wenn das Handy gerade gar
# nicht nach draussen kommt — und ein zweiter Request waere genau der
# Moment, in dem der Captive-DNS wieder dazwischenfunkt.
_GO_ICON_INSTAGRAM = (
    '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">'
    '<path d="M12 2.2c3.2 0 3.58.01 4.85.07 1.17.05 1.8.25 2.23.41.56.22.96.48'
    ' 1.38.9.42.42.68.82.9 1.38.16.42.36 1.06.41 2.23.06 1.27.07 1.65.07'
    ' 4.85s-.01 3.58-.07 4.85c-.05 1.17-.25 1.8-.41 2.23-.22.56-.48.96-.9'
    ' 1.38-.42.42-.82.68-1.38.9-.42.16-1.06.36-2.23.41-1.27.06-1.65.07-4.85'
    '.07s-3.58-.01-4.85-.07c-1.17-.05-1.8-.25-2.23-.41a3.8 3.8 0 0'
    ' 1-1.38-.9 3.8 3.8 0 0 1-.9-1.38c-.16-.42-.36-1.06-.41-2.23-.06-1.27'
    '-.07-1.65-.07-4.85s.01-3.58.07-4.85c.05-1.17.25-1.8.41-2.23.22-.56.48'
    '-.96.9-1.38.42-.42.82-.68 1.38-.9.42-.16 1.06-.36 2.23-.41C8.42 2.21'
    ' 8.8 2.2 12 2.2Zm0 3.17A6.63 6.63 0 1 0 18.63 12 6.63 6.63 0 0 0 12'
    ' 5.37Zm0 10.94A4.31 4.31 0 1 1 16.31 12 4.31 4.31 0 0 1 12 16.31Zm6.89'
    '-11.15a1.55 1.55 0 1 1-1.55-1.55 1.55 1.55 0 0 1 1.55 1.55Z"/></svg>')

_GO_ICON_CALENDAR = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    ' stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"'
    ' aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="3.5"/>'
    '<path d="M3 10h18M8 3v3.5M16 3v3.5"/><path d="m9 15.2 2.1 2.1 3.9-3.9"/>'
    '</svg>')

_GO_ICON_LINK = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    ' stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"'
    ' aria-hidden="true"><path d="M10.5 13.5a4 4 0 0 0 5.66 0l2.83-2.83a4 4 0'
    ' 0 0-5.66-5.66l-1.4 1.42"/><path d="M13.5 10.5a4 4 0 0 0-5.66 0l-2.83'
    ' 2.83a4 4 0 0 0 5.66 5.66l1.4-1.42"/></svg>')

# slug → (Icon, Hintergrund der Icon-Kachel). Die Instagram-Kachel traegt
# bewusst den Verlauf der Marke: der Gast erkennt in der halben Sekunde,
# die die Seite steht, woran er ist — ohne ein Wort zu lesen.
_GO_ICONS = {
    "instagram": (_GO_ICON_INSTAGRAM,
                  "linear-gradient(135deg,#f9ce34,#ee2a7b 52%,#6228d7)"),
    "termin":    (_GO_ICON_CALENDAR,
                  "linear-gradient(135deg,#4285f4,#1a73e8)"),
}
_GO_ICON_DEFAULT = (_GO_ICON_LINK,
                    "linear-gradient(135deg,#4285f4,#1a73e8)")

# Platzhalter im Template: __NAME__. Ein Zwischenschritt setzt keinen neuen
# Platzhalter frei — alle Werte werden in einem Durchgang eingesetzt, sonst
# koennte ein Label, das zufaellig "__SHOWN__" enthaelt, den naechsten
# replace()-Aufruf kapern.
_GO_SLOT_RE = re.compile(r"__([A-Z]+)__")

_GO_PAGE_TMPL = """<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex">
<meta name="theme-color" content="#f8f9fa">
<title>__LABEL__</title>
<style>
/* Bewusst dieselbe Palette und Typografie wie die Galerie (frontend/src/
   theme.ts): der Gast kommt von dort und soll nicht das Gefuehl haben,
   auf einer fremden Zwischenseite gelandet zu sein. */
:root{
  color-scheme:light;
  --blue:#1a73e8; --blue-dark:#1557b0; --blue-tint:#f0f4f9;
  --ink:#1f1f1f; --ink-soft:#5f6368;
  --line:#e8eaed; --card:#fff; --bg:#f8f9fa;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0;min-height:100dvh;
  padding:calc(env(safe-area-inset-top,0px) + 2rem) 1.25rem
          calc(env(safe-area-inset-bottom,0px) + 2rem);
  display:flex;align-items:center;justify-content:center;
  font:16px/1.55 "Inter Variable","Inter",system-ui,-apple-system,"Segoe UI",
       Roboto,sans-serif;
  color:var(--ink);background:var(--bg);
  background-image:radial-gradient(115% 55% at 50% 0,
                   rgba(26,115,232,.10),rgba(26,115,232,0) 72%);
  background-repeat:no-repeat;
  -webkit-tap-highlight-color:transparent;
  -webkit-font-smoothing:antialiased;
}
main{width:100%;max-width:24rem}
.card{
  background:var(--card);border:1px solid var(--line);border-radius:20px;
  padding:1.75rem 1.5rem 1.5rem;text-align:center;
  box-shadow:0 1px 2px rgba(60,64,67,.06),0 8px 24px rgba(60,64,67,.12);
}
.icon{
  width:56px;height:56px;margin:0 auto 1rem;border-radius:17px;
  display:flex;align-items:center;justify-content:center;
  background:__ACCENT__;color:#fff;
  box-shadow:0 2px 8px rgba(60,64,67,.18);
}
.icon svg{width:29px;height:29px;display:block}
h1{margin:0;font-size:1.375rem;font-weight:600;letter-spacing:-.015em;
   line-height:1.25;word-break:break-word}
.host{margin:.3rem 0 0;font-size:.875rem;color:var(--ink-soft);
      word-break:break-all}
.status{
  display:flex;align-items:center;justify-content:center;gap:.5rem;
  margin:1.1rem 0 0;font-size:.875rem;color:var(--ink-soft);
}
.spin{
  width:15px;height:15px;flex:none;border-radius:50%;
  border:2px solid rgba(26,115,232,.25);border-top-color:var(--blue);
  animation:spin .7s linear infinite;
}
@keyframes spin{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){.spin{animation-duration:2.4s}}
.btn{
  display:flex;align-items:center;justify-content:center;gap:.5rem;
  min-height:48px;margin-top:1.15rem;padding:.8rem 1.25rem;
  border-radius:999px;background:var(--blue);color:#fff;
  text-decoration:none;font-weight:600;font-size:1rem;letter-spacing:-.005em;
  word-break:break-word;
  box-shadow:0 1px 2px rgba(26,115,232,.35);
  transition:background .15s,transform .1s;
}
.btn:active{background:var(--blue-dark);transform:scale(.985)}
.btn svg{width:17px;height:17px;flex:none}
.hint{margin-top:1.35rem;padding-top:1.35rem;border-top:1px solid var(--line);
      text-align:left}
.hint h2{margin:0 0 .9rem;font-size:.9375rem;font-weight:600}
.steps{list-style:none;margin:0;padding:0;counter-reset:step}
.steps li{
  counter-increment:step;position:relative;padding-left:2.1rem;
  margin-bottom:.7rem;font-size:.9rem;color:var(--ink-soft);
}
.steps li:last-child{margin-bottom:0}
.steps li::before{
  content:counter(step);position:absolute;left:0;top:.05rem;
  width:1.45rem;height:1.45rem;border-radius:50%;
  background:var(--blue-tint);color:var(--blue);
  font-size:.75rem;font-weight:600;
  display:flex;align-items:center;justify-content:center;
}
.ssid{color:var(--ink);font-weight:600;background:var(--blue-tint);
      border-radius:6px;padding:.05rem .35rem}
.url{
  margin:1.1rem 0 0;padding:.6rem .7rem;border-radius:10px;
  background:var(--bg);border:1px solid var(--line);
  font:.75rem/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;
  color:var(--ink-soft);word-break:break-all;
  -webkit-user-select:all;user-select:all;
}
[hidden]{display:none!important}
</style></head>
<body><main>
<div class="card">
<div class="icon">__ICON__</div>
<h1>__LABEL__</h1>
<p class="host">__SUBLINE__</p>
<p class="status" id="status" hidden>
<span class="spin" aria-hidden="true"></span>Einen Moment&nbsp;… wir leiten dich weiter</p>
<a class="btn" id="go" href="__HREF__">Jetzt &ouml;ffnen
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"
stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
<path d="M5 12h13m-5.5-6 6 6-6 6"/></svg></a>
<div class="hint" id="hint">
<h2>Seite l&auml;dt nicht?</h2>
<ol class="steps">
<li>Du bist im WLAN <span class="ssid">__SSID__</span> — das hat kein Internet.</li>
<li>WLAN kurz trennen oder mobile Daten einschalten.</li>
<li>Dann oben auf den Button tippen.</li>
</ol>
<p class="url">__SHOWN__</p>
</div>
</div>
</main>
<script>
(function () {
  var target = __JSON__;
  var app = __APPS__;
  var hint = document.getElementById("hint");
  var status = document.getElementById("status");
  // Ohne JS bleibt der Erklaertext stehen — er wird erst hier eingeklappt.
  hint.hidden = true;
  status.hidden = false;
  var done = false;
  function fallback() {
    if (done) { return; }
    done = true;
    status.hidden = true;
    hint.hidden = false;
  }
  // Mit Internet geht es auf dem Handy bevorzugt in die App: dort ist der
  // Gast eingeloggt und folgt mit einem Tap. Ohne App-Ziel (Desktop,
  // Buchungslink) bleibt es beim normalen Redirect.
  function leave() {
    var ua = navigator.userAgent || "";
    var deep = /Android/i.test(ua) ? app.android
             : /iPad|iPhone|iPod/i.test(ua) ? app.ios
             : "";
    if (!deep) { location.replace(target); return; }
    if (deep === app.android) {
      // intent:// traegt seine Web-Fallback-URL selbst — Chrome springt
      // dorthin, wenn die App fehlt.
      location.replace(deep);
      return;
    }
    // iOS: ein unbekanntes Schema laeuft still ins Leere (bzw. zeigt einen
    // Fehlerdialog), es gibt kein Signal dafuer. Also selbst nachfassen —
    // ausser die Seite ist inzwischen im Hintergrund, dann ist die App
    // aufgegangen und ein Redirect wuerde dem Gast nur den Browser
    // wieder vor die Nase setzen.
    var back = setTimeout(function () {
      if (!document.hidden) { location.replace(target); }
    }, __APPWAIT__);
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) { return; }
      clearTimeout(back);
      // Sonst steht in dem Tab, zu dem der Gast spaeter zurueckkommt, fuer
      // immer "wir leiten dich weiter …". textContent raeumt den Spinner
      // gleich mit weg.
      status.textContent = "In der App geöffnet.";
    });
    location.href = deep;
  }
  // no-cors reicht: uns interessiert nur, ob ueberhaupt eine Verbindung
  // zustande kommt. Im Fotobox-WLAN zeigt der Captive-DNS die Ziel-Domain
  // auf die Box, deren Port 443 zu ist — der Request scheitert also sofort.
  var ctl = new AbortController();
  var timer = setTimeout(function () { ctl.abort(); fallback(); }, __PROBE__);
  fetch(target, {mode: "no-cors", cache: "no-store", signal: ctl.signal})
    .then(function () {
      clearTimeout(timer);
      if (done) { return; }
      done = true;
      leave();
    })
    .catch(function () { clearTimeout(timer); fallback(); });
})();
</script>
</body></html>"""


def _js_literal(value) -> str:
    r"""JS-Literal fuer den Einbau in einen <script>-Block.

    json.dumps allein reicht nicht: es escaped zwar Anfuehrungszeichen, laesst
    aber '</script>' durch — und der HTML-Parser beendet den Script-Block an
    genau dieser Zeichenfolge, ganz egal ob sie in JS in einem String steht.
    Deshalb zusaetzlich < > & als \u-Sequenzen, die JS wieder als das
    urspruengliche Zeichen liest.
    """
    return (json.dumps(value)
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026"))


def _go_subline(slug: str, target: str, domain: str) -> str:
    """Zeile unter der Ueberschrift: wohin der Tap fuehrt.

    Bei Instagram das Handle statt der Domain — "@fotobox.wirtz" sagt dem
    Gast mehr als "instagram.com", das er unter der Ueberschrift ohnehin
    schon gelesen hat. Die vollstaendige URL steht weiter unten im
    Erklaertext, falls er sie abtippen muss.
    """
    if slug == "instagram":
        match = _INSTAGRAM_HANDLE_RE.match(target)
        if match:
            return "@" + match.group(1).lstrip("@")
    return domain


def _go_page(target: str, label: str, apps: Optional[dict] = None,
             slug: str = "") -> str:
    domain = target.split("://", 1)[-1].split("/", 1)[0] or target
    # Den echten Netznamen nennen statt "Fotobox-WLAN": der Mieter darf die
    # SSID im Admin-Panel aendern, und der Gast sucht im WLAN-Menue genau
    # den Namen, der dort steht.
    ssid = (config.cfg.get("wifi_ssid") or "").strip() or "der Fotobox"
    icon, accent = _GO_ICONS.get(slug, _GO_ICON_DEFAULT)
    slots = {
        "SSID":    html.escape(ssid),
        "LABEL":   html.escape(label),
        "HREF":    html.escape(target, quote=True),
        "SUBLINE": html.escape(_go_subline(slug, target, domain)),
        "SHOWN":   html.escape(target),
        "ICON":    icon,
        "ACCENT":  accent,
        "JSON":    _js_literal(target),
        "APPS":    _js_literal(apps or {}),
        "APPWAIT": str(_GO_APP_MS),
        "PROBE":   str(_GO_PROBE_MS),
    }
    return _GO_SLOT_RE.sub(lambda m: slots[m.group(1)], _GO_PAGE_TMPL)


@app.route("/go/<slug>")
def go_link(slug: str):
    entry = _GO_LINKS.get(slug)
    if entry is None:
        return redirect("/")
    url_key, label_key, fallback_label = entry

    target = (config.cfg.get(url_key) or "").strip()
    # Der Wert kommt zwar aus der Owner-Config und nicht vom Gast, landet hier
    # aber in einem href und in einem JS-String — ein 'javascript:'-Eintrag
    # waere ein Eigentor. Deshalb nur echte Web-Links durchlassen.
    if not target.lower().startswith(("http://", "https://")):
        if target:
            logger.warning("/go/%s: '%s' ist keine http(s)-URL — ignoriert",
                           slug, target)
        return redirect("/")

    label = (config.cfg.get(label_key) or "").strip() if label_key else ""
    # mimetype (nicht content_type): Flask haengt das charset selbst an —
    # steht es hier schon drin, geht es doppelt raus.
    response = Response(_go_page(target, label or fallback_label,
                                 _app_targets(slug, target), slug),
                        mimetype="text/html")
    # Nicht cachen: sonst zeigt das Handy nach einer Config-Aenderung noch
    # tagelang die alte Ziel-URL.
    response.headers["Cache-Control"] = "no-store"
    return response


def _public_links() -> dict:
    """Instagram/Booking fuer die Galerie-Seite.

    Der Gast hat das Handy beim Fotos-Holen ohnehin schon in der Hand — das
    ist die Stelle mit der geringsten Huerde, ganz ohne zweiten Scan. Die
    Links selbst laufen wieder ueber /go/, weil der Gast in diesem Moment
    per Definition im Fotobox-WLAN steckt.
    """
    return {
        "instagram_url": (config.cfg.get("instagram_url") or "").strip(),
        "booking_url":   (config.cfg.get("booking_url") or "").strip(),
        "booking_label": (config.cfg.get("booking_label")
                          or "Termin buchen").strip(),
    }


# ── Sichtbarkeit: Gaeste nur im laufenden Event ────────────────────────────────

def _may_see_all_events() -> bool:
    """Nur der Admin sieht jedes Event — Gastgeber und Gaeste das laufende.

    Ohne diese Trennung sieht jeder im Fotobox-WLAN die Fotos der letzten Feier:
    `is_safe_event` prueft nur Pfad-Traversal, nicht Zugehoerigkeit. Der
    Gastgeber ist bewusst *nicht* ausgenommen: er mietet die Box fuer seine
    eigene Feier, das Archiv der vorigen Mieter geht ihn nichts an. Der Owner
    kann die Galerie per `gallery_guests_see_all` bewusst als Archiv oeffnen.
    """
    if config.cfg.get("gallery_guests_see_all"):
        return True
    return _session_role() == "admin"


def _may_see_event(event: str) -> bool:
    return _may_see_all_events() or event == events.current_event_folder(config.cfg)


def _visible_photo_list(event_filter: Optional[str] = None) -> list:
    """Wie `_photo_list`, aber auf die sichtbaren Events begrenzt.

    Bewusst nicht in `_photo_list` selbst: Altersloeschung, Thumbnail-Prewarm
    und die Admin-Uebersicht brauchen weiterhin *alle* Fotos — sonst raeumt der
    Cleanup vergangene Events nie wieder auf.
    """
    if _may_see_all_events():
        return _photo_list(event_filter)
    active = events.current_event_folder(config.cfg)
    if event_filter and event_filter != active:
        return []
    return _photo_list(active)


def _kind_predicate(kind: Optional[str]):
    """Prädikat fuer den Galerie-Filter, angewandt auf collage.classify()[0].

    * "collage" — nur die fertigen 2x2-Bilder
    * "single"  — jede Einzelaufnahme, auch die vier aus einer Collage: der
                  Gast soll an seine Rohbilder kommen, nicht nur an die
                  Montage.
    * sonst     — alles ausser den Collage-Mitgliedern; die sind in ihrer
                  Collage bereits zu sehen und wuerden die Ansicht sonst
                  verfuenffachen.
    """
    if kind == "collage":
        return lambda k: k == collage_mod.KIND_COLLAGE
    if kind == "single":
        return lambda k: k in (collage_mod.KIND_SINGLE, collage_mod.KIND_MEMBER)
    return lambda k: k != collage_mod.KIND_MEMBER


@app.route("/img/<event>/<filename>")
def img(event, filename):
    # 404 statt 403: dass es weitere Events gibt, geht einen Gast nichts an.
    if not _may_see_event(event):
        abort(404)
    path = _safe_path(event, filename)
    if path is None:
        abort(404)
    response = send_file(path)
    # `private`, weil die Antwort jetzt von der Session abhaengt — ein
    # geteilter Cache duerfte sie nicht an den naechsten Gast weiterreichen.
    response.headers["Cache-Control"] = "private, max-age=3600"
    return response


@app.route("/thumb/<event>/<filename>")
def thumb(event, filename):
    if not _may_see_event(event):
        abort(404)
    t = _make_thumb(event, filename)
    if t is None:
        abort(404)
    response = send_file(t)
    response.headers["Cache-Control"] = "private, max-age=3600"
    return response


@app.route("/preview/<event>/<filename>")
def preview(event, filename):
    """1280px-Vorschau für die Detail-Ansicht — viel kleiner als Original."""
    if not _may_see_event(event):
        abort(404)
    p = _make_preview(event, filename)
    if p is None:
        abort(404)
    response = send_file(p)
    response.headers["Cache-Control"] = "private, max-age=3600"
    return response


@app.route("/download/<event>/<filename>")
def download(event, filename):
    if not _may_see_event(event):
        abort(404)
    path = _safe_path(event, filename)
    if path is None:
        abort(404)
    return send_file(path, as_attachment=True)


# ── ZIP-Bulk-Download ──────────────────────────────────────────────────────────

class _ChunkBuffer:
    """File-like Buffer der ZipFile-Output sammelt; wird per flush() geleert."""
    def __init__(self):
        self._buf = bytearray()
        self._pos = 0

    def write(self, data):
        self._buf.extend(data)
        self._pos += len(data)
        return len(data)

    def tell(self):
        return self._pos

    def flush(self):
        pass

    def take(self) -> bytes:
        if not self._buf:
            return b""
        out = bytes(self._buf)
        self._buf = bytearray()
        return out


def _stream_zip(items: list[tuple[str, str]]):
    """Generiert ZIP-Daten on-the-fly, ohne alles in den Speicher zu laden."""
    buf = _ChunkBuffer()
    with ZipFile(buf, mode="w", compression=ZIP_STORED, allowZip64=True) as zf:
        for arcname, src in items:
            try:
                zinfo = ZipInfo.from_file(src, arcname)
                zinfo.compress_type = ZIP_STORED
                with zf.open(zinfo, mode="w", force_zip64=True) as zout, \
                     open(src, "rb") as fsrc:
                    while True:
                        chunk = fsrc.read(64 * 1024)
                        if not chunk:
                            break
                        zout.write(chunk)
                        out = buf.take()
                        if out:
                            yield out
            except Exception as exc:
                logger.warning("ZIP-Skip %s: %s", arcname, exc)
                continue
            out = buf.take()
            if out:
                yield out
    final = buf.take()
    if final:
        yield final


def _zip_safe_name(name: str) -> str:
    keep = []
    for c in name:
        if c.isalnum() or c in "_-":
            keep.append(c)
        else:
            keep.append("_")
    out = "".join(keep).strip("_") or "Fotobox"
    return out[:60]


@app.route("/api/download-zip")
def api_download_zip():
    # Bulk-Download nur pro Event — sonst könnte ein Gast alte Bilder
    # voriger Mieter mit ziehen. Datenschutzthema.
    event_filter = (request.args.get("event") or "").strip()
    if not event_filter or not events.is_safe_event(event_filter):
        return jsonify(ok=False, error="Event-Parameter erforderlich"), 400
    # Der Traversal-Check oben sagt nur "sauberer Ordnername", nicht "darf der
    # Gast da ran". Ohne das hier zieht jeder das komplette letzte Event als ZIP.
    if not _may_see_event(event_filter):
        abort(404)

    # Ohne kind-Parameter bleibt es beim kompletten Event — der Gast, der
    # "ZIP" drueckt, will seine Bilder, nicht die Auswahl von irgendwem.
    # Erst ein aktiver Galerie-Filter schickt kind mit.
    kind = (request.args.get("kind") or "").strip().lower() or None
    keep = _kind_predicate(kind) if kind else (lambda _k: True)

    pic_dir = _pic_dir()
    items: list[tuple[str, str]] = []
    for ev, f in _photo_list(event_filter):
        if not keep(collage_mod.classify(f)[0]):
            continue
        items.append((f"{ev}/{f}", os.path.join(pic_dir, ev, f)))
    if not items:
        abort(404)

    suffix = {"collage": "-collagen", "single": "-einzelbilder"}.get(kind, "")
    zip_name = f"{_zip_safe_name(event_filter)}{suffix}.zip"

    return Response(
        _stream_zip(items),
        mimetype="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_name}"',
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-store",
        },
    )


@app.route("/api/count")
def api_count():
    event_filter = request.args.get("event") or None
    return jsonify(count=len(_visible_photo_list(event_filter)))


@app.route("/api/events")
def api_events():
    _maybe_cleanup_old_photos()
    active = events.current_event_folder(config.cfg)
    all_events = events.list_events(config.cfg)
    # Gaeste bekommen die Event-Auswahl gar nicht erst zu sehen — sonst stuende
    # in der Galerie eine Liste fremder Feiern, auch wenn die Fotos gesperrt sind.
    visible = (all_events if _may_see_all_events()
               else [e for e in all_events if e.get("folder") == active])
    return jsonify({
        "active":             active,
        "events":             visible,
        "event_name":         config.cfg.get("event_name", "Fotobox"),
        "photo_max_age_days": int(config.cfg.get("photo_max_age_days", 0)),
        **_public_links(),
    })


@app.route("/api/photos")
def api_photos():
    _maybe_cleanup_old_photos()
    event_filter = request.args.get("event") or None
    pic_dir = _pic_dir()
    out = []
    for ev, f in _visible_photo_list(event_filter):
        try:
            st = os.stat(os.path.join(pic_dir, ev, f))
        except OSError:
            continue
        kind, group = collage_mod.classify(f)
        out.append({
            "event":    ev,
            "filename": f,
            "mtime":    st.st_mtime,
            "size":     st.st_size,
            # Gefiltert wird im Client: die Liste eines Events kommt ohnehin
            # komplett, ein zweiter Roundtrip pro Filterklick waere ueber den
            # Hotspot nur langsamer. Der Server liefert die Einordnung.
            "kind":     kind,
            "group":    group,
        })
    return jsonify({
        "event_name":         config.cfg.get("event_name", "Fotobox"),
        "active_event":       events.current_event_folder(config.cfg),
        "filter":             event_filter,
        "count":              len(out),
        "photos":             out,
        "photo_max_age_days": int(config.cfg.get("photo_max_age_days", 0)),
        **_public_links(),
    })


@app.route("/api/delete/<event>/<filename>", methods=["POST"])
def api_delete(event: str, filename: str):
    # Wer eingeloggt ist, löscht ohne PIN-Abfrage; alle anderen müssen den PIN
    # mitschicken — beides geschützt durch das Login-Lockout (selber Bucket wie
    # /api/admin/login).
    ip = _client_ip()
    role = _session_role()
    if role is None:
        locked = _login_check_locked(ip)
        if locked is not None:
            return jsonify(ok=False,
                           error=f"Zu viele Fehlversuche – bitte {locked}s warten"), 429
        pin = request.form.get("pin", "").strip()
        admin_pin = config.cfg.get("admin_pin", "1234")
        host_pin  = config.cfg.get("host_pin", "")
        # Foto-Einzellöschung: Admin- ODER Host-PIN reicht. Bulk-Reset bleibt
        # in /api/admin/reset und ist weiterhin admin-only.
        if pin and secrets.compare_digest(pin, admin_pin):
            role = "admin"
        elif pin and host_pin and secrets.compare_digest(pin, host_pin):
            role = "host"
        else:
            _login_record_failure(ip)
            return jsonify(ok=False, error="Falscher PIN"), 403
        _login_record_success(ip)
    # Der Gastgeber räumt nur im laufenden Event auf. Ohne diese Zeile reicht
    # seine PIN, um Fotos vergangener Vermietungen zu löschen — Ordner, die er
    # laut _may_see_all_events nicht einmal sehen darf. 404 statt 403, damit
    # die Antwort nichts über die Existenz fremder Events verrät.
    if role != "admin" and event != events.current_event_folder(config.cfg):
        abort(404)
    path = _safe_path(event, filename)
    if path is None:
        return jsonify(ok=False, error="Datei nicht gefunden"), 404
    try:
        os.remove(path)
    except Exception as exc:
        logger.error("Foto löschen: %s", exc)
        return jsonify(ok=False, error="Löschen fehlgeschlagen"), 500
    # Thumbnail UND Mid-Size-Preview mit entfernen. Ohne die Preview liefert
    # /preview/<event>/<file> das geloeschte Foto weiter in 1280px aus — und
    # genau die URL rendert die Detail-Ansicht (PhotoView.tsx).
    for derived in (os.path.join(_thumb_dir(), event, filename),
                    os.path.join(_preview_dir(), event, filename)):
        try:
            os.remove(derived)
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.warning("Abgeleitete Datei '%s' nicht entfernt: %s", derived, exc)
    # Falls Event-Ordner jetzt leer ist, entfernen
    ev_dir = os.path.join(_pic_dir(), event)
    try:
        if os.path.isdir(ev_dir) and not os.listdir(ev_dir):
            os.rmdir(ev_dir)
    except OSError:
        pass
    logger.info("Foto gelöscht: %s/%s", event, filename)
    return jsonify(ok=True)


@app.errorhandler(404)
def spa_fallback(err):
    """Netz fuer weitere Client-Routen: unbekannte GET-Pfade an die SPA geben.

    Bewusst eng: nur GET, nie unter /api/ (dort muss ein 404 ein 404 bleiben,
    sonst bekommt fetch() HTML statt JSON), und nichts mit Datei-Endung —
    ein fehlendes Bild soll weiter sauber 404en statt index.html zu liefern.
    """
    path = request.path
    if path.startswith("/api/"):
        # JSON statt Flasks HTML-404 — api.ts liest im Fehlerfall res.json().
        return jsonify(ok=False, error="Not Found"), 404
    if (request.method == "GET"
            and "." not in path.rsplit("/", 1)[-1]
            and _spa_enabled()):
        return send_file(SPA_INDEX)
    return err


# ── Admin-SPA-Catch-all ────────────────────────────────────────────────────────

@app.route("/admin", defaults={"_path": ""})
@app.route("/admin/<path:_path>")
def admin_spa(_path: str):
    if _spa_enabled():
        return send_file(SPA_INDEX)
    return _no_spa_response()


# ── Admin JSON-API ─────────────────────────────────────────────────────────────

def _session_role() -> Optional[str]:
    """Aktive Rolle: 'admin', 'host' oder None."""
    if not session.get("admin_logged_in"):
        return None
    return session.get("role") or "admin"  # Legacy-Sessions ohne Rolle = admin


def _api_login_required(f):
    """Eingeloggt — egal ob Admin oder Gastgeber."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _session_role():
            return jsonify(ok=False, error="Unauthorized"), 401
        return f(*args, **kwargs)
    return decorated


def _api_admin_required(f):
    """Nur Admin-Rolle — Gastgeber bekommt 403."""
    @wraps(f)
    def decorated(*args, **kwargs):
        role = _session_role()
        if role is None:
            return jsonify(ok=False, error="Unauthorized"), 401
        if role != "admin":
            return jsonify(ok=False, error="Forbidden"), 403
        return f(*args, **kwargs)
    return decorated


@app.route("/api/admin/me")
def api_admin_me():
    role = _session_role()
    return jsonify(authenticated=bool(role), role=role)


def _client_ip() -> str:
    # Hinter Hotspot/lokal — kein Proxy. addr reicht.
    return request.remote_addr or "unknown"


def _login_check_locked(ip: str) -> Optional[int]:
    """Liefert verbleibende Sekunden des Lockouts oder None."""
    with _login_lock:
        until = _login_locked_until.get(ip, 0)
        remaining = int(until - time.time())
        return remaining if remaining > 0 else None


def _login_record_failure(ip: str):
    now = time.time()
    with _login_lock:
        dq = _login_attempts.setdefault(ip, deque())
        dq.append(now)
        # Alte Versuche außerhalb des Fensters wegwerfen
        while dq and now - dq[0] > _LOGIN_WINDOW_S:
            dq.popleft()
        if len(dq) >= _LOGIN_MAX_ATTEMPTS:
            _login_locked_until[ip] = now + _LOGIN_LOCKOUT_S
            dq.clear()
            logger.warning("Admin-Login: %s gesperrt für %ds", ip, _LOGIN_LOCKOUT_S)


def _login_record_success(ip: str):
    with _login_lock:
        _login_attempts.pop(ip, None)
        _login_locked_until.pop(ip, None)


@app.route("/api/admin/login", methods=["POST"])
def api_admin_login():
    ip = _client_ip()
    locked = _login_check_locked(ip)
    if locked is not None:
        return jsonify(ok=False,
                       error=f"Zu viele Fehlversuche – bitte {locked}s warten"), 429

    pin = (request.form.get("pin") or
           (request.get_json(silent=True) or {}).get("pin", "")).strip()
    admin_pin = config.cfg.get("admin_pin", "1234")
    host_pin  = config.cfg.get("host_pin", "")

    # Admin zuerst — falls beide PINs identisch konfiguriert sind, gewinnt
    # Admin (sonst wäre der Gastgeber-Modus eine Sicherheitslücke).
    role: Optional[str] = None
    if pin and secrets.compare_digest(pin, admin_pin):
        role = "admin"
    elif pin and host_pin and secrets.compare_digest(pin, host_pin):
        role = "host"

    if role:
        # Nur der Owner bekommt die lange Laufzeit (PERMANENT_SESSION_LIFETIME
        # statt "bis Browser zu") — er meldet sich einmal an und loescht danach
        # ohne PIN. Der Gastgeber-Cookie stirbt mit dem Browser: die Box wird
        # weitervermietet, sein Zugang soll nicht 30 Tage nachwirken.
        session.permanent = (role == "admin")
        session["admin_logged_in"] = True
        session["role"] = role
        _login_record_success(ip)
        return jsonify(ok=True, role=role)

    _login_record_failure(ip)
    return jsonify(ok=False, error="Falscher PIN"), 401


@app.route("/api/admin/logout", methods=["POST"])
def api_admin_logout():
    session.clear()
    return jsonify(ok=True)


@app.route("/api/admin/status")
@_api_login_required
def api_admin_status():
    # Niemals selbst gphoto2 starten — die Camera-Watchdog hat bereits eine
    # USB-Session offen, ein paralleler --auto-detect kollidiert. Stattdessen
    # den shared Status der Camera-Instanz lesen.
    cam_state = camera_mod.latest_status()
    camera_ok = bool(cam_state.get("available"))

    try:
        usage = shutil.disk_usage(config.BASE_DIR)
        free_mb  = int(usage.free  / 1024 / 1024)
        total_mb = int(usage.total / 1024 / 1024)
    except Exception:
        free_mb = 0
        total_mb = 0

    return jsonify({
        "camera_ok":   camera_ok,
        "free_mb":     free_mb,
        "free_gb":     round(free_mb / 1024, 1),
        "total_mb":    total_mb,
        "total_gb":    round(total_mb / 1024, 1),
        # Sichtbarkeitsgefiltert: sonst verrät die Zahl dem Gastgeber, dass
        # auf der Box noch Fotos fremder Vermietungen liegen.
        "photo_count": len(_visible_photo_list()),
        "event_name":  config.cfg.get("event_name", "Fotobox"),
    })


# Auslieferungswerte aus config.py. Nicht importiert, sondern dupliziert:
# aendert der Owner den Default in _DEFAULTS, soll die Warnung fuer den ALTEN
# Wert trotzdem greifen.
# Direkt aus config._DEFAULTS abgeleitet, damit die Warnung nicht ins Leere
# laeuft, sobald sich ein Auslieferungswert aendert.
_SHIPPED_LABELS = {"admin_pin": "Admin-PIN", "host_pin": "Gastgeber-PIN",
                   "wifi_password": "WLAN-Passwort"}
_SHIPPED_DEFAULTS = {k: config.default_value(k) for k in _SHIPPED_LABELS}


def _insecure_defaults() -> list:
    """Welche sicherheitsrelevanten Werte sind noch Auslieferungszustand?

    Zusaetzlich gemeldet werden zu kurze PINs. Der Login prueft die Laenge
    bewusst nicht nach — eine vierstellige PIN aus einer config.json von vor
    `config.PIN_MIN_LEN` funktioniert weiter, sonst sperrt ein Update den
    Besitzer aus. Unsicher ist sie trotzdem, also gehoert sie in die Warnung.
    """
    out = []
    for key, label in _SHIPPED_LABELS.items():
        value = config.cfg.get(key) or ""
        if value == _SHIPPED_DEFAULTS[key]:
            out.append(label)
        elif key.endswith("_pin") and 0 < len(value) < config.PIN_MIN_LEN:
            out.append(f"{label} (zu kurz)")
    return out


@app.route("/api/admin/config", methods=["GET", "POST"])
@_api_login_required
def api_admin_config():
    role = _session_role()
    is_admin = role == "admin"

    if request.method == "GET":
        # WLAN-Daten dürfen Host und Admin sehen — der Gastgeber soll für
        # seine Veranstaltung auch SSID/Passwort anpassen können. PINs bleiben
        # admin-only, sonst könnte der Host den Admin-PIN auslesen und sich
        # selbst hochstufen.
        out = {
            "event_name":         config.cfg.get("event_name", "Fotobox"),
            "subtitle":           config.cfg.get("subtitle", ""),
            "countdown_duration": config.cfg.get("countdown_duration", 3),
            "has_logo":           os.path.isfile(config.cfg.get("logo_path", "")),
            "wifi_ssid":          config.cfg.get("wifi_ssid", ""),
            "wifi_password":      config.cfg.get("wifi_password", ""),
            "theme":              dict(config.cfg.get("theme") or {}),
            "instagram_url":      config.cfg.get("instagram_url", ""),
            "booking_url":        config.cfg.get("booking_url", ""),
            # Warnung, solange Auslieferungs-PINs aktiv sind. Der Admin-PIN
            # gibt "alle Fotos loeschen" frei — auf einem offenen Gaeste-WLAN
            # ist "1234" faktisch kein Schutz.
            "insecure_defaults":  _insecure_defaults(),
            "print_enabled":      bool(config.cfg.get("print_enabled", True)),
            "printer_name":       config.cfg.get("printer_name", ""),
            "print_copies":       int(config.cfg.get("print_copies", 1)),
            "print_mode":         config.cfg.get("print_mode", "auto"),
            "role":               role,
        }
        if is_admin:
            out.update({
                "admin_pin": config.cfg.get("admin_pin", "1234"),
                "host_pin":  config.cfg.get("host_pin", ""),
            })
        return jsonify(out)

    data = request.get_json(silent=True) or request.form

    # Beide Rollen: event_name, subtitle, countdown, WLAN, theme
    try:
        countdown = int(data.get("countdown_duration",
                                 config.cfg["countdown_duration"]))
        countdown = max(1, min(10, countdown))
    except (ValueError, TypeError):
        countdown = config.cfg["countdown_duration"]

    # WLAN serverseitig pruefen. Die Client-Pruefung in AdminWifi.tsx laesst
    # sich per direktem POST umgehen — und ein zu kurzes Passwort faellt sonst
    # erst beim naechsten Boot auf, wenn hotspot.start() den AP verweigert und
    # niemand mehr ins Netz kommt.
    new_ssid = (data.get("wifi_ssid") or config.cfg["wifi_ssid"]).strip()
    new_pw   = data.get("wifi_password", config.cfg["wifi_password"]) or ""
    if not 1 <= len(new_ssid.encode("utf-8")) <= 32:
        return jsonify(ok=False,
                       error="WLAN-Name muss 1–32 Zeichen lang sein"), 400
    if not 8 <= len(new_pw) <= 63:
        return jsonify(ok=False,
                       error="WLAN-Passwort muss 8–63 Zeichen lang sein (WPA2)"), 400
    wifi_changed = (new_ssid != config.cfg.get("wifi_ssid")
                    or new_pw != config.cfg.get("wifi_password"))

    # Hinweis: instagram_url + booking_url sind Owner-Settings — werden vom
    # Box-Besitzer direkt in config.json gepflegt und nie über die Admin-API
    # geschrieben, damit Mieter sie nicht überschreiben können.
    config.cfg.update({
        "event_name":         (data.get("event_name") or config.cfg["event_name"]).strip(),
        "subtitle":           str(data.get("subtitle", config.cfg.get("subtitle", ""))).strip()[:80],
        "countdown_duration": countdown,
        "wifi_ssid":          new_ssid,
        "wifi_password":      new_pw,
    })

    # Theme: Hex-Strings + panel_alpha. Ungültige Werte werden ignoriert,
    # damit ein kaputter Color-Picker das Theme nicht in Stücke schießt.
    new_theme = data.get("theme")
    if isinstance(new_theme, dict):
        cleaned: dict = {}
        for k, v in new_theme.items():
            if k == "panel_alpha":
                try:
                    cleaned[k] = max(0, min(255, int(v)))
                except (ValueError, TypeError):
                    pass
            elif isinstance(v, str) and len(v) == 7 and v.startswith("#"):
                try:
                    int(v[1:], 16)
                    cleaned[k] = v.upper()
                except ValueError:
                    pass
        if cleaned:
            merged = dict(config.cfg.get("theme") or {})
            merged.update(cleaned)
            config.cfg["theme"] = merged

    # PIN-Verwaltung bleibt admin-only — vom Host-Request still ignoriert.
    if is_admin:
        for pin_key in ("admin_pin", "host_pin"):
            new_pin = data.get(pin_key)
            if new_pin is None:
                continue
            new_pin = new_pin.strip()
            # Leerer host_pin = Gastgeber-Login deaktivieren. admin_pin darf
            # nie leer sein, sonst sperrt sich der Admin selbst aus.
            if pin_key == "host_pin" and new_pin == "":
                config.cfg["host_pin"] = ""
                continue
            if not config.PIN_MIN_LEN <= len(new_pin) <= config.PIN_MAX_LEN:
                return jsonify(
                    ok=False,
                    error=f"PIN muss {config.PIN_MIN_LEN}–{config.PIN_MAX_LEN} "
                          "Zeichen lang sein"), 400
            config.cfg[pin_key] = new_pin

    # Druckeinstellungen: admin-only. Der Drucker gehoert dem Box-Besitzer,
    # ein Mieter soll ihn nicht umstellen koennen.
    if is_admin:
        if "print_enabled" in data:
            config.cfg["print_enabled"] = bool(data.get("print_enabled"))
        if "printer_name" in data:
            config.cfg["printer_name"] = str(data.get("printer_name") or "").strip()[:128]
        if "print_copies" in data:
            try:
                config.cfg["print_copies"] = max(1, min(9, int(data.get("print_copies"))))
            except (TypeError, ValueError):
                pass
        if "print_mode" in data:
            mode = str(data.get("print_mode") or "auto").lower()
            if mode in ("auto", "cover", "fit"):
                config.cfg["print_mode"] = mode
        # Zustand sofort neu ermitteln, damit die Oberflaeche nicht den alten
        # Cache-Wert zeigt und der Result-Screen den Knopf richtig setzt.
        try:
            import printing
            printing.refresh_status(config.cfg)
        except Exception as exc:
            logger.warning("Druckerstatus nach Konfigwechsel: %s", exc)

    config.save_config(config.cfg)

    # Geaenderte WLAN-Daten muessen in den laufenden AP. Ohne das zeigte der
    # Boxschirm sofort die neue SSID (ui.py laedt die Config sekuendlich neu),
    # waehrend der AP weiter die alte sendete — die angezeigten Zugangsdaten
    # waren schlicht falsch und niemand kam rein.
    restarting = wifi_changed and _restart_hotspot_async()
    return jsonify(ok=True, wifi_restarting=restarting)


def _restart_hotspot_async() -> bool:
    """Startet den Hotspot im Hintergrund mit den neuen Zugangsdaten neu.

    Im Hintergrund, weil nmcli mehrere Sekunden braucht und der Browser des
    Admins sonst in einen Timeout liefe — die Antwort muss RAUS, bevor der AP
    faellt, sonst sieht der Admin nur einen Verbindungsabbruch ohne Erklaerung.
    """
    if not _bind_all:
        # Kein Hotspot-Betrieb (Setup per --no-hotspot): nichts neu zu starten.
        return False
    try:
        import hotspot
    except ImportError:
        return False

    def _worker():
        try:
            # Kurz warten, damit die HTTP-Antwort den Client sicher erreicht,
            # bevor ihm das WLAN unter den Fuessen weggezogen wird.
            time.sleep(1.5)
            logger.info("WLAN geändert — Hotspot wird neu gestartet")
            hotspot.stop()
            if hotspot.start():
                logger.info("Hotspot mit neuen Zugangsdaten aktiv")
            else:
                logger.error("Hotspot-Neustart fehlgeschlagen — alte Verbindung "
                             "ist weg, Box braucht ggf. einen Neustart")
        except Exception as exc:
            logger.error("Hotspot-Neustart: %s", exc, exc_info=True)

    threading.Thread(target=_worker, daemon=True).start()
    return True


@app.route("/api/admin/printers")
@_api_admin_required
def api_admin_printers():
    """Verfuegbare CUPS-Drucker + aktueller Zustand fuer die Admin-Oberflaeche."""
    try:
        import printing
        return jsonify(ok=True,
                       printers=printing.list_printers(),
                       default=printing.default_printer(),
                       status=printing.refresh_status(config.cfg))
    except Exception as exc:
        logger.error("Druckerliste: %s", exc, exc_info=True)
        # Bewusst 200: die Admin-Seite soll "kein Drucksystem" anzeigen
        # koennen, statt in den generischen Fehler-Toast zu laufen.
        return jsonify(ok=False, error="Drucksystem nicht erreichbar",
                       printers=[], default=None,
                       status={"available": False, "printer": None,
                               "message": "Drucksystem nicht erreichbar"}), 200


_ALLOWED_LOGO_FORMATS = {"PNG", "JPEG", "GIF", "WEBP", "BMP"}
# Pi 4B hat 4 GB RAM — 50 MP gibt PIL ~200 MB; alles drüber ist Bomb-Verdacht.
_MAX_LOGO_PIXELS = 50_000_000


@app.route("/api/admin/logo", methods=["POST"])
@_api_login_required
def api_admin_logo():
    logo_file = request.files.get("logo")
    if not logo_file or not logo_file.filename:
        return jsonify(ok=False, error="Keine Datei ausgewählt"), 400

    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:
        return jsonify(ok=False, error="PIL nicht verfügbar"), 500

    # 1. Format-Check über verify() — verbraucht den Stream, danach reseek
    try:
        with Image.open(logo_file) as probe:
            fmt = (probe.format or "").upper()
            w, h = probe.size
            if fmt not in _ALLOWED_LOGO_FORMATS:
                return jsonify(ok=False,
                               error=f"Format {fmt or '?'} nicht unterstützt"), 400
            if w * h > _MAX_LOGO_PIXELS:
                return jsonify(ok=False,
                               error="Bild zu groß (max. 50 Megapixel)"), 400
            probe.verify()
    except (UnidentifiedImageError, Image.DecompressionBombError):
        return jsonify(ok=False, error="Ungültige oder zu große Bilddatei"), 400
    except Exception as exc:
        logger.warning("Logo-Verify: %s", exc)
        return jsonify(ok=False, error="Ungültige Bilddatei"), 400

    # 2. Konvertieren + Speichern. Auf Display-Größe runterskalieren — die UI
    # zeigt das Logo eh nur mit max 80 px Höhe.
    logo_path = os.path.join(config.BASE_DIR, "Layout", "logo.png")
    os.makedirs(os.path.dirname(logo_path), exist_ok=True)
    try:
        logo_file.seek(0)
        with Image.open(logo_file) as img:
            img.load()
            if img.height > 200:
                ratio = 200 / img.height
                img = img.resize((int(img.width * ratio), 200), Image.LANCZOS)
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            img.save(logo_path, "PNG", optimize=True)
    except (Image.DecompressionBombError, MemoryError):
        return jsonify(ok=False, error="Bild zu groß zum Verarbeiten"), 400
    except Exception as exc:
        logger.error("Logo-Save: %s", exc)
        return jsonify(ok=False, error="Speichern fehlgeschlagen"), 500

    config.cfg["logo_path"] = logo_path
    config.save_config(config.cfg)
    return jsonify(ok=True)


@app.route("/api/admin/logo/preview")
def api_admin_logo_preview():
    logo_path = config.cfg.get("logo_path", "")
    if not logo_path or not os.path.isfile(logo_path):
        abort(404)
    return send_file(logo_path)


@app.route("/api/admin/event/new", methods=["POST"])
@_api_admin_required
def api_admin_new_event():
    """Das laufende Event abschliessen und einen frischen Ordner festnageln.

    Deckt die Faelle ab, die `event_session_hours` (18 h) nicht loest: eine
    Vermietung ueber zwei Tage landet sonst je nach Pause in einem oder in
    zwei Ordnern, und zwei Feiern am selben Tag mit gleichem Namen immer im
    selben. Ein geaenderter `event_name` trennt zwar ebenfalls — aber eben nur,
    wenn der Name sich wirklich aendert.

    Loescht nichts, die bisherigen Fotos bleiben in ihrem Ordner. Gaeste und
    Gastgeber sehen danach aber nur noch das neue Event (_may_see_all_events),
    darum ist das eine Admin- und keine Gastgeber-Aktion.
    """
    previous = events.current_event_folder(config.cfg)
    folder = events.start_new_event(config.cfg)
    return jsonify(ok=True, folder=folder, previous=previous)


def _purge_event(event: str) -> int:
    """Loescht alle Fotos eines Events samt Thumbnails, Previews und Ordner.

    Rueckgabe: Anzahl entfernter Fotos.
    """
    pic_dir = _pic_dir()
    removed = 0
    for ev, fname in list(_photo_list(event)):
        try:
            os.remove(os.path.join(pic_dir, ev, fname))
            removed += 1
        except OSError as exc:
            logger.warning("Foto '%s/%s' nicht geloescht: %s", ev, fname, exc)
    # Ohne die abgeleiteten Dateien liefert /thumb bzw. /preview das geloeschte
    # Bild weiter aus — dieselbe Falle wie in api_delete.
    for derived in (os.path.join(_thumb_dir(), event),
                    os.path.join(_preview_dir(), event)):
        shutil.rmtree(derived, ignore_errors=True)
    # Den Ordner selbst nur weg, wenn wirklich nichts mehr drin liegt: eine
    # fremde Datei soll nicht stillschweigend mit verschwinden.
    ev_dir = os.path.join(pic_dir, event)
    try:
        if os.path.isdir(ev_dir) and not os.listdir(ev_dir):
            os.rmdir(ev_dir)
    except OSError:
        pass
    return removed


@app.route("/api/admin/event/<event>/delete", methods=["POST"])
@_api_admin_required
def api_admin_delete_event(event: str):
    """Ein komplettes Event wegraeumen. Admin-Session genuegt, kein PIN.

    Bewusst ohne den "LOESCHEN"-Tippzwang aus /api/admin/reset: der trifft
    *alle* Events und ist die Stufe darueber. Hier steht der Ordner in der URL,
    das Frontend fragt einmal mit Foto-Anzahl nach, und SameSite=Lax deckt den
    CSRF-Fall ab.

    Trifft es das laufende Event, legt die naechste Aufnahme den Ordner ueber
    events.current_event_dir() neu an — der Pin in .active_event.json bleibt
    absichtlich stehen, damit die Feier nicht mitten drin den Ordner wechselt.
    """
    if not events.is_safe_event(event):
        return jsonify(ok=False, error="Ungueltiger Event-Ordner"), 400
    if not os.path.isdir(os.path.join(_pic_dir(), event)):
        return jsonify(ok=False, error="Event nicht gefunden"), 404
    removed = _purge_event(event)
    logger.info("Event geloescht: %s (%d Fotos)", event, removed)
    return jsonify(ok=True, removed=removed)


def _purge_all_photos() -> int:
    """Alle Fotos, leere Event-Ordner und abgeleitete Bilder wegraeumen.

    Rueckgabe: Anzahl entfernter Fotos. Previews liegen unter `_thumb_dir()`
    und gehen ueber den rekursiven Walk mit weg.
    """
    pic_dir = _pic_dir()
    td = _thumb_dir()
    removed = 0
    for ev, fname in list(_photo_list()):
        try:
            os.remove(os.path.join(pic_dir, ev, fname))
            removed += 1
        except Exception:
            pass
    # Leere Event-Ordner entfernen
    for entry in list(os.listdir(pic_dir)) if os.path.isdir(pic_dir) else []:
        full = os.path.join(pic_dir, entry)
        if os.path.isdir(full):
            try:
                if not os.listdir(full):
                    os.rmdir(full)
            except OSError:
                pass
    # Thumbnails komplett wegräumen (rekursiv)
    if os.path.isdir(td):
        for root, dirs, files in os.walk(td, topdown=False):
            for fname in files:
                try:
                    os.remove(os.path.join(root, fname))
                except OSError:
                    pass
            for d in dirs:
                try:
                    os.rmdir(os.path.join(root, d))
                except OSError:
                    pass
    return removed


@app.route("/api/admin/reset", methods=["POST"])
@_api_admin_required
def api_admin_reset():
    data = request.get_json(silent=True) or request.form
    confirm = (data.get("confirm") or "").strip()
    if confirm != "LOESCHEN":
        return jsonify(ok=False, error="Bestätigung fehlgeschlagen"), 400

    removed = _purge_all_photos()
    logger.info("Admin-Reset: %d Fotos gelöscht", removed)
    return jsonify(ok=True, removed=removed)


def _truthy(value) -> bool:
    """Checkbox-Flag aus JSON (`true`) oder Formular (`"on"`)."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "on", "yes")


def _reset_logo() -> None:
    """Das Mieter-Logo entfernen.

    Geloescht wird nur `Layout/logo.png` — dorthin schreibt jeder Upload
    (api_admin_logo). `Layout/logo_default.png` bleibt unberuehrt, und
    ui._load_logo faellt genau darauf zurueck, sobald der Slot leer ist.
    """
    path = os.path.join(config.BASE_DIR, "Layout", "logo.png")
    config.cfg["logo_path"] = path
    try:
        os.remove(path)
    except FileNotFoundError:
        pass                        # war nie eins da — nichts zu tun
    except OSError as exc:
        logger.warning("Logo '%s' nicht entfernt: %s", path, exc)


_HANDOVER_STEPS = ("branding", "logo", "photos", "new_event")


@app.route("/api/admin/handover", methods=["POST"])
@_api_admin_required
def api_admin_handover():
    """Die Box fuer die naechste Vermietung vorbereiten.

    Bewusst ein Knopf und kein Automatismus: ein Reset, der von selbst
    zuschlaegt, trifft irgendwann ein laufendes Event. Der Aufrufer haakt an,
    was weg soll — nicht gesetzte Schritte passieren nicht.

    WLAN und PINs bleiben aussen vor. Die vergibt der Box-Besitzer, und ein
    Reset auf die Auslieferungswerte waere ein Rueckschritt: danach stuende
    wieder "1234" drin, worueber _insecure_defaults zu Recht warnt.
    """
    data = request.get_json(silent=True) or request.form
    steps = {k: _truthy(data.get(k)) for k in _HANDOVER_STEPS}

    if not any(steps.values()):
        return jsonify(ok=False, error="Nichts ausgewählt"), 400
    # Derselbe Tippzwang wie /api/admin/reset, aber nur wenn wirklich Fotos
    # drankommen: alle uebrigen Schritte sind wiederherstellbar.
    if steps["photos"] and (data.get("confirm") or "").strip() != "LOESCHEN":
        return jsonify(ok=False, error="Bestätigung fehlgeschlagen"), 400

    if steps["branding"]:
        for key in config.HANDOVER_FIELDS:
            config.cfg[key] = config.default_value(key)
    if steps["logo"]:
        _reset_logo()
    if steps["branding"] or steps["logo"]:
        config.save_config(config.cfg)

    removed = _purge_all_photos() if steps["photos"] else 0
    # Erst nach dem Loeschen: sonst zeigt der Pin auf einen Ordner, der gerade
    # weggeraeumt wurde, und das naechste Foto landet unter dem Namen der
    # vorigen Vermietung.
    folder = events.start_new_event(config.cfg) if steps["new_event"] else None

    logger.info("Uebergabe vorbereitet (%s), %d Fotos geloescht",
                ", ".join(k for k, v in steps.items() if v), removed)
    return jsonify(ok=True, done=steps, removed=removed, folder=folder)


# ── Server starten ─────────────────────────────────────────────────────────────

def _prewarm_thumbnails():
    """Generiert Thumbnails für alle existierenden Fotos im Hintergrund.
    Sonst stallt der erste Galerie-Aufruf wenn 50+ Bilder gleichzeitig
    durch PIL gejagt werden."""
    files = _photo_list()
    if not files:
        return
    logger.info("Thumbnail-Prewarm: %d Bilder werden vorab generiert", len(files))
    for ev, f in files:
        if not _running:
            return
        try:
            _make_thumb(ev, f)
        except Exception:
            pass
    logger.info("Thumbnail-Prewarm fertig")


_running = True


def _can_bind(host: str, port: int) -> bool:
    """Probe-Bind: prüft ob (host, port) verfügbar ist OHNE den Server
    zu starten. Wirft den eigentlichen Bind-Versuch von waitress zuvor
    ab, damit wir eine klare Fehlermeldung loggen können statt eines
    stummen Thread-Crashs."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((host, port))
        return True
    except (PermissionError, OSError):
        return False
    finally:
        s.close()


_bind_all: Optional[bool] = None


def set_bind_all(value: bool):
    """Legt fest ob der Galerie-Server an alle Interfaces bindet.

    main.py ruft das VOR preflight() mit dem *effektiven* Hotspot-Zustand auf
    (config-Flag UND nicht per --no-hotspot unterdrueckt). Ohne diesen Aufruf
    faellt _default_host() auf das reine Config-Flag zurueck, damit
    Standalone-Starts sich verhalten wie bisher.
    """
    global _bind_all
    _bind_all = bool(value)


def _default_host() -> str:
    """0.0.0.0 nur wenn der Hotspot wirklich laufen soll.

    Sonst 127.0.0.1 — im Heim-WLAN (Setup-Betrieb per --no-hotspot) waere die
    Galerie samt Admin-Panel sonst ungewollt fuer das ganze Netz offen.
    """
    want = _bind_all if _bind_all is not None else config.cfg.get("hotspot_enabled")
    return "0.0.0.0" if want else "127.0.0.1"


def preflight() -> int:
    """Prüft synchron ob der konfigurierte Port gebunden werden kann.

    Muss VOR run() (im Thread) und VOR der QR-Code-Erstellung in der UI
    laufen, damit gallery_url konsistent ist falls auf einen anderen Port
    zurückgefallen werden muss.

    Auf <1024 braucht's setcap auf der venv-Python (install.sh richtet
    das ein). Fehlt der setcap, fallen wir der Reihe nach auf 5000 → 8080
    zurück und passen config.cfg an, sonst crasht waitress später stumm
    im Thread und der Service ist tot ohne Hinweis im Log.

    Rückgabe: der tatsächlich nutzbare Port.
    """
    host = _default_host()
    port = config.cfg.get("gallery_port", 80)
    if _can_bind(host, port):
        return port
    # Reihenfolge: User-Konfig zuerst (oben), dann harte Fallbacks.
    # Doppelte werden gefiltert damit wir den User-Port nicht erneut probieren.
    for fallback in (p for p in (5000, 8080) if p != port):
        if _can_bind(host, fallback):
            logger.error(
                "Galerie: Port %d kann nicht gebunden werden (setcap auf "
                "venv-Python fehlt? './install.sh' erneut laufen lassen). "
                "Fallback auf Port %d — Captive-Portal funktioniert in "
                "diesem Modus NICHT.", port, fallback)
            config.cfg["gallery_port"] = fallback
            config.cfg["gallery_url"] = config.build_gallery_url(
                config.cfg.get("hotspot_ip", "192.168.4.1"), fallback)
            return fallback
    # Alle Fallbacks belegt → Server wird gleich stumm crashen, aber
    # wenigstens steht's klar im Log.
    logger.error(
        "Galerie: weder Port %d noch 5000/8080 verfügbar — "
        "Galerie startet wahrscheinlich nicht.", port)
    return port


def run(host: Optional[str] = None, port: Optional[int] = None):
    """Startet den Galerie-Server.

    Wenn host nicht gesetzt wird, hängt das Bind davon ab ob der Hotspot aktiv
    ist: mit Hotspot bindet der Server an alle Interfaces (Gäste sollen ja die
    Galerie über WLAN erreichen), ohne Hotspot nur an 127.0.0.1 — sonst wäre
    die Galerie ungewollt im Heim-WLAN exponiert.
    """
    global _running
    if host is None:
        host = _default_host()
    port = port or config.cfg["gallery_port"]

    log_dir = os.path.join(config.BASE_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    # Rotierend statt unbegrenzt: bei 40 Gaesten mit 8-Sekunden-Polling
    # schreibt werkzeug sonst ueber einen Abend hunderte MB auf die SD-Karte.
    # 5 MB x 3 reicht zur Fehlersuche und deckelt bei 20 MB.
    fh = RotatingFileHandler(os.path.join(log_dir, "gallery.log"),
                             maxBytes=5 * 1024 * 1024, backupCount=3,
                             encoding="utf-8")
    fh.setLevel(logging.INFO)
    logging.getLogger("werkzeug").addHandler(fh)

    # Thumbnails parallel zum Server-Start vorab generieren
    threading.Thread(target=_prewarm_thumbnails, daemon=True).start()

    logger.info("Galerie: http://%s:%d", host, port)

    # Waitress (Production-WSGI) — deutlich schneller als Flasks Dev-Server.
    # Fallback auf Flask wenn waitress nicht installiert ist.
    try:
        from waitress import serve
        serve(app, host=host, port=port, threads=8,
              ident="Fotobox-Gallery",
              channel_timeout=120)
    except ImportError:
        logger.warning("waitress nicht installiert — fallback auf Flask Dev-Server")
        app.run(host=host, port=port, threaded=True, use_reloader=False)
    except (PermissionError, OSError) as exc:
        # Sollte nach _can_bind nicht mehr passieren — nur als Sicherheitsnetz.
        logger.error("Galerie-Server-Bind unerwartet gescheitert: %s", exc)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    os.makedirs(_pic_dir(), exist_ok=True)
    events.migrate_flat_photos(config.cfg)
    # Preflight wechselt config.cfg["gallery_port"] auf 5000/8080 falls 80
    # nicht bindbar ist (Windows-Dev ohne Admin) — sonst stirbt waitress stumm.
    port = preflight()
    run(host="127.0.0.1", port=port)


