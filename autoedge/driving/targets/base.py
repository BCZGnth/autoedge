"""The interface a search target (mock site, Bing, ...) must implement so
the driving loop can stay target-agnostic. Everything here is expressed in
terms of a Selenium `driver`; a target owns its own page structure/selectors
and translates the small set of actions below into whatever that structure
requires.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SearchTarget(ABC):
    name: str

    @abstractmethod
    def ensure_ready(self, driver: Any) -> None:
        """Navigate to the target's home page and get it into a searchable
        state (dismiss cookie banners, confirm sign-in, etc). Called once
        per driver lifetime before any searches."""

    @abstractmethod
    def submit_search(self, driver: Any, query: str) -> None:
        """Perform one search and land on a results page."""

    @abstractmethod
    def result_links(self, driver: Any) -> list:
        """Clickable organic-result elements on the current results page,
        in display order."""

    @abstractmethod
    def goto_next_page(self, driver: Any) -> bool:
        """Advance to the next page of results. Returns False (and leaves
        the driver where it was) if there is no next page."""

    @abstractmethod
    def is_results_page(self, driver: Any) -> bool:
        """Whether the driver is currently sitting on a results page for
        this target -- used to detect "did we make it back to the SERP"
        after visiting a result."""
