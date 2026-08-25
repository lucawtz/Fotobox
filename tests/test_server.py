"""Galerie-Server: Routing, Löschen, Rollentrennung, Bind-Entscheidung."""
import os
import time

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
    # Bewusst das LAUFENDE Event: /thumb und /preview sind seit _may_see_event()
    # fuer Gaeste auf das aktive Event beschraenkt, ein fremdes Datum liefert 404.
    import events
    ev, fn = events.current_event_folder(config.cfg), "foto.jpg"
    orig = photo_factory(os.path.join(cfg["picture_dir"], ev, fn), size=(2000, 1500))
    # Angemeldet, weil `ev` nicht das laufende Event ist: seit P2-17 kommen
    # Gaeste dort nicht mehr an Bilder. Hier geht es um das Aufraeumen von
    # Thumbnail und Preview beim Loeschen, nicht um die Sichtbarkeit.
    _login(app)
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
    import events
    ev, fn = events.current_event_folder(config.cfg), "foto.jpg"
    orig = photo_factory(os.path.join(cfg["picture_dir"], ev, fn))
    r = app.post(f"/api/delete/{ev}/{fn}", data={"pin": "0815"})
    assert r.status_code == 403
    assert os.path.exists(orig)


def test_delete_rejects_traversal(app):
    r = app.post("/api/delete/..%2f../foto.jpg", data={"pin": "1234"})
    assert r.status_code in (403, 404)


# ── Neues Event starten ────────────────────────────────────────────────────────

def test_new_event_is_admin_only(app):
    """Der Gastgeber sieht nur das laufende Event — er darf es nicht wechseln,
    sonst sperrt er sich selbst von seinen eigenen Fotos aus."""
    assert app.post("/api/admin/event/new").status_code == 401
    assert _login(app, "host").post("/api/admin/event/new").status_code == 403
    assert _login(app, "admin").post("/api/admin/event/new").status_code == 200


def test_new_event_starts_fresh_folder_without_touching_photos(app, cfg, photo_factory):
    """Trennt eine Vermietung ueber mehrere Tage, die `event_session_hours`
    sonst je nach Pause im selben Ordner laesst."""
    import events
    first = events.current_event_folder(config.cfg)
    foto = photo_factory(os.path.join(cfg["picture_dir"], first, "foto.jpg"))

    body = _login(app).post("/api/admin/event/new").get_json()

    assert body["previous"] == first
    assert body["folder"] != first, "Ordner blieb derselbe — Aktion wirkungslos"
    assert events.current_event_folder(config.cfg) == body["folder"]
    assert os.path.isfile(foto), "Fotos des alten Events wurden angefasst"


# ── Uebergabe an den naechsten Gastgeber ───────────────────────────────────────

def test_handover_is_admin_only(app):
    assert app.post("/api/admin/handover",
                    json={"branding": True}).status_code == 401
    assert _login(app, "host").post("/api/admin/handover",
                                    json={"branding": True}).status_code == 403


def test_handover_rejects_empty_selection(app):
    """Ohne Haken passiert nichts — dann soll die Antwort das auch sagen,
    statt Erfolg zu melden."""
    assert _login(app).post("/api/admin/handover", json={}).status_code == 400


def test_handover_resets_branding_but_keeps_wifi_and_pins(app, cfg, monkeypatch):
    for key, value in (("event_name", "Lisa und Tom"),
                       ("subtitle", "Wir heiraten"),
                       ("theme", {"accent": "#FF0000"}),
                       ("wifi_password", "vom-vormieter")):
        monkeypatch.setitem(config.cfg, key, value)

    assert _login(app).post("/api/admin/handover",
                            json={"branding": True}).status_code == 200

    for key in config.HANDOVER_FIELDS:
        assert config.cfg[key] == config.default_value(key), key
    # WLAN und PINs vergibt der Box-Besitzer selbst: ein Reset wuerde hier
    # wieder "fotobox123" bzw. "1234" hinschreiben.
    assert config.cfg["wifi_password"] == "vom-vormieter"
    assert config.cfg["admin_pin"] == cfg["admin_pin"]


