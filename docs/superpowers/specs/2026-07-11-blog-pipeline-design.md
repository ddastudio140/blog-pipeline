# 블로그 자동화 파이프라인 (n8n → Python) 설계

## 배경

기존에는 n8n(`n8n/auto-blog.json`)으로 다음을 자동화했다:

- zum.com 실시간 트렌드에서 키워드 선정 (최근 2일 중복 회피)
- 네이버 뉴스 검색 API로 뉴스 수집, 본문 크롤링
- Gemini CLI로 블로그 글(마크다운) 생성
- GitHub 저장소에 글/이미지 커밋

이 워크플로우를 n8n에서 Python으로 대체한다. 블로그 글 생성에 사용하는 LLM은 Gemini CLI에서 [NVIDIA build API](https://build.nvidia.com/)로 완전히 교체한다.

## 목표

- 키워드 선정 → 뉴스 수집 → 블로그 글 생성 → GitHub 게시까지 전체 파이프라인을 Python으로 재구현
- 수집 주기를 사용자가 설정할 수 있어야 한다
- 외부에서 키워드를 직접 전송할 수 있어야 한다 (n8n의 webhook 대체)
- 작성된 블로그 글의 제목/요약을 저장해, 새 글 작성 시 과거 글을 참조로 활용할 수 있어야 한다

## 범위 밖

- n8n UI를 통한 워크플로우 관리는 대체하지 않는다 (완전히 Python 코드/설정 기반으로 전환)
- 다국어 지원, 다중 LLM 폴백은 다루지 않는다 (NVIDIA API 단일 사용)

## 아키텍처

하나의 상시 실행 FastAPI 서비스가 스케줄러와 webhook을 겸한다.

```
FastAPI app (상시 실행, docker-compose 단일 서비스)
  ├─ APScheduler          : 설정된 주기(SCHEDULE_INTERVAL_MINUTES)마다 파이프라인 자동 실행
  ├─ POST /webhook/keyword: 외부에서 키워드 전송 시 즉시 파이프라인 실행 (API Key 인증)
  └─ pipeline.py (공용 오케스트레이터, 스케줄러/webhook 양쪽에서 호출)
       ├─ keyword_source.py   : zum.com 트렌드 크롤링 + SQLite 기반 중복 회피 선택
       ├─ news_collector.py   : 네이버 뉴스 검색 API + 본문 크롤링(일반/스포츠/연예)
       ├─ storage.py          : SQLite (수집 소스 원문 + 발행 이력 + 키워드 이력)
       ├─ post_writer.py      : NVIDIA build.nvidia.com API로 블로그 글 생성 (과거 글 참조 주입)
       └─ publisher.py        : 대표 이미지 다운로드 + GitHub 커밋 업로드
```

CLI 진입점(`python -m blog_pipeline.cli --keyword "..."`)도 제공해 단발 실행/디버깅을 지원한다. CLI와 webhook, 스케줄러 모두 동일한 `pipeline.run(keyword: str | None)` 함수를 호출한다.

동시 실행 방지: 스케줄러 트리거와 webhook 트리거가 겹칠 수 있으므로, 파이프라인 실행 중에는 in-process 락을 걸고, 락이 걸려 있는 동안 들어온 webhook 요청은 409를 반환한다.

## 컴포넌트별 설계

### keyword_source.py

- 입력 키워드가 주어지면 그대로 반환
- 없으면 zum.com(`https://zum.com/`)의 `.issue-word-list__keyword` 요소를 크롤링해 후보 키워드 목록을 얻는다
- `storage.py`의 `keyword_history` 테이블에서 최근 2일(오늘+어제, KST 기준) 내 이미 선택된 키워드를 조회해 제외
- 첫 번째로 남는 후보를 선택하고, 선택 즉시 `keyword_history`에 기록
- 후보가 모두 소진되면 `None` 반환 (파이프라인은 조용히 종료, 에러 아님)

### news_collector.py

- 네이버 뉴스 검색 API(`https://openapi.naver.com/v1/search/news.json`) 호출, `display=30`
- `link`가 `https://n.news.naver.com`, `https://m.sports.naver.com`, `https://m.entertain.naver.com` 중 하나로 시작하는 항목만 필터
- 상위 5건만 사용
- 도메인별로 다른 CSS 셀렉터로 제목/본문/대표이미지 추출 (n8n의 3가지 파싱 규칙을 그대로 이식):
  - 일반(`n.news.naver.com`): `#dic_area`(본문), `#title_area`(제목), `meta[property="og:image"]`(이미지)
  - 스포츠(`m.sports.naver.com`): `._article_content`(본문), `h2`(제목), `meta[property="og:image"]`(이미지)
  - 연예(`m.entertain.naver.com`): `div._article_content`(본문), `meta[property="og:title"]`(제목), `div._article_content img`(이미지)
- 개별 기사 크롤링 실패 시 해당 기사만 스킵하고 나머지로 진행

### storage.py

SQLite 파일: `data/blog_pipeline.db`

```sql
CREATE TABLE keyword_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    selected_at TEXT NOT NULL  -- ISO8601, KST
);

CREATE TABLE sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    keyword TEXT NOT NULL,
    title TEXT,
    body TEXT,
    image_url TEXT,
    link TEXT,
    fetched_at TEXT NOT NULL
);

CREATE TABLE posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    file_path TEXT NOT NULL,
    image_path TEXT,
    commit_sha TEXT,
    published_at TEXT NOT NULL
);
```

- `posts` 테이블은 과거 글 참조(포스트 생성 시 프롬프트에 주입)와 이력 조회에 사용
- `keyword_history`는 2일 중복 회피 로직에만 사용 (오래된 행은 주기적으로 정리하지 않아도 무방 — 조회 시 날짜로 필터링)

### post_writer.py

- NVIDIA build API(`NVIDIA_API_KEY` 사용)로 블로그 글 생성 요청
- 기존 n8n의 `generate-post-prompt-gemini.md` 프롬프트 내용을 참고해 새 프롬프트 템플릿을 작성 (`prompts/generate-post-prompt.md`)
- `storage.py`에서 최근 발행된 글 중 관련성 있는 N개(제목+요약)를 조회해 프롬프트에 "참고할 과거 글 목록"으로 주입 — 자연스러운 연결/중복 회피 목적
- 응답에서 제목/본문/요약을 파싱 (요약은 없으면 LLM에게 별도로 1~2문장 요약도 함께 생성하도록 프롬프트에 명시)
- API 실패 시 1회 재시도, 그래도 실패하면 예외 발생시켜 run 실패 처리

### publisher.py

- 대표 이미지 다운로드 (`sources`에서 첫 기사의 `image_url` 사용, 확장자는 URL에서 추출, 실패 시 이미지 없이 진행)
- GitHub API(`GITHUB_TOKEN`)로 다음 경로에 커밋:
  - 마크다운: `posts/{yyyyMMdd}/{HHmm}_{keyword}.md`
  - 이미지: `posts/{yyyyMMdd}/{HHmm}_{keyword}.{ext}`
- 대상 저장소는 `.env`의 `GITHUB_OWNER`/`GITHUB_REPO` (기본값 `ddastudio140`/`blog-post`)
- 성공 시 `posts` 테이블에 결과 기록 (commit_sha 포함)
- 실패 시 예외 발생, `posts`에 기록하지 않음 (재시도는 다음 스케줄/webhook 호출에 맡김)

## 설정 (.env)

```
NAVER_CLIENT_ID=
NAVER_CLIENT_SECRET=
NVIDIA_API_KEY=
GITHUB_TOKEN=
GITHUB_OWNER=ddastudio140
GITHUB_REPO=blog-post
WEBHOOK_API_KEY=
SCHEDULE_INTERVAL_MINUTES=60
```

- `.env`는 `.gitignore`에 포함하고, `.env.example`을 커밋해 필요한 키를 문서화한다
- `SCHEDULE_INTERVAL_MINUTES` 변경은 컨테이너 재시작이 필요 (APScheduler가 기동 시점에 값을 읽음)

## API

### POST /webhook/keyword

- 인증: `X-API-Key` 헤더가 `WEBHOOK_API_KEY`와 일치해야 함 (n8n의 headerAuth 대체)
- 요청 바디: `{"keyword": "천궁"}`
- 파이프라인 실행 중이면 409 반환
- 정상 접수 시 즉시 파이프라인을 실행하고 결과(성공/실패, 생성된 글 경로)를 응답으로 반환

## 에러 처리 정책

| 상황 | 처리 |
|---|---|
| 키워드 후보 소진 | 로그만 남기고 조용히 종료 (커밋 없음, run 자체는 "성공"으로 간주) |
| 개별 기사 크롤링 실패 | 해당 기사 스킵, 5개 중 일부만 있어도 계속 진행 |
| NVIDIA API 실패 | 1회 재시도 후 실패 시 run 실패로 종료, 에러 로그 |
| GitHub 업로드 실패 | 예외 발생, run 실패로 기록, posts row 남기지 않음 |
| webhook 중복 요청 (실행 중) | 409 반환 |

## 배포

- Dockerfile + docker-compose로 단일 서비스 구성 (포트 8000, webhook용)
- 볼륨 마운트: `./data`(SQLite), `.env`
- 컨테이너 내부 프로세스는 FastAPI + APScheduler가 함께 상시 실행

## 테스트 전략

- `keyword_source.py`, `news_collector.py`, `post_writer.py`, `publisher.py`: 외부 API/HTTP 호출을 mock한 unit test
- `storage.py`: 임시 SQLite 파일 기반 통합 테스트
- webhook 엔드포인트: FastAPI `TestClient`로 인증/동시성 락/정상 흐름 테스트

## 미해결/향후 논의

- 없음 (범위 내 항목은 모두 확정됨)
