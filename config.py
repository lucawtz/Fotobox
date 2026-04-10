import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Hardware
BUTTON_PIN = 17
CAPTURE_DEVICE = 0      # Index der Capture Card

# Foto
COUNTDOWN_SECONDS = 3
PICTURE_PATH = os.path.join(BASE_DIR, "Picture_Box")

# Polaroid-Rahmen: (Mittelpunkt X, Mittelpunkt Y, Rotation in Grad)
POLAROID_FRAMES = [
    (380,  255, -5),
    (840,  265,  4),
    (1290, 255, -3),
]

# Live-View Bereich (x, y, breite, höhe)
LIVE_VIEW_RECT = (145, 520, 1370, 450)
