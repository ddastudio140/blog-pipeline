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
