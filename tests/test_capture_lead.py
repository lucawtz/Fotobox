"""Wann `run_countdown` die Aufnahme startet.

Zwischen Anfrage und Belichtung liegen auf der EOS 700D Ø 3,73 s (gemessen
ueber 29 Aufnahmen, siehe Kommentar bei capture_lead_s). Der Countdown ist
standardmaessig 3 s lang — der Vorlauf ist also GROESSER als der Countdown,
und die Aufnahme muss mit ihm zusammen starten. Vorher stand capture_lead_s
auf 0,9 s, und der Verschluss fiel rund 2,8 s nach der Null: der Gast sah
3-2-1, "Lächeln!", das Standbild — und wartete dann noch drei Sekunden.

Getestet wird der echte Code aus ui.py ohne Fenster (SDL-dummy, UI-Instanz
per __new__), weil sich der Startzeitpunkt sonst nur an der Box beobachten
laesst — und dort nur als Gefuehl, nicht als Zahl.
"""
import os
import threading
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

import config
import ui as ui_mod


@pytest.fixture
def countdown_ui():
    """UI, die nichts zeichnet — nur die Ablaufsteuerung ist Gegenstand."""
    pygame.display.init()
    pygame.display.set_mode((320, 240))

    inst = ui_mod.UI.__new__(ui_mod.UI)
    inst._draw_countdown_frame = lambda *a, **k: None
    inst._draw_laecheln_frame = lambda *a, **k: None
    inst._flash = lambda *a, **k: None
    yield inst
    pygame.display.quit()


def _run(inst, seconds, lead_s):
    """Fuehrt run_countdown aus und gibt zurueck, wann ausgeloest wurde.

    Rueckgabe: Sekunden zwischen Start des Countdowns und dem Aufruf von
    on_capture. Der Verschluss wird sofort gemeldet, damit die
    "Lächeln!"-Schleife nicht in ihr Zeitfenster laeuft.
    """
    shutter = threading.Event()
    started: list = []

    def on_capture():
        started.append(time.monotonic())
        shutter.set()

    t0 = time.monotonic()
    inst.run_countdown(on_capture, seconds=seconds, lead_s=lead_s,
                       shutter=shutter)
    assert started, "on_capture muss aufgerufen worden sein"
    return started[0] - t0


def test_capture_starts_with_the_countdown_when_the_lead_exceeds_it(countdown_ui):
    """Vorlauf laenger als der Countdown: frueher als sofort geht nicht.

    Genau dieser Fall ist die Voreinstellung — 3,1 s Vorlauf gegen 3 s
    Countdown. Startete die Aufnahme stattdessen erst am Ende, faellt der
    Verschluss volle 3,7 s spaeter, und das ist das Warten, ueber das sich
    niemand freut.
    """
    delay = _run(countdown_ui, seconds=1, lead_s=3.1)

    assert delay < 0.25, \
        f"Aufnahme muss mit dem Countdown starten, kam aber nach {delay:.2f} s"


def test_without_a_lead_the_capture_waits_for_zero(countdown_ui):
    """Gegenprobe: ohne Vorlauf wird erst am Ende des Countdowns ausgeloest.

    Sonst wuerde der Test oben auch dann gruen bleiben, wenn `lead_s` gar
    nicht mehr ausgewertet wird.
    """
    delay = _run(countdown_ui, seconds=1, lead_s=0.0)

    assert delay >= 0.9, \
        f"ohne Vorlauf darf erst bei null ausgeloest werden, kam nach {delay:.2f} s"


def test_default_lead_covers_the_default_countdown():
    """Die Voreinstellung muss den Standard-Countdown wirklich ausfuellen.

    Faellt capture_lead_s je wieder unter countdown_duration, liegt ein Teil
    der Totzeit hinter "Lächeln!" statt im Countdown — der Fehler, der hier
    behoben wurde. Der Test haelt die beiden Werte aneinander, statt eine
    Zahl fuer sich zu pruefen.
    """
    lead = config.default_value("capture_lead_s")
    countdown = config.default_value("countdown_duration")

    assert lead >= countdown, (
        f"Vorlauf {lead} s deckt den Countdown von {countdown} s nicht ab — "
        "der Verschluss faellt dann nach der Null")
