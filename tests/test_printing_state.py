"""Der angezeigte Druckerzustand muss der echte sein.

Eigene Datei neben test_printing_locale.py, weil hier ein anderer Fehler
abgesichert wird: dort ging es darum, dass ein vorhandener Drucker ueberhaupt
gefunden wird, hier darum, dass ein gefundener Drucker nicht faelschlich als
bereit gemeldet wird.

Hintergrund: `lpstat -p` beschreibt die Warteschlange, nicht das Geraet. Eine
freigegebene, leere Queue meldet 'idle' — auch wenn der Selphy ausgeschaltet
ist, das Papier alle ist oder das Kabel ab ist. Die Admin-Seite zeigte darauf
"ist bereit" und die Box den Drucken-Knopf; der Gast druckte ins Nichts und
merkte es erst, als nichts herauskam.

Die Zustaende kommen deshalb aus IPP (sprachneutral, mit
printer-state-reasons), und ob das Geraet ueberhaupt am Bus haengt, aus sysfs
— das weiss CUPS naemlich gar nicht.
"""
import pytest

import printing


class FakeProc:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


SELPHY_URI = "usb://Canon/SELPHY%20CP1500?serial=C125082420462327"
SELPHY_SERIAL = "C125082420462327"


def ipp_group(name, state="idle", reasons="none", uri=SELPHY_URI, accepting="true"):
    return (f"        printer-is-accepting-jobs (boolean) = {accepting}\n"
            f"        printer-state (enum) = {state}\n"
            f"        printer-state-reasons (keyword) = {reasons}\n"
            f"        printer-name (nameWithoutLanguage) = {name}\n"
            f"        device-uri (uri) = {uri}\n")


def ipp_out(*groups):
    """Ausgabe von `ipptool -tv`, so wie CUPS sie auf dem Pi liefert."""
    head = ('"/tmp/q.test":\n'
            "    CUPS-Get-Printers:\n"
            "        attributes-charset (charset) = utf-8\n"
            "    /tmp/q                                          [PASS]\n"
            "        RECEIVED: 400 bytes in response\n"
            "        status-code = successful-ok (successful-ok)\n"
            "        attributes-charset (charset) = utf-8\n")
    return head + "        -- separator --\n".join(groups)


@pytest.fixture(autouse=True)
def reset_status():
    printing._status.update(available=False, printer=None, message="", checked=0.0)
    yield
    printing._status["checked"] = 0.0


@pytest.fixture
def ipp(monkeypatch):
    """Stubbt ipptool und die USB-Seriennummern aus sysfs.

    `_usb_serials` wird mitgestubbt, damit die Tests auf einem Entwicklerrechner
    ohne /sys dasselbe pruefen wie auf dem Pi.
    """
    def install(*groups, serials=(SELPHY_SERIAL,), ipptool_ok=True):
        def fake_run(args, **kw):
            if args[0] == "ipptool":
                return FakeProc(0, ipp_out(*groups)) if ipptool_ok else None
            return FakeProc(1)

        monkeypatch.setattr(printing.subprocess, "run", fake_run)
        # serials=None steht fuer ein unlesbares sysfs, () fuer ein lesbares
        # ohne passendes Geraet — genau die Unterscheidung, an der haengt, ob
        # der Drucken-Knopf verschwindet.
        monkeypatch.setattr(printing, "_usb_serials",
                            lambda: None if serials is None else set(serials))
    return install


# ── Antwort zerlegen ──────────────────────────────────────────────────────────

def test_mehrere_drucker_aus_einer_antwort(ipp):
    """Die Gruppen einer Sammelantwort duerfen nicht ineinanderlaufen."""
    ipp(ipp_group("Selphy"), ipp_group("Buero_HP", state="stopped", uri="ipp://hp/"))
    printers = printing.list_printers()
    assert [(p["name"], p["state"]) for p in printers] == \
        [("Selphy", "idle"), ("Buero_HP", "disabled")]


