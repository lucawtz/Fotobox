"""gphoto2-Wrapper ohne gphoto2 und ohne Kamera.

Geprueft wird, WELCHE gphoto2-Aufrufe camera.py absetzt und wann. Genau das
war das Problem auf der echten Box: jeder Aufruf ist ein eigener Prozess mit
USB-Init, jeder Live-View-Wechsel klappt hoerbar den Spiegel, und beides lag
frueher mitten in der Wartezeit des Gastes.
"""
import os

import pytest

import camera as camera_mod

# Vor allen Fixtures festgehalten: die cam-Fixture ersetzt _init durch
# einen No-op, und genau das echte _init soll hier laufen.
_REAL_INIT = camera_mod.Camera._init


class FakeResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# So meldet gphoto2 eine fertige Aufnahme. Die erste Zeile ist der Marker, an
# dem die UI ihr "Lächeln!" abraeumt.
CAPTURE_OUTPUT = [
    "New file is in location /capt0000.jpg on the camera",
    "Saving file as foto_1.jpg",
    "Deleting file /capt0000.jpg on the camera",
]


class FakePopen:
    """Ersetzt den gphoto2-Prozess: Ausgabezeilen, Returncode, sonst nichts.

    capture() liest die Ausgabe waehrend des Laufs statt danach — deshalb
    braucht die Attrappe ein iterierbares stdout und kein fertiges Ergebnis.
    """

    def __init__(self, lines, returncode):
        self.stdout = iter(line + chr(10) for line in lines)
        self.returncode = returncode
        self.killed = False

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.killed = True


class FakeHolder:
    """Der Halte-Prozess: lebt, bis ihn jemand beendet.

    Genau das ist im echten Betrieb sein einziger Zweck — er haelt die
    PTP-Sitzung offen, damit der Live-View nicht zusammenfaellt.
    """

    def __init__(self):
        self.stopped = False

    def poll(self):
        return 0 if self.stopped else None

    def terminate(self):
        self.stopped = True

    def kill(self):
        self.stopped = True

    def wait(self, timeout=None):
        self.stopped = True
        return 0


@pytest.fixture
def cam(monkeypatch):
    """Camera ohne _init und ohne Watchdog, mit protokolliertem subprocess.

    `cam.calls` sammelt die gphoto2-Argumentlisten, `cam.state["on_capture"]`
    darf ein Callback setzen, das die heruntergeladene Datei schreibt (oder
    eben nicht), `cam.state["lines"]` bestimmt die Ausgabe des Prozesses.
    """
    monkeypatch.setattr(camera_mod.Camera, "_init", lambda self: None)
    monkeypatch.setattr(camera_mod.Camera, "_watchdog", lambda self: None)

    calls = []
    state = {"on_capture": None, "returncode": 0, "stderr": "",
             "lines": list(CAPTURE_OUTPUT)}

    def fake_run(args, **kwargs):
        calls.append(list(args))
        return FakeResult(stderr=state["stderr"])

    holders = []

    def fake_popen(args, **kwargs):
        calls.append(list(args))
        if any(a.startswith("--wait-event") for a in args):
            h = FakeHolder()
            holders.append(h)
            return h
        cb = state["on_capture"]
        if cb is not None:
            cb(kwargs.get("cwd"), args[args.index("--filename") + 1])
        return FakePopen(state["lines"], state["returncode"])

    monkeypatch.setattr(camera_mod.subprocess, "run", fake_run)
    monkeypatch.setattr(camera_mod.subprocess, "Popen", fake_popen)

    c = camera_mod.Camera()
    c.available = True
    c.HOLD_GRACE_S = 0          # im Test nicht auf den Prozessstart warten
    c.holders = holders         # jeder je gestartete Halte-Prozess
    # Ob stdbuf auf dem Testrechner liegt, darf die Aufrufliste nicht
    # veraendern — der Zeilenpuffer hat seinen eigenen Test.
    c._stdbuf = None
    c.calls = calls
    c.state = state
    return c


