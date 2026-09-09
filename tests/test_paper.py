"""Der Papiervorrat muss gezaehlt werden, weil der Drucker ihn nicht meldet.

Ueber CUPS sagt der Selphy nur `media-empty`, und das erst, wenn das letzte
Blatt durch ist — zum Nachlegen ist das zu spaet. paper.py zaehlt deshalb die
angenommenen Druckauftraege mit.

Abgesichert wird hier vor allem, was der Zaehler NICHT tun darf: er darf einen
Druck nicht kippen, wenn er selbst kaputt geht, und er darf nach einem
Neustart mitten im Event nicht bei null anfangen. Beides waere schlimmer als
gar kein Zaehler.
"""
import json
import os

import pytest
from PIL import Image

import config
import paper
import printing
import ui as ui_mod


@pytest.fixture
def paper_cfg(cfg):
    """Config mit eingeschaltetem Zaehler. Die Zustandsdatei liegt neben der
    (vom conftest auf tmp_path umgebogenen) config.json — jeder Test bekommt
    dadurch seinen eigenen Stand."""
    cfg.update(paper_pack_size=108, paper_warn_at=10)
    return cfg


class FakeProc:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


@pytest.fixture
def cups(monkeypatch):
    """Ein bereiter Drucker, der jeden Auftrag annimmt."""
    def fake_run(args, **kw):
        if args[:2] == ["lpstat", "-p"]:
            return FakeProc(0, "printer Selphy is idle.  enabled since ...")
        if args[:2] == ["lpstat", "-d"]:
            return FakeProc(0, "system default destination: Selphy")
        if args[0] == "lp":
            return FakeProc(0, "request id is Selphy-1 (1 file(s))")
        return FakeProc(1)
    monkeypatch.setattr(printing.subprocess, "run", fake_run)


def _photo(tmp_path):
    path = tmp_path / "foto.jpg"
    Image.new("RGB", (600, 400)).save(path, "JPEG")
    return str(path)


# ── Zaehlen ────────────────────────────────────────────────────────────────────

def test_a_print_takes_one_sheet(paper_cfg):
    paper.refill(paper_cfg)
    st = paper.record(paper_cfg, 1)
    assert (st["used"], st["left"]) == (1, 107)


def test_copies_take_as_many_sheets_as_they_print(paper_cfg, cups, tmp_path):
    """Drei Kopien sind drei Blatt. Der Zaehler muss dieselbe Zahl nehmen, die
    auch auf der lp-Kommandozeile landet — sonst laeuft er bei jedem Druck um
    zwei Blatt daneben."""
    paper.refill(paper_cfg)
    paper_cfg["print_copies"] = 3
    ok, _ = printing.print_photo(_photo(tmp_path), paper_cfg)
    assert ok is True
    assert paper.state(paper_cfg)["left"] == 105


def test_test_print_counts_a_single_sheet(paper_cfg, cups, tmp_path, monkeypatch):
    """Der Testdruck zieht genau ein Blatt, auch wenn 5 Kopien eingestellt sind
    — er geht mit print_copies=1 durch print_photo (printing.print_test)."""
    paper.refill(paper_cfg)
    paper_cfg["print_copies"] = 5
    monkeypatch.setattr(printing, "test_page", lambda cfg, printer=None: _photo(tmp_path))
    ok, _ = printing.print_test(paper_cfg)
    assert ok is True
    assert paper.state(paper_cfg)["used"] == 1


def test_a_rejected_job_costs_no_paper(paper_cfg, monkeypatch, tmp_path):
    """Abgelehnt heisst: es kam kein Blatt heraus. Wer nach einer Fehlermeldung
    trotzdem Papier verliert, misstraut dem Zaehler zu Recht."""
    paper.refill(paper_cfg)

    def fake_run(args, **kw):
        if args[:2] == ["lpstat", "-p"]:
            return FakeProc(0, "printer Selphy is idle.  enabled since ...")
        if args[:2] == ["lpstat", "-d"]:
            return FakeProc(0, "system default destination: Selphy")
        if args[0] == "lp":
            return FakeProc(1, "", "lp: Der Drucker 'Selphy' ist deaktiviert")
        return FakeProc(1)
    monkeypatch.setattr(printing.subprocess, "run", fake_run)

    ok, _ = printing.print_photo(_photo(tmp_path), paper_cfg)
    assert ok is False
    assert paper.state(paper_cfg)["used"] == 0


