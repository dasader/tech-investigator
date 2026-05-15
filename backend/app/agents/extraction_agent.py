import asyncio
import json
import re
import httpx
from google import genai
from google.genai import types
from app.config import settings
from app.utils import run_sync_with_retry
from app.agents.country_codes import COUNTRY_CODES

genai_client = genai.Client(api_key=settings.gemini_api_key)

BATCH_EXTRACTION_PROMPT = """다음 논문 초록에서 지표 목록의 수치를 각각 추출하세요.

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

async def _get_country_from_openalex(doi: str, *, client: httpx.AsyncClient) -> str | None:
    try:
        url = f"https://api.openalex.org/works/doi:{doi}"
        headers = {"User-Agent": "TechSpec/1.0 (mailto:ilhwan.lee@gmail.com)"}
        r = await client.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        authorships = data.get("authorships") or []
        if not authorships:
            return None
        institutions = authorships[0].get("institutions") or []
        if not institutions:
            return None
        code = institutions[0].get("country_code")
        if not code:
            return None
        return COUNTRY_CODES.get(code, code)
    except Exception:
        return None


async def extract_metrics_from_paper(
    paper: dict,
    indicators: list[dict],
    semaphore: asyncio.Semaphore | None = None,
    *,
    client: httpx.AsyncClient,
) -> list[tuple[int, dict]]:
    """논문 1개에서 여러 지표를 한 번의 Gemini 호출로 추출.

    Returns: [(indicator_id, result_dict), ...]
    """
    if not indicators:
        return []

    if not re.search(r'\d', paper.get("abstract", "")):
        return []

    sem = semaphore or asyncio.Semaphore(1)
    async with sem:
        indicators_json = json.dumps(
            [
                {
                    "id": ind["id"],
                    "name": ind["name"],
                    "unit": ind.get("unit") or "",
                    **({"extraction_hint": ind["extraction_hint"]}
                       if ind.get("extraction_hint") else {}),
                }
                for ind in indicators
            ],
            ensure_ascii=False,
        )
        prompt = BATCH_EXTRACTION_PROMPT.format(
            title=paper.get("title", ""),
            abstract=paper.get("abstract", ""),
            indicators_json=indicators_json,
            n=len(indicators),
        )
        doi = paper.get("doi")

        async def _country_coro() -> str | None:
            if paper.get("country") is not None:
                return paper["country"]
            if paper.get("country_lookup_done"):
                return None
            return await _get_country_from_openalex(doi, client=client) if doi else None

        response, country = await asyncio.gather(
            run_sync_with_retry(lambda: genai_client.models.generate_content(
                model=settings.gemini_model_fast,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )),
            _country_coro(),
        )

        text = response.text
        if not text:
            raise ValueError("Empty response from Gemini batch extraction")

        try:
            parsed = json.loads(text)
            if not isinstance(parsed, list):
                parsed = [parsed]
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON from Gemini batch extraction: {text[:200]}") from e

        valid_ids = {ind["id"] for ind in indicators}
        results: list[tuple[int, dict]] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            ind_id = item.get("indicator_id")
            if ind_id is None or ind_id not in valid_ids:
                continue
            results.append((int(ind_id), {
                "value": item.get("value"),
                "unit": item.get("unit"),
                "confidence_score": item.get("confidence_score", 0.0),
                "quote": item.get("quote"),
                "paper_title": paper.get("title"),
                "journal_name": paper.get("journal_name"),
                "doi": doi,
                "source_url": f"https://doi.org/{doi}" if doi else None,
                "year": paper.get("year"),
                "country": country,
            }))

        return results
