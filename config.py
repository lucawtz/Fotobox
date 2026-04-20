import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Hardware – 3 Knöpfe (übereinander)
BUTTON_UP   = 17   # GPIO oben   (war BUTTON_PIN)
BUTTON_DOWN = 27   # GPIO unten  (neu)
BUTTON_OK   = 22   # GPIO mitte  (neu)
CAPTURE_DEVICE = 0

# Foto
COUNTDOWN_SECONDS = 3
PICTURE_PATH = os.path.join(BASE_DIR, "Picture_Box")

# Overlay
OVERLAY_PATH = os.path.join(BASE_DIR, "Layout", "Overlay_Allgemein.png")

# Modus: Polaroids (3 Fotos, bestehendes Overlay-Layout)
POLAROID_FRAMES = [
    (567,  255,  -5),
    (1098, 256,   5),
    (1633, 257,  12),
]
POLAROID_PHOTO_SIZE = (310, 295)

# Modus: Fotostreifen (4 Fotos, vertikal rechts)
STRIP_FRAMES = [
    (1700, 155, 0),
    (1700, 385, 0),
    (1700, 615, 0),
    (1700, 845, 0),
]
STRIP_PHOTO_SIZE = (270, 200)

# Modus: Collage (4 Fotos, 2×2 Raster)
COLLAGE_FRAMES = [
    (730,  350, -2),
    (1190, 350,  2),
    (730,  730, -2),
    (1190, 730,  2),
]
COLLAGE_PHOTO_SIZE = (430, 350)

# Live-View
LIVE_VIEW_RECT = (440, 600, 1040, 450)

# UI-Timing
REVIEW_DURATION         = 5.0   # Sekunden Ergebnis-Anzeige
IDLE_SLIDESHOW_INTERVAL = 4.0   # Sekunden zwischen Idle-Slideshow-Fotos
