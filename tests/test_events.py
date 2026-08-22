"""Event-Ordner-Logik.

Kern ist der Mitternachts-Bug: eine Feier von 20:00 bis 02:00 wurde still in
zwei Ordner aufgeteilt — zwei Eintraege in der Galerie, ZIP-Download nur die
halbe Feier, max_photos doppelt so hoch.
"""
import datetime as dt
import os

import pytest

import events


def T(s: str) -> float:
    return dt.datetime.strptime(s, "%Y-%m-%d %H:%M").timestamp()


@pytest.fixture
def at(cfg, monkeypatch):
    """Fragt den aktiven Ordner zu einem bestimmten Zeitpunkt ab."""
    def _at(when: str):
        monkeypatch.setattr(events.time, "time", lambda: T(when))
        return events.current_event_folder(cfg)
    return _at


def test_event_survives_midnight(cfg, at):
    cfg["event_name"] = "Lisa und Tom"
    folders = {
        at("2026-10-15 20:00"),
        at("2026-10-15 23:59"),
        at("2026-10-16 00:01"),
        at("2026-10-16 02:00"),
    }
    assert folders == {"2026-10-15_lisa-und-tom"}, \
        "Feier ueber Mitternacht muss in einem Ordner bleiben"


def test_next_day_starts_new_event(cfg, at):
    cfg["event_name"] = "Lisa und Tom"
    first = at("2026-10-15 20:00")
    later = at("2026-10-16 19:00")          # 23 h spaeter, > event_session_hours
    assert later != first
    assert later == "2026-10-16_lisa-und-tom"


def test_session_window_is_configurable(cfg, at):
    """Am selben Kalendertag heisst der neue Ordner gleich — pruefbar ist
    deshalb nur, ob die Session neu angefangen hat (Pin-Zeitstempel)."""
    cfg["event_name"] = "Test"
    cfg["event_session_hours"] = 2

    at("2026-10-15 20:00")
    started_1 = events._read_pin(cfg)["started"]

    at("2026-10-15 21:30")                       # innerhalb des Fensters
    assert events._read_pin(cfg)["started"] == started_1, "Session wurde erneuert"

    at("2026-10-15 23:00")                       # ausserhalb
    assert events._read_pin(cfg)["started"] > started_1, "Session lief nicht ab"


def test_expired_session_same_day_reuses_folder(cfg, at):
    """Bewusstes Verhalten: laeuft eine Session am selben Tag ab, landen die
    Fotos wieder im gleichen Ordner (gleiches Datum, gleicher Name). Wer
    wirklich trennen will, nimmt start_new_event() — das haengt -2 an."""
    cfg["event_name"] = "Test"
    cfg["event_session_hours"] = 1
    first = at("2026-10-15 10:00")
    assert at("2026-10-15 20:00") == first

    second = events.start_new_event(cfg)
    assert second == first, "ohne existierenden Ordner keine Kollision"


def test_restart_keeps_folder(cfg, at, monkeypatch):
    """systemd startet nach einem Absturz neu — der Ordner darf nicht wechseln."""
    cfg["event_name"] = "Lisa und Tom"
    before = at("2026-10-15 21:00")
    # Prozessneustart: Modulzustand ist weg, nur die Datei bleibt
    import importlib
    importlib.reload(events)
    monkeypatch.setattr(events.time, "time", lambda: T("2026-10-15 21:05"))
    assert events.current_event_folder(cfg) == before


def test_renaming_event_starts_new_folder(cfg, at):
    at("2026-10-15 20:00")
    cfg["event_name"] = "Geburtstag Anna"
    assert at("2026-10-15 21:00") == "2026-10-15_geburtstag-anna"


def test_clock_jumping_backwards_resets(cfg, at):
    """Pi ohne RTC: die Uhr steht nach dem Boot falsch, bis NTP greift."""
    cfg["event_name"] = "Test"
    at("2026-10-15 21:00")
    assert at("2020-01-01 00:00").startswith("2020-01-01")


def test_start_new_event_avoids_collision(cfg, monkeypatch):
    cfg["event_name"] = "Sommerfest"
    monkeypatch.setattr(events.time, "time", lambda: T("2026-10-15 10:00"))
    first = events.current_event_folder(cfg)
    os.makedirs(os.path.join(cfg["picture_dir"], first), exist_ok=True)

    second = events.start_new_event(cfg)
    assert second == first + "-2"
    assert events.current_event_folder(cfg) == second


def test_explicit_when_bypasses_pin(cfg, at):
    """Historische Abfragen duerfen den Pin weder lesen noch setzen."""
    cfg["event_name"] = "Test"
    at("2026-10-15 20:00")
    old = events.current_event_folder(cfg, when=T("2020-05-05 12:00"))
    assert old == "2020-05-05_test"
    # Pin unveraendert
    assert events.current_event_folder(cfg) == "2026-10-15_test"


def test_pin_file_is_not_listed_as_event(cfg, at, photo_factory):
    at("2026-10-15 20:00")
    photo_factory(os.path.join(cfg["picture_dir"], "2026-10-15_test", "a.jpg"))
    folders = [e["folder"] for e in events.list_events(cfg)]
    assert events._PIN_FILE not in folders
    assert folders == ["2026-10-15_test"]


def test_unreadable_pin_falls_back_to_date(cfg, monkeypatch):
    """Kaputte Pin-Datei darf die Box nicht lahmlegen."""
    cfg["event_name"] = "Test"
    with open(os.path.join(cfg["picture_dir"], events._PIN_FILE), "w") as f:
        f.write("kein json")
    monkeypatch.setattr(events.time, "time", lambda: T("2026-10-15 20:00"))
    assert events.current_event_folder(cfg) == "2026-10-15_test"


def test_pin_with_unsafe_folder_is_ignored(cfg, monkeypatch):
    """Manipulierte Pin-Datei darf keinen Pfad-Ausbruch erzeugen."""
    import json
    cfg["event_name"] = "Test"
    with open(os.path.join(cfg["picture_dir"], events._PIN_FILE), "w") as f:
        json.dump({"folder": "../../etc", "slug": "test",
                   "started": T("2026-10-15 19:00")}, f)
    monkeypatch.setattr(events.time, "time", lambda: T("2026-10-15 20:00"))
    got = events.current_event_folder(cfg)
    assert got == "2026-10-15_test"
    assert events.is_safe_event(got)
