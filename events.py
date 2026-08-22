"""Event-basiertes Foto-Routing.

Fotos werden automatisch nach Datum + Event-Name in Unterordnern abgelegt:
    Picture_Box/<YYYY-MM-DD>_<event-slug>/foto_<timestamp>.jpg

Das passiert komplett ohne Admin-Eingriff — Datums-Wechsel = neuer Ordner,
Event-Name (aus config) bleibt typischerweise konstant pro Vermietung.
"""

import json
import logging
import os
import re
import threading
import time
import unicodedata
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

_EXTS = {".jpg", ".jpeg", ".png"}

# Der aktive Event-Ordner wird festgenagelt, statt bei jedem Aufruf neu aus
# datetime.now() abgeleitet zu werden. Sonst wandert eine Feier von 20:00 bis
# 02:00 um Mitternacht still in einen zweiten Ordner: zwei Eintraege in der
# Galerie, der ZIP-Download zieht nur eine Haelfte, max_photos gilt doppelt.
# Die Datei liegt neben den Fotos, damit sie einen Reboot ueberlebt — ein
# Absturz mitten im Event soll den Ordner nicht wechseln.
_PIN_FILE = ".active_event.json"
_pin_lock = threading.RLock()


def _pin_path(cfg: dict) -> str:
    return os.path.join(cfg["picture_dir"], _PIN_FILE)


def _read_pin(cfg: dict) -> Optional[dict]:
    try:
        with open(_pin_path(cfg), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _write_pin(cfg: dict, folder: str, slug: str, started: float) -> None:
    path = _pin_path(cfg)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"folder": folder, "slug": slug, "started": started}, f)
        os.replace(tmp, path)
    except OSError as exc:
        # Nicht fatal: ohne Pin faellt current_event_folder auf das alte
        # Datums-Verhalten zurueck. Aber es gehoert ins Log.
        logger.warning("Aktives Event nicht gespeichert (%s): %s", path, exc)


def start_new_event(cfg: dict) -> str:
    """Beendet die laufende Session und nagelt einen frischen Ordner fest.

    Fuer den Fall, dass zwei Events am selben Tag mit gleichem Namen
    stattfinden oder der Gastgeber bewusst trennen will.
    """
    with _pin_lock:
        slug = slugify(cfg.get("event_name", "Fotobox"))
        now = time.time()
        folder = f"{datetime.fromtimestamp(now).strftime('%Y-%m-%d')}_{slug}"
        # Kollision am selben Tag: -2, -3, ... anhaengen statt in den
        # bestehenden Ordner zu schreiben.
        base, n = folder, 2
        while os.path.isdir(os.path.join(cfg["picture_dir"], folder)):
            folder = f"{base}-{n}"
            n += 1
        _write_pin(cfg, folder, slug, now)
        logger.info("Neues Event gestartet: %s", folder)
        return folder


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return (s or "fotobox")[:40]


def current_event_folder(cfg: dict, when: Optional[float] = None) -> str:
    """Ordnername des aktiven Events.

    Ohne `when` gilt der festgenagelte Ordner der laufenden Session, solange
    (a) der Event-Name unveraendert ist und (b) die Session juenger als
    `event_session_hours` ist. Damit bleibt eine Feier ueber Mitternacht in
    einem Ordner, waehrend am naechsten Tag automatisch ein neuer beginnt.

    Mit `when` wird ohne Pin gerechnet (historische Abfragen).
    """
    slug = slugify(cfg.get("event_name", "Fotobox"))
    if when is not None:
        return f"{datetime.fromtimestamp(when).strftime('%Y-%m-%d')}_{slug}"

    now = time.time()
    max_age = float(cfg.get("event_session_hours", 18)) * 3600
    with _pin_lock:
        pin = _read_pin(cfg)
        if pin is not None:
            started = pin.get("started")
            folder = pin.get("folder", "")
            # 0 <= age faengt eine rueckwaerts gestellte Uhr ab (Pi ohne RTC
            # korrigiert die Zeit per NTP oft erst Minuten nach dem Boot).
            if (pin.get("slug") == slug
                    and isinstance(started, (int, float))
                    and 0 <= now - started < max_age
                    and is_safe_event(folder)):
                return folder

        folder = f"{datetime.fromtimestamp(now).strftime('%Y-%m-%d')}_{slug}"
        _write_pin(cfg, folder, slug, now)
        return folder


