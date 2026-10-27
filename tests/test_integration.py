"""Actual FFmpeg/MP3 and subprocess integration; no copyrighted samples/network."""

import json
import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from spotano.db import Store
from spotano.exporter import Exporter
from spotano.library import Library, SyncPlan, validate_mp3
from spotano.provider import SpotProvider


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg is not installed")
def test_real_audio_transcode_library_restart_export(tmp_path):
    source = tmp_path / "own-generated.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(22050)
        audio.writeframes(b"\x00\x00" * 22050)
    original = tmp_path / "own-generated.mp3"
    subprocess.run(
        [shutil.which("ffmpeg"), "-y", "-i", str(source), str(original)], capture_output=True, check=True
    )
    store = Store(tmp_path / "data")
    store.set_setting("musicbrainz", False)
    song_id = "T" * 22
    metadata = {
        "song_id": song_id,
        "name": "Som de teste gerado localmente",
        "artist": "spoTano Tests",
        "genres": ["rock"],
    }
    store.add_playlist("https://open.spotify.com/playlist/" + "P" * 22)
    with store.connect() as db:
        db.execute("INSERT INTO tracks(id,metadata) VALUES(?,?)", (song_id, json.dumps(metadata)))
        db.execute("INSERT INTO membership VALUES(1,?,0)", (song_id,))
    events = []
    provider = SpotProvider(progress=events.append)

    class Local:
        def download(self, metadata, output):
            return provider.call(
                "local", {"source": str(original), "output": str(output), "metadata": metadata}
            )

    lib = Library(store, Local())
    result = lib.apply(SyncPlan(store.setting("revision"), [], downloads=[metadata]))
    assert not result["failures"], result
    assert any("convertendo áudio local" in event for event in events)
    row = Store(store.root).tracks()[0]
    validate_mp3(lib.music / row["path"])
    usb = tmp_path / "usb"
    usb.mkdir()
    exporter = Exporter(lib)
    exporter.apply(exporter.preview(usb))
    assert exporter.preview(usb).reused == 1
    assert exporter.preview(usb).copy == []


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg is not installed")
def test_reused_sdk_engine_converts_two_samples_without_spotify_refresh(tmp_path, monkeypatch):
    import time

    import requests
    import spotdl.download.downloader as sdk
    import spotdl.providers.audio.base as audio
    import spotdl.utils.deno
    import spotdl.utils.ffmpeg
    import spotdl.utils.spotify

    from spotano.downloads import DownloadEngine

    source = tmp_path / "generated.wav"
    with wave.open(str(source), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(22050)
        stream.writeframes(b"\x00\x00" * 22050)
    monkeypatch.setattr(spotdl.utils.ffmpeg, "get_ffmpeg_path", lambda: Path(shutil.which("ffmpeg")))
    monkeypatch.setattr(spotdl.utils.deno, "get_deno_path", lambda: None)
    monkeypatch.setattr(
        spotdl.utils.spotify.SpotifyClient,
        "init",
        lambda **kwargs: pytest.fail("Spotify initialization must not run"),
    )
    monkeypatch.setattr(
        sdk, "reinit_song", lambda song: pytest.fail("Saved metadata must not be fetched again")
    )
    monkeypatch.setattr(
        requests.Session, "request", lambda *args, **kwargs: pytest.fail("No network expected")
    )

    class SearchProvider:
        def __init__(self, **kwargs):
            pass

        def search(self, song, only_verified=False):
            return "https://example.invalid/synthetic-audio"

    for provider in ("youtube-music", "youtube"):
        monkeypatch.setitem(sdk.AUDIO_PROVIDERS, provider, SearchProvider)

    def local_audio(self, url, download=False):
        shutil.copyfile(source, audio.get_temp_path() / "same-source.wav")
        return {"id": "same-source", "ext": "wav"}

    monkeypatch.setattr(audio.AudioProvider, "get_download_metadata", local_audio)
    monkeypatch.setattr("spotano.matching.FastMatcher.candidates", lambda self, metadata: [
        {"url": "https://example.invalid/synthetic-audio", "score": 100}])
    events = []
    started = time.monotonic()
    engine = DownloadEngine(tmp_path / "engine", events.append)
    try:
        original_downloader = engine.downloader
        for letter in "AB":
            output = tmp_path / (letter + ".mp3")
            result = engine.download(
                {
                    "song_id": letter * 22,
                    "name": "Generated " + letter,
                    "artist": "spoTano",
                    "duration": 1,
                    "genres": [],
                    "album_id": None,
                },
                output,
            )
            validate_mp3(output)
            assert engine.downloader is original_downloader
            assert len(engine.audio_provider.audio_handler._progress_hooks) == 1
            if letter == "A":
                original_provider = engine.audio_provider
                assert result["metrics"]["audio_provider_initializations"] == 1
            else:
                assert engine.audio_provider is original_provider
                assert result["metrics"]["audio_provider_reused"]
        assert audio.get_temp_path() == tmp_path / "engine/provider-temp"
        assert sum("Mecanismo pronto" in event for event in events) == 1
        print(
            f"Reusable real SDK + FFmpeg: two generated samples in {time.monotonic() - started:.2f}s; one initialization"
        )
    finally:
        engine.close()
