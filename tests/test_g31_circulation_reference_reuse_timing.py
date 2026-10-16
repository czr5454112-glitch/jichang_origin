"""Outcome-independent candidate construction and fail-closed reference gates."""
import copy
import gzip
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import reference_reuse_timing as reference
from scripts.experiments.g31_ics_circulation import assess_reference_reuse_timing as diagnostic


def data_and_views():
    data = reference.study.scene(6.)
    views = {owner: {"now": reference.study.START, "node_records": copy.deepcopy(data["node_records"]),
        "edge_records": copy.deepcopy(data["edge_records"]), "edge_contracts": copy.deepcopy(data["edge_contracts"]),
        "jobs": [{"business_bag_id": "loaded", "loaded_at": .1}] if owner == "A" else []}
        for owner in ("A", "B")}
    return data, views


def test_plan_uses_only_public_durations_and_local_checkpoint_load():
    data, views = data_and_views()
    plan = reference.candidate_plan(data, views)
    data["jobs"] = [{"completed_at": 999, "load_seconds": 999}]
    views["B"]["jobs"] = [{"private_future": True}]
    assert reference.candidate_plan(data, views) == plan
    assert plan["old_windows"] == pytest.approx((.11, 2.21, 3.11, 6.11))
    assert [r["value"] for r in plan["centers"]] == pytest.approx((1.1, 2.1, 2.2, .8, 1.9, 2.4))
    assert len(plan["seed_windows"]) == 22
    assert len(plan["refinements"]) == 9
    assert len(plan["windows"]) == 31
    assert all(w in [r["departure"] for r in plan["windows"]] for w in plan["old_windows"])


def test_refinement_is_deterministic_longest_interval_bisection():
    plan = reference.candidate_plan(*data_and_views())
    values = list(plan["seed_windows"])
    for refinement in plan["refinements"]:
        left, right = min(zip(sorted(values), sorted(values)[1:]), key=lambda p: (-(p[1] - p[0]), p[0]))
        assert refinement == {"left": left, "right": right, "midpoint": left + (right - left) / 2}
        values.append(refinement["midpoint"])
    assert sorted(values) == [row["departure"] for row in plan["windows"]]


def test_all_gates_and_unstarted_denominator_are_retained():
    plan = reference.candidate_plan(*data_and_views())
    manifest = reference.branch_manifest({str(g): plan for g in reference.study.GATES})
    assert len(manifest) == reference.MAX_BRANCHES == 96
    assert {row["gate"] for row in manifest.values()} == {0., 6., 12.}
    assert all(row["status"] == "unknown_unexecuted" for row in manifest.values())
    assert sum(row["initial_next"] == 1 for row in manifest.values()) == 93


def valid_rows():
    plan = reference.candidate_plan(*data_and_views())
    summary = {"status": "assessed", "completion": {"a": 5., "b": 7.},
        "business_complete": True, "common_horizon_complete": True,
        "all_transfers_received": True, "all_routes_updated": True,
        "same_L_two_returns_and_two_reloads": True, "chosen_routes_match_executed_edges": True,
        "audit": {"status": "passed"}}
    rows = {f"fixed_{i:02d}": {"status": "assessed", "initial_next": 1, "departure": w["departure"], "summary": copy.deepcopy(summary)}
            for i, w in enumerate(plan["windows"])}
    rows["challenger"] = {"status": "assessed", "initial_next": 2, "departure": .11, "summary": copy.deepcopy(summary)}
    return rows, plan


@pytest.mark.parametrize("defect", ["missing", "failed", "pending", "censored", "duplicate_job_set", "nonfinite", "audit"])
def test_incomplete_reference_never_names_finite_minimum(defect):
    rows, plan = valid_rows()
    if defect == "missing":
        del rows["fixed_00"]
    elif defect == "failed":
        rows["fixed_00"] = {"status": "unknown_failed"}
    elif defect == "pending":
        rows["fixed_00"]["summary"]["all_transfers_received"] = False
    elif defect == "censored":
        rows["fixed_00"]["summary"]["common_horizon_complete"] = False
    elif defect == "duplicate_job_set":
        rows["fixed_00"]["summary"]["completion"]["other"] = 2.
    elif defect == "nonfinite":
        rows["fixed_00"]["summary"]["completion"]["a"] = float("inf")
    else:
        rows["fixed_00"]["summary"]["audit"]["status"] = "failed"
    report = reference.assess_gate(rows, plan, {"a", "b"})
    assert report["status"] == "unknown_incomplete_domain"
    assert report["best_protected_fixed_timing"] is None
    assert report["challenger_advantage_over_finite_fixed_seconds"] is None
    assert report["retained_branch_count"] == len(rows)


def test_zero_protection_has_no_candidate_neighbor_tolerance():
    rows, plan = valid_rows()
    rows["challenger"]["summary"]["completion"]["a"] += 1e-12
    rows["challenger"]["summary"]["completion"]["b"] -= 1.
    report = reference.assess_gate(rows, plan, {"a", "b"})
    assert report["status"] == "complete_finite_reference"
    assert not report["cells"]["challenger"]["all_offered_protected"]
    assert report["challenger_advantage_over_finite_fixed_seconds"] is None


