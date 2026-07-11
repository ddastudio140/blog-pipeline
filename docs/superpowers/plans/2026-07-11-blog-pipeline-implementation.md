# 블로그 자동화 파이프라인 (n8n → Python) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** n8n 워크플로우(`n8n/auto-blog.json`)를 대체하는 Python 기반 블로그 자동화 파이프라인 구축 — 키워드 선정 → 네이버 뉴스 수집 → NVIDIA build API로 블로그 글 생성 → GitHub 게시, 스케줄러/webhook/CLI 3가지 트리거 지원.

**Architecture:** FastAPI 상시 서비스(APScheduler 내장) + 5개 독립 모듈(keyword_source, news_collector, storage, post_writer, publisher)을 공용 오케스트레이터(pipeline.py)가 순서대로 호출. CLI와 webhook, 스케줄러 모두 동일한 `pipeline.run()` 진입점을 공유. SQLite로 상태(키워드 이력, 수집 소스, 발행 이력) 영속화.

**Tech Stack:** Python 3.12, uv(패키지 관리), FastAPI, APScheduler, requests, BeautifulSoup4, PyGithub, openai SDK(NVIDIA build API 호출용), sqlite3(표준 라이브러리), pytest, Docker/docker-compose

## Global Constraints

- 참조 스펙: `docs/superpowers/specs/2026-07-11-blog-pipeline-design.md`
- SQLite DB 경로: `data/blog_pipeline.db` (볼륨 마운트 대상)
- 모든 시각은 KST(Asia/Seoul) 기준으로 저장/비교
- 네이버 뉴스 도메인 필터: `https://n.news.naver.com`, `https://m.sports.naver.com`, `https://m.entertain.naver.com` (이 3개만 허용, 상위 5건)
- GitHub 대상 저장소 기본값: `GITHUB_OWNER=ddastudio140`, `GITHUB_REPO=blog-post` (`.env`로 오버라이드 가능)
- 게시 경로: `posts/{yyyyMMdd}/{HHmm}_{keyword}.md` (이미지는 동일 디렉토리, 동일 파일명 + 원본 확장자)
- NVIDIA build API는 OpenAI 호환 엔드포인트(`https://integrate.api.nvidia.com/v1`)를 openai SDK로 호출, 기본 모델 `meta/llama-3.1-70b-instruct`(`.env`의 `NVIDIA_MODEL`로 오버라이드 가능)
- 패키지 관리는 uv (`pyproject.toml` + `uv.lock`), 테스트는 pytest
- 비밀값은 `.env`(gitignore 대상)로 관리, `.env.example`을 커밋해 필요한 키를 문서화
- 외부 API 호출(zum.com, 네이버, NVIDIA, GitHub)이 있는 모든 모듈의 unit test는 `unittest.mock` 또는 `pytest-mock`으로 외부 호출을 mock 처리 — 실제 네트워크 호출 금지

---

## File Structure

```
blog-pipeline/
├── pyproject.toml
├── uv.lock
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── data/                          # SQLite DB 볼륨 (gitignore)
├── prompts/
│   └── generate-post-prompt.md
├── src/
│   └── blog_pipeline/
│       ├── __init__.py
│       ├── config.py               # .env 로드 + 설정 dataclass
│       ├── storage.py               # SQLite 스키마 + CRUD 함수
│       ├── keyword_source.py        # zum.com 크롤링 + 중복 회피 선택
│       ├── news_collector.py        # 네이버 뉴스 검색 + 본문 크롤링
│       ├── post_writer.py           # NVIDIA API로 글 생성
│       ├── publisher.py             # 이미지 다운로드 + GitHub 커밋
│       ├── pipeline.py              # 오케스트레이터 (run 함수)
│       ├── app.py                   # FastAPI app + APScheduler 등록 + webhook
│       └── cli.py                   # CLI 진입점
└── tests/
    ├── conftest.py
    ├── test_storage.py
    ├── test_keyword_source.py
    ├── test_news_collector.py
    ├── test_post_writer.py
    ├── test_publisher.py
    ├── test_pipeline.py
    └── test_app.py
```

---

## Task 1: 프로젝트 스캐폴딩 + 설정 로딩

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `src/blog_pipeline/__init__.py`
- Create: `src/blog_pipeline/config.py`
- Test: `tests/test_config.py`
- Test: `tests/conftest.py`

**Interfaces:**
- Produces: `blog_pipeline.config.Settings` dataclass with fields: `naver_client_id: str`, `naver_client_secret: str`, `nvidia_api_key: str`, `nvidia_model: str`, `github_token: str`, `github_owner: str`, `github_repo: str`, `webhook_api_key: str`, `schedule_interval_minutes: int`, `db_path: str`
- Produces: `blog_pipeline.config.load_settings() -> Settings` (환경변수에서 로드, `.env` 파일을 `python-dotenv`로 먼저 로드)

