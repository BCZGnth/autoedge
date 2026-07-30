"""Generates fake-but-plausible search-result pages and article pages for
the mock search target, with no live network calls involved anywhere.

Content is deterministic per (query, index) via a seeded RNG, so revisiting
the "same" result twice renders the same fake article -- useful for tests
and for a human-like driver that sometimes goes back to something it saw a
moment ago.
"""

from __future__ import annotations

import random
from html import escape
from urllib.parse import quote

RESULTS_PER_PAGE = 10
MAX_PAGES = 4

_TITLE_TEMPLATES = [
    "Best {q}: A Complete Guide",
    "{q} Explained",
    "Everything You Need to Know About {q}",
    "{q} - Top Picks for 2026",
    "How {q} Actually Works",
    "{q}: Reviews and Comparisons",
    "A Beginner's Guide to {q}",
    "{q} FAQ",
    "The Truth About {q}",
    "{q} Tips From the Community",
]

_SNIPPET_TEMPLATES = [
    "A practical rundown of {q}, covering the basics and a few things "
    "people usually get wrong.",
    "We compare the most common approaches to {q} so you don't have to "
    "guess which one fits your situation.",
    "An overview of {q} written for people who are just getting started.",
    "Frequently asked questions about {q}, answered plainly.",
    "Community discussion and tips related to {q}.",
]

_PARAGRAPH_BANK = [
    "First, it helps to understand the basics before going further into {q}.",
    "Most people run into the same handful of issues with {q} early on.",
    "There isn't a single right answer here -- it depends on your goals.",
    "A common mistake is skipping the setup step and jumping straight in.",
    "Once the fundamentals click, the rest of {q} tends to fall into place.",
    "Several sources disagree on the details, so treat this as a starting point.",
    "In practice, small adjustments tend to matter more than big overhauls.",
    "It's worth revisiting this after some hands-on experience with {q}.",
    "Cost, time, and effort all trade off differently depending on your setup.",
    "A lot of the advice out there is outdated and worth double-checking.",
]


def _rng_for(*parts: object) -> random.Random:
    return random.Random("||".join(str(p) for p in parts))


def result_stub(query: str, page: int, index: int) -> dict:
    """Metadata for one result: what the results page shows and links to."""
    rng = _rng_for(query, page, index)
    title = rng.choice(_TITLE_TEMPLATES).format(q=query)
    snippet = rng.choice(_SNIPPET_TEMPLATES).format(q=query)
    result_id = f"{page}-{index}"
    return {"id": result_id, "title": title, "snippet": snippet}


def render_home() -> str:
    return """<!doctype html><html><head><title>MockSearch</title></head>
<body>
  <form action="/search" method="get">
    <input id="q" name="q" type="text" autocomplete="off">
    <button id="go" type="submit">Search</button>
  </form>
</body></html>"""


def render_results(query: str, page: int) -> str:
    stubs = [result_stub(query, page, i) for i in range(RESULTS_PER_PAGE)]
    items = "\n".join(
        f'<div class="result">'
        f'<a class="result-link" href="/page?rid={quote(s["id"])}&q={quote(query)}">'
        f'{escape(s["title"])}</a>'
        f'<p class="result-snippet">{escape(s["snippet"])}</p>'
        f'</div>'
        for s in stubs
    )
    next_link = ""
    if page < MAX_PAGES:
        next_link = (f'<a id="next-page" href="/search?q={quote(query)}'
                     f'&page={page + 1}">Next</a>')
    return f"""<!doctype html><html><head><title>results for {escape(query)}</title></head>
<body data-page="results">
  <form action="/search" method="get">
    <input id="q" name="q" type="text" autocomplete="off" value="{escape(query)}">
    <button id="go" type="submit">Search</button>
  </form>
  <div class="results">
{items}
  </div>
  {next_link}
</body></html>"""


def render_article(query: str, result_id: str) -> str:
    try:
        page_str, index_str = result_id.split("-", 1)
        page, index = int(page_str), int(index_str)
    except ValueError:
        page, index = 1, 0
    stub = result_stub(query, page, index)
    rng = _rng_for(query, result_id, "article")
    paragraph_count = rng.randint(6, 16)
    paragraphs = "\n".join(
        f"<p>{escape(rng.choice(_PARAGRAPH_BANK).format(q=query))}</p>"
        for _ in range(paragraph_count)
    )
    return f"""<!doctype html><html><head><title>{escape(stub['title'])}</title></head>
<body data-page="article">
  <h1>{escape(stub['title'])}</h1>
{paragraphs}
</body></html>"""
