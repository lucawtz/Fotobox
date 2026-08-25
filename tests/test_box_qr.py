"""Die Codes auf dem Boxbildschirm.

Zwei Stueck, und sie haben verschiedene Aufgaben:

* in der Sidebar der WLAN-Zugang — ein Scan traegt das Handy ins Netz, das
  Captive-Portal schiebt die Galerie hinterher
* auf dem Ergebnis-Schirm die Adresse genau des eben gemachten Fotos — ein
  gescannter Link landet immer im echten Browser, und nur dort kann der Gast
  sein Bild speichern

Der Sidebar-Code trug zwischenzeitlich den Galerie-Link. Das ist der einzige
Einstieg, der in einer Sackgasse enden kann: wer ihn scannt, ohne im WLAN zu
sein, bekommt eine Fehlerseite von Safari und keinen Hinweis, was fehlt.
"""
import re

import config

GALLERY = "http://fotobox.internal"


def _wlan_cfg(**over) -> dict:
    data = {
        "hotspot_enabled": True,
        "wifi_ssid": "Fotobox",
        "wifi_password": "fotobox123",
        "gallery_url": GALLERY,
    }
    data.update(over)
    return data


def _parse(payload: str) -> dict:
    """Liest den Payload so zurueck, wie ein Scanner es tut: Felder an
    unmaskierten Semikola trennen, dann die Maskierung aufloesen."""
    assert payload.startswith("WIFI:") and payload.endswith(";;")
    body = payload[len("WIFI:"):-1]
    return {k: re.sub(r"\\(.)", r"\1", v)
            for k, v in re.findall(r"([A-Z]):((?:\\.|[^;])*);", body)}


def _cfg(**over) -> dict:
    data = {"gallery_url": GALLERY, "picture_dir": "/srv/Picture_Box"}
    data.update(over)
    return data


# ── Der Normalfall ────────────────────────────────────────────────────────────

def test_code_traegt_die_wlan_daten():
    assert config.box_qr_payload(_wlan_cfg()) == "WIFI:T:WPA;S:Fotobox;P:fotobox123;;"


def test_offener_hotspot_wird_als_nopass_ausgewiesen():
    """Ohne Passwort ist der Hotspot offen — 'T:WPA;P:;' liesse das Handy
    nach einem Schluessel fragen, den es nicht gibt."""
    assert config.box_qr_payload(_wlan_cfg(wifi_password="")) == \
        "WIFI:T:nopass;S:Fotobox;;"


# ── Maskierung ────────────────────────────────────────────────────────────────

def test_sonderzeichen_ueberleben_den_scanner():
    ssid = 'Lisa\\Tom;Feier,2026:"Box"'
    pwd = 'geheim;mit\\allem,drin:"x"'
    parsed = _parse(config.build_wifi_qr(ssid, pwd))
    assert parsed["S"] == ssid
    assert parsed["P"] == pwd
    assert parsed["T"] == "WPA"


def test_backslash_wird_nicht_doppelt_maskiert():
    """Die Reihenfolge in _WIFI_QR_SPECIALS ist der ganze Punkt: kaeme der
    Backslash zuletzt, wuerde er die Maskierung der anderen Zeichen noch
    einmal maskieren und der Scanner laese '\\;' statt ';'."""
    assert _parse(config.build_wifi_qr("A;B", "passwort"))["S"] == "A;B"


# ── Rueckfall auf den Galerie-Link ────────────────────────────────────────────

def test_ohne_eigenen_hotspot_bleibt_es_beim_link():
    """Dann haengt die Box in einem fremden WLAN, dessen Zugangsdaten sie
    nicht kennt — ein WLAN-Code waere schlicht falsch."""
    cfg = _wlan_cfg(hotspot_enabled=False, gallery_url="http://192.168.2.140:5000")
    assert config.box_qr_payload(cfg) == "http://192.168.2.140:5000"


def test_zu_kurzes_passwort_faellt_auf_den_link_zurueck():
    """WPA2 verlangt 8 Zeichen, hotspot.start() verweigert kuerzere — es
    gaebe gar kein Netz, in das der Code fuehren koennte."""
    assert config.box_qr_payload(_wlan_cfg(wifi_password="kurz")) == GALLERY
    assert config.build_wifi_qr("Fotobox", "kurz") == ""


def test_ohne_ssid_faellt_es_auf_den_link_zurueck():
    assert config.box_qr_payload(_wlan_cfg(wifi_ssid="   ")) == GALLERY


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
    """Mit Default-SSID und -Passwort sind es 29 Module, auf der
    130-px-Kachel also 4 px je Modul. Jedes Zeichen mehr in SSID oder
    Passwort kann das Muster feiner machen — darunter wird es auf Distanz
    wackelig, und ui._make_qr warnt dann auch."""
    mods = _modules(config.box_qr_payload(_wlan_cfg()))
    assert mods <= 29
    assert 130 // mods >= 4


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
