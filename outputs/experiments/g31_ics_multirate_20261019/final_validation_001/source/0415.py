"""Offline deterministic policy replay and clock/lineage checks over real tape.

No native import or hidden-world reconstruction occurs here. Returned public
records are replayed only as validation data; they never feed a new online run.
Campaign archive/input/binary authority must additionally be checked by the
outer saved-evidence verifier.
"""
from __future__ import annotations

from copy import deepcopy
import json

from .original_notification_contract import contract, require
from .original_notification_probe import ENDPOINTS, propose, run_cohort


CLOCK_KEYS = frozenset(("engine_start_ns", "ended_ns", "start_ns", "end_ns", "accepted_wall_ns", "wall_ns",
    "handled_wall_ns", "drain_start_ns", "drain_end_ns", "output_end_ns", "submit_compute_ms", "wall_seconds"))


def canonical(value):
    return json.loads(json.dumps(value, allow_nan=False, sort_keys=True))


def without_clocks(value):
    if isinstance(value, dict): return {k: without_clocks(v) for k, v in value.items() if k not in CLOCK_KEYS}
    if isinstance(value, (list, tuple)): return [without_clocks(v) for v in value]
    return value


class ReplaySession:
    def __init__(self, rows):
        self.rows, self.cursor = rows, 0
        self.physical_time = rows[0]["physical_before"] if rows else 0.

    def __getattr__(self, endpoint):
        require(endpoint in ENDPOINTS, "unclassified_replay_endpoint")
        def invoke(*args, **kwargs):
            require(self.cursor < len(self.rows), "replay_exceeded_actual_tape")
            row = self.rows[self.cursor]
            require(row["endpoint"] == endpoint and canonical(row["args"]) == canonical(list(args))
                    and canonical(row["kwargs"]) == canonical(kwargs), "replay_call_or_payload_changed")
            require(self.physical_time == row["physical_before"], "replay_physical_clock_changed")
            self.cursor += 1; self.physical_time = row["physical_after"]
            require("error" not in row and "result" in row, "actual_service_failure")
            return deepcopy(row["result"])
        return invoke


