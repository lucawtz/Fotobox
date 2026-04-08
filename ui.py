import logging
from typing import Tuple
import pygame

logger = logging.getLogger(__name__)


class UI:
    def __init__(self, screen_size: Tuple[int, int], layout_path: str):
        pygame.init()
        self._screen = pygame.display.set_mode(screen_size, pygame.FULLSCREEN)
        pygame.display.set_caption("Fotobox")
        self._center = (screen_size[0] // 2, screen_size[1] // 2)

        try:
            self._overlay = pygame.image.load(layout_path).convert_alpha()
        except FileNotFoundError:
            logger.error("Overlay nicht gefunden: %s", layout_path)
            raise

        # Font einmalig laden, nicht in jeder Schleife neu erstellen
        self._font = pygame.font.Font(None, 200)
        logger.info("UI initialisiert")

    def show_overlay(self):
        self._screen.fill((0, 0, 0))
        self._screen.blit(self._overlay, (0, 0))
        pygame.display.flip()

    def show_countdown(self, seconds: int):
        for i in range(seconds, 0, -1):
            self._screen.fill((0, 0, 0))
            self._screen.blit(self._overlay, (0, 0))
            text = self._font.render(str(i), True, (255, 255, 255))
            text_rect = text.get_rect(center=self._center)
            self._screen.blit(text, text_rect)
            pygame.display.flip()

            # 1 Sekunde warten, Event-Loop dabei am Leben halten
            deadline = pygame.time.get_ticks() + 1000
            while pygame.time.get_ticks() < deadline:
                pygame.event.pump()
                pygame.time.wait(30)

    def check_quit_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return True
            if event.type == pygame.KEYDOWN and event.key == pygame.K_q:
                return True
        return False

    def close(self):
        pygame.quit()
