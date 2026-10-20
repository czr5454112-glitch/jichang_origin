"""Budgeted native030 micro-gates; every constructor is journaled before entry."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation.native_host import (
    audit_result, load_native, prepare_input,
)


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def ring(expiry=5.0):
    edges = [(3, 0, 1., 1.), (0, 1, 1., 1.), (1, 2, 1., 1.), (2, 3, 1., 1.)]
    return prepare_input({
        "schema": "g31.circulation.input.v1",
        "node_records": [(n, 1, .001, n, 0, [v for u, v, _, _ in edges if u == n]) for n in range(4)],
        "edge_records": edges,
        "node_contracts": [{"node": n, "zone": "A", "resource_owner": "A",
                            "capacity": {0: 2, 1: 1, 2: 2, 3: 2}[n]} for n in range(4)],
        "edge_contracts": [{"from": u, "to": v, "capacity": 1, "entry_headway": .1}
                           for u, v, _, _ in edges],
        "static_role_contract": {"schema": "g31.static_node_roles.v1", "loader_nodes": [2]},
        "trays": [{"tray_id": "X", "node": 0}, {"tray_id": "B", "node": 1},
                  {"tray_id": "Y", "node": 3}],
        "jobs": [
            {"business_bag_id": "Y-business", "origin": 3, "destination": 2, "arrival": 1.,
             "deadline": 30., "load_seconds": .001, "unload_seconds": .001, "hold_seconds": 0.},
            {"business_bag_id": "B-release", "origin": 1, "destination": 3, "arrival": 10.,
             "deadline": 30., "load_seconds": .001, "unload_seconds": .001, "hold_seconds": 0.},
        ],
        "transfers": [], "faults": [],
        "owner_protocol": {"enabled": True, "timeout": .5, "ack_delay": .1},
        "options": {"max_simulation_time": 30., "trace_limit": 10000},
    })


def transfer(expiry=5.):
    return {"request_id": "live:1:A:X-transfer", "owner_id": "A", "tray_id": "X",
            "source": 0, "destination": 2, "earliest_departure": 0., "expiry": expiry,
            "message_delay": 0., "transfer_scope": "local_empty_return"}


def recovery(binding, name="recover", **changes):
    result = {k: v for k, v in binding.items() if k != "failure_reason"}
    result.update(kind="recover_failed_empty", request_id="live:1:A:" + name,
                  expiry=20., message_delay=0.)
    result.update(changes)
    return result


def recovery_gate(session, case, output):
    observation = session.observe_protocol("A")
    trays = {row["tray_id"]: row for row in observation["trays"]}
    binding = trays["X"]["failed_empty_recovery"]
    payload = recovery(binding)
    log = []

    def submit(p):
        response = session.submit_protocol_command(p)
        log.append({"payload": p, "response": response})
        save(output / "command_calls.json", log)
        return response

    if "reject" in case:
        cases = [
            ("stale", {"expected_generation": binding["expected_generation"] + 1}, "stale_recovery_generation"),
            ("node", {"from": 2}, "recovery_node_mismatch"),
            ("transfer", {"failed_transfer_request_id": "live:1:A:missing"}, "failed_empty_binding_mismatch"),
            ("leg", {"failed_transport_leg_id": "unknown-leg"}, "failed_empty_binding_mismatch"),
            ("expired", {"expiry": 6.}, "recovery_expired"),
            ("loaded", {"tray_id": "Y", "from": trays["Y"]["node"],
                        "expected_generation": trays["Y"]["generation"]}, "loaded_recovery_not_allowed"),
            ("healthy", {"tray_id": "B", "from": trays["B"]["node"],
                         "expected_generation": trays["B"]["generation"]}, "not_quarantined"),
            ("owner", {"request_id": "live:1:B:foreign", "owner_id": "B",
                       "failed_transfer_request_id": "live:1:B:foreign-transfer"}, "resource_owner_mismatch"),
        ]
        for name, changes, _ in cases:
            assert submit(recovery(binding, name, **changes))["status"] == "pending"
        before = session.offline_state_sha256()
        assert submit(recovery(binding, "foreign-ref", failed_transfer_request_id="live:1:B:foreign"))["reason"] == "reference_not_owned"
        assert session.offline_state_sha256() == before
        try:
            submit(dict(payload, schema="invalid"))
        except ValueError:
            pass
        else:
            raise AssertionError("unknown schema accepted")
        assert session.offline_state_sha256() == before
        session.advance_to(6.2)
        responses = []
        for name, changes, expected in cases:
            request = recovery(binding, name, **changes)
            response = session.protocol_command(request["owner_id"], request["request_id"])
            responses.append(response)
            assert response["last_delivered_ack"]["status"] == "rejected", response
            assert response["last_delivered_ack"]["reason"] == expected, response
        save(output / "rejected_command_acks.json", responses)
        assert next(t for t in session.observe_protocol("A")["trays"] if t["tray_id"] == "X")["generation"] == binding["expected_generation"]
        return False
    if "outage" in case:
        assert submit(dict(payload, expiry=7.))["status"] == "pending"
        session.advance_to(8.2)
        response = session.protocol_command("A", payload["request_id"])
        save(output / "outage_ack.json", response)
        assert response["last_delivered_ack"]["reason"] == "recovery_expired"
        return False
    # Schedule a later stale command, then execute one recovery through dropped,
    # duplicate and retried ACKs. The stale payload must retain its old generation.
    stale = recovery(binding, "delayed-stale", message_delay=1.)
    assert submit(stale)["status"] == "pending"
    assert submit(payload)["status"] == "pending"
    immutable = session.offline_state_sha256()
    assert submit(dict(payload, expected_generation=binding["expected_generation"] + 1))["reason"] == "request_identity_conflict"
    assert session.offline_state_sha256() == immutable
    checkpoint = session.checkpoint()
    session.restore(checkpoint)
    assert session.offline_state_sha256() == immutable
    session.advance_to(6.6)
    assert session.protocol_command("A", payload["request_id"])["status"] == "timeout_unknown"
    after = next(t for t in session.observe_protocol("A")["trays"] if t["tray_id"] == "X")
    assert after["generation"] == binding["expected_generation"] + 1 and after["node"] == binding["from"]
    assert after["mode"] == "empty" and "failed_empty_recovery" not in after
    assert submit(payload)["reason"] == "retry_enqueued"
    session.advance_to(6.8)
    first = session.protocol_command("A", payload["request_id"])
    assert first["last_delivered_ack"]["status"] == "recovered", first
    session.advance_to(8.2)
    # The original ACK copy may arrive late; it must not supersede a newer ACK.
    assert session.protocol_command("A", payload["request_id"])["last_delivered_ack"] == first["last_delivered_ack"]
    assert submit(stale)["reason"] == "retry_enqueued"
    session.advance_to(9.4)
    stale_result = session.protocol_command("A", stale["request_id"])
    assert stale_result["last_delivered_ack"]["reason"] == "stale_recovery_generation", stale_result
    restored = session.checkpoint()
    state = session.offline_state_sha256()
    session.restore(restored)
    assert session.offline_state_sha256() == state
    assert submit(payload)["reason"] == "retry_enqueued"
    session.advance_to(9.6)
    final = next(t for t in session.observe_protocol("A")["trays"] if t["tray_id"] == "X")
    assert final["generation"] == binding["expected_generation"] + 1
    save(output / "recovery_proof.json", dict(binding=binding, recovered=after, final=final,
         first_ack=first, stale_ack=stale_result, checkpoint_restores=2, additional_constructors=0))
    return True


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    binary = args.binary.resolve(strict=True)
    sha = hashlib.sha256(binary.read_bytes()).hexdigest()
    entries = [json.loads(line) for line in args.ledger.read_text(encoding="utf-8").splitlines()] if args.ledger.exists() else []
    count = sum(row.get("owner") == "local_return" and row.get("kind") == "short_gate" for row in entries)
    if count >= 14:
        raise RuntimeError("local_return allocation of 14 constructor attempts exhausted")
    expiry = 25. if "no_expiry" in args.case or "entered" in args.case or "other_failure" in args.case else 5.
    value, payload = ring(expiry), transfer(expiry)
    if "recovery_valid" in args.case:
        value["owner_protocol"].update(drop_ack_packets=1, duplicate_acks=True, duplicate_ack_delay=2.)
    if "recovery_reject" in args.case:
        value["node_contracts"][3]["resource_owner"] = "B"
    if "recovery_outage" in args.case:
        value["owner_protocol"]["owner_outages"] = [{"owner": "A", "start": 5.5, "end": 8.}]
    if "fifo" in args.case:
        value["trays"].append({"tray_id": "Z", "node": 3})
        value["jobs"].append(dict(value["jobs"][0], business_bag_id="Z-business", arrival=1.1))
    if "unlisted_failure" in args.case or "other_failure" in args.case:
        value["options"]["max_decisions_per_bag"] = 1
    save(output / "input.json", value)
    save(output / "transfer.json", payload)
    receipt = dict(kind="short_gate", name=args.case, binary_sha256=sha, binary=str(binary),
                   owner="local_return", started_at_utc=datetime.now(timezone.utc).isoformat(),
                   pid=os.getpid(), constructors=1, output=str(output))
    native = load_native(binary)
    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    with args.ledger.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(receipt) + "\n")
    save(output / "receipt.json", dict(receipt, status="constructor_starting"))
    try:
        session = native.NativeSession(value)
        assert session.submit_protocol_transfer(payload)["status"] == "pending"
        session.advance_to(4.)
        save(output / "at_4_diagnostics.json", session.offline_diagnostics())
        if "checkpoint" in args.case:
            checkpoint = session.checkpoint()
            before = session.offline_state_sha256()
            session.restore(checkpoint)
            assert session.offline_state_sha256() == before
            receipt["in_place_checkpoint_restore"] = True
            receipt["restore_additional_constructors"] = 0
        session.advance_to(6.)
        if "checkpoint" in args.case:
            first_sha = session.offline_state_sha256()
            session.restore(checkpoint)
            session.advance_to(6.)
            assert session.offline_state_sha256() == first_sha
            receipt["same_expiry_replayed_identically_after_restore"] = True
        save(output / "at_6_diagnostics.json", session.offline_diagnostics())
        save(output / "at_6_observation.json", session.observe_protocol("A"))
        recovered = recovery_gate(session, args.case, output) if "recovery" in args.case else False
        extra_transfers = []
        if "unlisted_failure" in args.case or "other_failure" in args.case:
            if "other_failure" in args.case:
                session.advance_to(12.)
            current = next(t for t in session.observe_protocol("A")["trays"] if t["tray_id"] == "X")
            assert current["mode"] == "quarantined" and "failed_empty_recovery" not in current
            probe = dict(schema="g31.recover_failed_empty.v1", owner_id="A", tray_id="X",
                         expected_generation=current["generation"], **{"from": current["node"]},
                         failed_transfer_request_id=payload["request_id"],
                         failed_transport_leg_id=payload["request_id"] + ":empty_return:0")
            command = recovery(probe, "unlisted-failure")
            assert session.submit_protocol_command(command)["status"] == "pending"
            session.advance_to(12.2 if "other_failure" in args.case else 6.2)
            ack = session.protocol_command("A", command["request_id"])
            save(output / "unlisted_failure_recovery_rejection.json", dict(current=current, payload=command, ack=ack))
            expected = "inflight_or_receiving_obligation" if "other_failure" in args.case else "failure_not_recoverable"
            assert ack["last_delivered_ack"]["reason"] == expected, ack
        if "reuse" in args.case:
            fresh = dict(payload, request_id="live:1:A:X-fresh-return", earliest_departure=9.6, expiry=25.)
            assert session.submit_protocol_transfer(fresh)["status"] == "pending"
            extra_transfers.append(dict(fresh, issued_at=9.6))
            save(output / "fresh_transfer.json", fresh)
        if "entered" in args.case:
            session.advance_to(10.2)
            current = next(t for t in session.observe_protocol("A")["trays"] if t["tray_id"] == "X")
            assert current["mode"] == "empty_transit" and current["edge_to"] >= 0
            probe = dict(schema="g31.recover_failed_empty.v1", owner_id="A", tray_id="X",
                         expected_generation=current["generation"], **{"from": current["node"]},
                         failed_transfer_request_id=payload["request_id"],
                         failed_transport_leg_id=payload["request_id"] + ":empty_return:0")
            command = recovery(probe, "entered-probe")
            assert session.submit_protocol_command(command)["status"] == "pending"
            session.advance_to(10.4)
            ack = session.protocol_command("A", command["request_id"])
            save(output / "already_entered_recovery_rejection.json", dict(current=current, payload=command, ack=ack))
            assert ack["last_delivered_ack"]["reason"] == "inflight_or_receiving_obligation", ack
        if "retry" in args.case:
            assert session.submit_protocol_transfer(payload)["reason"] == "retry_enqueued"
            session.advance_to(6.2)
            assert session.submit_protocol_transfer(payload)["reason"] == "retry_enqueued"
        result = session.result_at(30.)
        save(output / "final_result.json", result)
        save(output / "final_diagnostics.json", session.offline_diagnostics())
        replay = deepcopy(value)
        replay["transfers"] = [dict(payload, issued_at=0.), *extra_transfers]
        conservation = audit_result(replay, result)
        save(output / "conservation.json", conservation)
        jobs = {row["business_bag_id"]: row for row in result["jobs"]}
        x = next(row for row in result["trays"] if row["tray_id"] == "X")
        terminal = result["transfers"][0]
        y_done = jobs["Y-business"]["status"] == "completed"
        if "unlisted_failure" in args.case or "other_failure" in args.case:
            assert x["mode"] == "quarantined" and terminal["reason"] != "departure_lease_expired_before_physical_entry"
            assert not any(r["event"] == "EMPTY_RECOVERY_GRANTED" for r in result["receipts"])
        elif "no_expiry" in args.case or "entered" in args.case:
            assert y_done and terminal["status"] == "received", (jobs, terminal)
        elif args.case.startswith("before"):
            assert not y_done and x["mode"] == "quarantined", (jobs, x)
        else:
            assert y_done and x["mode"] == ("empty" if recovered else "quarantined"), (jobs, x)
            assert terminal["reason"] == "departure_lease_expired_before_physical_entry"
            assert sum(r["event"] == "LEG_FAILED" and r["tray_id"] == "X" for r in result["receipts"]) == 1
            assert sum(r["event"] == "UNUSED_RECEIVING_RELEASED" and r["tray_id"] == "X" for r in result["receipts"]) == 1
            assert sum(r["event"] == "EMPTY_RECOVERY_GRANTED" and r["tray_id"] == "X" for r in result["receipts"]) == int(recovered)
            if "reuse" in args.case:
                assert len(result["transfers"]) == 2 and result["transfers"][1]["status"] == "received"
                assert len([r for r in result["leg_identities"] if r["kind"] == "empty_return"]) == 2
            assert any(r["event"] == "RESOURCE_WAIT" and r["tray_id"] == "Y" and 5. < r["time"] < 10. for r in result["receipts"])
            if "fifo" in args.case:
                assert jobs["Z-business"]["status"] == "completed"
                entries = [r for r in result["receipts"] if r["event"] == "EDGE_ENTER" and r["from"] == 0]
                assert [r["tray_id"] for r in entries] == ["Y", "Z"], entries
                assert entries[1]["time"] > entries[0]["time"] + .099
        receipt.update(status="passed", y_completed=y_done, x_mode=x["mode"],
                       transfer_status=terminal["status"], conservation=conservation)
    except BaseException as exc:
        receipt.update(status="failed", error=repr(exc), traceback=traceback.format_exc())
        raise
    finally:
        receipt["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
        save(output / "receipt.json", receipt)
        print(json.dumps(receipt))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--case", required=True)
    run(parser.parse_args())
