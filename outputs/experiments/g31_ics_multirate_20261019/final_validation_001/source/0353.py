"""One spool-only diagnostic-pipeline sample: three faults, shared600s.
Original pendingACK policy and original API invocation remain unchanged.
No native run is authorized by preparation.
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

from . import probe_original_route_update_pending_ack as reference
from . import probe_original_route_update_internal_deadline as policy
from .spooled_service_tape import SpoolServiceTape, unchanged_invocation_proof, MAX_BYTES, MAX_ROWS
from .route_update_pending_ack import PendingAckRouteUpdate, prove_unchanged_closure_tail

old, ROOT, OUT = policy.old, policy.ROOT, policy.OUT
CASES, JOB, ROOT_ID = policy.CASES, policy.JOB, policy.ROOT_ID
ADMISSION, HORIZON, ENDPOINTS = policy.ADMISSION, policy.HORIZON, policy.ENDPOINTS
PARENT_SECONDS = 600.
SCHEMA = "g31.original_route_spool.v1"
MODULE = "scripts.experiments.g31_ics_circulation.probe_original_route_update_spool"
RouteUpdate = PendingAckRouteUpdate
require = policy.require
REFERENCE = OUT / "original_route_pending_ack_prepare_001"
REFERENCE_RECEIPT_SHA = "3e362645d8074b6e21c4bf49418ebdf14aaf7995327391e00ebc45cbcfd9ed9b"
_SOURCE_CACHE = None


def contract():
    return {"schema": SCHEMA, "cases": CASES, "native_sessions": 3, "admission": ADMISSION,
        "horizon": HORIZON, "shared_parent_seconds": PARENT_SECONDS,
        "mode": "spool_only", "max_bytes": MAX_BYTES, "max_rows": MAX_ROWS,
        "input": "Same complete28506-job/22-tray authorizedR1 research input and three setup-wide ACK factors.",
        "change": "Only diagnostic storage: inherited ServiceTape invocation, JSON/UTF8/write/flush before return; fixed uncompressed spool, gzip level1 on close. No policy change; no RAM arm.",
        "failure": "Sticky unknown on capacity/short write/flush/export; accepted spool prefix retained, partial rejected tail explicitly unknown. Flush is not fsync/powerloss protection.",
        "parity": "Exact request-side saved replay; all API values/order/count, root semantics, requests/retries/ACKs, controller parts and common9900 seal against actual pendingACK reference; only fixed diagnostic clocks excluded.",
        "cost": "JSON/UTF8/flush retained inside warm root. Close compression/hash/export and saved verification retained in complete child/campaign; external launch-to-exit bound separately required.",
        "scope": "One diagnostic-pipeline sample, not algorithmic speedup, unbiased business admission, route maintenance or complete100ms certification."}


def source_paths():
    global _SOURCE_CACHE
    if _SOURCE_CACHE is not None:
        paths, hashes = _SOURCE_CACHE
        require(all(old.sha(path) == digest for path, digest in hashes.items()), "pending_cached_source_changed")
        return paths
    pending = list(reference.source_paths()) + [Path(__file__),
        Path(__file__).with_name("verify_original_route_update_spool.py"),
        Path(__file__).with_name("launch_original_route_update_spool.py"),
        ROOT / "tests/test_g31_circulation_route_spool_campaign.py",
        ROOT / "tests/test_g31_circulation_spooled_service_tape.py",
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
    unchanged_invocation_proof()
    receipt = old.read(REFERENCE / "receipt.json")
    require(receipt["status"] == "completed_finite_pending_ack_cohort" and receipt["source_changed"] == [], "pending_reference_failed")
    reference.verify_pins(REFERENCE, old.read(REFERENCE / "preregistered_protocol.json"))
    pins = reference_pins()
    reference.prepare(output)
    # The existing preparer returns its campaign receipt, while its complete
    # native/input/policy plan is the separately saved canonical document.
    plan = old.read(output / "preregistered_protocol.json")
    plan.update(schema=SCHEMA, candidate_output=str(output.resolve()), spool_contract=contract(), spool_reference=str(REFERENCE),
        spool_reference_pins=pins, source_before={str(path): old.sha(path) for path in source_paths()})
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
    require(plan["schema"] == SCHEMA and plan["spool_contract"] == contract() and
        plan["spool_reference"] == str(REFERENCE) and plan["candidate_output"] == str(output.resolve()), "pending_scope")
    expected = old.read(REFERENCE / "preregistered_protocol.json")
    replaced = {"schema", "source_before", "case_inputs", "candidate_output"}
    require(all(plan.get(key) == value for key, value in expected.items() if key not in replaced), "pending_unchanged_plan")
    require(set(plan["source_before"]) == {str(path) for path in source_paths()}, "pending_source_closure")
    require(plan["spool_reference_pins"] == reference_pins(), "pending_reference_inventory")
    old.verify_pins(output, plan, runtime=runtime)
    require(old.sha(plan["interpreter"]["path"]) == plan["interpreter"]["sha256"], "pending_interpreter")
    data = old.gzread(output / "input.json.gz")
    for case in CASES:
        path = output / case / "input.json.gz"
        require(old.sha(path) == plan["case_inputs"][case] and old.gzread(path) == policy.case_input(data, case), "pending_case_input")
    for field in ("baseline_prefix_pins", "scheduled_reference_pins", "pending_ack_reference_pins", "spool_reference_pins"):
        for path, digest in plan[field].items(): require(old.sha(path) == digest, "pending_evidence_changed")


def inherited_worker():
    environment = {**policy.worker.__globals__, "SCHEMA": SCHEMA, "verify_pins": verify_pins, "RouteUpdate": RouteUpdate, "ServiceTape": SpoolServiceTape}
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
            ("raw.json.gz", "service_tape.jsonl.gz", "service_tape.jsonl.gz.spool.jsonl", "diagnostic_capture.json", "shards.json", "error_prefix.json.gz") if (output / name / artifact).is_file()}
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
    receipt["status"] = "completed_finite_spool_cohort" if all(row.get("exit_code") == 0 for row in receipt["cases"].values()) and receipt["verification"].get("exit_code") == 0 and not receipt["source_changed"] and receipt["wall_seconds"] <= PARENT_SECONDS else "unknown_incomplete_spool_cohort"
    old.write(output / "receipt.json", receipt)
    return 0 if receipt["status"] == "completed_finite_spool_cohort" else 1


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
