from app.config import settings


def validate_and_rank(extractions: list[dict], min_confidence: float | None = None) -> list[dict]:
    """
    Validate and rank extractions by value, filtering out low-confidence results.

    Args:
        extractions: List of extraction dictionaries with value, confidence_score, etc.
        min_confidence: Minimum confidence score threshold. If None, uses settings.min_confidence_score

    Returns:
        List of top 3 valid extractions sorted by value (descending), then confidence_score (descending)
    """
    min_conf = min_confidence if min_confidence is not None else settings.min_confidence_score

    # Filter: value is not None and confidence_score >= min_conf
    valid = [
        e for e in extractions
        if e.get("value") is not None and e.get("confidence_score", 0) >= min_conf
    ]

    # Sort by value (descending), then confidence_score (descending)
    valid.sort(key=lambda x: (x.get("value", 0), x.get("confidence_score", 0)), reverse=True)

    # Return top 3
    return valid[:3]