def current_event_dir(cfg: dict) -> str:
    """Absolute path of the active event directory; created on demand."""
    path = os.path.join(cfg["picture_dir"], current_event_folder(cfg))
    os.makedirs(path, exist_ok=True)
    return path


def is_safe_event(event: str) -> bool:
    if not event:
        return False
    if "/" in event or os.sep in event or ".." in event or event.startswith("."):
        return False
    return True


def event_path(cfg: dict, event: str) -> Optional[str]:
    if not is_safe_event(event):
        return None
    path = os.path.join(cfg["picture_dir"], event)
    return path if os.path.isdir(path) else None


def list_events(cfg: dict) -> list[dict]:
    """Returns events sorted newest first, only those that contain photos.

    Jeder Eintrag enthält ein `cover` (Filename des neuesten Fotos im Ordner)
    für die Vorschau in der Ordner-Ansicht.
    """
    base = cfg["picture_dir"]
    if not os.path.isdir(base):
        return []
    active_folder = current_event_folder(cfg)
    out: list[dict] = []
    for entry in os.listdir(base):
        full = os.path.join(base, entry)
        if not os.path.isdir(full) or not is_safe_event(entry):
            continue
        try:
            files = [f for f in os.listdir(full)
                     if os.path.splitext(f)[1].lower() in _EXTS]
        except OSError:
            continue
        if not files:
            continue
        try:
            stamped = [(f, os.path.getmtime(os.path.join(full, f))) for f in files]
        except OSError:
            continue
        stamped.sort(key=lambda x: x[1], reverse=True)
        cover = stamped[0][0]
        mtime = stamped[0][1]
        date_part, _, slug_part = entry.partition("_")
        out.append({
            "folder":  entry,
            "date":    date_part,
            "slug":    slug_part,
            "display": _display_name(entry),
            "count":   len(files),
            "mtime":   mtime,
            "cover":   cover,
            "active":  entry == active_folder,
        })
    out.sort(key=lambda e: e["mtime"], reverse=True)
    return out


def _display_name(folder: str) -> str:
    """Human-readable label from folder name like '2026-04-30_lisa-und-tom'."""
    date_part, _, slug = folder.partition("_")
    if not slug:
        return date_part
    pretty = slug.replace("-", " ").strip()
    return f"{pretty[:1].upper()}{pretty[1:]}" if pretty else date_part


def migrate_flat_photos(cfg: dict) -> int:
    """Verschiebt flache .jpg-Dateien aus picture_dir/ in einen Datums-Archiv-Ordner.

    Ermöglicht Upgrade von alter Struktur (alle Fotos in einem Ordner) ohne
    Datenverlust. Wird beim Server-Start einmal ausgeführt."""
    base = cfg["picture_dir"]
    if not os.path.isdir(base):
        return 0
    flat = [f for f in os.listdir(base)
            if os.path.isfile(os.path.join(base, f))
            and os.path.splitext(f)[1].lower() in _EXTS]
    if not flat:
        return 0
    archive = os.path.join(base, f"{datetime.now().strftime('%Y-%m-%d')}_archiv")
    os.makedirs(archive, exist_ok=True)
    moved = 0
    for f in flat:
        try:
            os.rename(os.path.join(base, f), os.path.join(archive, f))
            moved += 1
        except OSError as exc:
            logger.warning("Migration %s: %s", f, exc)
    if moved:
        logger.info("Foto-Migration: %d Dateien → %s", moved, archive)
    return moved
