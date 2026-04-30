"""Event-basiertes Foto-Routing.

Fotos werden automatisch nach Datum + Event-Name in Unterordnern abgelegt:
    Picture_Box/<YYYY-MM-DD>_<event-slug>/foto_<timestamp>.jpg

Das passiert komplett ohne Admin-Eingriff — Datums-Wechsel = neuer Ordner,
Event-Name (aus config) bleibt typischerweise konstant pro Vermietung.
"""

import logging
import os
import re
import unicodedata
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

_EXTS = {".jpg", ".jpeg", ".png"}


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return (s or "fotobox")[:40]


def current_event_folder(cfg: dict, when: Optional[float] = None) -> str:
    """Folder name (relative) for the active event."""
    t = datetime.fromtimestamp(when) if when else datetime.now()
    return f"{t.strftime('%Y-%m-%d')}_{slugify(cfg.get('event_name', 'Fotobox'))}"


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
    """Returns events sorted newest first, only those that contain photos."""
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
            mtime = max(os.path.getmtime(os.path.join(full, f)) for f in files)
        except (OSError, ValueError):
            continue
        date_part, _, slug_part = entry.partition("_")
        out.append({
            "folder":  entry,
            "date":    date_part,
            "slug":    slug_part,
            "display": _display_name(entry),
            "count":   len(files),
            "mtime":   mtime,
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
