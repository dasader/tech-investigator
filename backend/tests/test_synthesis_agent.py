import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.pipeline import synthesize_node, PipelineState
from app.agents.synthesis_agent import build_report_markdown

pytestmark = pytest.mark.no_db


def _state(validated_values: dict, indicators: list[dict]) -> PipelineState:
    return {
        "job_id": 1,
        "query_id": 1,
        "category": "반도체·디스플레이",
        "description": "ALD 공정",
        "search_source": "semantic_scholar",
        "indicators": indicators,
        "search_results": {},
        "extracted_values": {},
        "validated_values": validated_values,
        "report_markdown": "",
        "error": "",
    }


@pytest.mark.asyncio
async def test_synthesize_skips_gemini_when_no_validated_data():
    """검증 통과 데이터가 한 건도 없으면 Gemini 합성을 호출하지 않고 빈 보고서를 반환한다."""
    indicators = [{"id": 10, "name": "지표A"}, {"id": 11, "name": "지표B"}]
    state = _state({10: [], 11: []}, indicators)

    with patch("app.agents.pipeline.build_report_markdown", new=AsyncMock()) as mock_build:
        result = await synthesize_node(state, MagicMock())

    mock_build.assert_not_called()
    assert result["report_markdown"] == ""


@pytest.mark.asyncio
async def test_synthesize_calls_gemini_when_some_data_exists():
    """지표 중 하나라도 검증 데이터가 있으면 Gemini 합성을 호출한다."""
    indicators = [{"id": 10, "name": "지표A"}, {"id": 11, "name": "지표B"}]
    state = _state({10: [{"value": 105, "confidence_score": 0.8}], 11: []}, indicators)

    with patch("app.agents.pipeline.build_report_markdown",
               new=AsyncMock(return_value="# 보고서")) as mock_build:
        result = await synthesize_node(state, MagicMock())

    mock_build.assert_called_once()
    assert result["report_markdown"] == "# 보고서"


@pytest.mark.asyncio
async def test_report_prompt_forbids_inventing_data():
    """합성 프롬프트는 제공된 데이터에만 근거하고 수치/출처를 지어내지 말 것을 명시해야 한다."""
    results_by_indicator = {
        "지표A": [{"value": 105, "unit": "WPH", "year": 2025, "country": "한국"}],
        "지표B": [],
    }
    captured: dict = {}

    def fake_generate(**kwargs):
        captured["prompt"] = kwargs["contents"]
        resp = MagicMock()
        resp.text = json.dumps({"markdown": "# 보고서"})
        return resp

    with patch("app.agents.synthesis_agent.genai_client") as mock_client:
        mock_client.models.generate_content.side_effect = fake_generate
        await build_report_markdown("반도체", "설명", results_by_indicator, "2026-05-14")

    prompt = captured["prompt"]
    assert "지어내" in prompt
    assert "데이터 없음" in prompt
