# Further Jobs — 2026-05-13

OpenAlex 통합 (`feat/openalex-search`) 진행 중 `/simplify` 리뷰에서 발견되었으나 이번 PR scope에서 의도적으로 보류한 항목과, 본 작업과 무관하게 노출된 사전 버그를 기록한다.

---

## A. Skipped from `/simplify` (별도 PR 권장)

> **Status (2026-05-14):** A1-A4 전부 완료. A3은 `chore/a3-per-source-concurrency` 브랜치. 본 문서의 모든 항목(A1-A4 + B1) 처리 완료.

### A1. 3-way HTTP retry 루프 공통화

- **위치**
  - `backend/app/agents/search_agent.py:26-45` (Semantic Scholar)
  - `backend/app/agents/scopus_agent.py:108-129`
  - `backend/app/agents/openalex_agent.py:55-76`
- **문제**: 세 모듈 모두 구조가 동일한 `for attempt in range(3) / try / except HTTPStatusError, TimeoutException, RequestError / else: raise` 패턴을 복사·붙여넣었다. 정책 변경(예: 재시도 횟수, 백오프 방식, 새 예외 타입)이 발생하면 세 곳을 모두 수정해야 한다.
- **권장**: `backend/app/utils.py` 또는 신규 `backend/app/agents/_http_retry.py`에 다음 시그니처의 헬퍼를 추출.
  ```python
  async def get_with_retry(url, params, headers=None, *, service_name: str, max_attempts: int = 3) -> dict
  ```
  각 agent는 URL/params/service 이름만 전달.
- **이번 PR에서 skip한 이유**: scope가 OpenAlex 추가에서 search agent 전반 리팩터로 확장됨. 회귀 위험과 리뷰 영역이 별도 PR로 분리하는 게 안전.

### A2. `httpx.AsyncClient` per-call 인스턴스화

- **위치**
  - `backend/app/agents/openalex_agent.py:71` — search 루프 안에서 매 attempt마다 새 클라이언트 생성
  - `backend/app/agents/extraction_agent.py:55` — `_get_country_from_openalex` 안에서 paper마다 새 클라이언트 생성
  - 동일 패턴: `scopus_agent.py`, `search_agent.py`
- **문제**: `httpx.AsyncClient`는 connection pool을 관리하지만, 매 호출마다 새로 만들면 keep-alive 연결이 폐기되어 매번 TCP+TLS 핸드셰이크가 발생. paper 단위 호출(`_get_country_from_openalex`)에서 손실이 더 크다 (수십~수백 paper).
- **권장**: module-level 또는 dependency-injected `AsyncClient` 인스턴스 하나를 재사용. 다만 lifecycle (애플리케이션 종료 시 close) 관리가 필요하므로 `lifespan` 핸들러나 context manager 패턴 도입 필요.
- **이번 PR에서 skip한 이유**: lifecycle 관리는 main.py / Celery worker 초기화에 영향을 미치며 single-agent 변경 범위를 벗어남.

### A3. 검색 단계 동시성 — `Semaphore(1)`

- **위치**: `backend/app/agents/pipeline.py:36` (`search_node`)
- **문제**: 모든 검색 source에 대해 `Semaphore(1)`로 직렬화. Semantic Scholar는 무키 1 req/s 제약이 있어 합리적이지만, OpenAlex는 100 req/s, Scopus는 9 req/s 한도라 직렬화가 불필요하게 느리다. N개 지표 검색 시 매번 N×(왕복+200ms) 누적.
- **권장**: source별 동시성 정책 도입.
  ```python
  CONCURRENCY = {"semantic_scholar": 1, "scopus": 5, "openalex": 10}
  semaphore = asyncio.Semaphore(CONCURRENCY[search_source])
  ```
- **이번 PR에서 skip한 이유**: source별 분기는 pipeline 추상화 수준에 닿는 변경. 별도 검토 후 적용.

### A4. 테스트 fixture 추출 — `httpx.AsyncClient` mock 보일러플레이트

- **위치**
  - `backend/tests/test_openalex_agent.py` — 5건의 search test가 각각 6줄 mock 셋업 반복
  - `backend/tests/test_scopus_agent.py` — 동일 패턴 4건 반복
  - 합계 9곳에서 동일 코드 복제
- **문제**: 향후 `httpx.AsyncClient` 사용 방식 변경 시 9곳을 모두 손봐야 함. 테스트 가독성도 저하.
- **권장**: `backend/tests/conftest.py`에 fixture 추가.
  ```python
  @pytest.fixture
  def httpx_mock(monkeypatch):
      def _make(module_path: str, status_code: int = 200, json_body=None):
          ...
      return _make
  ```
- **이번 PR에서 skip한 이유**: 테스트 전용 변경이라 운영 영향 없음. 세 번째 agent test가 추가될 때 함께 도입하는 것이 자연스럽다.

---

## B. 사전 버그 (master 시점부터 존재)

> **Status (2026-05-14):** B1 완료 — `chore/further-jobs-cleanup` 브랜치.

### B1. `test_extraction_agent.py`의 잘못된 import

- **위치**: `backend/tests/test_extraction_agent.py` (정확한 라인은 본 PR에서 확인 안 함)
- **증상**:
  ```
  ImportError: cannot import name 'extract_metric_from_paper'
  from 'app.agents.extraction_agent'
  ```
- **원인**: 실 구현은 `extract_metrics_from_paper`(복수형)인데 테스트는 `extract_metric_from_paper`(단수형)를 import. 함수 rename 후 테스트 동기화 누락으로 보임.
- **영향**: `pytest tests/test_extraction_agent.py` 단독 실행 시 collection 단계에서 실패. `pytest` 전체 실행 시에도 해당 모듈만 수집 실패하고 다른 모듈은 진행.
- **확인 commit**: `ed38824 — feat: skip OpenAlex lookup when paper.country already set (Scopus path)` (본 브랜치 분기점 8fe5bc6 이전).
- **권장 fix**: 테스트의 import 및 호출부를 모두 `extract_metrics_from_paper`로 수정. 동시에 함수 시그니처 변화(이제 indicators **list**를 한 번에 받는 batch 추출)에 맞춰 테스트 케이스 업데이트가 필요할 수 있음.
