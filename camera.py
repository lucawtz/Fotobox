import logging
import os
import time
from picamera2 import Picamera2

logger = logging.getLogger(__name__)


class Camera:
    def __init__(self):
        self._cam = Picamera2()
        config = self._cam.create_still_configuration()
        self._cam.configure(config)
        self._cam.start()
        logger.info("Kamera initialisiert")

    def capture(self, directory: str) -> str:
        os.makedirs(directory, exist_ok=True)
        timestamp = int(time.time())
        path = os.path.join(directory, f"foto_{timestamp}.jpg")
        self._cam.capture_file(path)
        logger.info("Foto gespeichert: %s", path)
        return path

    def close(self):
        self._cam.stop()
        self._cam.close()