def verify_raw(raw, owners, chunks, *, mandatory_setup_start_ns, proposal=propose):
    require(raw["contract"] == contract(), "campaign_contract_changed")
    require(type(raw["engine_start_ns"]) is int and type(raw["ended_ns"]) is int
        and 0 <= raw["engine_start_ns"] <= raw["ended_ns"], "invalid_engine_lifetime")
    require(raw["status"] in {"finite_cohort_closed", "completion_tail_exhausted", "public_horizon_reached"}
            and not raw["failures"], "failed_engine_prefix")
    rows = []
    for index, chunk in enumerate(chunks):
        require(chunk["index"] == index and isinstance(chunk["service_tape"], list), "missing_or_reordered_chunk")
        rows.extend(chunk["service_tape"])
    rows.extend(raw["unflushed_service_tape"])
    require(len(rows) == raw["native_call_count"] and [r["ordinal"] for r in rows] == list(range(1, len(rows)+1)),
            "missing_or_reordered_service_tape")
    previous_end = raw["engine_start_ns"]
    for row in rows:
        require(row["endpoint"] in ENDPOINTS and isinstance(row["args"], list) and isinstance(row["kwargs"], dict)
                and type(row["start_ns"]) is int and type(row["end_ns"]) is int
                and previous_end <= row["start_ns"] <= row["end_ns"] <= raw["ended_ns"], "invalid_service_interval")
        require("error" not in row and "result" in row, "failed_service_call")
        previous_end = row["end_ns"]
    session = ReplaySession(rows)
    # Re-execute unchanged public policy/codec/client logic against every exact
    # recorded endpoint result; omitted reads/submits/drains cannot disappear.
    clock_value = 0
    def clock():
        nonlocal clock_value
        clock_value += 1
        return clock_value
    replayed = run_cohort(session, owners, clock=clock, proposal=proposal)
    require(not replayed["failures"] and session.cursor == len(rows), "policy_replay_incomplete")
    compared = ("status", "physical_time", "admitted_notification_boundaries", "native_call_count", "ledger", "decisions", "outbox", "client_calls")
    for field in compared:
        require(canonical(without_clocks(raw[field])) == canonical(without_clocks(replayed[field])), "policy_replay_changed:"+field)
    # Independently bind real observation, submit/ACK and final-drain stamps to
    # tape. Replay alone intentionally ignores clocks and cannot prove these.
    by_ordinal = {r["ordinal"]: r for r in rows}
    batches, roots, operations = (raw["ledger"][k] for k in ("batches", "roots", "operations"))
    require(batches and type(mandatory_setup_start_ns) is int and mandatory_setup_start_ns >= 0, "missing_setup_or_batches")
    earliest = min(b["accepted_wall_ns"] for b in batches.values())
    require(mandatory_setup_start_ns <= raw["engine_start_ns"] <= earliest, "invalid_mandatory_setup_interval")
    setup_ns = earliest-mandatory_setup_start_ns
    for batch in batches.values():
        returned = batch["returned"]; require(returned is not None, "pending_native_boundary")
        require(type(batch["accepted_wall_ns"]) is int and type(returned["wall_ns"]) is int
            and raw["engine_start_ns"] <= batch["accepted_wall_ns"] <= returned["wall_ns"] <= raw["ended_ns"], "invalid_batch_lifetime")
        call = by_ordinal[returned["call_ordinal"]]
        require(call["endpoint"] == "advance_until_owner_notification" and batch["accepted_wall_ns"] <= call["start_ns"]
                <= call["end_ns"] <= returned["wall_ns"] and canonical(call["result"]) == canonical(returned["response"]), "notification_not_actual_return")
    report = {}
    for identity, row in roots.items():
        observation = row["observation"]; require(observation is not None and not row["scope_errors"], "unknown_observation_scope")
        call = by_ordinal[observation["call_ordinal"]]
        require(call["endpoint"] == "observe_protocol" and call["args"] == [row["owner"]]
                and observation["start_ns"] == call["start_ns"] <= call["end_ns"] <= observation["end_ns"], "observation_not_actual_read")
        require(row["accepted_wall_ns"] == batches[row["batch"]]["accepted_wall_ns"], "shared_trigger_not_charged")
        output = row["output"]
        if output:
            require(type(output["wall_ns"]) is int, "invalid_output_clock")
            drain = by_ordinal[output["drain_ordinal"]]
            require(drain["endpoint"] == "advance_to" and drain["args"] == [drain["physical_before"]]
                    and drain["physical_before"] == drain["physical_after"] and drain["result"] == output["drain"]
                    and drain["start_ns"] == output["drain_start_ns"] and drain["end_ns"] == output["drain_end_ns"]
                    and drain["end_ns"] <= output["wall_ns"] <= raw["ended_ns"], "returned_output_missing_complete_actual_drain")
            for operation_id in row["operations"]:
                ack = operations[operation_id]["ack"]
                require(ack is not None and ack["handled_wall_ns"] <= drain["start_ns"], "return_before_ack_processing")
        amount = (output["wall_ns"] if output else raw["ended_ns"])-row["accepted_wall_ns"]+setup_ns
        require(amount >= 0, "negative_complete_bound")
        report[identity] = {"complete_operation_upper_ns": amount if output else None, "known_prefix_upper_ns": amount,
            "job_children": {job: {"complete_operation_upper_ns": amount if output else None, "affected_job_scope_verified": False}
                for job in observation["scope"]["eligible_job_ids"]}, "disposition": output["disposition"] if output else None}
    for identity, operation in operations.items():
        payload = raw["outbox"][identity]["payload"]
        calls = [r for r in rows if r["endpoint"].startswith("submit_protocol_") and r["args"] == [payload]]
        require(len(calls) == len(operation["attempts"]), "immutable_attempt_count_changed")
        for attempt, call in zip(operation["attempts"], calls):
            require(attempt["at"] == call["physical_before"] and attempt["wall_ns"] <= call["start_ns"]
                    and attempt["wall_ns"] >= roots[operation["root"]]["observation"]["end_ns"], "attempt_not_actual_submit")
        ack = operation["ack"]
        if ack:
            require(type(ack["handled_wall_ns"]) is int and ack["handled_wall_ns"] <= raw["ended_ns"], "invalid_ack_clock")
            query = by_ordinal[ack["query_ordinal"]]
            require(query["endpoint"] in {"protocol_command", "protocol_request"} and query["args"] == [payload["owner_id"], identity]
                    and query["result"]["request_id"] == identity
                    and {**query["result"]["last_delivered_ack"], "request_id": identity} == ack["body"]
                    and query["end_ns"] <= ack["handled_wall_ns"], "ack_not_actual_delivered_query")
    return {"status": "validated_finite_original_notification_operation_accounting", "root_count": len(roots),
        "closed_count": sum(r["complete_operation_upper_ns"] is not None for r in report.values()),
        "notification_boundary_count": raw["admitted_notification_boundaries"],
        "job_child_count": sum(len(r["job_children"]) for r in report.values()), "roots": report,
        "mandatory_setup_ns": setup_ns, "service_call_count": len(rows), "source_offered_jobs": 28506,
        "original_business_request_100ms_certified": False, "native_runtime_accepted": False,
        "scope": "Finite original-input notification-operation bundles; whole trigger/static setup/native work retained, no division. Job child affected scope remains unverified."}
