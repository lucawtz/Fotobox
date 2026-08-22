"""Galerie-Server: Routing, Löschen, Rollentrennung, Bind-Entscheidung."""
import os

import pytest

import config
import gallery_server


@pytest.fixture
def app(cfg, monkeypatch, tmp_path):
    """Flask-Testclient mit isolierten Verzeichnissen."""
    monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "config.json"))
    for k in ("picture_dir", "thumbnail_dir", "admin_pin", "host_pin"):
        monkeypatch.setitem(config.cfg, k, cfg[k])
    monkeypatch.setattr(gallery_server, "_bind_all", False)
    return gallery_server.app.test_client()


def _login(client, role="admin"):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
        sess["role"] = role
    return client


# ── SPA-Routing ────────────────────────────────────────────────────────────────

SPA = pytest.mark.skipif(not os.path.isfile(gallery_server.SPA_INDEX),
                         reason="frontend/dist fehlt — 'npm run build' im frontend/")


@SPA
@pytest.mark.parametrize("path", [
    "/",
    "/event/2026-10-15_lisa-und-tom",     # P0-2: lieferte vorher ein nacktes 404
    "/photo/2026-10-15_lisa-und-tom/foto.jpg",
    "/admin",
    "/admin/print",
    "/eine/kuenftige/client-route",
])
def test_client_routes_serve_the_spa(app, path):
    r = app.get(path)
    assert r.status_code == 200
    assert b'<div id="root"' in r.data


def test_unknown_api_returns_json_404(app):
    r = app.get("/api/gibtsnicht")
    assert r.status_code == 404
    assert "json" in r.content_type
    assert r.get_json()["ok"] is False


def test_missing_file_stays_404(app):
    r = app.get("/thumb/2026-10-15_x/nichtda.jpg")
    assert r.status_code == 404
    assert b'<div id="root"' not in r.data


# ── Bind-Entscheidung (P0-1) ───────────────────────────────────────────────────

@pytest.mark.parametrize("bind_all,hotspot_cfg,expected", [
    (True,  True,  "0.0.0.0"),      # Pi im Normalbetrieb
    (False, True,  "127.0.0.1"),    # --no-hotspot trotz aktivierter Config
    (None,  True,  "0.0.0.0"),      # Standalone: Config entscheidet
    (None,  False, "127.0.0.1"),
])
def test_default_host(monkeypatch, bind_all, hotspot_cfg, expected):
    monkeypatch.setattr(gallery_server, "_bind_all", bind_all)
    monkeypatch.setitem(config.cfg, "hotspot_enabled", hotspot_cfg)
    assert gallery_server._default_host() == expected


# ── Löschen (P1-14) ────────────────────────────────────────────────────────────

def test_delete_removes_photo_thumbnail_and_preview(app, cfg, photo_factory):
    ev, fn = "2026-10-15_test", "foto.jpg"
    orig = photo_factory(os.path.join(cfg["picture_dir"], ev, fn), size=(2000, 1500))
    app.get(f"/thumb/{ev}/{fn}")
    app.get(f"/preview/{ev}/{fn}")

    thumb = os.path.join(gallery_server._thumb_dir(), ev, fn)
    preview = os.path.join(gallery_server._preview_dir(), ev, fn)
    assert all(map(os.path.isfile, (orig, thumb, preview)))

    r = app.post(f"/api/delete/{ev}/{fn}", data={"pin": cfg["admin_pin"]})
    assert r.status_code == 200

    assert not os.path.exists(orig)
    assert not os.path.exists(thumb)
    assert not os.path.exists(preview), \
        "Preview blieb liegen — /preview lieferte das geloeschte Foto weiter aus"
    assert app.get(f"/preview/{ev}/{fn}").status_code == 404


def test_delete_needs_correct_pin(app, cfg, photo_factory):
    ev, fn = "2026-10-15_test", "foto.jpg"
    orig = photo_factory(os.path.join(cfg["picture_dir"], ev, fn))
    r = app.post(f"/api/delete/{ev}/{fn}", data={"pin": "0815"})
    assert r.status_code == 403
    assert os.path.exists(orig)


