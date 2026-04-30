import logging
import os
import secrets
import shutil
import threading
import time
from collections import deque
from datetime import datetime
from functools import wraps
from typing import Optional
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from flask import (Flask, Response, abort, jsonify, request,
                   send_file, session)

import camera as camera_mod
import config
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


app = Flask(__name__, template_folder=os.path.join(config.BASE_DIR, "templates"))
app.secret_key = _load_or_create_secret_key()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # 16 MB für Logo-Uploads — alles drüber wird von Flask abgewiesen,
    # ohne dass der Request gelesen wird.
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,
)

_EXTS = {".jpg", ".jpeg", ".png"}
_thumb_lock = threading.Lock()

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

_PORTAL_PATHS = {
    "/hotspot-detect.html",         # iOS, macOS
    "/library/test/success.html",
    "/generate_204",                # Android, Chrome
    "/gen_204",
    "/ncsi.txt",                    # Windows
    "/connecttest.txt",
    "/redirect",
    "/success.txt",                 # Firefox
    "/canonical.html",
    "/check_network_status.txt",
}


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
    cfg_ip = config.cfg.get("hotspot_ip", "192.168.4.1")
    if not host or _looks_like_ip(host) or host == "localhost" or host.endswith(".local"):
        return None
    # Hierher kommen wir nur via DNS-Hijack (Hostname statt IP).
    from flask import redirect
    return redirect(f"http://{cfg_ip}/", code=302)


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


@app.route("/img/<event>/<filename>")
def img(event, filename):
    path = _safe_path(event, filename)
    if path is None:
        abort(404)
    response = send_file(path)
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


@app.route("/thumb/<event>/<filename>")
def thumb(event, filename):
    t = _make_thumb(event, filename)
    if t is None:
        abort(404)
    response = send_file(t)
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


@app.route("/preview/<event>/<filename>")
def preview(event, filename):
    """1280px-Vorschau für die Detail-Ansicht — viel kleiner als Original."""
    p = _make_preview(event, filename)
    if p is None:
        abort(404)
    response = send_file(p)
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


@app.route("/download/<event>/<filename>")
def download(event, filename):
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

    pic_dir = _pic_dir()
    items: list[tuple[str, str]] = []
    for ev, f in _photo_list(event_filter):
        items.append((f"{ev}/{f}", os.path.join(pic_dir, ev, f)))
    if not items:
        abort(404)

    zip_name = f"{_zip_safe_name(event_filter)}.zip"

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
    return jsonify(count=len(_photo_list(event_filter)))


@app.route("/api/events")
def api_events():
    return jsonify({
        "active": events.current_event_folder(config.cfg),
        "events": events.list_events(config.cfg),
        "event_name": config.cfg.get("event_name", "Fotobox"),
    })


@app.route("/api/photos")
def api_photos():
    event_filter = request.args.get("event") or None
    pic_dir = _pic_dir()
    out = []
    for ev, f in _photo_list(event_filter):
        try:
            st = os.stat(os.path.join(pic_dir, ev, f))
            out.append({
                "event":    ev,
                "filename": f,
                "mtime":    st.st_mtime,
                "size":     st.st_size,
            })
        except OSError:
            continue
    return jsonify({
        "event_name":   config.cfg.get("event_name", "Fotobox"),
        "active_event": events.current_event_folder(config.cfg),
        "filter":       event_filter,
        "count":        len(out),
        "photos":       out,
    })


@app.route("/api/delete/<event>/<filename>", methods=["POST"])
def api_delete(event: str, filename: str):
    # Eingeloggte Admins dürfen ohne PIN-Abfrage löschen, normale Gäste
    # müssen den PIN mitschicken — beides geschützt durch das Login-Lockout
    # (selber Bucket wie /api/admin/login).
    ip = _client_ip()
    if not session.get("admin_logged_in"):
        locked = _login_check_locked(ip)
        if locked is not None:
            return jsonify(ok=False,
                           error=f"Zu viele Fehlversuche – bitte {locked}s warten"), 429
        pin = request.form.get("pin", "").strip()
        expected = config.cfg.get("admin_pin", "1234")
        if not pin or not secrets.compare_digest(pin, expected):
            _login_record_failure(ip)
            return jsonify(ok=False, error="Falscher PIN"), 403
        _login_record_success(ip)
    path = _safe_path(event, filename)
    if path is None:
        return jsonify(ok=False, error="Datei nicht gefunden"), 404
    try:
        os.remove(path)
    except Exception as exc:
        logger.error("Foto löschen: %s", exc)
        return jsonify(ok=False, error="Löschen fehlgeschlagen"), 500
    thumb_path = os.path.join(_thumb_dir(), event, filename)
    if os.path.exists(thumb_path):
        try:
            os.remove(thumb_path)
        except OSError:
            pass
    # Falls Event-Ordner jetzt leer ist, entfernen
    ev_dir = os.path.join(_pic_dir(), event)
    try:
        if os.path.isdir(ev_dir) and not os.listdir(ev_dir):
            os.rmdir(ev_dir)
    except OSError:
        pass
    logger.info("Foto gelöscht: %s/%s", event, filename)
    return jsonify(ok=True)


