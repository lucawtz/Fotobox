"""Druck-Anbindung.

Ohne echten Drucker pruefbar: die Bildaufbereitung (rechnet aufs Papierformat)
und die Auswertung der CUPS-Ausgaben. Der eigentliche Druck wird auf dem Pi
getestet.
"""
import os

import pytest
from PIL import Image

import printing


class FakeProc:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


SELPHY_IDLE = "printer Selphy is idle.  enabled since Thu 01 Jan 2026\n"


@pytest.fixture(autouse=True)
def reset_status():
    printing._status.update(available=False, printer=None, message="", checked=0.0)
    yield
    printing._status["checked"] = 0.0


@pytest.fixture
def cups(monkeypatch):
    """Ersetzt subprocess.run durch feste CUPS-Antworten."""
    def install(p_out=SELPHY_IDLE, d_out="system default destination: Selphy",
                lp=FakeProc(0, "request id is Selphy-1 (1 file(s))"), p_rc=0):
        calls = []

        def fake_run(args, **kw):
            calls.append(args)
            if args[:2] == ["lpstat", "-p"]:
                return FakeProc(p_rc, p_out)
            if args[:2] == ["lpstat", "-d"]:
                return FakeProc(0, d_out)
            if args[0] == "lp":
                if lp is None:
                    raise FileNotFoundError("lp")
                return lp
            return FakeProc(1)

        monkeypatch.setattr(printing.subprocess, "run", fake_run)
        return calls
    return install


# ── Bildaufbereitung ───────────────────────────────────────────────────────────

def _white_fraction(path):
    """Anteil weisser Flaeche. Misst die GANZE Flaeche, nicht nur eine Spalte:
    ein 1:1-Bild auf Querformat-Papier bekommt Raender links und rechts, ein
    Panorama oben und unten."""
    with Image.open(path) as im:
        px = im.load()
        ys = range(0, im.height, 5)
        xs = range(0, im.width, 5)
        white = sum(1 for y in ys for x in xs if all(c > 245 for c in px[x, y]))
        return white / (len(ys) * len(xs))


@pytest.mark.parametrize("size,expect_border", [
    ((6000, 4000), False),   # DSLR 3:2 — passt fast, randlos
    ((4000, 6000), False),   # Hochformat wird gedreht, dann randlos
    ((2000, 2000), True),    # 2x2-Collage — darf NICHT beschnitten werden
    ((6000, 1200), True),    # Panorama
])
def test_auto_mode_picks_border_by_aspect(cfg, tmp_path, size, expect_border):
    src = tmp_path / "in.jpg"
    Image.new("RGB", size, (40, 40, 40)).save(src, "JPEG")
    out = printing.prepare(str(src), cfg)
    try:
        frac = _white_fraction(out)
        assert (frac > 0.02) is expect_border, f"weiss={frac:.1%}"
    finally:
        if out != str(src):
            os.remove(out)


def test_forced_modes_override_auto(cfg, tmp_path):
    """3:2 passt fast aufs Papier — der Unterschied ist nur ein 8px-Rand,
    deshalb geometrisch statt ueber den Weissanteil pruefen."""
    src = tmp_path / "in.jpg"
    Image.new("RGB", (6000, 4000), (40, 40, 40)).save(src, "JPEG")

    def top_row_is_white(mode):
        cfg["print_mode"] = mode
        out = printing.prepare(str(src), cfg)
        try:
            with Image.open(out) as im:
                px = im.load()
                return all(all(c > 245 for c in px[x, 1])
                           for x in range(0, im.width, 17))
        finally:
            os.remove(out)

    assert top_row_is_white("fit") is True
    assert top_row_is_white("cover") is False
    assert top_row_is_white("auto") is False


def test_output_matches_paper_size(cfg, tmp_path):
    src = tmp_path / "in.jpg"
    Image.new("RGB", (6000, 4000)).save(src, "JPEG")
    cfg["print_size_mm"] = [148, 100]
    cfg["print_dpi"] = 300
    out = printing.prepare(str(src), cfg)
    try:
        with Image.open(out) as im:
            assert im.size == (1748, 1181)   # 148mm/25.4*300 x 100mm/25.4*300
    finally:
        os.remove(out)


