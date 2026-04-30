import logging
import os
import subprocess
import threading
import time

logger = logging.getLogger(__name__)


class Camera:
    def __init__(self):
        self.available = False
        self.error_message = ""
        self._running = True
        self._init()
        threading.Thread(target=self._watchdog, daemon=True).start()

    # ── Init / Detect ──────────────────────────────────────────────────────────

    def _detect(self) -> bool:
        try:
            r = subprocess.run(
                ["gphoto2", "--auto-detect"],
                capture_output=True, text=True, timeout=10,
            )
            return "usb" in r.stdout.lower()
        except Exception:
            return False

    def _init(self):
        if self._detect():
            subprocess.run(
                ["gphoto2", "--set-config", "reviewtime=0"],
                capture_output=True, timeout=10,
            )
            self.available = True
            self.error_message = ""
            logger.info("Kamera bereit")
        else:
            self.available = False
            self.error_message = "Keine Kamera gefunden – USB prüfen"
            logger.warning(self.error_message)

    # ── Watchdog ───────────────────────────────────────────────────────────────

    def _watchdog(self):
        while self._running:
            time.sleep(10)
            detected = self._detect()
            if detected and not self.available:
                logger.info("Watchdog: Kamera wieder erkannt – reinit")
                self._init()
            elif not detected and self.available:
                self.available = False
                self.error_message = "Kamera getrennt – USB prüfen"
                logger.warning("Watchdog: Kamera verloren")

    # ── Capture ────────────────────────────────────────────────────────────────

    def capture(self, directory: str) -> str:
        if not self.available:
            raise RuntimeError("Kamera nicht verfügbar")
        os.makedirs(directory, exist_ok=True)
        filename = f"foto_{int(time.time())}.jpg"
        before = set(os.listdir(directory))

        subprocess.run(
            ["gphoto2", "--set-config", "viewfinder=0"],
            capture_output=True, timeout=5,
        )
        time.sleep(0.3)

        try:
            result = subprocess.run(
                ["gphoto2", "--capture-image-and-download", "--filename", filename],
                capture_output=True, text=True, timeout=30,
                cwd=directory,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Aufnahme fehlgeschlagen: {result.stderr.strip()}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Aufnahme Timeout")
        finally:
            subprocess.run(
                ["gphoto2", "--set-config", "viewfinder=1"],
                capture_output=True, timeout=5,
            )

        after = set(os.listdir(directory))
        new_files = after - before
        name = (max(new_files, key=lambda f: os.path.getmtime(os.path.join(directory, f)))
                if new_files else filename)
        path = os.path.join(directory, name)
        logger.info("Foto gespeichert: %s", path)
        return path

    def close(self):
        self._running = False