def _write(cwd, filename):
    with open(os.path.join(cwd, filename), "wb") as f:
        f.write(b"jpeg")


def _gphoto_verbs(calls):
    """Nur die aussagekraeftigen Argumente, ohne das fuehrende 'gphoto2'."""
    return [" ".join(a[1:]) for a in calls]


# ── Aufnahme ───────────────────────────────────────────────────────────────────

def test_capture_returns_the_downloaded_file(cam, tmp_path):
    cam.state["on_capture"] = _write

    path = cam.capture(str(tmp_path))

    assert os.path.isfile(path)
    assert os.path.basename(path).startswith("foto_")


def test_capture_is_a_single_gphoto_call(cam, tmp_path):
    """Kein Live-View davor, keiner danach.

    Frueher haengte capture() noch output=, viewfinder=1 und capture-preview
    an — drei zusaetzliche Prozessstarts und zwei Spiegelhuebe, alle in der
    Zeit, in der auf dem Bildschirm "Foto wird uebertragen" steht, obwohl
    danach der Result-Screen kommt, der gar kein Live-Bild zeigt.
    """
    cam.state["on_capture"] = _write

    cam.capture(str(tmp_path))

    assert _gphoto_verbs(cam.calls) == [
        f"--capture-image-and-download --filename {os.path.basename(cam.calls[0][-1])}"
    ]


def test_capture_without_a_file_is_an_error_not_a_phantom_path(cam, tmp_path):
    """Kein Download = Fehler.

    Vorher gab capture() den *erwarteten* Dateinamen zurueck, auch wenn nichts
    angekommen war. main.py hielt das fuer Erfolg, der Result-Screen blieb
    schwarz und der einzige Hinweis stand im Log. Haeufigste Ursache: die
    Kamera steht auf RAW+JPEG (zwei Dateien auf einen --filename).
    """
    cam.state["on_capture"] = None

    with pytest.raises(RuntimeError, match="kein Bild"):
        cam.capture(str(tmp_path))


def test_capture_reports_the_gphoto_error(cam, tmp_path):
    cam.state["returncode"] = 1
    cam.state["lines"] = ["*** Error ***",
                          "ERROR: Could not claim the USB device"]

    with pytest.raises(RuntimeError, match="Could not claim"):
        cam.capture(str(tmp_path))


# ── Ausloesemoment ─────────────────────────────────────────────────────────────

def test_capture_reports_the_shutter_moment(cam, tmp_path):
    """Der Callback kommt, sobald gphoto2 die Datei auf der Kamera meldet.

    Daran haengt die UI ihr "Lächeln!". Vorher stand das Wort blind 1200 ms
    lang da, waehrend der Verschluss auf der EOS 700D erst nach gut einer
    Sekunde faellt — der Gast wurde also regelmaessig fotografiert, waehrend
    er schon auf den Uebertragungs-Screen schaute.
    """
    cam.state["on_capture"] = _write
    fired = []

    cam.capture(str(tmp_path), on_shutter=lambda: fired.append(True))

    assert fired == [True], "genau einmal, beim Marker"


def test_capture_survives_a_missing_shutter_marker(cam, tmp_path):
    """Ohne Marker keine Meldung — aber auch kein Fehler.

    Ein aelteres gphoto2 oder ein fehlendes stdbuf darf die Aufnahme nicht
    scheitern lassen; die UI hat fuer diesen Fall ihre eigene Obergrenze.
    """
    cam.state["on_capture"] = _write
    cam.state["lines"] = ["Saving file as foto_1.jpg"]
    fired = []

    path = cam.capture(str(tmp_path), on_shutter=lambda: fired.append(True))

    assert os.path.isfile(path)
    assert fired == []


