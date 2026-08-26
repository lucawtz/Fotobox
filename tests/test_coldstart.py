"""Stecker raus, Stecker rein — und alles kommt von allein zurueck.

Der Kaltstart ist ein Rennen, das die Box zweimal verlieren kann:

1. `fotobox.service` haengt an graphical.target. Das Target gilt als
   erreicht, sobald der Display-Manager *gestartet* wurde — nicht, wenn die
   Autologin-Sitzung steht. Die UI fand dann keinen Bildschirm, main.py
   endete mit 1, und nach fuenf solchen Versuchen in fuenf Minuten blieb der
   Service stehen: schwarzer Schirm bis zum naechsten SSH-Login.

2. `network.target` sagt nur, dass die Netzwerk-Einrichtung begonnen hat.
   Kennt NetworkManager wlan0 noch nicht, gab hotspot.start() sofort auf —
   eine Warnzeile im Log, und die Box lief den ganzen Abend ohne
   Gaeste-WLAN, ohne dass es jemandem auffiel.

Beide Rennen sind jetzt gewonnen, indem gewartet wird. Diese Tests halten
das fest — nachweisen laesst es sich sonst nur, indem man wirklich den
Stecker zieht (dafuer: scripts/smoke_test.py, Sektion 10).
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pytest

import display_env
import hotspot
import ui as ui_mod


HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── 1. Display: warten statt aufgeben ──────────────────────────────────────

@pytest.fixture
def no_forced_driver(monkeypatch):
    """Ohne die Vorgabe aus dem Testlauf — sonst wird gar nicht gewartet."""
    monkeypatch.delenv("SDL_VIDEODRIVER", raising=False)
    monkeypatch.setattr(ui_mod.time, "sleep", lambda _s: None)


def _rounds(results, seen=None):
    """Fake fuer UI._open_display_once, das `results` der Reihe nach liefert.

    Setzt SDL_VIDEODRIVER wie das Original, damit der Test die Rueckstellung
    zwischen zwei Versuchen wirklich prueft.
    """
    calls = {"n": 0}

    def fake(verbose=True):
        if seen is not None:
            seen.append(os.environ.get("SDL_VIDEODRIVER"))
        os.environ["SDL_VIDEODRIVER"] = "x11"
        screen = results[min(calls["n"], len(results) - 1)]
        calls["n"] += 1
        return (screen, ["wayland", "x11"], None if screen else "kein Schirm")

    fake.calls = calls
    return fake


def test_ui_wartet_auf_die_autologin_sitzung(monkeypatch, no_forced_driver):
    """Die ersten Versuche scheitern, der vierte klappt — genau der Kaltstart."""
    fake = _rounds([None, None, None, "SCHIRM"])
    monkeypatch.setattr(ui_mod.UI, "_open_display_once", staticmethod(fake))

    assert ui_mod.UI._open_display() == "SCHIRM"
    assert fake.calls["n"] == 4


def test_zwischen_zwei_versuchen_wird_neu_erkannt(monkeypatch, no_forced_driver):
    """SDL_VIDEODRIVER muss vor dem naechsten Versuch wieder weg sein.

    display_env.detect haelt einen gesetzten Treiber fuer eine bewusste
    Vorgabe und liefert ihn unbesehen zurueck. Bliebe der zuletzt probierte
    'x11' stehen, saehe die Erkennung einen inzwischen aufgetauchten
    Wayland-Socket nie — die Box wartete bis zum Ende der Frist auf einen
    Stack, den es auf dieser Karte gar nicht gibt.
    """
    assert display_env.detect({"SDL_VIDEODRIVER": "x11"}, 1000,
                              lambda _p: True, lambda _p: [])["session"] == "erzwungen"

    seen = []
    fake = _rounds([None, None, "SCHIRM"], seen)
    monkeypatch.setattr(ui_mod.UI, "_open_display_once", staticmethod(fake))

    ui_mod.UI._open_display()
    assert seen == [None, None, None], f"Treiber-Vorgabe blieb stehen: {seen}"


def test_vorgegebener_treiber_wird_nicht_wiederholt(monkeypatch):
    """SDL_VIDEODRIVER von aussen heisst: der ist da oder falsch.

    Warten aendert daran nichts — und scripts/smoke_test.py wie
    scripts/preview_layouts.py haetten sonst 90 s Leerlauf pro Fehlversuch.
    """
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    fake = _rounds([None])
    monkeypatch.setattr(ui_mod.UI, "_open_display_once", staticmethod(fake))

    with pytest.raises(RuntimeError):
        ui_mod.UI._open_display()
    assert fake.calls["n"] == 1


def test_warten_endet_mit_der_frist(monkeypatch):
    """Kommt gar keine Sitzung, muss die Frist greifen — sonst haengt main.py."""
    monkeypatch.delenv("SDL_VIDEODRIVER", raising=False)
    monkeypatch.setattr(ui_mod.UI, "DISPLAY_WAIT_S", 0.05)
    monkeypatch.setattr(ui_mod.UI, "DISPLAY_RETRY_S", 0.01)
    fake = _rounds([None])
    monkeypatch.setattr(ui_mod.UI, "_open_display_once", staticmethod(fake))

    with pytest.raises(RuntimeError, match="Kein nutzbarer SDL-Videotreiber"):
        ui_mod.UI._open_display()


def test_stop_bricht_das_warten_ab(monkeypatch, no_forced_driver):
    """'systemctl stop' waehrend des Wartens darf nicht in den Hard-Kill laufen.

    main.py haengt sein SIGTERM-Flag als should_abort ein. Ohne den Ausstieg
    wartete der Prozess die vollen 90 s ab, systemd 35 s (TimeoutStopSec) und
    schoesse ihn dann ab.
    """
    fake = _rounds([None])
    monkeypatch.setattr(ui_mod.UI, "_open_display_once", staticmethod(fake))

    with pytest.raises(RuntimeError):
        ui_mod.UI._open_display(should_abort=lambda: True)
    assert fake.calls["n"] == 1


# ── 2. Hotspot: warten, bis NetworkManager das Interface kennt ─────────────

def test_hotspot_wartet_auf_das_interface(monkeypatch):
    """Beim dritten Blick ist wlan0 da — bis dahin wird nicht aufgegeben."""
    monkeypatch.setattr(hotspot.time, "sleep", lambda _s: None)
    blicke = {"n": 0}

    def fake_exists(_ifname):
        blicke["n"] += 1
        return blicke["n"] >= 3

    monkeypatch.setattr(hotspot, "_interface_exists", fake_exists)
    assert hotspot._wait_for_interface("wlan0", timeout_s=30) is True
    assert blicke["n"] == 3


def test_vorhandenes_interface_kostet_keine_zeit(monkeypatch):
    """Der Normalfall darf den Start nicht bremsen: ein Blick, fertig."""
    schlafen = []
    monkeypatch.setattr(hotspot.time, "sleep", schlafen.append)
    monkeypatch.setattr(hotspot, "_interface_exists", lambda _i: True)

    assert hotspot._wait_for_interface("wlan0") is True
    assert schlafen == []


def test_hotspot_gibt_nach_der_frist_auf(monkeypatch):
    """Ein falsch konfiguriertes Interface darf den Start nicht ewig blockieren.

    main.py baut den Hotspot VOR der UI auf — endloses Warten hiesse:
    schwarzer Schirm.
    """
    monkeypatch.setattr(hotspot, "_interface_exists", lambda _i: False)
    assert hotspot._wait_for_interface("wlan9", timeout_s=0.05,
                                       delay_s=0.01) is False


def test_connection_up_versucht_es_erneut(monkeypatch):
    """Beim Kaltstart ist das Geraet oft registriert, aber noch nicht nutzbar."""
    monkeypatch.setattr(hotspot.time, "sleep", lambda _s: None)
    versuche = {"n": 0}

    class R:
        def __init__(self, rc):
            self.returncode, self.stdout, self.stderr = rc, "", "busy"

    def fake_nmcli(args, timeout=10, check=False):
        versuche["n"] += 1
        return R(0 if versuche["n"] >= 3 else 1)

    monkeypatch.setattr(hotspot, "_nmcli", fake_nmcli)
    assert hotspot._connection_up("Test") is True
    assert versuche["n"] == 3


def test_connection_up_gibt_irgendwann_auf(monkeypatch):
    monkeypatch.setattr(hotspot.time, "sleep", lambda _s: None)
    monkeypatch.setattr(hotspot, "_nmcli", lambda *a, **k: None)
    assert hotspot._connection_up("Test", attempts=2) is False


# ── 3. Die Unit muss hinter NetworkManager einsortiert sein ────────────────

def test_unit_startet_nach_dem_networkmanager():
    """network.target allein reicht nicht — es sagt nichts ueber NM aus."""
    with open(os.path.join(HERE, "fotobox.service"), encoding="utf-8") as f:
        unit = f.read()

    # Kommentarzeilen zaehlen nicht mit — der Grund fuer die Ordnung steht
    # in der Unit direkt darueber und nennt dieselben Namen.
    directives = [l.strip() for l in unit.splitlines()
                  if "=" in l and not l.strip().startswith("#")]
    after = next((l.split("=", 1)[1] for l in directives
                  if l.startswith("After=")), "")
    assert "NetworkManager.service" in after
    assert "graphical.target" in after
    # network-online.target waere hier falsch: NetworkManager-wait-online
    # wartet auf eine aktivierte Verbindung, und die entsteht erst, wenn wir
    # selbst den AP aufspannen. Das Target liefe in seinen Timeout.
    assert not any("network-online.target" in l for l in directives)
