"""Real, isolated first-download trials using the application's normal pipeline."""

import json
import os
import platform
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
    if len(rows) < size:
        raise ValueError(f"As playlists marcadas precisam ter pelo menos {size} músicas distintas.")
    return [json.loads(rows[round(i * (len(rows) - 1) / (size - 1))]["metadata"]) for i in range(size)]


def recommend(rows):
    """Only complete, failure-free pairs qualify; prefer fewer workers within 5%."""
    groups = {}
    for row in rows:
        key = (row["download_workers"], row["conversion_workers"])
        groups.setdefault(key, []).append(row)
    candidates = []
    for (downloads, conversions), trials in groups.items():
        if len(trials) != 2 or any(t["failures"] or t["downloaded"] != t["total"] for t in trials):
            continue
        seconds = statistics.mean(t["seconds"] for t in trials)
        candidates.append(
            {
                "download_workers": downloads,
                "conversion_workers": conversions,
                "seconds": seconds,
                "tracks_per_minute": 60 * trials[0]["total"] / seconds,
            }
        )
    if not candidates:
        return None
    fastest = min(c["seconds"] for c in candidates)
    return min(
        (c for c in candidates if c["seconds"] <= fastest * 1.05),
        key=lambda c: (c["download_workers"] + c["conversion_workers"], c["download_workers"]),
    )


class PerformanceTest:
    def __init__(self, library):
        self.library = library
        self.store = library.store
        self.progress, self.cancel = library.progress, library.cancel

    def check_cancel(self):
        if self.cancel.is_set():
            raise Cancelled("Teste cancelado. Medições parciais salvas; configurações preservadas.")

    def trial(self, tracks, downloads, conversions, directory):
        # Same volume, clean catalog and empty caches for every trial. Never seed MP3s.
        with tempfile.TemporaryDirectory(prefix="trial-", dir=directory) as temporary:
            store = Store(Path(temporary))
            for key, default in (("musicbrainz", True), ("lastfm_api_key", "")):
                store.set_setting(key, self.store.setting(key, default))
            store.set_setting("download_options", download_options(self.store))
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

    def run(self, tracks):
        self.check_cancel()
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
        directory = self.store.root / "benchmarks" / stamp
        directory.mkdir(parents=True)
        report = {
            "created_at": datetime.now(UTC).isoformat(),
            "status": "running",
            "directory": str(directory),
            "sample": tracks,
            "options": download_options(self.store),
            "platform": platform.platform(),
            "logical_cpus": os.cpu_count(),
            "method": "cold caches; same sample; two rounds in reverse configuration order; staged sweep",
            "rows": [],
            "recommendation": None,
        }

        def save():
            atomic_json(directory / "summary.json", sanitize(report))

        def sweep(configs, stage):
            for repetition in range(2):
                ordered = configs if repetition == 0 else list(reversed(configs))
                for downloads, conversions in ordered:
                    self.check_cancel()
                    self.progress(
                        f"Teste de desempenho · {stage} · rodada {repetition + 1}/2 · "
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
                        row.update(self.trial(tracks, downloads, conversions, directory))
                    except Cancelled:
                        raise
                    except Exception as exc:
                        row.update(seconds=time.monotonic() - began, downloaded=0, failures=[str(exc)])
                    self.check_cancel()
                    report["rows"].append(row)
                    save()
                    self.progress(
                        f"Medição: {downloads}/{conversions} · {row['seconds']:.1f}s · "
                        f"{row['downloaded']}/{len(tracks)} baixadas · {len(row['failures'])} falhas."
                    )

        save()
        self.progress(f"Relatório do teste: {directory}")
        try:
            sweep([(d, min(d, 2)) for d in range(1, 5)], "downloads")
            best = recommend(report["rows"])
            if best:
                downloads = best["download_workers"]
                sweep(
                    [(downloads, c) for c in range(1, downloads + 1) if c != best["conversion_workers"]],
                    "conversões",
                )
            report["recommendation"] = recommend(report["rows"])
            report["status"] = "completed"
        except BaseException as exc:
            report["status"] = "cancelled" if isinstance(exc, Cancelled) else "failed"
            raise
        finally:
            save()
            self.store.set_setting("performance_report", str(directory / "summary.json"))
        return sanitize(report)


def result_lines(report):
    lines = [
        f"Medição: {report['created_at']} · estado: {report['status']}",
        "Mesma amostra, caches locais vazios, duas rodadas em ordem inversa.",
        "Comparação por etapas: downloads primeiro; conversões no melhor nível de downloads.",
        "Os tempos incluem preparação, busca, transferência, categoria e conversão habilitadas.",
        "A preparação pesa mais em amostras pequenas. Para lotes grandes, prefira testar com 8 músicas.",
        "Sugestão entre os valores testados, válida para esta amostra e condições de rede/provedor.",
        "Até 5% do menor tempo: prefere menos processos. Não garante o ótimo global.",
        "",
    ]
    for row in report["rows"]:
        lines.append(
            f"Downloads {row['download_workers']} · Conversões {row['conversion_workers']} · "
            f"Rodada {row['round']}: {row['seconds']:.1f}s · "
            f"{row['downloaded']}/{row['total']} músicas · {len(row['failures'])} falhas"
        )
    if report["status"] != "completed":
        lines.append("Teste interrompido. Medições parciais não geram sugestão.")
    elif not report["recommendation"]:
        lines.append("Sem sugestão: nenhuma configuração completou duas rodadas sem falhas.")
    lines.extend(["", f"Relatório e métricas: {report['directory']}"])
    return lines
