import csv
import json
import subprocess
from types import SimpleNamespace

import pytest
from test_library import P1, A, B, FakeProvider, snapshot, track
from test_optimization import metadata, result

from spotano.db import Store
from spotano.library import Library
from spotano.matching import FastMatcher, MatchError, rank_candidate
from spotano.provider import Cancelled
from spotano.telemetry import RunMetrics


def test_square_bracket_guest_credit_matches_parentheses_without_relaxing_identity():
    wanted = metadata(
        name="Balada Louca [feat. João Neto & Frederico] - Ao Vivo",
        artist="Munhoz & Mariano", duration=187,
    )
    candidate = result(
        name="Balada Louca (Ao Vivo) (feat. João Neto & Frederico)",
        artist="Munhoz & Mariano", duration=187,
    )
    assert rank_candidate(wanted, candidate)["score"] == 100
    for other in (
        result(name="Não Tô Valendo Nada (Ao Vivo)", artist="Munhoz & Mariano", duration=187),
        result(name=candidate.name, artist="Outro artista", duration=187),
        result(name="Balada Louca (Remix)", artist="Munhoz & Mariano", duration=187),
        result(name=candidate.name, artist="Munhoz & Mariano", duration=100),
    ):
        assert rank_candidate(wanted, other) is None


def test_expanded_pages_skip_identical_metadata_but_reconsider_album_evidence(monkeypatch):
    import spotano.matching as matching

    calls = []
    original = matching.rank_candidate

    def rank(*args, **kwargs):
        calls.append(args[1])
        return original(*args, **kwargs)

    monkeypatch.setattr(matching, "rank_candidate", rank)

    class Provider:
        client = object()

        def get_results(self, query, **options):
            incomplete = result(name="Song", album="Studio")
            if options["limit"] == 30:
                return [incomplete, result(name="Song", album="Ao Vivo")]
            return [incomplete]

    matcher = FastMatcher([Provider()])
    assert matcher.candidates(metadata(name="Song - Ao Vivo"))[0]["score"] == 100
    assert len(calls) == 2
    assert matcher.stats["duplicate_candidates_skipped"] == 2


@pytest.mark.parametrize("credits", [("Henrique", "Juliano"), ("Henrique e Juliano",)])
def test_duo_credits_and_live_annotation_match(credits):
    wanted = metadata(artist="Henrique & Juliano", name="Desbeijar Minha Boca - Ao Vivo", duration=157)
    candidate = result(name="Desbeijar Minha Boca (Ao Vivo)", artist=credits[0], duration=158)
    candidate = SimpleNamespace(**{**candidate.json, "artists": credits})
    assert rank_candidate(wanted, candidate)["score"] >= 94
    assert rank_candidate(wanted, result(name="Desbeijar Minha Boca (Ao Vivo)", artist="Henrique")) is None


def test_parenthesized_live_location_does_not_obscure_title_but_year_remains_required():
    wanted = metadata(artist="Jorge & Mateus", name="Seu Astral - Live In Sao Paulo / 2010", duration=191)
    assert rank_candidate(
        wanted, result(name="Seu Astral (Live In Sao Paulo / 2010)", artist="Jorge & Mateus", duration=192)
    )
    for title in ("Seu Astral (Ao Vivo)", "Seu Astral (Live In Sao Paulo / 2012)"):
        assert rank_candidate(wanted, result(name=title, artist="Jorge & Mateus", duration=192)) is None


def test_alternate_translated_title_and_full_collaborator_prefix():
    assert rank_candidate(
        metadata(name="Eu Quero Só Você - Ao Vivo"), result(name="Eu Quero Só Você (Be With You) (Ao Vivo)")
    )
    wanted = metadata(
        name="Como Um Beijo",
        artist="Marcos & Belutti",
        artists=["Marcos & Belutti", "Nadson O Ferinha"],
        duration=205,
    )
    assert rank_candidate(
        wanted,
        result(name="Marcos & Belutti, Nadson o Ferinha - COMO UM BEIJO", artist="Canal", duration=211),
    )
    assert (
        rank_candidate(metadata(name="Tentação (Nopelo360) - Ao Vivo"), result(name="Tentação (Ao Vivo)"))
        is None
    )
    assert rank_candidate(metadata(name="Deslumbrante (Studio)"), result(name="Deslumbrante (Ao Vivo)")) is None
    assert rank_candidate(metadata(name="Song (Extended Version)"), result(name="Song")) is None


