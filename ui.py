import functools
import logging
import math
import os
import threading
import time
from collections import deque
from typing import Optional

import cv2
import pygame
import pygame.gfxdraw

logger = logging.getLogger(__name__)

W, H = 1920, 1080

# Fallback-Farben — werden verwendet wenn das Theme im config.json fehlt
# oder ungültig ist. Entsprechen dem Default-Look (Gold/Dunkel).
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

# Layout-Konstanten — fest in Code. Mieter-Anpassungen laufen über
# theme/branding/actions in config.json, das Layout bleibt fix.
SIDEBAR_W       = 320
SIDEBAR_PAD     = 20
LOGO_CIRCLE_R   = 80      # Radius des Cream-Kreises um das Logo.
ACTION_X        = 1530
ACTION_W        = 320
ACTION_H        = 110
ACTION_GAP      = 24
ACTION_RADIUS   = 28      # Stärker abgerundete Ecken — moderner als 18.
LIVE_OUTER_W    = 12      # Aussenrahmen (braun) ums Live-View.
LIVE_INNER_W    = 3       # Innerer Goldakzent.

# Mini-QRs unter dem Galerie-Code (Instagram / Terminbuchung). Bewusst
# kleiner als der Galerie-QR — der bleibt der Hauptcode der Sidebar.
SOCIAL_QR_SIZE  = 80      # Zielgroesse; _make_qr rundet auf ganze Module auf.
SOCIAL_QR_PAD   = 7       # Cremerand um den Code — zugleich seine Quiet-Zone.
SOCIAL_ROW_GAP  = 10      # Luft zwischen den beiden Reihen.
SOCIAL_ICON     = 18      # Instagram-/Kalender-Glyph neben der Beschriftung.

# Polaroid-Renderer
POLAROID_PAD_TOP = 18
POLAROID_PAD_LR  = 18
POLAROID_PAD_BOT = 60
POLAROID_PIN_R   = 9

# Pastellfarbene Platzhalter für leere Polaroid-Slots — Hint, dass dort
# Fotos erscheinen werden. Reihenfolge passt zum Mockup (taupe, hellblau, rosa).
_PLACEHOLDER_COLORS = [
    (201, 168, 138),
    (157, 190, 210),
    (212, 165, 181),
]

# Mapping: action.key (config) → pygame-Taste, damit der Button-Highlight
# weiß welche Taste/GPIO ihn aktiviert. Halten parallel zu hardware.py.
_ACTION_KEYS = {
    "trigger": pygame.K_SPACE,
    "right":   pygame.K_e,
    "left":    pygame.K_q,
}


def _hex_to_rgb(s: str, default=(0, 0, 0)) -> tuple:
    """'#D4A86A' → (212, 168, 106). Robust gegen leere/kaputte Strings."""
    s = (s or "").lstrip("#")
    if len(s) != 6:
        return default
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return default


def _aa_filled_circle(surf, color, cx, cy, r):
    """Antialiased gefüllter Kreis. pygame.draw.circle hat harte, gezackte
    Kanten — gfxdraw.filled_circle + aacircle blendet die Kontur weich an
    den Hintergrund an, sodass der Kreis nicht mehr 'pixelig' wirkt.
    """
    cx, cy, r = int(cx), int(cy), int(r)
    if len(color) == 3:
        color = (*color, 255)
    pygame.gfxdraw.filled_circle(surf, cx, cy, r, color)
    pygame.gfxdraw.aacircle(surf, cx, cy, r, color)


@functools.lru_cache(maxsize=16)
def _aa_round_rect_mask(w: int, h: int, radius: int,
                        supersample: int = 2) -> pygame.Surface:
    """Alpha-Maske für eine Rounded-Rect-Form mit weichen Ecken.

    Die Maske wird supersample-fach grösser gerendert und per smoothscale
    auf Zielgrösse runtergerechnet — das gibt sanft auslaufende Alpha-
    Verläufe an den abgerundeten Ecken (statt gezackter Pixeltreppen).
    RGB ist überall (255,255,255), nur Alpha variiert. So darf die Maske
    via BLEND_RGBA_MIN auf eine farbige Surface geblittet werden, ohne
    dass die Farbe an den Ecken nach Grau verfärbt.

    Gecached, weil alle Action-Buttons identische Maße haben — sonst
    würden wir die Supersample-Maske 60×/Sek/Button neu erstellen.
    """
    big = pygame.Surface((w * supersample, h * supersample), pygame.SRCALPHA)
    big.fill((255, 255, 255, 0))
    pygame.draw.rect(big, (255, 255, 255, 255), big.get_rect(),
                     border_radius=radius * supersample)
    return pygame.transform.smoothscale(big, (w, h))


