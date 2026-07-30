"""Per-persona topic memory: an inverted forgetting-curve model.

Real spaced repetition strengthens a memory each time it's reinforced and
schedules the *next* review further out as strength grows. We invert that:
a topic's "strength" still grows on reinforcement and decays over real
elapsed time, but decayed (weak) topics are what the engine is *more* likely
to search next -- because a person who can't retain something goes back to
it, worded differently each time. Chronic-forget topics get an extra cap on
how high their strength can climb, so they never stabilize and keep
recurring indefinitely; stable long-term interests have a low decay rate and
a high cap so they surface occasionally without dominating; transient
topics decay fast and, once weak, mostly just stop competing for selection
rather than getting revisited forever.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field


HISTORY_LIMIT = 8


@dataclass
class Topic:
    name: str
    strength: float = 0.5
    decay_rate: float = 0.02       # fraction lost per hour of real time
    reinforcement: float = 0.35    # strength gained per search
    chronic_forget: bool = False
    cap: float = 1.0               # max strength this topic can reach
    last_touched: float = field(default_factory=time.time)
    history: list = field(default_factory=list)

    def __post_init__(self):
        if self.chronic_forget:
            # Never let it climb high enough to stop being "due" again.
            self.cap = min(self.cap, 0.55)

    def decay(self, now: float) -> None:
        hours = max(0.0, (now - self.last_touched) / 3600.0)
        if hours == 0.0:
            return
        self.strength *= math.exp(-self.decay_rate * hours)
        self.last_touched = now

    def reinforce(self, query: str, now: float) -> None:
        self.strength = min(self.cap, self.strength + self.reinforcement)
        self.last_touched = now
        self.history.append(query)
        if len(self.history) > HISTORY_LIMIT:
            self.history = self.history[-HISTORY_LIMIT:]

    def selection_weight(self) -> float:
        """Weaker topics are more "due"; a small floor keeps even a fully
        saturated topic reachable so stable interests still resurface."""
        due = (1.0 - self.strength / max(self.cap, 1e-6))
        weight = 0.08 + due
        if self.chronic_forget:
            weight *= 1.6  # these recur more insistently than plain decay implies
        return max(weight, 0.01)


class TopicMemory:
    """A weighted pool of Topics (one persona category, e.g. "work" or
    "leisure") that decays over real time and picks by inverse-strength."""

    def __init__(self, topics: list[Topic]):
        if not topics:
            raise ValueError("TopicMemory needs at least one topic")
        self.topics = topics

    @classmethod
    def from_config(cls, entries: list[dict]) -> "TopicMemory":
        now = time.time()
        topics = []
        for entry in entries:
            topics.append(Topic(
                name=entry["name"],
                strength=float(entry.get("strength", 0.5)),
                decay_rate=float(entry.get("decay_rate", 0.02)),
                reinforcement=float(entry.get("reinforcement", 0.35)),
                chronic_forget=bool(entry.get("chronic_forget", False)),
                cap=float(entry.get("cap", 1.0)),
                last_touched=now,
            ))
        return cls(topics)

    def decay_all(self, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        for topic in self.topics:
            topic.decay(now)

    def pick(self, now: float | None = None, exclude: str | None = None) -> Topic:
        now = now if now is not None else time.time()
        self.decay_all(now)
        pool = [t for t in self.topics if t.name != exclude] or self.topics
        weights = [t.selection_weight() for t in pool]
        return random.choices(pool, weights=weights, k=1)[0]

    def reinforce(self, name: str, query: str, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        for topic in self.topics:
            if topic.name == name:
                topic.reinforce(query, now)
                return
        raise KeyError(f"unknown topic: {name}")

    def get(self, name: str) -> Topic:
        for topic in self.topics:
            if topic.name == name:
                return topic
        raise KeyError(f"unknown topic: {name}")
