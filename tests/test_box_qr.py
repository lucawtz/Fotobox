"""Die Codes auf dem Boxbildschirm.

Zwei Stueck, und beide fuehren zu den Fotos statt ins WLAN:

* in der Sidebar der Galerie-Link
* auf dem Ergebnis-Schirm die Adresse genau des eben gemachten Fotos

Hier stand einmal der WLAN-Zugang als WIFI:-Payload, damit ein Scan das
Handy ins Netz traegt und das Captive-Portal die Galerie hinterherschiebt.
Am Geraet ist das durchgefallen — iOS oeffnet nach dem Beitritt nichts,
solange keine App das Netz anfasst, und fuer den Gast passierte sichtbar
gar nichts. Verbinden kann jeder von Hand; was niemand kann, ist eine
Adresse erraten, nachdem er das Anmeldefenster geschlossen hat.
"""
import config

GALLERY = "http://fotobox.internal"


def _cfg(**over) -> dict:
    data = {"gallery_url": GALLERY, "picture_dir": "/srv/Picture_Box"}
    data.update(over)
    return data


# ── Der Code auf dem Ergebnis-Schirm ──────────────────────────────────────────

def test_foto_url_zeigt_auf_das_einzelne_bild():
    got = config.photo_url(_cfg(), "/srv/Picture_Box/2026-08-25_fest/foto_1.jpg")
    assert got == f"{GALLERY}/photo/2026-08-25_fest/foto_1.jpg"


def test_foto_url_kodiert_sonderzeichen():
    """Eventnamen wie 'Sommerfest 2026' und Dateinamen mit & duerfen den
    Link nicht zerreissen — der Gast scannt ihn, er kann ihn nicht
    reparieren."""
    got = config.photo_url(_cfg(), "/srv/Picture_Box/Sommerfest 2026/foto & co.jpg")
    assert got == f"{GALLERY}/photo/Sommerfest%202026/foto%20%26%20co.jpg"


def test_flacher_altbestand_bekommt_keinen_link():
    """Liegt das Foto direkt im picture_dir, fehlt die Event-Komponente.
    Ein geratener Link fuehrte auf eine 404-Seite — dann lieber keiner,
    der Ergebnis-Schirm faellt auf den Sidebar-Code zurueck."""
    assert config.photo_url(_cfg(), "/srv/Picture_Box/foto_flach.jpg") == ""


def test_ohne_galerie_adresse_kein_link():
    assert config.photo_url(_cfg(gallery_url=""), "/srv/Picture_Box/fest/f.jpg") == ""
    assert config.photo_url(_cfg(), "") == ""


# ── Groesse der Muster ────────────────────────────────────────────────────────

def _modules(payload: str) -> int:
    qrcode = __import__("qrcode")
    qr = qrcode.QRCode(border=0)
    qr.add_data(payload)
    qr.make(fit=True)
    return qr.modules_count


def test_sidebar_code_bleibt_grob_genug():
    """Der Galerie-Link kommt mit 25 Modulen aus. Auf der 130-px-Kachel
    der Sidebar sind das 5 px je Modul — der Wert, gegen den die
    Kachelgroesse in ui._social_layout bemessen ist."""
    mods = _modules(GALLERY)
    assert mods <= 25
    assert 130 // mods >= 5


def test_foto_code_braucht_die_grosse_kachel():
    """Eine Foto-URL traegt Event- und Dateinamen mit und landet bei 41
    Modulen. Auf Sidebar-Groesse waeren das 3 px je Modul und der Decoder
    steigt aus; RESULT_QR_SIZE haelt ihn bei 6."""
    mods = _modules(config.photo_url(
        _cfg(), "/srv/Picture_Box/2026-08-25_hochzeit-lisa-und-tom/"
                "foto_20260825_120000.jpg"))
    assert mods <= 41
    assert 260 // mods >= 6, "Kachel zu klein fuer diese URL"
    assert 130 // mods < 4, "Annahme veraltet — dann tut es die Sidebar auch"
