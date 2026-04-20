# TechSpec 서비스 설계 문서

**작성일:** 2026-04-20  
**프로젝트:** 국가전략기술 Spec 조사 서비스

---

## 1. 서비스 개요

국가전략기술 분야의 정의·범위를 입력하면, 해당 분야의 기술 수준을 나타내는 정량 지표(spec)를 자동 생성하고, 학술 논문에 근거한 달성치를 레퍼런스와 함께 제공하는 서비스.

### 목표 사용자
- 정부/공공기관 정책 담당자 (기술 수준 현황 보고)
- 연구자/학자 (글로벌 달성치 파악)
- 기업 R&D 전략팀 (경쟁 기술 벤치마킹)

### 핵심 가치
- 논문 기반 수치 제공으로 신뢰성 확보
- LLM 자동화로 빠른 초안 생성
- 사용자 편집으로 품질 보증

---

## 2. 사용자 흐름 (4단계)

### 단계 1: 기술 입력
- 국가전략기술 12대 분야 분류 선택 (드롭다운)
- 자유 텍스트로 세부 범위 보완
- 예시: "반도체 → HBM 고대역폭 메모리 적층 기술, 이형접합 기판 기반"

### 단계 2: 지표 확정
- Gemini가 5~10개 정량 지표 초안 자동 생성 (5~10초 내 즉시 반환)
- 사용자가 지표 추가/삭제/수정 가능
- 확정 후 비동기 분석 작업 시작

### 단계 3: 비동기 처리
- 5~15분 소요 (WebSocket으로 진행률 실시간 표시)
- 완료 시 이메일 알림 발송
- 부분 실패 시 완료된 데이터로 리포트 생성

### 단계 4: 결과 대시보드
- 지표별 최고 달성치 + 논문 출처 (DOI/제목)
- 시계열 추이 차트 (연도별 달성치 변화)
- 국가별 비교표 (한국/미국/중국/일본 등)
- **분석 기준일 표시** (jobs.completed_at — 검색 시점에 따라 결과가 달라질 수 있으므로)
- PDF 다운로드 (리포트 표지에 분석 기준일 명시)

---

## 3. 아키텍처

### 전체 구성

```
[ React SPA ] ←REST/WebSocket→ [ FastAPI ]
                                     │
                              [ Celery Worker ]
                                     │
                        [ LangGraph 멀티 에이전트 파이프라인 ]
                          ①→②→③→④→⑤
                                     │
              ┌──────────────────────┤
          PostgreSQL              Redis              MinIO
          (메인 DB)              (캐시/브로커)       (PDF 저장)
```

### 멀티 에이전트 파이프라인 (LangGraph)

| # | 에이전트 | 모델 | 역할 |
|---|---------|------|------|
| ① | Indicator Agent | gemini-2.5-pro | 기술 설명 → 정량 지표 초안 생성 |
| ② | Search Agent | API 직접 호출 | Semantic Scholar + arXiv + Google Search Grounding 병렬 검색 |
| ③ | Extraction Agent | gemini-2.5-pro | 논문에서 수치·단위·연도·국가 구조화 추출 |
| ④ | Validation Agent | gemini-2.5-pro | 복수 출처 교차검증, 신뢰도 점수 산출 |
| ⑤ | Synthesis Agent | gemini-2.5-flash | 시계열·국가비교 집계, 리포트 마크다운 생성 |

### 외부 데이터 소스

| 소스 | 용도 | 비용 |
|------|------|------|
| Semantic Scholar API | 학술 논문 검색 (200M+ 건) | 무료 |
| arXiv API | 최신 프리프린트 검색 | 무료 |
| Google Search Grounding | 최신 기술 보고서·뉴스 검색 | Gemini API 내 포함 |

---

## 4. 데이터 모델

### 핵심 테이블

```sql
tech_queries
  id, user_id, category, description, created_at

indicators
  id, query_id, name, unit, search_keywords, confirmed_by_user

jobs
  id, query_id, status(pending/running/done/failed),
  progress_pct, current_step, completed_at   ← 분석 기준 시점으로 사용

metric_values
  id, indicator_id, value, unit, year, country,
  confidence_score, paper_title, doi, source_url, quote
```

---

## 5. 오류 처리

| 상황 | 처리 방식 |
|------|----------|
| 논문에서 수치 미발견 | Google Search Grounding 재시도 1회 → 없으면 "데이터 부족" 표시 |
| API 호출 실패 | Celery 자동 재시도 3회 (지수 백오프) → 부분 결과로 진행 |
| confidence_score < 0.5 | 결과에 ⚠️ 경고 + 원문 인용구(quote) 함께 표시 |
| 작업 타임아웃 (15분) | 완료된 지표까지 부분 저장, 사용자 재시도 가능 |

---

## 6. 기술 스택

| 레이어 | 기술 |
|--------|------|
| Frontend | React + TypeScript, Vite, Tailwind CSS, Recharts, React Query |
| Backend | FastAPI, Pydantic v2, SQLAlchemy + Alembic, WebSocket |
| Agent | LangGraph, google-generativeai SDK |
| 비동기 | Celery + Redis |
| DB/저장 | PostgreSQL, MinIO (PDF) |
| PDF 생성 | WeasyPrint |
| 배포 | Docker Compose |

### Docker Compose 서비스

| 서비스 | 호스트 포트 | 컨테이너 포트 | 역할 |
|--------|-----------|--------------|------|
| frontend | **8098** | 80 | React (Nginx 정적 빌드) |
| frontend-dev | **5186** | 5173 | Vite dev 서버 (로컬 개발 전용) |
| api | **8017** | 8000 | FastAPI |
| worker | 없음 | - | Celery + LangGraph |
| db | **5439** | 5432 | PostgreSQL |
| redis | **6381** | 6379 | Redis |
| minio | **9000** | 9000 | MinIO (S3 호환) |

---

## 7. 환경변수 설정

```env
# Gemini 모델 (변경 시 여기만 수정)
GEMINI_API_KEY=your_key_here
GEMINI_MODEL_COMPLEX=gemini-2.5-pro
GEMINI_MODEL_FAST=gemini-2.5-flash

# 외부 API
SEMANTIC_SCHOLAR_API_KEY=your_key_here

# 처리 파라미터
JOB_TIMEOUT_MINUTES=15
MAX_PAPERS_PER_INDICATOR=30
MIN_CONFIDENCE_SCORE=0.5

# DB/인프라
DATABASE_URL=postgresql://...
REDIS_URL=redis://redis:6379
MINIO_ENDPOINT=minio:9000
SMTP_HOST=smtp.gmail.com      # 이메일 알림용 (필수)
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
```

---

## 8. 테스트 전략

- **유닛 테스트 (pytest):** Extraction Agent 수치 추출 정확도, Validation Agent 이상치 제거 로직
- **통합 테스트:** 실제 API 호출 포함 전체 파이프라인 E2E (반도체 예시 입력)
- **LLM 품질 평가:** 알려진 논문 수치와 비교하는 golden set 구성, confidence_score 보정

---

## 9. 확장 계획

- API 엔드포인트 공개 (타 시스템 연동)
- 결과 캐시 (Redis, 24시간) — 유사 쿼리 재처리 방지
- Celery Worker 수평 확장 (컨테이너 복제)
- 향후: 사용자별 결과 히스토리, 분야별 지표 템플릿 DB 구축
