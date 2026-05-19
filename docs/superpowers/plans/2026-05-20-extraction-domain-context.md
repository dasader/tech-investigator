# Extraction Domain Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gemini 추출 프롬프트에 사용자가 입력한 기술 도메인(`category` + `description`)을 주입해, 도메인 외 논문에서 추출된 수치가 confidence 감점을 받도록 한다.

**Architecture:** `BATCH_EXTRACTION_PROMPT` 상단에 도메인 컨텍스트 블록과 매칭 지침 1단락을 추가. `extract_metrics_from_paper` 시그니처에 두 키워드 인자(기본값 `""`)를 더해 backward compatible 유지. `pipeline.py`의 `extract_node`에서 `state["category"]`/`state["description"]`을 전달.

**Tech Stack:** Python / FastAPI / Gemini SDK / pytest-asyncio.

**Spec:** [`docs/superpowers/specs/2026-05-20-extraction-domain-context-design.md`](../specs/2026-05-20-extraction-domain-context-design.md)

---

## File Structure

**Modify:**
- `backend/app/agents/extraction_agent.py` — `BATCH_EXTRACTION_PROMPT` 상단 블록 추가 (~10줄), `extract_metrics_from_paper` 시그니처 +2 키워드 인자, `format()` 호출에 `category`/`description` 추가.
- `backend/app/agents/pipeline.py:82-85` — `extract_node`의 task 생성에 `category`/`description` 키워드 전달.
- `backend/tests/test_extraction_agent.py` — 신규 테스트 2개 추가 (기존 6개 테스트는 backward compatible 유지로 변경 불요).

**No changes:** DB schema, migrations, API 응답 형식, `indicator_agent.py`, `validation_agent.py`, `synthesis_agent.py`, `search_agent.py`, 프론트엔드, `test_pipeline_task.py`(extract_metrics_from_paper를 mock하므로 시그니처 변화 영향 없음).

---

## Task 1: `extract_metrics_from_paper`에 도메인 컨텍스트 주입

**Files:**
- Modify: `backend/app/agents/extraction_agent.py:13-38` (BATCH_EXTRACTION_PROMPT), `:62-68` (시그니처), `:94-99` (format 호출)
- Modify: `backend/tests/test_extraction_agent.py` (신규 테스트 추가)

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_extraction_agent.py` 끝에 추가:

```python
@pytest.mark.asyncio
async def test_extraction_prompt_includes_domain_context():
    """category/description이 Gemini prompt에 포함된다."""
    captured_prompts: list[str] = []

    def _capture(**kwargs):
        captured_prompts.append(kwargs.get("contents", ""))
        return _gemini_response([{
            "indicator_id": 1, "value": 1228.0, "unit": "GB/s",
            "confidence_score": 0.9, "quote": "1228 GB/s",
        }])

    with patch("app.agents.extraction_agent.genai_client") as mock_client, \
         patch("app.agents.extraction_agent._get_country_from_openalex",
               new=AsyncMock(return_value=None)):
        mock_client.models.generate_content.side_effect = _capture
        await extract_metrics_from_paper(
            PAPER_WITH_VALUE, [INDICATOR_BANDWIDTH], client=_client(),
            category="HBM 고대역폭 메모리",
            description="이형접합 기판 기반의 적층 기술",
        )

    assert len(captured_prompts) == 1
    prompt = captured_prompts[0]
    assert "HBM 고대역폭 메모리" in prompt
    assert "이형접합 기판 기반의 적층 기술" in prompt
    assert "연구 도메인 컨텍스트" in prompt
    assert "도메인 매칭 지침" in prompt
