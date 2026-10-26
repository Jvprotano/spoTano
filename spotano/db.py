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
CREATE TABLE IF NOT EXISTS genre_cache(
 artist TEXT PRIMARY KEY, genres TEXT NOT NULL, fetched_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS history(
 id INTEGER PRIMARY KEY, time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 action TEXT NOT NULL, detail TEXT NOT NULL);
"""


class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "library.sqlite3"
        with self.connect() as db:
            db.executescript(SCHEMA)
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("INSERT OR IGNORE INTO settings VALUES('revision', '0')")
            db.execute("INSERT OR IGNORE INTO settings VALUES('by_genre', 'true')")
            db.execute("INSERT OR IGNORE INTO settings VALUES('musicbrainz', 'true')")

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

    def remove_playlist(self, playlist_id):
        with self.connect() as db:
            db.execute("DELETE FROM playlists WHERE id=?", (playlist_id,))
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
