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
        self.busy = []
        self.countdowns = []
        self.leads = []
        self.shutter_set = []
        # Auto-Wake muss waehrend der Aufnahme aus und danach wieder an sein.
        self.autowake = []
        # Ebenso die verlaengerte Haltezeit des Standbilds.
        self.hold_extended = []
        self.liveview_waits = []
        self.liveview_returns = True

    def run_countdown(self, on_capture, seconds=3, photo_num=1, total=1,
                      lead_s=0.0, shutter=None):
        self.countdowns.append((photo_num, total))
        self.leads.append(lead_s)
        on_capture()
        # Die echte UI wartet hier auf genau dieses Event, bevor sie
        # "Lächeln!" abraeumt — dass es gesetzt wird, sichert der Test unten.
        self.shutter_set.append(shutter.is_set() if shutter else None)

    def wait_for_capture(self, done, timeout=35.0):
        return done.is_set()

    def wait_for_liveview(self, timeout):
        # Voreinstellung: das Bild ist sofort zurueck. Der Test fuer den
        # Fehlerfall setzt liveview_returns auf False.
        self.liveview_waits.append(timeout)
        return self.liveview_returns

    def show_notice(self, title, detail="", seconds=3.5, error=True):
        self.notices.append((title, detail))

    def show_busy(self, title, detail=""):
        self.busy.append((title, detail))

    def pause_live_autowake(self, paused):
        self.autowake.append(paused)

    def hold_live_frame_longer(self, active):
        self.hold_extended.append(active)


class FakeCamera:
    """Schreibt echte JPEGs. `fail_at` = 1-basierter Shot, der fehlschlaegt."""

    capture_budget_s = 5.0

    def __init__(self, fail_at=None, size=(600, 400)):
        self.fail_at = fail_at
        self.size = size
        self.shots = 0
        self.available = True
        self.error_message = ""
        # Protokoll der Live-View-Weckrufe, jeweils mit dem Shot-Stand zum
        # Zeitpunkt des Aufrufs. Damit laesst sich pruefen, dass geweckt wird
        # NACH der Aufnahme und nicht mittendrin.
        self.wakes = []
        # Erzwungene Neustarts des Halters — nur wenn das Bild ausbleibt.
        self.forced = []

    def request_liveview(self, force=False):
        self.wakes.append(self.shots)
        if force:
            self.forced.append(self.shots)

    def capture(self, directory, on_shutter=None):
        self.shots += 1
        if on_shutter is not None:
            on_shutter()
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


# ── Live-View ──────────────────────────────────────────────────────────────────
#
# Der Live-View kommt von der HDMI-Capture-Card und setzt voraus, dass die
# Kamera im Live-View-Modus steht (Spiegel hoch). Jeder Wechsel dorthin
# klappert hoerbar und kostet einen gphoto2-Prozessstart. Deshalb darf er nur
# dort passieren, wo gleich wieder ein Live-Bild sichtbar wird — und nie in
# der Zeit, in der der Gast auf das fertige Foto wartet.


def test_liveview_is_woken_after_the_shot_not_during(cfg, flow):
    ui, _ = flow
    cam = FakeCamera()

    main._capture_sequence(ui, cam, cfg, "single")

    assert cam.wakes == [1], \
        "genau ein Weckruf, und zwar nachdem das Foto im Kasten ist"


def test_liveview_is_woken_between_collage_shots(cfg, flow):
    """Zwischen den Shots schaut der Gast auf den Countdown — dort braucht er
    das Live-Bild, um sich auszurichten."""
    ui, _ = flow
    cam = FakeCamera()

    main._capture_sequence(ui, cam, cfg, "collage")

    assert cam.wakes == [1, 2, 3, 4], \
        "nach jedem Shot einmal — nach dem letzten ueber _capture_sequence"


def test_collage_says_it_is_working_before_it_starts_rendering(cfg, flow):
    """Vier Bilder zusammenrechnen dauert sichtbar lange.

    Ohne Ansage steht der Gast vor einem Schirm, auf dem nichts passiert.
    Beim Einzelfoto gibt es nichts zusammenzurechnen, dort darf sie nicht
    kommen.
    """
    ui, _ = flow
    main._capture_sequence(ui, FakeCamera(), cfg, "collage")
    assert [t for t, _ in ui.busy] == ["Collage wird erstellt"]

    ui.busy.clear()
    main._capture_sequence(ui, FakeCamera(), cfg, "single")
    assert ui.busy == []


