"""Flat downloads, independent extras, safe retagging and fixed estimates."""

import itertools
import sqlite3

import pytest
from test_library import P1, A, FakeProvider

from spotano.audio import write_tags
from spotano.db import SCHEMA, Store
from spotano.exporter import Exporter
from spotano.library import Library
from spotano.options import OPTIONS, download_options, option_costs


def collection(tmp_path):
    store = Store(tmp_path / "data")
    store.add_playlist(P1)
    provider = FakeProvider()
    return store, provider, Library(store, provider, validator=lambda p: None)


def test_simple_default_skips_classification_and_exports_flat(tmp_path, monkeypatch):
    store, provider, lib = collection(tmp_path)

    def unwanted(*args):
        pytest.fail("Simple download must never classify genres")

    store.set_setting("output_layout", "unified")
    monkeypatch.setattr("spotano.library.GenreResolver.resolve", unwanted)
    result = lib.apply(lib.preview())
    assert result["downloaded"] == 1 and not result["failures"]
    assert download_options(store) == dict.fromkeys(OPTIONS, False)
    row = store.tracks()[0]
    assert "/" not in row["path"] and "\\" not in row["path"]
    assert row["tagged"] == 0
    destination = tmp_path / "usb"
    destination.mkdir()
    plan = Exporter(lib).preview(destination)
    Exporter(lib).apply(plan)
    assert len(list(plan.root.glob("*.mp3"))) == 1
    assert provider.downloads == [A]
    assert {row["action"] for row in store.rows("SELECT action FROM history")} <= {"sync", "export"}


@pytest.mark.parametrize("categories,artists,metadata", list(itertools.product((False, True), repeat=3)))
def test_options_work_independently(tmp_path, categories, artists, metadata, monkeypatch):
    from mutagen.id3 import ID3, ID3NoHeaderError

    store, provider, lib = collection(tmp_path)
    store.set_setting("musicbrainz", False)
    store.set_setting("download_options", dict(categories=categories, artists=artists, metadata=metadata))
    calls = []
    monkeypatch.setattr(
        "spotano.library.GenreResolver.resolve", lambda self, data: calls.append(data) or "Pop"
    )
    assert not lib.apply(lib.preview())["failures"]
    row = store.tracks()[0]
    folders = (["Pop"] if categories else []) + (["Artista"] if artists else [])
    assert row["path"].split("/")[:-1] == folders
    assert bool(calls) == categories
    path = lib.music / row["path"]
    if metadata:
        assert ID3(path)["TPE1"].text == ["Artista"]
        assert ID3(path).version[:2] == (2, 3)
    else:
        with pytest.raises(ID3NoHeaderError):
            ID3(path)
    # Existing files must be retagged/reorganized without another audio download.
    store.set_setting("download_options", dict.fromkeys(OPTIONS, False))
    lib.reorganize()
    fresh = store.tracks()[0]
    assert "/" not in fresh["path"] and lib.available(fresh)
    assert fresh["tagged"] == 0 and provider.downloads == [A]
    if metadata:
        with pytest.raises(ID3NoHeaderError):
            ID3(lib.music / fresh["path"])
        assert list((store.root / "trash").rglob("*.mp3"))


def test_retag_modified_file_preserves_bytes(tmp_path):
    store, _, lib = collection(tmp_path)
    lib.apply(lib.preview())
    path = lib.music / store.tracks()[0]["path"]
    path.write_bytes(b"user modification")
    store.set_setting("download_options", {"metadata": True})
    with pytest.raises(ValueError, match="modificado"):
        lib.reorganize()
    assert path.read_bytes() == b"user modification"


def test_unknown_genre_is_not_reclassified_on_every_sync(tmp_path, monkeypatch):
    store, _, lib = collection(tmp_path)
    store.set_setting("download_options", {"categories": True})
    calls = []
    monkeypatch.setattr(
        "spotano.library.GenreResolver.resolve", lambda self, data: calls.append(data) or "Outros"
    )
    lib.apply(lib.preview())
    lib.apply(lib.preview())
    lib.reorganize()
    assert len(calls) == 1


def test_flat_same_title_tracks_have_distinct_names(tmp_path):
    from test_library import B, snapshot, track

    store, provider, lib = collection(tmp_path)
    provider.snapshots[P1] = snapshot(track(), {**track(B), "name": track()["name"]})
    result = lib.apply(lib.preview())
    assert result["downloaded"] == 2
    assert len(list(lib.music.glob("*.mp3"))) == 2
    assert all(lib.available(row) for row in store.tracks())


def test_tag_write_and_removal_preserve_audio_frames(tmp_path):
    from mutagen.id3 import ID3

    path = tmp_path / "test.mp3"
    audio = b"audio frames" * 100
    path.write_bytes(audio)
    metadata = dict(
        name="Título",
        artist="Artista",
        artists=["Artista", "Convidado"],
        album_name="Álbum",
        album_artist="Artista",
        year=2026,
        track_number=2,
    )
    write_tags(path, metadata, True)
    assert ID3(path)["TIT2"].text == ["Título"]
    assert "APIC" not in ID3(path)
    write_tags(path, metadata, False)
    assert path.read_bytes() == audio


def test_estimates_are_fixed_and_do_not_read_user_logs(monkeypatch):
    def unwanted(*args, **kwargs):
        pytest.fail("Fixed estimates must not read user history or log files")

    monkeypatch.setattr(Store, "rows", unwanted)
    monkeypatch.setattr("pathlib.Path.open", unwanted)
    costs = option_costs()
    assert costs == {"categories": "+~8 s/música", "artists": "+<1 s/música", "metadata": "+~0,1 s/música"}
    costs["categories"] = "changed"
    assert option_costs()["categories"] == "+~8 s/música"


def test_existing_catalog_migrates_to_simple_without_losing_rows(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    with sqlite3.connect(root / "library.sqlite3") as db:
        db.executescript(SCHEMA)
        db.execute("INSERT INTO settings VALUES('by_genre','true')")
        db.execute(
            "INSERT INTO tracks(id,metadata,path,sha256) VALUES(?,?,?,?)", (A, "{}", "old.mp3", "hash")
        )
    store = Store(root)
    assert not any(download_options(store).values())
    assert store.tracks()[0]["path"] == "old.mp3"
    assert store.tracks()[0]["tagged"] == 1
    store.set_setting("download_options", {"metadata": True})
    assert download_options(Store(root))["metadata"] is True


def test_interrupted_optional_tag_install_recovers_flags_and_audio(tmp_path, monkeypatch):
    store, provider, lib = collection(tmp_path)
    lib.apply(lib.preview())
    store.set_setting("download_options", {"metadata": True})
    monkeypatch.setattr(lib.files, "finish", lambda *_: (_ for _ in ()).throw(OSError("interrupted")))
    with pytest.raises(OSError, match="interrupted"):
        lib.reorganize()
    resumed = Library(Store(store.root), provider, validator=lambda path: None)
    row = resumed.store.tracks()[0]
    assert row["tagged"] == 1 and resumed.available(row)
    assert not resumed.store.rows("SELECT * FROM file_transitions")
    resumed.reorganize()
    assert provider.downloads == [A]
