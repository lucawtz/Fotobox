"""Papiervorrat mitzaehlen.

Ueber CUPS meldet der Selphy nur `media-empty` — und das erst, wenn das letzte
Blatt durch ist. Am Event-Tag ist das die falsche Reihenfolge: wer nachlegen
will, muss es vorher wissen, nicht wenn schon ein Gast vor der leeren Box
steht. Eine Restmenge liefert das Geraet ueber den `usblp`-Treiber nicht
(siehe HARDWARE.md), also wird sie hier selbst gefuehrt.

Gezaehlt wird, was CUPS annimmt: jeder angenommene Auftrag zieht so viele
Blatt ab, wie er Kopien hat. Der Stand liegt neben der config.json, damit ein
Neustart mitten im Event ihn nicht vergisst.

Das ist eine Schaetzung, kein Messwert. Ein Papierstau, ein in CUPS
abgebrochener Auftrag oder eine von Hand nachgelegte Handvoll Blatt gehen
daneben, und der Zaehler merkt davon nichts. Daraus folgen drei Dinge, die
hier bewusst so gebaut sind:

  * Die Oberflaeche schreibt "noch ca." — eine glatte Zahl wuerde eine
    Genauigkeit vorgeben, die es nicht gibt.
  * `set_left` gibt es, damit der Stand nach jedem Stau wieder stimmt, ohne
    dass jemand ein halbes Paket verwirft.
  * Gesperrt wird hier nichts. Ob wirklich Papier da ist, weiss allein der
    Drucker (`media-empty` in printing._REASON_TEXT); ein Zaehler, der auf 0
    steht, waehrend die Kassette voll ist, duerfte den Knopf nicht wegnehmen.
"""

import json
import logging
import os
import threading
import time
from typing import Optional

import config

logger = logging.getLogger(__name__)

# Neben der config.json und nicht bei den Fotos: der Stand gehoert zur Box,
# nicht zum Event. Ein neuer Event-Ordner faengt bei null an, die Kassette
# nicht. Der Pfad wird bei jedem Zugriff aus config.CONFIG_PATH abgeleitet,
# damit die Tests ihn ueber dieselbe Stellschraube umbiegen koennen wie alles
# andere (siehe tests/conftest.py).
_STATE_FILE = ".paper_state.json"

# Obergrenze fuer eine Paketgroesse. Das groesste Canon-Paket hat 108 Blatt;
# 999 laesst Luft fuer alles, was ein anderer Drucker mitbringt, und faengt
# den vertippten Tausender ab.
PACK_MAX = 999

_lock = threading.RLock()
# Der Zaehler wird aus der Renderschleife der Box gelesen (1x/s) und beim
# Drucken geschrieben. Gecacht wird ueber die mtime statt ueber eine Zeit:
# im Normalfall laeuft alles in einem Prozess (main.py startet den
# Galerie-Server als Thread), aber `dev_server.py` startet ihn allein — dann
# schreibt ein zweiter Prozess dieselbe Datei, und ein reiner In-Memory-Cache
# zeigte dort dauerhaft veraltete Zahlen.
_cache: Optional[dict] = None
_cache_key: Optional[tuple] = None

_EMPTY = {"used": 0, "loaded_at": None, "last_print": None}


def _path() -> str:
    return os.path.join(os.path.dirname(config.CONFIG_PATH), _STATE_FILE)


def _read() -> dict:
    """Gespeicherter Stand. Fehlt die Datei, ist das kein Fehler — dann ist
    schlicht noch nie gedruckt worden."""
    path = _path()
    try:
        st = os.stat(path)
        key = (path, st.st_mtime_ns, st.st_size)
    except OSError:
        key = (path, None, None)

    with _lock:
        global _cache, _cache_key
        if _cache is not None and key == _cache_key:
            return dict(_cache)
        data = dict(_EMPTY)
        if key[1] is not None:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                if isinstance(stored, dict):
                    data.update({k: stored.get(k, v) for k, v in _EMPTY.items()})
            except (OSError, ValueError) as exc:
                # Eine kaputte Zaehlerdatei darf das Drucken nicht aufhalten.
                # Bei 0 weiterzuzaehlen ist die harmlosere Luege: es warnt zu
                # spaet statt zu frueh, und das faellt beim naechsten Blick
                # ins Panel auf.
                logger.warning("Papierzaehler unlesbar (%s): %s", path, exc)
        _cache, _cache_key = dict(data), key
        return data


