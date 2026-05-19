import pytest
from app.utils import get_engine_label

pytestmark = pytest.mark.no_db


def test_engine_label_combined():
    assert get_engine_label("combined") == "OpenAlex + Semantic Scholar + KCI + Gemini"


def test_engine_label_scopus():
    assert get_engine_label("scopus") == "Scopus (Elsevier) + Gemini"


def test_engine_label_legacy_values_default_to_combined():
    # 마이그레이션 전 잔존 구값(semantic_scholar/openalex)도 기본 라벨로
    assert get_engine_label("semantic_scholar") == "OpenAlex + Semantic Scholar + KCI + Gemini"
    assert get_engine_label("openalex") == "OpenAlex + Semantic Scholar + KCI + Gemini"
