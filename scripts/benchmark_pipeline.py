"""Exercise 200-track first download/resume/reuse with simulated network/audio.

This measures orchestration and catalog/file integrity, never YouTube throughput.
"""

import argparse
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spotano.db import Store
from spotano.library import Library


class Provider:
    def __init__(self, count):
        self.tracks = [{"song_id": f"{index:022d}", "name": f"Generated {index}",
                        "artist": f"Generated artist {index % 10}", "genres": ["sertanejo"],
                        "duration": 180} for index in range(count)]
        self.calls, self.active, self.peak = 0, 0, 0
        self.lock = threading.Lock()
        self.fail = {self.tracks[19]["song_id"]} if count >= 20 else set()

    def playlist(self, url):
        return {"name": "200-track synthetic benchmark", "total": len(self.tracks),
                "skipped": 0, "tracks": self.tracks}

    def download(self, metadata, output):
        with self.lock:
            self.calls += 1
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            time.sleep(0.02)
            if metadata["song_id"] in self.fail:
                raise OSError("Synthetic interrupted transfer")
            output.write_bytes(metadata["song_id"].encode() * 128)
        finally:
            with self.lock:
                self.active -= 1


def benchmark(workers, count):
    with tempfile.TemporaryDirectory(prefix=f"spotano-benchmark-{workers}-") as directory:
        store = Store(Path(directory))
        store.set_setting("musicbrainz", False)
        store.set_setting("download_workers", workers)
        provider = Provider(count)
        lib = Library(store, provider, validator=lambda path: None)
        lib.import_playlist("https://open.spotify.com/playlist/" + "P" * 22)
        started = time.monotonic()
        first = lib.apply(lib.preview(force=True))
        elapsed = time.monotonic() - started
        assert first["downloaded"] == count - len(provider.fail)
        assert provider.peak <= workers
        provider.fail.clear()
        resume = lib.apply(lib.preview())
        assert resume["downloaded"] == (1 if count >= 20 else 0)
        assert resume["reused"] == count - (1 if count >= 20 else 0)
        before = provider.calls
        reused = lib.apply(lib.preview())
        assert reused["reused"] == count and provider.calls == before
        assert len(list(lib.music.rglob("*.mp3"))) == count
        assert not store.rows("SELECT * FROM file_transitions")
        with store.connect() as db:
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        return {"workers": workers, "tracks": count, "first_batch_seconds": round(elapsed, 3),
                "peak_downloads": provider.peak, "resume_downloads": resume["downloaded"],
                "final_reused": reused["reused"], "final_files": count,
                "kind": "synthetic_network_and_audio; not a YouTube speed prediction"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracks", type=int, default=200)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rows = []
    for workers in (2, 3, 4):
        row = benchmark(workers, args.tracks)
        rows.append(row)
        print(json.dumps(row), flush=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(rows, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
