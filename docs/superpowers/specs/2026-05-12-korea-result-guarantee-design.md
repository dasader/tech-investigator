# 설계: 지표별 한국 결과 최소 1개 보장

**날짜:** 2026-05-12  
**대상 파일:** `backend/app/agents/validation_agent.py`

## 목표

각 지표의 최종 결과(metric_values)에 한국 결과가 가능하면 1개 이상 포함되도록 한다.

## 변경 범위

`validate_and_rank` 함수 단일 수정. 파이프라인의 다른 단계(검색·추출·합성)는 변경 없음.

## 로직

### 기존
1. `value != null AND confidence ≥ 0.5` 필터
2. `(value, confidence)` 내림차순 정렬
3. 상위 5개 반환

### 변경 후
위 1–3 단계 이후 추가:

4. top5에 `country == "South Korea"` 결과가 없고,  
   전체 추출 결과 중 `value != null`인 한국 결과가 존재하면:
   - 한국 후보를 `value × confidence` 내림차순 정렬
   - 최고 1개를 top5에 포함
     - top5가 5개 미만 → 추가 (6개까지 허용)
     - top5가 5개 → 마지막(인덱스 4) 교체

## 판별 조건

- 한국 결과: `country == "South Korea"`  
  (OpenAlex country_code `"KR"` → `_COUNTRY_CODES` 매핑값)
- 한국 후보 자격: `value != null` (confidence 기준 없음)

## 엣지 케이스

| 상황 | 처리 |
|------|------|
| 한국 결과 없음 | top5 그대로 반환 |
| 한국 결과가 이미 top5 안에 있음 | 변경 없음 |
| top5가 5개 미만 | 한국 결과 추가 (초과 허용) |
| 한국 후보 모두 value=null | 변경 없음 |

## 신뢰도 정책

- 기존 결과: confidence ≥ 0.5 유지
- 한국 보장 결과: confidence 기준 면제, value × confidence 복합 기준으로 최선 1개 선택
