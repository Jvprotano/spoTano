"""Real, isolated first-download trials using the application's normal pipeline."""

import json
import math
import os
import platform
import random
import statistics
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .db import Store
from .library import Library
from .options import download_options
from .paths import atomic_json
from .provider import Cancelled, SpotProvider
from .telemetry import sanitize

CONFIGURATIONS = tuple((d, c) for d in range(1, 5) for c in range(1, 5))
REPETITIONS = 3
MAX_SPREAD = 0.25
TIE_MARGIN = 0.05
SCHEMA_VERSION = 3
DEFAULT_PLAYLIST = "https://open.spotify.com/playlist/0aoPyrSGmKxpwxzN9NDr7c"
QUICK_CONFIGURATIONS = ((1, 1), (2, 2), (3, 3), (4, 4))
PROTOCOLS = {
    "quick": {"label": "rápido", "repetitions": 2, "max_spread": 0.15},
    "complete": {"label": "completo", "repetitions": REPETITIONS, "max_spread": MAX_SPREAD},
}


def configurations_for(mode, baseline=None):
    if mode not in PROTOCOLS:
        raise ValueError("Escolha o teste rápido ou completo.")
    if mode == "complete":
        return CONFIGURATIONS
    configs = list(QUICK_CONFIGURATIONS)
    if baseline is not None:
        baseline = tuple(baseline)
        if baseline not in CONFIGURATIONS:
            raise ValueError("Paralelismo atual inválido. Escolha valores de 1 a 4 nas Configurações.")
        if baseline not in configs:
            configs.append(baseline)
    return tuple(configs)


def report_mode(report):
    # Version 2 used the identical complete protocol, before modes were introduced.
    return "complete" if report.get("schema_version") == 2 else report.get("mode", "complete")


def report_ranking(report):
    protocol = PROTOCOLS[report_mode(report)]
    ranking = rank_results(
        report["rows"],
        report.get("repetitions", 2),
        total=len(report["sample"]) if report.get("sample") else None,
        max_spread=protocol["max_spread"],
    )
    for row in ranking:
        row["initial_configuration"] = [row["download_workers"], row["conversion_workers"]] == list(
            report.get("baseline") or []
        )
    return ranking


def test_settings(store):
    """Snapshot the workload; never compare trials with different options."""
    return {
        "download_options": download_options(store),
        "musicbrainz": store.setting("musicbrainz", True),
        "lastfm_api_key": store.setting("lastfm_api_key", ""),
        "output_layout": store.setting("output_layout", "playlists"),
        "conversion_encoder": store.setting("conversion_encoder", "windows"),
    }


def settings_match(store, report):
    # Persist no credentials. Only compare whether the optional source was enabled.
    settings = test_settings(store)
    workload = {
        "musicbrainz": settings["musicbrainz"],
        "lastfm_enabled": bool(settings["lastfm_api_key"] or os.environ.get("LASTFM_API_KEY")),
        "output_layout": settings["output_layout"],
        "conversion_encoder": settings["conversion_encoder"],
    }
    return report.get("options") == settings["download_options"] and report.get("workload") == workload


def select_sample(store, playlist_ids, size=4):
    if size not in (4, 8):
        raise ValueError("Escolha uma amostra de 4 ou 8 músicas.")
    ids = sorted(set(playlist_ids))
    if not ids:
        raise ValueError("Marque playlists na aba Playlists antes de testar.")
    marks = ",".join("?" for _ in ids)
    rows = store.rows(
        f"""SELECT DISTINCT t.id,t.metadata FROM tracks t JOIN membership m ON m.track_id=t.id
        WHERE m.playlist_id IN ({marks}) ORDER BY t.id""",
        ids,
    )
    return sample_tracks([json.loads(row["metadata"]) for row in rows], size)


def sample_tracks(tracks, size=8):
    """Spread the sample over durations, deduplicating the playlist first."""
    if size not in (4, 8):
        raise ValueError("Escolha uma amostra de 4 ou 8 músicas.")
    unique = {track["song_id"]: track for track in tracks}
    if len(unique) < size:
        raise ValueError(
            f"A playlist de teste precisa ter pelo menos {size} músicas distintas. Troque a playlist ou a amostra nas Configurações."
        )

    def duration(track):
        value = track.get("duration")
        return value if isinstance(value, (int, float)) and math.isfinite(value) and value > 0 else 0

    ordered = sorted(unique.values(), key=lambda t: (duration(t), t["song_id"]))
    return [ordered[round(i * (len(ordered) - 1) / (size - 1))] for i in range(size)]


