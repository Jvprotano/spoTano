import json
from pathlib import Path

import pytest

from spotano.db import Store
from spotano.exporter import Exporter
from spotano.library import Library
from spotano.paths import inside, playlist_url, safe_name
from spotano.provider import Cancelled, strict_playlist

A, B, C = "A" * 22, "B" * 22, "C" * 22
P1, P2 = "https://open.spotify.com/playlist/" + A, "https://open.spotify.com/playlist/" + B


def track(song_id=A, genre="sertanejo universitário"):
    return {
        "song_id": song_id,
        "name": "Canção " + song_id[0],
        "artist": "Artista",
        "artists": ["Artista"],
        "genres": [genre],
        "url": "https://open.spotify.com/track/" + song_id,
    }


def snapshot(*tracks):
    return {"name": "Playlist teste", "tracks": list(tracks), "total": len(tracks), "skipped": 0}


class FakeProvider:
    def __init__(self):
        self.snapshots = {P1: snapshot(track()), P2: snapshot(track(), track(B))}
        self.downloads = []
        self.fail = set()

    def playlist(self, url):
        result = self.snapshots[url]
        if isinstance(result, Exception):
            raise result
        return result

    def download(self, metadata, output):
        self.downloads.append(metadata["song_id"])
        output.write_bytes(b"simulated audio bytes: " + metadata["song_id"].encode())
        if metadata["song_id"] in self.fail:
            raise OSError("network interrupted")


@pytest.fixture
def collection(tmp_path):
    store = Store(tmp_path / "data")
    store.set_setting("musicbrainz", False)
    store.add_playlist(P1)
    provider = FakeProvider()
    library = Library(store, provider, validator=lambda p: None)
    return store, provider, library


def test_duplicate_membership_downloads_once_and_restart_reuses(collection):
    store, provider, library = collection
    store.add_playlist(P2)
    result = library.apply(library.preview())
    assert result["downloaded"] == 2
    assert sorted(provider.downloads) == [A, B]
    restarted = Library(Store(store.root), provider, validator=lambda p: None)
    assert restarted.preview().retained == 2
    assert restarted.preview().downloads == []


def test_removing_one_membership_never_deletes_shared_file(collection):
    store, provider, lib = collection
    store.add_playlist(P2)
    lib.apply(lib.preview())
    provider.snapshots[P1] = snapshot()
    plan = lib.preview()
    assert len(plan.removed) == 1
    lib.apply(plan)
    shared = next(t for t in store.tracks() if t["id"] == A)
    assert shared["references_count"] == 1
    assert lib.available(shared)
    assert lib.orphan_preview() == []


def test_failed_second_playlist_preserves_all_state(collection):
    store, provider, lib = collection
    store.add_playlist(P2)
    lib.apply(lib.preview())
    before = store.rows("SELECT * FROM membership")
    provider.snapshots[P1] = snapshot()
    provider.snapshots[P2] = OSError("offline")
    with pytest.raises(OSError):
        lib.preview()
    assert store.rows("SELECT * FROM membership") == before


def test_failed_force_preserves_previous_audio_and_continues(collection):
    store, provider, lib = collection
    store.add_playlist(P2)
    lib.apply(lib.preview())
    old = store.tracks()[0]
    provider.fail.add(A)
    result = lib.apply(lib.preview(force=True))
    assert len(result["failures"]) == 1
    assert result["downloaded"] == 1
    assert lib.available(old)
    assert not list((store.root / "staging").rglob("*.mp3"))


def test_failed_first_download_is_retried(collection):
    store, provider, lib = collection
    provider.fail.add(A)
    lib.apply(lib.preview())
    assert store.tracks()[0]["status"] == "error"
    assert len(lib.preview().downloads) == 1
    provider.fail.clear()
    lib.apply(lib.preview())
    assert store.tracks()[0]["status"] == "ready"


def test_corrupt_audio_is_not_installed(collection):
    store, provider, lib = collection
    lib.validator = lambda p: (_ for _ in ()).throw(ValueError("invalid MP3"))
    result = lib.apply(lib.preview())
    assert result["failures"]
    assert store.tracks()[0]["path"] is None


