import logging
import subprocess
import sys

import config

logger = logging.getLogger(__name__)


def start() -> bool:
    if sys.platform != "linux":
        logger.warning("Hotspot: nur auf Linux verfügbar (Plattform: %s)", sys.platform)
        return False
    try:
        subprocess.run(
            [
                "nmcli", "device", "wifi", "hotspot",
                "ssid", config.HOTSPOT_SSID,
                "password", config.HOTSPOT_PASSWORD,
                "con-name", "fotobox-hotspot",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info("Hotspot '%s' gestartet — IP: %s", config.HOTSPOT_SSID, config.HOTSPOT_IP)
        return True
    except FileNotFoundError:
        logger.warning("nmcli nicht gefunden — Hotspot nicht verfügbar")
    except subprocess.CalledProcessError as exc:
        logger.warning("Hotspot-Fehler: %s", exc.stderr.strip())
    return False
