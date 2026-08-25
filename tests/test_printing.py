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
    printing._status.update(available=False, printer=None, message="", pending=None,
                            checked=0.0)
    yield
    printing._status["checked"] = 0.0


@pytest.fixture
def cups(monkeypatch):
    """Ersetzt subprocess.run durch feste CUPS-Antworten."""
    def install(p_out=SELPHY_IDLE, d_out="system default destination: Selphy",
                lp=FakeProc(0, "request id is Selphy-1 (1 file(s))"), p_rc=0,
                jobs=None):
        """`jobs`: Zeilen wie von `lpstat -o`. None = Queue nicht auslesbar."""
        calls = []

        def fake_run(args, **kw):
            calls.append(args)
            if args[:2] == ["lpstat", "-p"]:
                return FakeProc(p_rc, p_out)
            if args[:2] == ["lpstat", "-d"]:
                return FakeProc(0, d_out)
            if args[:2] == ["lpstat", "-o"]:
                return FakeProc(1) if jobs is None else FakeProc(0, jobs)
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


# ── Randlos-Ueberstand ─────────────────────────────────────────────────────────

def _px(mm, dpi=300):
    return int(round(mm / 25.4 * dpi))


def _dark_photo(tmp_path):
    src = tmp_path / "in.jpg"
    Image.new("RGB", (6000, 4000), (30, 30, 30)).save(src, "JPEG", quality=95)
    return src


def test_bleed_grows_the_canvas_per_axis(cfg, tmp_path):
    """Der Ueberstand kommt als weisser Rand dazu, die Nutzflaeche bleibt.

    Genau darin unterscheidet sich die Korrektur von `scaling`: dort schrumpft
    das Bild, hier waechst die Leinwand darum herum.
    """
    src = _dark_photo(tmp_path)
    cfg.update(print_size_mm=[148, 100], print_dpi=300, print_bleed_mm=[2, 1.5])
    out = printing.prepare(str(src), cfg)
    try:
        with Image.open(out) as im:
            assert im.size == (_px(148 + 4), _px(100 + 3))
    finally:
        os.remove(out)


def test_bleed_only_pads_the_axis_it_is_set_on(cfg, tmp_path):
    """Der eigentliche Grund fuer die Millimeter statt eines Prozentwerts:
    beim Selphy sollen nur die Laschenseiten Rand bekommen, die echte
    Blattkante oben und unten nicht."""
    src = _dark_photo(tmp_path)
    cfg.update(print_size_mm=[148, 100], print_dpi=300, print_mode="cover",
               print_bleed_mm=[3, 0])
    out = printing.prepare(str(src), cfg)
    try:
        with Image.open(out) as im:
            px = im.load()
            mid_y, mid_x = im.height // 2, im.width // 2
            assert all(c > 245 for c in px[1, mid_y]), "links muss Rand sein"
            assert all(c > 245 for c in px[im.width - 2, mid_y]), "rechts auch"
            assert not all(c > 245 for c in px[mid_x, 1]), "oben darf keiner sein"
            assert not all(c > 245 for c in px[mid_x, im.height - 2]), "unten auch nicht"
    finally:
        os.remove(out)


def test_bleed_keeps_the_photo_at_paper_size(cfg, tmp_path):
    """Die dunkle Flaeche muss danach exakt das Papierformat einnehmen —
    sonst haette die Korrektur das Bild verkleinert statt es zu platzieren."""
    src = _dark_photo(tmp_path)
    cfg.update(print_size_mm=[148, 100], print_dpi=300, print_mode="cover",
               print_bleed_mm=[4, 2])
    out = printing.prepare(str(src), cfg)
    try:
        with Image.open(out) as im:
            px, mid_y = im.load(), im.height // 2
            dark = [x for x in range(im.width) if not all(c > 245 for c in px[x, mid_y])]
            # JPEG weicht die Kante ueber ein paar Pixel auf — 2 px Toleranz.
            assert abs((dark[-1] - dark[0] + 1) - _px(148)) <= 2
    finally:
        os.remove(out)


@pytest.mark.parametrize("value", [None, [], [2], ["a", "b"], [-5, -5], [999, 999]])
def test_absurd_bleed_does_not_break_the_print(cfg, cups, tmp_path, value):
    """Wie beim Skalierungsregler: ein Vertipper darf hoechstens den Rand
    kosten, nie den Ausdruck."""
    cups()
    src = _dark_photo(tmp_path)
    cfg.update(print_size_mm=[148, 100], print_dpi=300, print_bleed_mm=value)
    ok, _ = printing.print_photo(str(src), cfg)
    assert ok is True


