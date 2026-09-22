"""cao_memory — SQLite FTS5 Episodic Memory Layer.

Provides fast full-text indexed storage and recall of past sessions, architectural
decisions, bug fixes, and user preferences into wcao/memory.sqlite.
"""
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def get_default_db_path() -> Path:
    from run.cao_auto import find_repo_root
    root = find_repo_root(Path.cwd())
    wcao = root / "wcao"
    wcao.mkdir(parents=True, exist_ok=True)
    return wcao / "memory.sqlite"


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or get_default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS session_memory USING fts5(
                session_id,
                category,
                summary,
                details,
                file_paths,
                created_at
            )
        """)


def store_memory(
    category: str,
    summary: str,
    details: str = "",
    file_paths: str = "",
    session_id: str = "default",
    db_path: Optional[Path] = None,
) -> int:
    """Store an episodic memory entry into the FTS5 database."""
    conn = get_connection(db_path)
    now_iso = datetime.now(timezone.utc).isoformat()
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO session_memory(session_id, category, summary, details, file_paths, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, category, summary, details, file_paths, now_iso),
        )
        return cursor.lastrowid


STOPWORDS = {"the", "for", "to", "in", "and", "a", "an", "is", "of", "on", "with", "this", "that", "it"}


def _sanitize_fts_query(query: str) -> str:
    # Remove characters that can break SQLite FTS syntax
    cleaned = re.sub(r'[^\w\s]', ' ', query)
    tokens = [t.strip().lower() for t in cleaned.split() if t.strip().lower() not in STOPWORDS and len(t.strip()) > 1]
    if not tokens:
        tokens = [t.strip().lower() for t in cleaned.split() if t.strip()]
    if not tokens:
        return ""
    # Use OR disjunction so relevant keyword matches are ranked by BM25
    return " OR ".join(f'"{t}"*' for t in tokens[:10])


def query_memory(
    query_text: str,
    category: Optional[str] = None,
    limit: int = 10,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Query memories using FTS5 match."""
    conn = get_connection(db_path)
    fts_query = _sanitize_fts_query(query_text)
    if not fts_query:
        return []

    try:
        if category:
            cursor = conn.execute(
                """
                SELECT rowid, session_id, category, summary, details, file_paths, created_at, rank
                FROM session_memory
                WHERE session_memory MATCH ? AND category = ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, category, limit),
            )
        else:
            cursor = conn.execute(
                """
                SELECT rowid, session_id, category, summary, details, file_paths, created_at, rank
                FROM session_memory
                WHERE session_memory MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, limit),
            )
        return [dict(r) for r in cursor.fetchall()]
    except sqlite3.OperationalError:
        # Fallback to simple LIKE if FTS expression encounters an error
        like_term = f"%{query_text}%"
        if category:
            cursor = conn.execute(
                """
                SELECT rowid, session_id, category, summary, details, file_paths, created_at, 0 as rank
                FROM session_memory
                WHERE (summary LIKE ? OR details LIKE ?) AND category = ?
                ORDER BY rowid DESC
                LIMIT ?
                """,
                (like_term, like_term, category, limit),
            )
        else:
            cursor = conn.execute(
                """
                SELECT rowid, session_id, category, summary, details, file_paths, created_at, 0 as rank
                FROM session_memory
                WHERE summary LIKE ? OR details LIKE ?
                ORDER BY rowid DESC
                LIMIT ?
                """,
                (like_term, like_term, limit),
            )
        return [dict(r) for r in cursor.fetchall()]


def list_memories(limit: int = 20, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """List recent memories."""
    conn = get_connection(db_path)
    cursor = conn.execute(
        """
        SELECT rowid, session_id, category, summary, details, file_paths, created_at, 0 as rank
        FROM session_memory
        ORDER BY rowid DESC
        LIMIT ?
        """,
        (limit,),
    )
    return [dict(r) for r in cursor.fetchall()]