def test_handover_removes_only_the_tenant_logo(app, tmp_path, monkeypatch):
    """Geloescht wird `Layout/logo.png` — dorthin schreibt jeder Upload.
    `logo_default.png` ist der Besitzer-Standard, auf den ui._load_logo
    zurueckfaellt, und muss liegen bleiben."""
    layout = tmp_path / "Layout"
    layout.mkdir()
    (layout / "logo.png").write_bytes(b"mieter")
    (layout / "logo_default.png").write_bytes(b"besitzer")
    monkeypatch.setattr(config, "BASE_DIR", str(tmp_path))
    monkeypatch.setitem(config.cfg, "logo_path", str(layout / "logo.png"))

    assert _login(app).post("/api/admin/handover",
                            json={"logo": True}).status_code == 200

    assert not (layout / "logo.png").exists()
    assert (layout / "logo_default.png").exists(), "Besitzer-Logo mitgeloescht"


def test_handover_photos_need_the_typed_confirmation(app, cfg, photo_factory):
    import events
    ev = events.current_event_folder(config.cfg)
    foto = photo_factory(os.path.join(cfg["picture_dir"], ev, "foto.jpg"))

    r = _login(app).post("/api/admin/handover", json={"photos": True})

    assert r.status_code == 400
    assert os.path.isfile(foto)


def test_handover_clears_photos_and_repins_the_event(app, cfg, photo_factory):
    import events
    old = events.current_event_folder(config.cfg)
    foto = photo_factory(os.path.join(cfg["picture_dir"], old, "foto.jpg"))
    client = _login(app)
    client.get(f"/thumb/{old}/foto.jpg")
    thumb = os.path.join(gallery_server._thumb_dir(), old, "foto.jpg")
    assert os.path.isfile(thumb), "Vorbedingung: Thumbnail wurde erzeugt"

    body = client.post("/api/admin/handover",
                       json={"photos": True, "new_event": True,
                             "confirm": "LOESCHEN"}).get_json()

    assert body["removed"] == 1
    assert not os.path.exists(foto)
    assert not os.path.exists(thumb)
    # Der Pin darf nicht auf den gerade weggeraeumten Ordner zeigen.
    assert events.current_event_folder(config.cfg) == body["folder"]


# ── WLAN-Validierung (P1-12) ───────────────────────────────────────────────────

@pytest.mark.parametrize("pw,ok", [
    # Leer ist erlaubt und heisst "offenes Netz": am Eventabend ist das
    # Abtippen des Passworts die Huerde, an der Gaeste haengenbleiben.
    ("", True),
    # 1 bis 7 Zeichen bleiben verboten. Das ist immer ein Versehen — der AP
    # kaeme mit WPA2 gar nicht hoch, und ihn stattdessen stillschweigend
    # offen aufzuspannen waere die schlechteste Antwort darauf.
    ("kurz", False), ("1234567", False),
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
    for key in ("admin_pin", "host_pin", "wifi_password"):
        monkeypatch.setitem(config.cfg, key, config.default_value(key))
    body = _login(app).get("/api/admin/config").get_json()
    assert set(body["insecure_defaults"]) == {"Admin-PIN", "Gastgeber-PIN", "WLAN-Passwort"}

    monkeypatch.setitem(config.cfg, "admin_pin", "847193")
    body = _login(app).get("/api/admin/config").get_json()
    assert "Admin-PIN" not in body["insecure_defaults"]


def test_pin_from_an_older_config_is_flagged_as_too_short(app, monkeypatch):
    """Vierstellige PINs aus einer config.json von vor `PIN_MIN_LEN` gelten
    beim Login weiter — ein Update darf den Besitzer nicht aussperren. Die
    Warnung muss sie trotzdem nennen, sonst faellt es nie auf."""
    monkeypatch.setitem(config.cfg, "admin_pin", "1234")
    body = _login(app).get("/api/admin/config").get_json()
    assert "Admin-PIN (zu kurz)" in body["insecure_defaults"]


# ── PIN-Länge ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("pin,accepted", [
    ("12345",         False),      # eine Stelle zu wenig
    ("123456",        True),
    ("123456789012",  True),       # Maximum
    ("1234567890123", False),
])
def test_pin_length_is_enforced(app, pin, accepted):
    r = _login(app).post("/api/admin/config", json={"admin_pin": pin})
    assert (r.status_code == 200) is accepted
    if accepted:
        assert config.cfg["admin_pin"] == pin


def test_empty_host_pin_still_disables_host_login(app):
    """Leer heisst 'Gastgeber-Login aus' und darf nicht an der Mindestlaenge
    haengenbleiben. Der Admin-PIN darf dagegen nie leer werden."""
    c = _login(app)
    assert c.post("/api/admin/config", json={"host_pin": ""}).status_code == 200
    assert config.cfg["host_pin"] == ""
    assert c.post("/api/admin/config", json={"admin_pin": ""}).status_code == 400


