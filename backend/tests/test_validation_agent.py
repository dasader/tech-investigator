from app.agents.validation_agent import validate_and_rank


def test_returns_top3_by_value():
    extractions = [
        {"value": 1228.0, "unit": "GB/s", "year": 2024, "country": "Korea", "confidence_score": 0.9, "paper_title": "A", "doi": None, "source_url": None, "quote": "q1"},
        {"value": 819.0, "unit": "GB/s", "year": 2022, "country": "USA", "confidence_score": 0.85, "paper_title": "B", "doi": None, "source_url": None, "quote": "q2"},
        {"value": 460.0, "unit": "GB/s", "year": 2020, "country": "Japan", "confidence_score": 0.8, "paper_title": "C", "doi": None, "source_url": None, "quote": "q3"},
        {"value": None, "unit": None, "year": None, "country": None, "confidence_score": 0.0, "paper_title": "D", "doi": None, "source_url": None, "quote": None},
    ]
    result = validate_and_rank(extractions, min_confidence=0.5)
    assert len(result) <= 3
    assert result[0]["value"] == 1228.0
    assert all(r["value"] is not None for r in result)


def test_filters_low_confidence():
    extractions = [
        {"value": 100.0, "unit": "GB/s", "year": 2024, "country": "USA", "confidence_score": 0.3, "paper_title": "A", "doi": None, "source_url": None, "quote": None},
        {"value": 200.0, "unit": "GB/s", "year": 2024, "country": "Korea", "confidence_score": 0.8, "paper_title": "B", "doi": None, "source_url": None, "quote": None},
    ]
    result = validate_and_rank(extractions, min_confidence=0.5)
    assert len(result) == 1
    assert result[0]["value"] == 200.0
