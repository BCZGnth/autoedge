"""Turns a topic into a search query that plausibly differs from past
queries on that topic.

Primary path: a local Ollama model (qwen2.5:1.5b by default) gets the
topic, the persona's memory strength for it, and recent query history, and
is asked to produce one new, differently-worded query -- a rewording,
narrowing, synonym swap, shorthand, typo-flavored version, or natural
follow-up. This is what gives the "morphing" real variety instead of
template slot-filling.

Fallback path: when Ollama isn't reachable (not running, model not pulled,
network hiccup, timeout) we degrade to a template bank so the engine never
hard-fails just because a local model isn't available. The fallback bank
lives here as small per-topic-shape templates rather than the old fixed
TOPICS dict, since topics now come from persona YAML, not a shared bank.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5:1.5b"
REQUEST_TIMEOUT = 6.0  # seconds; this runs per-query, keep it snappy

_PROMPT = """You are simulating one search a real person types into a search engine.

Topic they're interested in: "{topic}"
How well they currently remember/understand this topic (0=barely, 1=solid): {strength:.2f}
Their last few searches on this exact topic, most recent last:
{history}

Write ONE new, short search-engine query for this same topic that is NOT a
copy of any query above. Vary it the way a real person would: different
phrasing, a synonym, more/less specific, shorthand, a typo, or a natural
follow-up question. Low memory strength should read as a more basic or
re-orienting query; high strength should read as more specific/advanced.
Output ONLY the query text, lowercase, no quotes, no explanation."""


def _format_history(history: list[str]) -> str:
    if not history:
        return "(none yet -- this is the first search on this topic)"
    return "\n".join(f"- {q}" for q in history[-5:])


class OllamaUnavailable(Exception):
    pass


def generate_via_ollama(topic: str, strength: float, history: list[str],
                         model: str = DEFAULT_MODEL,
                         url: str = OLLAMA_URL,
                         timeout: float = REQUEST_TIMEOUT) -> str:
    prompt = _PROMPT.format(topic=topic, strength=strength,
                             history=_format_history(history))
    try:
        resp = requests.post(url, json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.9, "num_predict": 40},
        }, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise OllamaUnavailable(str(exc)) from exc

    text = resp.json().get("response", "").strip()
    # Models sometimes add an explanation on a second line; take the first.
    text = text.splitlines()[0] if text else ""
    # ...and sometimes wrap the query in quotes or add a trailing period.
    text = text.strip().strip('"').strip("'").strip()
    text = re.sub(r"\s+", " ", text).strip().rstrip(".")
    if not text:
        raise OllamaUnavailable("empty response")
    return text.lower()


# ---------------------------------------------------------------------------
# Template fallback -- only used when Ollama is unreachable.
# ---------------------------------------------------------------------------

_OPENERS = [
    "what is {topic}",
    "{topic} guide",
    "{topic} explained",
    "how does {topic} work",
    "{topic} for beginners",
]
_FOLLOWUPS = [
    "{topic} tips",
    "{topic} common mistakes",
    "{topic} vs alternatives",
    "more on {topic}",
    "{topic} step by step",
    "{topic} reddit",
    "{topic} update",
]
_SHORTHAND_RE = re.compile(r"\b(and|the|a|an|of|for)\b")


def _shorthand(query: str) -> str:
    return re.sub(r"\s+", " ", _SHORTHAND_RE.sub("", query)).strip()


def generate_via_template(topic: str, history: list[str]) -> str:
    pool = _FOLLOWUPS if history else _OPENERS
    for _ in range(8):
        template = random.choice(pool)
        query = template.format(topic=topic)
        if random.random() < 0.15:
            query = _shorthand(query)
        if query not in history:
            return query
    return f"{topic} {random.randint(2020, 2026)}"  # last-resort variation


@dataclass
class QueryGenerator:
    model: str = DEFAULT_MODEL
    url: str = OLLAMA_URL
    use_ollama: bool = True

    def generate(self, topic: str, strength: float, history: list[str]) -> str:
        if self.use_ollama:
            try:
                return generate_via_ollama(topic, strength, history,
                                            model=self.model, url=self.url)
            except OllamaUnavailable:
                pass  # fall through to template bank
        return generate_via_template(topic, history)
