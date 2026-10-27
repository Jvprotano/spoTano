"""Hash-based export: only owned paths, previews, atomic verified copies."""

import hashlib
import json
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from .paths import atomic_copy, atomic_json, digest, inside, safe_name

LAYOUTS = {
    "unified": "Coleção unificada",
    "playlists": "Uma pasta por playlist",
    "groups": "Pastas por grupo",
}


def output_folders(playlists, layout):
    """Stable disambiguation also handles names that collide after ASCII conversion."""
    if layout not in LAYOUTS:
        raise ValueError("Organização de saída inválida.")
    if layout == "unified":
        return {p["id"]: "" for p in playlists}
    keys = {
        p["id"]: (p["output_group"] or "Sem grupo")
        if layout == "groups"
        else (p["output_group"] or p["name"])
        for p in playlists
    }
    folders = {}
    # Different playlists always get different folders; exact group names intentionally merge.
    used = {}
    assigned = {}
    for p in playlists:
        key = keys[p["id"]]
        identity = key if layout == "groups" else p["id"]
        if identity in assigned:
            folders[p["id"]] = assigned[identity]
            continue
        folder = safe_name(key, 48)
        while folder.casefold() in used and used[folder.casefold()] != identity:
            folder = f"{folder}_{p['id']}"
        used[folder.casefold()] = identity
        assigned[identity] = folder
        folders[p["id"]] = folder
    return folders


@dataclass
class ExportPlan:
    revision: int
    root: Path
    manifest: dict
    desired: dict
    copy: list
    remove: list
    reused: int
    bytes_required: int


