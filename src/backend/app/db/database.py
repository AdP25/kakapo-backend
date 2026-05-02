from __future__ import annotations

import sqlite3
from typing import Optional

from app.core.config import DB_PATH

_db_conn: Optional[sqlite3.Connection] = None


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS exact_cache (
            key TEXT PRIMARY KEY,
            response_json TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS semantic_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_text TEXT NOT NULL,
            query_hash TEXT NOT NULL UNIQUE,
            response_json TEXT NOT NULL,
            created_at REAL NOT NULL,
            last_used_at REAL NOT NULL,
            hit_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts DATETIME DEFAULT CURRENT_TIMESTAMP,
            model TEXT,
            prompt_hash TEXT,
            prompt_preview TEXT,
            tokens_in INTEGER,
            tokens_out INTEGER,
            tokens_saved INTEGER DEFAULT 0,
            cost_usd REAL,
            counterfactual_usd REAL,
            saved_usd REAL,
            cache_status TEXT,
            latency_ms INTEGER
        );
        """
    )

    cols = {row[1] for row in conn.execute("PRAGMA table_info(requests)").fetchall()}
    if "tokens_saved" not in cols:
        conn.execute("ALTER TABLE requests ADD COLUMN tokens_saved INTEGER DEFAULT 0")
    conn.commit()


def get_db() -> sqlite3.Connection:
    global _db_conn
    if _db_conn is None:
        _db_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _db_conn.row_factory = sqlite3.Row
        init_db(_db_conn)
    return _db_conn


def close_db() -> None:
    global _db_conn
    if _db_conn:
        _db_conn.close()
        _db_conn = None
