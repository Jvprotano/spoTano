import json
import time

import pytest
from test_library import P1, A, B, FakeProvider, snapshot, track

from spotano.catalogue import catalogue_match
from spotano.db import Store
from spotano.exporter import Exporter
from spotano.genres import GENRE_VERSION, GenreResolver
from spotano.library import Library
from spotano.paths import atomic_copy, atomic_json


def recording(**values):
    return {"song_id": A, "artist": "Felipe e Rodrigo", "artists": ["Felipe e Rodrigo"],
            "name": "Pós - Ao Vivo", "duration": 175, **values}


def apple(**values):
    return {"kind": "song", "trackId": 123, "artistName": "Felipe e Rodrigo",
            "trackName": "Pós (Ao Vivo)", "trackTimeMillis": 175577,
            "primaryGenreName": "Sertanejo", **values}


@pytest.mark.parametrize("changes", [
    {"artistName": "Outro artista"}, {"trackName": "Pós"}, {"trackTimeMillis": 220000},
    {"trackName": "Pós (Ao Vivo) Remix"}, {"trackName": "Pós 2 (Ao Vivo)"},
    {"trackTimeMillis": "invalid"}, {"primaryGenreName": None}, {"kind": "music-video"},
])
def test_catalogue_rejects_wrong_recording_and_malformed_results(changes):
    assert catalogue_match(recording(), [apple(**changes)]) is None


def test_catalogue_accepts_confirmed_song_and_rejects_conflicting_categories():
    assert catalogue_match(recording(), [apple()])["category"] == "Sertanejo"
    assert catalogue_match(recording(), [apple(), apple(trackId=124, primaryGenreName="Rock")]) is None
    assert catalogue_match(recording(duration=0), [apple()]) is None
    assert catalogue_match(recording(artist="東京", artists=["東京"]), [apple(artistName="大阪")]) is None


def test_duo_and_collaborator_credits_are_recognized_without_guessing_title():
    md = recording(artist="Hugo & Guilherme", artists=["Hugo & Guilherme", "Zé Vaqueiro"])
    assert catalogue_match(md, [apple(artistName="Hugo & Guilherme & Zé Vaqueiro")])
    assert catalogue_match(md, [apple(artistName="Zé Vaqueiro")]) is None


def test_lower_search_score_namesake_cannot_override_spotify_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(GenreResolver, "itunes", lambda *args: None)
    monkeypatch.setattr(GenreResolver, "deezer", lambda *args: None)
    resolver = GenreResolver(Store(tmp_path))
    md = recording(artist="BK", artist_id="S" * 22)
    responses = [
        {"artists": [{"id": "producer", "name": "BK", "score": 100,
                      "tags": [{"name": "electronic", "count": 1}]},
                     {"id": "rapper", "name": "BK", "score": 82}]},
        {"relations": [{"artist": {"id": "rapper"}}]},
        {"tags": [{"name": "rap", "count": 2}]},
    ]
    calls = []

    def request(source, url, params):
        calls.append((url, params))
        return responses.pop(0)

    monkeypatch.setattr(resolver, "request", request)
    assert resolver.resolve(md) == "Rap e Hip-Hop"
    assert calls[1][1]["resource"].endswith(md["artist_id"])
    assert calls[2][0].endswith("rapper")


def test_short_name_without_identity_does_not_trust_popularity(tmp_path, monkeypatch):
    resolver = GenreResolver(Store(tmp_path))
    monkeypatch.setattr(resolver, "request", lambda *args: {
        "artists": [{"id": "producer", "name": "BK", "score": 100,
                     "tags": [{"name": "electronic", "count": 1}]}]})
    assert resolver.musicbrainz("BK") == []


def test_catalogue_cache_reuses_other_tracks_and_survives_restart(tmp_path, monkeypatch):
    store = Store(tmp_path)
    resolver = GenreResolver(store)
    calls = []

    def request(source, url, params):
        calls.append(params)
        return {"results": [apple(), apple(trackId=124, trackName="Outra (Ao Vivo)")]}

    monkeypatch.setattr(resolver, "request", request)
    assert resolver.itunes(recording())["category"] == "Sertanejo"
    second = recording(song_id=B, name="Outra - Ao Vivo")
    assert GenreResolver(store).itunes(second)["category"] == "Sertanejo"
    assert len(calls) == 1


