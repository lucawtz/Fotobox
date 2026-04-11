import logging
import os
import subprocess
import time

logger = logging.getLogger(__name__)


class Camera:
    def __init__(self):
        result = subprocess.run(
            ["gphoto2", "--auto-detect"],
            capture_output=True, text=True, timeout=10
        )
        if "usb" not in result.stdout:
            raise RuntimeError("Keine Kamera gefunden. Kabel prüfen.")
        logger.info("Kamera erkannt: %s", result.stdout.strip().splitlines()[-1])

        subprocess.run(
            ["gphoto2", "--set-config", "reviewtime=0"],
            capture_output=True, timeout=10
        )
        logger.info("Bildkontrolle deaktiviert")

    def capture(self, directory: str) -> str:
        os.makedirs(directory, exist_ok=True)
        filename = f"foto_{int(time.time())}.jpg"
        path = os.path.join(directory, filename)

        subprocess.run(
            ["gphoto2", "--set-config", "viewfinder=0"],
            capture_output=True, timeout=5
        )
        time.sleep(0.3)

        try:
            result = subprocess.run(
                ["gphoto2", "--capture-image-and-download", "--filename", path],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                logger.error("gphoto2 Fehler: %s", result.stderr)
                raise RuntimeError(f"Aufnahme fehlgeschlagen: {result.stderr.strip()}")
        except subprocess.TimeoutExpired:
            logger.error("gphoto2 Timeout — Kamera reagiert nicht")
            raise RuntimeError("Aufnahme Timeout")
        finally:
            # Viewfinder IMMER wieder einschalten, auch bei Fehler
            subprocess.run(
                ["gphoto2", "--set-config", "viewfinder=1"],
                capture_output=True, timeout=5
            )

        logger.info("Foto gespeichert: %s", path)
        return path

    def close(self):
        pass
