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
