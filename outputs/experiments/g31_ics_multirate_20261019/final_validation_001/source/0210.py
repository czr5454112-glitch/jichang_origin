"""Bounded launch of coverage-corrected delivery003; prior002 remains immutable.

Does not prepare, replace, repair or retry a campaign. Native lives only inside
one child process, which subprocess.run kills on the declared hard timeout.
After its exit, the saved evidence is independently re-read without native.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[3]
EXPECTED_PLAN = "6c9914f8870b1971ba8ef3fb009dbf08551240a8853949094205c50bb343f882"
EXPECTED_BINARY = "b024724e3bf0a8e4232eaeb13d99ab6a42018e85e4166acf9081991510ca311b"
WORKER_MODULE = "scripts.experiments.g31_ics_circulation.research_native_preexisting_occupancy"


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def require(value, reason):
    if not value: raise ValueError("prepared_delivery:" + reason)
def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def verify(output, binary, launcher_sha, *, initial):
    require(sha(__file__) == launcher_sha, "launcher_changed")
    require(sha(output/"preregistered_protocol.json") == EXPECTED_PLAN, "plan_changed")
    plan = read(output/"preregistered_protocol.json")
    require(plan["phase"] == "delivery_gate" and plan["native_branch_budget"] == len(plan["rows"]) == 9, "wrong_gate")
    require(sha(binary) == EXPECTED_BINARY, "binary_changed")
    require(Path(sys.executable).resolve() == Path(plan["python_environment"]["executable"]).resolve()
        and sys.version == plan["python_environment"]["version"], "interpreter_changed")
    require(set(plan["source_archive"]) == set(plan["source_sha256"]), "source_archive_denominator")
    for source, digest in plan["source_sha256"].items():
        archive = (output/plan["source_archive"][source]).resolve()
        require(archive.is_relative_to(output/"source") and sha(source) == sha(archive) == digest, "live_or_archive_source_changed")
    require(set(plan["input_file_sha256"]) == set(plan["row_configuration_sha256"]) == set(plan["rows"]), "input_denominator")
    for key in plan["rows"]:
        source = output/"inputs"/(key+".json")
        require(sha(source) == plan["input_file_sha256"][key], "input_file_changed")
        canonical = json.dumps(read(source), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        require(hashlib.sha256(canonical).hexdigest() == plan["row_configuration_sha256"][key], "input_contract_changed")
    if initial:
        require(read(output/"branch_ledger.json") == plan["rows"], "campaign_already_started")
        require(not any((output/name).exists() for name in ("receipt.json", "bounded_parent_receipt.json", "worker_failure.json")), "existing_attempt")
        require(not any(output.glob("*/*.json.gz")), "existing_raw_branch")
    return plan


def launch(output, binary, launcher_sha, timeout):
    require(math.isfinite(timeout) and 0 < timeout <= 180., "timeout_exceeds_preregistered_bound")
    plan = verify(output, binary, launcher_sha, initial=True)
    source_copy = output/"bounded_parent_source.py"
    require(not source_copy.exists(), "existing_parent_archive")
    shutil.copyfile(__file__, source_copy)
    require(sha(source_copy) == launcher_sha, "parent_archive_changed")
    command = [sys.executable, "-m", WORKER_MODULE, "--worker", "--output", str(output),
        "--binary", str(binary), "--expected-binary-sha256", EXPECTED_BINARY]
    receipt = {"schema": "g31.prepared_preexisting_delivery_parent.v1", "status": "running",
        "launcher_sha256": launcher_sha, "plan_sha256": EXPECTED_PLAN, "native_binary_sha256": EXPECTED_BINARY,
        "worker_hard_timeout_seconds": timeout, "native_branch_budget": 9, "command": command,
        "source_scope": "this pinned launcher plus prepared41 project Python sources and pinned interpreter; no new policy import",
        "business_metrics": None, "complete_request_100ms_certified": False}
    write(output/"bounded_parent_receipt.json", receipt); started = time.perf_counter()
    try:
        with (output/"bounded_worker.stdout.log").open("wb") as stdout, (output/"bounded_worker.stderr.log").open("wb") as stderr:
            result = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=timeout)
        receipt["worker_exit_code"] = result.returncode
        require(result.returncode == 0, "worker_failed")
        verify(output, binary, launcher_sha, initial=False)
        # Import after the child exits. This is saved-data validation only and
        # cannot alter that child's already checked module closure or policy.
        runner = importlib.import_module(WORKER_MODULE)
        receipt["independent_saved_evidence"] = runner.require_delivery_gate(output, EXPECTED_BINARY, plan)
        receipt["status"] = "passed_delivery_gate_no_business_run"
    except subprocess.TimeoutExpired:
        receipt["status"] = "unknown_worker_hard_timeout"
    except BaseException as error:
        receipt.update(status="unknown_failed_verification_or_worker", error=repr(error), traceback=traceback.format_exc())
    finally:
        receipt["wall_seconds"] = time.perf_counter()-started
        try:
            verify(output, binary, launcher_sha, initial=False)
            require(sha(source_copy) == launcher_sha, "parent_archive_changed")
            receipt["source_and_input_changed"] = []
        except BaseException as error:
            receipt.update(status="invalidated_identity_drift", identity_error=repr(error))
        write(output/"bounded_parent_receipt.json", receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--expected-launcher-sha256", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=180.)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args(); output, binary = args.output.resolve(), args.binary.resolve()
    if args.check_only:
        verify(output, binary, args.expected_launcher_sha256, initial=True)
        print(json.dumps({"status": "prepared_identity_verified_no_native_calls", "branches": 9, "plan_sha256": EXPECTED_PLAN})); return
    receipt = launch(output, binary, args.expected_launcher_sha256, args.timeout_seconds)
    print(json.dumps({key: receipt[key] for key in ("status", "wall_seconds", "native_branch_budget")}))
    if receipt["status"] != "passed_delivery_gate_no_business_run": raise SystemExit(1)


if __name__ == "__main__": main()
