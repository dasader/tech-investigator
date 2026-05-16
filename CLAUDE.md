# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

TechSpec — 기술 분야(예: HBM, 양자컴퓨터)를 입력하면 Semantic Scholar / OpenAlex / Scopus에서 논문을 검색하고, Gemini로 수치를 추출해 글로벌 최고 달성치를 보고서로 생성하는 서비스.

## 실행 명령어

```bash
# 전체 스택 실행 (최초 또는 코드 변경 후)
docker compose up --build

# 마이그레이션 적용 (최초 실행 후 또는 모델 변경 후)
docker compose exec api alembic upgrade head

# 테스트 (Docker 내부에서만 실행 가능 — Gemini SDK·DB·Redis 등 컨테이너 의존성)
docker compose exec api pytest
docker compose exec api pytest backend/tests/test_validation_agent.py -v

# 마이그레이션 신규 생성
docker compose exec api alembic revision --autogenerate -m "설명"

# 프론트엔드 개발 서버 (Docker 없이)
cd frontend && npm install && npm run dev
```

## 포트

| 서비스 | 호스트 포트 |
|--------|-----------|
| API (FastAPI) | 8017 |
| Frontend | 8098 |
| PostgreSQL | 5439 |
| Redis | 6381 |
| MinIO API | 9000 |
| MinIO Console | 9001 |

## 아키텍처

### 전체 흐름

```
사용자 입력 (기술명 + 이메일)
  → POST /api/tech-queries         # TechQuery 생성
  → Gemini가 지표 목록 제안         # IndicatorAgent
  → 사용자 지표 확정
  → POST /api/queries/{id}/jobs    # Celery 태스크 큐잉
  → WebSocket /ws/jobs/{id}        # 실시간 진행 상태
  → GET /api/jobs/{id}/results     # 완료 후 결과 조회
  → GET /api/jobs/{id}/pdf         # 보고서 HTML (인쇄 → PDF)
```

### 파이프라인 (4단계, `backend/app/agents/pipeline.py`)

`run_pipeline_task` (Celery) → `asyncio.run(run_pipeline(...))` 순으로 실행:

1. **search_node** — 지표당 논문 검색. `TechQuery.search_source`에 따라 분기 (`search_agent.py`)
2. **extract_node** — Gemini에게 각 논문 초록에서 수치 추출 (`extraction_agent.py`), 동시성 `Semaphore(10)`. 지표당 상한 `settings.max_papers_per_indicator`(현재 50)
3. **validate_node** — 신뢰도 필터(`min_confidence_score` 0.5 이상) + value 큰 순으로 상위 `top_results_per_indicator`(현재 5)건 선별, DB 저장 (`validation_agent.py`)
4. **synthesize_node** — Gemini로 마크다운 보고서 생성 (`synthesis_agent.py`). **검증 통과 데이터가 0건이면 호출 자체를 스킵**(모델이 수치·출처를 통째로 지어내는 환각을 차단)

### 검색 소스 모드 (`pipeline.py`의 `SOURCE_PLAN`)

`TechQuery.search_source` 컬럼 값으로 분기:

- `combined` (기본): Semantic Scholar + OpenAlex 동시 검색, DOI/title 기반 best-of 머지. 동시성 `S2=1` / `OpenAlex=10` (S2는 ~1 req/s 제한)
- `scopus`: Scopus 단독. 동시성 `5` (Elsevier ~9 req/s 한도)

### 비동기 작업 + 알림

- **Celery 재시도**: `pipeline_task.py:14`의 `max_retries=3, default_retry_delay=60` — 예외 시 60초 후 최대 3회 재시도
- **이메일 알림**: 정상 완료 시점에 **단 1회** 발송 (`pipeline_task.py:35`, `services/email_service.py`). "장시간 대기" 임계값 분기는 없음. 다음 조건이면 무발송:
  - `user_email` 미입력
  - 파이프라인 예외 (retry 후 최종 실패 포함)
  - `SMTP_USER` 미설정 (조용히 return)
- 본문은 plaintext, 결과 페이지 URL만 안내 — 보고서 직접 링크 아님

### 핵심 패턴

**Gemini SDK 호출** — SDK가 동기 전용이므로 모두 `app/utils.py`의 `run_sync()`로 래핑:
```python
from app.utils import run_sync
response = await run_sync(lambda: genai_client.models.generate_content(...))
```

**국가 정보** — Semantic Scholar affiliations는 대부분 빈값. 대신 OpenAlex API를 DOI로 조회 (`_get_country_from_openalex` in `extraction_agent.py`). Gemini 호출과 `asyncio.gather()`로 병렬 실행.

**SQLAlchemy 모델 초기화 주의** — `main.py`와 `pipeline_task.py` 양쪽에 모든 모델을 명시적으로 import해야 FK 관계가 정상 작동. 모델 추가 시 두 파일 모두 업데이트 필요.

**보고서 PDF** — weasyprint 버그로 서버사이드 생성 불가. `/api/jobs/{id}/pdf`는 HTML을 반환하고 브라우저 `window.print()`로 저장.

**`MAX_PAPERS_PER_INDICATOR` 변경 시 주의** — `backend/app/config.py`의 기본값과 루트 `.env`의 환경변수가 **둘 다 정의**되어 있고 `.env`가 우선한다. 변경하려면 두 곳을 함께 수정해야 효과가 있음.

**한국어 UI 텍스트** — `Job.current_step`(예: "논문 검색 중", "수치 추출 중", "완료")과 이메일 본문 등 사용자 노출 문자열은 한국어로 고정. 변경 시 프론트엔드/이메일 모두 확인.

### DB 스키마

```
tech_queries → indicators (query_id FK, confirmed_by_user)
tech_queries → jobs (query_id FK, status/progress_pct/current_step/report_markdown)
indicators   → metric_values (indicator_id FK, value/unit/year/country/confidence_score/doi)
```

### 프론트엔드

React SPA (Vite + Tailwind), 라우터 없이 `App.tsx`의 `step` 상태로 4단계 전환:
`input` → `indicators` → `status` → `results`

진행 상태는 WebSocket(`useJobStatus.ts`)으로 polling. 결과 페이지는 보고서/데이터 탭으로 구분되며, 데이터 탭에는 `TimeSeriesChart`(연도별)와 `CountryCompareChart`(국가별) 차트 포함.
