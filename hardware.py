import logging
import time

import pygame

logger = logging.getLogger(__name__)


class Buttons:
    """Bis zu 3 GPIO-Taster (left, trigger, right) mit Tastatur-Fallback.

    Tasten: Q = links, Space = auslösen, E = rechts
    GPIO:   Pin 17 = links, Pin 27 = auslösen, Pin 22 = rechts

    Ein Pin darf None sein — dann ist dieser Taster schlicht nicht verbaut.
    `wired` sagt, welche es gibt; die UI zeigt danach nur Aktionen an, die
    auch erreichbar sind. Ohne GPIO (Dev-Maschine) gelten alle drei als
    vorhanden, dort ist die Tastatur die Bedienung.
    """

    NAMES = ("left", "trigger", "right")

    def __init__(self, pin_left, pin_trigger, pin_right):
        self._left_btn = None
        self._trigger_btn = None
        self._right_btn = None
        # Ob echte Taster da sind. Die UI blendet danach die Tastenkuerzel
        # ein oder aus: am Gast-Screen sind "[ Q ]" und "[ Space ]" sinnlos,
        # weil an der Box keine Tastatur haengt.
        self.has_gpio = False
        pins = dict(zip(self.NAMES, (pin_left, pin_trigger, pin_right)))
        try:
            from gpiozero import Button
            made = {}
            for name, pin in pins.items():
                if pin is None:
                    continue
                made[name] = Button(pin, pull_up=True, bounce_time=0.1)
            if not made:
                raise RuntimeError("kein Pin konfiguriert")
            self._left_btn    = made.get("left")
            self._trigger_btn = made.get("trigger")
            self._right_btn   = made.get("right")
            self.has_gpio = True
            logger.info("Taster: %s", "  ".join(
                f"{n}=GPIO{pins[n]}" for n in self.NAMES if n in made))
            missing = [n for n in self.NAMES if n not in made]
            if missing:
                logger.info("Nicht verbaut: %s — die UI blendet die "
                            "zugehoerigen Aktionen aus", ", ".join(missing))
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

    def wired(self, name: str) -> bool:
        """Ist dieser Taster erreichbar? Ohne GPIO zaehlt die Tastatur."""
        if not self.has_gpio:
            return True
        return getattr(self, f"_{name}_btn") is not None

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
