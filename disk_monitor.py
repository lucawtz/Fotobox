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


def _all_photos(picture_dir: str) -> list[tuple[str, float]]:
    """Liefert (absoluter_pfad, mtime) für alle Fotos in allen Event-Ordnern."""
    out: list[tuple[str, float]] = []
    if not os.path.isdir(picture_dir):
        return out
    for root, _dirs, files in os.walk(picture_dir):
        for fname in files:
            if os.path.splitext(fname)[1].lower() not in _EXTS:
                continue
            full = os.path.join(root, fname)
            try:
                out.append((full, os.path.getmtime(full)))
            except OSError:
                continue
    return out


def enforce_max_photos(picture_dir: str, max_count: int):
    """Löscht älteste Fotos über alle Event-Ordner hinweg, bis max_count erreicht."""
    photos = _all_photos(picture_dir)
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

    # Leere Event-Ordner aufräumen
    for entry in os.listdir(picture_dir):
        full = os.path.join(picture_dir, entry)
        if os.path.isdir(full):
            try:
                if not os.listdir(full):
                    os.rmdir(full)
            except OSError:
                pass
