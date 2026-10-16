"""Causal recovery, explicit route authority, campaign and assay guards."""
import copy
import json
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import research_synthetic_reuse_v2 as study


def view():
    data = study.v1.scene(6.)
    return {"owner_id": "B", "now": 1.5, "node_records": data["node_records"],
        "edge_records": data["edge_records"], "edge_contracts": data["edge_contracts"],
        "node_contracts": [{**n, **({"occupancy": 0} if n["resource_owner"] == "B" else {})} for n in data["node_contracts"]],
        "trays": [{"tray_id": "E", "node": 5, "mode": "empty", "edge_to": -1, "available_at": 0.}],
        "delivered_messages": [{"kind": "demand", "source_owner": "A", "observed_at": .1, "delivered_at": .2,
            "publication_sequence": 1, "jobs": [{"origin": 1}]}]}


def rejection():
    return {"request": {"request_id": "supply0"}, "ack": {"status": "rejected", "reason": "receiving_full", "delivered_at": 1.}}


@pytest.mark.parametrize("defect", ["early", "undelivered", "wrong_reason", "not_empty", "moving", "future_demand", "limit", "expiry"])
def test_recovery_requires_delivered_rejection_cooldown_local_tray_and_demand(defect):
    v, previous, count = view(), rejection(), 1
    assert study.recovery_basis(v, previous, count)
    if defect == "early": v["now"] = 1.5 - 1e-12
    elif defect == "undelivered": previous["ack"]["delivered_at"] = 2.
    elif defect == "wrong_reason": previous["ack"]["reason"] = "other"
    elif defect == "not_empty": v["trays"][0]["mode"] = "loaded"
    elif defect == "moving": v["trays"][0]["edge_to"] = 1
    elif defect == "future_demand": v["delivered_messages"][0]["delivered_at"] = 2.
    elif defect == "limit": count = study.SUPPLY_ATTEMPT_LIMIT
    else: v["now"] = 39.
    assert study.recovery_basis(v, previous, count) is None


def test_recovery_keeps_original_rejection_and_local_snapshot_immutable():
    v, previous = view(), rejection()
    frozen = copy.deepcopy((v, previous))
    result = study.recovery_basis(v, previous, 1)
    result["delivered_rejection"]["reason"] = "changed"
    result["local_tray"]["mode"] = "changed"
    assert (v, previous) == frozen


def test_explicit_next3_and_lawful_capacity_bypass_never_claim_unknown_native_route():
    v = view()
    assert study.later_choice(v, {}, "adaptive")["next"] == 3
    next(n for n in v["node_contracts"] if n["node"] == 3)["occupancy"] = 1
    result = study.later_choice(v, {}, "adaptive")
    assert result["next"] == 8 and result["selection_reason"] == "local3_full_bypass"
    assert study.later_choice(v, {}, "native_keep")["next"] is None
    del next(n for n in v["node_contracts"] if n["node"] == 3)["occupancy"]
    with pytest.raises(ValueError, match="missing_lawful_local_resource"):
        study.later_choice(v, {}, "adaptive")


def test_current_preference_is_unknown_until_matching_delivered_ack():
    tray = {"tray_id": "L", "business_bag_id": "reuse1", "node": 7, "generation": 3, "traversal_id": 9}
    request = {**tray, "from": 7, "next": 3, "expected_generation": 3, "expected_traversal": 9, "expiry": 20.}
    client = SimpleNamespace(rows={"r": {"kind": "route", "request": request, "ack": {}}})
    assert study.known_current_preference(client, tray, 10.) is None
    client.rows["r"]["ack"] = {"status": "updated", "delivered_at": 11.}
    assert study.known_current_preference(client, tray, 10.) is None
    assert study.known_current_preference(client, tray, 11.) == 3
    tray["generation"] += 1
    assert study.known_current_preference(client, tray, 11.) is None


def test_predeclared_campaign_uses117_unique_cells_and_reuses15_old_labels(tmp_path):
    for gate in study.v1.GATES:
        folder = tmp_path / f"gate{int(gate)}"
        folder.mkdir()
        data = study.v1.scene(gate)
        (folder / "input.json").write_text(json.dumps(data))
        v = view()
        v.update(now=study.v1.START, jobs=[{"business_bag_id": "loaded", "loaded_at": .1}])
        import gzip
        with gzip.open(folder / "route1_window1.json.gz", "wt") as stream:
            json.dump({"seed_views": {"A": v, "B": v}, "checkpoint_identity": "test"}, stream)
    scenes, ledger = study.plan_campaign(tmp_path)
    assert len(ledger) == 117
    assert {p: sum(r["phase"] == p for r in ledger.values()) for p in ("old24", "stronger96", "causal12")} == {"old24": 24, "stronger96": 81, "causal12": 12}
    assert all(r["status"] == "unknown_unexecuted" for r in ledger.values())
    report = study.reports(ledger, scenes)
    assert all(len(r["stronger96"]["cells"]) == 32 for r in report.values())
    assert all(r["stronger96"]["status"] == "unknown_incomplete_domain" for r in report.values())


