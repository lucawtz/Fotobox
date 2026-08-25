import contextlib
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
    """gphoto2-Wrapper mit dauerhaft offener Live-View-Sitzung.

    Der Halte-Prozess ist der Kern des Moduls. Der per USB eingeschaltete
    Live-View lebt nur, solange ein gphoto2-Prozess die PTP-Sitzung offen
    haelt; endet der Prozess, faellt die Kamera zurueck und HDMI zeigt wieder
    ihr Info-Display. Das ist gemessen, nicht vermutet: bei offener Sitzung
    trug HDMI durchgehend ein Live-Bild, drei Sekunden nach Prozessende stand
    wieder das Menue. Deshalb laeuft dauerhaft ein Prozess allein zu diesem
    Zweck, und jeder andere Zugriff auf die Kamera muss ihn kurz
    beiseiteraeumen.

    Die zweite Regel des Moduls bleibt: jeder gphoto2-Aufruf ist ein eigener
    Prozess mit kompletter USB-Session-Initialisierung (1-2 s), und jeder
    Wechsel in oder aus dem Live-View klappt den Spiegel — das ist das
    hoerbare Klicken. Also so wenige Aufrufe wie moeglich, und keiner davon in
    der Zeit, in der ein Gast auf den Bildschirm schaut und wartet.

    Aufgabenteilung:
      _init()             einmalige Kamera-Settings, dann Halter an
      _hold_start/_stop() der Prozess, der den Live-View am Leben haelt
      _hold_supervisor()  startet ihn nach, wenn er von selbst endet
      _usb()              Halter weg, Befehl, Halter zurueck
      wake_liveview()     Halter neu aufsetzen, blockierend
      request_liveview()  dasselbe im Hintergrund und nur wenn noetig
      capture()           NUR die Aufnahme, ohne Live-View-Geraffel

    `output` (wohin das Live-Bild geht) gehoert in jeden Start des Halters,
    und zwar NACH viewfinder=1. Auch das ist gemessen: gphoto2 zieht beim
    Einschalten des Viewfinders den Ausgang selbst auf 'PC', damit es die
    Frames ueber USB bekommt — wer ihn vorher setzt, bekommt ihn genau dort
    ueberschrieben und schickt das Live-Bild ausschliesslich ueber USB, nie
    auf HDMI, wo die Capture-Card haengt. Gesetzt wird per Index, weil
    'output=3' sonst mehrdeutig ist (Position in der Liste oder Wert).

    Der frueher noetige capture-preview-Pull ist entfallen. Er sollte den
    Live-View nach dem Spiegelhub am Leben halten — was er nie konnte, weil
    auch er nur ein Prozess war, der sich beendet.

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

    # Wie lange ein Halte-Prozess laeuft, bevor er sich beendet und neu
    # gestartet wird. gphoto2 braucht bei --wait-event eine Obergrenze; die
    # Luecke beim Wechsel ist ein Prozessstart lang (gut eine Sekunde).
    DEFAULT_HOLD_SESSION_S = 1800

    # AF-Methode als Index aus `gphoto2 --get-config afmethod`:
    # 0 LiveFace, 1 LiveMulti, 2 Live, 3 Quick.
    # Voreinstellung 2 (Live): ein kleines festes Feld in der Bildmitte.
    # LiveFace zeichnet stattdessen einen Rahmen um jedes erkannte Gesicht und
    # laesst ihn mitwandern — auf einem 1920x1080-Schirm vor einer Warteschlange
    # ist das der unruhigste Teil des ganzen Bildes. LiveMulti ist noch
    # groesser. Ganz ohne Rahmen geht keine der Methoden, das zeichnet die
    # Kamera in ihr HDMI-Signal.
    DEFAULT_AF_METHOD = "2"

    # Wie lange nach dem Start gewartet wird, bevor der Halter als "steht"
    # gilt. Scheitert gphoto2 am belegten USB-Geraet, beendet es sich in
    # dieser Zeit — ohne die Pause meldeten wir Erfolg fuer einen Prozess,
    # der gerade stirbt.
    HOLD_GRACE_S = 1.5

    def __init__(self, keepalive_s: int = DEFAULT_KEEPALIVE_S,
                 output_mode: str = DEFAULT_OUTPUT_MODE,
                 preview_pull: bool = True,   # entfallen, siehe wake_liveview
                 hold_session_s: int = DEFAULT_HOLD_SESSION_S,
                 af_method: str = DEFAULT_AF_METHOD):
        self.available = False
        self.error_message = ""
        self._running = True
        self._cmd_lock = threading.Lock()
        self._capturing = False
        self._keepalive_s = max(5, int(keepalive_s))
        self._output_mode = str(output_mode)
        # Laesst hoechstens einen Hintergrund-Wake gleichzeitig zu: vier
        # Collage-Shots wuerden sonst vier Wake-Threads hinterlassen, die
        # sich auf dem _cmd_lock stauen und die Kamera vier Mal klappern
        # lassen, obwohl einmal reicht.
        self._wake_gate = threading.Semaphore(1)
        self._stdbuf = shutil.which("stdbuf")
        # Der Halte-Prozess und die Absicht, einen zu haben. Beides getrennt:
        # waehrend einer Aufnahme laeuft keiner, gewollt ist er trotzdem.
        self._holder = None
        self._hold_wanted = False
        self._hold_session_s = max(30, int(hold_session_s))
        self._af_method = str(af_method)
        self._init()
        threading.Thread(target=self._hold_supervisor, daemon=True).start()
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

    @contextlib.contextmanager
    def _usb(self, timeout: float = -1):
        """Exklusiver Zugriff auf die Kamera fuer die Dauer des Blocks.

        Der Halte-Prozess wird dafuer beendet und danach wieder gestartet:
        gphoto2 kann sich das USB-Geraet nicht teilen, ein zweiter Aufruf
        bekaeme "Could not claim the USB device". Das Live-Bild ist in dieser
        Zeit weg — deshalb gehoert in einen solchen Block nur, was wirklich
        mit der Kamera reden muss.
        """
        if not self._cmd_lock.acquire(timeout=timeout):
            raise RuntimeError("Kamera ist noch beschäftigt")
        try:
            self._hold_stop()
            yield
        finally:
            if self._hold_wanted and self._running:
                self._hold_start()
            self._cmd_lock.release()

    def _gphoto(self, args: list, timeout: int = 10):
        with self._usb():
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

        # AF-Methode. Steht hier und nicht im Halter, weil sie — anders als
        # output — ueber das Prozessende hinaus in der Kamera stehen bleibt.
        self._set_config(f"afmethod={self._af_method}", by_index=True)

        # Auto-Power-Off best effort. Welcher Wert "aus" bedeutet, ist
        # modellabhaengig: 0 bei den einen, 65535 bei den anderen. Bisher
        # wurden stumpf beide gesetzt, wodurch der zweite den ersten wieder
        # ueberschrieb. Jetzt bleibt der erste stehen, den die Kamera nimmt.
        for value in ("0", "65535"):
            if self._set_config(f"autopoweroff={value}"):
                break

        # Ab hier soll dauerhaft ein Halte-Prozess laufen. Er schaltet den
        # Live-View ein und haelt ihn, solange er lebt — damit steht das
        # Live-Bild ab dem App-Start und niemand muss erst den Q-Knopf oder
        # den Display-Knopf an der Kamera druecken.
        self._hold_wanted = True
        self._hold_start()

        self.available = True
        self.error_message = ""
        _set_status(True, "")
        logger.info("Kamera bereit (Live-View aktiviert)")

    # ── Live-View Wake ─────────────────────────────────────────────────────────

    def _hold_alive(self) -> bool:
        p = self._holder
        return p is not None and p.poll() is None

    def _hold_start(self) -> None:
        """Startet den Halte-Prozess, falls keiner laeuft.

        Der Prozess tut nichts weiter, als den Live-View einzuschalten und
        danach auf Ereignisse zu warten — er existiert allein dafuer, die
        PTP-Sitzung offen zu halten. Die Reihenfolge (viewfinder zuerst,
        dann output) ist die gemessene, siehe Klassen-Docstring.
        """
        if self._hold_alive():
            return
        cmd = ["gphoto2",
               "--set-config", "viewfinder=1",
               "--set-config-index", f"output={self._output_mode}",
               f"--wait-event={self._hold_session_s}s"]
        try:
            self._holder = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:
            self._holder = None
            logger.warning("Halte-Prozess liess sich nicht starten: %s", exc)

    def _hold_stop(self) -> None:
        """Beendet den Halte-Prozess und wartet, bis er das USB-Geraet los ist.

        Das Warten ist der Punkt: ohne es wuerde der naechste gphoto2-Aufruf
        auf ein noch belegtes Geraet treffen.
        """
        p, self._holder = self._holder, None
        if p is None or p.poll() is not None:
            return
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("Halte-Prozess reagiert nicht auf terminate — kill")
            p.kill()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.error("Halte-Prozess liess sich nicht beenden")

    def _hold_supervisor(self) -> None:
        """Startet den Halte-Prozess nach, wenn er von selbst endet.

        Das passiert regelmaessig — nach _hold_session_s laeuft --wait-event
        aus — und unregelmaessig, wenn die Kamera zwischendurch zickt. Beides
        sieht von hier gleich aus und wird gleich behandelt.

        Bewusst pollend statt auf den Prozess wartend: waehrend einer Aufnahme
        soll gerade NICHT nachgestartet werden, und ein blockierendes wait()
        wuesste davon nichts.
        """
        while self._running:
            time.sleep(1.0)
            if not self._hold_wanted or self._capturing or self._hold_alive():
                continue
            # Nur wenn gerade kein anderer gphoto2-Aufruf laeuft — sonst
            # naehmen wir ihm das Geraet unter den Haenden weg.
            if not self._cmd_lock.acquire(blocking=False):
                continue
            try:
                self._hold_start()
            finally:
                self._cmd_lock.release()

    def wake_liveview(self, with_preview: bool = None,
                      reset_output: bool = False) -> bool:
        """Holt den Live-View zurueck — durch einen neuen Halte-Prozess.

        Frueher schaltete diese Methode den Live-View ein und ging davon aus,
        er bleibe an. Er bleibt nicht: der per USB eingeschaltete Live-View
        lebt nur, solange ein gphoto2-Prozess die PTP-Sitzung offen haelt.
        Endet der Prozess, faellt die Kamera zurueck und HDMI zeigt wieder ihr
        Info-Display. Deshalb ist "wecken" hier gleichbedeutend mit "den
        Halter neu aufsetzen".

        `with_preview` und `reset_output` sind wirkungslos und bleiben nur,
        damit bestehende Aufrufe nicht brechen. Der frueher noetige
        capture-preview-Pull erledigt sich mit der offenen Sitzung von selbst
        — er sollte den Live-View am Leben halten, was in Wahrheit nie
        funktionierte.
        """
        self._hold_wanted = True
        logger.info("wake_liveview — Halte-Prozess wird neu gestartet")
        if not self._cmd_lock.acquire(timeout=self.BUSY_TIMEOUT_S):
            logger.warning("Wake: Kamera ist noch beschäftigt")
            return False
        try:
            self._hold_stop()
            self._hold_start()
        finally:
            self._cmd_lock.release()

        # Kurz nachsehen, ob er steht: scheitert gphoto2 am USB-Geraet, ist er
        # nach gut einer Sekunde wieder weg. Ohne diese Pause meldeten wir
        # Erfolg fuer einen Prozess, der gerade stirbt.
        time.sleep(self.HOLD_GRACE_S)
        ok = self._hold_alive()
        logger.info("  → Live-View %s", "steht" if ok else "kam nicht hoch")
        return ok

    def request_liveview(self) -> None:
        """Sorgt im Hintergrund dafuer, dass der Live-View steht.

        Laeuft der Halter schon, kostet das nichts — der Normalfall. Nur wenn
        er fehlt, wird ein Wake angestossen, und auch dann hoechstens einer
        gleichzeitig.
        """
        if not self.available or self._capturing or not self._running:
            return
        if self._hold_alive():
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
        """Prueft, ob die Kamera noch da ist — moeglichst ohne sie zu stoeren.

        Solange der Halte-Prozess laeuft, ist die Frage bereits beantwortet:
        er redet ununterbrochen mit der Kamera. Frueher lief hier alle 25 s
        ein eigenes --auto-detect; mit offener Sitzung waere das nicht nur
        ueberfluessig, sondern schaedlich — jeder Aufruf muesste den Halter
        beenden und damit das Live-Bild fuer ein paar Sekunden wegnehmen.
        Nachgesehen wird deshalb nur, wenn der Halter gerade NICHT steht.
        """
        while self._running:
            time.sleep(self._keepalive_s)
            if self._capturing:
                continue

            if self._hold_alive():
                if not self.available:
                    self.available = True
                    self.error_message = ""
                    _set_status(True, "")
                    logger.info("Watchdog: Kamera wieder da")
                continue

            if not self.available:
                # Kein Halter und keine Kamera: nachsehen, ob inzwischen eine
                # da ist. Bewusst NICHT an _hold_wanted geknuepft — genau
                # daran haengt der Fall "Pi laeuft schon, Kamera geht erst
                # jetzt an": beim App-Start scheitert _init am _detect,
                # _hold_wanted bleibt False, und ein Halter, der uns die
                # Frage abnehmen koennte, existiert nie. Ohne diesen Weg
                # blieb der Fehlerbanner bis zum naechsten Neustart stehen.
                if self._detect():
                    logger.info("Watchdog: Kamera erkannt – init")
                    self._init()
            elif self._hold_wanted:
                self.available = False
                self.error_message = "Kamera getrennt – USB prüfen"
                _set_status(False, self.error_message)
                logger.warning("Watchdog: Kamera verloren")

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
            # Nicht unbegrenzt auf das Geraet warten: sonst zaehlt die
            # Wartezeit eines fremden gphoto2-Aufrufs voll gegen den
            # UI-Timeout, und der Gast bekommt "Kamera antwortet nicht" fuer
            # eine Kamera, die noch gar nicht gefragt wurde.
            #
            # _usb beendet dafuer den Halte-Prozess — das Live-Bild ist
            # waehrend der Aufnahme also weg und kommt danach von selbst
            # wieder. Genau dort schaut ohnehin niemand hin: es folgt der
            # Result-Screen.
            with self._usb(timeout=self.BUSY_TIMEOUT_S):
                rc, output = self._run_capture(filename, directory, on_shutter)
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
        self._hold_wanted = False
        self._hold_stop()
