"""Der QR-Code am Boxbildschirm traegt das WLAN, nicht den Link.

Ein Link kann kein Handy ins WLAN bringen — nur der WIFI:-Payload kann das,
und das Captive-Portal schiebt die Galerie danach von selbst hinterher
(siehe config.box_qr_payload und gallery_server._captive_portal_redirect).
Getestet wird deshalb beides: dass der Payload stimmt, und dass die Box in
den Faellen, in denen es kein eigenes WLAN gibt, auf den Link zurueckfaellt.
"""
import re

import config

GALLERY = "http://192.168.4.1"


def _cfg(**over) -> dict:
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


# ── Der Normalfall ────────────────────────────────────────────────────────────

def test_code_traegt_die_wlan_daten():
    assert config.box_qr_payload(_cfg()) == "WIFI:T:WPA;S:Fotobox;P:fotobox123;;"


def test_offener_hotspot_wird_als_nopass_ausgewiesen():
    """Ohne Passwort ist der Hotspot offen — 'T:WPA;P:;' liesse das Handy
    nach einem Schluessel fragen, den es nicht gibt."""
    assert config.box_qr_payload(_cfg(wifi_password="")) == \
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
    cfg = _cfg(hotspot_enabled=False, gallery_url="http://192.168.2.140:5000")
    assert config.box_qr_payload(cfg) == "http://192.168.2.140:5000"


def test_zu_kurzes_passwort_faellt_auf_den_link_zurueck():
    """WPA2 verlangt 8 Zeichen, hotspot.start() verweigert kuerzere — es
    gaebe gar kein Netz, in das der Code fuehren koennte."""
    assert config.box_qr_payload(_cfg(wifi_password="kurz")) == GALLERY
    assert config.build_wifi_qr("Fotobox", "kurz") == ""


def test_ohne_ssid_faellt_es_auf_den_link_zurueck():
    assert config.box_qr_payload(_cfg(wifi_ssid="   ")) == GALLERY


# ── Groesse des Musters ───────────────────────────────────────────────────────

def test_payload_bleibt_scannbar_klein():
    """Jedes Zeichen mehr kann das Muster feiner machen, und feiner heisst
    weniger Pixel je Modul auf der Sidebar-Kachel (ui.py: _social_layout
    rendert in ganzen Modulen). Mit Default-SSID und -Passwort muessen es
    die 29 Module bleiben, gegen die die Kachelgroesse bemessen ist.
    """
    qrcode = __import__("qrcode")
    qr = qrcode.QRCode(border=0)
    qr.add_data(config.box_qr_payload(_cfg()))
    qr.make(fit=True)
    assert qr.modules_count <= 29


# ── Der Code auf dem Ergebnis-Schirm ──────────────────────────────────────────
# Er zeigt auf das einzelne Foto, nicht auf das WLAN. Der Grund ist eine
# Eigenheit der Handys: ein mit der Kamera gescannter Code oeffnet sich immer
# im echten Browser, nie im WLAN-Anmeldefenster — und nur dort kann der Gast
# sein Bild sichern.

def _photo_cfg(**over) -> dict:
    data = {"gallery_url": "http://fotobox.internal",
            "picture_dir": "/srv/Picture_Box"}
    data.update(over)
    return data


def test_foto_url_zeigt_auf_das_einzelne_bild():
    got = config.photo_url(_photo_cfg(),
                           "/srv/Picture_Box/2026-08-25_fest/foto_1.jpg")
    assert got == "http://fotobox.internal/photo/2026-08-25_fest/foto_1.jpg"


def test_foto_url_kodiert_sonderzeichen():
    """Eventnamen wie 'Sommerfest 2026' und Dateinamen mit & duerfen den
    Link nicht zerreissen — der Gast scannt ihn, er kann ihn nicht
    reparieren."""
    got = config.photo_url(_photo_cfg(),
                           "/srv/Picture_Box/Sommerfest 2026/foto & co.jpg")
    assert got == ("http://fotobox.internal/photo/"
                   "Sommerfest%202026/foto%20%26%20co.jpg")


def test_flacher_altbestand_bekommt_keinen_link():
    """Liegt das Foto direkt im picture_dir, fehlt die Event-Komponente.
    Ein geratener Link fuehrte auf eine 404-Seite — dann lieber keiner,
    der Ergebnis-Schirm faellt auf den WLAN-Code zurueck."""
    assert config.photo_url(_photo_cfg(),
                            "/srv/Picture_Box/foto_flach.jpg") == ""


def test_ohne_galerie_adresse_kein_link():
    assert config.photo_url(_photo_cfg(gallery_url=""),
                            "/srv/Picture_Box/fest/f.jpg") == ""
    assert config.photo_url(_photo_cfg(), "") == ""


def test_foto_code_bleibt_auf_dem_ergebnis_schirm_scannbar():
    """41 Module bei realistischem Eventnamen. Auf der Sidebar-Groesse
    waeren das 3 px je Modul und der Decoder steigt aus; RESULT_QR_SIZE
    haelt ihn bei 6.
    """
    qrcode = __import__("qrcode")
    url = config.photo_url(
        _photo_cfg(), "/srv/Picture_Box/2026-08-25_hochzeit-lisa-und-tom/"
                      "foto_20260825_120000.jpg")
    qr = qrcode.QRCode(border=0)
    qr.add_data(url)
    qr.make(fit=True)
    assert qr.modules_count <= 41
    assert 260 // qr.modules_count >= 6, "Kachel zu klein fuer diese URL"
