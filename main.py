import argparse
import logging
import os
import signal
import sys
import threading
import time
from typing import Optional

import pygame

import collage as collage_mod
import config
import disk_monitor
import events
import gallery_server
import hotspot
import printing
import usb_status
from camera import Camera
from hardware import Buttons
from ui import UI

# ── Logging ────────────────────────────────────────────────────────────────────

def _setup_logging():
    """Logs gehen via stdout — systemd-Service leitet das via
    StandardOutput=append:.../logs/fotobox.log direkt in die Datei
    um. Daher KEIN zusätzlicher FileHandler aus Python — sonst stünde
    jede Zeile doppelt im Log.
    """
    log_dir = os.path.join(config.BASE_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[logging.StreamHandler(sys.stdout)],
    )


logger = logging.getLogger(__name__)


# Rueckgabewert fuer den bewusst herbeigefuehrten Ausstieg (Esc am Bildschirm
# oder Fenster zu). Die systemd-Unit laesst die Box danach als EINZIGE Ausnahme
# stehen — jeder andere Exit startet sie neu, siehe RestartPreventExitStatus
# in fotobox.service.
#
# Der Grund: main.py endet auch dann mit 0, wenn die Display-Session
# wegbricht. Mit dem frueheren Restart=on-failure blieb die Box danach tot
# liegen, ohne dass es nach einem Fehler aussah. Am 26.08. zweimal passiert,
# einmal ueber Nacht — neun Stunden Ausfall, die niemand bemerkt haette.
EXIT_USER_QUIT = 42

# Bildrate der Zustandsmaschine (Homescreen, Ergebnis, Slideshow).
#
# Waren 30, und der Hauptthread lag damit dauerhaft bei 99,8 % CPU — der mit
# Abstand groesste Einzelposten auf einem Pi, der ohne aktive Kuehlung bei
# 80 Grad laeuft. Gerendert wird dabei nichts, was 30 Bilder pro Sekunde
# braucht: der Homescreen steht still, das Live-Bild darin kommt mit
# capture_fps (6), und die einzige Animation ist das 1,5 s lange Einblenden
# eines neuen Polaroids.
#
# Countdown, Blitz und Ergebnis-Ueberblendung haben ihre eigenen Schleifen mit
# eigenem Takt — die bleiben schnell, dort zaehlt Fluessigkeit.
#
# Die Zahl ist auf der Box ausgemessen, nicht geschaetzt: ein Homescreen-Render
# kostet rund 68 ms. Bei 15 fps waeren das 102 % eines Kerns, die Bremse kommt
# also gar nicht zum Zug — der Hauptthread stand deshalb dauerhaft bei 99,3 %.
# Bei 4 fps fiel er auf 27,2 %, der ganze Prozess von 155 auf 60,7 % und der
# Pi von 78,4 auf 74,0 Grad.
#
#   fps      Hauptthread        Eingabeverzoegerung
#    15        ~100 % (satt)          66 ms
#     8          ~54 %               125 ms
#     6          ~41 %               166 ms
#     4          ~27 %               250 ms
#
# 8 ist gewaehlt, weil schneller zu rendern als das Live-Bild ankommt nichts
# bringt: capture_fps steht auf 6. Die 125 ms Verzoegerung bis ein Tastendruck
# bemerkt wird, sind vor einem funf Sekunden langen Countdown unerheblich.
#
# Der eigentliche Hebel waere, den Homescreen nicht jedes Bild komplett neu zu
# zeichnen — Sidebar, QR-Karten und Polaroids aendern sich zwischen zwei
# Bildern nicht, nur das Live-Bild darin. Dann waeren die 68 ms zweistellig
# kleiner und hoehere Raten wieder bezahlbar. Das ist ein Umbau am Renderpfad
# und steht hier bewusst nicht drin.
STATE_FPS = 8


# ── Capture-Helfer ─────────────────────────────────────────────────────────────

