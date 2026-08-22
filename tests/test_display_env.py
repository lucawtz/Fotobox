"""Display-Stack-Erkennung (P1-5).

Der Pi kann X11 oder Wayland fahren; `fotobox.service` setzte fest
DISPLAY=:0. Ob das reicht, sieht man erst beim Aufbau — deshalb sind hier
die Pi-Szenarien nachgebaut, statt auf den Hardware-Test zu warten.

Alle Zugriffe auf Umgebung und Dateisystem gehen über Parameter, die
Erkennung ist damit ohne Pi vollständig prüfbar.
"""
import pytest

from display_env import detect


def fs(*paths):
    """Fake-Dateisystem: exists() und listdir() über eine Pfadliste."""
    tree = set(paths)

    def exists(p):
        return p in tree or any(x.startswith(p.rstrip("/") + "/") for x in tree)

    def listdir(p):
        prefix = p.rstrip("/") + "/"
        out = {x[len(prefix):].split("/")[0] for x in tree if x.startswith(prefix)}
        if not out and p not in tree:
            raise FileNotFoundError(p)
        return sorted(out)

    return exists, listdir


def run(environ, *paths, uid=1000):
    exists, listdir = fs(*paths)
    return detect(environ=dict(environ), uid=uid, exists=exists, listdir=listdir)


# ── Wayland (Bookworm auf Pi 4/5) ──────────────────────────────────────────────

def test_wayland_socket_is_found_without_env():
    """labwc/wayfire laufen, aber die Unit reicht WAYLAND_DISPLAY nicht durch."""
    r = run({"DISPLAY": ":0"}, "/run/user/1000/wayland-0", "/run/user/1000/wayland-0.lock")
    assert r["session"] == "wayland"
    assert r["env"]["WAYLAND_DISPLAY"] == "wayland-0"
    assert r["env"]["XDG_RUNTIME_DIR"] == "/run/user/1000"
    assert r["drivers"] == ["wayland", "x11"]


def test_lock_file_is_not_mistaken_for_a_socket():
    r = run({}, "/run/user/1000/wayland-1.lock", "/run/user/1000/wayland-1")
    assert r["env"]["WAYLAND_DISPLAY"] == "wayland-1"


def test_only_lock_file_means_no_wayland():
    r = run({"DISPLAY": ":0"}, "/run/user/1000/wayland-0.lock")
    assert r["session"] == "x11"
    assert r["drivers"] == ["x11"]


def test_existing_wayland_display_is_respected():
    r = run({"WAYLAND_DISPLAY": "wayland-3", "XDG_RUNTIME_DIR": "/run/user/1000"})
    assert r["session"] == "wayland"
    assert "WAYLAND_DISPLAY" not in r["env"], "vorhandener Wert wurde ueberschrieben"
    assert "XDG_RUNTIME_DIR" not in r["env"]


def test_x11_stays_as_fallback_under_wayland():
    """Aeltere SDL-Builds ohne Wayland-Support kommen ueber XWayland hoch."""
    r = run({}, "/run/user/1000/wayland-0")
    assert r["drivers"] == ["wayland", "x11"]


def test_custom_runtime_dir_is_used():
    r = run({"XDG_RUNTIME_DIR": "/run/user/1001"}, "/run/user/1001/wayland-0", uid=1001)
    assert r["env"]["WAYLAND_DISPLAY"] == "wayland-0"


# ── X11 ────────────────────────────────────────────────────────────────────────

def test_plain_x11_session():
    r = run({"DISPLAY": ":0"}, "/tmp/.X11-unix/X0")
    assert r["session"] == "x11"
    assert r["drivers"] == ["x11"]
    assert r["env"] == {}


def test_display_is_added_when_x_socket_exists():
    """Die Unit koennte DISPLAY vergessen — der Socket verraet die Session."""
    r = run({}, "/tmp/.X11-unix/X0")
    assert r["env"]["DISPLAY"] == ":0"
    assert r["drivers"] == ["x11"]


