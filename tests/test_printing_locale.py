"""Druckererkennung darf nicht an der Systemsprache haengen.

Eigene Datei statt Ergaenzung von test_printing.py: dessen `cups`-Fixture
stubbt `lpstat -p` ausschliesslich mit englischer Ausgabe, wodurch dieser
Fehler dort strukturell unsichtbar bleibt.

Hintergrund: `lpstat -p` wird von CUPS uebersetzt. Auf einem deutschen System
lieferte der englische Parser in list_printers() nichts, damit meldete
available() False, damit blendete die UI den Druck-Knopf aus (print_ready) —
mit der irrefuehrenden Meldung "Kein Drucker in CUPS eingerichtet", obwohl ein
Drucker angeschlossen war. `lpstat -e` gibt nur nackte Namen aus und ist
deshalb sprachunabhaengig.
"""
import pytest

import printing


class FakeProc:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


# Echte Ausgaben eines deutschsprachigen macOS/CUPS.
DE_LPSTAT_P = ('Drucker „Selphy“ ist inaktiv; aktiviert seit '
               'Mon Aug 10 09:13:13 2026\n')
DE_LPSTAT_D = "System-Standardzielort: Selphy\n"
EN_LPSTAT_P = "printer Selphy is idle.  enabled since Thu 01 Jan 2026\n"


@pytest.fixture(autouse=True)
def reset_status():
    printing._status.update(available=False, printer=None, message="", checked=0.0)
    yield
    printing._status["checked"] = 0.0


@pytest.fixture
def cups_lang(monkeypatch):
    """Stubbt lpstat mit waehlbarer Sprache und optionalem `-e`-Support."""
    def install(p_out=DE_LPSTAT_P, d_out=DE_LPSTAT_D, e_out="Selphy\n", e_rc=0):
        def fake_run(args, **kw):
            if args[:2] == ["lpstat", "-e"]:
                return FakeProc(e_rc, e_out)
            if args[:2] == ["lpstat", "-p"]:
                return FakeProc(0, p_out)
            if args[:2] == ["lpstat", "-d"]:
                return FakeProc(0, d_out)
            return FakeProc(1)
        monkeypatch.setattr(printing.subprocess, "run", fake_run)
    return install


def test_german_lpstat_still_finds_the_printer(cups_lang):
    cups_lang()
    names = [p["name"] for p in printing.list_printers()]
    assert names == ["Selphy"]


def test_german_printer_counts_as_ready(cups_lang):
    """Zustand unbekannt heisst anbieten, nicht verstecken — sonst waere der
    Druck am Eventabend spurlos weg."""
    cups_lang()
    assert printing.list_printers()[0]["ready"] is True


def test_english_state_is_still_parsed(cups_lang):
    """Der Zustand darf nicht verloren gehen, wo CUPS ihn lesbar liefert."""
    cups_lang(p_out=EN_LPSTAT_P)
    printer = printing.list_printers()[0]
    assert printer["state"] == "idle"
    assert printer["ready"] is True


def test_disabled_printer_is_not_ready(cups_lang):
    cups_lang(p_out="printer Selphy is disabled since Thu 01 Jan 2026\n")
    assert printing.list_printers()[0]["ready"] is False


def test_falls_back_to_lpstat_p_when_dash_e_unsupported(cups_lang):
    """Aeltere CUPS-Versionen kennen `-e` nicht — dann bleibt der Parser."""
    cups_lang(p_out=EN_LPSTAT_P, e_rc=1, e_out="")
    assert [p["name"] for p in printing.list_printers()] == ["Selphy"]


def test_no_printer_stays_empty(cups_lang):
    cups_lang(p_out="", e_out="", e_rc=0)
    assert printing.list_printers() == []


def test_status_is_ready_on_german_system(cfg, cups_lang):
    """Der Endpunkt, an dem der Bug sichtbar wurde: die UI fragt hierueber ab.

    Bewusst refresh_status() statt available(): letzteres liest den 20-s-Cache,
    und `checked=0.0` gilt bei kleinem time.monotonic() als frisch statt als
    abgelaufen — der Test wuerde dann den zurueckgesetzten Wert pruefen.
    """
    cups_lang()
    cfg["printer_name"] = ""
    st = printing.refresh_status(cfg)
    assert st["available"] is True
    assert st["printer"] == "Selphy"


def test_resolve_printer_works_without_english(cfg, cups_lang):
    cups_lang()
    cfg["printer_name"] = ""
    assert printing.resolve_printer(cfg) == "Selphy"


def test_configured_name_is_matched_against_dash_e(cfg, cups_lang):
    cups_lang(e_out="Selphy\nHP_ENVY\n")
    cfg["printer_name"] = "HP_ENVY"
    assert printing.resolve_printer(cfg) == "HP_ENVY"


# ── Standarddrucker (lpstat -d ist ebenfalls uebersetzt) ───────────────────────

@pytest.mark.parametrize("d_out,expected", [
    ("System-Standardzielort: Selphy\n",             "Selphy"),
    ("system default destination: Selphy\n",         "Selphy"),
    ("destination par défaut du système : Selphy\n", "Selphy"),
    ("no system default destination\n",              None),
    ("Kein System-Standardzielort.\n",               None),
    ("",                                             None),
])
def test_default_printer_is_language_independent(cups_lang, d_out, expected):
    """Auf Deutsch lieferte der englische Regex None — resolve_printer() nahm
    dann den erstbesten Drucker statt des eingestellten Standards."""
    cups_lang(d_out=d_out)
    assert printing.default_printer() == expected


def test_configured_default_wins_over_first_printer(cfg, cups_lang):
    cups_lang(e_out="Buero_HP\nSelphy\n", d_out="System-Standardzielort: Selphy\n")
    cfg["printer_name"] = ""
    assert printing.resolve_printer(cfg) == "Selphy", \
        "Standarddrucker wurde ignoriert, erstbester genommen"