- [ ] **Step 1: uv 프로젝트 초기화**

```bash
cd /Users/hongwon/devspace/projects/release/blog-pipeline
uv init --package --name blog_pipeline --python 3.12 .
```

Expected: `pyproject.toml`, `src/blog_pipeline/__init__.py` 생성됨

- [ ] **Step 2: 의존성 추가**

```bash
uv add fastapi "uvicorn[standard]" apscheduler requests beautifulsoup4 pygithub openai python-dotenv pydantic
uv add --dev pytest pytest-mock httpx
```

Expected: `pyproject.toml`의 `dependencies`에 반영, `uv.lock` 생성

- [ ] **Step 3: `.env.example` 작성**

```
NAVER_CLIENT_ID=
NAVER_CLIENT_SECRET=
NVIDIA_API_KEY=
NVIDIA_MODEL=meta/llama-3.1-70b-instruct
GITHUB_TOKEN=
GITHUB_OWNER=ddastudio140
GITHUB_REPO=blog-post
WEBHOOK_API_KEY=
SCHEDULE_INTERVAL_MINUTES=60
DB_PATH=data/blog_pipeline.db
```

- [ ] **Step 4: `.gitignore` 작성**

```
.env
data/
__pycache__/
*.pyc
.venv/
.pytest_cache/
```

- [ ] **Step 5: 실패하는 테스트 작성**

`tests/conftest.py`:
```python
import os
import pytest


@pytest.fixture
def env_vars(monkeypatch):
    values = {
        "NAVER_CLIENT_ID": "test-client-id",
        "NAVER_CLIENT_SECRET": "test-client-secret",
        "NVIDIA_API_KEY": "test-nvidia-key",
        "NVIDIA_MODEL": "meta/llama-3.1-70b-instruct",
        "GITHUB_TOKEN": "test-github-token",
        "GITHUB_OWNER": "ddastudio140",
        "GITHUB_REPO": "blog-post",
        "WEBHOOK_API_KEY": "test-webhook-key",
        "SCHEDULE_INTERVAL_MINUTES": "60",
        "DB_PATH": "data/test_blog_pipeline.db",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values
```

`tests/test_config.py`:
```python
from blog_pipeline.config import load_settings


def test_load_settings_reads_all_fields(env_vars):
    settings = load_settings()

    assert settings.naver_client_id == "test-client-id"
    assert settings.naver_client_secret == "test-client-secret"
    assert settings.nvidia_api_key == "test-nvidia-key"
    assert settings.nvidia_model == "meta/llama-3.1-70b-instruct"
    assert settings.github_token == "test-github-token"
    assert settings.github_owner == "ddastudio140"
    assert settings.github_repo == "blog-post"
    assert settings.webhook_api_key == "test-webhook-key"
    assert settings.schedule_interval_minutes == 60
    assert settings.db_path == "data/test_blog_pipeline.db"
```

- [ ] **Step 6: 테스트 실패 확인**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'blog_pipeline.config'`

- [ ] **Step 7: `config.py` 구현**

```python
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    naver_client_id: str
    naver_client_secret: str
    nvidia_api_key: str
    nvidia_model: str
    github_token: str
    github_owner: str
    github_repo: str
    webhook_api_key: str
    schedule_interval_minutes: int
    db_path: str


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        naver_client_id=os.environ["NAVER_CLIENT_ID"],
        naver_client_secret=os.environ["NAVER_CLIENT_SECRET"],
        nvidia_api_key=os.environ["NVIDIA_API_KEY"],
        nvidia_model=os.environ.get("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct"),
        github_token=os.environ["GITHUB_TOKEN"],
        github_owner=os.environ.get("GITHUB_OWNER", "ddastudio140"),
        github_repo=os.environ.get("GITHUB_REPO", "blog-post"),
        webhook_api_key=os.environ["WEBHOOK_API_KEY"],
        schedule_interval_minutes=int(os.environ.get("SCHEDULE_INTERVAL_MINUTES", "60")),
        db_path=os.environ.get("DB_PATH", "data/blog_pipeline.db"),
    )