def test_bleed_is_capped_at_a_quarter_of_the_edge(cfg, tmp_path):
    """Mehr als ein Viertel der Kante ist sicher ein Vertipper — und der darf
    die Nutzflaeche nicht gegen null ziehen."""
    src = _dark_photo(tmp_path)
    cfg.update(print_size_mm=[148, 100], print_dpi=300, print_bleed_mm=[999, 999])
    out = printing.prepare(str(src), cfg)
    try:
        with Image.open(out) as im:
            assert im.size == (_px(148 + 2 * 37), _px(100 + 2 * 25))
    finally:
        os.remove(out)


def test_no_bleed_is_the_old_behaviour(cfg, tmp_path):
    """Der Standard darf sich nicht geaendert haben: bestehende Boxen drucken
    nach einem Update genau wie vorher."""
    src = _dark_photo(tmp_path)
    cfg.update(print_size_mm=[148, 100], print_dpi=300)
    for value in (None, [0, 0], [0.0, 0.0]):
        cfg["print_bleed_mm"] = value
        out = printing.prepare(str(src), cfg)
        try:
            with Image.open(out) as im:
                assert im.size == (1748, 1181), value
        finally:
            os.remove(out)


def test_bleed_moves_the_test_page_corner_marks_inward(cfg):
    """Der Testdruck muss dieselbe Korrektur mitmachen wie ein Foto — sonst
    misst man mit ihm etwas anderes, als spaeter gedruckt wird."""
    cfg.update(print_size_mm=[148, 100], print_dpi=300, print_bleed_mm=[3, 3])
    page = printing.test_page(cfg, "Selphy")
    try:
        out = printing.prepare(page, cfg)
        try:
            with Image.open(out) as im:
                px = im.load()
                assert im.size == (_px(148 + 6), _px(100 + 6))
                # Aussen weiss (das ist der Ueberstand), der Eckwinkel sitzt
                # jetzt um genau diesen Ueberstand eingerueckt.
                assert all(c > 245 for c in px[2, 2])
                inset = _px(3)
                assert not all(c > 245 for c in px[inset + 2, inset + 2])
        finally:
            if out != page:
                os.remove(out)
    finally:
        os.remove(page)


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
    # Ohne auslesbare Queue bleibt es beim unverbindlichen Satz.
    assert ok is True and msg == "Bitte am Drucker warten"
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


def test_scaling_defaults_to_full_page(cfg, cups, tmp_path):
    """Ohne Konfiguration bleibt es beim bisherigen Verhalten: ganze Seite."""
    calls = cups()
    photo = tmp_path / "foto.jpg"
    Image.new("RGB", (600, 400)).save(photo, "JPEG")
    printing.print_photo(str(photo), cfg)
    assert "scaling=100" in " ".join([c for c in calls if c[0] == "lp"][0])


def test_scaling_pulls_the_print_back_onto_the_sheet(cfg, cups, tmp_path):
    """Der Regler gegen den Bleed des randlosen Selphy-Treibers."""
    calls = cups()
    photo = tmp_path / "foto.jpg"
    Image.new("RGB", (600, 400)).save(photo, "JPEG")
    cfg.update(print_scale_pct=96)
    printing.print_photo(str(photo), cfg)
    assert "scaling=96" in " ".join([c for c in calls if c[0] == "lp"][0])


@pytest.mark.parametrize("value", [0, -5, 140, "viel", None])
def test_absurd_scaling_does_not_break_the_print(cfg, cups, tmp_path, value):
    """Ein Vertipper darf hoechstens den Rand kosten, nie den Ausdruck."""
    calls = cups()
    photo = tmp_path / "foto.jpg"
    Image.new("RGB", (600, 400)).save(photo, "JPEG")
    cfg.update(print_scale_pct=value)
    ok, _ = printing.print_photo(str(photo), cfg)
    lp = " ".join([c for c in calls if c[0] == "lp"][0])
    assert ok is True
    assert any(f"scaling={n}" in lp for n in (50, 100))


@pytest.mark.parametrize("manual", ["scaling=80", "fit-to-page"])
def test_manual_scaling_option_wins(cfg, cups, tmp_path, manual):
    """Zwei widersprechende -o scaling auf einer Zeile waeren Gluecksspiel."""
    calls = cups()
    photo = tmp_path / "foto.jpg"
    Image.new("RGB", (600, 400)).save(photo, "JPEG")
    cfg.update(print_scale_pct=96, print_options=[manual])
    printing.print_photo(str(photo), cfg)
    lp = [c for c in calls if c[0] == "lp"][0]
    assert lp.count("-o") == 2               # media + die Handeinstellung
    assert "scaling=96" not in " ".join(lp)


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


