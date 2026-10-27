"""Compare persistent run summaries, including phases and correspondence cache."""

import argparse
import json
import statistics
from pathlib import Path


def summarize(path):
    if path.is_dir():
        path = path / "summary.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("tracks", [])
    ready = [row for row in rows if row["status"] == "ready"]
    metrics = [row.get("evidence", {}).get("metrics", {}) for row in ready]
    totals = [row["seconds"] for row in ready]
    return {"run_id": data["run_id"], "status": data["status"], "wall_seconds": data["seconds"],
            "downloaded": data.get("downloaded", len(ready)), "reused": data.get("reused", 0),
            "failed": sum(row["status"] == "error" for row in rows),
            "median_track_s": round(statistics.median(totals), 3) if totals else None,
            "slowest_track_s": max(totals) if totals else None,
            "p95_track_s": round(statistics.quantiles(totals, n=20)[18], 3) if len(totals) >= 20 else None,
            "search_worker_seconds": round(sum(item.get("search_s", 0) for item in metrics), 3),
            "search_queries": sum(item.get("queries", 0) for item in metrics),
            "view_extractions": sum(item.get("view_extractions", 0) for item in metrics),
            "cache_hits": sum(bool(item.get("cache_hit")) for item in metrics),
            "note": "phase sums overlap across workers; compare first runs separately from cache/reuse"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", type=Path, nargs="+")
    args = parser.parse_args()
    for path in args.runs:
        print(json.dumps(summarize(path), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
