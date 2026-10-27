"""Exercise real SQLite/files across restarts; providers/audio bytes are synthetic."""

import subprocess
import sys
from pathlib import Path

import pytest
from test_library import P1, A, FakeProvider, snapshot, track

from spotano.db import Store
from spotano.library import Library
from spotano.paths import digest
from spotano.provider import Cancelled


def collection(tmp_path, count=240):
    store = Store(tmp_path / "data")
    store.set_setting("musicbrainz", False)
    store.set_setting("download_workers", 1)
    provider = FakeProvider()
    provider.snapshots[P1] = snapshot(*(track(f"{index:022d}") for index in range(count)))
    lib = Library(store, provider, validator=lambda path: None)
    lib.import_playlist(P1)
    return store, provider, lib


def reopen(store, provider):
    provider.downloads.clear()
    # Resuming must not need the Spotify connection, nor change the saved playlist.
    provider.snapshots[P1] = OSError("Spotify offline")
    return Library(Store(store.root), provider, validator=lambda path: None)


def test_240_tracks_resume_network_failures_and_repair_missing_or_corrupt_files(tmp_path):
    store, provider, lib = collection(tmp_path)
    store.set_setting("download_workers", 4)
    provider.fail = {f"{index:022d}" for index in range(0, 240, 17)}
    result = lib.apply(lib.preview(saved=True))
    assert result["downloaded"] == 225 and len(result["failures"]) == 15
    assert len(store.rows("SELECT * FROM download_pending")) == 15
    assert store.playlists()[0]["downloaded_at"] is None
    ready = [row for row in store.tracks() if row["path"]]
    (lib.music / ready[0]["path"]).unlink()
    (lib.music / ready[1]["path"]).write_bytes(b"corrupt")
    expected = provider.fail | {row["id"] for row in ready[:2]}
    provider.fail.clear()
    resumed = reopen(store, provider)
    plan = resumed.preview(saved=True)
    assert {row["song_id"] for row in plan.downloads} == expected
    assert plan.retained == 223
    result = resumed.apply(plan)
    assert result["downloaded"] == 16 and result["reused"] == 223 and len(result["failures"]) == 1
    assert set(provider.downloads) == expected
    # A changed file may contain a user's edit. Preserve it for review rather than overwrite it.
    corrupt = lib.music / ready[1]["path"]
    assert corrupt.read_bytes() == b"corrupt"
    corrupt.unlink()  # Simulate explicitly removing the reviewed, invalid copy.
    result = resumed.apply(resumed.preview(saved=True))
    assert result["downloaded"] == 1 and result["reused"] == 239 and not result["failures"]
    assert all(resumed.available(row) for row in store.tracks())
    assert not store.rows("SELECT * FROM download_pending")
    assert store.playlists()[0]["downloaded_at"]


@pytest.mark.parametrize("force", [False, True])
def test_240_tracks_resume_after_process_termination_without_repeating_completed_audio(tmp_path, force):
    store, provider, lib = collection(tmp_path)
    if force:
        lib.apply(lib.preview(saved=True))
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("_resume_worker.py")),
            str(store.root),
            "force" if force else "new",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 17, result.stdout + result.stderr
    pending = {row["track_id"] for row in store.rows("SELECT * FROM download_pending")}
    assert len(pending) == 167
    completed = {row["id"]: row for row in store.tracks() if row["id"] not in pending}
    assert len(completed) == 73
    hashes = {track_id: digest(lib.music / row["path"]) for track_id, row in completed.items()}
    resumed = reopen(store, provider)
    plan = resumed.preview(saved=True)
    assert plan.retained == 73 and {row["song_id"] for row in plan.downloads} == pending
    result = resumed.apply(plan)
    assert result["downloaded"] == 167 and not result["failures"]
    assert set(provider.downloads) == pending
    assert hashes == {track_id: digest(lib.music / row["path"]) for track_id, row in completed.items()}
    assert not store.rows("SELECT * FROM download_pending")
    assert all(resumed.available(row) for row in store.tracks())


def test_240_tracks_cancel_then_reopen_keeps_completed_downloads(tmp_path):
    store, provider, lib = collection(tmp_path)
    store.set_setting("download_workers", 4)
    saved = []

    def progress(message):
        if isinstance(message, str) and message.startswith("Salvo ·"):
            saved.append(message)
            if len(saved) == 73:
                lib.cancel.set()

    lib.progress = progress
    with pytest.raises(Cancelled):
        lib.apply(lib.preview(saved=True))
    resumed = reopen(store, provider)
    plan = resumed.preview(saved=True)
    assert 73 <= plan.retained <= 76 and len(plan.downloads) == 240 - plan.retained
    resumed.apply(plan)
    assert len(provider.downloads) == len(plan.downloads)
    assert not store.rows("SELECT * FROM download_pending")


def test_failed_forced_replacement_survives_retagging_and_unrelated_playlist(tmp_path):
    store, provider, lib = collection(tmp_path, count=3)
    lib.apply(lib.preview(saved=True))
    failed = store.tracks()[0]["id"]
    provider.fail = {failed}
    store.set_setting("download_options", {"metadata": True})
    result = lib.apply(lib.preview(force=True, saved=True))
    assert len(result["failures"]) == 1
    assert lib.available(store.tracks()[0])  # Old audio stays usable.
    assert store.rows("SELECT track_id FROM download_pending") == [{"track_id": failed}]
    lib.correct_genre(failed, "Pop")  # Retagging is not a completed replacement.
    assert store.rows("SELECT track_id FROM download_pending") == [{"track_id": failed}]
    other = lib.import_playlist("https://open.spotify.com/playlist/" + "B" * 22)
    plan = lib.preview(playlist_ids=[other], saved=True)
    assert {row["song_id"] for row in plan.downloads} == {A, "B" * 22}
    provider.fail.clear()
    resumed = reopen(store, provider)
    plan = resumed.preview(playlist_ids=[1], saved=True)
    assert [row["song_id"] for row in plan.downloads] == [failed] and plan.retained == 2
    resumed.apply(plan)
    assert provider.downloads == [failed]


def test_crash_after_file_replace_recovers_queue_completion_atomically(tmp_path, monkeypatch):
    store, _, lib = collection(tmp_path, count=1)
    original = lib.files.finish
    monkeypatch.setattr(lib.files, "finish", lambda *args: (_ for _ in ()).throw(Cancelled("crash")))
    with pytest.raises(Cancelled):
        lib.apply(lib.preview(saved=True))
    assert len(store.rows("SELECT * FROM file_transitions")) == 1
    assert len(store.rows("SELECT * FROM download_pending")) == 1
    monkeypatch.setattr(lib.files, "finish", original)
    resumed = Library(Store(store.root), FakeProvider(), validator=lambda path: None)
    assert not store.rows("SELECT * FROM file_transitions")
    assert not store.rows("SELECT * FROM download_pending")
    assert resumed.preview(saved=True).retained == 1
