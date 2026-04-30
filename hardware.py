import logging
import time

import pygame

logger = logging.getLogger(__name__)


class Buttons:
    """3 GPIO-Buttons (left, trigger, right) mit Tastatur-Fallback.

    Tasten: Q = links, Space = auslösen, E = rechts
    GPIO:   Pin 17 = links, Pin 27 = auslösen, Pin 22 = rechts
    """

    def __init__(self, pin_left: int, pin_trigger: int, pin_right: int):
        self._left_btn = None
        self._trigger_btn = None
        self._right_btn = None
        try:
            from gpiozero import Button
            self._left_btn    = Button(pin_left,    pull_up=True, bounce_time=0.1)
            self._trigger_btn = Button(pin_trigger, pull_up=True, bounce_time=0.1)
            self._right_btn   = Button(pin_right,   pull_up=True, bounce_time=0.1)
            logger.info("Buttons: left=GPIO%d  trigger=GPIO%d  right=GPIO%d",
                        pin_left, pin_trigger, pin_right)
        except Exception as exc:
            logger.warning("GPIO-Buttons nicht verfügbar (%s) — nur Tastatur (Q/Space/E)", exc)

    def left_pressed(self) -> bool:
        hw = bool(self._left_btn and self._left_btn.is_pressed)
        kb = bool(pygame.key.get_pressed()[pygame.K_q])
        return hw or kb

    def trigger_pressed(self) -> bool:
        hw = bool(self._trigger_btn and self._trigger_btn.is_pressed)
        kb = bool(pygame.key.get_pressed()[pygame.K_SPACE])
        return hw or kb

    def right_pressed(self) -> bool:
        hw = bool(self._right_btn and self._right_btn.is_pressed)
        kb = bool(pygame.key.get_pressed()[pygame.K_e])
        return hw or kb

    def any_pressed(self) -> bool:
        return self.left_pressed() or self.trigger_pressed() or self.right_pressed()

    def wait_for_release(self, timeout: float = 5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            pygame.event.pump()
            if not self.any_pressed():
                return
            pygame.time.wait(30)

    def close(self):
        for btn in (self._left_btn, self._trigger_btn, self._right_btn):
            if btn:
                try:
                    btn.close()
                except Exception:
                    pass
