import json

import pytest
from test_library import P1, A, FakeProvider, snapshot, track

from spotano.db import Store
from spotano.exporter import Exporter
from spotano.genres import GENRE_VERSION, GenreResolver
from spotano.library import Library
from spotano.paths import atomic_copy, digest, inside


def test_atomic_copy_failure_keeps_old_target(tmp_path):
    source, target = tmp_path / "source.mp3", tmp_path / "target.mp3"
    source.write_bytes(b"new bytes")
    target.write_bytes(b"old bytes")
    with pytest.raises(OSError):
        atomic_copy(source, target, "invalid hash")
    assert target.read_bytes() == b"old bytes"
    assert list(tmp_path.glob("*.part")) == []


def test_genre_cache_avoids_network_and_manual_correction_has_priority(tmp_path, monkeypatch):
    store = Store(tmp_path / "data")
    import time

    with store.connect() as db:
        db.execute(
            "INSERT INTO genre_cache VALUES(?,?,?)",
            ("Artista", json.dumps({"version": GENRE_VERSION, "tags": ["indie rock"]}), time.time()),
        )
    import requests

    monkeypatch.setattr(requests.Session, "get", lambda *a, **kw: pytest.fail("network must not be used"))
    assert GenreResolver(store).resolve({"artist": "Artista", "genres": []}) == "Rock e Metal"
    with store.connect() as db:
        db.execute("INSERT INTO artist_categories VALUES(?,?)", ("artista", "Sertanejo"))
    assert GenreResolver(store).resolve({"artist": "Artista", "genres": []}) == "Sertanejo"


def test_modified_library_file_is_never_overwritten_by_forced_download(tmp_path):
    store = Store(tmp_path / "data")
    store.set_setting("musicbrainz", False)
    store.add_playlist(P1)
    lib = Library(store, FakeProvider(), validator=lambda p: None)
    lib.apply(lib.preview())
    target = inside(lib.music, store.tracks()[0]["path"])
    target.write_bytes(b"external edit")
    result = lib.apply(lib.preview(force=True))
    assert result["failures"]
    assert target.read_bytes() == b"external edit"


def test_export_after_interruption_reuses_already_verified_new_copy(tmp_path):
    store = Store(tmp_path / "data")
    store.set_setting("musicbrainz", False)
    store.add_playlist(P1)
    provider = FakeProvider()
    lib = Library(store, provider, validator=lambda p: None)
    lib.apply(lib.preview())
    usb = tmp_path / "usb"
    usb.mkdir()
    exporter = Exporter(lib)
    plan = exporter.preview(usb)
    # Simulate termination after atomic copy but before committing the manifest.
    relative = plan.copy[0]
    target = inside(plan.root, relative)
    atomic_copy(inside(lib.music, plan.desired[relative]["source"]), target, plan.desired[relative]["sha256"])
    resumed = exporter.preview(usb)
    assert resumed.reused == 1 and resumed.copy == []
    exporter.apply(resumed)
    provider.snapshots[P1] = snapshot(track(A, "pop"))
    lib.apply(lib.preview())
    assert digest(target) == plan.desired[relative]["sha256"]


def test_absolute_paths_are_rejected_even_within_root(tmp_path):
    with pytest.raises(ValueError):
        inside(tmp_path, str(tmp_path / "a.mp3"))
