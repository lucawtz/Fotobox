"""Das Live-Signal der EOS ist anamorph — die Vorschau entzerrt es.

Ueber HDMI gibt die 700D ihr Live-Bild gestreckt aus: der Inhalt misst nach
dem Randschnitt 1771x890 (Seitenverhaeltnis 1,99), zeigt aber den 3:2-Sensor.
Alles darin ist damit rund 1,33x in die Breite gezogen. Auf der Box
nachgemessen ueber eine affine Schaetzung zwischen Live-Frame und Foto
derselben Szene: 1,36.

Das Foto selbst ist davon unberuehrt — es kommt als 5184x3456 (exakt 3:2) aus
der Kamera. Verzerrt war immer nur die Vorschau, und damit richtete sich der
Gast nach einem Bild aus, das es so nicht gibt.

Korrigiert wird beim ohnehin noetigen Skalieren: der Zuschnitt nimmt die
Streckung vorweg, das abschliessende resize entzerrt mit. Kostet nichts.
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import numpy as np
import pytest

import ui as ui_mod


def _frame(w, h):
    return np.zeros((h, w, 3), dtype=np.uint8)


def _probe(cfg):
    inst = ui_mod.UI.__new__(ui_mod.UI)
    inst._cfg = cfg
    return inst


# ── Der Faktor selbst ─────────────────────────────────────────────────────────

def test_stretch_is_derived_from_the_frame():
    """1771x890 auf einem 3:2-Sensor sind rund 1,33x zu breit."""
    p = _probe({"live_source_aspect": [3, 2]})

    s = p._source_stretch(_frame(1771, 890))

    assert s == pytest.approx(1.99 / 1.5, abs=0.01)


def test_an_unstretched_source_needs_no_correction():
    """Liefert eine Quelle schon 3:2, bleibt alles wie es ist."""
    p = _probe({"live_source_aspect": [3, 2]})

    assert p._source_stretch(_frame(1500, 1000)) == pytest.approx(1.0)


def test_without_config_there_is_no_correction():
    """Leer heisst: nimm das Bild, wie es kommt — das alte Verhalten."""
    for value in (None, [], [0, 0]):
        p = _probe({"live_source_aspect": value})
        assert p._source_stretch(_frame(1771, 890)) == 1.0


def test_a_broken_value_does_not_crash(caplog):
    """Ein kaputter Config-Wert darf den Abend nicht beenden."""
    p = _probe({"live_source_aspect": "16:9"})

    with caplog.at_level("WARNING"):
        assert p._source_stretch(_frame(1771, 890)) == 1.0

    assert any("live_source_aspect" in r.getMessage() for r in caplog.records)


def test_the_factor_is_clamped():
    """Ein misslungener Randschnitt darf die Vorschau nicht zerquetschen.

    Bleibt bei einem halb schwarzen Frame nur ein schmaler Streifen uebrig,
    waere der abgeleitete Faktor absurd — dann lieber ein leicht falsches
    Bild als ein unbrauchbares.
    """
    p = _probe({"live_source_aspect": [3, 2]})

    assert p._source_stretch(_frame(4000, 100)) <= 2.0
    assert p._source_stretch(_frame(100, 4000)) >= 0.5


# ── Wirkung auf den Zuschnitt ─────────────────────────────────────────────────

@pytest.fixture
def geometry(monkeypatch):
    """UI, die _live_geometry echt durchlaeuft — nur ohne Fenster.

    Festgehalten wird, mit welchem Zielformat zugeschnitten wurde: dort
    steckt die Entzerrung, und dort faellt sie auch weg, wenn sie jemand
    versehentlich herausnimmt.
    """
    import pygame
    pygame.display.init()
    pygame.display.set_mode((320, 240))

    seen = {}
    inst = ui_mod.UI.__new__(ui_mod.UI)
    inst._cfg = {"live_view_aspect": [16, 9], "live_source_aspect": [3, 2]}
    inst._live_aspect = 1.5
    inst._live_frame_rgb = lambda: (_frame(1771, 890), None)
    inst._live_box = lambda: pygame.Rect(0, 0, 800, 450)
    inst._live_surface = lambda f, w, h: pygame.Surface((w, h))

    real_crop = ui_mod.UI._crop_to_aspect

    def spy(frame, target):
        seen["target"] = target
        return real_crop(frame, target)

    monkeypatch.setattr(ui_mod.UI, "_crop_to_aspect", staticmethod(spy))
    inst.seen = seen
    yield inst
    pygame.display.quit()


def test_the_crop_takes_the_stretch_into_account(geometry):
    """Zugeschnitten wird in Quellpixeln, also 16:9 MAL Streckung.

    Ohne den Faktor schneidet die Box ein 16:9-Stueck aus einem gestreckten
    Bild und zeigt es als 16:9 — die Verzerrung bleibt dann drin.
    """
    geometry._live_geometry()

    stretch = 1771 / 890 / 1.5
    assert geometry.seen["target"] == pytest.approx(16 / 9 * stretch, rel=0.01)


def test_without_correction_the_crop_is_plain(geometry):
    """Gegenprobe: ohne live_source_aspect bleibt es beim nackten Zielformat."""
    geometry._cfg["live_source_aspect"] = None

    geometry._live_geometry()

    assert geometry.seen["target"] == pytest.approx(16 / 9, rel=0.01)
