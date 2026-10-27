"""A killable, bounded subprocess isolates upstream SDKs from UI and state."""

import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path


class Cancelled(Exception):
    pass


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
    def __init__(self, cancel=None):
        self.cancel = cancel or threading.Event()

    def call(self, action, payload=None, timeout=300):
        with tempfile.TemporaryDirectory(prefix="spotano-worker-") as temp:
            request, result = Path(temp) / "request.json", Path(temp) / "result.json"
            request.write_text(json.dumps({"action": action, "payload": payload or {}}), encoding="utf-8")
            command = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "spotano"]
            command += ["--worker", str(request), str(result)]
            kwargs = (
                {"creationflags": subprocess.CREATE_NO_WINDOW}
                if os.name == "nt"
                else {"start_new_session": True}
            )
            with (Path(temp) / "worker.log").open("w", encoding="utf-8") as log:
                process = subprocess.Popen(command, stdout=log, stderr=log, **kwargs)
                started = time.monotonic()
                try:
                    while process.poll() is None:
                        if self.cancel.wait(0.15):
                            raise Cancelled("Operação cancelada; arquivos anteriores preservados.")
                        if time.monotonic() - started > timeout:
                            raise TimeoutError(
                                "O provedor excedeu o tempo limite. Tente atualizar novamente."
                            )
                finally:
                    if process.poll() is None:
                        stop_tree(process)
            if not result.exists():
                raise RuntimeError("O mecanismo de download encerrou sem resposta. Verifique a instalação.")
            data = json.loads(result.read_text(encoding="utf-8"))
            if "error" in data:
                raise RuntimeError(data["error"])
            return data["result"]

    def playlist(self, url):
        return self.call("playlist", {"url": url})

    def download(self, metadata, output):
        return self.call("download", {"metadata": metadata, "output": str(output)}, timeout=480)

    def setup(self):
        return self.call("setup", timeout=600)


def strict_playlist(client, url):
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
    from .paths import atomic_json

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

            ffmpeg = get_ffmpeg_path() or download_ffmpeg()
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
            answer = strict_playlist(SpotifyClient(), payload["url"])
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
        elif action == "download":
            import asyncio

            from spotdl.download.downloader import Downloader
            from spotdl.types.song import Song
            from spotdl.utils.deno import get_deno_path
            from spotdl.utils.ffmpeg import get_ffmpeg_path
            from spotdl.utils.spotify import SpotifyClient

            ffmpeg = get_ffmpeg_path()
            if not ffmpeg:
                raise ValueError("Instale os componentes em Configurações → Preparar downloads.")
            deno = get_deno_path()
            if deno:
                os.environ["PATH"] = str(deno.parent) + os.pathsep + os.environ.get("PATH", "")
            SpotifyClient.init(client_id="", client_secret="", no_cache=True)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            settings = {
                "output": str(Path(payload["output"]).resolve().parent / "{title}.{output-ext}"),
                "format": "mp3",
                "bitrate": "192k",
                "ffmpeg": str(ffmpeg),
                "ffmpeg_args": "-ar 44100 -ac 2 -id3v2_version 3 -map_metadata -1",
                "threads": 1,
                "lyrics_providers": [],
                "audio_providers": ["youtube-music", "youtube"],
                "overwrite": "force",
                "simple_tui": True,
                "skip_album_art": True,
            }
            downloader = Downloader(settings=settings, loop=loop)
            song = Song.from_missing_data(**payload["metadata"])
            # spotDL 4.6.0 has no skip-all-tags setting. Tags are optional work
            # owned by Library, after download, in both local and remote flows.
            from spotdl.download import downloader as downloader_module

            original_embed = downloader_module.embed_metadata
            downloader_module.embed_metadata = lambda *args, **kwargs: None
            try:
                _, path = downloader.download_song(song)
            finally:
                downloader_module.embed_metadata = original_embed
            if path is None or not Path(path).is_file():
                raise ValueError("Áudio indisponível ou bloqueado pelo provedor. Tente novamente mais tarde.")
            target = Path(payload["output"]).resolve()
            actual = Path(path).resolve()
            if not actual.is_relative_to(target.parent):
                raise ValueError("O mecanismo retornou um arquivo fora da pasta temporária.")
            if actual != target:
                os.replace(actual, target)
            answer = str(target)
            loop.close()
        else:
            raise ValueError("Operação desconhecida.")
        atomic_json(result, {"result": answer})
    except Exception as exc:
        # Only return a bounded diagnostic. Do not persist provider output/cookies/tokens.
        import re

        message = re.sub(r"(?i)(token|secret|authorization|password)([=: ]+)\S+", r"\1\2[oculto]", str(exc))
        atomic_json(result, {"error": f"{type(exc).__name__}: {message[:700]}"})
