import random

from autoedge.core.persona import load_persona
from autoedge.core.session_planner import SessionPlanner, SessionState, alertness


def test_alertness_low_overnight_high_midday_for_day_chronotype():
    overnight = alertness(hour=3.0, chronotype="day")
    midday = alertness(hour=11.5, chronotype="day")
    assert midday > overnight


def test_alertness_post_lunch_dip_is_lower_than_midday_peak():
    peak = alertness(hour=11.5, chronotype="day")
    dip = alertness(hour=14.5, chronotype="day")
    assert dip < peak


def test_night_owl_more_alert_overnight_than_day_chronotype():
    day_overnight = alertness(hour=23.0, chronotype="day")
    owl_overnight = alertness(hour=23.0, chronotype="night_owl")
    assert owl_overnight > day_overnight


def _planner():
    persona = load_persona("grad_student")
    return SessionPlanner(persona)


def test_ceiling_blocks_new_sessions_once_reached():
    random.seed(3)
    planner = _planner()
    planner.searches_today = planner.persona.daily_search_ceiling
    now = 1_700_000_000.0
    for i in range(200):
        event = planner.tick(now + i * 60)
        assert event is None
        assert planner.state == SessionState.IDLE


def test_day_rollover_resets_ceiling_and_partially_recovers_depletion():
    planner = _planner()
    planner.searches_today = planner.persona.daily_search_ceiling
    planner.depletion = 0.9
    now = 1_700_000_000.0
    planner.tick(now)  # establishes the initial day marker
    next_day = now + 36 * 3600  # comfortably past a calendar-day boundary
    planner.tick(next_day)
    assert planner.searches_today == 0
    assert planner.depletion < 0.9


def test_ending_work_raises_depletion():
    random.seed(4)
    planner = _planner()
    now = 1_700_000_000.0
    planner._start_work(now)
    before = planner.depletion
    planner._end_work(now + planner.work_budget_seconds)
    assert planner.depletion > before
    assert planner.state == SessionState.IDLE


def test_ending_leisure_lowers_depletion_and_forces_a_later_work_start():
    random.seed(5)
    planner = _planner()
    now = 1_700_000_000.0
    planner.depletion = 0.8
    planner._start_leisure(now)
    planner._end_leisure(now + planner.leisure_guilt_threshold_seconds)
    assert planner.depletion < 0.8
    assert planner.pending_work_at is not None
    assert planner.pending_work_at > now

    # Nothing should happen before the pending time arrives...
    event = planner.tick(planner.pending_work_at - 1.0)
    assert event is None
    assert planner.state == SessionState.IDLE

    # ...but Work should start once it does, regardless of the
    # probabilistic roll -- this is the "external/state pressure forces
    # the return" half of the Work<->Leisure transition rule.
    event = planner.tick(planner.pending_work_at + 1.0)
    assert event == "work_started"
    assert planner.state == SessionState.WORK


def test_leisure_guilt_is_purely_time_driven_not_content_driven():
    """Guilt should climb monotonically with elapsed time in Leisure
    regardless of anything else -- a regression here (e.g. guilt pinned to
    0 or jumping non-monotonically) would silently break the "leisure only
    ends via time/deadline pressure" rule."""
    planner = _planner()
    now = 1_700_000_000.0
    planner._start_leisure(now)
    threshold = planner.leisure_guilt_threshold_seconds
    g1 = planner.guilt
    planner.tick(now + threshold * 0.3)
    g2 = planner.guilt
    planner.tick(now + threshold * 0.6)
    g3 = planner.guilt
    assert g1 <= g2 <= g3


def test_work_and_leisure_cycle_over_a_simulated_week():
    """End-to-end sanity: over a week of 1-minute ticks the planner should
    visit both Work and Leisure at least a few times each, and never spend
    literally 100% of ticks in one state (a stuck FSM would)."""
    random.seed(6)
    planner = _planner()
    now = 1_700_000_000.0
    work_events = 0
    leisure_events = 0
    for i in range(60 * 24 * 7):
        event = planner.tick(now)
        if event == "work_started":
            work_events += 1
        elif event == "leisure_started":
            leisure_events += 1
        now += 60
    assert work_events >= 3
    assert leisure_events >= 3
