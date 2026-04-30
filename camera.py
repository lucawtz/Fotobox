import logging
import os
import subprocess
import threading
import time

logger = logging.getLogger(__name__)


class Camera:
    """gphoto2-Wrapper mit Watchdog und Live-View-Keep-Alive für Canon-DSLRs.

    Bei Canon-Kameras (z.B. EOS 700D) reicht es nicht, viewfinder=1 ein
    einziges Mal zu setzen — die Kamera fällt nach kurzer Zeit wieder aus
    dem Live-View-Modus. Stattdessen muss kontinuierlich ein Preview-Frame
    über USB abgerufen werden, dann bleibt sowohl Display als auch HDMI-Out
    dauerhaft aktiv.

    KEEPALIVE_SECONDS: Wie oft ein Preview-Pull ausgelöst wird. Sollte
    deutlich kürzer sein als der Auto-Off-Timer der Kamera (Canon-Default
    ~15-30s). Bei Problemen: in config.json "camera_keepalive_s" setzen.
    """

    DEFAULT_KEEPALIVE_S = 8

    def __init__(self, keepalive_s: int = DEFAULT_KEEPALIVE_S):
        self.available = False
        self.error_message = ""
        self._running = True
        self._cmd_lock = threading.Lock()  # Serialisiert gphoto2-Aufrufe
        self._capturing = False
        self._keepalive_s = max(3, int(keepalive_s))
        self._init()
        threading.Thread(target=self._watchdog, daemon=True).start()

    # ── gphoto2-Wrapper ────────────────────────────────────────────────────────

    def _gphoto(self, args: list, timeout: int = 10):
        """Führt einen gphoto2-Befehl thread-sicher aus (mit capture_output)."""
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

        # Bildkontrolle nach Aufnahme deaktivieren (best effort)
        try:
            self._gphoto(["--set-config", "reviewtime=0"], timeout=10)
        except Exception as exc:
            logger.debug("reviewtime: %s", exc)

        # Auto-Power-Off versuchen zu deaktivieren — bei vielen Canons
        # nicht via gphoto2 zugänglich, deshalb best effort
        for cfg in ("autopoweroff=0", "autopoweroff=65535"):
            try:
                self._gphoto(["--set-config", cfg], timeout=5)
            except Exception:
                pass

        # Live-View durch einen Preview-Pull starten — das ist der zuverlässige
        # Trigger für Canon-Kameras, viewfinder=1 alleine reicht oft nicht.
        if not self._kick_liveview():
            logger.warning("Init: Live-View-Start fehlgeschlagen — Display bleibt evtl. aus")

        self.available = True
        self.error_message = ""
        logger.info("Kamera bereit — Keep-Alive alle %ds", self._keepalive_s)

    # ── Live-View Keep-Alive ───────────────────────────────────────────────────

    def _kick_liveview(self) -> bool:
        """Holt einen Preview-Frame und verwirft ihn — Side-Effect: Live-View
        wird gestartet bzw. der Auto-Off-Timer der Kamera zurückgesetzt.

        Return True wenn die Kamera erreichbar war.
        """
        try:
            with self._cmd_lock:
                result = subprocess.run(
                    ["gphoto2", "--capture-preview", "--stdout"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=8,
                )
                return result.returncode == 0
        except subprocess.TimeoutExpired:
            logger.debug("LV-Kick: Timeout")
        except Exception as exc:
            logger.debug("LV-Kick: %s", exc)
        return False

    # ── Watchdog ───────────────────────────────────────────────────────────────

    def _watchdog(self):
        while self._running:
            time.sleep(self._keepalive_s)
            if self._capturing:
                continue  # Capture-Vorgang nicht stören

            if not self.available:
                if self._detect():
                    logger.info("Watchdog: Kamera wieder erkannt – reinit")
                    self._init()
                continue

            # Live-View durch Preview-Pull frisch halten. Schlägt der Pull
            # fehl, ist die Verbindung wahrscheinlich verloren.
            if not self._kick_liveview():
                self.available = False
                self.error_message = "Kamera-Kontakt verloren – USB prüfen"
                logger.warning("Watchdog: Live-View-Pull fehlgeschlagen")

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

        # Live-View nach Aufnahme reaktivieren — die Kamera fällt nach
        # einem Capture meist aus dem Live-View-Modus
        self._kick_liveview()

        after = set(os.listdir(directory))
        new_files = after - before
        name = (max(new_files, key=lambda f: os.path.getmtime(os.path.join(directory, f)))
                if new_files else filename)
        path = os.path.join(directory, name)
        logger.info("Foto gespeichert: %s", path)
        return path

    def close(self):
        self._running = False
