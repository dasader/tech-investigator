# 스펙 B — 키워드 프롬프트 개선 + 추출 힌트 분리 (2026-05-15)

검색 수율 개선의 두 번째 사이클. `indicator_agent`의 `INDICATOR_PROMPT`를 강화해 `search_keywords`를 넓게 생성하고, 추출 정확도를 높이기 위한 별도 자연어 단서 필드 `extraction_hint`를 추가한다.

스펙 A(멀티소스 통합 검색)는 검색을 두 소스로 확장해 수율을 높였지만, 키워드 자체가 좁으면 두 소스 모두 결과가 적게 잡힌다(Job 29 ALD 케이스). 본 스펙은 키워드 자체의 폭과 추출 단계의 정확도를 함께 개선한다.

---

## 0. 결정 요약

| 결정 사항 | 값 | 근거 |
|---|---|---|
| 키워드 다양화 방식 | 단일 `search_keywords` 필드 + Gemini가 OR 표현 내장 | 단일 검색 호출 유지, 구현 가장 간단 |
| extraction_hint 형태 | 자연어 1~2문장 단서 | Gemini가 자연어 prompt로 처리하므로 LLM 친화적 |
| 두 부분 묶음 | 한 사이클 통합 | `INDICATOR_PROMPT` 한 번의 호출에 둘 다 생성 — 의존성 적음 |
| 신규 컬럼 | `indicators.extraction_hint VARCHAR(500) NULL` | 별도 필드로 의미·책임 분리; `description`(사용자용 1문장)과 구분 |
| 마이그레이션 | 컬럼 추가만, 기존 행 백필 없음 | 기존 잡은 재실행되지 않음, 백필 가치 적음 |
| 프론트엔드 | 노출 안 함 | 사용자 워크플로(이름·단위만 편집)에 인지 부담 추가 안 함 |
| 라우터 | `routers/indicators.py`가 Gemini 반환 dict에서 `extraction_hint` 추가 추출 | 기존 `search_keywords` 추출 패턴과 일관 |
| 커밋 단위 | 단일 commit (백엔드 + 마이그레이션 + 테스트) | 한 기능의 일관된 변경 |

---

## 1. `INDICATOR_PROMPT` 강화 (`indicator_agent.py`)

### 1.1 `search_keywords` 가이드 확장

현재 `INDICATOR_PROMPT`의 검색 키워드 가이드는 `"영어 논문 검색 키워드 (예: HBM bandwidth GB/s)"` 한 줄뿐. 다음으로 확장:

```
search_keywords 작성 규칙:
- 따옴표 구문검색("...")을 사용하지 마세요 — 결과가 과도하게 좁아집니다.
- 핵심 용어 2~3개로 제한하세요. "300mm" 같은 과도한 한정어, 특정 모델명·세대명은 배제하세요.
- 약어와 정식 명칭을 OR로 함께 포함하세요.

좋은 예: "WIWNU OR within-wafer non-uniformity"
나쁜 예: "\"spatial ALD\" throughput WPH 300mm"
```

### 1.2 신규 `extraction_hint` 필드 생성

`INDICATOR_PROMPT`가 반환하는 각 지표 JSON에 신규 필드:

```
extraction_hint 작성 규칙:
- 1~2문장의 자연어 단서.
- 이 지표가 논문에서 보통 어떤 형태로 보고되는지 명시.
- 헷갈리기 쉬운 단위 변형(예: GB/s vs TB/s, µm vs nm)이나 혼동 가능 개념을 언급.
- 합리적 수치 범위가 있다면 간단히 (예: "HBM 컨텍스트에서 보통 4~10 µm 범위").

예: "TSV 피치는 보통 µm 단위. HBM 컨텍스트에서는 4~10 µm 범위. 마이크로범프 피치(bump pitch)와 혼동 주의."
```

### 1.3 출력 JSON 스키마 (변경 후)

```json
{
  "name": "지표명 (한글)",
  "unit": "단위 (예: GB/s, nm, %)",
  "description": "지표 설명 (1문장)",
  "search_keywords": "넓은 OR 표현 영어 키워드",
  "extraction_hint": "1~2문장 추출 단서"
}
```

