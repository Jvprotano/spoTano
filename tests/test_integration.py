"""Actual FFmpeg/MP3 and subprocess integration; no copyrighted samples/network."""

import json
import shutil
import subprocess
import wave

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
    provider = SpotProvider()

    class Local:
        def download(self, metadata, output):
            return provider.call(
                "local", {"source": str(original), "output": str(output), "metadata": metadata}
            )

    lib = Library(store, Local())
    result = lib.apply(SyncPlan(store.setting("revision"), [], downloads=[metadata]))
    assert not result["failures"], result
    row = Store(store.root).tracks()[0]
    validate_mp3(lib.music / row["path"])
    usb = tmp_path / "usb"
    usb.mkdir()
    exporter = Exporter(lib)
    exporter.apply(exporter.preview(usb))
    assert exporter.preview(usb).reused == 1
    assert exporter.preview(usb).copy == []
    # Apply extras to the real MP3 and return to flat/tag-free without downloading.
    from mutagen.mp3 import MP3

    store.set_setting("download_options", {"categories": True, "artists": True, "metadata": True})
    lib.reorganize()
    row = store.tracks()[0]
    assert row["path"].startswith("Rock e Metal/spoTano Tests/")
    assert MP3(lib.music / row["path"]).tags["TIT2"].text == [metadata["name"]]
    validate_mp3(lib.music / row["path"])
    store.set_setting("download_options", {})
    lib.reorganize()
    row = store.tracks()[0]
    assert "/" not in row["path"] and MP3(lib.music / row["path"]).tags is None
    validate_mp3(lib.music / row["path"])
