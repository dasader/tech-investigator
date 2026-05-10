from unittest.mock import patch, MagicMock, AsyncMock

MOCK_INDICATORS = [
    {"name": "대역폭", "unit": "GB/s", "description": "메모리 대역폭", "search_keywords": "HBM bandwidth"},
]
MOCK_PAPERS = [
    {"paper_id": "abc", "title": "HBM3E test", "abstract": "achieves 1228 GB/s in Korea 2024", "year": 2024, "citation_count": 10, "doi": "10.1109/test"},
]
MOCK_EXTRACTION = {
    "value": 1228.0,
    "unit": "GB/s",
    "year": 2024,
    "country": "Korea",
    "confidence_score": 0.9,
    "paper_title": "HBM3E test",
    "doi": "10.1109/test",
    "source_url": None,
    "quote": "achieves 1228 GB/s",
}


def test_full_flow(client):
    with patch("app.agents.indicator_agent.generate_indicators", new=AsyncMock(return_value=MOCK_INDICATORS)), \
         patch("app.agents.search_agent.search_all_sources", new=AsyncMock(return_value=MOCK_PAPERS)), \
         patch("app.agents.extraction_agent.extract_metric_from_paper", return_value=MOCK_EXTRACTION), \
         patch("app.agents.synthesis_agent.build_report_markdown", return_value="# 리포트"):

        res = client.post("/tech-input", json={"category": "반도체", "description": "HBM 기술"})
        assert res.status_code == 200
        query_id = res.json()["id"]

        res = client.post(f"/queries/{query_id}/indicators/generate")
        assert res.status_code == 200
        indicators = res.json()
        assert len(indicators) >= 1
        indicator_id = indicators[0]["id"]

        res = client.put(f"/indicators/{indicator_id}", json={"confirmed_by_user": True})
        assert res.status_code == 200

        with patch("app.routers.jobs.run_pipeline_task") as mock_task:
            mock_task.delay = MagicMock()
            res = client.post(f"/queries/{query_id}/jobs")
            assert res.status_code == 200
            job_data = res.json()
            assert job_data["status"] == "pending"
            assert "id" in job_data
