from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

from blog_pipeline import storage

KST = timezone(timedelta(hours=9))
ZUM_TREND_URL = "https://zum.com/"
logger = logging.getLogger("blog_pipeline.keyword_source")


def _fetch_trend_keywords() -> list[str]:
    response = requests.get(ZUM_TREND_URL, timeout=10)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    elements = soup.select(".issue-word-list__keyword")
    return [el.get_text(strip=True) for el in elements if el.get_text(strip=True)]


def select_keyword(db_path: str, manual_keyword: str | None = None) -> str | None:
    if manual_keyword:
        logger.info("수동 지정 키워드 사용: %s", manual_keyword)
        return manual_keyword

    candidates = _fetch_trend_keywords()
    logger.info("실시간 트렌드 키워드 후보 %d개 조회됨", len(candidates))

    now = datetime.now(KST)
    yesterday = now - timedelta(days=1)
    since_date = yesterday.strftime("%Y-%m-%d")
    used = set(storage.get_recent_keywords(db_path, since_date=since_date))
    logger.info("최근 사용된 키워드 %d개 (제외 대상)", len(used))

    for candidate in candidates:
        if candidate not in used:
            storage.record_keyword_selection(db_path, candidate, now.isoformat())
            logger.info("트렌드 키워드 선정: %s", candidate)
            return candidate

    logger.warning("모든 트렌드 후보가 이미 사용되어 선정 가능한 키워드가 없음")
    return None
