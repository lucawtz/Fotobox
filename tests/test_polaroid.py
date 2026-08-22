"""Polaroid-Rendering: befuellte Polaroids muessen genauso aussehen wie leere.

Hintergrund des Regressionstests: `add_photo` waermte den Rotations-Cache mit
dem *nackten* Foto vor. `_draw_polaroid` fand daraufhin einen Cache-Treffer und
rief `_build_polaroid` — den einzigen Ort, an dem Cream-Rahmen und Pin
entstehen — fuer befuellte Polaroids nie auf. Ergebnis auf dem Homescreen:
leere Polaroids mit Pin, befuellte ohne.
"""
import os
from collections import deque

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

import ui as ui_mod

PW, PH = 310, 295
FRAME_W = PW + ui_mod.POLAROID_PAD_LR * 2
FRAME_H = PH + ui_mod.POLAROID_PAD_TOP + ui_mod.POLAROID_PAD_BOT


@pytest.fixture
def gallery(tmp_path):
    """UI-Instanz mit genau den Attributen, die add_photo/_build_polaroid brauchen."""
    pygame.display.init()
    pygame.display.set_mode((FRAME_W, FRAME_H))

    inst = ui_mod.UI.__new__(ui_mod.UI)
    inst._cfg = {}
    inst._PW, inst._PH = PW, PH
    inst._gallery = deque(maxlen=3)
    inst._photo_cache = {}
    inst._fade_start = {}
    inst._rot_cache = {}
    # angle 0 — rotozoom laesst die Groesse dann unveraendert und der Vergleich
    # mit FRAME_W/FRAME_H bleibt exakt.
    inst._frames = [(100, 100, 0)]
    inst._apply_theme({})
    yield inst
    pygame.display.quit()


@pytest.fixture
def jpeg(tmp_path):
    from PIL import Image
    path = str(tmp_path / "foto.jpg")
    Image.new("RGB", (1200, 800), (40, 110, 190)).save(path, "JPEG")
    return path


def _colors(surface):
    surface.lock()
    try:
        return {surface.get_at((x, y))[:3]
                for x in range(0, surface.get_width(), 2)
                for y in range(0, surface.get_height(), 2)}
    finally:
        surface.unlock()


def test_added_photo_is_cached_as_a_full_polaroid(gallery, jpeg):
    gallery.add_photo(jpeg)

    cached = gallery._rot_cache[(jpeg, 0)]
    assert cached.get_size() == (FRAME_W, FRAME_H), (
        "Im Cache muss das ganze Polaroid liegen, nicht nur das Foto — sonst "
        "ueberspringt _draw_polaroid den Rahmen-Aufbau")


def test_added_photo_keeps_its_pin(gallery, jpeg):
    gallery.add_photo(jpeg)

    cached = gallery._rot_cache[(jpeg, 0)]
    pin_px = cached.get_at((FRAME_W // 2, ui_mod.POLAROID_PIN_R + 6))[:3]
    r, g, b = pin_px
    assert r > g and r > b, f"Pin fehlt oder ist nicht rot: {pin_px}"


def test_added_photo_keeps_its_cream_frame(gallery, jpeg):
    gallery.add_photo(jpeg)

    cached = gallery._rot_cache[(jpeg, 0)]
    # Unterer Rand — beim Polaroid der breite Steg unter dem Bild.
    assert cached.get_at((FRAME_W // 2, FRAME_H - 20))[:3] == \
        gallery._theme["polaroid_frame"]


def test_filled_and_empty_polaroid_have_the_same_footprint(gallery, jpeg):
    """Beide Zustaende muessen deckungsgleich sein — sonst springt das Layout,
    sobald das erste Foto eintrifft."""
    gallery.add_photo(jpeg)
    filled = gallery._rot_cache[(jpeg, 0)]
    empty = gallery._build_polaroid(None, ui_mod._PLACEHOLDER_COLORS[0], 0)

    assert filled.get_size() == empty.get_size()


def test_pin_sits_above_the_photo_not_behind_it(gallery, jpeg):
    """Der Pin wird nach dem Foto gezeichnet und ragt in dessen obere Kante."""
    gallery.add_photo(jpeg)
    cached = gallery._rot_cache[(jpeg, 0)]

    overlap_y = ui_mod.POLAROID_PAD_TOP + 2   # schon im Fotobereich
    assert overlap_y < ui_mod.POLAROID_PIN_R + 6 + ui_mod.POLAROID_PIN_R, \
        "Testannahme: der Pin reicht in den Fotobereich hinein"
    px = cached.get_at((FRAME_W // 2, overlap_y))[:3]
    r, g, b = px
    assert r > g and r > b, f"Foto ueberdeckt den Pin: {px}"
