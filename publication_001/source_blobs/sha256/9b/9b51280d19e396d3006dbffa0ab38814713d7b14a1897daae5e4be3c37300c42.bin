"""Independent post-run saved-horizon audit, without native execution.

An interrupted producer's status remains unchanged. A passed report certifies
only the recorded, complete physical horizon and the listed consistency checks.
The expensive repeated controller-state subtree is opaque in intermediate raw
shards, SHA-bound to the producer's completed full-parse manifest; final state
and every new record are independently decoded with standard Python JSON.
"""
from __future__ import annotations
import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import time

from .finite_reference import outcome_cost
from .native_host import audit_result
from .validate_protocol_control import replay_input
from .verify_full_day import business_counts, command_option, verify_input_provenance
from .read_sharded_raw import read_bound_shard, sha256_file

ROOT = Path(__file__).resolve().parents[3]


def file_stat(path):
    s = Path(path).stat()
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)


def auditor_sources():
    return {str(Path(m.__file__).resolve().relative_to(ROOT)): sha256_file(m.__file__)
        for m in list(sys.modules.values()) if getattr(m, "__file__", None)
        and str(m.__file__).endswith(".py") and Path(m.__file__).resolve().is_relative_to(ROOT)}


def verify_source_archive(directory, receipt):
    before = receipt.get("source_before")
    if not isinstance(before, dict) or not before:
        raise ValueError("saved_horizon:missing_source_manifest")
    for name, expected in before.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("saved_horizon:unsafe_source_path")
        if sha256_file(directory / "source_archive" / relative) != expected:
            raise ValueError("saved_horizon:archived_source_changed")
        if sha256_file(ROOT / relative) != expected:
            raise ValueError("saved_horizon:live_audit_dependency_or_source_changed")
    return dict(before)


def verify_resume_proof(directory, receipt, manifest, evidence):
    schema = receipt.get("schema", "")
    supported = {"g31.full_day_verified_resume_worker.v1", "g31.sparse_sealed_resume_worker.v1"}
    if schema not in supported:
        if "resume" in schema or "--cut-manifest" in receipt.get("command", []):
            raise ValueError("saved_horizon:unsupported_resume_schema")
        return {"resumed": False}
    def load(name):
        raw = (directory / name).read_bytes()
        evidence[name] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)
    cut_name = "resume_source/cut_manifest.json"
    cut = load(cut_name)
    stop_name = "resume_source/stop_receipt.json"
    stop = load(stop_name)
    reconstruction = load("reconstruction.json")
    expected_cut = command_option(receipt, "--expected-cut-sha256")
    expected_stop = command_option(receipt, "--expected-stop-sha256")
    field = "cut_manifest_sha256" if schema == "g31.sparse_sealed_resume_worker.v1" else "source_cut_manifest_sha256"
    if (evidence[cut_name] != expected_cut or expected_cut != receipt[field]
            or evidence[stop_name] != expected_stop
            or (schema == "g31.full_day_verified_resume_worker.v1" and expected_stop != receipt["source_stop_receipt_sha256"])
            or cut.get("schema") != ("g31.sparse_sealed_resume_cut.v1" if schema == "g31.sparse_sealed_resume_worker.v1" else "g31.full_day_known_seal_cut.v1")
            or stop.get("source_worker_stopped") is not True
            or stop.get("unchanged_policy") is not True
            or stop.get("cut_manifest_sha256") != evidence[cut_name]
            or reconstruction.get("status") != "verified_against_known_native_seal"
            or reconstruction.get("native_state_sha256") != cut.get("known_native_seal")
            or reconstruction.get("parts") != len(cut["shards"])
            or len(cut["shards"]) != cut["source_cut"] + 1
            or reconstruction.get("physical_time") != cut["physical_time"]
            or reconstruction.get("owners") != cut["owner_activations"]
            or cut.get("binary_sha256") != receipt["binary_sha256"]
            or cut.get("input_sha256") != evidence["input.json.gz"]):
        raise ValueError("saved_horizon:resume_proof_mismatch")
    for kind in ("receipt", "heartbeat"):
        name = f"resume_source/source_{kind}_snapshot.json"
        load(name)
        if evidence[name] != cut[f"source_{kind}_sha256"]:
            raise ValueError("saved_horizon:resumed_source_snapshot_changed")
    for old, new in zip(cut["shards"], manifest["shards"], strict=False):
        if Path(old["path"]) != Path(new["path"]) or old["sha256"] != new["sha256"]:
            raise ValueError("saved_horizon:resumed_prefix_changed")
    if len(manifest["shards"]) < len(cut["shards"]):
        raise ValueError("saved_horizon:resumed_prefix_missing")
    return {"resumed": True, "cut_manifest_sha256": evidence[cut_name],
            "prefix_parts": len(cut["shards"]), "known_prefix_seal": cut["known_native_seal"],
            "physical_time": cut["physical_time"], "controller_config": cut["controller_config"],
            "prefix_counts": {"control_records": reconstruction["owners"],
                "native_batches": reconstruction["native_boundaries"], "client_calls": reconstruction["submissions"]},
            "trace_records": reconstruction["trace_records"],
            "reconstruction_status": reconstruction["status"],
            "independently_replayed_here": False}


