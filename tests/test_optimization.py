import json
import shutil
import subprocess
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_library import P1, A, FakeProvider, snapshot, track

from spotano.audio import validate_duration
from spotano.db import Store
from spotano.downloads import DownloadEngine
from spotano.exporter import Exporter
from spotano.genres import GENRE_VERSION, GenreResolver, classify
from spotano.library import Library, validate_mp3
from spotano.matching import FastMatcher, MatchError, canonical_youtube, rank_candidate
from spotano.paths import digest
from spotano.telemetry import sanitize


def result(name="Song", artist="Artist", duration=180, video="abcdefghijk", **kwargs):
    from spotdl.types.result import Result

    return Result(source="YouTubeMusic", url="https://www.youtube.com/watch?v=" + video,
                  name=name, author=artist, artists=(artist,), duration=duration,
                  verified=True, result_id=video, **kwargs)


def metadata(**kwargs):
    return {"song_id": A, "name": "Song", "artist": "Artist", "artists": ["Artist"],
            "duration": 180, **kwargs}


def test_confident_first_page_never_extracts_views_or_calls_second_provider():
    calls = []

    class Provider:
        client = object()

        def get_results(self, query, **options):
            calls.append(options)
            return [result()]

        def get_views(self, url):
            pytest.fail("Candidate extraction for popularity must not run")

    matcher = FastMatcher([Provider(), SimpleNamespace()])
    selected = matcher.candidates(metadata())
    assert len(calls) == 1 and calls[0]["limit"] == 10
    assert selected[0]["score"] == 100 and matcher.stats["view_extractions"] == 0


@pytest.mark.parametrize("candidate", [
    result(name="Song (Cover)"), result(name="Song - Live"), result(name="Song Remix"),
    result(name="Song (Slowed + Reverb)"), result(artist="Someone Else"),
    result(duration=90), result(name="Unrelated Title"),
])
def test_fast_matching_rejects_wrong_recordings(candidate):
    assert rank_candidate(metadata(), candidate) is None


def test_live_edition_can_be_identified_by_album_but_studio_cannot_replace_it():
    expected = metadata(name="Song - Ao Vivo")
    assert rank_candidate(expected, result()) is None
    assert rank_candidate(expected, result(album="Live Album Ao Vivo"))["score"] == 100
    assert rank_candidate(metadata(name="Song - Remastered"), result()) is None
    assert rank_candidate(metadata(name="Song (2022 Remaster)"), result(name="Song (2010 Remaster)")) is None
    assert rank_candidate(metadata(name="Song (2022 Remaster)"), result(name="Song (2022 Remaster)"))


def test_ambiguous_results_require_explicit_selection():
    class Provider:
        client = object()

        def get_results(self, *_args, **_kwargs):
            return [result(duration=0), result(duration=0, video="bcdefghijkl")]

    matcher = FastMatcher([Provider()])
    with pytest.raises(MatchError, match="ambígua"):
        matcher.candidates(metadata())
    assert len(matcher.last_candidates) == 2


def test_cache_follows_identity_and_matcher_version_and_manual_choice(tmp_path):
    store = Store(tmp_path)
    original = metadata()
    evidence = {**rank_candidate(original, result()), "version": 1}
    store.save_audio_match(original, evidence)
    assert Store(tmp_path).audio_match(original)["url"] == evidence["url"]
    assert store.audio_match(metadata(duration=240)) is None
    assert store.audio_match(metadata(name="Song - Live")) is None
    store.save_audio_match(original, {**evidence, "version": 0})
    assert store.audio_match(original) is None
    store.set_audio_source(A, "https://youtu.be/abcdefghijk?t=20")
    assert store.rows("SELECT url FROM audio_sources")[0]["url"] == evidence["url"]
    assert store.audio_match(original) is None
    store.set_audio_source(A, "")
    assert not store.rows("SELECT * FROM audio_sources")


@pytest.mark.parametrize("value", ["http://youtu.be/abcdefghijk", "https://evil.test/abcdefghijk",
                                    "https://youtube.com/playlist?list=abc", "https://youtube.com/watch?v=short",
                                    "https://user:pass@youtube.com/watch?v=abcdefghijk"])