def sample(monkeypatch):
    monkeypatch.setattr(study, "audit_result", lambda *_: {"status": "passed"})
    data = study.v1.scene(6.)
    rows = {key: {"kind": "transfer", "request": {"request_id": key}, "ack": {"status": "received", "delivered_at": 5.}}
            for key in ("supply", "return0", "return1")}
    rows.update({key: {"kind": "route", "request": {"request_id": key}, "ack": {"status": "updated", "delivered_at": 5.}}
                 for key in ("route0", "route1")})
    continuation = {"status": "finished", "supply_lineage": ["supply"], "recovery_decisions": [],
        "returns": [{"request_id": "return0"}, {"request_id": "return1"}],
        "route_choices": [{"job": job, "request_id": f"route{i}", "next": 3, "known_delivered_preference": None} for i, job in enumerate(("reuse1", "reuse2"))]}
    receipts = [{"event": "EDGE_ENTER", "tray_id": "L", "business_bag_id": "loaded", "from": 0, "to": 1}]
    for i, job in enumerate(("reuse1", "reuse2")):
        receipts.extend([{"event": "EMPTY_RECEIVED", "tray_id": "L", "node": 7, "time": 10 + i * 5},
            {"event": "LOAD_START", "tray_id": "L", "business_bag_id": job, "time": 10 + i * 5},
            {"event": "EDGE_ENTER", "tray_id": "L", "business_bag_id": job, "from": 7, "to": 3}])
    result = {"advance": {"status": "reached", "horizon_complete": True, "physical_time": 40.},
        "jobs": [{"business_bag_id": j["business_bag_id"], "completed_at": 20.} for j in data["jobs"]],
        "trays": [{"tray_id": t} for t in ("L", "E")], "receipts": receipts}
    client, spec = SimpleNamespace(rows=rows, calls=[]), {"initial_next": 1, "later_mode": "adaptive"}
    assert study.assess_cell(data, result, client, continuation, spec)["status"] == "assessed"
    return data, result, client, continuation, spec


@pytest.mark.parametrize("defect", ["pending_route", "rejected_route", "wrong_edge", "wrong_tray", "unfinished", "censored", "stock", "missing_choice"])
def test_repaired_contract_still_fails_closed(monkeypatch, defect):
    args = sample(monkeypatch)
    data, result, client, continuation, spec = args
    if defect == "pending_route": client.rows["route0"]["ack"] = {}
    elif defect == "rejected_route": client.rows["route0"]["ack"]["status"] = "rejected"
    elif defect == "wrong_edge": result["receipts"][-1]["to"] = 8
    elif defect == "wrong_tray": result["receipts"][-2]["tray_id"] = "E"
    elif defect == "unfinished": result["jobs"][0]["completed_at"] = -1.
    elif defect == "censored": result["advance"]["horizon_complete"] = False
    elif defect == "stock": result["trays"].append({"tray_id": "extra"})
    else: continuation["route_choices"].pop()
    assert study.assess_cell(*args)["status"] == "unknown_incomplete_or_unexecuted"


def test_strict_protection_rejects_tiny_positive_delta(monkeypatch):
    summary = study.assess_cell(*sample(monkeypatch))
    row = {"summary": summary, "status": "assessed", "initial_next": 1, "departure": .11, "later_mode": "adaptive"}
    other = copy.deepcopy(row)
    other["summary"]["completion"]["loaded"] += 1e-12
    result = study.assess_domain({"baseline": row, "other": other}, row, {"baseline", "other"})
    assert not result["cells"]["other"]["all_offered_protected"]
    result = study.assess_domain({"baseline": row}, row, {"baseline", "other"})
    assert result["status"] == "unknown_incomplete_domain" and result["protected_gain_seconds"] is None


def test_saved117_native_cells_reassess_and_retain_negative_causal_result():
    import os
    from pathlib import Path
    from scripts.experiments.g31_ics_circulation.verify_synthetic_reuse_v2 import verify
    root = Path(__file__).resolve().parents[1]
    configured = os.environ.get("G31_REUSE_V2_EVIDENCE")
    if not configured:
        pytest.skip("Set G31_REUSE_V2_EVIDENCE to explicitly reassess the frozen117 native branches")
    evidence = Path(configured)
    assert evidence.is_dir(), "Configured frozen117 native campaign must exist"
    report = verify(evidence, root / "outputs/experiments/g31_ics_lt2_20261014/synthetic_reuse_chain_003")
    assert report["native_branch_count"] == 117
    assert report["retained_and_recovered_receiving_full_rejections"] == 36
    assert report["supply_recovery_branch_count"] == 30
    assert report["protected_adaptive_cells_with_later_bypass8"] == []
    assert all(all(row[field] for field in ("jobs", "trays", "transfers", "leg_identities"))
               for row in report["old24_physical_comparisons"].values())
    assert sum(all(row.values()) for row in report["old24_physical_comparisons"].values()) == 23
    for cell in report["causal_ablations"]:
        if cell["initial_next"] == 2:
            assert set(cell["adaptive_minus_ablation_per_job_seconds"].values()) == {0.}
        elif cell["gate"] == 6.:
            assert cell["adaptive_minus_ablation_per_job_seconds"]["receiver"] == pytest.approx(-.81)
            assert not cell["adaptive_protected"] and not cell["ablation_protected"]
