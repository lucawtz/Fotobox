import logging
import math
import os
import threading
import time
from collections import deque
from typing import Optional

import cv2
import pygame

logger = logging.getLogger(__name__)

W, H = 1920, 1080

# Farben
C_GOLD   = (212, 168, 106)
C_DARK   = (40,  25,  10)
C_WHITE  = (255, 255, 255)
C_BLACK  = (0,   0,   0)
C_RED    = (220, 60,  40)
C_GREEN  = (80,  200, 80)
C_YELLOW = (255, 220, 50)
C_DIM    = (155, 120, 65)
C_BTN_BG = (60,  38,  15)
C_BTN_HL = (180, 130, 60)


class _LiveReader:
    """Liest Capture-Card-Frames in einem Hintergrund-Thread."""

    _TARGET_FPS = 30

    def __init__(self, device: int):
        self._cap = cv2.VideoCapture(device)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not self._cap.isOpened():
            raise RuntimeError(f"Capture-Device {device} nicht verfügbar")
        self._frame = None
        self._lock = threading.Lock()
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()
        logger.info("LiveReader gestartet (device=%d)", device)

    def _loop(self):
        interval = 1.0 / self._TARGET_FPS
        while self._running:
            t0 = time.monotonic()
            ok, frame = self._cap.read()
            if ok:
                with self._lock:
                    self._frame = frame
            elapsed = time.monotonic() - t0
            rest = interval - elapsed
            if rest > 0:
                time.sleep(rest)

    def latest(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def close(self):
        self._running = False
        self._cap.release()


class UI:
    """Pygame-UI mit State-Machine für Homescreen, Countdown, Result und Slideshow."""

    def __init__(self, cfg: dict, capture_device: int):
        self._cfg = cfg

        pygame.init()
        self._screen = pygame.display.set_mode((W, H), pygame.FULLSCREEN)
        pygame.display.set_caption("Fotobox")
        pygame.mouse.set_visible(False)

        # Fonts
        self._f_big    = pygame.font.SysFont("sans-serif", 200, bold=True)
        self._f_large  = pygame.font.SysFont("sans-serif", 110, bold=True)
        self._f_medium = pygame.font.SysFont("sans-serif", 60,  bold=True)
        self._f_normal = pygame.font.SysFont("sans-serif", 40,  bold=True)
        self._f_small  = pygame.font.SysFont("sans-serif", 26)
        self._f_event  = pygame.font.SysFont("sans-serif", 52,  bold=True)

        # Overlay / Hintergrund
        overlay = cfg.get("overlay_path", "")
        if overlay and os.path.isfile(overlay):
            img = pygame.image.load(overlay).convert()
            self._bg = pygame.transform.scale(img, (W, H)) if img.get_size() != (W, H) else img
        else:
            self._bg = pygame.Surface((W, H))
            self._bg.fill(C_DARK)
            logger.warning("Overlay nicht gefunden — dunkler Hintergrund")

        # Logo
        self._logo_surf = self._load_logo(cfg.get("logo_path", ""))

        # QR-Code
        self._qr_surf = self._make_qr(cfg.get("gallery_url", ""), size=160)

        # Polaroid-Galerie
        frames = cfg.get("polaroid_frames", [[567, 255, -5], [1098, 256, 5], [1633, 257, 12]])
        self._frames = [tuple(f) for f in frames]
        pw, ph = cfg.get("polaroid_photo_size", [310, 295])
        self._PW, self._PH = pw, ph
        self._gallery: deque = deque(maxlen=len(self._frames))
        self._photo_cache: dict = {}
        self._rot_cache: dict = {}
        self._fade_start: dict = {}
        self._FADE_MS = 1500

        # Slideshow
        self._slide_paths: list = []
        self._slide_idx: int = 0
        self._slide_start_ms: int = 0
        self._slide_surf: Optional[pygame.Surface] = None
        self._SLIDE_FADE_MS = 800

        # Result-Screen Cache
        self._result_cache: dict = {}

        # Live-Reader (Capture-Card)
        self._live: Optional[_LiveReader] = None
        try:
            self._live = _LiveReader(capture_device)
        except Exception as exc:
            logger.warning("Kein Live-Feed: %s", exc)

    # ── Öffentliche API ────────────────────────────────────────────────────────

    def check_quit(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return True
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return True
        return False

    def reload_logo(self):
        self._logo_surf = self._load_logo(self._cfg.get("logo_path", ""))

    # ── Homescreen ─────────────────────────────────────────────────────────────

    def render_homescreen(self, camera_ok: bool, camera_msg: str,
                          free_mb: int, photo_count: int):
        self._screen.blit(self._bg, (0, 0))
        self._draw_polaroids()
        self._draw_overlay_button_highlights()
        self._draw_qr_bottom_left()
        self._draw_status_bar(camera_ok, free_mb, photo_count)
        if not camera_ok:
            self._draw_error_banner(camera_msg or "Kamera nicht erkannt – USB prüfen")
        pygame.display.flip()

    def _draw_overlay_button_highlights(self):
        """Zeichnet einen Glow um die im Overlay enthaltenen Foto- und Collage-Buttons,
        wenn die zugehörige Taste/GPIO-Knopf gedrückt ist."""
        keys = pygame.key.get_pressed()
        foto_pressed    = keys[pygame.K_SPACE]
        collage_pressed = keys[pygame.K_e]

        foto_rect    = pygame.Rect(*self._cfg.get(
            "overlay_button_foto",    [1475, 700, 385, 100]))
        collage_rect = pygame.Rect(*self._cfg.get(
            "overlay_button_collage", [1475, 840, 385, 110]))

        if foto_pressed:
            self._draw_button_glow(foto_rect)
        if collage_pressed:
            self._draw_button_glow(collage_rect)

    def _draw_button_glow(self, rect: pygame.Rect):
        glow = pygame.Surface((rect.width + 40, rect.height + 40), pygame.SRCALPHA)
        for i in range(8, 0, -1):
            alpha = 30 + (8 - i) * 10
            pygame.draw.rect(
                glow, (*C_GOLD, alpha),
                glow.get_rect().inflate(-i * 4, -i * 4),
                width=4, border_radius=14,
            )
        self._screen.blit(glow, (rect.x - 20, rect.y - 20))

    def _draw_status_bar(self, camera_ok: bool, free_mb: int, photo_count: int):
        bar = pygame.Surface((W, 28), pygame.SRCALPHA)
        bar.fill((0, 0, 0, 160))
        self._screen.blit(bar, (0, H - 28))

        cam_color = C_GREEN if camera_ok else C_RED
        cam_text  = "Kamera: OK" if camera_ok else "Kamera: FEHLT"
        items = [
            (cam_text, cam_color),
            (f"Speicher: {free_mb / 1024:.1f} GB" if free_mb >= 1024
             else f"Speicher: {free_mb} MB",
             C_YELLOW if free_mb < self._cfg.get("disk_warn_mb", 500) else C_DIM),
            (f"Fotos: {photo_count}", C_DIM),
            ("Hotspot: aktiv" if self._cfg.get("hotspot_enabled") else "Hotspot: aus", C_DIM),
        ]
        x = 20
        for text, color in items:
            lbl = self._f_small.render(text, True, color)
            self._screen.blit(lbl, (x, H - 24))
            x += lbl.get_width() + 60

    def _draw_error_banner(self, message: str):
        banner_h = 54
        surf = pygame.Surface((W, banner_h), pygame.SRCALPHA)
        surf.fill((180, 40, 20, 210))
        self._screen.blit(surf, (0, 0))
        lbl = self._f_normal.render(message, True, C_WHITE)
        self._screen.blit(lbl, lbl.get_rect(centerx=W // 2, centery=banner_h // 2))

    # ── Countdown-Screen (blockierend) ─────────────────────────────────────────

    def run_countdown(self, on_capture, seconds: int = 3,
                      photo_num: int = 1, total: int = 1) -> None:
        """Zeigt Countdown, löst on_capture() danach aus, zeigt 'Lächeln!'.

        on_capture wird als Callback in einem Thread gestartet.
        Aufrufer wartet nach dieser Methode auf das done-Event.
        """
        for i in range(seconds, 0, -1):
            deadline = pygame.time.get_ticks() + 1000
            while pygame.time.get_ticks() < deadline:
                self._draw_countdown_frame(i, photo_num, total)
                pygame.event.pump()
                pygame.time.wait(30)

        self._flash()
        threading.Thread(target=on_capture, daemon=True).start()

        deadline = pygame.time.get_ticks() + 1200
        while pygame.time.get_ticks() < deadline:
            self._draw_laecheln_frame(photo_num, total)
            pygame.event.pump()
            pygame.time.wait(30)

    def _draw_countdown_frame(self, number: int, photo_num: int, total: int):
        self._draw_live_fullscreen()
        lbl = self._f_big.render(str(number), True, C_WHITE)
        self._screen.blit(lbl, lbl.get_rect(center=(W // 2, H // 2)))
        if total > 1:
            sub = self._f_normal.render(f"Foto {photo_num} von {total}", True, C_GOLD)
            self._screen.blit(sub, sub.get_rect(center=(W // 2, H // 2 + 140)))
        pygame.display.flip()

    def _draw_laecheln_frame(self, photo_num: int, total: int):
        self._draw_live_fullscreen()
        lbl = self._f_large.render("Lächeln!", True, C_YELLOW)
        self._screen.blit(lbl, lbl.get_rect(center=(W // 2, H // 2)))
        if total > 1:
            sub = self._f_normal.render(f"Foto {photo_num} von {total}", True, C_GOLD)
            self._screen.blit(sub, sub.get_rect(center=(W // 2, H // 2 + 120)))
        pygame.display.flip()

    def _flash(self, duration_ms: int = 300):
        start = pygame.time.get_ticks()
        flash = pygame.Surface((W, H))
        flash.fill(C_WHITE)
        while True:
            elapsed = pygame.time.get_ticks() - start
            if elapsed >= duration_ms:
                break
            alpha = max(0, 255 - int(elapsed / duration_ms * 255))
            self._draw_live_fullscreen()
            flash.set_alpha(alpha)
            self._screen.blit(flash, (0, 0))
            pygame.display.flip()
            pygame.event.pump()
            pygame.time.wait(16)

    # ── Result-Screen ──────────────────────────────────────────────────────────

    def render_result(self, photo_path: str, time_left: float):
        self._screen.fill((10, 6, 2))
        self._draw_result_photo(photo_path)
        self._draw_qr_result()
        self._draw_result_buttons(time_left)
        pygame.display.flip()

    def _draw_result_photo(self, path: str):
        if path not in self._result_cache:
            try:
                img = pygame.image.load(path).convert()
                target_w = int(W * 0.72)
                target_h = int(H * 0.72)
                scale = min(target_w / img.get_width(), target_h / img.get_height())
                nw = int(img.get_width() * scale)
                nh = int(img.get_height() * scale)
                self._result_cache[path] = pygame.transform.smoothscale(img, (nw, nh))
            except Exception as exc:
                logger.warning("Result-Foto: %s", exc)
                return
        surf = self._result_cache[path]
        self._screen.blit(surf, surf.get_rect(centerx=W // 2, centery=H // 2 - 60))

    def _draw_qr_result(self):
        if self._qr_surf is None:
            return
        QR = self._qr_surf.get_width()
        PAD = 16
        x, y = W - QR - PAD, PAD
        bg = pygame.Surface((QR + PAD * 2, QR + PAD * 2))
        bg.fill(C_WHITE)
        self._screen.blit(bg, (x - PAD, y - PAD))
        self._screen.blit(self._qr_surf, (x, y))

    def _draw_result_buttons(self, time_left: float):
        keys = pygame.key.get_pressed()
        btn_w, btn_h = 340, 72
        gap = 60
        total_w = 3 * btn_w + 2 * gap
        sx = (W - total_w) // 2
        by = H - btn_h - 20

        # Timer
        timer = self._f_small.render(f"Zurück in {max(0, int(time_left)) + 1}s",
                                     True, C_DIM)
        self._screen.blit(timer, timer.get_rect(centerx=W // 2, bottom=by - 10))

        defs = [
            ("← Zurück",  "Q",     keys[pygame.K_q]),
            ("Nochmal",   "Space", keys[pygame.K_SPACE]),
            ("Drucken →", "E",     keys[pygame.K_e]),
        ]
        for i, (label, key_hint, hl) in enumerate(defs):
            rect = pygame.Rect(sx + i * (btn_w + gap), by, btn_w, btn_h)
            color = C_BTN_HL if hl else C_BTN_BG
            pygame.draw.rect(self._screen, color, rect, border_radius=12)
            pygame.draw.rect(self._screen, C_GOLD, rect, width=2, border_radius=12)
            lbl = self._f_normal.render(label, True, C_WHITE if hl else C_GOLD)
            self._screen.blit(lbl, lbl.get_rect(centerx=rect.centerx, centery=rect.centery - 10))
            hint = self._f_small.render(f"[ {key_hint} ]", True, C_DIM)
            self._screen.blit(hint, hint.get_rect(centerx=rect.centerx, centery=rect.centery + 20))

    # ── Slideshow ──────────────────────────────────────────────────────────────

    def refresh_slideshow(self, folder: str):
        exts = {".jpg", ".jpeg", ".png"}
        try:
            paths = sorted(
                [os.path.join(folder, f) for f in os.listdir(folder)
                 if os.path.splitext(f)[1].lower() in exts]
            )
        except FileNotFoundError:
            paths = []
        self._slide_paths = paths
        self._slide_idx = 0
        self._slide_start_ms = pygame.time.get_ticks()
        self._slide_surf = None
        logger.info("Slideshow: %d Fotos", len(paths))

    def render_slideshow(self):
        if not self._slide_paths:
            self.render_homescreen(True, "", 0, 0)
            return
        duration = self._cfg.get("slide_duration_ms", 5000)
        now = pygame.time.get_ticks()
        if now - self._slide_start_ms > duration:
            self._slide_idx = (self._slide_idx + 1) % len(self._slide_paths)
            self._slide_start_ms = now
            self._slide_surf = None
        if self._slide_surf is None:
            try:
                img = pygame.image.load(self._slide_paths[self._slide_idx]).convert()
                self._slide_surf = pygame.transform.smoothscale(img, (W, H))
            except Exception:
                self._slide_surf = pygame.Surface((W, H))
                self._slide_surf.fill(C_BLACK)
        elapsed = now - self._slide_start_ms
        alpha = min(255, int(elapsed / self._SLIDE_FADE_MS * 255))
        self._slide_surf.set_alpha(alpha)
        self._screen.fill(C_BLACK)
        self._screen.blit(self._slide_surf, (0, 0))
        self._draw_qr()
        # Hint
        pulse = (math.sin(now / 600) + 1) / 2
        lbl = self._f_normal.render("Drück einen Knopf", True, C_WHITE)
        surf = pygame.Surface(lbl.get_size(), pygame.SRCALPHA)
        surf.blit(lbl, (0, 0))
        surf.set_alpha(int(60 + pulse * 195))
        self._screen.blit(surf, surf.get_rect(center=(W // 2, H - 60)))
        pygame.display.flip()

    # ── Polaroid-Galerie ───────────────────────────────────────────────────────

    def add_photo(self, path: str):
        self._gallery.append(path)
        try:
            img = pygame.image.load(path).convert()
            scaled = self._scale_to_fill(img, self._PW, self._PH)
            self._photo_cache[path] = scaled
            self._fade_start[path] = pygame.time.get_ticks()
            for _, _, angle in self._frames:
                surf = pygame.Surface((self._PW, self._PH), pygame.SRCALPHA)
                surf.blit(scaled, (0, 0))
                self._rot_cache[(path, angle)] = pygame.transform.rotate(surf, angle)
        except Exception as exc:
            logger.warning("Polaroid-Ladefehler: %s", exc)

    def _draw_polaroids(self):
        photos = list(self._gallery)
        for i, (cx, cy, angle) in enumerate(self._frames):
            if i < len(photos):
                path  = photos[i]
                photo = self._photo_cache.get(path)
                alpha = self._photo_alpha(path)
            else:
                path, photo, alpha = None, None, 255
            self._draw_polaroid(cx, cy, angle, path, photo, alpha)

    def _photo_alpha(self, path: str) -> int:
        if path not in self._fade_start:
            return 255
        elapsed = pygame.time.get_ticks() - self._fade_start[path]
        return min(255, int(elapsed / self._FADE_MS * 255))

    def _draw_polaroid(self, cx, cy, angle, path, photo, alpha):
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

    # ── Live-View ──────────────────────────────────────────────────────────────

    def _draw_live_fullscreen(self):
        if self._live is None:
            self._screen.fill(C_BLACK)
            return
        frame = self._live.latest()
        if frame is not None:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            fh, fw = frame.shape[:2]
            scale = min(W / fw, H / fh)
            nw, nh = int(fw * scale), int(fh * scale)
            frame = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
            surf = pygame.surfarray.make_surface(frame.swapaxes(0, 1))
            self._screen.fill(C_BLACK)
            self._screen.blit(surf, ((W - nw) // 2, (H - nh) // 2))
        else:
            self._screen.fill(C_BLACK)

    # ── QR-Code ────────────────────────────────────────────────────────────────

    def _draw_qr(self):
        """QR rechts unten – für Slideshow/Result (kollidiert nicht mit Overlay-Buttons)."""
        if self._qr_surf is None:
            return
        QR, PAD = self._qr_surf.get_width(), 12
        x, y = W - QR - PAD, H - QR - PAD
        bg = pygame.Surface((QR + PAD * 2, QR + PAD * 2))
        bg.fill(C_WHITE)
        bg.set_alpha(220)
        self._screen.blit(bg, (x - PAD, y - PAD))
        self._screen.blit(self._qr_surf, (x, y))

    def _draw_qr_bottom_left(self):
        """QR im Holzfeld unter den Polaroids, links — weicht den Overlay-Buttons aus."""
        if self._qr_surf is None:
            return
        QR, PAD = self._qr_surf.get_width(), 12
        x, y = 260, 470
        bg = pygame.Surface((QR + PAD * 2, QR + PAD * 2))
        bg.fill(C_WHITE)
        bg.set_alpha(220)
        self._screen.blit(bg, (x - PAD, y - PAD))
        self._screen.blit(self._qr_surf, (x, y))
        hint = self._f_small.render("Galerie scannen", True, C_WHITE)
        self._screen.blit(hint, hint.get_rect(centerx=x + QR // 2, top=y + QR + PAD + 6))

    # ── Hilfsmethoden ─────────────────────────────────────────────────────────

    @staticmethod
    def _load_logo(path: str) -> Optional[pygame.Surface]:
        if not path or not os.path.isfile(path):
            return None
        try:
            img = pygame.image.load(path).convert_alpha()
            max_h = 80
            if img.get_height() > max_h:
                scale = max_h / img.get_height()
                img = pygame.transform.smoothscale(
                    img, (int(img.get_width() * scale), max_h))
            return img
        except Exception as exc:
            logger.warning("Logo: %s", exc)
            return None

    @staticmethod
    def _make_qr(url: str, size: int = 160) -> Optional[pygame.Surface]:
        if not url:
            return None
        try:
            import qrcode
            from PIL import Image
            qr = qrcode.make(url).convert("RGB").resize((size, size), Image.NEAREST)
            return pygame.image.frombuffer(
                qr.tobytes("raw", "RGB"), (size, size), "RGB").copy()
        except ImportError:
            logger.warning("qrcode/pillow fehlt — QR-Code deaktiviert")
        except Exception as exc:
            logger.warning("QR-Code: %s", exc)
        return None

    @staticmethod
    def _scale_to_fill(surf: pygame.Surface, w: int, h: int) -> pygame.Surface:
        sw, sh = surf.get_size()
        scale  = max(w / sw, h / sh)
        nw, nh = int(sw * scale), int(sh * scale)
        scaled = pygame.transform.smoothscale(surf, (nw, nh))
        return scaled.subsurface(
            pygame.Rect((nw - w) // 2, (nh - h) // 2, w, h)).copy()

    def close(self):
        if self._live:
            self._live.close()
        pygame.quit()
