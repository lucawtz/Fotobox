"""Waehrend einer Aufnahme darf der Gast das Aufnahmemenue nicht sehen.

Sobald gphoto2 fuer die Aufnahme das USB-Geraet uebernimmt, endet der
Live-View, und die Kamera legt ihr eigenes Info-Display auf HDMI. Zwischen
Countdown und Ergebnis blitzten dadurch Menue und Schwarzbild auf.

Erkennen laesst sich das nur an der Bewegung: ein Live-Bild rauscht auch bei
voellig stillem Motiv, ein Menue steht exakt still. Auf der Box gemessen 0,80
gegen 0,00. Ueber die Helligkeit ginge es nicht — das Menue ist ueberwiegend
schwarz und damit so dunkel wie mancher Raum.
"""
import os
from collections import deque

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import numpy as np
import pytest

import ui as ui_mod


class MotionProbe:
    """Nur die Bewegungsmessung des LiveReaders, ohne Capture-Device."""

    _MOTION_THRESHOLD = ui_mod._LiveReader._MOTION_THRESHOLD
    _MOTION_WINDOW = ui_mod._LiveReader._MOTION_WINDOW
    _measure_motion = ui_mod._LiveReader._measure_motion
    moving = ui_mod._LiveReader.moving

    def __init__(self):
        self._prev_gray = None
        self._motion = deque(maxlen=self._MOTION_WINDOW)

    def feed(self, frames):
        for f in frames:
            self._measure_motion(f)


def _menu_frame():
    """Ein stehendes Bild, wie es die Kamera als Aufnahmemenue liefert:
    ueberwiegend schwarz mit hellen Elementen."""
    f = np.zeros((480, 640, 3), dtype=np.uint8)
    f[40:90, 40:300] = 235       # "M 1/125 F5.6"
    f[300:340, 40:200] = 200     # "ONE SHOT"
    return f


def _live_frames(count, seed=7):
    """Ein stilles Motiv mit Sensorrauschen — das ist ein Live-Bild."""
    rng = np.random.default_rng(seed)
    base = np.full((480, 640, 3), 60, dtype=np.int16)
    base[100:300, 200:400] = 90                      # irgendein Motiv
    out = []
    for _ in range(count):
        noisy = base + rng.normal(0, 1.2, base.shape)
        out.append(np.clip(noisy, 0, 255).astype(np.uint8))
    return out


def test_a_still_menu_is_not_a_live_picture():
    """Derselbe Frame wieder und wieder — das ist kein Kamerabild."""
    probe = MotionProbe()

    probe.feed([_menu_frame()] * 12)

    assert not probe.moving()


def test_sensor_noise_marks_a_live_picture():
    """Auch ein voellig stilles Motiv rauscht — daran haengt die Erkennung."""
    probe = MotionProbe()

    probe.feed(_live_frames(12))

    assert probe.moving()


def test_a_single_frame_decides_nothing():
    """Ohne Vorgaenger gibt es keine Differenz — und keine Behauptung."""
    probe = MotionProbe()

    probe.feed(_live_frames(1))

    assert not probe.moving()


def test_the_switch_to_the_menu_is_noticed():
    """Genau der Moment, in dem die Aufnahme beginnt."""
    probe = MotionProbe()
    probe.feed(_live_frames(12))
    assert probe.moving()

    probe.feed([_menu_frame()] * 12)

    assert not probe.moving(), "sonst zeigt die Box dem Gast das Aufnahmemenue"


def test_a_short_freeze_does_not_flip_the_verdict():
    """Geglaettet, damit ein einzelner doppelter Frame das Bild nicht
    einfrieren laesst — die Capture-Card liefert gelegentlich einen."""
    probe = MotionProbe()
    frames = _live_frames(12)
    probe.feed(frames)

    probe.feed([frames[-1]])       # ein einzelner Wiederholframe

    assert probe.moving()


# ── Das Festhalten des letzten Bildes ──────────────────────────────────────────

class FakeReader:
    """LiveReader-Attrappe: liefert, was der Test vorgibt."""

    def __init__(self):
        self.frame = None
        self.is_moving = True

    def latest(self):
        return self.frame

    def moving(self):
        return self.is_moving


class HoldProbe:
    """Nur die Frame-Auswahl der UI, ohne Fenster."""

    _LIVE_HOLD_S = ui_mod.UI._LIVE_HOLD_S
    _live_frame_rgb = ui_mod.UI._live_frame_rgb
    _fresh_live_frame = ui_mod.UI._fresh_live_frame

    def __init__(self, live):
        self._live = live
        self._live_hold = None
        self._live_hold_at = 0.0
        self._autowake_paused = True     # Wecken ist hier nicht das Thema
        self._live_dark_since = None
        self._live_wake_last = 0.0
        self._wake_cb = None

    # Der Letterbox-Zuschnitt ist eine eigene Baustelle und hier nur Rauschen.
    def _crop_black_borders(self, frame):
        return frame

    def _note_live_signal(self, ok):
        pass


@pytest.fixture
def hold(monkeypatch):
    clock = {"now": 500.0}
    monkeypatch.setattr(ui_mod.time, "monotonic", lambda: clock["now"])
    reader = FakeReader()
    p = HoldProbe(reader)
    p.reader = reader
    p.tick = lambda s: clock.__setitem__("now", clock["now"] + s)
    return p


def _bright(value=120):
    return np.full((480, 640, 3), value, dtype=np.uint8)


def test_a_live_frame_is_passed_through(hold):
    hold.reader.frame = _bright()

    frame, msg = hold._live_frame_rgb()

    assert frame is not None and msg is None


def test_the_menu_is_replaced_by_the_last_live_frame(hold):
    """Der eigentliche Zweck: waehrend der Aufnahme bleibt der Gast stehen,
    statt dass das Aufnahmemenue der Kamera aufblitzt."""
    hold.reader.frame = _bright(120)
    live, _ = hold._live_frame_rgb()

    hold.reader.frame = _menu_frame()
    hold.reader.is_moving = False
    hold.tick(1.0)
    frame, msg = hold._live_frame_rgb()

    assert msg is None
    assert np.array_equal(frame, live), "es muss das festgehaltene Bild sein"


def test_a_black_signal_is_also_covered(hold):
    """Zwischen Ende des Live-Views und Kameramenue liegt kurz gar nichts."""
    hold.reader.frame = _bright(120)
    live, _ = hold._live_frame_rgb()

    hold.reader.frame = np.zeros((480, 640, 3), dtype=np.uint8)
    hold.tick(0.5)
    frame, _ = hold._live_frame_rgb()

    assert np.array_equal(frame, live)


def test_the_hold_expires(hold):
    """Ein eingefrorenes Bild sieht aus wie ein lebendes. Nach ein paar
    Sekunden waere das eine Luege — dann lieber die Meldung."""
    hold.reader.frame = _bright(120)
    hold._live_frame_rgb()

    hold.reader.frame = _menu_frame()
    hold.reader.is_moving = False
    hold.tick(hold._LIVE_HOLD_S + 1)
    frame, msg = hold._live_frame_rgb()

    assert frame is None
    assert msg


def test_without_any_live_frame_there_is_nothing_to_hold(hold):
    """Startet die Box vor der Kamera, gibt es kein letztes gutes Bild."""
    hold.reader.frame = _menu_frame()
    hold.reader.is_moving = False

    frame, msg = hold._live_frame_rgb()

    assert frame is None
    assert msg

