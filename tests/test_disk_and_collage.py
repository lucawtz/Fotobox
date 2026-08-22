"""Aufräum-Logik und Collage.

`disk_monitor` löscht Nutzerdaten. Ein Fehler hier ist unwiderruflich — die
Fotos einer Feier gibt es kein zweites Mal.
"""
import os
import time

import pytest

import collage
import disk_monitor


def _age(path, days):
    old = time.time() - days * 86400
    os.utime(path, (old, old))


def test_get_free_mb_returns_minus_one_on_error():
    """0 sah aus wie eine volle Platte und haette die Aufnahme blockiert."""
    assert disk_monitor.get_free_mb("/gibt/es/wirklich/nicht") == -1


def test_get_free_mb_on_real_path(tmp_path):
    assert disk_monitor.get_free_mb(str(tmp_path)) > 0


def test_enforce_photo_max_age_deletes_only_old(cfg, photo_factory):
    ev = os.path.join(cfg["picture_dir"], "2026-10-15_test")
    alt = photo_factory(os.path.join(ev, "alt.jpg"))
    neu = photo_factory(os.path.join(ev, "neu.jpg"))
    _age(alt, 30)

    disk_monitor.enforce_photo_max_age(cfg["picture_dir"], 7)
    assert not os.path.exists(alt)
    assert os.path.exists(neu)


def test_enforce_photo_max_age_disabled_with_zero(cfg, photo_factory):
    ev = os.path.join(cfg["picture_dir"], "2026-10-15_test")
    alt = photo_factory(os.path.join(ev, "alt.jpg"))
    _age(alt, 400)
    disk_monitor.enforce_photo_max_age(cfg["picture_dir"], 0)
    assert os.path.exists(alt), "0 muss die Altersloeschung abschalten"


def test_enforce_max_photos_is_per_event(cfg, photo_factory):
    """Sonst verdraengen die Fotos einer neuen Vermietung die der vorigen."""
    alt_ev = os.path.join(cfg["picture_dir"], "2026-09-01_alt")
    neu_ev = os.path.join(cfg["picture_dir"], "2026-10-15_neu")
    alt = [photo_factory(os.path.join(alt_ev, f"a{i}.jpg")) for i in range(5)]
    neu = [photo_factory(os.path.join(neu_ev, f"n{i}.jpg")) for i in range(5)]
    for i, p in enumerate(neu):
        _age(p, 0)
        os.utime(p, (time.time() + i, time.time() + i))

    disk_monitor.enforce_max_photos(cfg["picture_dir"], 3, event_dir=neu_ev)

    assert all(os.path.exists(p) for p in alt), "fremdes Event angefasst"
    assert sum(os.path.exists(p) for p in neu) == 3


def test_enforce_max_photos_keeps_the_newest(cfg, photo_factory):
    ev = os.path.join(cfg["picture_dir"], "2026-10-15_test")
    paths = []
    for i in range(5):
        p = photo_factory(os.path.join(ev, f"f{i}.jpg"))
        os.utime(p, (time.time() - (5 - i) * 60,) * 2)
        paths.append(p)

    disk_monitor.enforce_max_photos(cfg["picture_dir"], 2, event_dir=ev)
    survivors = [os.path.basename(p) for p in paths if os.path.exists(p)]
    assert survivors == ["f3.jpg", "f4.jpg"]


def test_cleanup_old_thumbnails(cfg, photo_factory):
    td = cfg["thumbnail_dir"]
    alt = photo_factory(os.path.join(td, "2026-01-01_x", "alt.jpg"))
    neu = photo_factory(os.path.join(td, "2026-10-15_y", "neu.jpg"))
    _age(alt, 90)
    disk_monitor.cleanup_old_thumbnails(td, 30)
    assert not os.path.exists(alt)
    assert os.path.exists(neu)


def test_cleanup_handles_missing_dir():
    disk_monitor.cleanup_old_thumbnails("/gibt/es/nicht", 30)   # darf nicht werfen


# ── Collage ────────────────────────────────────────────────────────────────────

def test_make_collage_produces_square_grid(cfg, photo_factory, tmp_path):
    shots = [photo_factory(str(tmp_path / f"s{i}.jpg"), size=(1200, 800),
                           color=(50 * i, 40, 60))
             for i in range(4)]
    out = collage.make_collage(shots, cfg["picture_dir"])
    assert out and os.path.isfile(out)

    from PIL import Image
    with Image.open(out) as im:
        assert im.width > 0 and im.height > 0
        # Vier Kacheln: die Quadranten duerfen nicht alle gleich aussehen
        w, h = im.size
        quads = [im.crop(b).resize((1, 1)).getpixel((0, 0)) for b in
                 ((0, 0, w // 2, h // 2), (w // 2, 0, w, h // 2),
                  (0, h // 2, w // 2, h), (w // 2, h // 2, w, h))]
        assert len(set(quads)) > 1, "alle Quadranten identisch — Collage falsch gebaut"


def test_make_collage_lands_in_target_dir(cfg, photo_factory, tmp_path):
    shots = [photo_factory(str(tmp_path / f"s{i}.jpg")) for i in range(4)]
    out = collage.make_collage(shots, cfg["picture_dir"])
    assert os.path.dirname(os.path.abspath(out)) == os.path.abspath(cfg["picture_dir"])