class _LiveReader:
    """Liest Capture-Card-Frames in einem Hintergrund-Thread mit Auto-Reconnect.

    Wenn das HDMI-Kabel kurz gezogen wird oder das Capture-Device
    Read-Errors liefert, versucht der Reader das Device alle paar Sekunden
    neu zu öffnen — ohne dass die UI durchgängig 'kein Signal' anzeigt.
    """

    _TARGET_FPS = 30
    _RECONNECT_INTERVAL_S = 3.0
    _MAX_CONSEC_READ_FAILS = 30

    def __init__(self, device: int):
        self._device = device
        self._cap = cv2.VideoCapture(device)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not self._cap.isOpened():
            raise RuntimeError(f"Capture-Device {device} nicht verfügbar")
        self._frame = None
        self._lock = threading.Lock()
        self._running = True
        self._fail_count = 0
        self._last_reconnect = 0.0
        threading.Thread(target=self._loop, daemon=True).start()
        logger.info("LiveReader gestartet (device=%d)", device)

    def _try_reconnect(self):
        now = time.monotonic()
        if now - self._last_reconnect < self._RECONNECT_INTERVAL_S:
            return
        self._last_reconnect = now
        try:
            self._cap.release()
        except Exception:
            pass
        self._cap = cv2.VideoCapture(self._device)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if self._cap.isOpened():
            logger.info("LiveReader: Capture-Device wieder geöffnet")
            self._fail_count = 0
        else:
            logger.debug("LiveReader: Reconnect-Versuch fehlgeschlagen")

    def _loop(self):
        interval = 1.0 / self._TARGET_FPS
        while self._running:
            t0 = time.monotonic()
            try:
                ok, frame = self._cap.read()
            except Exception as exc:
                logger.debug("LiveReader read-Exception: %s", exc)
                ok, frame = False, None

            if ok and frame is not None:
                with self._lock:
                    self._frame = frame
                self._fail_count = 0
            else:
                self._fail_count += 1
                if self._fail_count >= self._MAX_CONSEC_READ_FAILS:
                    self._try_reconnect()

            elapsed = time.monotonic() - t0
            rest = interval - elapsed
            if rest > 0:
                time.sleep(rest)

    def latest(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def close(self):
        self._running = False
        try:
            self._cap.release()
        except Exception:
            pass


class UI:
    """Pygame-UI mit State-Machine für Homescreen, Countdown, Result und Slideshow."""

    def __init__(self, cfg: dict, capture_device: int):
        self._cfg = cfg

        pygame.init()
        self._screen = pygame.display.set_mode((W, H), pygame.FULLSCREEN)
        pygame.display.set_caption("Fotobox")
        pygame.mouse.set_visible(False)

        # Fonts
        self._f_big      = pygame.font.SysFont("sans-serif", 200, bold=True)
        self._f_large    = pygame.font.SysFont("sans-serif", 110, bold=True)
        self._f_medium   = pygame.font.SysFont("sans-serif", 60,  bold=True)
        self._f_normal   = pygame.font.SysFont("sans-serif", 40,  bold=True)
        self._f_small    = pygame.font.SysFont("sans-serif", 26)
        self._f_event    = pygame.font.SysFont("sans-serif", 36,  bold=True)
        self._f_sub      = pygame.font.SysFont("sans-serif", 22)
        self._f_initials = pygame.font.SysFont("sans-serif", 72,  bold=True)
        self._f_label    = pygame.font.SysFont("sans-serif", 18,  bold=True)

        # Theme + Background-Gradient. _apply_theme baut self._bg neu —
        # läuft auch im Live-Reload, wenn der Mieter die Farben ändert.
        self._apply_theme(cfg)

        # Logo — _logo_surf ist die rohe Datei, _logo_circular die runde
        # Variante die in den Cream-Kreis blittet wird.
        self._logo_surf = self._load_logo(cfg.get("logo_path", ""))
        self._logo_circular = (
            self._make_circular_logo(self._logo_surf)
            if self._logo_surf is not None else None
        )

        # Galerie-QR als grosse Card — der Hauptcode. Instagram/Booking
        # bekommen darunter je einen kleineren Code (_draw_social_links);
        # sie sind visuell klar untergeordnet, aber genauso scannbar.
        self._qr_surf = self._make_qr(cfg.get("gallery_url", ""), size=160)

        # Mini-QRs werden lazy erzeugt und ueber die Ziel-URL gecacht —
        # aendert der Owner einen Link, rendert der naechste Frame ihn neu.
        self._mini_qr_cache: dict = {}

        # Live-Reload-Tracking — gallery_server.py teilt config.cfg mit
        # dieser Instanz (siehe main.py: gallery_server.run im Thread).
        # Strings (event_name, subtitle, wifi-Texte) sind sofort sichtbar
        # — nur Logo-Surface, QR und Theme-Gradient müssen wir bei
        # Wert-Änderungen neu rendern.
        self._logo_path_seen    = cfg.get("logo_path", "")
        self._logo_mtime        = self._mtime(self._logo_path_seen)
        self._qr_url_seen       = cfg.get("gallery_url", "")
        self._theme_seen        = dict(cfg.get("theme") or {})
        # Von main.py gesetzt (gecachter CUPS-Zustand aus printing.status()).
        # Steuert, ob der Result-Screen einen Druck-Knopf anbietet.
        self.print_ready        = False
        self._last_reload_check = 0.0

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

        # Result-Screen Cache — gecappt, sonst Memory-Leak nach hunderten Fotos
        self._result_cache: dict = {}
        self._RESULT_CACHE_MAX = 8

        # Live-Reader (Capture-Card)
        self._live: Optional[_LiveReader] = None
        try:
            self._live = _LiveReader(capture_device)
        except Exception as exc:
            logger.warning("Kein Live-Feed: %s", exc)

        # Crop-Cache: Letterbox-Ränder ändern sich praktisch nie, deshalb
        # nur alle CROP_REFRESH_S neu vermessen statt auf jedem Frame.
        self._crop_box: Optional[tuple] = None  # (y0, y1, x0, x1, h, w)
        self._crop_last_ms: int = 0
        self._CROP_REFRESH_MS = 2000

    # ── Öffentliche API ────────────────────────────────────────────────────────

    def check_quit(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return True
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return True
        return False

    @staticmethod
    def _mtime(path: str) -> float:
        try:
            return os.path.getmtime(path)
        except OSError:
            return 0.0

    def _check_config_reload(self):
        """1× pro Sekunde prüfen ob sich gecachte Asset-Dateien oder die
        Galerie-URL geändert haben. Wird vor jedem Render aufgerufen — billig
        durch das 1-Sekunden-Throttle, sodass die Render-Schleife nicht
        bei jedem Frame stat()-Calls macht.
        """
        now = time.monotonic()
        if now - self._last_reload_check < 1.0:
            return
        self._last_reload_check = now

        # Logo — Path und/oder mtime können sich ändern (Upload überschreibt
        # die gleiche Datei, daher reicht Path-Vergleich allein nicht).
        logo_path = self._cfg.get("logo_path", "")
        logo_mt   = self._mtime(logo_path)
        if logo_path != self._logo_path_seen or logo_mt != self._logo_mtime:
            logger.info("Live-Reload: Logo geändert (%s)", logo_path)
            self._logo_surf      = self._load_logo(logo_path)
            self._logo_circular  = (
                self._make_circular_logo(self._logo_surf)
                if self._logo_surf is not None else None
            )
            self._logo_path_seen = logo_path
            self._logo_mtime     = logo_mt

        # Theme — bei Änderung Hintergrund-Gradient + Theme-Farben neu bauen.
        theme_now = dict(self._cfg.get("theme") or {})
        if theme_now != self._theme_seen:
            logger.info("Live-Reload: Theme geändert")
            self._apply_theme(self._cfg)
            self._theme_seen = theme_now

        # QR-Code — neu generieren wenn sich gallery_url ändert (z.B. Port
        # oder hotspot_ip vom Admin verstellt).
        url = self._cfg.get("gallery_url", "")
        if url != self._qr_url_seen:
            logger.info("Live-Reload: gallery_url geändert (%s)", url)
            self._qr_surf     = self._make_qr(url, size=160)
            self._qr_url_seen = url

    # ── Homescreen ─────────────────────────────────────────────────────────────

    def render_homescreen(self, camera_ok: bool, camera_msg: str,
                          free_mb: int, photo_count: int):
        self._check_config_reload()
        self._screen.blit(self._bg, (0, 0))
        self._draw_sidebar_bg()
        self._draw_logo_sidebar()
        self._draw_event_header()
        self._draw_qr_card()
        self._draw_wifi_box()
        self._draw_live_frame_outer()
        self._draw_live()
        self._draw_live_frame()
        self._draw_polaroids()
        self._draw_action_buttons()
        self._draw_status_bar(camera_ok, free_mb, photo_count)
        if not camera_ok:
            self._draw_error_banner(camera_msg or "Kamera nicht erkannt – USB prüfen")
        pygame.display.flip()

    def latest_live_frame(self):
        """Letzter Live-View-Frame (BGR) oder None.

        Wird von der Dev-Kamera genutzt, damit sie kein zweites
        cv2.VideoCapture auf dasselbe Geraet oeffnen muss.
        """
        return self._live.latest() if self._live else None

    def _draw_live(self):
        """Live-Vorschau aus der Capture-Card im konfigurierten live_view_rect.

        Schneidet automatisch schwarze Letterbox-Ränder aus dem HDMI-Signal
        weg und zeigt eine Meldung wenn kein Signal anliegt.
        """
        x, y, w, h = self._cfg.get("live_view_rect", [440, 600, 1040, 450])

        if self._live is None:
            self._draw_no_signal(x, y, w, h)
            return
        frame = self._live.latest()
        if frame is None or frame.max() < 20:
            self._draw_no_signal(x, y, w, h, "Bitte Display an der Kamera einschalten")
            return

        frame = self._crop_black_borders(frame)
        if frame is None:
            self._draw_no_signal(x, y, w, h, "Bitte Display an der Kamera einschalten")
            return

        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        fh, fw = frame.shape[:2]
        scale  = min(w / fw, h / fh)
        nw, nh = int(fw * scale), int(fh * scale)
        frame = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
        # frombuffer ist 3-5x schneller als surfarray.make_surface(swapaxes),
        # weil keine numpy-Achsen-Umordnung und keine Pixelformat-Konvertierung
        # nötig ist — der RGB-Buffer aus cv2.resize wird direkt blittable.
        surf = pygame.image.frombuffer(frame.tobytes(), (nw, nh), "RGB")
        self._screen.blit(surf, (x + (w - nw) // 2, y + (h - nh) // 2))

    def _draw_no_signal(self, x: int, y: int, w: int, h: int,
                        msg: str = "Warte auf Kamera…"):
        lbl = self._f_normal.render(msg, True, C_WHITE)
        self._screen.blit(lbl, lbl.get_rect(center=(x + w // 2, y + h // 2)))

    def _crop_black_borders(self, frame):
        """Schneidet schwarze Ränder aus einem Frame heraus (HDMI-Letterbox).

        Das Crop-Rechteck wird gecached und nur alle _CROP_REFRESH_MS neu
        vermessen — die Letterbox bewegt sich praktisch nie, dafür sparen
        wir auf jedem Frame eine cv2.resize + numpy-Pass (~1 ms auf Pi 4B).
        """
        h, w = frame.shape[:2]
        now_ms = pygame.time.get_ticks()

        cached = self._crop_box
        if (cached is not None
                and cached[4] == h and cached[5] == w
                and now_ms - self._crop_last_ms < self._CROP_REFRESH_MS):
            y0, y1, x0, x1, _, _ = cached
            return frame[y0:y1, x0:x1]

        box = self._measure_crop_box(frame)
        if box is None:
            return None
        y0, y1, x0, x1 = box
        self._crop_box = (y0, y1, x0, x1, h, w)
        self._crop_last_ms = now_ms
        return frame[y0:y1, x0:x1]

    @staticmethod
    def _measure_crop_box(frame):
        """Misst das Crop-Rechteck auf einem 1/8-Downsample (~1 ms auf Pi)."""
        import numpy as np
        h, w = frame.shape[:2]
        small = cv2.resize(frame, (max(1, w // 8), max(1, h // 8)),
                           interpolation=cv2.INTER_AREA)
        gray = small.mean(axis=2)
        mask = gray > 18
        if not mask.any():
            return None
        rows = mask.any(axis=1)
        cols = mask.any(axis=0)
        y_idx = np.where(rows)[0]
        x_idx = np.where(cols)[0]
        y0 = max(0, y_idx[0] * 8)
        y1 = min(h, (y_idx[-1] + 1) * 8)
        x0 = max(0, x_idx[0] * 8)
        x1 = min(w, (x_idx[-1] + 1) * 8)
        if (x1 - x0) < 100 or (y1 - y0) < 100:
            return None
        return (y0, y1, x0, x1)

    def _action_rects(self):
        """Berechnet Position+Rect für jeden konfigurierten Action-Button.
        Buttons werden vertikal gestapelt rechts angeordnet, mittig zur
        Höhe der Live-View, damit sie auf Augenhöhe der Vorschau sitzen.
        """
        actions = self._cfg.get("actions") or []
        if not actions:
            return []
        n = len(actions)
        total_h = n * ACTION_H + (n - 1) * ACTION_GAP

        live = self._cfg.get("live_view_rect", [440, 600, 1040, 450])
        center_y = live[1] + live[3] // 2
        y0 = max(80, center_y - total_h // 2)

        return [(action,
                 pygame.Rect(ACTION_X, y0 + i * (ACTION_H + ACTION_GAP),
                             ACTION_W, ACTION_H))
                for i, action in enumerate(actions)]

    def _draw_action_buttons(self):
        """Action-Buttons mit pro-Action Akzentfarbe und modernem Look:
        - Filled (Foto): nur Fläche, ohne Border, weisser Text
        - Outline: dünner 2-px-Border, farbiger Text
        - Label zentriert, dezenter Chevron rechts als Hinweis
        - Weicher Schatten unter dem Button für Tiefe
        """
        keys  = pygame.key.get_pressed()
        panel = self._theme["panel_bg"]
        text  = self._theme["text"]

        for action, rect in self._action_rects():
            pg_key  = _ACTION_KEYS.get(action.get("key", ""))
            pressed = bool(pg_key and keys[pg_key])
            color   = _hex_to_rgb(action.get("color", ""),
                                  self._theme["accent"])
            filled  = bool(action.get("filled", False))

            # AA-Maske einmal pro Button bauen — wird für Schatten,
            # Body und Outline wiederverwendet, sodass alle drei Layer
            # exakt denselben weichen Rand teilen.
            aa_mask = _aa_round_rect_mask(rect.width, rect.height,
                                          ACTION_RADIUS)

            # Weicher Schatten — zwei Layer für mehr Tiefe ohne harte Kante.
            for offset_y, alpha in ((4, 35), (8, 25)):
                shadow = pygame.Surface((rect.width, rect.height),
                                        pygame.SRCALPHA)
                shadow.fill((0, 0, 0, alpha))
                shadow.blit(aa_mask, (0, 0),
                            special_flags=pygame.BLEND_RGBA_MIN)
                self._screen.blit(shadow, (rect.x, rect.y + offset_y))

            # Hauptkörper mit Theme-Farbe.
            bg = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            if filled or pressed:
                bg.fill((*color, 245))
                label_color = text
            else:
                bg.fill((*panel, 240))
                label_color = color
            bg.blit(aa_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            self._screen.blit(bg, rect.topleft)

            # Outline-Buttons bekommen einen dünnen Border, Filled keinen
            # — sonst wirkt der Button doppelt umrandet. AA über die
            # gleiche Supersample-Maske, damit die Border-Ecken sauber sind.
            if not (filled or pressed):
                outline = pygame.Surface((rect.width, rect.height),
                                         pygame.SRCALPHA)
                pygame.draw.rect(outline, (*color, 255),
                                 outline.get_rect(),
                                 width=2, border_radius=ACTION_RADIUS)
                outline.blit(aa_mask, (0, 0),
                             special_flags=pygame.BLEND_RGBA_MIN)
                self._screen.blit(outline, rect.topleft)

            # Label zentriert
            label = action.get("label", "Aktion")
            lbl = self._f_medium.render(label, True, label_color)
            self._screen.blit(lbl, lbl.get_rect(center=rect.center))

            # Chevron rechts — kleiner und dünner als vorher, nur als Akzent.
            cx = rect.right - 28
            cy = rect.centery
            ch = 12
            pygame.draw.lines(
                self._screen, label_color, False,
                [(cx - 9, cy - ch), (cx, cy), (cx - 9, cy + ch)],
                width=3,
            )

            if pressed:
                self._draw_button_glow(rect, color)

    def _draw_button_glow(self, rect: pygame.Rect, color=None):
        if color is None:
            color = self._theme["accent"]
        glow = pygame.Surface((rect.width + 40, rect.height + 40), pygame.SRCALPHA)
        for i in range(8, 0, -1):
            alpha = 30 + (8 - i) * 10
            pygame.draw.rect(
                glow, (*color, alpha),
                glow.get_rect().inflate(-i * 4, -i * 4),
                width=4, border_radius=ACTION_RADIUS,
            )
        self._screen.blit(glow, (rect.x - 20, rect.y - 20))

    # ── Theme / Hintergrund ────────────────────────────────────────────────────

    def _apply_theme(self, cfg: dict):
        """Liest theme aus cfg, parst Hex-Strings zu RGB und baut den
        Hintergrund-Gradient. Wird beim Init und bei jedem Live-Reload mit
        geänderten Theme-Werten aufgerufen.
        """
        t = cfg.get("theme") or {}
        self._theme = {
            "bg_top":         _hex_to_rgb(t.get("bg_top",         "#D5BB99"), (213, 187, 153)),
            "bg_bottom":      _hex_to_rgb(t.get("bg_bottom",      "#B89A75"), (184, 154, 117)),
            "sidebar_bg":     _hex_to_rgb(t.get("sidebar_bg",     "#3D2818"), (61,  40,  24)),
            "sidebar_text":   _hex_to_rgb(t.get("sidebar_text",   "#FFFFFF"), C_WHITE),
            "sidebar_dim":    _hex_to_rgb(t.get("sidebar_dim",    "#A09080"), (160, 144, 128)),
            "logo_circle":    _hex_to_rgb(t.get("logo_circle",    "#F5EBD8"), (245, 235, 216)),
            "logo_text":      _hex_to_rgb(t.get("logo_text",      "#A36B3F"), (163, 107, 63)),
            "panel_bg":       _hex_to_rgb(t.get("panel_bg",       "#1F1812"), (31,  24,  18)),
            "panel_border":   _hex_to_rgb(t.get("panel_border",   "#7A5A35"), (122, 90,  53)),
            "polaroid_frame": _hex_to_rgb(t.get("polaroid_frame", "#FAEED9"), (250, 238, 217)),
            "polaroid_pin":   _hex_to_rgb(t.get("polaroid_pin",   "#C24838"), (194, 72,  56)),
            "live_bg":        _hex_to_rgb(t.get("live_bg",        "#1A140F"), (26,  20,  15)),
            "live_outer":     _hex_to_rgb(t.get("live_outer",     "#5A3A1C"), (90,  58,  28)),
            "live_inner":     _hex_to_rgb(t.get("live_inner",     "#C9A06A"), (201, 160, 106)),
            "accent":         _hex_to_rgb(t.get("accent",         "#D4A86A"), C_GOLD),
            "accent_dim":     _hex_to_rgb(t.get("accent_dim",     "#9B7840"), C_DIM),
            "text":           _hex_to_rgb(t.get("text",           "#FFFFFF"), C_WHITE),
            "panel_alpha":    int(t.get("panel_alpha", 255)),
        }
        self._bg = self._build_gradient_bg()
        # Polaroid-Cache invalidieren — Frame-Farbe ist Theme-abhängig.
        rot_cache = getattr(self, "_rot_cache", None)
        if rot_cache is not None:
            rot_cache.clear()

    def _build_gradient_bg(self) -> pygame.Surface:
        """Vertikaler Gradient bg_top → bg_bottom — ersetzt das frühere
        Overlay-PNG. Wird 1× pro Theme-Änderung gebaut, nicht pro Frame.
        """
        surf = pygame.Surface((W, H))
        top = self._theme["bg_top"]
        bot = self._theme["bg_bottom"]
        for y in range(H):
            t = y / (H - 1)
            c = (int(top[0] * (1 - t) + bot[0] * t),
                 int(top[1] * (1 - t) + bot[1] * t),
                 int(top[2] * (1 - t) + bot[2] * t))
            pygame.draw.line(surf, c, (0, y), (W, y))
        return surf

    # ── Sidebar / Header / Live-Frame ──────────────────────────────────────────

    def _draw_sidebar_bg(self):
        """Vollflächige dunkle Sidebar — klarer Cut zum Hintergrund, kein Akzent."""
        pygame.draw.rect(self._screen, self._theme["sidebar_bg"],
                         (0, 0, SIDEBAR_W, H))

    def _draw_logo_sidebar(self):
        """Logo als kreisförmiger Cream-Container oben in der Sidebar.
        Hochgeladene Logos werden zirkulär maskiert (cover-Skalierung), damit
        rechteckige Logos sauber in den Kreis passen. Wenn weder ein hoch-
        geladenes Logo noch das Default-Logo (Layout/logo_default.png)
        existiert, fallen wir auf Initialen aus dem Event-Namen zurück.
        """
        cx = SIDEBAR_W // 2
        cy = SIDEBAR_PAD + LOGO_CIRCLE_R
        circle_color = self._theme["logo_circle"]

        # Cream-Kreis als Hintergrund — bleibt rund auch wenn das Logo
        # transparente Bereiche hat. AA-Kontur, sonst Pixeltreppe am Rand.
        _aa_filled_circle(self._screen, circle_color, cx, cy, LOGO_CIRCLE_R)

        if self._logo_circular is not None:
            self._screen.blit(
                self._logo_circular,
                self._logo_circular.get_rect(center=(cx, cy)),
            )
        else:
            # Letzter Fallback: Initialen aus dem Event-Namen.
            initials = self._event_initials(self._cfg.get("event_name", ""))
            lbl = self._f_initials.render(initials, True, self._theme["logo_text"])
            self._screen.blit(lbl, lbl.get_rect(center=(cx, cy)))

    @staticmethod
    def _event_initials(name: str) -> str:
        """'Hochzeit Müller' → 'HM', 'Fotobox' → 'FB'. Maximal 2 Buchstaben."""
        words = (name or "").strip().split()
        if not words:
            return "FB"
        if len(words) == 1:
            return words[0][:2].upper()
        return (words[0][0] + words[1][0]).upper()

    def _draw_event_header(self):
        """Event-Name + Subtitle (z.B. Datum) in der Sidebar unter dem Logo."""
        cx = SIDEBAR_W // 2
        y  = SIDEBAR_PAD + LOGO_CIRCLE_R * 2 + 24

        event_name = (self._cfg.get("event_name") or "").strip()
        subtitle   = (self._cfg.get("subtitle")   or "").strip()
        max_w      = SIDEBAR_W - 30

        for text, font, color in (
            (event_name, self._f_event, self._theme["sidebar_text"]),
            (subtitle,   self._f_sub,   self._theme["sidebar_dim"]),
        ):
            if not text:
                continue
            lbl = font.render(text, True, color)
            if lbl.get_width() > max_w:
                scale = max_w / lbl.get_width()
                lbl = pygame.transform.smoothscale(
                    lbl, (int(lbl.get_width() * scale),
                          int(lbl.get_height() * scale)))
            self._screen.blit(lbl, lbl.get_rect(centerx=cx, top=y))
            y += lbl.get_height() + 8

    def _draw_live_frame_outer(self):
        """Brauner Aussenrahmen + dunkler Backing-Block. Wird VOR dem
        Live-Bild gezeichnet, damit der Rahmen als Frame fungiert und
        der Backing-Block bei 'kein Signal' den dunklen Bereich liefert.
        """
        x, y, w, h = self._cfg.get("live_view_rect", [440, 600, 1040, 450])
        outer = pygame.Rect(x - LIVE_OUTER_W, y - LIVE_OUTER_W,
                            w + 2 * LIVE_OUTER_W, h + 2 * LIVE_OUTER_W)
        pygame.draw.rect(self._screen, self._theme["live_outer"],
                         outer, border_radius=14)
        pygame.draw.rect(self._screen, self._theme["live_bg"],
                         pygame.Rect(x, y, w, h), border_radius=6)

    def _draw_live_frame(self):
        """Innerer Goldakzent — NACH dem Live-Bild gezeichnet, sitzt als
        dezenter Strich auf dem Bildrand.
        """
        x, y, w, h = self._cfg.get("live_view_rect", [440, 600, 1040, 450])
        pygame.draw.rect(self._screen, self._theme["live_inner"],
                         pygame.Rect(x, y, w, h),
                         width=LIVE_INNER_W, border_radius=6)

    def _draw_status_bar(self, camera_ok: bool, free_mb: int, photo_count: int):
        bar = pygame.Surface((W, 28), pygame.SRCALPHA)
        bar.fill((0, 0, 0, 160))
        self._screen.blit(bar, (0, H - 28))

        cam_color = C_GREEN if camera_ok else C_RED
        cam_text  = "Kamera: OK" if camera_ok else "Kamera: FEHLT"
        items = [
            (cam_text, cam_color),
            (self._disk_label(free_mb), self._disk_color(free_mb)),
            (f"Fotos: {photo_count}", C_DIM),
            ("Hotspot: aktiv" if self._cfg.get("hotspot_enabled") else "Hotspot: aus", C_DIM),
        ]
        x = 20
        for text, color in items:
            lbl = self._f_small.render(text, True, color)
            self._screen.blit(lbl, (x, H - 24))
            x += lbl.get_width() + 60

    def _disk_label(self, free_mb: int) -> str:
        if free_mb < 0:
            return "Speicher: ?"
        return (f"Speicher: {free_mb / 1024:.1f} GB" if free_mb >= 1024
                else f"Speicher: {free_mb} MB")

    def _disk_color(self, free_mb: int):
        """Drei Stufen statt zwei: unter disk_block_mb nimmt die Box gar keine
        Fotos mehr auf — das muss deutlicher aussehen als eine Warnung."""
        if free_mb < 0:
            return C_DIM
        if free_mb < self._cfg.get("disk_block_mb", 150):
            return C_RED
        if free_mb < self._cfg.get("disk_warn_mb", 500):
            return C_YELLOW
        return C_DIM

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

    def wait_for_capture(self, done, timeout: float = 35.0,
                         message: str = "Foto wird übertragen…") -> bool:
        """Haelt die Render-Schleife am Leben, waehrend gphoto2 laeuft.

        Vorher wartete main.py hier blockierend — der Bildschirm stand bis zu
        35 s auf dem letzten "Lächeln!"-Frame, ohne jedes Lebenszeichen. Der
        Gast konnte nicht unterscheiden, ob die Box arbeitet oder haengt.

        Rueckgabe: True wenn `done` rechtzeitig gesetzt wurde, sonst False.
        """
        deadline = time.monotonic() + timeout
        dots = 0
        while not done.is_set():
            if time.monotonic() >= deadline:
                return False
            self._draw_live_fullscreen()
            shade = pygame.Surface((W, H), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 150))
            self._screen.blit(shade, (0, 0))
            lbl = self._f_medium.render(message, True, C_WHITE)
            self._screen.blit(lbl, lbl.get_rect(center=(W // 2, H // 2 - 30)))
            # Laufende Punkte als Lebenszeichen — reicht, um "arbeitet" von
            # "eingefroren" zu unterscheiden.
            dots = (dots + 1) % 60
            pips = "•" * (1 + dots // 20)
            pip = self._f_large.render(pips, True, C_GOLD)
            self._screen.blit(pip, pip.get_rect(center=(W // 2, H // 2 + 70)))
            pygame.display.flip()
            pygame.event.pump()
            pygame.time.wait(30)
        return True

    def show_notice(self, title: str, detail: str = "",
                    seconds: float = 3.5, error: bool = True) -> None:
        """Vollflaechiger Hinweis fuer den Gast (blockierend).

        Ohne das laeuft bei einem Kamera-Fehler der Countdown, der Blitz feuert
        — und dann passiert sichtbar nichts. Die einzige Spur war eine Zeile im
        Log, die am Event-Abend niemand liest.
        """
        accent = C_RED if error else C_GREEN
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self._screen.fill((12, 8, 4))
            box = pygame.Rect(0, 0, 1200, 380)
            box.center = (W // 2, H // 2)
            pygame.draw.rect(self._screen, (28, 20, 12), box, border_radius=28)
            pygame.draw.rect(self._screen, accent, box, width=5, border_radius=28)
            lbl = self._f_medium.render(title, True, C_WHITE)
            self._screen.blit(lbl, lbl.get_rect(center=(W // 2, H // 2 - 55)))
            if detail:
                sub = self._f_normal.render(detail, True, C_DIM)
                self._screen.blit(sub, sub.get_rect(center=(W // 2, H // 2 + 35)))
            left = max(0.0, end - time.monotonic())
            bar_w = int(box.width * (left / seconds)) if seconds > 0 else 0
            pygame.draw.rect(self._screen, accent,
                             (box.left, box.bottom - 8, bar_w, 8),
                             border_bottom_left_radius=28)
            pygame.display.flip()
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
        self._check_config_reload()
        self._screen.fill((10, 6, 2))
        self._draw_result_photo(photo_path)
        self._draw_qr_result()
        self._draw_result_buttons(time_left)
        pygame.display.flip()

    def _draw_result_photo(self, path: str):
        surf = self._result_surface(path)
        if surf is not None:
            self._screen.blit(surf, (0, 0))

    def _result_surface(self, path: str):
        """Fertig komponiertes Vollbild: unscharfer Hintergrund + scharfes Foto.

        Wird pro Pfad gecacht, sodass pro Frame nur noch ein einziger Blit
        anfaellt — auf dem Pi merklich billiger als jedes Mal neu skalieren.
        """
        if path in self._result_cache:
            return self._result_cache[path]

        try:
            img = pygame.image.load(path).convert()
        except Exception as exc:
            logger.warning("Result-Foto: %s", exc)
            return None

        iw, ih = img.get_width(), img.get_height()
        canvas = pygame.Surface((W, H))

        # Hintergrund: dasselbe Foto stark weichgezeichnet und abgedunkelt,
        # damit an den Seiten keine harten schwarzen Balken stehen. Der Blur
        # ist ein Down-/Upscale — pygame.transform.gaussian_blur gibt es nicht
        # in jedem Build und waere hier deutlich teurer.
        small = pygame.transform.smoothscale(img, (max(1, W // 24), max(1, H // 24)))
        canvas.blit(pygame.transform.smoothscale(small, (W, H)), (0, 0))
        shade = pygame.Surface((W, H))
        shade.fill((0, 0, 0))
        shade.set_alpha(130)
        canvas.blit(shade, (0, 0))

        # Vordergrund: contain statt cover — das komplette Foto bleibt sichtbar,
        # es wird also niemandem der Kopf abgeschnitten.
        fit = min(W / iw, H / ih)
        nw, nh = max(1, int(iw * fit)), max(1, int(ih * fit))
        sharp = pygame.transform.smoothscale(img, (nw, nh))
        canvas.blit(sharp, sharp.get_rect(center=(W // 2, H // 2)))

        self._result_cache[path] = canvas
        # Cap: älteste Einträge wegwerfen damit der Cache nicht endlos wächst
        while len(self._result_cache) > self._RESULT_CACHE_MAX:
            oldest = next(iter(self._result_cache))
            self._result_cache.pop(oldest, None)
        return canvas

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

    _SCRIM_H = 300

    def _result_scrim(self):
        """Schwarzer Verlauf von transparent nach unten hin deckend.

        Einmal gebaut und gecacht — die Buttons liegen jetzt direkt auf dem
        Foto, und ohne Scrim waeren sie auf hellen Aufnahmen unlesbar.
        """
        if getattr(self, "_scrim_surf", None) is None:
            scrim = pygame.Surface((W, self._SCRIM_H), pygame.SRCALPHA)
            for i in range(self._SCRIM_H):
                # Exponent flacher als quadratisch, damit schon die Timer-Zeile
                # oberhalb der Buttons abgedunkelt wird — auf einem hellen Foto
                # war der goldene Text dort sonst praktisch unlesbar.
                a = int(245 * (i / self._SCRIM_H) ** 1.3)
                pygame.draw.line(scrim, (0, 0, 0, a), (0, i), (W, i))
            self._scrim_surf = scrim
        return self._scrim_surf

    def _draw_result_buttons(self, time_left: float):
        self._screen.blit(self._result_scrim(), (0, H - self._SCRIM_H))
        keys = pygame.key.get_pressed()
        btn_w, btn_h = 340, 72
        gap = 60
        # Der Druck-Knopf erscheint nur, wenn CUPS einen bereiten Drucker
        # kennt. Vorher stand "Drucken" immer da und tat sichtbar nichts,
        # solange kein Drucker eingerichtet war — schlimmer als kein Knopf.
        n_btn = 3 if self.print_ready else 2
        total_w = n_btn * btn_w + (n_btn - 1) * gap
        sx = (W - total_w) // 2
        by = H - btn_h - 20

        # Timer
        timer = self._f_small.render(f"Zurück in {max(0, int(time_left)) + 1}s",
                                     True, C_WHITE)
        self._screen.blit(timer, timer.get_rect(centerx=W // 2, bottom=by - 10))

        # Pfeile werden gezeichnet statt als '←'/'→' gesetzt: pygame findet
        # fuer SysFont('sans-serif') keinen Treffer (weder in Sysfonts noch in
        # Sysalias — nur 'sans' waere ein Alias) und faellt deshalb auf das
        # gebundelte freesansbold.ttf zurueck. Dem fehlen die Pfeil-Glyphen,
        # es erschien nur ein .notdef-Kaestchen — auf dem Pi genauso wie auf
        # der Dev-Maschine, weil die Fontdatei im pygame-Paket liegt.
        ARROW_SIZE, ARROW_GAP = 22, 14
        defs = [
            ("Zurück",  "left",  "Q",     keys[pygame.K_q]),
            ("Nochmal", None,    "Space", keys[pygame.K_SPACE]),
        ]
        if self.print_ready:
            defs.append(("Drucken", "right", "E", keys[pygame.K_e]))
        for i, (label, arrow, key_hint, hl) in enumerate(defs):
            rect = pygame.Rect(sx + i * (btn_w + gap), by, btn_w, btn_h)
            color = C_BTN_HL if hl else C_BTN_BG
            pygame.draw.rect(self._screen, color, rect, border_radius=12)
            pygame.draw.rect(self._screen, C_GOLD, rect, width=2, border_radius=12)

            fg  = C_WHITE if hl else C_GOLD
            lbl = self._f_normal.render(label, True, fg)
            ly  = rect.centery - 10
            # Pfeil + Text als Gruppe zentrieren, damit die Beschriftung nicht
            # gegenueber den Buttons ohne Pfeil verrutscht.
            group_w = lbl.get_width() + (ARROW_SIZE + ARROW_GAP if arrow else 0)
            gx = rect.centerx - group_w // 2
            if arrow == "left":
                self._draw_arrow(gx + ARROW_SIZE // 2, ly, ARROW_SIZE, fg, "left")
                self._screen.blit(lbl, lbl.get_rect(midleft=(gx + ARROW_SIZE + ARROW_GAP, ly)))
            else:
                self._screen.blit(lbl, lbl.get_rect(midleft=(gx, ly)))
                if arrow == "right":
                    self._draw_arrow(gx + lbl.get_width() + ARROW_GAP + ARROW_SIZE // 2,
                                     ly, ARROW_SIZE, fg, "right")

            hint = self._f_small.render(f"[ {key_hint} ]", True, C_DIM)
            self._screen.blit(hint, hint.get_rect(centerx=rect.centerx, centery=rect.centery + 20))

    def _draw_arrow(self, cx: int, cy: int, size: int, color, pointing: str):
        """Gefuelltes Dreieck als Pfeil — schriftunabhaengig und damit auf
        Dev-Maschine und Pi garantiert deckungsgleich."""
        h, w = size, int(size * 0.78)
        if pointing == "left":
            pts = [(cx + w // 2, cy - h // 2), (cx + w // 2, cy + h // 2), (cx - w // 2, cy)]
        else:
            pts = [(cx - w // 2, cy - h // 2), (cx - w // 2, cy + h // 2), (cx + w // 2, cy)]
        pygame.draw.polygon(self._screen, color, pts)

    # ── USB-Export-Overlay ─────────────────────────────────────────────────────

    def render_usb_overlay(self, status: dict):
        """Vollbild-Overlay während ein USB-Stick-Export läuft.

        status: {state, current, total, message}  — geliefert von usb_export.py
        """
        state    = status.get("state", "")
        current  = int(status.get("current") or 0)
        total    = int(status.get("total")   or 0)
        message  = status.get("message", "") or ""

        if state == "copying":
            title       = "Fotos werden auf USB kopiert"
            color       = C_GOLD
            sub_text    = f"{current} / {total}"
            hint        = message[-50:] if message else "bitte Stick stecken lassen"
        elif state == "done":
            title       = "Fertig"
            color       = C_GREEN
            sub_text    = f"{current} / {total}" if total else ""
            hint        = "Stick kann jetzt entnommen werden"
        elif state == "error":
            title       = "Fehler"
            color       = C_RED
            sub_text    = ""
            hint        = message or "Stick prüfen oder neu einstecken"
        else:  # mounting / unbekannt
            title       = "USB-Stick erkannt"
            color       = C_GOLD
            sub_text    = ""
            hint        = message or "wird vorbereitet …"

        # Verdunkelnder Hintergrund
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 220))
        self._screen.blit(overlay, (0, 0))

        # Titel
        title_surf = self._f_large.render(title, True, color)
        self._screen.blit(title_surf, title_surf.get_rect(center=(W // 2, H // 2 - 180)))

        # Counter
        if sub_text:
            ct = self._f_big.render(sub_text, True, C_WHITE)
            self._screen.blit(ct, ct.get_rect(center=(W // 2, H // 2 - 20)))

        # Progress-Bar (nur bei copying mit total > 0 oder done)
        if state in ("copying", "done") and total > 0:
            bar_w = 900
            bar_h = 22
            bar_x = (W - bar_w) // 2
            bar_y = H // 2 + 130
            pct = max(0.0, min(1.0, current / total))
            pygame.draw.rect(self._screen, C_BTN_BG,
                             (bar_x, bar_y, bar_w, bar_h),
                             border_radius=11)
            fill_w = int(bar_w * pct)
            if fill_w > 0:
                pygame.draw.rect(self._screen, color,
                                 (bar_x, bar_y, fill_w, bar_h),
                                 border_radius=11)

        # Hinweis-Zeile
        if hint:
            hsurf = self._f_normal.render(hint, True, C_DIM)
            self._screen.blit(hsurf, hsurf.get_rect(center=(W // 2, H // 2 + 220)))

        pygame.display.flip()

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
        self._check_config_reload()
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
                self._rot_cache[(path, angle)] = pygame.transform.rotozoom(
                    surf, angle, 1.0)
        except Exception as exc:
            logger.warning("Polaroid-Ladefehler: %s", exc)

        # Cache-Hygiene: alles wegwerfen was nicht mehr in der Polaroid-deque ist.
        # Sonst wachsen _photo_cache/_rot_cache linear mit der Anzahl Fotos.
        active = set(self._gallery)
        for p in [p for p in self._photo_cache if p not in active]:
            self._photo_cache.pop(p, None)
            self._fade_start.pop(p, None)
        for key in [k for k in self._rot_cache if k[0] not in active]:
            self._rot_cache.pop(key, None)

    def _draw_polaroids(self):
        photos = list(self._gallery)
        for i, (cx, cy, angle) in enumerate(self._frames):
            if i < len(photos):
                path        = photos[i]
                photo       = self._photo_cache.get(path)
                alpha       = self._photo_alpha(path)
                placeholder = None
            else:
                path        = None
                photo       = None
                alpha       = 255
                placeholder = _PLACEHOLDER_COLORS[i % len(_PLACEHOLDER_COLORS)]
            self._draw_polaroid(cx, cy, angle, path, photo, alpha, placeholder)

    def _photo_alpha(self, path: str) -> int:
        if path not in self._fade_start:
            return 255
        elapsed = pygame.time.get_ticks() - self._fade_start[path]
        return min(255, int(elapsed / self._FADE_MS * 255))

    def _draw_polaroid(self, cx, cy, angle, path, photo, alpha,
                       placeholder=None):
        """Zeichnet ein Polaroid mit Cream-Frame, Pin oben und Schatten.
        Wenn photo=None und placeholder gesetzt ist, wird der Foto-Bereich
        mit einer Pastellfarbe gefüllt — Hint, dass dort später Fotos
        erscheinen werden.
        """
        if photo is None and placeholder is None:
            return

        cache_key = (path, angle) if photo is not None else (placeholder, angle)
        rotated = self._rot_cache.get(cache_key)
        if rotated is None:
            rotated = self._build_polaroid(photo, placeholder, angle)
            self._rot_cache[cache_key] = rotated

        # Schatten — separat rotieren, damit er zur Polaroid-Verkippung passt.
        fw = self._PW + POLAROID_PAD_LR * 2
        fh = self._PH + POLAROID_PAD_TOP + POLAROID_PAD_BOT
        shadow = pygame.Surface((fw, fh), pygame.SRCALPHA)
        pygame.draw.rect(shadow, (0, 0, 0, 90),
                         shadow.get_rect(), border_radius=4)
        shadow = pygame.transform.rotozoom(shadow, angle, 1.0)
        self._screen.blit(shadow,
                          shadow.get_rect(center=(cx + 6, cy + 10)))

        if alpha < 255:
            rotated = rotated.copy()
            rotated.set_alpha(alpha)
        self._screen.blit(rotated, rotated.get_rect(center=(cx, cy)))

    def _build_polaroid(self, photo, placeholder, angle):
        """Baut ein einzelnes Polaroid: Cream-Frame, Foto/Platzhalter,
        roter Pin oben — und rotiert es um angle Grad. Wird vom Aufrufer
        gecached, also keine Optimierung nötig."""
        fw = self._PW + POLAROID_PAD_LR * 2
        fh = self._PH + POLAROID_PAD_TOP + POLAROID_PAD_BOT

        frame = pygame.Surface((fw, fh), pygame.SRCALPHA)
        pygame.draw.rect(frame, self._theme["polaroid_frame"],
                         (0, 0, fw, fh), border_radius=2)

        photo_rect = pygame.Rect(POLAROID_PAD_LR, POLAROID_PAD_TOP,
                                 self._PW, self._PH)
        if photo is not None:
            frame.blit(photo, photo_rect.topleft)
        else:
            pygame.draw.rect(frame, placeholder, photo_rect)

        # Pin oben — kleiner roter Kreis mit Schatten + Highlight, AA-Kanten.
        pin_cx = fw // 2
        pin_cy = POLAROID_PIN_R + 6
        _aa_filled_circle(frame, (0, 0, 0, 100),
                          pin_cx + 1, pin_cy + 2, POLAROID_PIN_R)
        _aa_filled_circle(frame, self._theme["polaroid_pin"],
                          pin_cx, pin_cy, POLAROID_PIN_R)
        _aa_filled_circle(frame, (255, 255, 255, 140),
                          pin_cx - 3, pin_cy - 3, max(2, POLAROID_PIN_R // 3))

        # rotozoom statt rotate: gefilterte (smoothscale-basierte) Rotation.
        # rotate gibt nearest-neighbour-Pixeltreppen am gedrehten Rand —
        # rotozoom blendet die Pixel weich, kein Aliasing mehr.
        return pygame.transform.rotozoom(frame, angle, 1.0)

    # ── Live-View ──────────────────────────────────────────────────────────────

    def _draw_live_fullscreen(self):
        self._screen.fill(C_BLACK)
        if self._live is None:
            return
        frame = self._live.latest()
        if frame is None or frame.max() < 20:
            return
        frame = self._crop_black_borders(frame)
        if frame is None:
            return
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        fh, fw = frame.shape[:2]
        scale = min(W / fw, H / fh)
        nw, nh = int(fw * scale), int(fh * scale)
        frame = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
        surf = pygame.image.frombuffer(frame.tobytes(), (nw, nh), "RGB")
        self._screen.blit(surf, ((W - nw) // 2, (H - nh) // 2))

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

    # Layout-Anker für die Sidebar — gemeinsame Berechnung, sodass QR-Card
    # und WLAN-Box konsistent positioniert sind und sich nicht überlappen
    # können, egal welche Inhalte konfiguriert sind.

    def _sidebar_header_bottom(self) -> int:
        """y-Position direkt unterhalb des Event-Headers (Logo + Name + Sub)."""
        y = SIDEBAR_PAD + LOGO_CIRCLE_R * 2 + 24
        if (self._cfg.get("event_name") or "").strip():
            y += self._f_event.get_height() + 8
        if (self._cfg.get("subtitle") or "").strip():
            y += self._f_sub.get_height() + 8
        return y

    def _wifi_box_metrics(self) -> tuple:
        """Liefert (top_y, height) der WLAN-Box. Nicht-konfigurierte Box
        liefert (H, 0) — dann gibt es nichts zu vermeiden."""
        ssid = (self._cfg.get("wifi_ssid")     or "").strip()
        pwd  = (self._cfg.get("wifi_password") or "").strip()
        rows = (1 if ssid else 0) + (1 if pwd else 0)
        if rows == 0:
            return (H, 0)
        line_h  = self._f_normal.get_height()
        label_h = self._f_label.get_height()
        box_h   = 22 + rows * (label_h + 4 + line_h + 14)
        margin_bottom = 56
        return (H - margin_bottom - box_h, box_h)

    def _qr_group_height(self) -> int:
        """Gesamthöhe der QR-Group: Card + Caption + (optional) Mini-QR-Reihen."""
        caption_h = self._f_sub.get_height() + 12
        rows = self._social_rows()
        social_h = 0
        if rows:
            # Reihenhöhen aus den echten Surfaces — _make_qr rundet auf ganze
            # Module auf, die Kachel ist also nicht exakt SOCIAL_QR_SIZE hoch.
            social_h = 16 + sum(self._social_row_height(surf)
                                for surf, _, _ in rows)
        return self._qr_card_size() + caption_h + social_h

    def _sidebar_qr_y(self) -> int:
        """y-Start der QR-Card. Vertikal zentriert zwischen Header und
        WLAN-Box, damit die Sidebar visuell ausgewogen wirkt.
        """
        top    = self._sidebar_header_bottom() + 20
        bottom = self._wifi_box_metrics()[0] - 30
        total  = self._qr_group_height()
        y      = top + ((bottom - top) - total) // 2
        return max(top, y)

    _QR_CARD_PAD = 14

    def _qr_card_size(self) -> int:
        """Kantenlänge der Galerie-QR-Card. Der Code selbst ist nicht exakt
        160 px gross — _make_qr rundet auf ganze Module auf, damit keine
        Modulspalte beim Skalieren ein Pixel breiter wird als die nächste."""
        qr = self._qr_surf.get_width() if self._qr_surf is not None else 160
        return qr + self._QR_CARD_PAD * 2

    def _draw_qr_card(self):
        """QR auf cremig-weißem Container in der Sidebar — vertikal mittig.
        Caption und Mini-QRs werden direkt darunter gezeichnet.
        """
        cx = SIDEBAR_W // 2
        PAD    = self._QR_CARD_PAD
        card_w = card_h = self._qr_card_size()
        y = self._sidebar_qr_y()

        card = pygame.Rect(cx - card_w // 2, y, card_w, card_h)
        pygame.draw.rect(self._screen, self._theme["logo_circle"],
                         card, border_radius=10)

        if self._qr_surf is not None:
            self._screen.blit(self._qr_surf,
                              (card.x + PAD, card.y + PAD))
        else:
            err = self._f_small.render("QR fehlt", True, self._theme["panel_bg"])
            self._screen.blit(err, err.get_rect(center=card.center))

        hint = self._f_sub.render("Fotos auf's Handy", True,
                                  self._theme["sidebar_text"])
        hint_y = card.bottom + 12
        self._screen.blit(hint, hint.get_rect(centerx=cx, top=hint_y))

        self._draw_social_links(cx, hint_y + hint.get_height() + 16)

    def _link_url(self, slug: str, cfg_key: str) -> str:
        """Ziel-URL für einen Mini-QR.

        Default ist der lokale Kurzlink auf /go/<slug> (gallery_server.go_link)
        statt der nackten Ziel-URL. Grund: hotspot.py biegt per
        'address=/#/<ip>' jede DNS-Anfrage auf die Box um — ein QR mit
        'https://…' läuft also für jeden Gast, der gerade im Fotobox-WLAN
        hängt, in einen Verbindungsfehler. Die /go/-Seite ist dagegen eine
        reine IP-URL über http, geht immer auf und leitet selbst weiter,
        sobald das Handy Internet hat.

        qr_link_mode="direct" packt stattdessen die Ziel-URL direkt in den
        Code — nur sinnvoll, wenn die Gäste typischerweise nicht im
        Fotobox-WLAN sind.
        """
        target = (self._cfg.get(cfg_key) or "").strip()
        if not target:
            return ""
        if self._cfg.get("qr_link_mode", "local") != "local":
            return target
        base = (self._cfg.get("gallery_url") or "").rstrip("/")
        return f"{base}/go/{slug}" if base else target

    def _mini_qr(self, url: str):
        """Gecachte Mini-QR-Surface. Der Cache hängt an der URL, sodass ein
        geänderter Link im nächsten Frame automatisch neu gerendert wird."""
        if url not in self._mini_qr_cache:
            if len(self._mini_qr_cache) > 8:
                self._mini_qr_cache.clear()
            # border=2 statt der üblichen 4 Module: den Rest der Quiet-Zone
            # liefert der Cremerand der Kachel. Auf ~85 px zählt jedes Modul.
            self._mini_qr_cache[url] = self._make_qr(
                url, size=SOCIAL_QR_SIZE, border=2, low_ecc=True)
        return self._mini_qr_cache[url]

    def _social_rows(self) -> list:
        """[(qr_surface, icon_type, label)] für die konfigurierten Links."""
        rows = []
        insta = self._link_url("instagram", "instagram_url")
        if insta:
            rows.append((self._mini_qr(insta), "instagram",
                         self._instagram_handle(
                             self._cfg.get("instagram_url") or "")))
        booking = self._link_url("termin", "booking_url")
        if booking:
            label = (self._cfg.get("booking_label") or "").strip()
            rows.append((self._mini_qr(booking), "calendar",
                         label or "Termin buchen"))
        return rows

    @staticmethod
    def _social_row_height(surf) -> int:
        h = surf.get_height() if surf is not None else SOCIAL_QR_SIZE
        return h + SOCIAL_QR_PAD * 2 + SOCIAL_ROW_GAP

    def _draw_social_links(self, cx: int, y: int):
        """Instagram und Terminbuchung als scannbare Mini-QR-Codes.

        Der Boxbildschirm ist kein Touchscreen: ein reines Textlabel wie
        "Termine buchen" ist für den Gast eine Sackgasse — er liest es und
        kann nichts damit anfangen. Ein QR-Code ist der einzige Weg von der
        Box aufs Handy, deshalb steht hier je ein kleiner Code statt eines
        blossen Icons.

        Der frühere Einwand (drei Codes in der schmalen Sidebar wirken
        überladen) wird über die Hierarchie gelöst: die Mini-Codes sind
        deutlich kleiner als der Galerie-QR und liegen auf einer flachen
        Kachel statt auf dessen grosser Card.
        """
        rows = self._social_rows()
        if not rows:
            return

        # Beide Reihen linksbündig zueinander ausrichten — sonst tanzen die
        # Beschriftungen je nach Textlänge unterschiedlich weit heraus.
        tile_w  = max((surf.get_width() if surf else SOCIAL_QR_SIZE)
                      for surf, _, _ in rows) + SOCIAL_QR_PAD * 2
        label_w = max(self._f_sub.size(lbl)[0] for _, _, lbl in rows)
        block_w = tile_w + 12 + SOCIAL_ICON + 8 + label_w
        x0 = max(12, cx - block_w // 2)

        ry = y
        for surf, icon_type, label in rows:
            tile_h = (surf.get_height() if surf else SOCIAL_QR_SIZE) \
                + SOCIAL_QR_PAD * 2
            tile = pygame.Rect(x0, ry, tile_w, tile_h)
            pygame.draw.rect(self._screen, self._theme["logo_circle"],
                             tile, border_radius=6)
            if surf is not None:
                self._screen.blit(surf, surf.get_rect(center=tile.center))

            ix = tile.right + 12
            iy = tile.centery - SOCIAL_ICON // 2
            if icon_type == "instagram":
                self._draw_instagram_icon(ix, iy, SOCIAL_ICON)
            else:
                self._draw_calendar_icon(ix, iy, SOCIAL_ICON)

            lbl = self._f_sub.render(label, True, self._theme["sidebar_text"])
            self._screen.blit(
                lbl, (ix + SOCIAL_ICON + 8,
                      tile.centery - lbl.get_height() // 2))

            ry += tile_h + SOCIAL_ROW_GAP

    def _draw_instagram_icon(self, x: int, y: int, size: int):
        """Vereinfachtes Instagram-Logo: gerundetes Quadrat + Kreis innen
        + kleiner Punkt rechts oben (Flash). Programmatisch gezeichnet."""
        color = self._theme["accent"]
        pygame.draw.rect(self._screen, color, (x, y, size, size),
                         width=2, border_radius=size // 5)
        pygame.draw.circle(self._screen, color,
                           (x + size // 2, y + size // 2), size // 4, width=2)
        pygame.draw.circle(self._screen, color,
                           (x + size - 5, y + 5), 1)

    def _draw_calendar_icon(self, x: int, y: int, size: int):
        """Vereinfachter Kalender: Rechteck mit zwei Bindern oben."""
        color = self._theme["accent"]
        body_y = y + 4
        body_h = size - 4
        pygame.draw.rect(self._screen, color, (x, body_y, size, body_h),
                         width=2, border_radius=2)
        pygame.draw.rect(self._screen, color, (x + 5, y, 3, 6))
        pygame.draw.rect(self._screen, color, (x + size - 8, y, 3, 6))
        pygame.draw.line(self._screen, color,
                         (x, body_y + 7), (x + size, body_y + 7), 1)

    @staticmethod
    def _instagram_handle(url: str) -> str:
        """'https://instagram.com/foo/' → '@foo'. Fallback: 'Instagram'."""
        s = url.strip().rstrip("/")
        if "instagram.com/" in s:
            handle = s.split("instagram.com/")[-1].split("/")[0].split("?")[0]
            if handle:
                return f"@{handle}"
        if s.startswith("@"):
            return s
        return "Instagram"

    def _draw_wifi_box(self):
        """WLAN+Passwort als eigene Box mit Border-Akzent unten in der Sidebar."""
        ssid = (self._cfg.get("wifi_ssid")     or "").strip()
        pwd  = (self._cfg.get("wifi_password") or "").strip()
        if not ssid and not pwd:
            return

        cx = SIDEBAR_W // 2
        box_w = SIDEBAR_W - 40
        # Bottom-up positionieren — direkt über der Status-Bar (28 px hoch).
        margin_bottom = 56
        # Box-Höhe abhängig davon ob beide Felder gesetzt sind.
        line_h = self._f_normal.get_height()
        label_h = self._f_label.get_height()
        rows = (1 if ssid else 0) + (1 if pwd else 0)
        box_h = 22 + rows * (label_h + 4 + line_h + 14)

        x = (SIDEBAR_W - box_w) // 2
        y = H - margin_bottom - box_h
        box = pygame.Rect(x, y, box_w, box_h)

        pygame.draw.rect(self._screen, self._theme["panel_bg"],
                         box, border_radius=10)
        pygame.draw.rect(self._screen, self._theme["panel_border"],
                         box, width=2, border_radius=10)

        ty = y + 14
        for label, value in (("WLAN", ssid), ("Passwort", pwd)):
            if not value:
                continue
            lbl = self._f_label.render(label, True, self._theme["sidebar_dim"])
            self._screen.blit(lbl, (x + 16, ty))
            ty += lbl.get_height() + 2
            val = self._f_normal.render(value, True, self._theme["sidebar_text"])
            # Falls zu breit: skalieren.
            if val.get_width() > box_w - 32:
                scale = (box_w - 32) / val.get_width()
                val = pygame.transform.smoothscale(
                    val, (int(val.get_width() * scale),
                          int(val.get_height() * scale)))
            self._screen.blit(val, (x + 16, ty))
            ty += val.get_height() + 12

    # ── Hilfsmethoden ─────────────────────────────────────────────────────────

    @staticmethod
    def _load_logo(path: str) -> Optional[pygame.Surface]:
        """Lädt das aktive Logo. Wenn der konfigurierte Pfad fehlt,
        wird auf Layout/logo_default.png (Box-Besitzer-Standard) zurück-
        gefallen — das Default-Logo wird nicht durch Mieter-Uploads
        überschrieben.

        Skalierung erfolgt nur grob (max 200 px). Die finale runde Form
        macht _make_circular_logo später, weil die Größe des Cream-Kreises
        in der Sidebar Layout-fest ist.
        """
        here = os.path.dirname(os.path.abspath(__file__))
        fallback = os.path.join(here, "Layout", "logo_default.png")
        candidates = ([path] if path else []) + [fallback]

        for candidate in candidates:
            if not candidate or not os.path.isfile(candidate):
                continue
            try:
                img = pygame.image.load(candidate).convert_alpha()
                max_h = 200
                max_w = SIDEBAR_W - 40
                sw, sh = img.get_size()
                scale = min(max_h / sh, max_w / sw, 1.0)
                if scale < 1.0:
                    img = pygame.transform.smoothscale(
                        img, (int(sw * scale), int(sh * scale)))
                return img
            except Exception as exc:
                logger.warning("Logo (%s): %s", candidate, exc)
        return None

    @staticmethod
    def _make_circular_logo(logo: pygame.Surface) -> pygame.Surface:
        """Skaliert das Logo so, dass es den Cream-Kreis komplett ausfüllt
        (cover statt contain), und schneidet es rund zu. Das Ergebnis ist
        ein Surface mit Durchmesser 2*(LOGO_CIRCLE_R - 6) — die 6 px Marge
        verhindern, dass das Logo den Cream-Rand überdeckt.
        """
        radius   = LOGO_CIRCLE_R - 6
        diameter = radius * 2

        sw, sh = logo.get_size()
        # cover-Skalierung: Logo füllt den Kreis aus, wird ggf. beschnitten.
        scale  = max(diameter / sw, diameter / sh)
        nw, nh = max(diameter, int(sw * scale)), max(diameter, int(sh * scale))
        scaled = pygame.transform.smoothscale(logo, (nw, nh))

        crop_x = (nw - diameter) // 2
        crop_y = (nh - diameter) // 2
        cropped = scaled.subsurface(
            pygame.Rect(crop_x, crop_y, diameter, diameter)
        ).copy()

        # Kreis-Maske mit AA-Edge: 4× supersamplen + smoothscale gibt einen
        # weichen Alpha-Verlauf am Rand — sonst wirkt das Logo entlang der
        # Kreis-Kante "pixelig". Vorfüllen mit weissem RGB (Alpha=0) hält
        # das RGB am Rand neutral, sodass BLEND_RGBA_MIN die Logo-Farben
        # nicht entlang der Kante grau verfärbt.
        SS = 4
        big = pygame.Surface((diameter * SS, diameter * SS), pygame.SRCALPHA)
        big.fill((255, 255, 255, 0))
        pygame.draw.circle(big, (255, 255, 255, 255),
                           (radius * SS, radius * SS), radius * SS)
        masked = pygame.transform.smoothscale(big, (diameter, diameter))
        masked.blit(cropped, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        return masked

    @staticmethod
    def _make_qr(url: str, size: int = 160, border: int = 4,
                 low_ecc: bool = False) -> Optional[pygame.Surface]:
        """QR-Surface, hochskaliert auf ein ganzzahliges Vielfaches der
        Modulbreite.

        Die gelieferte Kantenlänge ist deshalb meist etwas grösser als
        `size` — Aufrufer müssen sie am Surface ablesen statt anzunehmen.
        Der Grund: bei krummer Skalierung bekommt eine Modulspalte 2 und
        die nächste 3 Pixel, und genau daran scheitern Handy-Scanner auf
        den kleinen Kacheln.

        `border` ist die Quiet-Zone in Modulen. Die Mini-Codes fahren mit
        2 statt 4, weil der Cremerand ihrer Kachel den Rest beisteuert.

        `low_ecc` schaltet auf die schwächste Fehlerkorrektur. Die ist hier
        genau richtig: der Code steht auf einem sauberen Bildschirm, es gibt
        keinen Fleck und keinen Knick zu kompensieren — dafür braucht er
        eine QR-Version weniger und bleibt auf kleinen Kacheln lesbar.
        """
        if not url:
            logger.warning("QR-Code: keine URL — gallery_url leer in config?")
            return None
        try:
            import qrcode
            from PIL import Image

            qr = qrcode.QRCode(
                border=border,
                error_correction=(qrcode.constants.ERROR_CORRECT_L if low_ecc
                                  else qrcode.constants.ERROR_CORRECT_M),
            )
            qr.add_data(url)
            qr.make(fit=True)
            total = qr.modules_count + 2 * border
            scale = max(1, math.ceil(size / total))
            px    = total * scale
            img   = qr.make_image().get_image().convert("RGB")
            img   = img.resize((px, px), Image.NEAREST)
            surf  = pygame.image.frombuffer(
                img.tobytes("raw", "RGB"), (px, px), "RGB").copy()
            logger.info("QR-Code erstellt für %s (%d Module → %dx%d px)",
                        url, total, px, px)
            return surf
        except ImportError as exc:
            logger.warning("qrcode/pillow fehlt: %s — QR deaktiviert", exc)
        except Exception as exc:
            logger.warning("QR-Code-Fehler: %s", exc)
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
