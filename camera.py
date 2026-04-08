import logging
import os
import subprocess
import time

logger = logging.getLogger(__name__)


class Camera:
    def __init__(self):
        result = subprocess.run(
            ["gphoto2", "--auto-detect"],
            capture_output=True, text=True
        )
        if "usb" not in result.stdout:
            raise RuntimeError("Keine Kamera gefunden. Kabel prüfen.")
        logger.info("Kamera erkannt: %s", result.stdout.strip().splitlines()[-1])

        # Bildkontrolle aus — Kamera bleibt nach Foto im Live-View
        subprocess.run(
            ["gphoto2", "--set-config", "reviewtime=0"],
            capture_output=True
        )
        logger.info("Bildkontrolle deaktiviert")

    def capture(self, directory: str) -> str:
        os.makedirs(directory, exist_ok=True)
        filename = f"foto_{int(time.time())}.jpg"
        path = os.path.join(directory, filename)

        # Shutter auslösen ohne Live-View zu verlassen
        subprocess.run(
            ["gphoto2", "--set-config", "eosremoterelease=Immediate"],
            capture_output=True
        )
        time.sleep(0.1)
        subprocess.run(
            ["gphoto2", "--set-config", "eosremoterelease=None"],
            capture_output=True
        )

        # Auf neue Datei warten und herunterladen (max. 15 Sekunden)
        result = subprocess.run(
            ["gphoto2", "--wait-event-and-download=FILEADDED", "--filename", path],
            capture_output=True, text=True,
            timeout=15
        )

        if result.returncode != 0:
            logger.error("gphoto2 Fehler: %s", result.stderr)
            raise RuntimeError(f"Download fehlgeschlagen: {result.stderr.strip()}")

        logger.info("Foto gespeichert: %s", path)
        return path

    def close(self):
        pass
