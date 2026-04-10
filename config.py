import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Hardware
BUTTON_PIN = 17
CAPTURE_DEVICE = 0      # Index der Capture Card

# Foto
COUNTDOWN_SECONDS = 3
PICTURE_PATH = os.path.join(BASE_DIR, "Picture_Box")

# Layout
OVERLAY_PATH = os.path.join(BASE_DIR, "Layout", "Overlay_Allgemein.png")

# Positionen der drei Polaroid-Foto-Slots (x, y, breite, höhe)
PHOTO_SLOTS = [
    (200,  88, 449, 333),   # Polaroid links
    (620, 119, 449, 309),   # Polaroid mitte
    (1010, 105, 350, 317),  # Polaroid rechts
]

# Live-View Bereich (x, y, breite, höhe)
LIVE_VIEW_RECT = (150, 587, 1350, 412)
