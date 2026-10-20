"""Verified tape reconstruction and continuation with sparse diagnostic seals.

The original cut seal is mandatory. JSON alone never restores native state.
Every original shard is copied byte-for-byte; every new controller return is
saved. Only diagnostic sealing cadence changes, outside controller windows.
"""
from __future__ import annotations
import argparse
from collections import Counter
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import traceback

from . import profile_lt2_streaming as streaming
from .event_protocol_control import run_event_protocol_control
from .finite_reference import outcome_cost
from .native_host import audit_result, load_native
from .reconstruct_native_tape import NativeTapeReconstructor
from .validate_protocol_control import replay_input
from .verify_full_day import verify as verify_full_day, verify_input_provenance

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = "g31.full_day_known_seal_cut.v1"
REQUIRED_POLICY = ("event_protocol_control.py", "protocol_control.py", "analytic_control.py", "regional_control.py", "native_host.py")


def require(ok, reason):
    if not ok:
        raise ValueError("resume_full_day:" + reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_gz(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def dump(path, value):
    streaming.atomic_json(Path(path), value)


def option(command, name, default=None):
    if name not in command:
        require(default is not None, "missing_option:" + name)
        return default
    require(command.count(name) == 1 and command.index(name) + 1 < len(command), "duplicate_or_empty_option:" + name)
    return command[command.index(name) + 1]


def digest_string(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def finite(value, *, positive=False):
    return type(value) in (float, int) and math.isfinite(value) and (value > 0 if positive else value >= 0)


def source_scope(receipt):
    command = receipt["command"]
    result = {"suite": option(command, "--suite"), "horizon": float(option(command, "--horizon")),
              "segment_seconds": float(option(command, "--segment-seconds", "3600"))}
    result.update({key: int(option(command, "--" + key.replace("_", "-")))
                   for key in ("event_budget", "max_activations", "activation_shard_budget")})
    require(result["suite"] in {"synthetic", "full1x", "full2x"} and
            finite(result["horizon"], positive=True) and finite(result["segment_seconds"], positive=True) and
            all(result[key] > 0 for key in ("event_budget", "max_activations", "activation_shard_budget")), "invalid_source_scope")
    return result


def validate_policy_sources(source, receipt):
    before = receipt["source_before"]
    require(type(before) is dict and before and not receipt.get("source_changed"), "source_receipt_invalid")
    names = {Path(key).name for key in before}
    require(set(REQUIRED_POLICY) <= names, "policy_dependency_missing")
    for relative, expected in before.items():
        path = Path(relative)
        require(not path.is_absolute() and ".." not in path.parts and digest_string(expected), "source_path_invalid")
        live, archived = ROOT / path, source / "source_archive" / path
        require(live.resolve().is_relative_to(ROOT) and sha(live) == expected and sha(archived) == expected,
                "policy_source_changed:" + relative)


def next_target(part, horizon, segment_seconds):
    continuation = part["control_continuation"]
    target, physical = continuation["requested_horizon"], continuation["physical_time"]
    require(finite(target) and finite(physical) and physical <= target <= horizon, "invalid_cut_time")
    require(part["status"] in {"reached", "control_budget_exhausted"} and continuation["status"] == part["status"],
            "unsupported_cut_status")
    if part["status"] == "reached":
        state = part["controller_state"]
        require(physical == target and state["native_timestamp_complete"] is True and
                not state["pending_owners"] and not state["pending_causes"] and not state["needs_native_drain"],
                "incomplete_reached_cut")
        return min(target + segment_seconds, horizon)
    return target  # Preserve a pending same-timestamp owner round exactly.


def prepare_cut(source, output):
    """Pin the heartbeat observed by this invocation; never stop the producer."""
    source, output = Path(source).resolve(), Path(output).resolve()
    require(source != output and not output.is_relative_to(source), "cut_output_inside_source")
    output.mkdir(parents=True, exist_ok=False)
    receipt_bytes = (source / "receipt.json").read_bytes()
    heartbeat_bytes = (source / "heartbeat.json").read_bytes()
    receipt, heartbeat = json.loads(receipt_bytes), json.loads(heartbeat_bytes)
    require(receipt.get("schema") == "g31.lt2.profile_worker.v1" and
            receipt.get("status") in {"running", "completed", "failed", "hard_timeout"}, "unsupported_source_receipt")
    require(heartbeat.get("stage") == "segment_saved" and type(heartbeat.get("segment")) is int and
            heartbeat["segment"] >= 0, "no_published_heartbeat_cut")
    command = receipt["command"]
    suite = option(command, "--suite")
    require(suite in {"synthetic", "full1x", "full2x"}, "unsupported_suite")
    horizon, segment_seconds = float(option(command, "--horizon")), float(option(command, "--segment-seconds", "3600"))
    require(finite(horizon, positive=True) and finite(segment_seconds, positive=True), "invalid_horizon")
    budgets = {key: int(option(command, "--" + key.replace("_", "-")))
               for key in ("event_budget", "max_activations", "activation_shard_budget")}
    require(all(value > 0 for value in budgets.values()), "invalid_budget")
    binary = (ROOT / option(command, "--binary")).resolve()
    require(digest_string(receipt["binary_sha256"]) and sha(binary) == receipt["binary_sha256"] ==
            option(command, "--expected-binary-sha256"), "binary_identity_mismatch")
    validate_policy_sources(source, receipt)
    cut = heartbeat["segment"]
    paths = [source / "segments" / f"{index:04d}.json.gz" for index in range(cut + 1)]
    require(all(path.is_file() for path in paths), "prefix_shard_missing")
    descriptors = [{"path": f"segments/{index:04d}.json.gz", "sha256": sha(path)} for index, path in enumerate(paths)]
    part = read_gz(paths[-1])
    require(digest_string(part.get("native_state_sha256")), "source_cut_has_no_native_seal")
    require(part["status"] == heartbeat["status"] and
            part["control_continuation"]["physical_time"] == heartbeat["physical_time"], "heartbeat_cut_mismatch")
    target = next_target(part, horizon, segment_seconds)
    require(heartbeat["physical_time"] < horizon and type(heartbeat["owner_activations"]) is int and
            0 <= heartbeat["owner_activations"] < budgets["max_activations"], "cut_not_continuable")
    for key in ("controller_wall_seconds", "diagnostic_export_wall_seconds", "diagnostic_seal_wall_seconds"):
        require(finite(heartbeat[key]), "invalid_prior_cost")
    input_path = source / "input.json.gz"
    data = read_gz(input_path)
    total = len(data["jobs"])
    require(total == heartbeat["offered_total"], "offered_total_mismatch")
    provenance = verify_input_provenance(source, data, receipt, total, horizon)
    (output / "source_receipt_snapshot.json").write_bytes(receipt_bytes)
    (output / "source_heartbeat_snapshot.json").write_bytes(heartbeat_bytes)
    manifest = {"schema": SCHEMA, "source_directory": str(source), "source_cut": cut,
        "source_receipt_sha256": sha(output / "source_receipt_snapshot.json"),
        "source_heartbeat_sha256": sha(output / "source_heartbeat_snapshot.json"),
        "input_sha256": sha(input_path), "binary": str(binary), "binary_sha256": receipt["binary_sha256"],
        "suite": suite, "horizon": horizon, "segment_seconds": segment_seconds, **budgets,
        "offered_total": total, "provenance": provenance, "shards": descriptors,
        "known_native_seal": part["native_state_sha256"], "physical_time": heartbeat["physical_time"],
        "owner_activations": heartbeat["owner_activations"], "next_target": target,
        "controller_config": part["controller_state"]["config"],
        "cut_controller_state_sha256": hashlib.sha256(json.dumps(part["controller_state"], ensure_ascii=False,
            allow_nan=False, separators=(",", ":")).encode()).hexdigest(),
        "prior_costs": {key: heartbeat[key] for key in
            ("controller_wall_seconds", "diagnostic_export_wall_seconds", "diagnostic_seal_wall_seconds")},
        "source_policy_sha256": receipt["source_before"],
        "scope": "Published immutable prefix only; native state must be reconstructed and match original saved seal. Source process stopping is separately authorized and evidenced. No source file or process was changed."}
    dump(output / "cut_manifest.json", manifest)
    return manifest


def validate_cut(path, expected_sha):
    path = Path(path).resolve()
    require(digest_string(expected_sha) and sha(path) == expected_sha, "cut_manifest_changed")
    cut = json.loads(path.read_bytes())
    require(cut.get("schema") == SCHEMA and type(cut.get("source_cut")) is int and cut["source_cut"] >= 0,
            "invalid_cut_manifest")
    require(digest_string(cut.get("known_native_seal")), "source_cut_has_no_native_seal")
    source = Path(cut["source_directory"]).resolve()
    require(sha(path.parent / "source_receipt_snapshot.json") == cut["source_receipt_sha256"] and
            sha(path.parent / "source_heartbeat_snapshot.json") == cut["source_heartbeat_sha256"], "cut_snapshot_changed")
    receipt = json.loads((path.parent / "source_receipt_snapshot.json").read_bytes())
    heartbeat = json.loads((path.parent / "source_heartbeat_snapshot.json").read_bytes())
    require(all(cut.get(key) == value for key, value in source_scope(receipt).items()), "source_scope_changed")
    require(receipt["source_before"] == cut["source_policy_sha256"], "policy_manifest_mismatch")
    validate_policy_sources(source, receipt)
    require(sha(cut["binary"]) == cut["binary_sha256"] == receipt["binary_sha256"], "binary_identity_mismatch")
    require(sha(source / "input.json.gz") == cut["input_sha256"], "input_changed")
    require(len(cut["shards"]) == cut["source_cut"] + 1 and heartbeat["segment"] == cut["source_cut"], "prefix_count_mismatch")
    for index, row in enumerate(cut["shards"]):
        require(row["path"] == f"segments/{index:04d}.json.gz" and digest_string(row["sha256"]), "prefix_order_or_path")
        shard = (source / row["path"]).resolve()
        require(shard.is_relative_to(source) and sha(shard) == row["sha256"], "prefix_shard_changed")
    part = read_gz(source / cut["shards"][-1]["path"])
    require(part["native_state_sha256"] == cut["known_native_seal"] and
            part["controller_state"]["config"] == cut["controller_config"] and
            next_target(part, cut["horizon"], cut["segment_seconds"]) == cut["next_target"], "cut_state_mismatch")
    require(hashlib.sha256(json.dumps(part["controller_state"], ensure_ascii=False, allow_nan=False,
            separators=(",", ":")).encode()).hexdigest() == cut["cut_controller_state_sha256"], "cut_controller_state_changed")
    require(heartbeat["physical_time"] == cut["physical_time"] == part["control_continuation"]["physical_time"] and
            heartbeat["owner_activations"] == cut["owner_activations"], "cut_denominator_mismatch")
    require(heartbeat["stage"] == "segment_saved" and heartbeat["status"] == part["status"] and
            heartbeat["offered_total"] == cut["offered_total"] and
            all(cut["prior_costs"].get(key) == heartbeat[key] and finite(heartbeat[key]) for key in
                ("controller_wall_seconds", "diagnostic_export_wall_seconds", "diagnostic_seal_wall_seconds")), "prior_metadata_mismatch")
    require(type(cut["owner_activations"]) is int and 0 <= cut["owner_activations"] < cut["max_activations"] and
            cut["physical_time"] < cut["horizon"], "cut_not_continuable")
    return cut


def validate_stop(path, expected_sha, cut_sha):
    require(digest_string(expected_sha) and sha(path) == expected_sha, "stop_receipt_changed")
    stopped = json.loads(Path(path).read_bytes())
    require(stopped.get("schema") == "g31.full_day_resume_stop.v1" and
            stopped.get("source_worker_stopped") is True and stopped.get("unchanged_policy") is True and
            stopped.get("cut_manifest_sha256") == cut_sha, "source_worker_not_confirmed_stopped")
    return stopped


def finalize_verification(output, receipt, cut, verifier=verify_full_day):
    """An independent audit failure invalidates the published execution receipt."""
    if receipt["status"] != "completed":
        return
    summary = json.loads((output / "summary.json").read_bytes())
    if summary["status"] == "reached" and summary["physical_time"] == cut["horizon"]:
        try:
            audit = verifier(output, cut["offered_total"], cut["horizon"])
            dump(output / "independent_full_day_verification.json", audit)
        except Exception as error:
            receipt.update(status="failed_independent_full_day_verification", exit_code=2,
                           independent_verification_error=type(error).__name__ + ":" + str(error))
            dump(output / "receipt.json", receipt)
            raise


def reconstruct(cut, output, session_factory=load_native, reconstructor_class=NativeTapeReconstructor):
    """No session or controller checkpoint escapes before known-seal success."""
    source, output = Path(cut["source_directory"]), Path(output)
    (output / "segments").mkdir(exist_ok=False)
    data = read_gz(source / "input.json.gz")
    require(len(data["jobs"]) == cut["offered_total"], "offered_total_mismatch")
    shutil.copyfile(source / "input.json.gz", output / "input.json.gz")
    for name in ("input_manifest.json", "static_diagnostics.json", "return_contract_diagnostics.json"):
        if (source / name).exists():
            shutil.copyfile(source / name, output / name)
    session = session_factory(Path(cut["binary"])).NativeSession(data)
    replay = reconstructor_class(session, event_budget=cut["event_budget"])
    segments, internal_wall = [], 0.
    for index, descriptor in enumerate(cut["shards"]):
        origin, target = source / descriptor["path"], output / descriptor["path"]
        require(sha(origin) == descriptor["sha256"], "prefix_shard_changed")
        shutil.copyfile(origin, target)
        require(sha(target) == descriptor["sha256"], "prefix_copy_changed")
        part = read_gz(target)
        report = replay.replay_part(part)
        internal_wall += part["wall_seconds"]
        segments.append({"horizon": part["control_continuation"]["requested_horizon"],
            "physical_time": part["control_continuation"]["physical_time"], "status": part["status"],
            "cumulative_control_wall_seconds": internal_wall})
        dump(output / "reconstruction_heartbeat.json", {**report, "source_shard": index})
        if index != cut["source_cut"]:
            del part
    report = replay.finish(cut["known_native_seal"])
    require(report["owners"] == cut["owner_activations"] and report["parts"] == len(cut["shards"]) and
            report["physical_time"] == cut["physical_time"], "replayed_denominator_mismatch")
    prior_wall = cut["prior_costs"]["controller_wall_seconds"]
    require(prior_wall >= internal_wall, "prior_outer_wall_less_than_raw_controller_wall")
    segments[-1]["cumulative_control_wall_seconds"] = prior_wall
    report["prefix_outer_wrapper_residual_seconds"] = prior_wall - internal_wall
    report["prefix_cost_scope"] = "Raw per-call internal wall accumulated; original measured outer-wrapper residual charged at cut. Exact original cumulative controller cost preserved."
    # Bind Python state to the exact source bytes as well as the physical seal.
    require(part["controller_state"]["config"] == cut["controller_config"], "replayed_config_mismatch")
    verified = replay.verified_session()
    return verified, part, segments, report, data


def should_seal(part, activation_count, maximum, final_horizon):
    return (part["status"] != "control_budget_exhausted" or activation_count >= maximum or
            part["control_continuation"]["physical_time"] >= final_horizon)


def worker(args):
    started_worker = time.perf_counter()
    cut = validate_cut(args.cut_manifest, args.expected_cut_sha256)
    validate_stop(args.stop_receipt, args.expected_stop_sha256, args.expected_cut_sha256)
    require(str(Path(args.binary).resolve()) == str(Path(cut["binary"]).resolve()) and
            args.suite == cut["suite"] and args.horizon == cut["horizon"] and args.event_budget == cut["event_budget"],
            "resume_scope_changed")
    proof = args.output / "resume_source"
    proof.mkdir(exist_ok=False)
    for name in ("cut_manifest.json", "source_receipt_snapshot.json", "source_heartbeat_snapshot.json"):
        shutil.copyfile(args.cut_manifest.parent / name, proof / name)
    shutil.copyfile(args.stop_receipt, proof / "stop_receipt.json")
    started = time.perf_counter()
    session, part, segments, reconstruction, data = reconstruct(cut, args.output)
    reconstruction["wall_seconds"] = time.perf_counter() - started
    dump(args.output / "reconstruction.json", reconstruction)
    run = {key: part[key] for key in ("status", "result", "controller_state", "control_continuation")}
    run["segments"] = segments
    offset, count = reconstruction["trace_records"], reconstruction["owners"]
    elapsed = cut["prior_costs"]["controller_wall_seconds"]
    export_seconds = cut["prior_costs"]["diagnostic_export_wall_seconds"]
    seal_seconds = cut["prior_costs"]["diagnostic_seal_wall_seconds"]
    new_seals = []
    target, segment = cut["next_target"], cut["source_cut"] + 1
    config = copy.deepcopy(cut["controller_config"])
    owners = config.pop("owners")
    part = None
    while True:
        started = time.perf_counter()
        part = run_event_protocol_control(session, owners, horizon=target, event_budget=cut["event_budget"],
            max_activations=min(cut["activation_shard_budget"], cut["max_activations"] - count),
            state=run["controller_state"], _consume_state=True, **config)
        elapsed += time.perf_counter() - started
        count += len(part["control_records"])
        if should_seal(part, count, cut["max_activations"], cut["horizon"]):
            started = time.perf_counter()
            part["native_state_sha256"] = session.offline_state_sha256()
            part["diagnostic_seal_wall_ms"] = 1000 * (time.perf_counter() - started)
            seal_seconds += part["diagnostic_seal_wall_ms"] / 1000
            new_seals.append({"shard": segment, "physical_time": session.physical_time,
                              "native_state_sha256": part["native_state_sha256"]})
        for key in ("control_records", "native_batches"):
            for row in part[key]:
                row["trace_sequence"] += offset
        offset += len(part["control_records"]) + len(part["native_batches"])
        for key in ("status", "result", "controller_state", "control_continuation"):
            run[key] = part[key]
        run["segments"].append({"horizon": target, "physical_time": session.physical_time,
            "status": part["status"], "cumulative_control_wall_seconds": elapsed})
        started = time.perf_counter()
        path = args.output / "segments" / f"{segment:04d}.json.gz"
        require(not path.exists(), "new_shard_already_exists")
        streaming.gz(path, part, compresslevel=1)
        export_seconds += time.perf_counter() - started
        hashes = args.output / "segment_hashes"
        hashes.mkdir(exist_ok=True)
        hash_path = hashes / f"{segment:04d}.json"
        require(not hash_path.exists(), "new_shard_hash_already_exists")
        dump(hash_path, {"path": str(path.relative_to(args.output)), "sha256": sha(path)})
        dump(args.output / "heartbeat.json", {"stage": "segment_saved", "segment": segment, "status": part["status"],
            "physical_time": session.physical_time, "owner_activations": count,
            "offered_total": len(data["jobs"]), "offered_by_current_time": sum(j["arrival"] <= session.physical_time for j in data["jobs"]),
            "controller_wall_seconds": elapsed, "diagnostic_export_wall_seconds": export_seconds,
            "diagnostic_seal_wall_seconds": seal_seconds, "reconstruction_wall_seconds": reconstruction["wall_seconds"],
            "latest_native_seal": new_seals[-1] if new_seals else None,
            "native_persistence": "Verified original sealed prefix reconstructed by full native tape; current unsealed tail is not a native checkpoint."})
        segment += 1
        if (part["status"] not in {"reached", "control_budget_exhausted"} or
                (part["status"] == "reached" and target == cut["horizon"]) or count >= cut["max_activations"]):
            if part["status"] == "reached" and target < cut["horizon"]:
                run["status"], run["result"] = "control_budget_exhausted", None
            break
        if part["status"] == "reached":
            target = min(target + cut["segment_seconds"], cut["horizon"])
        part = None
    require(digest_string(part.get("native_state_sha256")), "final_exit_not_sealed")
    final_seal = part["native_state_sha256"]
    part = None
    run["wall_seconds"] = elapsed
    manifest = streaming.shard_manifest(args.output, run, count)
    spans = {"status": "deferred_full_raw_trace_available", "request_count": len(run["controller_state"]["client"]["outbox"]),
        "attempt_count": manifest["counts"]["client_calls"], "complete_100ms_requirement_certified": False}
    summary = {"status": run["status"], "physical_time": session.physical_time, "horizon": cut["horizon"],
        "offered_total": len(data["jobs"]), "offered_by_current_time": sum(j["arrival"] <= session.physical_time for j in data["jobs"]),
        "wall_seconds": elapsed, "owner_activations": count, "timing": spans, "cprofile_enabled": False,
        "trace_gc": False, "retain_trace_in_memory": False, "complete_100ms_requirement_certified": False,
        "diagnostic_storage": "complete_shards", "native_sha256": cut["binary_sha256"], "native_state_sha256": final_seal,
        "metrics": None, "gzip_level": 1, "diagnostic_export_wall_seconds": export_seconds,
        "diagnostic_seal_wall_seconds": seal_seconds, "reconstruction": reconstruction, "prior_costs": cut["prior_costs"],
        "new_seal_schedule": "Every reached segment horizon and every final budget/status exit; no extra controller activation or physical boundary",
        "source_cut_manifest_sha256": args.expected_cut_sha256, "source_stop_receipt_sha256": args.expected_stop_sha256,
        "scope": "Same input/binary/policy and exact known-seal reconstruction, then unchanged controller. Original prefix and new raw shards retained. Not JSON restoration, isolated timing, business protection or complete-request certification."}
    result = run.get("result")
    if result is not None:
        started = time.perf_counter()
        streaming.gz(args.output / "native_offline_diagnostics.json.gz", session.offline_diagnostics(), compresslevel=1)
        export_seconds += time.perf_counter() - started
        summary.update(metrics=outcome_cost(result, data["jobs"], cut["horizon"]),
            audit=audit_result(replay_input(data, streaming.shard_calls(args.output)), result),
            business_status_counts=dict(Counter(j["status"] for j in result["jobs"])),
            tray_mode_counts=dict(Counter(t["mode"] for t in result["trays"])),
            all_input_arrivals_observed=all(j["arrival"] <= session.physical_time for j in data["jobs"]))
    summary["diagnostic_export_wall_seconds"] = export_seconds
    summary["resume_worker_wall_seconds_through_summary"] = time.perf_counter() - started_worker
    dump(args.output / "summary.json", summary)
    dump(args.output / "heartbeat.json", {"stage": "worker_finished", "status": run["status"], "physical_time": session.physical_time})
    validate_cut(args.cut_manifest, args.expected_cut_sha256)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cut-manifest", type=Path)
    parser.add_argument("--expected-cut-sha256")
    parser.add_argument("--stop-receipt", type=Path)
    parser.add_argument("--expected-stop-sha256")
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--suite")
    parser.add_argument("--horizon", type=float)
    parser.add_argument("--event-budget", type=int)
    parser.add_argument("--hard-timeout", type=float, default=7200.)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.prepare_source:
        require(not args.worker, "prepare_cannot_run_native_worker")
        cut = prepare_cut(args.prepare_source, args.output)
        print(json.dumps({"cut": cut["source_cut"], "cut_manifest_sha256": sha(args.output / "cut_manifest.json")}))
        return 0
    require(all(value is not None for value in (args.cut_manifest, args.expected_cut_sha256, args.stop_receipt,
        args.expected_stop_sha256, args.binary, args.suite, args.horizon, args.event_budget)), "resume_arguments_required")
    require(finite(args.hard_timeout, positive=True) and args.hard_timeout <= 7200, "invalid_hard_timeout")
    if args.worker:
        try:
            return worker(args)
        except Exception:
            (args.output / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            raise
    cut = validate_cut(args.cut_manifest, args.expected_cut_sha256)
    validate_stop(args.stop_receipt, args.expected_stop_sha256, args.expected_cut_sha256)
    args.output.mkdir(parents=True, exist_ok=False)
    sources = sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m, "__file__", None)
        and str(m.__file__).endswith(".py") and Path(m.__file__).resolve().is_relative_to(ROOT)})
    before = {str(p.relative_to(ROOT)): sha(p) for p in sources}
    for path in sources:
        archived = args.output / "source_archive" / path.relative_to(ROOT)
        archived.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, archived)
    command = [sys.executable, "-m", __spec__.name, *sys.argv[1:], "--worker"]
    receipt = {"schema": "g31.full_day_verified_resume_worker.v1", "status": "running", "command": command,
        "source_before": before, "binary_sha256": cut["binary_sha256"], "hard_timeout_seconds": args.hard_timeout,
        "source_cut_manifest_sha256": args.expected_cut_sha256, "source_stop_receipt_sha256": args.expected_stop_sha256,
        "maximum_native_workers": 1, "complete_100ms_requirement_certified": False}
    dump(args.output / "receipt.json", receipt)
    started = time.perf_counter()
    with (args.output / "stdout.log").open("w", encoding="utf-8") as out, (args.output / "stderr.log").open("w", encoding="utf-8") as err:
        try:
            result = subprocess.run(command, cwd=ROOT, stdout=out, stderr=err, timeout=args.hard_timeout, check=False)
            receipt.update(status="completed" if result.returncode == 0 else "failed", exit_code=result.returncode)
        except subprocess.TimeoutExpired:
            receipt.update(status="hard_timeout", exit_code=None, result="unknown_unsealed_tail_preserved")
    receipt.update(wall_seconds=time.perf_counter() - started,
        source_changed=[p for p, expected in before.items() if sha(ROOT / p) != expected])
    if receipt["source_changed"]:
        receipt["status"] = "invalidated_source_changed"
    dump(args.output / "receipt.json", receipt)
    finalize_verification(args.output, receipt, cut)
    print(json.dumps({key: receipt[key] for key in ("status", "exit_code", "wall_seconds", "source_changed")}))
    return 0 if receipt["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
