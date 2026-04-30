"""Lese-Helfer für den USB-Export-Status.

scripts/usb_export.py schreibt /run/fotobox/usb_status.json bei jedem
Fortschritt — die Hauptschleife pollt den Status und blendet das
Overlay ein, solange eine Datei vorhanden ist.
"""

import json
import os
from typing import Optional

STATE_PATH = "/run/fotobox/usb_status.json"


def read() -> Optional[dict]:
    """Liefert den aktuellen Export-Status oder None wenn keiner aktiv ist."""
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    except OSError:
        return None


def is_active() -> bool:
    return os.path.exists(STATE_PATH)