def test_collage_keeps_all_four_edges(cfg, tmp_path):
    """Der teuerste Fehler waere, die obere und untere Fotoreihe abzuschneiden."""
    src = tmp_path / "collage.jpg"
    im = Image.new("RGB", (2000, 2000), (30, 30, 30))
    im.paste((255, 0, 0),   (0, 0, 2000, 40))        # oben
    im.paste((0, 255, 0),   (0, 1960, 2000, 2000))   # unten
    im.paste((0, 0, 255),   (0, 0, 40, 2000))        # links
    im.paste((255, 255, 0), (1960, 0, 2000, 2000))   # rechts
    im.save(src, "JPEG", quality=95)

    out = printing.prepare(str(src), cfg)
    try:
        with Image.open(out) as res:
            px = res.load()
            found = set()
            for y in range(0, res.height, 3):
                for x in range(0, res.width, 3):
                    r, g, b = px[x, y]
                    if r > 180 and g < 90 and b < 90:   found.add("oben")
                    elif g > 180 and r < 90 and b < 90: found.add("unten")
                    elif b > 180 and r < 90 and g < 90: found.add("links")
                    elif r > 180 and g > 180 and b < 90: found.add("rechts")
            assert found == {"oben", "unten", "links", "rechts"}
    finally:
        os.remove(out)


def test_broken_image_returns_original(cfg, tmp_path):
    bad = tmp_path / "kaputt.jpg"
    bad.write_bytes(b"kein JPEG")
    assert printing.prepare(str(bad), cfg) == str(bad)


def test_invalid_paper_size_falls_back(cfg, tmp_path):
    src = tmp_path / "in.jpg"
    Image.new("RGB", (600, 400)).save(src, "JPEG")
    for bad in ([0, 0], ["a", "b"], [], None):
        cfg["print_size_mm"] = bad
        out = printing.prepare(str(src), cfg)
        try:
            with Image.open(out) as im:
                assert im.size == (1748, 1181)   # Default 148x100
        finally:
            if out != str(src):
                os.remove(out)


# ── Druckerzustand ─────────────────────────────────────────────────────────────

def test_ready_printer(cfg, cups):
    cups()
    st = printing.refresh_status(cfg)
    assert st["available"] is True and st["printer"] == "Selphy"


@pytest.mark.parametrize("p_out,p_rc,expect_msg", [
    ("", 0, "Kein Drucker"),
    ("", 1, "Kein Drucker"),                                      # cupsd tot
    ("printer Selphy is disabled since Thu\n", 0, "deaktiviert"), # Papier leer
])
def test_unavailable_states(cfg, cups, p_out, p_rc, expect_msg):
    cups(p_out=p_out, p_rc=p_rc)
    st = printing.refresh_status(cfg)
    assert st["available"] is False
    assert expect_msg.lower() in st["message"].lower()


def test_missing_lpstat_binary(cfg, monkeypatch):
    def boom(args, **kw):
        raise FileNotFoundError(args[0])
    monkeypatch.setattr(printing.subprocess, "run", boom)
    assert printing.refresh_status(cfg)["available"] is False


def test_configured_printer_not_found(cfg, cups):
    cups()
    cfg["printer_name"] = "GibtsNicht"
    st = printing.refresh_status(cfg)
    assert st["available"] is False and "GibtsNicht" in st["message"]


def test_print_disabled_in_config(cfg, cups):
    cups()
    cfg["print_enabled"] = False
    assert printing.refresh_status(cfg)["available"] is False


def test_first_printer_when_no_default(cfg, cups):
    cups(p_out="printer Selphy is idle.  enabled\nprinter HP is idle.  enabled\n",
         d_out="no system default destination")
    assert printing.refresh_status(cfg)["printer"] == "Selphy"


# ── Druckauftrag ───────────────────────────────────────────────────────────────

def test_successful_job(cfg, cups, tmp_path):
    calls = cups()
    photo = tmp_path / "foto.jpg"
    Image.new("RGB", (600, 400)).save(photo, "JPEG")
    ok, msg = printing.print_photo(str(photo), cfg)
    assert ok is True and "gedruckt" in msg
    lp = [c for c in calls if c[0] == "lp"][0]
    assert lp[:3] == ["lp", "-d", "Selphy"]


def test_lp_options_from_config(cfg, cups, tmp_path):
    calls = cups()
    photo = tmp_path / "foto.jpg"
    Image.new("RGB", (600, 400)).save(photo, "JPEG")
    cfg.update(print_copies=3, print_media="Postcard",
               print_options=["StpBorderless=True"])
    printing.print_photo(str(photo), cfg)
    lp = " ".join([c for c in calls if c[0] == "lp"][0])
    assert "-n 3" in lp and "media=Postcard" in lp and "StpBorderless=True" in lp


def test_lp_error_is_reported(cfg, cups, tmp_path):
    cups(lp=FakeProc(1, "", "lp: Error - no default destination"))
    photo = tmp_path / "foto.jpg"
    Image.new("RGB", (600, 400)).save(photo, "JPEG")
    ok, msg = printing.print_photo(str(photo), cfg)
    assert ok is False and "no default destination" in msg


def test_missing_photo(cfg, cups):
    cups()
    ok, msg = printing.print_photo("/gibt/es/nicht.jpg", cfg)
    assert ok is False and "nicht gefunden" in msg