def test_nothing_running_still_returns_a_candidate():
    """Kein Display gefunden: trotzdem x11 versuchen und den echten
    SDL-Fehler ins Log bringen, statt vorher aufzugeben."""
    r = run({})
    assert r["session"] == "unbekannt"
    assert r["drivers"] == ["x11"]


# ── Explizite Vorgabe ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("forced", ["dummy", "x11", "wayland", "kmsdrm"])
def test_forced_driver_wins(forced):
    """scripts/preview_layouts.py und die Tests setzen SDL_VIDEODRIVER=dummy."""
    r = run({"SDL_VIDEODRIVER": forced, "DISPLAY": ":0"}, "/run/user/1000/wayland-0")
    assert r["drivers"] == [forced]
    assert r["env"] == {}
    assert r["session"] == "erzwungen"


def test_empty_forced_driver_is_ignored():
    r = run({"SDL_VIDEODRIVER": "  ", "DISPLAY": ":0"}, "/tmp/.X11-unix/X0")
    assert r["drivers"] == ["x11"]


# ── Robustheit ─────────────────────────────────────────────────────────────────

def test_unreadable_runtime_dir_does_not_raise():
    def exists(p):
        return p == "/run/user/1000"

    def listdir(p):
        raise PermissionError(p)

    r = detect(environ={"DISPLAY": ":0"}, uid=1000, exists=exists, listdir=listdir)
    assert r["drivers"] == ["x11"]


# ── Entwicklerrechner ──────────────────────────────────────────────────────────
#
# main.py laeuft auch ausserhalb des Pi (--dev-camera). Ohne Plattform-Zweig
# faellt die Erkennung dort auf x11 durch und pygame scheitert mit
# "x11 not available" — die UI startet gar nicht erst.

def test_macos_uses_the_native_driver():
    exists, listdir = fs()
    r = detect(environ={}, uid=501, exists=exists, listdir=listdir,
               platform="darwin")
    assert r["drivers"] == ["cocoa"]
    assert r["session"] == "macos"


def test_windows_uses_the_native_driver():
    exists, listdir = fs()
    r = detect(environ={}, uid=0, exists=exists, listdir=listdir,
               platform="win32")
    assert r["drivers"] == ["windows"]


def test_forced_driver_still_wins_on_macos():
    """Sonst wuerde die eigene Testsuite (SDL_VIDEODRIVER=dummy) auf einem
    Mac gegen cocoa laufen und ein Fenster aufreissen."""
    exists, listdir = fs()
    r = detect(environ={"SDL_VIDEODRIVER": "dummy"}, uid=501,
               exists=exists, listdir=listdir, platform="darwin")
    assert r["drivers"] == ["dummy"]


def test_linux_is_unaffected_by_the_platform_switch():
    exists, listdir = fs("/run/user/1000/wayland-0")
    r = detect(environ={}, uid=1000, exists=exists, listdir=listdir,
               platform="linux")
    assert r["drivers"] == ["wayland", "x11"]


# ── Aufloesung ─────────────────────────────────────────────────────────────────
#
# Kann der Schirm 1920x1080 nicht exakt, nimmt SDL bei FULLSCREEN den
# naechstbesten Modus und liefert eine Surface dieser Groesse. Das Layout
# haengt aber an W/H — ohne SCALED sitzt alles unten Verankerte daneben.

@pytest.fixture
def display_modes(monkeypatch):
    import pygame

    def set_modes(modes):
        monkeypatch.setattr(pygame.display, "list_modes", lambda *a, **k: modes)

    return set_modes


def test_native_resolution_needs_no_scaling(display_modes):
    import pygame
    from ui import UI, W, H

    display_modes([(2560, 1440), (W, H), (1280, 720)])
    assert UI._scaling_flag() == 0


def test_missing_resolution_switches_to_scaled(display_modes):
    import pygame
    from ui import UI

    display_modes([(2560, 1600), (1920, 1200)])   # MacBook: kein 1920x1080
    assert UI._scaling_flag() == pygame.SCALED


def test_any_resolution_needs_no_scaling(display_modes):
    """list_modes() liefert -1, wenn dem Treiber jede Groesse recht ist."""
    from ui import UI

    display_modes(-1)
    assert UI._scaling_flag() == 0
