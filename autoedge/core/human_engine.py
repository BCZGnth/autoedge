"""Ties Persona + TopicMemory + SessionPlanner + QueryGenerator +
InterruptionEngine together and exposes a small action stream, so all of
the "what would a human do next" logic is testable without a browser.

The consuming driver calls `tick(now)` roughly once a minute (or once a
`fast_mode` second) and executes whatever Actions come back -- typically
zero or one per call, since most ticks are spent simply waiting/reading,
which is the driver's job to pace, not the engine's.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

from .interruption import InterruptionEngine, TabManager
from .persona import Persona
from .query_generator import QueryGenerator
from .session_planner import SessionPlanner, SessionState
from .topic_memory import Topic, TopicMemory


@dataclass
class SearchAction:
    tab_id: int
    topic: str | None
    query: str
    new_tab: bool
    origin: str   # "main" | "idea" | "revisit"


@dataclass
class CloseTabAction:
    tab_id: int


Action = SearchAction | CloseTabAction


class HumanEngine:
    def __init__(self, persona: Persona, query_generator: QueryGenerator | None = None):
        self.persona = persona
        self.planner = SessionPlanner(persona)
        self.interruption = InterruptionEngine(persona)
        self.tabs = TabManager(persona.tab_hoarding)
        self.query_gen = query_generator or QueryGenerator()

        self.recent_queries: list[str] = []
        self.main_tab = None
        self.main_kind: str | None = None
        self.main_memory: TopicMemory | None = None
        self.main_topic_name: str | None = None
        self._pending_resume: dict | None = None

    # -- public status, for logging/tests ----------------------------------

    def status(self, now: float | None = None) -> dict:
        now = now if now is not None else time.time()
        return {
            "state": self.planner.state.value,
            "label": self.planner.label(),
            "alertness": round(self.planner.current_alertness(now), 2),
            "searches_today": self.planner.searches_today,
            "open_tabs": len(self.tabs.open_tabs()),
            "main_topic": self.main_topic_name,
        }

    # -- main entry point ----------------------------------------------------

    def tick(self, now: float | None = None) -> list[Action]:
        now = now if now is not None else time.time()
        event = self.planner.tick(now)

        if event in ("work_started", "leisure_started"):
            action = self._start_main_session(event, now)
            return [action] if action else []

        if event in ("work_ended", "leisure_ended"):
            return self._end_main_session(event, now)

        if self.planner.state == SessionState.IDLE:
            return []

        if self.planner.ceiling_reached():
            return []

        kind = "work" if self.planner.state == SessionState.WORK else "leisure"

        if self._resume_due(now):
            action = self._resume_main(now)
            return [action] if action else []
        if self._pending_resume is not None:
            return []  # drifting/idle-ing before resuming; nothing new yet

        idea = self.interruption.maybe_fire(kind, now)
        if idea is not None:
            return self._handle_idea(idea, now)

        swept = self.tabs.maybe_batch_cleanup(now)
        if swept:
            return [CloseTabAction(t.id) for t in swept]

        return self._maybe_followup(now)

    # -- session start/end ----------------------------------------------------

    def _memory_for_kind(self, kind: str) -> TopicMemory:
        return self.persona.work_topics if kind == "work" else self.persona.leisure_topics

    def _memory_for_topic(self, topic_name: str) -> TopicMemory | None:
        for memory in (self.persona.work_topics, self.persona.leisure_topics):
            try:
                memory.get(topic_name)
                return memory
            except KeyError:
                continue
        return None

    def _start_main_session(self, event: str, now: float):
        kind = "work" if event == "work_started" else "leisure"
        memory = self._memory_for_kind(kind)
        topic = memory.pick(now)
        query = self.query_gen.generate(topic.name, topic.strength / topic.cap, topic.history)
        tab = self.tabs.open("main", topic.name, query, now)

        self.main_tab = tab
        self.main_kind = kind
        self.main_memory = memory
        self.main_topic_name = topic.name
        self._pending_resume = None

        memory.reinforce(topic.name, query, now)
        self.recent_queries.append(query)
        self.planner.record_search()
        return SearchAction(tab.id, topic.name, query, new_tab=True, origin="main")

    def _end_main_session(self, event: str, now: float) -> list[Action]:
        actions: list[Action] = []
        if self.main_tab is not None and not self.main_tab.closed:
            if event == "work_ended":
                self.tabs.close_completed_work_tab(self.main_tab)
                actions.append(CloseTabAction(self.main_tab.id))
            else:
                self.tabs.resolve_abandoned_idea(self.main_tab)
                if self.main_tab.closed:
                    actions.append(CloseTabAction(self.main_tab.id))
        self.main_tab = None
        self.main_kind = None
        self.main_memory = None
        self.main_topic_name = None
        self._pending_resume = None
        return actions

    # -- self-generated ideas --------------------------------------------------

    def _handle_idea(self, idea, now: float) -> list[Action]:
        topic_name = idea.topic or "something unrelated"
        tab = self.tabs.open("idea", topic_name, None, now)

        if not idea.follow_through:
            self.tabs.resolve_abandoned_idea(tab)
            return [CloseTabAction(tab.id)] if tab.closed else []

        memory = self._memory_for_topic(topic_name)
        if memory is None:
            # An ad-hoc idea with no home yet: let it bleed into leisure
            # memory as a fresh, low-strength thread so it can recur later.
            memory = self.persona.leisure_topics
            memory.topics.append(Topic(name=topic_name, strength=0.15, decay_rate=0.05))

        topic = memory.get(topic_name)
        query = self.query_gen.generate(topic.name, topic.strength / topic.cap, topic.history)
        tab.query = query
        tab.followed_through = True
        memory.reinforce(topic.name, query, now)
        self.recent_queries.append(query)
        self.planner.record_search()

        resume_kind, delay, _drift_tabs = self.interruption.draw_resume_plan()
        self._pending_resume = {
            "kind": resume_kind,
            "due_at": now + delay if resume_kind == "delayed" else now,
        }
        return [SearchAction(tab.id, topic.name, query, new_tab=True, origin="idea")]

    def _resume_due(self, now: float) -> bool:
        if self._pending_resume is None:
            return False
        if self._pending_resume["kind"] == "not_this_session":
            return False
        return now >= self._pending_resume["due_at"]

    def _resume_main(self, now: float):
        self._pending_resume = None
        if (self.main_tab is None or self.main_tab.closed
                or self.main_memory is None or self.main_topic_name is None):
            return None
        topic = self.main_memory.get(self.main_topic_name)
        query = self.query_gen.generate(topic.name, topic.strength / topic.cap, topic.history)
        self.main_memory.reinforce(topic.name, query, now)
        self.recent_queries.append(query)
        self.planner.record_search()
        return SearchAction(self.main_tab.id, topic.name, query, new_tab=False, origin="main")

    # -- in-thread continuation --------------------------------------------

    def _maybe_followup(self, now: float) -> list[Action]:
        if self.main_tab is None or self.main_tab.closed or self.main_memory is None:
            return []
        if self.planner.ceiling_reached():
            return []
        if random.random() > 0.25:
            return []  # most ticks: still reading, nothing new to do

        revisit = self.interruption.maybe_revisit_recent(self.recent_queries)
        if revisit is not None:
            self.planner.record_search()
            return [SearchAction(self.main_tab.id, self.main_topic_name, revisit,
                                  new_tab=False, origin="revisit")]

        topic = self.main_memory.get(self.main_topic_name)
        query = self.query_gen.generate(topic.name, topic.strength / topic.cap, topic.history)
        refine_in_place = self.interruption.maybe_refine_in_place()
        self.main_memory.reinforce(topic.name, query, now)
        self.recent_queries.append(query)
        self.planner.record_search()

        if refine_in_place:
            return [SearchAction(self.main_tab.id, topic.name, query,
                                  new_tab=False, origin="main")]

        stray = self.main_tab
        stray.origin = "revisit"  # now just an old results page, eligible for cleanup
        self.main_tab = self.tabs.open("main", topic.name, query, now)
        return [SearchAction(self.main_tab.id, topic.name, query,
                              new_tab=True, origin="main")]
