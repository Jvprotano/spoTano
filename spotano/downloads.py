"""A bounded set of reusable, killable SDK processes; one download per process."""

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from .matching import FastMatcher, canonical_youtube
from .paths import atomic_json
from .progress import download_progress
from .provider import Cancelled, ProviderError, stop_tree


def safe_error(exc):
    from .telemetry import sanitize

    message = sanitize(str(exc))
    return f"{type(exc).__name__}: {message[:700]}"


class WorkerExited(RuntimeError):
    def __init__(self, code, detail=""):
        self.code = code
        super().__init__(f"O mecanismo encerrou sem resposta (código {code}). " + detail)


class DownloadBatch:
    def __init__(self, provider):
        self.provider = provider
        self.sessions = {}
        self.lock = threading.Lock()
        self.temp = tempfile.TemporaryDirectory(prefix="spotano-batch-")

    def download(self, metadata, output):
        with self.lock:
            session = self.sessions.setdefault(threading.get_ident(), None)
            if session is None:
                settings = {**getattr(self.provider, "download_settings", {}), "gate_dir": self.temp.name}
                session = WarmDownload(self.provider.cancel, self.provider.progress, settings)
                self.sessions[threading.get_ident()] = session
        return session.download(metadata, output)

    def close(self):
        try:
            for session in self.sessions.values():
                session.close()
        finally:
            self.temp.cleanup()


