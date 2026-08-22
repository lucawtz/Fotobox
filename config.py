import json
import logging
import os
import threading

logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# Mieter-spezifische Felder — alles was über das Admin-Panel veränderbar
# ist. NUR diese Werte landen in der lokalen config.json (gitignored).
# Alle Owner-Defaults (idle_timeout, instagram_url, gpio_pins, hotspot_*,
# polaroid_frames usw.) leben in _DEFAULTS unten, sind im Repo getrackt
# und kommen automatisch via `git pull` aufs Pi.
_MIETER_FIELDS = frozenset({
    "event_name",
    "subtitle",
    "countdown_duration",
    "wifi_ssid",
    "wifi_password",
    "admin_pin",
    "host_pin",
    "logo_path",
    "theme",
})

# Box-spezifische Einstellungen: gehoeren nicht dem Mieter, unterscheiden sich
# aber von Geraet zu Geraet (welcher Drucker haengt dran?) und muessen deshalb
# genauso in die lokale config.json — ein `git pull` darf sie nicht ueberschreiben.
_BOX_FIELDS = frozenset({
    "print_enabled",
    "printer_name",
    "print_copies",
    "print_mode",
})

# Alles was persistiert wird. Der Rest lebt ausschliesslich in _DEFAULTS und
# kommt per git aufs Pi.
_PERSISTED_FIELDS = _MIETER_FIELDS | _BOX_FIELDS

_DEFAULTS: dict = {
    "wifi_ssid": "Fotobox",
    "wifi_password": "fotobox123",
    "event_name": "Fotobox",
    "subtitle": "Drück einen Knopf",
    "countdown_duration": 3,
    "max_photos": 500,
    "gpio_pins": {"left": 17, "trigger": 27, "right": 22},
    "logo_path": "Layout/logo.png",
    "admin_pin": "1234",
    "host_pin": "0000",
    "idle_timeout": 0,
    "slide_duration_ms": 5000,
    "gallery_port": 80,
    # Owner-Default: die Box IST der Access-Point. Zum Einrichten per
    # VNC/Heim-WLAN stattdessen `main.py --no-hotspot` starten — das
    # laesst den Galerie-Server auch auf 127.0.0.1 gebunden.
    "hotspot_enabled": True,
    "hotspot_ip": "192.168.4.1",
    "hotspot_interface": "wlan0",
    # Wie lange eine Event-Session laeuft, bevor automatisch ein neuer
    # Ordner beginnt. 18h deckt "Feier bis 02:00" ab, trennt aber den
    # naechsten Tag zuverlaessig. Siehe events.current_event_folder().
    "event_session_hours": 18,
    "picture_dir": "Picture_Box",
    # Gaeste UND Gastgeber sehen nur das laufende Event. Auf True stellen,
    # wenn die Galerie bewusst als Archiv ueber alle Feiern dienen soll — dann
    # sieht aber jeder im Fotobox-WLAN auch die Fotos der letzten
    # Veranstaltung. Nur der Admin sieht unabhaengig davon immer alles.
    "gallery_guests_see_all": False,
    "capture_device": 0,
    "theme": {
        "bg_top":         "#D5BB99",
        "bg_bottom":      "#B89A75",
        "sidebar_bg":     "#3D2818",
        "sidebar_text":   "#FFFFFF",
        "sidebar_dim":    "#A09080",
        "logo_circle":    "#F5EBD8",
        "logo_text":      "#A36B3F",
        "panel_bg":       "#1F1812",
        "panel_border":   "#7A5A35",
        "polaroid_frame": "#FAEED9",
        "polaroid_pin":   "#C24838",
        "live_bg":        "#1A140F",
        "live_outer":     "#5A3A1C",
        "live_inner":     "#C9A06A",
        "accent":         "#D4A86A",
        "accent_dim":     "#9B7840",
        "text":           "#FFFFFF",
        "panel_alpha":    255,
    },
    "actions": [
        {"id": "foto",    "label": "Foto",    "key": "trigger", "color": "#D4A86A", "filled": True},
        {"id": "collage", "label": "Collage", "key": "right",   "color": "#A66BB5"},
    ],
    "polaroid_frames": [[567, 255, -5], [1098, 256, 5], [1633, 257, 12]],
    "polaroid_photo_size": [310, 295],
    # 16:9 — passt zum HDMI-Output der Kamera, sodass kein Letterbox entsteht.
    "live_view_rect": [510, 540, 800, 450],
    "instagram_url": "https://www.instagram.com/lucawtz",
    "booking_url":   "https://bytebots.de/",
    # Erste Zeile der Booking-Reihe in der Sidebar; darunter zeigt ui.py
    # automatisch die Domain aus booking_url. "Termine buchen" allein war
    # eine Sackgasse — es nennt kein Ziel, das der Gast ansteuern koennte.
    "booking_label": "Fotobox mieten",
    "disk_warn_mb": 500,
    # Harte Grenze: darunter wird die Aufnahme verweigert, statt gphoto2
    # ins Leere laufen zu lassen. Ein RAW+JPEG-Paar der 700D braucht ~30 MB,
    # 150 MB lassen also noch Luft fuer Thumbnails und Logs.
    "disk_block_mb": 150,
    "thumbnail_max_age_days": 30,
    "photo_max_age_days": 7,
    # ── Drucken ────────────────────────────────────────────────────────────
    # printer_name leer = CUPS-Standarddrucker (sonst exakter Name aus
    # `lpstat -p`). print_media und print_options haengen vom Treiber ab —
    # die passenden Werte liefert `lpoptions -p <drucker> -l`, siehe README.
    "print_enabled": True,
    "printer_name": "",
    "print_copies": 1,
    "print_media": "Postcard",        # Canon Selphy CP: 100x148 mm
    "print_size_mm": [148, 100],      # Querformat, Breite x Hoehe
    "print_dpi": 300,
    # auto = randlos wenn das Seitenverhaeltnis fast passt (Einzelfoto),
    # sonst vollstaendig mit weissem Rand (2x2-Collage wuerde sonst
    # oben und unten abgeschnitten). Alternativ "cover" oder "fit".
    "print_mode": "auto",
    "print_options": [],
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
            # Nur Mieter-Felder aus der lokalen config.json überlagern —
            # so bleibt z.B. ein neuer idle_timeout-Default aus config.py
            # nach `git pull` wirksam, statt von einer alten persistierten
            # config.json überschrieben zu werden.
            for k in _PERSISTED_FIELDS:
                if k in saved:
                    data[k] = saved[k]
        except Exception as exc:
            logger.warning("config.json unlesbar: %s — nutze Defaults", exc)

    # Relative Pfade → absolut
    if not os.path.isabs(data["logo_path"]):
        data["logo_path"] = os.path.join(BASE_DIR, data["logo_path"])
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

    Es werden NUR Mieter-Felder geschrieben — alle Owner-Defaults stammen
    aus config.py und bleiben unberührt. So überschreibt die persistierte
    config.json keine Code-Updates aus git.
    """
    saveable = {k: v for k, v in data.items() if k in _PERSISTED_FIELDS}
    if "logo_path" in saveable and isinstance(saveable["logo_path"], str):
        if os.path.isabs(saveable["logo_path"]):
            try:
                saveable["logo_path"] = os.path.relpath(saveable["logo_path"], BASE_DIR)
            except ValueError:
                pass
        # Plattform-neutral speichern: Backslashes (Windows) auf Forward-Slashes,
        # damit die config.json zwischen Dev-Maschine und Pi austauschbar bleibt.
        saveable["logo_path"] = saveable["logo_path"].replace("\\", "/")

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
