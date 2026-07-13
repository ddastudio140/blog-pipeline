from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from blog_pipeline import news_collector

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 7, 12, 23, 0, 0, tzinfo=KST)


def test_filter_and_limit_keeps_only_allowed_domains_and_top_5():
    items = [
        {"link": "https://n.news.naver.com/1"},
        {"link": "https://m.sports.naver.com/2"},
        {"link": "https://m.entertain.naver.com/3"},
        {"link": "https://blog.naver.com/not-allowed"},
        {"link": "https://n.news.naver.com/4"},
        {"link": "https://n.news.naver.com/5"},
        {"link": "https://n.news.naver.com/6"},
    ]

    result = news_collector._filter_and_limit(items)

    assert len(result) == 5
    assert all(
        item["link"].startswith(
            ("https://n.news.naver.com", "https://m.sports.naver.com", "https://m.entertain.naver.com")
        )
        for item in result
    )


def test_parse_article_general_domain():
    html = """
    <html><body>
      <div id="title_area">일반 뉴스 제목</div>
      <div id="dic_area">일반 뉴스 본문</div>
      <meta property="og:image" content="https://img.example.com/general.jpg">
    </body></html>
    """
    with patch("blog_pipeline.news_collector.requests.get") as mock_get:
        mock_get.return_value.text = html
        mock_get.return_value.raise_for_status = lambda: None

        result = news_collector._parse_article("https://n.news.naver.com/article/1")

    assert result["title"] == "일반 뉴스 제목"
    assert result["body"] == "일반 뉴스 본문"
    assert result["image_url"] == "https://img.example.com/general.jpg"


def test_parse_article_sports_domain():
    html = """
    <html><body>
      <h2>스포츠 뉴스 제목</h2>
      <div class="_article_content">스포츠 뉴스 본문</div>
      <meta property="og:image" content="https://img.example.com/sports.jpg">
    </body></html>
    """
    with patch("blog_pipeline.news_collector.requests.get") as mock_get:
        mock_get.return_value.text = html
        mock_get.return_value.raise_for_status = lambda: None

        result = news_collector._parse_article("https://m.sports.naver.com/article/1")

    assert result["title"] == "스포츠 뉴스 제목"
    assert result["body"] == "스포츠 뉴스 본문"


def test_parse_article_returns_none_on_request_failure():
    with patch("blog_pipeline.news_collector.requests.get", side_effect=Exception("network error")):
        result = news_collector._parse_article("https://n.news.naver.com/article/broken")

    assert result is None


def test_collect_combines_search_and_parse(monkeypatch):
    search_items = [
        {"link": "https://n.news.naver.com/1"},
        {"link": "https://blog.naver.com/skip-me"},
    ]
    parsed_article = {
        "title": "제목",
        "body": "본문",
        "image_url": "https://img.example.com/1.jpg",
    }

    with patch("blog_pipeline.news_collector._search_news", return_value=search_items), \
         patch("blog_pipeline.news_collector._parse_article", return_value=parsed_article):
        result = news_collector.collect("천궁", "client-id", "client-secret")

    assert len(result) == 1
    assert result[0]["title"] == "제목"
    assert result[0]["link"] == "https://n.news.naver.com/1"
    assert "fetched_at" in result[0]


def test_filter_and_limit_excludes_articles_older_than_max_age():
    items = [
        {"link": "https://n.news.naver.com/1", "pubDate": "Sun, 12 Jul 2026 20:00:00 +0900"},  # 3시간 전, 허용
        {"link": "https://n.news.naver.com/2", "pubDate": "Wed, 08 Jul 2026 20:00:00 +0900"},  # 4일 전, 제외
    ]

    result = news_collector._filter_and_limit(items, now=NOW)

    assert [item["link"] for item in result] == ["https://n.news.naver.com/1"]


def test_filter_and_limit_keeps_article_without_pub_date():
    items = [{"link": "https://n.news.naver.com/1"}]

    result = news_collector._filter_and_limit(items, now=NOW)

    assert len(result) == 1


def test_is_recent_boundary_within_max_age_days():
    just_inside = {"pubDate": "Thu, 09 Jul 2026 23:01:00 +0900"}  # 정확히 3일 이내
    just_outside = {"pubDate": "Thu, 09 Jul 2026 22:59:00 +0900"}  # 3일 초과

    assert news_collector._is_recent(just_inside, NOW) is True
    assert news_collector._is_recent(just_outside, NOW) is False


def test_search_news_requests_date_sorted_results():
    with patch("blog_pipeline.news_collector.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"items": []}
        mock_get.return_value.raise_for_status = lambda: None

        news_collector._search_news("천궁", "client-id", "client-secret")

    _, kwargs = mock_get.call_args
    assert kwargs["params"]["sort"] == "date"


def test_collect_skips_articles_that_fail_to_parse():
    search_items = [
        {"link": "https://n.news.naver.com/1"},
        {"link": "https://n.news.naver.com/2"},
    ]

    with patch("blog_pipeline.news_collector._search_news", return_value=search_items), \
         patch("blog_pipeline.news_collector._parse_article", side_effect=[None, {"title": "t", "body": "b", "image_url": None}]):
        result = news_collector.collect("천궁", "client-id", "client-secret")

    assert len(result) == 1
