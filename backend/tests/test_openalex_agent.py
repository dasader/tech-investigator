import pytest
from app.agents.openalex_agent import _reconstruct_abstract

pytestmark = pytest.mark.no_db


def test_reconstruct_abstract_basic():
    inv_idx = {
        "We": [0],
        "present": [1],
        "HBM3E": [2],
        "memory": [3],
    }
    assert _reconstruct_abstract(inv_idx) == "We present HBM3E memory"


def test_reconstruct_abstract_repeated_words():
    inv_idx = {
        "the": [0, 4],
        "memory": [1, 5],
        "is": [2],
        "fast": [3],
    }
    # positions: 0=the 1=memory 2=is 3=fast 4=the 5=memory
    assert _reconstruct_abstract(inv_idx) == "the memory is fast the memory"


def test_reconstruct_abstract_none_returns_empty():
    assert _reconstruct_abstract(None) == ""


def test_reconstruct_abstract_empty_dict_returns_empty():
    assert _reconstruct_abstract({}) == ""


def test_reconstruct_abstract_handles_gaps():
    # OpenAlex 인덱스는 일반적으로 gap 없음. gap이 있어도 sort된 키 순서로 처리해야 함.
    inv_idx = {"word_a": [0], "word_b": [10]}
    result = _reconstruct_abstract(inv_idx)
    assert result == "word_a word_b"
