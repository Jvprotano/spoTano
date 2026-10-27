"""Incremental library operations, independent of the network adapter and GUI."""

import json
import re
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .audio import DurationMismatch, needs_genre, validate_duration, validate_mp3, write_genre
from .files import AudioFiles
from .genres import CATEGORIES, GenreResolver
from .paths import digest, inside, playlist_url, safe_name
from .provider import Cancelled
from .telemetry import RunMetrics, sanitize


def now():
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class SyncPlan:
    revision: int
    snapshots: list
    downloads: list = field(default_factory=list)
    added: list = field(default_factory=list)
    removed: list = field(default_factory=list)
    retained: int = 0
    force: bool = False
    warnings: list = field(default_factory=list)
    refresh_metadata: bool = True
    preserve_removed: bool = False
    remove_missing: bool = False
    cleanup: list = field(default_factory=list)


class Library:
    def __init__(self, store, provider, progress=lambda message: None, cancel=None, validator=validate_mp3):
        self.store, self.provider, self.progress = store, provider, progress
        self.cancel = cancel or threading.Event()
        self.validator = validator
        self.music = self.store.root / "Music"
        self.music.mkdir(exist_ok=True)
        self.files = AudioFiles(store, progress)
        self.files.recover()

    def check_cancel(self):
        if self.cancel.is_set():
            raise Cancelled("Operação cancelada; arquivos anteriores preservados.")

    def available(self, track):
        if not track.get("path") or not track.get("sha256"):
            return False
        path = inside(self.music, track["path"])
        return path.is_file() and digest(path) == track["sha256"]

    def validate_snapshot(self, snapshot):
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("tracks"), list):
            raise ValueError("Snapshot inválido; biblioteca preservada.")
        if not snapshot.get("name"):
            raise ValueError("Nome da playlist ausente.")
        for track in snapshot["tracks"]:
            if not re.fullmatch(r"[A-Za-z0-9]{22}", track.get("song_id", "")):
                raise ValueError("Identificador de faixa inválido.")
            if not track.get("name") or not track.get("artist"):
                raise ValueError("Metadados de faixa incompletos.")

    def save_snapshot(self, db, playlist_id, snapshot):
        for track in snapshot["tracks"]:
            db.execute(
                """INSERT INTO tracks(id,metadata) VALUES(?,?)
                ON CONFLICT(id) DO UPDATE SET metadata=excluded.metadata""",
                (track["song_id"], json.dumps(track, ensure_ascii=False)),
            )
        db.execute("DELETE FROM membership WHERE playlist_id=?", (playlist_id,))
        db.executemany(
            "INSERT OR IGNORE INTO membership VALUES(?,?,?)",
            [(playlist_id, track["song_id"], position) for position, track in enumerate(snapshot["tracks"])],
        )
        skipped = snapshot.get("skipped", 0)
        db.execute(
            "UPDATE playlists SET name=?,synced_at=?,warning=?,total=? WHERE id=?",
            (
                snapshot["name"],
                now(),
                f"{skipped} itens não suportados" if skipped else "",
                snapshot.get("total", len(snapshot["tracks"])),
                playlist_id,
            ),
        )

    def import_playlist(self, url):
        url = playlist_url(url)
        if self.store.rows("SELECT id FROM playlists WHERE url=?", (url,)):
            raise ValueError("Playlist já importada. Marque-a para consultar mudanças ou baixar áudios.")
        self.progress("Importando playlist: consultando nome e faixas no Spotify…")
        snapshot = self.provider.playlist(url)
        self.validate_snapshot(snapshot)
        self.check_cancel()
        with self.store.connect() as db:
            playlist_id = db.execute(
                "INSERT INTO playlists(url,name) VALUES(?,?)", (url, snapshot["name"])
            ).lastrowid
            self.save_snapshot(db, playlist_id, snapshot)
            self.store.bump(db)
        self.progress(
            f"Importada: {snapshot['name']} · {len(snapshot['tracks'])} faixas disponíveis. "
            "Marque a playlist para baixar os áudios."
        )
        return playlist_id

    def preview(self, force=False, playlist_ids=None, saved=False, remove_missing=False):
        revision = self.store.setting("revision")
        playlists = self.store.playlists()
        if playlist_ids is not None:
            requested = set(playlist_ids)
            playlists = [p for p in playlists if p["id"] in requested]
            if not requested or {p["id"] for p in playlists} != requested:
                raise ValueError("Marque pelo menos uma playlist válida.")
        if not playlists:
            raise ValueError("Adicione pelo menos uma playlist.")
        plan = SyncPlan(
            revision=revision, snapshots=[], force=force, refresh_metadata=not (force or saved),
            preserve_removed=saved, remove_missing=remove_missing,
        )
        desired = {}
        for playlist in playlists:
            self.check_cancel()
            if force or saved:
                if not playlist["synced_at"]:
                    raise ValueError(
                        f"{playlist['name']}: use Atualizar selecionadas para consultar a lista primeiro."
                    )
                self.progress(
                    f"Usando lista salva: {playlist['name']} · última consulta {playlist['synced_at']}."
                )
                snapshot = {
                    "name": playlist["name"],
                    "total": playlist["total"],
                    "skipped": max(0, (playlist["total"] or playlist["count"]) - playlist["count"]),
                    "tracks": [
                        json.loads(row["metadata"])
                        for row in self.store.rows(
                            """SELECT t.metadata FROM membership m JOIN tracks t ON t.id=m.track_id
                        WHERE m.playlist_id=? ORDER BY m.position""",
                            (playlist["id"],),
                        )
                    ],
                }
                plan.warnings.append(
                    f"{playlist['name']}: usa a lista já salva; para buscar mudanças no Spotify, "
                    "use Atualizar selecionadas."
                )
            else:
                self.progress(f"Lendo {playlist['name']}…")
                snapshot = self.provider.playlist(playlist["url"])
            self.validate_snapshot(snapshot)
            current_ids = {
                r["track_id"]
                for r in self.store.rows(
                    "SELECT track_id FROM membership WHERE playlist_id=?", (playlist["id"],)
                )
            }
            previous = {
                r["track_id"]: json.loads(r["metadata"])
                for r in self.store.rows(
                    "SELECT track_id,metadata FROM download_membership WHERE playlist_id=?", (playlist["id"],)
                )
            }
            old = set(previous)
            if old and not playlist["downloaded_at"]:
                plan.warnings.append(
                    f"{snapshot['name']}: catálogo antigo; a referência é a última lista "
                    "salva, sem confirmação histórica de download concluído."
                )
            if snapshot.get("skipped", 0):
                plan.warnings.append(
                    f"{snapshot['name']}: {snapshot['skipped']} itens indisponíveis ou "
                    "não suportados não serão baixados."
                )
            ids = set()
            for track in snapshot["tracks"]:
                ids.add(track["song_id"])
                desired[track["song_id"]] = track
            # Unknown/local/deleted items cannot prove that former tracks were removed.
            if snapshot.get("skipped", 0) and (old | current_ids) - ids:
                raise ValueError(
                    f"{snapshot['name']}: há itens indisponíveis e possíveis remoções. "
                    "O estado anterior foi preservado. Resolva os itens no Spotify e atualize."
                )
            plan.added.extend((snapshot["name"], desired[i]["name"]) for i in sorted(ids - old))
            plan.removed.extend((snapshot["name"], previous[i]["name"]) for i in sorted(old - ids))
            plan.snapshots.append((playlist["id"], snapshot))
            self.progress(
                f"Lida: {snapshot['name']} · {len(ids)} faixas · "
                f"{len(ids - old)} inclusões · {len(old - ids)} saídas em relação aos downloads mantidos."
            )
        existing = {t["id"]: t for t in self.store.tracks()}
        for track_id, metadata in desired.items():
            self.check_cancel()
            self.progress(f"Verificando arquivo local: {metadata['artist']} — {metadata['name']}")
            if force or track_id not in existing or not self.available(existing[track_id]):
                plan.downloads.append(metadata)
            else:
                plan.retained += 1
        if remove_missing:
            plan.cleanup = self.removal_candidates(plan)
        if revision != self.store.setting("revision"):
            raise ValueError("A biblioteca mudou durante a consulta. Gere outra prévia.")
        self.progress(
            f"Prévia pronta: {len(plan.downloads)} downloads · {plan.retained} reutilizadas. "
            "Aguardando confirmação."
        )
        return plan

    def refresh_playlists(self, playlist_ids):
        """Read and verify all selected playlists before saving metadata, never audio."""
        plan = self.preview(playlist_ids=playlist_ids)
        self.check_cancel()
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            revision = int(db.execute("SELECT value FROM settings WHERE key='revision'").fetchone()[0])
            if revision != plan.revision:
                raise ValueError("Prévia desatualizada. Consulte as playlists novamente.")
            for playlist_id, snapshot in plan.snapshots:
                self.save_snapshot(db, playlist_id, snapshot)
            missing = {track["song_id"] for track in plan.downloads}
            for _, snapshot in plan.snapshots:
                for track in snapshot["tracks"]:
                    if track["song_id"] not in missing:
                        db.execute("UPDATE tracks SET status='ready',error='' WHERE id=? AND status='pending'",
                                   (track["song_id"],))
            for track in plan.downloads:
                db.execute("UPDATE tracks SET status='pending' WHERE id=?",
                           (track["song_id"],))
            self.store.bump(db)
        plan.revision = revision + 1
        plan.refresh_metadata = False
        self.store.log("refresh", f"{len(plan.snapshots)} playlists consultadas; nenhum áudio alterado")
        self.progress("Consulta concluída. Nenhum áudio foi baixado ou removido.")
        return plan

    def removal_candidates(self, plan):
        """Only removed downloads owned exclusively by this selection can be quarantined."""
        departing = set()
        for playlist_id, snapshot in plan.snapshots:
            current = {t["song_id"] for t in snapshot["tracks"]}
            departing.update(
                (playlist_id, row["track_id"])
                for row in self.store.rows(
                    "SELECT track_id FROM download_membership WHERE playlist_id=?", (playlist_id,)
                ) if row["track_id"] not in current
            )
        candidates = {track_id for _, track_id in departing}
        protected = {
            row["track_id"] for row in self.store.rows("SELECT playlist_id,track_id FROM download_membership")
            if (row["playlist_id"], row["track_id"]) not in departing
        }
        return [t for t in self.orphan_preview() if t["id"] in candidates - protected]

    def relative_path(self, track_id, metadata, category):
        folder = category if self.store.setting("by_genre", True) else safe_name(metadata["artist"])
        return (
            f"{safe_name(folder)}/{safe_name(metadata['artist'] + ' - ' + metadata['name'])} [{track_id}].mp3"
        )

    def apply(self, plan):
        workers = max(1, min(4, int(self.store.setting("download_workers", 2))))
        run = RunMetrics(self.store, len(plan.downloads), plan.retained, workers)
        self.last_run = run.directory
        self.progress(f"Execução {run.run_id} · métricas e diagnóstico em {run.directory}")
        if hasattr(self.provider, "download_settings"):
            self.provider.download_settings = {"conversion_workers": self.store.setting("conversion_workers", 2)}
        try:
            result = self._apply(plan, run)
            run.finish("completed_with_errors" if result["failures"] else "completed", **result)
            result["run_directory"] = str(run.directory)
            return result
        except BaseException as exc:
            run.finish("cancelled" if isinstance(exc, Cancelled) else "failed", error=str(exc))
            raise

    def _apply(self, plan, run):
        with GenreResolver(self.store, self.progress, self.cancel) as resolver:
            return self._apply_with_resolver(plan, run, resolver)

    def _apply_with_resolver(self, plan, run, resolver):
        self.check_cancel()
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            revision = int(db.execute("SELECT value FROM settings WHERE key='revision'").fetchone()[0])
            if revision != plan.revision:
                raise ValueError("Prévia desatualizada. Gere uma nova prévia.")
            if plan.refresh_metadata:
                for playlist_id, snapshot in plan.snapshots:
                    self.save_snapshot(db, playlist_id, snapshot)
            self.store.bump(db)
        resolver = GenreResolver(self.store, self.progress, self.cancel)
        failures = []
        total = len(plan.downloads)
        failed_ids = set()
        workers = max(1, min(4, int(self.store.setting("download_workers", 2))))
        self.progress(
            f"Iniciando: {total} downloads; {plan.retained} arquivos serão reutilizados; "
            f"até {workers} músicas em paralelo."
        )
        batch_started = time.monotonic()
        completed = 0
        current_tracks = {row["id"]: row for row in self.store.tracks()}

        def report_batch():
            self.progress(
                {
                    "kind": "batch_progress",
                    "total": total,
                    "completed": completed,
                    "failed": len(failures),
                    "reused": plan.retained,
                }
            )

        report_batch()

        def download(index, metadata):
            self.check_cancel()
            started = time.monotonic()
            track_id = metadata["song_id"]
            label = f"{index}/{total} · {metadata['artist']} — {metadata['name']}"
            self.progress(f"Classificando gênero · {label}")
            staging = self.store.root / "staging" / uuid.uuid4().hex
            staging.mkdir(parents=True)
            try:
                current = current_tracks[track_id]

                def classify_track():
                    began = time.monotonic()
                    category = current["override"] or resolver.resolve(metadata)
                    run.record("classification", track_id=track_id, category=category,
                               seconds=round(time.monotonic() - began, 3))
                    return category

                classification = genre_pool.submit(classify_track)
                self.check_cancel()
                output = staging / "audio.mp3"
                source = self.store.rows("SELECT url FROM audio_sources WHERE track_id=?", (track_id,))
                request = {**metadata, "_cached_match": self.store.audio_match(metadata),
                           "_source_url": source[0]["url"] if source else None}
                run.record("track_start", track_id=track_id, name=metadata["name"], artist=metadata["artist"],
                           expected_duration=metadata.get("duration"), cache_hit=bool(request["_cached_match"]))
                self.progress(f"Iniciando download · {label}")
                try:
                    evidence = self.provider.download(request, output)
                except Exception:
                    if request["_cached_match"]:
                        with self.store.connect() as db:
                            db.execute("DELETE FROM audio_matches WHERE track_id=?", (track_id,))
                    raise
                category = classification.result()
                self.check_cancel()
                self.progress(f"Validando MP3 e calculando SHA-256 · {label}")
                if self.validator is validate_mp3:
                    write_genre(output, category)
                info = self.validator(output)
                if self.validator is validate_mp3:
                    validate_duration(info.length, metadata.get("duration"))
                relative = self.relative_path(track_id, metadata, category)
                from .matching import fingerprint

                match = evidence.get("match") if isinstance(evidence, dict) else None
                self.files.install(output, current, relative, category,
                                   match=match if match and match.get("version") else None,
                                   fingerprint=fingerprint(metadata))
                run.record("track_finished", track_id=track_id, status="ready", category=category,
                           seconds=round(time.monotonic() - started, 3),
                           evidence=evidence if isinstance(evidence, dict) else {})
                self.progress(f"Salvo · {label} · {relative}")
                self.progress(f"Tempo total da faixa · {label} · {time.monotonic() - started:.1f}s")
            except Cancelled:
                raise
            except Exception as exc:
                message = sanitize(str(exc))
                with self.store.connect() as db:
                    if isinstance(exc, DurationMismatch):
                        db.execute("DELETE FROM audio_matches WHERE track_id=?", (track_id,))
                    db.execute(
                        "UPDATE tracks SET status='error',error=? WHERE id=?", (message[:1800], track_id)
                    )
                run.record("track_finished", track_id=track_id, status="error", error=message,
                           seconds=round(time.monotonic() - started, 3), evidence=getattr(exc, "diagnostic", {}))
                self.progress(f"Falha: {metadata['name']} · {message}")
                return track_id, (metadata["name"], message)
            finally:
                shutil.rmtree(staging)
            return track_id, None

        pool_context = (
            self.provider.download_batch if hasattr(self.provider, "download_batch") else nullcontext
        )
        with (
            pool_context(),
            ThreadPoolExecutor(max_workers=workers, thread_name_prefix="spotano-genres") as genre_pool,
            ThreadPoolExecutor(max_workers=workers, thread_name_prefix="spotano-download") as pool,
        ):
            # Submit only a bounded window, so cancellation doesn't leave hundreds of queued jobs.
            iterator = iter(enumerate(plan.downloads, 1))
            pending = {
                pool.submit(download, *item)
                for item in [next(iterator, None) for _ in range(workers)]
                if item is not None
            }
            while pending:
                future = next(as_completed(pending))
                pending.remove(future)
                try:
                    track_id, failure = future.result()
                except BaseException:
                    self.cancel.set()
                    for other in pending:
                        other.cancel()
                    raise
                if failure:
                    failed_ids.add(track_id)
                    failures.append(failure)
                completed += 1
                report_batch()
                self.progress(
                    f"Progresso do lote: {completed}/{total} faixas finalizadas; {len(failures)} falhas."
                )
                self.check_cancel()
                item = next(iterator, None)
                if item is not None:
                    pending.add(pool.submit(download, *item))

        # Repair unknown categories in reused audio too, without another download.
        selected_ids = {t["song_id"] for _, snapshot in plan.snapshots for t in snapshot["tracks"]}
        downloaded_ids = {track["song_id"] for track in plan.downloads}
        for track in self.store.tracks():
            self.check_cancel()
            if (
                track["id"] in selected_ids
                and track["id"] not in failed_ids
                and track["id"] not in downloaded_ids
                and track["path"]
                and not track["override"]
                and (track["category"] == "Outros" or resolver.needs_refresh(json.loads(track["metadata"])))
            ):
                category = resolver.resolve(json.loads(track["metadata"]))
                if category != track["category"]:
                    with self.store.connect() as db:
                        db.execute("UPDATE tracks SET category=? WHERE id=?", (category, track["id"]))
                        self.store.bump(db)
        self.reorganize()
        removed = 0
        # Download failures or cancellation must never trigger a removal phase.
        if plan.remove_missing and not failures:
            cleanup = self.removal_candidates(plan)
            if {(t["id"], t["path"], t["sha256"]) for t in cleanup} != {
                (t["id"], t["path"], t["sha256"]) for t in plan.cleanup
            }:
                raise ValueError("Os arquivos para remoção mudaram. Gere outra prévia; áudios preservados.")
            if cleanup:
                self.quarantine(cleanup, self.store.setting("revision"))
                removed = len(cleanup)
        # Advance each playlist independently only after its entire download succeeds.
        for playlist_id, snapshot in plan.snapshots:
            self.check_cancel()
            if failed_ids.intersection(t["song_id"] for t in snapshot["tracks"]):
                continue
            with self.store.connect() as db:
                if not plan.preserve_removed or (plan.remove_missing and not failures):
                    db.execute("DELETE FROM download_membership WHERE playlist_id=?", (playlist_id,))
                db.executemany(
                    "INSERT OR REPLACE INTO download_membership VALUES(?,?,?)",
                    [
                        (playlist_id, t["song_id"], json.dumps(t, ensure_ascii=False))
                        for t in snapshot["tracks"]
                    ],
                )
                db.execute("UPDATE playlists SET downloaded_at=? WHERE id=?", (now(), playlist_id))
                self.store.bump(db)
        self.store.log(
            "sync", f"{total - len(failures)} downloads; {plan.retained} reutilizadas; {len(failures)} falhas"
        )
        self.progress(
            f"Finalizado: {total - len(failures)} downloads · {plan.retained} reutilizadas · "
            f"{len(failures)} falhas · {time.monotonic() - batch_started:.1f}s no lote."
        )
        return {"downloaded": total - len(failures), "reused": plan.retained, "failures": failures,
                "removed": removed}

    def reorganize(self):
        pending = {json.loads(row["payload"])["track_id"]
                   for row in self.store.rows("SELECT payload FROM file_transitions")}
        for track in self.store.tracks():
            self.check_cancel()
            if not track["path"] or track["id"] in pending:
                continue
            metadata = json.loads(track["metadata"])
            relative = self.relative_path(track["id"], metadata, track["override"] or track["category"])
            source, target = inside(self.music, track["path"]), inside(self.music, relative)
            if not source.is_file():
                continue
            category = track["override"] or track["category"]
            if relative == track["path"] and (self.validator is not validate_mp3
                                               or not needs_genre(source, category)):
                continue
            if digest(source) != track["sha256"]:
                raise ValueError("Arquivo modificado externamente; reorganização bloqueada: " + str(source))
            if target.exists() and digest(target) != track["sha256"]:
                raise ValueError("Conflito de nomes na reorganização: " + str(target))
            staging = self.store.root / "staging" / uuid.uuid4().hex
            staging.mkdir(parents=True)
            try:
                output = staging / "audio.mp3"
                shutil.copyfile(source, output)
                if self.validator is validate_mp3:
                    write_genre(output, category)
                    self.validator(output)
                self.files.install(output, track, relative, category)
            finally:
                shutil.rmtree(staging)

    def correct_genre(self, track_id, category):
        if category and category not in {*CATEGORIES, "Outros"}:
            raise ValueError("Categoria inválida.")
        with self.store.connect() as db:
            db.execute("UPDATE tracks SET override=? WHERE id=?", (category or None, track_id))
            self.store.bump(db)
        if not category:
            row = self.store.rows("SELECT metadata FROM tracks WHERE id=?", (track_id,))[0]
            with GenreResolver(self.store, self.progress, self.cancel) as resolver:
                automatic = resolver.resolve(json.loads(row["metadata"]))
            with self.store.connect() as db:
                db.execute("UPDATE tracks SET category=? WHERE id=?", (automatic, track_id))
                self.store.bump(db)
        self.reorganize()

    def correct_artist(self, track_id, category):
        from .genres import GenreResolver

        if category and category not in {*CATEGORIES, "Outros"}:
            raise ValueError("Categoria inválida.")
        row = self.store.rows("SELECT metadata FROM tracks WHERE id=?", (track_id,))[0]
        metadata = json.loads(row["metadata"])
        key = GenreResolver(self.store).artist_identity(metadata)
        with self.store.connect() as db:
            if category:
                db.execute("INSERT OR REPLACE INTO artist_categories VALUES(?,?)", (key, category))
            else:
                db.execute("DELETE FROM artist_categories WHERE artist=?", (key,))
            self.store.bump(db)
        self.reclassify(force=False, artist=key)

    def reclassify(self, force=True, artist=None):
        with GenreResolver(self.store, self.progress, self.cancel, force=force) as resolver:
            for track in self.store.tracks():
                self.check_cancel()
                metadata = json.loads(track["metadata"])
                if track["override"] or (artist and resolver.artist_identity(metadata) != artist):
                    continue
                category = resolver.resolve(metadata)
                with self.store.connect() as db:
                    db.execute("UPDATE tracks SET category=? WHERE id=?", (category, track["id"]))
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
