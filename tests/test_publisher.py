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


def test_build_paths_sanitizes_path_traversal_keyword():
    published_at = datetime(2026, 7, 11, 14, 30, tzinfo=KST)

    md_path, image_path = publisher._build_paths("../../secret", published_at, "jpg")

    assert md_path.startswith("posts/20260711/")
    assert ".." not in md_path
    assert "/" not in md_path[len("posts/20260711/"):]
    assert image_path.startswith("posts/20260711/")
    assert ".." not in image_path
    assert "/" not in image_path[len("posts/20260711/"):]


def test_build_paths_sanitizes_backslashes_in_keyword():
    published_at = datetime(2026, 7, 11, 14, 30, tzinfo=KST)

    md_path, _ = publisher._build_paths("..\\..\\windows_secret", published_at, None)

    assert md_path.startswith("posts/20260711/")
    assert "\\" not in md_path
    assert ".." not in md_path


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


def test_publish_when_image_download_fails_uploads_markdown_only():
    published_at = datetime(2026, 7, 11, 14, 30, tzinfo=KST)
    mock_repo = Mock()
    mock_repo.create_file.return_value = {"commit": Mock(sha="md-commit-sha")}
    mock_github_instance = Mock()
    mock_github_instance.get_repo.return_value = mock_repo

    with patch("blog_pipeline.publisher.Github", return_value=mock_github_instance), \
         patch("blog_pipeline.publisher.requests.get", side_effect=Exception("network error")):
        result = publisher.publish(
            keyword="천궁",
            title="제목",
            body_markdown="본문",
            image_url="https://example.com/photo.jpg",
            github_token="token",
            github_owner="ddastudio140",
            github_repo="blog-post",
            published_at=published_at,
        )

    assert result["image_path"] is None
    assert mock_repo.create_file.call_count == 1


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
