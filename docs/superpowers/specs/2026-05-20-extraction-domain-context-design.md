# Extraction에 도메인 컨텍스트 주입 설계

**Date:** 2026-05-20
**Status:** Approved (brainstorming)
**Scope:** Gemini 추출 프롬프트에 사용자가 입력한 기술 도메인(category + description)을 주입하여, 검색에서 우연히 매칭된 도메인 외 논문의 수치를 confidence 감점으로 자연스럽게 걸러낸다.

## 1. 배경

현재 `extract_metrics_from_paper`(`backend/app/agents/extraction_agent.py`)의 Gemini 프롬프트는 paper의 title + abstract와 지표 메타데이터(name, unit, extraction_hint)만 받는다. 사용자가 입력한 **원본 기술 분야(`TechQuery.category`) 및 세부 설명(`TechQuery.description`)은 IndicatorAgent에만 전달되고 추출 단계에는 누락**된다.

이로 인해 발생 가능한 false positive:
- 사용자가 "HBM 고대역폭 메모리" 입력 → 지표 "메모리 대역폭" 생성.
- 같은 키워드로 검색된 논문이 DDR5 관련일 때, Gemini는 도메인 컨텍스트를 모르므로 DDR5의 수치를 그대로 추출.
- `extraction_hint`에 도메인 단서가 풍부하면 자체 보정되지만, 약하거나 누락되면 그대로 통과.

기대 효과:
- 도메인 명백 불일치 논문의 수치에 낮은 confidence를 부여 → 기존 `validate_and_rank`의 `min_confidence_score=0.5` 필터가 자연스럽게 drop.
- 인접·비교 기술(예: HBM 컨텍스트에서 GDDR7 비교 수치)은 중간 confidence로 살아남아 보고서에서 비교 정보로 활용 가능.

비목표:
- IndicatorAgent의 지표 생성 로직 변경.
- DB schema 또는 API 응답 형식 변경.
- 임계값(min_confidence_score) 자체 변경.
- 검색 단계의 도메인 필터링 — 검색은 keyword 기반 그대로.

## 2. 사용자 결정 사항 (brainstorming 합의)

| 항목 | 선택 | 근거 |
|------|------|------|
| 컨텍스트 범위 | `category + description` | 가장 풍부한 정보. description은 사용자가 직접 작성한 자연어라 도메인 시그널이 강함 |
| 불일치 정책 | Soft: confidence 감점 | value는 유지(디버깅·관찰 가능), validate 단계의 기존 필터가 자연스럽게 drop. Strict(value=null)는 인접 비교치까지 잃을 위험 |
| 인접 기술 처리 | 비교 목적이면 중간 confidence (~0.5) | 보고서에서 SOTA 비교 컨텍스트로 활용 가능 |

## 3. 변경 사항

### 3.1 `BATCH_EXTRACTION_PROMPT` (`extraction_agent.py:13`)

프롬프트 상단에 도메인 컨텍스트 블록과 매칭 지침 1단락을 삽입한다. 기존 본문(논문 제목·초록·지표 JSON·단위 규칙·extraction_hint 규칙·응답 형식)은 그대로 유지.

새 블록:

```
연구 도메인 컨텍스트:
- 기술 분야: {category}
- 세부 설명: {description}

도메인 매칭 지침:
- 논문이 위 도메인과 명백히 다른 세부기술을 다루는 경우(예: 다른 메모리 타입,
  다른 응용 영역) 수치는 추출하되 confidence_score를 0.3 이하로 책정하세요.
- 인접 기술을 비교 목적으로 다루는 경우(예: HBM 분석 중 GDDR7 비교)는
  confidence_score를 중간(약 0.5) 책정.
- 도메인이 정확히 일치하면 평소대로 평가.
```

### 3.2 `extract_metrics_from_paper` 시그니처 확장

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

- 두 신규 인자는 모두 키워드 전용 + 기본값 `""`. Backward compatible — 호출 시 누락해도 깨지지 않으며, 빈 문자열이면 프롬프트의 컨텍스트 블록은 빈 채로 들어간다(Gemini가 무시).
- 프롬프트 포맷 호출:
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

### 3.3 `pipeline.py` `extract_node` 호출부 갱신

`backend/app/agents/pipeline.py:82` 부근의 task 생성을 다음으로 갱신:

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

`PipelineState`는 이미 `category`와 `description` 필드를 보유 — 추가 schema 변경 불필요.

### 3.4 테스트

- **기존 `test_extraction_agent.py` 갱신** (있는 경우): 프롬프트 포맷 변경으로 `BATCH_EXTRACTION_PROMPT.format(...)` 호출 인자가 늘어났음을 반영. 기존 mock 어설션이 깨지지 않게 조정.
- **신규 `test_extraction_includes_domain_context`**: `extract_metrics_from_paper(..., category="HBM", description="고대역폭 메모리")` 호출 시 Gemini로 전달되는 prompt 문자열에 두 컨텍스트가 포함되는지 검증. Gemini 호출은 mock.
- **신규 `test_extraction_works_without_category`**: 두 신규 인자 누락 시 정상 동작 (backward compat).
- `test_pipeline.py`는 변경 불요 — extract_node 자체는 `extract_metrics_from_paper`를 통과 호출하므로 mock 레벨에서 영향 없음.

## 4. 비목표·범위 외

- IndicatorAgent의 `extraction_hint` 생성 로직 변경 없음.
- `min_confidence_score` 등 validate 단계 임계값 변경 없음.
- 보고서 합성(`synthesis_agent.py`) 변경 없음.

## 5. 오류 처리

- `category` / `description`이 빈 문자열일 때: 프롬프트의 컨텍스트 블록은 그대로 비어 들어감. Gemini는 매칭 지침을 적용할 수 없으므로 사실상 기존 동작과 동일.
- `category` 또는 `description`에 중괄호(`{`, `}`) 등 `str.format` 위협 문자가 포함된 경우: 사용자 입력이 직접 들어가는 위치는 `{category}` / `{description}` placeholder에만 한정되므로 format injection 위험은 없다. `format`은 placeholder 외 텍스트를 escape하지 않지만, 사용자 입력이 format string 자체에 들어가는 것이 아니므로 안전.

## 6. 효과 측정 (선택적 follow-up)

본 spec은 효과 검증을 강제하지 않지만, 권장:
- 동일 category·description으로 2회 실행 (변경 전/후) 후 `metric_values` 테이블에서 confidence_score 분포 비교.
- 도메인 외 추출이 줄어들었는지 수동 spot check 5~10건.

## 7. 변경 표면 요약

| 파일 | 변경 |
|------|------|
| `backend/app/agents/extraction_agent.py` | `BATCH_EXTRACTION_PROMPT` 상단 블록 추가, `extract_metrics_from_paper` 시그니처 +2 인자, `format()` 호출 갱신 |
| `backend/app/agents/pipeline.py` | `extract_node`의 task 생성에 `category`/`description` 키워드 전달 |
| `backend/tests/test_extraction_agent.py` | 신규 또는 갱신 — 2개 테스트 |

DB schema·migration·API 응답 형식·프론트엔드 변경 없음.

## 8. 가정과 미해결 사항

- `description`이 매우 길거나 노이즈가 많은 경우 Gemini의 도메인 판단이 흐려질 수 있음 — 실사용 모니터링으로 추후 길이 제한 도입 여부 결정.
- "명백히 다른 세부기술"의 판단은 Gemini의 사전 지식에 의존 — 신생 기술 분야는 판단 정확도가 낮을 수 있음.
