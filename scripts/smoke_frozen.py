"""Exercise the actual frozen worker without relying on a Python installation in it."""

import json
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

from mutagen.mp3 import MP3


def main():
    exe = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="spotano-frozen-smoke-") as directory:
        root = Path(directory)

        def call(action, payload):
            request, response = root / "request.json", root / "response.json"
            response.unlink(missing_ok=True)
            request.write_text(json.dumps({"action": action, "payload": payload}), encoding="utf-8")
            subprocess.run([str(exe), "--worker", str(request), str(response)], check=True, timeout=180)
            data = json.loads(response.read_text(encoding="utf-8"))
            if "error" in data:
                raise RuntimeError(data["error"])
            return data["result"]

        diagnostics = call("diagnostics", {})
        assert diagnostics["spotdl"] == "4.6.0", diagnostics
        source = root / "source.wav"
        with wave.open(str(source), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(22050)
            audio.writeframes(b"\x00\x00" * 22050)
        original, result = root / "original.mp3", root / "result.mp3"
        subprocess.run(
            [shutil.which("ffmpeg"), "-y", "-i", str(source), str(original)],
            check=True,
            capture_output=True,
            timeout=30,
        )
        call(
            "local",
            {
                "source": str(original),
                "output": str(result),
                "metadata": {"name": "Generated test", "artist": "spoTano"},
            },
        )
        events = [
            json.loads(line)["message"]
            for line in (root / "progress.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert any("convertendo áudio local" in event for event in events), events
        info = MP3(result).info
        assert info.sample_rate == 44100 and info.channels == 2 and info.length > 0
        print("Frozen worker OK: SDK imports, FFmpeg, real MP3 transcoding and progress events.")


if __name__ == "__main__":
    main()
