import logging
import math
import random
import threading
from collections import deque
from typing import List, Optional, Tuple

import cv2
import numpy as np
import pygame

logger = logging.getLogger(__name__)

W, H = 1920, 1080

# ── Farben ─────────────────────────────────────────────────────────────────────
WOOD_BASE   = ( 85,  55,  28)
POLAROID    = (248, 244, 235)
PIN_RED     = (210,  45,  35)
PIN_LIGHT   = (240,  80,  70)
WIRE_COLOR  = ( 55,  35,  15)
ACCENT      = (190, 145,  65)
BTN_BG      = ( 45,  28,  12)
BTN_BORDER  = (175, 135,  60)
TEXT_LIGHT  = (230, 205, 155)
TEXT_DIM    = (160, 130,  80)
LIVE_BORDER = ( 60,  40,  18)


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
    # Polaroid-Rahmen Abmessungen
    _FW, _FH = 390, 450         # Gesamt-Rahmen
    _PW, _PH = 350, 310         # Foto-Bereich
    _PX, _PY = 20, 25           # Foto-Offset im Rahmen

    def __init__(
        self,
        capture_device: int,
        polaroid_frames: List[Tuple[int, int, int]],
        live_rect: Tuple[int, int, int, int],
    ):
        pygame.init()
        self._screen = pygame.display.set_mode((W, H), pygame.FULLSCREEN)
        pygame.display.set_caption("Fotobox")
        pygame.mouse.set_visible(False)

        self._frames = polaroid_frames   # [(cx, cy, angle), ...]
        self._live_rect = live_rect

        self._font_btn    = pygame.font.SysFont("sans-serif", 28, bold=True)
        self._font_count  = pygame.font.SysFont("sans-serif", 260, bold=True)
        self._font_small  = pygame.font.SysFont("sans-serif", 20)

        self._gallery: deque = deque(maxlen=len(polaroid_frames))
        self._cache: dict = {}

        # Hintergrund einmalig vorrendern
        self._bg = self._build_background()

        self._live = _LiveReader(capture_device)
        logger.info("UI initialisiert")

    # ── Öffentliche API ────────────────────────────────────────────────────────

    def add_photo(self, path: str):
        self._gallery.append(path)
        try:
            img = pygame.image.load(path).convert()
            self._cache[path] = self._scale_to_fill(img, self._PW, self._PH)
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

    # ── Hintergrund vorrendern ─────────────────────────────────────────────────

    def _build_background(self) -> pygame.Surface:
        surf = pygame.Surface((W, H))

        # Holz-Maserung
        rng = random.Random(7)
        surf.fill(WOOD_BASE)
        for y in range(0, H, 5):
            v = rng.randint(-22, 22)
            r = max(0, min(255, WOOD_BASE[0] + v))
            g = max(0, min(255, WOOD_BASE[1] + v))
            b = max(0, min(255, WOOD_BASE[2] + v))
            t = rng.choice([1, 1, 2, 3])
            dy = rng.randint(-4, 4)
            pygame.draw.line(surf, (r, g, b), (0, y), (W, y + dy), t)

        # Senkrechte Bretter-Trennlinien
        for x in range(0, W, rng.randint(160, 260)):
            pygame.draw.line(surf, (50, 32, 14), (x, 0), (x, H), 2)

        # Horizontaler Draht für die Polaroids
        wire_y = 60
        pygame.draw.line(surf, WIRE_COLOR, (120, wire_y), (W - 120, wire_y), 3)

        # Linke Seitenleiste
        self._draw_left_sidebar(surf)

        # Rechte Seitenleiste
        self._draw_right_sidebar(surf)

        return surf

    def _draw_left_sidebar(self, surf: pygame.Surface):
        cx = 72

        # Logo-Kreis
        pygame.draw.circle(surf, (20, 15, 8), (cx, 95), 55)
        pygame.draw.circle(surf, ACCENT, (cx, 95), 55, 2)
        lbl = self._font_btn.render("LOGO", True, TEXT_DIM)
        surf.blit(lbl, (cx - lbl.get_width() // 2, 95 - lbl.get_height() // 2))

        # QR-Code Platzhalter
        qr_x, qr_y, qr_s = cx - 42, 200, 84
        pygame.draw.rect(surf, (240, 235, 220), (qr_x, qr_y, qr_s, qr_s))
        # Einfaches QR-Gitter
        cell = qr_s // 7
        for row in range(7):
            for col in range(7):
                if (row + col) % 2 == 0 or (row < 3 and col < 3) or \
                   (row < 3 and col > 3) or (row > 3 and col < 3):
                    pygame.draw.rect(surf, (20, 15, 8),
                                     (qr_x + col * cell + 2, qr_y + row * cell + 2,
                                      cell - 2, cell - 2))

        # Instagram-Icon (stilisiertes Quadrat + Kreis)
        ig_x, ig_y = cx - 30, 340
        pygame.draw.rect(surf, (0, 0, 0, 0), (ig_x, ig_y, 60, 60))
        # Gradient simulieren via mehrere Rechtecke
        for i, color in enumerate([(193, 53, 132), (225, 48, 108),
                                    (253, 29, 29), (245, 96, 64), (250, 175, 51)]):
            pygame.draw.rect(surf, color,
                             (ig_x + i * 2, ig_y + i * 2, 60 - i * 4, 60 - i * 4),
                             border_radius=12 - i)
        pygame.draw.circle(surf, (255, 255, 255), (cx, ig_y + 30), 16, 3)
        pygame.draw.circle(surf, (255, 255, 255), (cx + 18, ig_y + 12), 4)

    def _draw_right_sidebar(self, surf: pygame.Surface):
        lx = W - 370
        for i, label in enumerate(["Foto", "Collage", "Filter"]):
            y = 565 + i * 145
            pygame.draw.rect(surf, BTN_BG, (lx, y, 340, 75), border_radius=6)
            pygame.draw.rect(surf, BTN_BORDER, (lx, y, 340, 75), 2, border_radius=6)
            txt = self._font_btn.render(f"{label}  ▶", True, TEXT_LIGHT)
            surf.blit(txt, (lx + 170 - txt.get_width() // 2,
                            y + 37 - txt.get_height() // 2))

    # ── Laufzeit-Rendering ─────────────────────────────────────────────────────

    def _draw_live(self):
        x, y, w, h = self._live_rect
        # Rahmen
        pygame.draw.rect(self._screen, LIVE_BORDER, (x - 4, y - 4, w + 8, h + 8),
                         border_radius=4)
        frame = self._live.latest()
        if frame is not None:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            fh, fw = frame.shape[:2]
            scale = min(w / fw, h / fh)
            nw, nh = int(fw * scale), int(fh * scale)
            frame = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
            surf = pygame.surfarray.make_surface(frame.swapaxes(0, 1))
            self._screen.blit(surf, (x + (w - nw) // 2, y + (h - nh) // 2))
        else:
            pygame.draw.rect(self._screen, (10, 10, 10), (x, y, w, h))
            lbl = self._font_btn.render("Warte auf Kamera…", True, TEXT_DIM)
            self._screen.blit(lbl, (x + w // 2 - lbl.get_width() // 2,
                                    y + h // 2 - lbl.get_height() // 2))

    def _draw_polaroids(self):
        photos = list(self._gallery)
        for i, (cx, cy, angle) in enumerate(self._frames):
            photo = self._cache.get(photos[i]) if i < len(photos) else None
            self._draw_polaroid(cx, cy, angle, photo)

    def _draw_polaroid(self, cx: int, cy: int, angle: float,
                       photo: Optional[pygame.Surface]):
        # Rahmen-Surface
        frame_surf = pygame.Surface((self._FW, self._FH), pygame.SRCALPHA)

        # Schatten
        shadow = pygame.Surface((self._FW, self._FH), pygame.SRCALPHA)
        pygame.draw.rect(shadow, (0, 0, 0, 90),
                         (0, 0, self._FW, self._FH), border_radius=3)
        shadow_rot = pygame.transform.rotate(shadow, angle)
        sr = shadow_rot.get_rect(center=(cx + 8, cy + 8))
        self._screen.blit(shadow_rot, sr)

        # Weißer Rahmen
        pygame.draw.rect(frame_surf, POLAROID, (0, 0, self._FW, self._FH),
                         border_radius=3)

        # Foto oder schwarzer Platzhalter
        if photo:
            frame_surf.blit(photo, (self._PX, self._PY))
        else:
            pygame.draw.rect(frame_surf, (12, 12, 12),
                             (self._PX, self._PY, self._PW, self._PH))

        # Rahmen rotieren und zeichnen
        rotated = pygame.transform.rotate(frame_surf, angle)
        rr = rotated.get_rect(center=(cx, cy))
        self._screen.blit(rotated, rr)

        # Roter Pin oben an der Befestigungsstelle
        rad = math.radians(angle)
        pin_x = int(cx - (self._FH / 2) * math.sin(rad))
        pin_y = int(cy - (self._FH / 2) * math.cos(rad))
        pygame.draw.circle(self._screen, PIN_RED, (pin_x, pin_y), 11)
        pygame.draw.circle(self._screen, PIN_LIGHT, (pin_x - 3, pin_y - 3), 5)

    def _draw_countdown_frame(self, number: int):
        self._screen.blit(self._bg, (0, 0))
        self._draw_live()
        self._draw_polaroids()
        dim = pygame.Surface((W, H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 160))
        self._screen.blit(dim, (0, 0))
        lbl = self._font_count.render(str(number), True, (255, 255, 255))
        self._screen.blit(lbl, (W // 2 - lbl.get_width() // 2,
                                H // 2 - lbl.get_height() // 2))
        pygame.display.flip()

    @staticmethod
    def _scale_to_fill(surf: pygame.Surface, w: int, h: int) -> pygame.Surface:
        sw, sh = surf.get_size()
        scale = max(w / sw, h / sh)
        nw, nh = int(sw * scale), int(sh * scale)
        scaled = pygame.transform.smoothscale(surf, (nw, nh))
        x = (nw - w) // 2
        y = (nh - h) // 2
        return scaled.subsurface(pygame.Rect(x, y, w, h)).copy()
