"""Build a self-contained Windows folder and portable ZIP, with dependency notices."""

import hashlib
import importlib.metadata
import shutil
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parents[1]


def main():
    PyInstaller.__main__.run(
        [
            str(ROOT / "launcher.py"),
            "--noconfirm",
            "--onedir",
            "--windowed",
            "--name",
            "spoTano",
            "--distpath",
            str(ROOT / "dist"),
            "--workpath",
            str(ROOT / "build"),
            "--paths",
            str(ROOT),
            "--recursive-copy-metadata",
            "spotdl",
            *[
                f"--collect-all={p}"
                for p in [
                    "spotdl",
                    "SpotipyFree",
                    "spotapi",
                    "curl_cffi",
                    "pykakasi",
                    "ytmusicapi",
                    "yt_dlp",
                    "yt_dlp_ejs",
                ]
            ],
        ]
    )
    target = ROOT / "dist" / "spoTano"
    for name in ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / name, target / name)
    shutil.copytree(ROOT / "docs", target / "docs", dirs_exist_ok=True)
    licenses = target / "licenses"
    licenses.mkdir(exist_ok=True)
    # Include installed distribution notices, including the Python/packager dependencies.
    inventory = []
    for dist in sorted(importlib.metadata.distributions(), key=lambda d: d.metadata["Name"].lower()):
        name = dist.metadata["Name"]
        inventory.append(f"{name}=={dist.version}")
        dest = licenses / name
        for file in dist.files or []:
            if any(token in str(file).lower() for token in ("license", "copying", "notice")):
                source = Path(dist.locate_file(file))
                if source.is_file():
                    dest.mkdir(exist_ok=True)
                    # Preserve structure to avoid overwriting different dependency notices.
                    relative = str(file).replace("../", "").replace("..\\", "")
                    output = dest / relative
                    output.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, output)
    (licenses / "versions.txt").write_text("\n".join(inventory), encoding="utf-8")
    archive = Path(
        shutil.make_archive(str(ROOT / "dist" / "spoTano-1.0.0-windows-x64"), "zip", ROOT / "dist", "spoTano")
    )
    with archive.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    (ROOT / "dist" / "SHA256SUMS.txt").write_text(f"{checksum}  {archive.name}\n", encoding="ascii")
    print(archive)


if __name__ == "__main__":
    main()
