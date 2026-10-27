"""Journaled audio installation and explicit review of unreferenced physical copies."""

import json
import os
import re
import uuid

from .paths import atomic_copy, digest, inside


class AudioFiles:
    def __init__(self, store, progress=lambda message: None):
        self.store, self.progress = store, progress
        self.music = store.root / "Music"

    def install(self, staged, current, relative, category, match=None, fingerprint=None):
        new_hash = digest(staged)
        target = inside(self.music, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        old_path, old_hash = current.get("path"), current.get("sha256")
        if target.exists() and (old_path != relative or digest(target) != old_hash):
            raise ValueError("Arquivo local alterado ou desconhecido; preservado para revisão.")
        if old_path and old_path != relative:
            old = inside(self.music, old_path)
            if old.exists() and digest(old) != old_hash:
                raise ValueError("Arquivo anterior modificado; substituição bloqueada para revisão.")
        transition_id = uuid.uuid4().hex
        payload = {"track_id": current["id"], "old_path": old_path, "old_hash": old_hash,
                   "path": relative, "sha256": new_hash, "category": category,
                   "trash": "trash/" + transition_id + "/"}
        if match and fingerprint:
            payload["match"], payload["fingerprint"] = match, fingerprint
        # Preserve the original before touching the target; the journal survives a process crash.
        if old_path and old_hash:
            old = inside(self.music, old_path)
            if old.is_file() and digest(old) == old_hash:
                atomic_copy(old, inside(self.store.root, payload["trash"] + old_path), old_hash)
        with self.store.connect() as db:
            db.execute("INSERT INTO file_transitions VALUES(?,?)", (transition_id, json.dumps(payload)))
        os.replace(staged, target)
        self.finish(transition_id, payload)
        return new_hash

    def finish(self, transition_id, payload):
        target = inside(self.music, payload["path"])
        if not target.is_file() or digest(target) != payload["sha256"]:
            # Installation did not finish. Preserve all bytes for inspection; never register partial output.
            with self.store.connect() as db:
                db.execute("DELETE FROM file_transitions WHERE id=?", (transition_id,))
            self.progress("Recuperação: instalação incompleta preservada; download poderá ser repetido.")
            return
        rows = self.store.rows("SELECT path,sha256 FROM tracks WHERE id=?", (payload["track_id"],))
        if not rows:
            return
        current = rows[0]
        if (current["path"], current["sha256"]) not in {
            (payload["old_path"], payload["old_hash"]), (payload["path"], payload["sha256"])
        }:
            self.progress("Recuperação: catálogo mudou; transição preservada para revisão.")
            return
        cleanup_old = bool(payload["old_path"] and payload["old_path"] != payload["path"])
        with self.store.connect() as db:
            db.execute("UPDATE tracks SET path=?,sha256=?,category=?,status='ready',error='',"
                       "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                       (payload["path"], payload["sha256"], payload["category"], payload["track_id"]))
            self.store.bump(db)
            if payload.get("match"):
                import time

                db.execute("INSERT OR REPLACE INTO audio_matches VALUES(?,?,?,?)",
                           (payload["track_id"], payload["fingerprint"],
                            json.dumps(payload["match"]), time.time()))
            if not cleanup_old:
                db.execute("DELETE FROM file_transitions WHERE id=?", (transition_id,))
        if cleanup_old:
            old = inside(self.music, payload["old_path"])
            if old.exists():
                if digest(old) != payload["old_hash"]:
                    self.progress("Recuperação: cópia anterior alterada foi preservada para revisão.")
                    return
                backup = inside(self.store.root, payload["trash"] + payload["old_path"])
                if not backup.exists():
                    atomic_copy(old, backup, payload["old_hash"])
                old.unlink()
            with self.store.connect() as db:
                db.execute("DELETE FROM file_transitions WHERE id=?", (transition_id,))

    def recover(self):
        for row in self.store.rows("SELECT * FROM file_transitions"):
            self.finish(row["id"], json.loads(row["payload"]))

    def review(self):
        known = {row["path"] for row in self.store.tracks() if row["path"]}
        tracks = {row["id"] for row in self.store.tracks()}
        result = []
        for path in self.music.rglob("*.mp3"):
            relative = path.relative_to(self.music).as_posix()
            if relative in known:
                continue
            match = re.search(r"\[([A-Za-z0-9]{22})\]\.mp3$", path.name)
            result.append({"path": relative, "sha256": digest(inside(self.music, relative)),
                           "reason": "Cópia sem vínculo de faixa cadastrada" if match and match[1] in tracks
                           else "Arquivo físico sem vínculo no catálogo"})
        return result

    def quarantine(self, rows, revision):
        if revision != self.store.setting("revision"):
            raise ValueError("A biblioteca mudou. Gere outra revisão.")
        batch = "trash/review-" + uuid.uuid4().hex + "/"
        known = {row["path"] for row in self.store.tracks() if row["path"]}
        for row in rows:
            if row["path"] in known:
                raise ValueError("Arquivo voltou a ser usado; limpeza interrompida.")
            source = inside(self.music, row["path"])
            if not source.is_file() or digest(source) != row["sha256"]:
                raise ValueError("Arquivo mudou desde a revisão; preservado.")
            atomic_copy(source, inside(self.store.root, batch + row["path"]), row["sha256"])
            if digest(source) != row["sha256"]:
                raise ValueError("Arquivo alterado durante a revisão; preservado.")
            source.unlink()
        self.store.log("physical_cleanup", f"{len(rows)} arquivos para {batch}")
        return str(self.store.root / batch)
