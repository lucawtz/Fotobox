import logging
import math
import threading
from collections import deque
from typing import List, Optional, Tuple

import cv2
import numpy as np
import pygame

logger = logging.getLogger(__name__)

W, H = 1920, 1080

# ── Farben ─────────────────────────────────────────────────────────────────────
POLAROID    = (248, 244, 235)
PIN_RED     = (198,  38,  28)
PIN_HIGH    = (240,  80,  65)
PIN_DARK    = (130,  20,  12)
WIRE_COL    = ( 48,  30,  12)
ACCENT      = (185, 140,  58)
BTN_BG      = ( 38,  24,  10)
BTN_BORDER  = (165, 125,  52)
TEXT_LIGHT  = (235, 208, 158)
TEXT_DIM    = (155, 120,  65)


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
    _FW, _FH = 390, 450     # Polaroid-Rahmen gesamt
    _PW, _PH = 350, 310     # Foto-Bereich
    _PX, _PY =  20,  25     # Foto-Offset im Rahmen

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

        self._frames   = polaroid_frames
        self._live_rect = live_rect

        self._font_btn   = pygame.font.SysFont("sans-serif", 28, bold=True)
        self._font_count = pygame.font.SysFont("sans-serif", 260, bold=True)

        self._gallery: deque = deque(maxlen=len(polaroid_frames))
        self._cache: dict = {}

        logger.info("Generiere Holz-Textur …")
        self._bg = self._make_wood()
        self._draw_static_elements(self._bg)
        logger.info("UI initialisiert")

        self._live = _LiveReader(capture_device)

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

    # ── Holz-Textur (numpy) ────────────────────────────────────────────────────

    @staticmethod
    def _make_wood() -> pygame.Surface:
        rng = np.random.RandomState(17)
        px = np.zeros((H, W, 3), dtype=np.float32)

        # Horizontale Bretter
        y = 0
        while y < H:
            ph = int(rng.uniform(130, 195))
            y_end = min(y + ph, H)

            br = float(82 + rng.randint(-14, 14))
            bg = float(53 + rng.randint(-10, 10))
            bb = float(27 + rng.randint(-7,   7))

            x_arr = np.arange(W, dtype=np.float32)
            for row in range(y, y_end):
                local = (row - y) / max(ph - 1, 1)
                # Zwei überlagerte Sinuswellen für Maserung
                f1 = float(rng.uniform(0.04, 0.09))
                f2 = f1 * float(rng.uniform(1.9, 2.4))
                ph1 = float(rng.uniform(0, 20))
                ph2 = float(rng.uniform(0, 10))
                grain = (np.sin(row * f1 + x_arr * 0.0025 + ph1) * 14
                       + np.sin(row * f2 + x_arr * 0.0009 + ph2) *  6
                       + np.sin(x_arr * 0.018 + row * 0.004)      *  3)
                # Randschatten innerhalb des Bretts
                edge = math.sin(local * math.pi) * 10 - 5
                px[row, :, 0] = br + grain + edge
                px[row, :, 1] = bg + grain * 0.62 + edge * 0.62
                px[row, :, 2] = bb + grain * 0.30 + edge * 0.30

            # Fuge zwischen Brettern
            gap_s = max(0, y_end - 3)
            px[gap_s:y_end, :] = [24, 14,  6]
            y = y_end

        # Holzknoten
        x_arr2 = np.arange(W, dtype=np.float32)
        for _ in range(int(rng.randint(4, 7))):
            kx = float(rng.randint(120, W - 120))
            ky = float(rng.randint(40,  H - 40))
            kr = float(rng.randint(22, 48))
            y_arr = np.arange(H, dtype=np.float32).reshape(-1, 1)
            dist = np.sqrt((x_arr2 - kx) ** 2 + (y_arr - ky) ** 2)
            ring   = np.where((dist < kr) & (dist > kr * 0.45), -22.0, 0.0)
            center = np.where(dist < kr * 0.45, -38.0, 0.0)
            total  = ring + center
            px[:, :, 0] = np.clip(px[:, :, 0] + total,        0, 255)
            px[:, :, 1] = np.clip(px[:, :, 1] + total * 0.68, 0, 255)
            px[:, :, 2] = np.clip(px[:, :, 2] + total * 0.38, 0, 255)

        # Vignette
        y_a = np.linspace(-1, 1, H, dtype=np.float32).reshape(-1, 1)
        x_a = np.linspace(-1, 1, W, dtype=np.float32).reshape(1, -1)
        vig = np.clip((x_a ** 2 + y_a ** 2) * 38 - 8, 0, 55)
        for c in range(3):
            px[:, :, c] = np.clip(px[:, :, c] - vig, 0, 255)

        arr = np.clip(px, 0, 255).astype(np.uint8)
        return pygame.surfarray.make_surface(arr.swapaxes(0, 1))

    # ── Statische Elemente einmalig auf Hintergrund zeichnen ───────────────────

    def _draw_static_elements(self, surf: pygame.Surface):
        self._draw_wire(surf)
        self._draw_left_sidebar(surf)
        self._draw_right_sidebar(surf)

    def _pin_position(self, cx: int, cy: int, angle: float) -> Tuple[int, int]:
        """Mitte-oben des Polaroid-Rahmens nach Rotation."""
        rad = math.radians(angle)
        return (int(cx - self._FH / 2 * math.sin(rad)),
                int(cy - self._FH / 2 * math.cos(rad)))

    def _draw_wire(self, surf: pygame.Surface):
        """Durchhängender Draht zwischen den Pin-Positionen."""
        anchors = [(80, 55)] + \
                  [self._pin_position(cx, cy, a) for cx, cy, a in self._frames] + \
                  [(W - 80, 55)]
        for i in range(len(anchors) - 1):
            p1, p2 = anchors[i], anchors[i + 1]
            prev = p1
            segs = 30
            for j in range(1, segs + 1):
                t  = j / segs
                x  = int(p1[0] + t * (p2[0] - p1[0]))
                sag = int(18 * 4 * t * (1 - t))
                y  = int(p1[1] + t * (p2[1] - p1[1]) + sag)
                pygame.draw.line(surf, WIRE_COL, prev, (x, y), 2)
                prev = (x, y)

    def _draw_left_sidebar(self, surf: pygame.Surface):
        font = self._font_btn
        cx = 72

        # Logo
        pygame.draw.circle(surf, (18, 12,  6), (cx, 100), 56)
        pygame.draw.circle(surf, ACCENT,       (cx, 100), 56, 2)
        lbl = font.render("LOGO", True, TEXT_DIM)
        surf.blit(lbl, (cx - lbl.get_width() // 2, 100 - lbl.get_height() // 2))

        # QR-Code
        qx, qy, qs = cx - 40, 205, 80
        pygame.draw.rect(surf, (238, 232, 218), (qx, qy, qs, qs))
        cell = qs // 7
        for row in range(7):
            for col in range(7):
                dark = (
                    (row < 3 and col < 3) or (row < 3 and col > 3) or
                    (row > 3 and col < 3) or (row + col) % 3 == 0
                )
                if dark:
                    pygame.draw.rect(surf, (15, 10, 5),
                                     (qx + col * cell + 1, qy + row * cell + 1,
                                      cell - 1, cell - 1))

        # Instagram-Icon
        ig_cx, ig_cy = cx, 355
        r = 30
        # Äußerer Kreis-Gradient simuliert
        for i, col in enumerate([(193, 53, 132), (220, 48, 108),
                                  (253, 29,  29), (245, 96,  64), (250, 175, 51)]):
            pygame.draw.circle(surf, col, (ig_cx, ig_cy), r - i * 2)
        pygame.draw.circle(surf, (255, 255, 255), (ig_cx, ig_cy), 14, 3)
        pygame.draw.circle(surf, (255, 255, 255), (ig_cx + 14, ig_cy - 14), 4)

    def _draw_right_sidebar(self, surf: pygame.Surface):
        lx = W - 365
        for i, label in enumerate(["Foto", "Collage", "Filter"]):
            y = 540 + i * 148
            # Schatten
            pygame.draw.rect(surf, (15, 9, 4), (lx + 4, y + 4, 335, 76),
                             border_radius=7)
            # Button
            pygame.draw.rect(surf, BTN_BG,     (lx, y, 335, 76), border_radius=7)
            pygame.draw.rect(surf, BTN_BORDER, (lx, y, 335, 76), 2, border_radius=7)
            # Highlight-Linie oben
            pygame.draw.line(surf, (200, 158, 72),
                             (lx + 12, y + 2), (lx + 323, y + 2))
            txt = self._font_btn.render(f"{label}  ▶", True, TEXT_LIGHT)
            surf.blit(txt, (lx + 167 - txt.get_width() // 2,
                            y + 38 - txt.get_height() // 2))

    # ── Live-View ──────────────────────────────────────────────────────────────

    def _draw_live(self):
        x, y, w, h = self._live_rect
        # Holz-Rahmen (mehrschichtig für Tiefe)
        pygame.draw.rect(self._screen, (20, 12,  5), (x - 8, y - 8, w + 16, h + 16),
                         border_radius=4)
        pygame.draw.rect(self._screen, (60, 38, 16), (x - 4, y - 4, w + 8,  h + 8),
                         border_radius=3)

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
            pygame.draw.rect(self._screen, (8, 8, 8), (x, y, w, h))
            lbl = self._font_btn.render("Warte auf Kamera…", True, TEXT_DIM)
            self._screen.blit(lbl, (x + w // 2 - lbl.get_width() // 2,
                                    y + h // 2 - lbl.get_height() // 2))

    # ── Polaroid-Rahmen ────────────────────────────────────────────────────────

    def _draw_polaroids(self):
        photos = list(self._gallery)
        for i, (cx, cy, angle) in enumerate(self._frames):
            photo = self._cache.get(photos[i]) if i < len(photos) else None
            self._draw_polaroid(cx, cy, angle, photo)

    def _draw_polaroid(self, cx: int, cy: int, angle: float,
                       photo: Optional[pygame.Surface]):
        # ── Schatten (mehrere Schichten = weicher Schatten) ──────────────
        for off, alpha in ((12, 28), (9, 42), (6, 56), (3, 70)):
            sh = pygame.Surface((self._FW, self._FH), pygame.SRCALPHA)
            pygame.draw.rect(sh, (0, 0, 0, alpha), (0, 0, self._FW, self._FH),
                             border_radius=3)
            sr = pygame.transform.rotate(sh, angle)
            self._screen.blit(sr, sr.get_rect(center=(cx + off, cy + off)))

        # ── Rahmen-Surface ───────────────────────────────────────────────
        fs = pygame.Surface((self._FW, self._FH), pygame.SRCALPHA)

        # Weißer Polaroid-Körper mit leicht vergilbtem Ton
        pygame.draw.rect(fs, POLAROID, (0, 0, self._FW, self._FH), border_radius=3)

        # Papier-Textur (feine Linien simulieren Fasern)
        for row in range(0, self._FH, 4):
            alpha_t = 8 if row % 8 == 0 else 4
            pygame.draw.line(fs, (180, 175, 165, alpha_t),
                             (0, row), (self._FW, row))

        # Innenschatten um Foto-Bereich
        for i in range(4):
            shade = 60 - i * 12
            pygame.draw.rect(fs, (0, 0, 0, shade),
                             (self._PX - i, self._PY - i,
                              self._PW + i * 2, self._PH + i * 2), 1)

        # Foto oder Platzhalter
        if photo:
            fs.blit(photo, (self._PX, self._PY))
        else:
            pygame.draw.rect(fs, (10, 10, 10),
                             (self._PX, self._PY, self._PW, self._PH))
            # Kamera-Icon-Platzhalter
            icx = self._PX + self._PW // 2
            icy = self._PY + self._PH // 2
            pygame.draw.rect(fs, (35, 35, 35),
                             (icx - 35, icy - 22, 70, 44), border_radius=5)
            pygame.draw.circle(fs, (55, 55, 55), (icx, icy), 14)
            pygame.draw.circle(fs, (28, 28, 28), (icx, icy), 9)
            pygame.draw.circle(fs, (70, 70, 70), (icx - 25, icy - 14), 5)

        # Rotieren und blиtten
        rotated = pygame.transform.rotate(fs, angle)
        self._screen.blit(rotated, rotated.get_rect(center=(cx, cy)))

        # ── Realistischer Pin ────────────────────────────────────────────
        px, py = self._pin_position(cx, cy, angle)
        # Stift-Körper
        pygame.draw.circle(self._screen, PIN_DARK,  (px,     py    ), 13)
        pygame.draw.circle(self._screen, PIN_RED,   (px,     py    ), 11)
        pygame.draw.circle(self._screen, (220, 55, 45), (px, py    ),  8)
        # Glanz-Highlight
        pygame.draw.circle(self._screen, PIN_HIGH,  (px - 3, py - 3),  4)
        pygame.draw.circle(self._screen, (255, 200, 195), (px - 4, py - 4), 2)

    # ── Countdown ─────────────────────────────────────────────────────────────

    def _draw_countdown_frame(self, number: int):
        self._screen.blit(self._bg, (0, 0))
        self._draw_live()
        self._draw_polaroids()
        dim = pygame.Surface((W, H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 165))
        self._screen.blit(dim, (0, 0))
        lbl = self._font_count.render(str(number), True, (255, 255, 255))
        self._screen.blit(lbl, (W // 2 - lbl.get_width() // 2,
                                H // 2 - lbl.get_height() // 2))
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
