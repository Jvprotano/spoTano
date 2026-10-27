"""Classification before downloads and immediate, scoped reorganization afterwards."""

from test_library import P1, A, B, C, FakeProvider, snapshot, track

from spotano.db import Store
from spotano.library import Library


def collection(tmp_path):
    store = Store(tmp_path / "data")
    store.set_setting("musicbrainz", False)
    store.set_setting("download_options", {"categories": True, "metadata": True})
    provider = FakeProvider()
    other = {**track(C), "artist": "Outro artista", "artists": ["Outro artista"]}
    provider.snapshots[P1] = snapshot(track(A), track(B), other)
    lib = Library(store, provider, validator=lambda path: None)
    lib.import_playlist(P1)
    return store, provider, lib


def test_artist_correction_before_download_and_future_tracks_respects_individual_choices(tmp_path):
    store, provider, lib = collection(tmp_path)
    lib.correct_genre(A, "Rock e Metal")
    lib.correct_artist(B, "Pop")
    assert provider.downloads == []
    rows = {row["id"]: row for row in store.tracks()}
    assert rows[A]["override"] == "Rock e Metal" and rows[B]["category"] == "Pop"
    assert rows[C]["classified"] == 0  # Unrelated music is not reclassified.
    assert all(row["path"] is None for row in rows.values())
    lib.apply(lib.preview(saved=True))
    rows = {row["id"]: row for row in store.tracks()}
    assert rows[A]["path"].startswith("Rock e Metal/")
    assert rows[B]["path"].startswith("Pop/")
    assert rows[C]["path"].startswith("Sertanejo/")
    future = track("D" * 22)
    provider.snapshots[P1] = snapshot(track(A), track(B), future)
    lib.refresh_playlists([1])
    lib.apply(lib.preview(saved=True))
    assert next(row for row in store.tracks() if row["id"] == future["song_id"])["path"].startswith("Pop/")


def test_correction_moves_existing_files_and_tags_immediately_without_downloading(tmp_path):
    from mutagen.id3 import ID3

    store, provider, lib = collection(tmp_path)
    lib.apply(lib.preview(saved=True))
    before = {row["id"]: row for row in store.tracks()}
    provider.downloads.clear()
    lib.correct_genre(A, "Rock e Metal")
    lib.correct_artist(B, "Pop")
    after = {row["id"]: row for row in store.tracks()}
    assert after[A]["path"].startswith("Rock e Metal/")
    assert after[B]["path"].startswith("Pop/")
    assert after[C] == before[C]
    for track_id, category in [(A, "Rock e Metal"), (B, "Pop")]:
        assert not (lib.music / before[track_id]["path"]).exists()
        assert ID3(lib.music / after[track_id]["path"])["TCON"].text == [category]
        assert lib.available(after[track_id])
    assert provider.downloads == []
    assert len(list(lib.music.rglob("*.mp3"))) == 3
