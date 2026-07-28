"""
SQLite cache for OASYS Version Diff — persists the fetched version list and the
per-version tickets "back to the tool folder" (backend/data/version_diff.db).

Two tables:
  versions(key PK, label, jira_version_id, order_index, released, release_date,
           url, oasys_label, fetched_at)
  tickets (version_key, ticket_key, summary, status, issuetype, category, url,
           priority, fetched_at, PRIMARY KEY(version_key, ticket_key))

``key`` is the stable identifier we use everywhere else (the Jira version name,
e.g. "Core-6.20.7"). Everything is upserted; a refresh replaces rows for the
affected keys. Thread-safe via a module lock (uvicorn is async but our handlers
call these synchronously).
"""
from __future__ import annotations

import sqlite3
import time
from threading import Lock
from typing import Any, Optional

import config

_lock = Lock()
_conn: Optional[sqlite3.Connection] = None


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(config.DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _init(_conn)
    return _conn


def _init(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS versions (
            key             TEXT PRIMARY KEY,
            label           TEXT,
            oasys_label     TEXT,
            jira_version_id TEXT,
            order_index     INTEGER,
            released        INTEGER,
            release_date    TEXT,
            url             TEXT,
            fetched_at      REAL
        );
        CREATE TABLE IF NOT EXISTS tickets (
            version_key TEXT,
            ticket_key  TEXT,
            summary     TEXT,
            status      TEXT,
            issuetype   TEXT,
            category    TEXT,
            priority    TEXT,
            url         TEXT,
            fetched_at  REAL,
            PRIMARY KEY (version_key, ticket_key)
        );
        """
    )
    conn.commit()


# --------------------------------------------------------------------------- #
# Versions
# --------------------------------------------------------------------------- #
def save_versions(versions: list[dict]) -> None:
    """Replace the whole version list (it defines the ordered dropdown)."""
    now = time.time()
    with _lock:
        conn = _connect()
        conn.execute("DELETE FROM versions")
        conn.executemany(
            """INSERT INTO versions
               (key, label, oasys_label, jira_version_id, order_index,
                released, release_date, url, fetched_at)
               VALUES (:key, :label, :oasys_label, :jira_version_id, :order_index,
                       :released, :release_date, :url, :fetched_at)""",
            [{
                "key": v["key"],
                "label": v.get("label"),
                "oasys_label": v.get("oasys_label"),
                "jira_version_id": v.get("jira_version_id"),
                "order_index": v.get("order_index", i),
                "released": 1 if v.get("released") else 0,
                "release_date": v.get("release_date"),
                "url": v.get("url"),
                "fetched_at": now,
            } for i, v in enumerate(versions)],
        )
        conn.commit()


def get_versions() -> list[dict]:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT * FROM versions ORDER BY order_index ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def versions_age() -> Optional[float]:
    """Seconds since the version list was last saved, or None if empty."""
    with _lock:
        conn = _connect()
        row = conn.execute("SELECT MAX(fetched_at) AS t FROM versions").fetchone()
    if not row or row["t"] is None:
        return None
    return time.time() - row["t"]


# --------------------------------------------------------------------------- #
# Tickets
# --------------------------------------------------------------------------- #
def save_tickets(version_key: str, tickets: list[dict]) -> None:
    now = time.time()
    with _lock:
        conn = _connect()
        conn.execute("DELETE FROM tickets WHERE version_key = ?", (version_key,))
        conn.executemany(
            """INSERT OR REPLACE INTO tickets
               (version_key, ticket_key, summary, status, issuetype, category,
                priority, url, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(
                version_key, t["key"], t.get("summary"), t.get("status"),
                t.get("issuetype"), t.get("category"), t.get("priority"),
                t.get("url"), now,
            ) for t in tickets],
        )
        conn.commit()


def get_tickets(version_key: str) -> list[dict]:
    with _lock:
        conn = _connect()
        # Alias ticket_key -> key so a cache-hit ticket has the SAME shape as a
        # fresh one from jira.issues_for_version (which uses "key"). Otherwise
        # downstream `t["key"]` KeyErrors and the frontend renders blank keys.
        rows = conn.execute(
            "SELECT ticket_key AS key, summary, status, issuetype, category, priority, url "
            "FROM tickets WHERE version_key = ? ORDER BY category, ticket_key",
            (version_key,),
        ).fetchall()
    return [dict(r) for r in rows]


def tickets_age(version_key: str) -> Optional[float]:
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT MAX(fetched_at) AS t FROM tickets WHERE version_key = ?",
            (version_key,),
        ).fetchone()
    if not row or row["t"] is None:
        return None
    return time.time() - row["t"]
