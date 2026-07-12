from __future__ import annotations

import logging
import re
from datetime import datetime

import requests
from github import Github

_EXTENSION_PATTERN = re.compile(r"\.(jpg|jpeg|png|webp|gif|bmp)($|\?)", re.IGNORECASE)
_DEFAULT_EXTENSION = "jpg"
logger = logging.getLogger("blog_pipeline.publisher")


def _download_image(image_url: str) -> tuple[bytes, str] | None:
    try:
        response = requests.get(image_url, timeout=10)
        response.raise_for_status()
    except Exception as error:  # noqa: BLE001
        logger.warning("대표 이미지 다운로드 실패: %s (%s)", image_url, error)
        return None

    match = _EXTENSION_PATTERN.search(image_url)
    extension = match.group(1).lower() if match else _DEFAULT_EXTENSION
    logger.info("대표 이미지 다운로드 성공: %s", image_url)
    return response.content, extension


def _sanitize_keyword_for_path(keyword: str) -> str:
    # 경로 구분자와 상위 디렉토리 이동 시퀀스를 제거
    sanitized = re.sub(r"[/\\]", "_", keyword)
    sanitized = sanitized.replace("..", "_")
    return sanitized


def _build_paths(keyword: str, published_at: datetime, image_ext: str | None) -> tuple[str, str | None]:
    safe_keyword = _sanitize_keyword_for_path(keyword)
    date_dir = published_at.strftime("%Y%m%d")
    time_prefix = published_at.strftime("%H%M")
    md_path = f"posts/{date_dir}/{time_prefix}_{safe_keyword}.md"
    image_path = f"posts/{date_dir}/{time_prefix}_{safe_keyword}.{image_ext}" if image_ext else None
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
    logger.info("GitHub 저장소 연결됨: %s/%s (keyword=%s)", github_owner, github_repo, keyword)

    commit_message = f"[Auto] {keyword} 블로그 포스트 - {published_at.strftime('%Y-%m-%d %H:%M')}"
    md_result = repo.create_file(md_path, commit_message, f"# {title}\n\n{body_markdown}")
    commit_sha = md_result["commit"].sha
    logger.info("마크다운 파일 커밋 완료 (keyword=%s): %s (sha=%s)", keyword, md_path, commit_sha)

    if image_bytes is not None and image_path is not None:
        repo.create_file(image_path, commit_message, image_bytes)
        logger.info("이미지 파일 커밋 완료 (keyword=%s): %s", keyword, image_path)

    return {"file_path": md_path, "image_path": image_path, "commit_sha": commit_sha}
