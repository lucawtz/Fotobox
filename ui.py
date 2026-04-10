import logging
import threading
from collections import deque
from typing import Optional, List, Tuple

import cv2
import numpy as np
import pygame

logger = logging.getLogger(__name__)

W, H = 1920, 1080


class _LiveReader:
    """Liest Capture-Card-Frames in einem Hintergrund-Thread."""

    def __init__(self, device: int):
        self._cap = cv2.VideoCapture(device)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not self._cap.isOpened():
            raise RuntimeError(f"Capture-Device {device} konnte nicht geöffnet werden.")
        self._frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()
        logger.info("LiveReader gestartet (device=%d)", device)

    def _loop(self):
        while self._running:
            ok, frame = self._cap.read()
            if ok:
                with self._lock:
                    self._frame = frame

    def latest(self) -> Optional[np.ndarray]:
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def close(self):
        self._running = False
        self._cap.release()


class UI:
    def __init__(
        self,
        capture_device: int,
        overlay_path: str,
        photo_slots: List[Tuple[int, int, int, int]],
        live_rect: Tuple[int, int, int, int],
    ):
        pygame.init()
        self._screen = pygame.display.set_mode((W, H), pygame.FULLSCREEN)
        pygame.display.set_caption("Fotobox")
        pygame.mouse.set_visible(False)

        try:
            img = pygame.image.load(overlay_path).convert_alpha()
            self._overlay = pygame.transform.smoothscale(img, (W, H))
        except FileNotFoundError:
            logger.error("Overlay nicht gefunden: %s", overlay_path)
            raise

        self._photo_slots = photo_slots
        self._live_rect = live_rect

        self._font_count = pygame.font.SysFont("sans-serif", 260, bold=True)

        self._gallery: deque = deque(maxlen=len(photo_slots))
        self._cache: dict = {}

        self._live = _LiveReader(capture_device)
        logger.info("UI initialisiert")

    # ── Öffentliche API ────────────────────────────────────────────────────────

    def add_photo(self, path: str):
        self._gallery.append(path)
        try:
            img = pygame.image.load(path).convert()
            # Auf Slot-Größe skalieren (erster Slot als Referenz)
            sw, sh = self._photo_slots[0][2], self._photo_slots[0][3]
            self._cache[path] = self._scale_to_fill(img, sw, sh)
        except Exception as exc:
            logger.warning("Foto konnte nicht geladen werden: %s", exc)

    def render(self):
        self._screen.fill((0, 0, 0))
        self._screen.blit(self._overlay, (0, 0))   # Overlay als Hintergrund
        self._draw_live()                            # Live-View in schwarzen Bereich
        self._draw_photos()                          # Fotos in Polaroid-Slots
        pygame.display.flip()

    def show_countdown(self, seconds: int):
        for i in range(seconds, 0, -1):
            deadline = pygame.time.get_ticks() + 1000
            while pygame.time.get_ticks() < deadline:
                self._draw_countdown_frame(i)
                pygame.event.pump()
                pygame.time.wait(30)

    def check_quit_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return True
            if event.type == pygame.KEYDOWN and event.key == pygame.K_q:
                return True
        return False

    def space_pressed(self) -> bool:
        keys = pygame.key.get_pressed()
        return bool(keys[pygame.K_SPACE])

    def close(self):
        self._live.close()
        pygame.quit()

    # ── Zeichen-Helfer ─────────────────────────────────────────────────────────

    def _draw_live(self):
        x, y, w, h = self._live_rect
        frame = self._live.latest()
        if frame is not None:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            fh, fw = frame.shape[:2]
            scale = min(w / fw, h / fh)
            nw, nh = int(fw * scale), int(fh * scale)
            frame = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
            surf = pygame.surfarray.make_surface(frame.swapaxes(0, 1))
            self._screen.blit(surf, (x + (w - nw) // 2, y + (h - nh) // 2))

    def _draw_photos(self):
        photos = list(self._gallery)
        for i, (sx, sy, sw, sh) in enumerate(self._photo_slots):
            if i < len(photos):
                surf = self._cache.get(photos[i])
                if surf:
                    # Auf aktuellen Slot skalieren
                    scaled = pygame.transform.smoothscale(surf, (sw, sh))
                    self._screen.blit(scaled, (sx, sy))

    def _draw_countdown_frame(self, number: int):
        self._screen.fill((0, 0, 0))
        self._screen.blit(self._overlay, (0, 0))
        self._draw_live()
        self._draw_photos()
        # Abdunkeln
        dim = pygame.Surface((W, H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 160))
        self._screen.blit(dim, (0, 0))
        # Countdown-Zahl
        lbl = self._font_count.render(str(number), True, (255, 255, 255))
        self._screen.blit(lbl, (W // 2 - lbl.get_width() // 2,
                                H // 2 - lbl.get_height() // 2))
        pygame.display.flip()

    @staticmethod
    def _scale_to_fill(surf: pygame.Surface, w: int, h: int) -> pygame.Surface:
        """Skaliert und beschneidet auf exakte Größe (kein Letterboxing)."""
        sw, sh = surf.get_size()
        scale = max(w / sw, h / sh)
        nw, nh = int(sw * scale), int(sh * scale)
        scaled = pygame.transform.smoothscale(surf, (nw, nh))
        # Mitte ausschneiden
        x = (nw - w) // 2
        y = (nh - h) // 2
        return scaled.subsurface(pygame.Rect(x, y, w, h)).copy()
