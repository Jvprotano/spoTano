"""Focused calibration policy and recovery checks, without provider traffic."""

import json
from pathlib import Path

import pytest

from spotano.benchmark import PerformanceTest, recommend, select_sample
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
        )
        for _ in range(2)
    ]


def test_recommendation_rejects_failures_and_incomplete_pairs():
    rows = pair(2, 2, 10.4) + pair(4, 4, 10) + pair(3, 3, 1, ["limited"])
    rows += pair(1, 1, 1)[:1]
    assert recommend(rows)["download_workers"] == 2
    assert recommend(pair(2, 2, 1, ["failed"])) is None


def test_sweep_repeats_same_sample_and_preserves_settings(tmp_path, monkeypatch):
    store = Store(tmp_path)
    store.set_setting("download_workers", 1)
    lib = Library(store, object())
    benchmark = PerformanceTest(lib)
    tracks = [dict(song_id=f"{i:022d}", name=str(i), artist="Own") for i in range(4)]
    calls = []

    def trial(sample, downloads, conversions, directory):
        assert sample == tracks
        calls.append((downloads, conversions))
        return dict(seconds=100 / downloads + 5 / conversions, downloaded=4, failures=[])

    monkeypatch.setattr(benchmark, "trial", trial)
    report = benchmark.run(tracks)
    assert calls[:4] == [(1, 1), (2, 2), (3, 2), (4, 2)]
    assert calls[4:8] == list(reversed(calls[:4]))
    assert len(calls) == 14
    assert report["recommendation"]["download_workers"] == 4
    assert store.setting("download_workers") == 1
    assert not store.tracks()
    assert json.loads((Path(report["directory"]) / "summary.json").read_text())


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
        benchmark.run([])
    report = json.loads(Path(store.setting("performance_report")).read_text())
    assert report["status"] == "cancelled" and len(report["rows"]) == 1
    assert report["recommendation"] is None
    assert store.setting("download_workers") == 2


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