@pytest.mark.parametrize("defect", ["route", "time", "duplicate_incumbent", "active_row"])
def test_action_metadata_and_unique_incumbent_are_bound_to_plan(defect):
    rows, plan = valid_rows()
    if defect == "route":
        rows["fixed_00"]["initial_next"] = 2
    elif defect == "time":
        rows["fixed_00"]["departure"] += .001
    elif defect == "duplicate_incumbent":
        rows["fixed_00"]["departure"] = plan["old_windows"][1]
    else:
        rows["fixed_00"]["status"] = "unknown_in_progress"
    report = reference.assess_gate(rows, plan, {"a", "b"})
    assert report["status"] == "unknown_incomplete_domain"
    assert report["best_protected_fixed_timing"] is None
    assert report["challenger_advantage_over_finite_fixed_seconds"] is None


def test_finite_reference_can_remove_a_previous_timing_grid_advantage():
    rows, plan = valid_rows()
    rows["fixed_00"]["summary"]["completion"]["b"] -= 2.
    rows["challenger"]["summary"]["completion"]["b"] -= 1.41
    report = reference.assess_gate(rows, plan, {"a", "b"})
    assert report["challenger_advantage_over_finite_fixed_seconds"] == pytest.approx(-.59)
    assert report["old_challenger_strictly_beaten_or_tied"] is True
    assert report["continuous_fixed_timing_optimum"] == "unknown"


@pytest.mark.skipif(not os.environ.get("G31_TIMING_REFERENCE_EVIDENCE"), reason="explicit saved evidence path; no native worker")
def test_saved_all96_branches_match_frozen_plan_and_reassessment():
    directory = Path(os.environ["G31_TIMING_REFERENCE_EVIDENCE"])
    protocol = json.loads((directory / "preregistered_protocol.json").read_text(encoding="utf-8"))
    receipt = json.loads((directory / "receipt.json").read_text(encoding="utf-8"))
    ledger = json.loads((directory / "branch_ledger.json").read_text(encoding="utf-8"))
    assert receipt["status"] in {"executed", "completed_with_unknowns"} and not receipt["source_changed"]
    assert len(ledger) == protocol["planned_branch_count"] == 96
    for gate in reference.study.GATES:
        sub = directory / f"gate{int(gate)}"
        data = json.loads((sub / "input.json").read_text(encoding="utf-8"))
        assert data == json.loads(json.dumps(reference.study.scene(gate)))
        rows = {}
        for key, row in ledger.items():
            if row["gate"] != gate:
                continue
            label = key.split("/")[1]
            raw = reference.read_gzip(sub / f"{label}.json.gz")
            client = SimpleNamespace(rows=raw["outbox"], calls=raw["calls"])
            assert reference.study.assess_cell(data, raw["result"], client, raw["continuation"], row["initial_next"]) == row["summary"] == raw["summary"]
            assert raw["checkpoint_identity"] == receipt["regimes"][str(gate)]["checkpoint_identity"]
            for choice in raw["continuation"]["route_choices"]:
                assert all(m["delivered_at"] <= choice["at"] for m in choice["delivered_forecasts"])
            for decision in raw["continuation"]["returns"]:
                assert decision["delivered_demand"]["delivered_at"] <= decision["at"]
            assert reference.candidate_plan(data, raw["seed_views"]) == protocol["gates"][str(gate)]
            expected = protocol["branch_manifest"][key]
            assert (row["departure"], row["initial_next"]) == (expected["departure"], expected["initial_next"])
            rows[label] = row
        report = reference.assess_gate(rows, protocol["gates"][str(gate)], {j["business_bag_id"] for j in data["jobs"]})
        saved = copy.deepcopy(receipt["regimes"][str(gate)])
        saved.pop("checkpoint_identity")
        assert saved.pop("original_incumbent_replayed_exactly")
        assert report == saved


@pytest.mark.parametrize("defect", ["pending", "censored", "ack_after_horizon"])
def test_rejection_diagnosis_needs_a_complete_horizon_and_delivered_terminal_ack(defect):
    raw = {"summary": {"status": "unknown_incomplete_or_unexecuted", "completion": {"receiver": -1.},
                       "audit": {"status": "passed"}, "same_L_two_returns_and_two_reloads": True},
        "result": {"advance": {"status": "reached", "horizon_complete": True, "physical_time": 40.}, "receipts": []},
        "outbox": {"x": {"kind": "transfer", "request": {"request_id": "live:B:initial-supply"},
                         "ack": {"status": "rejected", "reason": "receiving_full", "delivered_at": 2.}}},
        "continuation": {"route_choices": []}}
    assert diagnostic.diagnose_branch(raw)["category"] == "proven_selected_initial_intent_rejected_receiving_full"
    if defect == "pending":
        raw["outbox"]["x"]["ack"]["status"] = "pending"
    elif defect == "censored":
        raw["result"]["advance"]["horizon_complete"] = False
    else:
        raw["outbox"]["x"]["ack"]["delivered_at"] = 41.
    assert diagnostic.diagnose_branch(raw)["category"].startswith("unknown_")
