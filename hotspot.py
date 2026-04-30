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
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
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
            "Hotspot-Interface '%s' nicht gefunden — Hotspot wird nicht gestartet", ifname)
        return False

    # Alte Verbindung mit gleichem Namen entfernen, damit Interface-Wechsel sauber greift
    subprocess.run(
        ["nmcli", "connection", "delete", "fotobox-hotspot"],
        capture_output=True, text=True,
    )

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
        )
        logger.info("Hotspot '%s' gestartet auf %s — IP: %s",
                    ssid, ifname, cfg["hotspot_ip"])
        return True
    except FileNotFoundError:
        logger.warning("nmcli nicht gefunden — Hotspot nicht verfügbar")
    except subprocess.CalledProcessError as exc:
        logger.warning("Hotspot-Fehler (%s): %s", ifname, exc.stderr.strip())
    return False