def test_delete_rejects_traversal(app):
    r = app.post("/api/delete/..%2f../foto.jpg", data={"pin": "1234"})
    assert r.status_code in (403, 404)


# ── WLAN-Validierung (P1-12) ───────────────────────────────────────────────────

@pytest.mark.parametrize("pw,ok", [
    ("", False), ("kurz", False), ("1234567", False),
    ("12345678", True), ("x" * 63, True), ("x" * 64, False),
])
def test_wifi_password_length_enforced_server_side(app, pw, ok):
    """Die Client-Pruefung laesst sich per direktem POST umgehen."""
    r = _login(app).post("/api/admin/config",
                         json={"wifi_ssid": "Fotobox", "wifi_password": pw})
    assert (r.status_code == 200) is ok


@pytest.mark.parametrize("ssid,ok", [
    ("F", True), ("A" * 32, True), ("A" * 33, False),
    ("Café-Ümläute", True),
])
def test_wifi_ssid_length_enforced(app, ssid, ok):
    r = _login(app).post("/api/admin/config",
                         json={"wifi_ssid": ssid, "wifi_password": "gueltig123"})
    assert (r.status_code == 200) is ok


def test_invalid_wifi_does_not_corrupt_config(app):
    before = config.cfg["wifi_password"]
    _login(app).post("/api/admin/config",
                     json={"wifi_ssid": "F", "wifi_password": "x"})
    assert config.cfg["wifi_password"] == before


# ── Rollentrennung ─────────────────────────────────────────────────────────────

def test_printers_endpoint_is_admin_only(app):
    assert app.get("/api/admin/printers").status_code == 401
    assert _login(app, "host").get("/api/admin/printers").status_code == 403
    assert _login(app, "admin").get("/api/admin/printers").status_code == 200


def test_host_cannot_change_printer(app):
    _login(app, "admin").post("/api/admin/config", json={
        "wifi_ssid": "F", "wifi_password": "gueltig123", "printer_name": "Selphy"})
    _login(app, "host").post("/api/admin/config", json={
        "wifi_ssid": "F", "wifi_password": "gueltig123", "printer_name": "GEKAPERT"})
    assert config.cfg["printer_name"] == "Selphy"


@pytest.mark.parametrize("value,expected", [(0, 1), (99, 9), (4.7, 4)])
def test_print_copies_clamped(app, value, expected):
    _login(app, "admin").post("/api/admin/config", json={
        "wifi_ssid": "F", "wifi_password": "gueltig123", "print_copies": value})
    assert config.cfg["print_copies"] == expected


def test_invalid_print_mode_ignored(app):
    c = _login(app, "admin")
    c.post("/api/admin/config", json={"wifi_ssid": "F", "wifi_password": "gueltig123",
                                      "print_mode": "fit"})
    c.post("/api/admin/config", json={"wifi_ssid": "F", "wifi_password": "gueltig123",
                                      "print_mode": "unsinn"})
    assert config.cfg["print_mode"] == "fit"


# ── Warnung bei Auslieferungs-PINs (P2-21) ─────────────────────────────────────

def test_insecure_defaults_reported(app, monkeypatch):
    monkeypatch.setitem(config.cfg, "admin_pin", "1234")
    monkeypatch.setitem(config.cfg, "host_pin", "0000")
    monkeypatch.setitem(config.cfg, "wifi_password", "fotobox123")
    body = _login(app).get("/api/admin/config").get_json()
    assert set(body["insecure_defaults"]) == {"Admin-PIN", "Gastgeber-PIN", "WLAN-Passwort"}

    monkeypatch.setitem(config.cfg, "admin_pin", "8471")
    body = _login(app).get("/api/admin/config").get_json()
    assert "Admin-PIN" not in body["insecure_defaults"]
