"""Das gehaltene Standbild im Countdown bleibt scharf und ungedimmt.

Waehrend der Aufnahme liefert die Capture-Card nichts Neues — gphoto2 hat das
USB-Geraet, der Live-View der Kamera ist aus. Die UI haelt deshalb den letzten
Frame. Ob der weichgezeichnet wird, ist dreimal hin- und hergegangen
(33a8f2e unscharf, 3824d8b zurueck, 78301d5/56efa96 wieder unscharf), deshalb
steht die Entscheidung hier als Test und nicht nur als Kommentar.

Begruendung fuer "scharf": der Weichzeichner sollte verhindern, dass das
unbewegte Bild "Foto ist im Kasten" behauptet. Das galt, solange die Luecke
zwischen Live-View-Ende und Verschluss HINTER "Lächeln!" lag. Seit
capture_lead_s richtig kalibriert ist, liegt sie im Countdown bei "2" und "1"
— die Ziffern laufen sichtbar weiter, und das Standbild ist das Einzige,
woran die Gaeste sich noch ausrichten koennen.
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import numpy as np
import pygame
import pytest

import ui as ui_mod


# Quellbild 16:9, damit es verlustfrei auf 1920x1080 skaliert.
SRC_W, SRC_H = 640, 360
LEFT = (220, 40, 40)
RIGHT = (40, 40, 220)


@pytest.fixture
def screen():
    pygame.display.init()
    surf = pygame.display.set_mode((ui_mod.W, ui_mod.H))
    yield surf
    pygame.display.quit()


def _frame():
    """Zwei Farbhaelften mit harter Kante — die verraet jeden Weichzeichner."""
    f = np.zeros((SRC_H, SRC_W, 3), dtype=np.uint8)
    f[:, : SRC_W // 2] = LEFT
    f[:, SRC_W // 2 :] = RIGHT
    return f


def _draw(screen, held: bool):
    inst = ui_mod.UI.__new__(ui_mod.UI)
    inst._screen = screen
    inst._live_is_held = held
    inst._live_frame_rgb = lambda: (_frame(), None)
    inst._draw_live_fullscreen()
    return inst


def test_held_still_keeps_its_colours(screen):
    """Kein Abdunkeln: das Standbild hat dieselben Farben wie das Live-Bild.

    Der frueher hier wirksame Regler liess 45 % der Helligkeit stehen — aus
    (220, 40, 40) waere (99, 18, 18) geworden.
    """
    _draw(screen, held=True)

    # Tief in der linken Haelfte, weit weg von der Kante.
    assert screen.get_at((ui_mod.W // 4, ui_mod.H // 2))[:3] == LEFT


def test_held_still_keeps_its_hard_edge(screen):
    """Kein Weichzeichner: die Kante zwischen den Haelften bleibt hart.

    Ein Gauss haette die Farben ueber die Mitte hinweg ineinander gezogen —
    zwei Pixel neben der Kante stuende dann eine Mischfarbe.
    """
    _draw(screen, held=True)

    mid = ui_mod.W // 2
    y = ui_mod.H // 2
    assert screen.get_at((mid - 6, y))[:3] == LEFT
    assert screen.get_at((mid + 6, y))[:3] == RIGHT


def test_held_and_fresh_are_drawn_identically(screen):
    """Gehalten und frisch sehen gleich aus — das ist der ganze Punkt.

    Faengt jemand wieder an, zwischen beiden zu unterscheiden, faellt es
    hier auf, egal mit welchem Effekt.
    """
    _draw(screen, held=False)
    fresh = pygame.image.tostring(screen, "RGB")

    screen.fill((0, 0, 0))
    _draw(screen, held=True)
    held = pygame.image.tostring(screen, "RGB")

    assert held == fresh
