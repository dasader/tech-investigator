import pytest
from app.agents.search_agent import merge_papers

pytestmark = pytest.mark.no_db


def _s2(doi=None, title="", abstract="", year=None, citation=0, journal=None):
    return {
        "paper_id": "s2-id", "title": title, "abstract": abstract, "year": year,
        "citation_count": citation, "doi": doi, "journal_name": journal, "country": None,
    }


def _oa(doi=None, title="", abstract="", year=None, citation=0, journal=None, country=None):
    return {
        "paper_id": "oa-id", "title": title, "abstract": abstract, "year": year,
        "citation_count": citation, "doi": doi, "journal_name": journal, "country": country,
        "country_lookup_done": True,
    }


def test_same_doi_merges_field_level_best_of():
    s2 = _s2(doi="10.1/X", title="A", abstract="short", year=2024, citation=5)
    oa = _oa(doi="10.1/x", title="A", abstract="a much longer abstract", year=2024,
             citation=12, journal="Nature", country="South Korea")
    result = merge_papers([s2], [oa])
    assert len(result) == 1
    m = result[0]
    assert m["abstract"] == "a much longer abstract"   # 더 긴 abstract
    assert m["country"] == "South Korea"               # OpenAlex country
    assert m["country_lookup_done"] is True            # OpenAlex 기여 → 전파
    assert m["citation_count"] == 12                   # max
    assert m["journal_name"] == "Nature"               # non-null 우선


def test_dedup_by_title_when_no_doi():
    s2 = _s2(doi=None, title="Same Title", abstract="x", citation=1)
    oa = _oa(doi=None, title="same title", abstract="y", citation=2)
    result = merge_papers([s2], [oa])
    assert len(result) == 1


def test_papers_without_doi_or_title_are_kept():
    s2 = _s2(doi=None, title="", abstract="x")
    oa = _oa(doi=None, title="", abstract="y")
    result = merge_papers([s2], [oa])
    assert len(result) == 2


def test_disjoint_papers_all_kept():
    s2 = _s2(doi="10.1/a", title="A")
    oa = _oa(doi="10.1/b", title="B")
    result = merge_papers([s2], [oa])
    assert len(result) == 2


def test_result_sorted_by_citation_desc():
    low = _s2(doi="10.1/low", title="low", citation=3)
    high = _oa(doi="10.1/high", title="high", citation=99)
    result = merge_papers([low], [high])
    assert [p["citation_count"] for p in result] == [99, 3]