def test_manual_sources_are_only_canonical_video_urls(value):
    with pytest.raises(ValueError):
        canonical_youtube(value)


def test_cached_extraction_failure_falls_back_without_repeating_bad_candidate(tmp_path):
    engine = DownloadEngine.__new__(DownloadEngine)
    engine.root = tmp_path
    engine.prepare_seconds, engine.download_count = 0, 0
    (tmp_path / "audio").mkdir()
    engine.progress = lambda message: None
    calls = []

    class Downloader:
        errors = []

        def download_song(self, song):
            calls.append(song.download_url)
            if len(calls) == 1:
                self.errors.append("AudioProviderError: connection failed api_key=hidden-value")
                return song, None
            output = tmp_path / "audio" / "test.mp3"
            output.write_bytes(b"fixture")
            return song, output

    def candidates(md, **options):
        assert options["exclude"] == {"https://www.youtube.com/watch?v=abcdefghijk"}
        return [{"url": "https://www.youtube.com/watch?v=bcdefghijkl", "version": 1}]

    engine.downloader = Downloader()
    engine.matcher = SimpleNamespace(stats={}, candidates=candidates)
    response = engine.download(metadata(_cached_match={"url": "https://www.youtube.com/watch?v=abcdefghijk"}),
                               tmp_path / "final.mp3")
    assert len(calls) == 2 and len(set(calls)) == 2
    assert response["metrics"]["attempts"] == 2
    assert response["match"]["url"].endswith("bcdefghijkl")


def test_weighted_genres_specific_styles_and_country_evidence():
    assert classify([{"name": "country", "count": 3}, {"name": "southern rock", "count": 1},
                     {"name": "bluegrass", "count": 1}]) == "Country e Folk"
    assert classify([{"name": "latin", "count": 3}, {"name": "sertanejo", "count": 2}]) == "Sertanejo"
    assert classify(["agrofunk"]) == "Funk Brasileiro"


def test_other_artist_cache_hit_does_not_wait_for_slow_network(tmp_path, monkeypatch):
    store = Store(tmp_path)
    with store.connect() as db:
        db.execute("INSERT INTO genre_cache VALUES(?,?,?)",
                   ("cached", json.dumps({"version": GENRE_VERSION, "tags": ["sertanejo"]}), time.time()))
    resolver = GenreResolver(store)
    entered, release = threading.Event(), threading.Event()

    def slow(artist):
        entered.set()
        assert release.wait(5)
        return ["rock"]

    monkeypatch.setattr(resolver, "musicbrainz", slow)
    with ThreadPoolExecutor(max_workers=2) as pool:
        waiting = pool.submit(resolver.resolve, {"artist": "Slow"})
        assert entered.wait(2)
        try:
            cached = pool.submit(resolver.resolve, {"artist": "Cached"})
            assert cached.result(timeout=1) == "Sertanejo"
        finally:
            release.set()
        assert waiting.result(timeout=2) == "Rock e Metal"


def test_artist_queries_are_single_flight_and_force_refreshes_old_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(GenreResolver, "itunes", lambda *args: None)
    monkeypatch.setattr(GenreResolver, "deezer", lambda *args: None)
    store = Store(tmp_path)
    calls = []
    resolver = GenreResolver(store)

    def lookup(artist):
        calls.append(artist)
        time.sleep(0.03)
        return [{"name": "country", "count": 3}]

    monkeypatch.setattr(resolver, "musicbrainz", lookup)
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(resolver.resolve, [metadata()] * 8)) == ["Country e Folk"] * 8
    assert calls == ["Artist"]
    refreshed = GenreResolver(store, force=True)
    monkeypatch.setattr(refreshed, "musicbrainz", lambda artist: ["sertanejo"])
    assert refreshed.resolve(metadata()) == "Sertanejo"


