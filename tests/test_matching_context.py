"""Focused regressions for missing versus conflicting recording metadata."""

from types import SimpleNamespace

import pytest
from test_optimization import metadata, result

from spotano.matching import rank_candidate


def test_unlabelled_single_accepts_verified_near_exact_live_recording():
    wanted = metadata(name="Deslumbrante", artist="Hugo & Guilherme", duration=176)
    row = result(name="Deslumbrante (Ao Vivo)", artist="Hugo e Guilherme", duration=177)
    assert rank_candidate(wanted, row)["evidence_notes"]
    assert rank_candidate(wanted, SimpleNamespace(**{**row.json, "verified": False})) is None
    assert rank_candidate({**wanted, "album_name": "Studio"}, row) is None
    assert rank_candidate({**wanted, "duration": 165}, row) is None


def test_missing_year_requires_verified_same_venue_and_near_exact_identity():
    wanted = metadata(
        name="Liberdade Provisória - Live - Ibirapuera / 2019",
        artist="Henrique & Juliano",
        duration=186,
    )
    row = result(
        name="Henrique e Juliano - LIBERDADE PROVISÓRIA - DVD Ao Vivo No Ibirapuera",
        artist="Henrique e Juliano",
        duration=183,
    )
    assert rank_candidate(wanted, row)["evidence_notes"]
    for changes in (
        {"verified": False},
        {"duration": 170},
        {"name": row.name + " 2022"},
        {"name": row.name.replace("Ibirapuera", "Palmas")},
    ):
        assert rank_candidate(wanted, SimpleNamespace(**{**row.json, **changes})) is None


@pytest.mark.parametrize("event", ["No Pelo 360", "Nopelo360"])
def test_project_label_and_guest_credits_in_video_title(event):
    wanted = metadata(
        name="Tentação (Nopelo360) - Ao Vivo",
        artist="Mayke & Rodrigo",
        artists=["Mayke & Rodrigo", "Hugo & Guilherme"],
        duration=144,
    )
    row = result(
        name=f"Mayke e Rodrigo - Tentação part. Hugo e Guilherme | Ao Vivo {event}",
        artist="Mayke e Rodrigo",
        duration=156,
    )
    assert rank_candidate(wanted, row)["score"] >= 94
    assert (
        rank_candidate(wanted, result(name="Tentação (Ao Vivo)", artist="Mayke & Rodrigo", duration=145))
        is None
    )
    assert (
        rank_candidate(wanted, SimpleNamespace(**{**row.json, "name": row.name.replace(event, "Outro DVD")}))
        is None
    )
