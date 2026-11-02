"""Fast Windows MP3 encoding with validated headers and a LAME fallback."""

import os
import subprocess
import tempfile
import time
from pathlib import Path

from mutagen import MutagenError

from .audio import validate_mp3

ENCODERS = {"windows": "Rápida · Windows", "lame": "Tradicional · LAME"}
PROFILE_ARGS = "-vn -loglevel info -map_metadata -1 -ar 44100 -ac 2 -id3v2_version 3"


class MP3Converter:
    def __init__(self, convert, progress=lambda message: None, preference="windows"):
        self.convert = convert
        self.progress = progress
        self.native = os.name == "nt" and preference == "windows"
        self.metrics = {}

    async def __call__(self, **options):
        self.metrics = {"encoder": "libmp3lame", "encoder_fallback": False}
        if not self.native or options.get("output_format", "mp3") != "mp3":
            return await self.convert(**options)
        target = Path(options["output_file"])
        started = time.monotonic()
        # Never install the native encoder's malformed Xing frame counts. FFmpeg
        # parses the individual MP3 frames on stream copy and rebuilds the header.
        with tempfile.TemporaryDirectory(prefix="encoder-", dir=target.parent) as directory:
            raw, fixed = Path(directory) / "raw.mp3", Path(directory) / "fixed.mp3"
            handler = options.get("progress_handler")
            try:
                self.progress("Convertendo com FFmpeg para MP3 · Windows")
                success, error = await self.convert(
                    **{
                        **options,
                        "output_file": raw,
                        "ffmpeg_args": PROFILE_ARGS + " -c:a mp3_mf",
                        "progress_handler": (lambda value: handler(min(99, value))) if handler else None,
                    }
                )
                if not success:
                    raise RuntimeError((error or {}).get("error", "Encoder Windows indisponível"))
                self.progress("Convertendo com FFmpeg para MP3 · finalizando cabeçalho")
                remux_started = time.monotonic()
                success, error = await self.convert(
                    **{
                        **options,
                        "input_file": raw,
                        "output_file": fixed,
                        "ffmpeg_args": "-vn -loglevel error -map_metadata -1 -c:a copy -id3v2_version 3",
                        "progress_handler": None,
                    }
                )
                if not success:
                    raise RuntimeError((error or {}).get("error", "Falha ao finalizar o MP3"))
                validate_mp3(fixed)
                os.replace(fixed, target)
                self.metrics.update(encoder="mp3_mf", remux_s=round(time.monotonic() - remux_started, 3))
                if handler:
                    handler(100)
                return True, None
            except (OSError, ValueError, RuntimeError, MutagenError, subprocess.TimeoutExpired) as exc:
                from .telemetry import sanitize

                self.native = False  # Do not repeat a failing encoder on every song.
                self.metrics.update(
                    encoder_fallback=True,
                    native_error=sanitize(str(exc))[:700],
                    native_attempt_s=round(time.monotonic() - started, 3),
                )
                self.progress("Conversão rápida indisponível; usando LAME nesta sessão.")
        return await self.convert(**options)


async def local_convert(**options):
    """Local imports avoid loading the Spotify SDK just to run FFmpeg."""
    import asyncio
    import shlex
    import subprocess

    command = [
        str(options["ffmpeg"]),
        "-nostdin",
        "-y",
        "-i",
        str(options["input_file"]),
        "-c:a",
        "libmp3lame",
        "-b:a",
        "192k",
        *shlex.split(options.get("ffmpeg_args") or PROFILE_ARGS),
        str(options["output_file"]),
    ]
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    result = await asyncio.to_thread(subprocess.run, command, capture_output=True, timeout=180, **flags)
    return result.returncode == 0, {"error": result.stderr.decode("utf-8", errors="replace")[-3000:]}
