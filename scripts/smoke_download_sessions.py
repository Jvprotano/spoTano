"""Exercise a warm worker with two own WAV samples served only on loopback."""

import functools
import http.server
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path
from unittest.mock import patch

from mutagen.mp3 import MP3

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spotano.downloads import WarmDownload


def main():
    exe = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
    launches, events = [], []
    original = subprocess.Popen

    def launch(command, **kwargs):
        if "--worker" in command:
            if exe:
                command = [str(exe), *command[-3:]]
            process = original(command, **kwargs)
            launches.append(process)
            return process
        return original(command, **kwargs)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *_):
            pass

    with tempfile.TemporaryDirectory(prefix="spotano-warm-smoke-") as directory:
        root = Path(directory)
        source = root / "own-generated.wav"
        with wave.open(str(source), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(22050)
            audio.writeframes(b"\x00\x00" * 22050)
        server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(Handler, directory=directory)
        )
        serving = threading.Thread(target=server.serve_forever, daemon=True)
        serving.start()
        session = WarmDownload(threading.Event(), events.append)
        started = time.monotonic()
        try:
            with patch("spotano.downloads.subprocess.Popen", launch):
                for letter in "AB":
                    target = root / f"{letter}.mp3"
                    session.download(
                        {
                            "name": "Own generated sample " + letter,
                            "artist": "spoTano tests",
                            "song_id": letter * 22,
                            "album_id": None,
                            "genres": [],
                            "duration": 1,
                            "download_url": f"http://127.0.0.1:{server.server_port}/own-generated.wav",
                        },
                        target,
                        timeout=120,
                    )
                    audio = MP3(target).info
                    assert audio.sample_rate == 44100 and audio.channels == 2 and audio.length > 0
                    assert not MP3(target).tags or not MP3(target).tags.getall("APIC")
                assert len(launches) == 1, "Each song must reuse the same process"
                assert sum("Mecanismo pronto em" in message for message in events) == 1
                assert any("Reutilizando" in message for message in events)
                assert any("Recebendo áudio do provedor ·" in message for message in events), events
                assert sum("Convertendo com FFmpeg para MP3 · 100%" in message for message in events) >= 2
                session.close()
            assert launches[0].poll() is not None
            print(
                f"Warm {'frozen' if exe else 'source'} worker OK: two own samples, one process/initialization, "
                f"MP3, transfer/conversion progress, loopback only, {time.monotonic() - started:.2f}s."
            )
        except BaseException:
            print("\n".join(events[-20:]))
            raise
        finally:
            session.close()
            server.shutdown()
            server.server_close()
            serving.join(5)


if __name__ == "__main__":
    main()
