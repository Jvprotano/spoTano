"""Regressions from exercising the real spotDL boundary."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from spotano.provider import Cancelled, SpotProvider, worker


@pytest.mark.parametrize("outside", [False, True])
def test_download_installs_returned_filename_and_rejects_escape(tmp_path, monkeypatch, outside):
    import spotdl.download.downloader
    import spotdl.utils.deno
    import spotdl.utils.ffmpeg
    import spotdl.utils.spotify

    monkeypatch.setattr(spotdl.utils.ffmpeg, "get_ffmpeg_path", lambda: Path("ffmpeg"))
    monkeypatch.setattr(spotdl.utils.deno, "get_deno_path", lambda: None)
    monkeypatch.setattr(
        spotdl.utils.spotify.SpotifyClient,
        "init",
        lambda **kwargs: pytest.fail("Must not initialize Spotify for audio downloads"),
    )
    staging = tmp_path / "stage"
    staging.mkdir()
    expected = staging / "audio.mp3"

    class Downloader:
        def __init__(self, settings, loop):
            # A literal path is interpreted as a directory by spotDL 4.6.0.
            assert "{track-id}" in settings["output"]
            self.progress_handler = SimpleNamespace(update_callback=None)
            self.directory = Path(settings["output"]).parent
            self.audio_providers = []
            self.errors = []

        def download_song(self, song):
            for stage in ("Searching for song", "Downloading", "Converting", "Done"):
                self.progress_handler.update_callback(None, stage)
            assert song.album_id == "" and song.genres == []
            actual = (tmp_path if outside else self.directory) / "Provider chosen title.mp3"
            actual.parent.mkdir(parents=True, exist_ok=True)
            actual.write_bytes(b"test audio")
            return song, actual

    monkeypatch.setattr(spotdl.download.downloader, "Downloader", Downloader)
    monkeypatch.setattr("spotano.matching.FastMatcher.candidates", lambda self, metadata: [
        {"url": "https://www.youtube.com/watch?v=abcdefghijk", "score": 100}])
    request, result = tmp_path / "request.json", tmp_path / "response.json"
    request.write_text(
        json.dumps(
            {
                "action": "download",
                "payload": {
                    "metadata": {"name": "Title", "artist": "Artist", "song_id": "A" * 22},
                    "output": str(expected),
                },
            }
        )
    )
    worker(request, result)
    response = json.loads(result.read_text(encoding="utf-8"))
    events = [
        json.loads(line)["message"]
        for line in (tmp_path / "progress.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert "Recebendo áudio do provedor" in events
    assert "Convertendo com FFmpeg para MP3" in events
    if outside:
        assert "error" in response and not expected.exists()
    else:
        assert response["result"]["output"] == str(expected)
        assert expected.is_file() and expected.read_bytes() == b"test audio"


def test_worker_progress_is_forwarded_before_process_finishes(tmp_path, monkeypatch):
    events = []
    finished = False

    def report(message):
        if message == "Etapa em tempo real":
            assert not finished
        events.append(message)

    class Process:
        def __init__(self, command, **kwargs):
            self.polls = 0
            self.result = Path(command[-1])
            (self.result.parent / "progress.jsonl").write_text(
                json.dumps({"message": "Etapa em tempo real"}) + "\n", encoding="utf-8"
            )

        def poll(self):
            nonlocal finished
            self.polls += 1
            if self.polls > 1:
                self.result.write_text(json.dumps({"result": "ok"}))
                finished = True
                return 0

    monkeypatch.setattr("spotano.provider.subprocess.Popen", Process)
    provider = SpotProvider(progress=report)
    assert provider.call("diagnostics") == "ok"
    assert "Etapa em tempo real" in events


@pytest.mark.parametrize("cancelled", [True, False])
def test_waiting_worker_reports_silence_and_stops_on_timeout_or_cancellation(monkeypatch, cancelled):
    events, stopped = [], []
    clock = [0]

    class Cancel:
        def wait(self, seconds):
            clock[0] += 15
            return cancelled

    monkeypatch.setattr("spotano.provider.time.monotonic", lambda: clock[0])
    monkeypatch.setattr(
        "spotano.provider.subprocess.Popen", lambda *args, **kwargs: SimpleNamespace(poll=lambda: None)
    )
    monkeypatch.setattr("spotano.provider.stop_tree", stopped.append)
    provider = SpotProvider(Cancel(), events.append)
    with pytest.raises(Cancelled if cancelled else TimeoutError):
        provider.call("download", timeout=20)
    assert len(stopped) == 1
    if not cancelled:
        assert any("sem novas etapas há 15s" in event for event in events)
