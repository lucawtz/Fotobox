import logging
import os
import shutil
import subprocess
import threading
import time

logger = logging.getLogger(__name__)


# Modul-globaler Status, den der gallery_server (anderer Thread) gefahrlos
# auslesen kann — ohne selbst gphoto2 zu starten und damit eine USB-Kollision
# mit der Camera-Watchdog zu riskieren. Camera setzt das bei jedem Detect.
_status_lock = threading.Lock()
_latest_status = {"available": False, "error": "Kamera noch nicht initialisiert"}


def latest_status() -> dict:
    with _status_lock:
        return dict(_latest_status)


def _set_status(available: bool, error: str = ""):
    with _status_lock:
        _latest_status["available"] = available
        _latest_status["error"] = error


class Camera:
    """gphoto2-Wrapper mit Watchdog und asynchronem Live-View-Wake.

    Jeder gphoto2-Aufruf ist ein eigener Prozess mit kompletter
    USB-Session-Initialisierung (1-2 s), und jeder Wechsel in oder aus dem
    Live-View klappt den Spiegel — das ist das hoerbare Klicken. Daraus
    folgen die zwei Regeln dieses Moduls: so wenige gphoto2-Aufrufe wie
    moeglich, und keiner davon in der Zeit, in der ein Gast auf den
    Bildschirm schaut und wartet.

    Aufgabenteilung:
      _init()             einmalige Kamera-Settings + erster Live-View
      wake_liveview()     Spiegel hoch, blockierend — fuer _init und den
                          manuellen Wake (Q bzw. Tasterkombination)
      request_liveview()  dasselbe im Hintergrund, fuer die Stellen an
                          denen gleich wieder ein Live-Bild sichtbar wird
      capture()           NUR die Aufnahme, ohne Live-View-Geraffel

    Live-View bei der EOS 700D braucht zwei Schritte:
    1. viewfinder=1 — Spiegel hoch, LV-Modus an
    2. capture-preview — pullt einmal einen Frame, sonst faellt die 700D
       nach dem Spiegelhub sofort wieder heraus. Falls die Kamera den Pull
       nicht braucht, spart `camera_preview_pull: false` einen Spiegelhub
       und bis zu 8 s pro Wake.

    `output` (wohin das Live-Bild geht) gehoert in JEDEN Wake, und zwar NACH
    viewfinder=1. Beides ist gemessen, nicht angenommen: der Wert haelt nicht
    ueber das Prozessende hinaus (danach liest er sich wieder als 'Off'), und
    gphoto2 zieht ihn beim Einschalten des Viewfinders selbst auf 'PC' — wer
    ihn vorher setzt, bekommt ihn genau dort ueberschrieben und schickt das
    Live-Bild damit ausschliesslich ueber USB, nie auf HDMI.

    Wichtiger Vorbehalt zum ganzen Modul: der per PTP eingeschaltete Live-View
    lebt nur, solange ein gphoto2-Prozess die Sitzung offen haelt. Endet der
    Prozess, faellt die Kamera zurueck und HDMI zeigt wieder ihr Info-Display.
    Ein Wake reicht also fuer den Moment, nicht fuer die Dauer.

    Beobachtetes "Ausloese-Geraeusch" beim capture-preview ist nur der
    Spiegelhub, nicht der Verschluss — keine Shutter-Aktuationen verbraucht.

    An der Kamera selbst gehoert eingestellt: 'Auto-Power-Off' aus,
    Bildqualitaet JPEG (NICHT RAW+JPEG — zwei Dateien auf einen --filename
    lassen den Download scheitern) und manueller Fokus. Siehe README,
    Abschnitt "Kamera einstellen".
    """

    DEFAULT_KEEPALIVE_S = 25
    # Index in der Choice-Liste der Kamera, nicht der Klartextwert. Welcher
    # Index welchen Modus meint, ist modellabhaengig und steht in der Ausgabe
    # von `gphoto2 --get-config output` — bei falschem Index kommt aus der
    # Kamera weder auf HDMI noch auf dem Display ein Bild.
    DEFAULT_OUTPUT_MODE = "3"

    # Obergrenze der eigentlichen Aufnahme inklusive Download.
    CAPTURE_TIMEOUT_S = 30
    # Obergrenze fuer das Warten auf einen anderen, noch laufenden
    # gphoto2-Aufruf — etwa einen Live-View-Wake, der zwischen zwei
    # Collage-Shots noch nicht fertig ist. Ohne diese Grenze konnte ein
    # haengender Aufruf beliebig weit in die Wartezeit des naechsten Gastes
    # hineinlaufen und dort einen Timeout ausloesen, der nach Kamerafehler
    # aussah.
    BUSY_TIMEOUT_S = 10

    def __init__(self, keepalive_s: int = DEFAULT_KEEPALIVE_S,
                 output_mode: str = DEFAULT_OUTPUT_MODE,
                 preview_pull: bool = True):
        self.available = False
        self.error_message = ""
        self._running = True
        self._cmd_lock = threading.Lock()
        self._capturing = False
        self._keepalive_s = max(5, int(keepalive_s))
        self._output_mode = str(output_mode)
        self._preview_pull = bool(preview_pull)
        # Laesst hoechstens einen Hintergrund-Wake gleichzeitig zu: vier
        # Collage-Shots wuerden sonst vier Wake-Threads hinterlassen, die
        # sich auf dem _cmd_lock stauen und die Kamera vier Mal klappern
        # lassen, obwohl einmal reicht.
        self._wake_gate = threading.Semaphore(1)
        self._stdbuf = shutil.which("stdbuf")
        self._init()
        threading.Thread(target=self._watchdog, daemon=True).start()

    @property
    def capture_budget_s(self) -> float:
        """Was ein capture()-Aufruf von aussen hoechstens dauern kann.

        main.py leitet daraus seinen UI-Timeout ab, statt eine zweite Zahl zu
        pflegen. Genau daran lief der frueher fest verdrahtete 35-s-Timeout
        in den Fehlerfall: capture() haengte damals noch das Live-View-Wecken
        an die Aufnahme und konnte 48 s brauchen — die UI gab nach 35 s auf
        und verwarf ein Foto, das laengst auf der Platte lag.
        """
        return float(self.CAPTURE_TIMEOUT_S + self.BUSY_TIMEOUT_S)

    # ── gphoto2-Wrapper ────────────────────────────────────────────────────────

    def _gphoto(self, args: list, timeout: int = 10):
        with self._cmd_lock:
            return subprocess.run(
                ["gphoto2"] + args,
                capture_output=True, text=True, timeout=timeout,
            )

    def _set_config(self, assignment: str, timeout: int = 5,
                    by_index: bool = False) -> bool:
        """Setzt eine gphoto2-Config und sagt, ob die Kamera sie genommen hat.

        Frueher stand die immer gleiche try/returncode/stderr-Kaskade an
        jeder Aufrufstelle einzeln — und an zweien davon wurde der
        Rueckgabewert gar nicht ausgewertet.

        by_index=True nimmt --set-config-index. Bei Auswahllisten ist das
        blanke --set-config mehrdeutig: 'output=3' kann die Nummer 3 aus der
        Liste meinen oder den Wert 3. Auf der EOS 700D landete die Kamera
        damit auf 'PC' statt auf 'TFT + PC' — das Live-Bild ging also nur
        ueber USB und nie auf HDMI, wo die Capture-Card haengt.
        """
        flag = "--set-config-index" if by_index else "--set-config"
        try:
            r = self._gphoto([flag, assignment], timeout=timeout)
        except Exception as exc:
            logger.debug("  → %s Exception: %s", assignment, exc)
            return False
        if r.returncode == 0:
            logger.info("  → %s OK", assignment)
            return True
        err = (r.stderr or "").strip()[:120] or "(kein Fehlertext)"
        logger.info("  → %s fehlgeschlagen: %s", assignment, err)
        return False

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
            _set_status(False, self.error_message)
            logger.warning(self.error_message)
            return

        # Bildkontrolle aus: sonst blendet die Kamera nach jeder Aufnahme das
        # Foto ins Display und damit auch auf HDMI.
        self._set_config("reviewtime=0", timeout=10)

        # Auto-Power-Off best effort. Welcher Wert "aus" bedeutet, ist
        # modellabhaengig: 0 bei den einen, 65535 bei den anderen. Bisher
        # wurden stumpf beide gesetzt, wodurch der zweite den ersten wieder
        # ueberschrieb. Jetzt bleibt der erste stehen, den die Kamera nimmt.
        for value in ("0", "65535"):
            if self._set_config(f"autopoweroff={value}"):
                break

        # Live-View direkt beim Start aktivieren, damit die Fotobox sofort
        # nach dem App-Start ein Live-Bild zeigt und niemand erst den
        # Q-Knopf oder den Display-Knopf druecken muss.
        self.wake_liveview()

        self.available = True
        self.error_message = ""
        _set_status(True, "")
        logger.info("Kamera bereit (Live-View aktiviert)")

    # ── Live-View Wake ─────────────────────────────────────────────────────────

    def wake_liveview(self, with_preview: bool = None,
                      reset_output: bool = False) -> bool:
        """Aktiviert Live-View an der Kamera. Blockiert bis zu ~13 s.

        Schritt 1: viewfinder=1 — Live-View an, Spiegel hoch.
        Schritt 2: output auf TFT+PC. Die Reihenfolge ist NICHT beliebig:
            gphoto2 zieht beim Einschalten des Viewfinders den Ausgang selbst
            auf 'PC', damit es die Frames ueber USB bekommt. Wer output vorher
            setzt, bekommt es genau dort ueberschrieben — gemessen an der
            EOS 700D, die daraufhin 'PC' meldete und auf HDMI nichts ausgab.
        Schritt 3 (optional): einen Preview-Frame abrufen.

        with_preview=None uebernimmt die Konfiguration (camera_preview_pull),
        True/False ueberstimmt sie fuer diesen Aufruf.

        `reset_output` ist wirkungslos und bleibt nur, damit bestehende
        Aufrufe nicht brechen: output wird inzwischen bei jedem Wake gesetzt.
        Es haelt naemlich nicht — nach dem Ende des gphoto2-Prozesses liest es
        sich wieder als 'Off'. Die frueher hier stehende Annahme, der Wert
        bleibe in der Kamera stehen, war schlicht falsch.

        Aufrufer im UI-Pfad nehmen request_liveview() — das hier blockiert.
        """
        if with_preview is None:
            with_preview = self._preview_pull
        logger.info("wake_liveview(with_preview=%s)", with_preview)

        ok = self._set_config("viewfinder=1")
        self._set_config(f"output={self._output_mode}", by_index=True)

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

    def request_liveview(self) -> None:
        """Weckt den Live-View im Hintergrund — der Aufrufer wartet nicht.

        Gedacht fuer die Stellen, an denen gleich wieder ein Bildschirm mit
        Live-Bild kommt (Homescreen nach dem Result-Screen, Countdown des
        naechsten Collage-Shots). Frueher haengte capture() das Aufwecken
        direkt an die Aufnahme — also genau in die Sekunden, in denen der
        Gast auf "Foto wird übertragen" starrt, obwohl danach der
        Result-Screen kommt, der ueberhaupt kein Live-Bild zeigt.

        Mehrfachaufrufe sind billig: laeuft schon ein Wake, kehrt der
        naechste sofort zurueck, statt einen zweiten Spiegelhub anzustossen.
        """
        if not self.available or self._capturing or not self._running:
            return
        if not self._wake_gate.acquire(blocking=False):
            return

        def _run():
            try:
                self.wake_liveview()
            except Exception as exc:
                logger.warning("Hintergrund-Wake fehlgeschlagen: %s", exc)
            finally:
                self._wake_gate.release()

        threading.Thread(target=_run, daemon=True).start()

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
                _set_status(False, self.error_message)
                logger.warning("Watchdog: Kamera verloren")
            # Sonst: nichts tun. Der Watchdog weckt bewusst keinen Live-View
            # — das wuerde eine manuelle Aktivierung am Kamera-Display wieder
            # killen. Wecken tut, wer das Live-Bild gleich braucht.

    # ── Capture ────────────────────────────────────────────────────────────────

    # Diese Zeile schreibt gphoto2, sobald die Kamera die Datei angelegt hat —
    # die Belichtung ist damit durch. Auf der EOS 700D gemessen liegt sie rund
    # 0,7 s hinter dem EXIF-Ausloesezeitpunkt: als "es ist passiert"-Signal
    # taugt sie, als Vorhersage nicht. Fuer den Vorlauf vor dem Ausloesen gibt
    # es deshalb capture_lead_s in der Config.
    _SHUTTER_MARKER = "New file is in location"

    def _run_capture(self, filename: str, directory: str, on_shutter):
        """Startet gphoto2 und meldet den Ausloesemoment, sobald er kommt.

        Rueckgabe: (Returncode, gesammelte Ausgabe).

        Statt subprocess.run, weil hier die Ausgabe waehrend des Laufs
        gebraucht wird und nicht erst danach — subprocess.run gibt sie
        geschlossen am Ende zurueck, und dann ist der Moment vorbei.

        stderr laeuft in denselben Strom: gphoto2 verteilt seine Meldungen auf
        beide, und zwei Pipes einzeln leerzupumpen waere ein Verklemmungsrisiko
        fuer nichts — die Fehlermeldung entsteht ohnehin aus dem Gesamttext.
        """
        cmd = ["gphoto2", "--capture-image-and-download", "--filename", filename]
        # Ohne Zeilenpufferung schiebt gphoto2 seine Ausgabe blockweise raus,
        # sobald sie in eine Pipe geht — die Marker-Zeile kaeme dann erst zum
        # Prozessende und waere als Signal wertlos. Fehlt stdbuf, laeuft die
        # Aufnahme normal weiter, nur eben ohne frueheren Marker.
        if self._stdbuf:
            cmd = [self._stdbuf, "-oL"] + cmd

        proc = subprocess.Popen(
            cmd, cwd=directory, text=True, bufsize=1,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )

        lines = []

        def _read():
            for line in proc.stdout:
                lines.append(line.rstrip())
                if on_shutter is None or self._SHUTTER_MARKER not in line:
                    continue
                try:
                    on_shutter()
                except Exception as exc:      # der Callback gehoert der UI
                    logger.warning("on_shutter fehlgeschlagen: %s", exc)

        reader = threading.Thread(target=_read, daemon=True)
        reader.start()
        try:
            proc.wait(timeout=self.CAPTURE_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
            raise RuntimeError("Aufnahme Timeout")
        finally:
            # Der Lesethread haengt an der Pipe und endet mit ihr. Nach einem
            # kill kann das einen Wimpernschlag dauern, deshalb ueberhaupt ein
            # join — und deshalb einer mit Grenze.
            reader.join(timeout=2.0)
        return proc.returncode, "\n".join(lines)


    def capture(self, directory: str, on_shutter=None) -> str:
        """Nimmt genau ein Foto auf und gibt dessen Pfad zurueck.

        Bewusst NUR die Aufnahme: kein Live-View davor, keiner danach. Der
        Live-View wird dort geweckt, wo er wieder sichtbar wird — siehe
        request_liveview() und main._capture_sequence.

        `on_shutter` wird aufgerufen, sobald die Kamera die Belichtung hinter
        sich hat — daran haengt die UI ihr "Lächeln!". Der Aufruf kommt aus
        dem Lese-Thread, muss also selbst thread-sicher sein und darf nicht
        blockieren. Bleibt der Marker aus, kommt der Callback gar nicht; die
        UI braucht dafuer eine eigene Obergrenze.
        """
        if not self.available:
            raise RuntimeError("Kamera nicht verfügbar")
        os.makedirs(directory, exist_ok=True)
        # Millisekunden im Filename — int(time.time()) hat Sekunden-Aufloesung
        # und wuerde bei zwei Captures innerhalb derselben Sekunde (Collage!)
        # die vorherige Datei ueberschreiben.
        filename = f"foto_{int(time.time() * 1000)}.jpg"
        before = set(os.listdir(directory))

        self._capturing = True
        try:
            # Nicht unbegrenzt auf das Lock warten: sonst zaehlt die Wartezeit
            # eines fremden gphoto2-Aufrufs voll gegen den UI-Timeout, und der
            # Gast bekommt "Kamera antwortet nicht" fuer eine Kamera, die noch
            # gar nicht gefragt wurde.
            if not self._cmd_lock.acquire(timeout=self.BUSY_TIMEOUT_S):
                raise RuntimeError("Kamera ist noch beschäftigt")
            try:
                rc, output = self._run_capture(filename, directory, on_shutter)
            finally:
                self._cmd_lock.release()
        finally:
            self._capturing = False

        if rc != 0:
            tail = " / ".join(output.split("\n")[-3:]).strip()
            raise RuntimeError(
                f"Aufnahme fehlgeschlagen: {tail or '(kein Fehlertext)'}")

        after = set(os.listdir(directory))
        new_files = after - before
        if not new_files:
            # Frueher fiel capture() hier auf den *erwarteten* Dateinamen
            # zurueck und meldete Erfolg fuer eine Datei, die es nicht gibt.
            # main.py ging damit in den Result-Screen, das Laden scheiterte
            # still im Log und der Gast sah einen schwarzen Bildschirm ohne
            # jede Erklaerung. Haeufigste Ursachen: die Kamera steht auf
            # RAW+JPEG (zwei Dateien, ein --filename) oder capturetarget
            # zeigt auf die Speicherkarte statt auf den internen Speicher.
            raise RuntimeError(
                "Kamera hat kein Bild geliefert – Bildqualität (JPEG statt "
                "RAW+JPEG) und Speicherziel prüfen")
        name = max(new_files,
                   key=lambda f: os.path.getmtime(os.path.join(directory, f)))
        path = os.path.join(directory, name)
        logger.info("Foto gespeichert: %s", path)
        return path

    def close(self):
        self._running = False
