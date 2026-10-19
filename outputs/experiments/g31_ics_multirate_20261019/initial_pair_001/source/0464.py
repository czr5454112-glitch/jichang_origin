"""Resume a sparse-sealed interrupted stream without rewriting its evidence.

The source heartbeat can describe an unsealed tail. A separate selection pins
the last contemporaneous seal; all discarded-tail costs remain charged. The
accepted reconstruction/continuation worker is reused in an isolated process.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import time
import traceback

from . import resume_full_day as base
from .install_public_travel_pool import installed_public_travel_pool

SCHEMA = "g31.sparse_sealed_resume_cut.v1"
ROOT = base.ROOT


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def state_sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, allow_nan=False,
        separators=(",", ":")).encode()).hexdigest()


def source_scope(receipt):
    if receipt["schema"] == "g31.full_day_verified_resume_worker.v1":
        command = receipt["command"]
        origin = Path(base.option(command, "--cut-manifest"))
        base.require(base.sha(origin) == base.option(command, "--expected-cut-sha256"), "ancestor_cut_changed")
        previous = read(origin)
        scope = {key: previous[key] for key in ("suite", "horizon", "segment_seconds",
            "event_budget", "max_activations", "activation_shard_budget")}
        base.require(base.option(command, "--suite") == scope["suite"] and
            float(base.option(command, "--horizon")) == scope["horizon"] and
            int(base.option(command, "--event-budget")) == scope["event_budget"], "ancestor_scope_mismatch")
        return scope
    base.require(receipt["schema"] in {"g31.full_day_sparse_public_pool_worker.v1",
        "g31.full_day_sparse_worker.v1", "g31.lt2.profile_worker.v1"}, "unsupported_sparse_source")
    return base.source_scope(receipt)


def verify_absence(path, expected_sha, source):
    base.require(base.sha(path) == expected_sha, "absence_observation_changed")
    record = read(path)
    base.require(record.get("schema") == "g31.user_resume_process_observation.v1" and
        record.get("all_original_identities_absent") is True, "old_process_not_absent")
    def tokens(row):
        return [s.strip('"') for s in shlex.split(row["expected"]["CommandLine"], posix=False)]
    def same_output(row):
        command = tokens(row)
        return (command.count("--output") == 1 and command.index("--output") + 1 < len(command)
            and (ROOT / command[command.index("--output") + 1]).resolve() == source.resolve())
    matching = [r for r in record["processes"] if same_output(r)]
    parents = [r for r in matching if "--worker" not in tokens(r)]
    workers = [r for r in matching if "--worker" in tokens(r)]
    base.require(len(matching) == 2 and len(parents) == len(workers) == 1 and
        all(r.get("old_identity_present") is False and r.get("observed") is None for r in matching) and
        workers[0]["expected"]["ParentProcessId"] == parents[0]["expected"]["ProcessId"],
        "missing_parent_worker_absence")
    return record


def selected_metadata(source, receipt, heartbeat):
    scope = source_scope(receipt)
    base.require(receipt.get("status") in {"running", "failed", "hard_timeout"}, "source_not_interrupted")
    base.validate_policy_sources(source, receipt)
    base.require(heartbeat.get("stage") == "segment_saved", "source_heartbeat_not_segment")
    seal = heartbeat.get("latest_native_seal")
    if seal is None:
        seal = {"shard": heartbeat["segment"], "physical_time": heartbeat["physical_time"]}
    index = seal["shard"]
    base.require(type(index) is int and 0 <= index <= heartbeat["segment"], "invalid_sealed_index")
    part = base.read_gz(source / "segments" / f"{index:04d}.json.gz")
    physical = part["control_continuation"]["physical_time"]
    base.require(base.digest_string(part.get("native_state_sha256")) and
        seal.get("native_state_sha256", part["native_state_sha256"]) == part["native_state_sha256"] and
        seal["physical_time"] == physical <= heartbeat["physical_time"] < scope["horizon"], "known_seal_mismatch")
    owners = part["controller_state"]["owner_epochs"]
    base.require(set(owners) == set(part["controller_state"]["config"]["owners"]) and
        all(type(v) is int and v >= 0 for v in owners.values()), "invalid_owner_epochs")
    count = sum(owners.values())
    base.require(count <= heartbeat["owner_activations"] < scope["max_activations"], "source_budget_exhausted")
    binary = (ROOT / base.option(receipt["command"], "--binary")).resolve()
    base.require(base.sha(binary) == receipt["binary_sha256"], "source_binary_changed")
    costs = {k: heartbeat[k] for k in ("controller_wall_seconds", "diagnostic_export_wall_seconds",
        "diagnostic_seal_wall_seconds")}
    base.require(all(base.finite(v) for v in costs.values()), "invalid_source_cost")
    prior_reconstruction = heartbeat.get("cumulative_reconstruction_wall_seconds",
        heartbeat.get("reconstruction_wall_seconds", 0.))
    base.require(base.finite(prior_reconstruction), "invalid_prior_reconstruction_cost")
    return {**scope, "source_cut": index, "physical_time": physical, "owner_activations": count,
        "known_native_seal": part["native_state_sha256"], "binary": str(binary),
        "binary_sha256": receipt["binary_sha256"], "offered_total": heartbeat["offered_total"],
        "next_target": base.next_target(part, scope["horizon"], scope["segment_seconds"]),
        "controller_config": part["controller_state"]["config"],
        "cut_controller_state_sha256": state_sha(part["controller_state"]),
        "prior_costs": costs, "source_policy_sha256": receipt["source_before"],
        "excluded_tail": {"first_shard": index + 1, "last_published_shard": heartbeat["segment"],
            "last_physical_time": heartbeat["physical_time"], "native_checkpoint_identity": "unknown"},
        "prior_cost_scope": "Entire source heartbeat costs, including unsealed excluded tail, remain charged. No inference that these are exact cut-only timings; any replayed tail adds new cost.",
        "source_reconstruction_wall_seconds": prior_reconstruction}


def prepare(source, output, absence):
    source, output, absence = source.resolve(), output.resolve(), absence.resolve()
    base.require(source != output and not output.is_relative_to(source), "output_inside_source")
    base.require(not output.exists(), "immutable_output_exists")
    receipt, heartbeat = read(source / "receipt.json"), read(source / "heartbeat.json")
    verify_absence(absence, base.sha(absence), source)
    metadata = selected_metadata(source, receipt, heartbeat)
    data = base.read_gz(source / "input.json.gz")
    provenance = base.verify_input_provenance(source, data, receipt, metadata["offered_total"], metadata["horizon"])
    shards = []
    for index in range(heartbeat["segment"] + 1):
        relative = f"segments/{index:04d}.json.gz"
        digest = base.sha(source / relative)
        sidecar = source / "segment_hashes" / f"{index:04d}.json"
        if sidecar.exists():
            saved = read(sidecar)
            base.require(Path(saved["path"]).as_posix() == relative and saved["sha256"] == digest, "source_sidecar_changed")
        shards.append({"path": relative, "sha256": digest})
    output.mkdir(parents=True)
    for name in ("receipt.json", "heartbeat.json"):
        shutil.copyfile(source / name, output / ("source_" + name.replace(".json", "_snapshot.json")))
    shutil.copyfile(absence, output / "process_observation.json")
    manifest = {"schema": SCHEMA, "source_directory": str(source), **metadata,
        "source_receipt_sha256": base.sha(output / "source_receipt_snapshot.json"),
        "source_heartbeat_sha256": base.sha(output / "source_heartbeat_snapshot.json"),
        "input_sha256": base.sha(source / "input.json.gz"), "provenance": provenance,
        "absence_sha256": base.sha(output / "process_observation.json"),
        "shards": shards[:metadata["source_cut"] + 1], "excluded_tail_shards": shards[metadata["source_cut"] + 1:]}
    base.dump(output / "cut_manifest.json", manifest)
    cut_sha = base.sha(output / "cut_manifest.json")
    base.dump(output / "source_stop_receipt.json", {"schema": "g31.full_day_resume_stop.v1",
        "source_worker_stopped": True, "unchanged_policy": True, "cut_manifest_sha256": cut_sha,
        "evidence_kind": "observed_original_parent_and_worker_absent; exit_reason_unknown",
        "process_observation_sha256": manifest["absence_sha256"]})
    return manifest


def validate(path, expected_sha):
    path = Path(path).resolve()
    base.require(base.sha(path) == expected_sha, "selected_cut_changed")
    cut = read(path)
    base.require(cut.get("schema") == SCHEMA, "invalid_sparse_cut_schema")
    source = Path(cut["source_directory"])
    for name in ("receipt", "heartbeat"):
        base.require(base.sha(path.parent / f"source_{name}_snapshot.json") == cut[f"source_{name}_sha256"], "source_snapshot_changed")
    receipt, heartbeat = (read(path.parent / f"source_{name}_snapshot.json") for name in ("receipt", "heartbeat"))
    verify_absence(path.parent / "process_observation.json", cut["absence_sha256"], source)
    expected = selected_metadata(source, receipt, heartbeat)
    base.require(all(cut.get(k) == v for k, v in expected.items()), "selected_cut_metadata_changed")
    base.require(base.sha(source / "input.json.gz") == cut["input_sha256"], "source_input_changed")
    base.require(len(cut["shards"]) == cut["source_cut"] + 1 and
        len(cut["shards"]) + len(cut["excluded_tail_shards"]) == heartbeat["segment"] + 1, "selected_prefix_count")
    for index, row in enumerate(cut["shards"] + cut["excluded_tail_shards"]):
        base.require(row["path"] == f"segments/{index:04d}.json.gz" and
            base.sha(source / row["path"]) == row["sha256"], "source_prefix_or_tail_changed")
    return cut


@contextmanager
def selected_validator():
    """Only a serial worker's validation adapter; never modifies source files."""
    original = base.validate_cut
    original_reconstruct = base.reconstruct
    base.require(original.__module__ == base.__name__, "foreign_cut_validator")
    def reconstruct_with_cost_scope(cut, *args, **kwargs):
        session, part, segments, report, data = original_reconstruct(cut, *args, **kwargs)
        report["prefix_cost_scope"] = cut["prior_cost_scope"]
        report["charged_source_cost_minus_selected_raw_seconds"] = report.pop("prefix_outer_wrapper_residual_seconds")
        report["prior_reconstruction_wall_seconds"] = cut["source_reconstruction_wall_seconds"]
        return session, part, segments, report, data
    base.validate_cut = validate
    base.reconstruct = reconstruct_with_cost_scope
    try:
        yield
    finally:
        base.validate_cut = original
        base.reconstruct = original_reconstruct