def _do_countdown(ui: UI, camera: Camera, cfg: dict,
                  photo_num: int, total: int) -> Optional[str]:
    result: dict = {"path": None, "error": None}
    done = threading.Event()
    # Wird gesetzt, sobald die Kamera belichtet hat — daran haengt die UI ihr
    # "Lächeln!". Auch im finally, damit ein Fehlschlag den Bildschirm nicht
    # bis zur Obergrenze auf "Lächeln!" stehen laesst.
    shutter = threading.Event()

    def _capture():
        try:
            result["path"] = camera.capture(events.current_event_dir(cfg),
                                            on_shutter=shutter.set)
            if not result["path"]:
                result["error"] = "Kamera lieferte kein Bild"
        except Exception as exc:
            logger.error("Capture fehlgeschlagen: %s", exc)
            result["error"] = str(exc)
        finally:
            shutter.set()
            done.set()

    ui.run_countdown(
        on_capture=_capture,
        seconds=cfg["countdown_duration"],
        photo_num=photo_num,
        total=total,
        lead_s=cfg.get("capture_lead_s", 0.9),
        shutter=shutter,
    )

    # Warten MIT laufender Render-Schleife: sonst steht der Bildschirm bis zum
    # Timeout auf dem letzten "Lächeln!"-Frame und wirkt abgestuerzt.
    #
    # Den Timeout gibt die Kamera vor, statt hier als zweite Zahl zu stehen.
    # Die frueheren festen 35 s waren gegen den 30-s-Capture-Timeout gerechnet
    # — capture() haengte damals aber noch das Live-View-Wecken an und konnte
    # 48 s brauchen. Die UI gab also auf und verwarf Fotos, die es laengst gab.
    timeout = camera.capture_budget_s + 5.0
    if not ui.wait_for_capture(done, timeout=timeout):
        logger.error("Capture-Timeout nach %.0f s — gphoto2 antwortet nicht",
                     timeout)
        ui.show_notice("Kamera antwortet nicht",
                       "Bitte kurz warten und nochmal auslösen")
        return None

    if not result["path"]:
        # Bisher lief der Gast hier ins Leere: Countdown, Blitz — und nichts.
        logger.error("Kein Foto gespeichert: %s", result["error"])
        ui.show_notice("Foto konnte nicht gespeichert werden",
                       "Bitte nochmal auslösen")
        return None

    return result["path"]


COLLAGE_SHOTS = 4

# Wie lange zwischen zwei Collage-Shots auf das Live-Bild gewartet wird, bevor
# der Halte-Prozess erzwungen neu aufgesetzt wird — und wie lange danach.
#
# Die erste Zahl war 1,2 s und damit zu knapp gegen den falschen Startpunkt
# gerechnet: der Halter, auf dessen Bild hier gewartet wird, ist gerade erst
# gestartet — capture() tut das im finally von _usb(), noch bevor es
# zurueckkehrt. Sein Neuaufbau braucht gemessen rund 1,5 s, dazu die gut
# 0,3 s, die der LiveReader ueber sein Bewegungsfenster braucht, ehe er ein
# Bild als lebend durchlaesst (ui._LiveReader._MOTION_WINDOW).
#
# Die 1,2 s liefen also regelmaessig ab, waehrend das Bild schon unterwegs
# war. Der erzwungene Neustart riss dann einen Halter ab, der gleich
# geliefert haette, und zahlte einen zweiten Neuaufbau — rund eine Sekunde je
# Shot, genug um das gehaltene Standbild ueber seine Haltezeit zu heben und
# den naechsten Countdown schwarz zu machen.
#
# 2,0 s decken Neuaufbau und Bewegungsfenster ab. Erst danach ist das
# Ausbleiben des Bildes ein Befund und kein zu frueher Blick. Kommt es
# vorher, kostet die groessere Zahl nichts: wait_for_liveview kehrt mit dem
# ersten frischen Bild zurueck, nicht am Ende des Fensters.
LIVEVIEW_GRACE_S = 2.0
LIVEVIEW_FORCE_S = 3.0


