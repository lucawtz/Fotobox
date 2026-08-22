"""Druck-Anbindung über CUPS.

Ersetzt das frühere `subprocess.Popen(["lp", path])` in main.py, das weder ein
Zielgerät noch ein Papierformat kannte, keine Rückmeldung gab und pro Druck
einen Zombie-Prozess hinterließ.

Aufbau:
  * `status()`   – gecachter Druckerzustand für die UI (30 Hz-Renderschleife
                   darf nicht bei jedem Frame `lpstat` forken).
  * `prepare()`  – rechnet das Foto auf das Papierformat, damit der Selphy
                   nicht willkürlich beschneidet oder weiße Ränder lässt.
  * `print_photo()` – schickt den Job ab und meldet Erfolg/Fehler zurück.

Zielgerät ist ein Canon Selphy (Thermosublimation, 10×15 bzw. Postkarte
100×148 mm), das Modul ist aber druckerunabhängig: Name, Medium und rohe
lp-Optionen kommen aus der Config.
"""

import logging
import os
import re
import subprocess
import tempfile
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Wie lange ein ermittelter Druckerzustand als frisch gilt. Die UI fragt in
# der Renderschleife an; ohne Cache wären das ~30 lpstat-Forks pro Sekunde.
_STATUS_TTL_S = 20.0

_lock = threading.Lock()
_status: dict = {"available": False, "printer": None, "message": "noch nicht geprüft",
                 "checked": 0.0}


# ── CUPS-Abfragen ──────────────────────────────────────────────────────────────

def _run(args: list, timeout: float = 8.0) -> Optional[subprocess.CompletedProcess]:
    """Führt ein CUPS-Kommando aus. None = Binary fehlt oder Timeout.

    Bewusst `run` statt `Popen`: der alte Code sammelte die Kindprozesse nie
    ein, jeder Druck hinterließ einen Zombie für die Lebensdauer der Box.
    """
    try:
        return subprocess.run(args, capture_output=True, text=True,
                              timeout=timeout, check=False)
    except FileNotFoundError:
        logger.warning("CUPS-Kommando nicht gefunden: %s", args[0])
        return None
    except subprocess.TimeoutExpired:
        logger.warning("CUPS-Kommando '%s' nach %ss abgebrochen", args[0], timeout)
        return None
    except OSError as exc:
        logger.warning("CUPS-Kommando '%s': %s", args[0], exc)
        return None


def list_printers() -> list[dict]:
    """Alle CUPS-Drucker mit Zustand. Leere Liste = keiner eingerichtet."""
    proc = _run(["lpstat", "-p"])
    if proc is None or proc.returncode != 0:
        return []
    out = []
    for line in proc.stdout.splitlines():
        # "printer Selphy is idle.  enabled since ..." / "... is disabled since"
        m = re.match(r"printer\s+(\S+)\s+is\s+(\S+?)\.?\s", line + " ")
        if not m:
            continue
        name, state = m.group(1), m.group(2).lower()
        out.append({
            "name":  name,
            "state": state,                      # idle | printing | disabled
            "ready": state in ("idle", "printing"),
            "line":  line.strip(),
        })
    return out


def default_printer() -> Optional[str]:
    proc = _run(["lpstat", "-d"])
    if proc is None or proc.returncode != 0:
        return None
    # "system default destination: Selphy"  /  "no system default destination"
    m = re.search(r"destination:\s*(\S+)", proc.stdout)
    return m.group(1) if m else None


def resolve_printer(cfg: dict) -> Optional[str]:
    """Welcher Drucker soll es sein: Config, sonst CUPS-Default, sonst der erste."""
    wanted = (cfg.get("printer_name") or "").strip()
    printers = list_printers()
    names = [p["name"] for p in printers]
    if wanted:
        return wanted if wanted in names else None
    dflt = default_printer()
    if dflt and dflt in names:
        return dflt
    return names[0] if names else None


def refresh_status(cfg: dict) -> dict:
    """Fragt CUPS wirklich ab und aktualisiert den Cache."""
    with _lock:
        if not cfg.get("print_enabled", True):
            _status.update(available=False, printer=None,
                           message="Drucken in der Config deaktiviert",
                           checked=time.monotonic())
            return dict(_status)

        printers = list_printers()
        if not printers:
            _status.update(available=False, printer=None,
                           message="Kein Drucker in CUPS eingerichtet",
                           checked=time.monotonic())
            return dict(_status)

        name = resolve_printer(cfg)
        if name is None:
            wanted = cfg.get("printer_name")
            _status.update(
                available=False, printer=None,
                message=f"Drucker '{wanted}' nicht gefunden",
                checked=time.monotonic())
            return dict(_status)

        entry = next((p for p in printers if p["name"] == name), None)
        ready = bool(entry and entry["ready"])
        _status.update(
            available=ready, printer=name,
            message="bereit" if ready else f"Drucker '{name}' ist deaktiviert",
            checked=time.monotonic())
        return dict(_status)


def status(cfg: dict) -> dict:
    """Gecachter Zustand — für die UI-Renderschleife gedacht."""
    if time.monotonic() - _status.get("checked", 0.0) > _STATUS_TTL_S:
        return refresh_status(cfg)
    with _lock:
        return dict(_status)


def available(cfg: dict) -> bool:
    return bool(status(cfg).get("available"))


# ── Bildaufbereitung ───────────────────────────────────────────────────────────

