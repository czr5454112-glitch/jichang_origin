from copy import deepcopy
from dataclasses import asdict, replace

import pytest

from test_ics_circulation_v3_same_zone_labels import collect_tiny
from scripts.experiments.ics_circulation_v3.model import Bag
from scripts.experiments.ics_circulation_v3.same_zone_labels import run_label_branch, comparison_passes
from scripts.experiments.ics_circulation_v3 import same_zone_stability as stability
from scripts.experiments.ics_circulation_v3.run_same_zone_stability import compare_bridge


@pytest.fixture
def captured():
    _, captures, _ = collect_tiny(future=(Bag("later", "L", "U", 20, 50),
        Bag("protected", "L", "U", 30, 80, True)))
    return captures[0]


def test_exact_conditional_integer_support_and_boundary():
    bag = Bag("x", "L", "U", 10, 20)
    assert stability.conditional_support(bag, 7)["total_mass"] == 24
    result = stability.conditional_support(bag, 8)
    assert result["total_mass"] == 17
    assert [r["jitter"] for r in result["outcomes"]] == [None, 0, 2]
    assert stability.conditional_support(replace(bag, protected=True), 8)["total_mass"] == 1
    with pytest.raises(ValueError, match="strictly after"):
        stability.conditional_support(bag, 10)


def test_integer_sampling_visits_every_conditional_mass_without_clipping(monkeypatch, captured):
    payload, meta = captured
    engine = stability.restore_matching_continuation(payload, meta)
    bag = Bag("boundary", "L", "U", engine.state.now + 1, engine.state.now + 40)

    class Enumerated:
        def __init__(self, seed):
            self.value = 0

        def randrange(self, n):
            assert n == 17
            value = self.value
            self.value += 1
            return value

    monkeypatch.setattr(stability.random, "Random", Enumerated)
    tapes = stability.sample_conditional_futures(engine.state, (bag,), 10, 17)
    assert sum(not t for t in tapes) == 3
    assert sum(bool(t) and t[0].arrival == bag.arrival for t in tapes) == 7
    assert sum(bool(t) and t[0].arrival == bag.arrival + 2 for t in tapes) == 7


def test_sampling_nested_deterministic_and_protected_exact(captured):
    payload, meta = captured
    engine = stability.restore_matching_continuation(payload, meta)
    a = stability.sample_conditional_futures(engine.state, payload["future"], 130, 32)
    b = stability.sample_conditional_futures(engine.state, payload["future"], 130, 8)
    assert a[:8] == b
    assert a != stability.sample_conditional_futures(engine.state, payload["future"], 131, 32)
    protected = next(b for b in payload["future"] if b.protected)
    assert all(protected in tape for tape in a)
    assert all(stability.validate_sampled_future(engine.state, payload["future"], tape) == tape for tape in a)


@pytest.mark.parametrize("violation", ["protected_cancel", "protected_shift", "od", "slack", "jitter", "new", "duplicate"])
def test_invalid_sample_rejected_before_physics(captured, violation):
    payload, meta = captured
    later, protected = payload["future"]
    cases = {"protected_cancel": (later,), "protected_shift": (later, replace(protected, arrival=32, deadline=82)),
        "od": (replace(later, origin="J"), protected), "slack": (replace(later, deadline=51), protected),
        "jitter": (replace(later, arrival=21, deadline=51), protected),
        "new": (later, protected, replace(later, bag_id="new")), "duplicate": (later, later, protected)}
    with pytest.raises(ValueError):
        stability.restore_sampled_continuation(payload, meta, cases[violation])


def test_future_replacement_preserves_private_continuation_and_original(captured):
    payload, meta = captured
    old = deepcopy(payload)
    sampled = (payload["future"][1],)
    engine, binding = stability.restore_sampled_continuation(payload, meta, sampled)
    assert all(binding["unchanged"].values())
    assert stability.pending_future(engine) == sampled
    assert payload["future"] == old["future"]
    assert stability.validate_checkpoint_binding(payload["checkpoint"], meta)
    assert engine.instant_physical_ticks == []


def test_identity_tape_exact_bridge_and_detached_trace(captured):
    payload, meta = captured
    old = run_label_branch(payload, meta, forced_index=0, minimum_observation_at=85)
    new = stability.run_sampled_branch(payload, meta, payload["future"], candidate_index=0, minimum_observation_at=85)
    comparison = compare_bridge(old, new)
    assert comparison_passes(comparison), comparison
    assert new["instant_physical_tick_trace"]
    first = new["instant_physical_tick_trace"][0]
    assert "later" not in first["completed"]


def test_memo_cannot_cross_state_candidate_or_continuation(captured):
    payload, _ = captured
    args = ["checkpoint", 0, "action", payload["future"], "continuation"]
    original = stability.memo_key(*args)
    for index, value in ((0, "other_checkpoint"), (1, 1), (2, "other_action"), (4, "other_method")):
        changed = list(args)
        changed[index] = value
        assert stability.memo_key(*changed) != original
    assert stability.memo_key(*args) == stability.memo_key(*args[:3], tuple(reversed(args[3])), args[4])


def test_strata_zero_is_not_replaced_by_success_or_cost():
    collections = {s: [{"decision_index": 0, "time": 2, "role": "origin", "candidate_count": 0, "total_cost": 1000},
        {"decision_index": 1, "time": 3, "role": "origin", "candidate_count": 4, "total_cost": -1}]
        for s in stability.SCENE_SEEDS}
    selected = stability.select_strata(collections)
    assert selected["counts"]["selected_nonempty"] == 0
    assert selected["counts"]["zero"] == 3
    assert selected["counts"]["missing_cells"] == 15


def test_bridge_only_elapsed_measurement_is_exempt(captured):
    payload, meta = captured
    old = run_label_branch(payload, meta, forced_index=0, minimum_observation_at=85)
    changed = deepcopy(old)
    if changed["slow_history_suffix"]:
        changed["slow_history_suffix"][0]["diagnostics"]["elapsed_ms"] += 100
    assert comparison_passes(compare_bridge(old, changed))
    changed["search_work"] += 1
    assert not comparison_passes(compare_bridge(old, changed))
