"""Open an isolated demo catalog for library/resume visual QA, without network calls."""

import tempfile
import tkinter as tk
from pathlib import Path

from spotano.db import Store
from spotano.gui import App
from spotano.library import Library


class DemoProvider:
    def playlist(self, url):
        return {
            "name": "Playlist de demonstração",
            "total": 3,
            "tracks": [
                {"song_id": letter * 22, "name": name, "artist": "Artista de demonstração", "genres": []}
                for letter, name in zip("ABC", ["Primeira música", "Segunda música", "Terceira música"])
            ],
        }


directory = Path(tempfile.mkdtemp(prefix="spotano-recovery-ui-"))
store = Store(directory)
store.set_setting("musicbrainz", False)
lib = Library(store, DemoProvider())
lib.import_playlist("https://open.spotify.com/playlist/" + "P" * 22)
with store.connect() as db:
    db.execute("INSERT INTO download_pending VALUES(1,?)", ("B" * 22,))
root = tk.Tk()
app = App(root, directory)
root.title("spoTano · Biblioteca e retomada · QA")
root.geometry("1000x760")
root.mainloop()