def test_processing_heisst_druckt(ipp):
    ipp(ipp_group("Selphy", state="processing"))
    assert printing.list_printers()[0]["state"] == "printing"


def test_ohne_ipptool_greift_lpstat(ipp, monkeypatch):
    """Faellt ipptool aus, darf nicht die ganze Druckererkennung ausfallen."""
    def fake_run(args, **kw):
        if args[0] == "ipptool":
            return None                      # Binary fehlt
        if args[:2] == ["lpstat", "-e"]:
            return FakeProc(0, "Selphy\n")
        if args[:2] == ["lpstat", "-p"]:
            return FakeProc(0, "printer Selphy is idle.  enabled since Do\n")
        return FakeProc(1)

    monkeypatch.setattr(printing.subprocess, "run", fake_run)
    monkeypatch.setattr(printing, "_usb_serials", lambda: set())
    printer = printing.list_printers()[0]
    assert printer["name"] == "Selphy"
    assert printer["ready"] is True


# ── Was der Drucker selbst meldet ─────────────────────────────────────────────

def test_papier_leer_blockiert(ipp, cfg):
    ipp(ipp_group("Selphy", reasons="media-empty-error"))
    cfg["printer_name"] = "Selphy"
    st = printing.refresh_status(cfg)
    assert st["available"] is False
    assert "Papier leer" in st["message"]


def test_grund_traegt_schweregrad_und_klartext(ipp):
    ipp(ipp_group("Selphy", reasons="cover-open-error"))
    reason = printing.list_printers()[0]["reasons"][0]
    assert reason == {"key": "cover-open", "severity": "error",
                      "text": "Abdeckung offen", "blocking": True}


def test_farbband_fast_leer_ist_nur_ein_hinweis(ipp, cfg):
    """Ein Warnhinweis darf den Drucken-Knopf nicht wegnehmen — ein Blatt geht
    fast immer noch, und ein fehlender Knopf erklaert sich niemandem."""
    ipp(ipp_group("Selphy", reasons="marker-supply-low-warning"))
    cfg["printer_name"] = "Selphy"
    st = printing.refresh_status(cfg)
    assert st["available"] is True
    assert "Farbband fast leer" in st["message"]


def test_unbekannter_grund_wird_durchgereicht(ipp):
    """Lieber ein rohes Schluesselwort anzeigen als den Hinweis verschlucken."""
    ipp(ipp_group("Selphy", reasons="wartungsklappe-lose-warning"))
    reason = printing.list_printers()[0]["reasons"][0]
    assert reason["text"] == "wartungsklappe lose"
    assert reason["blocking"] is False


def test_mehrere_gruende_werden_alle_gemeldet(ipp):
    ipp(ipp_group("Selphy", reasons="media-empty-error,cover-open-error"))
    texts = [r["text"] for r in printing.list_printers()[0]["reasons"]]
    assert texts == ["Papier leer", "Abdeckung offen"]


def test_keine_gruende_heisst_bereit(ipp, cfg):
    ipp(ipp_group("Selphy"))
    cfg["printer_name"] = "Selphy"
    assert printing.refresh_status(cfg)["message"] == "bereit"


def test_drucker_nimmt_keine_auftraege_an(ipp):
    ipp(ipp_group("Selphy", accepting="false"))
    assert printing.list_printers()[0]["ready"] is False


# ── Haengt das Geraet ueberhaupt dran? ────────────────────────────────────────

def test_ausgeschalteter_drucker_ist_nicht_bereit(ipp, cfg):
    """Der Fall, den CUPS nicht sieht: Selphy aus, Queue meldet weiter 'idle'.

    Ohne den sysfs-Abgleich stand hier "ist bereit", der Boxschirm zeigte den
    Drucken-Knopf, und der Auftrag blieb in der Warteschlange haengen.
    """
    ipp(ipp_group("Selphy"), serials=())
    cfg["printer_name"] = "Selphy"
    st = printing.refresh_status(cfg)
    assert st["available"] is False
    assert st["connected"] is False
    assert "nicht verbunden" in st["message"]


