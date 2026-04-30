import json
import logging
import os
import threading

logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

_DEFAULTS: dict = {
    "wifi_ssid": "Fotobox",
    "wifi_password": "fotobox123",
    "event_name": "Fotobox",
    "countdown_duration": 3,
    "max_photos": 500,
    "gpio_pins": {"left": 17, "trigger": 27, "right": 22},
    "logo_path": "Layout/logo.png",
    "admin_pin": "1234",
    "host_pin": "0000",
    "idle_timeout": 300,
    "slide_duration_ms": 5000,
    "gallery_port": 80,
    "hotspot_enabled": False,
    "hotspot_ip": "192.168.4.1",
    "hotspot_interface": "wlan0",
    "picture_dir": "Picture_Box",
    "capture_device": 0,
    "overlay_path": "Layout/Overlay_Allgemein.png",
    "polaroid_frames": [[567, 255, -5], [1098, 256, 5], [1633, 257, 12]],
    "polaroid_photo_size": [310, 295],
    "live_view_rect": [440, 600, 1040, 450],
    "overlay_button_foto": [1475, 700, 385, 100],
    "overlay_button_collage": [1475, 840, 385, 110],
    "disk_warn_mb": 500,
    "thumbnail_max_age_days": 30,
    "camera_keepalive_s": 25,
    "camera_output_mode": "3",
}


def load_config() -> dict:
    data = {k: (list(v) if isinstance(v, (list, tuple)) else
                dict(v) if isinstance(v, dict) else v)
            for k, v in _DEFAULTS.items()}

    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            data.update(saved)
        except Exception as exc:
            logger.warning("config.json unlesbar: %s — nutze Defaults", exc)

    # Relative Pfade → absolut
    for key in ("logo_path", "overlay_path"):
        if not os.path.isabs(data[key]):
            data[key] = os.path.join(BASE_DIR, data[key])
    if not os.path.isabs(data["picture_dir"]):
        data["picture_dir"] = os.path.join(BASE_DIR, data["picture_dir"])

    # Laufzeit-Werte
    data["gallery_url"] = build_gallery_url(data["hotspot_ip"], data["gallery_port"])
    data["thumbnail_dir"] = os.path.join(BASE_DIR, "thumbnails")

    return data


def build_gallery_url(host: str, port: int) -> str:
    """Baut die Gallery-URL — Port 80 wird weggelassen, damit der QR-Code
    ein cleanes 'http://192.168.4.1' zeigt statt 'http://192.168.4.1:80'."""
    return f"http://{host}" if int(port) == 80 else f"http://{host}:{port}"


_save_lock = threading.Lock()


def save_config(data: dict):
    """Atomic save: tmp-Datei schreiben + os.replace, damit ein Stromausfall
    während des Schreibens keine korrupte config.json hinterlässt.
    """
    saveable = {k: v for k, v in data.items()
                if k not in ("gallery_url", "thumbnail_dir")}
    for key in ("logo_path", "overlay_path", "picture_dir"):
        if key in saveable and os.path.isabs(saveable[key]):
            try:
                saveable[key] = os.path.relpath(saveable[key], BASE_DIR)
            except ValueError:
                pass
        # Plattform-neutral speichern: Backslashes (Windows) auf Forward-Slashes,
        # damit die config.json zwischen Dev-Maschine und Pi austauschbar bleibt.
        if key in saveable and isinstance(saveable[key], str):
            saveable[key] = saveable[key].replace("\\", "/")

    tmp_path = CONFIG_PATH + ".tmp"
    with _save_lock:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(saveable, f, indent=2, ensure_ascii=False)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp_path, CONFIG_PATH)
    logger.info("config.json gespeichert")


cfg: dict = load_config()
