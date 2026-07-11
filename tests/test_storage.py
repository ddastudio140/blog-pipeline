import sqlite3

import pytest

from blog_pipeline import storage


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    storage.init_db(path)
    return path


def test_init_db_creates_tables(db_path):
    conn = sqlite3.connect(db_path)
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    conn.close()
    assert {"keyword_history", "sources", "posts"} <= tables


def test_record_and_get_recent_keywords(db_path):
    storage.record_keyword_selection(db_path, "천궁", "2026-07-11T10:00:00+09:00")
    storage.record_keyword_selection(db_path, "오래된키워드", "2026-07-01T10:00:00+09:00")

    recent = storage.get_recent_keywords(db_path, since_date="2026-07-10")

    assert recent == ["천궁"]


def test_save_sources_persists_rows(db_path):
    sources = [
        {
            "title": "제목1",
            "body": "본문1",
            "image_url": "https://example.com/1.jpg",
            "link": "https://n.news.naver.com/1",
            "fetched_at": "2026-07-11T10:00:00+09:00",
        }
    ]

    storage.save_sources(db_path, run_id="run-1", keyword="천궁", sources=sources)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM sources WHERE run_id = 'run-1'").fetchall()
    conn.close()

    assert len(rows) == 1
    assert rows[0]["title"] == "제목1"
    assert rows[0]["keyword"] == "천궁"


def test_save_post_and_get_recent_posts(db_path):
    storage.save_post(
        db_path,
        keyword="천궁",
        title="천궁 관련 블로그 글",
        summary="요약입니다",
        file_path="posts/20260711/1000_천궁.md",
        image_path="posts/20260711/1000_천궁.jpg",
        commit_sha="abc123",
        published_at="2026-07-11T10:00:00+09:00",
    )

    posts = storage.get_recent_posts(db_path, limit=5)

    assert len(posts) == 1
    assert posts[0]["title"] == "천궁 관련 블로그 글"
    assert posts[0]["summary"] == "요약입니다"


def test_get_recent_posts_orders_by_published_at_desc(db_path):
    storage.save_post(
        db_path, keyword="a", title="old", summary="s1",
        file_path="p1.md", image_path=None, commit_sha=None,
        published_at="2026-07-10T10:00:00+09:00",
    )
    storage.save_post(
        db_path, keyword="b", title="new", summary="s2",
        file_path="p2.md", image_path=None, commit_sha=None,
        published_at="2026-07-11T10:00:00+09:00",
    )

    posts = storage.get_recent_posts(db_path, limit=5)

    assert [p["title"] for p in posts] == ["new", "old"]
