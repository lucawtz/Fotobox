import logging
import os
import shutil
import subprocess
import threading
from functools import wraps
from typing import Optional

from flask import (Flask, abort, jsonify, redirect, render_template,
                   request, send_file, session, url_for)

import config

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


def _safe_path(filename: str) -> Optional[str]:
    if os.sep in filename or "/" in filename or ".." in filename:
        return None
    path = os.path.join(_pic_dir(), filename)
    return path if os.path.isfile(path) else None


def _photo_list() -> list[str]:
    try:
        files = [f for f in os.listdir(_pic_dir())
                 if os.path.splitext(f)[1].lower() in _EXTS]
        files.sort(key=lambda f: os.path.getmtime(os.path.join(_pic_dir(), f)),
                   reverse=True)
        return files
    except FileNotFoundError:
        return []


def _make_thumb(filename: str) -> Optional[str]:
    td = _thumb_dir()
    thumb = os.path.join(td, filename)
    with _thumb_lock:
        if os.path.exists(thumb):
            return thumb
        src = _safe_path(filename)
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
            logger.warning("Thumbnail '%s': %s", filename, exc)
            return None


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login_page"))
        return f(*args, **kwargs)
    return decorated


# ── Galerie-Routen ─────────────────────────────────────────────────────────────

@app.route("/")
def gallery():
    if _spa_enabled():
        return send_file(SPA_INDEX)
    photos = _photo_list()
    for f in photos:
        threading.Thread(target=_make_thumb, args=(f,), daemon=True).start()
    return render_template("gallery.html", photos=photos,
                           event_name=config.cfg.get("event_name", "Fotobox"))


@app.route("/photo/<filename>")
def photo(filename):
    if _spa_enabled():
        return send_file(SPA_INDEX)
    if _safe_path(filename) is None:
        abort(404)
    return render_template("photo.html", filename=filename,
                           event_name=config.cfg.get("event_name", "Fotobox"))


@app.route("/assets/<path:fname>")
def spa_assets(fname: str):
    if not _spa_enabled():
        abort(404)
    full = os.path.normpath(os.path.join(SPA_DIST, "assets", fname))
    if not full.startswith(os.path.abspath(SPA_DIST)) or not os.path.isfile(full):
        abort(404)
    return send_file(full)


@app.route("/img/<filename>")
def img(filename):
    path = _safe_path(filename)
    if path is None:
        abort(404)
    return send_file(path)


@app.route("/thumb/<filename>")
def thumb(filename):
    t = _make_thumb(filename)
    if t is None:
        abort(404)
    return send_file(t)


@app.route("/download/<filename>")
def download(filename):
    path = _safe_path(filename)
    if path is None:
        abort(404)
    return send_file(path, as_attachment=True)


@app.route("/api/count")
def api_count():
    return jsonify(count=len(_photo_list()))


@app.route("/api/photos")
def api_photos():
    files = _photo_list()
    out = []
    pic_dir = _pic_dir()
    for f in files:
        try:
            st = os.stat(os.path.join(pic_dir, f))
            out.append({"filename": f, "mtime": st.st_mtime, "size": st.st_size})
        except OSError:
            continue
        threading.Thread(target=_make_thumb, args=(f,), daemon=True).start()
    return jsonify({
        "event_name": config.cfg.get("event_name", "Fotobox"),
        "count": len(out),
        "photos": out,
    })


@app.route("/api/delete/<filename>", methods=["POST"])
def api_delete(filename: str):
    pin = request.form.get("pin", "").strip()
    if pin != config.cfg.get("admin_pin", "1234"):
        return jsonify(ok=False, error="Falscher PIN"), 403
    path = _safe_path(filename)
    if path is None:
        return jsonify(ok=False, error="Datei nicht gefunden"), 404
    try:
        os.remove(path)
    except Exception as exc:
        logger.error("Foto löschen: %s", exc)
        return jsonify(ok=False, error="Löschen fehlgeschlagen"), 500
    thumb_path = os.path.join(_thumb_dir(), filename)
    if os.path.exists(thumb_path):
        try:
            os.remove(thumb_path)
        except OSError:
            pass
    logger.info("Foto gelöscht: %s", filename)
    return jsonify(ok=True)


@app.route("/delete/<filename>", methods=["POST"])
def delete_photo(filename):
    pin = request.form.get("pin", "").strip()
    if pin != config.cfg.get("admin_pin", "1234"):
        return render_template("photo.html", filename=filename,
                               event_name=config.cfg.get("event_name", "Fotobox"),
                               error="Falscher PIN")
    path = _safe_path(filename)
    if path is None:
        abort(404)
    try:
        os.remove(path)
    except Exception as exc:
        logger.error("Foto löschen: %s", exc)
        abort(500)
    thumb_path = os.path.join(_thumb_dir(), filename)
    if os.path.exists(thumb_path):
        os.remove(thumb_path)
    logger.info("Foto gelöscht: %s", filename)
    return redirect(url_for("gallery"))


