from copy import deepcopy
from dataclasses import asdict
from types import SimpleNamespace
import pickle

import pytest

from scripts.experiments.ics_circulation_v3.model import Bag, Edge, Network, Node, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.network_role_labels import SearchBudget, bind_accounting
from scripts.experiments.ics_circulation_v3.phase4_control import ControlSpec, build_engine
from scripts.experiments.ics_circulation_v3.role_coverage import CursorSimulation, checkpoint_fingerprint
from scripts.experiments.ics_circulation_v3.routing_cache_contract import enable_replay_cache
from scripts.experiments.ics_circulation_v3.same_zone_experiment import install_supply_policy
from scripts.experiments.ics_circulation_v3.same_zone_labels import (
    checkpoint_metadata, validate_checkpoint_binding, restore_matching_continuation,
    pending_future, run_cycle, run_label_branch, compare_normal_resume, comparison_passes)
from scripts.experiments.ics_circulation_v3.same_zone_query_probe import install_query_probe


def engine_fixture(*, future=(), disconnected=False):
    network = Network({n: Node(n, "zone", "owner", 3) for n in ("L", "J", "U")},
        {} if disconnected else {"LJ": Edge("LJ", "L", "J", 2),
            "JU": Edge("JU", "J", "U", 2), "UL": Edge("UL", "U", "L", 2)})
    state = Snapshot(0, network, {"tray": Tray("tray", "L", "loaded", "seen")},
        {"seen": Bag("seen", "L", "U", 0, 30)})
    base = build_engine(state, (), future, ControlSpec(planning_horizon=20, predictive=True))
    enable_replay_cache(base)
    engine = CursorSimulation.from_base_checkpoint(base.checkpoint(), contract=base.control_contract)
    install_supply_policy(engine, "same_zone32plus32")
    return engine


def collect_tiny(*, future=(), probe=False):
    engine = engine_fixture(future=future)
    rows, captured = [], []
    owner = bind_accounting(engine, SearchBudget(100, 100000, 20))
    if probe:
        install_query_probe(engine, rows)

    def capture(current, tray, options, row, accounting):
        checkpoint = current.checkpoint().clone()
        metadata = checkpoint_metadata(checkpoint)
        captured.append(({"checkpoint": checkpoint, "pool": tuple(options),
                          "future": pending_future(current)}, metadata))

    outcome = run_cycle(engine, {**engine.state.bags, **{b.bag_id: b for b in future}},
        minimum_observation_at=45, budget=owner.budget, owner=owner, capture=capture,
        retain_physical_ticks=True)
    return outcome, captured, rows


def test_actual_normal_resume_reproduces_common_endpoint_and_every_search():
    original, captures, _ = collect_tiny()
    assert original["status"] == "controller_quiescent"
    for payload, metadata in captures:
        restored = run_label_branch(payload, metadata, minimum_observation_at=original["stopped_at"])
        comparison = compare_normal_resume(original, restored, metadata)
        assert comparison_passes(comparison), comparison


def test_binding_rejects_wrong_actual_method_and_private_clock():
    _, captures, _ = collect_tiny()
    payload, metadata = captures[0]
    changed = payload["checkpoint"].clone()
    changed.base.slow_controller.next_trigger_at += 1
    with pytest.raises(ValueError, match="binding failed"):
        validate_checkpoint_binding(changed, metadata)
    changed = payload["checkpoint"].clone()
    changed.base.slow_controller.controller.max_same_zone_candidates = 31
    with pytest.raises(ValueError, match="binding failed"):
        validate_checkpoint_binding(changed, metadata)


def test_pool_future_and_suffix_prefixes_cannot_be_substituted():
    future = (Bag("later", "L", "U", 20, 50),)
    _, captures, _ = collect_tiny(future=future)
    payload, metadata = captures[0]
    altered = dict(payload, future=())
    with pytest.raises(ValueError, match="future"):
        restore_matching_continuation(altered, metadata)
    altered = dict(payload, pool=())
    with pytest.raises(ValueError, match="pool"):
        restore_matching_continuation(altered, metadata)
    for field in ("search_prefix_count", "selector_prefix_count", "trace_prefix_count"):
        bad = deepcopy(metadata)
        bad[field] += 1
        with pytest.raises(ValueError, match="binding failed"):
            validate_checkpoint_binding(payload["checkpoint"], bad)


def test_probe_checkpoint_is_resumable_without_sink_and_exact_normal_suffix():
    original, captures, queries = collect_tiny(probe=True)
    assert queries and queries[0]["callsite"] == "engine_loaded"
    payload, metadata = pickle.loads(pickle.dumps(captures[0]))
    assert type(payload["checkpoint"].base.generator).__name__ == "BudgetGenerator"
    restored = run_label_branch(payload, metadata, minimum_observation_at=original["stopped_at"])
    assert comparison_passes(compare_normal_resume(original, restored, metadata))


def test_capture_failure_keeps_real_generation_in_denominator():
    engine = engine_fixture()

    def fail(*args):
        raise OSError("checkpoint disk failure")

    outcome = run_cycle(engine, engine.state.bags, minimum_observation_at=45, capture=fail)
    assert outcome["status"] == "execution_failure"
    assert len(outcome["opportunities"]) == 1
    assert outcome["opportunities"][0]["capture_failure"]["type"] == "OSError"
    assert outcome["search_calls"] == 1


def test_zero_attempt_has_actual_empty_checkpoint_and_remains_censored():
    engine = engine_fixture(disconnected=True)
    captured = []

    def capture(current, *args):
        checkpoint = current.checkpoint().clone()
        captured.append((checkpoint, checkpoint_metadata(checkpoint)))

    outcome = run_cycle(engine, engine.state.bags, minimum_observation_at=45,
        budget=SearchBudget(1, 100000, 20), capture=capture)
    assert outcome["status"] == "budget_censored"
    assert outcome["opportunities"][0]["candidate_count"] == 0
    assert captured[0][0].cursor.pending_options == ()
    assert all(validate_checkpoint_binding(*captured[0]).values())
    assert outcome["last_cycle_state"]["expected_task_count"] == 1
    assert not outcome["last_cycle_state"]["task_complete"]


def test_forced_branch_keeps_full_future_ledger_and_does_not_mutate_checkpoint():
    future = (Bag("later", "L", "U", 20, 50, protected=True),)
    _, captures, _ = collect_tiny(future=future)
    payload, metadata = captures[0]
    before = checkpoint_fingerprint(payload["checkpoint"])
    outcome = run_label_branch(payload, metadata, forced_index=0)
    assert outcome["status"] == "controller_quiescent"
    assert set(outcome["expected_task_ids"]) == {"seen", "later"}
    assert all(row["completed_at"] is not None for row in outcome["evaluation_ledger"])
    assert outcome["forced_intervention"]["candidate_index"] == 0
    assert checkpoint_fingerprint(payload["checkpoint"]) == before
