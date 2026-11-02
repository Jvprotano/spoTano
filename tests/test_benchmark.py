"""Focused calibration policy and recovery checks, without provider traffic."""

import json
from collections import Counter
from pathlib import Path

import pytest

from spotano.benchmark import (
    CONFIGURATIONS,
    QUICK_CONFIGURATIONS,
    REPETITIONS,
    PerformanceTest,
    configurations_for,
    rank_results,
    recommend,
    report_recommendation,
    result_lines,
    sample_tracks,
    select_sample,
    settings_match,
)
from spotano.db import Store
from spotano.library import Library
from spotano.provider import Cancelled


def pair(downloads, conversions, seconds, failures=None):
    return [
        dict(
            download_workers=downloads,
            conversion_workers=conversions,
            seconds=seconds,
            failures=failures or [],
            downloaded=4,
            total=4,
            round=repetition + 1,
        )
        for repetition in range(REPETITIONS)
    ]


def test_recommendation_rejects_failures_and_incomplete_rounds():
    rows = pair(2, 2, 10.4) + pair(4, 4, 10) + pair(3, 3, 1, ["limited"])
    rows += pair(1, 1, 1)[:2]
    assert recommend(rows)["download_workers"] == 2
    assert recommend(pair(2, 2, 1, ["failed"])) is None


@pytest.mark.parametrize("baseline, expected_lots", [((2, 2), 8), ((3, 1), 10)])
def test_quick_compares_balanced_profiles_and_current_setting_twice(
    tmp_path, monkeypatch, baseline, expected_lots
):
    store = Store(tmp_path)
    store.set_setting("download_workers", baseline[0])
    store.set_setting("conversion_workers", baseline[1])
    benchmark = PerformanceTest(Library(store, object()))
    calls = []
    tracks = [dict(song_id=f"{i:022d}") for i in range(4)]

    def trial(sample, d, c, directory):
        calls.append((d, c))
        assert {t["song_id"] for t in sample} == {t["song_id"] for t in tracks}
        return dict(seconds=10 if (d, c) == baseline else 20, downloaded=4, failures=[])

    monkeypatch.setattr(benchmark, "trial", trial)
    report = benchmark.run(tracks, mode="quick")
    expected = configurations_for("quick", baseline)
    assert set(QUICK_CONFIGURATIONS) <= set(calls)
    assert Counter(calls) == dict.fromkeys(expected, 2)
    assert len(calls) == expected_lots
    assert calls[len(expected) :] == list(reversed(calls[: len(expected)]))
    assert report["mode"] == "quick" and report["repetitions"] == 2
    assert report["max_spread"] == 0.15 and len(report["sample"]) == 4
    best = report_recommendation(report)
    assert (best["download_workers"], best["conversion_workers"]) == baseline
    assert store.setting("download_workers") == baseline[0]
    assert store.setting("conversion_workers") == baseline[1]
    assert "não explora todas as combinações" in "\n".join(result_lines(report))
    # The on-disk report remains applicable after JSON converts tuples to lists.
    saved = json.loads(Path(store.setting("performance_report")).read_text())
    assert report_recommendation(saved) == best
    saved["rows"].pop()
    assert report_recommendation(saved) is None


def test_quick_rejects_sample_too_small_for_four_download_workers(tmp_path):
    benchmark = PerformanceTest(Library(Store(tmp_path), object()))
    with pytest.raises(ValueError, match="exatamente 4"):
        benchmark.run([dict(song_id=str(i)) for i in range(3)], mode="quick")


def test_quick_uses_stricter_variation_gate_than_complete():
    rows = pair(2, 2, 10)[:2]
    rows[1]["seconds"] = 12
    assert recommend(rows, repetitions=2, max_spread=0.15) is None
    assert recommend(rows, repetitions=2, max_spread=0.25)


def test_median_ranking_and_instability_do_not_hide_faster_results():
    fast = pair(4, 4, 10)
    fast[-1]["seconds"] = 30
    rows = fast + pair(2, 1, 10.4) + pair(1, 1, 12)
    ranking = rank_results(rows)
    assert [r["download_workers"] for r in ranking] == [4, 2, 1]
    assert ranking[0]["seconds"] == 10 and not ranking[0]["stable"]
    assert ranking[0]["spread"] == 2
    assert recommend(rows)["download_workers"] == 2
    # A slower stable result far from an unstable fastest result is not a winner.
    assert recommend(fast + pair(1, 1, 12)) is None


@pytest.mark.parametrize("seconds", [0, -1, float("nan"), float("inf")])
def test_invalid_timings_cannot_win(seconds):
    assert recommend(pair(1, 1, seconds)) is None


