"""Exit without cleanup after 73 durable saves, like a terminated desktop process."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spotano.db import Store  # noqa: E402
from spotano.library import Library  # noqa: E402


class Provider:
    def download(self, metadata, output):
        output.write_bytes(b"replacement audio: " + metadata["song_id"].encode())


saved = 0


def progress(message):
    global saved
    if isinstance(message, str) and message.startswith("Salvo ·"):
        saved += 1
        if saved == 73:
            os._exit(17)


store = Store(Path(sys.argv[1]))
library = Library(store, Provider(), progress, validator=lambda path: None)
library.apply(library.preview(force=sys.argv[2] == "force", playlist_ids=[1], saved=True))