```

- [ ] **Step 8: 테스트 통과 확인**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (2 tests)

- [ ] **Step 9: 커밋**

```bash
git init
git add pyproject.toml uv.lock .env.example .gitignore src/ tests/
git commit -m "feat: scaffold python project with settings loader"
```

---

## Task 2: SQLite storage 모듈

**Files:**
- Create: `src/blog_pipeline/storage.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Consumes: 없음 (DB 경로 문자열만 받음)
- Produces:
  - `storage.init_db(db_path: str) -> None` — 3개 테이블 생성(존재하면 스킵)
  - `storage.record_keyword_selection(db_path: str, keyword: str, selected_at: str) -> None`
  - `storage.get_recent_keywords(db_path: str, since_date: str) -> list[str]` — `selected_at >= since_date` (ISO 날짜 문자열 비교)인 키워드 목록
  - `storage.save_sources(db_path: str, run_id: str, keyword: str, sources: list[dict]) -> None` — 각 dict는 `title`, `body`, `image_url`, `link`, `fetched_at` 키를 가짐
  - `storage.get_recent_posts(db_path: str, limit: int) -> list[dict]` — `published_at` 내림차순, 각 dict는 `title`, `summary` 키 포함
  - `storage.save_post(db_path: str, keyword: str, title: str, summary: str, file_path: str, image_path: str | None, commit_sha: str | None, published_at: str) -> None`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_storage.py`:
```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_storage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'blog_pipeline.storage'`

- [ ] **Step 3: `storage.py` 구현**

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_storage.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: 커밋**

```bash
git add src/blog_pipeline/storage.py tests/test_storage.py
git commit -m "feat: add sqlite storage module for keyword/source/post history"
```

---

## Task 3: keyword_source 모듈 (zum.com 크롤링 + 중복 회피)

**Files:**
- Create: `src/blog_pipeline/keyword_source.py`
- Test: `tests/test_keyword_source.py`

**Interfaces:**
- Consumes: `storage.get_recent_keywords(db_path, since_date) -> list[str]`, `storage.record_keyword_selection(db_path, keyword, selected_at) -> None` (Task 2)
- Produces: `keyword_source.select_keyword(db_path: str, manual_keyword: str | None = None) -> str | None`
  - `manual_keyword`가 주어지면 그대로 반환 (storage 기록 없음 — 수동 키워드는 중복 회피 이력에 남기지 않음, 반복 지정 허용)
  - 없으면 zum.com 크롤링 → 최근 2일 제외 → 첫 후보 선택 + `record_keyword_selection` 기록 → 반환
  - 후보 소진 시 `None`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_keyword_source.py`:
```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_keyword_source.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'blog_pipeline.keyword_source'`

- [ ] **Step 3: `keyword_source.py` 구현**

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_keyword_source.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: 커밋**

```bash
git add src/blog_pipeline/keyword_source.py tests/test_keyword_source.py
git commit -m "feat: add keyword_source module with zum.com trend crawling"
```

---

## Task 4: news_collector 모듈 (네이버 뉴스 검색 + 본문 크롤링)

**Files:**
- Create: `src/blog_pipeline/news_collector.py`
- Test: `tests/test_news_collector.py`

**Interfaces:**
- Consumes: 없음 (client_id/secret은 인자로 받음)
- Produces:
  - `news_collector.collect(keyword: str, naver_client_id: str, naver_client_secret: str) -> list[dict]`
  - 각 dict: `{"title": str, "body": str, "image_url": str | None, "link": str, "fetched_at": str}`
  - 내부 헬퍼 `_search_news(keyword, client_id, secret) -> list[dict]` (raw API 응답의 items)
  - 내부 헬퍼 `_filter_and_limit(items: list[dict]) -> list[dict]` (도메인 필터 + 상위 5건)
  - 내부 헬퍼 `_parse_article(url: str) -> dict | None` (도메인별 셀렉터로 파싱, 실패 시 None)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_news_collector.py`:
```python
from unittest.mock import Mock, patch

from blog_pipeline import news_collector


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


def test_collect_skips_articles_that_fail_to_parse():
    search_items = [
        {"link": "https://n.news.naver.com/1"},
        {"link": "https://n.news.naver.com/2"},
    ]

    with patch("blog_pipeline.news_collector._search_news", return_value=search_items), \
         patch("blog_pipeline.news_collector._parse_article", side_effect=[None, {"title": "t", "body": "b", "image_url": None}]):
        result = news_collector.collect("천궁", "client-id", "client-secret")

    assert len(result) == 1
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_news_collector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'blog_pipeline.news_collector'`

- [ ] **Step 3: `news_collector.py` 구현**

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

KST = timezone(timedelta(hours=9))
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
    candidates = _filter_and_limit(items)

    results = []
    fetched_at = datetime.now(KST).isoformat()
    for item in candidates:
        parsed = _parse_article(item["link"])
        if parsed is None:
            continue
        results.append(
            {
                "title": parsed["title"],
                "body": parsed["body"],
                "image_url": parsed["image_url"],
                "link": item["link"],
                "fetched_at": fetched_at,
            }
        )
    return results
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_news_collector.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: 커밋**

```bash
git add src/blog_pipeline/news_collector.py tests/test_news_collector.py
git commit -m "feat: add news_collector module for naver news search and parsing"
```

---

## Task 5: post_writer 모듈 (NVIDIA build API로 블로그 글 생성)

**Files:**
- Create: `prompts/generate-post-prompt.md`
- Create: `src/blog_pipeline/post_writer.py`
- Test: `tests/test_post_writer.py`

**Interfaces:**
- Consumes: `storage.get_recent_posts(db_path, limit) -> list[dict]` (Task 2, `title`/`summary` 키 사용)
- Produces: `post_writer.generate_post(sources: list[dict], keyword: str, db_path: str, api_key: str, model: str) -> dict`
  - 반환 dict: `{"title": str, "body_markdown": str, "summary": str}`
  - 내부 헬퍼 `_build_prompt(sources: list[dict], keyword: str, reference_posts: list[dict]) -> str`
  - 내부 헬퍼 `_call_nvidia_api(prompt: str, api_key: str, model: str) -> str` (raw LLM 응답 텍스트, 1회 재시도 포함)
  - 내부 헬퍼 `_parse_response(raw_text: str) -> dict` (title/body_markdown/summary 파싱)

**응답 포맷 계약:** LLM에게 다음 구분자 포맷으로 응답하도록 프롬프트에서 강제한다.
```
TITLE: <제목>
SUMMARY: <1~2문장 요약>
---
<마크다운 본문>
```

- [ ] **Step 1: 프롬프트 템플릿 작성**

`prompts/generate-post-prompt.md`:
```markdown
당신은 한국어 블로그 작가입니다. 아래 뉴스 기사들을 참고하여 자연스러운 블로그 글을 작성하세요.

