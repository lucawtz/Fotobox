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

        # Live-View kurz pausieren — PTP-Capture braucht freien Bus
        subprocess.run(["gphoto2", "--set-config", "viewfinder=0"], capture_output=True)
        time.sleep(0.5)

        result = subprocess.run(
            ["gphoto2", "--capture-image-and-download", "--filename", path],
            capture_output=True, text=True
        )

        # Live-View sofort wieder starten
        subprocess.run(["gphoto2", "--set-config", "viewfinder=1"], capture_output=True)

        if result.returncode != 0:
            logger.error("gphoto2 Fehler: %s", result.stderr)
            raise RuntimeError(f"Aufnahme fehlgeschlagen: {result.stderr.strip()}")

        logger.info("Foto gespeichert: %s", path)
        return path

    def close(self):
        pass
