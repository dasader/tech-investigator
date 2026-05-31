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
    search_source: str = "combined",
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

데이터 사용 원칙 (반드시 준수):
- 위 "조사 결과" JSON에 실제로 존재하는 값만 사용하세요. 수치·단위·연도·국가·출처를 절대 지어내지 마세요.
- 사전 지식이나 일반 상식으로 빈칸을 채우지 마세요. JSON에 없는 정보는 보고서에도 없어야 합니다.
- 값 배열이 비어 있는 지표는 표에서 값·단위·연도·국가·출처를 모두 "데이터 없음"으로 표기하고, 요약에서는 해당 지표를 추측해서 서술하지 마세요.
- 요약은 실제 데이터가 있는 지표만 근거로 작성하세요.

보고서 구조:
1. 요약 (5~7문장): 데이터가 있는 각 지표에 대해 현재 글로벌 선두 국가가 어디인지를 명확히 언급하고, 해당 국가가 달성한 대표 수치를 함께 서술하세요. 국가 간 기술 격차와 주요 트렌드를 포함하세요.
2. 지표별 글로벌 최고 달성치 표 (지표 | 값 | 단위 | 연도 | 국가 | 출처)
3. 주석: "본 분석은 {analyzed_at} 기준으로 {engine_label}에서 검색된 논문 데이터를 바탕으로 합니다. 이후 발표된 연구 결과는 반영되지 않았을 수 있습니다."

JSON 형식으로 반환하세요:
{{"markdown": "<마크다운 보고서 전체>"}}"""

    response = await run_sync_with_retry(lambda: genai_client.models.generate_content(
        model=settings.gemini_model_fast,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.HIGH),
        ),
    ))

    if not response.text:
        raise ValueError("Empty response from Gemini synthesis")

    try:
        result = json.loads(response.text)
        return result.get("markdown") or response.text
    except json.JSONDecodeError:
        return response.text
