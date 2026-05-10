import json
import asyncio
from google import genai
from google.genai import types
from app.config import settings

genai_client = genai.Client(api_key=settings.gemini_api_key)

INDICATOR_PROMPT = """당신은 국가전략기술 분야의 전문가입니다.
아래 기술 분야에 대해 기술 수준을 측정할 수 있는 정량 지표 5~10개를 JSON 배열로 반환하세요.

기술 분야: {category}
세부 설명: {description}

각 지표는 다음 형식으로 작성하세요:
{{
  "name": "지표명 (한글)",
  "unit": "단위 (예: GB/s, nm, %)",
  "description": "지표 설명 (1문장)",
  "search_keywords": "영어 논문 검색 키워드 (예: HBM bandwidth GB/s)"
}}

규칙:
- 반드시 측정 가능한 수치 지표만 포함 (정성 지표 제외)
- JSON 배열만 반환, 설명 텍스트 없음
- 5개 이상 10개 이하"""

async def generate_indicators(category: str, description: str) -> list[dict]:
    prompt = INDICATOR_PROMPT.format(category=category, description=description)
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: genai_client.models.generate_content(
            model=settings.gemini_model_complex,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            ),
        )
    )
    return json.loads(response.text)
