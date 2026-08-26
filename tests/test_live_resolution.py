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

    # _fourcc_name liest CAP_PROP_FOURCC zurueck; ohne gesetzten Wert kommt
    # 0 heraus und das Kuerzel ist leer — genau der Fall "Karte hat das
    # Format abgelehnt".

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


# ── Fehlende Karte beim Start ─────────────────────────────────────────────────
#
# Frueher warf _LiveReader hier, die UI setzte self._live auf None und
# versuchte es NIE wieder: auf dem Boxschirm stand "Warte auf Kamera", auch
# nachdem die Karte laengst wieder steckte. Am 26.08. dreimal passiert — die
# Karte faellt mit "error -71" vom Bus und muss neu gesteckt werden.

def test_a_missing_device_does_not_raise(caps):
    """Kein Fehler mehr: die Leseschleife holt die Karte selbst zurueck."""
    caps.state["opened"] = False

    reader = ui_mod._LiveReader(0, (1920, 1080), "MJPG", 6)

    assert reader.is_open() is False


def test_a_missing_device_is_still_retried(caps):
    """Der Reconnect-Pfad muss auch ohne Karte beim Start erreichbar sein."""
    caps.state["opened"] = False
    reader = ui_mod._LiveReader(0, (1920, 1080), "MJPG", 6)

    caps.state["opened"] = True          # Karte wieder eingesteckt
    reader._last_reconnect = -999
    reader._try_reconnect()

    assert reader.is_open() is True, "die zurueckgekehrte Karte muss greifen"
    assert len(caps) == 2


def test_is_open_reflects_the_device(caps):
    """Woran die UI ihre Meldung unterscheidet."""
    assert ui_mod._LiveReader(0, (1920, 1080), "MJPG", 6).is_open() is True

    caps.state["opened"] = False
    assert ui_mod._LiveReader(0, (1920, 1080), "MJPG", 6).is_open() is False


# ── Bildformat und Bildrate ───────────────────────────────────────────────────
# Auf der Box gemessen: YUYV 5,0 fps bei 21 MB/s USB-Last, MJPG 30,0 fps bei
# ~2 MB/s. Der Standard der Karte ist YUYV — ohne Anforderung laeuft das
# Live-Bild also mit 5 Bildern pro Sekunde und saettigt dabei einen Bus, den
# sich Kamera und Drucker teilen. Beide USB-Ausfaelle vom 26.08. passen dazu.

def test_fourcc_is_requested(caps):
    """Ohne diese Anforderung faellt die Karte auf YUYV zurueck."""
    ui_mod._LiveReader(0, (1920, 1080), "MJPG", 12)

    want = ui_mod.cv2.VideoWriter_fourcc(*"MJPG")
    assert caps[0].props[ui_mod.cv2.CAP_PROP_FOURCC] == want


def test_fourcc_is_set_before_the_resolution(caps):
    """Reihenfolge zaehlt: ein spaeterer Formatwechsel wirft die Groesse um.

    FakeCap.props ist ein dict und behaelt seit Python 3.7 die
    Einfuegereihenfolge — damit laesst sich das hier ueberhaupt pruefen.
    """
    ui_mod._LiveReader(0, (1920, 1080), "MJPG", 12)

    order = list(caps[0].props)
    assert order.index(ui_mod.cv2.CAP_PROP_FOURCC) < \
           order.index(ui_mod.cv2.CAP_PROP_FRAME_WIDTH)


def test_empty_fourcc_means_no_request(caps):
    """Leer in der Config heisst: nimm, was die Karte von sich aus liefert."""
    ui_mod._LiveReader(0, (1920, 1080), "", 12)

    assert ui_mod.cv2.CAP_PROP_FOURCC not in caps[0].props


def test_frame_rate_comes_from_the_config(caps):
    """Nicht "so schnell wie moeglich": jedes Bild kostet rund 18 ms CPU.

    Der Pi laeuft ohne aktive Kuehlung bei knapp 80 Grad — die Bildrate ist
    deshalb ein Regler und keine Konstante.
    """
    reader = ui_mod._LiveReader(0, (1920, 1080), "MJPG", 12)

    assert reader._fps == 12
    assert reader._fps != ui_mod._LiveReader._TARGET_FPS, \
        "sonst pruefte der Test nur den alten Festwert"


def test_reconnect_keeps_format_and_rate(caps):
    """Nach einem USB-Reset ist das Geraet frisch — beides muss wieder hin."""
    reader = ui_mod._LiveReader(0, (1920, 1080), "MJPG", 12)
    reader._last_reconnect = -999
    reader._try_reconnect()

    want = ui_mod.cv2.VideoWriter_fourcc(*"MJPG")
    assert caps[1].props[ui_mod.cv2.CAP_PROP_FOURCC] == want
    assert reader._fps == 12
