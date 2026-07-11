from __future__ import annotations

from pathlib import Path

from openai import OpenAI

from blog_pipeline import storage

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
PROMPT_TEMPLATE_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "generate-post-prompt.md"
REFERENCE_POST_LIMIT = 5


def _format_reference_posts(reference_posts: list[dict]) -> str:
    if not reference_posts:
        return "(과거 글 없음)"
    lines = [f"- {post['title']}: {post['summary']}" for post in reference_posts]
    return "\n".join(lines)


def _format_sources(sources: list[dict]) -> str:
    parts = []
    for idx, source in enumerate(sources, start=1):
        parts.append(f"[기사 {idx}] {source['title']}\n{source['body']}")
    return "\n\n".join(parts)


def _build_prompt(sources: list[dict], keyword: str, reference_posts: list[dict]) -> str:
    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    prompt = template.format(
        reference_posts=_format_reference_posts(reference_posts),
        sources=_format_sources(sources),
    )
    return f"키워드: {keyword}\n\n{prompt}"


def _call_nvidia_api(prompt: str, api_key: str, model: str) -> str:
    client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key)
    last_error: Exception | None = None
    for _ in range(2):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content
        except Exception as error:  # noqa: BLE001
            last_error = error
    raise last_error


def _parse_response(raw_text: str) -> dict:
    header, _, body = raw_text.partition("---")
    title = ""
    summary = ""
    for line in header.splitlines():
        if line.startswith("TITLE:"):
            title = line[len("TITLE:"):].strip()
        elif line.startswith("SUMMARY:"):
            summary = line[len("SUMMARY:"):].strip()
    return {"title": title, "summary": summary, "body_markdown": body.strip()}


def generate_post(sources: list[dict], keyword: str, db_path: str, api_key: str, model: str) -> dict:
    reference_posts = storage.get_recent_posts(db_path, limit=REFERENCE_POST_LIMIT)
    prompt = _build_prompt(sources, keyword, reference_posts)
    raw_text = _call_nvidia_api(prompt, api_key, model)
    return _parse_response(raw_text)
