import logging
from gpiozero import Button

logger = logging.getLogger(__name__)


class PhotoButton:
    def __init__(self, pin: int):
        self._button = Button(pin, pull_up=True, bounce_time=0.1)
        logger.info("Button initialisiert auf GPIO-Pin %d", pin)

    def is_pressed(self) -> bool:
        return self._button.is_pressed

    def wait_for_release(self, timeout: float = 5.0):
        self._button.wait_for_release(timeout=timeout)

    def close(self):
        self._button.close()
