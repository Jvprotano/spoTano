"""Compare real MP3 conversion locally, including remux, validation and concurrency."""

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spotano.audio import validate_mp3
from spotano.conversion import PROFILE_ARGS, MP3Converter, local_convert


async def trial(inputs, output, encoder, workers, ffmpeg):
    gate = asyncio.Semaphore(workers)

    async def convert(index, source):
        async with gate:
            converter = MP3Converter(local_convert, preference=encoder)
            target = output / f"{index}.mp3"
            started = time.perf_counter()
            ok, error = await converter(
                input_file=source,
                output_file=target,
                ffmpeg=ffmpeg,
                output_format="mp3",
                bitrate="192k",
                ffmpeg_args=PROFILE_ARGS,
            )
            if not ok:
                raise RuntimeError(error)
            info = validate_mp3(target)
            return {
                "sample": index,
                "seconds": time.perf_counter() - started,
                "duration": info.length,
                **converter.metrics,
            }

    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    tracks = await asyncio.gather(*(convert(i, p) for i, p in enumerate(inputs)))
    return {"encoder": encoder, "workers": workers, "wall_s": time.perf_counter() - started, "tracks": tracks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seconds", type=int, default=90)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    parser.add_argument("--rounds", type=int, default=2)
    args = parser.parse_args()
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or args.seconds < 1 or args.rounds < 1:
        parser.error("FFmpeg, duração e repetições válidas são necessários.")
    args.output.mkdir(parents=True, exist_ok=True)
    inputs = []
    # Match typical provider input (Opus/48 kHz). Preparation is outside timings.
    for index, source in enumerate(args.sources):
        target = args.output / f"input-{index}.opus"
        subprocess.run(
            [
                ffmpeg,
                "-nostdin",
                "-y",
                "-v",
                "error",
                "-i",
                str(source.resolve()),
                "-t",
                str(args.seconds),
                "-vn",
                "-map_metadata",
                "-1",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-c:a",
                "libopus",
                "-b:a",
                "128k",
                str(target),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        inputs.append(target)
    rows = []
    for repetition in range(args.rounds):
        for encoder in ("lame", "windows") if repetition % 2 == 0 else ("windows", "lame"):
            row = asyncio.run(
                trial(inputs, args.output / f"{repetition}-{encoder}", encoder, args.workers, ffmpeg)
            )
            row["round"] = repetition
            rows.append(row)
            (args.output / "results.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
            print(f"{encoder} round {repetition + 1}: {row['wall_s']:.3f}s", flush=True)


if __name__ == "__main__":
    main()
