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