def _write(data: dict) -> bool:
    """Stand sichern. Erst in eine Nebendatei, dann umbenennen — ein Absturz
    mitten im Schreiben soll keinen halben Zaehler hinterlassen (wie in
    events._write_pin)."""
    path = _path()
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except OSError as exc:
        logger.warning("Papierzaehler nicht gespeichert (%s): %s", path, exc)
        return False
    with _lock:
        global _cache, _cache_key
        _cache = dict(data)
        try:
            st = os.stat(path)
            _cache_key = (path, st.st_mtime_ns, st.st_size)
        except OSError:
            _cache_key = None
    return True


def _clamp_int(value, default: int = 0, high: int = PACK_MAX) -> int:
    try:
        return max(0, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def pack_size(cfg: dict) -> int:
    """Blatt je Paket laut Config. 0 = Zaehler aus."""
    return _clamp_int(cfg.get("paper_pack_size", 0), 0)


def warn_at(cfg: dict) -> int:
    """Ab wieviel Restblatt gewarnt wird."""
    return _clamp_int(cfg.get("paper_warn_at", 10), 10)


def state(cfg: dict) -> dict:
    """Papierstand fuer Oberflaeche und Statusleiste.

    `tracked` sagt, ob ueberhaupt eine Paketgroesse hinterlegt ist. Ohne die
    ist `left` bedeutungslos, und beide Oberflaechen zeigen dann gar nichts —
    lieber keine Zahl als eine erfundene.
    """
    size = pack_size(cfg)
    data = _read()
    used = _clamp_int(data.get("used"), 0, high=10 ** 6)
    left = max(0, size - used) if size else 0
    warn = warn_at(cfg)
    return {
        "tracked":   size > 0,
        "size":      size,
        "used":      used,
        "left":      left,
        "warn_at":   warn,
        "low":       size > 0 and left <= warn,
        "empty":     size > 0 and left <= 0,
        # None = seit dem Einrichten noch nie zurueckgesetzt. Das Panel fragt
        # dann danach, statt eine Zahl zu zeigen, die niemand geeicht hat.
        "loaded_at": data.get("loaded_at"),
    }


def record(cfg: dict, sheets: int = 1) -> dict:
    """Verbrauchte Blatt abziehen. Aufgerufen, sobald CUPS einen Auftrag
    angenommen hat.

    Gezaehlt wird auch, wenn keine Paketgroesse hinterlegt ist. Sonst stuende
    der Zaehler beim spaeteren Einschalten auf einem Stand von vorgestern, und
    die erste angezeigte Zahl waere die falscheste.
    """
    # Bewusst grosszuegig begrenzt: was eine sinnvolle Blattzahl je Auftrag
    # ist, weiss die Aufrufseite (printing._copies laesst 1-9 durch). Hier
    # still auf eine kleinere Zahl zu kappen hiesse, einen echten Verbrauch
    # zu verschlucken.
    n = _clamp_int(sheets, 1, high=10 ** 6)
    if n <= 0:
        return state(cfg)
    with _lock:
        data = _read()
        data["used"] = _clamp_int(data.get("used"), 0, high=10 ** 6) + n
        data["last_print"] = time.time()
        _write(data)
    return state(cfg)


def refill(cfg: dict) -> dict:
    """Neues Paket eingelegt: Zaehler auf null."""
    with _lock:
        data = _read()
        data["used"] = 0
        data["loaded_at"] = time.time()
        _write(data)
    return state(cfg)


def set_left(cfg: dict, left: int) -> dict:
    """Restmenge von Hand setzen — nach einem Stau oder wenn nachgezaehlt
    wurde.

    Ohne hinterlegte Paketgroesse gibt es keinen Bezugswert; dann bleibt der
    Stand, wie er ist. Der Aufrufer prueft das vorher (gallery_server), hier
    steht es nur, damit ein direkter Aufruf nichts kaputt macht.
    """
    size = pack_size(cfg)
    if size <= 0:
        return state(cfg)
    with _lock:
        data = _read()
        data["used"] = size - _clamp_int(left, 0, high=size)
        # Kein neues loaded_at: von Hand korrigiert ist nicht dasselbe wie
        # frisch eingelegt, und das Panel unterscheidet beides.
        _write(data)
    return state(cfg)
