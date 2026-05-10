import json
import pytest
from unittest.mock import patch, MagicMock
from app.agents.indicator_agent import generate_indicators

MOCK_RESPONSE = [
    {"name": "대역폭", "unit": "GB/s", "description": "메모리 초당 전송 데이터량", "search_keywords": "HBM bandwidth GB/s"},
    {"name": "적층 다이 수", "unit": "개", "description": "수직 적층된 DRAM 다이 수", "search_keywords": "HBM stacked dies count"},
]

@pytest.mark.asyncio
async def test_generate_indicators_returns_list():
    with patch("app.agents.indicator_agent.genai_client") as mock_client:
        mock_response = MagicMock()
        mock_response.text = '[{"name":"대역폭","unit":"GB/s","description":"메모리 초당 전송 데이터량","search_keywords":"HBM bandwidth GB/s"},{"name":"적층 다이 수","unit":"개","description":"수직 적층된 DRAM 다이 수","search_keywords":"HBM stacked dies count"}]'
        mock_client.models.generate_content.return_value = mock_response
        result = await generate_indicators("반도체", "HBM 고대역폭 메모리 적층 기술")
    assert isinstance(result, list)
    assert len(result) >= 1
    assert "name" in result[0]
    assert "unit" in result[0]

@pytest.mark.asyncio
async def test_generate_indicators_returns_at_least_5():
    with patch("app.agents.indicator_agent.genai_client") as mock_client:
        items = [{"name": f"지표{i}", "unit": "unit", "description": "desc", "search_keywords": "kw"} for i in range(7)]
        mock_response = MagicMock()
        mock_response.text = json.dumps(items)
        mock_client.models.generate_content.return_value = mock_response
        result = await generate_indicators("반도체", "HBM 기술")
    assert len(result) >= 5

@pytest.mark.asyncio
async def test_empty_response_raises():
    with patch("app.agents.indicator_agent.genai_client") as mock_client:
        mock_response = MagicMock()
        mock_response.text = ""
        mock_client.models.generate_content.return_value = mock_response
        with pytest.raises(ValueError, match="Empty response"):
            await generate_indicators("반도체", "HBM")

@pytest.mark.asyncio
async def test_invalid_json_raises():
    with patch("app.agents.indicator_agent.genai_client") as mock_client:
        mock_response = MagicMock()
        mock_response.text = "not valid json {{{"
        mock_client.models.generate_content.return_value = mock_response
        with pytest.raises(ValueError, match="Invalid JSON"):
            await generate_indicators("반도체", "HBM")