# ── Admin-Routen ───────────────────────────────────────────────────────────────

@app.route("/admin")
def admin_root():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("admin_login_page"))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login_page():
    error = None
    if request.method == "POST":
        pin = request.form.get("pin", "").strip()
        if pin == config.cfg.get("admin_pin", "1234"):
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        error = "Falscher PIN"
    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login_page"))


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    msg   = request.args.get("msg")
    error = request.args.get("error")
    return render_template("admin_dashboard.html",
                           cfg=config.cfg,
                           event_name=config.cfg.get("event_name", "Fotobox"),
                           msg=msg, error=error)


@app.route("/admin/config", methods=["POST"])
@admin_required
def admin_config():
    form = request.form
    try:
        countdown = int(form.get("countdown_duration",
                                 config.cfg["countdown_duration"]))
        countdown = max(1, min(10, countdown))
    except ValueError:
        countdown = config.cfg["countdown_duration"]

    config.cfg.update({
        "event_name":        form.get("event_name", config.cfg["event_name"]).strip(),
        "wifi_ssid":         form.get("wifi_ssid",  config.cfg["wifi_ssid"]).strip(),
        "wifi_password":     form.get("wifi_password", config.cfg["wifi_password"]),
        "countdown_duration": countdown,
    })

    new_pin = form.get("admin_pin", "").strip()
    if len(new_pin) >= 4:
        config.cfg["admin_pin"] = new_pin

    config.save_config(config.cfg)
    return redirect(url_for("admin_dashboard") + "?msg=Einstellungen+gespeichert")


@app.route("/admin/logo", methods=["POST"])
@admin_required
def admin_logo():
    logo_file = request.files.get("logo")
    if not logo_file or logo_file.filename == "":
        return redirect(url_for("admin_dashboard") + "?error=Keine+Datei+ausgewählt")
    try:
        from PIL import Image
        img = Image.open(logo_file)
        img.verify()
    except Exception:
        return redirect(url_for("admin_dashboard") + "?error=Ungültige+Bilddatei")

    logo_path = os.path.join(config.BASE_DIR, "Layout", "logo.png")
    os.makedirs(os.path.dirname(logo_path), exist_ok=True)
    logo_file.seek(0)
    from PIL import Image
    with Image.open(logo_file) as img:
        img.save(logo_path, "PNG")

    config.cfg["logo_path"] = logo_path
    config.save_config(config.cfg)
    return redirect(url_for("admin_dashboard") + "?msg=Logo+hochgeladen")


@app.route("/admin/reset", methods=["POST"])
@admin_required
def admin_reset():
    confirm = request.form.get("confirm", "").strip()
    if confirm != "LOESCHEN":
        return redirect(url_for("admin_dashboard") + "?error=Bestätigung+fehlgeschlagen")

    pic_dir = _pic_dir()
    td = _thumb_dir()
    removed = 0
    for fname in list(_photo_list()):
        try:
            os.remove(os.path.join(pic_dir, fname))
            removed += 1
        except Exception:
            pass
    if os.path.isdir(td):
        for fname in os.listdir(td):
            try:
                os.remove(os.path.join(td, fname))
            except Exception:
                pass
    logger.info("Admin-Reset: %d Fotos gelöscht", removed)
    return redirect(url_for("admin_dashboard") + f"?msg={removed}+Fotos+gelöscht")


@app.route("/admin/status")
@admin_required
def admin_status():
    camera_ok = False
    try:
        r = subprocess.run(["gphoto2", "--auto-detect"],
                           capture_output=True, text=True, timeout=5)
        camera_ok = "usb" in r.stdout.lower()
    except Exception:
        pass

    try:
        free_mb = int(shutil.disk_usage(config.BASE_DIR).free / 1024 / 1024)
    except Exception:
        free_mb = 0

    return jsonify({
        "camera_ok":   camera_ok,
        "free_mb":     free_mb,
        "free_gb":     round(free_mb / 1024, 1),
        "photo_count": len(_photo_list()),
        "event_name":  config.cfg.get("event_name", "Fotobox"),
    })


# ── Server starten ─────────────────────────────────────────────────────────────

def run(host: str = "0.0.0.0", port: int = None):
    port = port or config.cfg["gallery_port"]

    log_dir = os.path.join(config.BASE_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    fh = logging.FileHandler(os.path.join(log_dir, "gallery.log"))
    fh.setLevel(logging.INFO)
    logging.getLogger("werkzeug").addHandler(fh)

    logger.info("Galerie: http://%s:%d", host, port)
    app.run(host=host, port=port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    os.makedirs(_pic_dir(), exist_ok=True)
    run(host="127.0.0.1")


