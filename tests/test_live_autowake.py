"""Das Live-Bild holt sich die Box selbst zurueck.

Das Bild auf dem Schirm kommt nicht von gphoto2, sondern aus dem
HDMI-Ausgang der Kamera ueber eine Capture-Card. Ob dort etwas ankommt, weiss
deshalb einzig die UI — die Kamera kennt nur ihre eigenen gphoto2-Erfolge,
und aus einem geglueckten 'viewfinder=1' folgt kein Bild auf HDMI.

Geprueft wird hier die Entscheidung, nicht das Zeichnen: ab wann geweckt wird,
wie oft, und wann bewusst nicht.
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pytest

import ui as ui_mod


class Probe:
    """Nur die Weck-Entscheidung, ohne Fenster und ohne Capture-Card.

    UI.__init__ braucht ein Display; gebraucht wird hier aber allein
    _note_live_signal, das ausser den vier Zustandsfeldern nichts anfasst.
    """

    _LIVE_DEAD_S = ui_mod.UI._LIVE_DEAD_S
    _LIVE_WAKE_COOLDOWN_S = ui_mod.UI._LIVE_WAKE_COOLDOWN_S
    _note_live_signal = ui_mod.UI._note_live_signal

    def __init__(self):
        self.wakes = 0
        self._wake_cb = lambda: setattr(self, "wakes", self.wakes + 1)
        self._live_dark_since = None
        self._live_wake_last = 0.0
        self._autowake_paused = False


@pytest.fixture
def probe(monkeypatch):
    """Probe mit steuerbarer Uhr — `probe.tick(s)` laesst Zeit vergehen."""
    clock = {"now": 1000.0}
    monkeypatch.setattr(ui_mod.time, "monotonic", lambda: clock["now"])
    p = Probe()
    p.tick = lambda s: clock.__setitem__("now", clock["now"] + s)
    return p


def test_a_short_gap_does_not_wake_anything(probe):
    """Der Spiegelhub selbst verdunkelt HDMI kurz. Darauf zu wecken hiesse,
    auf das eigene Wecken zu reagieren."""
    probe._note_live_signal(False)
    probe.tick(probe._LIVE_DEAD_S - 0.5)
    probe._note_live_signal(False)

    assert probe.wakes == 0


def test_a_lasting_black_screen_wakes_the_liveview(probe):
    probe._note_live_signal(False)
    probe.tick(probe._LIVE_DEAD_S + 0.1)
    probe._note_live_signal(False)

    assert probe.wakes == 1


def test_a_returning_picture_resets_the_clock(probe):
    """Kommt zwischendurch ein Bild, faengt die Dunkel-Uhr von vorn an."""
    probe._note_live_signal(False)
    probe.tick(probe._LIVE_DEAD_S - 0.5)
    probe._note_live_signal(True)
    probe.tick(1.0)
    probe._note_live_signal(False)

    assert probe.wakes == 0


def test_a_dead_camera_is_not_hammered(probe):
    """Bleibt es schwarz — Kamera aus, Kabel ab — darf die Box nicht im
    Sekundentakt den Spiegel klappern lassen."""
    for _ in range(200):
        probe.tick(0.5)
        probe._note_live_signal(False)

    elapsed = 200 * 0.5
    assert probe.wakes <= elapsed / probe._LIVE_WAKE_COOLDOWN_S + 1


def test_the_cooldown_lets_a_second_attempt_through_later(probe):
    probe._note_live_signal(False)
    probe.tick(probe._LIVE_DEAD_S + 0.1)
    probe._note_live_signal(False)
    assert probe.wakes == 1

    probe.tick(probe._LIVE_WAKE_COOLDOWN_S + probe._LIVE_DEAD_S + 0.1)
    probe._note_live_signal(False)
    probe.tick(probe._LIVE_DEAD_S + 0.1)
    probe._note_live_signal(False)

    assert probe.wakes == 2


def test_nothing_is_woken_during_a_capture(probe):
    """Waehrend Countdown und Aufnahme haelt sich das Wecken heraus."""
    probe._autowake_paused = True
    probe._note_live_signal(False)
    probe.tick(probe._LIVE_DEAD_S + 5)
    probe._note_live_signal(False)

    assert probe.wakes == 0


def test_the_wait_during_a_capture_still_counts(probe):
    """War es schon vor der Aufnahme schwarz, wird direkt danach geweckt —
    nicht erst nach weiteren vier Sekunden."""
    probe._autowake_paused = True
    probe._note_live_signal(False)
    probe.tick(probe._LIVE_DEAD_S + 5)
    probe._note_live_signal(False)

    probe._autowake_paused = False
    probe._note_live_signal(False)

    assert probe.wakes == 1


def test_without_a_waker_nothing_happens(probe):
    """Auf false gestellt (camera_auto_wake) bleibt es beim Q-Knopf."""
    probe._wake_cb = None
    probe._note_live_signal(False)
    probe.tick(probe._LIVE_DEAD_S + 1)
    probe._note_live_signal(False)

    assert probe.wakes == 0
