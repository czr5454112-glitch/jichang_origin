"""Original 151-node/227-edge, 24-bag/one-tray public owner-protocol comparison.

Input selection is the existing static mechanism-subset rule, not outcome
selection. Only a shared communication contract is added. A persistent native
session executes each policy; no Python physical state or fallback is used.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
import gzip
import json
import math
from pathlib import Path
import time
import traceback

from .assess_joint_window_protection import compare
from .finite_reference import _horizon_completion, outcome_cost
from .native_host import audit_result, load_native
from .original_mechanism import select_input
from .original_workload import digest, json_digest, write_json
from .protocol_control import run_protocol_control
from .validate_protocol_control import replay_input


HORIZON = 86400.
COUNT = 24
EXPECTED_BINARY_SHA256 = "079eaaeae53671d1a7d2a26437478850b329db80ec8eebc58b1fa70f5f0ddb7f"
COMMUNICATION = {"enabled": True, "timeout": 5., "ack_delay": .2,
                 "drop_ack_packets": 0, "duplicate_acks": False,
                 "duplicate_ack_delay": 0., "owner_outages": []}
POLICIES = {
    "reactive_r2": {"routes": False, "forecasts": False, "prebalance": True, "predictive": False},
    "predictive_r2": {"routes": False, "forecasts": True, "prebalance": True, "predictive": True},
    "joint_r1_r2": {"routes": True, "forecasts": True, "prebalance": True, "predictive": True},
}
CONTROLLER = {"control_period": 60., "command_delay": 2., "publication_delay": .5,
              "retry_period": 60., "compact": True, "lease_seconds": 120.}


def add_protocol_contract(original: dict) -> dict:
    if "owner_protocol" in original:
        raise ValueError("original_protocol:unexpected_existing_communication_contract")
    data = copy.deepcopy(original)
    data["owner_protocol"] = copy.deepcopy(COMMUNICATION)
    if {k: v for k, v in data.items() if k != "owner_protocol"} != original:
        raise AssertionError("original_protocol:physical_contract_changed")
    return data


def gz(path: Path, value):
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False)


def request_ledger(calls: list[dict], ack_views: dict) -> dict:
    """Separate immutable client attempts, delivered ACKs, and physical audit.

    Pending ACKs and missing acknowledgements are never counted as successful
    physical resolution. Final owner views are diagnostic exports after the
    controller has stopped; they cannot steer its previous decisions.
    """
    initial, retry_count = {}, 0
    for call in calls:
        identity = call["request"]["request_id"]
        if call["retry"]:
            retry_count += 1
            if identity not in initial or call["request"] != initial[identity]["request"] or call["kind"] != initial[identity]["kind"]:
                raise ValueError("original_protocol:retry_changed_payload_or_identity")
        else:
            if identity in initial:
                raise ValueError("original_protocol:duplicate_new_request_identity")
            initial[identity] = call
    transfer_acks, command_acks = [], []
    for owner, view in ack_views.items():
        for key, target in (("delivered_transfer_acks", transfer_acks), ("delivered_command_acks", command_acks)):
            for ack in view.get(key, []):
                if ack["delivered_at"] > view["now"] + 1e-8:
                    raise ValueError("original_protocol:undelivered_ack_exposed")
                target.append({"owner": owner, **ack})
    latest = {}
    for ack in transfer_acks + command_acks:
        if ack["request_id"] not in initial:
            raise ValueError("original_protocol:ack_without_original_request")
        key = ack["request_id"]
        if key not in latest or ack["sequence"] > latest[key]["sequence"]:
            latest[key] = ack
    rows = []
    for identity, call in initial.items():
        ack = latest.get(identity)
        rows.append({"request_id": identity, "kind": call["kind"], "owner_id": call["request"]["owner_id"],
                     "issued_at": call["at"], "submission_reply": call["reply"],
                     "last_delivered_ack": ack, "resolution_without_ack": "unknown",
                     "physical_received_at": ack.get("received_at") if ack and call["kind"] == "transfer" and ack["status"] == "received" else None})
    return {"request_count": len(initial), "retry_calls": retry_count,
            "requests_by_kind": dict(Counter(c["kind"] for c in initial.values())),
            "submission_status_counts": dict(Counter(c["reply"]["status"] for c in initial.values())),
            "last_delivered_ack_status_counts": dict(Counter(a["status"] for a in latest.values())),
            "requests_without_delivered_ack": len(initial)-len(latest), "requests": rows,
            "delivered_transfer_acks": transfer_acks, "delivered_command_acks": command_acks,
            "scope": "client immutable requests and actually delivered ACK snapshots; not unacknowledged native truth"}


def execute_policy(session, owners, options, *, max_seconds=180., segment_seconds=3600., event_budget=100000):
    """Continue the same host and controller state, with bounded stop points.

    Wall budget is checked between declared segments, so one segment can
    overrun it. An event-truncated tick is never retried via result_at. No
    prefix is priced as if it had reached the full common horizon.
    """
    if not all(math.isfinite(x) and x > 0 for x in (max_seconds, segment_seconds)) or event_budget <= 0:
        raise ValueError("original_protocol:invalid_budget")
    started = time.perf_counter()
    aggregate = {"status": "running", "result": None, "controller_state": None,
                 "control_records": [], "client_calls": [], "native_batches": [], "segments": [],
                 "complete_100ms_requirement_certified": False}
    index = 1
    while session.physical_time < HORIZON:
        if time.perf_counter() - started >= max_seconds:
            aggregate["status"] = "wall_budget_exhausted"
            break
        target = min(HORIZON, index * segment_seconds)
        if target <= session.physical_time:
            raise ValueError("original_protocol:invalid_segment_boundary")
        run = run_protocol_control(session, owners, horizon=target, event_budget=event_budget,
                                   state=aggregate["controller_state"], **CONTROLLER, **options)
        for key in ("control_records", "client_calls", "native_batches"):
            aggregate[key].extend(run[key])
        aggregate["controller_state"], aggregate["result"] = run["controller_state"], run["result"]
        aggregate["control_continuation"] = run["control_continuation"]
        aggregate["segments"].append({"requested_horizon": target, "status": run["status"],
                                       "physical_time": session.physical_time,
                                       "cumulative_wall_seconds": time.perf_counter()-started})
        aggregate["status"] = run["status"]
        if run["status"] != "reached":
            break
        index += 1
    aggregate["requested_horizon"] = HORIZON
    aggregate["controller_wall_seconds"] = time.perf_counter()-started
    return aggregate


def assess_execution(data, run, session):
    declared = sorted(j["business_bag_id"] for j in data["jobs"] if j["arrival"] <= HORIZON)
    row = {"status": "unknown", "declared_offered": len(declared), "declared_business_ids": declared,
           "metrics": None, "audit": None, "complete_100ms_requirement_certified": False}
    if not isinstance(run.get("result"), dict):
        row["completion"] = {"status": "unknown", "problems": ["no_complete_native_result"], "outer_status": run.get("status")}
        return row
    completion = _horizon_completion(run["result"], session, HORIZON, run.get("status"))
    row["completion"] = completion
    if completion["status"] != "reached":
        return row
    replay = replay_input(data, run["client_calls"])
    row["audit"] = audit_result(replay, run["result"])
    row["metrics"] = outcome_cost(run["result"], data["jobs"], HORIZON)
    if row["metrics"]["offered"] != len(declared):
        raise ValueError("original_protocol:offered_denominator_changed")
    by_tray = defaultdict(list)
    for event in run["result"]["receipts"]:
        if event["event"] == "UNLOAD_COMPLETE":
            by_tray[event["tray_id"]].append(event["business_bag_id"])
    row.update({"status": "verified_complete_execution", "same_tray_completed_business_ids": dict(by_tray),
                "physical_transfer_status_counts": dict(Counter(r["status"] for r in run["result"]["transfers"])),
                "physical_transfers": len(run["result"]["transfers"]), "native_event_count": run["result"]["native_summary"].get("event_count"),
                "global_physical_optimality": "unknown"})
    return row


def paired_comparisons(cases):
    comparisons = {}
    for candidate, baseline in (("predictive_r2", "reactive_r2"), ("joint_r1_r2", "reactive_r2"),
                                 ("joint_r1_r2", "predictive_r2")):
        a, b = cases.get(candidate, {}).get("metrics"), cases.get(baseline, {}).get("metrics")
        if a is None or b is None:
            comparisons[candidate+"__vs__"+baseline] = {"status": "unknown_incomplete_execution", "preserved": None}
            continue
        identities = sorted(j["business_bag_id"] for j in b["per_job"])
        comparison = compare(a, b, identities)
        comparison.update({"status": "executed_paired_comparison", "cost_delta": a["cost"]-b["cost"]})
        comparisons[candidate+"__vs__"+baseline] = comparison
    return comparisons


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true", help="write selected inputs/protocol without loading native")
    parser.add_argument("--max-seconds-per-policy", type=float, default=180.)
    parser.add_argument("--event-budget", type=int, default=100000)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    here = Path(__file__).parent
    paths = [Path(__file__), *(here/name for name in ("original_mechanism.py", "original_workload.py",
        "protocol_control.py", "analytic_control.py", "regional_control.py", "native_host.py",
        "finite_reference.py", "assess_joint_window_protection.py", "validate_protocol_control.py"))]
    before = {str(p): digest(p) for p in paths}
    archive = args.output/"source_archive"; archive.mkdir()
    for path in paths:
        (archive/path.name).write_bytes(path.read_bytes())
    receipt = {"schema": "g31.original_protocol_comparison.v1", "status": "preparing", "cases": {},
               "source_before": before, "expected_binary_sha256": EXPECTED_BINARY_SHA256,
               "binary_sha256": digest(args.binary), "complete_100ms_requirement_certified": False,
               "novelty": "engineering integration and strong analytic comparators; not new method evidence",
               "global_physical_optimality": "unknown"}
    write_json(args.output/"receipt.json", receipt)
    try:
        if receipt["binary_sha256"] != EXPECTED_BINARY_SHA256:
            raise ValueError("original_protocol:binary_is_not_frozen_native010")
        original, selection, lineage = select_input(COUNT, horizon=HORIZON)
        data = add_protocol_contract(original)
        if len(data["node_records"]) != 151 or len(data["edge_records"]) != 227 or len(data["jobs"]) != COUNT or len(data["trays"]) != 1:
            raise ValueError("original_protocol:unexpected_original_witness_shape")
        if sum(j["arrival"] <= HORIZON for j in data["jobs"]) != COUNT:
            raise ValueError("original_protocol:selected_job_outside_horizon")
        owners = sorted({n.get("resource_owner", n["zone"]) for n in data["node_contracts"]})
        permissions = {"allowed_business_ids": [j["business_bag_id"] for j in data["jobs"] if j.get("allow_suffix_reroute", False)],
                       "protected_business_ids": [j["business_bag_id"] for j in data["jobs"] if j.get("protected_service", True)],
                       "permission_fields_changed": False, "missing_allow_suffix_reroute_means_false": True}
        protocol = {"schema": "g31.original_protocol_comparison_plan.v1", "count": COUNT, "horizon": HORIZON,
                    "communication": COMMUNICATION, "controller": CONTROLLER, "policies": POLICIES,
                    "owners": owners, "r1_original_permissions": permissions, "segment_seconds": 3600.,
                    "max_seconds_per_policy": args.max_seconds_per_policy, "event_budget_per_native_advance": args.event_budget,
                    "wall_budget_scope": "checked between one-hour physical segments; possible one-segment overrun is recorded",
                    "input_selection": "existing static select_input(24) rule before any simulation; all outcomes retained",
                    "strong_reference": "reactive and predictive R2 analytic baselines with actual owner protocol; no full optimization claim",
                    "information_difference": "predictive methods use legal release/service forecasts; reactive method is explicit information/mechanism ablation",
                    "scope": "original entire directed graph, selected 24-job same-loader witness and one retained real tray; not full mother workload",
                    "complete_100ms_requirement_certified": False}
        selection["protocol_input_sha256"] = json_digest(data)
        selection["added_fields"] = ["owner_protocol"]
        write_json(args.output/"selection.json", selection)
        write_json(args.output/"input.json", data)
        write_json(args.output/"protocol.json", protocol)
        with gzip.open(args.output/"mother_crosswalk_selection.jsonl.gz", "wt", encoding="utf-8") as stream:
            for row in lineage:
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+"\n")
        receipt.update({"selection_sha256": digest(args.output/"selection.json"), "input_file_sha256": digest(args.output/"input.json"),
                        "protocol_sha256": digest(args.output/"protocol.json"), "mother_crosswalk_sha256": digest(args.output/"mother_crosswalk_selection.jsonl.gz"),
                        "declared_offered": COUNT, "r1_original_permissions": permissions})
        if args.prepare_only:
            receipt["status"] = "prepared_without_native_execution"
        else:
            native = load_native(args.binary)
            for policy, options in POLICIES.items():
                directory = args.output/policy; directory.mkdir()
                started = time.perf_counter()
                try:
                    session = native.NativeSession(data)
                    run = execute_policy(session, owners, options, max_seconds=args.max_seconds_per_policy,
                                         event_budget=args.event_budget)
                    gz(directory/"run.json.gz", run)
                    views = {owner: session.observe_protocol(owner) for owner in owners}
                    gz(directory/"delivered_views.json.gz", views)
                    ledger = request_ledger(run["client_calls"], views)
                    gz(directory/"request_ack_ledger.json.gz", ledger)
                    row = assess_execution(data, run, session)
                    row["protocol_ledger_summary"] = {k: v for k, v in ledger.items() if k not in ("requests", "delivered_transfer_acks", "delivered_command_acks")}
                    row["controller_wall_seconds"] = run["controller_wall_seconds"]
                    row["r1_requested"] = ledger["requests_by_kind"].get("route", 0)
                    row["r1_effective_scope"] = "original_permissions_only" if permissions["allowed_business_ids"] else "not_exercised_no_original_permission"
                    row["offline_final_state_sha256"] = session.offline_state_sha256()
                    row["raw_files_sha256"] = {name: digest(directory/name) for name in ("run.json.gz", "delivered_views.json.gz", "request_ack_ledger.json.gz")}
                except Exception:
                    row = {"status": "failed_execution", "exception": traceback.format_exc(), "metrics": None,
                           "declared_offered": COUNT, "complete_100ms_requirement_certified": False}
                row["total_wall_seconds"] = time.perf_counter()-started
                write_json(directory/"assessment.json", row)
                receipt["cases"][policy] = row
                write_json(args.output/"receipt.json", receipt)
            receipt["paired_comparisons"] = paired_comparisons(receipt["cases"])
            receipt["status"] = "executed_comparison_not_research_gate" if all(
                c["status"] == "verified_complete_execution" for c in receipt["cases"].values()) else "incomplete_or_failed_comparison"
    except Exception:
        receipt["status"] = "failed_preparation"
        receipt["exception"] = traceback.format_exc()
        raise
    finally:
        receipt["source_after"] = {str(p): digest(p) for p in paths}
        receipt["source_changed"] = [p for p in before if before[p] != receipt["source_after"][p]]
        if receipt["source_changed"]:
            receipt["status"] = "source_changed_unfrozen_execution"
        write_json(args.output/"receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "source_changed": receipt["source_changed"],
        "policies": {name: {"status": row["status"], "completed": (row.get("metrics") or {}).get("completed"),
                             "cost": (row.get("metrics") or {}).get("cost"), "r1_requested": row.get("r1_requested")}
                     for name, row in receipt["cases"].items()}}))
    return 0 if receipt["status"] in ("prepared_without_native_execution", "executed_comparison_not_research_gate") else 1


if __name__ == "__main__":
    raise SystemExit(main())
