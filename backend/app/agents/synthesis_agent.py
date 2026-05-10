import json
from google import genai
from app.config import settings

genai_client = genai.Client(api_key=settings.gemini_api_key)


def build_report_markdown(
    category: str,
    description: str,
    results_by_indicator: dict,
    analyzed_at: str
) -> str:
    """
    Build a tech spec investigation report in Korean using Gemini synthesis.

    Args:
        category: Technology category/field
        description: Detailed description of the technology
        results_by_indicator: Dictionary mapping indicator names to their top results
        analyzed_at: Analysis date in ISO format

    Returns:
        Markdown-formatted report as string

    Raises:
        ValueError: If Gemini response is empty
    """
    summary_json = json.dumps(results_by_indicator, ensure_ascii=False, indent=2)

    prompt = f"""다음 데이터를 바탕으로 국가전략기술 Spec 조사 보고서를 마크다운으로 작성하세요.

기술 분야: {category}
세부 설명: {description}
분석 기준일: {analyzed_at}
조사 결과:
{summary_json}

보고서 구조:
1. 분석 기준일: {analyzed_at} (첫 줄에 명시)
2. 요약 (3문장)
3. 지표별 글로벌 최고 달성치 표 (지표 | 값 | 단위 | 연도 | 국가 | 출처)
4. 시사점 (2~3문장)
5. 주석: "본 분석은 {analyzed_at} 기준으로 검색된 논문 데이터를 바탕으로 합니다. 이후 발표된 연구 결과는 반영되지 않았을 수 있습니다."

마크다운만 반환, 코드블록 없음."""

    response = genai_client.models.generate_content(
        model=settings.gemini_model_fast,
        contents=prompt,
    )

    if not response.text:
        raise ValueError("Empty response from Gemini synthesis")

    return response.text
