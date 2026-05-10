import json
from google import genai
from google.genai import types
from app.config import settings

genai_client = genai.Client(api_key=settings.gemini_api_key)

EXTRACTION_PROMPT = """다음 논문 초록에서 아래 지표의 수치를 추출하세요.

논문 제목: {title}
논문 초록: {abstract}
추출 대상 지표: {indicator_name} (단위: {unit})

JSON 형식으로만 응답하세요. 수치가 없으면 null:
{{
  "value": <숫자 또는 null>,
  "unit": "<단위 또는 null>",
  "year": <연도 정수 또는 null>,
  "country": "<국가명 또는 null>",
  "confidence_score": <0.0~1.0>,
  "quote": "<근거 문장 또는 null>"
}}"""


def extract_metric_from_paper(paper: dict, indicator_name: str, unit: str) -> dict:
    prompt = EXTRACTION_PROMPT.format(
        title=paper["title"],
        abstract=paper.get("abstract", ""),
        indicator_name=indicator_name,
        unit=unit or "",
    )
    response = genai_client.models.generate_content(
        model=settings.gemini_model_complex,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        ),
    )
    text = response.text
    if not text:
        raise ValueError("Empty response from Gemini extraction")
    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON from Gemini extraction: {text[:200]}") from e
    result["paper_title"] = paper["title"]
    result["doi"] = paper.get("doi")
    result["source_url"] = f"https://doi.org/{paper['doi']}" if paper.get("doi") else None
    return result
