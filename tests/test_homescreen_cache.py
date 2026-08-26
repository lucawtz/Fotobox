"""Der Homescreen zeichnet nur noch neu, was sich wirklich aendert.

Vorher entstand bei jedem Bild alles von Grund auf: Verlauf blitten, Sidebar,
Logo, Header-Schrift rendern, QR-Karten, WLAN-Box. Auf der Box gemessen rund
68 ms je Render — bei 15 Bildern je Sekunde mehr als ein ganzer Kern, auf
einem Pi, der ohne aktive Kuehlung bei 80 Grad laeuft.

Jetzt liegt das alles in einer Standebene, die einmal gebaut und danach nur
noch geblittet wird. Ein Cache ist aber nur so gut wie seine Invalidierung:
haengt die Standebene fest, aendert das Admin-Panel Theme oder Logo, und auf
dem Boxschirm passiert nichts. Genau das prueft diese Datei.
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

import ui as ui_mod


DYNAMIC = ("_draw_live_view", "_draw_polaroids",
           "_draw_action_buttons", "_draw_status_bar")


@pytest.fixture
def home(monkeypatch):
    """UI-Instanz, die nichts wirklich zeichnet, aber jeden Aufruf zaehlt."""
    pygame.display.init()
    screen = pygame.display.set_mode((320, 240))

    inst = ui_mod.UI.__new__(ui_mod.UI)
    inst._screen = screen
    inst._static_surf = None
    inst._bg = pygame.Surface((ui_mod.W, ui_mod.H))
    inst._bg.fill((40, 30, 20))

    calls: dict = {}

    def counter(name):
        def _fn(*a, **k):
            calls[name] = calls.get(name, 0) + 1
        return _fn

    for name in ui_mod.UI._STATIC_PARTS + DYNAMIC + ("_check_config_reload",
                                                     "_draw_error_banner"):
        monkeypatch.setattr(inst, name, counter(name), raising=False)
    monkeypatch.setattr(ui_mod.pygame.display, "flip", lambda: None)

    inst.calls = calls
    yield inst
    pygame.display.quit()


def _render(inst, camera_ok=True):
    inst.render_homescreen(camera_ok, "", 5000, 3)


# ── Der Cache greift ──────────────────────────────────────────────────────────

def test_static_parts_are_drawn_once_for_many_frames(home):
    """Fuenf Bilder, aber die Sidebar entsteht nur ein einziges Mal."""
    for _ in range(5):
        _render(home)

    for name in ui_mod.UI._STATIC_PARTS:
        assert home.calls.get(name) == 1, f"{name} wurde {home.calls.get(name)}x gezeichnet"


def test_dynamic_parts_are_drawn_every_frame(home):
    """Live-Bild, Polaroids, Knoepfe und Status muessen jedes Bild neu.

    Landen die versehentlich in der Standebene, friert der Homescreen ein —
    das waere schlimmer als die Rechenzeit, die hier gespart wird.
    """
    for _ in range(5):
        _render(home)

    for name in DYNAMIC:
        assert home.calls.get(name) == 5, f"{name}: {home.calls.get(name)} statt 5"


def test_layer_is_the_same_surface_across_frames(home):
    """Zweiter Aufruf liefert dasselbe Objekt, nicht eine gleiche Kopie."""
    first = home._static_layer()
    second = home._static_layer()

    assert first is second


# ── Die Invalidierung greift ──────────────────────────────────────────────────

def test_dropping_the_layer_rebuilds_it(home):
    """So invalidieren _check_config_reload und _apply_theme."""
    first = home._static_layer()
    home._static_surf = None
    second = home._static_layer()

    assert first is not second
    assert home.calls["_draw_qr_card"] == 2


def test_every_reload_branch_drops_the_layer():
    """Jede Aenderungsstelle im Live-Reload muss den Cache verwerfen.

    Geprueft am Quelltext, nicht am Verhalten: die Zweige haengen an
    Datei-Zeitstempeln und liessen sich sonst nur mit einem halben Dutzend
    Attrappen ausloesen. Zaehlt wird gegen die Log-Zeilen, mit denen jeder
    Zweig sein Eingreifen meldet.
    """
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, "ui.py"), encoding="utf-8") as f:
        src = f.read()

    block = src[src.index("def _check_config_reload"):src.index("def _static_layer")]
    reloads = block.count('logger.info("Live-Reload:')
    drops = block.count("self._static_surf = None")

    assert reloads > 0, "kein Live-Reload-Zweig gefunden — Test veraltet"
    assert drops == reloads, (
        f"{reloads} Aenderungszweige, aber nur {drops} verwerfen die "
        "Standebene — dort bliebe der Bildschirm stehen")


def test_theme_change_drops_the_layer():
    """_apply_theme baut die Farben neu — die Standebene traegt sie."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, "ui.py"), encoding="utf-8") as f:
        src = f.read()

    block = src[src.index("def _apply_theme"):src.index("def _build_gradient_bg")]
    assert "self._static_surf = None" in block


# ── Der Fehlerfall bleibt sichtbar ───────────────────────────────────────────

def test_error_banner_still_appears(home):
    """Das Banner haengt an camera_ok und gehoert nicht in den Cache."""
    _render(home, camera_ok=False)
    _render(home, camera_ok=False)

    assert home.calls.get("_draw_error_banner") == 2


def test_static_part_names_exist():
    """Ein Tippfehler in _STATIC_PARTS wuerde erst zur Laufzeit auffallen."""
    for name in ui_mod.UI._STATIC_PARTS:
        assert callable(getattr(ui_mod.UI, name, None)), f"{name} gibt es nicht"
