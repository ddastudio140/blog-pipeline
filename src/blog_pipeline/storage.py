from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS keyword_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    selected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    keyword TEXT NOT NULL,
    title TEXT,
    body TEXT,
    image_url TEXT,
    link TEXT,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    file_path TEXT NOT NULL,
    image_path TEXT,
    commit_sha TEXT,
    published_at TEXT NOT NULL
);
"""


def _connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


def init_db(db_path: str) -> None:
    conn = _connect(db_path)
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def record_keyword_selection(db_path: str, keyword: str, selected_at: str) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO keyword_history (keyword, selected_at) VALUES (?, ?)",
            (keyword, selected_at),
        )
        conn.commit()
    finally:
        conn.close()


def get_recent_keywords(db_path: str, since_date: str) -> list[str]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT keyword FROM keyword_history WHERE selected_at >= ? ORDER BY selected_at",
            (since_date,),
        ).fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()


def save_sources(db_path: str, run_id: str, keyword: str, sources: list[dict]) -> None:
    conn = _connect(db_path)
    try:
        conn.executemany(
            """
            INSERT INTO sources (run_id, keyword, title, body, image_url, link, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    run_id,
                    keyword,
                    source.get("title"),
                    source.get("body"),
                    source.get("image_url"),
                    source.get("link"),
                    source["fetched_at"],
                )
                for source in sources
            ],
        )
        conn.commit()
    finally:
        conn.close()


def get_recent_posts(db_path: str, limit: int) -> list[dict]:
    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM posts ORDER BY published_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def save_post(
    db_path: str,
    keyword: str,
    title: str,
    summary: str,
    file_path: str,
    image_path: str | None,
    commit_sha: str | None,
    published_at: str,
) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO posts (keyword, title, summary, file_path, image_path, commit_sha, published_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (keyword, title, summary, file_path, image_path, commit_sha, published_at),
        )
        conn.commit()
    finally:
        conn.close()
