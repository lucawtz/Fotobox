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

        self._font_btn    = pygame.font.SysFont("sans-serif", 28, bold=True)
        self._font_count  = pygame.font.SysFont("sans-serif", 200, bold=True)
        self._font_cheese = pygame.font.SysFont("sans-serif", 110, bold=True)

        self._gallery: deque = deque(maxlen=len(polaroid_frames))
        self._cache: dict = {}       # path -> skaliertes Surface
        self._rot_cache: dict = {}   # (path, angle) -> rotiertes SRCALPHA Surface
        self._fade_start: dict = {}  # path -> ticks beim Hinzufügen
        self._FADE_MS = 1500         # Einblend-Dauer in Millisekunden

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
            scaled = self._scale_to_fill(img, self._PW, self._PH)
            self._cache[path] = scaled
            self._fade_start[path] = pygame.time.get_ticks()
            # Rotierte Surfaces vorab berechnen (einmalig pro Foto)
            for _, _, angle in self._frames:
                surf = pygame.Surface((self._PW, self._PH), pygame.SRCALPHA)
                surf.blit(scaled, (0, 0))
                self._rot_cache[(path, angle)] = pygame.transform.rotate(surf, angle)
        except Exception as exc:
            logger.warning("Foto konnte nicht geladen werden: %s", exc)

    def render(self):
        self._screen.blit(self._bg, (0, 0))
        self._draw_live()
        self._draw_polaroids()
        pygame.display.flip()

    def show_countdown(self, seconds: int, on_trigger=None):
        for i in range(seconds, 0, -1):
            if i == 3 and on_trigger:
                threading.Thread(target=on_trigger, daemon=True).start()
            deadline = pygame.time.get_ticks() + 1000
            while pygame.time.get_ticks() < deadline:
                self._draw_countdown_frame(i)
                pygame.event.pump()
                pygame.time.wait(30)
        deadline = pygame.time.get_ticks() + 1000
        while pygame.time.get_ticks() < deadline:
            self._draw_cheese_frame()
            pygame.event.pump()
            pygame.time.wait(30)
        self.render()

    def check_quit_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return True
            if event.type == pygame.KEYDOWN and event.key == pygame.K_q:
                return True
        return False

    def space_pressed(self) -> bool:
        return bool(pygame.key.get_pressed()[pygame.K_SPACE])

    def wait_for_space_release(self):
        """Wartet bis die Leertaste losgelassen wird — verhindert Doppel-Trigger."""
        while pygame.key.get_pressed()[pygame.K_SPACE]:
            pygame.event.pump()
            pygame.time.wait(30)

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
            scale = min(w / fw, h / fh)
            nw, nh = int(fw * scale), int(fh * scale)
            frame = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
            surf  = pygame.surfarray.make_surface(frame.swapaxes(0, 1))
            self._screen.blit(surf, (x + (w - nw) // 2, y + (h - nh) // 2))
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
                path, photo, alpha = None, None, 255
            self._draw_polaroid(cx, cy, angle, path, photo, alpha)

    def _photo_alpha(self, path: str) -> int:
        """Berechnet aktuellen Alpha-Wert für Fade-in (0–255)."""
        if path not in self._fade_start:
            return 255
        elapsed = pygame.time.get_ticks() - self._fade_start[path]
        return min(255, int(elapsed / self._FADE_MS * 255))

    def _draw_polaroid(self, cx: int, cy: int, angle: float,
                       path: Optional[str], photo: Optional[pygame.Surface],
                       alpha: int = 255):
        if photo is None:
            return  # Schwarzer Platzhalter aus dem Overlay bleibt sichtbar
        # Gecachte rotierte Surface verwenden (einmalig berechnet in add_photo)
        rotated = self._rot_cache.get((path, angle))
        if rotated is None:
            surf = pygame.Surface((self._PW, self._PH), pygame.SRCALPHA)
            surf.blit(photo, (0, 0))
            rotated = pygame.transform.rotate(surf, angle)
            self._rot_cache[(path, angle)] = rotated
        if alpha < 255:
            rotated = rotated.copy()
            rotated.set_alpha(alpha)
        self._screen.blit(rotated, rotated.get_rect(center=(cx, cy)))

    # ── Countdown ─────────────────────────────────────────────────────────────

    def _draw_countdown_frame(self, number: int):
        self._screen.blit(self._bg, (0, 0))
        self._draw_live()
        self._draw_polaroids()
        self._draw_label_box(
            self._font_count.render(str(number), True, (255, 255, 255)),
            pad=30,
        )
        pygame.display.flip()

    def _draw_cheese_frame(self):
        self._screen.blit(self._bg, (0, 0))
        self._draw_live()
        self._draw_polaroids()
        self._draw_label_box(
            self._font_cheese.render("Cheese!", True, (255, 230, 50)),
            pad=25,
        )
        pygame.display.flip()

    def _draw_label_box(self, lbl: pygame.Surface, pad: int):
        """Zeichnet einen halbtransparenten Kasten mit Text zentriert im Live-View."""
        lx, ly, lw, lh = self._live_rect
        bw = lbl.get_width()  + pad * 2
        bh = lbl.get_height() + pad * 2
        bx = lx + (lw - bw) // 2
        by = ly + (lh - bh) // 2
        box = pygame.Surface((bw, bh), pygame.SRCALPHA)
        box.fill((0, 0, 0, 180))
        self._screen.blit(box, (bx, by))
        self._screen.blit(lbl, (bx + pad, by + pad))

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