def test_catalogue_failure_is_not_saved_as_negative(tmp_path, monkeypatch):
    import requests

    store = Store(tmp_path)
    resolver = GenreResolver(store)
    monkeypatch.setattr(resolver, "deezer", lambda *args: None)
    monkeypatch.setattr(resolver, "resolve_artist", lambda metadata: "Outros")
    monkeypatch.setattr(resolver, "itunes", lambda metadata: (_ for _ in ()).throw(requests.Timeout("slow")))
    assert resolver.resolve(recording()) == "Outros"
    assert not store.rows("SELECT * FROM genre_evidence")
    assert not store.rows("SELECT * FROM genre_queries")


def test_collaborator_disagreement_is_not_decided_by_credit_order(tmp_path, monkeypatch):
    resolver = GenreResolver(Store(tmp_path))
    monkeypatch.setattr(resolver, "itunes", lambda metadata: None)
    monkeypatch.setattr(resolver, "deezer", lambda metadata: None)
    monkeypatch.setattr(resolver, "resolve_artist", lambda metadata: {
        "Felipe e Rodrigo": "Outros", "one": "Rock e Metal", "two": "Rap e Hip-Hop"
    }[metadata["artist"]])
    md = recording(artist_details=[{"name": "Felipe e Rodrigo"}, {"name": "one"}, {"name": "two"}])
    assert resolver.resolve(md) == "Outros"


def library(tmp_path, *tracks):
    store = Store(tmp_path / "data")
    store.set_setting("musicbrainz", False)
    store.add_playlist(P1)
    provider = FakeProvider()
    provider.snapshots[P1] = snapshot(*tracks)
    lib = Library(store, provider, validator=lambda path: None)
    lib.apply(lib.preview())
    return store, provider, lib


def test_export_removes_id_and_migrates_managed_old_filename(tmp_path):
    store, _, lib = library(tmp_path, track())
    exporter = Exporter(lib)
    destination = tmp_path / "usb"
    destination.mkdir()
    row = store.tracks()[0]
    root = destination / "spoTano"
    atomic_copy(lib.music / row["path"], root / row["path"], row["sha256"])
    atomic_json(root / ".spotano-manifest.json", {"version": 1, "files": {row["path"]: {
        "id": A, "source": row["path"], "sha256": row["sha256"]}}})
    plan = exporter.preview(destination)
    assert plan.remove == [row["path"]]
    assert plan.copy == ["Sertanejo/Artista - Cancao A.mp3"]
    exporter.apply(plan)
    assert list((root / ".spotano-trash").rglob("*.mp3"))
    assert not (root / row["path"]).exists()
    assert A in row["path"] and (lib.music / row["path"]).exists()
    assert exporter.preview(destination).reused == 1
    entry = next(iter(json.loads((root / ".spotano-manifest.json").read_text())["files"].values()))
    assert entry["id"] == A


@pytest.mark.parametrize("layout", ["unified", "playlists", "groups"])
def test_export_collision_after_case_accent_or_truncation_never_loses_a_track(tmp_path, layout):
    first, second = track(A), track(B)
    first["name"], second["name"] = "Canção " + "X" * 110 + "A", "CANCAO " + "X" * 110 + "B"
    store, _, lib = library(tmp_path, first, second)
    store.set_setting("output_layout", layout)
    destination = tmp_path / "usb"
    destination.mkdir()
    exporter = Exporter(lib)
    plan = exporter.preview(destination)
    assert len(plan.copy) == 2 and len({name.casefold() for name in plan.copy}) == 2
    assert all("[" not in name and A not in name and B not in name for name in plan.copy)
    exporter.apply(plan)
    assert exporter.preview(destination).reused == 2


def test_old_wrong_category_refreshes_without_downloading_again(tmp_path, monkeypatch):
    store, provider, lib = library(tmp_path, track())
    with store.connect() as db:
        db.execute("UPDATE tracks SET category='Eletronica'")
        db.execute("INSERT OR REPLACE INTO genre_evidence VALUES(?,?)",
                   (A, json.dumps({"version": GENRE_VERSION - 1, "category": "Eletronica"})))
    monkeypatch.setattr(GenreResolver, "resolve", lambda self, metadata: "Rap e Hip-Hop")
    result = lib.apply(lib.preview())
    assert result["downloaded"] == 0 and provider.downloads == [A]
    assert store.tracks()[0]["category"] == "Rap e Hip-Hop"
    assert len(list(lib.music.rglob("*.mp3"))) == 1


def test_old_positive_artist_cache_is_invalidated(tmp_path, monkeypatch):
    monkeypatch.setattr(GenreResolver, "itunes", lambda *args: None)
    monkeypatch.setattr(GenreResolver, "deezer", lambda *args: None)
    store = Store(tmp_path)
    with store.connect() as db:
        db.execute("INSERT INTO genre_cache VALUES(?,?,?)", ("bk", json.dumps({
            "version": GENRE_VERSION - 1, "tags": ["electronic"]}), time.time()))
    resolver = GenreResolver(store)
    monkeypatch.setattr(resolver, "musicbrainz", lambda artist: ["rap"])
    assert resolver.resolve(recording(artist="BK")) == "Rap e Hip-Hop"