# ── /go/-Kurzlinks ─────────────────────────────────────────────────────────────
#
# Der Boxbildschirm ist kein Touchscreen: die Mini-QR-Codes in der Sidebar
# (ui.py) sind der einzige Weg vom Screen aufs Handy. Sie zeigen auf diese
# Route statt auf die nackte Ziel-URL, weil hotspot.py per 'address=/#/<ip>'
# jede DNS-Anfrage auf die Box umbiegt.

@pytest.fixture
def links(monkeypatch):
    monkeypatch.setitem(config.cfg, "booking_url", "https://example.com/buchen")
    monkeypatch.setitem(config.cfg, "booking_label", "Fotobox mieten")
    monkeypatch.setitem(config.cfg, "instagram_url", "https://instagram.com/foo")


def test_go_termin_renders_target_and_label(app, links):
    r = app.get("/go/termin")
    assert r.status_code == 200
    assert "html" in r.content_type
    body = r.data.decode()
    assert "https://example.com/buchen" in body
    assert "Fotobox mieten" in body
    # Die Seite muss den Gast auch ohne Internet abholen koennen — der
    # Erklaertext ist der ganze Punkt der Route.
    assert "das hat kein Internet" in body
    # Und sie muss den echten Netznamen nennen, nicht "Fotobox-WLAN":
    # der Mieter darf die SSID aendern.
    assert config.cfg["wifi_ssid"] in body


def test_go_instagram_uses_fallback_label(app, links):
    body = app.get("/go/instagram").data.decode()
    assert "https://instagram.com/foo" in body
    assert "<title>Instagram</title>" in body


def test_go_instagram_shows_handle_not_domain(app, links):
    """Unter der Ueberschrift steht, wohin der Tap fuehrt. "@foo" sagt dem
    Gast mehr als "instagram.com", das direkt darueber schon steht."""
    body = app.get("/go/instagram").data.decode()
    assert '<p class="host">@foo</p>' in body


def test_go_termin_shows_domain(app, links):
    """Fuer alles ausser Instagram bleibt es bei der Domain — sie ist das
    Einzige, woran der Gast erkennt, wo er gleich landet."""
    assert '<p class="host">example.com</p>' in app.get("/go/termin").data.decode()


def test_go_instagram_offers_app_links(app, links):
    """Der Follow-Tap passiert in der App, nicht auf der Login-Wand von
    instagram.com — also muss die Seite beide App-Schemata mitliefern."""
    body = app.get("/go/instagram").data.decode()
    assert "instagram://user?username=foo" in body
    assert "intent://instagram.com/_u/foo" in body
    assert "package=com.instagram.android" in body
    # Ohne App muss Chrome von selbst auf die Web-URL zurueckfallen koennen.
    assert "S.browser_fallback_url=https%3A%2F%2Finstagram.com%2Ffoo" in body


def test_go_termin_has_no_app_link(app, links):
    """Fuer eine beliebige Buchungsseite gibt es keine App — die Seite darf
    dann nicht in den iOS-Zweig laufen und auf ein totes Schema warten."""
    assert "var app = {};" in app.get("/go/termin").data.decode()


@pytest.mark.parametrize("url", [
    "https://instagram.com/explore/tags/fotobox",   # kein Profil
    "https://instagram.com/",                       # ohne Handle
    "https://example.com/instagram.com/foo",        # fremde Domain
])
def test_go_instagram_app_link_only_for_profiles(app, monkeypatch, url):
    monkeypatch.setitem(config.cfg, "instagram_url", url)
    body = app.get("/go/instagram").data.decode()
    assert "instagram://" not in body
    assert "var app = {};" in body


def test_go_is_not_cached(app, links):
    # Sonst zeigt das Handy nach einer Config-Aenderung noch die alte URL.
    assert app.get("/go/termin").headers["Cache-Control"] == "no-store"


def test_go_unknown_slug_redirects_home(app, links):
    r = app.get("/go/gibtsnicht")
    assert r.status_code == 302
    assert r.headers["Location"] == "/"


def test_go_unconfigured_link_redirects_home(app, monkeypatch):
    monkeypatch.setitem(config.cfg, "booking_url", "")
    assert app.get("/go/termin").status_code == 302


@pytest.mark.parametrize("bad", [
    "javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "example.com/buchen",          # ohne Schema — waere ein relativer Link
])
def test_go_rejects_non_http_urls(app, monkeypatch, bad):
    """Der Wert kommt aus der Owner-Config, landet aber in href und JS."""
    monkeypatch.setitem(config.cfg, "booking_url", bad)
    r = app.get("/go/termin")
    assert r.status_code == 302
    assert bad not in r.data.decode()