# 작성 규칙
- 마크다운 형식으로 작성
- 기사 내용을 그대로 베끼지 말고 재구성/요약하여 작성
- 독자가 이해하기 쉽도록 소제목(##)을 활용
- 과도한 광고성 문구, 확인되지 않은 추측은 배제

# 참고할 과거 글 목록
아래는 이 블로그에서 최근 작성한 글 제목/요약입니다. 내용이 겹치지 않도록 참고하고,
관련이 있다면 자연스럽게 문맥으로 연결하세요 (과거 글이 없으면 이 섹션은 비어있습니다).

{reference_posts}

# 참고 뉴스 데이터
{sources}

# 출력 형식
다음 형식을 반드시 지켜서 응답하세요. 다른 설명 문구를 추가하지 마세요.

TITLE: <블로그 글 제목>
SUMMARY: <이 글을 한두 문장으로 요약>
---
<여기부터 마크다운 본문>
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_post_writer.py`:
```python
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
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `uv run pytest tests/test_post_writer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'blog_pipeline.post_writer'`

- [ ] **Step 4: `post_writer.py` 구현**

```python
from __future__ import annotations

from pathlib import Path

from openai import OpenAI

from blog_pipeline import storage

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
PROMPT_TEMPLATE_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "generate-post-prompt.md"
REFERENCE_POST_LIMIT = 5


def _format_reference_posts(reference_posts: list[dict]) -> str:
    if not reference_posts:
        return "(과거 글 없음)"
    lines = [f"- {post['title']}: {post['summary']}" for post in reference_posts]
    return "\n".join(lines)


def _format_sources(sources: list[dict]) -> str:
    parts = []
    for idx, source in enumerate(sources, start=1):
        parts.append(f"[기사 {idx}] {source['title']}\n{source['body']}")
    return "\n\n".join(parts)


def _build_prompt(sources: list[dict], keyword: str, reference_posts: list[dict]) -> str:
    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    prompt = template.format(
        reference_posts=_format_reference_posts(reference_posts),
        sources=_format_sources(sources),
    )
    return f"키워드: {keyword}\n\n{prompt}"


def _call_nvidia_api(prompt: str, api_key: str, model: str) -> str:
    client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key)
    last_error: Exception | None = None
    for _ in range(2):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content
        except Exception as error:  # noqa: BLE001
            last_error = error
    raise last_error


def _parse_response(raw_text: str) -> dict:
    header, _, body = raw_text.partition("---")
    title = ""
    summary = ""
    for line in header.splitlines():
        if line.startswith("TITLE:"):
            title = line[len("TITLE:"):].strip()
        elif line.startswith("SUMMARY:"):
            summary = line[len("SUMMARY:"):].strip()
    return {"title": title, "summary": summary, "body_markdown": body.strip()}


def generate_post(sources: list[dict], keyword: str, db_path: str, api_key: str, model: str) -> dict:
    reference_posts = storage.get_recent_posts(db_path, limit=REFERENCE_POST_LIMIT)
    prompt = _build_prompt(sources, keyword, reference_posts)
    raw_text = _call_nvidia_api(prompt, api_key, model)
    return _parse_response(raw_text)
```

Note: `PROMPT_TEMPLATE_PATH`는 `.format()`을 사용하므로 `prompts/generate-post-prompt.md`에 리터럴 중괄호(`{`, `}`)가 없어야 한다. Step 1의 템플릿에는 `{reference_posts}`, `{sources}` 두 플레이스홀더만 존재하므로 안전하다.

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/test_post_writer.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: 커밋**

```bash
git add prompts/generate-post-prompt.md src/blog_pipeline/post_writer.py tests/test_post_writer.py
git commit -m "feat: add post_writer module using NVIDIA build API"
```

---

## Task 6: publisher 모듈 (이미지 다운로드 + GitHub 커밋)

**Files:**
- Create: `src/blog_pipeline/publisher.py`
- Test: `tests/test_publisher.py`

**Interfaces:**
- Consumes: 없음 (모든 값을 인자로 받음)
- Produces: `publisher.publish(keyword: str, title: str, body_markdown: str, image_url: str | None, github_token: str, github_owner: str, github_repo: str, published_at: datetime) -> dict`
  - 반환 dict: `{"file_path": str, "image_path": str | None, "commit_sha": str}`
  - 내부 헬퍼 `_download_image(image_url: str) -> tuple[bytes, str] | None` (bytes, 확장자) — 실패 시 None
  - 내부 헬퍼 `_build_paths(keyword: str, published_at: datetime, image_ext: str | None) -> tuple[str, str | None]` (md_path, image_path)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_publisher.py`:
```python
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch

import pytest

from blog_pipeline import publisher

KST = timezone(timedelta(hours=9))


def test_build_paths_with_image():
    published_at = datetime(2026, 7, 11, 14, 30, tzinfo=KST)

    md_path, image_path = publisher._build_paths("천궁", published_at, "jpg")

    assert md_path == "posts/20260711/1430_천궁.md"
    assert image_path == "posts/20260711/1430_천궁.jpg"


def test_build_paths_without_image():
    published_at = datetime(2026, 7, 11, 14, 30, tzinfo=KST)

    md_path, image_path = publisher._build_paths("천궁", published_at, None)

    assert md_path == "posts/20260711/1430_천궁.md"
    assert image_path is None


def test_download_image_returns_bytes_and_extension():
    mock_response = Mock()
    mock_response.content = b"fake-image-bytes"
    mock_response.raise_for_status = lambda: None

    with patch("blog_pipeline.publisher.requests.get", return_value=mock_response):
        result = publisher._download_image("https://example.com/photo.jpg")

    assert result == (b"fake-image-bytes", "jpg")


def test_download_image_returns_none_on_failure():
    with patch("blog_pipeline.publisher.requests.get", side_effect=Exception("network error")):
        result = publisher._download_image("https://example.com/photo.jpg")

    assert result is None


def test_publish_uploads_markdown_and_image_and_returns_paths():
    published_at = datetime(2026, 7, 11, 14, 30, tzinfo=KST)
    mock_repo = Mock()
    mock_repo.create_file.side_effect = [
        {"commit": Mock(sha="md-commit-sha")},
        {"commit": Mock(sha="image-commit-sha")},
    ]
    mock_github_instance = Mock()
    mock_github_instance.get_repo.return_value = mock_repo

    with patch("blog_pipeline.publisher.Github", return_value=mock_github_instance), \
         patch("blog_pipeline.publisher._download_image", return_value=(b"bytes", "jpg")):
        result = publisher.publish(
            keyword="천궁",
            title="천궁 미사일 체계 총정리",
            body_markdown="## 개요\n천궁은...",
            image_url="https://example.com/photo.jpg",
            github_token="token",
            github_owner="ddastudio140",
            github_repo="blog-post",
            published_at=published_at,
        )

    assert result["file_path"] == "posts/20260711/1430_천궁.md"
    assert result["image_path"] == "posts/20260711/1430_천궁.jpg"
    assert result["commit_sha"] == "md-commit-sha"
    assert mock_repo.create_file.call_count == 2


def test_publish_without_image_url_skips_image_upload():
    published_at = datetime(2026, 7, 11, 14, 30, tzinfo=KST)
    mock_repo = Mock()
    mock_repo.create_file.return_value = {"commit": Mock(sha="md-commit-sha")}
    mock_github_instance = Mock()
    mock_github_instance.get_repo.return_value = mock_repo

    with patch("blog_pipeline.publisher.Github", return_value=mock_github_instance):
        result = publisher.publish(
            keyword="천궁",
            title="제목",
            body_markdown="본문",
            image_url=None,
            github_token="token",
            github_owner="ddastudio140",
            github_repo="blog-post",
            published_at=published_at,
        )

    assert result["image_path"] is None
    assert mock_repo.create_file.call_count == 1
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_publisher.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'blog_pipeline.publisher'`

- [ ] **Step 3: `publisher.py` 구현**

```python
from __future__ import annotations

import re
from datetime import datetime

import requests
from github import Github

_EXTENSION_PATTERN = re.compile(r"\.(jpg|jpeg|png|webp|gif|bmp)($|\?)", re.IGNORECASE)
_DEFAULT_EXTENSION = "jpg"


def _download_image(image_url: str) -> tuple[bytes, str] | None:
    try:
        response = requests.get(image_url, timeout=10)
        response.raise_for_status()
    except Exception:
        return None

    match = _EXTENSION_PATTERN.search(image_url)
    extension = match.group(1).lower() if match else _DEFAULT_EXTENSION
    return response.content, extension


def _build_paths(keyword: str, published_at: datetime, image_ext: str | None) -> tuple[str, str | None]:
    date_dir = published_at.strftime("%Y%m%d")
    time_prefix = published_at.strftime("%H%M")
    md_path = f"posts/{date_dir}/{time_prefix}_{keyword}.md"
    image_path = f"posts/{date_dir}/{time_prefix}_{keyword}.{image_ext}" if image_ext else None
    return md_path, image_path


def publish(
    keyword: str,
    title: str,
    body_markdown: str,
    image_url: str | None,
    github_token: str,
    github_owner: str,
    github_repo: str,
    published_at: datetime,
) -> dict:
    image_bytes: bytes | None = None
    image_ext: str | None = None
    if image_url:
        downloaded = _download_image(image_url)
        if downloaded is not None:
            image_bytes, image_ext = downloaded

    md_path, image_path = _build_paths(keyword, published_at, image_ext)

    client = Github(github_token)
    repo = client.get_repo(f"{github_owner}/{github_repo}")

    commit_message = f"[Auto] {keyword} 블로그 포스트 - {published_at.strftime('%Y-%m-%d %H:%M')}"
    md_result = repo.create_file(md_path, commit_message, f"# {title}\n\n{body_markdown}")
    commit_sha = md_result["commit"].sha

    if image_bytes is not None and image_path is not None:
        repo.create_file(image_path, commit_message, image_bytes)

    return {"file_path": md_path, "image_path": image_path, "commit_sha": commit_sha}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_publisher.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: 커밋**

```bash
git add src/blog_pipeline/publisher.py tests/test_publisher.py
git commit -m "feat: add publisher module for image download and github commit"
```

---

## Task 7: pipeline 오케스트레이터

**Files:**
- Create: `src/blog_pipeline/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes:
  - `keyword_source.select_keyword(db_path, manual_keyword) -> str | None` (Task 3)
  - `news_collector.collect(keyword, naver_client_id, naver_client_secret) -> list[dict]` (Task 4)
  - `storage.save_sources(db_path, run_id, keyword, sources) -> None` (Task 2)
  - `post_writer.generate_post(sources, keyword, db_path, api_key, model) -> dict` (Task 5)
  - `publisher.publish(keyword, title, body_markdown, image_url, github_token, github_owner, github_repo, published_at) -> dict` (Task 6)
  - `storage.save_post(db_path, keyword, title, summary, file_path, image_path, commit_sha, published_at) -> None` (Task 2)
  - `config.Settings` (Task 1)
- Produces: `pipeline.run(settings: Settings, manual_keyword: str | None = None) -> dict`
  - 반환 dict: `{"status": "published" | "no_keyword" | "no_sources", "keyword": str | None, "file_path": str | None}`
  - 뉴스 수집 결과가 빈 리스트면 `"no_sources"` 상태로 종료 (게시하지 않음)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_pipeline.py`:
```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'blog_pipeline.pipeline'`

- [ ] **Step 3: `pipeline.py` 구현**

```python
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from blog_pipeline import keyword_source, news_collector, post_writer, publisher, storage
from blog_pipeline.config import Settings

KST = timezone(timedelta(hours=9))


def run(settings: Settings, manual_keyword: str | None = None) -> dict:
    keyword = keyword_source.select_keyword(settings.db_path, manual_keyword)
    if keyword is None:
        return {"status": "no_keyword", "keyword": None, "file_path": None}

    sources = news_collector.collect(keyword, settings.naver_client_id, settings.naver_client_secret)
    if not sources:
        return {"status": "no_sources", "keyword": keyword, "file_path": None}

    run_id = str(uuid.uuid4())
    storage.save_sources(settings.db_path, run_id, keyword, sources)

    generated = post_writer.generate_post(
        sources, keyword, settings.db_path, settings.nvidia_api_key, settings.nvidia_model
    )

    published_at = datetime.now(KST)
    main_image_url = sources[0].get("image_url")

    publish_result = publisher.publish(
        keyword=keyword,
        title=generated["title"],
        body_markdown=generated["body_markdown"],
        image_url=main_image_url,
        github_token=settings.github_token,
        github_owner=settings.github_owner,
        github_repo=settings.github_repo,
        published_at=published_at,
    )

    storage.save_post(
        settings.db_path,
        keyword=keyword,
        title=generated["title"],
        summary=generated["summary"],
        file_path=publish_result["file_path"],
        image_path=publish_result["image_path"],
        commit_sha=publish_result["commit_sha"],
        published_at=published_at.isoformat(),
    )

    return {"status": "published", "keyword": keyword, "file_path": publish_result["file_path"]}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: 커밋**

```bash
git add src/blog_pipeline/pipeline.py tests/test_pipeline.py
git commit -m "feat: add pipeline orchestrator wiring all modules together"
```

---

## Task 8: FastAPI app (webhook + APScheduler) + CLI

**Files:**
- Create: `src/blog_pipeline/app.py`
- Create: `src/blog_pipeline/cli.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `pipeline.run(settings, manual_keyword) -> dict` (Task 7), `config.load_settings() -> Settings` (Task 1)
- Produces:
  - `app.create_app(settings: Settings) -> FastAPI`
  - FastAPI 앱은 상태 `app.state.pipeline_lock: threading.Lock` 보유
  - `POST /webhook/keyword` — 헤더 `X-API-Key` 검증, 바디 `{"keyword": str}`, 락 획득 실패 시 409, 성공 시 `pipeline.run()` 결과를 200으로 반환
  - `cli.main(argv: list[str] | None = None) -> int` — `--keyword` 옵션 파싱 후 `pipeline.run()` 호출, 결과를 stdout에 출력하고 exit code 반환(published/no_keyword/no_sources는 0, 예외 발생 시 1)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_app.py`:
```python
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from blog_pipeline.app import create_app
from blog_pipeline.config import Settings


@pytest.fixture
def settings(tmp_path):
    from blog_pipeline import storage

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
        webhook_api_key="test-webhook-key",
        schedule_interval_minutes=60,
        db_path=db_path,
    )