def test_reliable_recording_genre_finishes_without_artist_network_requests(tmp_path, monkeypatch):
    resolver = GenreResolver(Store(tmp_path))
    monkeypatch.setattr(resolver, "itunes", lambda metadata: {"category": "Sertanejo", "tags": ["Sertanejo"]})
    monkeypatch.setattr(resolver, "resolve_artist", lambda metadata: pytest.fail("Unnecessary artist query"))
    assert resolver.resolve(recording()) == "Sertanejo"


def test_broad_catalogue_pop_does_not_override_specific_duet_evidence(tmp_path, monkeypatch):
    resolver = GenreResolver(Store(tmp_path))
    monkeypatch.setattr(resolver, "itunes", lambda metadata: {"category": "Pop", "tags": ["Pop"]})
    monkeypatch.setattr(resolver, "deezer", lambda metadata: None)
    monkeypatch.setattr(resolver, "resolve_artist", lambda metadata: "Sertanejo" if metadata["artist"] == "Guest" else "Outros")
    assert resolver.resolve(recording(artist_details=[{"name": "Felipe e Rodrigo"}, {"name": "Guest"}])) == "Sertanejo"


def test_deezer_validates_recording_before_album_lookup_and_caches_album(tmp_path, monkeypatch):
    resolver = GenreResolver(Store(tmp_path))
    calls = []

    def request(source, url, params):
        calls.append(url)
        if url.endswith("/search"):
            return {"data": [{"id": 1, "title": "Pós (Ao Vivo)", "duration": 175,
                              "artist": {"name": "Wrong"}, "album": {"id": 999}},
                             {"id": 2, "title": "Pós (Ao Vivo)", "duration": 175,
                              "artist": {"name": "Felipe e Rodrigo"}, "album": {"id": 42}}]}
        assert url.endswith("/42")
        return {"genres": {"data": [{"name": "Sertanejo"}]}}

    monkeypatch.setattr(resolver, "request", request)
    assert resolver.deezer(recording())["category"] == "Sertanejo"
    assert resolver.deezer(recording())["catalogue_id"] == 2
    assert len(calls) == 2


def test_classification_time_budget_stops_fallback_without_caching_failure(tmp_path, monkeypatch):
    from spotano.genres import GenreBudgetExceeded

    resolver = GenreResolver(Store(tmp_path))

    def expired(metadata):
        resolver.local.deadline = time.monotonic() - 1
        resolver.wait(0)

    monkeypatch.setattr(resolver, "itunes", expired)
    monkeypatch.setattr(resolver, "deezer", lambda metadata: resolver.wait(0))
    with pytest.raises(GenreBudgetExceeded):
        expired({})
    assert resolver.resolve(recording()) == "Outros"
    evidence = resolver.store.rows("SELECT * FROM genre_evidence")
    assert not evidence


def test_enabling_online_genres_does_not_reuse_a_disabled_unknown_result(tmp_path, monkeypatch):
    store = Store(tmp_path)
    store.set_setting("musicbrainz", False)
    resolver = GenreResolver(store)
    assert resolver.resolve(recording()) == "Outros"
    assert not store.rows("SELECT * FROM genre_evidence")
    store.set_setting("musicbrainz", True)
    monkeypatch.setattr(resolver, "itunes", lambda md: {"category": "Sertanejo"})
    assert resolver.resolve(recording()) == "Sertanejo"


def test_removing_artist_override_restores_automatic_category(tmp_path, monkeypatch):
    store = Store(tmp_path)
    md = recording(artist="Artist")
    with store.connect() as db:
        db.execute("INSERT INTO genre_cache VALUES(?,?,?)", ("artist", json.dumps({
            "version": GENRE_VERSION, "tags": ["rock"]}), time.time()))
        db.execute("INSERT INTO artist_categories VALUES(?,?)", ("artist", "Sertanejo"))
    assert GenreResolver(store).resolve(md) == "Sertanejo"
    with store.connect() as db:
        db.execute("DELETE FROM artist_categories")
    monkeypatch.setattr(GenreResolver, "itunes", lambda md: None)
    monkeypatch.setattr(GenreResolver, "deezer", lambda md: None)
    assert GenreResolver(store).resolve(md) == "Rock e Metal"
