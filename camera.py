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

    def capture(self, directory: str) -> str:
        os.makedirs(directory, exist_ok=True)
        filename = f"foto_{int(time.time())}.jpg"
        path = os.path.join(directory, filename)

        result = subprocess.run(
            ["gphoto2", "--capture-image-and-download", "--filename", path],
            capture_output=True, text=True
        )

        if result.returncode != 0:
            logger.error("gphoto2 Fehler: %s", result.stderr)
            raise RuntimeError(f"Aufnahme fehlgeschlagen: {result.stderr.strip()}")

        logger.info("Foto gespeichert: %s", path)
        self._restart_liveview()
        return path

    def _restart_liveview(self):
        subprocess.run(
            ["gphoto2", "--set-config", "viewfinder=1"],
            capture_output=True, text=True
        )
        logger.info("Live-View neu gestartet")

    def close(self):
        pass  # gphoto2 hat keine persistente Verbindung
