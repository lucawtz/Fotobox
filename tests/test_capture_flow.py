"""Aufnahme-Ablauf (Einzelfoto / Collage) ohne Kamera und ohne Display.

Der Ablauf hing bisher fest in der State-Machine von main.py und war damit
nur auf der echten Box mit DSLR pruefbar. `main._capture_sequence` kapselt
ihn, sodass er hier mit einer Attrappen-UI und einer Attrappen-Kamera
komplett durchlaufen kann — genau das, was zum Testen auf dem Laptop fehlte.
"""
import os

import pytest
from PIL import Image

import main


class FakeUI:
    """Ersetzt die Pygame-UI: kein Fenster, kein Countdown, kein Warten.

    `run_countdown` ruft den Capture-Callback direkt auf (die echte UI startet
    ihn in einem Thread und setzt danach dasselbe done-Event), `wait_for_capture`
    meldet nur noch, ob er fertig wurde.
    """

    def __init__(self):
        self.notices = []
        self.countdowns = []

    def run_countdown(self, on_capture, seconds=3, photo_num=1, total=1):
        self.countdowns.append((photo_num, total))
        on_capture()

    def wait_for_capture(self, done, timeout=35.0, message=""):
        return done.is_set()

    def show_notice(self, title, detail="", seconds=3.5, error=True):
        self.notices.append((title, detail))


class FakeCamera:
    """Schreibt echte JPEGs. `fail_at` = 1-basierter Shot, der fehlschlaegt."""

    def __init__(self, fail_at=None, size=(600, 400)):
        self.fail_at = fail_at
        self.size = size
        self.shots = 0
        self.available = True
        self.error_message = ""

    def capture(self, directory):
        self.shots += 1
        if self.fail_at == self.shots:
            return None
        os.makedirs(directory, exist_ok=True)
        # Jeder Shot eine andere Farbe — so laesst sich spaeter pruefen, dass
        # in der Collage wirklich vier verschiedene Bilder stecken.
        path = os.path.join(directory, f"foto_{self.shots}.jpg")
        shade = 40 * self.shots
        Image.new("RGB", self.size, (shade, 120, 200 - shade)).save(path, "JPEG")
        return path


@pytest.fixture
def flow(cfg, monkeypatch):
    """UI + Kamera-Attrappe, Event-Ordner auf das tmp_path der cfg-Fixture."""
    import events

    event_dir = os.path.join(cfg["picture_dir"], "2026-08-22")
    monkeypatch.setattr(events, "current_event_dir", lambda _cfg: event_dir)
    cfg["countdown_duration"] = 0
    return FakeUI(), event_dir


def _photos_in(directory):
    if not os.path.isdir(directory):
        return []
    return sorted(f for f in os.listdir(directory) if f.endswith(".jpg"))


# ── Einzelfoto ─────────────────────────────────────────────────────────────────

def test_single_returns_the_photo(cfg, flow):
    ui, event_dir = flow
    cam = FakeCamera()

    result = main._capture_sequence(ui, cam, cfg, "single")

    assert result and os.path.isfile(result)
    assert cam.shots == 1
    assert ui.countdowns == [(1, 1)]
    assert ui.notices == []


def test_single_failure_is_reported_not_swallowed(cfg, flow):
    ui, _ = flow
    cam = FakeCamera(fail_at=1)

    assert main._capture_sequence(ui, cam, cfg, "single") is None


# ── Collage ────────────────────────────────────────────────────────────────────

def test_collage_shoots_four_and_returns_one_image(cfg, flow):
    ui, event_dir = flow
    cam = FakeCamera()

    result = main._capture_sequence(ui, cam, cfg, "collage")

    assert cam.shots == 4, "Collage muss genau vier Aufnahmen ausloesen"
    assert ui.countdowns == [(1, 4), (2, 4), (3, 4), (4, 4)], \
        "Der Gast muss sehen, der wievielte Shot laeuft"
    assert result and os.path.isfile(result)
    assert os.path.basename(result).startswith("collage_")
    assert ui.notices == []


def test_collage_lands_in_the_event_folder(cfg, flow):
    ui, event_dir = flow

    result = main._capture_sequence(ui, FakeCamera(), cfg, "collage")

    assert os.path.dirname(result) == event_dir
    # Die vier Einzelfotos bleiben liegen — sie gehoeren in die Galerie.
    assert len(_photos_in(event_dir)) == 5


def test_collage_is_a_two_by_two_grid(cfg, flow):
    ui, _ = flow

    result = main._capture_sequence(ui, FakeCamera(), cfg, "collage")

    with Image.open(result) as img:
        w, h = img.size
        quadrants = [img.getpixel(p) for p in
                     ((w // 4, h // 4), (3 * w // 4, h // 4),
                      (w // 4, 3 * h // 4), (3 * w // 4, 3 * h // 4))]
    assert len(set(quadrants)) == 4, \
        "vier verschiedene Fotos muessen in vier verschiedenen Quadranten liegen"


def test_aborted_collage_leaves_no_orphans(cfg, flow):
    """Bricht Shot 3 ab, duerfen Shot 1+2 nicht in der Galerie zurueckbleiben."""
    ui, event_dir = flow
    cam = FakeCamera(fail_at=3)

    result = main._capture_sequence(ui, cam, cfg, "collage")

    assert result is None
    assert _photos_in(event_dir) == [], "angefangene Collage muss aufgeraeumt werden"
    assert ui.notices, "der Gast muss erfahren, dass die Collage verworfen wurde"
    assert "2 von 4" in ui.notices[-1][1]