`description`은 기존 의미(사용자 노출용 1문장 정의) 유지.

---

## 2. `BATCH_EXTRACTION_PROMPT` 변경 (`extraction_agent.py`)

### 2.1 `indicators_json` 변경

현재 `extract_metrics_from_paper`가 `indicators_json`을 만들 때:

```python
indicators_json = json.dumps(
    [{"id": ind["id"], "name": ind["name"], "unit": ind.get("unit") or ""} for ind in indicators],
    ensure_ascii=False,
)
```

다음으로 확장 (hint가 있을 때만 포함):

```python
indicators_json = json.dumps(
    [
        {
            "id": ind["id"],
            "name": ind["name"],
            "unit": ind.get("unit") or "",
            **({"extraction_hint": ind["extraction_hint"]} if ind.get("extraction_hint") else {}),
        }
        for ind in indicators
    ],
    ensure_ascii=False,
)
```

### 2.2 프롬프트 본문 추가 섹션

`BATCH_EXTRACTION_PROMPT`의 단위 처리 규칙 다음에 짧은 섹션 추가:

```
추출 힌트 활용:
- 지표에 extraction_hint가 있으면 해당 단서를 참고해 정확히 매칭하세요.
- 단서는 단위 변형·혼동 가능 개념·합리적 범위에 대한 가이드입니다.
- 단서가 없으면 무시하고 진행하세요.
```

### 2.3 회귀 가드

기존 indicator 행은 `extraction_hint=NULL`. dict-merge 패턴(`**({"extraction_hint": ...} if ...)`)이 None/빈 문자열을 자연스럽게 무시하므로 회귀 없음.

---

## 3. 데이터 모델 / 스키마 / 마이그레이션

### 3.1 `models/indicator.py`

한 줄 추가:

```python
extraction_hint = Column(String(500), nullable=True)
```

### 3.2 `schemas/indicator.py`

`IndicatorBase`, `IndicatorOut`, `IndicatorUpdate` 셋 모두에 추가:

```python
extraction_hint: Optional[str] = None
```

`IndicatorOut`에 노출되지만 프론트엔드는 무시(UI 미사용).

### 3.3 Alembic 마이그레이션 (신규 revision)

- **upgrade**: `op.add_column("indicators", sa.Column("extraction_hint", sa.String(length=500), nullable=True))`
- **downgrade**: `op.drop_column("indicators", "extraction_hint")`
- 기존 행 백필 없음 — 모두 NULL 유지.

---

## 4. 라우터 / 파이프라인 통합

### 4.1 `routers/indicators.py:18-28`

`generate_indicator_draft`가 Gemini 반환 dict에서 `extraction_hint`도 추출:

```python
ind = Indicator(
    query_id=query_id,
    name=d["name"],
    unit=d.get("unit"),
    description=d.get("description"),
    search_keywords=d.get("search_keywords"),
    extraction_hint=d.get("extraction_hint"),
)
```

### 4.2 `pipeline.py:158-160`

`run_pipeline`이 indicators를 dict 리스트로 변환할 때 `extraction_hint` 한 항목 추가:

```python
{
    "id": i.id,
    "name": i.name,
    "unit": i.unit,
    "search_keywords": i.search_keywords,
    "extraction_hint": i.extraction_hint,
}
```

`extract_node`는 이 dict를 그대로 `extract_metrics_from_paper`에 전달하므로 자동 흐름.

---

## 5. 테스트

### 5.1 `test_indicator_agent.py` 추가

| # | 검증 |
|---|------|
| 1 | Gemini mock 응답에 `extraction_hint` 포함 → 정상 파싱 후 dict에 포함 |
| 2 | Gemini가 `extraction_hint` 누락(legacy) → `KeyError` 없이 정상 동작 |
| 3 | `INDICATOR_PROMPT`에 "따옴표", "OR", "extraction_hint" 핵심 문구 포함 (프롬프트 의도 가드) |

