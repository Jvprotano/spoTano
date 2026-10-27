"""Private subprocess fixture: exercise real IPC without external audio/network."""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spotano import downloads
from spotano.provider import worker


class Engine:
    def __init__(self, root, progress, settings=None):
        self.root, self.progress = root, progress
        with (root / "initializations.txt").open("a", encoding="utf-8") as stream:
            stream.write("initialized\n")
        progress("Fixture mechanism ready")

    def download(self, metadata, output):
        self.progress("Fixture download started")
        marker = Path(output).parent / "crashed-once"
        if metadata["name"] == "crash_once" and not marker.exists():
            marker.write_text("yes")
            os._exit(42)
        if metadata["name"] == "crash_always":
            os._exit(43)
        if metadata["name"] == "slow":
            time.sleep(30)
        else:
            time.sleep(0.05)
        Path(output).write_bytes(metadata["song_id"].encode())
        return str(output)

    def close(self):
        pass


downloads.DownloadEngine = Engine
worker(Path(sys.argv[1]), Path(sys.argv[2]))
