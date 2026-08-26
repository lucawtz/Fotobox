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


# Wo das scharfe Bild landet: die Quelle ist 16:9, live_source_aspect 3:2,
# also wird sie um 1,185 gestaucht — 1620x1080, mittig, mit je 150 px
# weichgezeichnetem Rand links und rechts.
SHARP_X0, SHARP_X1 = 150, 1770


def _draw(screen, held: bool, hold_at: float = 100.0):
    inst = ui_mod.UI.__new__(ui_mod.UI)
    inst._screen = screen
    inst._live_is_held = held
    inst._live_hold_at = hold_at
    inst._fullscreen_cache = None
    inst._cfg = {"live_source_aspect": [3, 2]}
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
    # 20 px statt 6: das Bild ist jetzt um 2,5 hochskaliert, INTER_LINEAR
    # blendet ueber rund einen Quellpixel — das sind hier gut zwei Pixel.
    assert screen.get_at((mid - 20, y))[:3] == LEFT
    assert screen.get_at((mid + 20, y))[:3] == RIGHT


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


# ── Raender und Entzerrung ────────────────────────────────────────────────────
#
# Ein 3:2-Bild auf einem 16:9-Schirm laesst links und rechts je 150 px stehen.
# Die waren schwarz und zerlegten den Countdown-Schirm in drei Streifen.

def test_the_borders_are_filled_not_black(screen):
    """Neben dem Bild steht der weichgezeichnete Grund, kein Schwarz."""
    _draw(screen, held=False)

    left = screen.get_at((40, ui_mod.H // 2))[:3]
    right = screen.get_at((ui_mod.W - 40, ui_mod.H // 2))[:3]

    assert sum(left) > 20, "linker Rand ist schwarz geblieben"
    assert sum(right) > 20, "rechter Rand ist schwarz geblieben"


def test_the_border_is_blurred_not_the_picture(screen):
    """Der Rand ist weich, das Bild selbst bleibt hart.

    Sonst waere es der Weichzeichner ueber dem Standbild, der oben aus
    guten Gruenden nicht mehr da ist.
    """
    _draw(screen, held=True)
    y = ui_mod.H // 2

    # Im Bild: harte Kante zwischen den Farbhaelften (siehe Test oben).
    assert screen.get_at((SHARP_X0 + 40, y))[:3] == LEFT
    # Im Rand: eine Mischung, keine der beiden Reinfarben.
    assert screen.get_at((40, y))[:3] not in (LEFT, RIGHT)


def test_the_picture_is_undistorted(screen):
    """Die 16:9-Quelle wird auf 3:2 gestaucht, nicht formatfuellend gezogen.

    Ohne die Entzerrung waere der Gast im Countdown ein Drittel zu breit —
    genau in den Sekunden, in denen er sich ausrichtet.
    """
    _draw(screen, held=False)
    y = ui_mod.H // 2

    # Knapp innerhalb der erwarteten Bildkanten stehen die Reinfarben,
    # knapp ausserhalb nicht mehr.
    assert screen.get_at((SHARP_X0 + 5, y))[:3] == LEFT
    assert screen.get_at((SHARP_X1 - 5, y))[:3] == RIGHT
    assert screen.get_at((SHARP_X0 - 30, y))[:3] != LEFT


def test_the_composed_frame_is_cached(screen):
    """Der Countdown laeuft mit 33 fps gegen ein Live-Bild mit 6.

    Ohne Cache entstuende dasselbe Vollbild fuenfmal umsonst — auf einem Pi
    ohne Luefter ist das keine Kleinigkeit.
    """
    inst = _draw(screen, held=False)
    first = inst._fullscreen_cache

    inst._draw_live_fullscreen()

    assert inst._fullscreen_cache is first, "neu gerechnet statt geblittet"


def test_a_new_frame_drops_the_cache(screen):
    """Kommt ein frisches Bild, muss es auch gezeichnet werden."""
    inst = _draw(screen, held=False, hold_at=100.0)
    first = inst._fullscreen_cache

    inst._live_hold_at = 101.0        # frisches Bild angekommen
    inst._draw_live_fullscreen()

    assert inst._fullscreen_cache is not first