def test_capture_asks_for_line_buffering_when_stdbuf_exists(cam, tmp_path):
    """Ohne stdbuf kaeme die Marker-Zeile erst am Prozessende.

    gphoto2 puffert blockweise, sobald stdout eine Pipe ist. Dann waere der
    Marker exakt so wertlos wie das feste Zeitfenster, das er ersetzt.
    """
    cam._stdbuf = "/usr/bin/stdbuf"
    cam.state["on_capture"] = _write

    cam.capture(str(tmp_path))

    assert cam.calls[0][:3] == ["/usr/bin/stdbuf", "-oL", "gphoto2"]


def test_unavailable_camera_refuses_before_touching_usb(cam, tmp_path):
    cam.available = False

    with pytest.raises(RuntimeError):
        cam.capture(str(tmp_path))
    assert cam.calls == []


# ── Live-View: die offene Sitzung ──────────────────────────────────────────────

def _holder_cmd(calls):
    """Das Kommando des zuletzt gestarteten Halte-Prozesses."""
    for args in reversed(calls):
        if any(a.startswith("--wait-event") for a in args):
            return args
    return None


def test_the_holder_keeps_the_session_open(cam):
    """Der Live-View lebt nur, solange ein gphoto2-Prozess die PTP-Sitzung
    haelt — gemessen: bei offener Sitzung trug HDMI durchgehend ein
    Live-Bild, drei Sekunden nach Prozessende stand wieder das Info-Menue der
    Kamera. Genau dafuer gibt es diesen Prozess.
    """
    cam.wake_liveview()

    assert _holder_cmd(cam.calls) is not None
    assert cam._hold_alive()


def test_holder_sets_output_after_the_viewfinder(cam):
    """Die Reihenfolge ist der ganze Punkt.

    gphoto2 zieht beim Einschalten des Viewfinders den Ausgang selbst auf
    'PC', damit es die Frames ueber USB bekommt. Wer output vorher setzt,
    bekommt es dort ueberschrieben — an der EOS 700D gemessen: die Kamera
    meldete danach 'PC' und gab auf HDMI nichts aus, wo die Capture-Card
    haengt. Umgekehrt herum meldet sie 'TFT + PC', und das Bild kommt an.
    """
    cam.wake_liveview()

    cmd = _holder_cmd(cam.calls)
    assert cmd.index("viewfinder=1") < cmd.index("output=3")


def test_holder_sets_output_by_index_not_by_value(cam):
    """'output=3' allein ist mehrdeutig — Nummer aus der Liste oder Wert 3.

    Die 700D landete damit auf 'PC' statt auf 'TFT + PC'.
    """
    cam.wake_liveview()

    cmd = _holder_cmd(cam.calls)
    assert cmd[cmd.index("output=3") - 1] == "--set-config-index"


def test_a_wake_replaces_the_running_holder(cam):
    """Wecken heisst neu aufsetzen — der alte Prozess muss dabei weg sein,
    sonst streiten sich zwei um dasselbe USB-Geraet."""
    cam.wake_liveview()
    first = cam.holders[-1]

    cam.wake_liveview()

    assert first.stopped
    assert cam.holders[-1] is not first
    assert cam._hold_alive()


def test_no_preview_pull_anymore(cam):
    """Der capture-preview-Pull sollte den Live-View am Leben halten — was er
    nie konnte, weil auch er nur ein Prozess war, der sich beendet. Mit der
    offenen Sitzung ist er ueberfluessig und kostete nur einen Spiegelhub."""
    cam.wake_liveview()

    assert not any("--capture-preview" in " ".join(a) for a in cam.calls)


def test_background_wake_does_nothing_while_the_holder_runs(cam):
    """Der Normalfall — und er muss gratis sein, weil request_liveview aus
    der Renderschleife heraus gerufen wird."""
    cam.wake_liveview()
    cam.calls.clear()

    cam.request_liveview()

    assert cam.calls == []