def test_a_broken_counter_does_not_stop_the_print(paper_cfg, cups, tmp_path,
                                                  monkeypatch):
    """Die wichtigste Eigenschaft des Zaehlers: er ist Beiwerk. Geht er kaputt,
    wird trotzdem gedruckt — ein Gast, der wegen einer Buchhaltung kein Foto
    bekommt, waere der schlechteste denkbare Tausch."""
    def boom(*a, **kw):
        raise OSError("Dateisystem nur lesbar")
    monkeypatch.setattr(paper, "record", boom)
    ok, _ = printing.print_photo(_photo(tmp_path), paper_cfg)
    assert ok is True


def test_the_count_survives_a_restart(paper_cfg):
    """Ein Absturz mitten im Event darf den Stand nicht vergessen — deshalb
    liegt er auf der Platte und nicht nur im Speicher."""
    paper.refill(paper_cfg)
    paper.record(paper_cfg, 7)
    # Wie nach einem Neustart: nichts mehr im Speicher.
    paper._cache = None
    paper._cache_key = None
    assert paper.state(paper_cfg)["left"] == 101


# ── Warnen ─────────────────────────────────────────────────────────────────────

def test_warning_starts_at_the_configured_threshold(paper_cfg):
    paper.refill(paper_cfg)
    paper.record(paper_cfg, 108 - 11)
    assert paper.state(paper_cfg)["low"] is False
    paper.record(paper_cfg, 1)
    st = paper.state(paper_cfg)
    assert st["left"] == 10 and st["low"] is True and st["empty"] is False


def test_an_overdrawn_pack_stops_at_zero(paper_cfg):
    """Nachgelegt, ohne den Zaehler zurueckzusetzen: der Stand geht ins Minus.
    Angezeigt wird trotzdem 0 — eine negative Blattzahl gibt es nicht."""
    paper.refill(paper_cfg)
    paper.record(paper_cfg, 130)
    st = paper.state(paper_cfg)
    assert st["left"] == 0 and st["empty"] is True


# ── Aus und wieder an ──────────────────────────────────────────────────────────

def test_without_a_pack_size_nothing_is_claimed(cfg):
    """Ohne hinterlegte Paketgroesse zeigen Panel und Statusleiste gar nichts.
    Eine geratene Zahl waere schlimmer als keine — ihr glaubt man."""
    cfg["paper_pack_size"] = 0
    st = paper.state(cfg)
    assert st["tracked"] is False and st["low"] is False and st["empty"] is False


def test_counting_runs_even_while_switched_off(cfg):
    """Gezaehlt wird auch ohne Paketgroesse. Sonst stuende der Zaehler beim
    spaeteren Einschalten auf einem Stand von vorgestern, und ausgerechnet die
    erste angezeigte Zahl waere die falscheste."""
    cfg["paper_pack_size"] = 0
    paper.refill(cfg)
    paper.record(cfg, 4)
    cfg["paper_pack_size"] = 108
    assert paper.state(cfg)["left"] == 104


# ── Korrigieren ────────────────────────────────────────────────────────────────

def test_refill_starts_over(paper_cfg):
    paper.record(paper_cfg, 50)
    st = paper.refill(paper_cfg)
    assert st["used"] == 0 and st["left"] == 108 and st["loaded_at"] is not None


def test_counting_by_hand_wins(paper_cfg):
    """Nach einem Stau stimmt der Zaehler nicht mehr. Wer nachzaehlt, muss ihn
    geradeziehen koennen, ohne ein halbes Paket zu verwerfen."""
    paper.refill(paper_cfg)
    paper.record(paper_cfg, 20)
    st = paper.set_left(paper_cfg, 60)
    assert st["left"] == 60 and st["used"] == 48


def test_hand_correction_is_not_a_new_pack(paper_cfg):
    """`loaded_at` bleibt stehen: von Hand korrigiert ist nicht dasselbe wie
    frisch eingelegt, und das Panel schreibt daneben, wann zuletzt nachgelegt
    wurde."""
    st = paper.refill(paper_cfg)
    loaded = st["loaded_at"]
    assert paper.set_left(paper_cfg, 30)["loaded_at"] == loaded


