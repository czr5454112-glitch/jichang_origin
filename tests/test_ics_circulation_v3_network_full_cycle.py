from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest

from scripts.experiments.ics_circulation_v3.model import Bag, Edge, Network, Node, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.network_full_cycle import branch_full_cycle, compare_old_result
from scripts.experiments.ics_circulation_v3.network_role_labels import (
    SearchBudget, branch_network_decision, collect_network_decisions)
from scripts.experiments.ics_circulation_v3.phase4_control import ControlSpec
from scripts.experiments.ics_circulation_v3.role_coverage import checkpoint_fingerprint


def actual_sample():
    network = Network({n: Node(n, "z", "p", 2) for n in ("L", "J", "U")},
        {"LJ": Edge("LJ", "L", "J", 2), "JU": Edge("JU", "J", "U", 2),
         "UL": Edge("UL", "U", "L", 2)})
    snapshot = Snapshot(5, network, {"tray": Tray("tray", "L", "loaded", "seen")},
        {"seen": Bag("seen", "L", "U", 1, 20)})
    scene = SimpleNamespace(name="test_only", initial=snapshot, forecasts=(), future_bags=(), horizon=15)
    collection = collect_network_decisions(scene, spec=ControlSpec(planning_horizon=20, predictive=False),
        budget=SearchBudget(30, 10000, 10), bands=(0,))
    return collection["samples"][0]


def test_exact_h80_then_complete_future_after_h80_without_mutating_checkpoint():
    sample = actual_sample()
    checkpoint, candidate = sample["checkpoint"], sample["pool"][0]
    future = (Bag("late", "L", "U", 100, 130),)
    before = checkpoint_fingerprint(checkpoint)
    old = branch_network_decision(checkpoint, candidate, future, horizon_ticks=80)
    result = branch_full_cycle(checkpoint, candidate, future, old_result=old["result"])
    assert result["status"] == "controller_quiescent"
    assert result["old80_comparison"]["equal"]
    assert result["milestones"]["task_complete"]["time"] > 100
    assert result["milestones"]["controller_quiescent"]["time"] >= result["milestones"]["transport_drained"]["time"] + 1
    assert result["result"].uncompleted_bag_ids == ()
    assert set(result["result"].completed) == {"seen", "late"}
    assert checkpoint_fingerprint(checkpoint) == before


def test_old_result_mismatch_stops_exactly_at80_and_retains_evidence():
    sample = actual_sample()
    old = branch_network_decision(sample["checkpoint"], sample["pool"][0], (), horizon_ticks=80)["result"]
    old = replace(old, total_cost=old.total_cost + 1)
    out = branch_full_cycle(sample["checkpoint"], sample["pool"][0], (), old_result=old)
    assert out["status"] == "old80_mismatch"
    assert out["stopped_at"] == sample["time"] + 80
    assert out["old80_comparison"]["different_fields"] == ["total_cost"]
    assert str(out["stopped_at"]) in out["endpoints"]


def test_tick_and_work_censoring_never_claim_infeasibility_or_completed_endpoint():
    sample = actual_sample()
    future = (Bag("late", "L", "U", 100, 130),)
    cap = branch_full_cycle(sample["checkpoint"], sample["pool"][0], future, tail_cap=1)
    assert cap["status"] == "tick_cap_censored"
    assert not cap["last_cycle_state"]["task_complete"]
    budget = branch_full_cycle(sample["checkpoint"], sample["pool"][0], future,
                              budget=SearchBudget(1, 100000, 20))
    assert budget["status"] == "budget_censored"
    assert budget["old80_comparison"] is None


def test_saved_result_equality_keeps_every_nontiming_stat():
    sample = actual_sample()
    old = branch_network_decision(sample["checkpoint"], sample["pool"][0], (), horizon_ticks=80)["result"]
    raw = asdict(old)
    raw["policy_stats"]["generation_ms"] += 123
    assert compare_old_result(raw, old)["equal"]
    raw["policy_stats"]["generation_calls"] += 1
    assert not compare_old_result(raw, old)["equal"]


def test_whole_original_domain_and_pilot_selection_are_outcome_independent():
    from scripts.experiments.ics_circulation_v3.run_network_full_cycle import selected_requests
    samples, rows = {}, []
    for scene in ("cross_cycle", "counterflow", "near_full"):
        for role in ("origin", "continuation"):
            key = scene + role
            samples[key] = {"scene": scene, "saved": {"role": role, "candidate_count": 4}}
            rows.extend({"scene": scene, "sample": key, "group": g, "draw": d, "candidate": c}
                        for g in range(4) for d in range(8) for c in range(4))
    assert len(selected_requests(samples, rows, "pilot")) == 12
    assert selected_requests(samples, rows, "full") == rows
    with pytest.raises(ValueError):
        selected_requests(samples, rows, "invalid")


def test_shards_partition_requests_and_keep_exact_memo_classes_whole():
    from scripts.experiments.ics_circulation_v3.run_network_full_cycle import shard_requests, memo_key
    rows = [{"request_key": f"s{s}c{c}d{d}", "sample": f"s{s}", "candidate": c,
             "future_sha256": str(d % 3)} for s in range(4) for c in range(4) for d in range(32)]
    shards = [shard_requests(rows, index, 6) for index in range(6)]
    assert sorted(r["request_key"] for shard in shards for r in shard) == sorted(r["request_key"] for r in rows)
    ownership = {}
    for index, shard in enumerate(shards):
        for row in shard:
            assert ownership.setdefault(memo_key(row), index) == index
    with pytest.raises(ValueError):
        shard_requests(rows, 6, 6)
