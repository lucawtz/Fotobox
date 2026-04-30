import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Hardware
BUTTON_PIN = 17
CAPTURE_DEVICE = 0      # Index der Capture Card

# Foto
COUNTDOWN_SECONDS = 3
PICTURE_PATH = os.path.join(BASE_DIR, "Picture_Box")

# Overlay-Bild (bereits 1920×1080, wird 1:1 geladen)
OVERLAY_PATH = os.path.join(BASE_DIR, "Layout", "Overlay_Allgemein.png")

# Polaroid-Foto-Bereiche im Overlay (Mittelpunkt X, Mittelpunkt Y, Rotation in Grad)
POLAROID_FRAMES = [
    (567,  255,  -5),    # links
    (1098, 256,   5),    # mitte
    (1633, 257,  12),    # rechts
]

# Größe des schwarzen Foto-Bereichs je Polaroid (etwas kleiner als Slot 317×302)
POLAROID_PHOTO_SIZE = (310, 295)

# Live-View Bereich — gleicher Abstand oben (zu Polaroids) und unten (zum Rand)
LIVE_VIEW_RECT = (440, 600, 1040, 450)

# Idle-Diashow: Sekunden ohne Auslöser bis die Slideshow startet
IDLE_TIMEOUT = 60
# Anzeigedauer pro Foto in der Diashow (Millisekunden)
SLIDE_DURATION_MS = 5000

# Galerie-Webserver
GALLERY_PORT = 5000

# WLAN-Hotspot (Option B)
HOTSPOT_ENABLED  = False          # auf False setzen zum Testen via VNC/SSH
HOTSPOT_SSID     = "Fotobox"
HOTSPOT_PASSWORD = "fotobox123"
HOTSPOT_IP       = "192.168.4.1"
GALLERY_URL      = f"http://{HOTSPOT_IP}:{GALLERY_PORT}"
