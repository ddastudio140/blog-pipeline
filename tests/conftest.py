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
