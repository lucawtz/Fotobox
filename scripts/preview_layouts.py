"""Rendert mehrere Layout-Varianten als PNG zur Vorschau (kein Pi nötig).

Aufruf:
    python scripts/preview_layouts.py
Ergebnis: scripts/preview_*.png
"""
import math
import os
import sys

import pygame

W, H = 1920, 1080
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _font(size: int, bold: bool = True) -> pygame.font.Font:
    # Versuche echte Fonts in dieser Reihenfolge; SysFont liefert
    # unter dummy-driver manchmal nur Boxen, deshalb explizite Pfade.
    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return pygame.font.Font(path, size)
    return pygame.font.Font(None, size)


def _gradient(surf: pygame.Surface, top: tuple, bottom: tuple):
    h = surf.get_height()
    w = surf.get_width()
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(top[0] * (1 - t) + bottom[0] * t)
        g = int(top[1] * (1 - t) + bottom[1] * t)
        b = int(top[2] * (1 - t) + bottom[2] * t)
        pygame.draw.line(surf, (r, g, b), (0, y), (w, y))


def _rounded_panel(surf: pygame.Surface, rect: pygame.Rect,
                   color: tuple, radius: int = 18, alpha: int = 220):
    panel = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    pygame.draw.rect(panel, (*color, alpha), panel.get_rect(),
                     border_radius=radius)
    surf.blit(panel, rect.topleft)


def _polaroid_placeholder(surf: pygame.Surface, cx: int, cy: int,
                          angle: float, w: int = 280, h: int = 290,
                          tint: tuple = (210, 210, 210)):
    pol = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(pol, (245, 240, 230), pol.get_rect(), border_radius=4)
    inner = pygame.Rect(18, 18, w - 36, h - 70)
    pygame.draw.rect(pol, tint, inner)
    pygame.draw.rect(pol, (40, 40, 40), inner, width=2)
    rotated = pygame.transform.rotate(pol, angle)
    # weicher Schatten
    shadow = pygame.Surface(rotated.get_size(), pygame.SRCALPHA)
    shadow.fill((0, 0, 0, 70))
    shadow_mask = pygame.mask.from_surface(rotated)
    shadow = shadow_mask.to_surface(setcolor=(0, 0, 0, 80),
                                    unsetcolor=(0, 0, 0, 0))
    surf.blit(shadow, shadow.get_rect(center=(cx + 6, cy + 8)))
    surf.blit(rotated, rotated.get_rect(center=(cx, cy)))


def _qr_placeholder(surf: pygame.Surface, x: int, y: int, size: int = 160):
    bg = pygame.Surface((size + 24, size + 24), pygame.SRCALPHA)
    pygame.draw.rect(bg, (255, 255, 255, 240), bg.get_rect(), border_radius=12)
    surf.blit(bg, (x - 12, y - 12))
    # Mock-QR
    cell = size // 16
    import random
    rng = random.Random(42)
    for i in range(16):
        for j in range(16):
            if (i < 3 and j < 3) or (i < 3 and j > 12) or (i > 12 and j < 3):
                continue
            if rng.random() > 0.5:
                pygame.draw.rect(
                    surf, (15, 15, 15),
                    (x + j * cell, y + i * cell, cell, cell))
    # Position-Marker
    for ix, iy in [(0, 0), (0, 13), (13, 0)]:
        pygame.draw.rect(surf, (15, 15, 15),
                         (x + ix * cell, y + iy * cell, cell * 3, cell * 3))
        pygame.draw.rect(surf, (255, 255, 255),
                         (x + ix * cell + cell // 2,
                          y + iy * cell + cell // 2,
                          cell * 2, cell * 2))
        pygame.draw.rect(surf, (15, 15, 15),
                         (x + ix * cell + cell,
                          y + iy * cell + cell,
                          cell, cell))


