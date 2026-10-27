"""A killable, bounded subprocess isolates upstream SDKs from UI and state."""

import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path


class Cancelled(Exception):
    pass


class ProviderError(RuntimeError):
    def __init__(self, message, diagnostic=None):
        super().__init__(message)
        self.diagnostic = diagnostic or {}


def stop_tree(process):
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=15,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=20)


class SpotProvider:
    def __init__(self, cancel=None, progress=lambda message: None):
        self.cancel = cancel or threading.Event()
        self.progress = progress
        self._batch = None
        self.download_settings = {}

    def call(self, action, payload=None, timeout=300):
        with tempfile.TemporaryDirectory(prefix="spotano-worker-") as temp:
            request, result = Path(temp) / "request.json", Path(temp) / "result.json"
            request.write_text(json.dumps({"action": action, "payload": payload or {}}), encoding="utf-8")
            command = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "spotano"]
            command += ["--worker", str(request), str(result)]
            activity = Path(temp) / "progress.jsonl"
            activity.touch()
            kwargs = (
                {"creationflags": subprocess.CREATE_NO_WINDOW}
                if os.name == "nt"
                else {"start_new_session": True}
            )
            labels = {
                "playlist": "Consulta ao Spotify",
                "download": "Download de áudio",
                "setup": "Preparação de componentes",
                "local": "Conversão de áudio local",
                "diagnostics": "Diagnóstico",
            }
            label = labels.get(action, action)
            self.progress(f"{label}: iniciando mecanismo (limite de {timeout}s).")
            with (
                (Path(temp) / "worker.log").open("w", encoding="utf-8") as log,
                activity.open(encoding="utf-8") as updates,
            ):
                process = subprocess.Popen(command, stdout=log, stderr=log, **kwargs)
                started = last_event = last_notice = time.monotonic()

                def drain():
                    nonlocal last_event
                    while True:
                        position = updates.tell()
                        line = updates.readline()
                        if not line.endswith("\n"):
                            updates.seek(position)
                            break
                        try:
                            self.progress(json.loads(line)["message"])
                            last_event = time.monotonic()
                        except (ValueError, KeyError):
                            pass

                try:
                    while process.poll() is None:
                        drain()
                        if self.cancel.wait(0.15):
                            raise Cancelled("Operação cancelada; arquivos anteriores preservados.")
                        current = time.monotonic()
                        if current - last_notice >= 10 and current - last_event >= 10:
                            self.progress(
                                f"{label}: {int(current - started)}s decorridos; "
                                f"sem novas etapas há {int(current - last_event)}s. "
                                f"Aguardando provedor; limite de {timeout}s. Você pode cancelar."
                            )
                            last_notice = current
                        if current - started > timeout:
                            raise TimeoutError(
                                "O provedor excedeu o tempo limite. Tente atualizar novamente."
                            )
                finally:
                    if process.poll() is None:
                        stop_tree(process)
                drain()
            if not result.exists():
                raise RuntimeError("O mecanismo de download encerrou sem resposta. Verifique a instalação.")
            data = json.loads(result.read_text(encoding="utf-8"))
            if "error" in data:
                raise ProviderError(data["error"], data.get("diagnostic"))
            return data["result"]

    def playlist(self, url):
        return self.call("playlist", {"url": url})

    def download(self, metadata, output):
        if self._batch is not None:
            return self._batch.download(metadata, output)
        return self.call("download", {"metadata": metadata, "output": str(output)}, timeout=480)

    @contextmanager
    def download_batch(self):
        from .downloads import DownloadBatch

        if self._batch is not None:
            raise RuntimeError("Já há um lote de downloads em execução.")
        batch = self._batch = DownloadBatch(self)
        try:
            yield batch
        finally:
            try:
                batch.close()
            finally:
                self._batch = None

    def setup(self):
        return self.call("setup", timeout=600)

    def candidates(self, metadata):
        return self.call("candidates", {"metadata": metadata}, timeout=120)


def strict_playlist(client, url, progress=lambda message: None):
    """Reject incomplete pages and changing snapshots, including empty snapshots."""
    from .paths import playlist_url

    url = playlist_url(url)
    before = client.playlist(url)
    if not before or not before.get("name"):
        raise ValueError("Playlist inacessível. Verifique se é pública e se o link está correto.")
    response = client.playlist_items(url)
    if not isinstance(response, dict) or not isinstance(response.get("items"), list):
        raise ValueError("Resposta incompleta do Spotify; estado anterior preservado.")
    total = response.get("total")
    if not isinstance(total, int) or total < 0:
        raise ValueError("O provedor não informou o total da playlist; atualização bloqueada.")
    items = []
    visited = set()
    while True:
        if response.get("total", total) != total:
            raise ValueError("A playlist mudou durante a consulta. Atualize novamente.")
        items.extend(response["items"])
        progress(f"Spotify · {before['name']}: {len(items)}/{total} itens recebidos.")
        link = response.get("next")
        if not link:
            break
        if link in visited or len(items) >= total:
            raise ValueError("Paginação inconsistente; atualização bloqueada.")
        visited.add(link)
        response = client.next(response)
        if not isinstance(response, dict) or not isinstance(response.get("items"), list):
            raise ValueError("Falha na paginação; nenhuma remoção será aplicada.")
    if len(items) != total:
        raise ValueError(f"Lista incompleta ({len(items)}/{total}); atualização bloqueada.")
    after = client.playlist(url)
    if not after or before.get("snapshot_id") != after.get("snapshot_id"):
        raise ValueError("A playlist mudou durante a consulta. Atualize novamente.")
    tracks, skipped = [], 0
    for item in items:
        raw = (item.get("track") or item.get("item")) if isinstance(item, dict) else None
        if not raw or raw.get("is_local") or raw.get("type") != "track" or not raw.get("id"):
            skipped += 1
            continue
        album = raw.get("album") or {}
        artists = [a["name"] for a in raw.get("artists", []) if a.get("name")]
        if not artists or not raw.get("name"):
            raise ValueError("Metadados de faixa incompletos; atualização bloqueada.")
        tracks.append(
            {
                "song_id": raw["id"],
                "url": "https://open.spotify.com/track/" + raw["id"],
                "name": raw["name"],
                "artist": artists[0],
                "artists": artists,
                "artist_details": [
                    {"name": a["name"], "id": a.get("id")} for a in raw.get("artists", []) if a.get("name")
                ],
                "artist_id": next((a.get("id") for a in raw.get("artists", []) if a.get("name")), None),
                "genres": raw.get("genres", []) + album.get("genres", []),
                "album_name": album.get("name", ""),
                "album_artist": artists[0],
                "album_id": album.get("id"),
                "duration": int(raw.get("duration_ms", 0) / 1000),
                "year": int((album.get("release_date") or "0000")[:4]),
                "date": album.get("release_date", ""),
                "track_number": raw.get("track_number", 1),
                "tracks_count": album.get("total_tracks", 1),
                "disc_number": raw.get("disc_number", 1),
                "disc_count": 1,
                "explicit": raw.get("explicit", False),
                "isrc": raw.get("external_ids", {}).get("isrc"),
                "publisher": "",
                "cover_url": (album.get("images") or [{}])[0].get("url"),
                "copyright_text": None,
            }
        )
    return {"name": before["name"], "tracks": tracks, "skipped": skipped, "total": total}