@pytest.fixture
def client(settings):
    app = create_app(settings)
    return TestClient(app)


def test_webhook_rejects_missing_api_key(client):
    response = client.post("/webhook/keyword", json={"keyword": "천궁"})

    assert response.status_code == 401


def test_webhook_rejects_wrong_api_key(client):
    response = client.post(
        "/webhook/keyword",
        json={"keyword": "천궁"},
        headers={"X-API-Key": "wrong-key"},
    )

    assert response.status_code == 401


def test_webhook_runs_pipeline_and_returns_result(client):
    with patch("blog_pipeline.app.pipeline.run", return_value={"status": "published", "keyword": "천궁", "file_path": "posts/x.md"}) as mock_run:
        response = client.post(
            "/webhook/keyword",
            json={"keyword": "천궁"},
            headers={"X-API-Key": "test-webhook-key"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "published"
    mock_run.assert_called_once()


def test_webhook_returns_409_when_pipeline_already_running(client):
    app = client.app
    app.state.pipeline_lock.acquire()
    try:
        response = client.post(
            "/webhook/keyword",
            json={"keyword": "천궁"},
            headers={"X-API-Key": "test-webhook-key"},
        )
        assert response.status_code == 409
    finally:
        app.state.pipeline_lock.release()
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'blog_pipeline.app'`

- [ ] **Step 3: `app.py` 구현**

```python
from __future__ import annotations

import threading

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from blog_pipeline import pipeline
from blog_pipeline.config import Settings


class KeywordRequest(BaseModel):
    keyword: str


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings
    app.state.pipeline_lock = threading.Lock()

    scheduler = BackgroundScheduler(timezone="Asia/Seoul")
    scheduler.add_job(
        lambda: _run_scheduled(app),
        "interval",
        minutes=settings.schedule_interval_minutes,
    )
    app.state.scheduler = scheduler

    @app.on_event("startup")
    def _start_scheduler() -> None:
        scheduler.start()

    @app.on_event("shutdown")
    def _stop_scheduler() -> None:
        scheduler.shutdown(wait=False)

    @app.post("/webhook/keyword")
    def webhook_keyword(payload: KeywordRequest, x_api_key: str | None = Header(default=None)):
        if x_api_key != settings.webhook_api_key:
            raise HTTPException(status_code=401, detail="invalid api key")

        acquired = app.state.pipeline_lock.acquire(blocking=False)
        if not acquired:
            raise HTTPException(status_code=409, detail="pipeline already running")
        try:
            result = pipeline.run(settings, manual_keyword=payload.keyword)
        finally:
            app.state.pipeline_lock.release()

        return result

    return app


def _run_scheduled(app: FastAPI) -> None:
    acquired = app.state.pipeline_lock.acquire(blocking=False)
    if not acquired:
        return
    try:
        pipeline.run(app.state.settings)
    finally:
        app.state.pipeline_lock.release()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_app.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: `cli.py` 구현 (테스트 없이 — 얇은 wrapper)**

```python
from __future__ import annotations

import argparse
import json
import sys

from blog_pipeline import pipeline
from blog_pipeline.config import load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="블로그 자동화 파이프라인 단발 실행")
    parser.add_argument("--keyword", default=None, help="수동으로 지정할 키워드")
    args = parser.parse_args(argv)

    settings = load_settings()
    try:
        result = pipeline.run(settings, manual_keyword=args.keyword)
    except Exception as error:  # noqa: BLE001
        print(f"파이프라인 실행 실패: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: 커밋**

```bash
git add src/blog_pipeline/app.py src/blog_pipeline/cli.py tests/test_app.py
git commit -m "feat: add fastapi webhook/scheduler app and cli entrypoint"
```

---

## Task 9: Docker/docker-compose 배포 구성

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Modify: `pyproject.toml` (entry point 확인)

**Interfaces:**
- Consumes: 전체 `src/blog_pipeline` 패키지 (Task 1~8)
- Produces: 컨테이너 이미지가 `uvicorn blog_pipeline.app:create_app`을 기동 가능한 형태로 실행 (실제로는 `main.py` 형태의 얇은 실행 스크립트 필요 — `create_app`은 `settings` 인자가 필요하므로 factory 패턴 대신 모듈 레벨 앱 인스턴스를 만드는 `asgi.py`를 추가)

- [ ] **Step 1: ASGI 진입점 추가**

`src/blog_pipeline/asgi.py`:
```python
from blog_pipeline.app import create_app
from blog_pipeline.config import load_settings

app = create_app(load_settings())
```

- [ ] **Step 2: `Dockerfile` 작성**

```dockerfile
FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src/ ./src/
COPY prompts/ ./prompts/

ENV PYTHONPATH=/app/src

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "blog_pipeline.asgi:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: `docker-compose.yml` 작성**

```yaml
services:
  blog-pipeline:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./data:/app/data
    restart: unless-stopped
```

- [ ] **Step 4: 로컬 빌드 검증**

Run: `docker compose build`
Expected: 이미지 빌드 성공 (에러 없이 종료)

- [ ] **Step 5: 커밋**

```bash
git add src/blog_pipeline/asgi.py Dockerfile docker-compose.yml
git commit -m "feat: add docker deployment configuration"
```

---

## Task 10: 전체 파이프라인 통합 검증

**Files:**
- 없음 (기존 파일 대상 수동/자동 검증)

**Interfaces:**
- Consumes: Task 1~9의 전체 결과물

- [ ] **Step 1: 전체 테스트 스위트 실행**

Run: `uv run pytest -v`
Expected: 모든 테스트 PASS (Task 1~8에서 작성한 전체 테스트, 약 30개)

- [ ] **Step 2: `.env` 파일 생성 안내 확인**

Run: `test -f .env && echo "exists" || echo "missing (expected before real run)"`
Expected: `missing` (실제 API 키는 사용자가 직접 채워야 함 — 이 단계는 정보 확인용)

- [ ] **Step 3: CLI 자체 진단 (설정 누락 시 에러 확인)**

Run: `uv run python -m blog_pipeline.cli --keyword "테스트" 2>&1 | head -5`
Expected: `.env`가 없거나 필수 키가 비어있으므로 `KeyError` 또는 유사한 명확한 에러 메시지로 즉시 실패 (실제 크롤링/API 호출까지 도달하지 않음)

- [ ] **Step 4: 결과 보고**

전체 테스트 통과 및 CLI가 설정 누락을 올바르게 감지하는지 확인했다면, 사용자에게 다음을 안내:
- 실제 운영을 위해 `.env.example`을 복사해 `.env`를 만들고 API 키를 채워야 함
- `docker compose up -d`로 배포 가능
- 수동 테스트: `uv run python -m blog_pipeline.cli --keyword "천궁"`

- [ ] **Step 5: 커밋 (README 업데이트가 있다면)**

이 태스크는 코드 변경이 없으므로 커밋 생략. 검증 결과만 사용자에게 보고.

---

## Self-Review 결과

**Spec coverage:**
- 키워드 선정(zum.com + 중복회피) → Task 3 ✅
- 뉴스 수집(네이버 검색 + 도메인별 파싱) → Task 4 ✅
- SQLite 저장(keyword_history/sources/posts) → Task 2 ✅
- NVIDIA API 블로그 생성 + 과거 글 참조 → Task 5 ✅
- 이미지 다운로드 + GitHub 게시 → Task 6 ✅
- 파이프라인 오케스트레이션 → Task 7 ✅
- webhook(API Key 인증) + 스케줄러 + 동시 실행 방지 → Task 8 ✅
- CLI 단발 실행 → Task 8 ✅
- Docker 배포 → Task 9 ✅
- 설정(.env) → Task 1 ✅

**Placeholder scan:** 전체 재확인 완료, "TODO"/"TBD"/미완성 코드 없음.

**Type consistency:** `select_keyword(db_path, manual_keyword)`, `collect(keyword, client_id, client_secret)`, `generate_post(sources, keyword, db_path, api_key, model)`, `publish(keyword, title, body_markdown, image_url, github_token, github_owner, github_repo, published_at)`, `save_post(...)` — Task 7(pipeline.py)에서 사용하는 시그니처가 각 모듈의 Task별 Interfaces 선언과 일치함을 확인.
