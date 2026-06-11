"""
db.py — SQLite connection management and schema.

Functions:
- get_connection()        -> sqlite3.Connection (with row factory set)
- init_db()                -> creates tables + indexes if not present
- get_or_create_monitor()  -> ensures a monitor row exists for a config entry, returns its id
- get_all_monitors()       -> list of all monitor rows
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "monitor.db"


def get_connection() -> sqlite3.Connection:
    """
    Open a connection to the SQLite database.
    row_factory = sqlite3.Row lets us access columns by name (row["status_code"])
    instead of by index (row[2]) — much more readable.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Enforce foreign key constraints (off by default in SQLite)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """
    Create tables and indexes if they don't already exist.
    Safe to call every time the app starts.
    """
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS monitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            interval_sec INTEGER DEFAULT 60,
            timeout_sec INTEGER DEFAULT 5,
            fail_threshold INTEGER DEFAULT 3
        );

        CREATE TABLE IF NOT EXISTS checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            monitor_id INTEGER NOT NULL REFERENCES monitors(id),
            status_code INTEGER,
            response_ms INTEGER,
            success INTEGER NOT NULL,   -- 0 or 1 (SQLite has no native bool)
            error TEXT,                 -- exception message if request failed entirely
            checked_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            monitor_id INTEGER NOT NULL REFERENCES monitors(id),
            started_at TEXT NOT NULL DEFAULT (datetime('now')),
            resolved_at TEXT,
            cause TEXT
        );

        -- Speeds up "give me last 24h of checks for monitor X" queries
        CREATE INDEX IF NOT EXISTS idx_checks_monitor_time
            ON checks (monitor_id, checked_at DESC);

        -- Speeds up "is there an open incident for monitor X" queries
        CREATE INDEX IF NOT EXISTS idx_incidents_monitor_open
            ON incidents (monitor_id, resolved_at);
    """)
    conn.commit()
    conn.close()


def get_or_create_monitor(conn: sqlite3.Connection, name: str, url: str,
                           interval_sec: int, timeout_sec: int, fail_threshold: int) -> int:
    """
    Idempotent insert: if a monitor with this URL already exists, return its id.
    Otherwise insert it and return the new id.

    This lets us re-run the app with the same monitors.json without creating
    duplicate monitor rows every restart.
    """
    row = conn.execute("SELECT id FROM monitors WHERE url = ?", (url,)).fetchone()
    if row:
        return row["id"]

    cursor = conn.execute(
        """INSERT INTO monitors (name, url, interval_sec, timeout_sec, fail_threshold)
           VALUES (?, ?, ?, ?, ?)""",
        (name, url, interval_sec, timeout_sec, fail_threshold),
    )
    conn.commit()
    return cursor.lastrowid


def get_all_monitors(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return all monitor rows."""
    return conn.execute("SELECT * FROM monitors").fetchall()
