import logging
import threading
from collections import deque
from typing import Optional

import cv2
import numpy as np
import pygame

logger = logging.getLogger(__name__)

# ── Layout-Konstanten ──────────────────────────────────────────────────────────
W, H         = 1920, 1080
HEADER_H     = 60
GALLERY_H    = 320
LIVE_H       = H - HEADER_H - GALLERY_H   # 700
SLOT_W       = W // 3                      # 640

# ── Farben ─────────────────────────────────────────────────────────────────────
C_BG         = (10,  10,  15)
C_HEADER     = (20,  20,  40)
C_SLOT_EMPTY = (30,  30,  50)
C_ACCENT     = (220, 50,  80)
C_TEXT       = (255, 255, 255)
C_TEXT_DIM   = (140, 140, 160)


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
    def __init__(self, capture_device: int):
        pygame.init()
        self._screen = pygame.display.set_mode((W, H), pygame.FULLSCREEN)
        pygame.display.set_caption("Fotobox")
        pygame.mouse.set_visible(False)

        self._font_title = pygame.font.SysFont("sans-serif", 32, bold=True)
        self._font_count = pygame.font.SysFont("sans-serif", 260, bold=True)
        self._font_empty = pygame.font.SysFont("sans-serif", 22)

        # Letzte 3 Fotos (Pfad → gecachte Surface)
        self._gallery: deque = deque(maxlen=3)
        self._cache: dict = {}

        self._live = _LiveReader(capture_device)
        logger.info("UI initialisiert")

    # ── Öffentliche API ────────────────────────────────────────────────────────

    def add_photo(self, path: str):
        """Foto zur Galerie hinzufügen und Surface cachen."""
        self._gallery.append(path)
        try:
            img = pygame.image.load(path).convert()
            self._cache[path] = pygame.transform.smoothscale(img, (SLOT_W, GALLERY_H))
        except Exception as exc:
            logger.warning("Foto konnte nicht geladen werden (%s): %s", path, exc)

    def render(self):
        """Einen Frame zeichnen."""
        self._screen.fill(C_BG)
        self._draw_header()
        self._draw_gallery()
        self._draw_live()
        pygame.display.flip()

    def show_countdown(self, seconds: int):
        """Countdown über Live-View anzeigen — Live-View läuft weiter."""
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
        """Leertaste als Button-Ersatz für Tests ohne Hardware."""
        keys = pygame.key.get_pressed()
        return bool(keys[pygame.K_SPACE])

    def close(self):
        self._live.close()
        pygame.quit()

    # ── Zeichen-Helfer ─────────────────────────────────────────────────────────

    def _draw_header(self):
        pygame.draw.rect(self._screen, C_HEADER, (0, 0, W, HEADER_H))
        pygame.draw.rect(self._screen, C_ACCENT, (0, HEADER_H - 3, W, 3))
        lbl = self._font_title.render("FOTOBOX", True, C_TEXT)
        self._screen.blit(lbl, (W // 2 - lbl.get_width() // 2,
                                HEADER_H // 2 - lbl.get_height() // 2))

    def _draw_gallery(self):
        photos = list(self._gallery)
        for i in range(3):
            x, y = i * SLOT_W, HEADER_H
            slot = pygame.Rect(x, y, SLOT_W, GALLERY_H)
            if i < len(photos):
                surf = self._cache.get(photos[i])
                if surf:
                    self._screen.blit(surf, (x, y))
            else:
                pygame.draw.rect(self._screen, C_SLOT_EMPTY, slot)
                lbl = self._font_empty.render("Kein Foto", True, C_TEXT_DIM)
                self._screen.blit(lbl, (x + SLOT_W // 2 - lbl.get_width() // 2,
                                        y + GALLERY_H // 2 - lbl.get_height() // 2))
            # Trennlinie zwischen Slots
            pygame.draw.rect(self._screen, C_BG, slot, 2)

    def _draw_live(self):
        y0 = HEADER_H + GALLERY_H
        frame = self._live.latest()
        if frame is not None:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            fh, fw = frame.shape[:2]
            scale = min(W / fw, LIVE_H / fh)
            nw, nh = int(fw * scale), int(fh * scale)
            frame = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
            surf = pygame.surfarray.make_surface(frame.swapaxes(0, 1))
            # Zentriert im Live-Bereich
            self._screen.blit(surf, ((W - nw) // 2, y0 + (LIVE_H - nh) // 2))
        else:
            pygame.draw.rect(self._screen, C_SLOT_EMPTY, (0, y0, W, LIVE_H))
            lbl = self._font_title.render("Warte auf Kamera...", True, C_TEXT_DIM)
            self._screen.blit(lbl, (W // 2 - lbl.get_width() // 2,
                                    y0 + LIVE_H // 2 - lbl.get_height() // 2))

    def _draw_countdown_frame(self, number: int):
        """Live-View + abgedunkeltes Overlay + Countdown-Zahl."""
        self._screen.fill(C_BG)
        self._draw_header()
        self._draw_gallery()
        self._draw_live()
        # Abdunkeln
        dim = pygame.Surface((W, H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 160))
        self._screen.blit(dim, (0, 0))
        # Zahl
        lbl = self._font_count.render(str(number), True, C_TEXT)
        self._screen.blit(lbl, (W // 2 - lbl.get_width() // 2,
                                H // 2 - lbl.get_height() // 2))
        pygame.display.flip()
