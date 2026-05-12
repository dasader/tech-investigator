import json
from google import genai
from google.genai import types
from app.config import settings
from app.utils import run_sync_with_retry, get_engine_label

genai_client = genai.Client(api_key=settings.gemini_api_key)


async def build_report_markdown(
    category: str,
    description: str,
    results_by_indicator: dict,
    analyzed_at: str,
    search_source: str = "semantic_scholar",
) -> str:
    summary_json = json.dumps(results_by_indicator, ensure_ascii=False, indent=2)
    engine_label = get_engine_label(search_source)

    prompt = f"""다음 데이터를 바탕으로 국가전략기술 Spec 조사 보고서를 마크다운으로 작성하세요.

기술 분야: {category}
세부 설명: {description}
분석 기준일: {analyzed_at}
분석 엔진: {engine_label}
조사 결과:
{summary_json}

보고서 구조:
1. 요약 (5~7문장): 조사된 각 지표에 대해 현재 글로벌 선두 국가가 어디인지를 명확히 언급하고, 해당 국가가 달성한 대표 수치를 함께 서술하세요. 국가 간 기술 격차와 주요 트렌드를 포함하세요.
2. 지표별 글로벌 최고 달성치 표 (지표 | 값 | 단위 | 연도 | 국가 | 출처)
3. 주석: "본 분석은 {analyzed_at} 기준으로 {engine_label}에서 검색된 논문 데이터를 바탕으로 합니다. 이후 발표된 연구 결과는 반영되지 않았을 수 있습니다."

JSON 형식으로 반환하세요:
{{"markdown": "<마크다운 보고서 전체>"}}"""

    response = await run_sync_with_retry(lambda: genai_client.models.generate_content(
        model=settings.gemini_model_fast,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        ),
    ))

    if not response.text:
        raise ValueError("Empty response from Gemini synthesis")

    try:
        result = json.loads(response.text)
        return result.get("markdown") or response.text
    except json.JSONDecodeError:
        return response.text
