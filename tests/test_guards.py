"""Sicherheitsgrenzen und Datei-Auswahl.

Diese Funktionen entscheiden, auf welche Pfade ein Gast zugreifen darf. Ein
Fehler hier gibt das ganze Dateisystem frei — deshalb stehen sie hier zuerst.
"""
import os

import pytest

import events
import gallery_server


TRAVERSAL = [
    "..", "../", "../..", "../../etc/passwd",
    "..%2f..%2fetc%2fpasswd",
    "/etc/passwd", "/", "//",
    ".hidden", ".", ".ssh",
    "event/../../etc", "a/b",
    "", "   ".strip(),
]


@pytest.mark.parametrize("bad", TRAVERSAL)
def test_is_safe_event_rejects_traversal(bad):
    assert events.is_safe_event(bad) is False


@pytest.mark.parametrize("good", [
    "2026-10-15_lisa-und-tom",
    "2026-10-15_lisa-und-tom-2",
    "2026-01-01_archiv",
    "fotobox",
])
def test_is_safe_event_accepts_normal_folders(good):
    assert events.is_safe_event(good) is True


def test_is_safe_event_rejects_os_separator():
    # Auf Windows ist os.sep '\\' — der Guard muss beide Trenner kennen.
    assert events.is_safe_event("event" + os.sep + "sub") is False


@pytest.mark.parametrize("bad", [
    "../../etc/passwd", "..", "/abs/path", "sub/dir/file.jpg", "",
    "a/../b", "." + os.sep + "x",
])
def test_safe_filename_rejects_paths(bad):
    assert gallery_server._safe_filename(bad) is False


@pytest.mark.parametrize("good", ["foto_123.jpg", "IMG_0001.JPEG", "bild.png"])
def test_safe_filename_accepts_plain_names(good):
    assert gallery_server._safe_filename(good) is True


def test_safe_filename_does_not_check_extension():
    """Dokumentiert bewusstes Verhalten, kein Versehen.

    _safe_filename schuetzt ausschliesslich gegen Pfad-Ausbrueche. Die
    Beschraenkung auf Bilder passiert eine Ebene tiefer: _safe_path verlangt
    eine existierende Datei, und in picture_dir landen nur Fotos (camera.py
    und collage.py schreiben dort, sonst niemand).
    """
    assert gallery_server._safe_filename("notiz.txt") is True
    # ... aber ausliefern laesst sie sich trotzdem nicht, solange sie nicht existiert:
    assert gallery_server._safe_path("2026-10-15_test", "notiz.txt") is None


def test_safe_path_stays_inside_picture_dir(cfg, monkeypatch, photo_factory, tmp_path):
    import config
    monkeypatch.setitem(config.cfg, "picture_dir", cfg["picture_dir"])

    ev = "2026-10-15_test"
    photo_factory(os.path.join(cfg["picture_dir"], ev, "foto.jpg"))
    # Zieldatei ausserhalb, die ein Traversal erreichen wollen wuerde
    (tmp_path / "geheim.jpg").write_bytes(b"geheim")

    assert gallery_server._safe_path(ev, "foto.jpg") is not None
    for bad_event in ("..", "../..", "/etc"):
        assert gallery_server._safe_path(bad_event, "foto.jpg") is None
    for bad_file in ("../../geheim.jpg", "/etc/passwd"):
        assert gallery_server._safe_path(ev, bad_file) is None


def test_slugify_is_filesystem_safe():
    cases = {
        "Lisa & Tom": "lisa-tom",
        "Müller/Schmidt": "muller-schmidt",
        "  ": "fotobox",
        "": "fotobox",
        "../../etc": "etc",
        "Ärger mit Ümläuten!": "arger-mit-umlauten",
    }
    for raw, expected in cases.items():
        got = events.slugify(raw)
        assert got == expected, f"{raw!r} -> {got!r}, erwartet {expected!r}"
        # Egal was reinkommt: das Ergebnis muss als Ordnername sicher sein.
        assert events.is_safe_event(f"2026-10-15_{got}")


def test_slugify_caps_length():
    assert len(events.slugify("x" * 200)) <= 40
