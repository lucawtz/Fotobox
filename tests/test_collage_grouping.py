"""Collage-Gruppierung: Namenskonvention, Zuordnung und Galerie-Filter.

Vor dieser Konvention lagen nach einer Collage fuenf gleichberechtigte Dateien
im Event-Ordner — vier `foto_*.jpg` und ein `collage_*.jpg`. Weder Galerie noch
ZIP konnten erkennen, dass die vier zusammen genau das fuenfte ergeben.
"""
import os

import pytest
from PIL import Image

import collage
import config
import gallery_server


# ── Namenskonvention ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,kind,group", [
    ("collage_1755861234567.jpg",    collage.KIND_COLLAGE, "1755861234567"),
    ("collage_1755861234567_1.jpg",  collage.KIND_MEMBER,  "1755861234567"),
    ("collage_1755861234567_4.jpg",  collage.KIND_MEMBER,  "1755861234567"),
    ("foto_1755861234567.jpg",       collage.KIND_SINGLE,  None),
    ("IMG_0042.JPG",                 collage.KIND_SINGLE,  None),
    # Kein Zahlen-Suffix -> keine Gruppe. Sonst wuerde ein manuell abgelegtes
    # "collage_urlaub.jpg" als Collage durchgehen und die Gruppe waere Muell.
    ("collage_urlaub.jpg",           collage.KIND_SINGLE,  None),
])
def test_classify(name, kind, group):
    assert collage.classify(name) == (kind, group)


def test_classify_ignores_the_directory(tmp_path):
    nested = str(tmp_path / "2026-08-22" / "collage_123_2.jpg")
    assert collage.classify(nested) == (collage.KIND_MEMBER, "123")


# ── Zuordnung beim Bauen ───────────────────────────────────────────────────────

@pytest.fixture
def shots(tmp_path):
    out = []
    for i in range(4):
        p = tmp_path / f"foto_{i}.jpg"
        Image.new("RGB", (400, 300), (40 * i, 90, 160)).save(p, "JPEG")
        out.append(str(p))
    return out


def test_members_are_renamed_into_the_collage_group(shots, tmp_path):
    result = collage.make_collage(shots, str(tmp_path))

    _, group = collage.classify(result)
    assert group, "die Collage selbst muss eine Gruppe haben"

    names = sorted(f for f in os.listdir(tmp_path) if f.endswith(".jpg"))
    assert names == sorted([
        os.path.basename(result),
        *(collage.member_name(group, i, ".jpg") for i in range(1, 5)),
    ])


def test_all_five_files_share_one_group(shots, tmp_path):
    result = collage.make_collage(shots, str(tmp_path))
    groups = {collage.classify(f)[1] for f in os.listdir(tmp_path)
              if f.endswith(".jpg")}
    assert len(groups) == 1, f"Collage und Mitglieder muessen zusammengehoeren: {groups}"


def test_kinds_after_a_collage(shots, tmp_path):
    collage.make_collage(shots, str(tmp_path))
    kinds = [collage.classify(f)[0] for f in sorted(os.listdir(tmp_path))
             if f.endswith(".jpg")]
    assert kinds.count(collage.KIND_COLLAGE) == 1
    assert kinds.count(collage.KIND_MEMBER) == 4


def test_originals_survive_when_the_build_fails(tmp_path):
    """Erst speichern, dann umbenennen — sonst waeren die Aufnahmen weg."""
    broken = str(tmp_path / "kaputt.jpg")
    open(broken, "w").write("kein JPEG")
    others = []
    for i in range(3):
        p = tmp_path / f"foto_{i}.jpg"
        Image.new("RGB", (400, 300), (0, 0, 0)).save(p, "JPEG")
        others.append(str(p))

    with pytest.raises(Exception):
        collage.make_collage([broken, *others], str(tmp_path))

    for p in others:
        assert os.path.isfile(p), "unbeteiligte Aufnahmen duerfen nicht verschwinden"


# ── Filter-Praedikat ───────────────────────────────────────────────────────────

ALL_KINDS = [collage.KIND_COLLAGE, collage.KIND_MEMBER, collage.KIND_SINGLE]


def test_default_view_folds_members_into_their_collage():
    keep = gallery_server._kind_predicate(None)
    assert [k for k in ALL_KINDS if keep(k)] == \
        [collage.KIND_COLLAGE, collage.KIND_SINGLE]


def test_collage_filter_shows_only_finished_collages():
    keep = gallery_server._kind_predicate("collage")
    assert [k for k in ALL_KINDS if keep(k)] == [collage.KIND_COLLAGE]


def test_single_filter_includes_the_shots_a_collage_is_made_of():
    """Sonst kaeme der Gast nie an seine Rohbilder."""
    keep = gallery_server._kind_predicate("single")
    assert [k for k in ALL_KINDS if keep(k)] == \
        [collage.KIND_MEMBER, collage.KIND_SINGLE]


# ── API ────────────────────────────────────────────────────────────────────────

@pytest.fixture
def app(cfg, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "config.json"))
    for k in ("picture_dir", "thumbnail_dir"):
        monkeypatch.setitem(config.cfg, k, cfg[k])
    monkeypatch.setattr(gallery_server, "_bind_all", False)
    client = gallery_server.app.test_client()
    # Als Admin: sonst greift _may_see_all_events und das Testevent ist
    # unsichtbar, weil es nicht das laufende ist.
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
        sess["role"] = "admin"
    return client


@pytest.fixture
def event_with_collage(cfg):
    """Ein Event mit einem echten Einzelfoto und einer Collage aus vier Shots."""
    ev = os.path.join(cfg["picture_dir"], "2026-08-22_test")
    os.makedirs(ev, exist_ok=True)
    Image.new("RGB", (400, 300), (10, 20, 30)).save(
        os.path.join(ev, "foto_1755861111111.jpg"), "JPEG")
    shots = []
    for i in range(4):
        p = os.path.join(ev, f"foto_17558612222{i}2.jpg")
        Image.new("RGB", (400, 300), (40 * i + 10, 90, 160)).save(p, "JPEG")
        shots.append(p)
    collage.make_collage(shots, ev)
    return "2026-08-22_test"


def test_api_photos_reports_kind_and_group(app, event_with_collage):
    data = app.get(f"/api/photos?event={event_with_collage}").get_json()
    kinds = [p["kind"] for p in data["photos"]]

    assert kinds.count(collage.KIND_COLLAGE) == 1
    assert kinds.count(collage.KIND_MEMBER) == 4
    assert kinds.count(collage.KIND_SINGLE) == 1

    by_kind = {p["kind"]: p for p in data["photos"]}
    assert by_kind[collage.KIND_SINGLE]["group"] is None
    assert by_kind[collage.KIND_COLLAGE]["group"] == by_kind[collage.KIND_MEMBER]["group"]


def test_zip_without_filter_still_contains_everything(app, event_with_collage):
    """Der normale ZIP-Knopf darf keine Bilder unterschlagen."""
    import io
    from zipfile import ZipFile

    res = app.get(f"/api/download-zip?event={event_with_collage}")
    names = ZipFile(io.BytesIO(res.data)).namelist()
    assert len(names) == 6


def test_zip_can_be_narrowed_to_collages(app, event_with_collage):
    import io
    from zipfile import ZipFile

    res = app.get(f"/api/download-zip?event={event_with_collage}&kind=collage")
    names = ZipFile(io.BytesIO(res.data)).namelist()
    assert len(names) == 1
    assert "collage_" in names[0]
    assert "collagen" in res.headers["Content-Disposition"]