def test_optional_lastfm_has_weighted_tags_and_does_not_leak_key(tmp_path, monkeypatch):
    monkeypatch.setattr(GenreResolver, "itunes", lambda *args: None)
    monkeypatch.setattr(GenreResolver, "deezer", lambda *args: None)
    store = Store(tmp_path)
    store.set_setting("lastfm_api_key", "private-test-key")
    resolver = GenreResolver(store)
    monkeypatch.setattr(resolver, "musicbrainz", lambda artist: [])
    monkeypatch.setattr(resolver, "wikidata", lambda artist, artist_id: [])
    calls = []

    def request(source, url, params):
        calls.append(params)
        return {"toptags": {"tag": [{"name": "country", "count": "10"}, {"name": "rock", "count": "1"}]}}

    monkeypatch.setattr(resolver, "request", request)
    assert resolver.resolve(metadata()) == "Country e Folk"
    assert calls[0]["method"] == "artist.getTopTags"
    assert "private-test-key" not in json.dumps(sanitize(calls))


def make_library(tmp_path):
    store = Store(tmp_path / "data")
    store.set_setting("musicbrainz", False)
    store.add_playlist(P1)
    provider = FakeProvider()
    provider.snapshots[P1] = snapshot(track(A, "unknown"))
    lib = Library(store, provider, validator=lambda path: None)
    lib.apply(lib.preview())
    return store, provider, lib


def test_changed_category_on_redownload_leaves_one_active_copy_and_recoverable_old(tmp_path):
    store, provider, lib = make_library(tmp_path)
    old_path = store.tracks()[0]["path"]
    with store.connect() as db:
        db.execute("UPDATE tracks SET metadata=?", (json.dumps(track(A, "sertanejo")),))
    lib.apply(lib.preview(force=True))
    assert len(list(lib.music.rglob("*.mp3"))) == 1
    assert not (lib.music / old_path).exists()
    assert list((store.root / "trash").rglob("*.mp3"))
    assert store.tracks()[0]["path"].startswith("Sertanejo/")


def test_interrupted_install_is_recovered_before_next_run(tmp_path, monkeypatch):
    store, provider, lib = make_library(tmp_path)
    with store.connect() as db:
        db.execute("UPDATE tracks SET metadata=?", (json.dumps(track(A, "sertanejo")),))
    monkeypatch.setattr(lib.files, "finish", lambda *_: (_ for _ in ()).throw(OSError("simulated crash")))
    assert lib.apply(lib.preview(force=True))["failures"]
    assert store.rows("SELECT * FROM file_transitions")
    resumed = Library(Store(store.root), provider, validator=lambda path: None)
    assert len(list(resumed.music.rglob("*.mp3"))) == 1
    assert resumed.store.tracks()[0]["status"] == "ready"
    assert not resumed.store.rows("SELECT * FROM file_transitions")


def test_interruption_before_replace_keeps_previous_audio_and_cleans_incomplete_journal(tmp_path, monkeypatch):
    store, provider, lib = make_library(tmp_path)
    before = store.tracks()[0]
    with store.connect() as db:
        db.execute("UPDATE tracks SET metadata=?", (json.dumps(track(A, "sertanejo")),))
    original = __import__("os").replace

    def interrupted(source, target):
        if Path(target).is_relative_to(lib.music):
            raise OSError("crash before replace")
        return original(source, target)

    monkeypatch.setattr("spotano.files.os.replace", interrupted)
    assert lib.apply(lib.preview(force=True))["failures"]
    assert lib.available(before)
    monkeypatch.setattr("spotano.files.os.replace", original)
    resumed = Library(Store(store.root), provider, validator=lambda path: None)
    assert not resumed.store.rows("SELECT * FROM file_transitions")
    assert resumed.available(before)


def test_interrupted_old_copy_cleanup_recovers_without_another_download(tmp_path, monkeypatch):
    store, provider, lib = make_library(tmp_path)
    old = lib.music / store.tracks()[0]["path"]
    with store.connect() as db:
        db.execute("UPDATE tracks SET metadata=?", (json.dumps(track(A, "sertanejo")),))
    original = Path.unlink

    def interrupted(path, *args, **kwargs):
        if path == old:
            raise OSError("crash after database commit")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", interrupted)
    assert lib.apply(lib.preview(force=True))["failures"]
    assert store.tracks()[0]["path"].startswith("Sertanejo/")
    monkeypatch.setattr(Path, "unlink", original)
    count = len(provider.downloads)
    resumed = Library(Store(store.root), provider, validator=lambda path: None)
    assert not old.exists() and len(list(resumed.music.rglob("*.mp3"))) == 1
    assert len(provider.downloads) == count and resumed.store.tracks()[0]["status"] == "ready"


