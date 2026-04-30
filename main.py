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
import gallery_server
import hotspot
from camera import Camera
from hardware import Buttons
from ui import UI

# ── Logging ────────────────────────────────────────────────────────────────────

def _setup_logging():
    log_dir = os.path.join(config.BASE_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(log_dir, "fotobox.log")),
    ]
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)


logger = logging.getLogger(__name__)


# ── Capture-Helfer ─────────────────────────────────────────────────────────────

def _do_countdown(ui: UI, camera: Camera, cfg: dict,
                  photo_num: int, total: int) -> Optional[str]:
    result: dict = {"path": None}
    done = threading.Event()

    def _capture():
        try:
            result["path"] = camera.capture(cfg["picture_dir"])
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
    exts = {".jpg", ".jpeg", ".png"}
    try:
        return sum(1 for f in os.listdir(picture_dir)
                   if os.path.splitext(f)[1].lower() in exts)
    except FileNotFoundError:
        return 0


# ── Haupt-Funktion ─────────────────────────────────────────────────────────────

def main():
    _setup_logging()
    cfg = config.cfg

    running = True

    def shutdown(signum=None, frame=None):
        nonlocal running
        logger.info("Shutdown-Signal empfangen")
        running = False

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT,  shutdown)

    # Ordner anlegen
    os.makedirs(cfg["picture_dir"],   exist_ok=True)
    os.makedirs(cfg["thumbnail_dir"], exist_ok=True)

    # Hotspot — defensiv: darf die App-Initialisierung niemals blockieren
    if cfg.get("hotspot_enabled"):
        try:
            hotspot.start()
        except Exception as exc:
            logger.warning("Hotspot-Start fehlgeschlagen: %s", exc)

    # Galerie-Server (Daemon-Thread)
    threading.Thread(target=gallery_server.run, daemon=True).start()
    logger.info("Galerie: %s", cfg["gallery_url"])

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

    logger.info("Fotobox bereit. Space=Einzelfoto  E=Collage  Q=Zurück  Esc=Beenden")

    # ── State-Machine ──────────────────────────────────────────────────────────
    state           = "HOMESCREEN"
    mode            = "single"
    result_photo: Optional[str] = None
    result_since    = 0.0
    idle_since      = time.monotonic()
    clock           = pygame.time.Clock()

    try:
        while running:
            if ui.check_quit():
                break

            now       = time.monotonic()
            free_mb   = disk_monitor.get_free_mb(config.BASE_DIR)
            photo_cnt = _count_photos(cfg["picture_dir"])

            # ── HOMESCREEN ────────────────────────────────────────────────────
            if state == "HOMESCREEN":
                idle_timeout = cfg.get("idle_timeout", 0)
                if idle_timeout > 0 and now - idle_since >= idle_timeout:
                    ui.refresh_slideshow(cfg["picture_dir"])
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

                    # Disk-Wartung vor Aufnahme
                    disk_monitor.cleanup_old_thumbnails(
                        cfg["thumbnail_dir"],
                        cfg.get("thumbnail_max_age_days", 30))
                    disk_monitor.enforce_max_photos(
                        cfg["picture_dir"],
                        cfg.get("max_photos", 500))

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
                                shots, cfg["picture_dir"])
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
                                shots, cfg["picture_dir"])
                            result_since = time.monotonic()
                        else:
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
        logger.info("Fotobox beendet")


if __name__ == "__main__":
    main()
