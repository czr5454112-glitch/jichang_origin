"""Bounded actual v3 semantic regression, separate from timing acceptance.

Prepare/verify are read-only with respect to native execution. A successful
finite regression does not establish model protection or request latency.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
MODULE = "scripts.experiments.g31_ics_circulation.run_native027_semantic_gate"
SCHEMA = "g31.native027_semantic_gate.v1"
TEST = ROOT / "tests/test_g31_circulation_planning_snapshot_v3.py"
BINARY_SHA = "845486b745bc6e65a9988d1ef5429336b60fd472eb73c39e133e19ec93a7e7be"
EXPECTED = {
    "test_reservation_before_actual_entry_retains_unmatched_denominator": 1,
    "test_actual_entry_public_identity_and_exact_source_observable_exit": 1,
    "test_remote_incoming_identified_occupancy_and_no_atomic_cut_claim": 1,
    "test_source_changes_after_exit_and_old_capture_cannot_prove_arrival": 1,
    "test_checkpoint_retry_peer_selfcopy_and_typed_digest_are_exact": 4,
    "test_lost_self_ack_does_not_hide_peer_or_recapture_on_retry": 1,
    "test_outage_capture_and_delivery_preserve_causal_source_facts": 2,
    "test_latest_expiry_is_tombstone_and_old_pending_ack_has_no_future_body": 1,
    "test_caller_cannot_supply_entry_facts_or_internal_identity": 6,
    "test_wrong_owner_and_unknown_observer_cannot_read_capture": 1,
    "test_unrelated_private_traversals_and_future_events_do_not_change_source_body": 1,
    "test_reused_tray_and_empty_return_bind_current_source_job_and_traversal": 1,
}


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_bytes())
def require(value, reason):
    if not value: raise ValueError("native027_semantic:" + reason)


def write(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def source_paths():
    pending, found = [Path(__file__).resolve(), TEST], set()
    def enqueue(base):
        for path in (base.with_suffix(".py"), base / "__init__.py"):
            if path.is_file() and path.resolve().is_relative_to(ROOT):
                pending.append(path.resolve())
                for parent in path.parents:
                    if parent == ROOT: break
                    if (parent / "__init__.py").is_file(): pending.append(parent / "__init__.py")
    while pending:
        path = pending.pop().resolve()
        if path in found: continue
        found.add(path)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if isinstance(node, ast.ImportFrom):
                for base in ([path.parent] if node.level else [ROOT, ROOT / "src"]):
                    for _ in range(max(0, node.level - 1)): base = base.parent
                    if node.module: base = base.joinpath(*node.module.split(".")); enqueue(base)
                    for alias in node.names:
                        if alias.name != "*": enqueue(base.joinpath(*alias.name.split(".")))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    for base in (ROOT, ROOT / "src"): enqueue(base.joinpath(*alias.name.split(".")))
    return sorted(found | {ROOT / "pyproject.toml"})


def check_plan(directory, plan):
    require(plan["schema"] == SCHEMA and plan["expected_test_counts"] == EXPECTED, "test_domain_changed")
    require(set(plan["source_sha256"]) == {str(p) for p in source_paths()}, "source_inventory_changed")
    for name, digest in plan["source_sha256"].items():
        path = Path(name)
        require(sha(path) == digest == sha(directory / "source" / path.relative_to(ROOT)), "source_changed:" + name)
    require(sha(plan["binary"]) == plan["binary_sha256"] == BINARY_SHA, "binary_changed")
    require(sha(plan["interpreter"]) == plan["interpreter_sha256"], "interpreter_changed")
    require(sha(plan["build_receipt"]) == plan["build_receipt_sha256"], "build_receipt_changed")
    build = read(plan["build_receipt"])
    require(build["status"] == "build_passed_tests_held" and not build["source_changed"]
        and build["source_before"] == build["source_after"] and bool(build["source_after"]), "unverified_build")
    require(any(Path(p).resolve() == Path(plan["binary"]) and h == BINARY_SHA
        for p, h in build["binary_sha256"].items()), "binary_not_built")
    archive = Path(plan["build_receipt"]).parent / "source"
    for relative, digest in build["source_after"].items():
        path = Path(relative.replace("\\", "/"))
        require(not path.is_absolute() and ".." not in path.parts and sha(archive / path) == digest, "compiled_archive_changed")


def prepare(directory, binary, build_receipt):
    directory.mkdir(parents=True, exist_ok=False)
    paths = source_paths()
    plan = {"schema": SCHEMA, "expected_test_counts": EXPECTED,
        "source_sha256": {str(p): sha(p) for p in paths},
        "binary": str(binary.resolve()), "binary_sha256": sha(binary),
        "build_receipt": str(build_receipt.resolve()), "build_receipt_sha256": sha(build_receipt),
        "interpreter": str(Path(sys.executable).resolve()), "interpreter_sha256": sha(sys.executable),
        "timeout_seconds": 180, "maximum_native_workers": 1}
    for path in paths:
        target = directory / "source" / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, target)
    write(directory / "plan.json", plan)
    check_plan(directory, plan)
    return plan


def validate_xml(path):
    root = ET.parse(path).getroot(); cases = list(root.iter("testcase"))
    names = [case.attrib["name"] for case in cases]
    require(len(names) == len(set(names)) == 21, "test_count_or_duplicates")
    require(dict(Counter(name.split("[", 1)[0] for name in names)) == EXPECTED, "missing_required_test")
    require(not any(list(case) for case in cases), "test_failure_error_skip_or_unexpected_output")
    for suite in root.iter("testsuite"):
        require(all(int(suite.attrib.get(k, 0)) == 0 for k in ("failures", "errors", "skipped")), "suite_not_passed")
    return names


def worker(directory):
    plan = read(directory / "plan.json"); check_plan(directory, plan)
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    os.environ["G31_CIRCULATION_BINARY"] = plan["binary"]
    sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
    import pytest
    code = int(pytest.main([str(TEST), "-q", "--junitxml=" + str(directory / "tests.xml")]))
    loaded = {}
    for name, module in list(sys.modules.items()):
        location = getattr(module, "__file__", None)
        if not location: continue
        path = Path(location).resolve()
        if path.suffix == ".py" and (path.is_relative_to(ROOT) or name == "czr005" or name.startswith(("scripts.", "czr005."))):
            loaded[str(path)] = sha(path)
    # Extension loading need not register the module in sys.modules; retain the
    # exact fixture-loaded object solely for post-test artifact verification.
    test_module = next((m for m in sys.modules.values() if getattr(m, "__file__", None)
        and Path(m.__file__).resolve() == TEST), None)
    native = getattr(test_module, "_verified_native_for_gate", None)
    actual_binary = Path(native.__file__).resolve() if native is not None else None
    write(directory / "worker.json", {"exit_code": code, "loaded_source_sha256": loaded,
        "unarchived_loaded_sources": sorted(set(loaded) - set(plan["source_sha256"])),
        "binary_sha256_after": sha(plan["binary"]), "fixture_module_loaded": native is not None,
        "actual_binary_path": str(actual_binary) if actual_binary else None,
        "actual_binary_sha256": sha(actual_binary) if actual_binary else None,
        "native_host_identity": getattr(native, "_g31_native_artifact_identity", None),
        "python_version": sys.version, "pytest_version": pytest.__version__})
    check_plan(directory, plan)
    return code


def validate_worker(plan, actual):
    require(actual["exit_code"] == 0 and not actual["unarchived_loaded_sources"]
        and actual["fixture_module_loaded"] is True, "loaded_source_gap_or_failed_tests")
    require(actual["binary_sha256_after"] == actual["actual_binary_sha256"] == plan["binary_sha256"]
        and actual["actual_binary_path"] == plan["binary"]
        and actual["native_host_identity"] == {"resolved_path": plan["binary"], "sha256": plan["binary_sha256"]}, "loaded_artifact_changed")
    require(bool(actual["loaded_source_sha256"]) and all(plan["source_sha256"].get(p) == h
        for p, h in actual["loaded_source_sha256"].items()), "loaded_source_changed")
    require(actual["loaded_source_sha256"].get(str(TEST)) == plan["source_sha256"][str(TEST)], "test_module_not_loaded")


def verify_saved_semantic_gate(reference, *, expected_binary_sha256=BINARY_SHA):
    path = Path(reference["path"]); require(sha(path) == reference["sha256"], "receipt_changed")
    directory, receipt = path.parent, read(path)
    require(receipt["schema"] == SCHEMA and receipt["status"] == "passed", "gate_not_passed")
    for name in ("plan.json", "process.json", "worker.json", "tests.xml"):
        require(sha(directory / name) == receipt["evidence_sha256"][name], "evidence_changed:" + name)
    plan = read(directory / "plan.json"); check_plan(directory, plan)
    require(plan["binary_sha256"] == expected_binary_sha256, "wrong_requested_binary")
    process, actual = read(directory / "process.json"), read(directory / "worker.json")
    require(process["status"] == "exited" and process["exit_code"] == actual["exit_code"] == 0, "worker_not_successful")
    require(process["command"] == [plan["interpreter"], "-m", MODULE, "--output", str(directory.resolve()), "--worker"], "wrong_process")
    validate_worker(plan, actual)
    names = validate_xml(directory / "tests.xml")
    require(receipt["passed_test_names"] == names, "recorded_tests_changed")
    return {"status": "validated_native027_finite_semantic_regression", "passed": len(names),
        "binary_sha256": expected_binary_sha256, "native_model_protection_certified": False,
        "complete_request_100ms_certified": False}


def execute(directory, plan):
    check_plan(directory, plan)
    command = [plan["interpreter"], "-m", MODULE, "--output", str(directory.resolve()), "--worker"]
    process = {"command": command, "status": "launch_failed", "exit_code": None}
    started = time.perf_counter()
    try:
        with (directory / "stdout.txt").open("x") as stdout, (directory / "stderr.txt").open("x") as stderr:
            result = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=plan["timeout_seconds"], check=False)
        process.update(status="exited", exit_code=result.returncode)
    except subprocess.TimeoutExpired: process["status"] = "timeout"
    except OSError as error: process["error"] = str(error)
    process["wall_seconds"] = time.perf_counter() - started; write(directory / "process.json", process)
    receipt = {"schema": SCHEMA, "status": "failed_or_unknown", "passed_test_names": [], "evidence_sha256": {}}
    try:
        require(process["status"] == "exited" and process["exit_code"] == 0, "worker_failed")
        check_plan(directory, plan)
        receipt["passed_test_names"] = validate_xml(directory / "tests.xml")
        receipt["evidence_sha256"] = {name: sha(directory / name) for name in ("plan.json", "process.json", "worker.json", "tests.xml")}
        actual = read(directory / "worker.json")
        validate_worker(plan, actual)
        receipt["status"] = "passed"
    except (ValueError, KeyError, TypeError, OSError, ET.ParseError) as error: receipt["error"] = str(error)
    path = directory / "receipt.json"; write(path, receipt)
    if receipt["status"] == "passed":
        verified = verify_saved_semantic_gate({"path": str(path), "sha256": sha(path)})
        write(directory / "independent_verification.json", verified)
        return 0
    return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--binary", type=Path); parser.add_argument("--build-receipt", type=Path)
    parser.add_argument("--execute", action="store_true"); parser.add_argument("--worker", action="store_true")
    args = parser.parse_args(); directory = args.output.resolve()
    if args.worker: return worker(directory)
    plan = prepare(directory, args.binary, args.build_receipt)
    return execute(directory, plan) if args.execute else 0


if __name__ == "__main__": sys.exit(main())
