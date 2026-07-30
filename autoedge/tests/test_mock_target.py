"""HTTP-level tests for the mock search target -- these exercise the real
server over a real socket but never touch Selenium, so they run without a
browser."""

import re
import urllib.error
import urllib.request

import pytest

from autoedge.driving import mock_content
from autoedge.driving.mock_server import MockSearchServer


@pytest.fixture(scope="module")
def server():
    srv = MockSearchServer().start()
    yield srv
    srv.stop()


def _get(server, path):
    with urllib.request.urlopen(server.url(path), timeout=5) as resp:
        return resp.status, resp.read().decode("utf-8")


def test_home_page_has_search_box(server):
    status, body = _get(server, "/")
    assert status == 200
    assert 'id="q"' in body


def test_search_returns_results_with_links_and_snippets(server):
    status, body = _get(server, "/search?q=air+fryers")
    assert status == 200
    assert 'data-page="results"' in body
    links = re.findall(r'class="result-link" href="([^"]+)"', body)
    assert len(links) == mock_content.RESULTS_PER_PAGE


def test_missing_query_is_a_client_error(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(server, "/search")
    assert exc.value.code == 400


def test_unknown_path_is_404(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(server, "/nope")
    assert exc.value.code == 404


def test_pagination_stops_at_max_pages(server):
    _, first_page = _get(server, "/search?q=black+holes&page=1")
    assert 'id="next-page"' in first_page

    _, last_page = _get(server, f"/search?q=black+holes&page={mock_content.MAX_PAGES}")
    assert 'id="next-page"' not in last_page


def test_article_page_renders_content_matching_its_result(server):
    _, results = _get(server, "/search?q=espresso+machines&page=1")
    match = re.search(r'href="(/page\?rid=([^&"]+)&q=[^"]+)">([^<]+)</a>', results)
    assert match is not None
    href, rid, title = match.groups()

    _, article = _get(server, href)
    assert 'data-page="article"' in article
    assert title in article  # article title matches the result that linked to it


def test_result_stub_is_deterministic_for_same_query_page_index():
    a = mock_content.result_stub("laptops", page=1, index=0)
    b = mock_content.result_stub("laptops", page=1, index=0)
    assert a == b


def test_result_stub_varies_by_index():
    stubs = {mock_content.result_stub("laptops", page=1, index=i)["title"]
             for i in range(mock_content.RESULTS_PER_PAGE)}
    assert len(stubs) > 1
