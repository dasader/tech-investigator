from app.config import settings


def _to_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def validate_and_rank(extractions: list[dict], min_confidence: float | None = None) -> list[dict]:
    min_conf = min_confidence if min_confidence is not None else settings.min_confidence_score

    # Parse value/confidence once per element, then filter + rank on the numbers.
    scored = []
    for e in extractions:
        if e.get("value") is None:
            continue
        conf = _to_float(e.get("confidence_score", 0))
        if conf < min_conf:
            continue
        scored.append((_to_float(e.get("value")), conf, e))

    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [e for _, _, e in scored[:settings.top_results_per_indicator]]
