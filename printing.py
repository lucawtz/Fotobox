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
# `state` ist der CUPS-Zustand des aufgeloesten Druckers (idle | printing |
# disabled | unknown) oder None, wenn gar keiner in Frage kommt. Er haengt hier
# mit drin, damit die UI "geprueft bereit" von "angeboten, aber nicht
# auslesbar" unterscheiden kann — `available` allein sagt das nicht, weil
# 'unknown' bewusst als bereit durchgeht (siehe list_printers).
_status: dict = {"available": False, "printer": None, "message": "noch nicht geprüft",
                 "state": None, "checked": 0.0}


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


def _printer_states() -> dict:
    """Zustand je Drucker aus `lpstat -p`.

    Nur auswertbar, wenn CUPS englisch antwortet — die Zeile ist uebersetzt.
    Leeres dict heisst deshalb "Zustand unbekannt", nicht "kein Drucker".
    """
    proc = _run(["lpstat", "-p"])
    if proc is None or proc.returncode != 0:
        return {}
    states = {}
    for line in proc.stdout.splitlines():
        # "printer Selphy is idle.  enabled since ..." / "... is disabled since"
        m = re.match(r"printer\s+(\S+)\s+is\s+(\S+?)\.?\s", line + " ")
        if m:
            states[m.group(1)] = (m.group(2).lower(), line.strip())
    return states


def list_printers() -> list[dict]:
    """Alle CUPS-Drucker mit Zustand. Leere Liste = keiner eingerichtet.

    Die Namen kommen aus `lpstat -e` — eine nackte Zieladresse pro Zeile, ohne
    uebersetzbare Prosa. `lpstat -p` wird von CUPS dagegen lokalisiert: auf
    einem deutschen System steht dort 'Drucker „Selphy" ist inaktiv', woran der
    englische Parser scheitert. Das Ergebnis war eine leere Liste, damit
    `available() == False`, damit kein Druck-Knopf in der UI (`print_ready`) —
    und die irrefuehrende Meldung "Kein Drucker in CUPS eingerichtet", obwohl
    einer angeschlossen war.
    """
    states = _printer_states()

    names = []
    proc = _run(["lpstat", "-e"])
    if proc is not None and proc.returncode == 0:
        names = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    if not names:
        # Aeltere CUPS-Versionen ohne `-e`: dann bleibt nur der englische Parser.
        names = list(states)

    out = []
    for name in names:
        state, line = states.get(name, ("unknown", ""))
        out.append({
            "name":  name,
            "state": state,                      # idle | printing | disabled | unknown
            # 'unknown' heisst "lpstat antwortet nicht auf Englisch", nicht
            # "Drucker kaputt". Lieber den Knopf anbieten und einen echten
            # lp-Fehler melden, als das Drucken stumm zu verstecken.
            "ready": state in ("idle", "printing", "unknown"),
            "line":  line or name,
        })
    return out


def default_printer() -> Optional[str]:
    """Standarddrucker laut CUPS, oder None.

    Ebenfalls uebersetzt: "system default destination: Selphy" heisst auf
    Deutsch "System-Standardzielort: Selphy". Ein Regex auf das englische
    Wort lieferte dort None — resolve_printer() fiel dann auf den
    erstbesten Drucker zurueck und ignorierte den eingestellten Standard.
    Deshalb wird nur auf den Doppelpunkt gematcht; den gibt es genau dann,
    wenn ueberhaupt ein Standard gesetzt ist ("no system default
    destination" / "Kein System-Standardzielort" haben keinen).
    """
    proc = _run(["lpstat", "-d"])
    if proc is None or proc.returncode != 0:
        return None
    m = re.search(r":\s*(\S+)\s*$", proc.stdout.strip())
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
            _status.update(available=False, printer=None, state=None,
                           message="Drucken in der Config deaktiviert",
                           checked=time.monotonic())
            return dict(_status)

        printers = list_printers()
        if not printers:
            _status.update(available=False, printer=None, state=None,
                           message="Kein Drucker in CUPS eingerichtet",
                           checked=time.monotonic())
            return dict(_status)

        name = resolve_printer(cfg)
        if name is None:
            wanted = cfg.get("printer_name")
            _status.update(
                available=False, printer=None, state=None,
                message=f"Drucker '{wanted}' nicht gefunden",
                checked=time.monotonic())
            return dict(_status)

        entry = next((p for p in printers if p["name"] == name), None)
        ready = bool(entry and entry["ready"])
        state = entry["state"] if entry else "unknown"
        # Meldung aus dem Zustand statt aus dem Ja/Nein: "ist deaktiviert" war
        # frueher die Antwort auf JEDEN nicht-bereiten Zustand, auch auf
        # solche, die CUPS ausser 'disabled' liefert.
        if state == "unknown":
            message = f"Drucker '{name}' gefunden, Zustand nicht auslesbar"
        elif ready:
            message = "bereit"
        elif state == "disabled":
            message = f"Drucker '{name}' ist deaktiviert"
        else:
            message = f"Drucker '{name}' meldet '{state}'"
        _status.update(available=ready, printer=name, state=state,
                       message=message, checked=time.monotonic())
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

