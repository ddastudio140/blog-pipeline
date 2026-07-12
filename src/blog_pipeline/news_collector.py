from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

KST = timezone(timedelta(hours=9))
logger = logging.getLogger("blog_pipeline.news_collector")
SEARCH_URL = "https://openapi.naver.com/v1/search/news.json"
ALLOWED_DOMAINS = (
    "https://n.news.naver.com",
    "https://m.sports.naver.com",
    "https://m.entertain.naver.com",
)
MAX_ARTICLES = 5

_SELECTORS = {
    "https://n.news.naver.com": {
        "body": ("#dic_area", "text"),
        "title": ("#title_area", "text"),
        "image": ('meta[property="og:image"]', "content"),
    },
    "https://m.sports.naver.com": {
        "body": ("._article_content", "text"),
        "title": ("h2", "text"),
        "image": ('meta[property="og:image"]', "content"),
    },
    "https://m.entertain.naver.com": {
        "body": ("div._article_content", "text"),
        "title": ('meta[property="og:title"]', "content"),
        "image": ("div._article_content img", "src"),
    },
}


def _search_news(keyword: str, client_id: str, client_secret: str) -> list[dict]:
    response = requests.get(
        SEARCH_URL,
        params={"query": keyword, "display": 30},
        headers={
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json().get("items", [])


def _filter_and_limit(items: list[dict]) -> list[dict]:
    filtered = [item for item in items if item.get("link", "").startswith(ALLOWED_DOMAINS)]
    return filtered[:MAX_ARTICLES]


def _selectors_for(url: str) -> dict | None:
    for domain, selectors in _SELECTORS.items():
        if url.startswith(domain):
            return selectors
    return None


def _extract(soup: BeautifulSoup, selector: str, attr: str) -> str | None:
    element = soup.select_one(selector)
    if element is None:
        return None
    if attr == "text":
        return element.get_text(strip=True)
    return element.get(attr)


def _parse_article(url: str) -> dict | None:
    selectors = _selectors_for(url)
    if selectors is None:
        return None
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except Exception:
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    title_selector, title_attr = selectors["title"]
    body_selector, body_attr = selectors["body"]
    image_selector, image_attr = selectors["image"]

    title = _extract(soup, title_selector, title_attr)
    body = _extract(soup, body_selector, body_attr)
    image_url = _extract(soup, image_selector, image_attr)

    if title is None or body is None:
        return None

    return {"title": title, "body": body, "image_url": image_url}


def collect(keyword: str, naver_client_id: str, naver_client_secret: str) -> list[dict]:
    items = _search_news(keyword, naver_client_id, naver_client_secret)
    logger.info("네이버 뉴스 검색 결과: %d건 (keyword=%s)", len(items), keyword)

    candidates = _filter_and_limit(items)
    logger.info(
        "허용 도메인 필터링 후 %d건 선택됨 (최대 %d건, keyword=%s)", len(candidates), MAX_ARTICLES, keyword
    )

    results = []
    fetched_at = datetime.now(KST).isoformat()
    total = len(candidates)
    for idx, item in enumerate(candidates, start=1):
        parsed = _parse_article(item["link"])
        if parsed is None:
            logger.info(
                "[%d/%d] 기사 본문 파싱 실패, 건너뜀 (keyword=%s): %s", idx, total, keyword, item["link"]
            )
            continue
        logger.info(
            "[%d/%d] 기사 본문 파싱 성공 (keyword=%s): %s", idx, total, keyword, item["link"]
        )
        results.append(
            {
                "title": parsed["title"],
                "body": parsed["body"],
                "image_url": parsed["image_url"],
                "link": item["link"],
                "fetched_at": fetched_at,
            }
        )

    logger.info("최종 수집된 기사: %d건 (keyword=%s)", len(results), keyword)
    return results
