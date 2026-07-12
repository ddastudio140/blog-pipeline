from __future__ import annotations

import argparse
import json
import sys

from blog_pipeline import pipeline
from blog_pipeline.config import load_settings
from blog_pipeline.logging_setup import setup_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="블로그 자동화 파이프라인 단발 실행")
    parser.add_argument("--keyword", default=None, help="수동으로 지정할 키워드")
    args = parser.parse_args(argv)

    setup_logging()
    settings = load_settings()
    try:
        result = pipeline.run(settings, manual_keyword=args.keyword)
    except Exception as error:  # noqa: BLE001
        print(f"파이프라인 실행 실패: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
