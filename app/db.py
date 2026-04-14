from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE IF NOT EXISTS magnets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    magnet_uri TEXT NOT NULL,
                    magnet_hash TEXT,
                    source TEXT NOT NULL DEFAULT 'manual',
                    status TEXT NOT NULL DEFAULT 'pending',
                    remote_id INTEGER,
                    remote_status TEXT,
                    remote_status_code INTEGER,
                    filename TEXT,
                    size INTEGER,
                    last_error TEXT,
                    review_needed INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_magnets_hash ON magnets(magnet_hash) WHERE magnet_hash IS NOT NULL;
                CREATE TABLE IF NOT EXISTS magnet_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    magnet_id INTEGER NOT NULL REFERENCES magnets(id) ON DELETE CASCADE,
                    remote_file_id TEXT NOT NULL,
                    remote_path TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    size INTEGER NOT NULL DEFAULT 0,
                    selected INTEGER NOT NULL DEFAULT 1,
                    direct_link TEXT,
                    direct_link_status TEXT NOT NULL DEFAULT 'unknown',
                    direct_link_checked_at TEXT,
                    media_type TEXT,
                    title TEXT,
                    year INTEGER,
                    season INTEGER,
                    episode INTEGER,
                    confidence REAL NOT NULL DEFAULT 0,
                    review_needed INTEGER NOT NULL DEFAULT 0,
                    strm_path TEXT,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_magnet_files_unique ON magnet_files(magnet_id, remote_file_id);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    magnet_id INTEGER,
                    level TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload_json TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )

    def fetch_all(self, query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute(query, params).fetchall())

    def fetch_one(self, query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(query, params).fetchone()

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> int:
        with self.connect() as conn:
            cursor = conn.execute(query, params)
            return int(cursor.lastrowid)

    def log_event(self, level: str, event_type: str, message: str, magnet_id: int | None = None, payload: dict[str, Any] | None = None) -> None:
        self.execute(
            """
            INSERT INTO events (magnet_id, level, event_type, message, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (magnet_id, level, event_type, message, json.dumps(payload or {}, ensure_ascii=True), utc_now()),
        )
