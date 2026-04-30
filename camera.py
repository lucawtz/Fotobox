import logging
import os
import subprocess
import threading
import time

logger = logging.getLogger(__name__)


class Camera:
    """gphoto2-Wrapper mit Watchdog und automatischem Live-View-Keep-Alive.

    Der Live-View-Modus wird beim Start aktiviert und alle 10s vom Watchdog
    aufgefrischt — so bleibt das HDMI-Signal aktiv ohne dass jemand am
    Kamera-Display drücken muss.
    """

    KEEPALIVE_SECONDS = 10

    def __init__(self):
        self.available = False
        self.error_message = ""
        self._running = True
        self._cmd_lock = threading.Lock()  # Serialisiert gphoto2-Aufrufe
        self._capturing = False
        self._init()
        threading.Thread(target=self._watchdog, daemon=True).start()

    # ── gphoto2-Wrapper ────────────────────────────────────────────────────────

    def _gphoto(self, args: list, timeout: int = 10):
        """Führt einen gphoto2-Befehl thread-sicher aus."""
        with self._cmd_lock:
            return subprocess.run(
                ["gphoto2"] + args,
                capture_output=True, text=True, timeout=timeout,
            )

    # ── Init / Detect ──────────────────────────────────────────────────────────

    def _detect(self) -> bool:
        try:
            r = self._gphoto(["--auto-detect"], timeout=10)
            return "usb" in r.stdout.lower()
        except Exception:
            return False

    def _init(self):
        if not self._detect():
            self.available = False
            self.error_message = "Keine Kamera gefunden – USB prüfen"
            logger.warning(self.error_message)
            return

        # Bildkontrolle nach Aufnahme deaktivieren
        try:
            self._gphoto(["--set-config", "reviewtime=0"], timeout=10)
        except Exception as exc:
            logger.debug("reviewtime nicht setzbar: %s", exc)

        # Live-View aktivieren (HDMI-Output bleibt aktiv)
        try:
            self._gphoto(["--set-config", "viewfinder=1"], timeout=10)
        except Exception as exc:
            logger.debug("viewfinder nicht setzbar: %s", exc)

        # Auto-Power-Off deaktivieren (nicht alle Kameras unterstützen das)
        for cfg in ("autopoweroff=0", "autopoweroff=65535"):
            try:
                self._gphoto(["--set-config", cfg], timeout=5)
            except Exception:
                pass

        self.available = True
        self.error_message = ""
        logger.info("Kamera bereit (Live-View aktiviert)")

    # ── Watchdog mit Keep-Alive ────────────────────────────────────────────────

    def _watchdog(self):
        while self._running:
            time.sleep(self.KEEPALIVE_SECONDS)
            if self._capturing:
                continue  # Nicht in den laufenden Capture funken
            detected = self._detect()
            if detected and not self.available:
                logger.info("Watchdog: Kamera wieder erkannt – reinit")
                self._init()
            elif not detected and self.available:
                self.available = False
                self.error_message = "Kamera getrennt – USB prüfen"
                logger.warning("Watchdog: Kamera verloren")
            elif detected and self.available:
                # Keep-Alive: viewfinder=1 frisch setzen damit die Kamera
                # nicht in den Sleep-Modus geht und HDMI aktiv bleibt
                try:
                    self._gphoto(["--set-config", "viewfinder=1"], timeout=5)
                except Exception as exc:
                    logger.debug("Keep-Alive: %s", exc)

    # ── Capture ────────────────────────────────────────────────────────────────

    def capture(self, directory: str) -> str:
        if not self.available:
            raise RuntimeError("Kamera nicht verfügbar")
        os.makedirs(directory, exist_ok=True)
        filename = f"foto_{int(time.time())}.jpg"
        before = set(os.listdir(directory))

        self._capturing = True
        try:
            # Viewfinder ausschalten für saubere Aufnahme
            try:
                self._gphoto(["--set-config", "viewfinder=0"], timeout=5)
            except Exception:
                pass
            time.sleep(0.3)

            with self._cmd_lock:
                try:
                    result = subprocess.run(
                        ["gphoto2", "--capture-image-and-download",
                         "--filename", filename],
                        capture_output=True, text=True, timeout=30,
                        cwd=directory,
                    )
                    if result.returncode != 0:
                        raise RuntimeError(
                            f"Aufnahme fehlgeschlagen: {result.stderr.strip()}")
                except subprocess.TimeoutExpired:
                    raise RuntimeError("Aufnahme Timeout")

            # Viewfinder wieder einschalten
            try:
                self._gphoto(["--set-config", "viewfinder=1"], timeout=5)
            except Exception:
                pass
        finally:
            self._capturing = False

        after = set(os.listdir(directory))
        new_files = after - before
        name = (max(new_files, key=lambda f: os.path.getmtime(os.path.join(directory, f)))
                if new_files else filename)
        path = os.path.join(directory, name)
        logger.info("Foto gespeichert: %s", path)
        return path

    def close(self):
        self._running = False
