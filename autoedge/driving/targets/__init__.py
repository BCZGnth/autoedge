"""Target registry. "mock" is the safe default; "bing" drives a live search
engine and must be named explicitly by a caller -- it is never chosen for
you.
"""

from __future__ import annotations

from .base import SearchTarget

DEFAULT_TARGET = "mock"


def get_target(name: str = DEFAULT_TARGET) -> SearchTarget:
    if name == "mock":
        from .mock_target import MockTarget
        return MockTarget()
    if name == "bing":
        from .bing_target import BingTarget
        return BingTarget()
    raise ValueError(f"unknown search target: {name!r} (expected 'mock' or 'bing')")