def test_stale_preview_rejected(collection):
    store, _, lib = collection
    plan = lib.preview()
    store.set_setting("by_genre", False)
    with pytest.raises(ValueError, match="desatualizada"):
        lib.apply(plan)
    assert store.tracks() == []


def test_missing_file_redownloaded(collection):
    store, _, lib = collection
    lib.apply(lib.preview())
    inside(lib.music, store.tracks()[0]["path"]).unlink()
    assert len(lib.preview().downloads) == 1


def test_manual_genre_and_artist_organization_survive_restart(collection):
    store, _, lib = collection
    store.set_setting("download_options", {"categories": True})
    lib.apply(lib.preview())
    lib.correct_genre(A, "Rock e Metal")
    row = store.tracks()[0]
    assert row["path"].startswith("Rock e Metal/") and lib.available(row)
    store.set_setting("download_options", {"artists": True})
    lib.reorganize()
    assert store.tracks()[0]["path"].startswith("Artista/")
    assert store.tracks()[0]["override"] == "Rock e Metal"
    lib.apply(lib.preview(force=True))
    assert store.tracks()[0]["override"] == "Rock e Metal"


def test_cleanup_only_orphans_and_quarantines_with_preview_revision(collection):
    store, provider, lib = collection
    lib.apply(lib.preview())
    provider.snapshots[P1] = snapshot()
    lib.apply(lib.preview())
    tracks = lib.orphan_preview()
    assert len(tracks) == 1
    trash = lib.quarantine(tracks, store.setting("revision"))
    assert list(Path(trash).rglob("*.mp3"))
    assert store.tracks()[0]["path"] is None


def test_cleanup_rejects_new_reference(collection):
    store, provider, lib = collection
    lib.apply(lib.preview())
    provider.snapshots[P1] = snapshot()
    lib.apply(lib.preview())
    tracks, revision = lib.orphan_preview(), store.setting("revision")
    provider.snapshots[P1] = snapshot(track())
    lib.apply(lib.preview())
    with pytest.raises(ValueError):
        lib.quarantine(tracks, revision)
    assert lib.available(store.tracks()[0])


def test_unknown_items_do_not_prove_removal(collection):
    _, provider, lib = collection
    lib.apply(lib.preview())
    provider.snapshots[P1] = {**snapshot(), "skipped": 1}
    with pytest.raises(ValueError, match="indisponíveis"):
        lib.preview()


def test_cancellation_preserves_existing_files(collection):
    store, _, lib = collection
    lib.apply(lib.preview())
    plan = lib.preview(force=True)
    lib.cancel.set()
    with pytest.raises(Cancelled):
        lib.apply(plan)
    assert lib.available(store.tracks()[0])


def test_export_incremental_and_managed_removal(collection, tmp_path):
    store, provider, lib = collection
    store.add_playlist(P2)
    lib.apply(lib.preview())
    destination = tmp_path / "usb"
    destination.mkdir()
    unrelated = destination / "family.txt"
    unrelated.write_text("preserve")
    exporter = Exporter(lib)
    first = exporter.preview(destination)
    assert len(first.copy) == 2
    exporter.apply(first)
    paths = list(first.root.rglob("*.mp3"))
    mtimes = {p: p.stat().st_mtime_ns for p in paths}
    second = exporter.preview(destination)
    assert second.copy == [] and second.reused == 2
    exporter.apply(second)
    assert all(p.stat().st_mtime_ns == mtimes[p] for p in paths)
    provider.snapshots[P1] = snapshot()
    provider.snapshots[P2] = snapshot(track(B))
    lib.apply(lib.preview())
    third = exporter.preview(destination)
    assert len(third.remove) == 1
    exporter.apply(third)
    assert list((third.root / ".spotano-trash").rglob("*.mp3"))
    assert unrelated.read_text() == "preserve"


def test_export_blocks_incomplete_library(collection, tmp_path):
    _, provider, lib = collection
    provider.fail.add(A)
    lib.apply(lib.preview())
    with pytest.raises(ValueError, match="ausentes"):
        Exporter(lib).preview(tmp_path)


