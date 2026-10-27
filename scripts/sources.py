"""Collect matching PyPI source distributions and original source for binary release."""

import concurrent.futures
import hashlib
import importlib.metadata
import json
import subprocess
import tomllib
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def download(dist):
    name, version = dist.metadata["Name"], dist.version
    if name.lower() == "spotano":
        return None
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    with urllib.request.urlopen(url, timeout=60) as response:
        metadata = json.load(response)
    source = next((f for f in metadata["urls"] if f["packagetype"] == "sdist"), None)
    if source is None:
        raise RuntimeError(f"No source distribution for {name}=={version}; review before shipping.")
    dest = ROOT / "artifacts" / "third-party-source" / source["filename"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists() or hashlib.sha256(dest.read_bytes()).hexdigest() != source["digests"]["sha256"]:
        with urllib.request.urlopen(source["url"], timeout=120) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != source["digests"]["sha256"]:
            raise RuntimeError(f"Source checksum mismatch: {name}")
        dest.write_bytes(data)
    return dest


def main():
    dists = list(importlib.metadata.distributions())
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        sources = [p for p in pool.map(download, dists) if p]
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    archive = ROOT / "dist" / f"spoTano-{version}-source.zip"
    archive.parent.mkdir(exist_ok=True)
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for relative in tracked:
            if relative:
                output.write(ROOT / relative, "spoTano/" + relative)
        for source in sources:
            output.write(source, "spoTano/third-party-source/" + source.name)
    checksums = ROOT / "dist" / "SHA256SUMS.txt"
    with checksums.open("a", encoding="ascii") as stream:
        stream.write(hashlib.sha256(archive.read_bytes()).hexdigest() + "  " + archive.name + "\n")
    print(f"{archive}: {len(sources)} dependency sources")


if __name__ == "__main__":
    main()
