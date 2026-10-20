"""Offline evidence audit only; no native import, constructor, advance, or fit."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import time

from .foundation_airport_batch_patch import digest
from .foundation_airport_inventory_rule import inventory_view
from .foundation_airport_json_stream import iter_json_array_gz

SCHEMA = "g31.inventory_spi_offline_mechanism_audit.v1"


def require(condition, reason):
    if not condition:
        raise ValueError("inventory_spi_mechanism:" + reason)


def read(path):
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf8") as stream:
        return json.load(stream)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            value.update(block)
    return value.hexdigest()


def json_form(value):
    return json.loads(json.dumps(value, allow_nan=False))


def distribution(values):
    values = sorted(values)
    require(all(type(x) in (float, int) and math.isfinite(x) and x >= 0 for x in values),
        "finite_nonnegative_timing")
    if not values:
        return {"samples": 0, "sum_ms": 0., "p50_ms": None, "p95_ms": None,
            "p99_ms": None, "max_ms": None, "quantile_method": "linear_interpolation"}
    def quantile(fraction):
        position = fraction*(len(values)-1)
        lower = int(position)
        upper = min(lower+1, len(values)-1)
        return values[lower]+(values[upper]-values[lower])*(position-lower)
    return {"samples": len(values), "sum_ms": math.fsum(values), "p50_ms": quantile(.5),
        "p95_ms": quantile(.95), "p99_ms": quantile(.99), "max_ms": values[-1],
        "quantile_method": "linear_interpolation"}


def timing_summary(records, *, activate_at=7200., audit_receipt=None, snapshot_reads=None):
    result = {}
    for name, selected in (("all", records), ("after_activation", [r for r in records if r["at"] >= activate_at])):
        owners = [d for r in selected for d in r["owner_decisions"]]
        result[name] = {
            "control_ticks": len(selected), "owner_decisions": len(owners),
            "owner_planning_residual_post_and_submit_excluding_evaluator": distribution(
                [d["compute_ms"] for d in owners if "compute_ms" in d]),
            "shared_tick_preparation": distribution(
                [r["preparation_compute_ms"] for r in selected if "preparation_compute_ms" in r]),
            "offline_precommit_archive": distribution(
                [d["offline_evaluator_ms"] for d in owners if "offline_evaluator_ms" in d]),
            "offline_tick_start_observer": distribution(
                [r["offline_tick_start_observer_ms"] for r in selected if "offline_tick_start_observer_ms" in r]),
            "missing_owner_compute": sum("compute_ms" not in d for d in owners),
            "missing_tick_preparation": sum("preparation_compute_ms" not in r for r in selected),
        }
    if audit_receipt is not None:
        timings = audit_receipt["timings_ms"]
        require(len(timings) == audit_receipt["records"], "callback_persistence_timing_coverage")
        result["offline_callback_persistence"] = distribution([t["audit_persistence"] for t in timings])
    if snapshot_reads is not None:
        result["inventory_snapshot_endpoint"] = {
            "reads": len(snapshot_reads),
            "encoded_bytes_sum_over_reads_not_unique_network_bytes": sum(r["encoded_utf8_bytes"] for r in snapshot_reads),
            "endpoint_read": distribution([r["endpoint_read_ms"] for r in snapshot_reads]),
            "encoding_for_byte_measurement": distribution([r["byte_measurement_ms"] for r in snapshot_reads]),
        }
    result["scopes"] = {
        "owner_compute": "Includes fresh public views, planner/residual, optional post stage and submits; excludes recorded offline precommit work.",
        "preparation": "One shared tick covering refresh/retries, demand/inventory publications and service/recovery prep for all owners.",
        "snapshot_cost": "A subset of owner/preparation costs; do not add again.",
        "persistence_cost": "A subset of precommit evaluator costs; do not add again.",
        "callback_planning_zeros": "R0 planning_timing_not_captured_here values are not timing observations.",
        "complete_request_100ms_certified": False,
    }
    return result


def verified_callbacks(path, receipt, coverage):
    require(sha(path) == receipt["sha256"], "callback_file_sha256")
    previous, count = "0"*64, 0
    with gzip.open(path, "rt", encoding="utf8") as stream:
        for line in stream:
            envelope = json.loads(line)
            row = envelope["record"]
            require(row["audit_sequence"] == count and row["previous_record_sha256"] == previous
                and digest(row) == envelope["record_sha256"], "callback_hash_chain")
            previous, count = envelope["record_sha256"], count+1
            yield row
    require(count == receipt["records"] and previous == receipt["tail_record_sha256"],
        "callback_complete_tail")
    coverage.update(records_verified=count, expected_records=receipt["records"],
        full_hash_chain_verified=True, tail_sha256=previous)


def _index(data, result, calls, state):
    groups = defaultdict(list)
    for call in calls:
        groups[call["request"]["request_id"]].append(call)
    for identity, attempts in groups.items():
        require(sum(not row["retry"] for row in attempts) == 1,
            "exactly_one_initial_submit:" + identity)
        require(all(row["request"] == attempts[0]["request"] and row["kind"] == attempts[0]["kind"]
            for row in attempts), "immutable_retry_payload:" + identity)
    legs, by_leg, by_tray = {}, defaultdict(list), defaultdict(list)
    for row in result["leg_identities"]:
        identity = row["transport_leg_id"]
        require(identity not in legs, "unique_native_leg_identity")
        legs[identity] = row
    for order, row in enumerate(result["receipts"]):
        event = dict(row, receipt_index=order)
        by_leg[row["transport_leg_id"]].append(event)
        by_tray[row["tray_id"]].append(event)
    transfers = {r["request_id"]: r for r in result["transfers"]}
    require(len(transfers) == len(result["transfers"]), "unique_native_transfer")
    snapshots = {}
    for identity, row in state["client"]["outbox"].items():
        if row["kind"] == "planning_snapshot":
            ack = row.get("client_view", {}).get("last_delivered_ack", {})
            envelope = ack.get("planning_snapshot")
            summary = ack.get("planning_snapshot_summary")
            if envelope is not None or summary is not None:
                message = envelope["capture"]["message_id"] if envelope is not None else summary["message_id"]
                require(message not in snapshots, "unique_source_capture_message")
                snapshots[message] = {"request_id": identity, "payload": row["payload"],
                    "ack": {k: v for k, v in ack.items() if k not in
                        ("planning_snapshot", "planning_snapshot_summary")},
                    "envelope_sha256": digest(envelope) if envelope is not None else summary["envelope_sha256"]}
    return {"calls": groups, "legs": legs, "leg_events": by_leg, "tray_events": by_tray,
        "transfers": transfers, "outbox": state["client"]["outbox"], "snapshots": snapshots,
        "trays": data["trays"], "jobs": {r["business_bag_id"]: r for r in data["jobs"]}}


def _transfer_chain(index, identity, intended):
    calls = index["calls"].get(identity, [])
    require(calls and calls[0]["kind"] == "transfer", "post_submit_call_exists")
    request = calls[0]["request"]
    require({k: request.get(k) for k in intended} == intended, "intended_request_payload_binding")
    require(calls[0]["at"] == intended["issued_at"], "post_request_submission_clock")
    require(index["outbox"][identity]["payload"] == request, "saved_outbox_matches_request")
    native = index["transfers"].get(identity)
    ack = index["outbox"][identity].get("client_view", {}).get("last_delivered_ack")
    matched_legs = [r for key, r in index["legs"].items()
        if key.startswith(identity+":empty_return:") and r["kind"] == "empty_return"]
    row = {"request_id": identity, "request": request, "initial_submitted_at": calls[0]["at"],
        "retries": sum(c["retry"] for c in calls), "native_transfer": native,
        "delivered_ack": ack, "native_leg_count": len(matched_legs),
        "unique_leg": matched_legs[0] if len(matched_legs) == 1 else None,
        "request_payload_verified": True, "native_entity_chain_verified": False,
        "received_chain_verified": False, "direct_next_load_verified": False,
        "reason": "no_unique_native_empty_leg", "strict_nonharm_certified": False}
    if len(matched_legs) != 1:
        return row
    leg = matched_legs[0]
    require(index["trays"][leg["tray"]]["tray_id"] == request["tray_id"]
        and leg["job"] == -1, "empty_leg_tray_identity")
    events = index["leg_events"][leg["transport_leg_id"]]
    require(all(e["tray_id"] == request["tray_id"] for e in events), "leg_event_tray_identity")
    entries = [e for e in events if e["event"] == "EDGE_ENTER"]
    received = [e for e in events if e["event"] == "EMPTY_RECEIVED"]
    positive = ack is not None and ack["status"] in ("granted", "departed", "received")
    row.update(first_edge=entries[0] if entries else None, positive_delivered_ack=positive)
    if not native or native["tray"] != leg["tray"] or not entries or not positive:
        row["reason"] = "native_binding_edge_or_positive_ack_missing"
        return row
    require(entries[0]["from"] == request["source"]
        and entries[0]["time"] >= request["earliest_departure"], "first_edge_source_and_clock")
    row["native_entity_chain_verified"] = True
    if len(received) != 1 or native["status"] != "received":
        row["reason"] = "not_received_by_endpoint"
        return row
    receipt = received[0]
    require(receipt["node"] == request["destination"]
        and receipt["time"] == native["received_at"] and entries[0]["time"] <= receipt["time"],
        "receive_destination_and_native_clock")
    row.update(received_chain_verified=True, empty_received=receipt)
    later = [e for e in index["tray_events"][request["tray_id"]]
        if e["receipt_index"] > receipt["receipt_index"]]
    load = next((e for e in later if e["event"] == "LOAD_START"), None)
    row["next_load"] = load
    if load is None:
        row["reason"] = "received_without_later_load_by_endpoint"
        return row
    intervening = [e for e in later if e["receipt_index"] < load["receipt_index"]
        and e["event"] == "EDGE_ENTER"
        and index["legs"][e["transport_leg_id"]]["kind"] == "empty_return"]
    row["intervening_empty_leg_ids"] = sorted({e["transport_leg_id"] for e in intervening})
    if load["node"] != request["destination"] or intervening:
        row["reason"] = "next_load_at_other_node_or_after_another_empty_move"
        return row
    job = index["jobs"][load["business_bag_id"]]
    require(job["origin"] == request["destination"] and job["arrival"] <= load["time"],
        "next_business_load_identity_and_arrival")
    row.update(direct_next_load_verified=True, reason="direct_destination_next_load",
        next_business_bag_id=job["business_bag_id"], next_bag_arrival=job["arrival"],
        received_before_next_bag_arrival=receipt["time"] < job["arrival"],
        same_bag_wait_savings_claimed=False)
    return row


def _inventory_binding(callback, control_decision, index):
    observation = callback["observation"]
    chosen = callback["chosen_decision"]
    require(chosen == control_decision, "callback_post_decision_matches_control_record")
    evidence = chosen["inventory_return"]
    require(evidence["selected"] is True and len(chosen["intents"]) == 1, "single_selected_post_intent")
    action = evidence["selected_action"]
    require(action["public_state_digest"] == digest(observation)
        and action["baseline_batch_digest"] == digest([])
        and action["intent"] == chosen["intents"][0], "fresh_empty_priority_post_binding")
    actual = inventory_view(observation)
    require(json_form(actual) == json_form(evidence["inventory"]), "recomputed_legal_inventory_matches")
    target = actual["nodes"][chosen["intents"][0]["destination"]]
    row = {"inventory_validated": True, "inventory_source": target["source"],
        "target_stock": target["reported_actual_empty"], "target_as_of": target["as_of"],
        "fallback_reason": evidence.get("fallback_reason"), "delivered_snapshot_source_ack_bound": False}
    if target["source"] == "delivered_planning_snapshot":
        envelopes = [e for e in observation["planning_snapshots"]
            if e["capture"]["message_id"] == target["message_id"]]
        require(len(envelopes) == 1, "single_consumed_target_snapshot")
        envelope = envelopes[0]
        source = index["snapshots"].get(target["message_id"])
        require(source is not None and source["ack"]["status"] == "delivered"
            and source["envelope_sha256"] == digest(envelope)
            and source["ack"]["result_id"] == target["message_id"]
            and source["payload"]["owner_id"] == target["source_owner"]
            and source["payload"]["target_owner"] == observation["owner_id"],
            "actual_source_capture_command_ack_binding")
        row.update(delivered_snapshot_source_ack_bound=True, message_id=target["message_id"],
            capture_request_id=source["request_id"], capture_payload_sha256=envelope["payload_sha256"],
            captured_at=envelope["capture"]["captured_at"], delivered_at=envelope["delivered_at"],
            valid_until=envelope["capture"]["valid_until"])
    return row


def recovery_summary(index, state, result):
    capabilities = {r["request_id"]: r["capability"] for r in state.get("failed_empty_recoveries", {}).values()}
    rows = []
    for identity, calls in index["calls"].items():
        if calls[0]["kind"] != "recover_failed_empty":
            continue
        request = calls[0]["request"]
        capability = capabilities.get(identity)
        require(capability is not None and all(request[k] == v for k, v in capability.items()
            if k != "failure_reason"), "original_public_recovery_capability")
        ack = index["outbox"][identity].get("client_view", {}).get("last_delivered_ack")
        events = index["leg_events"][request["failed_transport_leg_id"]]
        failures = [e for e in events if e["event"] == "LEG_FAILED"]
        grants = [e for e in events if e["event"] == "EMPTY_RECOVERY_GRANTED"
            and e["reason"] == identity+":owner_failed_empty_recovery"]
        prior = index["transfers"].get(request["failed_transfer_request_id"])
        row = {"request_id": identity, "request": request, "original_capability": capability,
            "immutable_retry_count": sum(c["retry"] for c in calls), "delivered_ack": ack,
            "failed_history_retained": bool(prior and prior["status"] == "failed" and failures),
            "prior_failed_transfer": prior, "failure_receipts": failures, "recovery_receipts": grants,
            "verified_recovery": False}
        if ack and ack["status"] == "recovered":
            require(row["failed_history_retained"] and len(grants) == 1
                and ack["result_id"] == request["failed_transfer_request_id"]
                and ack["executed_at"] == grants[0]["time"]
                and grants[0]["tray_id"] == request["tray_id"]
                and grants[0]["node"] == grants[0]["from"] == grants[0]["to"] == request["from"]
                and failures[-1]["time"] <= grants[0]["time"]
                and failures[-1]["reason"] == capability["failure_reason"]
                == "departure_lease_expired_before_physical_entry"
                and not any(e["event"] == "EDGE_ENTER" for e in events),
                "narrow_recovery_native_chain")
            row["verified_recovery"] = True
        rows.append(row)
    return {"requests": len(rows), "verified_recoveries": sum(r["verified_recovery"] for r in rows),
        "retry_count": sum(r["immutable_retry_count"] for r in rows),
        "all_native_failed_transfer_count": sum(r["status"] == "failed" for r in result["transfers"]),
        "all_native_leg_failed_receipt_count": sum(r["event"] == "LEG_FAILED" for r in result["receipts"]),
        "final_quarantined_tray_count": sum(r["mode"] == "quarantined" for r in result["trays"]),
        "rows": rows, "recovery_is_learning_benefit": False}


def _compact_refresh_state(state, tick):
    """Retain request/ACK identities, not repeated full source capture bodies."""
    for refreshed in tick.get("refreshed", []):
        identity = refreshed["request_id"]
        require(identity in state["client"]["outbox"], "refreshed_request_was_submitted")
        view = refreshed["view"]
        compact_view = {k: v for k, v in view.items() if k != "last_delivered_ack"}
        if "last_delivered_ack" in view:
            ack = view["last_delivered_ack"]
            compact_ack = {k: v for k, v in ack.items() if k != "planning_snapshot"}
            if "planning_snapshot" in ack:
                envelope = ack["planning_snapshot"]
                compact_ack["planning_snapshot_summary"] = {
                    "message_id": envelope["capture"]["message_id"],
                    "envelope_sha256": digest(envelope)}
            compact_view["last_delivered_ack"] = compact_ack
        state["client"]["outbox"][identity]["client_view"] = compact_view
    for action in tick.get("service_actions", []):
        if action.get("kind") == "recover_failed_empty":
            identity = action["request_id"]
            require(identity not in state["failed_empty_recoveries"], "unique_recovery_capability_record")
            state["failed_empty_recoveries"][identity] = {
                "request_id": identity, "capability": action["capability"]}


def analyze(*, data, result, calls, records, state, callbacks, activate_at=7200.,
            audit_receipt=None, snapshot_reads=None):
    reconstruct = state is None
    if reconstruct:
        state = {"client": {"outbox": {c["request"]["request_id"]: {
            "kind": c["kind"], "payload": c["request"]} for c in calls if not c["retry"]}},
            "failed_empty_recoveries": {}}
    selected, reasons, phases = {}, Counter(), Counter()
    post_owner_ticks = set()
    timing_records = []
    for tick in records:
        if reconstruct:
            _compact_refresh_state(state, tick)
        timing_records.append({**{k: tick[k] for k in
            ("tick", "at", "preparation_compute_ms", "offline_tick_start_observer_ms") if k in tick},
            "owner_decisions": [{k: owner[k] for k in ("owner_id", "compute_ms", "offline_evaluator_ms")
                if k in owner} for owner in tick["owner_decisions"]]})
        for owner in tick["owner_decisions"]:
            post = owner.get("inventory_return")
            if post is None:
                continue
            reasons[post["reason"]] += 1
            key = (owner["owner_id"], tick["at"])
            require(key not in post_owner_ticks, "unique_post_phase_per_owner_tick")
            post_owner_ticks.add(key)
            require(len(post["attempts"]) <= 1, "at_most_one_new_post_submit")
            if not post["attempts"]:
                continue
            require(post["new_submissions"] == 1 and post["reason"] == "inventory_return_submitted",
                "post_submission_quota_evidence")
            selected[key] = {"tick": tick["tick"], "post": post, "callback": None}
    index = _index(data, result, calls, state)
    callback_count, untimed_planning = 0, 0
    for callback in callbacks:
        callback_count += 1
        phases[callback.get("protocol_phase", "unspecified")] += 1
        untimed_planning += callback.get("planning_timing_not_captured_here") is True
        chosen = callback.get("chosen_decision", {})
        if chosen.get("inventory_return", {}).get("selected") is not True:
            continue
        key = (callback["owner_id"], callback["observed_at"])
        require(key in selected and selected[key]["callback"] is None, "selected_post_has_unique_control_record")
        row = selected[key]
        row["inventory_binding"] = _inventory_binding(callback, row["post"]["decision"], index)
        row["callback"] = {"audit_sequence": callback.get("audit_sequence"),
            "record_sha256": digest(callback), "public_state_sha256": digest(callback["observation"])}
    witnesses = []
    for (owner, at), row in selected.items():
        require(row["callback"] is not None, "every_selected_post_has_captured_current")
        post = row["post"]
        request_id = post["attempts"][0]["request_id"]
        witness = _transfer_chain(index, request_id, post["decision"]["intents"][0])
        witness.update(owner_id=owner, observed_at=at, tick=row["tick"],
            inventory_binding=row["inventory_binding"], callback=row["callback"],
            rule_reason=post["decision"]["inventory_return"]["reason"])
        witnesses.append(witness)
    return {"schema": SCHEMA, "status": "audited", "inventory_returns": {
        "post_owner_ticks": len(post_owner_ticks), "post_reasons": dict(reasons),
        "submitted": len(witnesses), "callbacks_validated": len(selected),
        "delivered_snapshot_bound": sum(w["inventory_binding"]["delivered_snapshot_source_ack_bound"] for w in witnesses),
        "local_sensor_target": sum(w["inventory_binding"]["inventory_source"] == "current_local_sensor" for w in witnesses),
        "unknown_inventory_fallback": sum(w["inventory_binding"]["fallback_reason"] == "inventory_unknown" for w in witnesses),
        "native_entity_chain_verified": sum(w["native_entity_chain_verified"] for w in witnesses),
        "received_chain_verified": sum(w["received_chain_verified"] for w in witnesses),
        "direct_destination_next_load": sum(w["direct_next_load_verified"] for w in witnesses),
        "strict_prearrival_next_load": sum(w.get("received_before_next_bag_arrival", False) for w in witnesses),
        "native_status_counts": dict(Counter((w["native_transfer"] or {}).get("status", "missing") for w in witnesses)),
        "chain_reason_counts": dict(Counter(w["reason"] for w in witnesses)), "witnesses": witnesses},
        "recovery": recovery_summary(index, state, result),
        "callback_coverage": {"records_examined": callback_count, "protocol_phase_counts": dict(phases),
            "planning_values_explicitly_unmeasured": untimed_planning,
            "selected_post_inventory_recomputed": len(selected),
            "ack_index_reconstructed_from_all_control_refreshes": reconstruct},
        "timing": timing_summary(timing_records, activate_at=activate_at,
            audit_receipt=audit_receipt, snapshot_reads=snapshot_reads),
        "causal_scope": "Observed lifecycle chains only. No single-action causal benefit, same-bag wait saving, or service nonharm is inferred.",
        "native_runs_started": 0, "fits_started": 0}


def audit_run(directory, *, output=None):
    began = time.perf_counter()
    directory = Path(directory).resolve()
    require((directory / "worker_report.json").is_file(), "worker_not_closed")
    report, plan = read(directory / "worker_report.json"), read(directory / "plan.json")
    required = ("final_result.json.gz", "client_calls.json.gz", "control_records.json.gz",
        "controller_final_state.json.gz", "inventory_snapshot_reads.json.gz",
        "callback_audit_receipt.json", "callback_audit.jsonl.gz")
    require(all((directory / name).is_file() for name in required), "closed_run_incomplete_saved_evidence")
    require(sha(plan["input"]["path"]) == plan["input"]["sha256"], "bound_input_bytes")
    require(sha(plan["source_bundle"]["path"]) == plan["source_bundle"]["sha256"], "bound_source_manifest")
    sources = read(plan["source_bundle"]["path"])
    require(digest(sources["files"]) == sources["source_manifest_sha256"]
        == plan["source_manifest_sha256"], "source_manifest_identity")
    actor_pins = {}
    relative_directory = "scripts/experiments/g31_ics_circulation/"
    for name in ("foundation_airport_inventory_rule.py", "foundation_airport_protocol_v2.py",
                 "protocol_control.py", "analytic_control.py"):
        relative = relative_directory+name
        require(sha(Path(sources["root"])/relative) == sources["files"][relative],
            "frozen_actor_source_bytes:" + name)
        actor_pins[relative] = sources["files"][relative]
    require(sha(Path(__file__).with_name("foundation_airport_inventory_rule.py"))
        == actor_pins[relative_directory+"foundation_airport_inventory_rule.py"],
        "inventory_recomputation_uses_same_rule_source")
    data = read(plan["input"]["path"])
    require(digest(data) == plan["input_semantic_sha256"], "bound_input_semantics")
    receipt = read(directory / "callback_audit_receipt.json")
    coverage = {}
    result = analyze(data=data, result=read(directory / "final_result.json.gz"),
        calls=read(directory / "client_calls.json.gz"),
        records=iter_json_array_gz(directory / "control_records.json.gz"),
        state=None,
        callbacks=verified_callbacks(directory / "callback_audit.jsonl.gz", receipt, coverage),
        activate_at=plan["activate_at"], audit_receipt=receipt,
        snapshot_reads=read(directory / "inventory_snapshot_reads.json.gz"))
    result["callback_coverage"].update(coverage)
    result.update(run_name=plan["name"], method=plan["method"], parent=plan["parent"],
        worker_status=report["status"], final_physical_time=report.get("final_physical_time"),
        worker_wall_seconds=report["wall_seconds"], process_resources=report.get("process_resources"),
        audit_before_artifact_sha_seconds=time.perf_counter()-began,
        source_bundle=plan["source_bundle"], source_manifest_sha256=plan["source_manifest_sha256"],
        frozen_actor_source_sha256=actor_pins,
        artifact_sha256={name: sha(directory / name) for name in ("plan.json", "worker_report.json", *required)},
        audit_source_sha256=sha(__file__))
    result["audit_wall_seconds"] = time.perf_counter()-began
    path = Path(output) if output else directory / "inventory_mechanism_audit_001.json"
    require(not path.exists(), "fresh_audit_output_required")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf8")
    return path, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    parser.add_argument("--output")
    args = parser.parse_args()
    path, result = audit_run(args.directory, output=args.output)
    print(json.dumps({"path": str(path), "run_name": result["run_name"],
        "callback_coverage": result["callback_coverage"],
        "inventory_returns": {k: v for k, v in result["inventory_returns"].items() if k != "witnesses"},
        "recoveries": result["recovery"]["verified_recoveries"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
