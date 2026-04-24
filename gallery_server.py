import logging
import os
import threading

from flask import Flask, abort, jsonify, render_template, send_file

import config

logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder=os.path.join(config.BASE_DIR, "templates"))

_THUMB_DIR = os.path.join(config.BASE_DIR, ".thumbs")
_EXTS = {".jpg", ".jpeg", ".png"}
_thumb_lock = threading.Lock()


def _safe_path(filename: str):
    if os.sep in filename or "/" in filename or ".." in filename:
        return None
    path = os.path.join(config.PICTURE_PATH, filename)
    return path if os.path.isfile(path) else None


def _photo_list():
    try:
        files = [
            f for f in os.listdir(config.PICTURE_PATH)
            if os.path.splitext(f)[1].lower() in _EXTS
        ]
        files.sort(
            key=lambda f: os.path.getmtime(os.path.join(config.PICTURE_PATH, f)),
            reverse=True,
        )
        return files
    except FileNotFoundError:
        return []


def _make_thumb(filename: str):
    thumb = os.path.join(_THUMB_DIR, filename)
    with _thumb_lock:
        if os.path.exists(thumb):
            return thumb
        src = _safe_path(filename)
        if src is None:
            return None
        try:
            from PIL import Image
            os.makedirs(_THUMB_DIR, exist_ok=True)
            with Image.open(src) as img:
                img.thumbnail((400, 400))
                img.save(thumb)
            return thumb
        except Exception as exc:
            logger.warning("Thumbnail '%s': %s", filename, exc)
            return None


@app.route("/")
def gallery():
    photos = _photo_list()
    for f in photos:
        threading.Thread(target=_make_thumb, args=(f,), daemon=True).start()
    return render_template("gallery.html", photos=photos)


@app.route("/photo/<filename>")
def photo(filename):
    if _safe_path(filename) is None:
        abort(404)
    return render_template("photo.html", filename=filename)


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
def count():
    return jsonify(count=len(_photo_list()))


def run(host: str = "0.0.0.0", port: int = None):
    port = port or config.GALLERY_PORT
    logger.info("Galerie-Server: http://%s:%d", host, port)
    app.run(host=host, port=port, threaded=True, use_reloader=False)
