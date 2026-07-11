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