def test_rejections_survive_and_youtube_search_is_not_repeated(monkeypatch):
    provider = SimpleNamespace()
    queries = []

    def search(provider, query, limit):
        queries.append(query)
        return [result(duration=20)]

    monkeypatch.setattr(FastMatcher, "youtube_results", staticmethod(search))
    matcher = FastMatcher([provider])
    with pytest.raises(MatchError, match="Duração incompatível"):
        matcher.candidates(metadata())
    assert len(queries) == 1
    assert len(matcher.rejected_candidates) == 1
    assert "20s" in matcher.rejected_candidates[0]["reason"]
    assert matcher.rejected_candidates[0]["url"].startswith("https://www.youtube.com/")


def test_failure_report_keeps_identity_and_resume_only_retries_failed_track(tmp_path):
    store = Store(tmp_path)
    store.set_setting("musicbrainz", False)
    store.add_playlist(P1)
    provider = FakeProvider()
    provider.snapshots[P1] = snapshot(track(), track(B))
    provider.fail.add(B)
    lib = Library(store, provider, validator=lambda path: None)
    outcome = lib.apply(lib.preview())
    directory = lib.last_run
    with (directory / "failures.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter=";"))
    assert len(rows) == 1 and rows[0]["Spotify ID"] == B
    assert rows[0]["Artista"] == "Artista" and rows[0]["Música"] == "Canção B"
    assert rows[0]["Playlists"] == "Playlist teste" and "network interrupted" in rows[0]["Motivo"]
    assert "1 baixadas e validadas" in (directory / "report.txt").read_text(encoding="utf-8-sig")
    assert outcome["downloaded"] == 1 and [t["song_id"] for t in lib.preview(saved=True).downloads] == [B]
    provider.fail.clear()
    lib.apply(lib.preview(saved=True))
    summary = json.loads((lib.last_run / "summary.json").read_text(encoding="utf-8"))
    assert {r["track_id"]: r["status"] for r in summary["tracks"]} == {A: "reused", B: "ready"}
    assert provider.downloads.count(A) == 1


def test_cancelled_run_reports_queued_unstarted_tracks(tmp_path):
    store = Store(tmp_path)
    requested = [track(), track(B)]
    run = RunMetrics(store, 2, 0, 1, requested=requested)
    run.record("track_finished", track_id=A, status="cancelled", error="Cancelada")
    run.finish("cancelled")
    summary = json.loads((run.directory / "summary.json").read_text(encoding="utf-8"))
    assert {r["track_id"]: r["status"] for r in summary["tracks"]} == {A: "cancelled", B: "pending"}
    start = json.loads((run.directory / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert {r["track_id"] for r in start["queue"]} == {A, B}


def test_cancelled_library_marks_active_and_unstarted_tracks(tmp_path):
    store = Store(tmp_path)
    store.set_setting("download_workers", 1)
    store.set_setting("musicbrainz", False)
    store.add_playlist(P1)

    class Provider(FakeProvider):
        def download(self, metadata, output):
            raise Cancelled("cancelled by user")

    provider = Provider()
    provider.snapshots[P1] = snapshot(track(), track(B))
    lib = Library(store, provider, validator=lambda path: None)
    with pytest.raises(Cancelled):
        lib.apply(lib.preview())
    summary = json.loads((lib.last_run / "summary.json").read_text(encoding="utf-8"))
    assert {r["track_id"]: r["status"] for r in summary["tracks"]} == {A: "cancelled", B: "pending"}
    assert len(store.rows("SELECT * FROM download_pending")) == 2


def test_audit_recovers_abrupt_exit_with_no_summary_and_partial_last_event(tmp_path):
    from scripts.audit_download_run import audit

    store = Store(tmp_path / "library")
    run = RunMetrics(store, 2, 0, 1, requested=[track(), track(B)])
    run.record("track_finished", track_id=A, status="ready")
    with (run.directory / "events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write('{"event":')
    report = audit(run.directory, tmp_path / "review")
    assert report["historical_run"]["status"] == "interrupted"
    tracks = report["historical_run"]["tracks"]
    assert {r["track_id"]: r["status"] for r in tracks} == {A: "ready", B: "pending"}
    assert not (run.directory / "summary.json").exists()


def test_unresponsive_windows_cleanup_does_not_replace_download_failure(monkeypatch):
    from spotano import provider

    monkeypatch.setattr(provider, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(provider.subprocess, "CREATE_NO_WINDOW", 0, raising=False)

    def hung(*args, **kwargs):
        raise subprocess.TimeoutExpired("taskkill", 15)

    monkeypatch.setattr(provider.subprocess, "run", hung)

    class Process:
        pid = 123
        killed = False

        def poll(self):
            return -1 if self.killed else None

        def kill(self):
            self.killed = True

        def wait(self, timeout):
            assert self.killed

    process = Process()
    assert "taskkill" in provider.stop_tree(process)
    assert process.killed