def rank_results(rows, repetitions=REPETITIONS, total=None, max_spread=MAX_SPREAD):
    """Rank successful complete configurations by median; retain rejected evidence."""
    groups = {}
    for row in rows:
        key = (row["download_workers"], row["conversion_workers"])
        groups.setdefault(key, []).append(row)
    results = []
    for (downloads, conversions), trials in groups.items():
        reason = ""
        if len(trials) != repetitions or {t.get("round") for t in trials} != set(range(1, repetitions + 1)):
            reason = "Rodadas incompletas ou repetidas"
        elif any(
            not isinstance(t.get("seconds"), (int, float))
            or not math.isfinite(t["seconds"])
            or t["seconds"] <= 0
            for t in trials
        ):
            reason = "Tempo inválido"
        elif any(
            t["failures"]
            or t["total"] <= 0
            or t["downloaded"] != t["total"]
            or t["total"] != (total if total is not None else trials[0]["total"])
            for t in trials
        ):
            reason = "Falhas ou amostra incompleta"
        result = {
            "download_workers": downloads,
            "conversion_workers": conversions,
            "eligible": not reason,
            "reason": reason,
            "rounds": len(trials),
            "failures": sum(len(t["failures"]) for t in trials),
            "stable": False,
            "max_spread": max_spread,
        }
        if not reason:
            times = [t["seconds"] for t in trials]
            seconds = statistics.median(times)
            spread = (max(times) - min(times)) / seconds
            result.update(
                seconds=seconds,
                mean_seconds=statistics.mean(times),
                min_seconds=min(times),
                max_seconds=max(times),
                spread=spread,
                stable=spread <= max_spread,
                tracks_per_minute=60 * trials[0]["total"] / seconds,
            )
        results.append(result)
    return sorted(
        results,
        key=lambda r: (
            not r["eligible"],
            r.get("seconds", math.inf),
            r["download_workers"],
            r["conversion_workers"],
        ),
    )


def recommend(rows, repetitions=REPETITIONS, total=None, max_spread=MAX_SPREAD):
    """Require repeatable results near the fastest; ties favor fewer workers."""
    candidates = [r for r in rank_results(rows, repetitions, total, max_spread) if r["eligible"]]
    if not candidates:
        return None
    fastest = candidates[0]["seconds"]
    return min(
        (c for c in candidates if c["stable"] and c["seconds"] <= fastest * (1 + TIE_MARGIN)),
        key=lambda c: (c["download_workers"] + c["conversion_workers"], c["download_workers"], c["seconds"]),
        default=None,
    )


def report_recommendation(report):
    """Old, partial or incomplete sweeps cannot offer an applicable recommendation."""
    rows = report["rows"]
    mode = report_mode(report)
    if mode not in PROTOCOLS:
        return None
    protocol = PROTOCOLS[mode]
    configs = configurations_for(mode, report.get("baseline"))
    repetitions = protocol["repetitions"]
    if (
        report.get("schema_version") not in (2, SCHEMA_VERSION)
        or report["status"] != "completed"
        or report.get("repetitions") != repetitions
        or (mode == "quick" and len(report["sample"]) != 4)
        or len(rows) != len(configs) * repetitions
        or {(r["download_workers"], r["conversion_workers"]) for r in rows} != set(configs)
        or {(r["download_workers"], r["conversion_workers"], r.get("round")) for r in rows}
        != {(d, c, r) for d, c in configs for r in range(1, repetitions + 1)}
    ):
        return None
    return recommend(rows, repetitions, total=len(report["sample"]), max_spread=protocol["max_spread"])