def test_export_never_overwrites_unknown_or_modified_files(collection, tmp_path):
    _, _, lib = collection
    lib.apply(lib.preview())
    exporter = Exporter(lib)
    plan = exporter.preview(tmp_path)
    target = inside(plan.root, plan.copy[0])
    target.parent.mkdir(parents=True)
    target.write_bytes(b"user owned")
    with pytest.raises(ValueError, match="desconhecido"):
        exporter.apply(plan)
    assert target.read_bytes() == b"user owned"


def test_export_modified_source_after_preview_is_blocked(collection, tmp_path):
    store, _, lib = collection
    lib.apply(lib.preview())
    exporter = Exporter(lib)
    plan = exporter.preview(tmp_path)
    inside(lib.music, store.tracks()[0]["path"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="alteradas"):
        exporter.apply(plan)


def test_malicious_manifest_and_path_escape(collection, tmp_path):
    _, _, lib = collection
    lib.apply(lib.preview())
    root = tmp_path / "spoTano"
    root.mkdir()
    (root / ".spotano-manifest.json").write_text(
        json.dumps({"version": 1, "files": {"../outside.mp3": {"sha256": "x"}}})
    )
    with pytest.raises(ValueError, match="fora"):
        Exporter(lib).preview(tmp_path)
    with pytest.raises(ValueError):
        inside(tmp_path, "../outside")


def test_export_destination_cannot_be_library(collection):
    store, _, lib = collection
    lib.apply(lib.preview())
    with pytest.raises(ValueError):
        Exporter(lib).preview(store.root)


def test_database_backup_is_consistent(collection, tmp_path):
    store, _, lib = collection
    lib.apply(lib.preview())
    target = tmp_path / "catalog.sqlite3"
    store.backup(target)
    import sqlite3

    with sqlite3.connect(target) as db:
        assert db.execute("SELECT COUNT(*) FROM tracks").fetchone()[0] == 1
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_safe_names_and_playlist_validation():
    assert safe_name("CON") == "_CON"
    assert safe_name("São João: /?*") == "Sao Joao_ ___"
    assert playlist_url(P1 + "?si=test") == P1
    with pytest.raises(ValueError):
        playlist_url("https://evil.example/playlist/" + A)


class PageClient:
    def __init__(self, page, next_page=None, change=False):
        self.page, self.next_page, self.change = page, next_page, change
        self.calls = 0

    def playlist(self, url):
        self.calls += 1
        return {"name": "Test", "snapshot_id": "changed" if self.change and self.calls > 1 else "initial"}

    def playlist_items(self, url):
        return self.page

    def next(self, page):
        return self.next_page


@pytest.mark.parametrize(
    "page,next_page",
    [
        ({"items": [], "total": 3, "next": None}, None),
        ({"items": [], "total": 3, "next": "page2"}, None),
        ({"items": [], "next": None}, None),
        ({"items": [], "total": 3, "next": "page2"}, {"items": [], "total": 3, "next": "page2"}),
    ],
)
def test_strict_pagination_rejects_partial_results(page, next_page):
    with pytest.raises(ValueError):
        strict_playlist(PageClient(page, next_page), P1)


def test_empty_playlist_is_valid_but_changing_snapshot_is_not():
    page = {"items": [], "total": 0, "next": None}
    assert strict_playlist(PageClient(page), P1)["tracks"] == []
    with pytest.raises(ValueError, match="mudou"):
        strict_playlist(PageClient(page, change=True), P1)


def test_complete_pagination_retains_unsupported_items_count():
    raw = {"id": A, "type": "track", "name": "A", "artists": [{"name": "Author"}], "album": {}}
    first = {"items": [{"track": raw}], "total": 2, "next": "page2"}
    last = {"items": [{"track": None}], "total": 2, "next": None}
    data = strict_playlist(PageClient(first, last), P1)
    assert len(data["tracks"]) == 1 and data["skipped"] == 1 and data["total"] == 2
