"""Der LiveReader fordert eine Aufloesung an, statt den Standard zu nehmen.

Auf der Box gemessen (MacroSilicon USB3.0 Capture, EOS 700D ueber HDMI):

    ohne Anforderung   640x480     mittlere Helligkeit  4 von 255
    1920x1080 gefordert 1920x1080  sauberes Raumbild

Bei 640x480 liefert die Karte also praktisch Schwarz. Die UI verwirft
schwarze Frames (_fresh_live_frame) und zeigt "Bitte Display an der Kamera
einschalten" — obwohl Kamera und Live-View laufen. Genau dieser Zustand trat
nach jedem Stromzyklus auf, weil das Geraet dann frisch angemeldet ist und
auf seinen Standard zurueckfaellt.

Der Reconnect-Pfad braucht dieselbe Anforderung: nach einem USB-Reset ist das
Geraet ebenfalls frisch angemeldet.
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pytest

import ui as ui_mod


class FakeCap:
    """cv2.VideoCapture-Attrappe: merkt sich, was gesetzt wurde."""

    def __init__(self, opened=True, reports=None):
        self.props = {}
        self._opened = opened
        # Was get() zurueckmeldet — die Karte muss nicht liefern, was man
        # anfordert, und genau das soll auffallen.
        self._reports = reports

    def set(self, prop, value):
        self.props[prop] = value
        return True

    def get(self, prop):
        if self._reports and prop in self._reports:
            return self._reports[prop]
        return self.props.get(prop, 0)

    def isOpened(self):
        return self._opened

    def read(self):
        return False, None

    def release(self):
        pass


class Caps(list):
    """Liste der geoeffneten Attrappen, plus `state` zum Steuern.

    Eigene Klasse, weil sich an eine nackte list kein Attribut haengen laesst.
    """
    state: dict


@pytest.fixture
def caps(monkeypatch):
    """Sammelt jede geoeffnete Attrappe; der Lesethread bleibt aus."""
    made = Caps()
    state = {"opened": True, "reports": None}

    def fake_capture(device):
        c = FakeCap(state["opened"], state["reports"])
        made.append(c)
        return c

    monkeypatch.setattr(ui_mod.cv2, "VideoCapture", fake_capture)
    # Der Lesethread wuerde endlos gegen die Attrappe laufen.
    monkeypatch.setattr(ui_mod._LiveReader, "_loop", lambda self: None)
    made.state = state
    return made


W_PROP = 3   # cv2.CAP_PROP_FRAME_WIDTH
H_PROP = 4   # cv2.CAP_PROP_FRAME_HEIGHT


def test_requested_resolution_is_set(caps):
    """Ohne diese beiden set() liefert die Karte 640x480 und damit Schwarz."""
    ui_mod._LiveReader(0, (1920, 1080))

    assert caps[0].props[ui_mod.cv2.CAP_PROP_FRAME_WIDTH] == 1920
    assert caps[0].props[ui_mod.cv2.CAP_PROP_FRAME_HEIGHT] == 1080


def test_buffersize_is_still_set(caps):
    """Der Puffer von 1 bleibt — sonst laeuft das Live-Bild hinterher."""
    ui_mod._LiveReader(0, (1920, 1080))

    assert caps[0].props[ui_mod.cv2.CAP_PROP_BUFFERSIZE] == 1


def test_reconnect_requests_the_resolution_again(caps):
    """Nach einem USB-Reset ist das Geraet frisch angemeldet.

    Ohne erneute Anforderung faellt es dabei auf 640x480 zurueck, und das
    Live-Bild bleibt nach dem Wiederanlaufen schwarz — schlimmer als der
    Ausfall selbst, weil es dann so aussieht, als sei die Kamera schuld.
    """
    reader = ui_mod._LiveReader(0, (1920, 1080))
    reader._last_reconnect = -999          # Sperre gegen zu haeufiges Neuoeffnen
    reader._try_reconnect()

    assert len(caps) == 2, "der Reconnect muss ein neues Device oeffnen"
    assert caps[1].props[ui_mod.cv2.CAP_PROP_FRAME_WIDTH] == 1920
    assert caps[1].props[ui_mod.cv2.CAP_PROP_FRAME_HEIGHT] == 1080


def test_no_size_means_no_request(caps):
    """[0, 0] in der Config heisst: nimm, was das Geraet liefert."""
    ui_mod._LiveReader(0, ())

    assert ui_mod.cv2.CAP_PROP_FRAME_WIDTH not in caps[0].props
    assert ui_mod.cv2.CAP_PROP_FRAME_HEIGHT not in caps[0].props


def test_mismatch_is_logged_as_warning(caps, caplog):
    """Liefert die Karte etwas anderes, muss das im Log stehen.

    Bei schwarzem Live-Bild ist das die erste Frage, und ohne diese Zeile
    braucht es wieder eine Messung an der Box, um sie zu beantworten.
    """
    caps.state["reports"] = {ui_mod.cv2.CAP_PROP_FRAME_WIDTH: 640,
                             ui_mod.cv2.CAP_PROP_FRAME_HEIGHT: 480}

    with caplog.at_level("WARNING"):
        ui_mod._LiveReader(0, (1920, 1080))

    # getMessage() setzt die %-Argumente ein; r.message allein ist die rohe
    # Vorlage und enthaelt die Zahlen noch gar nicht.
    assert any("640x480" in r.getMessage() for r in caplog.records), caplog.text


def test_closed_device_still_raises(caps):
    """Ohne Karte bleibt es beim Fehler — die UI faengt ihn ab."""
    caps.state["opened"] = False

    with pytest.raises(RuntimeError):
        ui_mod._LiveReader(0, (1920, 1080))