# ── Admin-SPA-Catch-all ────────────────────────────────────────────────────────

@app.route("/admin", defaults={"_path": ""})
@app.route("/admin/<path:_path>")
def admin_spa(_path: str):
    if _spa_enabled():
        return send_file(SPA_INDEX)
    return _no_spa_response()


# ── Admin JSON-API ─────────────────────────────────────────────────────────────

def _api_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return jsonify(ok=False, error="Unauthorized"), 401
        return f(*args, **kwargs)
    return decorated


@app.route("/api/admin/me")
def api_admin_me():
    return jsonify(authenticated=bool(session.get("admin_logged_in")))


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
    expected = config.cfg.get("admin_pin", "1234")
    # secrets.compare_digest gegen Timing-Attacks
    if pin and secrets.compare_digest(pin, expected):
        session["admin_logged_in"] = True
        _login_record_success(ip)
        return jsonify(ok=True)

    _login_record_failure(ip)
    return jsonify(ok=False, error="Falscher PIN"), 401


@app.route("/api/admin/logout", methods=["POST"])
def api_admin_logout():
    session.clear()
    return jsonify(ok=True)


@app.route("/api/admin/status")
@_api_admin_required
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
        "photo_count": len(_photo_list()),
        "event_name":  config.cfg.get("event_name", "Fotobox"),
    })


@app.route("/api/admin/config", methods=["GET", "POST"])
@_api_admin_required
def api_admin_config():
    if request.method == "GET":
        return jsonify({
            "event_name":         config.cfg.get("event_name", "Fotobox"),
            "wifi_ssid":          config.cfg.get("wifi_ssid", ""),
            "wifi_password":      config.cfg.get("wifi_password", ""),
            "countdown_duration": config.cfg.get("countdown_duration", 3),
            "admin_pin":          config.cfg.get("admin_pin", "1234"),
            "has_logo":           os.path.isfile(config.cfg.get("logo_path", "")),
        })

    data = request.get_json(silent=True) or request.form
    try:
        countdown = int(data.get("countdown_duration",
                                 config.cfg["countdown_duration"]))
        countdown = max(1, min(10, countdown))
    except (ValueError, TypeError):
        countdown = config.cfg["countdown_duration"]

    config.cfg.update({
        "event_name":         (data.get("event_name") or config.cfg["event_name"]).strip(),
        "wifi_ssid":          (data.get("wifi_ssid")  or config.cfg["wifi_ssid"]).strip(),
        "wifi_password":      data.get("wifi_password", config.cfg["wifi_password"]) or "",
        "countdown_duration": countdown,
    })

    new_pin = (data.get("admin_pin") or "").strip()
    if new_pin:
        if len(new_pin) < 4 or len(new_pin) > 12:
            return jsonify(ok=False,
                           error="PIN muss 4–12 Zeichen lang sein"), 400
        config.cfg["admin_pin"] = new_pin

    config.save_config(config.cfg)
    return jsonify(ok=True)


_ALLOWED_LOGO_FORMATS = {"PNG", "JPEG", "GIF", "WEBP", "BMP"}
# Pi 4B hat 4 GB RAM — 50 MP gibt PIL ~200 MB; alles drüber ist Bomb-Verdacht.
_MAX_LOGO_PIXELS = 50_000_000


@app.route("/api/admin/logo", methods=["POST"])
@_api_admin_required
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


@app.route("/api/admin/reset", methods=["POST"])
@_api_admin_required
def api_admin_reset():
    data = request.get_json(silent=True) or request.form
    confirm = (data.get("confirm") or "").strip()
    if confirm != "LOESCHEN":
        return jsonify(ok=False, error="Bestätigung fehlgeschlagen"), 400

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
    logger.info("Admin-Reset: %d Fotos gelöscht", removed)
    return jsonify(ok=True, removed=removed)


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


def run(host: Optional[str] = None, port: Optional[int] = None):
    """Startet den Galerie-Server.

    Wenn host nicht gesetzt wird, hängt das Bind davon ab ob der Hotspot aktiv
    ist: mit Hotspot bindet der Server an alle Interfaces (Gäste sollen ja die
    Galerie über WLAN erreichen), ohne Hotspot nur an 127.0.0.1 — sonst wäre
    die Galerie ungewollt im Heim-WLAN exponiert.
    """
    global _running
    if host is None:
        host = "0.0.0.0" if config.cfg.get("hotspot_enabled") else "127.0.0.1"
    port = port or config.cfg["gallery_port"]

    log_dir = os.path.join(config.BASE_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    fh = logging.FileHandler(os.path.join(log_dir, "gallery.log"))
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    os.makedirs(_pic_dir(), exist_ok=True)
    events.migrate_flat_photos(config.cfg)
    run(host="127.0.0.1")