def test_more_than_a_pack_cannot_be_claimed(paper_cfg):
    """In eine 108er-Kassette passen keine 500 Blatt."""
    assert paper.set_left(paper_cfg, 500)["left"] == 108


def test_hand_correction_needs_a_pack_size(cfg):
    """Ohne Bezugswert gibt es keinen Rest. Der Endpunkt faengt das mit einer
    Klartextmeldung ab, hier zaehlt nur: es wird nichts kaputtgerechnet."""
    cfg["paper_pack_size"] = 0
    paper.record(cfg, 5)
    assert paper.set_left(cfg, 40)["used"] == 5


# ── Robustheit ─────────────────────────────────────────────────────────────────

def test_a_corrupt_state_file_does_not_break_anything(paper_cfg):
    """Eine halb geschriebene Datei (Stromausfall) darf hoechstens den Zaehler
    kosten, nicht den Druck."""
    path = os.path.join(os.path.dirname(config.CONFIG_PATH), ".paper_state.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"used": 4')
    paper._cache = None
    paper._cache_key = None
    assert paper.state(paper_cfg)["left"] == 108
    assert paper.record(paper_cfg, 1)["used"] == 1


@pytest.mark.parametrize("value", [None, "", "viele", -5, 1e9, [108]])
def test_absurd_pack_sizes_do_not_break_the_display(cfg, value):
    """Ein Vertipper im Panel darf hoechstens den Zaehler abschalten."""
    cfg["paper_pack_size"] = value
    st = paper.state(cfg)
    assert 0 <= st["size"] <= paper.PACK_MAX and st["left"] >= 0


def test_state_file_lives_next_to_the_config(paper_cfg):
    """Neben der config.json, nicht bei den Fotos: der Stand gehoert zur Box.
    Ein neuer Event-Ordner faengt bei null an, die Kassette nicht."""
    paper.refill(paper_cfg)
    path = os.path.join(os.path.dirname(config.CONFIG_PATH), ".paper_state.json")
    with open(path, encoding="utf-8") as f:
        assert json.load(f)["used"] == 0


# ── Statusleiste der Box ───────────────────────────────────────────────────────
#
# Die Leiste ist das einzige, was der Betreiber waehrend des Events sieht —
# das Admin-Panel liegt auf dem Handy, der Boxschirm steht vor ihm. Geprueft
# wird nur die Textzeile, nicht das Rendering: dafuer braeuchte es ein
# Display, und die Entscheidung "was steht da" haengt nicht daran.

def _bar_item(state):
    """`_paper_item` ohne pygame-Fenster: die Methode liest nur self.paper."""
    fake = ui_mod.UI.__new__(ui_mod.UI)
    fake.paper = state
    return ui_mod.UI._paper_item(fake)


def test_status_bar_stays_quiet_without_a_pack_size(cfg):
    cfg["paper_pack_size"] = 0
    assert _bar_item(paper.state(cfg)) is None


def test_status_bar_says_ca(paper_cfg):
    """"ca." gehoert an die Zahl, nicht in eine Fussnote: wer dem Zaehler
    blind glaubt, steht mit leerer Kassette da."""
    paper.refill(paper_cfg)
    paper.record(paper_cfg, 8)
    text, color = _bar_item(paper.state(paper_cfg))
    assert text == "Papier: ca. 100" and color == ui_mod.C_DIM


def test_status_bar_turns_yellow_before_it_matters(paper_cfg):
    paper.refill(paper_cfg)
    paper.record(paper_cfg, 100)
    text, color = _bar_item(paper.state(paper_cfg))
    assert text == "Papier: ca. 8" and color == ui_mod.C_YELLOW


def test_an_empty_pack_does_not_claim_zero_sheets(paper_cfg):
    """Der Zaehler weiss nicht, ob wirklich Schluss ist — nur, dass ein Paket
    rechnerisch durch ist. Genau das soll dastehen."""
    paper.refill(paper_cfg)
    paper.record(paper_cfg, 108)
    text, color = _bar_item(paper.state(paper_cfg))
    assert text == "Papier: Paket durch" and color == ui_mod.C_RED