def test_background_wake_revives_a_dead_holder(cam):
    cam.wake_liveview()
    cam.holders[-1].stopped = True     # Sitzung abgelaufen oder Kamera zickte
    cam.calls.clear()

    cam.request_liveview()
    assert cam._wake_gate.acquire(timeout=5), "Hintergrund-Wake wurde nie fertig"

    assert _holder_cmd(cam.calls) is not None


# ── Der Halter muss dem Rest aus dem Weg gehen ─────────────────────────────────

def test_capture_stops_the_holder_and_brings_it_back(cam, tmp_path):
    """gphoto2 kann sich das USB-Geraet nicht teilen: liefe der Halter
    weiter, bekaeme die Aufnahme "Could not claim the USB device". Danach
    muss er von selbst zurueckkommen, sonst bliebe das Live-Bild fuer immer
    weg."""
    cam.wake_liveview()
    holder = cam.holders[-1]
    cam.state["on_capture"] = _write

    cam.capture(str(tmp_path))

    assert holder.stopped, "waehrend der Aufnahme darf kein Halter laufen"
    assert cam._hold_alive(), "danach muss das Live-Bild von selbst wiederkommen"


def test_plain_commands_also_yield_the_device(cam):
    """Auch ein simples --set-config muss am Halter vorbei."""
    cam.wake_liveview()
    holder = cam.holders[-1]

    cam._set_config("reviewtime=0")

    assert holder.stopped
    assert cam._hold_alive()


def test_closing_stops_the_holder_for_good(cam):
    cam.wake_liveview()
    holder = cam.holders[-1]

    cam.close()

    assert holder.stopped
    assert not cam._hold_wanted, "sonst startet der Supervisor ihn wieder nach"


def test_background_wake_stays_out_of_a_running_capture(cam):
    """Sonst stauen sich Wake und Aufnahme auf demselben USB-Gerät."""
    cam._capturing = True

    cam.request_liveview()

    assert cam.calls == []


def test_background_wake_is_skipped_without_a_camera(cam):
    cam.available = False

    cam.request_liveview()

    assert cam.calls == []


# ── Zeitbudget ─────────────────────────────────────────────────────────────────

def test_capture_budget_covers_lock_wait_and_capture(cam):
    """main.py leitet seinen UI-Timeout hieraus ab. Liefe der Wert der
    tatsaechlichen Dauer hinterher, verwuerfe die UI wieder Fotos, die es
    laengst gibt."""
    assert cam.capture_budget_s == cam.CAPTURE_TIMEOUT_S + cam.BUSY_TIMEOUT_S


# ── Kamera-Einstellungen beim Start ────────────────────────────────────────────

@pytest.fixture
def cam_init(monkeypatch, cam):
    """Wie `cam`, aber _init laeuft wirklich durch — mit gefundener Kamera."""
    monkeypatch.setattr(camera_mod.Camera, "_detect", lambda self: True)
    cam.calls.clear()
    _REAL_INIT(cam)
    return cam


def test_init_turns_face_detection_off(cam_init):
    """LiveFace zeichnet einen Rahmen um jedes erkannte Gesicht und laesst ihn
    mitwandern — auf dem grossen Schirm der unruhigste Teil des Live-Bildes.
    'Live' ist ein kleines festes Feld in der Mitte. Ganz ohne Rahmen geht
    keine der Methoden, den zeichnet die Kamera in ihr HDMI-Signal.
    """
    assert "--set-config-index afmethod=2" in _gphoto_verbs(cam_init.calls)


def test_init_turns_the_image_review_off(cam_init):
    """Sonst blendet die Kamera nach jeder Aufnahme das Foto ins Display —
    und damit auf HDMI, wo die Box es fuer ein Live-Bild haelt."""
    assert any(v.startswith("--set-config reviewtime=0")
               for v in _gphoto_verbs(cam_init.calls))


def test_init_leaves_a_holder_running(cam_init):
    """Ohne ihn faellt der Live-View sofort wieder zusammen."""
    assert cam_init._hold_wanted
    assert cam_init._hold_alive()
