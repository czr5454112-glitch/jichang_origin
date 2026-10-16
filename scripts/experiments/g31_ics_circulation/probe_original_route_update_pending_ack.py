"""Three bounded actual candidates: stop full reads after witnessed first hop.

The unchanged internal-deadline worker is instantiated with private globals.
Only the explicitly declared request policy variant changes; the background,
native binary, input, retry, final horizon, and evidence writer remain intact.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
from types import FunctionType

from . import probe_original_route_update_internal_deadline as policy
from .route_update_pending_ack import PendingAckRouteUpdate, prove_unchanged_closure_tail

old, ROOT, OUT = policy.old, policy.ROOT, policy.OUT
CASES, JOB, ROOT_ID = policy.CASES, policy.JOB, policy.ROOT_ID
ADMISSION, HORIZON, ENDPOINTS = policy.ADMISSION, policy.HORIZON, policy.ENDPOINTS
PARENT_SECONDS = 600.
SCHEMA = "g31.original_route_pending_ack.v1"
MODULE = "scripts.experiments.g31_ics_circulation.probe_original_route_update_pending_ack"
RouteUpdate = PendingAckRouteUpdate
require = policy.require
REFERENCE = OUT / "original_route_internal_deadline_prepare_001"
REFERENCE_RECEIPT_SHA = "a233e312208304089fdbdf22e17db845c7d7917d214f38d39c1e501de60fd7ff"
_SOURCE_CACHE = None


def contract():
    return {"schema": SCHEMA, "cases": CASES, "native_sessions": 3, "admission": ADMISSION,
        "horizon": HORIZON, "shared_parent_seconds": PARENT_SECONDS,
        "input": "Same complete28506-job/22-tray authorizedR1 research input and all three setup-wide ACK factors.",
        "change": "After this instance records actual first-hop proof through its original fresh full view, use actual refresh/ACK queries/retry while omitting subsequent full views. Preserve immutable request, actual delivered ACK, rejection/failure, same-time drain and codec. No buffered writer change.",
        "diagnostics": ["intent.last_now", "intent.observation_count", "intent.reservation", "their copies in encoded return", "new pending_ack_path counters/proof"],
        "chronology": "Later ACK must bind to its actual protocol_command response and corresponding request step; never freshen last physical observation time.",
        "parity": "Exact original pre-admission prefix; all warm API rows/order/values except declared postproof full observe reads and fixed diagnostic clocks; exact requests/retries/ACKs/steps/physical proof/background controller parts and common9900 producer seal. New candidate native execution required.",
        "scope": "Finite witnessed job4 first-hop request, not unbiased admission, route maintenance or full business completion. Root admitted before first fresh view at9600. Warm/cold full costs retained; no100ms prediction."}


def source_paths():
    global _SOURCE_CACHE
    if _SOURCE_CACHE is not None:
        paths, hashes = _SOURCE_CACHE
        require(all(old.sha(path) == digest for path, digest in hashes.items()), "pending_cached_source_changed")
        return paths
    pending = list(policy.source_paths()) + [Path(__file__),
        Path(__file__).with_name("verify_original_route_update_pending_ack.py"),
        Path(__file__).with_name("launch_original_route_update_pending_ack.py"),
        ROOT / "tests/test_g31_circulation_route_pending_ack_campaign.py",
        ROOT / "tests/test_g31_circulation_pending_ack_evidence.py",
        ROOT / "tests/test_g31_circulation_route_pending_ack.py"]
    found = {}
    def enqueue(target):
        for item in (target.with_suffix(".py"), target / "__init__.py"):
            if item.is_file() and item.resolve().is_relative_to(ROOT):
                pending.append(item)
                for ancestor in item.parents:
                    if ancestor == ROOT: break
                    if (ancestor / "__init__.py").is_file(): pending.append(ancestor / "__init__.py")
    while pending:
        path = pending.pop().resolve()
        if path in found: continue
        source = path.read_bytes(); found[path] = hashlib.sha256(source).hexdigest()
        for node in ast.walk(ast.parse(source.decode("utf8"))):
            if isinstance(node, ast.ImportFrom):
                for base in ([path.parent] if node.level else [ROOT, ROOT / "src"]):
                    for _ in range(max(0, node.level - 1)): base = base.parent
                    if node.module: base = base.joinpath(*node.module.split(".")); enqueue(base)
                    for alias in node.names:
                        if alias.name != "*": enqueue(base / alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    for base in (ROOT, ROOT / "src"): enqueue(base.joinpath(*alias.name.split(".")))
    require(all(old.sha(path) == digest for path, digest in found.items()), "pending_source_changed_during_parse")
    _SOURCE_CACHE = tuple(sorted(found)), found
    return _SOURCE_CACHE[0]


def reference_pins():
    require(old.sha(REFERENCE / "receipt.json") == REFERENCE_RECEIPT_SHA, "pending_reference_authority")
    pins = {str(REFERENCE / name): old.sha(REFERENCE / name) for name in
        ("receipt.json", "preregistered_protocol.json", "independent_verification.json", "external_launch_receipt.json")}
    for case in CASES:
        for name in ("input.json.gz", "raw.json.gz", "service_tape.jsonl.gz", "shards.json"):
            path = REFERENCE / case / name; pins[str(path)] = old.sha(path)
        for row in old.read(REFERENCE / case / "shards.json"):
            path = REFERENCE / case / row["path"]
            require(old.sha(path) == row["sha256"], "pending_reference_shard")
            pins[str(path)] = row["sha256"]
    return pins


def prepare(output):
    require(not output.exists(), "pending_output_exists")
    prove_unchanged_closure_tail()
    receipt = old.read(REFERENCE / "receipt.json")
    require(receipt["status"] == "completed_finite_probe" and receipt["source_changed"] == [], "pending_reference_failed")
    policy.verify_pins(REFERENCE, old.read(REFERENCE / "preregistered_protocol.json"))
    pins = reference_pins()
    plan = policy.prepare(output)
    plan.update(schema=SCHEMA, candidate_output=str(output.resolve()), pending_ack_contract=contract(), pending_ack_reference=str(REFERENCE),
        pending_ack_reference_pins=pins, source_before={str(path): old.sha(path) for path in source_paths()})
    for path, digest in plan["source_before"].items():
        target = output / "source_archive" / Path(path).relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, target)
        require(old.sha(target) == digest, "pending_archive_copy")
    old.write(output / "preregistered_protocol.json", plan)
    campaign = {"schema": SCHEMA, "status": "prepared_native_unexecuted", "contract": contract(),
        "plan_sha256": old.sha(output / "preregistered_protocol.json"), "source_before": plan["source_before"],
        "interpreter": plan["interpreter"]}
    old.write(output / "campaign.json", campaign)
    old.write(output / "branch_ledger.json", {name: {"status": "unknown_unexecuted"} for name in CASES})
    verify_pins(output, plan)
    return campaign


def verify_pins(output, plan, *, runtime=False):
    require(plan["schema"] == SCHEMA and plan["pending_ack_contract"] == contract() and
        plan["pending_ack_reference"] == str(REFERENCE) and plan["candidate_output"] == str(output.resolve()), "pending_scope")
    expected = old.read(REFERENCE / "preregistered_protocol.json")
    replaced = {"schema", "source_before", "case_inputs"}
    require(all(plan.get(key) == value for key, value in expected.items() if key not in replaced), "pending_unchanged_plan")
    require(set(plan["source_before"]) == {str(path) for path in source_paths()}, "pending_source_closure")
    require(plan["pending_ack_reference_pins"] == reference_pins(), "pending_reference_inventory")
    old.verify_pins(output, plan, runtime=runtime)
    require(old.sha(plan["interpreter"]["path"]) == plan["interpreter"]["sha256"], "pending_interpreter")
    data = old.gzread(output / "input.json.gz")
    for case in CASES:
        path = output / case / "input.json.gz"
        require(old.sha(path) == plan["case_inputs"][case] and old.gzread(path) == policy.case_input(data, case), "pending_case_input")
    for field in ("baseline_prefix_pins", "scheduled_reference_pins", "pending_ack_reference_pins"):
        for path, digest in plan[field].items(): require(old.sha(path) == digest, "pending_evidence_changed")


def inherited_worker():
    environment = {**policy.worker.__globals__, "SCHEMA": SCHEMA, "verify_pins": verify_pins, "RouteUpdate": RouteUpdate}
    return FunctionType(policy.worker.__code__, environment, name="unchanged_internal_worker",
        argdefs=policy.worker.__defaults__, closure=policy.worker.__closure__)


def worker(output, case):
    inherited_worker()(output, case)


def verify_campaign(output):
    campaign = old.read(output / "campaign.json")
    require(campaign["schema"] == SCHEMA and campaign["contract"] == contract() and
        campaign["plan_sha256"] == old.sha(output / "preregistered_protocol.json"), "pending_campaign")
    plan = old.read(output / "preregistered_protocol.json")
    require(campaign["source_before"] == plan["source_before"] and campaign["interpreter"] == plan["interpreter"], "pending_campaign_pins")
    verify_pins(output, plan)
    return campaign


def execute(output, admission):
    require(sys.stdin.readline().rstrip("\n") == admission == old.sha(output / "campaign.json"), "pending_job_admission")
    began = time.perf_counter(); measured = time.perf_counter_ns()
    campaign = verify_campaign(output)
    require(all(not (output / name / artifact).exists() for name in CASES
        for artifact in ("worker_claim.json", "raw.json.gz", "error_prefix.json.gz", "segments")), "pending_preexisting_execution")
    with (output / "execution_claim.json").open("x", encoding="utf8") as stream:
        json.dump({"campaign_sha256": admission}, stream)
    receipt = {"schema": SCHEMA, "status": "running", "campaign_sha256": admission,
        "parent_measured_start_ns": measured, "cases": {name: {"status": "unknown_unexecuted"} for name in CASES}}
    old.write(output / "receipt.json", receipt)
    for name in CASES:
        command = [sys.executable, "-m", MODULE, "--output", str(output), "--worker", name]
        result = policy.child(command, output / name / "worker.log", began)
        result["command"] = command
        result["artifact_sha256"] = {artifact: old.sha(output / name / artifact) for artifact in
            ("raw.json.gz", "service_tape.jsonl.gz", "shards.json", "error_prefix.json.gz") if (output / name / artifact).is_file()}
        receipt["cases"][name] = result
        if name == next(iter(CASES)) and "parent_child_start_ns" in result:
            receipt["shared_parent_setup_ns"] = result["parent_child_start_ns"] - measured
        old.write(output / "receipt.json", receipt); old.write(output / "branch_ledger.json", receipt["cases"])
    command = [sys.executable, "-m", MODULE.replace("probe_", "verify_", 1), "--output", str(output), "--write-report"]
    receipt["verification"] = {**policy.child(command, output / "verification.log", began), "command": command}
    receipt["source_changed"] = []
    try: verify_campaign(output)
    except BaseException as error: receipt["source_changed"].append(repr(error))
    receipt["wall_seconds"] = time.perf_counter() - began
    receipt["parent_measured_end_ns"] = time.perf_counter_ns()
    receipt["status"] = "completed_finite_pending_ack_cohort" if all(row.get("exit_code") == 0 for row in receipt["cases"].values()) and receipt["verification"].get("exit_code") == 0 and not receipt["source_changed"] and receipt["wall_seconds"] <= PARENT_SECONDS else "unknown_incomplete_pending_ack_cohort"
    old.write(output / "receipt.json", receipt)
    return 0 if receipt["status"] == "completed_finite_pending_ack_cohort" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True); parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--worker", choices=tuple(CASES)); parser.add_argument("--campaign", action="store_true")
    parser.add_argument("--admission")
    args = parser.parse_args(); output = args.output.resolve()
    require(sum((args.prepare, args.worker is not None, args.campaign)) == 1, "pending_mode")
    if args.prepare: prepare(output); print("prepared_native_unexecuted")
    elif args.worker: worker(output, args.worker)
    else: raise SystemExit(execute(output, args.admission))


if __name__ == "__main__": main()
