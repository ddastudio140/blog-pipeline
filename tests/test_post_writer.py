from unittest.mock import Mock, patch

import pytest

from blog_pipeline import post_writer, storage


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    storage.init_db(path)
    return path


SAMPLE_SOURCES = [
    {"title": "기사1", "body": "본문1", "image_url": None, "link": "https://n.news.naver.com/1", "fetched_at": "2026-07-11T10:00:00+09:00"}
]

RAW_RESPONSE = """TITLE: 천궁 미사일 체계 총정리
SUMMARY: 천궁 미사일 체계의 특징과 최근 동향을 정리했습니다.
---
## 개요
천궁은...
"""


def test_build_prompt_includes_keyword_and_sources_and_references(db_path):
    storage.save_post(
        db_path, keyword="이전키워드", title="이전 글 제목", summary="이전 글 요약",
        file_path="p.md", image_path=None, commit_sha=None,
        published_at="2026-07-10T10:00:00+09:00",
    )
    reference_posts = storage.get_recent_posts(db_path, limit=5)

    prompt = post_writer._build_prompt(SAMPLE_SOURCES, "천궁", reference_posts)

    assert "천궁" in prompt
    assert "기사1" in prompt
    assert "이전 글 제목" in prompt


def test_parse_response_extracts_title_summary_body():
    result = post_writer._parse_response(RAW_RESPONSE)

    assert result["title"] == "천궁 미사일 체계 총정리"
    assert result["summary"] == "천궁 미사일 체계의 특징과 최근 동향을 정리했습니다."
    assert "## 개요" in result["body_markdown"]


def test_call_nvidia_api_returns_content_on_success():
    mock_response = Mock()
    mock_response.choices = [Mock(message=Mock(content=RAW_RESPONSE))]

    with patch("blog_pipeline.post_writer.OpenAI") as mock_openai_cls:
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create.return_value = mock_response

        result = post_writer._call_nvidia_api("프롬프트", api_key="key", model="meta/llama-3.1-70b-instruct")

    assert result == RAW_RESPONSE


def test_call_nvidia_api_retries_once_then_raises():
    with patch("blog_pipeline.post_writer.OpenAI") as mock_openai_cls:
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create.side_effect = Exception("api error")

        with pytest.raises(Exception, match="api error"):
            post_writer._call_nvidia_api("프롬프트", api_key="key", model="meta/llama-3.1-70b-instruct")

    assert mock_client.chat.completions.create.call_count == 2


def test_generate_post_returns_parsed_result(db_path):
    with patch("blog_pipeline.post_writer._call_nvidia_api", return_value=RAW_RESPONSE):
        result = post_writer.generate_post(
            SAMPLE_SOURCES, "천궁", db_path, api_key="key", model="meta/llama-3.1-70b-instruct"
        )

    assert result["title"] == "천궁 미사일 체계 총정리"
    assert result["summary"] == "천궁 미사일 체계의 특징과 최근 동향을 정리했습니다."
    assert "## 개요" in result["body_markdown"]
