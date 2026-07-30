import random

import pytest

from autoedge.core.topic_memory import Topic, TopicMemory


def test_strength_decays_over_elapsed_time():
    topic = Topic(name="x", strength=0.8, decay_rate=0.1, last_touched=0.0)
    topic.decay(now=3600.0)  # one hour later
    assert topic.strength < 0.8
    assert topic.last_touched == 3600.0


def test_no_decay_without_elapsed_time():
    topic = Topic(name="x", strength=0.8, decay_rate=0.1, last_touched=1000.0)
    topic.decay(now=1000.0)
    assert topic.strength == 0.8


def test_reinforcement_increases_strength_and_records_history():
    topic = Topic(name="x", strength=0.2, decay_rate=0.02, reinforcement=0.3)
    topic.reinforce("first query", now=0.0)
    assert topic.strength == pytest.approx(0.5)
    assert topic.history == ["first query"]


def test_reinforcement_caps_at_topic_cap():
    topic = Topic(name="x", strength=0.9, decay_rate=0.02, reinforcement=0.5, cap=1.0)
    topic.reinforce("q", now=0.0)
    assert topic.strength <= 1.0


def test_history_is_bounded():
    topic = Topic(name="x", strength=0.2)
    for i in range(20):
        topic.reinforce(f"query {i}", now=float(i))
    assert len(topic.history) <= 8
    assert topic.history[-1] == "query 19"


def test_chronic_forget_topic_never_stabilizes():
    """A chronic-forget topic must never climb high enough to stop being
    "due" -- repeated reinforcement should plateau well below full
    strength, so it keeps recurring rather than getting permanently learned."""
    topic = Topic(name="x", strength=0.1, decay_rate=0.05, reinforcement=0.4,
                  chronic_forget=True)
    now = 0.0
    for _ in range(50):
        topic.reinforce("q", now=now)
        now += 1.0
    assert topic.strength <= topic.cap
    assert topic.cap < 1.0  # chronic-forget cap is clamped below full retention


def test_non_chronic_topic_can_reach_full_cap():
    topic = Topic(name="x", strength=0.1, decay_rate=0.01, reinforcement=0.5, cap=1.0)
    topic.reinforce("q", now=0.0)
    topic.reinforce("q2", now=1.0)
    topic.reinforce("q3", now=2.0)
    assert topic.strength == pytest.approx(1.0)


def test_selection_weight_favors_weaker_topics():
    weak = Topic(name="weak", strength=0.05, cap=1.0)
    strong = Topic(name="strong", strength=0.95, cap=1.0)
    assert weak.selection_weight() > strong.selection_weight()


def test_chronic_forget_gets_extra_selection_weight_at_equal_strength():
    plain = Topic(name="plain", strength=0.3, cap=1.0, chronic_forget=False)
    chronic = Topic(name="chronic", strength=0.3, cap=0.55, chronic_forget=True)
    # Even accounting for the lower cap changing "due-ness", the chronic
    # multiplier should make it at least as eager to be picked.
    assert chronic.selection_weight() >= plain.selection_weight()


def test_pick_is_weighted_not_uniform():
    """Over many draws, a much-weaker topic should be picked noticeably
    more often than a nearly-saturated one."""
    random.seed(42)
    memory = TopicMemory([
        Topic(name="weak", strength=0.02, cap=1.0, decay_rate=0.0),
        Topic(name="strong", strength=0.98, cap=1.0, decay_rate=0.0),
    ])
    picks = [memory.pick(now=0.0).name for _ in range(500)]
    weak_count = picks.count("weak")
    strong_count = picks.count("strong")
    assert weak_count > strong_count * 2


def test_topic_memory_requires_at_least_one_topic():
    with pytest.raises(ValueError):
        TopicMemory([])


def test_reinforce_unknown_topic_raises():
    memory = TopicMemory([Topic(name="known")])
    with pytest.raises(KeyError):
        memory.reinforce("unknown", "q", now=0.0)


def test_from_config_round_trip():
    memory = TopicMemory.from_config([
        {"name": "a", "strength": 0.4, "decay_rate": 0.03, "chronic_forget": True},
        {"name": "b", "strength": 0.6, "decay_rate": 0.01},
    ])
    a = memory.get("a")
    b = memory.get("b")
    assert a.chronic_forget is True
    assert a.cap < 1.0
    assert b.chronic_forget is False
    assert b.cap == 1.0