```

- [ ] **Step 2: 테스트 실행 (실패)**

Run: `docker compose exec api pytest tests/test_extraction_agent.py::test_extraction_prompt_includes_domain_context -v`
Expected: FAIL — `TypeError: extract_metrics_from_paper() got an unexpected keyword argument 'category'`.

- [ ] **Step 3: 프롬프트 + 시그니처 + format 호출 수정**

`backend/app/agents/extraction_agent.py:13` 부근의 `BATCH_EXTRACTION_PROMPT` 정의를 다음으로 **교체**:

```python
BATCH_EXTRACTION_PROMPT = """다음 논문 초록에서 지표 목록의 수치를 각각 추출하세요.

연구 도메인 컨텍스트:
- 기술 분야: {category}
- 세부 설명: {description}

도메인 매칭 지침:
- 논문이 위 도메인과 명백히 다른 세부기술을 다루는 경우(예: 다른 메모리 타입, 다른 응용 영역) 수치는 추출하되 confidence_score를 0.3 이하로 책정하세요.
- 인접 기술을 비교 목적으로 다루는 경우(예: HBM 분석 중 GDDR7 비교)는 confidence_score를 중간(약 0.5) 책정.
- 도메인이 정확히 일치하면 평소대로 평가.

논문 제목: {title}
논문 초록: {abstract}

추출 대상 지표 (JSON):
{indicators_json}

단위 처리 규칙:
1. 각 지표에 unit이 지정된 경우, 논문의 수치를 해당 단위로 환산하여 반환하세요.
   예) 지표 단위가 "nm"이고 논문이 "1.2 μm"를 보고하면 → value: 1200, unit: "nm"
2. 단위 환산이 불가능한 경우(물리량 자체가 다른 경우, 예: pieces/mL ↔ cells/mL)는 value를 null로 처리하세요.
3. 지표에 unit이 없으면 논문의 단위를 그대로 반환하세요.
4. 응답의 unit 필드는 항상 지표의 정의된 단위를 사용하세요 (논문 표기 단위가 아님).

추출 힌트 활용:
- 지표에 extraction_hint가 있으면 해당 단서를 참고해 정확히 매칭하세요.
- 단서는 단위 변형·혼동 가능 개념·합리적 범위에 대한 가이드입니다.
- 단서가 없으면 무시하고 진행하세요.

반드시 아래 형식의 JSON 배열로만 응답하세요. 수치가 없으면 value를 null로:
[
  {{"indicator_id": <id>, "value": <숫자|null>, "unit": "<단위|null>", "confidence_score": <0.0~1.0>, "quote": "<근거 문장|null>"}},
  ...
]
지표 {n}개 모두 포함하여 정확히 {n}개 항목을 반환하세요."""
```

같은 파일의 `extract_metrics_from_paper` 시그니처(line 62 부근)를 교체:

```python
async def extract_metrics_from_paper(
    paper: dict,
    indicators: list[dict],
    semaphore: asyncio.Semaphore | None = None,
    *,
    client: httpx.AsyncClient,
    category: str = "",
    description: str = "",
) -> list[tuple[int, dict]]:
```

같은 함수 내부의 `prompt = BATCH_EXTRACTION_PROMPT.format(...)` 호출(line 94 부근)을 교체:

```python
        prompt = BATCH_EXTRACTION_PROMPT.format(
            category=category,
            description=description,
            title=paper.get("title", ""),
            abstract=paper.get("abstract", ""),
            indicators_json=indicators_json,
            n=len(indicators),
        )
```

- [ ] **Step 4: 테스트 통과 확인 + 기존 회귀**

Run: `docker compose exec api pytest tests/test_extraction_agent.py -v`
Expected: 7 passed (기존 6 + 신규 1). 기존 테스트는 category/description 인자를 누락한 채 호출하지만 기본값 `""`로 정상 동작.

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/extraction_agent.py backend/tests/test_extraction_agent.py
git commit -m "feat(extraction): inject domain context into Gemini prompt"
```

---

## Task 2: Backward compatibility 명시적 검증

`category`/`description` 누락 호출이 정상 동작하는지 잠그는 테스트. 기본값 `""`가 만드는 동작을 명시화.

**Files:**
- Modify: `backend/tests/test_extraction_agent.py`

- [ ] **Step 1: 테스트 추가**

`backend/tests/test_extraction_agent.py` 끝에 추가:

```python
@pytest.mark.asyncio
async def test_extraction_works_without_domain_context():
    """category/description 누락 호출도 정상 동작 (backward compat)."""
    captured_prompts: list[str] = []

    def _capture(**kwargs):
        captured_prompts.append(kwargs.get("contents", ""))
        return _gemini_response([{
            "indicator_id": 1, "value": 1228.0, "unit": "GB/s",
            "confidence_score": 0.9, "quote": "1228 GB/s",
        }])

    with patch("app.agents.extraction_agent.genai_client") as mock_client, \
         patch("app.agents.extraction_agent._get_country_from_openalex",
               new=AsyncMock(return_value=None)):
        mock_client.models.generate_content.side_effect = _capture
        # category/description 인자 없이 호출
        results = await extract_metrics_from_paper(
            PAPER_WITH_VALUE, [INDICATOR_BANDWIDTH], client=_client(),
        )

    assert len(results) == 1
    # 컨텍스트 블록은 들어가지만 값은 빈 문자열 — Gemini가 사실상 무시
    prompt = captured_prompts[0]
    assert "기술 분야: \n" in prompt or "기술 분야: " in prompt
    assert "세부 설명: \n" in prompt or "세부 설명: " in prompt
```

- [ ] **Step 2: 테스트 실행 (통과)**

Run: `docker compose exec api pytest tests/test_extraction_agent.py::test_extraction_works_without_domain_context -v`
Expected: PASS (Task 1의 기본값이 처리).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_extraction_agent.py
git commit -m "test(extraction): pin backward-compat for missing domain context"
```

---

## Task 3: `pipeline.py extract_node`가 도메인 컨텍스트 전달

**Files:**
- Modify: `backend/app/agents/pipeline.py:82-85`
- Modify: `backend/tests/test_extraction_agent.py` 또는 별도 테스트 (pipeline-level 검증)

`PipelineState`는 이미 `category`와 `description`을 보유 — 별도 schema 변경 불필요.

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_pipeline.py` 끝에 추가 (없으면 신규):

