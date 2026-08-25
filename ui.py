import functools
import logging
import math
import os
import threading
import time
from collections import deque
from typing import Optional

import cv2
import numpy as np
import pygame
import pygame.gfxdraw

import config
import display_env

logger = logging.getLogger(__name__)

W, H = 1920, 1080

# ── Action-Buttons: Geometrie + Hit-Test ───────────────────────────────────────
# Bewusst modulweit statt als UI-Methode: so laesst sich der Hit-Test fuer
# Klick/Tap ohne initialisiertes Display testen (tests/test_actions.py).

def action_rects(cfg: dict) -> list:
    """Position + Rect jedes konfigurierten Action-Buttons.

    Buttons werden vertikal gestapelt rechts angeordnet, mittig zur Höhe der
    Live-View, damit sie auf Augenhöhe der Vorschau sitzen.
    """
    actions = cfg.get("actions") or []
    if not actions:
        return []
    n = len(actions)
    total_h = n * ACTION_H + (n - 1) * ACTION_GAP

    live = cfg.get("live_view_rect") or config.default_value("live_view_rect")
    center_y = live[1] + live[3] // 2
    y0 = max(80, center_y - total_h // 2)

    return [(action,
             pygame.Rect(ACTION_X, y0 + i * (ACTION_H + ACTION_GAP),
                         ACTION_W, ACTION_H))
            for i, action in enumerate(actions)]


def action_at(cfg: dict, pos) -> Optional[dict]:
    """Welcher Action-Button liegt unter `pos`? None wenn keiner getroffen ist."""
    for action, rect in action_rects(cfg):
        if rect.collidepoint(pos):
            return action
    return None


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
# Eckenradius des Live-Bilds. Bildmaske, Backing-Block und innerer Akzent
# teilen ihn sich, damit Bildkante und Akzent in den Ecken aufeinander
# liegen statt sich zu kreuzen.
LIVE_RADIUS     = 6

# Instagram-/Booking-Reihen unter dem Galerie-Code. Beide koennen einen
# eigenen, fertig gestalteten Code tragen (instagram_qr_path,
# booking_qr_path) — beide Ziele sind konstante externe URLs. Ist keiner
# hinterlegt, zeichnet _draw_social_links das Glyph.
# Instagram-/Kalender-Glyph neben der Beschriftung. 30 statt der frueheren 22:
# das Symbol steht neben 24-pt-Text und soll als Zeichen lesbar sein, nicht als
# Verzierung. Hoehe kostet das nichts — die Reihe ist mit zwei Textzeilen 53 px
# hoch, und _social_row_height nimmt davon ohnehin das Maximum.
SOCIAL_ICON     = 30
SOCIAL_ROW_GAP  = 18      # Luft zwischen den Reihen.
# Kantenlaenge fuer instagram_qr_path und booking_qr_path. Instagrams
# Code hat 41 Module (Version 6) — bei 96 px waeren das 2,3 px pro Modul,
# und mit runden Punkten und dem Gradient-Kontrast ist das zu wenig zum
# Scannen. 130 px ergeben ~3,2 px/Modul.
#
# UI.QR_SIZE ist an diesen Wert gekoppelt: der Galerie-Code soll genauso
# gross sein wie die Codes darunter. Wer hier dreht, dreht also an allen
# dreien — siehe den Kommentar an QR_SIZE fuer den gemessenen Preis.
SOCIAL_QR_SIZE  = 130
# Cremerand um die Sidebar-Codes — und zugleich deren einzige Quiet-Zone:
# _crop_to_code schneidet die mitgelieferte Ruhezone weg, damit ein Export
# mit breitem Rand nicht winzig skaliert wird. Die QR-Norm verlangt 4
# Module. Bei 130 px sind das im groebsten Fall (33 Module, 3,9 px/Modul)
# knapp 16 px — der frueher hier stehende Wert 10 ergab nur 2,5 Module.
# Untergrenze fuer den Cremerand um eine Code-Kachel. Der tatsaechliche
# Wert kommt aus UI._qr_pad und richtet sich nach dem groebsten Raster.
SOCIAL_QR_PAD   = 12
# Untergrenze, auf die _social_layout herunterregeln darf. Reicht sie
# nicht, wird stattdessen ein Code abgeworfen — Details in _social_layout.
#
# 100 statt der frueheren 104, weil die Groesse seit dem Umstieg auf ganze
# Module in Schritten der Modulzahl laeuft (bei 25 Modulen also 125, 100,
# 75, ...) und 104 den 100er-Schritt blockiert haette. Bei 100 px hat der
# Galerie-Code 4,0 px/Modul und im Kameratest 3 von 6 Stufen. Instagrams
# 41-Modul-Code kommt dort nur auf 2,4 px/Modul und ist damit unter seiner
# Lesbarkeitsgrenze — wer beide gross UND scanbar will, braucht weniger
# Codes oder kleinere Schrift.
SOCIAL_QR_MIN   = 100

# ── Header-Grenzen ────────────────────────────────────────────────────────────
# Untergrenzen, unter die _fit_text den Header NICHT senken darf. Darunter
# liest der Gast aus 2 m Abstand nichts mehr — dann lieber mitten im Wort
# umbrechen (_hard_wrap) als weiter schrumpfen.
EVENT_MIN_PT = 22
SUB_MIN_PT   = 16

# Die daraus abgeleiteten Zeichengrenzen stehen in config.py
# (EVENT_NAME_MAX_CHARS / SUBTITLE_MAX_CHARS) — dort kommt der Galerie-Server
# ohne pygame-Import an sie heran. Durchgesetzt werden sie beim Speichern;
# was trotzdem zu lang ankommt, faengt _hard_wrap ab.

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


# Schriftfamilien in Reihenfolge der Bevorzugung. pygame.font.match_font
# kennt 'sans-serif' NICHT — weder in Sysfonts noch in Sysalias, dort waere
# nur 'sans' ein Alias. SysFont("sans-serif", ...) faellt deshalb still auf
# das gebundelte freesansbold.ttf zurueck, und zwar auf dem Pi genauso wie
# auf der Dev-Maschine, weil die Datei im pygame-Paket liegt.
#
# Das kostete dreifach: die Schrift ist grob gerastert, ihr fehlen Glyphen
# (deshalb sind die Pfeile im Result-Screen von Hand gezeichnet), und sie
# rendert rund ein Drittel kleiner als angefordert — "22 px" ergaben 15 px
# Zeilenhoehe. Aus 2 m Abstand war der Untertitel damit nicht mehr lesbar.
_FONT_FAMILIES = ("dejavusans", "notosans", "liberationsans",
                  "helveticaneue", "arial", "helvetica", "freesans")


@functools.lru_cache(maxsize=None)
def _font_path(bold: bool) -> Optional[str]:
    """Datei der ersten gefundenen echten Schrift, sonst None.

    None heisst: pygame-Default. Dann sieht es aus wie frueher — lieber
    das als eine UI ohne Text, wenn ein System keine der Familien hat.
    """
    for family in _FONT_FAMILIES:
        path = pygame.font.match_font(family, bold=bold)
        if path:
            return path
    return None


def _font(size: int, bold: bool = False) -> pygame.font.Font:
    """Schrift in Punktgroesse `size`."""
    path = _font_path(bold)
    font = pygame.font.Font(path, size)
    # Kein eigener Fett-Schnitt gefunden: synthetisch fetten, sonst faellt
    # der Unterschied zwischen Ueberschrift und Fliesstext weg.
    if bold and (path is None or path == _font_path(False)):
        font.set_bold(True)
    return font


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

    # Ab wieviel mittlerer Pixelaenderung je Frame ein Bild als "lebt" gilt.
    # Auf der Box gemessen: ein Live-Bild rauscht auch bei voellig stillem
    # Motiv mit rund 0,8, das Info-Display der Kamera steht mit exakt 0,0.
    # Dazwischen ist viel Luft, der Schwellwert muss nicht genau sitzen.
    _MOTION_THRESHOLD = 0.35
    # Ueber wieviele Frames der Median gebildet wird. Median und nicht Mittel:
    # beim Wechsel vom Live-Bild zum Menue steht ein einzelner riesiger
    # Sprung in der Reihe, den ein Mittelwert sekundenlang mitschleppt — und
    # so lange saehe der Gast genau das Menue, das hier verhindert werden
    # soll. Der Median kippt nach der Haelfte des Fensters, also rund 0,15 s,
    # und laesst sich umgekehrt von einem einzelnen Wiederholframe der
    # Capture-Card nicht beirren.
    _MOTION_WINDOW = 9

    def __init__(self, device: int):
        self._device = device
        self._cap = cv2.VideoCapture(device)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not self._cap.isOpened():
            raise RuntimeError(f"Capture-Device {device} nicht verfügbar")
        self._frame = None
        self._lock = threading.Lock()
        self._running = True
        self._prev_gray = None
        self._motion = deque(maxlen=self._MOTION_WINDOW)
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
                self._measure_motion(frame)
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

    def _measure_motion(self, frame):
        """Haelt fest, wie stark sich der Frame vom vorigen unterscheidet.

        Damit laesst sich ein Live-Bild von einem stehenden Bild
        unterscheiden — und genau das ist der Unterschied zwischen "die
        Kamera zeigt den Gast" und "die Kamera zeigt ihr Aufnahmemenue".
        Ueber die Helligkeit ginge das nicht: das Menue ist ueberwiegend
        schwarz und damit genauso dunkel wie mancher Raum.
        """
        # Bewusst auf dem vollen Frame und ohne Verkleinern: jedes Mitteln
        # beim Skalieren daempft genau das Rauschen weg, an dem ein Live-Bild
        # zu erkennen ist. Der Schwellwert oben ist am vollen Frame gemessen.
        # Kosten sind kein Argument — Graustufen und Differenz auf 640x480
        # liegen deutlich unter einer Millisekunde.
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        prev, self._prev_gray = self._prev_gray, gray
        if prev is None or prev.shape != gray.shape:
            return
        self._motion.append(float(np.mean(cv2.absdiff(gray, prev))))

    def moving(self) -> bool:
        """True, wenn das Signal lebt (rauscht) statt stillzustehen."""
        if len(self._motion) < self._MOTION_WINDOW:
            # Noch keine Aussage moeglich — im Zweifel ist das Bild echt,
            # sonst faengt jede Box mit einem eingefrorenen Bild an.
            return bool(self._motion)
        return float(np.median(self._motion)) > self._MOTION_THRESHOLD

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

    # Wie lange der Mauszeiger nach der letzten Bewegung sichtbar bleibt.
    _CURSOR_IDLE_S = 3.0

    # Die Status-Bar ist Aufbau-Information: Kamera, Speicher, Hotspot
    # interessieren genau so lange, bis die Box steht. Danach ist sie nur
    # noch ein Balken im Bild, deshalb blendet sie nach 30 Sekunden aus.
    #
    # Zurueck holt sie die Taste I. Bewusst NICHT die Maus: eine einzige
    # MOUSEMOTION startete die volle Minute neu, und auf einem Rechner mit
    # Maus heisst das, dass sie praktisch nie verschwindet — gemessen an
    # der laufenden App, die Bar war nach Ablauf weg und zwei Sekunden
    # spaeter wieder da. Ebenso wenig die Ausloeser: die drueckt am
    # Eventabend der Gast. Eine Tastatur haengt nur beim Aufbau dran.
    _STATUS_BAR_S    = 30.0
    _STATUS_BAR_FADE = 1.0    # Sekunden Ausblendung, damit sie nicht springt
    _status_bar_until = 0.0

    @staticmethod
    def _scaling_flag() -> int:
        """pygame.SCALED, falls der Schirm W x H nicht exakt kann — sonst 0.

        Ohne das nimmt SDL bei FULLSCREEN einfach den nächstbesten Modus und
        liefert eine Surface dieser Größe: auf einem MacBook z.B. 1920x1200.
        Das gesamte Layout hängt aber an den Konstanten W/H — alles, was
        unten verankert ist (WLAN-Box, Status-Bar, Result-QR), säße dann
        120 px zu hoch. SCALED garantiert die Wunschgröße und skaliert
        selbst auf den Schirm.

        Die Entscheidung faellt bewusst *vor* dem set_mode: ein zweiter
        set_mode-Aufruf nach einem bereits gesetzten Fullscreen-Modus haengt
        sich auf macOS weg, ein Nachkorrigieren scheidet also aus.

        Muss nach pygame.display.init() laufen — list_modes() braucht einen
        initialisierten Treiber.

        Nebenwirkung: schaltet zusammen mit SCALED die Skalierungsqualitaet
        auf linear. SDL filtert sonst mit Nearest-Neighbour, und ein Schirm,
        der kleiner als W x H ist, franst damit jede Schrift und jede
        Polaroid-Kante aus. Der Hint wird beim Erzeugen des Renderers
        gelesen, muss also vor dem set_mode stehen.
        """
        try:
            modes = pygame.display.list_modes()
        except pygame.error as exc:
            logger.debug("Display: list_modes() nicht verfuegbar: %s", exc)
            return 0
        # -1 heisst "jede Groesse geht" (z.B. im Fenstermodus-Treiber).
        if modes == -1 or not modes or (W, H) in modes:
            UI._log_upscale()
            return 0
        logger.info("Display: %dx%d ist kein nativer Modus (verfuegbar: %s…) "
                    "— SCALED aktiv", W, H, modes[:3])
        # setdefault: ein bewusst gesetztes SDL_RENDER_SCALE_QUALITY (0 =
        # nearest, 2 = best) bleibt stehen.
        os.environ.setdefault("SDL_RENDER_SCALE_QUALITY", "1")
        return pygame.SCALED

    @staticmethod
    def _log_upscale():
        """Meldet, wenn der Schirm groesser ist als W x H.

        FULLSCREEN schaltet den Schirm dann auf einen 1920x1080-Modus und
        das Panel rechnet das Bild selbst hoch. Fonts und Kanten werden
        dabei weich — auf einem 2560x1440-Monitor um Faktor 1,33. Es ist
        kein Fehler der UI, sieht aber wie einer aus, deshalb steht es im
        Log statt dass man es am Bild raten muss.
        """
        try:
            sizes = pygame.display.get_desktop_sizes()
        except (pygame.error, AttributeError):
            return
        if sizes and sizes[0] != (W, H):
            logger.info(
                "Display: Schirm ist %dx%d, gerendert wird %dx%d — das Panel "
                "skaliert selbst hoch, Schrift wirkt dadurch weicher als auf "
                "einem echten %dx%d-Schirm", *sizes[0], W, H, W, H)

    @staticmethod
    def _open_display():
        """Oeffnet das Vollbild — ueber Wayland oder X11, je nachdem was laeuft.

        Frueher stand hier ein blankes set_mode(), abhaengig vom fest in
        fotobox.service gesetzten DISPLAY=:0. Auf einem Bookworm mit
        Wayland-Compositor und ohne XWayland blieb der Schirm damit schwarz.
        Jetzt liefert display_env.prepare() eine Treiber-Reihenfolge, die
        hier der Reihe nach durchprobiert wird.
        """
        drivers = display_env.prepare()
        last_exc = None
        for driver in drivers:
            os.environ["SDL_VIDEODRIVER"] = driver
            try:
                pygame.display.quit()      # evtl. Rest vom Fehlversuch davor
                pygame.display.init()
                flags = pygame.FULLSCREEN | UI._scaling_flag()
                screen = pygame.display.set_mode((W, H), flags)
                if screen.get_size() != (W, H):
                    # Sollte nach _scaling_flag() nicht mehr vorkommen — wenn
                    # doch, sitzt das halbe Layout falsch und man sucht sonst
                    # lange nach dem Grund.
                    logger.warning(
                        "Display: Surface ist %s statt %dx%d — Layout sitzt "
                        "nicht bündig", screen.get_size(), W, H)
                logger.info("Display: SDL-Treiber '%s' aktiv (%dx%d%s)",
                            driver, W, H,
                            ", skaliert" if flags & pygame.SCALED else "")
                return screen
            except pygame.error as exc:
                logger.warning("Display: Treiber '%s' scheitert (%s)", driver, exc)
                last_exc = exc
        raise RuntimeError(
            f"Kein nutzbarer SDL-Videotreiber (probiert: {', '.join(drivers)}). "
            f"Letzter Fehler: {last_exc}"
        )

    def __init__(self, cfg: dict, capture_device: int):
        self._cfg = cfg

        pygame.init()
        self._screen = self._open_display()
        pygame.display.set_caption("Fotobox")
        pygame.mouse.set_visible(False)

        # Fonts
        # Groessen sind Punktgroessen der echten Schrift (siehe _font). Sie
        # sind kleiner als die frueheren SysFont-Zahlen und ergeben trotzdem
        # groesseren Text, weil der Fallback rund ein Drittel unter der
        # angeforderten Groesse blieb.
        self._f_big      = _font(150, bold=True)
        self._f_large    = _font(84,  bold=True)
        self._f_medium   = _font(46,  bold=True)
        self._f_normal   = _font(38,  bold=True)
        self._f_small    = _font(24)
        self._f_event    = _font(38,  bold=True)
        self._f_sub      = _font(24)

        self._f_initials = _font(56,  bold=True)
        self._f_label    = _font(19,  bold=True)
        logger.info("Schrift: %s (fett: %s)",
                    _font_path(False) or "pygame-Default",
                    _font_path(True) or "synthetisch")

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

        # Der einzige QR-Code der Sidebar. Instagram und Terminbuchung
        # stehen darunter als Text (_draw_social_links) — beides fuehrt
        # ueber die Galerie, und drei Codes nebeneinander erschlagen den
        # Blick, ohne dass einer davon gewinnt.
        # Er traegt den Galerie-Link — warum nicht den WLAN-Zugang, steht
        # in config.py.
        # border=0: die Ruhezone liefert der Cremerand der Karte, damit
        # das Muster genauso gross ist wie bei den Codes darunter.
        self._qr_surf = self._make_qr(self._qr_payload(), size=self.QR_SIZE,
                                      border=0, **self._qr_colors())
        # Fassung des Galerie-Codes in Layout-Groesse — (Schluessel, Surface),
        # gefuellt von _gallery_qr.
        self._qr_scaled: Optional[tuple] = None

        # Optionaler Instagram-QR (instagram_qr_path). Ist er gesetzt, tritt
        # er in der Sidebar an die Stelle des Instagram-Glyphs.
        self._insta_qr = self._load_social_qr(
            cfg.get("instagram_qr_path", ""), "Instagram-QR")

        # Optionaler Buchungs-QR (booking_qr_path). Selbst gestaltbar, weil
        # booking_url eine konstante externe Adresse ist — siehe config.py.
        self._booking_qr = self._load_social_qr(
            cfg.get("booking_qr_path", ""), "Buchungs-QR")

        # Live-Reload-Tracking — gallery_server.py teilt config.cfg mit
        # dieser Instanz (siehe main.py: gallery_server.run im Thread).
        # Strings (event_name, subtitle, wifi-Texte) sind sofort sichtbar
        # — nur Logo-Surface, QR und Theme-Gradient müssen wir bei
        # Wert-Änderungen neu rendern.
        self._logo_path_seen    = cfg.get("logo_path", "")
        self._logo_mtime        = self._mtime(self._logo_path_seen)
        self._insta_qr_seen     = cfg.get("instagram_qr_path", "")
        self._insta_qr_mtime    = self._mtime(self._insta_qr_seen)
        self._booking_qr_seen   = cfg.get("booking_qr_path", "")
        self._booking_qr_mtime  = self._mtime(self._booking_qr_seen)
        self._qr_payload_seen   = self._qr_payload()
        self._cfg_mtime         = self._mtime(config.CONFIG_PATH)
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
        # Rechteck des Fotos in _slide_surf — der QR-Code weicht ihm aus.
        self._slide_rect: Optional[pygame.Rect] = None
        self._SLIDE_FADE_MS = 800

        # Result-Screen Cache — gecappt, sonst Memory-Leak nach hunderten Fotos
        self._result_cache: dict = {}
        # (Schluessel, Surface) des Codes auf dem Ergebnis-Schirm. Einer
        # reicht: dort liegt immer genau ein Foto.
        self._photo_qr_cache: Optional[tuple] = None
        self._RESULT_CACHE_MAX = 8

        # Live-Reader (Capture-Card)
        # _live_dst ist die wiederverwendete Ziel-Surface aus _live_surface,
        # _live_aspect das Format, nach dem sich der Rahmen richtet.
        self._live_dst: Optional[pygame.Surface] = None
        self._live_aspect: float = self._LIVE_FALLBACK_ASPECT
        self._live: Optional[_LiveReader] = None
        try:
            self._live = _LiveReader(capture_device)
        except Exception as exc:
            logger.warning("Kein Live-Feed: %s", exc)

        # Selbsttaetiges Wecken des Live-Views. Gesetzt wird der Rueckruf von
        # main.py (camera.request_liveview) — die UI kennt die Kamera nicht.
        self._wake_cb = None
        self._live_dark_since: Optional[float] = None
        # Letztes brauchbares Live-Bild und wann es kam. Solange die Kamera
        # kein echtes Bild liefert — waehrend einer Aufnahme etwa —, bleibt
        # dieses stehen, statt Menue oder Schwarz durchzureichen.
        self._live_hold = None
        self._live_hold_at: float = 0.0
        self._live_wake_last: float = 0.0
        self._autowake_paused = False

        # Crop-Cache: Letterbox-Ränder ändern sich praktisch nie, deshalb
        # nur alle CROP_REFRESH_S neu vermessen statt auf jedem Frame.
        self._crop_box: Optional[tuple] = None  # (y0, y1, x0, x1, h, w)
        self._crop_last_ms: int = 0
        self._CROP_REFRESH_MS = 2000

        # Klick/Tap auf einen Action-Button. Auf der Box haengt keine Maus,
        # das bleibt dort also totes Kapital — auf dem Entwicklungs-Laptop
        # ist es der einzige Weg, die Buttons ohne GPIO auszuloesen.
        self._pending_click: Optional[tuple] = None
        self._cursor_until: float = 0.0
        self._status_bar_until = time.monotonic() + self._STATUS_BAR_S

    # ── Öffentliche API ────────────────────────────────────────────────────────

    def check_quit(self) -> bool:
        """Pumpt die Event-Queue und meldet einen Beenden-Wunsch.

        Nebenbei werden Maus-/Touch-Events eingesammelt: `pygame.event.get()`
        leert die Queue, wer hier nicht hinschaut sieht einen Klick nie
        wieder. Muss deshalb jeden Frame laufen — tut es in main.py auch.
        """
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return True
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return True
            if (event.type == pygame.KEYDOWN
                    and event.key == pygame.K_i):
                # Umschalter: nochmal I blendet sie sofort wieder aus,
                # sonst muesste man eine Minute warten.
                self._status_bar_until = (
                    0.0 if self._status_bar_alpha()
                    else time.monotonic() + self._STATUS_BAR_S)
            if event.type == pygame.MOUSEMOTION:
                self._cursor_until = time.monotonic() + self._CURSOR_IDLE_S
                pygame.mouse.set_visible(True)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._pending_click = event.pos
            elif event.type == pygame.FINGERDOWN:
                # Touch liefert normalisierte Koordinaten (0..1).
                self._pending_click = (int(event.x * W), int(event.y * H))

        # Cursor wieder ausblenden, sobald die Maus ruht — sonst steht auf
        # einem angeschlossenen Testmonitor dauerhaft ein Pfeil im Bild.
        if self._cursor_until and time.monotonic() > self._cursor_until:
            self._cursor_until = 0.0
            pygame.mouse.set_visible(False)
        return False

    def take_click_action(self) -> Optional[dict]:
        """Konsumiert einen anstehenden Klick/Tap und liefert die getroffene
        Action aus `config["actions"]` (oder None).

        Wird in main.py in JEDEM Frame aufgerufen, egal in welchem State:
        sonst bliebe ein Klick auf dem Result-Screen liegen und wuerde
        verspaetet eine Aufnahme starten, sobald der Homescreen wieder da ist.
        """
        pos, self._pending_click = self._pending_click, None
        if pos is None:
            return None
        return action_at(self._cfg, pos)

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

        # config.json — die Box und das Admin-Panel sind nicht zwingend
        # derselbe Prozess. Im Dev-Setup laeuft das Panel unter
        # dev_server.py und die Box unter main.py; dann erreicht eine
        # Aenderung im einen den anderen nur ueber die Datei. Das Logo
        # fiel dabei nie auf, weil es ohnehin am Zeitstempel haengt — das
        # Theme lebte dagegen nur im Dict des anderen Prozesses.
        cfg_mt = self._mtime(config.CONFIG_PATH)
        if cfg_mt != self._cfg_mtime:
            self._cfg_mtime = cfg_mt
            if config.reload_persisted(self._cfg):
                logger.info("Live-Reload: config.json neu eingelesen")

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

        # Instagram-QR — gleiches Spiel wie beim Logo: der Owner kann die
        # Datei austauschen, ohne den Pfad zu ändern.
        insta_path = self._cfg.get("instagram_qr_path", "")
        insta_mt   = self._mtime(insta_path)
        if (insta_path != self._insta_qr_seen
                or insta_mt != self._insta_qr_mtime):
            logger.info("Live-Reload: Instagram-QR geändert (%s)", insta_path)
            self._insta_qr        = self._load_social_qr(insta_path,
                                                          "Instagram-QR")
            self._insta_qr_seen   = insta_path
            self._insta_qr_mtime  = insta_mt

        # Buchungs-QR — identisch, nur ein anderer Pfad.
        book_path = self._cfg.get("booking_qr_path", "")
        book_mt   = self._mtime(book_path)
        if (book_path != self._booking_qr_seen
                or book_mt != self._booking_qr_mtime):
            logger.info("Live-Reload: Buchungs-QR geändert (%s)", book_path)
            self._booking_qr        = self._load_social_qr(book_path,
                                                            "Buchungs-QR")
            self._booking_qr_seen   = book_path
            self._booking_qr_mtime  = book_mt

        # Theme — bei Änderung Hintergrund-Gradient + Theme-Farben neu bauen.
        theme_now     = dict(self._cfg.get("theme") or {})
        theme_changed = theme_now != self._theme_seen
        if theme_changed:
            logger.info("Live-Reload: Theme geändert")
            self._apply_theme(self._cfg)
            self._theme_seen = theme_now

        # QR-Code — neu generieren wenn sich sein Inhalt ändert (SSID oder
        # WLAN-Passwort im Admin geaendert, ohne Hotspot auch Port oder
        # hotspot_ip) und seit der Code Theme-Farben trägt auch bei jedem
        # Theme-Wechsel.
        payload = self._qr_payload()
        if payload != self._qr_payload_seen or theme_changed:
            logger.info("Live-Reload: QR neu erzeugt (%s)", payload)
            self._qr_surf         = self._make_qr(
                payload, size=self.QR_SIZE, border=0, **self._qr_colors())
            self._qr_payload_seen = payload

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
        self._draw_live_view()
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

    def _draw_live_view(self):
        """Rahmen und Live-Bild — beide auf demselben Rechteck.

        Frueher zog der Rahmen ueber das volle live_view_rect und das Bild
        lag mittig darin. Bei jedem Seitenverhaeltnis ausser dem des Rects
        blieben dadurch schwarze Balken zwischen Bild und Rahmen stehen —
        es sah aus, als sitze das Bild nicht im Rahmen. Jetzt bestimmt das
        Bild das Rechteck und der Rahmen legt sich darum, egal welches
        Format die Capture-Card liefert.
        """
        rect, surf, msg = self._live_geometry()
        self._draw_live_frame_outer(rect)
        if surf is None:
            self._draw_no_signal(rect, msg)
        else:
            self._screen.blit(surf, rect)
        self._draw_live_frame(rect)

    # So lange muss das HDMI-Signal am Stueck schwarz sein, bevor die Box den
    # Live-View von sich aus weckt. Kurze Luecken — Spiegelhub, Umschalten der
    # Capture-Card — sollen das gerade nicht ausloesen.
    _LIVE_DEAD_S = 4.0
    # Sperrzeit zwischen zwei Weckversuchen. Ohne sie klappert eine
    # ausgeschaltete Kamera im Sekundentakt, weil das Bild ja schwarz bleibt.
    _LIVE_WAKE_COOLDOWN_S = 20.0

    def set_liveview_waker(self, callback) -> None:
        """Was gerufen wird, wenn ueber Sekunden kein Live-Bild ankommt.

        Die UI ist die einzige Stelle, die das ueberhaupt bemerken kann: die
        Kamera kennt nur ihre eigenen gphoto2-Erfolge, und aus einem
        erfolgreichen 'viewfinder=1' folgt nicht, dass auf HDMI auch etwas
        herauskommt. Gesehen wird es hier, erledigt wird es dort.
        """
        self._wake_cb = callback

    def pause_live_autowake(self, paused: bool) -> None:
        """Waehrend Countdown und Aufnahme kein Wecken — ein Spiegelhub
        mittendrin waere genau der Ruckler, den das Ganze vermeiden soll.

        Die Dunkel-Uhr laeuft dabei weiter: war der Schirm schon vor der
        Aufnahme schwarz, wird direkt danach geweckt statt erst vier Sekunden
        spaeter nochmal von vorn.
        """
        self._autowake_paused = paused

    def _note_live_signal(self, ok: bool) -> None:
        """Bucht das Ergebnis eines Frame-Versuchs und weckt notfalls.

        Geweckt wird nur bei echtem Schwarzbild. Ein von Hand am
        Kamera-Display aktivierter Live-View liefert Frames und wird deshalb
        nie ueberfahren — genau daran scheiterte frueher jeder Versuch, das
        im Watchdog zu erledigen.
        """
        now = time.monotonic()
        if ok:
            self._live_dark_since = None
            return
        if self._live_dark_since is None:
            self._live_dark_since = now
        if self._wake_cb is None or self._autowake_paused:
            return
        if now - self._live_dark_since < self._LIVE_DEAD_S:
            return
        if now - self._live_wake_last < self._LIVE_WAKE_COOLDOWN_S:
            return
        self._live_wake_last = now
        self._live_dark_since = None
        logger.info("Seit %.0f s kein Live-Bild — Live-View wird geweckt",
                    self._LIVE_DEAD_S)
        try:
            self._wake_cb()
        except Exception as exc:
            logger.warning("Selbsttaetiges Wecken fehlgeschlagen: %s", exc)

    def _live_box(self) -> pygame.Rect:
        """Der konfigurierte Platz der Live-Vorschau — Obergrenze fuer das
        Bild, nicht dessen tatsaechliche Groesse."""
        x, y, w, h = (self._cfg.get("live_view_rect")
                      or config.default_value("live_view_rect"))
        return pygame.Rect(x, y, w, h)

    # Seitenverhaeltnis, das der Rahmen annimmt, solange noch kein Bild
    # gekommen ist. 16:9, weil jede HDMI-Quelle das liefert — und weil
    # _live_box breiter ist als jedes reale Signal: in voller Breite saehe
    # der Rahmen beim Start aus wie ein Briefkasten statt wie ein Monitor.
    _LIVE_FALLBACK_ASPECT = 16 / 9

    def _target_aspect(self) -> Optional[float]:
        """Format, auf das die Vorschau zugeschnitten wird — None = keins.

        Kommt aus live_view_aspect. Kaputte Werte werden verworfen statt zu
        einer Division durch Null zu fuehren; ohne Zuschnitt sieht die
        Vorschau nur schmaler aus, mit einem Absturz waere der Abend vorbei.
        """
        raw = self._cfg.get("live_view_aspect")
        if not raw:
            return None
        try:
            w, h = raw
            if w > 0 and h > 0:
                return w / h
        except (TypeError, ValueError):
            pass
        logger.warning("live_view_aspect ist unbrauchbar (%r) — Vorschau "
                       "bleibt im Format der Quelle", raw)
        return None

    def _live_geometry(self):
        """(Rect, Bild oder None, Meldung oder None).

        Mit live_view_aspect steht das Rect fest, egal was die Quelle
        liefert — das Bild wird darauf zugeschnitten. Dadurch springt der
        Rahmen auch bei Signalverlust nicht mehr.

        Ohne Zielformat bestimmt die Quelle das Rect wie zuvor; bei
        Signalverlust behaelt es dann das zuletzt gesehene Format, statt
        auf die Fallback-Form zu springen: ein kurz gezogenes HDMI-Kabel
        liesse den Rahmen sonst sichtbar die Groesse wechseln.
        """
        box    = self._live_box()
        target = self._target_aspect()
        frame, msg = self._live_frame_rgb()

        if frame is None:
            return (self._fit_rect(box, target or self._live_aspect),
                    None, msg)

        if target is None:
            fh, fw = frame.shape[:2]
            self._live_aspect = fw / fh
            rect = self._fit_rect(box, self._live_aspect)
        else:
            rect  = self._fit_rect(box, target)
            frame = self._crop_to_aspect(frame, rect.w / rect.h)

        frame = cv2.resize(frame, (rect.w, rect.h),
                           interpolation=cv2.INTER_LINEAR)
        return rect, self._live_surface(frame, rect.w, rect.h), None

    @staticmethod
    def _crop_to_aspect(frame, target: float):
        """Mittiger Ausschnitt im Zielformat.

        Schneidet je nach Quelle oben/unten oder links/rechts weg. Gibt
        einen numpy-View zurueck, keine Kopie — cv2.resize kommt damit
        klar, und auf dem Pi spart das eine Kopie je Frame.
        """
        h, w = frame.shape[:2]
        if w > h * target:
            nw = max(1, int(round(h * target)))
            x0 = (w - nw) // 2
            return frame[:, x0:x0 + nw]
        nh = max(1, int(round(w / target)))
        y0 = (h - nh) // 2
        return frame[y0:y0 + nh, :]

    @staticmethod
    def _fit_rect(box: pygame.Rect, aspect: float) -> pygame.Rect:
        """Groesstes Rechteck dieses Seitenverhaeltnisses in `box`,
        zentriert auf dessen Mitte."""
        w = min(box.w, int(box.h * aspect))
        h = min(box.h, int(round(w / aspect)))
        rect = pygame.Rect(0, 0, max(1, w), max(1, h))
        rect.center = box.center
        return rect

    # So lange bleibt das letzte echte Live-Bild stehen, wenn keins mehr
    # nachkommt. Eine Aufnahme dauert gut zwei Sekunden, der Wechsel der
    # Halte-Sitzung gut eine — beides soll der Gast nicht sehen. Laenger
    # waere es eine Luege: ein eingefrorenes Bild sieht aus wie ein lebendes.
    _LIVE_HOLD_S = 8.0

    def _live_frame_rgb(self):
        """(RGB-Frame, Meldung) — genau eins von beiden ist None.

        Schneidet schwarze Letterbox-Raender weg und haelt das letzte echte
        Bild fest, wenn gerade keins ankommt.

        Das Festhalten ist der Unterschied zwischen einer Aufnahme, die
        aussieht wie geplant, und einer, bei der zwischen Countdown und
        Ergebnis das Aufnahmemenue der Kamera und ein schwarzes Bild
        aufblitzen: waehrend der Aufnahme gehoert das USB-Geraet gphoto2,
        der Live-View ist beendet, und die Kamera zeigt derweil ihr eigenes
        Display. Zu sehen bekommt der Gast davon nichts.
        """
        if self._live is None:
            return None, "Warte auf Kamera…"

        frame = self._fresh_live_frame()
        if frame is not None:
            self._note_live_signal(True)
            self._live_hold = frame
            self._live_hold_at = time.monotonic()
            return frame, None

        self._note_live_signal(False)
        if (self._live_hold is not None
                and time.monotonic() - self._live_hold_at < self._LIVE_HOLD_S):
            return self._live_hold, None
        return None, "Bitte Display an der Kamera einschalten"

    def _fresh_live_frame(self):
        """Ein echtes, verwertbares Live-Bild — oder None.

        None heisst dreierlei: kein Frame, ein schwarzer Frame, oder ein
        stehendes Bild. Der letzte Fall ist das Aufnahmemenue der Kamera,
        das ueber HDMI kommt, sobald der Live-View nicht laeuft — hell genug,
        um jede Helligkeitspruefung zu bestehen, und deshalb nur an seiner
        Bewegungslosigkeit zu erkennen.
        """
        frame = self._live.latest()
        if frame is None or frame.max() < 20:
            return None
        if not self._live.moving():
            return None
        frame = self._crop_black_borders(frame)
        if frame is None:
            return None
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    def _live_surface(self, frame, w: int, h: int) -> pygame.Surface:
        """Frame als Surface mit runden Ecken im Radius des Rahmens.

        Ohne die Maske stehen die vier eckigen Bildecken in den runden
        Ecken des Rahmens und ueberdecken dort den inneren Akzent.

        Die Ziel-Surface wird ueber Frames hinweg wiederverwendet: sie je
        Bild neu anzulegen und per convert_alpha() zu fuellen kostet das
        Doppelte, und der Live-View laeuft mit 30 fps.
        """
        dst = self._live_dst
        if dst is None or dst.get_size() != (w, h):
            dst = self._live_dst = pygame.Surface((w, h), pygame.SRCALPHA)
        # frombuffer ist 3-5x schneller als surfarray.make_surface(swapaxes),
        # weil keine numpy-Achsen-Umordnung und keine Pixelformat-Konvertierung
        # nötig ist — der RGB-Buffer aus cv2.resize wird direkt blittable.
        # Der Blit setzt Alpha flaechendeckend auf 255, die Maske danach
        # schneidet die Ecken wieder frei.
        dst.blit(pygame.image.frombuffer(frame.tobytes(), (w, h), "RGB"), (0, 0))
        dst.blit(_aa_round_rect_mask(w, h, LIVE_RADIUS), (0, 0),
                 special_flags=pygame.BLEND_RGBA_MIN)
        return dst

    def _draw_no_signal(self, rect: pygame.Rect, msg: Optional[str] = None):
        lbl = self._f_normal.render(msg or "Warte auf Kamera…", True, C_WHITE)
        self._screen.blit(lbl, lbl.get_rect(center=rect.center))

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
        return action_rects(self._cfg)

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

            # Label zentriert — mit Taster-Beschriftung darunter, sofern es
            # etwas zu unterscheiden gibt. Sie steht auf beiden Screens an
            # derselben Stelle, damit der Gast sie einmal liest und danach
            # weiss, welcher Taster ihm gehoert.
            label = action.get("label", "Aktion")
            lbl = self._f_medium.render(label, True, label_color)
            sub = self._switch_hint(action.get("key"))
            if sub:
                lbl_rect = lbl.get_rect(
                    center=(rect.centerx, rect.centery - 12))
                self._screen.blit(lbl, lbl_rect)
                hint = self._f_label.render(sub, True, label_color)
                hint.set_alpha(170)
                self._screen.blit(hint, hint.get_rect(
                    centerx=rect.centerx, top=lbl_rect.bottom + 2))
            else:
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

    @staticmethod
    def _wrap(text: str, font: pygame.font.Font, max_w: int,
              max_lines: int) -> Optional[list]:
        """Woerter auf hoechstens `max_lines` Zeilen umbrechen, die alle in
        `max_w` passen. None, wenn das mit dieser Schrift nicht aufgeht."""
        lines, cur = [], ""
        for word in text.split():
            # Wortbreite VOR dem Umbruch pruefen, nicht erst wenn das Wort am
            # Zeilenanfang steht. Frueher stand hier nur `if not cur` — ein zu
            # breites Wort mitten im Text landete damit ungeprueft in `cur` und
            # wurde als Zeile ausgegeben. _fit_text sah ein gueltiges Ergebnis
            # und senkte die Punktgroesse nie: "Hochzeit Anna &
            # Maximilian-Ferdinand" brach in eine 370 px breite Zeile um und
            # lief aus der 290 px schmalen Sidebar ueber die Live-View.
            if font.size(word)[0] > max_w:
                return None
            probe = f"{cur} {word}".strip()
            if font.size(probe)[0] <= max_w:
                cur = probe
                continue
            lines.append(cur)
            cur = word
            if len(lines) == max_lines:
                return None
        if cur:
            lines.append(cur)
        return lines if 0 < len(lines) <= max_lines else None

    def _fit_text(self, text: str, pt: int, bold: bool, max_w: int,
                  max_lines: int = 2, min_pt: int = 13) -> tuple:
        """(Schrift, Zeilen), sodass jede Zeile in `max_w` passt.

        Erst umbrechen, dann die Punktgroesse senken und NEU rendern.
        Bewusst nicht die fertige Grafik skalieren: genau das tat der
        Header frueher, und weil der Text ohnehin schon klein gerastert
        war, wurde er dabei matschig statt nur kleiner.
        """
        while pt > min_pt:
            font  = _font(pt, bold)
            lines = self._wrap(text, font, max_w, max_lines)
            if lines:
                return font, lines
            pt -= 1
        # Untergrenze erreicht. Hier stand frueher `or [text]` — eine einzelne,
        # beliebig breite Zeile. Bei einem deutschen Kompositum reicht das:
        # "Betriebsversammlungsjubilaeum" ist selbst bei 13 pt noch 330 px
        # breit und lief damit aus der Sidebar. Stattdessen hart umbrechen,
        # notfalls mitten im Wort — abgeschnittener Text ist haesslich, Text
        # ueber der Live-View ist kaputt.
        font = _font(min_pt, bold)
        return font, (self._wrap(text, font, max_w, max_lines)
                      or self._hard_wrap(text, font, max_w, max_lines))

    @staticmethod
    def _hard_wrap(text: str, font: pygame.font.Font, max_w: int,
                   max_lines: int) -> list:
        """Wie _wrap, bricht aber auch innerhalb eines Wortes um und gibt
        immer Zeilen zurueck. Was nicht mehr passt, endet mit '…'."""
        lines, cur = [], ""
        for word in text.split():
            for ch in ((" " + word) if cur else word):
                if font.size(cur + ch)[0] <= max_w:
                    cur += ch
                    continue
                lines.append(cur)
                if len(lines) == max_lines:
                    # Letzte Zeile kuerzen, bis das Auslassungszeichen passt.
                    last = lines[-1]
                    while last and font.size(last + "…")[0] > max_w:
                        last = last[:-1]
                    lines[-1] = last + "…"
                    return lines
                cur = ch.lstrip()
        if cur:
            lines.append(cur)
        return lines or [""]

    def _header_blocks(self) -> list:
        """[(Schrift, Zeilen, Farbe)] fuer Event-Name und Untertitel.

        Eine Quelle fuer Zeichnung UND Hoehenrechnung — sonst sitzt die
        QR-Gruppe auf einer Header-Hoehe, die es gar nicht gibt. Das
        Ergebnis wird gecacht, weil _fit_text pro Aufruf mehrere Schriften
        baut und die Sidebar jeden Frame neu gezeichnet wird.
        """
        name = (self._cfg.get("event_name") or "").strip()
        sub  = (self._cfg.get("subtitle")   or "").strip()
        key  = (name, sub, self._theme["sidebar_text"], self._theme["sidebar_dim"])
        if self._header_cache and self._header_cache[0] == key:
            return self._header_cache[1]

        max_w  = SIDEBAR_W - 30
        blocks = []
        for text, pt, min_pt, bold, color, max_lines in (
                (name, self._f_event_pt, EVENT_MIN_PT, True,
                 self._theme["sidebar_text"], 2),
                (sub,  self._f_sub_pt,   SUB_MIN_PT,   False,
                 self._theme["sidebar_dim"],  3)):
            if not text:
                continue
            font, lines = self._fit_text(text, pt, bold, max_w, max_lines,
                                         min_pt=min_pt)
            blocks.append((font, lines, color))
        self._header_cache = (key, blocks)
        return blocks

    # Ausgangs-Punktgroessen des Headers, die _fit_text bei Bedarf senkt.
    # Klassenattribute, damit auch Instanzen ohne __init__ sie haben.
    _f_event_pt       = 38
    _f_sub_pt         = 24
    _f_medium_pt      = 46
    _f_normal_pt      = 38
    _header_cache     = None
    _cfg_mtime        = 0.0
    # Von main.py auf False gesetzt, sobald echte GPIO-Taster da sind.
    show_key_hints    = True
    # Welche Taster wirklich erreichbar sind. main.py setzt das aus
    # Buttons.wired(); der Result-Screen zeigt danach nur Aktionen an, die
    # der Gast auch ausloesen kann. Ein Knopf auf dem Schirm, den niemand
    # druecken kann, ist schlimmer als gar keiner.
    wired_buttons     = frozenset(("left", "trigger", "right"))
    # Wie der Gast die verbauten Taster von links nach rechts sieht. Die
    # logischen Namen taugen dafuer nicht: an einer Box mit zwei Tastern
    # (trigger+right, siehe gpio_pins) ist `trigger` fuer ihn schlicht der
    # linke, obwohl er intern in der Mitte steht.
    _SWITCH_WORDS = {
        2: ("linker Taster", "rechter Taster"),
        3: ("linker Taster", "mittlerer Taster", "rechter Taster"),
    }
    _social_cache     = None
    _HEADER_LINE_GAP  = 2     # zwischen umgebrochenen Zeilen eines Blocks
    _HEADER_BLOCK_GAP = 8     # zwischen Event-Name und Untertitel

    # Untergrenze fuer Text auf der Sidebar. 4,5:1 ist der WCAG-Wert fuer
    # Fliesstext; darunter liest das niemand aus zwei Metern.
    TEXT_MIN_CONTRAST = 4.5

    def _readable(self, *candidates) -> tuple:
        """Erste Farbe aus `candidates`, die auf der Sidebar lesbar ist.

        Gebraucht, weil der Mieter jede Theme-Farbe frei setzen darf und
        manche dabei als Textfarbe unbrauchbar werden. Im dunklen Theme der
        Box liegt `accent` bei (45,45,45) auf einem (26,26,26)-Grund —
        gemessen 1,26:1. Die Domain unter "Fotobox mieten" stand damit
        praktisch unsichtbar da, und `accent_dim` ist dort sogar exakt die
        Hintergrundfarbe.

        Der Mieter darf sich seine Farben verderben, aber nicht die
        Lesbarkeit: reicht keine, wird die Textfarbe der Sidebar genommen.
        """
        bg = self._theme["sidebar_bg"]
        for c in candidates:
            if c is not None and UI._contrast(c, bg) >= self.TEXT_MIN_CONTRAST:
                return c
        return self._theme["sidebar_text"]

    def _switch_hint(self, key: Optional[str]) -> Optional[str]:
        """Beschriftung "linker/mittlerer/rechter Taster" zu einer Aktion.

        Ohne sie war an der Box nicht zu erkennen, welcher der beiden
        Taster welchen Knopf ausloest: die Knoepfe stehen auf dem
        Homescreen uebereinander und auf dem Result-Screen nebeneinander,
        also sagt schon die Position auf beiden Screens etwas anderes.

        None heisst "nicht beschriften" — und zwar in drei Faellen: an der
        Dev-Maschine (dort steht das Tastenkuerzel an derselben Stelle),
        bei nur einem verbauten Taster (nichts zu unterscheiden) und bei
        einer Aktion, deren Taster gar nicht verbaut ist.
        """
        if self.show_key_hints or not key:
            return None
        order = [n for n in ("left", "trigger", "right")
                 if n in self.wired_buttons]
        words = self._SWITCH_WORDS.get(len(order))
        if not words or key not in order:
            return None
        return words[order.index(key)]

    def _header_height(self) -> int:
        h = 0
        for font, lines, _ in self._header_blocks():
            h += (len(lines) * font.get_height()
                  + (len(lines) - 1) * self._HEADER_LINE_GAP
                  + self._HEADER_BLOCK_GAP)
        return h

    def _draw_event_header(self):
        """Event-Name + Untertitel in der Sidebar unter dem Logo."""
        cx = SIDEBAR_W // 2
        y  = SIDEBAR_PAD + LOGO_CIRCLE_R * 2 + 24
        for font, lines, color in self._header_blocks():
            for line in lines:
                lbl = font.render(line, True, color)
                self._screen.blit(lbl, lbl.get_rect(centerx=cx, top=y))
                y += lbl.get_height() + self._HEADER_LINE_GAP
            y += self._HEADER_BLOCK_GAP - self._HEADER_LINE_GAP

    def _draw_live_frame_outer(self, rect: pygame.Rect):
        """Brauner Aussenrahmen + dunkler Backing-Block. Wird VOR dem
        Live-Bild gezeichnet, damit der Rahmen als Frame fungiert und
        der Backing-Block bei 'kein Signal' den dunklen Bereich liefert.
        """
        pygame.draw.rect(self._screen, self._theme["live_outer"],
                         rect.inflate(2 * LIVE_OUTER_W, 2 * LIVE_OUTER_W),
                         border_radius=14)
        pygame.draw.rect(self._screen, self._theme["live_bg"], rect,
                         border_radius=LIVE_RADIUS)

    def _draw_live_frame(self, rect: pygame.Rect):
        """Innerer Goldakzent — NACH dem Live-Bild gezeichnet, sitzt als
        dezenter Strich auf dem Bildrand.
        """
        pygame.draw.rect(self._screen, self._theme["live_inner"], rect,
                         width=LIVE_INNER_W, border_radius=LIVE_RADIUS)

    def _status_bar_height(self) -> int:
        """Höhe der Status-Bar, aus der Schrift statt fest verdrahtet.

        Die frühere Konstante 28 stammte aus der Zeit des pygame-Fallbacks,
        in der _f_small nur 17 px hoch war. Mit einer echten Schrift sind
        es 27 px, und die Unterlängen wurden unten abgeschnitten.
        """
        return self._f_small.get_height() + 10

    def _status_bar_alpha(self) -> int:
        """0..255 — 0 heisst: Bar ist abgelaufen und wird nicht gezeichnet."""
        left = self._status_bar_until - time.monotonic()
        if left <= 0:
            return 0
        if left >= self._STATUS_BAR_FADE:
            return 255
        return max(1, int(255 * left / self._STATUS_BAR_FADE))

    def _draw_status_bar(self, camera_ok: bool, free_mb: int, photo_count: int):
        alpha = self._status_bar_alpha()
        if not alpha:
            return
        bar_h = self._status_bar_height()
        # Balken UND Text auf eine eigene Flaeche, damit das Ausblenden
        # beides zugleich erfasst — sonst bliebe die Schrift stehen,
        # waehrend der Hintergrund schon weg ist.
        bar = pygame.Surface((W, bar_h), pygame.SRCALPHA)
        bar.fill((0, 0, 0, 160))

        cam_color = C_GREEN if camera_ok else C_RED
        cam_text  = "Kamera: OK" if camera_ok else "Kamera: FEHLT"
        items = [
            (cam_text, cam_color),
            (self._disk_label(free_mb), self._disk_color(free_mb)),
            (f"Fotos: {photo_count}", C_DIM),
            ("Hotspot: aktiv" if self._cfg.get("hotspot_enabled") else "Hotspot: aus", C_DIM),
        ]
        ty = (bar_h - self._f_small.get_height()) // 2
        x = 20
        for text, color in items:
            lbl = self._f_small.render(text, True, color)
            bar.blit(lbl, (x, ty))
            x += lbl.get_width() + 60
        bar.set_alpha(alpha)
        self._screen.blit(bar, (0, H - bar_h))

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

    # Wie lange "Lächeln!" mindestens steht, damit es nicht bloss aufblitzt,
    # wenn die Kamera ungewoehnlich schnell meldet.
    _LAECHELN_MIN_MS = 350
    # Und wie lange hoechstens — fuer den Fall, dass der Ausloese-Marker gar
    # nicht kommt (altes gphoto2, fehlendes stdbuf, geaenderte Ausgabe).
    # Danach uebernimmt der Uebertragungs-Screen, der ohnehin ein Lebenszeichen
    # zeigt; verloren ist dabei nichts.
    _LAECHELN_MAX_MS = 5000

    def run_countdown(self, on_capture, seconds: int = 3,
                      photo_num: int = 1, total: int = 1,
                      lead_s: float = 0.0, shutter=None) -> None:
        """Zeigt Countdown, löst aus, zeigt 'Lächeln!' bis der Verschluss faellt.

        on_capture wird als Callback in einem Thread gestartet.
        Aufrufer wartet nach dieser Methode auf das done-Event.

        `lead_s` zieht diesen Start um Sekunden vor das Ende des Countdowns.
        Grund: zwischen dem gphoto2-Aufruf und der Belichtung liegen auf der
        EOS 700D rund 1,1 s (gemessen ueber EXIF, erster Schuss nach Ruhe eher
        1,9 s) — ohne Vorlauf faellt der Verschluss also erst, wenn "Lächeln!"
        schon wieder weg ist. Der Wert steht als capture_lead_s in der Config.

        `shutter` ist ein Event, das die Kamera setzt, sobald ausgeloest wurde.
        Damit endet "Lächeln!" am echten Ereignis statt nach blind gesetzten
        1200 ms, und der Blitz sitzt auf dem Moment, den er behauptet. Ohne
        Event bleibt es beim festen Fenster.
        """
        started = False

        def _start():
            threading.Thread(target=on_capture, daemon=True).start()

        end = pygame.time.get_ticks() + max(0, seconds) * 1000
        lead_ms = int(max(0.0, lead_s) * 1000)
        while True:
            left = end - pygame.time.get_ticks()
            if left <= 0:
                break
            if not started and left <= lead_ms:
                started = True
                _start()
            # Aufrunden: die letzte Sekunde zeigt die 1, nicht die 0.
            self._draw_countdown_frame(-(-left // 1000), photo_num, total)
            pygame.event.pump()
            pygame.time.wait(30)

        if not started:
            _start()

        start_ms = pygame.time.get_ticks()
        while True:
            waited = pygame.time.get_ticks() - start_ms
            if shutter is None:
                if waited >= 1200:
                    break
            elif waited >= self._LAECHELN_MIN_MS and shutter.is_set():
                break
            elif waited >= self._LAECHELN_MAX_MS:
                logger.warning("Kein Ausloese-Signal nach %d ms — "
                               "'Lächeln!' laeuft ins Zeitfenster",
                               self._LAECHELN_MAX_MS)
                break
            self._draw_laecheln_frame(photo_num, total)
            pygame.event.pump()
            pygame.time.wait(30)

        # Der Blitz kommt jetzt NACH dem Verschluss statt davor. Vorher war er
        # das Startsignal fuer eine Aufnahme, die erst gut eine Sekunde spaeter
        # stattfand — er meldete dem Gast "fertig", waehrend das Foto noch
        # bevorstand, und kostete zusaetzlich 300 ms Vorlauf.
        self._flash()

    def wait_for_capture(self, done, timeout: float = 35.0) -> bool:
        """Haelt die Render-Schleife am Leben, waehrend gphoto2 laeuft.

        Ohne sie wartete main.py blockierend, und der Bildschirm stand bis zum
        Timeout auf dem letzten Frame — kein Lebenszeichen, sah abgestuerzt
        aus. Die Schleife bleibt deshalb, auch wenn sie nichts Eigenes mehr
        zeichnet: sie haelt das Bild aktuell und die Event-Queue leer.

        Zu sehen ist waehrenddessen das stehende Live-Bild, also der Gast
        selbst. Hier lag frueher ein abgedunkelter Schleier mit "Foto wird
        uebertragen…" und laufenden Punkten darueber. Der ist bewusst raus:
        seit der Verschluss auf "Lächeln!" faellt (capture_lead_s) dauert die
        Uebertragung nur noch kurz, und ein Schleier, der fuer eine Sekunde
        aufzieht und gleich wieder verschwindet, ist mehr Unruhe als Auskunft.

        Rueckgabe: True wenn `done` rechtzeitig gesetzt wurde, sonst False.
        """
        deadline = time.monotonic() + timeout

        while not done.is_set():
            if time.monotonic() >= deadline:
                return False
            self._draw_live_fullscreen()
            pygame.display.flip()
            pygame.event.pump()
            pygame.time.wait(30)
        return True

    def wait_for_liveview(self, timeout: float) -> bool:
        """Haelt die Schleife am Leben, bis wieder ein echtes Live-Bild kommt.

        Gebraucht zwischen zwei Collage-Shots: dort schaut der Gast auf den
        naechsten Countdown und richtet sich aus, und genau dort war das Bild
        nach der Aufnahme weg. Gewartet wird auf das BILD, nicht auf den
        Halte-Prozess — dessen Laufen beweist nichts, siehe
        camera.request_liveview.

        Geprueft wird mit _fresh_live_frame und nicht mit _live_frame_rgb:
        letzteres reicht das gehaltene Standbild durch und waere sofort
        zufrieden, obwohl von der Kamera nichts mehr kommt.

        Rueckgabe: True, sobald ein frisches Bild da ist. False nach Ablauf
        von `timeout` — dann steht im naechsten Countdown das gehaltene
        Standbild, immer noch besser als Schwarz.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._fresh_live_frame() is not None:
                return True
            self._draw_live_fullscreen()
            pygame.display.flip()
            pygame.event.pump()
            pygame.time.wait(30)
        return False

    # Innenbreite der Notice-Box (1200 px minus je 40 px Rand).
    _NOTICE_W = 1120

    def _notice_title(self, text: str) -> tuple:
        """(Schrift, Zeilen) fuer die Ueberschrift eines Hinweises."""
        if not text:
            return _font(self._f_medium_pt, True), []
        return self._fit_text(text, self._f_medium_pt, True, self._NOTICE_W,
                              max_lines=2, min_pt=26)

    def _notice_detail(self, text: str) -> tuple:
        """(Schrift, Zeilen) fuer die Detailzeile eines Hinweises."""
        if not text:
            return _font(self._f_normal_pt, True), []
        return self._fit_text(text, self._f_normal_pt, True, self._NOTICE_W,
                              max_lines=3, min_pt=20)

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
            left = max(0.0, end - time.monotonic())
            self._draw_notice_frame(title, detail, accent,
                                    left / seconds if seconds > 0 else 0.0)
            pygame.display.flip()
            pygame.event.pump()
            pygame.time.wait(30)

    def show_busy(self, title: str, detail: str = "") -> None:
        """Ein einzelner Hinweis-Frame, ohne zu warten.

        Fuer Arbeit, die den Hauptthread ohnehin blockiert: der Frame bleibt
        genau so lange stehen, wie die Arbeit dauert, und kostet keine
        zusaetzliche Zeit. show_notice waere hier falsch — es wartet seine
        Sekunden ab und kaeme damit ZU der Wartezeit dazu, statt sie zu
        erklaeren.

        Kein Fortschrittsbalken: wie lange es dauert, weiss hier niemand, und
        ein Balken, der nicht laeuft, sagt weniger als keiner.
        """
        self._draw_notice_frame(title, detail, C_GREEN, None)
        pygame.display.flip()
        pygame.event.pump()

    def _draw_notice_frame(self, title: str, detail: str, accent,
                           bar: Optional[float]) -> None:
        """Ein Frame des Hinweis-Kastens. `bar` ist der verbleibende Anteil
        des Balkens unten, None laesst ihn weg."""
        self._screen.fill((12, 8, 4))
        box = pygame.Rect(0, 0, 1200, 380)
        box.center = (W // 2, H // 2)
        pygame.draw.rect(self._screen, (28, 20, 12), box, border_radius=28)
        pygame.draw.rect(self._screen, accent, box, width=5, border_radius=28)
        # Titel und Detail umbrechen statt roh rendern. `detail` kommt
        # von aussen — printing.py reicht Drucker-Fehlermeldungen durch
        # (auf 80 Zeichen gekuerzt). Mit der echten Schrift passen in die
        # 1200 px breite Box nur noch rund 57 Zeichen, eine typische
        # CUPS-Meldung stand also ausserhalb des Kastens, genau dann wenn
        # der Gast sie lesen soll.
        # Beide Bloecke als EINE mittig sitzende Gruppe stapeln. Feste
        # Mittelpunkte (frueher H/2-55 und H/2+35) tragen nur solange,
        # wie beides einzeilig bleibt — bei drei Detailzeilen lief der
        # Titel in die erste Detailzeile.
        blocks = [b for b in (self._notice_title(title) + (C_WHITE,),
                              self._notice_detail(detail) + (C_DIM,))
                  if b[1]]
        GAP = 24
        total = sum(len(l) * f.get_height() for f, l, _ in blocks)
        total += GAP * (len(blocks) - 1)
        ly = H // 2 - total // 2
        for lines_font, lines, color in blocks:
            for line in lines:
                surf = lines_font.render(line, True, color)
                self._screen.blit(surf, surf.get_rect(centerx=W // 2, top=ly))
                ly += lines_font.get_height()
            ly += GAP
        if bar is not None:
            pygame.draw.rect(self._screen, accent,
                             (box.left, box.bottom - 8,
                              int(box.width * bar), 8),
                             border_bottom_left_radius=28)

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
        self._draw_qr_result(photo_path)
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
        #
        # Das Foto sitzt mittig im SCHIRM, nicht mittig im Platz neben dem
        # Code: sonst haengt es sichtbar links. Damit der Code trotzdem daneben
        # passt und nicht darauf, wird die Code-Spalte auf beiden Seiten
        # freigehalten — rechts steht der Code darin, links bleibt sie leer.
        # Der Preis ist Bildgroesse: aus 1620x1080 werden bei 3:2 rund
        # 1224x816. Wer das Foto groesser will, muss den Code kleiner machen
        # (RESULT_QR_SIZE) oder ihn wieder darauf legen.
        area_w = W - 2 * self.RESULT_QR_COL
        fit = min(area_w / iw, H / ih)
        nw, nh = max(1, int(iw * fit)), max(1, int(ih * fit))
        sharp = pygame.transform.smoothscale(img, (nw, nh))
        canvas.blit(sharp, sharp.get_rect(center=(W // 2, H // 2)))

        self._result_cache[path] = canvas
        # Cap: älteste Einträge wegwerfen damit der Cache nicht endlos wächst
        while len(self._result_cache) > self._RESULT_CACHE_MAX:
            oldest = next(iter(self._result_cache))
            self._result_cache.pop(oldest, None)
        return canvas

    def _photo_qr(self, path: str) -> Optional[pygame.Surface]:
        """Code auf genau dieses Foto. Gecacht, weil der Ergebnis-Schirm
        jeden Frame neu gezeichnet wird und ein QR-Rendering teuer ist."""
        url = config.photo_url(self._cfg, path)
        if not url:
            return None
        colors = self._qr_colors()
        key = (url, colors["fg"], colors["bg"], colors["eye"])
        cached = self._photo_qr_cache
        if cached and cached[0] == key:
            return cached[1]
        surf = self._make_qr(url, size=self.RESULT_QR_SIZE, border=0, **colors)
        self._photo_qr_cache = (key, surf)
        return surf

    def _draw_qr_result(self, photo_path: str = ""):
        """Code oben rechts auf dem Ergebnis-Schirm — er zeigt auf DIESES
        Foto, nicht auf das WLAN.

        Dahinter steckt eine Eigenheit der Handys, die den ganzen Umweg
        spart: ein mit der Kamera gescannter Code oeffnet sich immer im
        echten Browser, nie im WLAN-Anmeldefenster. Und nur dort
        funktioniert "Bild sichern" — das Anmeldefenster kann keine
        Downloads (siehe frontend/src/captive.ts). Wer bisher sein Foto
        speichern wollte, musste sich aus dem Anmeldefenster freischalten
        und die Adresse von Hand eintippen. Jetzt ist es ein Scan.

        Der Gast muss dafuer schon im WLAN sein, sonst laeuft der Scan in
        eine Fehlerseite von Safari — und die sagt ihm nicht, was fehlt.
        Deshalb steht die Kurzanleitung mit SSID und Passwort direkt
        darunter: hier hat der Schirm Platz dafuer, anders als die Sidebar
        (die Rechnung steht in _qr_group_bounds).

        Laesst sich keine Foto-URL bilden, faellt der Schirm auf den
        Sidebar-Code zurueck: der fuehrt in die Galerie statt auf ein
        bestimmtes Bild.
        """
        qr = self._photo_qr(photo_path)
        hint = "Dein Foto aufs Handy" if qr is not None else "Fotos aufs Handy"
        if qr is None:
            qr = self._qr_surf
        if qr is None:
            return

        QR = qr.get_width()
        PAD = 16
        label = self._f_sub.render(hint, True, self._theme["panel_bg"])
        card_w = QR + PAD * 2
        card_h = QR + PAD * 2 + label.get_height() + 6

        # Kurzanleitung darunter. Sie beantwortet die einzige Frage, an der
        # der Scan scheitern kann: "ich bin noch gar nicht im WLAN".
        head, lines = self._wifi_hint(self.RESULT_QR_COL - 32)
        hint_h = 0
        if head is not None:
            hint_h = head.get_height() + 8 + sum(l.get_height() + 4
                                                 for l in lines)
        GAP = 22
        group_h = card_h + (GAP + hint_h if hint_h else 0)

        # Mittig in der reservierten Spalte, und auf derselben Hoehe wie das
        # Foto — nicht oben in der Ecke: dort sass der Code, als er noch auf
        # dem Bild lag, und neben dem Bild wirkt das aus der Achse.
        # Zentriert wird die ganze Gruppe, sonst haengt die Anleitung den
        # Code aus der Mitte. Nach unten begrenzt, damit sie nicht in den
        # Button-Verlauf laeuft: dessen Oberkante ist die harte Grenze,
        # die Schirmmitte nur der Wunsch.
        cx = W - self.RESULT_QR_COL + self.RESULT_QR_COL // 2
        x = cx - card_w // 2
        y = max(PAD, min((H - group_h) // 2,
                         H - self._SCRIM_H - group_h - 12))

        # Creme statt Weiss: der Code bringt seine Quiet-Zone selbst in
        # dieser Farbe mit, ein weisser Rahmen zöge eine sichtbare Kante
        # genau um sie herum.
        card = pygame.Surface((card_w, card_h))
        card.fill(self._qr_card_color())
        self._screen.blit(card, (x, y))
        self._screen.blit(qr, (x + PAD, y + PAD))
        self._screen.blit(label, label.get_rect(centerx=cx,
                                                top=y + PAD + QR + 4))

        if head is None:
            return
        ty = y + card_h + GAP
        self._screen.blit(head, head.get_rect(centerx=cx, top=ty))
        ty += head.get_height() + 8
        for line in lines:
            self._screen.blit(line, line.get_rect(centerx=cx, top=ty))
            ty += line.get_height() + 4

    def _wifi_hint(self, max_w: int) -> tuple:
        """(Ueberschrift, Zeilen) der Kurzanleitung — oder (None, []).

        Gedacht fuer den Gast, der den Code scannt, ohne im WLAN zu sein:
        Safari zeigt ihm dann eine Fehlerseite, die nichts erklaert. Hier
        steht, was fehlt, und zwar auf dem Schirm, den er ohnehin ansieht.

        Ohne konfiguriertes WLAN gibt es nichts anzuleiten — dann bleibt es
        beim blanken Code.
        """
        rows = self._wifi_rows()
        if not rows:
            return (None, [])
        head = self._f_label.render("Noch nicht im WLAN?", True,
                                    self._theme["sidebar_dim"])
        lines = [self._fit_width(
                     self._f_sub.render(f"{lbl}: {val}", True,
                                        self._theme["sidebar_text"]), max_w)
                 for lbl, val, _ in rows]
        return (self._fit_width(head, max_w), lines)

    @staticmethod
    def _fit_width(surf: pygame.Surface, max_w: int) -> pygame.Surface:
        """Schrumpft eine Textzeile, die breiter ist als ihr Platz.

        Ein langer WLAN-Name laeuft sonst stumm ueber den Rand der Spalte
        hinaus — dasselbe Problem, das die WLAN-Box in der Sidebar schon
        hatte."""
        if surf.get_width() <= max_w:
            return surf
        scale = max_w / surf.get_width()
        return pygame.transform.smoothscale(
            surf, (max_w, max(1, int(surf.get_height() * scale))))

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
        # Welche Knoepfe es gibt, entscheidet sich VOR der Geometrie —
        # sonst zentriert sie auf eine Anzahl, die gar nicht gezeichnet
        # wird. Der Druck-Knopf erscheint nur, wenn CUPS einen bereiten
        # Drucker kennt: vorher stand "Drucken" immer da und tat sichtbar
        # nichts, solange keiner eingerichtet war.
        #
        # "Zurück" braucht keinen eigenen Taster — der Timer darueber tut
        # dasselbe und sagt als "Zurück in 7s" auch, wann. Fehlt der linke
        # Taster, faellt der Knopf deshalb ersatzlos weg.
        defs = []
        if "left" in self.wired_buttons:
            defs.append(("Zurück", "left", "left", "Q", keys[pygame.K_q]))
        defs.append(("Nochmal", None, "trigger", "Space", keys[pygame.K_SPACE]))
        if self.print_ready and "right" in self.wired_buttons:
            defs.append(("Drucken", "right", "right", "E", keys[pygame.K_e]))

        n_btn = len(defs)
        total_w = n_btn * btn_w + (n_btn - 1) * gap
        sx = (W - total_w) // 2
        by = H - btn_h - 20

        # Timer
        timer = self._f_small.render(f"Zurück in {max(0, int(time_left)) + 1}s",
                                     True, C_WHITE)
        self._screen.blit(timer, timer.get_rect(centerx=W // 2, bottom=by - 10))

        # Pfeile werden gezeichnet statt als '←'/'→' gesetzt. Urspruenglich
        # war der Grund die Fallback-Schrift ohne Pfeil-Glyphen; die ist
        # inzwischen weg (siehe _font). Gezeichnet bleiben sie trotzdem,
        # damit sie auf Pi und Dev-Maschine deckungsgleich sind, egal
        # welche Schrift dort gefunden wird.
        ARROW_SIZE, ARROW_GAP = 22, 14
        for i, (label, arrow, key_name, key_hint, hl) in enumerate(defs):
            rect = pygame.Rect(sx + i * (btn_w + gap), by, btn_w, btn_h)
            color = C_BTN_HL if hl else C_BTN_BG
            pygame.draw.rect(self._screen, color, rect, border_radius=12)
            pygame.draw.rect(self._screen, C_GOLD, rect, width=2, border_radius=12)

            fg  = C_WHITE if hl else C_GOLD
            lbl = self._f_normal.render(label, True, fg)
            # Zweite Zeile: an der Dev-Maschine das Tastenkuerzel, an der
            # Box der Taster. Beide sitzen 20 px unter der Mitte, wofuer die
            # Beschriftung 10 px nach oben rueckt. Gibt es keine zweite
            # Zeile, entfaellt auch das Rueckem — sonst stuende die
            # Beschriftung sichtbar zu hoch ueber leerem Platz.
            sub = (f"[ {key_hint} ]" if self.show_key_hints
                   else self._switch_hint(key_name))
            ly  = rect.centery - 10 if sub else rect.centery
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

            if sub:
                hint = self._f_small.render(sub, True, C_DIM)
                self._screen.blit(hint, hint.get_rect(
                    centerx=rect.centerx, centery=rect.centery + 20))

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
                self._slide_surf, self._slide_rect = self._slide_frame(img)
            except Exception:
                self._slide_surf = pygame.Surface((W, H))
                self._slide_surf.fill(C_BLACK)
                self._slide_rect = None
        elapsed = now - self._slide_start_ms
        alpha = min(255, int(elapsed / self._SLIDE_FADE_MS * 255))
        self._slide_surf.set_alpha(alpha)
        self._screen.fill(C_BLACK)
        self._screen.blit(self._slide_surf, (0, 0))
        self._draw_qr(self._slide_rect)
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
            # Ueber _build_polaroid vorwaermen, NICHT das nackte Foto rotieren:
            # sonst steht im Cache ein Bild ohne Cream-Rand und ohne Pin, und
            # _draw_polaroid ruft _build_polaroid wegen des Cache-Treffers nie
            # auf. Genau daran verlor jedes befuellte Polaroid Rahmen und Pin,
            # waehrend die leeren Platzhalter (kein Vorwaermen) beides hatten.
            for _, _, angle in self._frames:
                self._rot_cache[(path, angle)] = self._build_polaroid(
                    scaled, None, angle)
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
        """Live-Bild ueber den ganzen Schirm — Countdown und Slideshow.

        Anders als _draw_live_view bleiben die schwarzen Balken hier
        stehen: es gibt keinen Rahmen, an dem sie stoeren wuerden, und ein
        formatfuellender Zuschnitt haette dem Gast im Countdown genau den
        Bildrand genommen, an dem er sich ausrichtet.
        """
        self._screen.fill(C_BLACK)
        frame, _ = self._live_frame_rgb()
        if frame is None:
            return
        fh, fw = frame.shape[:2]
        scale = min(W / fw, H / fh)
        nw, nh = int(fw * scale), int(fh * scale)
        frame = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
        surf = pygame.image.frombuffer(frame.tobytes(), (nw, nh), "RGB")
        self._screen.blit(surf, ((W - nw) // 2, (H - nh) // 2))

    # ── QR-Code ────────────────────────────────────────────────────────────────

    @staticmethod
    def _slide_frame(img) -> tuple:
        """(Vollbild-Surface, Rechteck des Fotos darin).

        Das Foto wird seitenverhaeltnistreu eingepasst statt auf W x H
        gezogen. Vorher tat die Slideshow genau das: eine 3:2-Aufnahme auf
        einem 16:9-Schirm kam rund 18 % zu breit heraus, jeder darauf war
        breiter als in Wirklichkeit.

        Die Balken links und rechts sind der Preis dafuer — und zugleich der
        Platz, in den der QR-Code rueckt, statt auf dem Foto zu liegen.

        Gearbeitet wird auf einer Vollbild-Surface, weil die Slideshow ihre
        Blende ueber set_alpha genau einer Surface faehrt.
        """
        iw, ih = img.get_width(), img.get_height()
        fit = min(W / iw, H / ih)
        nw, nh = max(1, int(iw * fit)), max(1, int(ih * fit))
        surf = pygame.Surface((W, H))
        surf.fill(C_BLACK)
        rect = pygame.Rect(0, 0, nw, nh)
        rect.center = (W // 2, H // 2)
        surf.blit(pygame.transform.smoothscale(img, (nw, nh)), rect)
        return surf, rect

    def _draw_qr(self, avoid: Optional[pygame.Rect] = None):
        """QR rechts unten — fuer die Slideshow.

        `avoid` ist das Rechteck des Fotos. Passt die Karte in den Balken
        rechts daneben, rueckt sie dorthin und liegt damit auf keinem Bild
        mehr. Passt sie nicht, bleibt sie wie bisher auf dem Foto: bei einem
        16:9-Foto gibt es keinen Balken, und ein Code, der halb ueber den
        Schirmrand haengt, waere schlechter als einer auf dem Bild.
        """
        if self._qr_surf is None:
            return
        QR, PAD = self._qr_surf.get_width(), 12
        card = QR + PAD * 2
        x, y = W - QR - PAD, H - QR - PAD
        if avoid is not None and W - avoid.right >= card:
            # Mittig in den Balken, unten mit demselben Abstand wie sonst.
            x = avoid.right + (W - avoid.right - card) // 2 + PAD
        bg = pygame.Surface((card, card))
        bg.fill(self._qr_card_color())        # siehe _draw_qr_result
        bg.set_alpha(220)
        self._screen.blit(bg, (x - PAD, y - PAD))
        self._screen.blit(self._qr_surf, (x, y))

    # Layout-Anker für die Sidebar — gemeinsame Berechnung, sodass QR-Card
    # und WLAN-Box konsistent positioniert sind und sich nicht überlappen
    # können, egal welche Inhalte konfiguriert sind.

    def _sidebar_header_bottom(self) -> int:
        """y-Position direkt unterhalb des Event-Headers (Logo + Name + Sub).

        Rechnet ueber _header_blocks und beruecksichtigt damit sowohl
        umgebrochene Zeilen als auch eine von _fit_text gesenkte
        Schriftgroesse — die frueher angenommene eine Zeile je Block war
        bei langen Untertiteln schlicht falsch.
        """
        return SIDEBAR_PAD + LOGO_CIRCLE_R * 2 + 24 + self._header_height()

    def _wifi_rows(self) -> list:
        """Zeilen der WLAN-Box: (Label, Wert, Font).

        Eine Stelle fuer Hoehenrechnung und Zeichnen — standen die
        auseinander, sass die QR-Gruppe darueber an einer Oberkante, die
        es nicht gab.

        Hier stand einmal eine dritte Zeile mit der Galerie-Adresse zum
        Abtippen. Sie kostete 69 px, und die nahm sie der QR-Gruppe
        darueber weg: der Instagram-Code braucht 130 px, um bei 41 Modulen
        ueber der Lesbarkeitsgrenze zu bleiben, und fiel damit ersatzlos
        auf Text zurueck. Ein Code, der nicht mehr da ist, wiegt schwerer
        als eine Adresse, die kaum jemand tippt: der WLAN-Code bringt das
        Handy ins Netz, und das Captive-Portal schiebt die Galerie
        unmittelbar danach auf. Wer hier wieder eine Zeile ergaenzt, nimmt
        sie dem Instagram-Code — die Rechnung steht in _qr_group_bounds.
        """
        rows = []
        ssid = (self._cfg.get("wifi_ssid")     or "").strip()
        pwd  = (self._cfg.get("wifi_password") or "").strip()
        if ssid:
            rows.append(("WLAN", ssid, self._f_normal))
        if pwd:
            rows.append(("Passwort", pwd, self._f_normal))
        return rows

    def _wifi_box_metrics(self) -> tuple:
        """Liefert (top_y, height) der WLAN-Box. Nicht-konfigurierte Box
        liefert (H, 0) — dann gibt es nichts zu vermeiden."""
        rows = self._wifi_rows()
        if not rows:
            return (H, 0)
        label_h = self._f_label.get_height()
        box_h   = 22 + sum(label_h + 4 + f.get_height() + 14
                           for _, _, f in rows)
        # Knapp ueber der Status-Bar: die ist seit der echten Schrift
        # hoeher, und ein fester Randwert liess die WLAN-Box in sie
        # hineinlaufen. 12 px Luft dazwischen reichen optisch.
        margin_bottom = self._status_bar_height() + 12
        return (H - margin_bottom - box_h, box_h)

    def _qr_group_bounds(self) -> tuple:
        """(oberste, unterste) y-Grenze für die QR-Gruppe. Eine Stelle für
        beide Nutzer — _sidebar_qr_y positioniert damit, _social_layout
        prüft damit, und sie können nicht auseinanderlaufen."""
        return (self._sidebar_header_bottom() + 20,
                self._wifi_box_metrics()[0] - 20)

    def _group_height(self, rows: list, qr_size: int) -> int:
        """Gesamthöhe der QR-Group für eine konkrete Reihen-Fassung und
        Kachelgrösse. Reine Rechnung, ohne Entscheidung — die trifft
        _social_layout."""
        caption_h = self._f_sub.get_height() + 12
        social_h  = (16 + sum(self._social_row_height(r, qr_size) for r in rows)
                     if rows else 0)
        # Die Galerie-Card zaehlt mit derselben Kantenlaenge: alle drei
        # Muster sollen gleich gross sein, also schrumpfen sie gemeinsam.
        return self._qr_card_size(qr_size) + caption_h + social_h

    def _social_layout(self) -> tuple:
        """(Reihen, Kachelgrösse) in der Fassung, die wirklich passt.

        Zwei Stufen. Erst schrumpfen die Kacheln — sie sind das einzig
        Elastische, denn Header und WLAN-Box sitzen fest und der
        Galerie-Code ist der, den der Gast scannen soll. Reicht das bis
        SOCIAL_QR_MIN nicht, verliert die unterste Reihe ihren Code und
        fällt auf Glyph und Text zurück: der Link bleibt sichtbar, nur
        ohne eigenen Code.

        Beide Stufen werden gebraucht. Mit drei Codes und den grösseren
        Schriften bleiben für die Gruppe 509 px, während schon drei
        78-px-Kacheln 561 px brauchen — es gibt schlicht keine Grösse, bei
        der drei Codes hineinpassen. Vorher lief die Gruppe in so einem
        Fall einfach in die WLAN-Box.
        """
        top, bottom = self._qr_group_bounds()
        room = bottom - top
        rows = self._social_rows()

        # Ergebnis cachen. _draw_qr_card (ueber _sidebar_qr_y) und
        # _draw_social_links rufen das je Frame — ohne Cache lief die Suche
        # zweimal pro Bild UND loggte zweimal. Bei drei Codes und 30 fps
        # waren das 120 Warnzeilen pro Sekunde, die das Journal auf dem Pi
        # zugeschuettet haben. Der Schluessel enthaelt alles, was das
        # Ergebnis beeinflusst; die Warnung steht im Cache-Miss und faellt
        # damit genau einmal je Konfiguration an.
        key = (top, bottom, self._qr_card_size(),
               tuple((r[0], r[1], r[2], r[3] is not None) for r in rows))
        if self._social_cache and self._social_cache[0] == key:
            return self._social_cache[1]

        while True:
            # Die Groesse laeuft in ganzen Modulen des Galerie-Codes, denn
            # der wird in ihr neu gerendert statt skaliert. Krumme
            # Kantenlaengen kosten messbar: 125 px auf 113 heruntergerechnet
            # ergibt 4,5 px/Modul und 2 von 6 Stufen im Kameratest, direkt
            # auf 100 px gerendert sind es 4,0 px/Modul und 3 von 6. Harte
            # Modulkanten wiegen schwerer als ein paar Pixel Kantenlaenge.
            mods = self._qr_modules(self._qr_payload())
            k    = max(1, SOCIAL_QR_SIZE // mods)
            size = mods * k
            while (k > 1 and mods * (k - 1) >= SOCIAL_QR_MIN
                   and self._group_height(rows, size) > room):
                k -= 1
                size = mods * k
            if self._group_height(rows, size) <= room:
                self._social_cache = (key, (rows, size))
                return rows, size
            idx = next((i for i in range(len(rows) - 1, -1, -1)
                        if rows[i][3] is not None), None)
            if idx is None:
                # Selbst ohne jeden Code zu hoch — dann ist der Header oder
                # die WLAN-Box zu gross, daran kann die QR-Gruppe nichts
                # aendern. Sichtbar machen statt stumm ueberlappen.
                logger.warning(
                    "Sidebar überfüllt: QR-Gruppe braucht %d px, verfügbar "
                    "sind %d px, und es gibt keinen Code mehr abzugeben. "
                    "Kürzeren Untertitel setzen oder die WLAN-Box kürzen.",
                    self._group_height(rows, size), room)
                self._social_cache = (key, (rows, size))
                return rows, size
            logger.warning(
                "Sidebar zu eng für %d Codes: '%s' fällt auf Glyph und Text "
                "zurück. Die Gruppe bräuchte %d px, verfügbar sind %d px.",
                sum(1 for r in rows if r[3] is not None) + 1,
                rows[idx][1], self._group_height(rows, size), room)
            rows[idx] = rows[idx][:3] + (None,)

    def _qr_group_height(self, qr_size: Optional[int] = None) -> int:
        """Gesamthöhe der QR-Group: Card + Caption + (optional) Code-Reihen.

        `qr_size` überschreibt die Kantenlänge der Reihen-Codes; ohne
        Angabe wird die Fassung benutzt, die _social_layout ermittelt hat.
        """
        if qr_size is None:
            rows, qr_size = self._social_layout()
        else:
            rows = self._social_rows()
        return self._group_height(rows, qr_size)

    def _sidebar_qr_y(self) -> int:
        """y-Start der QR-Card. Vertikal zentriert zwischen Header und
        WLAN-Box, damit die Sidebar visuell ausgewogen wirkt.
        """
        top, bottom = self._qr_group_bounds()
        total  = self._qr_group_height()
        y      = top + ((bottom - top) - total) // 2
        return max(top, y)

    # Kandidaten für den Akzent in den Augenkernen, in dieser Reihenfolge.
    # Genommen wird der erste, der zwei Hürden nimmt: genug Kontrast zum
    # Grund (sonst leidet die Finder-Erkennung) UND genug Abstand zur
    # Modulfarbe (sonst ist der Akzent gesetzt, aber nicht zu sehen).
    #
    # Beide Hürden sind nötig, und zwar wegen realer Themes: bordeaux
    # setzt logo_text exakt auf sidebar_bg und accent_dim nur ΔE 39
    # daneben — reine Ungleichheit hätte hier einen unsichtbaren Akzent
    # durchgewinkt. In braun fällt umgekehrt accent durch, weil es auf
    # Creme nur 1,85:1 bringt.
    _QR_EYE_KEYS      = ("accent", "logo_text", "accent_dim", "panel_border")
    _QR_EYE_MIN_DELTA = 60

    def _qr_card_color(self) -> tuple:
        """Grundfarbe der Code-Karten — bewusst nicht immer logo_circle.

        QR-Codes brauchen dunkle Module auf hellem Grund und eine helle
        Ruhezone. In dunklen Themes war beides verletzt: bei "Royal Night"
        (logo_circle #1A2540) fiel der Galerie-Code auf Schwarz-auf-Weiss
        zurueck und sass als weisser Block auf dunkelblauem Rand, der als
        Ruhezone nichts taugt. Instagrams Code verlor seinen Kontrast ganz,
        weil _white_to_alpha sein Weiss durchsichtig macht und darunter das
        Dunkelblau stand.

        Ist logo_circle hell genug, bleibt es dabei — dann behalten helle
        Themes ihren Cremeton. Sonst wird die Karte hell, auch wenn sie
        sich damit vom Theme absetzt. Ein Code, den niemand scannt, ist
        teurer als eine Karte, die auffaellt.
        """
        card = self._theme["logo_circle"]
        if UI._contrast(card, (0, 0, 0)) >= self.QR_CARD_MIN_CONTRAST:
            return card
        return (245, 245, 245)

    def _qr_payload(self) -> str:
        """Inhalt des Sidebar-Codes: der Galerie-Link.

        Eigene Methode, weil Layout, Cache und Live-Reload alle danach
        fragen — und weil hier einmal mehr stand als ein Dict-Zugriff
        (siehe den Kommentar in config.py zum ausgebauten WLAN-Payload).
        """
        return self._cfg.get("gallery_url", "")

    def _qr_colors(self) -> dict:
        """Theme-Farben für den Galerie-QR: Module im Sidebar-Ton, Grund in
        der Cremefarbe der Karte — so verschwindet die Quiet-Zone in ihr,
        statt als weisses Quadrat aufzusetzen. Dazu ein Akzent in den
        Augenkernen, sofern das Theme einen hergibt, der sich sowohl von
        der Modulfarbe als auch vom Grund abhebt.
        """
        fg  = self._theme["sidebar_bg"]
        bg  = self._qr_card_color()
        eye = next((c for c in (self._theme[k] for k in self._QR_EYE_KEYS)
                    if UI._contrast(c, bg) >= UI.QR_MIN_CONTRAST
                    and UI._color_distance(c, fg) >= self._QR_EYE_MIN_DELTA),
                   None)
        return {"fg": fg, "bg": bg, "eye": eye}

    @staticmethod
    @functools.lru_cache(maxsize=8)
    def _qr_modules(url: str) -> int:
        """Modulzahl des Codes fuer diese URL, ohne Ruhezone.

        Rechnet nur, rendert nicht — gebraucht, um Ruhezone und
        Kachelgroessen zu bemessen, bevor irgendein Bild existiert.
        """
        try:
            import qrcode
            qr = qrcode.QRCode(border=0)
            qr.add_data(url)
            qr.make(fit=True)
            return qr.modules_count
        except Exception:
            return 25

    def _qr_module_px(self, size: int) -> int:
        """Modulbreite, die _make_qr bei dieser Zielgroesse waehlen wird."""
        return max(1, size // self._qr_modules(self._qr_payload()))

    def _qr_pad(self) -> int:
        """Cremerand um jede Code-Kachel — zugleich deren Quiet-Zone.

        Ein Wert fuer alle drei Kacheln, damit sie gleich aussehen: der
        Galerie-Code sass frueher 30 px vom Kartenrand entfernt und die
        Social-Codes 16 px, weil nur der Galerie-Code seine Ruhezone im
        Bild trug.

        Bemessen wird am groebsten Raster, und das ist der Galerie-Code —
        25 Module gegenueber 41 bei Instagram. Wer die 4 Module der QR-Norm
        dort schafft, schafft sie bei den feineren Codes erst recht.
        """
        return max(SOCIAL_QR_PAD, 4 * self._qr_module_px(self.QR_SIZE))

    def _qr_card_size(self, side: Optional[int] = None) -> int:
        """Kantenlänge der Galerie-QR-Card zu einer Muster-Kantenlänge.

        Ohne Angabe wird die Breite des vorhandenen Codes benutzt. Beim
        Durchprobieren in _social_layout muss dagegen die Grösse zählen,
        die dort gerade getestet wird — sonst rechnet die Layoutprüfung
        mit einer Card, die es hinterher nicht gibt.
        """
        if side is None:
            side = (self._qr_surf.get_width() if self._qr_surf is not None
                    else SOCIAL_QR_SIZE)
        return side + self._qr_pad() * 2

    def _gallery_qr(self, side: int) -> Optional[pygame.Surface]:
        """Galerie-Code in der Ziel-Kantenlaenge, neu gerendert statt
        skaliert — siehe die Begruendung in _social_layout. Das Ergebnis
        wird gecacht, weil die Sidebar jeden Frame neu gezeichnet wird.

        Der Schluessel traegt URL und Farben mit, nicht nur die
        Kantenlaenge. Ohne sie ueberlebte der Code jeden Theme-Wechsel:
        _check_config_reload baute zwar _qr_surf neu, hier kam aber
        weiterhin die alte Fassung heraus. Und weil _social_layout den
        Code in der engen Sidebar fast immer verkleinert, lief praktisch
        jeder Frame ueber diesen Cache — sichtbar wurde es als heller
        Block, der seinen alten Grund behielt, waehrend die Karte
        darunter schon die neue Farbe hatte.
        """
        if self._qr_surf is None:
            return None
        if self._qr_surf.get_width() == side:
            return self._qr_surf
        colors = self._qr_colors()
        payload = self._qr_payload()
        key = (side, payload, colors["fg"], colors["bg"], colors["eye"])
        cached = self._qr_scaled
        if cached and cached[0] == key:
            return cached[1]
        surf = self._make_qr(payload, size=side, border=0,
                             **colors) or self._qr_surf
        self._qr_scaled = (key, surf)
        return surf

    def _draw_qr_card(self):
        """QR auf cremig-weißem Container in der Sidebar — vertikal mittig.
        Caption und Code-Reihen werden direkt darunter gezeichnet.
        """
        cx = SIDEBAR_W // 2
        PAD    = self._qr_pad()
        _, side = self._social_layout()
        qr = self._gallery_qr(side)
        card_w = card_h = self._qr_card_size(side)
        y = self._sidebar_qr_y()

        card = pygame.Rect(cx - card_w // 2, y, card_w, card_h)
        pygame.draw.rect(self._screen, self._qr_card_color(),
                         card, border_radius=10)

        if qr is not None:
            self._screen.blit(qr, (card.x + PAD, card.y + PAD))
        else:
            err = self._f_small.render("QR fehlt", True, self._theme["panel_bg"])
            self._screen.blit(err, err.get_rect(center=card.center))

        hint = self._f_sub.render(self._qr_caption(), True,
                                  self._theme["sidebar_text"])
        # Breitenklammer wie in der WLAN-Box: die Sidebar ist 320 px breit,
        # und eine laengere Beschriftung (oder eine groessere Schrift) liefe
        # sonst stumm ueber ihren Rand hinaus.
        if hint.get_width() > SIDEBAR_W - 24:
            scale = (SIDEBAR_W - 24) / hint.get_width()
            hint = pygame.transform.smoothscale(
                hint, (int(hint.get_width() * scale),
                       int(hint.get_height() * scale)))
        hint_y = card.bottom + 12
        self._screen.blit(hint, hint.get_rect(centerx=cx, top=hint_y))

        self._draw_social_links(cx, hint_y + hint.get_height() + 16)

    def _qr_caption(self) -> str:
        """Beschriftung unter dem Code — zugleich die Anleitung.

        Der Code traegt den Galerie-Link. Wer ihn scannt, ohne im WLAN zu
        sein, bekommt eine Fehlerseite von Safari und keinen Hinweis, was
        fehlt — deshalb steht die Reihenfolge hier, und zwar bevor er
        scannt. Die Zeile zeigt nach unten auf die WLAN-Box, wo SSID und
        Passwort stehen.

        Eine Zeile, keine zwei: in der Sidebar sind 503 px verfuegbar und
        503 px gebraucht (_qr_group_bounds). Was hier dazukommt, nimmt der
        Instagram-Code seine 130 px — das ist heute schon zweimal
        passiert. Die ausfuehrliche Fassung steht auf dem Ergebnis-Schirm,
        der Platz hat (_wifi_hint).

        Ohne eigenen Hotspot haengt die Box in einem fremden Netz, in dem
        der Gast ohnehin schon steckt. Dann waere die Reihenfolge eine
        Belehrung ohne Anlass.
        """
        if self._cfg.get("hotspot_enabled", True):
            return "Erst WLAN, dann scannen"
        return "Fotos auf's Handy"

    def _social_rows(self) -> list:
        """[(icon_type, zeile1, zeile2|None, qr_surface|None)]."""
        rows = []
        insta = (self._cfg.get("instagram_url") or "").strip()
        if insta:
            # Mit hinterlegtem instagram_qr_path tritt Instagrams eigener
            # Code an die Stelle des Glyphs — er ist an seiner Optik sofort
            # als Instagram erkennbar und wirkt deshalb nicht wie ein
            # zweiter, konkurrierender Code neben dem Galerie-QR.
            rows.append(("instagram", self._instagram_handle(insta),
                         None, self._insta_qr))
        booking = (self._cfg.get("booking_url") or "").strip()
        if booking:
            # Zweite Zeile mit der nackten Domain. "Termin buchen" allein war
            # eine Sackgasse — es sagt dem Gast, dass es etwas zu buchen gibt,
            # aber nicht wo. Die Domain kann er sich merken oder abtippen.
            label = (self._cfg.get("booking_label") or "").strip()
            rows.append(("calendar", label or "Termin buchen",
                         self._domain_of(booking), self._booking_qr))
        return rows

    def _social_row_height(self, row, qr_size: Optional[int] = None) -> int:
        """Höhe einer Reihe inklusive Abstand zur nächsten.

        `qr_size` ist die Kantenlänge, mit der die Kachel gezeichnet wird
        — nicht zwingend die des geladenen Surfaces, siehe _social_layout.
        """
        _, line1, line2, surf = row
        text_h = self._f_sub.get_height()
        if line2:
            text_h += self._f_label.get_height() + 2
        if surf is not None:
            side = surf.get_height() if qr_size is None else qr_size
            # Code über der Beschriftung — wie die Galerie-Card darüber.
            return (side + self._qr_pad() * 2 + 6 + text_h + SOCIAL_ROW_GAP)
        return max(text_h, SOCIAL_ICON) + SOCIAL_ROW_GAP

    @staticmethod
    def _fit_social(surf: pygame.Surface, side: int) -> pygame.Surface:
        """Kachel auf die effektive Kantenlänge bringen. Stimmt sie schon,
        wird das Original durchgereicht — der Normalfall."""
        if surf.get_width() == side:
            return surf
        return pygame.transform.smoothscale(surf, (side, side))

    @staticmethod
    def _domain_of(url: str) -> str:
        """'https://bytebots.de/termine' → 'bytebots.de'."""
        rest = url.split("://", 1)[-1].split("/", 1)[0]
        return rest[4:] if rest.startswith("www.") else rest

    def _draw_social_links(self, cx: int, y: int):
        """Instagram und Terminbuchung unter dem Galerie-QR.

        Alles zentriert und gestapelt, wie die Galerie-Card darüber: ein
        Code mit seiner Beschriftung darunter. Nebeneinander gesetzt bliebe
        in einer 320 px breiten Sidebar für den Text zu wenig übrig, und
        die Zeile klebte am rechten Rand.

        Der Galerie-Code bleibt der einzige selbst erzeugte QR — er ist die
        eine Sache, die der Gast an der Box tun soll. Instagrams eigener
        Code ist die Ausnahme, wenn er hinterlegt ist: den erkennt man an
        seiner Optik, statt ihn erst scannen zu müssen um zu wissen was
        drin ist. Erzeugen können wir ihn nicht, er kommt als Bild aus der
        App (instagram_qr_path).

        Der Buchungs-Link darf seit booking_qr_path ebenfalls einen eigenen
        Code tragen. Der Gast braucht ihn nicht — er hängt im Fotobox-WLAN
        und damit in der Galerie, wo der Button steht. Gedacht ist er für
        alle anderen: Gäste, die abends abfotografieren, wo die Box herkam.
        Ohne hinterlegtes Bild bleibt es bei Glyph und Domain; die Domain
        steht in beiden Fällen in der zweiten Zeile, weil ein Label ohne
        nennbares Ziel eine Sackgasse ist.
        """
        rows, qr_size = self._social_layout()
        if not rows:
            return

        # Frueher gab es das Glyph nur, solange keine Reihe einen echten Code
        # trug — die Sorge war, ein kleines Symbol neben einer 130-px-Kachel
        # wirke wie ein Versehen. Es steht aber gar nicht neben der Kachel,
        # sondern in der Reihe darunter neben ihrem Text, und dort fehlte der
        # Reihe jedes Erkennungszeichen. Sie bekommt es jetzt immer.

        ry = y
        for row in rows:
            icon_type, line1, line2, surf = row
            lbl = self._f_sub.render(line1, True, self._theme["sidebar_text"])
            sub = (self._f_label.render(line2, True,
                                        self._readable(self._theme["accent"]))
                   if line2 else None)

            if surf is not None:
                surf = self._fit_social(surf, qr_size)
                pad    = self._qr_pad()
                card_w = surf.get_width() + pad * 2
                card_h = surf.get_height() + pad * 2
                card = pygame.Rect(cx - card_w // 2, ry, card_w, card_h)
                pygame.draw.rect(self._screen, self._qr_card_color(),
                                 card, border_radius=8)
                self._screen.blit(surf, (card.x + pad, card.y + pad))
                ty = card.bottom + 6
                self._screen.blit(lbl, lbl.get_rect(centerx=cx, top=ty))
                if sub:
                    self._screen.blit(
                        sub, sub.get_rect(centerx=cx,
                                          top=ty + lbl.get_height() + 2))
            else:
                text_w = max(lbl.get_width(),
                             sub.get_width() if sub else 0)
                block_w = SOCIAL_ICON + 12 + text_w
                x0 = cx - block_w // 2
                row_h = self._social_row_height(row, qr_size) - SOCIAL_ROW_GAP
                # Das Symbol traegt dieselbe erzwungen lesbare Farbe wie die
                # Domain darunter. Ohne _readable naehme es theme["accent"] —
                # im dunklen Theme der Box 1,26:1 gegen den Grund, es waere
                # also da und trotzdem nicht zu sehen.
                icon_color = self._readable(self._theme["accent"])
                iy = ry + (row_h - SOCIAL_ICON) // 2
                if icon_type == "instagram":
                    self._draw_instagram_icon(x0, iy, SOCIAL_ICON, icon_color)
                else:
                    self._draw_calendar_icon(x0, iy, SOCIAL_ICON, icon_color)
                tx = x0 + SOCIAL_ICON + 12
                text_h = lbl.get_height() + (sub.get_height() + 2 if sub else 0)
                ty = ry + (row_h - text_h) // 2
                self._screen.blit(lbl, (tx, ty))
                if sub:
                    self._screen.blit(sub, (tx, ty + lbl.get_height() + 2))

            ry += self._social_row_height(row, qr_size)

    def _draw_instagram_icon(self, x: int, y: int, size: int, color=None):
        """Vereinfachtes Instagram-Logo: gerundetes Quadrat + Kreis innen
        + kleiner Punkt rechts oben (Flash). Programmatisch gezeichnet."""
        color = color or self._theme["accent"]
        pygame.draw.rect(self._screen, color, (x, y, size, size),
                         width=2, border_radius=size // 5)
        pygame.draw.circle(self._screen, color,
                           (x + size // 2, y + size // 2), size // 4, width=2)
        pygame.draw.circle(self._screen, color,
                           (x + size - 5, y + 5), 1)

    def _draw_calendar_icon(self, x: int, y: int, size: int, color=None):
        """Kalenderblatt: Koerper, gefuellter Kopf, zwei Ringe, ein Datum.

        Der gefuellte Kopfbalken ist der Unterschied zwischen "Rechteck mit
        Strichen" und "Kalender" — er gibt dem Zeichen die Silhouette, an der
        man es auf zwei Meter erkennt. Der Punkt darunter steht fuer den
        angestrichenen Tag und fuellt die sonst leere Flaeche.

        Alle Masse sind Anteile von `size`, damit das Zeichen bei einer
        anderen Groesse nicht auseinanderfaellt.
        """
        color = color or self._theme["accent"]
        ring_h = max(3, size // 6)
        body = pygame.Rect(x, y + ring_h, size, size - ring_h)
        head_h = max(5, size // 4)

        # Ringe zuerst: der Koerper deckt ihre Unterkante ab.
        ring_w = max(2, size // 10)
        for rx in (x + size // 4, x + size - size // 4 - ring_w):
            pygame.draw.rect(self._screen, color,
                             (rx, y, ring_w, ring_h * 2), border_radius=1)

        pygame.draw.rect(self._screen, color, body, width=2, border_radius=4)
        pygame.draw.rect(self._screen, color,
                         (body.x, body.y, body.width, head_h),
                         border_top_left_radius=4, border_top_right_radius=4)

        dot = max(3, size // 6)
        pygame.draw.rect(self._screen, color,
                         (body.centerx - dot // 2,
                          body.y + head_h + (body.height - head_h - dot) // 2,
                          dot, dot), border_radius=1)

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
        """WLAN und Passwort als eigene Box mit Border-Akzent unten in der
        Sidebar."""
        rows = self._wifi_rows()
        if not rows:
            return

        box_w = SIDEBAR_W - 40
        # Position und Hoehe kommen aus _wifi_box_metrics, nicht aus einer
        # zweiten Rechnung. Hier stand frueher ein eigenes `margin_bottom =
        # 56` samt Kopie der Hoehenformel — der Anker, an dem sich die
        # QR-Gruppe ausrichtet, meinte damit eine Oberkante, die 7 px
        # neben der gezeichneten lag.
        y, box_h = self._wifi_box_metrics()

        x = (SIDEBAR_W - box_w) // 2
        box = pygame.Rect(x, y, box_w, box_h)

        pygame.draw.rect(self._screen, self._theme["panel_bg"],
                         box, border_radius=10)
        pygame.draw.rect(self._screen, self._theme["panel_border"],
                         box, width=2, border_radius=10)

        ty = y + 14
        for label, value, font in rows:
            lbl = self._f_label.render(label, True, self._theme["sidebar_dim"])
            self._screen.blit(lbl, (x + 16, ty))
            ty += lbl.get_height() + 2
            val = font.render(value, True, self._theme["sidebar_text"])
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
    def _load_social_qr(path: str,
                        label: str = "Sidebar-QR") -> Optional[pygame.Surface]:
        """Lädt einen fertigen QR-Code (Instagrams eigenen) für die Sidebar.
        Leerer Pfad oder fehlende Datei → None, dann zeichnet
        _draw_social_links wieder das Glyph.

        Instagrams Code lässt sich nicht selbst erzeugen — er kommt als Bild
        aus der App, und zwar als grosse Kachel: weisse Karte, viel Rand,
        darunter das Handle als Schriftzug. Beides wird hier automatisch
        entfernt, damit der Owner nichts von Hand zuschneiden muss:

        * Der Schriftzug fliegt raus. Er steht ohnehin als Text daneben, und
          jeder Pixel, den er belegt, fehlt dem Code beim Verkleinern.
        * Der Rand fliegt raus, der Code füllt die Kachel.
        * Das Weiss wird transparent, damit der Code auf der Cremekachel der
          Sidebar sitzt statt in einem weissen Rechteck darauf.

        Das Weiss wird bewusst nur durch die *helle* Kachel ersetzt und nicht
        durch das Sidebar-Braun: ein QR-Code braucht dunkle Module auf hellem
        Grund. Auf dem Braun wäre der Kontrast umgekehrt, und daran scheitern
        viele Scanner.
        """
        if not path or not os.path.isfile(path):
            if path:
                logger.warning("%s: '%s' nicht gefunden — nutze Glyph",
                               label, path)
            return None
        try:
            from PIL import Image
            img = Image.open(path).convert("RGBA")
        except Exception as exc:
            logger.warning("%s '%s' nicht ladbar: %s — nutze Glyph",
                           label, path, exc)
            return None

        original = img.size
        try:
            img = UI._crop_to_code(img)
            img = UI._white_to_alpha(img)
        except Exception as exc:
            # Lieber ungeschnitten anzeigen als gar nicht.
            logger.warning("%s '%s': Aufbereitung fehlgeschlagen "
                           "(%s) — nehme das Bild unveraendert",
                           label, path, exc)

        side  = max(img.size) or 1
        scale = SOCIAL_QR_SIZE / side
        size  = (max(1, round(img.width * scale)),
                 max(1, round(img.height * scale)))
        small = img.resize(size, Image.LANCZOS)
        surf  = pygame.image.frombuffer(
            small.tobytes("raw", "RGBA"), size, "RGBA").convert_alpha()
        logger.info("%s geladen (%s, %dx%d → beschnitten %dx%d "
                    "→ %dx%d)", label, path, *original, *img.size, *size)
        return surf

    @staticmethod
    def _crop_to_code(img):
        """Schneidet Rand und Handle-Schriftzug weg, lässt nur den Code."""
        arr   = np.array(img)
        rgb   = arr[..., :3].astype(np.int16)
        alpha = arr[..., 3]
        # "Tinte" = sichtbar und nicht nahezu weiss.
        ink = (alpha > 40) & (rgb.min(axis=2) < 220)
        if not ink.any():
            return img

        rows   = ink.any(axis=1)
        top    = int(np.argmax(rows))
        bottom = int(len(rows) - np.argmax(rows[::-1]))

        band = UI._caption_gap(rows, top, bottom)
        if band is not None:
            bottom = band

        cols  = ink[top:bottom].any(axis=0)
        left  = int(np.argmax(cols))
        right = int(len(cols) - np.argmax(cols[::-1]))
        return img.crop((left, top, right, bottom))

    @staticmethod
    def _caption_gap(rows, top: int, bottom: int) -> Optional[int]:
        """y, ab dem der Handle-Schriftzug beginnt — oder None.

        Instagram setzt ihn als eigene Zeile unter den Code, getrennt durch
        ein leeres Band. Gesucht ist deshalb das breiteste leere Band in der
        unteren Hälfte. Die schmalen Lücken zwischen den Punktreihen des
        Codes sind um Grössenordnungen kleiner und fallen durch das
        Mindestmass heraus.
        """
        threshold = top + int((bottom - top) * 0.55)
        min_band  = max(4, int((bottom - top) * 0.02))
        best, best_len, start = None, 0, None
        for y in range(top, bottom):
            if not rows[y]:
                if start is None:
                    start = y
            elif start is not None:
                if start >= threshold and (y - start) > best_len:
                    best, best_len = start, y - start
                start = None
        return best if best_len >= min_band else None

    @staticmethod
    def _white_to_alpha(img):
        """Weissen Kartenhintergrund transparent machen.

        Kein harter Schwellwert: die Punkte sind weich gegen Weiss gerendert,
        ein Keying liesse an jeder Kante einen hellen Saum stehen. Stattdessen
        wird das Bild als farbige Tinte *auf* Weiss aufgefasst und diese
        Komposition umgekehrt — wie weit ein Pixel vom reinen Weiss entfernt
        ist, ergibt sein Alpha.
        """
        from PIL import Image

        arr   = np.array(img).astype(np.float32)
        rgb   = arr[..., :3]
        alpha = arr[..., 3:4] / 255.0
        # So sieht der Pixel aus, wenn das Bild auf Weiss liegt.
        over = rgb * alpha + 255.0 * (1.0 - alpha)
        new_alpha = 255.0 - over.min(axis=2, keepdims=True)
        safe = np.maximum(new_alpha / 255.0, 1e-6)
        new_rgb = np.clip((over - 255.0 * (1.0 - safe)) / safe, 0, 255)
        out = np.concatenate([new_rgb, new_alpha], axis=2).astype(np.uint8)
        return Image.fromarray(out, "RGBA")

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

    # ── Galerie-QR ────────────────────────────────────────────────────────────
    # Der Galerie-Code ist der einzige QR, den die Box selbst erzeugt — er
    # darf deshalb gestaltet werden, anders als Instagrams fertige Grafik:
    # runde Module, eckige Augen, Augenkerne im Goldton des Themes.
    #
    # Gegen die frühere schwarz-weisse Fassung geprüft mit _qr_readable,
    # einmal pixelgenau und viermal verkleinert plus weichgezeichnet (grob
    # das, was die Handykamera aus Distanz sieht): identisches Ergebnis.
    # Die Gestaltung kostet also keine Scanbarkeit. Begrenzend ist die
    # Kantenlänge — bei size=160 und 33 Modulen bleiben 5 px pro Modul.
    # Zielkantenlänge des Galerie-Codes, bewusst an SOCIAL_QR_SIZE
    # gekoppelt: beide Codes der Sidebar sollen gleich gross sein. Wer
    # einen davon ändert, ändert absichtlich beide.
    #
    # Das ist eine Gestaltungsentscheidung mit gemessenem Preis. _make_qr
    # rundet auf ganze Module auf, 130 landet bei 132 px — 4 px pro Modul.
    # Im Decodertest mit Verkleinerung und Unschärfe (grob die Handykamera
    # aus Distanz) kommt der Code damit auf 1 von 6 Stufen; bei 200 waren
    # es 231 px, 7 px/Modul und 4 von 6.
    #
    # Wer am Eventabend Scan-Probleme sieht, dreht deshalb hier und nicht
    # an den Farben — die Gestaltung kostet nachweislich nichts, die
    # Kantenlänge alles.
    QR_SIZE         = SOCIAL_QR_SIZE
    # Der Code auf dem Ergebnis-Schirm ist deutlich groesser, und das muss
    # er sein: er traegt eine ganze Foto-URL statt der kurzen WLAN-Daten.
    # Mit einem realistischen Eventnamen sind das 37 bis 41 Module — bei
    # 130 px waeren das 3 px je Modul, bei 260 px sind es 6 bis 7. Platz
    # ist da: 260 px sind auf 1920 px Breite ein Siebtel.
    RESULT_QR_SIZE  = 260
    # Breite der Spalte rechts, in der der Foto-Code sitzt. Das Foto wird nur
    # in den Rest hineingerechnet, statt den ganzen Schirm zu fuellen: vorher
    # lag der Code oben rechts AUF dem Bild und verdeckte genau das, was der
    # Gast sich gerade ansieht. Aus der Kachelgroesse abgeleitet, damit beide
    # nicht auseinanderlaufen — 16 px Innenrand je Seite wie in
    # _draw_qr_result, dazu 24 px Luft nach aussen und zum Bild.
    RESULT_QR_COL   = RESULT_QR_SIZE + 2 * 16 + 2 * 24
    QR_BOX          = 10     # Rendergrösse je Modul vor dem Herunterskalieren.
    QR_MIN_CONTRAST = 3.0    # WCAG-Verhältnis Modul zu Grund, sonst s/w.
    # Ab welcher Helligkeit logo_circle als Kartengrund taugt (Verhältnis
    # gegen Schwarz). Cremetoene liegen bei 15-17:1, das dunkle Navy von
    # "Royal Night" (#1A2540) bei 1,6:1.
    QR_CARD_MIN_CONTRAST = 8.0

    @staticmethod
    def _contrast(a, b) -> float:
        """WCAG-Kontrastverhältnis zweier RGB-Farben (1.0 bis 21.0)."""
        def lum(c):
            v = [x / 255.0 for x in c[:3]]
            v = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
                 for x in v]
            return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]
        hi, lo = sorted((lum(a), lum(b)), reverse=True)
        return (hi + 0.05) / (lo + 0.05)

    @staticmethod
    def _color_distance(a, b) -> float:
        """Wahrgenommener Farbabstand (Riemersma), nicht euklidisch: Rot-
        und Blauanteil werden je nach Helligkeit unterschiedlich gewichtet.

        Gebraucht, weil "andere Farbe" und "sichtbar andere Farbe" zwei
        verschiedene Dinge sind — #6E2A3A und #5C1F30 sind ungleich, aber
        nebeneinander nicht zu unterscheiden.
        """
        rm = (a[0] + b[0]) / 2
        dr, dg, db = a[0] - b[0], a[1] - b[1], a[2] - b[2]
        return math.sqrt((2 + rm / 256) * dr * dr + 4 * dg * dg
                         + (2 + (255 - rm) / 256) * db * db)

    @staticmethod
    def _qr_readable(img) -> bool:
        """Liest der Decoder den fertig skalierten Code noch?

        Diagnose, kein Gate: schlägt der Test selbst fehl, gilt der Code
        als in Ordnung — ein streikendes Testwerkzeug darf die Sidebar
        nicht leer lassen.
        """
        try:
            gray = cv2.cvtColor(np.array(img.convert("RGB")),
                                cv2.COLOR_RGB2GRAY)
            return bool(cv2.QRCodeDetector().detectAndDecode(gray)[0])
        except Exception as exc:
            logger.debug("QR-Decodetest nicht möglich: %s", exc)
            return True

    @staticmethod
    def _qr_pil(qr, fg: tuple, bg: tuple, eye: Optional[tuple]):
        """Zeichnet den Code als PIL-Bild. Rückgabe: (Bild, gestaltet?).

        Fehlt der styledpil-Zweig der qrcode-Lib (ältere Installation als
        das in requirements.txt gepinnte 8.2), wird eckig gezeichnet: die
        Gestaltung ist Kür, ein lesbarer Code ist Pflicht.
        """
        from PIL import ImageDraw
        styled = True
        try:
            from qrcode.image.styledpil import StyledPilImage
            from qrcode.image.styles.colormasks import SolidFillColorMask
            from qrcode.image.styles.moduledrawers.pil import (
                RoundedModuleDrawer, SquareModuleDrawer)
            img = qr.make_image(
                image_factory=StyledPilImage,
                module_drawer=RoundedModuleDrawer(radius_ratio=1),
                # Die drei Finder bleiben eckig — an ihnen findet der
                # Scanner den Code überhaupt erst.
                eye_drawer=SquareModuleDrawer(),
                color_mask=SolidFillColorMask(back_color=bg, front_color=fg),
            ).get_image().convert("RGB")
        except ImportError as exc:
            logger.info("qrcode-Styles fehlen (%s) — eckige Module", exc)
            img = qr.make_image(fill_color=fg,
                                back_color=bg).get_image().convert("RGB")
            styled = False

        if eye is not None:
            # Nur der innere 3x3-Kern der Finder trägt Farbe. Der Ring
            # darum muss die Modulfarbe behalten, sonst verliert die
            # Finder-Erkennung ihr 1:1:3:1:1-Verhältnis.
            box   = qr.box_size
            total = qr.modules_count + 2 * qr.border
            d     = ImageDraw.Draw(img)
            for ox, oy in ((qr.border, qr.border),
                           (total - qr.border - 7, qr.border),
                           (qr.border, total - qr.border - 7)):
                d.rectangle(((ox + 2) * box, (oy + 2) * box,
                             (ox + 5) * box - 1, (oy + 5) * box - 1),
                            fill=eye)
        return img, styled

    @staticmethod
    def _make_qr(url: str, size: int = 160, border: int = 4,
                 fg: tuple = (0, 0, 0), bg: tuple = (255, 255, 255),
                 eye: Optional[tuple] = None) -> Optional[pygame.Surface]:
        """QR-Surface in Theme-Farben, hochskaliert auf ein ganzzahliges
        Vielfaches der Modulbreite.

        Die gelieferte Kantenlänge ist deshalb meist etwas grösser als
        `size` — Aufrufer müssen sie am Surface ablesen statt anzunehmen.
        Der Grund: bei krummer Skalierung bekommt eine Modulspalte 2 und
        die nächste 3 Pixel, und genau daran scheitern Handy-Scanner auf
        den kleinen Kacheln.

        `border` ist die Quiet-Zone in Modulen. 0 ist zulaessig und der
        Normalfall in der Sidebar: dort liefert der Cremerand der Karte die
        Ruhezone, genau wie bei den Social-Codes, die _load_social_qr auf
        ihr Muster beschneidet. Steckt die Ruhezone dagegen im Bild, ist
        das sichtbare Muster kleiner als die Kachel daneben und sitzt
        weiter vom Rand weg — beides fiel im Vergleich sofort auf.

        `fg`/`bg` sind Modul- und Grundfarbe, `eye` faerbt die inneren
        Kerne der drei Finder.

        Reichen fg/bg nicht für QR_MIN_CONTRAST, fällt die Farbwahl still
        auf Schwarz-Weiss zurück: der Mieter kann jede Theme-Farbe frei
        setzen, und ein hübscher, aber unscannbarer Code wäre am
        Eventabend teurer als ein hässlicher.
        """
        if not url:
            logger.warning("QR-Code: keine Adresse — gallery_url leer in "
                           "der config?")
            return None
        try:
            import qrcode
            from PIL import Image

            fg, bg = tuple(fg), tuple(bg)
            eye = tuple(eye) if eye is not None else None

            ratio = UI._contrast(fg, bg)
            if ratio < UI.QR_MIN_CONTRAST:
                logger.warning(
                    "QR-Code: Kontrast Modul/Grund nur %.1f:1 (< %.1f) — "
                    "Theme-Farben verworfen, zeichne schwarz auf weiss",
                    ratio, UI.QR_MIN_CONTRAST)
                fg, bg, eye = (0, 0, 0), (255, 255, 255), None
            if eye is not None and UI._contrast(eye, bg) < UI.QR_MIN_CONTRAST:
                logger.info("QR-Code: Augenfarbe zu kontrastarm — Kerne "
                            "bleiben in Modulfarbe")
                eye = None

            qr = qrcode.QRCode(border=border, box_size=UI.QR_BOX)
            qr.add_data(url)
            qr.make(fit=True)
            total = qr.modules_count + 2 * border
            # Abrunden, nicht auf: `size` ist der Platz, der zur Verfuegung
            # steht, und die Kachel daneben ist genauso breit. Aufrunden
            # lieferte frueher 165 px fuer size=160 und liess den Code aus
            # seinem Feld herausragen.
            scale = max(1, size // total)
            px    = total * scale

            # Unter 4 px je Modul wird der Code auf Distanz und bei leichter
            # Unschaerfe wackelig — der Gast muss dann naeher ran. Die
            # Stellschraube ist nicht die Gestaltung (die kostet nachweislich
            # nichts, siehe Kommentar an QR_SIZE), sondern das Verhaeltnis von
            # Inhaltslaenge zu Kantenlaenge. Gemessen: der WLAN-Payload waechst
            # mit SSID und Passwort (29 Module bei "Fotobox" plus 10 Zeichen,
            # 33 bei einem langen Eventnamen als SSID), die Foto-URL mit dem
            # Eventordner (41 Module) — die bekommt auf dem Ergebnis-Schirm
            # deshalb RESULT_QR_SIZE statt QR_SIZE.
            if scale < 4:
                logger.warning(
                    "QR-Code für %s: nur %d px je Modul (%d Module auf "
                    "%d px) — kürzerer Inhalt oder grössere Kachel machen "
                    "das Muster gröber und damit besser scannbar",
                    url, scale, total, px)

            img, styled = UI._qr_pil(qr, fg, bg, eye)
            # Runde Module leben von geglätteten Kanten, eckige von harten
            # — deshalb hier zwei Filter statt einem.
            img  = img.resize((px, px),
                              Image.LANCZOS if styled else Image.NEAREST)

            # Der Decodetest braucht die Ruhezone. Steckt sie nicht im Bild
            # (border=0, weil die Kachel sie beisteuert), wird sie hier nur
            # fuer den Test angesetzt — sonst meldet der Decoder einen
            # Fehler, den es auf dem Bildschirm gar nicht gibt.
            test, quiet = img, max(0, 4 - border) * scale
            if quiet:
                test = Image.new("RGB", (px + 2 * quiet,) * 2, bg)
                test.paste(img, (quiet, quiet))
            if not UI._qr_readable(test):
                logger.warning(
                    "QR-Code für %s ist bei %d px nicht decodierbar — "
                    "QR-Card vergrössern oder Theme-Farben prüfen", url, px)

            surf = pygame.image.frombuffer(
                img.tobytes("raw", "RGB"), (px, px), "RGB").copy()
            logger.info("QR-Code erstellt für %s (%d Module → %dx%d px, %s)",
                        url, total, px, px, "gestaltet" if styled else "eckig")
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