def _capture_sequence(ui: UI, camera, cfg: dict, mode: str) -> Optional[str]:
    """Nimmt ein Einzelfoto ("single") oder eine 2x2-Collage ("collage") auf.

    Rueckgabe: Pfad des Bildes, das auf dem Result-Screen landet — oder None,
    wenn abgebrochen wurde. Der Grund wurde dem Gast dann bereits angezeigt.

    Stand vorher zweimal wortgleich in der State-Machine (Homescreen und
    "Nochmal" auf dem Result-Screen). Als eigene Funktion laesst sich der
    Ablauf ausserdem ohne Kamera und ohne Display testen —
    siehe tests/test_capture_flow.py.
    """
    # Waehrend Countdown und Aufnahme weckt die UI keinen Live-View — ein
    # Spiegelhub mittendrin waere genau der Ruckler, den der ganze Umbau
    # vermeiden soll.
    ui.pause_live_autowake(True)
    # ...und das letzte echte Live-Bild bleibt fuer die ganze Folge stehen.
    # Seine normale Haltezeit ist gegen ein einzelnes Foto gerechnet; bei
    # vier lief sie mitten im naechsten Countdown ab. Siehe
    # ui.hold_live_frame_longer.
    ui.hold_live_frame_longer(True)
    try:
        return (_do_countdown(ui, camera, cfg, 1, 1) if mode == "single"
                else _collage(ui, camera, cfg))
    finally:
        ui.pause_live_autowake(False)
        ui.hold_live_frame_longer(False)
        # Live-View zurueckholen, sobald die Aufnahme durch ist — aber im
        # Hintergrund. Als naechstes kommt der Result-Screen, der zehn
        # Sekunden lang gar kein Live-Bild zeigt; bis der Homescreen wieder
        # dran ist, steht das Bild also laengst. Vorher tat capture() das
        # selbst und synchron, mitten in der Wartezeit des Gastes.
        camera.request_liveview()


def _collage(ui: UI, camera, cfg: dict) -> Optional[str]:
    """Vier Shots hintereinander, zusammengesetzt zur 2x2-Collage."""
    shots: list = []
    for i in range(COLLAGE_SHOTS):
        photo = _do_countdown(ui, camera, cfg, i + 1, COLLAGE_SHOTS)
        if not photo:
            break
        shots.append(photo)
        # Zwischen zwei Shots das Live-Bild schon waehrend "Lächeln!" und dem
        # naechsten Countdown zurueckholen — dort schaut der Gast hin und
        # richtet sich aus. Nach dem letzten Shot nicht: das erledigt der
        # gemeinsame finally-Zweig in _capture_sequence.
        if len(shots) < COLLAGE_SHOTS:
            _restore_liveview(ui, camera)

    if len(shots) == COLLAGE_SHOTS:
        # Vier Bilder zusammenrechnen dauert auf dem Pi gut drei Sekunden.
        # Ohne Ansage steht der Gast vor einem Schirm, auf dem nichts mehr
        # passiert, und haelt die Box fuer haengen geblieben. show_busy statt
        # show_notice: der Frame steht genau so lange wie die Arbeit und
        # verlaengert sie nicht.
        ui.show_busy("Collage wird erstellt", "Gleich fertig…")
        return collage_mod.make_collage(shots, events.current_event_dir(cfg))

    # Abgebrochene Collage: angefangene Einzelfotos nicht in der Galerie
    # liegen lassen. _do_countdown hat den konkreten Fehler schon angezeigt,
    # hier nur noch klarstellen, dass die ganze Collage verworfen wurde.
    _cleanup_orphans(shots)
    ui.show_notice("Collage abgebrochen",
                   f"Nur {len(shots)} von {COLLAGE_SHOTS} Fotos — bitte neu starten")
    return None


def _restore_liveview(ui: UI, camera) -> None:
    """Live-Bild zwischen zwei Collage-Shots zurueckholen — und nachsehen.

    capture() beendet ueber _usb den Halte-Prozess und startet ihn danach
    selbst wieder. Dass er laeuft, heisst aber nicht, dass HDMI wieder ein
    Bild liefert: unmittelbar nach dem Auslesen ist die Kamera oft noch
    beschaeftigt, das viewfinder=1 des Halters scheitert an "PTP Device Busy",
    und der Prozess wartet anschliessend trotzdem auf Events. _hold_alive()
    ist damit True — der Watchdog macht weiter, request_liveview steigt aus,
    und die Selbstheilung der UI ist waehrend der Aufnahme abgeschaltet.

    Beim Einzelfoto faellt das nicht auf, dort folgt der Result-Screen. In der
    Collage folgen drei weitere Countdowns, und ohne Live-Bild richtet sich
    dort niemand mehr aus.

    Dass diese Countdowns frueher zusaetzlich auf schwarzem Grund liefen, ist
    inzwischen anderswo abgefangen: waehrend einer Aufnahmefolge laeuft das
    gehaltene Standbild nicht mehr ab (ui.hold_live_frame_longer). Das nimmt
    dem Fehlschlag hier seine schlimmste Folge, nicht seine Ursache — ein
    Standbild ist kein Live-Bild, und zurueckholen muss es diese Funktion.

    Deshalb wird hier auf das Bild gewartet statt auf den Prozess. Kommt
    binnen LIVEVIEW_GRACE_S keins, wird der Halter erzwungen neu aufgesetzt.
    """
    camera.request_liveview()
    if ui.wait_for_liveview(LIVEVIEW_GRACE_S):
        return
    logger.info("Live-Bild nach dem Shot nicht zurueck — Halter wird erzwungen")
    camera.request_liveview(force=True)
    if not ui.wait_for_liveview(LIVEVIEW_FORCE_S):
        logger.warning("Live-Bild bleibt aus — naechster Countdown laeuft "
                       "auf dem Standbild")


