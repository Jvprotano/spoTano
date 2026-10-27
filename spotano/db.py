"""SQLite is the source of truth; a connection belongs to one operation/thread."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS playlists(
 id INTEGER PRIMARY KEY, url TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
 synced_at TEXT, warning TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS tracks(
 id TEXT PRIMARY KEY, metadata TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'Outros',
 override TEXT, path TEXT, sha256 TEXT, status TEXT NOT NULL DEFAULT 'pending',
 error TEXT NOT NULL DEFAULT '', updated_at TEXT);
CREATE TABLE IF NOT EXISTS membership(
 playlist_id INTEGER REFERENCES playlists(id) ON DELETE CASCADE,
 track_id TEXT REFERENCES tracks(id), position INTEGER NOT NULL,
 PRIMARY KEY(playlist_id, track_id));
CREATE TABLE IF NOT EXISTS download_membership(
 playlist_id INTEGER REFERENCES playlists(id) ON DELETE CASCADE,
 track_id TEXT NOT NULL, metadata TEXT NOT NULL,
 PRIMARY KEY(playlist_id, track_id));
CREATE TABLE IF NOT EXISTS genre_cache(
 artist TEXT PRIMARY KEY, genres TEXT NOT NULL, fetched_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS audio_matches(
 track_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, evidence TEXT NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS audio_sources(track_id TEXT PRIMARY KEY, url TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS artist_categories(artist TEXT PRIMARY KEY, category TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS genre_evidence(track_id TEXT PRIMARY KEY, evidence TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS genre_queries(key TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS file_transitions(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS history(
 id INTEGER PRIMARY KEY, time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 action TEXT NOT NULL, detail TEXT NOT NULL);
"""


class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "library.sqlite3"
        new_catalog = not self.path.exists()
        with self.connect() as db:
            db.executescript(SCHEMA)
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("BEGIN IMMEDIATE")
            columns = {row["name"] for row in db.execute("PRAGMA table_info(playlists)")}
            for name, definition in {
                "total": "INTEGER",
                "downloaded_at": "TEXT",
                "output_group": "TEXT NOT NULL DEFAULT ''",
            }.items():
                if name not in columns:
                    db.execute(f"ALTER TABLE playlists ADD COLUMN {name} {definition}")
            if "downloaded_at" not in columns:
                # Preserve the last known playlist comparison for older catalogs.
                db.execute("""INSERT OR IGNORE INTO download_membership
                    SELECT m.playlist_id,m.track_id,t.metadata FROM membership m
                    JOIN tracks t ON t.id=m.track_id""")
            columns = {row[1] for row in db.execute("PRAGMA table_info(tracks)")}
            if "tagged" not in columns:
                db.execute("ALTER TABLE tracks ADD COLUMN tagged INTEGER NOT NULL DEFAULT 1")
            if "classified" not in columns:
                db.execute("ALTER TABLE tracks ADD COLUMN classified INTEGER NOT NULL DEFAULT 0")
                db.execute("UPDATE tracks SET classified=1 WHERE path IS NOT NULL")
            db.execute("INSERT OR IGNORE INTO settings VALUES('revision', '0')")
            db.execute(
                "INSERT OR IGNORE INTO settings VALUES('download_options', ?)",
                (json.dumps({"categories": False, "artists": False, "metadata": False}),),
            )
            db.execute("INSERT OR IGNORE INTO settings VALUES('musicbrainz', 'true')")
            db.execute(
                "INSERT OR IGNORE INTO settings VALUES('output_layout', ?)",
                (json.dumps("playlists" if new_catalog else "unified"),),
            )
            db.execute("INSERT OR IGNORE INTO settings VALUES('download_workers', '2')")
            db.execute("INSERT OR IGNORE INTO settings VALUES('conversion_workers', '2')")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def rows(self, sql, args=()):
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, args)]

    def setting(self, key, default=None):
        rows = self.rows("SELECT value FROM settings WHERE key=?", (key,))
        return json.loads(rows[0]["value"]) if rows else default

    @staticmethod
    def bump(db):
        db.execute("UPDATE settings SET value=CAST(value AS INTEGER)+1 WHERE key='revision'")

    def set_setting(self, key, value):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, json.dumps(value)))
            self.bump(db)

    def add_playlist(self, url, name="Nova playlist"):
        from .paths import playlist_url

        with self.connect() as db:
            db.execute(
                "INSERT INTO playlists(url,name) VALUES(?,?)", (playlist_url(url), name.strip() or "Playlist")
            )
            self.bump(db)
            return db.execute("SELECT id FROM playlists WHERE url=?", (playlist_url(url),)).fetchone()[0]

    def remove_playlist(self, playlist_id):
        with self.connect() as db:
            db.execute("DELETE FROM playlists WHERE id=?", (playlist_id,))
            self.bump(db)

    def set_output_group(self, playlist_ids, name):
        # Preserve user labels; filesystem normalization/disambiguation happens at export.
        name = name.strip()[:120]
        with self.connect() as db:
            db.executemany(
                "UPDATE playlists SET output_group=? WHERE id=?", [(name, i) for i in playlist_ids]
            )
            self.bump(db)

    def playlists(self):
        return self.rows("""SELECT p.*, COUNT(m.track_id) count FROM playlists p
            LEFT JOIN membership m ON m.playlist_id=p.id GROUP BY p.id ORDER BY p.id""")

    def tracks(self, active=False):
        return self.rows(
            """SELECT t.*, COUNT(m.playlist_id) references_count FROM tracks t
            LEFT JOIN membership m ON m.track_id=t.id GROUP BY t.id """
            + (" HAVING COUNT(m.playlist_id)>0 " if active else " ")
            + "ORDER BY t.id"
        )

    def log(self, action, detail):
        with self.connect() as db:
            db.execute("INSERT INTO history(action,detail) VALUES(?,?)", (action, str(detail)))

    def backup(self, target: Path):
        with self.connect() as db, sqlite3.connect(target) as dest:
            db.backup(dest)

    def audio_match(self, metadata):
        from .matching import MATCH_VERSION, canonical_youtube, fingerprint

        rows = self.rows("SELECT * FROM audio_matches WHERE track_id=?", (metadata["song_id"],))
        if not rows or rows[0]["fingerprint"] != fingerprint(metadata):
            return None
        value = json.loads(rows[0]["evidence"])
        try:
            value["url"] = canonical_youtube(value["url"])
        except (ValueError, KeyError, TypeError):
            return None
        return value if value.get("version") == MATCH_VERSION else None

    def save_audio_match(self, metadata, evidence):
        import time

        from .matching import fingerprint

        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO audio_matches VALUES(?,?,?,?)",
                (metadata["song_id"], fingerprint(metadata), json.dumps(evidence), time.time()),
            )

    def set_audio_source(self, track_id, url):
        from .matching import canonical_youtube

        url = canonical_youtube(url) if url.strip() else ""
        with self.connect() as db:
            if url:
                db.execute("INSERT OR REPLACE INTO audio_sources VALUES(?,?)", (track_id, url))
            else:
                db.execute("DELETE FROM audio_sources WHERE track_id=?", (track_id,))
            db.execute("DELETE FROM audio_matches WHERE track_id=?", (track_id,))
            self.bump(db)

    def clear_audio_matches(self):
        with self.connect() as db:
            db.execute("DELETE FROM audio_matches")
            self.bump(db)
