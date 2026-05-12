from app.config import settings


def _to_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def validate_and_rank(extractions: list[dict], min_confidence: float | None = None) -> list[dict]:
    min_conf = min_confidence if min_confidence is not None else settings.min_confidence_score

    valid = [
        e for e in extractions
        if e.get("value") is not None and _to_float(e.get("confidence_score", 0)) >= min_conf
    ]
    valid.sort(key=lambda x: (_to_float(x.get("value")), _to_float(x.get("confidence_score"))), reverse=True)
    return valid[:settings.top_results_per_indicator]