def read_manifest(root):
    path = inside(root, ".spotano-manifest.json")
    if not path.exists():
        return {"version": 1, "files": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1 or not isinstance(data.get("files"), dict):
        raise ValueError("Manifesto de exportação inválido; destino preservado.")
    for relative, entry in data["files"].items():
        if not isinstance(relative, str) or not relative.lower().endswith(".mp3"):
            raise ValueError("Manifesto contém um caminho que não é de áudio MP3.")
        inside(root, relative)
        if not isinstance(entry, dict) or not isinstance(entry.get("sha256"), str):
            raise ValueError("Manifesto de exportação inválido.")
    return data


def export_paths(tracks):
    """Human-readable names; stable, case-insensitive disambiguation across all layouts."""
    bases = {}
    for track in tracks:
        metadata = json.loads(track["metadata"])
        folder = str(Path(track["path"]).parent).replace("\\", "/")
        name = safe_name(metadata["artist"] + " - " + metadata["name"], 90)
        relative = (folder + "/" if folder != "." else "") + name
        bases.setdefault(relative.casefold(), []).append((track["id"], relative))
    assigned, used = {}, set()
    # Reserve every natural name before adding suffixes, including names ending in (2).
    reserved = {key + ".mp3" for key in bases}
    for key, group in sorted(bases.items()):
        for index, (identity, base) in enumerate(sorted(group), 1):
            name = base + ".mp3" if len(group) == 1 else f"{base} ({index}).mp3"
            if name.casefold() in used or (len(group) > 1 and name.casefold() in reserved):
                # Only a real collision needs a short suffix. The full ID stays in the manifest.
                suffix = hashlib.sha256(identity.encode()).hexdigest()
                for size in range(6, 65):
                    name = f"{base} ({suffix[:size]}).mp3"
                    if name.casefold() not in used | reserved:
                        break
            assigned[identity] = name
            used.add(name.casefold())
    return assigned


class Exporter:
    def __init__(self, library):
        self.library, self.store = library, library.store

    def preview(self, destination):
        destination = Path(destination).resolve()
        if not destination.is_dir():
            raise ValueError("Selecione uma pasta ou pendrive conectado.")
        root = (destination / "spoTano").resolve()
        if (
            root.is_relative_to(self.store.root)
            or self.store.root.is_relative_to(root)
            or root == destination
            or root != destination / "spoTano"
        ):
            raise ValueError("O destino deve ficar fora da biblioteca e não pode ser um link.")
        revision = self.store.setting("revision")
        manifest, desired = read_manifest(root), {}
        layout = self.store.setting("output_layout", "unified")
        playlists = self.store.playlists()
        folders = output_folders(playlists, layout)
        memberships = {}
        for row in self.store.rows("SELECT playlist_id,track_id FROM membership"):
            memberships.setdefault(row["track_id"], []).append(row["playlist_id"])
        tracks = self.store.tracks(active=True)
        if not tracks:
            raise ValueError("Não há faixas em playlists para exportar.")
        names = export_paths([track for track in tracks if track["path"]])
        for track in tracks:
            self.library.check_cancel()
            self.library.progress(
                "Conferindo áudio para exportação: " + track["path"]
                if track["path"]
                else "Conferindo faixa pendente…"
            )
            if not self.library.available(track):
                raise ValueError("Há faixas ausentes ou alteradas. Use Baixar novas ou Baixar tudo antes de exportar.")
            for playlist_id in memberships[track["id"]]:
                prefix = folders[playlist_id]
                relative = f"{prefix}/{names[track['id']]}" if prefix else names[track["id"]]
                desired[relative] = {
                    "id": track["id"],
                    "source": track["path"],
                    "sha256": track["sha256"],
                    "size": inside(self.library.music, track["path"]).stat().st_size,
                }
        copies, removals, reused, required = [], [], 0, 0
        for relative, entry in desired.items():
            target = inside(root, relative)
            if target.exists():
                current_hash = digest(target)
                if current_hash == entry["sha256"]:
                    reused += 1
                    continue
                if current_hash != manifest["files"].get(relative, {}).get("sha256"):
                    raise ValueError("Arquivo desconhecido ou modificado no destino: " + relative)
            copies.append(relative)
            required += entry["size"]
            if target.exists():
                required += target.stat().st_size
        for relative, entry in manifest["files"].items():
            if relative not in desired:
                target = inside(root, relative)
                if target.exists():
                    if digest(target) != entry["sha256"]:
                        raise ValueError("Arquivo antigo modificado no destino; preservado: " + relative)
                    removals.append(relative)
        if shutil.disk_usage(destination).free < required + 1024 * 1024:
            raise ValueError("Espaço insuficiente no destino para uma cópia segura.")
        if revision != self.store.setting("revision"):
            raise ValueError("A biblioteca mudou. Gere outra prévia.")
        return ExportPlan(revision, root, manifest, desired, copies, removals, reused, required)

    def apply(self, plan):
        if plan.revision != self.store.setting("revision") or read_manifest(plan.root) != plan.manifest:
            raise ValueError("Prévia desatualizada. Gere outra prévia de exportação.")
        # Recheck source and destination contents after the human review.
        fresh = self.preview(plan.root.parent)
        if fresh.desired != plan.desired or fresh.copy != plan.copy or fresh.remove != plan.remove:
            raise ValueError("Arquivos mudaram desde a prévia. Gere outra prévia.")
        plan.root.mkdir(parents=True, exist_ok=True)
        batch = uuid.uuid4().hex
        for index, relative in enumerate(plan.copy, 1):
            self.library.check_cancel()
            self.library.progress(f"Exportando {index}/{len(plan.copy)} · {relative}")
            target = inside(plan.root, relative)
            if target.exists():
                old_hash = digest(target)
                if old_hash != plan.manifest["files"].get(relative, {}).get("sha256"):
                    raise ValueError("Arquivo alterado após a prévia; destino preservado: " + relative)
                backup = inside(plan.root, ".spotano-trash/" + batch + "/" + relative)
                atomic_copy(target, backup, old_hash)
            atomic_copy(
                inside(self.library.music, plan.desired[relative]["source"]),
                target,
                plan.desired[relative]["sha256"],
            )
        self.library.check_cancel()
        # New manifest keeps pending obsolete entries until each quarantine succeeds.
        entries = dict(plan.desired)
        entries.update({r: plan.manifest["files"][r] for r in plan.remove})
        atomic_json(inside(plan.root, ".spotano-manifest.json"), {"version": 1, "files": entries})
        for relative in plan.remove:
            self.library.check_cancel()
            target = inside(plan.root, relative)
            if target.exists():
                if digest(target) != plan.manifest["files"][relative]["sha256"]:
                    raise ValueError("Arquivo alterado durante a exportação; preservado.")
                trash = inside(plan.root, ".spotano-trash/" + batch + "/" + relative)
                trash.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target, trash)
            entries.pop(relative)
            atomic_json(inside(plan.root, ".spotano-manifest.json"), {"version": 1, "files": entries})
        self.store.log("export", f"{len(plan.copy)} copiadas; {plan.reused} reutilizadas; {plan.root}")
        return str(plan.root)


def usb_drives():
    """CIM identifies USB disks even when Windows reports them as fixed volumes."""
    if os.name != "nt":
        return []
    script = """
    $items = @();
    Get-CimInstance Win32_LogicalDisk | Where-Object DriveType -eq 2 | ForEach-Object {
      $items += [pscustomobject]@{path=($_.DeviceID+'\\');label=$_.VolumeName;filesystem=$_.FileSystem}
    }
    Get-CimInstance Win32_DiskDrive | Where-Object InterfaceType -eq 'USB' | ForEach-Object {
      Get-CimAssociatedInstance -InputObject $_ -Association Win32_DiskDriveToDiskPartition | ForEach-Object {
        Get-CimAssociatedInstance -InputObject $_ -Association Win32_LogicalDiskToPartition | ForEach-Object {
          $items += [pscustomobject]@{path=($_.DeviceID+'\\');label=$_.VolumeName;filesystem=$_.FileSystem}
        }
      }
    }
    ConvertTo-Json -InputObject @($items | Sort-Object path -Unique) -Compress
    """
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=25,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode:
        raise RuntimeError("Não foi possível detectar USB. Selecione a pasta do pendrive manualmente.")
    return json.loads(result.stdout or "[]")
