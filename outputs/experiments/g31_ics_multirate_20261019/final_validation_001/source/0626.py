"""Actual native transfer/ACK fault ledger, with business and checkpoint audit.

This validates an opt-in transfer subprotocol. It is not an R1/R2 controller
integration, external-network deployment, or a complete 100ms certificate.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import time
import traceback

from .native_host import audit_result, load_native, tiny_cycle
from .original_workload import write_json


SPECS = [
    {"name": "ordinary", "protocol": {}, "retry_at": []},
    {"name": "lost_first_ack", "protocol": {"drop_ack_packets": 1}, "retry_at": [11.]},
    {"name": "lost_ack_late_retry", "protocol": {"drop_ack_packets": 1}, "retry_at": [65.]},
    {"name": "duplicate_ack", "protocol": {"duplicate_acks": True, "duplicate_ack_delay": 5.}, "retry_at": [11.]},
    {"name": "source_unavailable", "protocol": {"owner_outages": [{"owner": "B", "start": 9., "end": 20.}]}, "retry_at": [11.]},
    {"name": "receiver_unavailable", "protocol": {"owner_outages": [{"owner": "A", "start": 9., "end": 20.}]}, "retry_at": [11.]},
    {"name": "adjacent_outages", "protocol": {"owner_outages": [
        {"owner": "A", "start": 9., "end": 20.}, {"owner": "A", "start": 20., "end": 30.}]}, "retry_at": [11.]},
    {"name": "inflight_commitment", "protocol": {"owner_outages": [
        {"owner": "A", "start": 10.2, "end": 40.}, {"owner": "B", "start": 10.2, "end": 40.}]}, "retry_at": []},
    {"name": "duplicate_wire_on_recovery", "protocol": {"owner_outages": [
        {"owner": "A", "start": 9., "end": 20.}]}, "retry_at": [19.8, 19.8], "message_delay": .2},
    {"name": "refusal_ack_lost", "protocol": {"drop_ack_packets": 1}, "retry_at": [11.], "receiver_refuses": True},
]


def execute(native, spec: dict, folder: Path) -> dict:
    data = tiny_cycle()
    data["transfers"] = []
    data["owner_protocol"] = {"enabled": True, "timeout": .5, "ack_delay": .2, **spec["protocol"]}
    if spec.get("receiver_refuses"):
        next(n for n in data["node_contracts"] if n["node"] == 0)["allow_receive"] = False
    request = {"request_id": "live:1:B:ledger-return", "owner_id": "B", "tray_id": "T0", "source": 4,
               "destination": 0, "earliest_departure": 10., "expiry": 60., "message_delay": spec.get("message_delay", 0.)}
    folder.mkdir()
    write_json(folder/"input.json", data)
    write_json(folder/"request.json", request)
    session = native.NativeSession(data)
    calls = []

    def advance(target):
        reply = session.advance_to(target)
        if reply["status"] != "reached" or not reply["horizon_complete"]:
            raise AssertionError({"incomplete_protocol_prefix": reply})

    def submit(kind):
        started = time.perf_counter()
        reply = session.submit_protocol_transfer(request)
        calls.append({"time": session.physical_time, "kind": kind, "reply": reply,
                      "submit_call_ms": 1000*(time.perf_counter()-started),
                      "client_view": session.protocol_request("B", request["request_id"])})
        assert reply["status"] == "pending", reply

    advance(10.)
    submit("initial")
    # The same-ID retries are actual client actions, never a new empty order.
    for target in spec["retry_at"]:
        advance(target)
        calls.append({"time": target, "kind": "before_retry",
                      "client_view": session.protocol_request("B", request["request_id"])})
        submit("retry_same_payload")
    boundary = session.physical_time
    checkpoint = session.checkpoint()
    checkpoint_hash = session.offline_state_sha256()
    branch = session.fork()
    restored = native.NativeSession(data)
    restored.restore(checkpoint)
    assert branch.offline_state_sha256() == restored.offline_state_sha256() == checkpoint_hash
    result = session.result_at(70.)
    assert result["advance"]["status"] == "reached" and result["advance"]["horizon_complete"]
    siblings = [branch.result_at(70.), restored.result_at(70.)]
    for other in siblings:
        for key in ("jobs", "trays", "receipts", "transfers", "leg_identities"):
            assert result[key] == other[key], (spec["name"], key)
    view = session.observe_protocol("B")
    assert view == branch.observe_protocol("B") == restored.observe_protocol("B")
    assert session.offline_state_sha256() == branch.offline_state_sha256() == restored.offline_state_sha256()
    replay = copy.deepcopy(data)
    replay["transfers"] = [{**request, "issued_at": 10.}]
    audit = audit_result(replay, result)
    assert audit["status"] == "passed", audit
    assert len(result["transfers"]) == 1
    grants = [r for r in result["receipts"] if r["event"] == "EXPORT_GRANTED"]
    assert len(grants) <= 1
    if spec.get("receiver_refuses"):
        assert result["transfers"][0]["status"] == "rejected"
        assert not grants
    else:
        assert result["transfers"][0]["status"] == "received"
        assert len(grants) == 1
        assert all(job["status"] == "completed" for job in result["jobs"])
    for grant in grants:
        assert not any(o["start"] <= grant["time"] < o["end"] for o in spec["protocol"].get("owner_outages", []))
    if spec["name"] == "inflight_commitment":
        assert result["transfers"][0]["received_at"] < 40.
    final_client = session.protocol_request("B", request["request_id"])
    assert final_client["status"] == "acknowledged", final_client
    if spec["name"] == "duplicate_wire_on_recovery":
        assert final_client["attempt"] == 3
        assert any(ack["attempt"] == 3 for ack in view["delivered_transfer_acks"])
        # Emission sequence orders snapshots, independently of retry attempt.
        # A response to an older attempt can be emitted later at recovery.
        assert final_client["last_delivered_ack"]["sequence"] == max(
            ack["sequence"] for ack in view["delivered_transfer_acks"])
    rows = [r for r in result["receipts"] if r["event"].startswith("PROTOCOL_") or r["event"] in (
        "MODULE_REQUEST_DELIVERED", "EXPORT_GRANTED", "TRANSFER_REJECTED", "EMPTY_DEPARTED", "EMPTY_RECEIVED",
        "LOAD_START", "UNLOAD_COMPLETE", "HOLD_COMPLETE")]
    write_json(folder/"event_ledger.json", rows)
    write_json(folder/"client_calls.json", calls)
    write_json(folder/"audit.json", audit)
    with gzip.open(folder/"native_result.json.gz", "wt", encoding="utf-8") as stream:
        json.dump(result, stream)
    write_json(folder/"delivered_client_view.json", view)
    return {"name": spec["name"], "status": "passed", "offered": len(data["jobs"]),
            "completed": sum(j["status"] == "completed" for j in result["jobs"]),
            "transfer_status": result["transfers"][0]["status"], "grant_count": len(grants),
            "client_status": final_client["status"], "client_attempts": final_client["attempt"],
            "checkpoint_boundary": boundary, "checkpoint_sha256": checkpoint_hash,
            "fork_and_restore_full_future_equal": True, "audit": audit,
            "event_ledger_sha256": hashlib.sha256((folder/"event_ledger.json").read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = Path(__file__)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    receipt = {"schema": "g31.owner_protocol_execution.v1", "status": "running", "cases": [],
               "binary_sha256": hashlib.sha256(args.binary.read_bytes()).hexdigest(),
               "source_before": before, "complete_100ms_certified": False,
               "scope": "transfer-only native protocol with explicit fault contract; no R1/R2 protocol integration or field failure model claim"}
    write_json(args.output/"protocol.json", {"scenarios": SPECS, "horizon": 70., "physics": "single mature native G31"})
    write_json(args.output/"receipt.json", receipt)
    started = time.perf_counter()
    try:
        native = load_native(args.binary)
        for spec in SPECS:
            receipt["cases"].append(execute(native, spec, args.output/spec["name"]))
            write_json(args.output/"receipt.json", receipt)
        receipt["status"] = "passed"
    except Exception:
        receipt["status"] = "failed"
        receipt["exception"] = traceback.format_exc()
    receipt["source_after"] = hashlib.sha256(source.read_bytes()).hexdigest()
    receipt["source_changed"] = [] if receipt["source_after"] == before else [str(source)]
    receipt["wall_seconds"] = time.perf_counter()-started
    write_json(args.output/"receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "cases": len(receipt["cases"]),
                      "source_changed": receipt["source_changed"]}, indent=2))
    return int(receipt["status"] != "passed" or bool(receipt["source_changed"]))


if __name__ == "__main__":
    raise SystemExit(main())
