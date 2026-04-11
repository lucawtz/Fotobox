import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Hardware
BUTTON_PIN = 17
CAPTURE_DEVICE = 0      # Index der Capture Card

# Foto
COUNTDOWN_SECONDS = 3
PICTURE_PATH = os.path.join(BASE_DIR, "Picture_Box")

# Overlay-Bild (wird auf 1920×1080 gestreckt)
OVERLAY_PATH = os.path.join(BASE_DIR, "Layout", "Overlay-Fotobox.jpg")

# Polaroid-Foto-Bereiche im Overlay (Mittelpunkt X, Mittelpunkt Y, Rotation in Grad)
# Automatisch aus schwarzen Bereichen des Overlays berechnet (1248×832 → 1920×1080)
POLAROID_FRAMES = [
    (574,  314,  10),   # links  (top lehnt nach links)
    (946,  347,   0),   # mitte  (gerade)
    (1332, 327,  -8),   # rechts (top lehnt nach rechts)
]

# Live-View Bereich (x, y, breite, höhe)
LIVE_VIEW_RECT = (320, 694, 1058, 317)