class PerformanceTest:
    def __init__(self, library):
        self.library = library
        self.store = library.store
        self.progress, self.cancel = library.progress, library.cancel
        self.settings = None

    def check_cancel(self):
        if self.cancel.is_set():
            raise Cancelled("Teste cancelado. Medições parciais salvas; configurações preservadas.")

    def trial(self, tracks, downloads, conversions, directory):
        # Same volume, clean catalog and empty caches for every trial. Never seed MP3s.
        with tempfile.TemporaryDirectory(prefix="trial-", dir=directory) as temporary:
            store = Store(Path(temporary))
            for key, value in (self.settings or test_settings(self.store)).items():
                store.set_setting(key, value)
            store.set_setting("download_workers", downloads)
            store.set_setting("conversion_workers", conversions)
            provider = SpotProvider(self.cancel, self.progress)
            lib = Library(store, provider, self.progress, self.cancel)
            with store.connect() as db:
                playlist_id = db.execute(
                    "INSERT INTO playlists(url,name) VALUES(?,?)", ("benchmark", "Teste de desempenho")
                ).lastrowid
                lib.save_snapshot(db, playlist_id, {"name": "Teste de desempenho", "tracks": tracks})
                for track in tracks:
                    sources = self.store.rows(
                        "SELECT url FROM audio_sources WHERE track_id=?", (track["song_id"],)
                    )
                    if sources:
                        db.execute(
                            "INSERT INTO audio_sources VALUES(?,?)", (track["song_id"], sources[0]["url"])
                        )
                    overrides = self.store.rows("SELECT override FROM tracks WHERE id=?", (track["song_id"],))
                    if overrides:
                        db.execute(
                            "UPDATE tracks SET override=? WHERE id=?",
                            (overrides[0]["override"], track["song_id"]),
                        )
                for row in self.store.rows("SELECT * FROM artist_categories"):
                    db.execute("INSERT INTO artist_categories VALUES(?,?)", (row["artist"], row["category"]))
            plan = lib.preview(force=True, saved=True)
            began = time.monotonic()
            try:
                result = lib.apply(plan)
                return {
                    "seconds": time.monotonic() - began,
                    "downloaded": result["downloaded"],
                    "failures": result["failures"],
                }
            finally:
                # Keep sanitized phase evidence, but remove temporary audio and catalog (including keys).
                if hasattr(lib, "last_run"):
                    import shutil

                    shutil.copytree(lib.last_run, directory / "runs" / lib.last_run.name)

    def run(self, tracks, source_playlist=None, mode="complete"):
        self.check_cancel()
        baseline = (
            int(self.store.setting("download_workers", 2)),
            int(self.store.setting("conversion_workers", 2)),
        )
        configurations = configurations_for(mode, baseline)
        protocol = PROTOCOLS[mode]
        repetitions = protocol["repetitions"]
        if not tracks or len({t["song_id"] for t in tracks}) != len(tracks):
            raise ValueError("O teste precisa de uma amostra não vazia, sem músicas repetidas.")
        if mode == "quick" and len(tracks) != 4:
            raise ValueError("O teste rápido usa exatamente 4 músicas.")
        self.settings = test_settings(self.store)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
        directory = self.store.root / "benchmarks" / stamp
        directory.mkdir(parents=True)
        report = {
            "schema_version": SCHEMA_VERSION,
            "mode": mode,
            "baseline": baseline,
            "created_at": datetime.now(UTC).isoformat(),
            "status": "running",
            "directory": str(directory),
            "sample": tracks,
            "source_playlist_id": source_playlist.rsplit("/", 1)[-1] if source_playlist else None,
            "options": self.settings["download_options"],
            "workload": {
                "musicbrainz": self.settings["musicbrainz"],
                "lastfm_enabled": bool(self.settings["lastfm_api_key"] or os.environ.get("LASTFM_API_KEY")),
                "output_layout": self.settings["output_layout"],
                "conversion_encoder": self.settings["conversion_encoder"],
            },
            "platform": platform.platform(),
            "logical_cpus": os.cpu_count(),
            "method": "balanced profiles plus current configuration"
            if mode == "quick"
            else "full factorial 4x4",
            "repetitions": repetitions,
            "configurations": configurations,
            "max_spread": protocol["max_spread"],
            "tie_margin": TIE_MARGIN,
            "seed": uuid.uuid4().hex,
            "schedule": [],
            "rows": [],
            "ranking": [],
            "recommendation": None,
        }

        def save():
            atomic_json(directory / "summary.json", sanitize(report))

        rng = random.Random(report["seed"])
        configs = list(configurations)
        rng.shuffle(configs)

        def sweep():
            for repetition in range(repetitions):
                if repetition == 1:
                    configs.reverse()
                elif repetition > 1:
                    rng.shuffle(configs)
                # Each configuration sees the same track order within a round.
                sample = list(tracks)
                rng.shuffle(sample)
                report["schedule"].append(
                    {
                        "round": repetition + 1,
                        "configurations": list(configs),
                        "track_ids": [t["song_id"] for t in sample],
                    }
                )
                save()
                for downloads, conversions in configs:
                    self.check_cancel()
                    self.progress(
                        f"Teste {protocol['label']} · lote {len(report['rows']) + 1}/{len(configurations) * repetitions} · "
                        f"rodada {repetition + 1}/{repetitions} · "
                        f"{downloads} downloads / {conversions} conversões · {len(tracks)} músicas."
                    )
                    row = {
                        "download_workers": downloads,
                        "conversion_workers": conversions,
                        "round": repetition + 1,
                        "total": len(tracks),
                    }
                    began = time.monotonic()
                    try:
                        row.update(self.trial(sample, downloads, conversions, directory))
                    except Cancelled:
                        raise
                    except Exception as exc:
                        row.update(seconds=time.monotonic() - began, downloaded=0, failures=[str(exc)])
                    report["rows"].append(row)
                    save()
                    self.check_cancel()
                    self.progress(
                        f"Medição: {downloads}/{conversions} · {row['seconds']:.1f}s · "
                        f"{row['downloaded']}/{len(tracks)} baixadas · {len(row['failures'])} falhas."
                    )

        save()
        self.progress(f"Relatório do teste: {directory}")
        try:
            sweep()
            self.check_cancel()
            report["status"] = "completed"
            report["recommendation"] = report_recommendation(report)
        except BaseException as exc:
            report["status"] = "cancelled" if isinstance(exc, Cancelled) else "failed"
            raise
        finally:
            report["ranking"] = report_ranking(report)
            report["finished_at"] = datetime.now(UTC).isoformat()
            save()
            self.store.set_setting("performance_report", str(directory / "summary.json"))
        return sanitize(report)