def _live_view_placeholder(surf: pygame.Surface, rect: pygame.Rect,
                           label: str = "Live-Vorschau"):
    inner = pygame.Surface((rect.width, rect.height))
    _gradient(inner, (35, 35, 45), (15, 15, 22))
    # Diagonale "Stripes" für TV-Optik
    for i in range(0, rect.width + rect.height, 24):
        pygame.draw.line(inner, (45, 45, 55),
                         (i, 0), (i - rect.height, rect.height), 1)
    surf.blit(inner, rect.topleft)
    # Rahmen
    pygame.draw.rect(surf, (220, 175, 110), rect, width=3, border_radius=12)
    f = _font(48)
    lbl = f.render(label, True, (200, 200, 210))
    surf.blit(lbl, lbl.get_rect(center=rect.center))
    f2 = _font(24, bold=False)
    sub = f2.render("(im Betrieb: Capture-Card-Stream)",
                    True, (150, 150, 160))
    surf.blit(sub, sub.get_rect(centerx=rect.centerx, top=rect.centery + 35))


def _button(surf: pygame.Surface, rect: pygame.Rect, label: str,
            key_hint: str, accent: tuple, highlighted: bool = False):
    if highlighted:
        glow = pygame.Surface((rect.width + 40, rect.height + 40),
                              pygame.SRCALPHA)
        for i in range(8, 0, -1):
            a = 18 + (8 - i) * 8
            pygame.draw.rect(glow, (*accent, a),
                             glow.get_rect().inflate(-i * 4, -i * 4),
                             width=4, border_radius=22)
        surf.blit(glow, (rect.x - 20, rect.y - 20))

    btn = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    base = (*accent, 230) if highlighted else (35, 25, 18, 235)
    pygame.draw.rect(btn, base, btn.get_rect(), border_radius=18)
    pygame.draw.rect(btn, (*accent, 255), btn.get_rect(),
                     width=3, border_radius=18)
    surf.blit(btn, rect.topleft)

    fl = _font(46)
    lbl = fl.render(label, True, (255, 255, 255) if highlighted else accent)
    surf.blit(lbl, lbl.get_rect(centerx=rect.centerx, centery=rect.centery - 8))
    fs = _font(22, bold=False)
    hint = fs.render(f"[ {key_hint} ]", True,
                     (255, 255, 255, 200) if highlighted else (170, 130, 80))
    surf.blit(hint, hint.get_rect(centerx=rect.centerx, centery=rect.centery + 26))


def _statusbar(surf: pygame.Surface):
    bar = pygame.Surface((W, 36), pygame.SRCALPHA)
    bar.fill((0, 0, 0, 180))
    surf.blit(bar, (0, H - 36))
    f = _font(20, bold=False)
    items = [
        ("Kamera: OK", (90, 210, 90)),
        ("Speicher: 28.4 GB", (160, 130, 80)),
        ("Fotos: 142", (160, 130, 80)),
        ("Hotspot: aktiv", (160, 130, 80)),
        ("Event: Hochzeit Müller", (212, 168, 106)),
    ]
    x = 24
    for text, color in items:
        lbl = f.render(text, True, color)
        surf.blit(lbl, (x, H - 28))
        x += lbl.get_width() + 50


