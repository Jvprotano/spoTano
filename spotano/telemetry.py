"""Persistent, sanitized run evidence, independent of the visible log buffer."""

import csv
import importlib.metadata
import json
import platform
import re
import threading
import time
import uuid
from datetime import UTC, datetime

from . import __version__

RUN_STATUS = {
    "completed": "Concluída",
    "completed_with_errors": "Concluída com falhas",
    "cancelled": "Cancelada",
    "failed": "Interrompida por erro",
    "interrupted": "Interrompida",
}


def sanitize(value):
    if isinstance(value, dict):
        return {
            key: "[oculto]"
            if re.search(r"token|secret|password|cookie|api_key|authorization", key, re.I)
            else sanitize(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    if isinstance(value, str):

        def safe_url(match):
            from .matching import canonical_youtube

            try:
                return canonical_youtube(match[0])
            except ValueError:
                return "[URL do provedor]"

        value = re.sub(r"https?://\S+", safe_url, value)
        return re.sub(
            r"(?i)(token|secret|password|cookie|api_key|authorization)([=: ]+)\S+", r"\1\2[oculto]", value
        )[:3000]
    return value


class RunMetrics:
    def __init__(self, store, total, reused, workers, *, requested=(), playlists=()):
        self.started = time.monotonic()
        self.run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
        self.directory = store.root / "runs" / self.run_id
        self.directory.mkdir(parents=True)
        self.lock = threading.Lock()
        self.rows = []
        self.requested = {track["song_id"] for track in requested}
        self.identities = {}
        for playlist_id, snapshot in playlists:
            for track in snapshot["tracks"]:
                identity = self.identities.setdefault(
                    track["song_id"],
                    {
                        "track_id": track["song_id"],
                        "name": track["name"],
                        "artist": track["artist"],
                        "playlists": [],
                        "requested": track["song_id"] in self.requested,
                    },
                )
                identity["playlists"].append(snapshot["name"])
        for track in requested:
            self.identities.setdefault(
                track["song_id"],
                {
                    "track_id": track["song_id"],
                    "name": track["name"],
                    "artist": track["artist"],
                    "playlists": [],
                    "requested": True,
                },
            )
        versions = {}
        for package in ("spotdl", "yt-dlp", "ytmusicapi", "yt-dlp-ejs"):
            try:
                versions[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                pass
        self.record(
            "run_start",
            total=total,
            reused=reused,
            workers=workers,
            version=__version__,
            dependencies=versions,
            python=platform.python_version(),
            data_directory=str(store.root),
            conversion_workers=store.setting("conversion_workers", 2),
            queue=list(self.identities.values()),
        )

    def record(self, event, **data):
        identity = self.identities.get(data.get("track_id"), {})
        row = sanitize(
            {
                "event": event,
                "run_id": self.run_id,
                "time": datetime.now(UTC).isoformat(timespec="milliseconds"),
                "elapsed_s": round(time.monotonic() - self.started, 3),
                **identity,
                **data,
            }
        )
        with self.lock:
            with (self.directory / "events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            if event == "track_finished":
                self.rows.append(row)

    def finish(self, status, **data):
        from .paths import atomic_json

        self.record("run_end", status=status, **data)
        summary = sanitize(
            {
                "run_id": self.run_id,
                "status": status,
                "seconds": round(time.monotonic() - self.started, 3),
                "tracks": self.outcomes(status),
                **data,
            }
        )
        atomic_json(self.directory / "summary.json", summary)
        write_run_report(self.directory, summary)

    def outcomes(self, status):
        finished = {row["track_id"]: row for row in self.rows}
        for track_id, identity in self.identities.items():
            if track_id not in finished:
                requested = identity["requested"]
                finished[track_id] = {
                    **identity,
                    "status": "pending" if requested else "reused",
                    "error": (
                        "Download não concluído; use Baixar / retomar. Execução: "
                        + RUN_STATUS.get(status, status)
                        if requested
                        else ""
                    ),
                }
        return list(finished.values())


def write_run_report(directory, summary):
    """Readable evidence beside JSON diagnostics; also usable with older run summaries."""
    summary = sanitize(summary)
    tracks = summary.get("tracks", [])
    missing = [row for row in tracks if row["status"] not in {"ready", "reused"}]
    labels = {
        "ready": "Baixada e validada",
        "reused": "Reutilizada",
        "error": "Falha",
        "pending": "Pendente",
        "cancelled": "Cancelada",
    }
    lines = [
        f"spoTano — execução {summary['run_id']}",
        f"Estado: {RUN_STATUS.get(summary['status'], summary['status'])} · {summary.get('seconds', 0):.1f}s",
        f"{sum(row['status'] == 'ready' for row in tracks)} baixadas e validadas · "
        f"{sum(row['status'] == 'reused' for row in tracks)} reutilizadas · "
        f"{len(missing)} não concluídas",
        "",
        "Use Baixar / retomar para tentar as pendências; arquivos íntegros serão reutilizados.",
        "Se a gravação continuar sem correspondência, revise Biblioteca → Fonte do áudio.",
        "",
    ]
    for row in [*missing, *(row for row in tracks if row not in missing)]:
        lines.append(
            f"{labels.get(row['status'], row['status'])}: "
            f"{row.get('artist', '')} — {row.get('name', row['track_id'])} [{row['track_id']}]"
        )
        if row.get("error"):
            lines.append("  Motivo: " + row["error"])
        diagnostic = row.get("evidence", {})
        if diagnostic.get("stage"):
            lines.append("  Etapa: " + diagnostic["stage"])
        for candidate in diagnostic.get("rejected_candidates", [])[:3]:
            lines.append(f"  Rejeitada: {candidate['name']} · {candidate['reason']}")
    (directory / "report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    with (directory / "failures.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(["Spotify ID", "Artista", "Música", "Playlists", "Estado", "Etapa", "Motivo"])
        for row in missing:
            cells = [
                row["track_id"],
                row.get("artist", ""),
                row.get("name", ""),
                ", ".join(row.get("playlists", [])),
                labels.get(row["status"], row["status"]),
                row.get("evidence", {}).get("stage", ""),
                row.get("error", ""),
            ]
            writer.writerow(
                ["'" + str(cell) if str(cell).startswith(("=", "+", "-", "@")) else cell for cell in cells]
            )
