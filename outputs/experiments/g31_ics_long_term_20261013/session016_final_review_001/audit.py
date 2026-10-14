"""Read existing receipts and raw runs only; no native execution or source edit."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ROOT = BASE.parents[2]
CURRENT = BASE / "event_protocol_original24_016_001"
OLD = BASE / "event_protocol_original24_015_001"
LIVE = BASE / "live_validation_012"
COMPARISON = BASE / "event_protocol_015_016_comparison_001"
TIMERS = {"compute_cpu_ms", "compute_ms", "compute_wall_ms", "cpu_ms", "native_event_ms",
          "preparation_compute_ms", "submit_compute_ms", "wall_ms", "wall_seconds"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.load(gzip.open(path, "rt", encoding="utf-8")) if path.suffix == ".gz" else json.loads(path.read_text(encoding="utf-8-sig"))


def normalize(value):
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items() if k not in TIMERS}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    return value


def snapshot_check(mapping):
    return {"files": len(mapping), "mismatches": [p for p, digest in mapping.items() if sha(ROOT / p) != digest]}


def main():
    if (HERE / "assessment.json").exists():
        raise ValueError("independent audit refuses to overwrite prior evidence")
    current, old, live, comparison = map(read, [CURRENT / "receipt.json", OLD / "receipt.json", LIVE / "receipt.json", COMPARISON / "assessment.json"])
    build_path = ROOT / live["build_receipt"]
    build = read(build_path)
    binary = Path(live["binary"])
    report = {"schema": "g31.session016_independent_final_review.v1", "scope": "Read-only raw evidence audit; no native simulation, pytest rerun, or full-repository validation.",
              "runner_sha256": sha(Path(__file__)), "source_changed_claims": {"campaign": current["source_changed"], "regression": live["source_changed"], "build": build["source_changed"]},
              "receipt_sha256": {str(p.relative_to(BASE)): sha(p) for p in [CURRENT / "receipt.json", OLD / "receipt.json", LIVE / "receipt.json", COMPARISON / "assessment.json", build_path]},
              "binary": {"path": str(binary), "actual_sha256": sha(binary), "campaign_sha256": current["binary_sha256"], "regression_sha256": live["binary_sha256"]},
              "current_source_checks": {"campaign": snapshot_check(current["source_after"]), "regression": snapshot_check(live["source_after"]), "build": snapshot_check(build["source_after"])}}
    assert current["status"] == old["status"] == "executed_comparison_not_research_gate"
    assert live["status"] == build["status"] == comparison["status"] == "passed"
    assert all(not v for v in report["source_changed_claims"].values())
    assert all(not v["mismatches"] for v in report["current_source_checks"].values())
    assert report["binary"]["actual_sha256"] == current["binary_sha256"] == live["binary_sha256"]
    assert live["binary_sha256"] in build["binary_sha256"].values()
    assert sha(build_path) == live["build_receipt_sha256"]
    assert [sha(OLD / "receipt.json"), sha(CURRENT / "receipt.json")] == comparison["receipt_sha256"]
    assert sha(COMPARISON / "compare.py") == comparison["runner_sha256"]
    assert not live["compiled_source_mismatch"]
    cases = ET.parse(LIVE / "junit.xml").findall(".//testcase")
    counts = dict(tests=len(cases), failures=sum(c.find("failure") is not None for c in cases), errors=sum(c.find("error") is not None for c in cases), skipped=sum(c.find("skipped") is not None for c in cases))
    assert counts == live["counts"] == {"tests": 407, "failures": 0, "errors": 0, "skipped": 0}
    identity = [c.get("name") for c in cases if c.get("classname", "").endswith("test_g31_circulation_native_identity")]
    history = [c.get("name") for c in cases if c.get("name", "").startswith("test_historical_epsilon_order_scope")]
    assert len(identity) == 5 and len(history) == 1
    assert live["native_identity_regression"]["test_names"] == identity
    assert live["native_identity_regression"]["test_count"] == 5
    assert live["historical_order_regression"]["test_names"] == history
    assert live["current_native_and_python_test_count"] == 401
    report["regression"] = {"counts": counts, "files": len(live["test_files"]), "identity_cases_using_pinned_011_015": identity,
                            "historical_011_cases": history, "remaining_current_native_or_python_cases": 401,
                            "prior_wording_issue_corrected": "live011 had an overly broad all-other-native scope sentence. live012 reran the suite and explicitly lists the five pinned011/015 identity cases, one historical011 witness and401 current-native-or-Python cases. live011 remains unchanged.",
                            "prior_live011_receipt_sha256": sha(BASE / "live_validation_011/receipt.json")}
    assert (CURRENT / "original24/input.json").read_bytes() == (OLD / "original24/input.json").read_bytes()
    data = read(CURRENT / "original24/input.json")
    selection = read(CURRENT / "selection.json")
    jobs = {j["business_bag_id"]: j for j in data["jobs"]}
    assert len(jobs) == 24 and len(data["trays"]) == 1
    report["input_scope"] = {"offered": len(jobs), "trays": len(data["trays"]), "mother_offered": selection["mother_offered"],
                             "graph_nodes": selection["graph_nodes"], "graph_edges": selection["graph_edges"],
                             "suffix_reroute_authorized_jobs": sum(j.get("allow_suffix_reroute", False) for j in jobs.values()),
                             "selection_claim_boundary": selection["claim_boundary"], "input_sha256": sha(CURRENT / "original24/input.json")}
    report["policies"] = {}
    completions, event_signatures = {}, {}
    for policy, declared in current["cases"]["original24"]["policies"].items():
        directory = CURRENT / "original24" / policy
        run, prior = read(directory / "run.json.gz"), read(OLD / "original24" / policy / "run.json.gz")
        semantic_equal = normalize(run) == normalize(prior)
        assert semantic_equal
        assert declared["offline_final_state_sha256"] == old["cases"]["original24"]["policies"][policy]["offline_final_state_sha256"]
        result = run["result"]
        events = result["receipts"]
        assert all(a["time"] <= b["time"] for a, b in zip(events, events[1:]))
        completed = {j["business_bag_id"]: j["completed_at"] for j in result["jobs"] if j["status"] == "completed"}
        assert set(completed) == set(jobs)
        cost = sum(completed[k] - jobs[k]["arrival"] for k in jobs)
        assert abs(cost - declared["metrics"]["cost"]) < 1e-7
        late = [k for k in jobs if jobs[k]["deadline"] >= 0 and completed[k] > jobs[k]["deadline"]]
        assert len(late) == declared["metrics"]["deadline_violations"] == 19
        completions[policy] = completed
        cycle_count = 0
        for i, e in enumerate(events):
            if e["event"] != "EMPTY_RECEIVED":
                continue
            previous = next(r for r in reversed(events[:i]) if r["tray_id"] == e["tray_id"] and r["event"] == "UNLOAD_COMPLETE")
            hold = next(r for r in events[:i] if r["event"] == "HOLD_COMPLETE" and r["tray_id"] == e["tray_id"] and r["business_bag_id"] == previous["business_bag_id"])
            grant = next(r for r in events[:i] if r["event"] == "EXPORT_GRANTED" and r["reason"] == e["reason"])
            empty_edges = [r for r in events[:i] if r["event"] == "EDGE_ENTER" and r["transport_leg_id"] == e["transport_leg_id"]]
            load = next(r for r in events[i+1:] if r["event"] == "LOAD_START" and r["tray_id"] == e["tray_id"])
            assert previous["time"] + jobs[previous["business_bag_id"]]["hold_seconds"] <= hold["time"] <= grant["time"] <= empty_edges[0]["time"] <= e["time"] <= load["time"]
            assert empty_edges[0]["from"] == previous["node"] and empty_edges[-1]["to"] == load["node"]
            cycle_count += 1
        assert cycle_count == 23
        ledger = read(directory / "request_ack_ledger.json.gz")
        views = read(directory / "delivered_views.json.gz")
        messages = {m["message_id"]: m for v in views.values() for m in v["delivered_messages"]}
        forecasts = []
        for request in ledger["requests"]:
            if request["kind"] != "service_forecast":
                continue
            ack = request["last_delivered_ack"] or {}
            row = {"status": ack.get("status", "unknown"), "reason": ack.get("reason", "unknown")}
            if row["status"] == "delivered":
                msg = messages[ack["result_id"]]
                actual = next(r for r in events if r["event"] == "EDGE_ENTER" and r["tray_id"] == msg["tray_id"] and r["business_bag_id"] == msg["business_bag_id"] and r["from"] == msg["from"] and r["time"] >= msg["observed_at"])
                assert actual["to"] == msg["next"] and actual["time"] == msg["entry_estimate"]
                row.update(delivery_lag=msg["delivered_at"]-actual["time"], entry_error=msg["entry_estimate"]-actual["time"], message_id=msg["message_id"])
            forecasts.append(row)
        lags = [f["delivery_lag"] for f in forecasts if f["status"] == "delivered"]
        timers = [r["compute_wall_ms"] for r in run["control_records"] if "compute_wall_ms" in r]
        notices = [r for r in run["control_records"] if r.get("causes", {}).get("notification")]
        assert all(r["causes"]["notification"]["observed_at"] <= r["at"] for r in notices)
        physical = [{k: r[k] for k in ("time", "event", "tray_id", "business_bag_id", "node", "from", "to") if k in r} for r in events if r["event"] in {"LOAD_START", "UNLOAD_COMPLETE", "HOLD_COMPLETE", "EDGE_ENTER", "EDGE_EXIT", "EMPTY_RECEIVED"}]
        event_signatures[policy] = hashlib.sha256(json.dumps(physical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        report["policies"][policy] = {"semantic_equal_to_015_excluding_declared_timers": semantic_equal, "run_sha256": sha(directory / "run.json.gz"),
                                     "completed": len(completed), "late_count": len(late), "late_ids": late, "same_tray_reuse_cycles": cycle_count,
                                     "cost": cost, "forecast_status": dict(Counter(f["status"] for f in forecasts)),
                                     "forecast_rejection_reason": dict(Counter(f["reason"] for f in forecasts if f["status"] == "rejected")),
                                     "forecast_delivery_lag_min": min(lags, default=None), "forecast_delivery_lag_max": max(lags, default=None),
                                     "forecasts_delivered_before_actual_entry": sum(lag < 0 for lag in lags),
                                     "notification_activations_checked": len(notices), "observed_at_never_after_activation": True,
                                     "route_requests": sum(r["kind"] == "route" for r in ledger["requests"]),
                                     "owner_compute_samples": len(timers), "owner_compute_over_100ms": sum(t > 100 for t in timers), "owner_compute_max_ms": max(timers, default=None),
                                     "physical_sha256": event_signatures[policy]}
    report["pairs"] = {}
    for candidate, baseline in [("event_reactive", "periodic_reactive"), ("event_predictive", "periodic_predictive"), ("event_predictive", "event_reactive"), ("event_joint", "event_predictive")]:
        deltas = [completions[candidate][k] - completions[baseline][k] for k in jobs]
        report["pairs"][candidate + "__vs__" + baseline] = {"cost_delta": sum(deltas), "strictly_faster": sum(d < -1e-7 for d in deltas), "strictly_slower": sum(d > 1e-7 for d in deltas), "same_physical_events": event_signatures[candidate] == event_signatures[baseline]}
    report["open_gates"] = ["Full request 100ms remains uncertified, with observed owner-subtask violations; no controlled deployment measurement.",
                            "All 204 delivered next-node forecasts arrive 0.5s after actual entry; accurate time does not prove advance entry information or causal benefit.",
                            "24-job one-tray preselected mechanism witness, not the full 28,506-job mother or 2x workload; 19 jobs remain late.",
                            "No R1 suffix-reroute permission or route requests in this original witness; joint ties predictive and gives no joint-method increment.",
                            "Global optimality unknown; full-model strong-reference, normal-sort protection across the full offered set, novelty and learning gates remain open.",
                            "407 includes one historical011 witness and five native identity cases on pinned011/015; remaining401 combine current-native and Python-only checks, not all repository tests."]
    report["status"] = "passed_with_explicit_scope_limits"
    (HERE / "assessment.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("policies", "regression", "receipt_sha256")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
