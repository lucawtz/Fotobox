import logging
import signal
import sys
import threading

import config
from camera import Camera
from hardware import PhotoButton
from ui import UI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    button: PhotoButton | None = None
    camera: Camera | None = None
    ui: UI | None = None
    running = True

    def shutdown(signum=None, frame=None):
        nonlocal running
        logger.info("Shutdown-Signal empfangen — beende Fotobox")
        running = False

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    try:
        button = PhotoButton(config.BUTTON_PIN)
    except Exception as exc:
        logger.warning("GPIO-Button nicht verfügbar (%s) — nur Leertaste", exc)

    try:
        camera = Camera()
    except Exception as exc:
        logger.warning("Kamera nicht verfügbar (%s) — Foto-Aufnahme deaktiviert", exc)

    try:
        ui = UI(
            config.CAPTURE_DEVICE,
            config.POLAROID_FRAMES,
            config.LIVE_VIEW_RECT,
            config.OVERLAY_PATH,
            config.POLAROID_PHOTO_SIZE,
        )
    except Exception as exc:
        logger.error("UI konnte nicht gestartet werden: %s", exc)
        sys.exit(1)

    logger.info("Fotobox bereit — Knopf oder Leertaste zum Auslösen")

    try:
        while running:
            if ui.check_quit_events():
                break

            triggered = ui.space_pressed()
            if button and button.is_pressed():
                triggered = True

            if triggered:
                logger.info("Auslöser — starte Countdown")
                capture_result: dict = {"path": None}
                done = threading.Event()

                def _capture():
                    try:
                        capture_result["path"] = camera.capture(config.PICTURE_PATH)
                    except Exception as exc:
                        logger.error("Aufnahme fehlgeschlagen: %s", exc)
                    finally:
                        done.set()

                ui.show_countdown(
                    config.COUNTDOWN_SECONDS,
                    on_trigger=_capture if camera else None,
                )
                if camera:
                    done.wait()
                    if capture_result["path"]:
                        ui.add_photo(capture_result["path"])
                else:
                    logger.info("Kein Foto — Kamera nicht verbunden")
                if button:
                    button.wait_for_release()
                ui.wait_for_space_release()

            ui.render()

    except Exception as exc:
        logger.error("Unerwarteter Fehler: %s", exc, exc_info=True)
    finally:
        if button:
            button.close()
        if camera:
            camera.close()
        if ui:
            ui.close()
        logger.info("Fotobox beendet")


if __name__ == "__main__":
    main()