def test_physical_copy_review_never_moves_canonical_or_changed_files(tmp_path):
    store, _, lib = make_library(tmp_path)
    old = lib.music / "Old" / ("Duplicate [" + A + "].mp3")
    old.parent.mkdir()
    old.write_bytes(b"unreferenced old version")
    review = lib.files.review()
    assert len(review) == 1 and review[0]["path"].startswith("Old/")
    old.write_bytes(b"external changes after review")
    with pytest.raises(ValueError, match="mudou"):
        lib.files.quarantine(review, store.setting("revision"))
    assert old.exists() and lib.available(store.tracks()[0])
    lib.files.quarantine(lib.files.review(), store.setting("revision"))
    assert not old.exists() and lib.available(store.tracks()[0])


def test_artist_override_respects_track_override_and_returns_to_automatic(tmp_path):
    store, _, lib = make_library(tmp_path)
    lib.correct_artist(A, "Sertanejo")
    assert store.tracks()[0]["path"].startswith("Sertanejo/")
    lib.correct_genre(A, "Pop")
    lib.correct_artist(A, "Rock e Metal")
    assert store.tracks()[0]["override"] == "Pop"
    lib.correct_genre(A, "")
    assert store.tracks()[0]["path"].startswith("Rock e Metal/")


def test_run_summary_survives_visible_log_reset_and_failed_download(tmp_path):
    store, provider, lib = make_library(tmp_path)
    provider.fail.add(A)
    result = lib.apply(lib.preview(force=True))
    summary = json.loads((Path(result["run_directory"]) / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "completed_with_errors"
    assert summary["tracks"][0]["status"] == "error"
    assert summary["tracks"][0]["error"] == "network interrupted"
    assert lib.available(store.tracks()[0])


@pytest.fixture
def real_audio(tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg unavailable")
    source = tmp_path / "sample.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(44100)
        audio.writeframes(b"\x00\x00\x00\x00" * 44100)
    target = tmp_path / "sample.mp3"
    subprocess.run([ffmpeg, "-y", "-i", str(source), "-c:a", "libmp3lame", "-b:a", "192k",
                    "-ar", "44100", "-ac", "2", "-id3v2_version", "3", str(target)],
                   capture_output=True, check=True)
    return target


def test_tag_correction_preserves_profile_updates_hash_and_export_without_redownload(tmp_path, real_audio):
    from mutagen.id3 import ID3

    store = Store(tmp_path / "data")
    store.set_setting("musicbrainz", False)
    store.add_playlist(P1)

    class Provider(FakeProvider):
        def download(self, metadata, output):
            self.downloads.append(metadata["song_id"])
            shutil.copyfile(real_audio, output)

    provider = Provider()
    lib = Library(store, provider)
    lib.apply(lib.preview())
    exporter = Exporter(lib)
    usb = tmp_path / "usb"
    usb.mkdir()
    exporter.apply(exporter.preview(usb))
    before = store.tracks()[0]
    assert str(ID3(lib.music / before["path"])["TCON"]) == "Sertanejo"
    lib.correct_genre(A, "Pop")
    after = store.tracks()[0]
    assert after["sha256"] != before["sha256"]
    assert digest(lib.music / after["path"]) == after["sha256"]
    assert str(ID3(lib.music / after["path"])["TCON"]) == "Pop"
    validate_mp3(lib.music / after["path"])
    assert len(provider.downloads) == 1 and len(list(lib.music.rglob("*.mp3"))) == 1
    assert len(exporter.preview(usb).copy) == 1


def test_duration_rejects_shortened_audio():
    with pytest.raises(ValueError, match="Duração incompatível"):
        validate_duration(30, 180)
    validate_duration(181, 180)
