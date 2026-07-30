"""Self-generated interruptions ("had an idea, opened a tab") and tab
lifecycle bookkeeping.

Idea-firing is independent of any external event -- it's a per-tick roll
during an active Work or Leisure session, not something triggered by page
content. Whether the idea gets followed through or abandoned, and whether
the original task gets resumed cleanly, quickly, or not at all this
session, are each modeled as distributions rather than fixed constants --
see draw_resume_plan()'s docstring for why the "23 minutes to refocus"
figure is deliberately not baked in here.

Tabs accumulate the way real ones do: work tabs close promptly once a task
is done, but leisure/idea detours mostly just pile up until an occasional
batch cleanup sweeps several at once, gated by persona tab_hoarding.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from itertools import count


@dataclass
class Tab:
    id: int
    origin: str                 # "main" | "idea" | "revisit"
    topic: str | None
    query: str | None
    opened_at: float
    followed_through: bool = False
    closed: bool = False


class TabManager:
    def __init__(self, tab_hoarding: float):
        self.tab_hoarding = tab_hoarding
        self._ids = count(1)
        self.tabs: list[Tab] = []

    def open(self, origin: str, topic: str | None, query: str | None,
              now: float | None = None) -> Tab:
        tab = Tab(id=next(self._ids), origin=origin, topic=topic, query=query,
                   opened_at=now if now is not None else time.time())
        self.tabs.append(tab)
        return tab

    def close(self, tab: Tab) -> None:
        tab.closed = True

    def open_tabs(self) -> list[Tab]:
        return [t for t in self.tabs if not t.closed]

    def close_completed_work_tab(self, tab: Tab) -> None:
        """Work tabs close fairly promptly and deliberately once done."""
        self.close(tab)

    def resolve_abandoned_idea(self, tab: Tab) -> None:
        """An idea tab abandoned almost immediately: closes quickly
        ("nah, not worth it") more often than not, modulated by hoarding."""
        if random.random() > self.tab_hoarding * 0.7:
            self.close(tab)
        # else: left open -- becomes clutter until a batch cleanup sweeps it.

    def maybe_batch_cleanup(self, now: float | None = None) -> list[Tab]:
        """Occasionally sweep several stragglers at once rather than
        closing one-for-one. Heavier hoarders sweep less often and less."""
        candidates = [t for t in self.open_tabs() if t.origin != "main"]
        if not candidates:
            return []
        p_cleanup = 0.15 * (1.0 - 0.6 * self.tab_hoarding)
        if random.random() > p_cleanup:
            return []
        fraction = random.uniform(0.3, 1.0) * (1.0 - 0.4 * self.tab_hoarding)
        n = max(1, int(len(candidates) * fraction))
        sweep = random.sample(candidates, min(n, len(candidates)))
        for t in sweep:
            self.close(t)
        return sweep


@dataclass
class Idea:
    topic: str | None       # None => an ad-hoc, not-in-memory micro-topic
    tied_to_memory: bool
    impulsive: bool
    follow_through: bool


class InterruptionEngine:
    def __init__(self, persona):
        self.persona = persona

    def maybe_fire(self, session_kind: str, now: float | None = None) -> Idea | None:
        """session_kind: 'work' or 'leisure'. Independent per-tick roll --
        never triggered by page content."""
        p_fire = 0.05 if session_kind == "work" else 0.09
        if random.random() > p_fire:
            return None

        use_leisure_pool = session_kind == "leisure" or random.random() < 0.7
        memory = self.persona.leisure_topics if use_leisure_pool else self.persona.work_topics

        tied_to_memory = random.random() < 0.75
        if tied_to_memory:
            topic_obj = memory.pick(now)
            topic = topic_obj.name
            norm_strength = topic_obj.strength / max(topic_obj.cap, 1e-6)
            impulsive = norm_strength < 0.35
        else:
            topic = None
            impulsive = True
            norm_strength = 0.0

        base_follow = 0.25 if impulsive else 0.6
        follow_through = random.random() < min(0.9, base_follow + 0.3 * norm_strength)
        return Idea(topic=topic, tied_to_memory=tied_to_memory,
                    impulsive=impulsive, follow_through=follow_through)

    def draw_resume_plan(self) -> tuple[str, float, int]:
        """How (and whether) the original task gets resumed after a
        followed-through idea. Returns (kind, delay_seconds, drift_tabs).

        Widely-cited fixed numbers here (e.g. "23 minutes to refocus")
        measured whole interruption chains, not a single clean reset, so
        this draws from a distribution instead of hardcoding one: a chunk
        of resumptions are immediate, most of the rest land somewhere in a
        heavy-tailed few-minutes-to-much-longer range (occasionally
        drifting through 1-2 more tabs first), and some don't happen at
        all this session.
        """
        roll = random.random()
        if roll < 0.35:
            return ("immediate", 0.0, 0)
        if roll < 0.90:
            delay = random.lognormvariate(1.6, 0.9) * 60.0  # seconds
            drift_tabs = random.choices([0, 1, 2], weights=[0.4, 0.4, 0.2])[0]
            return ("delayed", delay, drift_tabs)
        return ("not_this_session", 0.0, 0)

    def maybe_refine_in_place(self) -> bool:
        """Reword the current query rather than opening a fresh tab."""
        return random.random() < 0.12

    def maybe_revisit_recent(self, recent_queries: list[str]) -> str | None:
        """Occasionally re-run (or re-word) a query from a few minutes ago
        instead of anything novel."""
        if recent_queries and random.random() < 0.08:
            return random.choice(recent_queries[-5:])
        return None
