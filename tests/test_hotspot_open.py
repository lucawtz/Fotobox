"""Offenes WLAN: der Hotspot laesst sich ohne Passwort aufspannen.

Am Eventabend ist das Abtippen des Passworts die Huerde, an der Gaeste
haengenbleiben — betrunken erst recht. Ein leeres Passwort heisst deshalb
"offen und so gewollt". Zwischen 1 und 7 Zeichen bleibt es ein Fehler: WPA2
verlangt mindestens 8, der AP kaeme gar nicht hoch, und ihn stattdessen
stillschweigend offen aufzuspannen waere die schlechteste Antwort darauf.
"""
import pytest

import hotspot


@pytest.fixture
def add_args(monkeypatch):
    """Faengt die Argumente von 'nmcli connection add' ab."""
    seen = {}

    def fake(args, timeout=10, check=False):
        if args[:2] == ["connection", "add"]:
            seen["args"] = args
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    monkeypatch.setattr(hotspot, "_nmcli", fake)
    return seen


def test_ohne_passwort_faellt_die_verschluesselung_weg(add_args):
    """wifi-sec mit leerem PSK geht nicht — NetworkManager lehnt 'wpa-psk'
    ohne Schluessel ab und die Connection kaeme gar nicht zustande."""
    assert hotspot._build_connection("wlan0", "Fotobox", "", "192.168.4.1")
    args = add_args["args"]
    assert not [a for a in args if a.startswith("wifi-sec")]
    assert "Fotobox" in args
    # Der Rest muss unveraendert stehen, sonst landet das Handy im
    # 10.42-Subnetz statt im konfigurierten.
    assert "192.168.4.1/24" in args
    assert "shared" in args


def test_mit_passwort_bleibt_wpa2(add_args):
    assert hotspot._build_connection("wlan0", "Fotobox", "geheim123",
                                     "192.168.4.1")
    args = add_args["args"]
    assert "wifi-sec.key-mgmt" in args
    assert args[args.index("wifi-sec.psk") + 1] == "geheim123"


def test_zu_kurzes_passwort_bleibt_ein_fehler(monkeypatch, caplog):
    """Nicht etwa still ein offenes Netz daraus machen."""
    import config
    monkeypatch.setitem(config.cfg, "wifi_password", "kurz")
    monkeypatch.setitem(config.cfg, "wifi_ssid", "Fotobox")
    monkeypatch.setattr(hotspot.sys, "platform", "linux")
    called = []
    monkeypatch.setattr(hotspot, "_build_connection",
                        lambda *a, **k: called.append(a) or True)
    assert hotspot.start() is False
    assert not called, "AP darf gar nicht erst gebaut werden"
