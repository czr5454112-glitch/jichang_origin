"""Assessor guards and read-only checks of saved native reuse-chain evidence."""
import copy
import gzip
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import research_synthetic_reuse_chain as study


def test_gate_changes_only_declared_release_field():
    scenes = [study.scene(gate) for gate in study.GATES]
    assert study.GATES == (0., 6., 12.)
    assert study.protocol()["branch_budget"] == 24
    for data in scenes:
        assert len(data["trays"]) == 2 and len(data["jobs"]) == 4
        assert all(job["arrival"] <= study.START for job in data["jobs"])
        assert next(n for n in data["node_contracts"] if n["node"] == 4)["allow_export"] is False
        data["jobs"][0]["storage_release_at"] = 0.
    assert scenes[0] == scenes[1] == scenes[2]


def test_candidate_windows_do_not_read_job_outcomes_or_private_loading():
    data = study.scene(0.)
    windows = study.departure_windows(data)
    data["jobs"] = [{"load_seconds": 999., "completed_at": -1}]
    assert study.departure_windows(data) == windows
    assert windows == pytest.approx((.11, 2.21, 3.11, 6.11))


def test_latest_withdrawal_never_resurrects_older_forecast_and_view_is_read_only():
    data = study.scene(0.)
    view = {"now": 5., "node_records": data["node_records"], "edge_records": data["edge_records"],
        "delivered_messages": [
            {"kind": "service_forecast", "tray_id": "E", "next": 3, "status": "conditional",
             "message_id": "old", "observed_at": 1., "publication_sequence": 1, "entry_estimate": 6., "release_estimate": 8.},
            {"kind": "service_forecast", "tray_id": "E", "next": 3, "status": "conditional",
             "message_id": "new", "observed_at": 2., "publication_sequence": 2, "entry_estimate": 6., "release_estimate": 8.}]}
    assert study.later_route(view, {})[0] == 8
    view["delivered_messages"].append({"kind": "service_forecast", "tray_id": "E", "next": 3,
        "status": "withdrawn", "supersedes": "new"})
    before = copy.deepcopy(view)
    assert study.later_route(view, {}) == (3, [])
    assert view == before


def sample(monkeypatch):
    monkeypatch.setattr(study, "audit_result", lambda *_: {"status": "passed"})
    data = study.scene(0.)
    client = SimpleNamespace(rows={str(i): {"kind": "transfer", "ack": {"status": "received"}} for i in range(3)}, calls=[])
    continuation = {"status": "finished", "returns": [], "route_choices": [
        {"job": "reuse1", "next": 3}, {"job": "reuse2", "next": 3}]}
    receipts = [{"event": "EDGE_ENTER", "tray_id": "L", "business_bag_id": "loaded", "from": 0, "to": 1}]
    for i, job in enumerate(("reuse1", "reuse2")):
        receipts.extend([
            {"event": "EMPTY_RECEIVED", "tray_id": "L", "node": 7, "time": 10 + i * 5},
            {"event": "LOAD_START", "tray_id": "L", "business_bag_id": job, "time": 10 + i * 5},
            {"event": "EDGE_ENTER", "tray_id": "L", "business_bag_id": job, "from": 7, "to": 3}])
    result = {"advance": {"status": "reached", "horizon_complete": True},
        "jobs": [{"business_bag_id": j["business_bag_id"], "completed_at": 20.} for j in data["jobs"]], "receipts": receipts}
    assert study.assess_cell(data, result, client, continuation, 1)["status"] == "assessed"
    return data, result, client, continuation


