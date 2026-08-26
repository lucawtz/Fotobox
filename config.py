import json
import logging
import os
import threading
from urllib.parse import quote

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
    "print_scale_pct",
    "print_bleed_mm",
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
    # Name, unter dem die Galerie im Fotobox-WLAN laeuft. Der Captive-DNS
    # beantwortet JEDEN Namen mit der Hotspot-IP (hotspot.py schreibt
    # 'address=/#/<ip>'), also loest dieser hier dort auf die Box auf.
    #
    # Er ist fuer die Gaeste da, die schon im WLAN haengen: der WLAN-QR
    # nuetzt ihnen nichts mehr, und eine IP tippt niemand freiwillig ab.
    #
    # '.internal' hat die ICANN 2024 ausdruecklich fuer private Netze
    # reserviert — die Endung wird nie an jemanden vergeben. Ein echter
    # Name wie '.box' gehoerte dagegen einem fremden Registry und koennte
    # ausserhalb des Hotspots eines Tages irgendwo landen.
    #
    # Leer = die Galerie laeuft wieder unter der nackten IP.
    "gallery_hostname": "fotobox.internal",
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
    # Aufloesung, die von der Capture-Card angefordert wird. NICHT optional:
    # ohne Anforderung nimmt cv2 den Standard des Geraets, und der ist bei der
    # MacroSilicon-Karte nach einer frischen USB-Anmeldung 640x480 — dort
    # liefert sie ein praktisch schwarzes Bild (gemessen: mittlere Helligkeit
    # 4 von 255, gegenueber einem sauberen Raumbild bei 1920x1080).
    #
    # Die UI verwirft schwarze Frames und zeigt "Bitte Display an der Kamera
    # einschalten" — obwohl Kamera und Live-View laufen. Genau dieser Zustand
    # trat nach jedem Stromzyklus auf: bis zum naechsten Neu-Einstecken blieb
    # das Format auf dem Geraet stehen, deshalb sah es aus wie ein
    # Kamera-Problem.
    #
    # [0, 0] = nichts anfordern (was das Geraet eben liefert).
    "capture_size": [1920, 1080],
    # Bildformat, das von der Capture-Card angefordert wird. Leer = das
    # nehmen, was sie von sich aus liefert.
    #
    # Auf der MacroSilicon-Karte ist ihr Standard YUYV, also unkomprimiert:
    # 1920x1080 mal 2 Byte sind gut 4 MB je Bild. Ueber USB 2.0 passen damit
    # nur 5 Bilder pro Sekunde durch — und die belegen 21 MB/s auf einem Bus,
    # den sich Kamera und Drucker teilen. Gemessen auf der Box:
    #
    #   YUYV   5,0 fps   15,6 % CPU   21 MB/s
    #   MJPG  30,0 fps   54,7 % CPU   ~2 MB/s
    #
    # MJPG ist je Bild sogar billiger (18,2 ms gegen 31,2 ms CPU) — die 54,7 %
    # kommen allein aus der sechsfachen Bildrate. Deshalb MJPG UND ein Deckel
    # per capture_fps.
    "capture_fourcc": "MJPG",
    # Bildrate, mit der der LiveReader liest. Nicht "so schnell wie moeglich":
    # jedes Bild kostet rund 18 ms CPU, und der Pi laeuft ohne aktive Kuehlung
    # bei knapp 80 Grad.
    #
    # 12 waren zu viel — auf der Box nachgemessen statt geschaetzt: der
    # LiveReader-Thread stieg von 15 % auf 37 % und der Pi von 78,8 auf
    # 81,3 Grad. Meine Rechnung hatte nur das Lesen (18 ms) gezaehlt; je Bild
    # kommt die Bewegungsmessung auf dem vollen 1080p-Frame dazu, zusammen
    # rund 30 ms.
    #
    # 6 fps kosten damit rund 18 % und liegen unter den 20 % des alten
    # YUYV-Betriebs — bei einem Bild mehr pro Sekunde und einem Zehntel der
    # USB-Last. Der eigentliche Gewinn von MJPG ist der Bus, nicht die Rate.
    #
    # Zum Ausrichten vor der Kamera reicht das: es ist ein Spiegel, kein
    # Video. Mit aktiver Kuehlung sind 15 bis 20 drin — der Regler dafuer ist
    # genau diese Zahl.
    "capture_fps": 6,
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
    #
    # Nachbarn, gegen die gemessen wurde:
    #
    #   links   Sidebar bis x=320          rechts  Action-Buttons ab x=1530
    #   oben    Polaroids bis y=485        unten   Status-Leiste ab y=1042
    #
    # Die Polaroid-Unterkante ist gerechnet, nicht geschaetzt: 346x373 px,
    # um bis zu 12 Grad gedreht, ergibt eine 437 px hohe Huellbox um den
    # Mittelpunkt bei y=257 — plus Schatten also rund 485. Die Status-Leiste
    # steht in _status_bar_height und haengt an der Schrifthoehe.
    #
    # Es bleiben 557 px. Der Rahmen (LIVE_OUTER_W=12) liegt AUSSERHALB des
    # Bildrechtecks und kostet 24 davon. Bei 3:2 bindet immer die Hoehe:
    #
    #   Hoehe 493  ->  Bild 739x493, Rahmen aussen 763x517
    #   davon Luft oben und unten je 20 px
    #
    # Frueher standen hier 450 px Hoehe mit je 41 px Luft — bewusst nicht
    # ausgereizt, weil randvoll gedraengt aussah. Das galt aber fuer ein
    # 16:9-Fenster, das die Breite ohnehin besser fuellte. Seit die Vorschau
    # das Fotoformat zeigt (live_view_aspect 3:2), ist die Hoehe der einzige
    # Hebel: 675x450 wurden so zu 739x493, ein Fuenftel mehr Flaeche.
    #
    # Die Breite bleibt Reserve fuer breitere Formate — bei 3:2 wird sie nie
    # gebraucht, das Bild sitzt mittig darin.
    "live_view_rect": [335, 517, 1180, 493],
    # Format, auf das die Live-Vorschau zugeschnitten wird — NICHT das Format
    # des Fotos, das bleibt, was die Kamera aufnimmt.
    #
    # 3:2 heisst: gar kein Zuschnitt. Die Vorschau zeigt genau den Ausschnitt,
    # der auch auf dem Foto landet — wer am Objektiv zoomt oder die Kamera
    # schwenkt, sieht das Ergebnis eins zu eins. Das ist die Vorgabe.
    #
    # Frueher stand hier 16:9, um die Breite des Vorschaufensters besser zu
    # fuellen: bei 450 px Hoehe sind das 800 statt 675 px. Der Preis war, dass
    # oben und unten etwas fehlte, was das Foto sehr wohl zeigt. Der damalige
    # Kommentar nannte das "die sichere Richtung" — wer in die Vorschau passt,
    # passt garantiert aufs Bild. Sicher ist das, ehrlich nicht: es beantwortet
    # die Frage "wie wird mein Bild" mit einem anderen Bild.
    #
    # Wer die Breite zurueck will, vergroessert live_view_rect in der Hoehe,
    # statt hier zu schneiden — bei 533 px Hoehe sind es wieder 800 px Breite.
    "live_view_aspect": [3, 2],
    # Was das Live-Signal GEOMETRISCH zeigt, nachdem die schwarzen Raender
    # weg sind — nicht, wie viele Pixel es hat.
    #
    # Die EOS 700D gibt ihr Live-Bild ueber HDMI anamorph aus: der Inhalt
    # misst nach dem Randschnitt 1771x890 (1,99), zeigt aber den 3:2-Sensor.
    # Alles darin ist damit um Faktor 1,33 in die Breite gezogen — auf der
    # Box nachgemessen ueber eine affine Schaetzung zwischen Live-Frame und
    # Foto derselben Szene: 1,36. Das Foto selbst ist unberuehrt davon und
    # kommt als 5184x3456 (3:2) aus der Kamera.
    #
    # Die Box rechnet daraus je Frame den Korrekturfaktor
    # (Quellformat / dieser Wert) und entzerrt beim ohnehin noetigen
    # Skalieren mit — das kostet nichts extra. Abgeleitet statt fest
    # eingetragen, damit eine andere Kamera oder ein anderer Randschnitt
    # nicht wieder eine handgemessene Zahl braucht.
    #
    # [0, 0] oder leer = keine Entzerrung (was die Quelle liefert).
    "live_source_aspect": [3, 2],
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
    # zu zeigen.
    #
    # Die Box hat ZWEI Taster, deshalb steht left auf null. Das ist keine
    # Sparmassnahme, sondern die Entscheidung aus IDEAS.md (22.08.2026): der
    # Collage-Stil gehoert ins Admin-Panel, nicht an einen dritten Knopf, weil
    # er eine Eigenschaft des Abends ist und keine des einzelnen Gastes. Damit
    # gab es fuer Taster drei keine Aufgabe mehr.
    #
    # trigger+right statt left+trigger, weil die Aktionen daran haengen: Foto
    # und Nochmal an trigger, Collage und Drucken an right. "Zurueck" verliert
    # dabei seinen Taster und braucht auch keinen — der 10-Sekunden-Timer des
    # Result-Screens tut dasselbe und sagt sogar, wann. Fehlt left, weckt
    # trigger+right gleichzeitig die Kamera.
    #
    # Beim Verdrahten: der LINKE Taster an GPIO 27, der RECHTE an GPIO 22.
    # ui._switch_hint beschriftet die Knoepfe nach dieser Reihenfolge, andersherum
    # angeschlossen zeigt der Schirm auf den falschen Taster.
    "gpio_pins": {"left": None, "trigger": 27, "right": 22},
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
    # StpBorderless: der Gutenprint-Treiber des Selphy steht von Haus aus auf
    # False und schrumpft das Bild per StpiShrinkOutput=Shrink in den
    # bedruckbaren Bereich — es kam also mit weissem Rand heraus, egal was
    # prepare() vorher aufs Papierformat gerechnet hatte. Welche Optionen der
    # Treiber kennt, zeigt `lpoptions -p <drucker> -l` (siehe README).
    "print_options": ["StpBorderless=True"],
    # Feinjustierung gegen den Bleed: randlos heisst beim Gutenprint-Treiber
    # "auf eine Flaeche rechnen, die groesser als das Blatt ist" — das Bild
    # laeuft dann oben und seitlich ueber die Kante hinaus. 100 = so lassen,
    # kleinere Werte holen es prozentual zurueck aufs Papier. Mit dem Lineal
    # am Testdruck einstellen: 97 nimmt rundum knapp 1,5 mm weg.
    "print_scale_pct": 100,
    # Dasselbe Problem, aber je Achse und in Millimetern: [lange Kante, kurze
    # Kante], jeweils der Ueberstand pro Blattrand. `print_scale_pct` zieht
    # beide Achsen prozentual gleich weit zusammen — der Ueberstand ist aber
    # auf beiden Achsen gleich viele Millimeter, auf der kurzen also
    # prozentual mehr. Beim Selphy zaehlt der Unterschied: links und rechts
    # sitzen die Abreisslaschen (dort darf Bild hinlaufen), oben und unten ist
    # die echte Blattkante. Gemessen am Testdruck, dessen Rahmen 5 mm vom
    # Blattrand liegt: kommt er mit 3 mm heraus, sind es 2 mm Ueberstand.
    # Anders als print_scale_pct wirkt das schon in prepare() und schrumpft
    # nur die Achse, die es soll. 0 = aus.
    "print_bleed_mm": [0.0, 0.0],
    # Wie lange der Drucker fuer ein Bild braucht. Geht nur in die Schaetzung
    # ein, die der Box-Dialog anzeigt, wenn Auftraege in der Queue haengen.
    "print_seconds_per_photo": 60,
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
    # AF-Methode als Index aus `gphoto2 --get-config afmethod`:
    # 0 LiveFace, 1 LiveMulti, 2 Live, 3 Quick. Voreinstellung 2 — ein kleines
    # festes Feld in der Bildmitte. 0 waere Gesichtserkennung: ein Rahmen um
    # jedes erkannte Gesicht, der mitwandert und damit der unruhigste Teil des
    # Live-Bildes ist. Ganz ohne Rahmen geht keine der Methoden.
    "camera_af_method": "2",
    # Wie viele Sekunden vor dem Ende des Countdowns ausgeloest wird. Zwischen
    # Anfrage und Belichtung liegt eine Verzoegerung, die die Box nicht
    # wegbekommt — auf der EOS 700D:
    #
    #   1. Geraet freiraeumen    Ø 1,24 s — der Halte-Prozess wird beendet,
    #      damit gphoto2 das USB-Geraet exklusiv bekommt. HIER friert das
    #      Live-Bild ein, rund zwei Sekunden vor dem Verschluss.
    #   2. Ausloesen             Ø 2,0 s — Live-View verlassen, Spiegel, AF,
    #      Belichtung.
    #   ────────────────────────────────
    #   Anfrage → BELICHTUNG     Ø 3,25 s
    #
    # ACHTUNG bei eigenen Messungen: die "Aufnahme-Zeiten"-Zeile im Log haengt
    # am Marker "New file is in location", und der meldet die fertige Datei
    # AUF DER KAMERA — per EXIF nachgemessen 0,34 bis 0,49 s NACH der
    # Belichtung. Die dort genannten Ø 3,73 s sind also der Marker, nicht der
    # Verschluss. Wer den Verschluss will, misst EXIF (DateTimeOriginal +
    # SubSecTimeOriginal) gegen den Prozessstart und rechnet den Versatz der
    # Kamera-Uhr heraus — die geht selten richtig.
    #
    # Der frueher hier stehende Wert 0,9 kam aus genau so einer EXIF-Messung,
    # mass aber nur Teil 2 ab gphoto2-Start und uebersah Teil 1 und den
    # Live-View-Ausstieg. Der Verschluss fiel damit rund 2,4 s nach der Null.
    #
    # 3,1 liegt knapp unter den gemessenen 3,25 s: der Verschluss faellt damit
    # rund 0,15 s NACH der Null. Zu spaet ist unkritisch, weil "Lächeln!" bis
    # zum Ausloesesignal stehen bleibt — zu frueh trifft einen Gast, der noch
    # nicht bereit ist.
    #
    # Der Countdown darf laenger sein als der Vorlauf, und laenger ist besser:
    # der Verschluss sitzt dann immer noch 0,15 s nach der Null, aber die
    # Gaeste bekommen mehr Live-Bild zum Ausrichten, bevor es einfriert.
    #
    #   Live-Zeit zum Ausrichten = countdown_duration - 3,1 + 1,24
    #
    # Bei countdown_duration = 3 bleibt nur gut eine Sekunde. Ist der Countdown
    # kuerzer als der Vorlauf, startet die Aufnahme mit ihm — frueher geht
    # nicht.
    "capture_lead_s": 3.1,
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
    data["gallery_url"] = build_gallery_url(gallery_host(data), data["gallery_port"])
    data["thumbnail_dir"] = os.path.join(BASE_DIR, "thumbnails")

    return data