def _paper_mm(cfg: dict) -> tuple[float, float]:
    """Papierformat als (lange Seite, kurze Seite) in mm, immer plausibel.

    Einzige Quelle fuer die Masse — prepare() hatte frueher eine zweite,
    ungepruefte Ableitung derselben Werte und ist bei print_size_mm=[0, 0]
    in eine Division durch null gelaufen.
    """
    size = cfg.get("print_size_mm") or [148, 100]
    try:
        w, h = float(size[0]), float(size[1])
        if not (w > 0 and h > 0):
            raise ValueError("Papierformat muss positiv sein")
    except (TypeError, ValueError, IndexError) as exc:
        logger.warning("Ungueltiges print_size_mm %r (%s) — nutze 148x100 mm",
                       size, exc)
        w, h = 148.0, 100.0
    return max(w, h), min(w, h)


def _print_dpi(cfg: dict) -> int:
    """Druckaufloesung aus der Config, immer plausibel.

    Wie _paper_mm die einzige Quelle: prepare() und die Testseite muessen
    dieselbe Zahl benutzen, sonst passt die Testseite nicht aufs Blatt.
    """
    raw = cfg.get("print_dpi", 300)
    try:
        dpi = int(raw or 300)
        if dpi <= 0:
            raise ValueError("dpi muss positiv sein")
        return dpi
    except (TypeError, ValueError) as exc:
        logger.warning("Ungueltiges print_dpi %r (%s) — nutze 300", raw, exc)
        return 300


def _paper_aspect(cfg: dict) -> float:
    """Seitenverhältnis des Papiers (Breite/Höhe) im Querformat."""
    long_mm, short_mm = _paper_mm(cfg)
    return long_mm / short_mm


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
    dpi = _print_dpi(cfg)
    long_mm, short_mm = _paper_mm(cfg)

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


# ── Testdruck ──────────────────────────────────────────────────────────────────
#
# Vor einem Event sind es immer dieselben vier Fragen: Kommt ueberhaupt Papier?
# Stimmt das Format? Wird der Rand abgeschnitten? Sind die Farben brauchbar?
# Ein Foto beantwortet davon nur die erste — auf einem Gruppenbild sieht
# niemand, dass links 3 mm fehlen. Darum eine Seite mit Rahmen, Eckwinkeln und
# Massstab: jedes Element beantwortet genau eine der Fragen.

_MODE_LABEL = {
    "auto":  "automatisch (Einzelfoto randlos, Collage vollständig)",
    "cover": "immer randlos",
    "fit":   "immer vollständig",
}


def _test_font(size_px: int):
    """Schrift fuer die Testseite, nach Verfuegbarkeit auf dem Ziel.

    Kein Grund fuer eine neue Abhaengigkeit: das Pi hat DejaVu, und pygame ist
    ohnehin Pflicht und bringt eine Schrift mit — dieselbe, auf die auch ui.py
    zurueckfaellt. Zuletzt Pillows eingebaute: dann sieht es haesslich aus,
    aber der Testdruck kommt trotzdem heraus.
    """
    from PIL import ImageFont
    candidates = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    try:
        import pygame
        candidates.append(os.path.join(os.path.dirname(pygame.__file__),
                                       "freesansbold.ttf"))
    except ImportError:
        pass
    for path in candidates:
        try:
            return ImageFont.truetype(path, size_px)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size_px)   # Pillow >= 10.1
    except TypeError:                                  # aeltere Pillow
        return ImageFont.load_default()


