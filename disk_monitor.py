import logging
import os
import shutil
import time

logger = logging.getLogger(__name__)

_EXTS = {".jpg", ".jpeg", ".png"}


def get_free_mb(path: str) -> int:
    try:
        return int(shutil.disk_usage(path).free / 1024 / 1024)
    except Exception:
        return 0


def cleanup_old_thumbnails(thumb_dir: str, max_age_days: int = 30):
    """Entfernt alte Thumbnails — sucht rekursiv durch Event-Subordner."""
    if not os.path.isdir(thumb_dir):
        return
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for root, _dirs, files in os.walk(thumb_dir):
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                if os.path.getmtime(fpath) < cutoff:
                    os.remove(fpath)
                    removed += 1
            except Exception as exc:
                logger.warning("Thumbnail-Cleanup: %s", exc)
    if removed:
        logger.info("Thumbnail-Cleanup: %d Dateien entfernt", removed)


def _event_photos(event_dir: str) -> list[tuple[str, float]]:
    """Liefert (absoluter_pfad, mtime) für alle Fotos in EINEM Event-Ordner."""
    out: list[tuple[str, float]] = []
    if not os.path.isdir(event_dir):
        return out
    try:
        entries = os.listdir(event_dir)
    except OSError:
        return out
    for fname in entries:
        if os.path.splitext(fname)[1].lower() not in _EXTS:
            continue
        full = os.path.join(event_dir, fname)
        try:
            out.append((full, os.path.getmtime(full)))
        except OSError:
            continue
    return out


def enforce_photo_max_age(picture_dir: str, max_age_days: int):
    """Loescht Fotos aelter als max_age_days quer ueber alle Event-Ordner.

    max_age_days <= 0 deaktiviert das zeitbasierte Cleanup.
    """
    if max_age_days <= 0 or not os.path.isdir(picture_dir):
        return
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for entry in os.listdir(picture_dir):
        ev_path = os.path.join(picture_dir, entry)
        if not os.path.isdir(ev_path):
            continue
        for fname in os.listdir(ev_path):
            if os.path.splitext(fname)[1].lower() not in _EXTS:
                continue
            fpath = os.path.join(ev_path, fname)
            try:
                if os.path.getmtime(fpath) < cutoff:
                    os.remove(fpath)
                    removed += 1
            except OSError as exc:
                logger.warning("Photo-Age-Cleanup: %s", exc)
        # Leeren Event-Ordner aufraeumen
        try:
            if not os.listdir(ev_path):
                os.rmdir(ev_path)
        except OSError:
            pass
    if removed:
        logger.info("Photo-Age-Cleanup: %d Fotos > %d Tage entfernt",
                    removed, max_age_days)


def enforce_max_photos(picture_dir: str, max_count: int, event_dir: str = None):
    """Löscht älteste Fotos in EINEM Event-Ordner bis max_count erreicht ist.

    Vorher hat das global über alle Events gelöscht — Datenschutz-Issue, weil
    Fotos vorheriger Mieter-Events durch neue verdrängt wurden. Jetzt:
    Limit gilt pro Event. Wenn event_dir nicht angegeben ist, no-op.
    """
    if not event_dir or not os.path.isdir(event_dir):
        return
    photos = _event_photos(event_dir)
    if len(photos) <= max_count:
        return
    photos.sort(key=lambda x: x[1])
    excess = len(photos) - max_count
    for path, _mt in photos[:excess]:
        try:
            os.remove(path)
            logger.info("Max-Fotos: gelöscht %s",
                        os.path.relpath(path, picture_dir))
        except Exception as exc:
            logger.warning("Max-Fotos Fehler: %s", exc)
