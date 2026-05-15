import json
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.extraction_agent import extract_metrics_from_paper

pytestmark = pytest.mark.no_db


PAPER_WITH_VALUE = {
    "title": "HBM3E achieves record bandwidth",
    "abstract": "In this paper, we present HBM3E achieving 1,228 GB/s bandwidth with 12 stacked dies. Fabricated by SK Hynix in Korea, presented at ISSCC 2024.",
    "year": 2024,
    "doi": "10.1109/isscc.2024.001",
    "citation_count": 45,
}

PAPER_WITHOUT_VALUE = {
    "title": "Overview of memory technology",
    "abstract": "This paper provides an overview of memory technology trends without specific measurements in 2023.",
    "year": 2023,
    "doi": None,
    "citation_count": 5,
}

INDICATOR_BANDWIDTH = {"id": 1, "name": "대역폭", "unit": "GB/s"}


def _gemini_response(payload: list[dict]) -> MagicMock:
    response = MagicMock()
    response.text = json.dumps(payload)
    return response


def _client() -> AsyncMock:
    return AsyncMock(spec=httpx.AsyncClient)


@pytest.mark.asyncio
async def test_extracts_value_from_paper():
    gemini_payload = [{
        "indicator_id": 1,
        "value": 1228.0,
        "unit": "GB/s",
        "confidence_score": 0.92,
        "quote": "HBM3E achieving 1,228 GB/s bandwidth",
    }]
    with patch("app.agents.extraction_agent.genai_client") as mock_client, \
         patch("app.agents.extraction_agent._get_country_from_openalex",
               new=AsyncMock(return_value="South Korea")):
        mock_client.models.generate_content.return_value = _gemini_response(gemini_payload)
        results = await extract_metrics_from_paper(PAPER_WITH_VALUE, [INDICATOR_BANDWIDTH], client=_client())

    assert len(results) == 1
    ind_id, payload = results[0]
    assert ind_id == 1
    assert payload["value"] == 1228.0
    assert payload["unit"] == "GB/s"
    assert payload["confidence_score"] == 0.92
    assert payload["country"] == "South Korea"


@pytest.mark.asyncio
async def test_returns_empty_when_no_value_found():
    with patch("app.agents.extraction_agent.genai_client") as mock_client, \
         patch("app.agents.extraction_agent._get_country_from_openalex",
               new=AsyncMock(return_value=None)):
        mock_client.models.generate_content.return_value = _gemini_response([])
        results = await extract_metrics_from_paper(PAPER_WITHOUT_VALUE, [INDICATOR_BANDWIDTH], client=_client())

    mock_client.models.generate_content.assert_called_once()
    assert results == []


@pytest.mark.asyncio
async def test_skips_openalex_when_country_already_set():
    paper_with_country = {
        **PAPER_WITH_VALUE,
        "country": "South Korea",
    }
    gemini_payload = [{
        "indicator_id": 1,
        "value": 1228.0,
        "unit": "GB/s",
        "confidence_score": 0.9,
        "quote": "1.2 TB/s",
    }]
    with patch("app.agents.extraction_agent.genai_client") as mock_client, \
         patch("app.agents.extraction_agent._get_country_from_openalex",
               new=AsyncMock()) as mock_openalex:
        mock_client.models.generate_content.return_value = _gemini_response(gemini_payload)
        results = await extract_metrics_from_paper(paper_with_country, [INDICATOR_BANDWIDTH], client=_client())

    mock_openalex.assert_not_called()
    _, payload = results[0]
    assert payload["country"] == "South Korea"


@pytest.mark.asyncio
async def test_skips_openalex_when_country_lookup_done():
    paper_lookup_done = {
        **PAPER_WITH_VALUE,
        "country": None,
        "country_lookup_done": True,
    }
    gemini_payload = [{
        "indicator_id": 1,
        "value": 1228.0,
        "unit": "GB/s",
        "confidence_score": 0.9,
        "quote": "1.2 TB/s",
    }]
    with patch("app.agents.extraction_agent.genai_client") as mock_client, \
         patch("app.agents.extraction_agent._get_country_from_openalex",
               new=AsyncMock()) as mock_openalex:
        mock_client.models.generate_content.return_value = _gemini_response(gemini_payload)
        results = await extract_metrics_from_paper(paper_lookup_done, [INDICATOR_BANDWIDTH], client=_client())

    mock_openalex.assert_not_called()
    _, payload = results[0]
    assert payload["country"] is None


INDICATOR_WITH_HINT = {
    "id": 7,
    "name": "TSV 피치",
    "unit": "µm",
    "extraction_hint": "TSV 피치는 보통 µm 단위. HBM 컨텍스트에서 4~10 µm 범위.",
}


@pytest.mark.asyncio
async def test_extraction_prompt_includes_hint_when_present():
    """지표에 extraction_hint가 있으면 Gemini prompt에 hint 문자열이 포함된다."""
    captured_prompts: list[str] = []

    def _capture(**kwargs):
        captured_prompts.append(kwargs.get("contents", ""))
        return _gemini_response([{
            "indicator_id": 7, "value": 5.5, "unit": "µm",
            "confidence_score": 0.9, "quote": "5.5 µm pitch",
        }])

    with patch("app.agents.extraction_agent.genai_client") as mock_client, \
         patch("app.agents.extraction_agent._get_country_from_openalex",
               new=AsyncMock(return_value=None)):
        mock_client.models.generate_content.side_effect = _capture
        await extract_metrics_from_paper(PAPER_WITH_VALUE, [INDICATOR_WITH_HINT], client=_client())

    assert len(captured_prompts) == 1
    prompt = captured_prompts[0]
    assert "TSV 피치는 보통 µm 단위" in prompt
    assert "extraction_hint" in prompt


@pytest.mark.asyncio
async def test_extraction_prompt_omits_hint_when_absent():
    """extraction_hint가 None/누락이면 prompt에 hint 키가 들어가지 않는다."""
    captured_prompts: list[str] = []

    def _capture(**kwargs):
        captured_prompts.append(kwargs.get("contents", ""))
        return _gemini_response([{
            "indicator_id": 1, "value": 1228.0, "unit": "GB/s",
            "confidence_score": 0.9, "quote": "1228 GB/s",
        }])

    with patch("app.agents.extraction_agent.genai_client") as mock_client, \
         patch("app.agents.extraction_agent._get_country_from_openalex",
               new=AsyncMock(return_value=None)):
        mock_client.models.generate_content.side_effect = _capture
        await extract_metrics_from_paper(PAPER_WITH_VALUE, [INDICATOR_BANDWIDTH], client=_client())

    assert len(captured_prompts) == 1
    # The prompt template itself mentions "extraction_hint" in the instructions;
    # what matters is the serialised indicators_json does NOT carry the key.
    import re as _re
    indicators_json_match = _re.search(r'추출 대상 지표 \(JSON\):\n(\[.*?\])', captured_prompts[0], _re.DOTALL)
    assert indicators_json_match, "Could not find indicators JSON section in prompt"
    indicators_section = indicators_json_match.group(1)
    assert "extraction_hint" not in indicators_section