# ─────────────────────────────────────────────────────────────────────────
# Variante 1: "Modern Dark" – dunkles, modernes App-Look mit Akzenten
# ─────────────────────────────────────────────────────────────────────────
def render_variant_modern_dark() -> pygame.Surface:
    surf = pygame.Surface((W, H))
    _gradient(surf, (28, 22, 32), (12, 10, 16))

    # ── Sidebar links ────────────────────────────────────────────────
    SIDE_W = 340
    sidebar = pygame.Surface((SIDE_W, H), pygame.SRCALPHA)
    _gradient(sidebar, (38, 28, 44), (22, 16, 28))
    surf.blit(sidebar, (0, 0))
    pygame.draw.line(surf, (212, 168, 106), (SIDE_W, 0), (SIDE_W, H), 2)

    # Logo-Box
    f_logo = _font(64)
    logo = f_logo.render("Fotobox", True, (212, 168, 106))
    surf.blit(logo, logo.get_rect(centerx=SIDE_W // 2, top=60))
    f_event = _font(28, bold=False)
    ev = f_event.render("Hochzeit Müller", True, (200, 195, 210))
    surf.blit(ev, ev.get_rect(centerx=SIDE_W // 2, top=130))

    # QR-Code in Sidebar
    qx = SIDE_W // 2 - 80
    qy = 220
    _qr_placeholder(surf, qx, qy, 160)
    fh = _font(24, bold=False)
    hint = fh.render("Galerie scannen", True, (200, 195, 210))
    surf.blit(hint, hint.get_rect(centerx=SIDE_W // 2, top=qy + 200))
    fh2 = _font(18, bold=False)
    sub = fh2.render("oder Phone mit", True, (150, 145, 160))
    surf.blit(sub, sub.get_rect(centerx=SIDE_W // 2, top=qy + 232))
    sub2 = fh2.render("WLAN „Fotobox\" verbinden", True, (150, 145, 160))
    surf.blit(sub2, sub2.get_rect(centerx=SIDE_W // 2, top=qy + 254))

    # Letzte Fotos (3 Polaroids als kleine Reihe in Sidebar unten)
    fp = _font(22, bold=False)
    lbl = fp.render("Letzte Fotos", True, (212, 168, 106))
    surf.blit(lbl, lbl.get_rect(centerx=SIDE_W // 2, top=580))
    for i, x in enumerate([60, 175]):
        _polaroid_placeholder(surf, x + 50, 720, (-4, 3)[i],
                              w=120, h=130, tint=(180, 170, 200))
    # Drittes Polaroid
    _polaroid_placeholder(surf, SIDE_W // 2, 870, -2,
                          w=140, h=150, tint=(190, 175, 210))

    # ── Hauptbereich ─────────────────────────────────────────────────
    # Live-View groß in der Mitte
    live_rect = pygame.Rect(SIDE_W + 60, 110, 1100, 620)
    _live_view_placeholder(surf, live_rect)

    # Titelbalken über Live-View
    f_title = _font(38)
    title = f_title.render("Stell dich in Position", True, (212, 168, 106))
    surf.blit(title, title.get_rect(centerx=live_rect.centerx, bottom=live_rect.top - 20))

    # Hinweis unter Live
    fh3 = _font(22, bold=False)
    hint2 = fh3.render(
        "Kamera-Display zeigt was du hier siehst — Knopf drücken zum Auslösen",
        True, (170, 165, 180))
    surf.blit(hint2, hint2.get_rect(centerx=live_rect.centerx, top=live_rect.bottom + 16))

    # ── Buttons rechts ───────────────────────────────────────────────
    btn_x = 1230
    btn_w = 600
    _button(surf, pygame.Rect(btn_x, 180, btn_w, 130),
            "Einzelfoto", "Trigger / Space", (212, 168, 106),
            highlighted=True)
    _button(surf, pygame.Rect(btn_x, 340, btn_w, 130),
            "Collage 2×2", "Rechts / E", (180, 130, 200))
    _button(surf, pygame.Rect(btn_x, 500, btn_w, 130),
            "Galerie", "Links / Q", (130, 180, 220))

    # Info-Box rechts unten
    info_rect = pygame.Rect(btn_x, 670, btn_w, 280)
    _rounded_panel(surf, info_rect, (45, 35, 28), radius=18, alpha=200)
    pygame.draw.rect(surf, (212, 168, 106), info_rect, width=2, border_radius=18)
    fi = _font(28)
    fl = fi.render("So geht's:", True, (212, 168, 106))
    surf.blit(fl, (info_rect.x + 24, info_rect.y + 18))
    fl2 = _font(22, bold=False)
    lines = [
        "1. Auf einen der Knöpfe drücken",
        "2. Countdown abwarten (3 Sek.)",
        "3. Foto bewundern und teilen",
        "",
        "Über QR-Code rechts kommst du zur",
        "Galerie aller Fotos.",
    ]
    for i, line in enumerate(lines):
        ll = fl2.render(line, True, (220, 215, 200))
        surf.blit(ll, (info_rect.x + 24, info_rect.y + 60 + i * 32))

    _statusbar(surf)
    return surf


# ─────────────────────────────────────────────────────────────────────────
# Variante 2: "Polaroid Wall" – an aktuelles Overlay angelehnt, aber clean
# ─────────────────────────────────────────────────────────────────────────
def render_variant_polaroid_wall() -> pygame.Surface:
    surf = pygame.Surface((W, H))
    # Hintergrund: warmes Beige/Cream mit subtiler Vignette
    _gradient(surf, (245, 235, 218), (228, 213, 188))
    # Vignette
    vign = pygame.Surface((W, H), pygame.SRCALPHA)
    for r in range(0, 600, 20):
        a = max(0, 60 - r // 12)
        pygame.draw.rect(vign, (60, 40, 20, a),
                         (r, r, W - 2 * r, H - 2 * r), width=20)
    surf.blit(vign, (0, 0))

    # ── Sidebar links (warm-dunkel) ──────────────────────────────────
    SIDE_W = 320
    sidebar = pygame.Surface((SIDE_W, H), pygame.SRCALPHA)
    _gradient(sidebar, (62, 42, 28), (38, 24, 14))
    surf.blit(sidebar, (0, 0))

    # Logo-Box
    logo_bg = pygame.Surface((220, 220), pygame.SRCALPHA)
    pygame.draw.circle(logo_bg, (255, 250, 240), (110, 110), 105)
    pygame.draw.circle(logo_bg, (212, 168, 106), (110, 110), 105, width=4)
    surf.blit(logo_bg, (50, 60))
    f = _font(72)
    init = f.render("FB", True, (180, 100, 60))
    surf.blit(init, init.get_rect(center=(160, 170)))

    # Event-Name
    f_ev = _font(34)
    ev = f_ev.render("Hochzeit Müller", True, (245, 220, 180))
    surf.blit(ev, ev.get_rect(centerx=SIDE_W // 2, top=305))
    f_dt = _font(22, bold=False)
    dt = f_dt.render("30. April 2026", True, (200, 170, 130))
    surf.blit(dt, dt.get_rect(centerx=SIDE_W // 2, top=350))

    # QR-Code
    qx = SIDE_W // 2 - 80
    qy = 420
    _qr_placeholder(surf, qx, qy, 160)
    fh = _font(22, bold=False)
    hint = fh.render("Fotos auf's Handy", True, (245, 220, 180))
    surf.blit(hint, hint.get_rect(centerx=SIDE_W // 2, top=qy + 195))

    # WLAN-Info
    wifi_box = pygame.Rect(30, 720, SIDE_W - 60, 180)
    _rounded_panel(surf, wifi_box, (28, 18, 10), radius=14, alpha=200)
    pygame.draw.rect(surf, (212, 168, 106), wifi_box,
                     width=2, border_radius=14)
    fw1 = _font(22)
    surf.blit(fw1.render("WLAN", True, (212, 168, 106)),
              (wifi_box.x + 16, wifi_box.y + 14))
    fw2 = _font(28)
    surf.blit(fw2.render("Fotobox", True, (255, 245, 230)),
              (wifi_box.x + 16, wifi_box.y + 50))
    surf.blit(fw1.render("Passwort", True, (212, 168, 106)),
              (wifi_box.x + 16, wifi_box.y + 96))
    surf.blit(fw2.render("fotobox123", True, (255, 245, 230)),
              (wifi_box.x + 16, wifi_box.y + 130))

    # ── Polaroid-Reihe oben ──────────────────────────────────────────
    polaroid_y = 240
    for i, (cx, angle, tint) in enumerate([
        (640, -6, (200, 180, 160)),
        (1100, 4, (170, 190, 200)),
        (1560, 10, (210, 170, 180)),
    ]):
        _polaroid_placeholder(surf, cx, polaroid_y, angle,
                              w=320, h=320, tint=tint)
    # "Pin"-Optik
    for cx in [640, 1100, 1560]:
        pygame.draw.circle(surf, (180, 30, 30), (cx, 90), 10)
        pygame.draw.circle(surf, (255, 200, 200), (cx - 3, 87), 3)

    # ── Live-View mittig unten ──────────────────────────────────────
    live_rect = pygame.Rect(SIDE_W + 80, 480, 950, 470)
    # Holzrahmen-Look
    frame = pygame.Rect(live_rect.x - 22, live_rect.y - 22,
                        live_rect.width + 44, live_rect.height + 44)
    _rounded_panel(surf, frame, (90, 60, 38), radius=16, alpha=255)
    pygame.draw.rect(surf, (130, 90, 55), frame, width=3, border_radius=16)
    _live_view_placeholder(surf, live_rect)

    # ── Buttons rechts ──────────────────────────────────────────────
    btn_x = 1500
    _button(surf, pygame.Rect(btn_x, 500, 380, 110),
            "Foto", "▶", (212, 168, 106), highlighted=True)
    _button(surf, pygame.Rect(btn_x, 640, 380, 110),
            "Collage", "▶", (180, 130, 200))
    _button(surf, pygame.Rect(btn_x, 780, 380, 110),
            "Galerie", "◀", (130, 180, 220))

    _statusbar(surf)
    return surf


# ─────────────────────────────────────────────────────────────────────────
# Variante 3: "Minimal/Studio" – sehr clean, fokus auf Live + Buttons
# ─────────────────────────────────────────────────────────────────────────
def render_variant_minimal() -> pygame.Surface:
    surf = pygame.Surface((W, H))
    surf.fill((18, 18, 22))

    # Top-Bar mit Event + Logo
    top = pygame.Surface((W, 90), pygame.SRCALPHA)
    top.fill((28, 28, 34, 240))
    surf.blit(top, (0, 0))
    pygame.draw.line(surf, (212, 168, 106), (0, 90), (W, 90), 2)

    f_logo = _font(40)
    surf.blit(f_logo.render("◉ Fotobox", True, (212, 168, 106)), (40, 24))
    f_ev = _font(32, bold=False)
    ev = f_ev.render("Hochzeit Müller  ·  30. April 2026", True, (220, 215, 220))
    surf.blit(ev, ev.get_rect(center=(W // 2, 45)))
    f_st = _font(22, bold=False)
    st = f_st.render("142 Fotos  ·  WLAN: Fotobox", True, (160, 155, 165))
    surf.blit(st, st.get_rect(right=W - 40, centery=45))

    # Live-View riesig in der Mitte
    live_rect = pygame.Rect(120, 140, 1300, 720)
    _live_view_placeholder(surf, live_rect)

    # QR-Code rechts neben Live-View
    qr_panel = pygame.Rect(1480, 140, 320, 380)
    _rounded_panel(surf, qr_panel, (30, 30, 38), radius=18, alpha=255)
    pygame.draw.rect(surf, (212, 168, 106), qr_panel, width=2, border_radius=18)
    f_qr = _font(26)
    lbl = f_qr.render("Galerie scannen", True, (212, 168, 106))
    surf.blit(lbl, lbl.get_rect(centerx=qr_panel.centerx, top=qr_panel.y + 24))
    _qr_placeholder(surf, qr_panel.centerx - 130, qr_panel.y + 80, 260)

    # Buttons rechts unten – groß
    _button(surf, pygame.Rect(1480, 545, 380, 130),
            "Foto", "Trigger", (212, 168, 106), highlighted=True)
    _button(surf, pygame.Rect(1480, 705, 380, 130),
            "Collage", "Rechts", (180, 130, 200))

    # Hinweisbar unten
    hint_bar = pygame.Rect(120, 900, 1300, 110)
    _rounded_panel(surf, hint_bar, (30, 30, 38), radius=18, alpha=255)
    pygame.draw.rect(surf, (212, 168, 106), hint_bar, width=2, border_radius=18)
    f_h = _font(28)
    surf.blit(f_h.render("→ Drück „Trigger\" zum Foto schießen", True,
                          (245, 235, 220)),
              (hint_bar.x + 24, hint_bar.y + 16))
    f_h2 = _font(22, bold=False)
    surf.blit(f_h2.render(
        "Mit „Rechts\" startest du eine 4-Foto-Collage. „Links\" zeigt die Galerie.",
        True, (160, 155, 165)),
              (hint_bar.x + 24, hint_bar.y + 60))

    _statusbar(surf)
    return surf


# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────
def main():
    # Headless – wir brauchen kein Display
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((1, 1))

    variants = [
        ("preview_1_modern_dark.png",   render_variant_modern_dark),
        ("preview_2_polaroid_wall.png", render_variant_polaroid_wall),
        ("preview_3_minimal.png",       render_variant_minimal),
    ]
    for fname, fn in variants:
        out = os.path.join(HERE, fname)
        surf = fn()
        pygame.image.save(surf, out)
        print(f"  -> {os.path.relpath(out, ROOT)}")

    pygame.quit()


if __name__ == "__main__":
    main()
