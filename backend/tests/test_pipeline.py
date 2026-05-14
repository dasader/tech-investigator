import pytest
from app.agents.pipeline import _concurrency_for, CONCURRENCY

pytestmark = pytest.mark.no_db


def test_concurrency_semantic_scholar_is_serial():
    assert _concurrency_for("semantic_scholar") == 1


def test_concurrency_scopus():
    assert _concurrency_for("scopus") == 5


def test_concurrency_openalex():
    assert _concurrency_for("openalex") == 10


def test_concurrency_unknown_source_falls_back_to_serial():
    assert _concurrency_for("some_future_source") == 1


def test_concurrency_dict_covers_all_known_sources():
    # CONCURRENCY 키가 search_source의 Literal 후보와 정확히 일치하는지 가드 —
    # 새 source가 스키마에 추가되면 CONCURRENCY 누락을 여기서 잡는다.
    from typing import get_args
    from app.schemas.tech_query import TechQueryCreate

    literal_sources = set(get_args(TechQueryCreate.model_fields["search_source"].annotation))
    assert set(CONCURRENCY) == literal_sources
