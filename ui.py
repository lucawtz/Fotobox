import logging
import threading
from collections import deque
from typing import List, Optional, Tuple

import cv2
import pygame

logger = logging.getLogger(__name__)

W, H = 1920, 1080

TEXT_DIM = (155, 120, 65)


class _LiveReader:
    """Liest Capture-Card-Frames in einem Hintergrund-Thread."""

    def __init__(self, device: int):
        self._cap = cv2.VideoCapture(device)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not self._cap.isOpened():
            raise RuntimeError(f"Capture-Device {device} konnte nicht geöffnet werden.")
        self._frame = None
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

    def latest(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def close(self):
        self._running = False
        self._cap.release()


class UI:

    def __init__(
        self,
        capture_device: int,
        polaroid_frames: List[Tuple[int, int, int]],
        live_rect: Tuple[int, int, int, int],
        overlay_path: Optional[str] = None,
        photo_size: Tuple[int, int] = (295, 290),
    ):
        pygame.init()
        self._screen = pygame.display.set_mode((W, H), pygame.FULLSCREEN)
        pygame.display.set_caption("Fotobox")
        pygame.mouse.set_visible(False)

        self._frames    = polaroid_frames
        self._live_rect = live_rect
        self._PW, self._PH = photo_size

        self._font_btn   = pygame.font.SysFont("sans-serif", 28, bold=True)
        self._font_count = pygame.font.SysFont("sans-serif", 200, bold=True)

        self._gallery: deque = deque(maxlen=len(polaroid_frames))
        self._cache: dict = {}
        self._fade_start: dict = {}   # path -> ticks beim Hinzufügen
        self._FADE_MS = 1500          # Einblend-Dauer in Millisekunden

        if overlay_path:
            logger.info("Lade Overlay: %s", overlay_path)
            self._bg = self._load_overlay(overlay_path)
        else:
            self._bg = pygame.Surface((W, H))
            self._bg.fill((40, 25, 10))
            logger.warning("Kein Overlay angegeben — dunkler Hintergrund")

        logger.info("UI initialisiert")
        self._live = _LiveReader(capture_device)

    # ── Öffentliche API ────────────────────────────────────────────────────────

    def add_photo(self, path: str):
        self._gallery.append(path)
        try:
            img = pygame.image.load(path).convert()
            self._cache[path] = self._scale_to_fill(img, self._PW, self._PH)
            self._fade_start[path] = pygame.time.get_ticks()
        except Exception as exc:
            logger.warning("Foto konnte nicht geladen werden: %s", exc)

    def render(self):
        self._screen.blit(self._bg, (0, 0))
        self._draw_live()
        self._draw_polaroids()
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
        return bool(pygame.key.get_pressed()[pygame.K_SPACE])

    def close(self):
        self._live.close()
        pygame.quit()

    # ── Overlay laden ──────────────────────────────────────────────────────────

    @staticmethod
    def _load_overlay(path: str) -> pygame.Surface:
        img = pygame.image.load(path).convert()
        iw, ih = img.get_size()
        if (iw, ih) != (W, H):
            img = pygame.transform.scale(img, (W, H))
        return img

    # ── Live-View ──────────────────────────────────────────────────────────────

    def _draw_live(self):
        x, y, w, h = self._live_rect
        frame = self._live.latest()
        if frame is not None:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            fh, fw = frame.shape[:2]
            # Fill: skalieren bis Breite/Höhe voll ausgenutzt, dann mittig zuschneiden
            scale = max(w / fw, h / fh)
            nw, nh = int(fw * scale), int(fh * scale)
            frame = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
            # Zuschnitt auf Rect-Größe
            cx = (nw - w) // 2
            cy = (nh - h) // 2
            frame = frame[cy:cy + h, cx:cx + w]
            surf  = pygame.surfarray.make_surface(frame.swapaxes(0, 1))
            self._screen.blit(surf, (x, y))
        else:
            # Kein draw.rect — schwarzer Kasten kommt aus dem Overlay
            lbl = self._font_btn.render("Warte auf Kamera…", True, TEXT_DIM)
            self._screen.blit(lbl, (x + w // 2 - lbl.get_width() // 2,
                                    y + h // 2 - lbl.get_height() // 2))

    # ── Polaroid-Fotos ─────────────────────────────────────────────────────────

    def _draw_polaroids(self):
        photos = list(self._gallery)
        for i, (cx, cy, angle) in enumerate(self._frames):
            if i < len(photos):
                path  = photos[i]
                photo = self._cache.get(path)
                alpha = self._photo_alpha(path)
            else:
                photo, alpha = None, 255
            self._draw_polaroid(cx, cy, angle, photo, alpha)

    def _photo_alpha(self, path: str) -> int:
        """Berechnet aktuellen Alpha-Wert für Fade-in (0–255)."""
        if path not in self._fade_start:
            return 255
        elapsed = pygame.time.get_ticks() - self._fade_start[path]
        return min(255, int(elapsed / self._FADE_MS * 255))

    def _draw_polaroid(self, cx: int, cy: int, angle: float,
                       photo: Optional[pygame.Surface], alpha: int = 255):
        if photo is None:
            return  # Schwarzer Platzhalter aus dem Overlay bleibt sichtbar
        # SRCALPHA: Rotations-Ecken transparent + Fade-in über alpha
        surf = pygame.Surface((self._PW, self._PH), pygame.SRCALPHA)
        surf.blit(photo, (0, 0))
        surf.set_alpha(alpha)
        rotated = pygame.transform.rotate(surf, angle)
        self._screen.blit(rotated, rotated.get_rect(center=(cx, cy)))

    # ── Countdown ─────────────────────────────────────────────────────────────

    def _draw_countdown_frame(self, number: int):
        self._screen.blit(self._bg, (0, 0))
        self._draw_live()
        self._draw_polaroids()
        lx, ly, lw, lh = self._live_rect
        dim = pygame.Surface((lw, lh), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 165))
        self._screen.blit(dim, (lx, ly))
        lbl = self._font_count.render(str(number), True, (255, 255, 255))
        self._screen.blit(lbl, (lx + lw // 2 - lbl.get_width() // 2,
                                ly + lh // 2 - lbl.get_height() // 2))
        pygame.display.flip()

    # ── Hilfsmethoden ─────────────────────────────────────────────────────────

    @staticmethod
    def _scale_to_fill(surf: pygame.Surface, w: int, h: int) -> pygame.Surface:
        sw, sh = surf.get_size()
        scale  = max(w / sw, h / sh)
        nw, nh = int(sw * scale), int(sh * scale)
        scaled = pygame.transform.smoothscale(surf, (nw, nh))
        x = (nw - w) // 2
        y = (nh - h) // 2
        return scaled.subsurface(pygame.Rect(x, y, w, h)).copy()
