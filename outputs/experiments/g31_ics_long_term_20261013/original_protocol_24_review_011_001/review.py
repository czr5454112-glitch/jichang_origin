"""Read-only event extraction from frozen protocol receipts; no native calls."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).parent
SOURCE = HERE.parent / "original_protocol_24_011_001"
BUDGET = HERE.parent / "original_protocol_24_budget_011_001"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_gz(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


receipt = json.loads((SOURCE / "receipt.json").read_text(encoding="utf-8"))
data = json.loads((SOURCE / "input.json").read_text(encoding="utf-8"))
result = {"schema": "g31.original_protocol_postrun_event_review.v1",
          "scope": "offline extraction of already executed receipts; no controller input or causal intervention",
          "source_receipt_sha256": sha(SOURCE / "receipt.json"),
          "review_source_sha256": sha(Path(__file__)), "cases": {}}
for name in receipt["cases"]:
    directory = SOURCE / name
    run = read_gz(directory / "run.json.gz")
    ledger = read_gz(directory / "request_ack_ledger.json.gz")
    events = run["result"]["receipts"]
    requests = {c["request"]["request_id"]: c for c in run["client_calls"] if not c["retry"]}
    acks = {r["request_id"]: r["last_delivered_ack"] for r in ledger["requests"]}
    physical = {r["request_id"]: r for r in run["result"]["transfers"]}
    cycles = []
    for index, empty in enumerate(events):
        if empty["event"] != "EMPTY_RECEIVED":
            continue
        request_id, tray = empty["reason"], empty["tray_id"]
        previous = next(e for e in reversed(events[:index]) if e["event"] == "UNLOAD_COMPLETE" and e["tray_id"] == tray)
        hold = next(e for e in events[:index] if e["event"] == "HOLD_COMPLETE" and e["tray_id"] == tray and e["business_bag_id"] == previous["business_bag_id"])
        grant = next(e for e in events[:index] if e["event"] == "EXPORT_GRANTED" and e["reason"] == request_id)
        load = next(e for e in events[index+1:] if e["event"] == "LOAD_START" and e["tray_id"] == tray)
        unload = next(e for e in events[index+1:] if e["event"] == "UNLOAD_COMPLETE" and e["tray_id"] == tray and e["business_bag_id"] == load["business_bag_id"])
        edges = [e for e in events[:index] if e["event"] == "EDGE_ENTER" and e["transport_leg_id"] == empty["transport_leg_id"]]
        request, ack, transfer = requests[request_id], acks[request_id], physical[request_id]
        assert previous["time"] <= hold["time"] <= grant["time"] <= edges[0]["time"] <= empty["time"] <= load["time"] <= unload["time"]
        assert grant["tray_id"] == tray and request["request"]["tray_id"] == tray
        assert ack["status"] == transfer["status"] == "received"
        assert ack["received_at"] == transfer["received_at"] == empty["time"]
        assert ack["delivered_at"] >= empty["time"]
        assert edges[0]["from"] == previous["node"] and edges[-1]["to"] == load["node"]
        cycles.append({"tray_id": tray, "request_id": request_id,
            "previous_business_bag_id": previous["business_bag_id"], "next_business_bag_id": load["business_bag_id"],
            "request_issued_at": request["at"], "forecast_ledger": request["request"]["forecast_ledger"],
            "unload_at": previous["time"], "hold_complete_at": hold["time"], "export_granted_at": grant["time"],
            "empty_departure_at": edges[0]["time"], "empty_received_at": empty["time"],
            "received_ack_delivered_at": ack["delivered_at"], "next_load_at": load["time"], "next_unload_at": unload["time"],
            "empty_transport_leg_id": empty["transport_leg_id"],
            "empty_edges": [{k: e[k] for k in ("time", "from", "to", "traversal_id")} for e in edges]})
    assert len(cycles) == len(data["jobs"])-1
    assert len({r["request_id"] for r in cycles}) == len(cycles)
    assert {r["tray_id"] for r in cycles} == {data["trays"][0]["tray_id"]}
    forecasts = [r for r in ledger["requests"] if r["kind"] == "service_forecast"]
    result["cases"][name] = {"source_run_sha256": sha(directory / "run.json.gz"),
        "source_ledger_sha256": sha(directory / "request_ack_ledger.json.gz"),
        "verified_reuse_cycles": len(cycles), "cycles": cycles,
        "request_supply_ledger_counts": dict(Counter(r["forecast_ledger"] for r in cycles)),
        "requests_before_previous_actual_unload": sum(r["request_issued_at"] < r["unload_at"] for r in cycles),
        "grant_before_previous_hold_complete": sum(r["export_granted_at"] < r["hold_complete_at"] for r in cycles),
        "service_forecast_ack_reasons": dict(Counter((r["last_delivered_ack"] or {}).get("reason", "unknown") for r in forecasts)),
        "r1_permission_count": len(receipt["r1_original_permissions"]["allowed_business_ids"]),
        "r1_request_count": receipt["cases"][name]["r1_requested"],
        "metrics": {k: v for k, v in receipt["cases"][name]["metrics"].items() if k != "per_job"}}
result["paired"] = {name: {"preserved": c["preserved"], "denominator": c["denominator"],
    "cost_delta": c["cost_delta"], "strictly_faster": sum(p["restricted_time_delta"] < -1e-7 for p in c["per_job"]),
    "strictly_slower": sum(p["restricted_time_delta"] > 1e-7 for p in c["per_job"])}
    for name, c in receipt["paired_comparisons"].items()}
budget = json.loads((BUDGET / "receipt.json").read_text(encoding="utf-8"))
result["budget_negative_control"] = {"source_receipt_sha256": sha(BUDGET / "receipt.json"), "cases": {}}
for name, row in budget["cases"].items():
    run = read_gz(BUDGET / name / "run.json.gz")
    assert row["status"] == "unknown" and row["metrics"] is None and row["declared_offered"] == len(data["jobs"])
    assert row["final_diagnostics_status"] == "not_read_incomplete_execution"
    assert run["status"] == "budget_exhausted" and run["result"] is None
    assert not run["controller_state"]["control_boundary_complete"] and len(run["segments"]) == 1
    result["budget_negative_control"]["cases"][name] = {"status": row["status"], "metrics": None,
        "declared_offered": row["declared_offered"], "physical_time": run["control_continuation"]["physical_time"],
        "segments_attempted": len(run["segments"]), "partial_tick_was_resumed": False,
        "source_run_sha256": sha(BUDGET / name / "run.json.gz")}
result["interpretation"] = [
    "The predictive analytic baseline uses local conditional release requests, but actual grants follow unload and hold.",
    "All service-forecast publications in this run were rejected; no gain can be credited to delivered resource windows.",
    "Joint matches predictive with zero original R1 permissions, so this is not evidence of a joint R1/R2 method increment.",
    "All 24 complete, but 19 violate deadlines; no global feasibility, original fleet sufficiency, optimality or 100ms claim."]
(HERE / "assessment.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
print(json.dumps({"cases": {n: {k: v for k, v in r.items() if k not in ("cycles", "metrics")} for n, r in result["cases"].items()},
                  "paired": result["paired"], "budget": result["budget_negative_control"]}, ensure_ascii=False))