def audit_saved(directory, expected_total, horizon, *, expected_final_seal=None, progress=None):
    if not __debug__:
        raise ValueError("saved_horizon:assertions_required_for_unchanged_physical_auditor")
    audit_source_before = auditor_sources()
    directory = Path(directory).resolve()
    receipt_path = directory / "receipt.json"
    receipt_bytes = receipt_path.read_bytes()
    receipt = json.loads(receipt_bytes)
    if receipt.get("status") not in {"completed", "failed", "hard_timeout", "failed_independent_full_day_verification"}:
        raise ValueError("saved_horizon:producer_receipt_not_terminal")
    if receipt.get("source_changed") != []:
        raise ValueError("saved_horizon:producer_source_changes_or_missing_check")
    source_files = {"receipt.json": hashlib.sha256(receipt_bytes).hexdigest()}
    def bound_json(name, compressed=False):
        raw = (directory / name).read_bytes()
        source_files[name] = hashlib.sha256(raw).hexdigest()
        return json.loads(gzip.decompress(raw) if compressed else raw)
    manifest = bound_json("run_shards.json")
    if (manifest.get("schema") != "g31.lt2.complete_sharded_trace.v1"
            or manifest.get("status") != "reached" or manifest.get("all_raw_records_retained") is not True):
        raise ValueError("saved_horizon:missing_complete_producer_manifest")
    data = bound_json("input.json.gz", True)
    provenance = verify_input_provenance(directory, data, receipt, expected_total, horizon)
    if provenance["input_manifest_sha256"] is not None:
        source_files["input_manifest.json"] = provenance["input_manifest_sha256"]
    archived_sources = verify_source_archive(directory, receipt)
    resume_proof = verify_resume_proof(directory, receipt, manifest, source_files)
    summary_path = directory / "summary.json"
    producer_summary = bound_json("summary.json") if summary_path.exists() else None
    shard_stats = {}
    counts = Counter(control_records=0, native_batches=0, client_calls=0)
    next_sequence, owner_max, owner_over, previous_physical_end = 0, 0., 0, 0.
    previous_call_at, previous_wall = 0., 0.
    immutable, calls, created, seen_paths = {}, [], Counter(), set()
    initial_calls, final_calls = {}, {}
    if len(manifest["shards"]) != len(manifest["segments"]):
        raise ValueError("full_day:segment_denominator_mismatch")
    for row, segment in zip(manifest["shards"], manifest["segments"], strict=True):
        path = (directory / row["path"]).resolve()
        if path in seen_paths or not path.is_relative_to(directory):
            raise ValueError("full_day:shard_path_or_hash_mismatch")
        seen_paths.add(path)
        before_stat = file_stat(path)
        part = read_bound_shard(path, row["sha256"], final=row is manifest["shards"][-1])
        if file_stat(path) != before_stat:
            raise ValueError("saved_horizon:raw_shard_changed_during_read")
        shard_stats[row["path"]] = before_stat
        shard_start = previous_physical_end
        source_files[row["path"]] = row["sha256"]
        if progress is not None:
            progress(len(seen_paths), len(manifest["shards"]), row["path"])
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
        if resume_proof["resumed"] and len(seen_paths) == resume_proof["prefix_parts"]:
            if (dict(counts) != resume_proof["prefix_counts"]
                    or next_sequence != resume_proof["trace_records"]
                    or part.get("native_state_sha256") != resume_proof["known_prefix_seal"]
                    or part["control_continuation"]["physical_time"] != resume_proof["physical_time"]):
                raise ValueError("saved_horizon:raw_prefix_cut_or_reconstruction_denominator_mismatch")
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
    if (not seen_paths or dict(counts) != manifest["counts"]
            or manifest["final_state_shard"] != manifest["shards"][-1]["path"]
            or seen_paths != {path.resolve() for path in (directory / "segments").glob("*.json.gz")}):
        raise ValueError("full_day:manifest_denominator_mismatch")
    state, result = part["controller_state"], part["result"]
    if resume_proof["resumed"] and state["config"] != resume_proof["controller_config"]:
        raise ValueError("saved_horizon:resumed_final_controller_config_changed")
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
    metrics = outcome_cost(result, data["jobs"], horizon)
    if manifest["wall_seconds"] != previous_wall:
        raise ValueError("saved_horizon:manifest_wall_mismatch")
    if ([j["business_bag_id"] for j in result["jobs"]] != [j["business_bag_id"] for j in data["jobs"]]
            or result["population"] != {"offered_by_horizon": expected_total, "observed": expected_total,
                "loaded": sum(j["loaded_at"] >= 0 for j in result["jobs"]), "completed": counts_business["completed"]}):
        raise ValueError("full_day:result_population_mismatch")
    if bound_json("native_offline_diagnostics.json.gz", True)["now"] != horizon:
        raise ValueError("full_day:offline_clock_mismatch")
    if (any(not math.isfinite(r["time"]) or not 0 <= r["time"] <= horizon for r in result["receipts"])
            or any(not math.isfinite(j[field]) or not (j[field] == -1 or 0 <= j[field] <= horizon)
                   for j in result["jobs"] for field in ("loaded_at", "storage_entered_at", "storage_released_at"))):
        raise ValueError("full_day:future_or_invalid_physical_fact")
    for field in ("offered", "completed", "unfinished", "failed"):
        if counts_business[field] != metrics[field]:
            raise ValueError("full_day:business_summary_count_mismatch")
    if counts_business["restricted_arrival_to_unload_cost"] != metrics["cost"]:
        raise ValueError("full_day:restricted_cost_mismatch")
    physical_audit = audit_result(replay_input(data, calls), result)
    if physical_audit["status"] != "passed":
        raise ValueError("full_day:physical_audit_mismatch")
    original_trays = {t["tray_id"] for t in data["trays"]}
    if original_trays != {t["tray_id"] for t in result["trays"]} or len(result["trays"]) != len(original_trays):
        raise ValueError("full_day:tray_conservation_mismatch")
    binary_path = ROOT / command_option(receipt, "--binary")
    if sha256_file(binary_path) != receipt["binary_sha256"]:
        raise ValueError("saved_horizon:native_identity_mismatch")
    seal = part.get("native_state_sha256")
    if not isinstance(seal, str) or len(seal) != 64 or any(c not in "0123456789abcdef" for c in seal):
        raise ValueError("saved_horizon:invalid_producer_native_seal")
    if expected_final_seal is not None and seal != expected_final_seal:
        raise ValueError("saved_horizon:expected_final_seal_mismatch")
    if producer_summary is not None:
        expected = {"status": "reached", "physical_time": horizon, "horizon": horizon,
            "offered_total": expected_total, "offered_by_current_time": expected_total,
            "all_input_arrivals_observed": True, "metrics": metrics,
            "business_status_counts": counts_business["business_status_counts"],
            "tray_mode_counts": dict(Counter(t["mode"] for t in result["trays"])),
            "wall_seconds": manifest["wall_seconds"], "owner_activations": counts["control_records"],
            "native_sha256": receipt["binary_sha256"], "native_state_sha256": seal, "audit": physical_audit}
        if any(producer_summary.get(k) != v for k, v in expected.items()):
            raise ValueError("saved_horizon:producer_summary_mismatch")
        if (producer_summary["timing"]["request_count"] != len(immutable)
                or producer_summary["timing"]["attempt_count"] != counts["client_calls"]):
            raise ValueError("saved_horizon:producer_summary_request_mismatch")
    # No source evidence is rewritten. All small evidence and every archive
    # source are rehashed after the audit; raw shards were consumed from exactly
    # the byte images whose SHA was checked. Stat tuples detect subsequent
    # changes to those immutable files without a second 3+ GiB hash pass.
    for name, expected_sha in source_files.items():
        path = directory / name
        if name in shard_stats:
            if file_stat(path) != shard_stats[name]:
                raise ValueError("saved_horizon:raw_shard_changed_during_audit")
        elif sha256_file(path) != expected_sha:
            raise ValueError("saved_horizon:evidence_changed_during_audit")
    if verify_source_archive(directory, receipt) != archived_sources:
        raise ValueError("saved_horizon:source_archive_changed_during_audit")
    if auditor_sources() != audit_source_before:
        raise ValueError("saved_horizon:auditor_source_changed_during_audit")
    return {"schema": "g31.lt2.saved_horizon_audit.v1", "status": "passed_saved_physical_horizon",
            "producer_receipt_status": receipt["status"], "producer_exit_code": receipt.get("exit_code"),
            "producer_process_success": receipt["status"] == "completed" and receipt.get("exit_code") == 0,
            "producer_summary_present": producer_summary is not None,
            "source_archive_sha256": archived_sources, "resume_proof": resume_proof,
            "auditor_sources_sha256": audit_source_before,
            "intermediate_controller_states": "Opaque bytes bound to producer fully parsed manifest; not independently syntax-decoded",
            "raw_stability": "Each exact compressed byte image hashed; before/after file identity/size/mtime checked, no second full hash pass", "new_native_executions": 0,
            "physical_horizon_completed": horizon, **counts_business, "physical_audit": physical_audit,
            "tray_count": len(original_trays), "original_r1_authorized_jobs": sum(bool(j.get("allow_suffix_reroute", False)) for j in data["jobs"]),
            "counts": dict(counts), "immutable_request_count": len(immutable),
            "initial_requests_by_kind": dict(Counter(c["kind"] for c in calls if not c["retry"])),
            "retry_attempt_count": sum(c["retry"] for c in calls),
            "open_protocol_request_count": sum(not row["terminal"] for row in state["client"]["outbox"].values()),
            "max_owner_activation_ms": owner_max, "owner_activation_over100ms_count": owner_over,
            "complete_request_100ms_certified": False, "full_request_accounting": "deferred_raw_evidence_available",
            "native_sha256": receipt["binary_sha256"], "native_state_sha256": seal,
            "native_state_seal_validation": "producer-reported; independent native replay not performed",
            "summary_deadline_tolerance": 1e-8,
            "input_provenance": provenance, "evidence_sha256": source_files,
            "scope": "Separate read-only audit of saved full-horizon raw evidence; original worker receipt remains unchanged; physical horizon completion is separate from business success, paired protection, and complete-request timing."}



def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory", type=Path, required=True)
    p.add_argument("--expected-total", type=int, required=True)
    p.add_argument("--horizon", type=float, required=True)
    p.add_argument("--expected-final-seal")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists() or args.output.resolve().is_relative_to(args.directory.resolve()):
        raise ValueError("saved_horizon:output_must_be_new_and_outside_original_run")
    started = time.perf_counter()
    def progress(done, total, name):
        print(json.dumps({"shards_read": done, "total": total, "last": name,
                          "audit_wall_seconds": time.perf_counter() - started}), flush=True)
    report = audit_saved(args.directory, args.expected_total, args.horizon,
                         expected_final_seal=args.expected_final_seal, progress=progress)
    report["audit_wall_seconds"] = time.perf_counter() - started
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({k: report[k] for k in ("status", "producer_receipt_status", "offered", "completed", "unfinished")}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
