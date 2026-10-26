"""Hash-based export: only owned paths, previews, atomic verified copies."""

import json
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from .paths import atomic_copy, atomic_json, digest, inside


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
        tracks = self.store.tracks(active=True)
        if not tracks:
            raise ValueError("Não há faixas em playlists para exportar.")
        for track in tracks:
            self.library.check_cancel()
            if not self.library.available(track):
                raise ValueError("Há faixas ausentes ou alteradas. Atualize a biblioteca antes de exportar.")
            desired[track["path"]] = {
                "id": track["id"],
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
            atomic_copy(inside(self.library.music, relative), target, plan.desired[relative]["sha256"])
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