def test_angeschlossener_drucker_bleibt_bereit(ipp, cfg):
    ipp(ipp_group("Selphy"))
    cfg["printer_name"] = "Selphy"
    st = printing.refresh_status(cfg)
    assert st["connected"] is True
    assert st["available"] is True


def test_netzwerkdrucker_wird_nicht_beurteilt(ipp, cfg):
    """Ueber einen Netzwerkdrucker sagt sysfs nichts — dann wird nichts
    behauptet, statt ihn vorsichtshalber auszublenden."""
    ipp(ipp_group("Buero_HP", uri="ipp://hp.local/ipp/print"), serials=())
    cfg["printer_name"] = "Buero_HP"
    st = printing.refresh_status(cfg)
    assert st["connected"] is None
    assert st["available"] is True


def test_usb_uri_ohne_seriennummer_wird_nicht_beurteilt(ipp):
    ipp(ipp_group("Selphy", uri="usb://Canon/SELPHY%20CP1500"), serials=())
    assert printing.list_printers()[0]["connected"] is None


def test_unlesbares_sysfs_blockiert_nicht(ipp, cfg):
    """Kein lesbares /sys heisst "unbekannt", nicht "Drucker weg".

    Sonst haette die Pruefung auf jedem System ohne /sys — und damit auf jedem
    Entwicklerrechner — den Drucken-Knopf abgeschaltet.
    """
    ipp(ipp_group("Selphy"), serials=None)
    cfg["printer_name"] = "Selphy"
    st = printing.refresh_status(cfg)
    assert st["connected"] is None
    assert st["available"] is True


# ── CUPS-Attrappen ────────────────────────────────────────────────────────────

def test_braille_drucker_ist_als_attrappe_markiert(ipp):
    ipp(ipp_group("CUPS-BRF-Printer", uri="cups-brf:/"))
    assert printing.list_printers()[0]["virtual"] is True


def test_attrappe_wird_nicht_automatisch_gewaehlt(ipp, cfg):
    """Auf einer frischen Box mit leerem printer_name stand der mitgelieferte
    Braille-Drucker sonst als bereitgemeldetes Ziel da — jedes Gastfoto waere
    darin verschwunden."""
    ipp(ipp_group("CUPS-BRF-Printer", uri="cups-brf:/"),
        ipp_group("Selphy"))
    cfg["printer_name"] = ""
    assert printing.resolve_printer(cfg) == "Selphy"


def test_ausdrueckliche_wahl_wird_respektiert(ipp, cfg):
    """Wer die Attrappe bewusst eintraegt, bekommt sie — hier wird nicht
    besser gewusst, was gemeint war."""
    ipp(ipp_group("CUPS-BRF-Printer", uri="cups-brf:/"))
    cfg["printer_name"] = "CUPS-BRF-Printer"
    assert printing.resolve_printer(cfg) == "CUPS-BRF-Printer"


def test_nur_attrappen_heisst_kein_ziel(ipp, cfg):
    ipp(ipp_group("CUPS-BRF-Printer", uri="cups-brf:/"))
    cfg["printer_name"] = ""
    assert printing.resolve_printer(cfg) is None


# ── Kosten ────────────────────────────────────────────────────────────────────

def test_statusabruf_fragt_nur_einmal_ab(ipp, cfg, monkeypatch):
    """refresh_status() holte die Liste zweimal — einmal selbst, einmal ueber
    resolve_printer(). Das faellt seit der IPP-Sammelabfrage nicht mehr auf,
    bleibt aber doppelte Arbeit an einer Stelle, die aus der Renderschleife
    der Box laeuft."""
    calls = []
    echt = printing.list_printers
    monkeypatch.setattr(printing, "list_printers",
                        lambda: (calls.append(1), echt())[1])
    ipp(ipp_group("Selphy"))
    cfg["printer_name"] = ""
    printing.refresh_status(cfg)
    assert len(calls) == 1
