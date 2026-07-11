from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

from blog_pipeline import storage

KST = timezone(timedelta(hours=9))
ZUM_TREND_URL = "https://zum.com/"


def _fetch_trend_keywords() -> list[str]:
    response = requests.get(ZUM_TREND_URL, timeout=10)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    elements = soup.select(".issue-word-list__keyword")
    return [el.get_text(strip=True) for el in elements if el.get_text(strip=True)]


def select_keyword(db_path: str, manual_keyword: str | None = None) -> str | None:
    if manual_keyword:
        return manual_keyword

    candidates = _fetch_trend_keywords()

    now = datetime.now(KST)
    yesterday = now - timedelta(days=1)
    since_date = yesterday.strftime("%Y-%m-%d")
    used = set(storage.get_recent_keywords(db_path, since_date=since_date))

    for candidate in candidates:
        if candidate not in used:
            storage.record_keyword_selection(db_path, candidate, now.isoformat())
            return candidate

    return None
