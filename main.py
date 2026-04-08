import logging
import signal
import sys

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
        camera = Camera()
        ui = UI(config.SCREEN_SIZE, config.LAYOUT_PATH)

        logger.info("Fotobox bereit — warte auf Knopfdruck")

        while running:
            if ui.check_quit_events():
                break

            if button.is_pressed():
                logger.info("Knopfdruck erkannt — starte Countdown")
                ui.show_countdown(config.COUNTDOWN_SECONDS)
                path = camera.capture(config.PICTURE_PATH)
                logger.info("Foto gespeichert: %s", path)
                # Warten bis Knopf losgelassen, damit kein Doppel-Auslöser
                button.wait_for_release()

            ui.show_overlay()

    except FileNotFoundError as exc:
        logger.error("Datei nicht gefunden: %s", exc)
        sys.exit(1)
    except Exception as exc:
        logger.error("Unerwarteter Fehler: %s", exc, exc_info=True)
        sys.exit(1)
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
