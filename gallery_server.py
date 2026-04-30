import logging
import os
import shutil
import subprocess
import threading
from datetime import datetime
from functools import wraps
from typing import Optional
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from flask import (Flask, Response, abort, jsonify, render_template,
                   request, send_file, session)

import config
import events

logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder=os.path.join(config.BASE_DIR, "templates"))
app.secret_key = os.urandom(24)

_EXTS = {".jpg", ".jpeg", ".png"}
_thumb_lock = threading.Lock()

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
                img.save(thumb)
            return thumb
        except Exception as exc:
            logger.warning("Thumbnail '%s/%s': %s", event, filename, exc)
            return None


# ── Galerie-Routen ─────────────────────────────────────────────────────────────

@app.route("/")
def gallery():
    if _spa_enabled():
        return send_file(SPA_INDEX)
    return render_template("gallery.html", photos=[f for _, f in _photo_list()],
                           event_name=config.cfg.get("event_name", "Fotobox"))


@app.route("/photo/<path:_filename>")
def photo(_filename):
    if _spa_enabled():
        return send_file(SPA_INDEX)
    abort(404)


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
    event_filter = request.args.get("event") or None
    pic_dir = _pic_dir()
    items: list[tuple[str, str]] = []
    for ev, f in _photo_list(event_filter):
        items.append((f"{ev}/{f}", os.path.join(pic_dir, ev, f)))
    if not items:
        abort(404)

    if event_filter:
        zip_name = f"{_zip_safe_name(event_filter)}.zip"
    else:
        date = datetime.now().strftime("%Y-%m-%d")
        zip_name = f"Fotobox_{_zip_safe_name(config.cfg.get('event_name', 'Fotobox'))}_{date}.zip"

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
    pin = request.form.get("pin", "").strip()
    if pin != config.cfg.get("admin_pin", "1234"):
        return jsonify(ok=False, error="Falscher PIN"), 403
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
    if session.get("admin_logged_in"):
        return render_template("admin_dashboard.html",
                               cfg=config.cfg,
                               event_name=config.cfg.get("event_name", "Fotobox"),
                               msg=None, error=None)
    return render_template("admin_login.html", error=None)


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


@app.route("/api/admin/login", methods=["POST"])
def api_admin_login():
    pin = (request.form.get("pin") or
           (request.get_json(silent=True) or {}).get("pin", "")).strip()
    if pin and pin == config.cfg.get("admin_pin", "1234"):
        session["admin_logged_in"] = True
        return jsonify(ok=True)
    return jsonify(ok=False, error="Falscher PIN"), 401


@app.route("/api/admin/logout", methods=["POST"])
def api_admin_logout():
    session.clear()
    return jsonify(ok=True)


@app.route("/api/admin/status")
@_api_admin_required
def api_admin_status():
    camera_ok = False
    try:
        r = subprocess.run(["gphoto2", "--auto-detect"],
                           capture_output=True, text=True, timeout=5)
        camera_ok = "usb" in r.stdout.lower()
    except Exception:
        pass

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
    if new_pin and len(new_pin) >= 4:
        config.cfg["admin_pin"] = new_pin

    config.save_config(config.cfg)
    return jsonify(ok=True)


@app.route("/api/admin/logo", methods=["POST"])
@_api_admin_required
def api_admin_logo():
    logo_file = request.files.get("logo")
    if not logo_file or logo_file.filename == "":
        return jsonify(ok=False, error="Keine Datei ausgewählt"), 400
    try:
        from PIL import Image
        img = Image.open(logo_file)
        img.verify()
    except Exception:
        return jsonify(ok=False, error="Ungültige Bilddatei"), 400

    logo_path = os.path.join(config.BASE_DIR, "Layout", "logo.png")
    os.makedirs(os.path.dirname(logo_path), exist_ok=True)
    logo_file.seek(0)
    with Image.open(logo_file) as img:
        img.save(logo_path, "PNG")

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


def run(host: str = "0.0.0.0", port: int = None):
    global _running
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