def build_gallery_url(host: str, port: int) -> str:
    """Baut die Gallery-URL — Port 80 wird weggelassen, damit der QR-Code
    ein cleanes 'http://192.168.4.1' zeigt statt 'http://192.168.4.1:80'."""
    return f"http://{host}" if int(port) == 80 else f"http://{host}:{port}"


def gallery_host(data: dict) -> str:
    """Host-Teil der Galerie-Adresse: der Name, wenn die Box ihr eigenes
    WLAN aufspannt — sonst die nackte IP.

    Ohne eigenen Hotspot gibt es keinen Captive-DNS, der den Namen
    aufloesen koennte; er waere dort eine Sackgasse. Dasselbe gilt fuer
    die Box selbst: ihr eigener Resolver haengt am Uplink, nicht am
    dnsmasq des Hotspots — wer von der Box aus die Galerie aufruft
    (scripts/smoke_test.py), muss die IP nehmen.
    """
    name = (data.get("gallery_hostname") or "").strip().strip(".").lower()
    if name and data.get("hotspot_enabled", True):
        return name
    return data.get("hotspot_ip", "192.168.4.1")


# ── Was der QR-Code am Boxbildschirm traegt ───────────────────────────────────
# Den Galerie-Link. Hier stand einmal der WLAN-Zugang (WIFI:T:WPA;S:...;;),
# damit ein Scan das Handy ins Netz traegt und das Captive-Portal die Galerie
# hinterherschiebt. Am Geraet ist das durchgefallen: iOS tritt zwar bei,
# blendet bei einem Netz ohne Internet aber weder das WLAN-Symbol ein noch
# oeffnet es etwas, solange keine App das Netz anfasst. Fuer den Gast passierte
# nach dem Scan sichtbar gar nichts — und er stand ohne Weg weiter da.
#
# Verbinden kann jeder von Hand, SSID und Passwort stehen gross auf dem
# Boxschirm. Was niemand kann, ist eine Adresse erraten, nachdem er das
# Anmeldefenster geschlossen hat. Genau dafuer ist der Code jetzt da: er
# fuehrt jederzeit zurueck in die Galerie, und zwar im echten Browser, weil
# ein gescannter Link immer dort landet.


def photo_url(data: dict, path: str) -> str:
    """Adresse eines einzelnen Fotos in der Galerie: /photo/<event>/<datei>.

    Gebraucht fuer den Code auf dem Ergebnis-Schirm. Der zeigt bewusst auf
    das eine Foto und nicht auf das WLAN: ein mit der Kamera gescannter Code
    oeffnet sich immer im echten Browser, nie im WLAN-Anmeldefenster — und
    nur dort kann der Gast das Bild sichern.

    Leerer String, wenn das Foto nicht in einem Event-Ordner liegt (flache
    Altbestaende, die events.migrate_flat_photos noch nicht eingeraeumt hat).
    Ein geratener Link waere dort schlimmer als keiner: er fuehrte auf eine
    404-Seite statt zum Bild.
    """
    base = (data.get("gallery_url") or "").rstrip("/")
    if not base or not path:
        return ""
    folder, filename = os.path.split(os.path.abspath(path))
    event = os.path.basename(folder)
    picture_dir = os.path.abspath(data.get("picture_dir") or "")
    if not filename or not event or folder == picture_dir:
        return ""
    return f"{base}/photo/{quote(event)}/{quote(filename)}"


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
