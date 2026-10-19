"""Prepare/run a source-pinned original28506 finite operation cohort.

Preparation never constructs NativeSession. Execution remains a separate,
explicit command after pure guards and source review; original business100ms
acceptance is never inferred from this experimental notification boundary.
"""
from __future__ import annotations

import argparse
import ast
import gzip
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[3]
# The repository uses a src layout. Fresh subprocesses must not rely on an
# unrelated earlier import or pytest's pythonpath setting to select the package.
if str(ROOT/"src") not in sys.path: sys.path.insert(0, str(ROOT/"src"))

from . import original_notification_probe as engine
from . import original_notification_contract as boundary
from . import replay_original_notification_probe as replay
from . import original_workload as original
from . import native025_request_timing as abi
from .capture_native025_request_timing import Native025TimingCapture
from .native_host import load_native
from .run_original_protocol import add_protocol_contract


CASES = {"baseline": 0, "drop_first_ack": 1, "withhold_ack": 100}
ARMS = ("plain", "timed")


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    path = Path(path)
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_text(encoding="utf-8"))


def write(path, data):
    path = Path(path); encoded = json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
    tmp = path.with_suffix(path.suffix+".tmp")
    tmp.write_bytes(gzip.compress(encoded, mtime=0) if path.suffix == ".gz" else encoded)
    tmp.replace(path)


def source_paths():
    pending = [Path(__file__)]; found = set()
    def enqueue(target):
        for candidate in (target.with_suffix(".py"), target/"__init__.py"):
            if candidate.is_file() and candidate.resolve().is_relative_to(ROOT):
                pending.append(candidate)
                for parent in candidate.parents:
                    if parent == ROOT: break
                    if (parent/"__init__.py").is_file(): pending.append(parent/"__init__.py")
    while pending:
        path = pending.pop().resolve()
        if path in found: continue
        found.add(path)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if isinstance(node, ast.ImportFrom):
                bases = [path.parent] if node.level else [ROOT, ROOT/"src"]
                for base in bases:
                    for _ in range(max(0, node.level-1)): base = base.parent
                    if node.module: base = base.joinpath(*node.module.split(".")); enqueue(base)
                    for alias in node.names:
                        if alias.name != "*": enqueue(base.joinpath(*alias.name.split(".")))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    for base in (ROOT, ROOT/"src"): enqueue(base.joinpath(*alias.name.split(".")))
    return sorted(found)


def unarchived_loaded_sources(plan):
    missing = []
    known = set(plan["source_sha256"])
    for name, module in list(sys.modules.items()):
        value = getattr(module, "__file__", None)
        if not value: continue
        path = Path(value).resolve()
        if path.suffix != ".py": continue
        project_name = name == "czr005" or name.startswith(("czr005.", "scripts."))
        if (path.is_relative_to(ROOT) or project_name) and str(path) not in known:
            # Test modules are not execution dependencies of a fresh worker.
            if path.is_relative_to(ROOT/"tests"): continue
            missing.append(str(path))
    return sorted(set(missing))


def unchanged(plan):
    return [name for name, expected in {**plan["source_sha256"], **plan["input_source_sha256"]}.items()
            if not Path(name).is_file() or sha(name) != expected]


