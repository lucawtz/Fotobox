import logging
import subprocess
import sys

import config

logger = logging.getLogger(__name__)


def _interface_exists(ifname: str) -> bool:
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "DEVICE,TYPE", "device"],
            check=True, capture_output=True, text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        logger.warning("nmcli device-Listing fehlgeschlagen: %s", exc)
        return False
    for line in result.stdout.splitlines():
        parts = line.split(":")
        if len(parts) >= 2 and parts[0] == ifname and parts[1] == "wifi":
            return True
    return False


def start() -> bool:
    if sys.platform != "linux":
        logger.warning("Hotspot: nur auf Linux verfügbar (Plattform: %s)", sys.platform)
        return False

    cfg = config.cfg
    ssid = cfg["wifi_ssid"]
    password = cfg["wifi_password"]
    ifname = cfg.get("hotspot_interface", "wlan0")

    if not _interface_exists(ifname):
        logger.warning(
            "Hotspot-Interface '%s' nicht gefunden — Hotspot wird nicht gestartet",
            ifname)
        return False

    # Alte Verbindung mit gleichem Namen entfernen — mit Timeout damit
    # die App nicht hängenbleibt falls NetworkManager nicht reagiert.
    try:
        subprocess.run(
            ["nmcli", "connection", "delete", "fotobox-hotspot"],
            capture_output=True, text=True, timeout=10,
        )
    except subprocess.TimeoutExpired:
        logger.warning("nmcli connection delete: Timeout — Hotspot übersprungen")
        return False
    except FileNotFoundError:
        logger.warning("nmcli nicht gefunden — Hotspot nicht verfügbar")
        return False

    try:
        subprocess.run(
            [
                "nmcli", "device", "wifi", "hotspot",
                "ifname", ifname,
                "ssid", ssid,
                "password", password,
                "con-name", "fotobox-hotspot",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        logger.info("Hotspot '%s' gestartet auf %s — IP: %s",
                    ssid, ifname, cfg["hotspot_ip"])
        return True
    except subprocess.TimeoutExpired:
        logger.warning("nmcli hotspot start: Timeout — Hotspot übersprungen")
    except FileNotFoundError:
        logger.warning("nmcli nicht gefunden — Hotspot nicht verfügbar")
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or "").strip()
        logger.warning("Hotspot-Fehler (%s): %s", ifname, err)
    return False
