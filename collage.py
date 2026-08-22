"""2x2-Collage aus vier Aufnahmen — plus die Namenskonvention, an der die
Galerie spaeter erkennt, was zusammengehoert.

Auf der Platte liegen nach einer Collage fuenf Dateien im Event-Ordner:

    collage_<gid>.jpg     das fertige 2x2-Bild
    collage_<gid>_1.jpg   die vier Einzelaufnahmen, aus denen es besteht
    collage_<gid>_2.jpg
    ...

Die gemeinsame `<gid>` ist die einzige Verbindung zwischen ihnen. Ohne sie
liesse sich in der Galerie nicht unterscheiden, ob ein `foto_*.jpg` ein
eigenstaendiges Bild ist oder nur ein Viertel einer Collage — und genau das
braucht der Filter "Collagen / Einzelbilder".
"""
import logging
import os
import re
import time
from typing import Optional, Tuple

from PIL import Image

logger = logging.getLogger(__name__)

_GAP = 20
_BG = (255, 255, 255)

# ── Namenskonvention ───────────────────────────────────────────────────────────

KIND_COLLAGE = "collage"   # das fertige 2x2-Bild
KIND_MEMBER  = "member"    # eine der vier Aufnahmen, aus denen es besteht
KIND_SINGLE  = "single"    # ein normal ausgeloestes Einzelfoto

# collage_<gid>[_<n>] — die Gruppe ist immer numerisch, weil sie aus einem
# Millisekunden-Zeitstempel kommt.
_NAME_RE = re.compile(r"^collage_(\d+)(?:_(\d+))?$")


def classify(filename: str) -> Tuple[str, Optional[str]]:
    """(kind, group) fuer einen Dateinamen. group ist None bei Einzelfotos.

    Robust gegenueber Altbestand: Collagen von vor dieser Konvention heissen
    ebenfalls `collage_<ms>.jpg` und werden korrekt als KIND_COLLAGE erkannt.
    Ihre damaligen Quellfotos heissen `foto_*.jpg` und bleiben Einzelfotos —
    nachtraeglich zuordnen laesst sich das nicht, dafuer fehlt die Gruppe.
    """
    stem = os.path.splitext(os.path.basename(filename))[0]
    match = _NAME_RE.match(stem)
    if not match:
        return KIND_SINGLE, None
    group, member = match.groups()
    return (KIND_MEMBER if member else KIND_COLLAGE), group


def member_name(group: str, index: int, ext: str) -> str:
    """Dateiname der `index`-ten Aufnahme (1-basiert) einer Collage."""
    return f"collage_{group}_{index}{ext}"


# ── Collage bauen ──────────────────────────────────────────────────────────────

def _adopt_shots(paths: list, group: str) -> list:
    """Benennt die Quellfotos auf die Collage-Konvention um.

    Laeuft bewusst NACH dem Speichern der Collage: schlaegt das Zusammenbauen
    fehl, bleiben die Aufnahmen unter ihrem urspruenglichen Namen liegen und
    tauchen als normale Einzelfotos in der Galerie auf, statt zu verschwinden.

    Ein fehlgeschlagenes Umbenennen ist kein Grund, die fertige Collage
    wegzuwerfen — dann steht das Foto eben als Einzelbild in der Galerie.
    """
    renamed = []
    for i, src in enumerate(paths, start=1):
        ext = os.path.splitext(src)[1]
        dst = os.path.join(os.path.dirname(src), member_name(group, i, ext))
        try:
            os.rename(src, dst)
            renamed.append(dst)
        except OSError as exc:
            logger.warning("Collage-Zuordnung fuer %s fehlgeschlagen: %s", src, exc)
            renamed.append(src)
    return renamed


def make_collage(paths: list[str], output_dir: str) -> str:
    """Erstellt 2×2-Collage aus genau 4 Fotos, gibt Pfad zurück.

    Nebenwirkung: die vier Quellfotos werden auf `collage_<gid>_<n>` umbenannt,
    damit die Galerie sie der Collage zuordnen kann. Die uebergebenen Pfade
    sind danach ungueltig.
    """
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
    group = str(int(time.time() * 1000))
    out_path = os.path.join(output_dir, f"collage_{group}.jpg")
    canvas.save(out_path, "JPEG", quality=92)

    _adopt_shots(paths, group)
    logger.info("Collage gespeichert: %s (Gruppe %s)", out_path, group)
    return out_path
