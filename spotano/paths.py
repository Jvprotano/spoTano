"""Safe names, bounded paths and atomic file operations."""

import hashlib
import json
import os
import re
import shutil
import unicodedata
import uuid
from pathlib import Path


def safe_name(value: str, limit: int = 65) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Za-z0-9 _().-]", "_", text).strip(" .")[:limit].rstrip(" .")
    if not text:
        text = "Sem nome"
    if text.split(".")[0].upper() in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(10)),
        *(f"LPT{i}" for i in range(10)),
    }:
        text = "_" + text
    return text


def inside(root: Path, relative: str) -> Path:
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Caminho fora da pasta gerenciada.")
    root = root.resolve()
    candidate = (root / relative).resolve()
    if candidate == root or not candidate.is_relative_to(root):
        raise ValueError("Caminho fora da pasta gerenciada.")
    # resolve() also prevents junction/symlink escapes.
    return candidate


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".part")
    try:
        with temp.open("w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def atomic_copy(source: Path, target: Path, expected_hash: str):
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + "." + uuid.uuid4().hex + ".part")
    try:
        shutil.copyfile(source, temp)
        if digest(temp) != expected_hash:
            raise OSError("A cópia não passou na verificação SHA-256.")
        with temp.open("r+b") as stream:
            os.fsync(stream.fileno())
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)


def playlist_url(value: str) -> str:
    match = re.fullmatch(
        r"https://open\.spotify\.com/(?:intl-[\w-]+/)?playlist/([A-Za-z0-9]{22})(?:\?[^\s]*)?/?",
        value.strip(),
    )
    if not match:
        raise ValueError("Use uma URL https://open.spotify.com/playlist/… válida.")
    return "https://open.spotify.com/playlist/" + match[1]