### 5.2 `test_extraction_agent.py` 추가

| # | 검증 |
|---|------|
| 1 | `indicators`에 `extraction_hint` 있을 때 Gemini에 전달된 prompt에 hint 문자열 포함 (prompt 캡처) |
| 2 | `extraction_hint` None/누락일 때도 정상 추출, prompt에 hint 키 미포함 |

`test_synthesis_agent.py`의 prompt 캡처 패턴 재사용 — `side_effect`로 contents 캡처 후 문자열 검사.

### 5.3 회귀 확인

- `test_pipeline_task.py`: search/extract 단계가 mock되므로 영향 없음
- `test_combined_search.py`: search_agent 한정, 영향 없음
- `test_pipeline.py`: SOURCE_PLAN 중심, 영향 없음

---

## 6. 커밋 / 검증

### 단일 commit

`feat(indicators): broaden search keywords + add extraction_hint`

변경 파일:
- `backend/app/agents/indicator_agent.py` (INDICATOR_PROMPT 강화)
- `backend/app/agents/extraction_agent.py` (BATCH_EXTRACTION_PROMPT + indicators_json)
- `backend/app/agents/pipeline.py` (run_pipeline indicators dict)
- `backend/app/models/indicator.py` (extraction_hint 컬럼)
- `backend/app/schemas/indicator.py` (extraction_hint 필드)
- `backend/app/routers/indicators.py` (Gemini dict 추출)
- `backend/alembic/versions/<revision>.py` (신규 마이그레이션)
- `backend/tests/test_indicator_agent.py` (3건)
- `backend/tests/test_extraction_agent.py` (2건)

### 검증 명령

```bash
docker compose exec api alembic upgrade head        # 마이그레이션 적용
docker compose exec api pytest tests/ -v            # 전체 통과 (스펙 A 기준선 57 + 신규 5 ≈ 62)
```

### 위험 요소 및 완화

| 위험 | 완화 |
|------|------|
| Gemini가 `extraction_hint` 누락·빈 값 반환 | 라우터의 `d.get(...)` None 허용; extraction_agent가 None/빈 hint 무시 |
| 키워드가 넓어져 결과가 너무 많아 추출 Gemini 비용 증가 | `extract_node`가 `[:max_papers_per_indicator]`(30)로 절단 — 비용 상한 동일 |
| Gemini가 여전히 따옴표 포함 키워드 생성 | good/bad 예시 페어로 일관성 확보; 후처리 strip은 안 함 (LLM 출력 신뢰) |
| 기존 indicator 행 `extraction_hint=NULL` 케이스 | dict-merge 패턴(`**({"extraction_hint": ...} if ...)`)이 자연 무시 |
| 스키마 마이그레이션 downgrade 시 `extraction_hint` 데이터 손실 | 데이터 메타성격(LLM 단서)이라 영구 보존 의무 없음. 마이그레이션 docstring에 명시 |

---

## 7. Scope 제외 (YAGNI / 별도 사이클)

- **기존 indicator 행 백필** — 가치 대비 비용 비대칭. 기존 잡은 재실행되지 않음.
- **프론트엔드 노출/편집 UI** — 사용자 워크플로(이름·단위만)에 인지 부담 추가 안 함.
- **단계적 검색 폴백** (0건일 때 토큰 줄여 재시도) — 별도 후속 사이클.
- **지표당 복수 쿼리 검색** (메인 + 대안 별도 검색 후 dedup) — 별도 후속 사이클.
- **`SearchSource` Literal 다중 파일 import 확산** (스펙 A simplify에서 미룬 follow-up) — 무관.

---

## 8. 후속 작업

본 스펙 완료 후 검색 수율 개선 사이클은 일단 마무리. 향후 후속 후보:
- **단계적 검색 폴백**: 좁은 쿼리 → 결과 N건 미만이면 토큰 빼고 재시도
- **결과 페이지 UI 개선**: 보고서·데이터 탭 차트, 비교 시각화
- **Scopus 활용** (유료 구독 시점)
