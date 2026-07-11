from unittest.mock import patch

import pytest

from blog_pipeline import keyword_source, storage


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    storage.init_db(path)
    return path


def test_select_keyword_returns_manual_keyword_without_crawling(db_path):
    with patch("blog_pipeline.keyword_source._fetch_trend_keywords") as mock_fetch:
        result = keyword_source.select_keyword(db_path, manual_keyword="천궁")

    assert result == "천궁"
    mock_fetch.assert_not_called()


def test_select_keyword_picks_first_unused_candidate(db_path):
    with patch(
        "blog_pipeline.keyword_source._fetch_trend_keywords",
        return_value=["이미사용됨", "새키워드"],
    ):
        storage.record_keyword_selection(db_path, "이미사용됨", "2026-07-11T09:00:00+09:00")

        result = keyword_source.select_keyword(db_path)

    assert result == "새키워드"


def test_select_keyword_returns_none_when_all_candidates_used(db_path):
    with patch(
        "blog_pipeline.keyword_source._fetch_trend_keywords",
        return_value=["이미사용됨"],
    ):
        storage.record_keyword_selection(db_path, "이미사용됨", "2026-07-11T09:00:00+09:00")

        result = keyword_source.select_keyword(db_path)

    assert result is None


def test_select_keyword_records_selection(db_path):
    with patch(
        "blog_pipeline.keyword_source._fetch_trend_keywords",
        return_value=["새키워드"],
    ):
        keyword_source.select_keyword(db_path)

    recent = storage.get_recent_keywords(db_path, since_date="2026-07-01")
    assert "새키워드" in recent


def test_fetch_trend_keywords_parses_zum_html():
    html = """
    <html><body>
      <span class="issue-word-list__keyword">키워드1</span>
      <span class="issue-word-list__keyword">키워드2</span>
    </body></html>
    """
    with patch("blog_pipeline.keyword_source.requests.get") as mock_get:
        mock_get.return_value.text = html
        mock_get.return_value.raise_for_status = lambda: None

        result = keyword_source._fetch_trend_keywords()

    assert result == ["키워드1", "키워드2"]
