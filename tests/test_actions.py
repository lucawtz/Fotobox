"""Action-Buttons: Geometrie und Klick-/Tap-Hit-Test.

Laeuft ohne Display — `ui.action_rects`/`ui.action_at` sind bewusst modulweite
Funktionen und nicht Methoden der UI, damit genau das moeglich ist.
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pytest

import ui as ui_mod


@pytest.fixture
def actions_cfg():
    return {
        "actions": [
            {"id": "foto",    "label": "Foto",    "key": "trigger"},
            {"id": "collage", "label": "Collage", "key": "right"},
        ],
        "live_view_rect": [510, 540, 800, 450],
    }


def test_buttons_do_not_overlap(actions_cfg):
    (_, first), (_, second) = ui_mod.action_rects(actions_cfg)
    assert first.bottom < second.top, "Buttons duerfen sich nicht beruehren"
    assert second.top - first.bottom == ui_mod.ACTION_GAP


def test_buttons_stay_on_screen(actions_cfg):
    for _, rect in ui_mod.action_rects(actions_cfg):
        assert rect.right <= ui_mod.W
        assert 0 <= rect.top and rect.bottom <= ui_mod.H


def test_click_hits_the_right_action(actions_cfg):
    rects = ui_mod.action_rects(actions_cfg)
    for action, rect in rects:
        hit = ui_mod.action_at(actions_cfg, rect.center)
        assert hit is action, f"Klick in die Mitte von {action['label']} muss treffen"


def test_click_between_or_beside_buttons_does_nothing(actions_cfg):
    (_, first), (_, second) = ui_mod.action_rects(actions_cfg)
    gap_y = (first.bottom + second.top) // 2
    assert ui_mod.action_at(actions_cfg, (first.centerx, gap_y)) is None
    assert ui_mod.action_at(actions_cfg, (10, 10)) is None
    assert ui_mod.action_at(actions_cfg, (first.left - 5, first.centery)) is None


def test_click_maps_to_the_same_key_as_the_hardware_button(actions_cfg):
    """Der Klick muss auf denselben `key` zeigen, den hardware.py kennt —
    sonst loest der Button auf dem Laptop etwas anderes aus als auf der Box."""
    keys = {a["key"] for a, _ in ui_mod.action_rects(actions_cfg)}
    assert keys <= {"left", "trigger", "right"}


def test_no_actions_configured_is_not_a_crash():
    assert ui_mod.action_rects({}) == []
    assert ui_mod.action_at({}, (100, 100)) is None


# ── Event-Verarbeitung ─────────────────────────────────────────────────────────
# Hier laeuft echter UI-Code: check_quit() leert die Pygame-Queue, also muss es
# den Klick dort selbst einsammeln — sonst ist er weg, bevor ihn jemand sieht.

@pytest.fixture
def headless_ui(actions_cfg):
    """Echte UI-Methoden auf einem minimalen Objekt, ohne Vollbild zu oeffnen."""
    import pygame

    pygame.display.init()
    pygame.display.set_mode((1, 1))
    inst = ui_mod.UI.__new__(ui_mod.UI)
    inst._cfg = actions_cfg
    inst._pending_click = None
    inst._cursor_until = 0.0
    pygame.event.clear()
    yield inst
    pygame.event.clear()
    pygame.display.quit()


def _click(pos):
    import pygame
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": pos}))


def test_click_survives_the_event_pump(headless_ui, actions_cfg):
    collage_rect = ui_mod.action_rects(actions_cfg)[1][1]
    _click(collage_rect.center)

    assert headless_ui.check_quit() is False
    action = headless_ui.take_click_action()

    assert action is not None and action["key"] == "right", \
        "Klick auf den zweiten Button muss den rechten Knopf ausloesen"


def test_click_is_consumed_only_once(headless_ui, actions_cfg):
    _click(ui_mod.action_rects(actions_cfg)[0][1].center)
    headless_ui.check_quit()

    assert headless_ui.take_click_action() is not None
    assert headless_ui.take_click_action() is None, \
        "ein Klick darf nicht zwei Aufnahmen ausloesen"


def test_escape_still_quits(headless_ui):
    import pygame
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE}))
    assert headless_ui.check_quit() is True
