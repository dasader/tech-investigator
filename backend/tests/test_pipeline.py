import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.orm import Session
from app.agents.pipeline import SOURCE_PLAN, extract_node

pytestmark = pytest.mark.no_db


def test_source_plan_combined():
    assert SOURCE_PLAN["combined"] == {"semantic_scholar": 1, "openalex": 10, "kci": 3}


def test_source_plan_scopus():
    assert SOURCE_PLAN["scopus"] == {"scopus": 5}


def test_source_plan_keys_match_schema_literal():
    # SOURCE_PLAN 키가 search_source의 Literal 후보와 정확히 일치하는지 가드 —
    # 스키마에 source가 추가/제거되면 SOURCE_PLAN 불일치를 여기서 잡는다.
    from typing import get_args
    from app.schemas.tech_query import TechQueryCreate

    literal_sources = set(get_args(TechQueryCreate.model_fields["search_source"].annotation))
    assert set(SOURCE_PLAN) == literal_sources


@pytest.mark.asyncio
async def test_extract_node_passes_domain_context_to_extractor():
    """extract_node가 state의 category/description을 extract_metrics_from_paper에 전달한다."""
    captured: dict = {}

    async def fake_extract(paper, indicators, semaphore, *, client, category="", description=""):
        captured["category"] = category
        captured["description"] = description
        return []  # 빈 결과로 충분

    state = {
        "job_id": 1,
        "query_id": 1,
        "category": "HBM 고대역폭 메모리",
        "description": "이형접합 기판 기반의 적층 기술",
        "search_source": "combined",
        "indicators": [{"id": 1, "name": "대역폭", "unit": "GB/s",
                        "search_keywords": "HBM", "extraction_hint": None}],
        "search_results": {1: [{"title": "T", "abstract": "1000 GB/s", "doi": "10.1/x"}]},
        "extracted_values": {},
        "validated_values": {},
        "report_markdown": "",
        "error": "",
    }
    db = MagicMock(spec=Session)
    db.query.return_value.filter.return_value.first.return_value = MagicMock(progress_pct=0.0, current_step="")
    client = AsyncMock(spec=httpx.AsyncClient)

    with patch("app.agents.pipeline.extract_metrics_from_paper", new=fake_extract):
        await extract_node(state, db, client)

    assert captured["category"] == "HBM 고대역폭 메모리"
    assert captured["description"] == "이형접합 기판 기반의 적층 기술"
