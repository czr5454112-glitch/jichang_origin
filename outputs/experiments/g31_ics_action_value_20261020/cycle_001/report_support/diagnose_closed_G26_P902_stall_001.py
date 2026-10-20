"""Offline diagnosis of three explicitly released, closed G26/P902 branches.

No simulator/model import or new simulation is performed. Full callback streams
are optional: only their first 241 records are examined and copied to small
artifact witnesses. A portable rerun can use those witnesses instead.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path


NAMES = ("G_N26_C00_P902_001", "G_N26_C10_P902_001", "G_N26_C11_S29_P902_001")
EVENTS = (
    "LOAD_START", "LOAD_COMPLETE", "UNLOAD_START", "UNLOAD_COMPLETE",
    "LEG_START", "LEG_COMPLETE", "EDGE_ENTER", "EDGE_EXIT", "EMPTY_RECEIVED",
    "STORAGE_ENTER", "STORAGE_RELEASE", "RESOURCE_WAIT", "RESOURCE_WAKE",
    "EXPORT_GRANTED", "LEG_FAILED", "UNUSED_RECEIVING_RELEASED",
    "BAG_ARRIVAL", "TRANSFER_REJECTED", "PROTOCOL_ACK_DELIVERED",
)


def require(ok, reason):
    if not ok:
        raise ValueError("stall_diagnosis:" + reason)


def read(path):
    with (gzip.open(path, "rt", encoding="utf8") if path.suffix == ".gz"
          else path.open(encoding="utf8")) as stream:
        return json.load(stream)


def sha(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def reference(path):
    return {"path": str(path.resolve()), "sha256": sha(path), "bytes": path.stat().st_size}


def callback_prefix(directory, support):
    witness = support / (directory.name + "_initial_241_callback_prefix_001.jsonl.gz")
    original = directory / "callback_audit.jsonl.gz"
    source = original if original.exists() else witness
    require(source.is_file(), "actual_callback_prefix_required")
    previous, lines, records = "0" * 64, [], []
    with gzip.open(source, "rb") as stream:
        for line in stream:
            packet = json.loads(line)
            row = packet["record"]
            require(row["audit_sequence"] == len(records)
                    and row["previous_record_sha256"] == previous
                    and digest(row) == packet["record_sha256"], "prefix_hash_chain")
            previous = packet["record_sha256"]
            records.append(row)
            lines.append(line)
            if len(records) == 241:
                break
    require(len(records) == 241 and records[-1]["observed_at"] == 7200.,
            "exact_first_post_warmup_callback")
    require(all(row["status"] == "ordinary_warmup" for row in records[:-1]),
            "all_preceding_callbacks_are_warmup")
    if not witness.exists():
        with witness.open("xb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as zipped:
                for line in lines:
                    zipped.write(line)
    else:
        with gzip.open(witness, "rb") as stream:
            require(stream.read() == b"".join(lines), "existing_witness_exact_prefix")
    return records[-1], {
        "prefix_witness": reference(witness),
        "verified_prefix_records": len(records), "tail_record_sha256": previous,
        "original_stream_receipt": reference(directory / "callback_audit_receipt.json"),
        "full_stream_scanned": False,
        "scope": "All 240 warmup records plus the first post-activation owner callback, not the full stream.",
    }


def diagnose_one(directory, receipt, support):
    files = ("input.json", "plan.json", "receipt.json", "final_result.json.gz",
             "client_calls.json.gz", "execution_evidence.json.gz",
             "activation_prefix.json.gz", "callback_audit_receipt.json")
    data, plan = (read(directory / name) for name in files[:2])
    require(sha(directory / "plan.json") == receipt["plan_sha256"]
            and sha(directory / "input.json") == plan["input"]["sha256"], "plan_input_binding")
    result = read(directory / "final_result.json.gz")
    calls = read(directory / "client_calls.json.gz")
    execution = read(directory / "execution_evidence.json.gz")
    activation = read(directory / "activation_prefix.json.gz")
    current, prefix_audit = callback_prefix(directory, support)
    now = result["physical_clock"]
    require(now == 59400. and result["advance"]["status"] == "reached"
            and result["advance"]["horizon_complete"] is True, "complete_fixed_endpoint")
    require(len(data["jobs"]) == len(result["jobs"]) == 28506, "whole_population")
    require(len(data["trays"]) == len(result["trays"]) == 26, "whole_fleet")
    require({j["business_bag_id"] for j in data["jobs"]}
            == {j["business_bag_id"] for j in result["jobs"]}, "job_identity")
    require({j["tray_id"] for j in data["trays"]}
            == {j["tray_id"] for j in result["trays"]}, "tray_identity")
    events, tray_events, leg_events = defaultdict(list), defaultdict(list), defaultdict(list)
    for event in result["receipts"]:
        events[event["event"]].append(event)
        if event["tray_id"]:
            tray_events[event["tray_id"]].append(event)
        if event["transport_leg_id"]:
            leg_events[event["transport_leg_id"]].append(event)
    completions = {e["business_bag_id"]: e["time"] for e in events["UNLOAD_COMPLETE"]}
    require(completions == {j["business_bag_id"]: j["completed_at"] for j in result["jobs"]
                            if j["status"] == "completed"}, "completion_receipt_identity")
    cost = math.fsum(max(0., min(completions.get(j["business_bag_id"], math.inf), now)
                             - max(7200., j["arrival"])) for j in data["jobs"])
    require(abs(cost - receipt["worker"]["cost"]["backlog_integral_bag_seconds"]) < 1e-6,
            "full_cost_recalculation")
    timeline = {}
    for name in EVENTS:
        selected = events[name]
        first = min((e["time"] for e in selected), default=None)
        last = max((e["time"] for e in selected), default=None)
        timeline[name] = {
            "count": len(selected), "first_at": first, "last_at": last,
            "seconds_since_last_at_endpoint": now - last if last is not None else None,
            "last_receipt": max(selected, key=lambda e: e["time"]) if selected else None,
        }
    requests = {}
    for call in calls:
        if call["kind"] == "transfer":
            requests.setdefault(call["request"]["request_id"], call)
    legs = {leg["runtime_id"]: leg for leg in result["leg_identities"]}
    quarantine = []
    active = []
    for tray in result["trays"]:
        items = tray_events[tray["tray_id"]]
        leg = legs.get(tray["active_leg"])
        latest_waits = [e for e in items if e["event"] == "RESOURCE_WAIT"
                        and leg and e["transport_leg_id"] == leg["transport_leg_id"]]
        latest_progress = [e for e in items if e["event"] in
                           ("EDGE_ENTER", "EDGE_EXIT", "LOAD_START", "UNLOAD_COMPLETE", "EMPTY_RECEIVED")]
        if tray["mode"] not in ("empty", "quarantined"):
            active.append({
                "tray": tray, "active_leg_identity": leg,
                "latest_actual_resource_wait_for_active_leg": latest_waits[-1] if latest_waits else None,
                "latest_physical_or_service_progress": latest_progress[-1] if latest_progress else None,
                "current_exact_wait_resource_index_exported": False,
            })
        if tray["mode"] == "quarantined":
            failures = [e for e in items if e["event"] == "LEG_FAILED"]
            details = []
            for failure in failures:
                rid = failure["transport_leg_id"].rsplit(":empty_return:", 1)[0]
                history = leg_events[failure["transport_leg_id"]]
                details.append({
                    "failure": failure, "actual_submission": requests.get(rid),
                    "native_transfer": next((t for t in result["transfers"] if t["request_id"] == rid), None),
                    "first_edge_count": sum(e["event"] == "EDGE_ENTER" for e in history),
                    "unused_receiving_release_count": sum(e["event"] == "UNUSED_RECEIVING_RELEASED"
                                                         for e in history),
                    "physical_edge_exits_after_failure": sum(e["time"] > failure["time"]
                                                            for e in events["EDGE_EXIT"]),
                    "job_completions_after_failure": sum(e["time"] > failure["time"]
                                                        for e in events["UNLOAD_COMPLETE"]),
                })
            quarantine.append({"tray": tray, "failures": details})
    changed = [r for r in execution["rows"] if r["decision_differs"]]
    observation = activation["observation"]
    require(observation["now"] == 7200. and current["observation"] == observation,
            "first_callback_equals_saved_activation_observation")
    last_edge = timeline["EDGE_EXIT"]["last_at"]
    last_service = timeline["UNLOAD_COMPLETE"]["last_at"]
    windows = []
    for begin in (7200., 14400., 21600., 25200., 36000., 54000.):
        windows.append({
            "start_exclusive": begin, "end_inclusive": now,
            "new_arrivals": sum(begin < e["time"] <= now for e in events["BAG_ARRIVAL"]),
            "new_completions": sum(begin < e["time"] <= now for e in events["UNLOAD_COMPLETE"]),
            "physical_edge_exits": sum(begin < e["time"] <= now for e in events["EDGE_EXIT"]),
            "new_load_starts": sum(begin < e["time"] <= now for e in events["LOAD_START"]),
        })
    return {
        "name": directory.name, "status": receipt["status"], "at": now,
        "information_variant": plan["information_variant"], "parent": plan["parent"],
        "input_references": {name: reference(directory / name) for name in files},
        "input_semantic_sha256": plan["input"]["semantic_sha256"],
        "binary_sha256": plan["binary"]["sha256"], "sources": plan["sources"],
        "activation_prefix": activation["prefix"],
        "warmup_at_7200": {
            "arrived_jobs_from_full_input": sum(j["arrival"] <= 7200. for j in data["jobs"]),
            "first_arrival_at": min(j["arrival"] for j in data["jobs"]),
            "physical_trays": len(observation["trays"]),
            "tray_modes": dict(Counter(t["mode"] for t in observation["trays"])),
            "any_active_leg": any(t.get("active_leg", -1) >= 0 for t in observation["trays"]),
            "any_inflight_edge": any(t["edge_to"] >= 0 for t in observation["trays"]),
            "first_callback_baseline_intents": current["baseline_decision"]["intents"],
            "first_callback_chosen_intents": current["chosen_decision"]["intents"],
            "first_callback_public_state_digest": current["public_state_digest"],
            "first_callback_forecast_identity": {
                key: current["forecast_evidence"][key]
                for key in ("model_id", "forecast_sha256", "forecast_provenance",
                            "actual_callback_consumption")
            } if current.get("forecast_evidence") else None,
            "prefix_audit": prefix_audit,
            "warmup_already_stalled_under_arrived_demand": False,
        },
        "native_summary": result["native_summary"],
        "job_status_counts": dict(Counter(j["status"] for j in result["jobs"])),
        "tray_mode_counts": dict(Counter(t["mode"] for t in result["trays"])),
        "physical_inflight_trays": sum(t["edge_to"] >= 0 for t in result["trays"]),
        "whole_28506_backlog_integral_bag_seconds": cost,
        "event_timeline": timeline, "endpoint_active_trays": active,
        "quarantined_trays": quarantine, "selected_windows": windows,
        "first_logged_changed_initial_decision": min(changed, key=lambda r: r["audit_sequence"]) if changed else None,
        "long_no_service_tail_seconds": now - last_service if last_service is not None else None,
        "long_no_physical_exit_tail_seconds": now - last_edge if last_edge is not None else None,
        "protocol_and_arrivals_after_last_physical_exit": {
            event: sum(e["time"] > last_edge for e in events[event])
            for event in ("BAG_ARRIVAL", "TRANSFER_REJECTED", "PROTOCOL_ACK_DELIVERED",
                          "PROTOCOL_COMMAND_ACK_DELIVERED")},
        "segment_summaries": [{k: row[k] for k in ("target", "physical_time", "status", "summary")}
                              for row in receipt["worker"]["segments"]],
        "exact_offline_diagnostics_saved": (directory / "offline_diagnostics.json.gz").exists(),
        "exact_native_wait_graph_available": False,
        "local_hold_wait_cycle_status": "unknown: exact native resource_waits/alternative indices were not exported",
        "permanent_global_deadlock_proven": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "fresh_output_required")
    cycle, support = args.cycle.resolve(), args.output.resolve().parent
    require(support.is_dir(), "output_parent_exists")
    # All three receipts are checked first, before opening their other outputs.
    receipts = {name: read(cycle / name / "receipt.json") for name in NAMES}
    require(all(r["status"] == "complete" for r in receipts.values()), "all_complete_receipts_required")
    rows = [diagnose_one(cycle / name, receipts[name], support) for name in NAMES]
    a, forecast, b = rows
    require(all(a["activation_prefix"] == row["activation_prefix"] for row in rows),
            "same_complete_warmup_prefix")
    require(all(a["input_semantic_sha256"] == row["input_semantic_sha256"]
            and a["binary_sha256"] == row["binary_sha256"] and a["sources"] == row["sources"]
            for row in rows),
            "same_input_binary_runtime_sources")
    require(all(a["warmup_at_7200"]["first_callback_public_state_digest"]
            == row["warmup_at_7200"]["first_callback_public_state_digest"] for row in rows),
            "same_actual_current_at_first_choice")
    forecast_identity = forecast["warmup_at_7200"]["first_callback_forecast_identity"]
    require(forecast_identity is not None
            and forecast_identity == b["warmup_at_7200"]["first_callback_forecast_identity"]
            and forecast_identity["actual_callback_consumption"] is True,
            "same_actually_consumed_forecast_at_first_choice")
    output = {
        "schema": "g31.closed_G26_P902_stall_diagnosis.v1",
        "read_scope": list(NAMES), "status": "closed_read_only_diagnosis",
        "rows": rows,
        "comparison": {
            "same_full_activation_prefix_verified": True,
            "same_input_binary_and_runtime_sources_verified": True,
            "completed_delta_C11_minus_C00": b["job_status_counts"]["completed"] - a["job_status_counts"]["completed"],
            "backlog_integral_advantage_C11_vs_C00_bag_seconds":
                a["whole_28506_backlog_integral_bag_seconds"] - b["whole_28506_backlog_integral_bag_seconds"],
            "C11_vs_C00_information_sets_differ": True,
            "completed_delta_C11_minus_C10":
                b["job_status_counts"]["completed"] - forecast["job_status_counts"]["completed"],
            "backlog_integral_advantage_C11_vs_C10_bag_seconds":
                forecast["whole_28506_backlog_integral_bag_seconds"] - b["whole_28506_backlog_integral_bag_seconds"],
            "C11_vs_C10_same_information_whole_policy_comparison": True,
            "C11_vs_C10_first_callback_actual_forecast_identity_equal": True,
            "first_logged_policy_divergence_at": b["first_logged_changed_initial_decision"]["observed_at"],
            "first_choice_isolated_causal_effect_established": False,
        },
        "interpretation": [
            "At 7200 all three runs had zero arrived bags and all 26 physical trays empty; this was not an already-demand-stalled warmup.",
            "The first post-warmup C11 callback changes an actual available empty allocation; the recorded C00/C10 choices permit comparison at the same current state. Full-policy trajectories then differ.",
            "The C00 receipt history establishes a finite-window system-wide lack of further physical movement and service after its final recorded edge/service events, despite later arrivals and protocol activity.",
            "Exact native resource-wait alternatives and deadlines were not exported in these prospective runs; no SCC is invented and permanent global deadlock is not proven.",
            "Quarantine is real capacity loss. Service and physical movement continued after the C00 quarantine, so that event alone is not the start of the final global no-progress tail.",
            "C11 versus C00 combines prediction and learning information differences. The separate C11-versus-C10 contrast uses the predeclared same-information arms and is a whole-policy contrast on one synthetic parent/fleet cell.",
            "The first different action is a traced mechanism witness, not an isolated causal attribution of all later whole-policy benefit.",
            "J is physical bag-seconds; callback wall time pauses native time and is not a validated asynchronous latency cost.",
        ],
        "strict_nonharm_certified": False, "full_G2_established": False,
        "native_starts": 0, "fit_calls": 0, "runtime_edits": 0,
        "auditor": reference(Path(__file__)),
    }
    # The source pins are already preserved in each plan; avoid repeating 842
    # hashes in this smaller diagnostic after comparing them above.
    for row in rows:
        row["runtime_sources_verified_against_peer"] = True
        del row["sources"]
    with args.output.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(output, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"output": str(args.output.resolve()), "sha256": sha(args.output),
                      "comparison": output["comparison"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
