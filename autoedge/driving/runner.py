"""Target-agnostic execution of one search: submit the query, disperse a
handful of clicks across a few result pages, read each visited page like a
human, and make it back to the results before moving on. Works against any
SearchTarget (mock or Bing) since it only ever calls the small interface in
`targets.base.SearchTarget`.
"""

from __future__ import annotations

import random

from selenium.common.exceptions import WebDriverException

from .interaction import human_scroll, pause
from .targets.base import SearchTarget


def disperse(total_clicks: int, num_pages: int) -> list[int]:
    """Spread total_clicks across num_pages, every page getting >= 0."""
    counts = [0] * num_pages
    for _ in range(total_clicks):
        counts[random.randrange(num_pages)] += 1
    return counts


def visit_result(driver, target: SearchTarget, link) -> None:
    """Click one result, read it like a human, come back to the SERP."""
    serp_url = driver.current_url
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'})", link)
        pause(0.6, 1.5)
        title = link.text[:60]
        link.click()
        print(f"      -> reading: {title}")
        pause(2.0, 4.0)  # page settle / first impression
        human_scroll(driver)
    except WebDriverException as exc:
        print(f"      -> couldn't read that one ({type(exc).__name__}), moving on")
    finally:
        # get back to the results page no matter how the site behaved
        for _ in range(3):
            if target.is_results_page(driver):
                break
            driver.back()
            pause(1.0, 2.0)
        if not target.is_results_page(driver):
            driver.get(serp_url)
            pause(1.0, 2.0)


def run_search(driver, target: SearchTarget, query: str) -> None:
    num_pages = random.randint(1, 3)
    num_clicks = random.randint(2, 7)
    plan = disperse(num_clicks, num_pages)
    print(f'  searching: "{query}"')
    print(f"  plan: {num_pages} page(s), {num_clicks} click(s) dispersed as {plan}")

    target.submit_search(driver, query)

    for page, clicks in enumerate(plan, start=1):
        pause(1.0, 2.5)
        human_scroll(driver)  # skim the results page itself

        links = target.result_links(driver)
        if not links:
            break
        indices = random.sample(range(min(len(links), 10)),
                                 min(clicks, len(links), 10))
        random.shuffle(indices)  # click out of order
        for index in indices:
            visit_result(driver, target, target.result_links(driver)[index])
            pause(1.5, 3.5)

        if page < num_pages:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            pause(0.8, 1.6)
            if not target.goto_next_page(driver):
                print("  no further result pages; stopping this search early")
                break
