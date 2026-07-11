FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
COPY prompts/ ./prompts/

RUN uv sync --frozen --no-dev

ENV PYTHONPATH=/app/src

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "blog_pipeline.asgi:app", "--host", "0.0.0.0", "--port", "8000"]
