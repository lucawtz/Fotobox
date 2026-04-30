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


def is_low(path: str, threshold_mb: int = 500) -> bool:
    free = get_free_mb(path)
    if free < threshold_mb:
        logger.warning("Speicherwarnung: nur %d MB frei", free)
        return True
    return False


def cleanup_old_thumbnails(thumb_dir: str, max_age_days: int = 30):
    if not os.path.isdir(thumb_dir):
        return
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for fname in os.listdir(thumb_dir):
        fpath = os.path.join(thumb_dir, fname)
        try:
            if os.path.getmtime(fpath) < cutoff:
                os.remove(fpath)
                removed += 1
        except Exception as exc:
            logger.warning("Thumbnail-Cleanup: %s", exc)
    if removed:
        logger.info("Thumbnail-Cleanup: %d Dateien entfernt", removed)


def enforce_max_photos(picture_dir: str, max_count: int):
    if not os.path.isdir(picture_dir):
        return
    files = sorted(
        [f for f in os.listdir(picture_dir) if os.path.splitext(f)[1].lower() in _EXTS],
        key=lambda f: os.path.getmtime(os.path.join(picture_dir, f)),
    )
    to_delete = files[:max(0, len(files) - max_count)]
    for fname in to_delete:
        try:
            os.remove(os.path.join(picture_dir, fname))
            logger.info("Max-Fotos: gelöscht %s", fname)
        except Exception as exc:
            logger.warning("Max-Fotos Fehler: %s", exc)