```python
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.orm import Session
from app.agents.pipeline import extract_node

pytestmark = pytest.mark.no_db


@pytest.mark.asyncio
async def test_extract_node_passes_domain_context_to_extractor():
    """extract_node가 state의 category/description을 extract_metrics_from_paper에 전달한다."""
    captured: dict = {}

    async def fake_extract(paper, indicators, semaphore, *, client, category="", description=""):
        captured["category"] = category
        captured["description"] = description
        return []  # 빈 결과로 충분

    state = {
        "job_id": 1,
        "query_id": 1,
        "category": "HBM 고대역폭 메모리",
        "description": "이형접합 기판 기반의 적층 기술",
        "search_source": "combined",
        "indicators": [{"id": 1, "name": "대역폭", "unit": "GB/s",
                        "search_keywords": "HBM", "extraction_hint": None}],
        "search_results": {1: [{"title": "T", "abstract": "1000 GB/s", "doi": "10.1/x"}]},
        "extracted_values": {},
        "validated_values": {},
        "report_markdown": "",
        "error": "",
    }
    db = MagicMock(spec=Session)
    db.query.return_value.filter.return_value.first.return_value = MagicMock(progress_pct=0.0, current_step="")
    client = AsyncMock(spec=httpx.AsyncClient)

    with patch("app.agents.pipeline.extract_metrics_from_paper", new=fake_extract):
        await extract_node(state, db, client)

    assert captured["category"] == "HBM 고대역폭 메모리"
    assert captured["description"] == "이형접합 기판 기반의 적층 기술"
```

- [ ] **Step 2: 테스트 실행 (실패)**

Run: `docker compose exec api pytest tests/test_pipeline.py::test_extract_node_passes_domain_context_to_extractor -v`
Expected: FAIL — `assert "" == "HBM 고대역폭 메모리"` 또는 KeyError. 현재 pipeline.py는 category/description을 전달하지 않음.

- [ ] **Step 3: `extract_node` 갱신**

`backend/app/agents/pipeline.py:82-85` 부근의 task list comprehension을 교체:

```python
    tasks = [
        extract_metrics_from_paper(
            group["paper"], group["indicators"], semaphore,
            client=client,
            category=state["category"],
            description=state["description"],
        )
        for group in paper_groups.values()
    ]
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `docker compose exec api pytest tests/test_pipeline.py tests/test_extraction_agent.py tests/test_pipeline_task.py -v`
Expected: 모든 테스트 통과 (신규 1 + 기존 모두).

- [ ] **Step 5: 전체 회귀**

Run: `docker compose exec api pytest`
Expected: 전체 통과 (이전 74 + 신규 3 ≈ 77 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/agents/pipeline.py backend/tests/test_pipeline.py
git commit -m "feat(pipeline): pass domain context from extract_node"
```

---

## Task 4: 실 사용 sanity check

도메인 외 논문이 들어왔을 때 confidence가 실제로 낮게 책정되는지 가벼운 수동 검증.

- [ ] **Step 1: 도커 재시작 (코드 반영)**

```bash
docker compose restart api worker
```

(volumes mount이므로 build는 불요. Python 모듈 재로드만 필요.)

- [ ] **Step 2: 한 번 돌려보기**

브라우저에서 `http://localhost:8098` → 작은 입력(예: category="HBM 고대역폭 메모리", description="이형접합 기판 적층 기술")으로 1회 실행.

- [ ] **Step 3: 결과 confidence 분포 확인**

```bash
docker compose exec db psql -U techspec -d techspec -c "SELECT i.name, mv.value, mv.unit, mv.confidence_score, LEFT(mv.paper_title, 60) FROM metric_values mv JOIN indicators i ON i.id = mv.indicator_id ORDER BY mv.created_at DESC LIMIT 20;"
```

Expected: confidence_score 분포가 0.5~0.95에 집중 (도메인 정확 일치 + 인접 기술 중간 + 불일치는 validate 단계에서 drop된 후이므로 거의 미관찰). 도메인 명백 불일치 case가 보고서에 누출되지 않는지 보고서 PDF에서 spot check.

본 task는 비공식 검증 — 결과를 사용자에게 보고하고 plan 종료. confidence 분포 이상하면 별도 follow-up.

---

## Self-Review Notes

**Spec 커버리지** — 스펙 8개 섹션 모두 task에 매핑:
- §3.1 프롬프트 갱신 → Task 1 Step 3
- §3.2 시그니처 확장 → Task 1 Step 3
- §3.3 pipeline 호출부 갱신 → Task 3 Step 3
- §3.4 테스트 → Task 1 Step 1, Task 2 Step 1, Task 3 Step 1
- §4 비목표 → 명시적으로 변경 안 함 (file list에 반영)
- §5 오류 처리 → Task 2가 빈 값 케이스 검증
- §6 효과 측정 → Task 4 (선택적 수동 검증)
- §7 변경 표면 → file 구조 섹션에 일치

**Placeholder 검사**: "TBD"/"TODO" 없음. Task 4는 수동 단계라 명시적으로 "수동 검증"이라고 표기.

**타입 일관성**:
- `extract_metrics_from_paper`의 시그니처는 Task 1에서 정의 후 Task 3에서 호출. 키워드 이름(`category`, `description`)과 기본값(`""`) 모두 일치.
- `PipelineState`의 `category`/`description` 필드는 기존 정의를 그대로 사용 (변경 없음).
