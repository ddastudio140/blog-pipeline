from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from blog_pipeline import keyword_source, news_collector, post_writer, publisher, storage
from blog_pipeline.config import Settings

KST = timezone(timedelta(hours=9))


def run(settings: Settings, manual_keyword: str | None = None) -> dict:
    storage.init_db(settings.db_path)

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