def prepare(output, profile, reference):
    output.mkdir(parents=True, exist_ok=False)
    data, manifest = read(profile/"input.json.gz"), read(profile/"input_manifest.json")
    cfg = boundary.contract()
    boundary.require(len(data["jobs"]) == cfg["original_offered_jobs"] == manifest["offered_business_count"]
        and len(data["node_records"]) == cfg["nodes"] and len(data["edge_records"]) == cfg["directed_edges"]
        and len({j["business_bag_id"] for j in data["jobs"]}) == cfg["original_offered_jobs"]
        and all(j.get("allow_suffix_reroute", False) is False for j in data["jobs"])
        and data.get("owner_notifications") == {"enabled": True}, "not_frozen_original1x_permission_domain")
    authority = read(reference); checked = abi.verify_contract(authority, require_runtime=True)
    paths = source_paths()
    sources = {str(p): sha(p) for p in paths}
    input_sources = {str((profile/name).resolve()): sha(profile/name) for name in ("input.json.gz", "input_manifest.json")}
    input_sources.update(manifest["source_sha256"])
    for path, expected in input_sources.items(): boundary.require(sha(path) == expected, "original_source_changed")
    plan = {"schema": "g31.original_notification_campaign.v1", "contract": cfg, "cases": CASES, "arms": list(ARMS),
        "profile": str(profile.resolve()), "contract_reference": authority, "accepted_reference_sha256": sha(reference),
        "accepted_contract_sha256": authority["sha256"], "binary": checked["contract"]["binary"],
        "binary_sha256": checked["contract"]["binary_sha256"], "source_sha256": sources, "input_source_sha256": input_sources,
        "process_timeout_seconds": 180., "maximum_native_workers": 1,
        "input_reconstruction": "Full build_input from source raw/map and exact archived proxy inside mandatory setup; add original protocol/notifications and require complete JSON structural identity before applying the one declared ACK-loss factor.",
        "scope": "Finite notification operations on full28506 input; no production business100ms or full-horizon service claim."}
    boundary.require(not unarchived_loaded_sources(plan), "unarchived_loaded_source_before_prepare")
    for path in paths:
        target = output/"source"/path.relative_to(ROOT); target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, target)
    shutil.copyfile(reference, output/"accepted_reference.json")
    shutil.copyfile(authority["path"], output/"accepted_contract.json")
    write(output/"plan.json", plan)
    return plan


def rebuild_input(plan, case):
    profile = Path(plan["profile"]); frozen = read(profile/"input.json.gz"); manifest = read(profile/"input_manifest.json")
    proxy = original.ProxyContract(**manifest["proxy_contract"])
    data, rebuilt_manifest, _ = original.build_input(scale=1, contract=proxy,
        horizon=frozen["options"]["max_simulation_time"], max_events=frozen["options"]["max_events"],
        trace_limit=frozen["options"]["trace_limit"], scorer=frozen["options"]["scorer_mode"])
    data = add_protocol_contract(data); data["owner_notifications"] = {"enabled": True}
    boundary.require(replay.canonical(data) == replay.canonical(frozen), "rebuilt_input_not_exact_full_source")
    boundary.require(rebuilt_manifest["offered_business_count"] == 28506, "offered_denominator_changed")
    data["owner_protocol"]["drop_ack_packets"] = CASES[case]
    return data, rebuilt_manifest


def worker(output, case, arm):
    plan = read(output/"plan.json"); boundary.require(not unchanged(plan) and not unarchived_loaded_sources(plan), "source_changed_or_unarchived_before_worker")
    cell = output/case/arm; cell.mkdir(parents=True, exist_ok=False)
    write(cell/"started.json", {"status": "unknown_in_progress", "case": case, "arm": arm, "source_offered_jobs": 28506})
    start = time.perf_counter_ns()
    data, input_manifest = rebuild_input(plan, case)
    checked = abi.verify_contract(plan["contract_reference"], require_runtime=True)
    native = load_native(checked["contract"]["binary"]); session = native.NativeSession(data)
    before_capture = time.perf_counter_ns()
    capture = Native025TimingCapture(session, native_module=native, contract_reference=plan["contract_reference"], session_identity=1) if arm == "timed" else None
    capture_setup = {"start_ns": before_capture, "end_ns": time.perf_counter_ns()}
    chunks = []
    def sink(chunk):
        path = cell/("tape_%04d.json.gz" % chunk["index"]); write(path, chunk)
        reference = {"path": path.name, "sha256": sha(path), "index": chunk["index"]}
        chunks.append(reference); return reference
    owners = sorted({n.get("resource_owner", n["zone"]) for n in data["node_contracts"]})
    raw = engine.run_cohort(capture if capture else session, owners, chunk_sink=sink)
    # Required output/ACK/drains have already ended; exports are diagnostics.
    raw.update(mandatory_setup_start_ns=start, capture_setup=capture_setup, owners=owners,
        input_sha256=original.json_digest(data), source_offered_jobs=len(data["jobs"]), case=case, arm=arm,
        native_binary_sha256=native._g31_native_artifact_identity["sha256"],
        native_state_sha256=session.offline_state_sha256(), source_changed=unchanged(plan),
        unarchived_loaded_sources=unarchived_loaded_sources(plan))
    if capture:
        capture.take_completed(); raw["timing"] = {"batches": capture.batches, "envelopes": capture.envelopes, "errors": capture.errors}
    write(cell/"input.json.gz", data); write(cell/"input_manifest.json", input_manifest); write(cell/"raw.json.gz", raw)
    write(cell/"completion.json", {"status": raw["status"], "source_changed": raw["source_changed"],
        "unarchived_loaded_sources": raw["unarchived_loaded_sources"],
        "raw_sha256": sha(cell/"raw.json.gz"), "input_sha256": sha(cell/"input.json.gz"), "chunks": chunks})
    return 0 if not raw["failures"] and not raw["source_changed"] and not raw["unarchived_loaded_sources"] else 2


