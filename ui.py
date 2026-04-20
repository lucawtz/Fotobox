import logging
import math
import glob as _glob
import os
import threading
from collections import deque
from typing import List, Optional, Tuple

import cv2
import numpy as np
import pygame

import config

logger = logging.getLogger(__name__)

W, H = 1920, 1080

TEXT_DIM    = (155, 120,  65)
CARD_BG     = ( 60,  45,  25)
CARD_SEL    = (255, 255, 255)
CARD_BORDER = (120,  90,  60)

MODES = ["Polaroids", "Fotostreifen", "Collage"]


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

        self._font_btn    = pygame.font.SysFont("sans-serif",  28, bold=True)
        self._font_count  = pygame.font.SysFont("sans-serif", 200, bold=True)
        self._font_cheese = pygame.font.SysFont("sans-serif", 110, bold=True)
        self._font_idle   = pygame.font.SysFont("sans-serif",  52, bold=True)
        self._font_mode   = pygame.font.SysFont("sans-serif",  42, bold=True)

        self._gallery: deque = deque(maxlen=len(polaroid_frames))
        self._cache: dict = {}
        self._rot_cache: dict = {}
        self._fade_start: dict = {}
        self._FADE_MS = 1500

        if overlay_path:
            logger.info("Lade Overlay: %s", overlay_path)
            self._bg = self._load_overlay(overlay_path)
        else:
            self._bg = pygame.Surface((W, H))
            self._bg.fill((40, 25, 10))
            logger.warning("Kein Overlay angegeben — dunkler Hintergrund")

        # Sounds
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            self._snd_beep    = self._make_sound(880, 0.08)
            self._snd_shutter = self._make_sound(220, 0.18)
            self._sound_ok = True
        except Exception as exc:
            logger.warning("Sound nicht verfügbar: %s", exc)
            self._sound_ok = False

        # Idle-Slideshow
        self._idle_photos: list  = []
        self._idle_idx: int      = 0
        self._idle_next_ms: int  = 0
        self._idle_surf: Optional[pygame.Surface] = None

        logger.info("UI initialisiert")
        self._live = _LiveReader(capture_device)

    # ── Öffentliche API ────────────────────────────────────────────────────────

    def add_photo(self, path: str):
        self._gallery.append(path)
        try:
            img    = pygame.image.load(path).convert()
            scaled = self._scale_to_fill(img, self._PW, self._PH)
            self._cache[path] = scaled
            self._fade_start[path] = pygame.time.get_ticks()
            for _, _, angle in self._frames:
                surf = pygame.Surface((self._PW, self._PH), pygame.SRCALPHA)
                surf.blit(scaled, (0, 0))
                self._rot_cache[(path, angle)] = pygame.transform.rotate(surf, angle)
        except Exception as exc:
            logger.warning("Foto konnte nicht geladen werden: %s", exc)

    def set_layout(self, frames: List[Tuple[int, int, int]], photo_size: Tuple[int, int]):
        """Wechselt Layout (Modus) und leert die Galerie."""
        self._frames = frames
        self._PW, self._PH = photo_size
        self._gallery = deque(maxlen=len(frames))
        self._cache.clear()
        self._rot_cache.clear()
        self._fade_start.clear()

    def render(self, show_live: bool = True):
        self._screen.blit(self._bg, (0, 0))
        if show_live:
            self._draw_live()
        self._draw_polaroids()
        pygame.display.flip()

    def draw_idle(self):
        ticks = pygame.time.get_ticks()
        self._screen.blit(self._bg, (0, 0))
        self._draw_live()

        # Slideshow-Foto klein einblenden
        self._update_idle_slideshow(ticks)
        if self._idle_surf:
            self._screen.blit(self._idle_surf, (760, 350))

        # Pulsierender Text
        pulse = (math.sin(ticks / 700 * math.pi) + 1) / 2
        alpha = int(100 + 155 * pulse)
        lbl = self._font_idle.render("Drück OK zum Starten", True, (255, 255, 255))
        lbl.set_alpha(alpha)
        lx = W // 2 - lbl.get_width() // 2
        ly = self._live_rect[1] + self._live_rect[3] // 2 - lbl.get_height() // 2
        self._screen.blit(lbl, (lx, ly))
        pygame.display.flip()

    def draw_mode_select(self, selected: int):
        self._screen.blit(self._bg, (0, 0))

        card_w, card_h = 640, 110
        gap = 28
        total_h = len(MODES) * card_h + (len(MODES) - 1) * gap
        start_y = (H - total_h) // 2

        for i, mode in enumerate(MODES):
            x = (W - card_w) // 2
            y = start_y + i * (card_h + gap)
            if i == selected:
                pygame.draw.rect(self._screen, CARD_SEL, (x, y, card_w, card_h), border_radius=14)
                txt_color = (30, 20, 8)
            else:
                pygame.draw.rect(self._screen, CARD_BG, (x, y, card_w, card_h), border_radius=14)
                pygame.draw.rect(self._screen, CARD_BORDER, (x, y, card_w, card_h), 2, border_radius=14)
                txt_color = (200, 175, 140)
            lbl = self._font_mode.render(mode, True, txt_color)
            self._screen.blit(lbl, (x + card_w // 2 - lbl.get_width() // 2,
                                    y + card_h // 2 - lbl.get_height() // 2))
            if i == selected:
                arrow = self._font_mode.render("▶", True, txt_color)
                self._screen.blit(arrow, (x + 22, y + card_h // 2 - arrow.get_height() // 2))

        pygame.display.flip()

    def show_flash(self):
        overlay = pygame.Surface((W, H))
        overlay.fill((255, 255, 255))
        start    = pygame.time.get_ticks()
        duration = 300
        while True:
            elapsed = pygame.time.get_ticks() - start
            if elapsed >= duration:
                break
            alpha = int(255 * (1 - elapsed / duration))
            overlay.set_alpha(alpha)
            self._screen.blit(overlay, (0, 0))
            pygame.display.flip()
            pygame.event.pump()
            pygame.time.wait(15)

    def show_countdown(self, seconds: int, on_trigger=None):
        for i in range(seconds, 0, -1):
            if i == seconds and on_trigger:
                threading.Thread(target=on_trigger, daemon=True).start()
            self.play_beep()
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

    def play_beep(self):
        if self._sound_ok:
            self._snd_beep.play()

    def play_shutter(self):
        if self._sound_ok:
            self._snd_shutter.play()

    def check_quit_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return True
            if event.type == pygame.KEYDOWN and event.key == pygame.K_q:
                return True
        return False

    def space_pressed(self) -> bool:
        return bool(pygame.key.get_pressed()[pygame.K_SPACE])

    def key_up_pressed(self) -> bool:
        keys = pygame.key.get_pressed()
        return bool(keys[pygame.K_UP] or keys[pygame.K_w])

    def key_down_pressed(self) -> bool:
        keys = pygame.key.get_pressed()
        return bool(keys[pygame.K_DOWN] or keys[pygame.K_s])

    def key_ok_pressed(self) -> bool:
        keys = pygame.key.get_pressed()
        return bool(keys[pygame.K_SPACE] or keys[pygame.K_RETURN])

    def wait_for_all_release(self):
        while True:
            keys = pygame.key.get_pressed()
            if not any([keys[pygame.K_SPACE], keys[pygame.K_RETURN],
                        keys[pygame.K_UP], keys[pygame.K_DOWN],
                        keys[pygame.K_w], keys[pygame.K_s]]):
                break
            pygame.event.pump()
            pygame.time.wait(30)

    def wait_for_space_release(self):
        while pygame.key.get_pressed()[pygame.K_SPACE]:
            pygame.event.pump()
            pygame.time.wait(30)

    def reload_idle_photos(self):
        pattern = os.path.join(config.PICTURE_PATH, "*.jpg")
        self._idle_photos = sorted(_glob.glob(pattern))
        self._idle_idx = 0
        self._idle_surf = None

    def close(self):
        self._live.close()
        pygame.quit()

    # ── Sound ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _make_sound(freq: float, duration: float) -> pygame.mixer.Sound:
        sample_rate = 44100
        n = int(sample_rate * duration)
        t = np.linspace(0, duration, n, endpoint=False)
        wave = (np.sin(2 * np.pi * freq * t) * 0.4 * 32767).astype(np.int16)
        fade_len = max(1, n // 5)
        wave[-fade_len:] = (wave[-fade_len:] * np.linspace(1, 0, fade_len)).astype(np.int16)
        stereo = np.column_stack([wave, wave])
        return pygame.sndarray.make_sound(stereo)

    # ── Idle-Slideshow ────────────────────────────────────────────────────────

    def _update_idle_slideshow(self, ticks: int):
        if not self._idle_photos:
            return
        if ticks >= self._idle_next_ms:
            self._idle_idx = (self._idle_idx + 1) % len(self._idle_photos)
            self._idle_next_ms = ticks + int(config.IDLE_SLIDESHOW_INTERVAL * 1000)
            try:
                surf = pygame.image.load(self._idle_photos[self._idle_idx]).convert()
                surf = pygame.transform.smoothscale(surf, (400, 300))
                surf.set_alpha(160)
                self._idle_surf = surf
            except Exception:
                self._idle_surf = None

    # ── Overlay laden ─────────────────────────────────────────────────────────

    @staticmethod
    def _load_overlay(path: str) -> pygame.Surface:
        img = pygame.image.load(path).convert()
        iw, ih = img.get_size()
        if (iw, ih) != (W, H):
            img = pygame.transform.scale(img, (W, H))
        return img

    # ── Live-View ─────────────────────────────────────────────────────────────

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
            lbl = self._font_btn.render("Warte auf Kamera…", True, TEXT_DIM)
            self._screen.blit(lbl, (x + w // 2 - lbl.get_width() // 2,
                                    y + h // 2 - lbl.get_height() // 2))

    # ── Polaroid-Fotos ────────────────────────────────────────────────────────

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
        if path not in self._fade_start:
            return 255
        elapsed = pygame.time.get_ticks() - self._fade_start[path]
        return min(255, int(elapsed / self._FADE_MS * 255))

    def _draw_polaroid(self, cx: int, cy: int, angle: float,
                       path: Optional[str], photo: Optional[pygame.Surface],
                       alpha: int = 255):
        if photo is None:
            return
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
        lx, ly, lw, lh = self._live_rect
        self._screen.blit(lbl, (lx + (lw - lbl.get_width()) // 2,
                                ly + (lh - lbl.get_height()) // 2))

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
