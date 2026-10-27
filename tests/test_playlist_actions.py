"""User choices must keep metadata refresh, downloads and removal independent."""

import pytest
from test_library import P1, P2, A, B, C, FakeProvider, snapshot, track

from spotano.db import Store
from spotano.library import Library


@pytest.fixture
def collection(tmp_path):
    store = Store(tmp_path / "data")
    store.set_setting("musicbrainz", False)
    store.add_playlist(P1)
    provider = FakeProvider()
    return store, provider, Library(store, provider, validator=lambda path: None)


def test_repeated_refresh_saves_changes_without_audio_or_baseline_changes(collection):
    store, provider, lib = collection
    lib.apply(lib.preview())
    baseline = store.rows("SELECT * FROM download_membership")
    downloaded_at = store.playlists()[0]["downloaded_at"]
    original = lib.music / store.tracks()[0]["path"]
    audio = original.read_bytes()
    provider.downloads.clear()
    provider.snapshots[P1] = snapshot(track(B))
    for _ in range(2):
        plan = lib.refresh_playlists([1])
        assert plan.added == [("Playlist teste", "Canção B")]
        assert plan.removed == [("Playlist teste", "Canção A")]
        assert provider.downloads == [] and original.read_bytes() == audio
        assert store.rows("SELECT * FROM download_membership") == baseline
        assert store.playlists()[0]["downloaded_at"] == downloaded_at
    restarted = Library(Store(store.root), provider, validator=lambda path: None)
    provider.playlist = lambda url: pytest.fail("Download must use the last saved query")
    result = restarted.apply(restarted.preview(playlist_ids=[1], saved=True))
    assert result["downloaded"] == 1 and result["removed"] == 0
    assert original.read_bytes() == audio
    assert restarted.preview(playlist_ids=[1], saved=True).removed  # Can remove later, after restart.
    removal = restarted.preview(playlist_ids=[1], saved=True, remove_missing=True)
    assert [t["id"] for t in removal.cleanup] == [A]
    result = restarted.apply(removal)
    assert result["downloaded"] == 0 and result["removed"] == 1
    assert not original.exists()
    assert any(p.read_bytes() == audio for p in (store.root / "trash").rglob("*.mp3"))
    assert restarted.preview(playlist_ids=[1], saved=True).removed == []


def test_failed_refresh_of_one_playlist_preserves_all_saved_snapshots(collection):
    store, provider, lib = collection
    store.add_playlist(P2)
    lib.apply(lib.preview())
    before = store.rows("SELECT * FROM membership"), store.playlists(), store.setting("revision")
    provider.snapshots[P1] = snapshot(track(C))
    provider.snapshots[P2] = OSError("offline")
    with pytest.raises(OSError):
        lib.refresh_playlists([1, 2])
    assert (store.rows("SELECT * FROM membership"), store.playlists(), store.setting("revision")) == before


def test_refresh_detects_missing_audio_and_saved_download_restores_it(collection):
    store, _, lib = collection
    lib.apply(lib.preview())
    source = lib.music / store.tracks()[0]["path"]
    source.unlink()
    plan = lib.refresh_playlists([1])
    assert len(plan.downloads) == 1
    assert store.tracks()[0]["status"] == "pending"
    assert not source.exists()
    lib.apply(lib.preview(playlist_ids=[1], saved=True))
    assert lib.available(store.tracks()[0])


def test_shared_audio_is_protected_by_current_and_retained_playlist_ownership(collection):
    store, provider, lib = collection
    store.add_playlist(P2)
    lib.apply(lib.preview())
    provider.snapshots[P1] = snapshot()
    lib.refresh_playlists([1])
    plan = lib.preview(playlist_ids=[1], saved=True, remove_missing=True)
    assert plan.cleanup == []
    assert lib.apply(plan)["removed"] == 0
    assert lib.available(next(t for t in store.tracks() if t["id"] == A))
    # Now both snapshots omit B, but P2's user chose to keep its old downloads.
    provider.snapshots[P1] = snapshot(track(B))
    lib.refresh_playlists([1])
    lib.apply(lib.preview(playlist_ids=[1], saved=True))
    provider.snapshots[P1] = snapshot()
    provider.snapshots[P2] = snapshot(track(A))
    lib.refresh_playlists([1, 2])
    lib.apply(lib.preview(playlist_ids=[2], saved=True))
    plan = lib.preview(playlist_ids=[1], saved=True, remove_missing=True)
    assert plan.cleanup == []  # P2 still owns its retained B download.
    assert lib.apply(plan)["removed"] == 0
    plan = lib.preview(playlist_ids=[2], saved=True, remove_missing=True)
    assert [t["id"] for t in plan.cleanup] == [B]
    assert lib.apply(plan)["removed"] == 1


def test_failed_download_skips_all_removals_and_keeps_comparison(collection):
    store, provider, lib = collection
    lib.apply(lib.preview())
    source = lib.music / store.tracks()[0]["path"]
    baseline = store.rows("SELECT * FROM download_membership")
    provider.snapshots[P1] = snapshot(track(B))
    provider.fail.add(B)
    lib.refresh_playlists([1])
    result = lib.apply(lib.preview(playlist_ids=[1], saved=True, remove_missing=True))
    assert result["failures"] and result["removed"] == 0 and source.exists()
    assert store.rows("SELECT * FROM download_membership") == baseline
    provider.fail.clear()
    result = lib.apply(lib.preview(playlist_ids=[1], saved=True, remove_missing=True))
    assert result["removed"] == 1 and not source.exists()


def test_removal_preview_rejects_modified_audio_and_stale_catalog(collection):
    store, provider, lib = collection
    lib.apply(lib.preview())
    source = lib.music / store.tracks()[0]["path"]
    provider.snapshots[P1] = snapshot()
    lib.refresh_playlists([1])
    plan = lib.preview(playlist_ids=[1], saved=True, remove_missing=True)
    store.set_setting("musicbrainz", False)
    with pytest.raises(ValueError, match="desatualizada"):
        lib.apply(plan)
    plan = lib.preview(playlist_ids=[1], saved=True, remove_missing=True)
    source.write_bytes(b"externally changed; preserve")
    with pytest.raises(ValueError, match="alterado externamente"):
        lib.apply(plan)
    assert source.read_bytes() == b"externally changed; preserve"
    assert store.rows("SELECT * FROM download_membership")


def test_new_catalog_separates_exports_and_existing_preference_survives(tmp_path):
    store = Store(tmp_path)
    assert store.setting("output_layout") == "playlists"
    store.set_setting("output_layout", "unified")
    assert Store(tmp_path).setting("output_layout") == "unified"

