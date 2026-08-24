"""gphoto2-Wrapper ohne gphoto2 und ohne Kamera.

Geprueft wird, WELCHE gphoto2-Aufrufe camera.py absetzt und wann. Genau das
war das Problem auf der echten Box: jeder Aufruf ist ein eigener Prozess mit
USB-Init, jeder Live-View-Wechsel klappt hoerbar den Spiegel, und beides lag
frueher mitten in der Wartezeit des Gastes.
"""
import os

import pytest

import camera as camera_mod


class FakeResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def cam(monkeypatch):
    """Camera ohne _init und ohne Watchdog, mit protokolliertem subprocess.run.

    `cam.calls` sammelt die gphoto2-Argumentlisten, `cam.on_capture` darf ein
    Callback setzen, das die heruntergeladene Datei schreibt (oder eben nicht).
    """
    monkeypatch.setattr(camera_mod.Camera, "_init", lambda self: None)
    monkeypatch.setattr(camera_mod.Camera, "_watchdog", lambda self: None)

    calls = []
    state = {"on_capture": None, "returncode": 0, "stderr": ""}

    def fake_run(args, **kwargs):
        calls.append(list(args))
        if "--capture-image-and-download" in args:
            cb = state["on_capture"]
            if cb is not None:
                cb(kwargs.get("cwd"), args[args.index("--filename") + 1])
            return FakeResult(state["returncode"], stderr=state["stderr"])
        return FakeResult()

    monkeypatch.setattr(camera_mod.subprocess, "run", fake_run)

    c = camera_mod.Camera()
    c.available = True
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
    cam.state["stderr"] = "ERROR: Could not claim the USB device"

    with pytest.raises(RuntimeError, match="Could not claim"):
        cam.capture(str(tmp_path))


def test_unavailable_camera_refuses_before_touching_usb(cam, tmp_path):
    cam.available = False

    with pytest.raises(RuntimeError):
        cam.capture(str(tmp_path))
    assert cam.calls == []


# ── Live-View ──────────────────────────────────────────────────────────────────

def test_wake_does_not_reset_output_by_default(cam):
    """output bleibt in der Kamera stehen, bis es jemand aendert.

    Es bei jedem Wecken neu zu setzen war ein kompletter gphoto2-Prozessstart
    (1-2 s USB-Init) fuer nichts.
    """
    cam.wake_liveview(with_preview=False)

    assert _gphoto_verbs(cam.calls) == ["--set-config viewfinder=1"]


def test_manual_wake_resets_output_too(cam):
    """Wer den Wake-Knopf drueckt, tut das weil das Bild fehlt — dann darf es
    der grosse Hammer sein."""
    cam.wake_liveview(with_preview=False, reset_output=True)

    assert _gphoto_verbs(cam.calls) == [
        "--set-config output=3",
        "--set-config viewfinder=1",
    ]


def test_preview_pull_follows_the_configuration(monkeypatch, cam):
    cam._preview_pull = False
    cam.wake_liveview()
    assert not any("--capture-preview" in v for v in _gphoto_verbs(cam.calls))

    cam.calls.clear()
    cam._preview_pull = True
    cam.wake_liveview()
    assert any("--capture-preview" in v for v in _gphoto_verbs(cam.calls))


def test_background_wake_actually_wakes(cam):
    cam._preview_pull = False

    cam.request_liveview()
    # Der Wake laeuft in einem Thread — er ist durch, sobald er das Gate
    # wieder freigibt.
    assert cam._wake_gate.acquire(timeout=5), "Hintergrund-Wake wurde nie fertig"

    assert _gphoto_verbs(cam.calls) == ["--set-config viewfinder=1"]


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
