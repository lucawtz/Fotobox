"""Captive-Portal: Popup aufmachen — und den Gast wieder herauslassen.

Das WLAN-Anmeldefenster kann keine Downloads. Wer sich per
/api/captive/release freischaltet, bekommt an den Probe-URLs seines
Betriebssystems ein "online" und landet damit im echten Browser.
"""
import pytest

import config
import gallery_server

GALLERY = "http://192.168.4.1"
PHONE = "192.168.4.23"
OTHER_PHONE = "192.168.4.24"


@pytest.fixture
def app(cfg, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setitem(config.cfg, "gallery_url", GALLERY)
    monkeypatch.setattr(gallery_server, "_bind_all", False)
    # Modulglobaler Freigabe-Speicher — sonst faerbt ein Test auf den
    # naechsten ab.
    monkeypatch.setattr(gallery_server, "_captive_released", {})
    return gallery_server.app.test_client()


def _probe(app, path, host="captive.apple.com", ip=PHONE):
    return app.get(path, base_url=f"http://{host}",
                   environ_base={"REMOTE_ADDR": ip})


# ── Ohne Freigabe: alles landet in der Galerie ─────────────────────────────────

def test_probe_oeffnet_das_popup_mit_der_galerie(app):
    r = _probe(app, "/hotspot-detect.html")
    assert r.status_code == 302
    # Das Flag sagt der SPA, dass sie im Popup steckt (frontend/src/captive.ts).
    assert r.headers["Location"] == f"{GALLERY}/?cna=1"


def test_getippter_hostname_bleibt_ohne_popup_flag(app):
    """apple.com im echten Safari ist kein Popup — dort darf der Hinweis
    'in den Browser wechseln' nicht auftauchen."""
    r = _probe(app, "/irgendwas", host="apple.com")
    assert r.status_code == 302
    assert r.headers["Location"] == f"{GALLERY}/"


def test_aufruf_per_ip_wird_nicht_umgeleitet(app):
    r = app.get("/api/count", base_url=GALLERY,
                environ_base={"REMOTE_ADDR": PHONE})
    assert r.status_code == 200


# ── Nach der Freigabe: das OS sieht "online" ───────────────────────────────────

def _release(app, ip=PHONE):
    r = app.post("/api/captive/release", base_url=GALLERY,
                 environ_base={"REMOTE_ADDR": ip})
    assert r.status_code == 200 and r.get_json()["ok"] is True


def test_apple_probe_bekommt_nach_freigabe_das_success_dokument(app):
    _release(app)
    r = _probe(app, "/hotspot-detect.html")
    assert r.status_code == 200
    # iOS prueft auf genau dieses Dokument; alles andere haelt das WLAN
    # weiter fuer captive und das Popup kommt zurueck.
    assert b"<TITLE>Success</TITLE>" in r.data


def test_android_probe_bekommt_nach_freigabe_204(app):
    _release(app)
    r = _probe(app, "/generate_204", host="connectivitycheck.gstatic.com")
    assert r.status_code == 204
    assert r.data == b""


def test_galerie_bleibt_nach_der_freigabe_ueber_den_hostnamen_erreichbar(app):
    """Nur die Verbindungstests werden durchgewunken — wer 'fotobox.box'
    tippt, soll weiterhin bei den Fotos landen."""
    _release(app)
    r = _probe(app, "/", host="fotobox.box")
    assert r.status_code == 302
    assert r.headers["Location"] == f"{GALLERY}/"


def test_freigabe_gilt_nur_fuer_das_eigene_geraet(app):
    _release(app)
    r = _probe(app, "/hotspot-detect.html", ip=OTHER_PHONE)
    assert r.status_code == 302, "fremdes Handy braucht sein eigenes Popup"


def test_freigabe_laeuft_ab(app, monkeypatch):
    _release(app)
    later = [gallery_server.time.time() + gallery_server._CAPTIVE_RELEASE_TTL_S + 1]
    monkeypatch.setattr(gallery_server.time, "time", lambda: later[0])
    r = _probe(app, "/hotspot-detect.html")
    assert r.status_code == 302


def test_ohne_erkennbare_adresse_wird_niemand_freigeschaltet(app):
    """remote_addr fehlt → Sammel-Key 'unknown'. Eine Freigabe darauf wuerde
    fuer jedes Geraet ohne Adresse gelten."""
    r = app.post("/api/captive/release", base_url=GALLERY,
                 environ_base={"REMOTE_ADDR": None})
    assert r.status_code == 200
    r = _probe(app, "/hotspot-detect.html", ip=None)
    assert r.status_code == 302


# ── Der eigene Name darf nicht im Kreis laufen ─────────────────────────────────

NAME = "fotobox.internal"


@pytest.fixture
def named_app(app, monkeypatch):
    """Galerie unter einem Namen statt unter der IP."""
    monkeypatch.setitem(config.cfg, "hotspot_enabled", True)
    monkeypatch.setitem(config.cfg, "gallery_hostname", NAME)
    monkeypatch.setitem(config.cfg, "gallery_url", f"http://{NAME}")
    return app


def test_eigener_name_wird_nicht_umgeleitet(named_app):
    """Der Kern der Sache: zeigt gallery_url auf einen Namen, ist das
    Redirect-Ziel selbst ein Hostname. Ohne Ausnahme leitet die Box ihn auf
    sich selbst um — und zwar endlos."""
    r = named_app.get("/api/count", base_url=f"http://{NAME}",
                      environ_base={"REMOTE_ADDR": PHONE})
    assert r.status_code == 200


def test_fremder_name_landet_weiterhin_in_der_galerie(named_app):
    r = named_app.get("/irgendwas", base_url="http://apple.com",
                      environ_base={"REMOTE_ADDR": PHONE})
    assert r.status_code == 302
    assert r.headers["Location"] == f"http://{NAME}/"


def test_probe_fuehrt_zum_namen_nicht_zur_ip(named_app):
    """Was der Gast im Anmeldefenster in der Adresszeile liest."""
    r = _probe(named_app, "/hotspot-detect.html")
    assert r.headers["Location"] == f"http://{NAME}/?cna=1"


# ── Portal-Ansage nach RFC 8908 ────────────────────────────────────────────────

def _portal(app, ip=PHONE):
    return app.get("/api/captive/portal", base_url=GALLERY,
                   environ_base={"REMOTE_ADDR": ip})


def test_portal_api_meldet_das_portal(app):
    r = _portal(app)
    assert r.status_code == 200
    # Der Medientyp ist Teil des Vertrags — mit application/json ignorieren
    # die Handys die Antwort.
    assert r.mimetype == "application/captive+json"
    body = r.get_json(force=True)
    assert body["captive"] is True
    assert body["user-portal-url"] == f"{GALLERY}/"


def test_portal_api_traegt_den_namen(named_app):
    assert _portal(named_app).get_json(force=True)["user-portal-url"] == \
        f"http://{NAME}/"


def test_portal_api_nach_freigabe_nicht_mehr_captive(app):
    """Wer gerade aus dem Anmeldefenster herausgegangen ist, darf nicht vom
    naechsten Banner wieder hineingeholt werden."""
    _release(app)
    body = _portal(app).get_json(force=True)
    assert body["captive"] is False
    assert body["seconds-remaining"] == gallery_server._CAPTIVE_RELEASE_TTL_S


def test_portal_api_gilt_je_geraet(app):
    _release(app)
    assert _portal(app, ip=OTHER_PHONE).get_json(force=True)["captive"] is True


# ── Was in der captive.conf landet ─────────────────────────────────────────────

def test_captive_conf_traegt_dns_hijack_und_option_114(monkeypatch):
    import hotspot
    monkeypatch.setitem(config.cfg, "gallery_port", 80)
    conf = hotspot.captive_conf_content("192.168.4.1")
    assert "address=/#/192.168.4.1" in conf
    # Die Option zeigt auf die IP, nicht auf den Namen: der Aufruf ist der
    # erste nach dem Beitritt und darf kein DNS brauchen.
    assert 'dhcp-option=114,"http://192.168.4.1/api/captive/portal"' in conf


def test_captive_conf_kennt_den_ausweichport(monkeypatch):
    """Faellt die Galerie auf 5000 zurueck, muss die Option mitziehen —
    sonst zeigt sie auf einen Port, den niemand bedient."""
    monkeypatch.setitem(config.cfg, "gallery_port", 5000)
    import hotspot
    assert '"http://192.168.4.1:5000/api/captive/portal"' in \
        hotspot.captive_conf_content("192.168.4.1")