def test_duplicate_rounds_and_mismatched_samples_cannot_win():
    rows = pair(1, 1, 10)
    rows[-1]["round"] = 1
    assert recommend(rows) is None
    rows = pair(1, 1, 10)
    rows[-1].update(total=8, downloaded=8)
    assert recommend(rows) is None
    assert recommend(pair(1, 1, 10), total=8) is None


def test_sweep_repeats_same_sample_and_preserves_settings(tmp_path, monkeypatch):
    store = Store(tmp_path)
    store.set_setting("download_workers", 1)
    store.set_setting("output_layout", "unified")
    lib = Library(store, object())
    benchmark = PerformanceTest(lib)
    tracks = [dict(song_id=f"{i:022d}", name=str(i), artist="Own") for i in range(4)]
    calls = []

    def trial(sample, downloads, conversions, directory):
        assert {t["song_id"] for t in sample} == {t["song_id"] for t in tracks}
        calls.append(((downloads, conversions), [t["song_id"] for t in sample]))
        return dict(seconds=100 / downloads + 5 / conversions, downloaded=4, failures=[])

    monkeypatch.setattr(benchmark, "trial", trial)
    report = benchmark.run(tracks)
    assert Counter(c[0] for c in calls) == dict.fromkeys(CONFIGURATIONS, REPETITIONS)
    assert [c[0] for c in calls[16:32]] == list(reversed([c[0] for c in calls[:16]]))
    assert len(calls) == 48
    for offset in range(0, 48, 16):
        assert all(c[1] == calls[offset][1] for c in calls[offset : offset + 16])
    assert len(report["schedule"]) == REPETITIONS and report["seed"]
    assert report["recommendation"]["download_workers"] == 4
    assert store.setting("download_workers") == 1
    assert store.setting("output_layout") == "unified"
    assert not store.tracks()
    saved = json.loads((Path(report["directory"]) / "summary.json").read_text())
    assert saved["ranking"] == report["ranking"]
    assert saved["recommendation"] == report_recommendation(saved)
    assert settings_match(store, saved)
    store.set_setting("musicbrainz", False)
    assert not settings_match(store, saved)
    assert len(rank_results(saved["rows"])) == 16
    saved["rows"].pop()
    assert report_recommendation(saved) is None


def test_full_grid_finds_interaction_missed_by_staged_sweep(tmp_path, monkeypatch):
    benchmark = PerformanceTest(Library(Store(tmp_path), object()))

    def trial(sample, d, c, directory):
        return dict(seconds=10 if (d, c) == (2, 1) else 20 + d, downloaded=4, failures=[])

    monkeypatch.setattr(benchmark, "trial", trial)
    tracks = [dict(song_id=f"{i:022d}") for i in range(4)]
    report = benchmark.run(tracks)
    best = report["recommendation"]
    assert (best["download_workers"], best["conversion_workers"]) == (2, 1)
    lines = result_lines(report)
    start = lines.index("RESULTADOS POR DESEMPENHO")
    assert lines[start + 1].startswith("1º · 2 downloads / 1 conversões")
    assert "16 combinações" in "\n".join(lines)


def test_trial_errors_are_retained_and_other_combinations_finish(tmp_path, monkeypatch):
    benchmark = PerformanceTest(Library(Store(tmp_path), object()))

    def trial(sample, d, c, directory):
        if (d, c) == (4, 4):
            raise RuntimeError("provider unavailable")
        return dict(seconds=10, downloaded=4, failures=[])

    monkeypatch.setattr(benchmark, "trial", trial)
    report = benchmark.run([dict(song_id=f"{i:022d}") for i in range(4)])
    assert report["status"] == "completed" and len(report["rows"]) == 48
    assert report["recommendation"]["download_workers"] == 1
    assert not report["ranking"][-1]["eligible"]
    assert report["ranking"][-1]["failures"] == 3


def test_cancel_saves_partial_report_without_suggestion(tmp_path, monkeypatch):
    store = Store(tmp_path)
    lib = Library(store, object())
    benchmark = PerformanceTest(lib)
    count = 0

    def trial(*args):
        nonlocal count
        count += 1
        if count == 2:
            lib.cancel.set()
            raise Cancelled("stop")
        return dict(seconds=10, downloaded=4, failures=[])

    monkeypatch.setattr(benchmark, "trial", trial)
    with pytest.raises(Cancelled):
        benchmark.run([dict(song_id=f"{i:022d}") for i in range(4)])
    report = json.loads(Path(store.setting("performance_report")).read_text())
    assert report["status"] == "cancelled" and len(report["rows"]) == 1
    assert report["recommendation"] is None
    assert store.setting("download_workers") == 2


