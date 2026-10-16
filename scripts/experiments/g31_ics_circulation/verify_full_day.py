"""Read-only full-denominator verification of a completed sharded execution.

This does not load a native extension, invent completion for unfinished jobs,
or certify whole-request timing from the owner-activation measurements.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path

from .finite_reference import outcome_cost
from .native_host import audit_result
from .original_workload import ProxyContract, build_input, json_digest
from .run_original_protocol import add_protocol_contract
from .validate_protocol_control import replay_input, scenarios

ROOT = Path(__file__).absolute().parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_gz(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def command_option(receipt, name):
    command = receipt["command"]
    if command.count(name) != 1 or command.index(name) + 1 >= len(command):
        raise ValueError("full_day:missing_or_duplicate_command_option")
    return command[command.index(name) + 1]


def verify_input_provenance(directory, data, receipt, expected_total, horizon):
    """Recreate the offered input, including all contracts, without any native run.

    Equal population size alone does not prove that the original workload was
    retained. Compare the entire reconstructed input and original manifest.
    This helper alone says nothing about completion of a running execution.
    """
    suite = command_option(receipt, "--suite")
    if float(command_option(receipt, "--horizon")) != horizon:
        raise ValueError("full_day:command_horizon_mismatch")
    if suite == "synthetic":
        _, expected, _ = scenarios()[1]
        manifest_hash = None
    elif suite in {"full1x", "full2x"}:
        scale = int(suite[-2])
        if expected_total != 28506 * scale or horizon != 86400.:
            raise ValueError("full_day:original_scope_mismatch")
        contract = ProxyContract("nanning-on-carrier-proxy-v1-n4-s4-t2", 4, 4, 2,
                                 1., 1., 0., "finite_berth_waiting_research_proxy")
        expected, manifest, _ = build_input(scale=scale, contract=contract,
            horizon=horizon, max_events=int(command_option(receipt, "--event-budget")), trace_limit=0)
        manifest_path = Path(directory) / "input_manifest.json"
        saved = json.loads(manifest_path.read_text(encoding="utf-8"))
        if json_digest(saved) != json_digest(manifest):
            raise ValueError("full_day:original_manifest_mismatch")
        manifest_hash = sha(manifest_path)
        expected = add_protocol_contract(expected)
    else:
        raise ValueError("full_day:unsupported_offered_scope")
    expected["owner_notifications"] = {"enabled": True}
    if len(expected["jobs"]) != expected_total or json_digest(data) != json_digest(expected):
        raise ValueError("full_day:offered_input_changed")
    return {"suite": suite, "reconstructed_offered_input_sha256": json_digest(expected),
            "input_manifest_sha256": manifest_hash, "new_native_executions": 0}


def business_counts(data, result, horizon, expected_total):
    if not math.isfinite(horizon) or horizon < 0 or type(expected_total) is not int or expected_total < 1:
        raise ValueError("full_day:invalid_business_scope")
    contracts = {j["business_bag_id"]: j for j in data["jobs"]}
    outcomes = {j["business_bag_id"]: j for j in result["jobs"]}
    if (len(contracts) != expected_total or len(contracts) != len(data["jobs"])
            or len(outcomes) != len(result["jobs"]) or contracts.keys() != outcomes.keys()):
        raise ValueError("full_day:missing_duplicate_or_extra_business_identity")
    completed, failed, strict_late, cost = 0, 0, 0, 0.
    for identity, contract in contracts.items():
        arrival = contract["arrival"]
        finish = outcomes[identity]["completed_at"]
        deadline = contract.get("deadline", -1.)
        if not (math.isfinite(arrival) and 0 <= arrival <= horizon and math.isfinite(finish)
                and (finish == -1 or finish >= 0) and math.isfinite(deadline)):
            raise ValueError("full_day:invalid_arrival_or_completion")
        done = 0 <= finish <= horizon
        if done and finish < arrival:
            raise ValueError("full_day:completion_before_arrival")
        if finish > horizon:
            raise ValueError("full_day:future_completion_in_final_result")
        if (outcomes[identity]["status"] == "completed") != done:
            raise ValueError("full_day:completion_status_mismatch")
        completed += done
        failed += outcomes[identity]["status"] in {"failed", "quarantined"}
        strict_late += deadline >= 0 and (finish if done else horizon) > deadline
        cost += (finish if done else horizon) - arrival
    return {"offered": expected_total, "completed": completed, "unfinished": expected_total - completed,
            "failed": failed, "strict_deadline_violations_by_horizon": strict_late,
            "restricted_arrival_to_unload_cost": cost,
            "business_status_counts": dict(Counter(j["status"] for j in result["jobs"])),
            "all_business_completed": completed == expected_total,
            "unpaired_zero_regression_certified": False}


def verify(directory, expected_total, horizon):
    directory = Path(directory).resolve()
    load = lambda name: json.loads((directory / name).read_text(encoding="utf-8"))
    receipt, summary, manifest = load("receipt.json"), load("summary.json"), load("run_shards.json")
    if receipt["status"] != "completed" or receipt["exit_code"] != 0 or receipt["source_changed"]:
        raise ValueError("full_day:incomplete_or_invalid_execution")
    if (summary["status"] != "reached" or summary["physical_time"] != horizon or summary["horizon"] != horizon
            or summary["offered_total"] != expected_total or summary["offered_by_current_time"] != expected_total
            or not summary["all_input_arrivals_observed"] or summary["metrics"] is None
            or manifest["status"] != "reached" or not manifest["all_raw_records_retained"]):
        raise ValueError("full_day:censored_or_incomplete_denominator")
    data = read_gz(directory / "input.json.gz")
    provenance = verify_input_provenance(directory, data, receipt, expected_total, horizon)
    source_files = {name: sha(directory / name) for name in
                    ("receipt.json", "summary.json", "run_shards.json", "input.json.gz", "native_offline_diagnostics.json.gz")}
    if provenance["input_manifest_sha256"] is not None:
        source_files["input_manifest.json"] = provenance["input_manifest_sha256"]
    counts = Counter(control_records=0, native_batches=0, client_calls=0)
    next_sequence, owner_max, owner_over, previous_physical_end = 0, 0., 0, 0.
    previous_call_at, previous_wall = 0., 0.
    immutable, calls, created, seen_paths = {}, [], Counter(), set()
    initial_calls, final_calls = {}, {}
    if len(manifest["shards"]) != len(manifest["segments"]):
        raise ValueError("full_day:segment_denominator_mismatch")
    for row, segment in zip(manifest["shards"], manifest["segments"], strict=True):
        path = (directory / row["path"]).resolve()
        if path in seen_paths or not path.is_relative_to(directory) or sha(path) != row["sha256"]:
            raise ValueError("full_day:shard_path_or_hash_mismatch")
        seen_paths.add(path)
        part = read_gz(path)
        shard_start = previous_physical_end
        source_files[row["path"]] = row["sha256"]
        for field in counts:
            if len(part[field]) != row["counts"][field]:
                raise ValueError("full_day:shard_count_mismatch")
            counts[field] += len(part[field])
        sequence = sorted(x["trace_sequence"] for field in ("control_records", "native_batches") for x in part[field])
        if (any(type(value) is not int for value in sequence)
                or sequence != list(range(next_sequence, next_sequence + len(sequence)))
                or any([r["trace_sequence"] for r in part[field]] != sorted(r["trace_sequence"] for r in part[field])
                       for field in ("control_records", "native_batches"))):
            raise ValueError("full_day:missing_duplicate_or_reordered_trace")
        next_sequence += len(sequence)
        chronology = [(r["trace_sequence"], r["at"], r["at"]) for r in part["control_records"]]
        chronology += [(r["trace_sequence"], r["start_at"], r["end_at"]) for r in part["native_batches"]]
        for _, start, end in sorted(chronology):
            if not (math.isfinite(start) and math.isfinite(end) and previous_physical_end == start <= end <= horizon):
                raise ValueError("full_day:invalid_physical_trace_order")
            previous_physical_end = end
        continuation = part["control_continuation"]
        wall = segment["cumulative_control_wall_seconds"]
        if (row["status"] != part["status"] or segment["status"] != part["status"]
                or continuation["status"] != part["status"]
                or not (row["physical_time"] == segment["physical_time"] == continuation["physical_time"] == previous_physical_end)
                or not (previous_physical_end <= continuation["requested_horizon"] == segment["horizon"] <= horizon)
                or not math.isfinite(wall) or wall < previous_wall):
            raise ValueError("full_day:shard_metadata_mismatch")
        previous_wall = wall
        owner_instants = {(r["owner_id"], r["at"]) for r in part["control_records"]}
        for record in part["control_records"]:
            duration = record["compute_wall_ms"]
            if not math.isfinite(duration) or duration < 0:
                raise ValueError("full_day:invalid_owner_duration")
            owner_max = max(owner_max, duration)
            owner_over += duration > 100.
        for call in part["client_calls"]:
            identity, payload = call["request"]["request_id"], call["request"]
            if (type(call["retry"]) is not bool or not math.isfinite(call["at"])
                    or not max(shard_start, previous_call_at) <= call["at"] <= previous_physical_end
                    or (payload["owner_id"], call["at"]) not in owner_instants
                    or call["kind"] != payload.get("kind", "transfer")):
                raise ValueError("full_day:invalid_client_call_context")
            previous_call_at = call["at"]
            if (call["retry"] and identity not in immutable) or (not call["retry"] and identity in immutable):
                raise ValueError("full_day:retry_before_creation_or_duplicate_creation")
            if immutable.setdefault(identity, payload) != payload:
                raise ValueError("full_day:mutated_retry")
            if not call["retry"]:
                created[identity] += 1
                initial_calls[identity] = call
            final_calls[identity] = call
            calls.append(call)
    if (not seen_paths or dict(counts) != manifest["counts"] or counts["control_records"] != summary["owner_activations"]
            or manifest["final_state_shard"] != manifest["shards"][-1]["path"]
            or seen_paths != {path.resolve() for path in (directory / "segments").glob("*.json.gz")}):
        raise ValueError("full_day:manifest_denominator_mismatch")
    state, result = part["controller_state"], part["result"]
    if (part["status"] != "reached" or manifest["last_shard_status"] != "reached"
            or previous_physical_end != horizon or continuation["requested_horizon"] != horizon
            or state["start"] != 0 or state["native_timestamp_complete"] is not True
            or state["pending_owners"] or state["pending_causes"] or state["needs_native_drain"]
            or result is None or result["advance"]["status"] != "reached"
            or result["advance"]["horizon_complete"] is not True
            or not (result["physical_clock"] == result["horizon"] == result["advance"]["physical_time"] == horizon)
            or result["control_continuation"] != continuation
            or not part["native_batches"] or part["native_batches"][-1]["timestamp_complete"] is not True
            or part["native_batches"][-1]["status"] != "horizon_reached"
            or part["native_batches"][-1]["trace_sequence"] != next_sequence - 1):
        raise ValueError("full_day:undrained_final_timestamp")
    if set(immutable) != set(state["client"]["outbox"]) or set(created) != set(immutable) or any(n != 1 for n in created.values()):
        raise ValueError("full_day:missing_request_creation_or_history")
    for identity, row in state["client"]["outbox"].items():
        if (row["payload"] != immutable[identity] or row["kind"] != initial_calls[identity]["kind"]
                or row["created_at"] != initial_calls[identity]["at"]
                or row["submission_reply"] != final_calls[identity]["reply"]):
            raise ValueError("full_day:outbox_history_mismatch")
    counts_business = business_counts(data, result, horizon, expected_total)
    # The inherited summary uses a 1e-8 deadline tolerance. Verify that saved
    # summary exactly, but report the independently recomputed strict count.
    if (summary["metrics"] != outcome_cost(result, data["jobs"], horizon)
            or summary["business_status_counts"] != counts_business["business_status_counts"]
            or summary["tray_mode_counts"] != dict(Counter(t["mode"] for t in result["trays"]))
            or not (summary["wall_seconds"] == manifest["wall_seconds"] == previous_wall)
            or summary["timing"]["request_count"] != len(immutable)
            or summary["timing"]["attempt_count"] != counts["client_calls"]):
        raise ValueError("full_day:summary_detail_mismatch")
    if ([j["business_bag_id"] for j in result["jobs"]] != [j["business_bag_id"] for j in data["jobs"]]
            or result["population"] != {"offered_by_horizon": expected_total, "observed": expected_total,
                "loaded": sum(j["loaded_at"] >= 0 for j in result["jobs"]), "completed": counts_business["completed"]}):
        raise ValueError("full_day:result_population_mismatch")
    if read_gz(directory / "native_offline_diagnostics.json.gz")["now"] != horizon:
        raise ValueError("full_day:offline_clock_mismatch")
    if (any(not math.isfinite(r["time"]) or not 0 <= r["time"] <= horizon for r in result["receipts"])
            or any(not math.isfinite(j[field]) or not (j[field] == -1 or 0 <= j[field] <= horizon)
                   for j in result["jobs"] for field in ("loaded_at", "storage_entered_at", "storage_released_at"))):
        raise ValueError("full_day:future_or_invalid_physical_fact")
    metrics = summary["metrics"]
    for field in ("offered", "completed", "unfinished", "failed"):
        if counts_business[field] != metrics[field]:
            raise ValueError("full_day:business_summary_count_mismatch")
    if counts_business["restricted_arrival_to_unload_cost"] != metrics["cost"]:
        raise ValueError("full_day:restricted_cost_mismatch")
    physical_audit = audit_result(replay_input(data, calls), result)
    if physical_audit != summary["audit"] or physical_audit["status"] != "passed":
        raise ValueError("full_day:physical_audit_mismatch")
    original_trays = {t["tray_id"] for t in data["trays"]}
    if original_trays != {t["tray_id"] for t in result["trays"]} or len(result["trays"]) != len(original_trays):
        raise ValueError("full_day:tray_conservation_mismatch")
    binary_path = ROOT / command_option(receipt, "--binary")
    if (receipt["binary_sha256"] != summary["native_sha256"]
            or sha(binary_path) != summary["native_sha256"]):
        raise ValueError("full_day:native_identity_mismatch")
    seal = summary["native_state_sha256"]
    if not isinstance(seal, str) or len(seal) != 64 or any(c not in "0123456789abcdef" for c in seal):
        raise ValueError("full_day:invalid_producer_native_seal")
    return {"schema": "g31.lt2.independent_full_day.v1", "status": "passed", "new_native_executions": 0,
            "physical_horizon_completed": horizon, **counts_business, "physical_audit": physical_audit,
            "tray_count": len(original_trays), "original_r1_authorized_jobs": sum(bool(j.get("allow_suffix_reroute", False)) for j in data["jobs"]),
            "counts": dict(counts), "immutable_request_count": len(immutable),
            "initial_requests_by_kind": dict(Counter(c["kind"] for c in calls if not c["retry"])),
            "retry_attempt_count": sum(c["retry"] for c in calls),
            "open_protocol_request_count": sum(not row["terminal"] for row in state["client"]["outbox"].values()),
            "max_owner_activation_ms": owner_max, "owner_activation_over100ms_count": owner_over,
            "complete_request_100ms_certified": False, "full_request_accounting": "deferred_raw_evidence_available",
            "native_sha256": summary["native_sha256"], "native_state_sha256": summary["native_state_sha256"],
            "native_state_seal_validation": "producer-reported; independent native replay not performed",
            "summary_deadline_tolerance": 1e-8,
            "input_provenance": provenance, "evidence_sha256": source_files,
            "scope": "Read-only complete sharded physical execution audit; physical horizon completion is separate from business success, paired protection, and complete-request timing."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--expected-total", type=int, required=True)
    parser.add_argument("--horizon", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.directory, args.expected_total, args.horizon)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({k: report[k] for k in ("status", "physical_horizon_completed", "offered", "completed", "unfinished")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
