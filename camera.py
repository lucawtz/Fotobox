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

        before = set(os.listdir(directory))

        subprocess.run(
            ["gphoto2", "--set-config", "viewfinder=0"],
            capture_output=True, timeout=5
        )
        time.sleep(0.3)

        try:
            result = subprocess.run(
                ["gphoto2", "--capture-image-and-download", "--filename", filename],
                capture_output=True, text=True, timeout=30,
                cwd=directory,
            )
            if result.returncode != 0:
                logger.error("gphoto2 Fehler: %s", result.stderr)
                raise RuntimeError(f"Aufnahme fehlgeschlagen: {result.stderr.strip()}")
        except subprocess.TimeoutExpired:
            logger.error("gphoto2 Timeout — Kamera reagiert nicht")
            raise RuntimeError("Aufnahme Timeout")
        finally:
            subprocess.run(
                ["gphoto2", "--set-config", "viewfinder=1"],
                capture_output=True, timeout=5
            )

        after = set(os.listdir(directory))
        new_files = after - before
        if new_files:
            name = max(new_files, key=lambda f: os.path.getmtime(os.path.join(directory, f)))
        else:
            name = filename
        path = os.path.join(directory, name)
        logger.info("Foto gespeichert: %s", path)
        return path

    def close(self):
        pass