def _do_print(ui: UI, path: str, cfg: dict) -> None:
    """Druckt ein Foto und sagt dem Gast, was passiert ist.

    Vorher war das ein nacktes `Popen(["lp", path])`: kein Zielgeraet, kein
    Papierformat, keine Rueckmeldung, und der Kindprozess wurde nie
    eingesammelt (ein Zombie pro Druck). Jetzt uebernimmt printing.py die
    Aufbereitung und meldet Erfolg oder Fehler zurueck.
    """
    ui.show_notice("Wird gedruckt…", "Einen Moment bitte", seconds=0.8, error=False)
    ok, message = printing.print_photo(path, cfg)
    if ok:
        # `message` ist im Erfolgsfall die Auskunft zur Warteschlange —
        # "Bitte am Drucker warten", oder "3 Fotos vor dir — etwa 3 Minuten",
        # wenn schon welche haengen. Frueher stand hier fest der erste Satz,
        # auch wenn der Gast in Wahrheit der Vierte war.
        ui.show_notice("Foto wird gedruckt", message, seconds=2.5, error=False)
    else:
        logger.error("Drucken fehlgeschlagen: %s", message)
        ui.show_notice("Drucken nicht möglich", message, seconds=4.0)


def _count_photos(picture_dir: str) -> int:
    """Zählt Fotos rekursiv über alle Event-Subordner."""
    exts = {".jpg", ".jpeg", ".png"}
    if not os.path.isdir(picture_dir):
        return 0
    total = 0
    for entry in os.listdir(picture_dir):
        full = os.path.join(picture_dir, entry)
        if os.path.isdir(full):
            try:
                total += sum(1 for f in os.listdir(full)
                             if os.path.splitext(f)[1].lower() in exts)
            except OSError:
                continue
        elif os.path.splitext(entry)[1].lower() in exts:
            total += 1
    return total


class _StatusCache:
    """Cacht Disk-Reads die in der UI-Hauptschleife (~30 Hz) abgefragt werden.
    `_count_photos` und `disk_usage` brauchen wir nur für die Status-Bar —
    1× pro Sekunde reicht.  Spart auf einem Pi mit 500+ Fotos spürbar I/O.
    """
    REFRESH_S = 1.0

    def __init__(self, picture_dir: str, cfg: dict):
        self._picture_dir = picture_dir
        self._cfg = cfg
        self._last = 0.0
        self.free_mb = 0
        self.photo_count = 0
        self.print_ready = False

    def maybe_refresh(self, now_monotonic: float):
        if now_monotonic - self._last < self.REFRESH_S:
            return
        self._last = now_monotonic
        self.free_mb = disk_monitor.get_free_mb(config.BASE_DIR)
        self.photo_count = _count_photos(self._picture_dir)
        # printing.status() cacht intern nochmal (20 s TTL) — hier wird also
        # nicht jede Sekunde ein lpstat geforkt.
        self.print_ready = printing.available(self._cfg)


def _cleanup_orphans(paths):
    """Löscht angelegte Photos einer abgebrochenen Collage."""
    for p in paths:
        try:
            if p and os.path.isfile(p):
                os.remove(p)
        except OSError as exc:
            logger.warning("Orphan-Cleanup %s: %s", p, exc)


# ── Haupt-Funktion ─────────────────────────────────────────────────────────────

def _parse_args():
    p = argparse.ArgumentParser(description="Fotobox")
    p.add_argument("--no-hotspot", action="store_true",
                   help="Hotspot trotz hotspot_enabled=true NICHT starten "
                        "(für Setup/Test mit VNC über Heim-WLAN)")
    p.add_argument("--dev-camera", action="store_true",
                   help="Fotos aus dem Live-View (Webcam) speichern statt per "
                        "gphoto2 — nur für Entwicklung ohne DSLR, NICHT auf dem Pi")
    return p.parse_args()