def worker(args):
    cut = validate(args.cut_manifest, args.expected_cut_sha256)
    base.dump(args.output / "interruption_cost_scope.json", {"prior_costs": cut["prior_costs"],
        "prior_reconstruction_wall_seconds": cut["source_reconstruction_wall_seconds"],
        "prior_cost_scope": cut["prior_cost_scope"], "original_process_exit_reason": "unknown",
        "paused_calendar_time": "separate user interruption; not normal active performance"})
    with selected_validator(), installed_public_travel_pool():
        result = base.worker(args)
    proof = args.output / "resume_source"
    shutil.copyfile(args.cut_manifest.parent / "process_observation.json", proof / "process_observation.json")
    reconstruction = read(args.output / "reconstruction.json")
    reconstruction.update(prior_reconstruction_wall_seconds=cut["source_reconstruction_wall_seconds"],
        cumulative_reconstruction_wall_seconds=cut["source_reconstruction_wall_seconds"] + reconstruction["wall_seconds"],
        prefix_cost_scope=cut["prior_cost_scope"])
    base.dump(args.output / "reconstruction.json", reconstruction)
    summary = read(args.output / "summary.json")
    summary.update(reconstruction=reconstruction, prior_cost_scope=cut["prior_cost_scope"],
        prior_reconstruction_wall_seconds=reconstruction["prior_reconstruction_wall_seconds"],
        cumulative_reconstruction_wall_seconds=reconstruction["cumulative_reconstruction_wall_seconds"])
    base.dump(args.output / "summary.json", summary)
    heartbeat = read(args.output / "heartbeat.json")
    heartbeat.update(cumulative_reconstruction_wall_seconds=reconstruction["cumulative_reconstruction_wall_seconds"])
    base.dump(args.output / "heartbeat.json", heartbeat)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-source", type=Path)
    parser.add_argument("--absence", type=Path)
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
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if args.prepare_source:
        cut = prepare(args.prepare_source, args.output, args.absence)
        print(json.dumps({k: cut[k] for k in ("source_cut", "physical_time", "owner_activations", "known_native_seal")}))
        return 0
    base.require(base.finite(args.hard_timeout, positive=True) and args.hard_timeout <= 7200, "invalid_resume_timeout")
    if args.worker:
        try:
            return worker(args)
        except Exception:
            (args.output / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            raise
    cut = validate(args.cut_manifest, args.expected_cut_sha256)
    base.validate_stop(args.stop_receipt, args.expected_stop_sha256, args.expected_cut_sha256)
    args.output.mkdir(parents=True, exist_ok=False)
    sources = sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m, "__file__", None)
        and str(m.__file__).endswith(".py") and Path(m.__file__).resolve().is_relative_to(ROOT)})
    before = {str(p.relative_to(ROOT)): base.sha(p) for p in sources}
    for path in sources:
        target = args.output / "source_archive" / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    command = [sys.executable, "-m", __spec__.name, *sys.argv[1:], "--worker"]
    receipt = {"schema": "g31.sparse_sealed_resume_worker.v1", "status": "running", "command": command,
        "source_before": before, "binary_sha256": cut["binary_sha256"], "hard_timeout_seconds": args.hard_timeout,
        "cut_manifest_sha256": args.expected_cut_sha256, "prior_interruption_retained": True,
        "cache_mode": "on_owner_public_static_only_cold_start", "complete_100ms_requirement_certified": False}
    base.dump(args.output / "receipt.json", receipt)
    started = time.perf_counter()
    with (args.output / "stdout.log").open("x", encoding="utf-8") as out, (args.output / "stderr.log").open("x", encoding="utf-8") as err:
        try:
            result = subprocess.run(command, cwd=ROOT, stdout=out, stderr=err, timeout=args.hard_timeout)
            receipt.update(status="completed" if result.returncode == 0 else "failed", exit_code=result.returncode)
        except subprocess.TimeoutExpired:
            receipt.update(status="hard_timeout", exit_code=None)
    receipt.update(wall_seconds=time.perf_counter() - started,
        source_changed=[p for p, h in before.items() if base.sha(ROOT / p) != h], binary_after_sha256=base.sha(args.binary))
    if receipt["source_changed"] or receipt["binary_after_sha256"] != cut["binary_sha256"]:
        receipt["status"] = "invalidated_source_or_binary_changed"
    base.dump(args.output / "receipt.json", receipt)
    base.finalize_verification(args.output, receipt, cut)
    print(json.dumps({k: receipt[k] for k in ("status", "wall_seconds", "source_changed")}))
    return 0 if receipt["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
