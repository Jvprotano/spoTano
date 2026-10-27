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
    events = []
    lib.progress = events.append
    result = lib.apply(lib.preview(force=True))
    assert len(result["failures"]) == 1
    assert result["downloaded"] == 1
    assert lib.available(old)
    assert not list((store.root / "staging").rglob("*.mp3"))
    batches = [event for event in events if isinstance(event, dict)]
    assert [event["completed"] for event in batches] == [0, 1, 2]
    assert batches[-1] == {"kind": "batch_progress", "completed": 2, "total": 2, "failed": 1, "reused": 0}
    events.clear()
    lib.apply(lib.preview())
    batches = [event for event in events if isinstance(event, dict)]
    assert batches == [{"kind": "batch_progress", "completed": 0, "total": 0, "failed": 0, "reused": 2}]


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
    lib.apply(lib.preview())
    lib.correct_genre(A, "Rock e Metal")
    row = store.tracks()[0]
    assert row["path"].startswith("Rock e Metal/") and lib.available(row)
    store.set_setting("by_genre", False)
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
    store.set_setting("output_layout", "unified")
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


def test_import_fetches_metadata_without_downloading_and_persists(collection):
    store, provider, lib = collection
    playlist_id = lib.import_playlist(P2 + "?si=shared")
    row = Store(store.root).playlists()[1]
    assert row["id"] == playlist_id and row["name"] == "Playlist teste"
    assert row["total"] == 2 and row["count"] == 2 and row["synced_at"]
    assert row["downloaded_at"] is None and provider.downloads == []
    assert len(lib.preview(playlist_ids=[playlist_id]).added) == 2
    with pytest.raises(ValueError, match="já importada"):
        lib.import_playlist(P2)


def test_failed_import_never_leaves_placeholder(collection):
    store, provider, lib = collection
    before = store.setting("revision")
    provider.snapshots[P2] = OSError("offline")
    with pytest.raises(OSError):
        lib.import_playlist(P2)
    assert len(store.playlists()) == 1 and store.setting("revision") == before
    provider.snapshots[P2] = snapshot({**track(B), "song_id": "invalid"})
    with pytest.raises(ValueError):
        lib.import_playlist(P2)
    assert len(store.playlists()) == 1 and store.tracks() == []


@pytest.mark.parametrize("force", [False, True])
def test_only_selected_playlists_are_read_and_applied(collection, force):
    store, provider, lib = collection
    second = store.add_playlist(P2)
    lib.apply(lib.preview())
    before = store.playlists()[1]
    provider.downloads.clear()
    provider.snapshots[P2] = OSError("must not read unselected playlist")
    provider.snapshots[P1] = snapshot(track(C))
    plan = lib.preview(force=force, playlist_ids=[1])
    assert [i for i, _ in plan.snapshots] == [1]
    lib.apply(plan)
    assert provider.downloads == [A if force else C]
    assert store.playlists()[1] == before
    assert store.rows("SELECT track_id FROM membership WHERE playlist_id=?", (second,)) == [
        {"track_id": A},
        {"track_id": B},
    ]


@pytest.mark.parametrize("ids", [[], [999], [1, 999]])
def test_empty_or_invalid_selection_is_rejected(collection, ids):
    with pytest.raises(ValueError, match="Marque"):
        collection[2].preview(playlist_ids=ids)


def test_failed_sync_keeps_last_completed_download_for_comparison(collection):
    store, provider, lib = collection
    lib.apply(lib.preview())
    baseline = store.rows("SELECT * FROM download_membership")
    completed = store.playlists()[0]["downloaded_at"]
    provider.snapshots[P1] = snapshot(track(B))
    provider.fail.add(B)
    lib.apply(lib.preview())
    assert store.rows("SELECT * FROM download_membership") == baseline
    assert store.playlists()[0]["downloaded_at"] == completed
    restarted = Library(Store(store.root), provider, validator=lambda p: None)
    pending = restarted.preview(playlist_ids=[1])
    assert pending.added == [("Playlist teste", "Canção B")]
    assert pending.removed == [("Playlist teste", "Canção A")]
    provider.fail.clear()
    restarted.apply(pending)
    assert restarted.preview().added == [] and restarted.preview().removed == []


