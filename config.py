import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Hardware
BUTTON_PIN = 17
CAPTURE_DEVICE = 0      # Index der Capture Card

# Foto
COUNTDOWN_SECONDS = 3
PICTURE_PATH = os.path.join(BASE_DIR, "Picture_Box")

# Overlay-Bild (bereits 1920×1080, wird 1:1 geladen)
OVERLAY_PATH = os.path.join(BASE_DIR, "Layout", "Overlay_Allgemein2.png")

# Polaroid-Foto-Bereiche im Overlay (Mittelpunkt X, Mittelpunkt Y, Rotation in Grad)
# Automatisch aus schwarzen Bereichen erkannt (Bild ist 1920×1080)
POLAROID_FRAMES = [
    (567,  255,   5),   # links  (top lehnt leicht nach links)
    (1098, 256,  -5),   # mitte  (leicht nach rechts)
    (1633, 257, -12),   # rechts (stärker nach rechts)
]

# Größe des Foto-Bereichs in jedem Polaroid (schwarze Fläche)
POLAROID_PHOTO_SIZE = (295, 290)

# Live-View Bereich (x, y, breite, höhe) — unter den Polaroids, zentriert zwischen Sidebar und Buttons
# Horizontal: Sidebar endet ~x=130, Buttons beginnen ~x=1610 → 1100px zentriert → x=320
# Vertikal:   Polaroids enden ~y=440 → y=470, Höhe=500
LIVE_VIEW_RECT = (320, 470, 1100, 500)
