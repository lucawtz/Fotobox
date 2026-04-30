"""WLAN-Hotspot über NetworkManager.

Wir konfigurieren die Connection explizit (band=bg, channel=6,
ipv4.method=shared mit fester IP) statt 'nmcli device wifi hotspot'
zu nutzen — dadurch ist DHCP, IP-Range und Frequenz vorhersagbar.
"""
import logging
import subprocess
import sys

import config

logger = logging.getLogger(__name__)

CONN_NAME = "fotobox-hotspot"


def _nmcli(args: list, timeout: int = 10, check: bool = False):
    """nmcli mit Timeout, gibt CompletedProcess zurück oder None bei Fehler."""
    try:
        return subprocess.run(
            ["nmcli"] + args,
            capture_output=True, text=True, timeout=timeout, check=check,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired,
            subprocess.CalledProcessError) as exc:
        logger.warning("nmcli %s fehlgeschlagen: %s", args[0] if args else "?", exc)
        return None


def _interface_exists(ifname: str) -> bool:
    r = _nmcli(["-t", "-f", "DEVICE,TYPE", "device"], timeout=5)
    if r is None or r.returncode != 0:
        return False
    for line in r.stdout.splitlines():
        parts = line.split(":")
        if len(parts) >= 2 and parts[0] == ifname and parts[1] == "wifi":
            return True
    return False


def _free_interface(ifname: str) -> None:
    """Trennt aktive WLAN-Client-Verbindungen auf ifname, damit der Hotspot
    nicht von einem auto-reconnectenden Heim-WLAN verdrängt wird."""
    r = _nmcli(["-t", "-f", "NAME,DEVICE,TYPE", "connection", "show", "--active"],
               timeout=5)
    if r is None or r.returncode != 0:
        return
    for line in r.stdout.splitlines():
        parts = line.split(":")
        if len(parts) < 3:
            continue
        name, device, ctype = parts[0], parts[1], parts[2]
        if device != ifname or ctype != "802-11-wireless" or name == CONN_NAME:
            continue
        logger.info("Hotspot: trenne konkurrierende Verbindung '%s' auf %s",
                    name, ifname)
        _nmcli(["connection", "down", name], timeout=10)


def _delete_existing() -> None:
    """Alte fotobox-hotspot-Connection entfernen damit ein frischer Build
    nicht von kaputten Altsettings gestört wird."""
    _nmcli(["connection", "delete", CONN_NAME], timeout=10)


def _build_connection(ifname: str, ssid: str, password: str,
                      hotspot_ip: str) -> bool:
    """Erstellt die fotobox-hotspot-Connection mit expliziten Settings."""
    # Aus 192.168.4.1 wird 192.168.4.1/24 für den ipv4.addresses-Wert
    ipv4_addr = f"{hotspot_ip}/24"

    # Schritt 1: Connection anlegen
    r = _nmcli([
        "connection", "add",
        "type", "wifi",
        "ifname", ifname,
        "con-name", CONN_NAME,
        "autoconnect", "no",
        "ssid", ssid,
    ], timeout=10)
    if r is None or r.returncode != 0:
        logger.warning("Hotspot-Add fehlgeschlagen: %s",
                       (r.stderr if r else "no result").strip()[:200])
        return False

    # Schritt 2: AP-Mode + 2.4 GHz + Channel 6 + WPA2 + DHCP-Share
    r = _nmcli([
        "connection", "modify", CONN_NAME,
        "802-11-wireless.mode", "ap",
        "802-11-wireless.band", "bg",
        "802-11-wireless.channel", "6",
        "ipv4.method", "shared",
        "ipv4.addresses", ipv4_addr,
        "ipv6.method", "ignore",
        "wifi-sec.key-mgmt", "wpa-psk",
        "wifi-sec.proto", "rsn",
        "wifi-sec.pairwise", "ccmp",
        "wifi-sec.group", "ccmp",
        "wifi-sec.psk", password,
    ], timeout=10)
    if r is None or r.returncode != 0:
        logger.warning("Hotspot-Modify fehlgeschlagen: %s",
                       (r.stderr if r else "no result").strip()[:200])
        return False

    return True


def stop() -> None:
    """Beendet den Hotspot."""
    _nmcli(["connection", "down", CONN_NAME], timeout=10)
    logger.info("Hotspot beendet")


def start() -> bool:
    if sys.platform != "linux":
        logger.warning("Hotspot: nur auf Linux verfügbar (Plattform: %s)", sys.platform)
        return False

    cfg = config.cfg
    ssid = cfg["wifi_ssid"]
    password = cfg["wifi_password"]
    ifname = cfg.get("hotspot_interface", "wlan0")
    hotspot_ip = cfg.get("hotspot_ip", "192.168.4.1")

    if len(password) < 8:
        logger.warning("Hotspot: WPA2 verlangt min. 8 Zeichen Passwort — abgebrochen")
        return False

    if not _interface_exists(ifname):
        logger.warning(
            "Hotspot-Interface '%s' nicht gefunden — Hotspot wird nicht gestartet",
            ifname)
        return False

    _free_interface(ifname)
    _delete_existing()

    if not _build_connection(ifname, ssid, password, hotspot_ip):
        _delete_existing()
        return False

    # Schritt 3: Connection starten
    r = _nmcli(["connection", "up", CONN_NAME], timeout=20)
    if r is None or r.returncode != 0:
        err = (r.stderr if r else "no result").strip()[:200]
        logger.warning("Hotspot-Up fehlgeschlagen (%s): %s", ifname, err)
        return False

    logger.info("Hotspot '%s' gestartet auf %s — IP: %s, Channel 6 (2.4 GHz)",
                ssid, ifname, hotspot_ip)
    return True
