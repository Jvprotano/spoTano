import subprocess
import sys
import threading
from pathlib import Path

import pytest

from spotano.downloads import WarmDownload, saved_song
from spotano.provider import Cancelled, SpotProvider


@pytest.fixture
def stub_worker(monkeypatch):
    original = subprocess.Popen
    starts = []

    def launch(command, **kwargs):
        if "--worker" not in command:
            return original(command, **kwargs)
        process = original(
            [
                sys.executable,
                str(Path(__file__).with_name("_download_worker_stub.py")),
                command[-2],
                command[-1],
            ],
            **kwargs,
        )
        starts.append(process)
        return process

    monkeypatch.setattr("spotano.downloads.subprocess.Popen", launch)
    return starts


def metadata(letter="A", name="test"):
    return {"song_id": letter * 22, "name": name, "artist": "Test artist", "genres": [], "album_id": None}


def test_one_process_is_reused_and_closed_after_batch(tmp_path, stub_worker):
    events = []
    provider = SpotProvider(progress=events.append)
    with provider.download_batch() as batch:
        provider.download(metadata(), tmp_path / "first.mp3")
        provider.download(metadata("B"), tmp_path / "second.mp3")
        session = next(iter(batch.sessions.values()))
        assert (session.root / "initializations.txt").read_text().splitlines() == ["initialized"]
        assert len(stub_worker) == 1
        assert any("Reutilizando" in message for message in events)
    assert (tmp_path / "second.mp3").read_bytes() == b"B" * 22
    assert provider._batch is None and stub_worker[0].poll() is not None


def test_timeout_kills_process_and_next_track_gets_new_worker(tmp_path, stub_worker):
    session = WarmDownload(threading.Event(), lambda message: None)
    try:
        with pytest.raises(TimeoutError):
            session.download(metadata(name="slow"), tmp_path / "slow.mp3", timeout=0.3)
        assert stub_worker[0].poll() is not None
        session.download(metadata("B"), tmp_path / "next.mp3", timeout=10)
        assert len(stub_worker) == 2 and (tmp_path / "next.mp3").read_bytes() == b"B" * 22
    finally:
        session.close()


def test_cancel_terminates_active_worker(tmp_path, stub_worker):
    cancel, started = threading.Event(), threading.Event()
    session = WarmDownload(cancel, lambda message: started.set() if "download started" in message else None)
    errors = []

    def run():
        try:
            session.download(metadata(name="slow"), tmp_path / "slow.mp3")
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=run)
    try:
        thread.start()
        assert started.wait(10)
        cancel.set()
        thread.join(10)
        assert not thread.is_alive() and isinstance(errors[0], Cancelled)
        assert stub_worker[0].poll() is not None and not (tmp_path / "slow.mp3").exists()
    finally:
        cancel.set()
        thread.join(10)
        session.close()


def test_saved_metadata_does_not_invent_album_identity_or_mutate_catalog():
    original = metadata()
    song = saved_song(original)
    assert song.album_id == "" and original["album_id"] is None
    assert song.genres == []
    assert all(
        value is not None
        for value in (song.album_id, song.album_artist, song.track_number, song.tracks_count, song.disc_count)
    )


def test_batch_uses_independent_processes_for_parallel_threads(tmp_path, stub_worker):
    provider = SpotProvider()
    barrier = threading.Barrier(2)
    failures = []

    def download(letter):
        try:
            barrier.wait(timeout=5)
            provider.download(metadata(letter), tmp_path / (letter + ".mp3"))
        except Exception as exc:
            failures.append(exc)

    with provider.download_batch() as batch:
        threads = [threading.Thread(target=download, args=(letter,)) for letter in "AB"]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(15)
        assert not failures and all(not thread.is_alive() for thread in threads)
        assert len(batch.sessions) == 2 and len(stub_worker) == 2
        assert len({str(session.root) for session in batch.sessions.values()}) == 2
    assert all(process.poll() is not None for process in stub_worker)