def test_go_escapes_target(app, monkeypatch):
    monkeypatch.setitem(config.cfg, "booking_url",
                        'https://example.com/"><script>alert(1)</script>')
    body = app.get("/go/termin").data.decode()
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body


@pytest.mark.parametrize("endpoint", ["/api/events", "/api/photos"])
def test_public_api_exposes_owner_links(app, links, endpoint):
    """Die Galerie-Seite braucht sie fuer den CTA (OwnerLinks.tsx) — der Gast
    hat das Handy dort ohnehin schon in der Hand."""
    data = app.get(endpoint).get_json()
    assert data["booking_url"] == "https://example.com/buchen"
    assert data["booking_label"] == "Fotobox mieten"
    assert data["instagram_url"] == "https://instagram.com/foo"


# ── Testdruck ──────────────────────────────────────────────────────────────────

def test_print_test_is_admin_only(app, monkeypatch):
    import printing
    monkeypatch.setattr(printing, "print_test", lambda cfg: (True, "Testseite wird gedruckt"))
    monkeypatch.setattr(gallery_server, "_last_test_print", None)
    assert app.post("/api/admin/print-test").status_code == 401
    assert _login(app, "host").post("/api/admin/print-test").status_code == 403
    assert _login(app, "admin").post("/api/admin/print-test").status_code == 200


def test_print_test_cooldown_blocks_second_sheet(app, monkeypatch):
    """Doppelklick oder zweiter Tab darf kein zweites Blatt ziehen."""
    import printing
    calls = []
    monkeypatch.setattr(printing, "print_test",
                        lambda cfg: (calls.append(cfg) or (True, "Testseite wird gedruckt")))
    monkeypatch.setattr(gallery_server, "_last_test_print", None)
    client = _login(app)

    assert client.post("/api/admin/print-test").get_json()["ok"] is True
    second = client.post("/api/admin/print-test")
    assert second.status_code == 429
    assert len(calls) == 1


def test_failed_print_test_allows_immediate_retry(app, monkeypatch):
    """Ein abgelehnter Auftrag verbraucht kein Papier — wer Papier nachlegt,
    soll sofort erneut testen koennen statt 30 s zu warten."""
    import printing
    monkeypatch.setattr(printing, "print_test", lambda cfg: (False, "Kein Papier"))
    monkeypatch.setattr(gallery_server, "_last_test_print", None)
    client = _login(app)

    first = client.post("/api/admin/print-test")
    assert first.status_code == 200
    assert first.get_json() == {"ok": False, "message": None, "error": "Kein Papier"}
    assert client.post("/api/admin/print-test").status_code == 200


def test_first_test_print_after_boot_is_not_blocked(app, monkeypatch):
    """`time.monotonic()` zaehlt ab Systemstart. Mit 0.0 als "noch nie
    gedruckt" lief der erste Testdruck auf einer frisch gebooteten Box in die
    Sperre — genau in dem Moment, in dem man den Drucker pruefen will."""
    import printing
    monkeypatch.setattr(printing, "print_test", lambda cfg: (True, "Testseite wird gedruckt"))
    monkeypatch.setattr(gallery_server, "_last_test_print", None)
    monkeypatch.setattr(gallery_server.time, "monotonic", lambda: 3.0)
    assert _login(app).post("/api/admin/print-test").status_code == 200


def test_concurrent_test_prints_pull_one_sheet(app, monkeypatch):
    """Zwei gleichzeitige Anfragen (Doppelklick auf einem Thread-Server) duerfen
    nicht beide durch die Zeitpruefung rutschen, bevor der Stempel steht."""
    import printing
    import threading
    started = threading.Event()
    calls = []

    def slow_print(cfg):
        calls.append(cfg)
        started.set()
        time.sleep(0.2)          # Fenster, in dem der zweite Klick ankommt
        return True, "Testseite wird gedruckt"

    monkeypatch.setattr(printing, "print_test", slow_print)
    monkeypatch.setattr(gallery_server, "_last_test_print", None)
    client = _login(app)

    codes = []
    first = threading.Thread(
        target=lambda: codes.append(client.post("/api/admin/print-test").status_code))
    first.start()
    assert started.wait(2), "erster Testdruck startete nicht"
    codes.append(client.post("/api/admin/print-test").status_code)
    first.join()

    assert len(calls) == 1, "zwei Blatt statt einem"
    assert sorted(codes) == [200, 429]