def test_successful_playlists_advance_independently_of_other_failures(collection):
    store, provider, lib = collection
    store.add_playlist(P2)
    provider.fail.add(B)
    lib.apply(lib.preview())
    assert store.playlists()[0]["downloaded_at"]
    assert store.playlists()[1]["downloaded_at"] is None
    assert lib.preview(playlist_ids=[1]).added == []
    assert len(lib.preview(playlist_ids=[2]).added) == 2


@pytest.mark.parametrize("layout,copies", [("unified", 2), ("playlists", 3), ("groups", 2)])
def test_output_layouts_export_shared_audio_and_reuse_without_downloads(collection, tmp_path, layout, copies):
    store, provider, lib = collection
    store.add_playlist(P2)  # Both have the same title, but distinct IDs.
    lib.apply(lib.preview())
    store.set_output_group([1, 2], "Viagem / verão")
    store.set_setting("output_layout", layout)
    exporter = Exporter(lib)
    plan = exporter.preview(tmp_path)
    assert len(plan.copy) == copies
    exporter.apply(plan)
    assert len(provider.downloads) == 2
    assert exporter.preview(tmp_path).reused == copies
    for relative, entry in plan.desired.items():
        assert inside(plan.root, relative).read_bytes() == inside(lib.music, entry["source"]).read_bytes()
    if layout == "groups":
        assert all(path.startswith("Viagem _ verao/") for path in plan.desired)
    if layout == "playlists":
        assert len({path.split("/")[0] for path in plan.desired}) == 2


def test_output_folder_collision_does_not_merge_distinct_playlists_or_groups():
    from spotano.exporter import output_folders

    rows = [
        {"id": i, "name": name, "output_group": name}
        for i, name in enumerate(["Rock", "rock", "rock", "róck"], 1)
    ]
    folders = output_folders(rows, "groups")
    assert folders[2] == folders[3]
    assert len({name.casefold() for name in folders.values()}) == 3
    assert len({name.casefold() for name in output_folders(rows, "playlists").values()}) == 4


def test_distinct_group_labels_survive_normalization_and_do_not_merge(collection, tmp_path):
    store, _, lib = collection
    store.add_playlist(P2)
    lib.apply(lib.preview())
    store.set_output_group([1], "Rock")
    store.set_output_group([2], "Róck")
    store.set_setting("output_layout", "groups")
    assert store.playlists()[1]["output_group"] == "Róck"
    plan = Exporter(lib).preview(tmp_path)
    assert len(plan.copy) == 3  # Shared song appears in each distinct group.
    assert len({relative.split("/")[0].casefold() for relative in plan.copy}) == 2


def test_layout_change_preserves_previous_output_in_trash_and_rejects_stale_plan(collection, tmp_path):
    store, _, lib = collection
    store.set_setting("output_layout", "unified")
    lib.apply(lib.preview())
    exporter = Exporter(lib)
    old = exporter.preview(tmp_path)
    exporter.apply(old)
    stale = exporter.preview(tmp_path)
    store.set_setting("output_layout", "playlists")
    with pytest.raises(ValueError, match="desatualizada"):
        exporter.apply(stale)
    changed = exporter.preview(tmp_path)
    assert len(changed.copy) == 1 and len(changed.remove) == 1
    exporter.apply(changed)
    assert list((changed.root / ".spotano-trash").rglob("*.mp3"))
    assert lib.available(store.tracks()[0])


def test_legacy_catalog_migrates_once_and_keeps_previous_comparison(tmp_path):
    import sqlite3

    root = tmp_path / "legacy"
    root.mkdir()
    with sqlite3.connect(root / "library.sqlite3") as db:
        db.executescript("""CREATE TABLE playlists(id INTEGER PRIMARY KEY, url TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL, synced_at TEXT, warning TEXT NOT NULL DEFAULT '');
            CREATE TABLE tracks(id TEXT PRIMARY KEY,metadata TEXT NOT NULL,category TEXT NOT NULL DEFAULT 'Outros',
            override TEXT,path TEXT,sha256 TEXT,status TEXT NOT NULL DEFAULT 'pending',
            error TEXT NOT NULL DEFAULT '',updated_at TEXT);
            CREATE TABLE membership(playlist_id INTEGER,track_id TEXT,position INTEGER,
            PRIMARY KEY(playlist_id,track_id));""")
        db.execute("INSERT INTO playlists(id,url,name) VALUES(1,?,?)", (P1, "Legado"))
        db.execute("INSERT INTO tracks(id,metadata) VALUES(?,?)", (A, json.dumps(track())))
        db.execute("INSERT INTO membership VALUES(1,?,0)", (A,))
    store = Store(root)
    assert len(store.rows("SELECT * FROM download_membership")) == 1
    library = Library(store, FakeProvider())
    assert "catálogo antigo" in library.preview().warnings[0]
    with store.connect() as db:
        db.execute("DELETE FROM download_membership")
    assert Store(root).rows("SELECT * FROM download_membership") == []
    assert store.playlists()[0]["downloaded_at"] is None


