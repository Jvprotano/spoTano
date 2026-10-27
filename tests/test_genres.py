import pytest

from spotano.genres import classify


@pytest.mark.parametrize(
    "genre,expected",
    [
        ("sertanejo universitário", "Sertanejo"),
        ("pagode baiano", "Pagode e Samba"),
        ("bossa nova", "MPB"),
        ("funk carioca", "Funk Brasileiro"),
        ("indie rock", "Rock e Metal"),
        ("brazilian hip hop", "Rap e Hip-Hop"),
        ("progressive house", "Eletronica"),
        ("forró", "Forro e Piseiro"),
        ("unknown", "Outros"),
        ("dance pop", "Pop"),
    ],
)
def test_broad_categories(genre, expected):
    assert classify([genre]) == expected


def test_short_keywords_do_not_match_inside_unrelated_words():
    assert classify(["crap", "popular artist", "metallurgy"]) == "Outros"
    assert classify(["thrash metal"]) == "Rock e Metal"


def resolver_fixture(tmp_path, monkeypatch, responses):
    from types import SimpleNamespace

    from spotano.db import Store
    from spotano.genres import GenreResolver

    calls, logs = [], []

    def get(self, url, **kwargs):
        calls.append((url, kwargs["params"]))
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None, json=lambda: response)

    monkeypatch.setattr("requests.Session.get", get)
    store = Store(tmp_path)
    resolver = GenreResolver(store, logs.append)
    resolver.wait = lambda seconds: None
    return store, resolver, calls, logs


def claim(value):
    return {"mainsnak": {"datavalue": {"value": value}}, "rank": "normal"}


def test_hugo_guilherme_falls_back_to_wikidata_and_retries_old_empty_cache(tmp_path, monkeypatch):
    import json
    import time

    responses = [
        {"artists": [{"id": "mb-hugo", "name": "Hugo & Guilherme", "score": 100}]},
        {"search": [{"id": "Q65170605"}]},
        {
            "entities": {
                "Q65170605": {
                    "labels": {"pt": {"value": "Hugo & Guilherme"}},
                    "claims": {"P31": [claim({"id": "Q215380"})], "P136": [claim({"id": "Q1958273"})]},
                }
            }
        },
        {"entities": {"Q1958273": {"labels": {"pt": {"value": "sertanejo"}}}}},
    ]
    store, resolver, calls, logs = resolver_fixture(tmp_path, monkeypatch, responses)
    with store.connect() as db:
        db.execute("INSERT INTO genre_cache VALUES(?,?,?)", ("Hugo & Guilherme", json.dumps([]), time.time()))
    assert resolver.resolve({"artist": "Hugo & Guilherme", "genres": []}) == "Sertanejo"
    assert len(calls) == 4 and any("Wikidata" in line for line in logs)
    assert resolver.resolve({"artist": "Hugo e Guilherme", "genres": []}) == "Sertanejo"
    assert len(calls) == 4


def test_specific_genre_beats_broad_latin_tag_and_positive_cache_persists(tmp_path, monkeypatch):
    from spotano.genres import GenreResolver

    responses = [
        {
            "artists": [
                {
                    "name": "Gusttavo Lima",
                    "id": "mb-gl",
                    "score": 100,
                    "tags": [{"name": "latin", "count": 3}, {"name": "sertanejo", "count": 2}],
                }
            ]
        }
    ]
    store, resolver, calls, logs = resolver_fixture(tmp_path, monkeypatch, responses)
    metadata = {"artist": "Gusttavo Lima", "genres": []}
    assert resolver.resolve(metadata) == "Sertanejo"
    assert GenreResolver(store).resolve(metadata) == "Sertanejo" and len(calls) == 1


def test_network_errors_are_visible_and_never_cached_as_missing_genres(tmp_path, monkeypatch):
    import requests

    from spotano.genres import GenreResolver

    responses = [requests.ConnectionError("offline"), requests.ConnectionError("offline")]
    store, resolver, calls, logs = resolver_fixture(tmp_path, monkeypatch, responses)
    metadata = {"artist": "Gusttavo Lima", "genres": []}
    assert resolver.resolve(metadata) == "Outros"
    assert store.rows("SELECT * FROM genre_cache") == []
    assert any("falha" in line for line in logs)
    responses.append(
        {
            "artists": [
                {
                    "name": "Gusttavo Lima",
                    "id": "mb-gl",
                    "score": 100,
                    "tags": [{"name": "sertanejo", "count": 2}],
                }
            ]
        }
    )
    retried = GenreResolver(store)
    retried.wait = lambda seconds: None
    assert retried.resolve(metadata) == "Sertanejo"


def test_new_negative_cache_expires_after_one_day(tmp_path, monkeypatch):
    import time

    from spotano.genres import GenreResolver

    responses = [{"artists": []}, {"search": []}]
    store, resolver, calls, _ = resolver_fixture(tmp_path, monkeypatch, responses)
    metadata = {"artist": "Some Band", "genres": []}
    assert resolver.resolve(metadata) == "Outros" and len(calls) == 2
    assert GenreResolver(store).resolve(metadata) == "Outros" and len(calls) == 2
    with store.connect() as db:
        db.execute("UPDATE genre_cache SET fetched_at=?", (time.time() - 2 * 86400,))
    responses.append(
        {
            "artists": [
                {"name": "Some Band", "id": "mb-id", "score": 100, "tags": [{"name": "rock", "count": 1}]}
            ]
        }
    )
    again = GenreResolver(store)
    again.wait = lambda seconds: None
    assert again.resolve(metadata) == "Rock e Metal" and len(calls) == 3


def test_wikidata_rejects_conflicting_artist_identity(tmp_path, monkeypatch):
    responses = [
        {"artists": []},
        {"search": [{"id": "Q123"}]},
        {
            "entities": {
                "Q123": {
                    "labels": {"pt": {"value": "Some Band"}},
                    "claims": {
                        "P31": [claim({"id": "Q215380"})],
                        "P136": [claim({"id": "Q1958273"})],
                        "P1902": [claim("different-spotify-id")],
                    },
                }
            }
        },
    ]
    _, resolver, calls, _ = resolver_fixture(tmp_path, monkeypatch, responses)
    assert resolver.resolve({"artist": "Some Band", "artist_id": "correct-id"}) == "Outros"
    assert len(calls) == 3
