# 논문 국가 정보 추출 방향 검토

지표 수치와 함께 표시할 논문 출신 국가를 어떻게 결정할 것인지에 대한 방향별 비교.

## 현황 (2026-05-11 기준 적용 방식)

**①번 적용 중**: Semantic Scholar `authors` 필드에서 제1저자 소속(affiliation)을 받아 Gemini가 국가명으로 파싱.

- `search_agent.py`: `SS_FIELDS`에 `authors` 추가
- `extraction_agent.py`: `_first_author_affiliation()` 헬퍼로 제1저자 affiliation 문자열 추출 → 프롬프트에 포함 → Gemini가 영문 국가명 반환
- 한계: Semantic Scholar의 affiliations 데이터 완성도가 낮아 빈 배열(`[]`)인 경우 많음. 이 경우 null로 저장.

---

## 방향별 비교

### ① 제1저자 국가 — **현재 적용**

| 항목 | 내용 |
|------|------|
| 데이터 소스 | Semantic Scholar `authors[0].affiliations` |
| 구현 난이도 | 낮음 |
| 데이터 커버리지 | 낮음 (많은 논문에서 affiliations가 빈 값) |
| 정확도 | 높음 (데이터 있을 때) |
| 추가 API 호출 | 없음 |

**적합한 경우**: 빠른 구현이 우선이고, null 허용 가능한 경우.

---

### ② 교신저자 국가 (CrossRef API)

| 항목 | 내용 |
|------|------|
| 데이터 소스 | CrossRef API (`https://api.crossref.org/works/{DOI}`) — `author[].affiliation` |
| 구현 난이도 | 중간 |
| 데이터 커버리지 | 중간~높음 (DOI 있는 논문은 대부분 커버) |
| 정확도 | 높음 |
| 추가 API 호출 | DOI당 1회 (rate limit: 50 req/s, polite pool 권장) |

**구현 예시**:
```python
import httpx

async def get_crossref_affiliation(doi: str) -> str | None:
    url = f"https://api.crossref.org/works/{doi}"
    headers = {"User-Agent": "TechSpec/1.0 (mailto:your@email.com)"}
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=headers)
        if r.status_code != 200:
            return None
    data = r.json().get("message", {})
    authors = data.get("author", [])
    # 교신저자 우선, 없으면 제1저자
    corresponding = next((a for a in authors if a.get("sequence") == "first"), None)
    if corresponding:
        affs = corresponding.get("affiliation", [])
        return affs[0].get("name") if affs else None
    return None
```

**주의사항**:
- DOI 없는 논문(arXiv 전용 등)은 커버 불가 → ①번 fallback 필요
- Polite Pool 사용을 위해 `User-Agent`에 연락처 이메일 포함 권장

**적합한 경우**: DOI 보유율이 높고 정확한 교신저자 국가가 필요한 경우.

---

### ③ Gemini 추론 (소속 없이 제목/초록만으로)

| 항목 | 내용 |
|------|------|
| 데이터 소스 | 논문 제목 + 초록 텍스트 |
| 구현 난이도 | 낮음 |
| 데이터 커버리지 | 낮음 (초록에 소속 기관명이 언급되는 경우만) |
| 정확도 | 낮음~중간 (환각 위험 있음) |
| 추가 API 호출 | 없음 (이미 Gemini 호출 중) |

**적합한 경우**: 빠른 구현이 목적이고 정확도 요건이 낮은 경우. 현재 ①번에서 affiliation이 없을 때 fallback으로 사용 가능.

---

### ④ 다수 국가 표시 (공동연구 반영)

| 항목 | 내용 |
|------|------|
| 데이터 소스 | 전체 저자 affiliations (①, ② 방식 기반) |
| 구현 난이도 | 중간 |
| 데이터 커버리지 | ①, ② 방식에 의존 |
| 정확도 | 높음 |
| UI 영향 | 국가 컬럼이 "USA, South Korea, Japan" 식으로 길어짐 |

**구현 방향**:
- 전체 저자 affiliations를 수집 → 중복 제거 → 최대 3개 국가만 표시
- 국제 공동연구가 많은 분야(반도체, AI 등)에서 유용

**적합한 경우**: 공동연구 현황도 함께 파악하고 싶은 경우. 보고서보다 데이터 분석 용도.

---

## 우선순위 체계 (권장)

현재 ①번만 적용 중. 커버리지를 높이려면 다음 fallback 체계 적용을 권장:

```
Semantic Scholar affiliations (①)
  → 없으면 CrossRef affiliation (②)
    → 없으면 null
```

이 체계를 적용하면 국가 커버리지가 크게 개선됨.

## 관련 파일

- `backend/app/agents/search_agent.py` — SS API 필드 설정
- `backend/app/agents/extraction_agent.py` — affiliation 파싱 및 국가 추출 로직
