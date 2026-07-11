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
