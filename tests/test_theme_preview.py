"""Die Theme-Vorschau im Panel zeichnet die Sidebar der Box nach.

Sie ist eine zweite Implementierung desselben Layouts — in TypeScript, gegen
dieselben Zahlen (ThemePreview.tsx traegt die Konstanten aus ui.py). Das ist
Absicht: das Panel soll die Farbwirkung zeigen koennen, ohne die Box zu
fragen. Es kostet aber genau eine Gefahr, und die ist keine theoretische —
sie ist bereits eingetreten: ui.py schrieb bei offenem WLAN "Kein Passwort
noetig" in die WLAN-Box, die Vorschau liess die Zeile ersatzlos weg. Nichts
brach dabei, die Vorschau zeigte nur etwas anderes als der Boxschirm.

Geprueft wird am Quelltext, nicht am Verhalten: fuer das Verhalten braeuchte
es eine JS-Testumgebung, die es hier nicht gibt. Ein Textvergleich faengt den
Fall trotzdem, um den es geht — dass jemand die eine Seite aendert und die
andere vergisst.
"""
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREVIEW = os.path.join(HERE, "frontend", "src", "pages", "admin",
                       "ThemePreview.tsx")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_open_wifi_hint_is_worded_identically():
    """Derselbe Satz auf beiden Seiten — sonst zeigt die Vorschau etwas,
    das so nie auf dem Boxschirm steht."""
    hint = "Kein Passwort nötig"

    assert hint in _read(os.path.join(HERE, "ui.py")), (
        f"{hint!r} steht nicht mehr in ui.py — dann gehoert es auch aus "
        "der Vorschau raus")
    assert hint in _read(PREVIEW), (
        f"{hint!r} fehlt der Theme-Vorschau — bei offenem WLAN zeigt sie "
        "dann eine leere Stelle, wo die Box einen Hinweis schreibt")


def test_preview_asks_whether_the_box_is_the_access_point():
    """Den Hinweis gibt es nur, solange die Box selbst der AP ist.

    ui.py haengt ihn an hotspot_enabled. Ratet die Vorschau den Wert statt
    ihn zu lesen, steht im Setup-Betrieb (--no-hotspot am Heim-WLAN) eine
    Zeile in der Vorschau, die auf dem Boxschirm fehlt.
    """
    src = _read(PREVIEW)

    assert "hotspotEnabled" in src, (
        "die Vorschau wertet hotspot_enabled nicht aus")
    assert "hotspot_enabled" in _read(
        os.path.join(HERE, "gallery_server.py")), (
        "der Admin-GET liefert hotspot_enabled nicht mehr — dann kann die "
        "Vorschau es auch nicht lesen")