def test_liveview_is_forced_back_when_the_picture_stays_away(cfg, flow):
    """Ein laufender Halte-Prozess ist kein Beweis fuer ein Bild.

    Faellt sein viewfinder=1 auf "PTP Device Busy", laeuft er trotzdem weiter
    — request_liveview wuerde ohne force nie wieder nachsehen, und der Gast
    saehe die restlichen Countdowns auf schwarzem Grund.
    """
    ui, _ = flow
    ui.liveview_returns = False
    cam = FakeCamera()

    main._capture_sequence(ui, cam, cfg, "collage")

    assert cam.forced == [1, 2, 3], \
        "nach jedem Shot ausser dem letzten einmal erzwungen"


def test_liveview_is_not_forced_when_the_picture_comes_back(cfg, flow):
    """Der Normalfall darf nichts kosten: kommt das Bild von selbst, wird der
    Halter nicht angefasst — ein Neustart nimmt es fuer gut 1,5 s weg."""
    ui, _ = flow
    cam = FakeCamera()

    main._capture_sequence(ui, cam, cfg, "collage")

    assert cam.forced == []


def test_liveview_is_woken_even_when_the_shot_fails(cfg, flow):
    """Sonst bliebe die Box nach einem Fehlschlag ohne Live-Bild stehen."""
    ui, _ = flow
    cam = FakeCamera(fail_at=1)

    main._capture_sequence(ui, cam, cfg, "single")

    assert cam.wakes == [1]


def test_the_still_is_held_through_the_whole_sequence(cfg, flow):
    """Die normale Haltezeit des Standbilds ist gegen EIN Foto gerechnet.

    Eine Collage sind vier, und blieb das Live-Bild nach einem Shot weg, lief
    sie mitten im naechsten Countdown ab — der zaehlte dann auf schwarzem
    Grund weiter, und zwar fuer den Rest der Collage.
    """
    ui, _ = flow

    main._capture_sequence(ui, FakeCamera(), cfg, "collage")

    assert ui.hold_extended == [True, False], \
        "waehrend der Folge verlaengert, danach wieder die normale Haltezeit"


def test_the_extended_hold_ends_even_when_the_shot_fails(cfg, flow):
    """Sonst behielte die Box ein beliebig altes Standbild fuer immer."""
    ui, _ = flow

    main._capture_sequence(ui, FakeCamera(fail_at=1), cfg, "single")

    assert ui.hold_extended[-1] is False


def test_the_grace_outlasts_a_holder_restart():
    """Gewartet wird auf einen Halter, der gerade erst gestartet wurde.

    capture() startet ihn im finally von _usb(), noch bevor es zurueckkehrt.
    Wer kuerzer wartet als sein Neuaufbau dauert, reisst ihn ab, kurz bevor
    er liefert — und zahlt einen zweiten Neuaufbau. Genau daran lagen die
    frueheren 1,2 s.
    """
    import camera as camera_mod

    assert main.LIVEVIEW_GRACE_S > camera_mod.Camera.HOLD_GRACE_S


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


# ── Ausloese-Zeitpunkt und Live-View ───────────────────────────────────────────

def test_countdown_gets_a_lead_from_the_config(cfg, flow):
    """Der Verschluss soll fallen, waehrend "Lächeln!" steht — nicht danach.

    Zwischen dem gphoto2-Aufruf und der Belichtung liegen auf der EOS 700D
    rund 1,1 s. Ohne Vorlauf loest die Box also erst aus, wenn "Lächeln!"
    laengst wieder weg ist.
    """
    ui, _ = flow
    cfg["capture_lead_s"] = 1.4

    main._capture_sequence(ui, FakeCamera(), cfg, "single")

    assert ui.leads == [1.4]


def test_every_collage_shot_gets_the_same_lead(cfg, flow):
    ui, _ = flow

    main._capture_sequence(ui, FakeCamera(), cfg, "collage")

    assert len(ui.leads) == 4
    assert len(set(ui.leads)) == 1


def test_ui_learns_when_the_shutter_fired(cfg, flow):
    """Die Kamera meldet den Ausloesemoment, die UI haengt daran ihr Wort."""
    ui, _ = flow

    main._capture_sequence(ui, FakeCamera(), cfg, "single")

    assert ui.shutter_set == [True]


def test_autowake_is_off_while_the_photo_is_taken(cfg, flow):
    """Ein Spiegelhub mitten im Countdown waere genau der Ruckler, den das
    selbsttaetige Wecken vermeiden soll — und er kaeme zum denkbar
    schlechtesten Zeitpunkt."""
    ui, _ = flow

    main._capture_sequence(ui, FakeCamera(), cfg, "collage")

    assert ui.autowake == [True, False], "waehrend der Aufnahme aus, danach wieder an"


def test_autowake_comes_back_even_when_the_shot_fails(cfg, flow):
    ui, _ = flow

    main._capture_sequence(ui, FakeCamera(fail_at=1), cfg, "single")

    assert ui.autowake[-1] is False, "sonst bliebe das Live-Bild dauerhaft sich selbst ueberlassen"
