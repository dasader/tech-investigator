import asyncio
import json
import httpx
from google import genai
from google.genai import types
from app.config import settings
from app.utils import run_sync

genai_client = genai.Client(api_key=settings.gemini_api_key)

EXTRACTION_PROMPT = """다음 논문 초록에서 아래 지표의 수치를 추출하세요.

논문 제목: {title}
논문 초록: {abstract}
추출 대상 지표: {indicator_name} (단위: {unit})

JSON 형식으로만 응답하세요. 수치가 없으면 null:
{{
  "value": <숫자 또는 null>,
  "unit": "<단위 또는 null>",
  "confidence_score": <0.0~1.0>,
  "quote": "<근거 문장 또는 null>"
}}"""

_COUNTRY_CODES: dict[str, str] = {
    "US": "USA", "CN": "China", "KR": "South Korea", "JP": "Japan",
    "DE": "Germany", "GB": "UK", "FR": "France", "CH": "Switzerland",
    "AU": "Australia", "CA": "Canada", "IN": "India", "SG": "Singapore",
    "TW": "Taiwan", "SE": "Sweden", "NL": "Netherlands", "IT": "Italy",
    "ES": "Spain", "IL": "Israel", "DK": "Denmark", "FI": "Finland",
    "BE": "Belgium", "AT": "Austria", "NO": "Norway", "NZ": "New Zealand",
    "BR": "Brazil", "RU": "Russia", "SA": "Saudi Arabia", "AE": "UAE",
    "MY": "Malaysia", "TH": "Thailand", "ID": "Indonesia", "VN": "Vietnam",
    "PL": "Poland", "CZ": "Czech Republic", "HU": "Hungary", "PT": "Portugal",
    "IR": "Iran", "TR": "Turkey", "EG": "Egypt", "ZA": "South Africa",
    "MX": "Mexico", "AR": "Argentina", "CL": "Chile", "CO": "Colombia",
    "PK": "Pakistan", "BD": "Bangladesh", "NG": "Nigeria", "KE": "Kenya",
}


async def _get_country_from_openalex(doi: str) -> str | None:
    try:
        url = f"https://api.openalex.org/works/doi:{doi}"
        headers = {"User-Agent": "TechSpec/1.0 (mailto:ilhwan.lee@gmail.com)"}
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, headers=headers)
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
        return _COUNTRY_CODES.get(code, code)
    except Exception:
        return None


async def extract_metric_from_paper(
    paper: dict,
    indicator_name: str,
    unit: str,
    semaphore: asyncio.Semaphore | None = None,
) -> dict:
    sem = semaphore or asyncio.Semaphore(1)
    async with sem:
        prompt = EXTRACTION_PROMPT.format(
            title=paper["title"],
            abstract=paper.get("abstract", ""),
            indicator_name=indicator_name,
            unit=unit or "",
        )
        doi = paper.get("doi")

        async def _country_coro() -> str | None:
            return await _get_country_from_openalex(doi) if doi else None

        response, country = await asyncio.gather(
            run_sync(lambda: genai_client.models.generate_content(
                model=settings.gemini_model_complex,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                ),
            )),
            _country_coro(),
        )

        text = response.text
        if not text:
            raise ValueError("Empty response from Gemini extraction")
        try:
            result = json.loads(text)
            if isinstance(result, list):
                result = result[0] if result else {}
            if not isinstance(result, dict):
                result = {}
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON from Gemini extraction: {text[:200]}") from e

        result["paper_title"] = paper["title"]
        result["doi"] = doi
        result["source_url"] = f"https://doi.org/{doi}" if doi else None
        result["year"] = paper.get("year")
        result["country"] = country
        return result
