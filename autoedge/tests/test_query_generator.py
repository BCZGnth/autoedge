import random

import pytest
import requests

from autoedge.core.query_generator import (
    QueryGenerator,
    generate_via_template,
    OllamaUnavailable,
)


def test_template_fallback_avoids_repeating_recent_history():
    random.seed(1)
    history = []
    for _ in range(10):
        q = generate_via_template("air fryers", history)
        assert q not in history
        history.append(q)
    assert len(set(history)) > 1  # not the same query every time


def test_template_fallback_produces_variety_across_many_calls():
    random.seed(2)
    seen = {generate_via_template("black holes", []) for _ in range(30)}
    # A silent bug here would be the generator always returning the same
    # string regardless of history/randomness.
    assert len(seen) >= 3


def test_query_generator_falls_back_when_ollama_unreachable():
    qg = QueryGenerator(use_ollama=True, url="http://localhost:1/api/generate")
    query = qg.generate("laptops", 0.5, [])
    assert isinstance(query, str) and query


def test_query_generator_skips_network_entirely_when_disabled(monkeypatch):
    def _fail(*a, **k):
        raise AssertionError("should not hit the network when use_ollama=False")
    monkeypatch.setattr(requests, "post", _fail)
    qg = QueryGenerator(use_ollama=False)
    query = qg.generate("laptops", 0.5, [])
    assert isinstance(query, str) and query


def test_ollama_bad_response_raises_unavailable(monkeypatch):
    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": "   "}  # empty after stripping

    def fake_post(*a, **k):
        return FakeResp()

    monkeypatch.setattr(requests, "post", fake_post)
    from autoedge.core.query_generator import generate_via_ollama
    with pytest.raises(OllamaUnavailable):
        generate_via_ollama("topic", 0.5, [])


def test_ollama_response_is_cleaned_up(monkeypatch):
    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": '"Best Air Fryers 2026."\nextra line'}

    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResp())
    from autoedge.core.query_generator import generate_via_ollama
    result = generate_via_ollama("air fryers", 0.5, [])
    assert result == "best air fryers 2026"
