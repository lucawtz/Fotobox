"""Gaeste sehen nur das laufende Event (P2-17).

`is_safe_event` prueft ausschliesslich Pfad-Traversal, nicht Zugehoerigkeit —
vorher lieferten `/api/photos`, `/api/events` und `/api/download-zip` alles von
der Platte, und ein Direktlink auf `/img/<altes-event>/...` kam ebenfalls durch.
Im Fotobox-WLAN sah damit jeder Gast die Fotos der letzten Feier.

Eigene Datei statt Ergaenzung von test_server.py, weil dort parallel gearbeitet
wird.
"""
import os

import pytest

import config
import events
import gallery_server


@pytest.fixture
def app(cfg, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "config.json"))
    for k in ("picture_dir", "thumbnail_dir", "admin_pin", "host_pin"):
        monkeypatch.setitem(config.cfg, k, cfg[k])
    # Altersloeschung aus dem Weg raeumen: sie soll hier nichts wegputzen.
    monkeypatch.setitem(config.cfg, "photo_max_age_days", 0)
    monkeypatch.setitem(config.cfg, "gallery_guests_see_all", False)
    monkeypatch.setattr(gallery_server, "_bind_all", False)
    return gallery_server.app.test_client()


@pytest.fixture
def two_events(photo_factory):
    """Aktives Event und eine vergangene Feier, je ein echtes JPEG."""
    base = config.cfg["picture_dir"]
    active = events.current_event_folder(config.cfg)
    old = "2020-01-01_alte-feier"
    photo_factory(os.path.join(base, active, "jetzt.jpg"))
    photo_factory(os.path.join(base, old, "damals.jpg"))
    return active, old


def _login(client, role="admin"):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
        sess["role"] = role
    return client


# ── Gast ───────────────────────────────────────────────────────────────────────

def test_guest_photos_only_from_active_event(app, two_events):
    active, old = two_events
    seen = {p["event"] for p in app.get("/api/photos").get_json()["photos"]}
    assert seen == {active}


def test_guest_event_list_hides_past_parties(app, two_events):
    active, old = two_events
    folders = [e["folder"] for e in app.get("/api/events").get_json()["events"]]
    assert folders == [active]


def test_guest_cannot_filter_into_a_foreign_event(app, two_events):
    """Der ?event=-Parameter darf kein Schlupfloch sein."""
    active, old = two_events
    body = app.get(f"/api/photos?event={old}").get_json()
    assert body["photos"] == []
    assert body["count"] == 0


@pytest.mark.parametrize("route", ["img", "thumb", "preview", "download"])
def test_guest_direct_link_into_old_event_is_404(app, two_events, route):
    """Ohne diese Sperre waere die Filterung reine Fassade."""
    active, old = two_events
    assert app.get(f"/{route}/{old}/damals.jpg").status_code == 404


@pytest.mark.parametrize("route", ["img", "thumb", "preview", "download"])
def test_guest_reaches_the_active_event(app, two_events, route):
    active, old = two_events
    assert app.get(f"/{route}/{active}/jetzt.jpg").status_code == 200


def test_guest_zip_of_foreign_event_is_refused(app, two_events):
    active, old = two_events
    assert app.get(f"/api/download-zip?event={old}").status_code == 404


def test_guest_zip_of_active_event_works(app, two_events):
    active, old = two_events
    assert app.get(f"/api/download-zip?event={active}").status_code == 200


def test_guest_count_is_scoped(app, two_events):
    assert app.get("/api/count").get_json()["count"] == 1


def test_served_photos_are_not_publicly_cacheable(app, two_events):
    """Die Antwort haengt jetzt an der Session — ein geteilter Cache darf sie
    nicht an den naechsten Gast weiterreichen."""
    active, _ = two_events
    cc = app.get(f"/img/{active}/jetzt.jpg").headers["Cache-Control"]
    assert "public" not in cc
    assert "private" in cc


# ── Angemeldete Rollen ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("role", ["admin", "host"])
def test_logged_in_roles_see_every_event(app, two_events, role):
    active, old = two_events
    _login(app, role)
    seen = {p["event"] for p in app.get("/api/photos").get_json()["photos"]}
    assert seen == {active, old}


@pytest.mark.parametrize("role", ["admin", "host"])
def test_logged_in_roles_reach_old_photos(app, two_events, role):
    active, old = two_events
    _login(app, role)
    assert app.get(f"/img/{old}/damals.jpg").status_code == 200


# ── Owner-Schalter ─────────────────────────────────────────────────────────────

def test_owner_can_open_the_archive(app, two_events, monkeypatch):
    active, old = two_events
    monkeypatch.setitem(config.cfg, "gallery_guests_see_all", True)
    seen = {p["event"] for p in app.get("/api/photos").get_json()["photos"]}
    assert seen == {active, old}
    assert app.get(f"/img/{old}/damals.jpg").status_code == 200


# ── Regression ─────────────────────────────────────────────────────────────────

def test_internal_photo_list_still_sees_everything(app, two_events):
    """Cleanup, Prewarm und Admin-Uebersicht duerfen NICHT gefiltert werden —
    sonst raeumt die Altersloeschung vergangene Events nie wieder auf."""
    active, old = two_events
    seen = {ev for ev, _ in gallery_server._photo_list()}
    assert seen == {active, old}
