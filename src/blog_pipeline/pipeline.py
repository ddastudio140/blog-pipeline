from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

from blog_pipeline import keyword_source, news_collector, post_writer, publisher, storage
from blog_pipeline.config import Settings

KST = timezone(timedelta(hours=9))
logger = logging.getLogger("blog_pipeline.pipeline")

TOTAL_STEPS = 6
SEPARATOR = "=" * 70


def _step(n: int, run_id: str, keyword: str | None, message: str) -> None:
    logger.info("[%d/%d] %s (keyword=%s, run_id=%s)", n, TOTAL_STEPS, message, keyword, run_id)


def run(settings: Settings, manual_keyword: str | None = None) -> dict:
    run_id = str(uuid.uuid4())
    started_at = time.monotonic()

    logger.info(SEPARATOR)
    logger.info(
        "파이프라인 실행 시작 (run_id=%s, manual_keyword=%s, 총 %d단계)",
        run_id,
        manual_keyword,
        TOTAL_STEPS,
    )

    try:
        return _run_steps(settings, manual_keyword, run_id)
    finally:
        elapsed = time.monotonic() - started_at
        logger.info("파이프라인 실행 종료: %.1f초 소요 (run_id=%s)", elapsed, run_id)
        logger.info(SEPARATOR)


def _run_steps(settings: Settings, manual_keyword: str | None, run_id: str) -> dict:
    storage.init_db(settings.db_path)

    keyword = keyword_source.select_keyword(settings.db_path, manual_keyword)
    if keyword is None:
        logger.warning("선정할 키워드가 없어 파이프라인을 종료합니다 (run_id=%s)", run_id)
        return {"status": "no_keyword", "keyword": None, "file_path": None}
    _step(1, run_id, keyword, "키워드 선정 완료")

    sources = news_collector.collect(keyword, settings.naver_client_id, settings.naver_client_secret)
    if not sources:
        logger.warning("키워드 '%s'에 대한 뉴스 소스를 찾지 못했습니다 (run_id=%s)", keyword, run_id)
        return {"status": "no_sources", "keyword": keyword, "file_path": None}
    _step(2, run_id, keyword, f"뉴스 소스 수집 완료: {len(sources)}건")

    storage.save_sources(settings.db_path, run_id, keyword, sources)
    _step(3, run_id, keyword, "수집한 뉴스 소스 DB 저장 완료")

    generated = post_writer.generate_post(
        sources, keyword, settings.db_path, settings.nvidia_api_key, settings.nvidia_model
    )
    _step(4, run_id, keyword, f"블로그 글 생성 완료: title={generated['title']!r}")

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
    _step(
        5,
        run_id,
        keyword,
        f"GitHub 게시 완료: file_path={publish_result['file_path']}, commit_sha={publish_result['commit_sha']}",
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
    _step(6, run_id, keyword, "게시글 메타데이터 DB 저장 완료")

    return {"status": "published", "keyword": keyword, "file_path": publish_result["file_path"]}