def main():
    args = _parse_args()
    _setup_logging()
    cfg = config.cfg

    running = True
    user_quit = False

    def shutdown(signum=None, frame=None):
        nonlocal running
        logger.info("Shutdown-Signal empfangen")
        running = False

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT,  shutdown)

    # Ordner anlegen + alte flache Fotos in Datums-Archiv migrieren
    os.makedirs(cfg["picture_dir"],   exist_ok=True)
    os.makedirs(cfg["thumbnail_dir"], exist_ok=True)
    events.migrate_flat_photos(cfg)

    # Hotspot — defensiv: darf die App-Initialisierung niemals blockieren.
    # CLI-Flag --no-hotspot überschreibt config (für VNC-Setup-Betrieb).
    hotspot_wanted = bool(cfg.get("hotspot_enabled")) and not args.no_hotspot
    if hotspot_wanted:
        try:
            hotspot.start()
        except Exception as exc:
            logger.warning("Hotspot-Start fehlgeschlagen: %s", exc)
    elif args.no_hotspot:
        logger.info("Hotspot per --no-hotspot übersprungen — Heim-WLAN bleibt aktiv")

    # Bind-Entscheidung an den *effektiven* Hotspot-Zustand koppeln, nicht nur
    # ans Config-Flag: mit Hotspot muss die Galerie auf allen Interfaces
    # lauschen (Gaeste-Handys), mit --no-hotspot bleibt sie auf 127.0.0.1.
    # Bewusst auch dann 0.0.0.0, wenn hotspot.start() oben gescheitert ist —
    # dann haengt der Pi meist am Heim-/Venue-WLAN und die Galerie ist die
    # einzige Rettung, um noch an die Fotos zu kommen.
    gallery_server.set_bind_all(hotspot_wanted)

    # Galerie-Server: Preflight synchron (Port-Bind-Check + ggf. Fallback)
    # damit der QR-Code in der UI die korrekte Port-Info bekommt. Falls
    # preflight unerwartet wirft, soll der Fotobox-Service trotzdem
    # weiterlaufen — Galerie ist nice-to-have, Auslöser+UI sind kritisch.
    try:
        gallery_server.preflight()
    except Exception as exc:
        logger.error("Galerie-Preflight fehlgeschlagen: %s", exc, exc_info=True)
    threading.Thread(target=gallery_server.run, daemon=True).start()
    logger.info("Galerie: %s", cfg.get("gallery_url", "?"))

    # Kamera (Watchdog im Hintergrund). Im Dev-Modus stattdessen die Webcam,
    # die ohnehin schon den Live-View speist — siehe dev_camera.py.
    if args.dev_camera:
        from dev_camera import DevCamera
        camera = DevCamera()
    else:
        camera = Camera(
            keepalive_s=cfg.get("camera_keepalive_s", 25),
            output_mode=str(cfg.get("camera_output_mode", "3")),
            hold_session_s=int(cfg.get("camera_hold_session_s", 1800)),
            af_method=str(cfg.get("camera_af_method", "2")),
        )

    # Taster (GPIO + Tastatur-Fallback). Ein Pin darf in gpio_pins auf null
    # stehen — dann ist der Taster nicht verbaut, und die UI blendet seine
    # Aktionen aus, statt einen toten Knopf anzuzeigen.
    pins = cfg.get("gpio_pins") or {}
    btns = Buttons(
        pin_left    = pins.get("left",    17),
        pin_trigger = pins.get("trigger", 27),
        pin_right   = pins.get("right",   22),
    )

    # Tastenkuerzel auf dem Result-Screen nur zeigen, wenn die Tastatur
    # wirklich die Eingabe ist. An der Box mit Tastern waere "[ Space ]"
    # eine Anleitung fuer etwas, das der Gast gar nicht hat.
    show_hints = not btns.has_gpio

    # UI
    #
    # should_abort: die UI wartet beim Kaltstart bis zu UI.DISPLAY_WAIT_S auf
    # die Autologin-Sitzung. Ein 'systemctl stop' waehrend dieses Wartens soll
    # nicht erst in den Hard-Kill laufen — der SIGTERM-Handler oben setzt
    # running=False, und das bricht das Warten ab.
    try:
        ui = UI(cfg, cfg.get("capture_device", 0),
                should_abort=lambda: not running)
        ui.show_key_hints = show_hints
        ui.wired_buttons  = frozenset(
            n for n in Buttons.NAMES if btns.wired(n))
    except Exception as exc:
        logger.error("UI konnte nicht gestartet werden: %s", exc)
        camera.close()
        btns.close()
        sys.exit(1)

    # Erst jetzt existiert der LiveReader — die Dev-Kamera zieht ihre Frames
    # von dort, statt das Capture-Device ein zweites Mal zu oeffnen.
    if args.dev_camera:
        camera.set_frame_provider(ui.latest_live_frame)

    # Bleibt das HDMI-Signal schwarz, holt sich die UI den Live-View selbst
    # zurueck. Sehen kann das nur sie, wecken nur die Kamera.
    if cfg.get("camera_auto_wake", True):
        ui.set_liveview_waker(camera.request_liveview)

    logger.info("Fotobox bereit. Space=Einzelfoto  E=Collage  "
                "Q=Wake-Camera/Zurück  I=Status-Leiste  Esc=Beenden  "
                "(die Buttons rechts sind auch klickbar)")

    # ── State-Machine ──────────────────────────────────────────────────────────
    state           = "HOMESCREEN"
    mode            = "single"
    result_photo: Optional[str] = None
    result_since    = 0.0
    idle_since      = time.monotonic()
    clock           = pygame.time.Clock()
    status_cache    = _StatusCache(cfg["picture_dir"], cfg)

    try:
        while running:
            if ui.check_quit():
                # Nur DIESER Weg gilt als gewollt. Ein Abbruch per SIGTERM
                # (systemctl stop/restart) laeuft ueber running=False und
                # endet mit 0 — da startet systemd ohnehin nicht neu, weil es
                # ein angeordneter Stop ist.
                user_quit = True
                break

            now = time.monotonic()

            # Klick/Tap jeden Frame abholen, auch wenn der aktuelle State ihn
            # nicht braucht — sonst bliebe er in der UI liegen und wuerde
            # spaeter im Homescreen eine ungewollte Aufnahme starten.
            clicked = ui.take_click_action()

            status_cache.maybe_refresh(now)
            free_mb   = status_cache.free_mb
            photo_cnt = status_cache.photo_count
            # Der Result-Screen blendet den Druck-Knopf danach ein oder aus.
            ui.print_ready = status_cache.print_ready

            # ── USB-Export hat absolute Priorität ─────────────────────────────
            # Wird vom udev-getriggerten scripts/usb_export.py geschrieben.
            # Solange er aktiv ist, alle anderen UI-Aktionen pausieren.
            usb = usb_status.read()
            if usb is not None:
                ui.render_usb_overlay(usb)
                idle_since = now      # Slideshow-Idle nicht hochzählen lassen
                clock.tick(15)
                continue

            # ── HOMESCREEN ────────────────────────────────────────────────────
            if state == "HOMESCREEN":
                idle_timeout = cfg.get("idle_timeout", 0)
                if idle_timeout > 0 and now - idle_since >= idle_timeout:
                    ui.refresh_slideshow(events.current_event_dir(cfg))
                    state = "SLIDESHOW"
                    continue

                left    = btns.left_pressed()
                trigger = btns.trigger_pressed()
                right   = btns.right_pressed()

                # Ein Klick/Tap auf einen Action-Button zaehlt wie der Knopf,
                # auf den er laut config["actions"][*]["key"] zeigt. Damit ist
                # die Box auf dem Entwicklungs-Laptop ohne GPIO komplett
                # bedienbar (und ein spaeterer Touchscreen ohne Zusatzcode).
                if clicked:
                    action_key = clicked.get("key")
                    trigger = trigger or action_key == "trigger"
                    right   = right   or action_key == "right"
                    left    = left    or action_key == "left"

                # Kamera-Display aufwecken. Normalerweise der linke Taster;
                # ist der nicht verbaut, beide vorhandenen gleichzeitig. Das
                # findet kein Gast zufaellig, und es spart den dritten
                # Taster, solange keiner da ist.
                # Async ausführen damit die UI nicht blockiert während
                # gphoto2 läuft.
                combo_wake = not btns.wired("left") and trigger and right
                if combo_wake or (left and not (trigger or right)):
                    idle_since = now
                    if camera.available:
                        logger.info("Manueller Wake — Live-View einschalten")
                        threading.Thread(
                            target=camera.wake_liveview, daemon=True).start()
                    btns.wait_for_release()

                elif trigger or right:
                    idle_since = now
                    mode       = "single" if trigger else "collage"

                    # Disk-Wartung vor Aufnahme — max_photos gilt PRO Event
                    # (sonst würden bei einer neuen Vermietung die Fotos der
                    # vorigen Mieter durch neue verdrängt).
                    disk_monitor.cleanup_old_thumbnails(
                        cfg["thumbnail_dir"],
                        cfg.get("thumbnail_max_age_days", 30))
                    disk_monitor.enforce_photo_max_age(
                        cfg["picture_dir"],
                        cfg.get("photo_max_age_days", 7))
                    disk_monitor.enforce_max_photos(
                        cfg["picture_dir"],
                        cfg.get("max_photos", 500),
                        event_dir=events.current_event_dir(cfg))

                    # Speicher voll: lieber sauber ablehnen als den Countdown
                    # laufen lassen und gphoto2 still scheitern sehen.
                    # -1 = nicht ermittelbar -> nicht blockieren.
                    block_mb = cfg.get("disk_block_mb", 150)
                    if 0 <= free_mb < block_mb:
                        logger.error("Auslöser blockiert: nur noch %d MB frei", free_mb)
                        ui.show_notice("Speicher voll",
                                       "Bitte Fotos auf USB sichern und löschen")
                        btns.wait_for_release()
                    elif not camera.available:
                        logger.warning("Auslöser ignoriert: %s", camera.error_message)
                        ui.show_notice("Kamera nicht bereit",
                                       camera.error_message or "Bitte Kamera prüfen")
                        btns.wait_for_release()
                    else:
                        # Hier bewusst kein Wake: der Gast hat gerade gedrückt,
                        # ein Spiegelhub würde den Countdown um Sekunden
                        # verzögern. Um den Live-View kümmert sich
                        # _capture_sequence, sobald die Aufnahme durch ist.
                        photo = _capture_sequence(ui, camera, cfg, mode)
                        if photo:
                            result_photo = photo
                            result_since = time.monotonic()
                            state = "RESULT"
                        btns.wait_for_release()
                else:
                    ui.render_homescreen(
                        camera.available, camera.error_message,
                        free_mb, photo_cnt)

            # ── RESULT ────────────────────────────────────────────────────────
            elif state == "RESULT":
                time_left = max(0.0, 10.0 - (now - result_since))

                if time_left <= 0:
                    ui.add_photo(result_photo)
                    state = "HOMESCREEN"
                    idle_since = now
                    continue

                left    = btns.left_pressed()
                trigger = btns.trigger_pressed()
                right   = btns.right_pressed()

                if left:
                    ui.add_photo(result_photo)
                    state = "HOMESCREEN"
                    idle_since = now
                    btns.wait_for_release()

                elif trigger:  # Nochmal
                    ui.add_photo(result_photo)
                    photo = _capture_sequence(ui, camera, cfg, mode)
                    if photo:
                        result_photo = photo
                        result_since = time.monotonic()
                    else:
                        # Zurueck auf den Homescreen statt auf dem Result-Screen
                        # mit dem alten Bild stehenzubleiben: dessen Timer laeuft
                        # weiter und wuerde das Foto ein zweites Mal in die
                        # Polaroid-Galerie haengen.
                        state = "HOMESCREEN"
                        idle_since = now
                    btns.wait_for_release()

                elif right:  # Drucken
                    _do_print(ui, result_photo, cfg)
                    btns.wait_for_release()

                else:
                    ui.render_result(result_photo, time_left)

            # ── SLIDESHOW ─────────────────────────────────────────────────────
            elif state == "SLIDESHOW":
                if btns.any_pressed():
                    state = "HOMESCREEN"
                    idle_since = now
                    btns.wait_for_release()
                else:
                    ui.render_slideshow()

            clock.tick(STATE_FPS)

    except Exception as exc:
        logger.error("Unerwarteter Fehler: %s", exc, exc_info=True)
    finally:
        btns.close()
        camera.close()
        ui.close()
        if cfg.get("hotspot_enabled"):
            hotspot.stop()
        logger.info("Fotobox beendet")

    if user_quit:
        # Nach dem Aufraeumen, nicht davor: sonst bliebe der Hotspot stehen
        # und die Kamera in ihrer Sitzung.
        logger.info("Beendet auf Wunsch (Esc) — systemd startet nicht neu")
        sys.exit(EXIT_USER_QUIT)


if __name__ == "__main__":
    main()
