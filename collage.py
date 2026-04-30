import logging
import os
import time

from PIL import Image

logger = logging.getLogger(__name__)

_GAP = 20
_BG = (255, 255, 255)


def make_collage(paths: list[str], output_dir: str) -> str:
    """Erstellt 2×2-Collage aus genau 4 Fotos, gibt Pfad zurück."""
    assert len(paths) == 4, "Genau 4 Fotos benötigt"

    images = [Image.open(p).convert("RGB") for p in paths]
    min_w = min(img.width for img in images)
    min_h = min(img.height for img in images)
    images = [img.resize((min_w, min_h), Image.LANCZOS) for img in images]

    canvas_w = min_w * 2 + _GAP * 3
    canvas_h = min_h * 2 + _GAP * 3
    canvas = Image.new("RGB", (canvas_w, canvas_h), _BG)

    positions = [
        (_GAP,             _GAP),
        (min_w + _GAP * 2, _GAP),
        (_GAP,             min_h + _GAP * 2),
        (min_w + _GAP * 2, min_h + _GAP * 2),
    ]
    for img, pos in zip(images, positions):
        canvas.paste(img, pos)

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"collage_{int(time.time() * 1000)}.jpg")
    canvas.save(out_path, "JPEG", quality=92)
    logger.info("Collage gespeichert: %s", out_path)
    return out_path