def worker(request: Path, result: Path):
    from .processes import background_subprocesses

    with background_subprocesses():
        _worker(request, result)


def _worker(request: Path, result: Path):
    from .paths import atomic_json

    def progress(message):
        # Structured stages only: no raw SDK output, URLs, cookies or credentials.
        with (request.parent / "progress.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"message": message}, ensure_ascii=False) + "\n")

    try:
        data = json.loads(request.read_text(encoding="utf-8"))
        payload, action = data["payload"], data["action"]
        if action == "diagnostics":
            import spotdl
            from spotdl.utils.deno import get_deno_path
            from spotdl.utils.ffmpeg import get_ffmpeg_path

            answer = {
                "spotdl": spotdl.__version__,
                "ffmpeg": str(get_ffmpeg_path() or "Não instalado"),
                "deno": str(get_deno_path() or "Não instalado"),
            }
        elif action == "setup":
            from spotdl.utils.deno import download_deno, get_deno_path
            from spotdl.utils.ffmpeg import download_ffmpeg, get_ffmpeg_path

            progress("Verificando / preparando FFmpeg…")
            ffmpeg = get_ffmpeg_path() or download_ffmpeg()
            progress("Verificando / preparando Deno…")
            deno = get_deno_path() or download_deno()
            answer = {"ffmpeg": str(ffmpeg), "deno": str(deno)}
        elif action == "playlist":
            from spotdl.utils.spotify import SpotifyClient

            official = bool(os.environ.get("SPOTIPY_CLIENT_ID") and os.environ.get("SPOTIPY_CLIENT_SECRET"))
            SpotifyClient.init(
                client_id=os.environ.get("SPOTIPY_CLIENT_ID", ""),
                client_secret=os.environ.get("SPOTIPY_CLIENT_SECRET", ""),
                use_official_api=official,
                no_cache=True,
            )
            progress("Conectando ao Spotify e lendo metadados da playlist…")
            answer = strict_playlist(SpotifyClient(), payload["url"], progress)
        elif action == "local":
            import shutil

            # Local audio needs only FFmpeg; avoid loading the remote SDK when
            # a system installation is already available.
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg:
                from spotdl.utils.ffmpeg import get_ffmpeg_path

                ffmpeg = get_ffmpeg_path()
            if not ffmpeg:
                raise ValueError("Prepare os componentes de download nas Configurações.")
            options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
            progress("FFmpeg · convertendo áudio local para MP3 192 kbps / 44,1 kHz / estéreo…")
            subprocess.run(
                [
                    str(ffmpeg),
                    "-y",
                    "-i",
                    payload["source"],
                    "-vn",
                    "-map_metadata",
                    "-1",
                    "-codec:a",
                    "libmp3lame",
                    "-b:a",
                    "192k",
                    "-ar",
                    "44100",
                    "-ac",
                    "2",
                    "-id3v2_version",
                    "3",
                    payload["output"],
                ],
                check=True,
                capture_output=True,
                timeout=240,
                **options,
            )
            answer = payload["output"]
        elif action in {"download", "candidates"}:
            from .downloads import DownloadEngine

            engine = DownloadEngine(request.parent, progress)
            try:
                if action == "candidates":
                    from .matching import MatchError

                    try:
                        answer = engine.matcher.candidates(payload["metadata"])
                    except MatchError:
                        if not engine.matcher.last_candidates:
                            raise
                        answer = engine.matcher.last_candidates
                else:
                    answer = engine.download(payload["metadata"], payload["output"])
            finally:
                engine.close()
        elif action == "session":
            from .downloads import session_worker

            answer = session_worker(request.parent, progress, payload)
        else:
            raise ValueError("Operação desconhecida.")
        atomic_json(result, {"result": answer})
    except Exception as exc:
        # Only return a bounded diagnostic. Do not persist provider output/cookies/tokens.
        from .telemetry import sanitize

        message = sanitize(str(exc))
        diagnostic = engine.diagnostic() if "engine" in locals() else {}
        atomic_json(result, {"error": f"{type(exc).__name__}: {message[:1800]}", "diagnostic": diagnostic})