# ── Warteschlange ──────────────────────────────────────────────────────────────
#
# Die Box hat keine eigene Queue, sie zaehlt die von CUPS. Der eigene Auftrag
# haengt beim Zaehlen schon mit drin — genau daran ist die Auskunft leicht um
# eins daneben, deshalb steht das hier mehrfach.

JOB = "Selphy-{} fotoboxpi 1024000 Mon 24 Aug 2026 22:30:00 CEST"


def _queue(n):
    """Baut eine lpstat -o-Ausgabe mit n Auftraegen."""
    return "".join(JOB.format(i + 1) + chr(10) for i in range(n))


def test_queue_empty_is_not_counted(cfg, cups):
    cups(jobs="")
    assert printing.pending_jobs("Selphy") == 0


def test_queue_counts_lines(cfg, cups):
    cups(jobs=_queue(3))
    assert printing.pending_jobs("Selphy") == 3


def test_queue_unreadable_is_none(cfg, cups):
    cups(jobs=None)
    assert printing.pending_jobs("Selphy") is None


def test_queue_asks_only_the_resolved_printer(cfg, cups):
    """Sonst zaehlt der Braille-Attrappendrucker mit, den resolve_printer meidet."""
    calls = cups(jobs=_queue(1))
    printing.pending_jobs("Selphy")
    assert ["lpstat", "-o", "Selphy"] in calls


def test_hint_alone_in_queue(cfg):
    # 1 = nur der eigene Auftrag, niemand davor.
    assert printing.queue_hint(cfg, 1) == "Bitte am Drucker warten"


def test_hint_one_ahead_is_singular(cfg):
    assert printing.queue_hint(cfg, 2) == "Ein Foto vor dir — etwa 1 Minute"


def test_hint_counts_others_not_own_job(cfg):
    # 4 in der Queue, davon einer der eigene -> 3 davor, 3 Minuten.
    assert printing.queue_hint(cfg, 4) == "3 Fotos vor dir — etwa 3 Minuten"


def test_hint_uses_config_duration(cfg):
    cfg["print_seconds_per_photo"] = 30
    assert printing.queue_hint(cfg, 5) == "4 Fotos vor dir — etwa 2 Minuten"


def test_hint_falls_back_on_garbage_duration(cfg):
    cfg["print_seconds_per_photo"] = "viel"
    assert "etwa 2 Minuten" in printing.queue_hint(cfg, 3)


def test_hint_never_promises_zero_minutes(cfg):
    cfg["print_seconds_per_photo"] = 1
    assert printing.queue_hint(cfg, 2) == "Ein Foto vor dir — etwa 1 Minute"


def test_hint_stays_vague_when_queue_unreadable(cfg):
    assert printing.queue_hint(cfg, None) == "Bitte am Drucker warten"


def test_print_photo_reports_the_queue(cfg, cups, tmp_path):
    cups(jobs=_queue(3))
    photo = tmp_path / "foto.jpg"
    Image.new("RGB", (600, 400)).save(photo, "JPEG")
    ok, msg = printing.print_photo(str(photo), cfg)
    assert ok is True and msg == "2 Fotos vor dir — etwa 2 Minuten"


def test_print_photo_counts_after_submitting(cfg, cups, tmp_path):
    """Vor dem lp gezaehlt waere die Auskunft um eins zu niedrig."""
    calls = cups(jobs=_queue(2))
    photo = tmp_path / "foto.jpg"
    Image.new("RGB", (600, 400)).save(photo, "JPEG")
    printing.print_photo(str(photo), cfg)
    namen = [c[0] if c[0] != "lpstat" else " ".join(c[:2]) for c in calls]
    assert namen.index("lp") < len(namen) - 1 - namen[::-1].index("lpstat -o")


def test_status_carries_pending(cfg, cups):
    cups(jobs=_queue(2))
    assert printing.refresh_status(cfg)["pending"] == 2


def test_pending_resets_when_printer_disappears(cfg, cups):
    cups(jobs=_queue(2))
    assert printing.refresh_status(cfg)["pending"] == 2
    cups(p_out="")
    assert printing.refresh_status(cfg)["pending"] is None
