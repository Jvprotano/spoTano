"""Real warm SDK/FFmpeg pipeline with generated audio served only on loopback."""

import argparse
import functools
import http.server
import json
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spotano.db import Store
from spotano.library import Library, validate_mp3
from spotano.provider import SpotProvider


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracks", type=int, default=200)
    parser.add_argument("--workers", type=int, default=4, choices=range(1, 5))
    parser.add_argument("--conversions", type=int, default=3, choices=range(1, 5))
    parser.add_argument("--exe", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    original_popen = subprocess.Popen
    processes = []
    peak = 0

    def launch(command, **kwargs):
        nonlocal peak
        if "--worker" in command:
            if args.exe:
                command = [str(args.exe.resolve()), *command[-3:]]
            process = original_popen(command, **kwargs)
            processes.append(process)
            peak = max(peak, sum(p.poll() is None for p in processes))
            return process
        return original_popen(command, **kwargs)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *_):
            pass

    with tempfile.TemporaryDirectory(prefix="spotano-sdk-benchmark-") as temporary:
        root = Path(temporary)
        audio = root / "own-generated.wav"
        with wave.open(str(audio), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(22050)
            stream.writeframes(b"\x00\x00" * 22050)
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0),
                    functools.partial(Handler, directory=str(root)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        tracks = [{"song_id": f"{i:022d}", "name": f"Own generated {i}", "artist": "spoTano tests",
                   "duration": 1, "genres": ["sertanejo"], "album_id": None,
                   "download_url": f"http://127.0.0.1:{server.server_port}/own-generated.wav"}
                  for i in range(args.tracks)]
        events = []

        class Provider(SpotProvider):
            def playlist(self, url):
                return {"name": "Own generated SDK benchmark", "tracks": tracks,
                        "total": len(tracks), "skipped": 0}

        store = Store(root / "data")
        store.set_setting("download_workers", args.workers)
        store.set_setting("conversion_workers", args.conversions)
        store.set_setting("musicbrainz", False)
        provider = Provider(progress=events.append)
        lib = Library(store, provider)
        lib.import_playlist("https://open.spotify.com/playlist/" + "P" * 22)
        began = time.monotonic()
        try:
            with patch("spotano.downloads.subprocess.Popen", launch):
                result = lib.apply(lib.preview(force=True))
            assert result["downloaded"] == args.tracks and not result["failures"], result
            assert peak <= args.workers
            assert all(process.poll() is not None for process in processes)
            assert len(list(lib.music.rglob("*.mp3"))) == args.tracks
            for row in store.tracks():
                validate_mp3(lib.music / row["path"])
                assert lib.available(row)
            assert lib.preview().retained == args.tracks
            summary = json.loads((Path(result["run_directory"]) / "summary.json").read_text(encoding="utf-8"))
            report = {"tracks": args.tracks, "workers": args.workers, "worker_processes": len(processes),
                      "peak_active_workers": peak,
                      "worker_restarts": sum(r.get("evidence", {}).get("metrics", {})
                                             .get("worker_restarts", 0) for r in summary["tracks"]),
                      "seconds": round(time.monotonic() - began, 3), "downloaded": result["downloaded"],
                      "failed": len(result["failures"]), "profile_and_hash_verified": args.tracks,
                      "conversions": args.conversions,
                      "extractor_initializations": sum(r.get("evidence", {}).get("metrics", {})
                                                       .get("audio_provider_initializations", 0)
                                                       for r in summary["tracks"]),
                      "extractor_reuses": sum(bool(r.get("evidence", {}).get("metrics", {})
                                                  .get("audio_provider_reused")) for r in summary["tracks"]),
                      "view_extractions": sum(r.get("evidence", {}).get("metrics", {}).get("view_extractions", 0)
                                              for r in summary["tracks"]),
                      "mode": "frozen" if args.exe else "source",
                      "phase_worker_seconds": {phase: round(sum(r.get("evidence", {}).get("metrics", {})
                          .get(phase, 0) for r in summary["tracks"]), 3) for phase in (
                              "initialization_s", "search_s", "extraction_s", "transfer_s",
                              "conversion_queue_s", "conversion_s", "tags_s")},
                      "kind": "real SDK/FFmpeg; generated 1s audio; loopback; not YouTube throughput"}
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(report, indent=2), flush=True)
        except BaseException:
            print("\n".join(str(e) for e in events[-25:]), flush=True)
            raise
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)


if __name__ == "__main__":
    main()
