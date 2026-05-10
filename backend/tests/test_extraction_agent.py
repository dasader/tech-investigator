import pytest
from unittest.mock import patch, MagicMock
from app.agents.extraction_agent import extract_metric_from_paper

PAPER_WITH_VALUE = {
    "title": "HBM3E achieves record bandwidth",
    "abstract": "In this paper, we present HBM3E achieving 1,228 GB/s bandwidth with 12 stacked dies. The device was fabricated by SK Hynix in Korea and presented at ISSCC 2024.",
    "year": 2024,
    "doi": "10.1109/isscc.2024.001",
    "citation_count": 45,
}

PAPER_WITHOUT_VALUE = {
    "title": "Overview of memory technology",
    "abstract": "This paper provides an overview of memory technology trends without specific measurements.",
    "year": 2023,
    "doi": None,
    "citation_count": 5,
}


@pytest.mark.asyncio
async def test_extracts_value_from_paper():
    with patch("app.agents.extraction_agent.genai_client") as mock_client:
        mock_response = MagicMock()
        mock_response.text = '{"value": 1228.0, "unit": "GB/s", "year": 2024, "country": "Korea", "confidence_score": 0.92, "quote": "HBM3E achieving 1,228 GB/s bandwidth"}'
        mock_client.models.generate_content.return_value = mock_response
        result = extract_metric_from_paper(PAPER_WITH_VALUE, "대역폭", "GB/s")
    assert result["value"] == 1228.0
    assert result["confidence_score"] >= 0.5


@pytest.mark.asyncio
async def test_returns_none_value_when_not_found():
    with patch("app.agents.extraction_agent.genai_client") as mock_client:
        mock_response = MagicMock()
        mock_response.text = '{"value": null, "unit": null, "year": null, "country": null, "confidence_score": 0.0, "quote": null}'
        mock_client.models.generate_content.return_value = mock_response
        result = extract_metric_from_paper(PAPER_WITHOUT_VALUE, "대역폭", "GB/s")
    assert result["value"] is None
    assert result["confidence_score"] == 0.0