@pytest.mark.parametrize("defect", ["duplicate", "missing", "infinite", "after_horizon", "censored", "audit_failed", "audit_exception", "missing_later_decision", "wrong_tray"])
def test_invalid_evidence_cannot_be_assessed(monkeypatch, defect):
    data, result, client, continuation = sample(monkeypatch)
    if defect == "duplicate":
        result["jobs"].append(copy.deepcopy(result["jobs"][0]))
    elif defect == "missing":
        result["jobs"].pop()
    elif defect == "infinite":
        result["jobs"][0]["completed_at"] = float("inf")
    elif defect == "after_horizon":
        result["jobs"][0]["completed_at"] = study.HORIZON + 1
    elif defect == "censored":
        result["advance"]["horizon_complete"] = False
    elif defect == "audit_failed":
        monkeypatch.setattr(study, "audit_result", lambda *_: {"status": "failed"})
    elif defect == "audit_exception":
        def broken_audit(*_):
            raise AssertionError("malformed receipt")
        monkeypatch.setattr(study, "audit_result", broken_audit)
    elif defect == "missing_later_decision":
        continuation["route_choices"].pop()
    else:
        next(r for r in result["receipts"] if r["event"] == "LOAD_START")["tray_id"] = "E"
    assert study.assess_cell(data, result, client, continuation, 1)["status"].startswith("unknown")


@pytest.mark.parametrize("defect", ["missing_cell", "wrong_key", "unresolved_cell"])
def test_incomplete_domain_has_no_named_exact_reference(monkeypatch, defect):
    args = sample(monkeypatch)
    row = study.assess_cell(*args, 1)
    cells = {f"route{r}_window{w}": copy.deepcopy(row) for r in (1, 2) for w in range(4)}
    if defect == "missing_cell":
        cells.pop("route2_window3")
    elif defect == "wrong_key":
        cells["other_cell"] = cells.pop("route2_window3")
    else:
        cells["route2_window3"]["status"] = "unknown"
    report = study.assess_regime(cells)
    assert report["status"] == "unknown_incomplete_domain"
    assert report["B5_best_protected_enumerated_initial_decision"] is None
    assert report["B2_like_best_protected_fixed_initial_suffix"] is None
    assert report["predeclared_factorial_kappa_seconds"] is None


def test_strict_zero_protection_rejects_even_tiny_positive_regression(monkeypatch):
    row = study.assess_cell(*sample(monkeypatch), 1)
    cells = {f"route{r}_window{w}": copy.deepcopy(row) for r in (1, 2) for w in range(4)}
    cells["route2_window0"]["completion"]["receiver"] += 1e-12
    cells["route2_window0"]["completion_sum"] += 1e-12
    report = study.assess_regime(cells)
    assert report["cells"]["route1_window1"]["all_offered_protected"]
    assert not report["cells"]["route2_window0"]["all_offered_protected"]


@pytest.mark.skipif(not os.environ.get("G31_REUSE_CHAIN_EVIDENCE"), reason="explicit saved evidence path required; no native branch is launched")
def test_saved_native_all_cells_reassess_and_keep_negative_regimes():
    directory = Path(os.environ["G31_REUSE_CHAIN_EVIDENCE"])
    original = json.loads((directory / "receipt.json").read_text(encoding="utf-8"))
    assert original["status"] == "executed" and not original["source_changed"]
    reports = []
    for gate in study.GATES:
        sub = directory / f"gate{int(gate)}"
        data = json.loads((sub / "input.json").read_text(encoding="utf-8"))
        cells = {}
        for route in (1, 2):
            for window in range(4):
                key = f"route{route}_window{window}"
                with gzip.open(sub / f"{key}.json.gz", "rt", encoding="utf-8") as stream:
                    raw = json.load(stream)
                client = SimpleNamespace(rows=raw["outbox"], calls=raw["calls"])
                cells[key] = study.assess_cell(data, raw["result"], client, raw["continuation"], route)
                assert cells[key] == raw["summary"]
                for choice in raw["continuation"]["route_choices"]:
                    assert all(m["delivered_at"] <= choice["at"] for m in choice["delivered_forecasts"])
                for decision in raw["continuation"]["returns"]:
                    assert decision["delivered_demand"]["delivered_at"] <= decision["at"]
                immutable = {}
                for call in raw["calls"]:
                    identity = call["request"]["request_id"]
                    assert immutable.setdefault(identity, call["request"]) == call["request"]
        assessed = study.assess_regime(cells)
        expected = copy.deepcopy(original["regimes"][str(gate)])
        expected.pop("checkpoint_identity")
        assert assessed == expected
        reports.append(assessed)
    assert [r["protected_joint_gain_over_best_fixed_seconds"] for r in reports] == pytest.approx((0., 1.41, 0.))
    assert [r["bidirectional_feedback_witness"] for r in reports] == [True, True, False]
