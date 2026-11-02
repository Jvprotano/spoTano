"""Read a historical download run and optionally verify its current local audio."""

import argparse
import json
import sqlite3
import statistics
import sys
from pathlib import Path

from mutagen import MutagenError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spotano.audio import validate_mp3
from spotano.paths import atomic_json, digest, inside
from spotano.telemetry import write_run_report


def audit(run_directory, output, catalog=None):
    identities = {}
    finished = {}
    last = {}
    start = {}
    with (run_directory / "events.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                if not line.endswith("\n"):
                    break  # An abrupt exit can leave the last append incomplete.
                raise
            last = event
            if event["event"] == "run_start":
                start = event
                identities.update({row["track_id"]: row for row in event.get("queue", [])})
            if event["event"] == "track_start":
                identities.setdefault(event["track_id"], {}).update(
                    {key: event[key] for key in ("name", "artist")}
                )
            if event["event"] == "track_finished":
                finished[event["track_id"]] = event
    summary_path = run_directory / "summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    else:
        for track_id, identity in identities.items():
            finished.setdefault(
                track_id,
                {
                    **identity,
                    "track_id": track_id,
                    "status": "pending" if identity.get("requested", True) else "reused",
                    "error": "Execução interrompida antes da conclusão; use Baixar / retomar."
                    if identity.get("requested", True)
                    else "",
                },
            )
        summary = {
            "run_id": start.get("run_id", run_directory.name),
            "status": "interrupted",
            "seconds": last.get("elapsed_s", 0),
            "tracks": list(finished.values()),
        }
    for row in summary["tracks"]:
        for key, value in identities.get(row["track_id"], {}).items():
            row.setdefault(key, value)
    output.mkdir(parents=True, exist_ok=True)
    write_run_report(output, summary)
    verification = []
    if catalog:
        # Use SQLite's read-only mode; auditing never opens Store or migrates a catalog.
        with sqlite3.connect(catalog.resolve().as_uri() + "?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            for row in summary["tracks"]:
                if row["status"] != "ready":
                    continue
                current = db.execute(
                    "SELECT path,sha256 FROM tracks WHERE id=?", (row["track_id"],)
                ).fetchone()
                check = {"track_id": row["track_id"]}
                try:
                    if not current or not current["path"]:
                        raise ValueError("Arquivo ausente no catálogo atual")
                    path = inside(catalog.parent / "Music", current["path"])
                    if digest(path) != current["sha256"]:
                        raise ValueError("SHA-256 diferente do catálogo atual")
                    info = validate_mp3(path)
                    check.update(status="valid", path=str(path), duration=round(info.length, 2))
                except (OSError, ValueError, MutagenError) as exc:
                    check.update(status="error", error=str(exc))
                verification.append(check)
    metrics = {}
    ready = [row for row in summary["tracks"] if row["status"] == "ready"]
    keys = {key for row in ready for key in row.get("evidence", {}).get("metrics", {})}
    for key in sorted(keys):
        values = [
            row["evidence"]["metrics"][key]
            for row in ready
            if isinstance(row.get("evidence", {}).get("metrics", {}).get(key), (int, float))
        ]
        if values:
            metrics[key] = {
                "sum": round(sum(values), 3),
                "median": round(statistics.median(values), 3),
                "max": round(max(values), 3),
            }
    report = {
        "source": str(run_directory),
        "historical_run": summary,
        "metrics": metrics,
        "current_file_verification": verification,
        "verification_note": "Verificação dos arquivos e hashes atuais; o catálogo pode ter mudado desde a execução.",
    }
    atomic_json(output / "audit.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--catalog", type=Path, help="Read-only catalog; verifies current hashes and MP3 profile"
    )
    args = parser.parse_args()
    if args.output.resolve() == args.run_directory.resolve():
        parser.error("Escolha uma pasta de saída diferente para preservar o diagnóstico original.")
    report = audit(args.run_directory, args.output, args.catalog)
    print(f"Relatório: {args.output.resolve() / 'report.txt'}")
    checks = report["current_file_verification"]
    if checks:
        print(f"Arquivos atuais válidos: {sum(row['status'] == 'valid' for row in checks)}/{len(checks)}")


if __name__ == "__main__":
    main()
