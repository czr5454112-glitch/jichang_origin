"""Resume a terminated sparse-resume attempt, retaining ancestor costs.

This separate driver leaves an active attempt and its frozen dependencies
unchanged. It never changes the binary, policy, workload, or known-seal gate.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from pathlib import Path
import json
import shlex
import shutil
import subprocess
import sys
import time
import traceback

from . import resume_sealed_stream as prior
from .install_public_travel_pool import installed_public_travel_pool

base, ROOT = prior.base, prior.ROOT
MODULE = "scripts.experiments.g31_ics_circulation.resume_chained_sealed_stream"
SCHEMA = "g31.chained_sparse_sealed_resume_worker.v1"
PARENTS = {"g31.sparse_sealed_resume_worker.v1", SCHEMA}
ABSENCE_SCHEMA = "g31.terminated_resume_process_observation.v1"
_source_scope = prior.source_scope
_selected_metadata = prior.selected_metadata
_verify_absence = prior.verify_absence


def ancestor_cut(receipt):
    command = receipt["command"]
    for key in ("--cut-manifest", "--expected-cut-sha256", "--binary", "--suite", "--horizon", "--event-budget"):
        base.require(command.count(key) == 1, "ambiguous_ancestor_argument:" + key)
    path = Path(base.option(command, "--cut-manifest"))
    expected = base.option(command, "--expected-cut-sha256")
    base.require(base.sha(path) == expected == receipt["cut_manifest_sha256"], "ancestor_cut_changed")
    cut = prior.read(path)
    base.require(cut["schema"] == prior.SCHEMA, "unsupported_ancestor_cut")
    base.require(Path(base.option(command, "--binary")).resolve() == Path(cut["binary"]).resolve()
        and receipt["binary_sha256"] == cut["binary_sha256"], "ancestor_binary_changed")
    base.require(base.option(command, "--suite") == cut["suite"]
        and float(base.option(command, "--horizon")) == cut["horizon"]
        and int(base.option(command, "--event-budget")) == cut["event_budget"], "ancestor_scope_changed")
    return cut, expected


def source_scope(receipt):
    if receipt["schema"] not in PARENTS: return _source_scope(receipt)
    cut, _ = ancestor_cut(receipt)
    return {key: cut[key] for key in ("suite", "horizon", "segment_seconds", "event_budget", "max_activations", "activation_shard_budget")}


def cumulative_reconstruction(receipt, heartbeat):
    cut, digest = ancestor_cut(receipt)
    inherited = cut["source_reconstruction_wall_seconds"]
    current = heartbeat["reconstruction_wall_seconds"]
    base.require(base.finite(inherited) and base.finite(current), "invalid_chain_reconstruction_cost")
    cumulative = inherited + current
    if "cumulative_reconstruction_wall_seconds" in heartbeat:
        base.require(heartbeat["cumulative_reconstruction_wall_seconds"] == cumulative, "inconsistent_chain_reconstruction_cost")
    return cumulative, digest, inherited


def selected_metadata(source, receipt, heartbeat):
    selected_heartbeat = heartbeat
    inherited_seal = receipt["schema"] in PARENTS and heartbeat.get("latest_native_seal") is None
    if inherited_seal:
        ancestor, _ = ancestor_cut(receipt)
        selected_heartbeat = {**heartbeat, "latest_native_seal": {"shard": ancestor["source_cut"],
            "physical_time": ancestor["physical_time"], "native_state_sha256": ancestor["known_native_seal"]}}
    metadata = _selected_metadata(source, receipt, selected_heartbeat)
    if receipt["schema"] in PARENTS:
        base.require(receipt["status"] in {"failed", "hard_timeout"}, "parent_attempt_still_running_or_complete")
        cost, digest, inherited = cumulative_reconstruction(receipt, heartbeat)
        metadata.update(source_reconstruction_wall_seconds=cost, ancestor_cut_manifest_sha256=digest,
            source_ancestor_reconstruction_wall_seconds=inherited, source_terminal_status=receipt["status"],
            source_exit_code=receipt.get("exit_code"),
            selected_seal_origin="ancestor_known_seal" if inherited_seal else "source_published_new_seal",
            prior_cost_scope="Entire latest heartbeat controller/export/seal costs, including excluded tail, remain charged; all ancestor reconstruction costs plus this source reconstruction are cumulative. Unpublished tail costs remain unknown.")
    return metadata


def verify_absence(path, expected_sha, source):
    base.require(base.sha(path) == expected_sha, "absence_observation_changed")
    record = prior.read(path)
    if record.get("schema") != ABSENCE_SCHEMA: return _verify_absence(path, expected_sha, source)
    base.require(record.get("all_original_identities_absent") is True and isinstance(record.get("observed_utc"), str), "parent_worker_absence_not_observed")
    def tokens(row): return [s.strip('"') for s in shlex.split(row["expected"]["CommandLine"], posix=False)]
    matching = []
    for row in record["processes"]:
        command = tokens(row)
        if command.count("--output") == 1 and (ROOT / base.option(command, "--output")).resolve() == source.resolve():
            matching.append(row)
    parents = [r for r in matching if "--worker" not in tokens(r)]
    workers = [r for r in matching if "--worker" in tokens(r)]
    base.require(len(matching) == 2 and len(parents) == len(workers) == 1 and
        all(r.get("old_identity_present") is False and r.get("observed") is None for r in matching), "missing_exact_parent_worker_absence")
    base.require(workers[0]["expected"]["ParentProcessId"] == parents[0]["expected"]["ProcessId"], "wrong_parent_worker_relationship")
    receipt = prior.read(source / "receipt.json")
    command = receipt["command"]
    base.require(receipt["schema"] in PARENTS and command.count("--worker") == 1
        and tokens(workers[0]) == command
        and tokens(parents[0]) == [arg for arg in command if arg != "--worker"], "process_command_not_source_attempt")
    reference = record["prior_identity_reference"]
    base.require(base.sha(reference["path"]) == reference["sha256"], "prior_process_identity_changed")
    identities = prior.read(reference["path"])
    base.require(all(type(r["expected"].get("ProcessId")) is int and r["expected"]["ProcessId"] > 0
        and isinstance(r["expected"].get("CreationDate"), str) and bool(r["expected"]["CreationDate"])
        and r["expected"] in identities for r in matching), "process_identity_not_previously_observed")
    return record


@contextmanager
def chained_adapters():
    """Serial-driver compatibility only; no frozen file or policy is modified."""
    original = prior.source_scope, prior.selected_metadata, prior.verify_absence
    base.require(original == (_source_scope, _selected_metadata, _verify_absence), "foreign_chain_adapter")
    prior.source_scope, prior.selected_metadata, prior.verify_absence = source_scope, selected_metadata, verify_absence
    try: yield
    finally: prior.source_scope, prior.selected_metadata, prior.verify_absence = original


def prepare(source, output, absence):
    source, output, absence = source.resolve(), output.resolve(), absence.resolve()
    receipt = prior.read(source / "receipt.json")
    base.require(receipt["schema"] in PARENTS and receipt["status"] in {"failed", "hard_timeout"}, "not_terminated_chained_source")
    base.require(prior.read(absence).get("schema") == ABSENCE_SCHEMA, "new_termination_observation_required")
    with chained_adapters(): cut = prior.prepare(source, output, absence)
    # These files are still inside this single preparation operation. Preserve
    # the original terminal receipt; do not relabel a known timeout as a pause.
    stop = prior.read(output / "source_stop_receipt.json")
    stop.update(evidence_kind="terminated_attempt_and_exact_parent_worker_absence",
        source_terminal_status=receipt["status"], source_exit_code=receipt.get("exit_code"))
    base.dump(output / "source_stop_receipt.json", stop)
    return cut


def validate(path, expected):
    with chained_adapters(): return prior.validate(path, expected)


def worker(args):
    cut = validate(args.cut_manifest, args.expected_cut_sha256)
    base.require(cut.get("source_terminal_status") in {"failed", "hard_timeout"}, "missing_terminated_source")
    base.dump(args.output / "interruption_cost_scope.json", {"prior_costs": cut["prior_costs"],
        "prior_reconstruction_wall_seconds": cut["source_reconstruction_wall_seconds"],
        "prior_cost_scope": cut["prior_cost_scope"], "source_terminal_status": cut["source_terminal_status"],
        "source_exit_code": cut["source_exit_code"], "user_pause_in_this_attempt": False})
    with chained_adapters(), prior.selected_validator(), installed_public_travel_pool():
        result = base.worker(args)
    proof = args.output / "resume_source"
    shutil.copyfile(args.cut_manifest.parent / "process_observation.json", proof / "process_observation.json")
    reconstruction = prior.read(args.output / "reconstruction.json")
    reconstruction.update(prior_reconstruction_wall_seconds=cut["source_reconstruction_wall_seconds"],
        cumulative_reconstruction_wall_seconds=cut["source_reconstruction_wall_seconds"] + reconstruction["wall_seconds"],
        prefix_cost_scope=cut["prior_cost_scope"])
    base.dump(args.output / "reconstruction.json", reconstruction)
    summary = prior.read(args.output / "summary.json")
    summary.update(reconstruction=reconstruction, prior_cost_scope=cut["prior_cost_scope"],
        prior_reconstruction_wall_seconds=reconstruction["prior_reconstruction_wall_seconds"],
        cumulative_reconstruction_wall_seconds=reconstruction["cumulative_reconstruction_wall_seconds"])
    base.dump(args.output / "summary.json", summary)
    heartbeat = prior.read(args.output / "heartbeat.json")
    heartbeat.update(cumulative_reconstruction_wall_seconds=reconstruction["cumulative_reconstruction_wall_seconds"])
    base.dump(args.output / "heartbeat.json", heartbeat)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-source", type=Path); parser.add_argument("--absence", type=Path)
    parser.add_argument("--output", type=Path, required=True); parser.add_argument("--cut-manifest", type=Path)
    parser.add_argument("--expected-cut-sha256"); parser.add_argument("--stop-receipt", type=Path)
    parser.add_argument("--expected-stop-sha256"); parser.add_argument("--binary", type=Path)
    parser.add_argument("--suite"); parser.add_argument("--horizon", type=float); parser.add_argument("--event-budget", type=int)
    parser.add_argument("--hard-timeout", type=float, default=7200.); parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if args.prepare_source:
        base.require(not args.worker, "prepare_is_not_worker")
        cut = prepare(args.prepare_source, args.output, args.absence)
        print(json.dumps({k: cut[k] for k in ("source_cut", "physical_time", "source_reconstruction_wall_seconds")})); return 0
    base.require(base.finite(args.hard_timeout, positive=True) and args.hard_timeout <= 7200, "invalid_chain_timeout")
    if args.worker:
        try: return worker(args)
        except Exception:
            (args.output / "error.txt").write_text(traceback.format_exc(), encoding="utf-8"); raise
    cut = validate(args.cut_manifest, args.expected_cut_sha256)
    base.validate_stop(args.stop_receipt, args.expected_stop_sha256, args.expected_cut_sha256)
    args.output.mkdir(parents=True, exist_ok=False)
    paths = sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m, "__file__", None)
        and str(m.__file__).endswith(".py") and Path(m.__file__).resolve().is_relative_to(ROOT)})
    before = {str(p.relative_to(ROOT)): base.sha(p) for p in paths}
    for path in paths:
        target = args.output / "source_archive" / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, target)
    command = [sys.executable, "-m", MODULE, *sys.argv[1:], "--worker"]
    receipt = {"schema": SCHEMA, "status": "running", "command": command, "source_before": before,
        "binary_sha256": cut["binary_sha256"], "hard_timeout_seconds": args.hard_timeout,
        "cut_manifest_sha256": args.expected_cut_sha256, "prior_interruption_retained": True,
        "cache_mode": "on_owner_public_static_only_cold_start", "complete_100ms_requirement_certified": False}
    base.dump(args.output / "receipt.json", receipt); started = time.perf_counter()
    with (args.output / "stdout.log").open("x", encoding="utf-8") as out, (args.output / "stderr.log").open("x", encoding="utf-8") as err:
        try:
            done = subprocess.run(command, cwd=ROOT, stdout=out, stderr=err, timeout=args.hard_timeout, check=False)
            receipt.update(status="completed" if done.returncode == 0 else "failed", exit_code=done.returncode)
        except subprocess.TimeoutExpired: receipt.update(status="hard_timeout", exit_code=None)
    receipt.update(wall_seconds=time.perf_counter() - started,
        source_changed=[p for p, digest in before.items() if base.sha(ROOT / p) != digest], binary_after_sha256=base.sha(args.binary))
    if receipt["source_changed"] or receipt["binary_after_sha256"] != cut["binary_sha256"]:
        receipt["status"] = "invalidated_source_or_binary_changed"
    base.dump(args.output / "receipt.json", receipt)
    with chained_adapters(): base.finalize_verification(args.output, receipt, cut)
    print(json.dumps({k: receipt[k] for k in ("status", "wall_seconds", "source_changed")}))
    return 0 if receipt["status"] == "completed" else 1


if __name__ == "__main__": sys.exit(main())
