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

# Laenge von Admin- und Gastgeber-PIN. Vier Stellen sind 10.000 Moeglichkeiten
# — auf einem offenen Gaeste-WLAN, in dem jeder die Galerie-URL kennt, ist das
# selbst mit Login-Lockout duenn. Sechs Stellen sind Faktor 100 mehr und noch
# gut merkbar. Der Login prueft die Laenge NICHT nach: eine kuerzere PIN aus
# einer aelteren config.json funktioniert weiter, sonst sperrt ein Update den
# Besitzer aus. gallery_server._insecure_defaults() warnt stattdessen.
PIN_MIN_LEN = 6
PIN_MAX_LEN = 12

# Zeichengrenzen fuer event_name / subtitle.
#
# Gemessen in ui.py gegen die Sidebar-Breite (SIDEBAR_W - 30 = 290 px) und die
# Lesbarkeitsuntergrenzen EVENT_MIN_PT / SUB_MIN_PT — unter denen liest der
# Gast aus 2 m Abstand nichts mehr:
#
#   Event-Name  22 pt fett, 2 Zeilen -> 51 Zeichen gemischt, 43 in Versalien
#   Untertitel  16 pt,      3 Zeilen -> 65 Zeichen gemischt, 62 in Versalien
#
# Genommen ist jeweils der Versalien-Fall, abgerundet. Laenger heisst seit
# ui._hard_wrap nicht mehr "kleiner", sondern "mitten im Wort umgebrochen und
# mit … abgeschnitten" — deshalb wird hier begrenzt statt geschrumpft.
#
# Hier und nicht in ui.py, damit der Galerie-Server sie lesen kann, ohne
# pygame zu importieren.
EVENT_NAME_MAX_CHARS = 40
SUBTITLE_MAX_CHARS   = 60

# Was eine Vermietung "einfaerbt" und bei der Uebergabe an den naechsten
# Gastgeber zurueck auf Auslieferungszustand kann. Bewusst OHNE wifi_* und
# *_pin: die vergibt der Box-Besitzer, und ein Reset auf "1234"/"fotobox123"
# waere ein Rueckschritt (siehe gallery_server._insecure_defaults).
# logo_path fehlt ebenfalls — der Pfad bleibt, geloescht wird die Datei.
HANDOVER_FIELDS = ("event_name", "subtitle", "countdown_duration", "theme")

_DEFAULTS: dict = {
    "wifi_ssid": "Fotobox",
    "wifi_password": "fotobox123",
    "event_name": "Fotobox",
    "subtitle": "Drück einen Knopf",
    "countdown_duration": 3,
    "max_photos": 500,
    "gpio_pins": {"left": 17, "trigger": 27, "right": 22},
    "logo_path": "Layout/logo.png",
    "admin_pin": "123456",
    "host_pin": "000000",
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
    # Der Platz, den die Live-Vorschau hoechstens einnehmen darf — nicht
    # ihre Groesse: ui._live_geometry legt das Kamerabild
    # seitenverhaeltnistreu hinein und zieht den Rahmen um das Ergebnis.
    # Die Zahlen sind der freie Bereich des Homescreens, ausgemessen gegen
    # seine Nachbarn und beidseitig um gut 10 px Luft eingerueckt:
    #
    #   links   Sidebar bis x=320          rechts  Action-Buttons ab x=1530
    #   oben    Polaroids bis y=485        unten   Status-Bar ab y=1042
    #
    # (Polaroid-Unterkante inklusive Drehung und Schattenversatz, Status-Bar
    # aus der Schrifthoehe — beides in ui.py, nicht frei waehlbar.)
    # LIVE_OUTER_W=12 fuer den Rahmen ist in der Luft schon eingerechnet.
    # Die Hoehe ist der bindende Wert, und sie ist bewusst NICHT bis an die
    # Nachbarn aufgezogen: der Streifen gibt 533 px her, genommen sind 450.
    # Ein 16:9-Signal wird damit 800x450 gross und behaelt oben wie unten
    # gut 40 px Luft. Randvoll sah es gedraengt aus, obwohl nichts kollidiert
    # — die Luft ist hier Absicht, kein uebrig gebliebener Platz.
    # Die Breite bleibt Reserve fuer breitere Formate.
    "live_view_rect": [345, 539, 1160, 450],
    "instagram_url": "https://www.instagram.com/lucawtz",
    # Instagrams eigener QR-Code, in der App im eigenen Profil exportierbar.
    # Leer = ui.py zeichnet stattdessen das Instagram-Glyph.
    # Das Bild darf so bleiben wie die App es ausspuckt: ui.py schneidet
    # Rand und Handle-Schriftzug selbst weg und macht das Weiss transparent.
    "instagram_qr_path": "Layout/instagram_qr.png",
    "booking_url":   "https://bytebots.de/",
    # Erste Zeile der Booking-Reihe in der Sidebar; darunter zeigt ui.py
    # automatisch die Domain aus booking_url. "Termine buchen" allein war
    # eine Sackgasse — es nennt kein Ziel, das der Gast ansteuern koennte.
    "booking_label": "Fotobox mieten",
    # Selbst gestalteter QR-Code auf booking_url. Anders als beim
    # Galerie-Code ist das gefahrlos: booking_url zeigt nach draussen und
    # wird nie zur Laufzeit umgeschrieben, waehrend gallery_url von
    # gallery_server.preflight() auf einen Fallback-Port gezogen werden
    # kann — ein fest gezeichneter Galerie-Code zeigte dann ins Leere.
    # Leer = ui.py zeichnet weiter Kalender-Glyph und Domain.
    #
    # Wie instagram_qr_path ein lokaler Dateipfad, KEINE URL: die Box haengt
    # am Event in ihrem eigenen WLAN ohne Internet und kann nichts laden.
    # Die Adresse selbst steht in booking_url. Die Datei liegt wie das Logo
    # in Layout/ und wird nicht mitcommittet — auf einer frischen Kopie
    # fehlt sie, dann faellt ui.py auf das Glyph zurueck und sagt es im Log.
    "booking_qr_path": "Layout/booking_qr.png",
    # Taster-Pins. Ein Wert darf null sein — dann ist dieser Taster nicht
    # verbaut, und die UI blendet seine Aktionen aus statt einen toten Knopf
    # zu zeigen. Mit zwei Tastern ist trigger+right die bessere Wahl: dann
    # bleiben Foto, Collage, Nochmal und Drucken erreichbar, und "Zurueck"
    # erledigt der 10-Sekunden-Timer des Result-Screens. Fehlt left, weckt
    # trigger+right gleichzeitig die Kamera.
    "gpio_pins": {"left": 17, "trigger": 27, "right": 22},
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
    # Index aus `gphoto2 --get-config output`, NICHT der Klartextwert. Welche
    # Nummer TFT+PC meint, unterscheidet sich je nach Modell — steht der
    # falsche drin, kommt aus der Kamera weder auf HDMI noch auf dem Display
    # ein Bild.
    "camera_output_mode": "3",
    # Wie lange ein Halte-Prozess laeuft, bevor er sich beendet und sofort neu
    # gestartet wird. Er haelt die PTP-Sitzung und damit den Live-View offen;
    # gphoto2 braucht dafuer eine Obergrenze. Beim Wechsel fehlt das Live-Bild
    # fuer einen Prozessstart lang, also gut eine Sekunde.
    "camera_hold_session_s": 1800,
    # Wie viele Sekunden vor dem Ende des Countdowns ausgeloest wird. Zwischen
    # dem gphoto2-Aufruf und der Belichtung liegt eine Verzoegerung, die die
    # Kamera vorgibt und die Box nicht wegbekommt — auf der EOS 700D per EXIF
    # gemessen 1,1 s im Betrieb, rund 1,9 s beim ersten Schuss nach Ruhe. Ohne
    # Vorlauf faellt der Verschluss erst, wenn "Lächeln!" schon wieder weg ist.
    # Etwas unter der gemessenen Verzoegerung ist Absicht: lieber kurz nach dem
    # "Lächeln!" ausloesen als davor.
    "capture_lead_s": 0.9,
    # Holt den Live-View selbsttaetig zurueck, wenn ueber Sekunden kein Bild
    # ueber HDMI kommt. Auf false bleibt es beim manuellen Wecken per Q bzw.
    # Tasterkombination.
    "camera_auto_wake": True,
}


