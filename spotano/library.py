"""Incremental library operations, independent of the network adapter and GUI."""

import json
import os
import re
import shutil
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .genres import CATEGORIES, GenreResolver
from .paths import digest, inside, safe_name
from .provider import Cancelled


def now():
    return datetime.now(UTC).isoformat(timespec="seconds")


def validate_mp3(path: Path):
    from mutagen.mp3 import MP3

    info = MP3(path).info
    if info.length <= 0 or info.bitrate <= 0:
        raise ValueError("O arquivo obtido não é um MP3 válido.")
    if info.sample_rate != 44100 or info.channels != 2:
        raise ValueError("MP3 fora do perfil automotivo (44,1 kHz / estéreo).")


@dataclass
class SyncPlan:
    revision: int
    snapshots: list
    downloads: list = field(default_factory=list)
    added: list = field(default_factory=list)
    removed: list = field(default_factory=list)
    retained: int = 0
    force: bool = False


class Library:
    def __init__(self, store, provider, progress=lambda message: None, cancel=None, validator=validate_mp3):
        self.store, self.provider, self.progress = store, provider, progress
        self.cancel = cancel or threading.Event()
        self.validator = validator
        self.music = self.store.root / "Music"
        self.music.mkdir(exist_ok=True)

    def check_cancel(self):
        if self.cancel.is_set():
            raise Cancelled("Operação cancelada; arquivos anteriores preservados.")

    def available(self, track):
        if not track.get("path") or not track.get("sha256"):
            return False
        path = inside(self.music, track["path"])
        return path.is_file() and digest(path) == track["sha256"]

    def preview(self, force=False):
        revision = self.store.setting("revision")
        playlists = self.store.playlists()
        if not playlists:
            raise ValueError("Adicione pelo menos uma playlist.")
        plan = SyncPlan(revision=revision, snapshots=[], force=force)
        desired = {}
        for playlist in playlists:
            self.check_cancel()
            self.progress(f"Lendo {playlist['name']}…")
            snapshot = self.provider.playlist(playlist["url"])
            if not isinstance(snapshot.get("tracks"), list):
                raise ValueError("Snapshot inválido; biblioteca preservada.")
            old = {
                r["track_id"]
                for r in self.store.rows(
                    "SELECT track_id FROM membership WHERE playlist_id=?", (playlist["id"],)
                )
            }
            ids = set()
            for track in snapshot["tracks"]:
                if not re.fullmatch(r"[A-Za-z0-9]{22}", track.get("song_id", "")):
                    raise ValueError("Identificador de faixa inválido.")
                ids.add(track["song_id"])
                desired[track["song_id"]] = track
            # Unknown/local/deleted items cannot prove that former tracks were removed.
            if snapshot.get("skipped", 0) and old - ids:
                raise ValueError(
                    f"{snapshot['name']}: há itens indisponíveis e possíveis remoções. "
                    "O estado anterior foi preservado. Resolva os itens no Spotify e atualize."
                )
            plan.added.extend((playlist["name"], desired[i]["name"]) for i in sorted(ids - old))
            previous = {r["id"]: json.loads(r["metadata"]) for r in self.store.tracks()}
            plan.removed.extend((playlist["name"], previous[i]["name"]) for i in sorted(old - ids))
            plan.snapshots.append((playlist["id"], snapshot))
        existing = {t["id"]: t for t in self.store.tracks()}
        for track_id, metadata in desired.items():
            self.check_cancel()
            if force or track_id not in existing or not self.available(existing[track_id]):
                plan.downloads.append(metadata)
            else:
                plan.retained += 1
        if revision != self.store.setting("revision"):
            raise ValueError("A biblioteca mudou durante a consulta. Gere outra prévia.")
        return plan

    def relative_path(self, track_id, metadata, category):
        folder = category if self.store.setting("by_genre", True) else safe_name(metadata["artist"])
        return (
            f"{safe_name(folder)}/{safe_name(metadata['artist'] + ' - ' + metadata['name'])} [{track_id}].mp3"
        )

    def apply(self, plan):
        self.check_cancel()
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            revision = int(db.execute("SELECT value FROM settings WHERE key='revision'").fetchone()[0])
            if revision != plan.revision:
                raise ValueError("Prévia desatualizada. Gere uma nova prévia.")
            for playlist_id, snapshot in plan.snapshots:
                for track in snapshot["tracks"]:
                    db.execute(
                        """INSERT INTO tracks(id,metadata) VALUES(?,?)
                        ON CONFLICT(id) DO UPDATE SET metadata=excluded.metadata""",
                        (track["song_id"], json.dumps(track, ensure_ascii=False)),
                    )
                db.execute("DELETE FROM membership WHERE playlist_id=?", (playlist_id,))
                for position, track in enumerate(snapshot["tracks"]):
                    db.execute(
                        "INSERT OR IGNORE INTO membership VALUES(?,?,?)",
                        (playlist_id, track["song_id"], position),
                    )
                db.execute(
                    "UPDATE playlists SET name=?,synced_at=?,warning=? WHERE id=?",
                    (
                        snapshot["name"],
                        now(),
                        f"{snapshot.get('skipped', 0)} itens não suportados",
                        playlist_id,
                    ),
                )
            self.store.bump(db)
        resolver = GenreResolver(self.store)
        failures = []
        total = len(plan.downloads)
        for index, metadata in enumerate(plan.downloads, 1):
            self.check_cancel()
            track_id = metadata["song_id"]
            self.progress(f"{index}/{total} · {metadata['artist']} — {metadata['name']}")
            staging = self.store.root / "staging" / uuid.uuid4().hex
            staging.mkdir(parents=True)
            try:
                current = self.store.rows("SELECT * FROM tracks WHERE id=?", (track_id,))[0]
                category = current["override"] or resolver.resolve(metadata)
                self.check_cancel()
                output = staging / "audio.mp3"
                self.provider.download(metadata, output)
                self.check_cancel()
                self.validator(output)
                file_hash = digest(output)
                relative = self.relative_path(track_id, metadata, category)
                target = inside(self.music, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() and (current["path"] != relative or digest(target) != current["sha256"]):
                    raise ValueError("Arquivo local alterado ou desconhecido; preservado para revisão.")
                # If replacement changes content, retain the old bytes before replacing them.
                if target.exists() and file_hash != current["sha256"]:
                    backup = inside(self.store.root, "trash/" + uuid.uuid4().hex + "/" + relative)
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(target, backup)
                os.replace(output, target)
                with self.store.connect() as db:
                    db.execute(
                        "UPDATE tracks SET path=?,sha256=?,category=?,status='ready',error='',updated_at=? WHERE id=?",
                        (relative, file_hash, category, now(), track_id),
                    )
                    self.store.bump(db)
                # Old path may remain after an interrupted reorganization. Never remove it blindly.
            except Cancelled:
                raise
            except Exception as exc:
                failures.append((metadata["name"], str(exc)))
                with self.store.connect() as db:
                    db.execute(
                        "UPDATE tracks SET status='error',error=? WHERE id=?", (str(exc)[:700], track_id)
                    )
                self.progress(f"Falha: {metadata['name']} · {exc}")
            finally:
                shutil.rmtree(staging)
        self.reorganize()
        self.store.log(
            "sync", f"{total - len(failures)} downloads; {plan.retained} reutilizadas; {len(failures)} falhas"
        )
        return {"downloaded": total - len(failures), "reused": plan.retained, "failures": failures}

    def reorganize(self):
        for track in self.store.tracks():
            self.check_cancel()
            if not track["path"]:
                continue
            metadata = json.loads(track["metadata"])
            relative = self.relative_path(track["id"], metadata, track["override"] or track["category"])
            if relative == track["path"]:
                continue
            source, target = inside(self.music, track["path"]), inside(self.music, relative)
            if not source.is_file():
                continue
            if digest(source) != track["sha256"]:
                raise ValueError("Arquivo modificado externamente; reorganização bloqueada: " + str(source))
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and digest(target) != track["sha256"]:
                raise ValueError("Conflito de nomes na reorganização: " + str(target))
            # Copy first, commit new path, then remove old verified copy. Crash-safe on both sides.
            from .paths import atomic_copy

            if not target.exists():
                atomic_copy(source, target, track["sha256"])
            with self.store.connect() as db:
                db.execute("UPDATE tracks SET path=? WHERE id=?", (relative, track["id"]))
                self.store.bump(db)
            source.unlink()

    def correct_genre(self, track_id, category):
        if category and category not in {*CATEGORIES, "Outros"}:
            raise ValueError("Categoria inválida.")
        with self.store.connect() as db:
            db.execute("UPDATE tracks SET override=? WHERE id=?", (category or None, track_id))
            self.store.bump(db)
        self.reorganize()

    def orphan_preview(self):
        return [t for t in self.store.tracks() if not t["references_count"] and t["path"]]

    def quarantine(self, tracks, revision):
        if self.store.setting("revision") != revision:
            raise ValueError("A biblioteca mudou. Gere outra prévia de limpeza.")
        batch = uuid.uuid4().hex
        for track in tracks:
            self.check_cancel()
            current = self.store.rows(
                """SELECT t.* FROM tracks t WHERE t.id=? AND NOT EXISTS
                (SELECT 1 FROM membership m WHERE m.track_id=t.id)""",
                (track["id"],),
            )
            if not current or current[0]["path"] != track["path"]:
                raise ValueError("Uma faixa voltou a ser usada; limpeza interrompida.")
            source = inside(self.music, track["path"])
            if source.exists():
                if digest(source) != track["sha256"]:
                    raise ValueError("Arquivo alterado externamente; limpeza bloqueada.")
                target = inside(self.store.root, "trash/" + batch + "/" + track["path"])
                target.parent.mkdir(parents=True, exist_ok=True)
                # Copy first so a crash never loses the last referenced bytes.
                from .paths import atomic_copy

                atomic_copy(source, target, track["sha256"])
            with self.store.connect() as db:
                db.execute(
                    "UPDATE tracks SET path=NULL,sha256=NULL,status='pending' WHERE id=?", (track["id"],)
                )
                self.store.bump(db)
            source.unlink(missing_ok=True)
        self.store.log("cleanup", f"{len(tracks)} faixas movidas para trash/{batch}")
        return str(self.store.root / "trash" / batch)
