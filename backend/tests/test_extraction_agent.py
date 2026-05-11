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
        result = await extract_metric_from_paper(PAPER_WITH_VALUE, "대역폭", "GB/s")
    assert result["value"] == 1228.0
    assert result["confidence_score"] >= 0.5


@pytest.mark.asyncio
async def test_returns_none_value_when_not_found():
    with patch("app.agents.extraction_agent.genai_client") as mock_client:
        mock_response = MagicMock()
        mock_response.text = '{"value": null, "unit": null, "year": null, "country": null, "confidence_score": 0.0, "quote": null}'
        mock_client.models.generate_content.return_value = mock_response
        result = await extract_metric_from_paper(PAPER_WITHOUT_VALUE, "대역폭", "GB/s")
    assert result["value"] is None
    assert result["confidence_score"] == 0.0


@pytest.mark.asyncio
async def test_skips_openalex_when_country_already_set():
    paper_with_country = {
        "title": "Scopus Paper",
        "abstract": "We present HBM3E achieving 1.2 TB/s bandwidth.",
        "year": 2024,
        "doi": "10.1109/test.2024.003",
        "citation_count": 20,
        "country": "South Korea",
    }
    with patch("app.agents.extraction_agent.genai_client") as mock_client, \
         patch("app.agents.extraction_agent._get_country_from_openalex") as mock_openalex:
        mock_response = MagicMock()
        mock_response.text = '{"value": 1228.0, "unit": "GB/s", "confidence_score": 0.9, "quote": "1.2 TB/s"}'
        mock_client.models.generate_content.return_value = mock_response

        result = await extract_metric_from_paper(paper_with_country, "대역폭", "GB/s")

    mock_openalex.assert_not_called()
    assert result["country"] == "South Korea"