def execute_cell(output, case, arm, *, runner=subprocess.run):
    plan = read(output/"plan.json"); path = output/(case+"_"+arm+".process.json")
    command = [sys.executable, "-m", __spec__.name, "--output", str(output), "--worker", "--case", case, "--arm", arm]
    started = time.perf_counter(); receipt = {"command": command, "status": "unknown_launch_failure", "exit_code": None}
    try:
        with (output/(case+"_"+arm+".stdout.txt")).open("w") as stdout, (output/(case+"_"+arm+".stderr.txt")).open("w") as stderr:
            process = runner(command, stdout=stdout, stderr=stderr, timeout=plan["process_timeout_seconds"], check=False)
        receipt.update(status="process_exited", exit_code=process.returncode)
    except subprocess.TimeoutExpired: receipt["status"] = "hard_timeout"
    except OSError as error: receipt["error"] = type(error).__name__+":"+str(error)
    receipt["wall_seconds"] = time.perf_counter()-started; write(path, receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True); parser.add_argument("--profile", type=Path)
    parser.add_argument("--reference", type=Path); parser.add_argument("--execute", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--case", choices=CASES); parser.add_argument("--arm", choices=ARMS)
    args = parser.parse_args()
    if args.worker:
        try: return worker(args.output, args.case, args.arm)
        except BaseException:
            write(args.output/(args.case+"_"+args.arm+".failure.json"), {"status": "unknown_failed_worker", "error": traceback.format_exc()})
            raise
    boundary.require(args.profile is not None and args.reference is not None, "profile_and_accepted_reference_required")
    plan = prepare(args.output, args.profile, args.reference)
    if not args.execute: return 0
    processes = {}
    for case in CASES:
        for arm in ARMS: processes[case+"/"+arm] = execute_cell(args.output, case, arm)
    write(args.output/"receipt.json", {"status": "executed_pending_independent_verification", "source_changed": unchanged(plan),
        "plan_sha256": sha(args.output/"plan.json"),
        "declared_cells": list(processes), "process_sha256": {key: sha(args.output/(key.replace("/", "_")+".process.json")) for key in processes},
        "completion_sha256": {key: sha(args.output/key/"completion.json") if (args.output/key/"completion.json").is_file() else None for key in processes},
        "maximum_native_workers": 1, "source_offered_jobs_per_cell": 28506, "original_business_request_100ms_certified": False})
    from .verify_original_notification_probe import verify_or_unknown
    report = verify_or_unknown(args.output); write(args.output/"independent_verification.json", report)
    return 0 if report["status"] == "validated_original_notification_operation_campaign" else 1


if __name__ == "__main__": sys.exit(main())
