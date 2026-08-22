"""Config-Persistenz.

Hier sass der Blocker, der die Box unbrauchbar gemacht hat: `hotspot_enabled`
war weder in den persistierten Feldern noch als True voreingestellt, damit
band der Galerie-Server nur auf 127.0.0.1 und kein Gast erreichte die Galerie.
"""
import json

import config


def _reload(monkeypatch, path):
    monkeypatch.setattr(config, "CONFIG_PATH", str(path))
    return config.load_config()


def test_owner_defaults_survive_admin_save(tmp_path, monkeypatch):
    """Der eigentliche Regressionstest fuer P0-1."""
    cfg = _reload(monkeypatch, tmp_path / "config.json")
    assert cfg["hotspot_enabled"] is True, "Hotspot muss ab Werk an sein"

    cfg["event_name"] = "Hochzeit Lisa und Tom"
    config.save_config(cfg)

    back = config.load_config()
    assert back["hotspot_enabled"] is True
    assert back["event_name"] == "Hochzeit Lisa und Tom"
    assert back["gallery_port"] == 80


def test_only_whitelisted_fields_are_written(tmp_path, monkeypatch):
    cfg = _reload(monkeypatch, tmp_path / "config.json")
    cfg["hotspot_enabled"] = False        # Owner-Feld: darf nicht persistieren
    cfg["gallery_port"] = 9999
    cfg["event_name"] = "Test"
    config.save_config(cfg)

    written = set(json.loads((tmp_path / "config.json").read_text(encoding="utf-8")))
    assert written <= config._PERSISTED_FIELDS
    assert "hotspot_enabled" not in written
    assert "gallery_port" not in written

    back = config.load_config()
    assert back["hotspot_enabled"] is True
    assert back["gallery_port"] == 80


def test_box_fields_persist(tmp_path, monkeypatch):
    """Der Druckername ist geraetespezifisch und muss den Neustart ueberleben."""
    cfg = _reload(monkeypatch, tmp_path / "config.json")
    cfg["printer_name"] = "Canon_SELPHY_CP1500"
    cfg["print_copies"] = 2
    cfg["print_mode"] = "fit"
    config.save_config(cfg)

    back = config.load_config()
    assert back["printer_name"] == "Canon_SELPHY_CP1500"
    assert back["print_copies"] == 2
    assert back["print_mode"] == "fit"
    # print_media bleibt Owner-Default, kommt per git pull
    assert back["print_media"] == config._DEFAULTS["print_media"]


def test_corrupt_config_falls_back_to_defaults(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text("{ das ist kein JSON", encoding="utf-8")
    cfg = _reload(monkeypatch, path)
    assert cfg["event_name"] == config._DEFAULTS["event_name"]
    assert cfg["hotspot_enabled"] is True


def test_save_is_atomic_and_leaves_no_tmp(tmp_path, monkeypatch):
    cfg = _reload(monkeypatch, tmp_path / "config.json")
    config.save_config(cfg)
    assert (tmp_path / "config.json").exists()
    assert not list(tmp_path.glob("*.tmp")), "tmp-Datei nicht aufgeraeumt"


def test_logo_path_is_stored_relative(tmp_path, monkeypatch):
    """Sonst waere die config.json nicht zwischen Dev-Rechner und Pi austauschbar."""
    cfg = _reload(monkeypatch, tmp_path / "config.json")
    assert cfg["logo_path"].startswith(config.BASE_DIR)   # absolut zur Laufzeit
    config.save_config(cfg)
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert not saved["logo_path"].startswith("/")
    assert "\\" not in saved["logo_path"]


def test_gallery_url_omits_port_80():
    assert config.build_gallery_url("192.168.4.1", 80) == "http://192.168.4.1"
    assert config.build_gallery_url("192.168.4.1", 5000) == "http://192.168.4.1:5000"