def test_page(cfg: dict, printer: Optional[str] = None) -> str:
    """Zeichnet eine Testseite im eingestellten Papierformat.

    Bewusst exakt im Seitenverhaeltnis des Papiers erzeugt: dann laesst
    prepare() sie unveraendert durch (cover wie fit sind hier identisch), und
    was auf dem Blatt fehlt, hat wirklich der Drucker abgeschnitten und nicht
    die Aufbereitung. Damit ist der Testdruck aussagekraeftig, egal welcher
    print_mode eingestellt ist.

    Alle Positionen sind Anteile der Blatthoehe, nur Rahmen, Eckwinkel und
    Massstab sind in mm — die muessen physikalisch stimmen, der Rest soll auf
    jedem Papierformat sitzen (Postkarte wie 13x18).

    Rueckgabe: Pfad einer temporaeren JPEG-Datei; der Aufrufer loescht sie.
    """
    from PIL import Image, ImageDraw

    long_mm, short_mm = _paper_mm(cfg)
    dpi = _print_dpi(cfg)

    def px(v_mm: float) -> int:
        return int(round(v_mm / 25.4 * dpi))

    w, h = px(long_mm), px(short_mm)
    xr, yb = w - 1, h - 1
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)

    ink  = (25, 25, 25)
    soft = (110, 110, 110)
    mark = (220, 0, 120)          # kraeftig, faellt auch auf blassem Druck auf

    # Rahmen 5 mm vom Blattrand. Ringsum gleich breit = Format und Skalierung
    # stimmen; auf einer Seite duenner = das Bild sitzt nicht mittig.
    inset = px(5)
    d.rectangle([inset, inset, xr - inset, yb - inset],
                outline=ink, width=max(1, px(0.4)))

    # Eckwinkel direkt am Blattrand. Randlos druckende Treiber vergroessern das
    # Bild leicht ("bleed") — dann fehlen genau diese Winkel, und man weiss,
    # wie viel ein echtes Foto am Rand verliert.
    arm, thick = px(9), max(2, px(0.8))
    for horiz, vert in (
        ((0, 0, arm, thick),                 (0, 0, thick, arm)),
        ((xr - arm, 0, xr, thick),           (xr - thick, 0, xr, arm)),
        ((0, yb - thick, arm, yb),           (0, yb - arm, thick, yb)),
        ((xr - arm, yb - thick, xr, yb),     (xr - thick, yb - arm, xr, yb)),
    ):
        d.rectangle(horiz, fill=mark)
        d.rectangle(vert, fill=mark)

    # Textblock. Bewusst ohne `anchor=`: das unterstuetzt die eingebaute
    # Pillow-Schrift aus _test_font nicht, und daran soll der Testdruck nicht
    # scheitern.
    x0, x1 = px(11), w - px(11)
    f_title = _test_font(max(8, int(h * 0.085)))
    f_body  = _test_font(max(6, int(h * 0.040)))
    f_small = _test_font(max(6, int(h * 0.030)))

    d.text((x0, int(h * 0.055)), "TESTDRUCK", font=f_title, fill=ink)
    d.text((x0, int(h * 0.165)),
           "Rahmen ringsum gleich breit? Eckwinkel vollständig? "
           "Dann stimmen Format und Ränder.",
           font=f_small, fill=soft)

    media = (cfg.get("print_media") or "").strip() or "Treiber-Standard"
    mode  = (cfg.get("print_mode") or "auto").lower()
    def clip(text: str, font, limit: int) -> str:
        """Kuerzt auf die Rahmenbreite. CUPS-Namen wie
        'Canon_SELPHY_CP1500_5640_series__Dachboden_' sind laenger als das
        Blatt breit ist, und der Text wuerde sonst stumm ins Nichts laufen."""
        try:
            if d.textlength(text, font=font) <= limit:
                return text
            while text and d.textlength(text + "…", font=font) > limit:
                text = text[:-1]
            return text + "…"
        except (AttributeError, TypeError):   # Schrift ohne Laengenmessung
            return text

    lines = [
        f"Drucker:   {printer or 'Standarddrucker'}",
        f"Papier:    {long_mm:g} x {short_mm:g} mm · {dpi} dpi · Medium {media}",
        f"Ausgabe:   {_MODE_LABEL.get(mode, mode)}",
        f"Gedruckt:  {time.strftime('%d.%m.%Y %H:%M')}",
    ]
    for i, line in enumerate(lines):
        d.text((x0, int(h * (0.27 + 0.055 * i))),
               clip(line, f_body, x1 - x0), font=f_body, fill=ink)

    # Farbfelder und Graukeil: zeigen leere Farbbaender und einen zugesetzten
    # Druckkopf, bevor es das Gruppenfoto tut.
    d.text((x0, int(h * 0.505)),
           "Farben und Graustufen müssen sich klar voneinander abheben:",
           font=f_small, fill=soft)
    patches = [(230, 30, 40), (0, 160, 70), (30, 80, 200),
               (0, 170, 210), (220, 0, 140), (250, 210, 0)]
    greys = [(v, v, v) for v in (255, 204, 153, 102, 51, 0)]

    def swatch_row(colors, top_frac, bottom_frac):
        top, bottom = int(h * top_frac), int(h * bottom_frac)
        span = (x1 - x0) / len(colors)
        for i, col in enumerate(colors):
            left = int(x0 + i * span)
            right = int(x0 + (i + 1) * span) - max(1, px(0.5))
            d.rectangle([left, top, right, bottom], fill=col, outline=soft)

    swatch_row(patches, 0.565, 0.665)
    swatch_row(greys,   0.675, 0.755)

    # Massstab: der einzige Weg, eine falsche Skalierung wirklich zu belegen.
    # Laenge nach Papier gewaehlt, damit er auch auf kleinem Format passt.
    usable_mm = long_mm - 22.0
    bar_mm = next((c for c in (100.0, 50.0, 20.0, 10.0) if c <= usable_mm),
                  max(usable_mm, 1.0))
    tick_mm = 10.0 if bar_mm >= 20.0 else bar_mm / 5.0
    bar_y = int(h * 0.845)
    d.rectangle([x0, bar_y, x0 + px(bar_mm), bar_y + max(1, px(0.5))], fill=ink)
    pos = 0.0
    while pos <= bar_mm + 1e-6:
        long_tick = pos in (0.0, bar_mm) or abs(pos - bar_mm / 2) < 1e-6
        tick_x = x0 + px(pos)
        d.rectangle([tick_x, bar_y - px(4.0 if long_tick else 2.0),
                     tick_x + max(1, px(0.5)), bar_y], fill=ink)
        pos += tick_mm
    d.text((x0, int(h * 0.885)),
           f"Massstab: diese Linie muss genau {bar_mm:g} mm lang sein — nachmessen.",
           font=f_small, fill=soft)

    fd, tmp = tempfile.mkstemp(prefix="fotobox-testpage-", suffix=".jpg")
    os.close(fd)
    img.save(tmp, "JPEG", quality=95, dpi=(dpi, dpi))
    logger.info("Testseite erzeugt: %dx%d px (%g x %g mm @ %d dpi)",
                w, h, long_mm, short_mm, dpi)
    return tmp


def print_test(cfg: dict) -> tuple[bool, str]:
    """Druckt eine Testseite ueber denselben Weg wie ein echtes Foto.

    Immer genau EIN Blatt, egal was `print_copies` sagt: der Testdruck soll das
    Papier pruefen, nicht verbrauchen — Thermosublimationspapier kommt in
    gezaehlten Boegen, und 9 Testdrucke waeren ein teurer Vertipper.

    Rueckgabe wie print_photo: (erfolgreich, Meldung).
    """
    st = refresh_status(cfg)
    if not st["available"]:
        return False, st["message"]

    try:
        path = test_page(cfg, st["printer"])
    except ImportError:
        return False, "Pillow fehlt — Testseite kann nicht erzeugt werden"
    except Exception as exc:
        logger.error("Testseite: %s", exc, exc_info=True)
        return False, "Testseite konnte nicht erzeugt werden"

    try:
        ok, message = print_photo(path, dict(cfg, print_copies=1))
        return ok, ("Testseite wird gedruckt" if ok else message)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
