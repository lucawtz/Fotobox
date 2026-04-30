import logging
import os
import subprocess
import threading
import time

logger = logging.getLogger(__name__)


class Camera:
    """gphoto2-Wrapper mit Watchdog und manuellem Live-View-Wake.

    HINWEIS zur EOS 700D:
    - 'gphoto2 --capture-preview' triggert auf manchen Canon-Modellen
      tatsächlich den Auslöser. Wir nutzen es deshalb NICHT für Keep-Alive.
    - Live-View wird über '--set-config viewfinder=1' gestartet. Das
      reicht meist nicht um die Kamera dauerhaft wach zu halten — daher
      die Empfehlung: im Kameramenü unter 'Auto-Power-Off' auf "Aus"
      stellen, dann bleibt der Live-View permanent.
    - Zusätzlich wird vor jeder Aufnahme automatisch wake_liveview()
      gerufen, falls die Kamera zwischendurch eingeschlafen ist.
    """

    DEFAULT_KEEPALIVE_S = 30

    # Config-Namen für Live-View je nach Kamera-Modell
    _VIEWFINDER_KEYS = ("viewfinder", "eosviewfinder")

    def __init__(self, keepalive_s: int = DEFAULT_KEEPALIVE_S):
        self.available = False
        self.error_message = ""
        self._running = True
        self._cmd_lock = threading.Lock()
        self._capturing = False
        self._keepalive_s = max(5, int(keepalive_s))
        self._init()
        threading.Thread(target=self._watchdog, daemon=True).start()

    # ── gphoto2-Wrapper ────────────────────────────────────────────────────────

    def _gphoto(self, args: list, timeout: int = 10):
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

        try:
            self._gphoto(["--set-config", "reviewtime=0"], timeout=10)
        except Exception as exc:
            logger.debug("reviewtime: %s", exc)

        # Auto-Power-Off versuchen zu deaktivieren (best effort)
        for cfg in ("autopoweroff=0", "autopoweroff=65535"):
            try:
                self._gphoto(["--set-config", cfg], timeout=5)
            except Exception:
                pass

        self.wake_liveview()

        self.available = True
        self.error_message = ""
        logger.info("Kamera bereit")

    # ── Live-View Wake (ohne capture-preview!) ─────────────────────────────────

    def wake_liveview(self) -> bool:
        """Aktiviert Live-View durch viewfinder=1 (sicher, kein Shutter-Trigger).

        Wird aufgerufen:
        - Beim Init (Start-Display)
        - Vor jeder Aufnahme (falls Kamera eingeschlafen ist)
        - Vom Watchdog periodisch (Best-Effort-Keep-Alive)
        - Manuell wenn der Nutzer den Wake-Knopf drückt
        """
        ok = False
        for key in self._VIEWFINDER_KEYS:
            try:
                r = self._gphoto(["--set-config", f"{key}=1"], timeout=5)
                if r.returncode == 0:
                    ok = True
                    break
            except Exception:
                continue
        if not ok:
            logger.debug("wake_liveview: kein viewfinder-Config setzbar")
        return ok

    # ── Watchdog ───────────────────────────────────────────────────────────────

    def _watchdog(self):
        while self._running:
            time.sleep(self._keepalive_s)
            if self._capturing:
                continue

            detected = self._detect()
            if detected and not self.available:
                logger.info("Watchdog: Kamera wieder erkannt – reinit")
                self._init()
            elif not detected and self.available:
                self.available = False
                self.error_message = "Kamera getrennt – USB prüfen"
                logger.warning("Watchdog: Kamera verloren")
            elif detected and self.available:
                # Sicherer Keep-Alive: nur viewfinder=1 nachsetzen, nicht
                # capture-preview (würde Shutter triggern bei der 700D)
                self.wake_liveview()

    # ── Capture ────────────────────────────────────────────────────────────────

    def capture(self, directory: str) -> str:
        if not self.available:
            raise RuntimeError("Kamera nicht verfügbar")
        os.makedirs(directory, exist_ok=True)
        filename = f"foto_{int(time.time())}.jpg"
        before = set(os.listdir(directory))

        self._capturing = True
        try:
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
        finally:
            self._capturing = False

        # Live-View nach Aufnahme reaktivieren
        self.wake_liveview()

        after = set(os.listdir(directory))
        new_files = after - before
        name = (max(new_files, key=lambda f: os.path.getmtime(os.path.join(directory, f)))
                if new_files else filename)
        path = os.path.join(directory, name)
        logger.info("Foto gespeichert: %s", path)
        return path

    def close(self):
        self._running = False
