"""Die Box kommt nach einem ungewollten Ende von selbst zurueck.

Am 26.08. lag die Box zweimal tot da, einmal ueber Nacht — neun Stunden, ohne
eine einzige Fehlerzeile. Grund: main.py endet auch dann mit 0, wenn die
Display-Session wegbricht. Fuer systemd sah das aus wie ein geordnetes Ende,
und Restart=on-failure greift dabei nicht.

Jetzt startet die Unit bei JEDEM Ende neu — mit genau einer Ausnahme, dem
bewussten Esc am Boxbildschirm. Diese Ausnahme haengt an einer Zahl, die in
zwei Dateien steht: EXIT_USER_QUIT in main.py und RestartPreventExitStatus in
fotobox.service. Laufen sie auseinander, faellt nichts auf — die Box beendet
sich dann still und bleibt aus, oder sie startet nach Esc stur wieder.
Deshalb dieser Test.
"""
import os
import re

import pytest

import main

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNIT = os.path.join(HERE, "fotobox.service")


@pytest.fixture(scope="module")
def unit():
    with open(UNIT, encoding="utf-8") as f:
        return f.read()


def _directive(unit: str, key: str):
    """Wert einer systemd-Direktive, Kommentarzeilen ignoriert."""
    for line in unit.splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        if name.strip() == key:
            return value.strip()
    return None


def test_service_restarts_on_any_exit(unit):
    """on-failure reicht nicht: der stille Exit 0 ist genau der Fall."""
    assert _directive(unit, "Restart") == "always"


def test_exception_matches_the_exit_code_in_main(unit):
    """Die 42 an beiden Orten muss dieselbe sein."""
    prevented = _directive(unit, "RestartPreventExitStatus")

    assert prevented is not None, "ohne Ausnahme startet Esc die Box wieder"
    assert int(prevented) == main.EXIT_USER_QUIT


def test_exit_code_is_not_zero(unit):
    """Der gewollte Ausstieg braucht einen eigenen Code.

    Mit 0 waere er von "Display weg" nicht zu unterscheiden — und genau
    diese Verwechslung war der Fehler.
    """
    assert main.EXIT_USER_QUIT != 0


def test_restart_loop_is_still_capped(unit):
    """Restart=always ohne Bremse schreibt bei dauerhaftem Fehler die Karte voll."""
    assert _directive(unit, "StartLimitBurst") is not None
    assert _directive(unit, "StartLimitIntervalSec") is not None


def test_deliberate_quit_is_wired_up():
    """main.py muss den Code auch wirklich zurueckgeben.

    Die Konstante allein tut nichts — sie braucht ein sys.exit auf dem
    Esc-Pfad, und zwar hinter dem Aufraeumen.
    """
    with open(os.path.join(HERE, "main.py"), encoding="utf-8") as f:
        src = f.read()

    assert "sys.exit(EXIT_USER_QUIT)" in src, \
        "der gewollte Ausstieg gibt seinen Code nicht zurueck"
    # Hinter dem Aufraeumen: sonst blieben Hotspot und Kamera-Sitzung stehen.
    assert src.index('logger.info("Fotobox beendet")') < src.index("sys.exit(EXIT_USER_QUIT)"), \
        "erst aufraeumen, dann beenden"


def test_stop_timeout_survives_a_running_capture(unit):
    """Beim Neustart mitten im Foto darf gphoto2 nicht hart gekillt werden.

    Steht hier mit, weil Restart=always die Zahl haeufiger zur Anwendung
    bringt als vorher: jeder ungewollte Exit fuehrt jetzt zu einem Neustart.
    """
    assert re.match(r"^\d+$", _directive(unit, "TimeoutStopSec") or "")
    assert int(_directive(unit, "TimeoutStopSec")) >= 30
