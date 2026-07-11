from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from blog_pipeline import pipeline, storage
from blog_pipeline.config import Settings

KST = timezone(timedelta(hours=9))


@pytest.fixture
def settings(tmp_path):
    db_path = str(tmp_path / "test.db")
    storage.init_db(db_path)
    return Settings(
        naver_client_id="cid",
        naver_client_secret="csecret",
        nvidia_api_key="nkey",
        nvidia_model="meta/llama-3.1-70b-instruct",
        github_token="gtoken",
        github_owner="ddastudio140",
        github_repo="blog-post",
        webhook_api_key="wkey",
        schedule_interval_minutes=60,
        db_path=db_path,
    )


SAMPLE_SOURCES = [
    {"title": "기사1", "body": "본문1", "image_url": "https://example.com/1.jpg", "link": "https://n.news.naver.com/1", "fetched_at": "2026-07-11T10:00:00+09:00"}
]

GENERATED_POST = {"title": "생성된 제목", "summary": "생성된 요약", "body_markdown": "## 본문"}

PUBLISH_RESULT = {"file_path": "posts/20260711/1000_천궁.md", "image_path": "posts/20260711/1000_천궁.jpg", "commit_sha": "sha123"}


def test_run_returns_no_keyword_status_when_no_candidate(settings):
    with patch("blog_pipeline.pipeline.keyword_source.select_keyword", return_value=None):
        result = pipeline.run(settings)

    assert result == {"status": "no_keyword", "keyword": None, "file_path": None}


def test_run_returns_no_sources_status_when_collection_empty(settings):
    with patch("blog_pipeline.pipeline.keyword_source.select_keyword", return_value="천궁"), \
         patch("blog_pipeline.pipeline.news_collector.collect", return_value=[]):
        result = pipeline.run(settings)

    assert result == {"status": "no_sources", "keyword": "천궁", "file_path": None}


def test_run_full_success_path_calls_all_steps_and_saves_post(settings):
    with patch("blog_pipeline.pipeline.keyword_source.select_keyword", return_value="천궁") as mock_select, \
         patch("blog_pipeline.pipeline.news_collector.collect", return_value=SAMPLE_SOURCES) as mock_collect, \
         patch("blog_pipeline.pipeline.post_writer.generate_post", return_value=GENERATED_POST) as mock_generate, \
         patch("blog_pipeline.pipeline.publisher.publish", return_value=PUBLISH_RESULT) as mock_publish:
        result = pipeline.run(settings, manual_keyword="천궁")

    mock_select.assert_called_once_with(settings.db_path, "천궁")
    mock_collect.assert_called_once_with("천궁", settings.naver_client_id, settings.naver_client_secret)
    mock_generate.assert_called_once()
    mock_publish.assert_called_once()

    assert result["status"] == "published"
    assert result["keyword"] == "천궁"
    assert result["file_path"] == "posts/20260711/1000_천궁.md"

    posts = storage.get_recent_posts(settings.db_path, limit=5)
    assert len(posts) == 1
    assert posts[0]["title"] == "생성된 제목"


def test_run_initializes_db_automatically_on_fresh_path(tmp_path):
    fresh_db_path = str(tmp_path / "fresh.db")  # init_db() 호출 안 함
    fresh_settings = Settings(
        naver_client_id="cid",
        naver_client_secret="csecret",
        nvidia_api_key="nkey",
        nvidia_model="meta/llama-3.1-70b-instruct",
        github_token="gtoken",
        github_owner="ddastudio140",
        github_repo="blog-post",
        webhook_api_key="wkey",
        schedule_interval_minutes=60,
        db_path=fresh_db_path,
    )

    with patch("blog_pipeline.pipeline.keyword_source.select_keyword", return_value="천궁"), \
         patch("blog_pipeline.pipeline.news_collector.collect", return_value=SAMPLE_SOURCES), \
         patch("blog_pipeline.pipeline.post_writer.generate_post", return_value=GENERATED_POST), \
         patch("blog_pipeline.pipeline.publisher.publish", return_value=PUBLISH_RESULT):
        result = pipeline.run(fresh_settings, manual_keyword="천궁")

    assert result["status"] == "published"
    posts = storage.get_recent_posts(fresh_db_path, limit=5)
    assert len(posts) == 1
