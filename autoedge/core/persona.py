"""Loads a character-roster YAML file into a Persona: everything persona
specific lives in data, not code, so adding a new character never touches
engine logic."""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field

import yaml

from .topic_memory import TopicMemory

ROSTER_DIR = os.path.join(os.path.dirname(__file__), "..", "personas")

VALID_CHRONOTYPES = {"day", "night_owl", "irregular"}


@dataclass
class TypingProfile:
    cpm: float = 200.0          # characters per minute, baseline
    error_rate: float = 0.03    # probability per character of a typo


@dataclass
class Persona:
    key: str
    display_name: str
    chronotype: str
    typing: TypingProfile
    tab_hoarding: float          # 0-1, chance a finished tab is left open
    daily_search_ceiling: int
    work_leisure_ratio: float    # baseline P(next session is Work | idle)
    work_topics: TopicMemory
    leisure_topics: TopicMemory
    has_work: bool = True        # e.g. retiree may relabel/omit "work"
    work_label: str = "Work"     # cosmetic relabel, e.g. "Volunteer admin"

    @classmethod
    def from_file(cls, path: str) -> "Persona":
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)

        chronotype = raw.get("chronotype", "day")
        if chronotype not in VALID_CHRONOTYPES:
            raise ValueError(
                f"{path}: chronotype must be one of {VALID_CHRONOTYPES}, got {chronotype!r}"
            )

        typing_raw = raw.get("typing", {})
        typing = TypingProfile(
            cpm=float(typing_raw.get("cpm", 200.0)),
            error_rate=float(typing_raw.get("error_rate", 0.03)),
        )

        key = os.path.splitext(os.path.basename(path))[0]
        return cls(
            key=key,
            display_name=raw.get("display_name", key),
            chronotype=chronotype,
            typing=typing,
            tab_hoarding=float(raw.get("tab_hoarding", 0.5)),
            daily_search_ceiling=int(raw.get("daily_search_ceiling", 6)),
            work_leisure_ratio=float(raw.get("work_leisure_ratio", 0.5)),
            work_topics=TopicMemory.from_config(raw.get("work_topics", []) or
                                                 [{"name": "(no work topics defined)"}]),
            leisure_topics=TopicMemory.from_config(raw["leisure_topics"]),
            has_work=bool(raw.get("has_work", True)),
            work_label=raw.get("work_label", "Work"),
        )


def roster_paths(roster_dir: str = ROSTER_DIR) -> list[str]:
    return sorted(glob.glob(os.path.join(roster_dir, "*.yaml")))


def load_roster(roster_dir: str = ROSTER_DIR) -> dict[str, Persona]:
    return {os.path.splitext(os.path.basename(p))[0]: Persona.from_file(p)
            for p in roster_paths(roster_dir)}


def load_persona(name: str, roster_dir: str = ROSTER_DIR) -> Persona:
    path = os.path.join(roster_dir, f"{name}.yaml")
    if not os.path.exists(path):
        available = ", ".join(sorted(p for p in
                              (os.path.splitext(os.path.basename(x))[0]
                               for x in roster_paths(roster_dir))))
        raise FileNotFoundError(
            f"no persona named '{name}' in {roster_dir} (available: {available})"
        )
    return Persona.from_file(path)
