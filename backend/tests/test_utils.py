import pytest
from app.utils import get_engine_label

pytestmark = pytest.mark.no_db


def test_engine_label_combined():
    assert get_engine_label("combined") == "OpenAlex + Semantic Scholar + Gemini"


def test_engine_label_scopus():
    assert get_engine_label("scopus") == "Scopus (Elsevier) + Gemini"


def test_engine_label_unknown_defaults_to_combined():
    assert get_engine_label("anything_else") == "OpenAlex + Semantic Scholar + Gemini"
