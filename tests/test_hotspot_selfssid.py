"""Der Pi darf sich nicht in seinen eigenen Hotspot einwaehlen wollen.

Klickt jemand am Desktop im WLAN-Menue auf die eigene Fotobox-SSID, legt
NetworkManager ein infrastructure-Profil mit autoconnect=yes an. Weil es an
kein Interface gebunden ist, probiert NM es auf jedem freien Adapter — der
4-Way-Handshake mit dem eigenen AP scheitert, NM fragt nach einem neuen Key,
und der Passwort-Dialog geht mitten im Event alle paar Minuten auf.
"""
import pytest

import hotspot


class FakeProc:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


CONNS = "aaaa-client:802-11-wireless\nbbbb-ap:802-11-wireless\ncccc-eth:802-3-ethernet\n"

DETAILS = {
    "aaaa-client": (
        "connection.id:netplan-wlan0-Fotobox\n"
        "802-11-wireless.mode:infrastructure\n"
        "802-11-wireless.ssid:Fotobox\n"
    ),
    "bbbb-ap": (
        "connection.id:alter-hotspot\n"
        "802-11-wireless.mode:ap\n"
        "802-11-wireless.ssid:Fotobox\n"
    ),
}


@pytest.fixture
def nmcli(monkeypatch):
    calls = []

    def fake(args, timeout=10, check=False):
        calls.append(args)
        if args[:2] == ["-t", "-f"] and args[2] == "UUID,TYPE":
            return FakeProc(CONNS)
        if "show" in args and "uuid" in args:
            return FakeProc(DETAILS.get(args[-1], ""))
        return FakeProc()

    monkeypatch.setattr(hotspot, "_nmcli", fake)
    return calls


def test_client_profil_auf_eigener_ssid_wird_geloescht(nmcli):
    hotspot._purge_self_ssid_clients("Fotobox")
    assert ["connection", "delete", "uuid", "aaaa-client"] in nmcli


def test_ap_profil_bleibt_stehen(nmcli):
    hotspot._purge_self_ssid_clients("Fotobox")
    deletes = [c for c in nmcli if c[:2] == ["connection", "delete"]]
    assert all("bbbb-ap" not in c for c in deletes), \
        "AP-Profile sind kein Autoconnect-Problem — nicht anfassen"


def test_fremde_ssid_bleibt_stehen(nmcli):
    hotspot._purge_self_ssid_clients("WLAN-Gerritsen")
    assert not [c for c in nmcli if c[:2] == ["connection", "delete"]], \
        "Das Heim-WLAN des Nutzers geht uns nichts an"
