import asyncio
from pathlib import Path

from spotano.conversion import MP3Converter


def test_native_failure_reuses_source_and_disables_further_native_attempts(tmp_path):
    calls = []

    async def convert(**options):
        calls.append(options)
        if "mp3_mf" in options["ffmpeg_args"]:
            return False, {"error": "encoder unavailable"}
        Path(options["output_file"]).write_bytes(b"fallback")
        return True, None

    converter = MP3Converter(convert)
    converter.native = True
    source = tmp_path / "source.opus"
    source.write_bytes(b"original")
    options = dict(input_file=source, output_file=tmp_path / "target.mp3", ffmpeg_args="-c:a libmp3lame")
    assert asyncio.run(converter(**options)) == (True, None)
    assert converter.metrics["encoder_fallback"]
    assert source.read_bytes() == b"original"
    assert asyncio.run(converter(**options)) == (True, None)
    assert len(calls) == 3
    assert calls[1]["input_file"] == source and calls[2]["input_file"] == source


def test_invalid_native_output_cannot_replace_target(tmp_path, monkeypatch):
    target = tmp_path / "target.mp3"
    target.write_bytes(b"existing")

    async def convert(**options):
        if Path(options["output_file"]) == target:
            assert target.read_bytes() == b"existing"
            return False, {"error": "fallback failed"}
        Path(options["output_file"]).write_bytes(b"invalid")
        return True, None

    converter = MP3Converter(convert)
    converter.native = True
    assert (
        asyncio.run(converter(input_file=tmp_path / "input", output_file=target, ffmpeg_args=""))[0] is False
    )
    assert target.read_bytes() == b"existing"
    assert not converter.native
