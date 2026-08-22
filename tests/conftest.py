"""Gemeinsame Fixtures.

Wichtig: `config` wird beim Import ausgewertet (`cfg = load_config()`), und
mehrere Module halten Referenzen auf `config.cfg`. Die Fixtures biegen deshalb
`config.CONFIG_PATH` und die Verzeichnisse auf ein tmp_path um, statt ein
frisches Modul zu importieren.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """Isolierte Konfiguration mit eigenen Verzeichnissen unter tmp_path."""
    import config

    monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "config.json"))
    data = config.load_config()
    data["picture_dir"] = str(tmp_path / "Picture_Box")
    data["thumbnail_dir"] = str(tmp_path / "thumbnails")
    os.makedirs(data["picture_dir"], exist_ok=True)
    os.makedirs(data["thumbnail_dir"], exist_ok=True)
    return data


@pytest.fixture
def photo_factory():
    """Erzeugt echte JPEGs — die Bildpfade arbeiten mit Pillow, nicht mit Stubs."""
    from PIL import Image

    def make(path, size=(800, 600), color=(120, 90, 60)):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        Image.new("RGB", size, color).save(path, "JPEG")
        return path

    return make
