"""Work <-> Leisure state machine, gated by circadian alertness.

Design note on the Work<->Leisure transition rule (flagged in the original
spec as needing a clean formulation): the two directions are deliberately
asymmetric.

  * Work -> Leisure is a soft probabilistic drift. Ending a Work session
    raises `depletion` (an ego-depletion/self-regulation proxy), which
    biases the *next* probabilistic roll toward Leisure -- it does not
    force a Leisure session. This matches the strength-model-of-self-
    control framing: depleted self-regulation makes leisure browsing more
    likely, it doesn't mandate it.

  * Leisure -> Work is threshold-driven, not content-driven. While in
    Leisure, a `guilt` variable accumulates purely as a function of
    elapsed time (a deadline-pressure/temporal-discounting proxy -- never
    a function of what was browsed). Once it crosses a per-session
    threshold, Leisure ends and a real idle gap (roughly 1-20 minutes,
    itself a stand-in for "external/state pressure asserting itself")
    follows before a new Work session is forced to start. This is
    intentionally more deterministic than the Work->Leisure direction,
    because the spec is explicit that nothing encountered *during*
    leisure organically produces a work thought -- the return has to come
    from state/external pressure, not from browsing content.

Alertness itself follows a circadian day-curve (low on waking, rising to a
late-morning/midday peak, a post-lunch dip, a smaller late-afternoon rise,
overnight trough), phase-shifted per chronotype, with a persona-level
random jitter so personas sharing a chronotype don't all sync to the same
clock. The post-lunch dip does double duty: it both lowers alertness *and*
directly biases the Work/Leisure roll toward Leisure, per the
cyberloafing/self-regulation research the spec cites.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

from .persona import Persona


class SessionState(Enum):
    IDLE = "idle"
    WORK = "work"
    LEISURE = "leisure"


# (hour, alertness) control points for a "day" chronotype; interpolated
# linearly between points. Encodes: low on waking, rise through morning,
# midday peak, post-lunch dip, smaller late-afternoon rise, overnight low.
_DAY_CURVE = [
    (0.0, 0.15), (5.0, 0.15), (6.0, 0.30), (8.0, 0.65), (10.0, 0.90),
    (11.5, 1.00), (13.0, 0.65), (14.5, 0.45), (16.0, 0.55), (18.0, 0.70),
    (20.0, 0.60), (22.0, 0.35), (24.0, 0.15),
]


def _interp(curve, hour: float) -> float:
    hour = hour % 24.0
    for (h0, v0), (h1, v1) in zip(curve, curve[1:]):
        if h0 <= hour <= h1:
            frac = 0.0 if h1 == h0 else (hour - h0) / (h1 - h0)
            return v0 + frac * (v1 - v0)
    return curve[-1][1]


def alertness(hour: float, chronotype: str, jitter: float = 0.0) -> float:
    hour = (hour + jitter) % 24.0
    if chronotype == "night_owl":
        # Phase-shift so the "midday" peak of the curve lands in the
        # evening/night and the curve's trough lands around actual midday.
        return _interp(_DAY_CURVE, (hour - 10.0) % 24.0)
    if chronotype == "irregular":
        # Flatter, less predictable -- blend the day curve toward a
        # constant so work hours can fall almost anywhere.
        return 0.5 * _interp(_DAY_CURVE, hour) + 0.5 * 0.6
    return _interp(_DAY_CURVE, hour)


def _local_hour(now: float) -> float:
    t = time.localtime(now)
    return t.tm_hour + t.tm_min / 60.0 + t.tm_sec / 3600.0


@dataclass
class SessionPlanner:
    persona: Persona
    state: SessionState = SessionState.IDLE
    state_entered_at: float = field(default_factory=time.time)

    depletion: float = 0.0                 # 0-1 ego-depletion proxy
    guilt: float = 0.0                      # 0-1 leisure guilt/pressure proxy
    work_budget_seconds: float = 0.0
    leisure_guilt_threshold_seconds: float = 0.0
    pending_work_at: float | None = None    # set when guilt has crossed over

    chronotype_jitter: float = field(default_factory=lambda: random.uniform(-1.2, 1.2))
    searches_today: int = 0
    # Lazily set from the first `now` a tick actually uses, rather than the
    # real wall clock at construction time -- keeps day-rollover honest when
    # driving the planner with a simulated/fast-forwarded clock (tests,
    # fast-mode) instead of live time.time().
    _day_marker: date | None = None

    # -- circadian helpers ---------------------------------------------

    def current_alertness(self, now: float | None = None) -> float:
        now = now if now is not None else time.time()
        return alertness(_local_hour(now), self.persona.chronotype,
                          self.chronotype_jitter)

    # -- bookkeeping ------------------------------------------------------

    def _roll_day(self, now: float) -> None:
        today = datetime.fromtimestamp(now).date()
        if self._day_marker is None:
            self._day_marker = today
            return
        if today != self._day_marker:
            self._day_marker = today
            self.searches_today = 0
            self.depletion *= 0.2   # a night's sleep resets most depletion
            self.guilt = 0.0

    def record_search(self) -> None:
        self.searches_today += 1

    def ceiling_reached(self) -> bool:
        return self.searches_today >= self.persona.daily_search_ceiling

    def label(self) -> str:
        if self.state == SessionState.WORK:
            return self.persona.work_label
        if self.state == SessionState.LEISURE:
            return "Leisure"
        return "Idle"

    # -- state transitions -------------------------------------------------

    def _draw_work_budget(self, now: float) -> float:
        al = self.current_alertness(now)
        base_minutes = 90.0 * (0.55 + 0.6 * al)   # ~50-140 min, ultradian-ish
        minutes = max(20.0, random.gauss(base_minutes, base_minutes * 0.2))
        return minutes * 60.0

    def _draw_leisure_threshold(self, now: float) -> float:
        al = self.current_alertness(now)
        # Lower alertness (the post-lunch dip) buys leisure more slack
        # before guilt kicks back in -- consistent with self-regulation
        # being the thing that's depleted there.
        base_minutes = 8.0 + 25.0 * (1.0 - al)
        minutes = max(3.0, random.gauss(base_minutes, base_minutes * 0.3))
        return minutes * 60.0

    def _start_work(self, now: float) -> None:
        self.state = SessionState.WORK
        self.state_entered_at = now
        self.work_budget_seconds = self._draw_work_budget(now)
        self.pending_work_at = None

    def _start_leisure(self, now: float) -> None:
        self.state = SessionState.LEISURE
        self.state_entered_at = now
        self.leisure_guilt_threshold_seconds = self._draw_leisure_threshold(now)
        self.guilt = 0.0

    def _end_work(self, now: float) -> None:
        elapsed = now - self.state_entered_at
        # Depletion scales with how much of the budget was actually spent;
        # a session cut short by early "task completion" depletes less.
        self.depletion = min(1.0, self.depletion +
                              0.55 * (elapsed / max(self.work_budget_seconds, 1.0)))
        self.state = SessionState.IDLE
        self.state_entered_at = now

    def _end_leisure(self, now: float) -> None:
        # Leisure serves a recovery function: depletion drops on the way out.
        self.depletion *= 0.35
        self.guilt = 0.0
        self.state = SessionState.IDLE
        self.state_entered_at = now
        # The return to Work is state/external-pressure driven, not
        # content-driven -- force it, but only after a real idle gap.
        self.pending_work_at = now + random.uniform(60.0, 20 * 60.0)

    def _p_work_given_start(self, now: float) -> float | None:
        al = self.current_alertness(now)
        if al < 0.18:
            return None  # deep in the overnight/trough window: stay idle
        leisure_pull = 0.5 * self.depletion + 0.5 * max(0.0, 0.6 - al)
        p_work = self.persona.work_leisure_ratio - leisure_pull
        return max(0.05, min(0.95, p_work))

    def tick(self, now: float | None = None) -> str | None:
        """Advance the FSM by one check. Returns an event name if a
        transition happened, else None. Safe to call frequently (e.g. once
        a minute) from a daemon loop -- most calls are no-ops."""
        now = now if now is not None else time.time()
        self._roll_day(now)

        if self.state == SessionState.WORK:
            elapsed = now - self.state_entered_at
            # Occasionally the task just gets done early, independent of budget.
            task_done_hazard = 0.0006 * max(0.0, elapsed / 60.0)
            if elapsed >= self.work_budget_seconds or random.random() < task_done_hazard:
                self._end_work(now)
                return "work_ended"
            return None

        if self.state == SessionState.LEISURE:
            elapsed = now - self.state_entered_at
            self.guilt = elapsed / self.leisure_guilt_threshold_seconds
            if self.guilt >= 1.0:
                self._end_leisure(now)
                return "leisure_ended"
            return None

        # IDLE
        if self.ceiling_reached():
            return None

        if self.pending_work_at is not None:
            if now >= self.pending_work_at:
                self._start_work(now)
                return "work_started"
            return None

        p_work = self._p_work_given_start(now)
        if p_work is None:
            return None
        # Small per-tick chance anything starts at all, scaled by alertness,
        # so sessions don't spin up the instant they're theoretically possible.
        al = self.current_alertness(now)
        if random.random() > 0.12 * al:
            return None
        if self.persona.has_work and random.random() < p_work:
            self._start_work(now)
            return "work_started"
        self._start_leisure(now)
        return "leisure_started"