def test_cancel_after_last_trial_preserves_all_measurements_without_recommendation(tmp_path, monkeypatch):
    benchmark = PerformanceTest(Library(Store(tmp_path), object()))
    count = 0

    def trial(*args):
        nonlocal count
        count += 1
        if count == len(CONFIGURATIONS) * REPETITIONS:
            benchmark.cancel.set()
        return dict(seconds=10, downloaded=4, failures=[])

    monkeypatch.setattr(benchmark, "trial", trial)
    with pytest.raises(Cancelled):
        benchmark.run([dict(song_id=f"{i:022d}") for i in range(4)])
    report = json.loads(Path(benchmark.store.setting("performance_report")).read_text())
    assert len(report["rows"]) == 48 and report["status"] == "cancelled"
    assert report_recommendation(report) is None


def test_trial_copies_workload_and_manual_choices_but_keeps_original_catalog_untouched(tmp_path, monkeypatch):
    store = Store(tmp_path / "original")
    store.set_setting("musicbrainz", False)
    store.set_setting("lastfm_api_key", "private-test-value")
    store.set_setting("conversion_encoder", "lame")
    store.set_setting("download_options", {"metadata": True})
    store.set_setting("output_layout", "unified")
    lib = Library(store, object())
    tracks = [dict(song_id=f"{i:022d}", name=str(i), artist="Own") for i in range(4)]
    with store.connect() as db:
        pid = db.execute("INSERT INTO playlists(url,name) VALUES('original','Original')").lastrowid
        lib.save_snapshot(db, pid, {"name": "Original", "tracks": tracks})
        db.execute(
            "INSERT INTO audio_sources VALUES(?,?)", (tracks[0]["song_id"], "https://youtu.be/abcdefghijk")
        )
        db.execute("UPDATE tracks SET override='Rock' WHERE id=?", (tracks[0]["song_id"],))
        db.execute("INSERT INTO artist_categories VALUES('Own','Pop')")
        db.execute("INSERT INTO genre_cache VALUES('Own','[]',1)")
    original = store.path.read_bytes()

    def apply(isolated, plan):
        assert isolated.store.root != store.root
        assert isolated.store.setting("download_options") == {
            "categories": False,
            "artists": False,
            "metadata": True,
        }
        assert isolated.store.setting("output_layout") == "unified"
        assert isolated.store.setting("conversion_encoder") == "lame"
        assert isolated.store.setting("lastfm_api_key") == "private-test-value"
        assert isolated.store.setting("download_workers") == 4
        assert isolated.store.setting("conversion_workers") == 1
        assert isolated.store.rows("SELECT * FROM audio_sources") == store.rows("SELECT * FROM audio_sources")
        assert isolated.store.rows("SELECT override FROM tracks ORDER BY id")[0]["override"] == "Rock"
        assert isolated.store.rows("SELECT * FROM artist_categories") == store.rows(
            "SELECT * FROM artist_categories"
        )
        assert not isolated.store.rows("SELECT * FROM genre_cache")
        assert len(plan.downloads) == 4 and plan.retained == 0
        return dict(downloaded=4, failures=[])

    monkeypatch.setattr(Library, "apply", apply)
    directory = tmp_path / "evidence"
    directory.mkdir()
    result = PerformanceTest(lib).trial(tracks, 4, 1, directory)
    assert result["downloaded"] == 4
    assert not list(directory.glob("trial-*"))
    assert store.path.read_bytes() == original


def test_legacy_report_is_readable_but_never_applicable():
    report = dict(created_at="old", status="completed", directory="old", rows=pair(1, 1, 10)[:2])
    assert report_recommendation(report) is None
    assert "Método antigo" in "\n".join(result_lines(report))


def test_sample_uses_only_marked_playlists_and_deduplicates(tmp_path):
    store = Store(tmp_path)
    lib = Library(store, object())
    tracks = [dict(song_id=f"{i:022d}", name=str(i), artist="Own") for i in range(12)]
    with store.connect() as db:
        for playlist_id, sample in ((1, tracks[:8]), (2, tracks[4:])):
            db.execute(
                "INSERT INTO playlists(id,url,name) VALUES(?,?,?)", (playlist_id, str(playlist_id), "Own")
            )
            lib.save_snapshot(db, playlist_id, {"name": "Own", "tracks": sample})
    assert len({t["song_id"] for t in select_sample(store, [1, 2], 8)}) == 8
    assert all(t in tracks[:8] for t in select_sample(store, [1]))
    with pytest.raises(ValueError, match="Marque"):
        select_sample(store, [])


def test_playlist_sample_deduplicates_and_spans_durations():
    tracks = [dict(song_id=str(i), duration=(12 - i) * 10) for i in range(12)]
    sample = sample_tracks(tracks + tracks[:3], 8)
    assert len({t["song_id"] for t in sample}) == 8
    assert sample[0]["duration"] == 10 and sample[-1]["duration"] == 120
    with pytest.raises(ValueError, match="playlist de teste"):
        sample_tracks(tracks[:3], 4)