def _paper_aspect(cfg: dict) -> float:
    """Seitenverhältnis des Papiers (Breite/Höhe) im Querformat."""
    size = cfg.get("print_size_mm") or [148, 100]
    try:
        w, h = float(size[0]), float(size[1])
        if w <= 0 or h <= 0:
            raise ValueError
    except (TypeError, ValueError, IndexError):
        w, h = 148.0, 100.0
    return max(w, h) / min(w, h)


def prepare(path: str, cfg: dict) -> str:
    """Rechnet das Foto auf das Papierformat und gibt eine temporäre Datei zurück.

    Zwei Modi, automatisch gewählt:
      * `cover` — Bild füllt das Papier, minimal beschnitten. Für Einzelfotos:
        ein 3:2-DSLR-Bild auf 148×100 mm verliert gut 1 %, sieht randlos aus.
      * `fit`   — Bild komplett sichtbar, weißer Rand. Für die 2×2-Collage
        Pflicht: ein quadratisches Bild mit `cover` auf Postkarte würde die
        obere und untere Fotoreihe abschneiden.

    Bei Problemen wird der Originalpfad zurückgegeben — lieber ein unschön
    skalierter Druck als gar keiner.
    """
    try:
        from PIL import Image, ImageOps
    except ImportError:
        logger.warning("Pillow fehlt — drucke Originaldatei")
        return path

    mode = (cfg.get("print_mode") or "auto").lower()
    target = _paper_aspect(cfg)
    dpi = int(cfg.get("print_dpi", 300) or 300)
    size_mm = cfg.get("print_size_mm") or [148, 100]
    long_mm, short_mm = max(size_mm), min(size_mm)

    try:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGB")
            # Hochformat-Aufnahmen aufs Querformat-Papier drehen, statt sie
            # winzig in die Mitte zu setzen.
            if img.height > img.width:
                img = img.rotate(90, expand=True)

            src = img.width / img.height
            if mode == "auto":
                # Innerhalb von 10 % ist der Beschnitt nicht wahrnehmbar →
                # randlos. Alles andere (Collage!) komplett zeigen.
                use_cover = abs(src - target) / target <= 0.10
            else:
                use_cover = mode == "cover"

            out_w = int(round(long_mm / 25.4 * dpi))
            out_h = int(round(short_mm / 25.4 * dpi))

            if use_cover:
                canvas = ImageOps.fit(img, (out_w, out_h),
                                      method=Image.LANCZOS, centering=(0.5, 0.5))
            else:
                canvas = Image.new("RGB", (out_w, out_h), (255, 255, 255))
                inner = ImageOps.contain(img, (out_w, out_h), method=Image.LANCZOS)
                canvas.paste(inner, ((out_w - inner.width) // 2,
                                     (out_h - inner.height) // 2))

            fd, tmp = tempfile.mkstemp(prefix="fotobox-print-", suffix=".jpg")
            os.close(fd)
            canvas.save(tmp, "JPEG", quality=95, dpi=(dpi, dpi))
            logger.info("Druckbild: %s → %dx%d px (%s)",
                        os.path.basename(path), out_w, out_h,
                        "randlos" if use_cover else "mit Rand")
            return tmp
    except Exception as exc:
        logger.warning("Druckbild-Aufbereitung fehlgeschlagen (%s) — nutze Original", exc)
        return path


# ── Druckauftrag ───────────────────────────────────────────────────────────────

def _lp_args(printer: str, cfg: dict, path: str) -> list:
    args = ["lp", "-d", printer]
    copies = int(cfg.get("print_copies", 1) or 1)
    if copies > 1:
        args += ["-n", str(max(1, min(9, copies)))]
    media = (cfg.get("print_media") or "").strip()
    if media:
        args += ["-o", f"media={media}"]
    # Rohe lp-Optionen aus der Config: welche der Selphy-Treiber genau will,
    # steht erst nach `lpoptions -p <drucker> -l` fest (siehe README).
    for opt in cfg.get("print_options") or []:
        if isinstance(opt, str) and opt.strip():
            args += ["-o", opt.strip()]
    return args + [path]


def print_photo(path: str, cfg: dict) -> tuple[bool, str]:
    """Schickt ein Foto zum Drucker. Rückgabe: (erfolgreich, Meldung für den Gast).

    Blockiert nur so lange, bis CUPS den Job angenommen hat (Sekundenbruchteile) —
    nicht bis das Bild gedruckt ist. Der Selphy braucht danach knapp eine Minute.
    """
    if not os.path.isfile(path):
        return False, "Foto nicht gefunden"

    st = refresh_status(cfg)          # bewusst frisch: Papier kann leer sein
    if not st["available"]:
        return False, st["message"]

    printer = st["printer"]
    prepared = prepare(path, cfg)
    try:
        proc = _run(_lp_args(printer, cfg, prepared), timeout=20.0)
        if proc is None:
            return False, "Drucksystem antwortet nicht"
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip().splitlines()
            detail = err[-1] if err else f"lp beendete sich mit Code {proc.returncode}"
            logger.error("Druckauftrag abgelehnt: %s", detail)
            return False, detail[:80]
        job = (proc.stdout or "").strip()
        logger.info("Druckauftrag angenommen (%s): %s", printer, job)
        return True, "Foto wird gedruckt"
    finally:
        # Temporäre Datei nur löschen wenn wir sie selbst angelegt haben.
        if prepared != path:
            try:
                os.remove(prepared)
            except OSError:
                pass