def result_lines(report):
    legacy = report.get("schema_version") not in (2, SCHEMA_VERSION)
    mode = report_mode(report)
    protocol = PROTOCOLS[mode]
    ranking = report_ranking(report)
    lines = [
        f"Medição: {report['created_at']} · estado: {report['status']}",
        f"Playlist do teste: https://open.spotify.com/playlist/{report['source_playlist_id']}"
        if report.get("source_playlist_id")
        else "Playlist de origem não registrada neste relatório.",
        "Método antigo por etapas: repita o teste para obter a recomendação atual."
        if legacy
        else "Teste rápido: quatro perfis 1/1, 2/2, 3/3, 4/4 e configuração atual quando diferente; duas rodadas."
        if mode == "quick"
        else "Teste completo: todas as 16 combinações de 1–4 downloads × 1–4 conversões, três rodadas.",
        "Recomendação inicial entre os perfis testados. O rápido não explora todas as combinações; use o completo para uma comparação mais ampla."
        if mode == "quick"
        else "Comparação de todos os valores dos controles de paralelismo.",
        "Mesma amostra e opções, caches locais vazios e áudios novos em cada lote.",
        "Os tempos incluem preparação, busca, transferência, categoria e conversão habilitadas.",
        "A preparação pesa mais em amostras pequenas. Para lotes grandes, prefira testar com 8 músicas.",
        "Ranking por mediana (menor é melhor). Variação = (máximo − mínimo) / mediana.",
        f"Recomendação exige {protocol['repetitions']} rodadas sem falhas e variação de até {protocol['max_spread']:.0%}. "
        "Esse limite é uma regra prática, não confiança estatística.",
        "Até 5% do menor tempo: prefere menos processos entre resultados estáveis.",
        "Rede, provedor, caches externos e outros programas podem afetar o teste. Use o computador ocioso e ligado à tomada.",
        "O resultado vale para esta amostra e opções; não garante o tempo de uma playlist inteira.",
        "",
        "RESULTADOS POR DESEMPENHO",
    ]
    position = 0
    for row in ranking:
        label = f"{row['download_workers']} downloads / {row['conversion_workers']} conversões"
        if row["eligible"]:
            position += 1
            lines.append(
                f"{position}º · {label} · mediana {row['seconds']:.1f}s · {row['tracks_per_minute']:.1f} músicas/min · "
                f"mín–máx {row['min_seconds']:.1f}–{row['max_seconds']:.1f}s · variação {row['spread']:.0%}"
                + (" · INSTÁVEL" if not row["stable"] else "")
            )
        else:
            lines.append(f"Sem classificação · {label} · {row['reason']} · {row['failures']} falhas")
    lines.extend(["", "MEDIÇÕES POR RODADA (ORDEM DE EXECUÇÃO)"])
    for row in report["rows"]:
        lines.append(
            f"Downloads {row['download_workers']} · Conversões {row['conversion_workers']} · "
            f"Rodada {row['round']}: {row['seconds']:.1f}s · "
            f"{row['downloaded']}/{row['total']} músicas · {len(row['failures'])} falhas"
        )
    if report["status"] != "completed":
        lines.append("Teste interrompido. Medições parciais não geram recomendação.")
    elif not report_recommendation(report):
        lines.append("Sem recomendação aplicável: repita o teste completo e confira falhas e variação.")
    lines.extend(["", f"Relatório e métricas: {report['directory']}"])
    return lines