def default_value(key: str):
    """Frische Kopie des Auslieferungswerts.

    Listen und Dicts werden kopiert, damit ein Aufrufer `_DEFAULTS` nicht
    versehentlich mitaendert — `cfg["theme"]` wird an mehreren Stellen
    in-place gepatcht.
    """
    v = _DEFAULTS[key]
    return (list(v) if isinstance(v, (list, tuple)) else
            dict(v) if isinstance(v, dict) else v)


def load_config() -> dict:
    data = {k: default_value(k) for k in _DEFAULTS}

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
    # Optionale QR-Bilder: leer ist erlaubt, relative Pfade haengen an
    # BASE_DIR. Beide werden gleich behandelt, damit sie nicht auseinander
    # laufen, wenn einer davon angefasst wird.
    for _qr_key in ("instagram_qr_path", "booking_qr_path"):
        _rel = data.get(_qr_key) or ""
        if _rel and not os.path.isabs(_rel):
            data[_qr_key] = os.path.join(BASE_DIR, _rel)
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


def reload_persisted(target: dict) -> bool:
    """Liest config.json neu und uebernimmt die Mieter-/Box-Felder in
    `target`. Rueckgabe: ob sich etwas geaendert hat.

    Gebraucht, weil Admin-Panel und Box nicht zwingend derselbe Prozess
    sind. Im Dev-Setup laeuft das Panel unter dev_server.py, die Box unter
    main.py — jeder haelt sein eigenes cfg im Speicher, und eine Aenderung
    im einen erreicht den anderen nur ueber die Datei. Das Logo fiel dabei
    nie auf, weil es am Datei-Zeitstempel erkannt wird; das Theme lebt
    dagegen ausschliesslich im Dict.

    Nur persistierte Felder werden uebernommen. Laufzeitwerte wie
    gallery_url bleiben unberuehrt — die kann preflight() auf einen
    Fallback-Port gezogen haben, und ein Neuaufbau aus hotspot_ip und
    gallery_port wuerde das stillschweigend zuruecksetzen.
    """
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            stored = json.load(f)
    except FileNotFoundError:
        return False
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("config.json nicht lesbar (%s) — behalte den "
                       "aktuellen Stand", exc)
        return False
    if not isinstance(stored, dict):
        return False

    changed = False
    for key, value in stored.items():
        if key not in _PERSISTED_FIELDS:
            continue
        if key in ("logo_path", "instagram_qr_path", "booking_qr_path"):
            if isinstance(value, str) and value and not os.path.isabs(value):
                value = os.path.join(BASE_DIR, value)
        if target.get(key) != value:
            target[key] = value
            changed = True
    return changed


cfg: dict = load_config()
