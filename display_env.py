"""Display-Stack erkennen und SDL passend vorbereiten.

Hintergrund: `fotobox.service` setzte fest `DISPLAY=:0`. Raspberry Pi OS
Bookworm startet auf Pi 4/5 je nach Version aber einen Wayland-Compositor
(wayfire bzw. labwc). Ob dort ein nutzbares XWayland mit DISPLAY=:0
mitläuft, hängt von der Installation ab — läuft keins, findet SDL keinen
Bildschirm und die Box bleibt schwarz. Das fällt erst beim Aufbau auf,
also genau dann, wenn keine Zeit mehr ist.

Statt auf einen Stack zu wetten, wird hier zur Laufzeit geprüft, was
tatsächlich da ist, und eine Reihenfolge von SDL-Videotreibern
vorgeschlagen. `ui.py` probiert sie der Reihe nach durch.

Die Erkennung ist bewusst als reine Funktion gebaut (`detect`), damit sie
sich ohne Pi testen lässt: alle Zugriffe auf Umgebung und Dateisystem
kommen über Parameter herein.
"""

import logging
import os
import sys
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def detect(environ: dict,
           uid: int,
           exists: Callable[[str], bool],
           listdir: Callable[[str], list],
           platform: str = "linux") -> dict:
    """Ermittelt Umgebungsergänzungen und Treiber-Reihenfolge.

    Rückgabe:
        {"env": {...}, "drivers": [...], "session": "wayland"|"x11"|…}

    `env` enthält nur, was ergänzt werden muss — bereits gesetzte Werte
    werden nie überschrieben.

    `platform` ist ein `sys.platform`-String. Default "linux", weil das Pi
    der Normalfall ist; `prepare()` reicht den echten Wert durch.
    """
    # Ein explizit gesetzter Treiber gewinnt immer. Darauf verlassen sich
    # scripts/preview_layouts.py und die Tests (SDL_VIDEODRIVER=dummy).
    forced = (environ.get("SDL_VIDEODRIVER") or "").strip()
    if forced:
        return {"env": {}, "drivers": [forced], "session": "erzwungen"}

    # ── Entwicklungsmaschine ───────────────────────────────────────────────
    # Das Pi ist der Normalfall, aber main.py läuft auch auf dem Entwickler-
    # rechner (--dev-camera). Dort gibt es weder Wayland noch X11: SDL hat
    # genau einen nativen Treiber. Ohne diesen Zweig fällt die Erkennung
    # unten auf 'x11' durch und der Start scheitert an "x11 not available".
    if platform == "darwin":
        return {"env": {}, "drivers": ["cocoa"], "session": "macos"}
    if platform.startswith("win"):
        return {"env": {}, "drivers": ["windows"], "session": "windows"}

    env: dict = {}
    runtime_dir = environ.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}"

    # ── Wayland? ───────────────────────────────────────────────────────────
    wayland_display = environ.get("WAYLAND_DISPLAY")
    if not wayland_display and exists(runtime_dir):
        try:
            # Sockets heissen wayland-0, wayland-1, ... Die .lock-Dateien
            # daneben sind keine Sockets und muessen raus.
            candidates = sorted(n for n in listdir(runtime_dir)
                                if n.startswith("wayland-")
                                and not n.endswith(".lock"))
        except OSError as exc:
            logger.debug("XDG_RUNTIME_DIR '%s' nicht lesbar: %s", runtime_dir, exc)
            candidates = []
        if candidates:
            wayland_display = candidates[0]
            env["WAYLAND_DISPLAY"] = wayland_display

    if wayland_display:
        if not environ.get("XDG_RUNTIME_DIR"):
            env["XDG_RUNTIME_DIR"] = runtime_dir
        # x11 bleibt als Rueckfalloption drin: auf den meisten Bookworm-
        # Installationen laeuft XWayland mit, und ein pygame ohne
        # Wayland-Support (aeltere SDL-Builds) kommt darueber trotzdem hoch.
        drivers = ["wayland", "x11"]
        session = "wayland"
    else:
        drivers = ["x11"]
        session = "x11" if environ.get("DISPLAY") else "unbekannt"

    # ── X11 ────────────────────────────────────────────────────────────────
    if "x11" in drivers and not environ.get("DISPLAY"):
        # Ohne DISPLAY kann der x11-Treiber nichts anfangen. :0 ist die
        # Standard-Session eines Desktop-Autologins.
        if exists("/tmp/.X11-unix/X0"):
            env["DISPLAY"] = ":0"

    return {"env": env, "drivers": drivers, "session": session}


def prepare(environ: Optional[dict] = None) -> list:
    """Wendet die Erkennung auf os.environ an und liefert die Treiberliste."""
    target = os.environ if environ is None else environ
    result = detect(
        environ=target,
        uid=os.getuid() if hasattr(os, "getuid") else 0,
        exists=os.path.exists,
        listdir=os.listdir,
        platform=sys.platform,
    )
    for key, value in result["env"].items():
        target[key] = value
        logger.info("Display: %s=%s ergänzt", key, value)
    logger.info("Display: Session sieht nach '%s' aus, Treiber-Reihenfolge %s",
                result["session"], result["drivers"])
    return result["drivers"]
