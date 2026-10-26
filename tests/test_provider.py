"""Regressions from exercising the real spotDL boundary."""

import json
from pathlib import Path

import pytest

from spotano.provider import worker


@pytest.mark.parametrize("outside", [False, True])
def test_download_installs_returned_filename_and_rejects_escape(tmp_path, monkeypatch, outside):
    import spotdl.download.downloader
    import spotdl.utils.deno
    import spotdl.utils.ffmpeg
    import spotdl.utils.spotify

    monkeypatch.setattr(spotdl.utils.ffmpeg, "get_ffmpeg_path", lambda: Path("ffmpeg"))
    monkeypatch.setattr(spotdl.utils.deno, "get_deno_path", lambda: None)
    monkeypatch.setattr(spotdl.utils.spotify.SpotifyClient, "init", lambda **kwargs: None)
    staging = tmp_path / "stage"
    staging.mkdir()
    expected = staging / "audio.mp3"

    class Downloader:
        def __init__(self, settings, loop):
            # A literal path is interpreted as a directory by spotDL 4.6.0.
            assert "{title}" in settings["output"]

        def download_song(self, song):
            actual = (tmp_path if outside else staging) / "Provider chosen title.mp3"
            actual.write_bytes(b"test audio")
            return song, actual

    monkeypatch.setattr(spotdl.download.downloader, "Downloader", Downloader)
    request, result = tmp_path / "request.json", tmp_path / "response.json"
    request.write_text(
        json.dumps(
            {
                "action": "download",
                "payload": {"metadata": {"name": "Title", "artist": "Artist"}, "output": str(expected)},
            }
        )
    )
    worker(request, result)
    response = json.loads(result.read_text(encoding="utf-8"))
    if outside:
        assert "error" in response and not expected.exists()
    else:
        assert response["result"] == str(expected)
        assert expected.is_file() and expected.read_bytes() == b"test audio"