def test_no_lp_call_without_printer(cfg, cups, tmp_path):
    calls = cups(p_out="")
    photo = tmp_path / "foto.jpg"
    Image.new("RGB", (600, 400)).save(photo, "JPEG")
    ok, _ = printing.print_photo(str(photo), cfg)
    assert ok is False
    assert not [c for c in calls if c[0] == "lp"]


def test_tempfile_is_cleaned_up(cfg, cups, tmp_path):
    import glob
    import tempfile as tf
    cups()
    photo = tmp_path / "foto.jpg"
    Image.new("RGB", (6000, 4000)).save(photo, "JPEG")
    before = set(glob.glob(os.path.join(tf.gettempdir(), "fotobox-print-*")))
    printing.print_photo(str(photo), cfg)
    after = set(glob.glob(os.path.join(tf.gettempdir(), "fotobox-print-*")))
    assert after == before, "temporaeres Druckbild nicht aufgeraeumt"


def test_status_is_cached(cfg, cups, monkeypatch):
    calls = cups()
    printing.status(cfg)
    n1 = len(calls)
    printing.status(cfg)                 # sofort danach: aus dem Cache
    assert len(calls) == n1
    # Nach Ablauf der TTL wird wieder gefragt
    monkeypatch.setattr(printing, "_STATUS_TTL_S", -1)
    printing.status(cfg)
    assert len(calls) > n1


# ── Testdruck ──────────────────────────────────────────────────────────────────

def test_test_page_matches_paper_size(cfg):
    """Die Testseite muss exakt im Papierformat liegen — sonst wuerde prepare()
    sie beschneiden, und der gedruckte Rahmen saesse nicht mehr am Blattrand."""
    cfg["print_size_mm"] = [148, 100]
    cfg["print_dpi"] = 300
    page = printing.test_page(cfg, "Selphy")
    try:
        with Image.open(page) as im:
            assert (im.width, im.height) == (1748, 1181)
    finally:
        os.remove(page)


def test_test_page_survives_prepare_unchanged(cfg):
    """Egal welcher print_mode: die Seite darf weder Rand bekommen noch
    beschnitten werden, sonst misst man die Aufbereitung statt den Drucker."""
    cfg["print_size_mm"] = [148, 100]
    page = printing.test_page(cfg, "Selphy")
    try:
        for mode in ("auto", "cover", "fit"):
            cfg["print_mode"] = mode
            out = printing.prepare(page, cfg)
            try:
                with Image.open(out) as im:
                    size = (im.width, im.height)
                assert size == (1748, 1181), mode
                # Der Eckwinkel sitzt am Blattrand; ein weisser Rand hier
                # hiesse, dass 'fit' die Seite verkleinert hat.
                with Image.open(out) as im:
                    assert im.load()[2, 2] != (255, 255, 255), mode
            finally:
                if out != page:
                    os.remove(out)
    finally:
        os.remove(page)


@pytest.mark.parametrize("size", [[148, 100], [180, 130], [100, 148], [60, 40]])
def test_test_page_renders_on_any_format(cfg, size):
    """Kleines wie grosses Papier, quer wie hoch — die Seite darf nirgends
    ueber den Rand laufen oder beim Zeichnen aussteigen."""
    cfg["print_size_mm"] = size
    page = printing.test_page(cfg, "Selphy")
    try:
        with Image.open(page) as im:
            assert im.width >= im.height, "Testseite ist immer Querformat"
    finally:
        os.remove(page)


def test_print_test_forces_single_copy(cfg, cups):
    """print_copies gilt fuer Gaeste-Fotos, nicht fuer den Test: 9 Testblatt
    waeren ein teurer Vertipper."""
    calls = cups()
    cfg["print_copies"] = 9
    ok, msg = printing.print_test(cfg)
    assert ok is True, msg
    lp = next(c for c in calls if c[0] == "lp")
    assert "-n" not in lp, f"Testdruck mit mehreren Kopien: {lp}"
    assert cfg["print_copies"] == 9, "Config wurde veraendert statt kopiert"


def test_print_test_without_printer_does_not_print(cfg, cups):
    calls = cups(p_out="")
    ok, msg = printing.print_test(cfg)
    assert ok is False
    assert "Kein Drucker" in msg
    assert not [c for c in calls if c[0] == "lp"]


def test_print_test_cleans_up_both_tempfiles(cfg, cups):
    import glob
    import tempfile as tf
    cups()
    pattern = os.path.join(tf.gettempdir(), "fotobox-*")
    before = set(glob.glob(pattern))
    printing.print_test(cfg)
    assert set(glob.glob(pattern)) == before, "Testseite oder Druckbild blieb liegen"
