import pytest
from app.agents.pipeline import SOURCE_PLAN

pytestmark = pytest.mark.no_db


def test_source_plan_combined():
    assert SOURCE_PLAN["combined"] == {"semantic_scholar": 1, "openalex": 10}


def test_source_plan_scopus():
    assert SOURCE_PLAN["scopus"] == {"scopus": 5}


def test_source_plan_keys_match_schema_literal():
    # SOURCE_PLAN 키가 search_source의 Literal 후보와 정확히 일치하는지 가드 —
    # 스키마에 source가 추가/제거되면 SOURCE_PLAN 불일치를 여기서 잡는다.
    from typing import get_args
    from app.schemas.tech_query import TechQueryCreate

    literal_sources = set(get_args(TechQueryCreate.model_fields["search_source"].annotation))
    assert set(SOURCE_PLAN) == literal_sources
