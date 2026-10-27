"""Persistent, sanitized run evidence, independent of the visible log buffer."""

import importlib.metadata
import json
import platform
import re
import threading
import time
import uuid
from datetime import UTC, datetime

from . import __version__


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
    def __init__(self, store, total, reused, workers):
        self.started = time.monotonic()
        self.run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
        self.directory = store.root / "runs" / self.run_id
        self.directory.mkdir(parents=True)
        self.lock = threading.Lock()
        self.rows = []
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
        )

    def record(self, event, **data):
        row = sanitize(
            {
                "event": event,
                "run_id": self.run_id,
                "time": datetime.now(UTC).isoformat(timespec="milliseconds"),
                "elapsed_s": round(time.monotonic() - self.started, 3),
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
                "tracks": self.rows,
                **data,
            }
        )
        atomic_json(self.directory / "summary.json", summary)