def test_force_uses_imported_snapshot_without_network_or_changing_read_time(collection):
    store, provider, lib = collection
    playlist_id = lib.import_playlist(P2)
    before = store.playlists()[1]
    provider.playlist = lambda url: pytest.fail("Forced audio download must not query Spotify")
    plan = lib.preview(force=True, playlist_ids=[playlist_id])
    assert not plan.refresh_metadata and len(plan.downloads) == 2
    lib.apply(plan)
    after = store.playlists()[1]
    assert after["synced_at"] == before["synced_at"]
    assert after["name"] == before["name"] and after["count"] == 2


def test_force_requests_initial_metadata_if_legacy_playlist_has_never_been_read(collection):
    with pytest.raises(ValueError, match="Atualizar selecionadas"):
        collection[2].preview(force=True)


def test_download_concurrency_is_bounded_and_installs_each_result(collection):
    import threading
    import time

    store, provider, lib = collection
    provider.snapshots[P1] = snapshot(track(A), track(B), track(C))
    store.set_setting("download_workers", 2)
    original = provider.download
    lock, barrier = threading.Lock(), threading.Barrier(2)
    active = maximum = started = 0

    def concurrent(metadata, output):
        nonlocal active, maximum, started
        with lock:
            active += 1
            started += 1
            ordinal = started
            maximum = max(maximum, active)
        try:
            if ordinal <= 2:
                barrier.wait(timeout=5)
            time.sleep(0.03)
            original(metadata, output)
        finally:
            with lock:
                active -= 1

    provider.download = concurrent
    result = lib.apply(lib.preview())
    assert maximum == 2 and result["downloaded"] == 3
    assert all(lib.available(row) for row in store.tracks())


def test_cancellation_stops_queue_and_preserves_old_audio(collection):
    import threading

    store, provider, lib = collection
    provider.snapshots[P1] = snapshot(track(A), track(B), track(C))
    lib.apply(lib.preview())
    previous = store.tracks()
    plan = lib.preview(force=True)
    barrier = threading.Barrier(2)
    calls = []

    def interrupted(metadata, output):
        calls.append(metadata["song_id"])
        barrier.wait(timeout=5)
        lib.cancel.set()
        raise Cancelled("cancelled")

    provider.download = interrupted
    with pytest.raises(Cancelled):
        lib.apply(plan)
    assert len(calls) == 2
    assert all(lib.available(row) for row in previous)
    assert not list((store.root / "staging").rglob("audio.mp3"))


def test_unknown_category_is_repaired_in_reused_audio_without_downloading(collection, monkeypatch):
    store, provider, lib = collection
    provider.snapshots[P1] = snapshot(track(A, "unknown"))
    lib.apply(lib.preview())
    old = store.tracks()[0]
    assert old["category"] == "Outros"
    monkeypatch.setattr("spotano.library.GenreResolver.resolve", lambda self, metadata: "Sertanejo")
    provider.download = lambda *args: pytest.fail("Audio should be reused")
    result = lib.apply(lib.preview())
    row = store.tracks()[0]
    assert result["downloaded"] == 0 and row["category"] == "Sertanejo"
    assert row["sha256"] == old["sha256"] and lib.available(row)


def test_parallel_installs_handle_windows_extended_path_prefix(tmp_path, monkeypatch):
    import os

    if os.name != "nt":
        pytest.skip("Windows path spelling")
    original = Path.resolve

    def resolve(path, *args, **kwargs):
        value = original(path, *args, **kwargs)
        return Path("\\\\?\\" + str(value)) if path.suffix == ".mp3" else value

    monkeypatch.setattr(Path, "resolve", resolve)
    assert inside(tmp_path, "category/audio.mp3").name == "audio.mp3"
    with pytest.raises(ValueError):
        inside(tmp_path, "../outside.mp3")
