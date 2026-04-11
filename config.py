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

# Live-View Bereich — maximale Größe, zentriert bei x=960, 30px Abstand unten
LIVE_VIEW_RECT = (440, 560, 1040, 490)
