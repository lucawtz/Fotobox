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

    # Output-Mode für die EOS-700D: TFT = HDMI/Display, PC = USB-Preview.
    # Wir brauchen beides: TFT für die Capture-Card, PC für capture-preview.
    OUTPUT_MODE = "3"  # = TFT + PC

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

    def wake_liveview(self, with_preview: bool = True) -> bool:
        """Aktiviert Live-View an der Kamera.

        Schritt 1: output=3 (TFT+PC) setzen — bei der EOS 700D ist
            output per Default auf "Off"; ohne das kommt überhaupt
            kein Bild aus der Kamera (weder Display noch HDMI noch USB).
        Schritt 2: viewfinder=1 (Live-View-Modus an, Spiegel hoch).
        Schritt 3 (optional): einen Preview-Frame über USB abrufen, damit
            die Kamera im Live-View-Modus bleibt — ohne diesen Pull fällt
            die 700D nach dem Spiegelhub sofort zurück.

        with_preview=False für Watchdog-Calls — den Preview-Pull machen
        wir nur wenn der Nutzer aktiv weckt (Q-Knopf, vor Aufnahme), nicht
        alle 30s im Watchdog.
        """
        logger.info("wake_liveview(with_preview=%s)", with_preview)
        ok = False

        # Schritt 1: output auf TFT+PC stellen (Default ist Off!)
        try:
            r = self._gphoto(["--set-config", f"output={self.OUTPUT_MODE}"], timeout=5)
            if r.returncode == 0:
                logger.info("  → output=%s (TFT+PC) OK", self.OUTPUT_MODE)
            else:
                err = r.stderr.strip()[:120] if r.stderr else "(kein Fehlertext)"
                logger.info("  → output=%s fehlgeschlagen: %s",
                            self.OUTPUT_MODE, err)
        except Exception as exc:
            logger.debug("  → output Exception: %s", exc)

        # Schritt 2: viewfinder einschalten
        try:
            r = self._gphoto(["--set-config", "viewfinder=1"], timeout=5)
            if r.returncode == 0:
                logger.info("  → viewfinder=1 OK")
                ok = True
            else:
                err = r.stderr.strip()[:120] if r.stderr else "(kein Fehlertext)"
                logger.info("  → viewfinder=1 fehlgeschlagen: %s", err)
        except Exception as exc:
            logger.debug("  → viewfinder Exception: %s", exc)

        # Schritt 3: Preview-Pull damit Live-View aktiv bleibt
        if with_preview:
            try:
                with self._cmd_lock:
                    r = subprocess.run(
                        ["gphoto2", "--capture-preview", "--stdout"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                        timeout=8,
                    )
                if r.returncode == 0:
                    logger.info("  → capture-preview OK (Live-View hält)")
                    ok = True
                else:
                    err = r.stderr.decode("utf-8", errors="replace").strip()[:200]
                    logger.warning("  → capture-preview failed: %s", err)
            except subprocess.TimeoutExpired:
                logger.warning("  → capture-preview Timeout")
            except Exception as exc:
                logger.warning("  → capture-preview Exception: %s", exc)

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
                # Sicherer Keep-Alive: nur viewfinder=1 nachsetzen ohne
                # Preview-Pull — sonst klappert der Spiegel alle 30s.
                # Live-View startet trotzdem nicht zuverlässig — der Nutzer
                # muss Q drücken (= wake_liveview mit Preview-Pull).
                self.wake_liveview(with_preview=False)

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