class WarmDownload:
    def __init__(self, cancel, progress, settings=None):
        self.cancel, self.progress = cancel, progress
        self.temp = tempfile.TemporaryDirectory(prefix="spotano-download-")
        self.root = Path(self.temp.name)
        self.process = self.log = self.events = None
        self.sequence = 0
        self.starts = 0
        self.settings = settings or {}
        self.phase, self.phase_started = "prepare", time.monotonic()

    def start(self):
        self.stop()
        self.starts += 1
        # A dead worker may leave a native child finishing an old file. A new
        # process must never share that scratch directory, especially on retry.
        self.root = Path(self.temp.name) / f"worker-{self.starts}"
        self.root.mkdir()
        request = self.root / "session.json"
        atomic_json(request, {"action": "session", "payload": self.settings})
        activity = self.root / "progress.jsonl"
        activity.write_text("", encoding="utf-8")
        self.events = activity.open(encoding="utf-8")
        self.log = (self.root / "worker.log").open("w", encoding="utf-8")
        command = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "spotano"]
        options = (
            {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
        )
        self.process = subprocess.Popen(
            command + ["--worker", str(request), str(self.root / "closed.json")],
            stdout=self.log,
            stderr=self.log,
            **options,
        )

    def drain(self, label):
        received = False
        while True:
            position = self.events.tell()
            line = self.events.readline()
            if not line.endswith("\n"):
                self.events.seek(position)
                return received
            message = json.loads(line)["message"]
            phases = {"Buscando correspondência": "search", "Obtendo informações": "extraction",
                      "Recebendo áudio": "transfer", "Convertendo com FFmpeg": "conversion",
                      "Aguardando vaga": "conversion_queue", "Gravando tags": "tags"}
            phase = next((value for prefix, value in phases.items() if str(message).startswith(prefix)), None)
            if phase and phase != self.phase:
                self.phase, self.phase_started = phase, time.monotonic()
            self.progress(f"{label} · {message}")
            received = True

    def download(self, metadata, output, timeout=480):
        started = time.monotonic()
        exits = []
        for attempt in range(2):
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError("O provedor excedeu o tempo limite durante a recuperação do mecanismo.")
            try:
                result = self._download(metadata, output, timeout=remaining)
                if isinstance(result, dict):
                    result.setdefault("metrics", {}).update(worker_restarts=len(exits), worker_exit_codes=exits)
                return result
            except WorkerExited as exc:
                exits.append(exc.code)
                if attempt:
                    raise
                if self.cancel.is_set():
                    raise Cancelled("Operação cancelada; arquivos anteriores preservados.") from exc
                self.progress(f"{metadata['artist']} — {metadata['name']} · {exc} "
                              "Reiniciando o mecanismo e repetindo esta faixa uma única vez.")

    def _download(self, metadata, output, timeout=480):
        label = f"{metadata['artist']} — {metadata['name']}"
        if self.cancel.is_set():
            raise Cancelled("Operação cancelada; arquivos anteriores preservados.")
        fresh = self.process is None or self.process.poll() is not None
        if fresh:
            self.start()
        self.progress(f"{label} · {'Preparando' if fresh else 'Reutilizando'} mecanismo de download.")
        self.sequence += 1
        response = self.root / f"result-{self.sequence}.json"
        atomic_json(
            self.root / "inbox.json",
            {
                "sequence": self.sequence,
                "metadata": metadata,
                "output": str(Path(output).resolve()),
            },
        )
        started = last_event = last_notice = time.monotonic()
        self.phase, self.phase_started = "prepare", started
        try:
            while not response.exists():
                if self.drain(label):
                    last_event = time.monotonic()
                if self.cancel.wait(0.15):
                    raise Cancelled("Operação cancelada; arquivos anteriores preservados.")
                current = time.monotonic()
                if current - last_notice >= 10 and current - last_event >= 10:
                    self.progress(
                        f"{label} · {int(current - started)}s decorridos; "
                        f"sem novas etapas há {int(current - last_event)}s. "
                        f"Aguardando provedor; limite de {timeout}s. Você pode cancelar."
                    )
                    last_notice = current
                if current - started > timeout:
                    raise TimeoutError(
                        "O provedor excedeu o tempo limite; o mecanismo será reiniciado na próxima faixa."
                    )
                phase_limits = {"prepare": 60, "search": 90, "extraction": 90, "transfer": 120,
                                "conversion_queue": 125, "conversion": 180, "tags": 30}
                if current - self.phase_started > phase_limits[self.phase]:
                    label = {"prepare": "preparação", "search": "busca", "extraction": "extração",
                             "transfer": "transferência", "conversion": "conversão",
                             "conversion_queue": "fila de conversão", "tags": "gravação de tags"}[self.phase]
                    raise TimeoutError(f"Etapa de {label} excedeu {phase_limits[self.phase]}s; "
                                       "mecanismo será reiniciado. Diagnóstico preservado na execução.")
                if self.process.poll() is not None and not response.exists():
                    self.log.flush()
                    with (self.root / "worker.log").open("rb") as stream:
                        stream.seek(max(0, stream.seek(0, 2) - 3000))
                        detail = safe_error(RuntimeError(stream.read().decode("utf-8", errors="replace")))
                    raise WorkerExited(self.process.returncode, detail if detail != "RuntimeError: " else "")
            self.drain(label)
            data = json.loads(response.read_text(encoding="utf-8"))
            response.unlink()
        except BaseException:
            self.stop()
            raise
        if "error" in data:
            raise ProviderError(data["error"], data.get("diagnostic"))
        return data["result"]

    def stop(self):
        if self.process is not None:
            if self.process.poll() is None:
                stop_tree(self.process)
            self.process = None
        for stream in (self.log, self.events):
            if stream is not None:
                stream.close()
        self.log = self.events = None
        (self.root / "inbox.json").unlink(missing_ok=True)

    def close(self):
        try:
            if self.process is not None and self.process.poll() is None:
                atomic_json(self.root / "inbox.json", {"stop": True})
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
        finally:
            self.stop()
            self.temp.cleanup()


def saved_song(metadata):
    """Empty, unavailable fields must not trigger spotDL's per-song Spotify refresh."""
    from spotdl.types.song import Song

    song_id = metadata.get("song_id", "")
    if not re.fullmatch(r"[A-Za-z0-9]{22}", song_id):
        raise ValueError("Identificador de faixa inválido.")
    values = {key: value for key, value in metadata.items() if key in Song.__dataclass_fields__}
    defaults = {
        "genres": [],
        "disc_count": 0,
        "tracks_count": 0,
        "track_number": 0,
        "disc_number": 0,
        "album_id": "",
        "album_artist": metadata["artist"],
        "artists": [metadata["artist"]],
        "album_name": "",
        "duration": 0,
        "year": 0,
        "date": "",
        "publisher": "",
        "isrc": "",
        "explicit": False,
        "url": "https://open.spotify.com/track/" + song_id,
    }
    for key, default in defaults.items():
        if values.get(key) is None:
            values[key] = default
    return Song.from_missing_data(**values)


class DownloadEngine:
    def __init__(self, root, progress, settings=None):
        started = time.monotonic()
        self.root, self.progress = Path(root).resolve(), progress
        self.settings = settings or {}
        self.download_count = 0
        progress("Preparando bibliotecas e provedores uma vez para este processo…")
        import asyncio

        import spotdl.download.downloader as sdk_downloader
        import spotdl.providers.audio.base as sdk_audio
        from spotdl.utils.deno import get_deno_path
        from spotdl.utils.ffmpeg import get_ffmpeg_path

        ffmpeg = get_ffmpeg_path()
        if not ffmpeg:
            raise ValueError("Instale os componentes em Configurações → Preparar downloads.")
        deno = get_deno_path()
        if deno and str(deno.parent) not in os.environ.get("PATH", "").split(os.pathsep):
            os.environ["PATH"] = str(deno.parent) + os.pathsep + os.environ.get("PATH", "")
        # spotDL 4.6.0 shares temp/<video-id> globally. Separate lanes must never write there together.
        private_temp = self.root / "provider-temp"
        private_temp.mkdir(parents=True, exist_ok=True)
        self.sdk_modules = (sdk_downloader, sdk_audio)
        self.original_temp = [module.get_temp_path for module in self.sdk_modules]
        for module in self.sdk_modules:
            module.get_temp_path = lambda: private_temp
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.downloader = sdk_downloader.Downloader(
                settings={
                    "output": str(self.root / "audio" / "{track-id}.{output-ext}"),
                    "format": "mp3",
                    "bitrate": "192k",
                    "ffmpeg": str(ffmpeg),
                    "ffmpeg_args": "-ar 44100 -ac 2 -id3v2_version 3",
                    "threads": 1,
                    "lyrics_providers": [],
                    "audio_providers": ["youtube-music", "youtube"],
                    "overwrite": "force",
                    "simple_tui": True,
                    "skip_album_art": True,
                    "fetch_albums": False,
                    "scan_for_songs": False,
                    "yt_dlp_args": "--socket-timeout 12 --retries 2 --extractor-retries 1",
                },
                loop=self.loop,
            )
            from functools import partial

            self.matcher = FastMatcher(self.downloader.audio_providers, progress)
            for provider in self.downloader.audio_providers:
                if hasattr(provider, "client"):
                    session = provider.client._session
                    session.request = partial(session.request, timeout=10)
            self.original_convert = sdk_downloader.async_convert
            # The SDK creates a fresh YoutubeDL for every song, losing HTTP connections
            # and initialized extractors. Each worker handles one song at a time.
            self.original_audio_provider = sdk_downloader.AudioProvider
            self.audio_provider = None

            def reusable_audio_provider(**options):
                if self.audio_provider is None:
                    self.audio_provider = self.original_audio_provider(**options)
                    self.metrics["audio_provider_initializations"] = 1
                else:
                    self.metrics["audio_provider_reused"] = True
                # Never deliver the next song's bytes to a previous song's tracker.
                self.audio_provider.audio_handler._progress_hooks.clear()
                return self.audio_provider

            sdk_downloader.AudioProvider = reusable_audio_provider

            async def limited_convert(*args, **kwargs):
                from .processes import conversion_slot

                self.progress("Aguardando vaga para conversão com FFmpeg")
                self.phase("conversion_queue")
                directory = Path(self.settings.get("gate_dir", self.root)) / "conversion-slots"
                with conversion_slot(directory, int(self.settings.get("conversion_workers", 2))) as waited:
                    self.metrics["queue_wait_s"] = round(waited, 3)
                    self.progress("Convertendo com FFmpeg para MP3 · 0%")
                    self.phase("Converting")
                    return await self.original_convert(*args, **kwargs)

            sdk_downloader.async_convert = limited_convert
        except BaseException:
            self.close()
            raise
        self.prepare_seconds = time.monotonic() - started
        progress(f"Mecanismo pronto em {self.prepare_seconds:.1f}s; sem nova consulta ao Spotify por faixa.")

    def download(self, metadata, output):
        song = saved_song(metadata)
        started = time.monotonic()
        self.metrics, self.stage, self.stage_started = {}, "prepare", started
        self.track_started, self.active_match, self.failed_phase = started, None, None
        self.matcher.last_candidates = []
        self.metrics["initialization_s"] = self.prepare_seconds if not self.download_count else 0
        self.download_count += 1
        self.matcher.stats = {"queries": 0, "candidates": 0, "view_extractions": 0}
        self.provider_error = ""
        self.progress("Buscando correspondência nos provedores de áudio")
        self.phase("search")
        manual = metadata.get("_source_url")
        cached = metadata.get("_cached_match")
        candidates = []
        if manual:
            candidates = [{"url": canonical_youtube(manual), "manual": True}]
        elif song.download_url:
            # An explicitly supplied source is also used for authorized local integration samples.
            candidates = [{"url": song.download_url, "explicit": True}]
        elif cached:
            candidates = [cached]
            self.progress("Reutilizando correspondência confirmada; extração da mídia será renovada.")
        else:
            candidates = self.matcher.candidates(metadata)
        failures, match = [], None
        tried, path = set(), None
        for attempt in range(3):
            candidate = next((row for row in candidates if row["url"] not in tried), None)
            if candidate is None:
                if attempt and not manual and not metadata.get("download_url"):
                    try:
                        self.progress("Buscando correspondência alternativa após falha do provedor")
                        self.phase("search")
                        candidates += self.matcher.candidates(metadata, exclude=tried)
                        candidate = next((row for row in candidates if row["url"] not in tried), None)
                    except ValueError as exc:
                        failures.append(safe_error(exc))
                if candidate is None:
                    break
            tried.add(candidate["url"])
            match = candidate
            self.active_match = candidate
            song.download_url = candidate["url"]
            self.downloader.errors.clear()
            self.provider_error = ""
            self.downloader.progress_handler = download_progress(self.progress, self.phase,
                                                                 self.capture_error)
            self.progress(f"Correspondência · tentativa {attempt + 1}/3 · "
                          + ("fonte escolhida" if manual else f"{candidate.get('score', 100):.1f} pontos"))
            self.progress("Obtendo informações do áudio")
            self.phase("extraction")
            _, path = self.downloader.download_song(song)
            if path is not None and Path(path).is_file():
                break
            reason = self.provider_error or (self.downloader.errors[-1] if self.downloader.errors
                                             else "Mecanismo sem arquivo de saída")
            failures.append(safe_error(RuntimeError(reason)))
            self.progress("Tentativa falhou · " + failures[-1])
            if manual or metadata.get("download_url"):
                break
            if cached:
                cached = None
                self.progress("Correspondência em cache falhou; buscando alternativas compatíveis.")
                self.phase("search")
                candidates += self.matcher.candidates(metadata, exclude=tried)
        if path is None or not Path(path).is_file():
            raise ValueError("Áudio não concluído: " + "; ".join(failures)[-1800:])
        actual, target = Path(path).resolve(), Path(output).resolve()
        if not actual.is_relative_to(self.root / "audio"):
            raise ValueError("O mecanismo retornou um arquivo fora da pasta temporária.")
        if actual != target:
            os.replace(actual, target)
        self.phase("finished")
        self.metrics.update(self.matcher.stats)
        self.metrics["total_s"] = round(time.monotonic() - started, 3)
        self.metrics["cache_hit"] = bool(metadata.get("_cached_match")
                                         and match["url"] == metadata["_cached_match"]["url"])
        self.metrics["attempts"] = len(tried)
        self.progress(f"Busca, transferência e conversão: {time.monotonic() - started:.1f}s.")
        return {"output": str(target), "match": match, "metrics": self.metrics}

    def capture_error(self, message):
        self.provider_error = message

    def diagnostic(self):
        from .telemetry import sanitize

        metrics = dict(getattr(self, "metrics", {}))
        metrics.update(self.matcher.stats)
        stage = getattr(self, "stage", "prepare")
        if hasattr(self, "stage_started"):
            metrics[stage + "_s"] = round(metrics.get(stage + "_s", 0)
                                          + time.monotonic() - self.stage_started, 3)
        metrics["total_s"] = round(time.monotonic() - getattr(self, "track_started", time.monotonic()), 3)
        return sanitize({"stage": getattr(self, "failed_phase", None) or stage, "metrics": metrics,
                         "match": getattr(self, "active_match", None),
                         "candidates": self.matcher.last_candidates})

    def phase(self, stage):
        if stage == "Error":
            self.failed_phase = self.stage
        stage = {"Searching for song": "search", "Getting audio meta": "extraction",
                 "Downloading": "transfer", "Converting": "conversion", "Embedding metadata": "tags",
                 "Done": "validation_pending", "Error": "error"}.get(stage, stage)
        if stage == self.stage:
            return
        current = time.monotonic()
        key = self.stage + "_s"
        self.metrics[key] = round(self.metrics.get(key, 0) + current - self.stage_started, 3)
        self.stage, self.stage_started = stage, current

    def close(self):
        if hasattr(self, "original_audio_provider"):
            self.sdk_modules[0].AudioProvider = self.original_audio_provider
            if self.audio_provider is not None:
                self.audio_provider.audio_handler.close()
        if hasattr(self, "original_convert"):
            self.sdk_modules[0].async_convert = self.original_convert
        for module, original in zip(self.sdk_modules, self.original_temp):
            module.get_temp_path = original
        self.loop.run_until_complete(self.loop.shutdown_default_executor())
        self.loop.close()


def session_worker(root, progress, settings=None):
    engine = None
    inbox = root / "inbox.json"
    try:
        while True:
            if not inbox.exists():
                time.sleep(0.05)
                continue
            job = json.loads(inbox.read_text(encoding="utf-8"))
            inbox.unlink()
            if job.get("stop"):
                return "closed"
            try:
                if engine is None:
                    engine = DownloadEngine(root, progress, settings)
                answer = {"result": engine.download(job["metadata"], job["output"])}
            except Exception as exc:
                diagnostic = engine.diagnostic() if engine is not None and hasattr(engine, "diagnostic") else {}
                answer = {"error": safe_error(exc), "diagnostic": diagnostic}
            atomic_json(root / f"result-{int(job['sequence'])}.json", answer)
    finally:
        if engine is not None:
            engine.close()
