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
