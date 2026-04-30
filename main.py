import argparse
import logging
import os
import signal
import subprocess
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


# ── Capture-Helfer ─────────────────────────────────────────────────────────────

def _do_countdown(ui: UI, camera: Camera, cfg: dict,
                  photo_num: int, total: int) -> Optional[str]:
    result: dict = {"path": None}
    done = threading.Event()

    def _capture():
        try:
            result["path"] = camera.capture(events.current_event_dir(cfg))
        except Exception as exc:
            logger.error("Capture fehlgeschlagen: %s", exc)
        finally:
            done.set()

    ui.run_countdown(
        on_capture=_capture,
        seconds=cfg["countdown_duration"],
        photo_num=photo_num,
        total=total,
    )
    done.wait(timeout=35)
    return result["path"]


def _do_print(path: str):
    try:
        subprocess.Popen(["lp", path])
        logger.info("Druckauftrag: %s", path)
    except FileNotFoundError:
        logger.warning("lp nicht verfügbar — Drucken übersprungen")
    except Exception as exc:
        logger.error("Druckfehler: %s", exc)


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

    def __init__(self, picture_dir: str):
        self._picture_dir = picture_dir
        self._last = 0.0
        self.free_mb = 0
        self.photo_count = 0

    def maybe_refresh(self, now_monotonic: float):
        if now_monotonic - self._last < self.REFRESH_S:
            return
        self._last = now_monotonic
        self.free_mb = disk_monitor.get_free_mb(config.BASE_DIR)
        self.photo_count = _count_photos(self._picture_dir)


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
    return p.parse_args()


def main():
    args = _parse_args()
    _setup_logging()
    cfg = config.cfg

    running = True

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
    if cfg.get("hotspot_enabled") and not args.no_hotspot:
        try:
            hotspot.start()
        except Exception as exc:
            logger.warning("Hotspot-Start fehlgeschlagen: %s", exc)
    elif args.no_hotspot:
        logger.info("Hotspot per --no-hotspot übersprungen — Heim-WLAN bleibt aktiv")

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

    # Kamera (Watchdog im Hintergrund)
    camera = Camera(
        keepalive_s=cfg.get("camera_keepalive_s", 25),
        output_mode=str(cfg.get("camera_output_mode", "3")),
    )

    # Buttons (GPIO + Tastatur-Fallback)
    pins = cfg.get("gpio_pins", {})
    btns = Buttons(
        pin_left    = pins.get("left",    17),
        pin_trigger = pins.get("trigger", 27),
        pin_right   = pins.get("right",   22),
    )

    # UI
    try:
        ui = UI(cfg, cfg.get("capture_device", 0))
    except Exception as exc:
        logger.error("UI konnte nicht gestartet werden: %s", exc)
        camera.close()
        btns.close()
        sys.exit(1)

    logger.info("Fotobox bereit. Space=Einzelfoto  E=Collage  "
                "Q=Wake-Camera/Zurück  Esc=Beenden")

    # ── State-Machine ──────────────────────────────────────────────────────────
    state           = "HOMESCREEN"
    mode            = "single"
    result_photo: Optional[str] = None
    result_since    = 0.0
    idle_since      = time.monotonic()
    clock           = pygame.time.Clock()
    status_cache    = _StatusCache(cfg["picture_dir"])

    try:
        while running:
            if ui.check_quit():
                break

            now = time.monotonic()
            status_cache.maybe_refresh(now)
            free_mb   = status_cache.free_mb
            photo_cnt = status_cache.photo_count

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

                # Linker Knopf (Q) auf dem Homescreen = Kamera-Display aufwecken.
                # Async ausführen damit die UI nicht 8-18 s blockiert während
                # gphoto2 läuft.
                if left and not (trigger or right):
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
                    disk_monitor.enforce_max_photos(
                        cfg["picture_dir"],
                        cfg.get("max_photos", 500),
                        event_dir=events.current_event_dir(cfg))

                    if not camera.available:
                        logger.warning("Auslöser ignoriert: %s", camera.error_message)
                        btns.wait_for_release()
                    elif mode == "single":
                        # Kein Auto-Wake — Live-View muss manuell per Camera-Knopf
                        # oder Q auf der Fotobox aktiviert werden, sonst killt der
                        # capture-preview-Pull eine eventuell laufende manuelle LV.
                        photo = _do_countdown(ui, camera, cfg, 1, 1)
                        if photo:
                            result_photo = photo
                            result_since = time.monotonic()
                            state = "RESULT"
                        btns.wait_for_release()
                    else:  # collage
                        shots: list[str] = []
                        for i in range(4):
                            photo = _do_countdown(ui, camera, cfg, i + 1, 4)
                            if photo:
                                shots.append(photo)
                            else:
                                break
                        if len(shots) == 4:
                            result_photo = collage_mod.make_collage(
                                shots, events.current_event_dir(cfg))
                            result_since = time.monotonic()
                            state = "RESULT"
                        else:
                            # Abgebrochene Collage: angefangene Einzelfotos
                            # nicht in der Galerie liegen lassen
                            _cleanup_orphans(shots)
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
                    if mode == "single":
                        photo = _do_countdown(ui, camera, cfg, 1, 1)
                        if photo:
                            result_photo = photo
                            result_since = time.monotonic()
                    else:
                        shots = []
                        for i in range(4):
                            photo = _do_countdown(ui, camera, cfg, i + 1, 4)
                            if photo:
                                shots.append(photo)
                            else:
                                break
                        if len(shots) == 4:
                            result_photo = collage_mod.make_collage(
                                shots, events.current_event_dir(cfg))
                            result_since = time.monotonic()
                        else:
                            _cleanup_orphans(shots)
                            state = "HOMESCREEN"
                            idle_since = now
                    btns.wait_for_release()

                elif right:  # Drucken
                    _do_print(result_photo)
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

            clock.tick(30)

    except Exception as exc:
        logger.error("Unerwarteter Fehler: %s", exc, exc_info=True)
    finally:
        btns.close()
        camera.close()
        ui.close()
        if cfg.get("hotspot_enabled"):
            hotspot.stop()
        logger.info("Fotobox beendet")


if __name__ == "__main__":
    main()
