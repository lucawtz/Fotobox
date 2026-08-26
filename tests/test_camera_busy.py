"""Kamera vom Desktop belegt: erkennen, freiraeumen, ehrlich melden.

Nach einem Kaltstart bietet gvfs die angeschlossene Kamera als Laufwerk an
und der Dateimanager haengt sie ein. Danach gehoert das USB-Geraet ihm, und
jeder gphoto2-Aufruf scheitert mit "Could not claim the USB device".

Beobachtet am 26.08. auf der Box: nach dem Stromzyklus lief _init glatt
durch, jeder set-config scheiterte, und am Ende stand trotzdem "Kamera
bereit (Live-View aktiviert)" im Log — waehrend auf dem Schirm kein
Live-Bild kam und kein Fehler stand. Grund: _detect() fragt den USB-Bus
(--auto-detect listet die Kamera auch dann, wenn sie belegt ist) und nicht
die Kamera selbst.
"""
import pytest

import camera as camera_mod

# Vor jedem Patch festgehalten: die Fixture ersetzt _init durch einen No-op,
# und genau das echte _init ist hier der Gegenstand. Ohne diese Zeile ruft der
# Test seinen eigenen No-op auf und prueft nichts.
_REAL_INIT = camera_mod.Camera._init


# So meldet gphoto2 ein belegtes Geraet — gekuerzt, aber im Wortlaut.
BUSY_ERR = (
    "*** Error ***\n"
    "An error occurred in the io-library ('Could not claim the USB device'): "
    "Could not claim interface 0 (Device or resource busy). Make sure no "
    "other program (gvfs-gphoto2-volume-monitor) or kernel module is using "
    "the device and you have read/write access to the device."
)

CAM_URI = "gphoto2://Canon_Inc._Canon_Digital_Camera/"

# Ausgabe von `gio mount -l` mit eingehaengter Kamera. Die URI steht doppelt
# drin — einmal als Volume-Mount, einmal als GDaemonMount; genau so sah es
# auf der Box aus, und ausgehaengt werden darf trotzdem nur einmal.
GIO_LIST = f"""Volume(0): Canon Digital Camera
  Type: GProxyVolume (GProxyVolumeMonitorGPhoto2)
  Mount(0): Canon Digital Camera -> {CAM_URI}
    Type: GProxyShadowMount (GProxyVolumeMonitorGPhoto2)
Mount(1): Canon Digital Camera -> {CAM_URI}
  Type: GDaemonMount
"""

GIO_EMPTY = "Drive(0): Generic Flash Disk\n  Type: GProxyDrive (GProxyVolumeMonitorUDisks2)\n"


class FakeResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def busy_cam(monkeypatch):
    """Camera, deren gphoto2-Aufrufe "belegt" melden, bis ausgehaengt wurde.

    `cam.gio` sammelt die abgesetzten gio-Kommandos, `cam.state["listing"]`
    bestimmt, was `gio mount -l` zurueckgibt.
    """
    monkeypatch.setattr(camera_mod.Camera, "_init", lambda self: None)
    monkeypatch.setattr(camera_mod.Camera, "_watchdog", lambda self: None)
    monkeypatch.setattr(camera_mod.Camera, "_hold_supervisor", lambda self: None)
    # Der Halter wuerde einen echten Popen absetzen; hier geht es nur um _init.
    monkeypatch.setattr(camera_mod.Camera, "_hold_start", lambda self: None)
    # _free_from_gvfs wartet eine Sekunde auf gvfsd — im Test nicht.
    monkeypatch.setattr(camera_mod.time, "sleep", lambda *_: None)

    state = {"listing": GIO_LIST, "unmounted": False, "unmount_rc": 0}
    gio = []

    def fake_run(args, **kwargs):
        args = list(args)
        if args[0] == "gio":
            gio.append(args)
            if args[1:3] == ["mount", "-l"]:
                return FakeResult(stdout=state["listing"])
            if args[1:3] == ["mount", "-u"]:
                if state["unmount_rc"] == 0:
                    state["unmounted"] = True
                return FakeResult(returncode=state["unmount_rc"])
            return FakeResult(returncode=1)
        # gphoto2: belegt, solange die Kamera noch eingehaengt ist
        if state["unmounted"]:
            return FakeResult(returncode=0)
        return FakeResult(returncode=1, stderr=BUSY_ERR)

    monkeypatch.setattr(camera_mod.subprocess, "run", fake_run)

    c = camera_mod.Camera()
    c._detect = lambda: True          # die Kamera haengt am USB — das ist ja das Problem
    c.gio = gio
    c.state = state
    yield c
    c._running = False


# ── Selbsthilfe ────────────────────────────────────────────────────────────────

def test_busy_camera_is_unmounted_and_then_works(busy_cam):
    """Belegt → aushaengen → nochmal versuchen → bereit."""
    _REAL_INIT(busy_cam)

    assert ["gio", "mount", "-u", CAM_URI] in busy_cam.gio, \
        "die eingehaengte Kamera muss ausgehaengt werden"
    assert busy_cam.available is True
    assert busy_cam.error_message == ""


def test_each_mount_point_is_released_once(busy_cam):
    """Dieselbe URI steht doppelt im gio-Listing — einmal aushaengen reicht."""
    _REAL_INIT(busy_cam)

    unmounts = [g for g in busy_cam.gio if g[1:3] == ["mount", "-u"]]
    assert len(unmounts) == 1, f"einmal aushaengen, nicht {len(unmounts)}x"


# ── Ehrlichkeit, wenn es nicht klappt ─────────────────────────────────────────

def test_camera_that_stays_busy_is_not_reported_ready(busy_cam):
    """Laesst sie sich nicht freiraeumen, darf die Box NICHT "bereit" melden.

    Das war der eigentliche Fehler: available blieb True, der Gast sah kein
    Live-Bild und auch kein Fehlerbanner.
    """
    busy_cam.state["unmount_rc"] = 1          # Aushaengen scheitert

    _REAL_INIT(busy_cam)

    assert busy_cam.available is False
    assert "belegt" in busy_cam.error_message.lower()


def test_busy_without_any_gvfs_mount_is_reported_too(busy_cam):
    """Belegt, aber kein gphoto2-Mount in Sicht — dann haelt es jemand anders.

    Auch dann ist "bereit" die falsche Antwort; die Box kann das Geraet
    nicht ansprechen.
    """
    busy_cam.state["listing"] = GIO_EMPTY

    _REAL_INIT(busy_cam)

    assert busy_cam.available is False
    assert not [g for g in busy_cam.gio if g[1:3] == ["mount", "-u"]], \
        "ohne gphoto2-Mount gibt es nichts auszuhaengen"


def test_status_for_the_gallery_matches(busy_cam):
    """Der Galerie-Server liest denselben Zustand — er darf nicht abweichen."""
    busy_cam.state["unmount_rc"] = 1

    _REAL_INIT(busy_cam)

    assert camera_mod.latest_status()["available"] is False


# ── Der gute Fall bleibt unberuehrt ───────────────────────────────────────────

def test_free_camera_is_not_unmounted(busy_cam):
    """Ist die Kamera frei, wird gar nicht erst nach Mounts gesucht.

    Sonst laege bei jedem Start ein gio-Aufruf im Weg, fuer nichts.
    """
    busy_cam.state["unmounted"] = True        # gphoto2 antwortet sofort sauber

    _REAL_INIT(busy_cam)

    assert busy_cam.gio == [], "ohne Problem kein gio"
    assert busy_cam.available is True
