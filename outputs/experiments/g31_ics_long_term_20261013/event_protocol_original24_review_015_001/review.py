"""Independent read-only accounting of five frozen native015 policy runs."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "event_protocol_original24_015_001"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.load(gzip.open(path, "rt", encoding="utf-8")) if path.suffix == ".gz" else json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    if (HERE / "assessment.json").exists():
        raise ValueError("review:refusing_to_overwrite_assessment")
    receipt = read(SOURCE / "receipt.json")
    assert receipt["status"] == "executed_comparison_not_research_gate" and receipt["source_changed"] == []
    assert receipt["binary_sha256"] == "5919ed48a86aed8302f1c9a813574c161feac93600f998e89e5cdfd385bbc098"
    folder = SOURCE / "original24"
    data = read(folder / "input.json")
    business = {j["business_bag_id"]: j for j in data["jobs"]}
    permissions = [j["business_bag_id"] for j in data["jobs"] if j.get("allow_suffix_reroute", False)]
    assert len(business) == 24 and len(data["trays"]) == 1
    report = dict(schema="g31.event_original24_independent_review.v1", status="passed",
                  source_receipt_sha256=sha(SOURCE / "receipt.json"), input_sha256=sha(folder / "input.json"),
                  runner_sha256=sha(Path(__file__)), r1_allowed_business_ids=permissions, policies={}, pairs={},
                  scope="Offline audit of existing native events and delivered messages; no new native execution, causal ablation or optimality certification.")
    completions, physical = {}, {}
    for policy, declared in receipt["cases"]["original24"]["policies"].items():
        directory = folder / policy
        run = read(directory / "run.json.gz")
        ledger = read(directory / "request_ack_ledger.json.gz")
        views = read(directory / "delivered_views.json.gz")
        assert run["status"] == "reached" and declared["status"] == "verified_complete_execution"
        result, events = run["result"], run["result"]["receipts"]
        assert all(a["time"] <= b["time"] for a, b in zip(events, events[1:])), "physical receipt clock reversed"
        assert set(business) == {j["business_bag_id"] for j in result["jobs"]}
        completed = {j["business_bag_id"]: j["completed_at"] for j in result["jobs"]}
        assert all(t >= 0 for t in completed.values())
        completions[policy] = completed
        calls = {c["request"]["request_id"]: c for c in run["client_calls"] if not c["retry"]}
        acks = {r["request_id"]: r["last_delivered_ack"] for r in ledger["requests"]}
        transfers = {r["request_id"]: r for r in result["transfers"]}
        cycles = []
        for index, received in enumerate(events):
            if received["event"] != "EMPTY_RECEIVED":
                continue
            tray, identity = received["tray_id"], received["reason"]
            previous = next(e for e in reversed(events[:index]) if e["tray_id"] == tray and e["event"] == "UNLOAD_COMPLETE")
            hold = next(e for e in events[:index] if e["tray_id"] == tray and e["event"] == "HOLD_COMPLETE" and e["business_bag_id"] == previous["business_bag_id"])
            grant = next(e for e in events[:index] if e["event"] == "EXPORT_GRANTED" and e["reason"] == identity)
            edges = [e for e in events[:index] if e["event"] == "EDGE_ENTER" and e["transport_leg_id"] == received["transport_leg_id"]]
            loaded = next(e for e in events[index+1:] if e["tray_id"] == tray and e["event"] == "LOAD_START")
            unloaded = next(e for e in events[index+1:] if e["tray_id"] == tray and e["event"] == "UNLOAD_COMPLETE" and e["business_bag_id"] == loaded["business_bag_id"])
            call, ack = calls[identity], acks[identity]
            assert previous["time"] <= hold["time"] <= grant["time"] <= edges[0]["time"] <= received["time"] <= loaded["time"] <= unloaded["time"]
            assert hold["time"] >= previous["time"] + business[previous["business_bag_id"]]["hold_seconds"]
            assert grant["tray_id"] == call["request"]["tray_id"] == tray
            assert ack["status"] == transfers[identity]["status"] == "received"
            assert ack["received_at"] == transfers[identity]["received_at"] == received["time"]
            assert ack["delivered_at"] >= received["time"]
            assert edges[0]["from"] == previous["node"] and edges[-1]["to"] == loaded["node"]
            cycles.append(dict(request_id=identity, tray_id=tray, previous_bag=previous["business_bag_id"], next_bag=loaded["business_bag_id"],
                requested_at=call["at"], supply_ledger=call["request"].get("forecast_ledger"), unload_at=previous["time"],
                hold_complete_at=hold["time"], export_at=grant["time"], departure_at=edges[0]["time"],
                received_at=received["time"], ack_at=ack["delivered_at"], next_load_at=loaded["time"], next_unload_at=unloaded["time"],
                empty_transport_leg_id=received["transport_leg_id"], empty_traversal_ids=[e["traversal_id"] for e in edges]))
        assert len(cycles) == 23 and len({c["request_id"] for c in cycles}) == 23
        assert {c["tray_id"] for c in cycles} == {data["trays"][0]["tray_id"]}
        messages = {m["message_id"]: m for v in views.values() for m in v["delivered_messages"] if m["kind"] == "service_forecast"}
        forecasts = []
        for request in ledger["requests"]:
            if request["kind"] != "service_forecast":
                continue
            ack = request["last_delivered_ack"] or {}
            row = dict(request_id=request["request_id"], status=ack.get("status", "unknown"), reason=ack.get("reason", "unknown"))
            if row["status"] == "delivered":
                message = messages[ack["result_id"]]
                assert message["observed_at"] == ack["executed_at"]
                assert message["observed_at"] <= message["delivered_at"] <= ack["delivered_at"]
                entry = next((e for e in events if e["event"] == "EDGE_ENTER" and e["tray_id"] == message["tray_id"]
                    and e["business_bag_id"] == message["business_bag_id"] and e["from"] == message["from"]
                    and e["time"] >= message["observed_at"]), None)
                row.update(message_id=message["message_id"], observed_at=message["observed_at"], delivered_at=message["delivered_at"],
                           entry_estimate=message["entry_estimate"], release_estimate=message["release_estimate"],
                           actual_entry=entry, next_matches_actual=bool(entry and entry["to"] == message["next"]),
                           delivered_strictly_before_actual_entry=bool(entry and message["delivered_at"] < entry["time"]),
                           estimated_window_expired_at_delivery=message["release_estimate"] <= message["delivered_at"],
                           entry_error=message["entry_estimate"]-entry["time"] if entry else None)
            forecasts.append(row)
        cost = sum(completed[k]-business[k]["arrival"] for k in business)
        assert abs(cost-declared["metrics"]["cost"]) <= 1e-7
        route_count = sum(c["kind"] == "route" for c in calls.values())
        assert permissions or route_count == 0
        physical_rows = [{k: e[k] for k in ("time", "event", "tray_id", "business_bag_id", "node", "from", "to") if k in e}
                         for e in events if e["event"] in {"LOAD_START", "UNLOAD_COMPLETE", "HOLD_COMPLETE", "EDGE_ENTER", "EDGE_EXIT", "EMPTY_RECEIVED"}]
        physical[policy] = hashlib.sha256(json.dumps(physical_rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        report["policies"][policy] = dict(run_sha256=sha(directory/"run.json.gz"), ledger_sha256=sha(directory/"request_ack_ledger.json.gz"),
            raw_receipts_monotonic=True, completed=24, verified_same_tray_reuse_cycles=23, cycles=cycles, route_requests=route_count,
            source_ledger_counts=dict(Counter(c["supply_ledger"] for c in cycles)),
            requests_before_real_unload=sum(c["requested_at"] < c["unload_at"] for c in cycles),
            forecast_status_counts=dict(Counter(f["status"] for f in forecasts)),
            forecast_rejection_reasons=dict(Counter(f["reason"] for f in forecasts if f["status"] == "rejected")),
            forecasts_delivered_before_actual_entry=sum(f.get("delivered_strictly_before_actual_entry", False) for f in forecasts),
            forecasts_expired_at_delivery=sum(f.get("estimated_window_expired_at_delivery", False) for f in forecasts),
            forecasts_next_mismatch=sum(not f["next_matches_actual"] for f in forecasts if f["status"] == "delivered"),
            forecasts=forecasts, independently_recomputed_cost=cost, physical_sha256=physical[policy])
    for candidate, baseline in (("event_reactive", "periodic_reactive"), ("event_predictive", "periodic_predictive"),
                                ("event_predictive", "event_reactive"), ("event_joint", "event_predictive")):
        differences = {k: completions[candidate][k]-completions[baseline][k] for k in business}
        report["pairs"][candidate+"__vs__"+baseline] = dict(cost_delta=sum(differences.values()),
            strictly_faster=sum(d < -1e-7 for d in differences.values()), strictly_slower=sum(d > 1e-7 for d in differences.values()),
            same_physical_events=physical[candidate] == physical[baseline], per_bag_completion_delta=differences)
    (HERE/"assessment.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps(dict(status=report["status"], policies={name:{k:v for k,v in row.items() if k not in ("cycles","forecasts")}
        for name,row in report["policies"].items()}, pairs={name:{k:v for k,v in row.items() if k!="per_bag_completion_delta"}
        for name,row in report["pairs"].items()}), ensure_ascii=False))


if __name__ == "__main__":
    main()
