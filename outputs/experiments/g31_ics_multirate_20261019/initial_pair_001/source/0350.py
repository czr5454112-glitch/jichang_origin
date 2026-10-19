"""One true internal public deadline; unchanged eligibility and route semantics."""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import shutil
import sys
import time
import traceback
from . import probe_original_route_update as base
from . import probe_original_route_update_eligibility as eligibility
from . import event_protocol_control_deadline as scheduled

old, ROOT, OUT = base.old, base.ROOT, base.OUT
SCHEMA = "g31.original_caller_route_update_internal_deadline.v1"
CASES, JOB, ADMISSION, HORIZON = base.CASES, base.JOB, base.ADMISSION, base.HORIZON
PARENT_SECONDS, ROOT_ID, ENDPOINTS = base.PARENT_SECONDS, base.ROOT_ID, base.ENDPOINTS
ServiceTape, Boundary, invoke_root = base.ServiceTape, base.Boundary, base.invoke_root
case_input, require, child = base.case_input, base.require, base.child
BASE_SHA = "43ddfc061084d8228b56f23ee19b90ba6197a17b52edc41a8f2d9d7c987c5a8e"
REFERENCE = OUT / "original_route_update_prepare_001"
SCHEDULED_REFERENCE = OUT / "original_route_eligibility_prepare_001"
SCHEDULED_REFERENCE_SHA = "100714347fdb77a2745739d8860b8c0b3746b555ab1ca8a5862ce8350924604f"
REFERENCE_RECEIPT_SHA = "fbba7fb2f1c9358ffbe8c2d7982c2152ae2bf325467e26c8fe7f45e435a453d7"


def contract():
    result = deepcopy(eligibility.contract()); result["schema"] = SCHEMA
    result["internal_deadline_amendment"] = {
        "implementation": "New separate controller copy adds only optional public-deadline hook before native call. Use min of existing scheduler deadline and initial fresh-view eligibility deadline until actual wake fires. Record true native deadline; never rewrite a response. Overall horizon remains9900, so no full result or shard is exported at9603.5.",
        "policy": "Exactly the tested eligibility RouteUpdate and original Boundary. Same root admission9600,2s wire,60s immutable retry and all closure guards. No candidate-view cache or earlier work excluded.",
        "comparison": "All request-side API arguments/results/physical times must equal actual split eligibility001, excluding only outer ordinal/wall stamps and finite advance_to wall_seconds. Diagnostic continuation runs unchanged live R2 to fixed9900 for allthreecases even after root return, so final native seals must match the actual split0019900 endpoints. Failed/censored reaching9900 or differing seals fail this comparison; no endpoint inference.",
        "timing": "All warm work retained, no hypothetical removal of old output cost. Cold whole child/campaign includes new continuation through9900 and complete evidence verification. No100ms prediction or certification."}
    result["scheduling_amendment"]["implementation"] = result["internal_deadline_amendment"]["implementation"]
    return result


RouteUpdate = eligibility.RouteUpdate
eligibility_deadline = eligibility.eligibility_deadline


def public_deadline(update, now):
    if update is None or update.closed or update.censored_ns is not None:
        return None
    schedule = update.eligibility_schedule
    if schedule is None or schedule["fired_at"] is not None:
        return None
    due = min(HORIZON, schedule["deadline"])
    require(now <= due, "internal_public_wakeup_missed")
    return due


def source_paths():
    return sorted(set(eligibility.source_paths()) | {Path(__file__).resolve(), Path(scheduled.__file__).resolve(),
        Path(__file__).with_name("verify_original_route_update_internal_deadline.py").resolve(),
        ROOT / "tests/test_g31_circulation_original_route_update_internal_deadline.py"})


def prepare(output):
    require(old.sha(base.__file__) == BASE_SHA, "eligibility_base_changed")
    original_receipt = old.read(REFERENCE / "receipt.json")
    require(old.sha(REFERENCE / "receipt.json") == REFERENCE_RECEIPT_SHA
        and original_receipt["status"] == "completed_finite_probe" and original_receipt["source_changed"] == [],
        "eligibility_reference_not_accepted")
    plan = base.prepare(output)
    plan.update(schema=SCHEMA, contract=contract(), baseline_reference=str(REFERENCE),
        rule="Original caller root at9600; true internal caller deadline before native call; no intermediate full result; same eligibility policy and final9900 diagnostic continuation.")
    plan["baseline_prefix_pins"] = {}
    for name in ("receipt.json", "preregistered_protocol.json", "independent_verification.json", "external_launch_receipt.json"):
        path = REFERENCE / name; plan["baseline_prefix_pins"][str(path)] = old.sha(path)
    for case in CASES:
        for name in ("input.json.gz", "shards.json"):
            path = REFERENCE / case / name; plan["baseline_prefix_pins"][str(path)] = old.sha(path)
        for row in old.read(REFERENCE / case / "shards.json"):
            if row["target"] == ADMISSION:
                path = REFERENCE / case / row["path"]
                require(old.sha(path) == row["sha256"], "eligibility_reference_prefix_changed")
                plan["baseline_prefix_pins"][str(path)] = row["sha256"]
    require(old.sha(SCHEDULED_REFERENCE / "receipt.json") == SCHEDULED_REFERENCE_SHA, "internal_reference_receipt_changed")
    plan["scheduled_reference"] = str(SCHEDULED_REFERENCE)
    plan["scheduled_reference_pins"] = {}
    for name in ("receipt.json", "preregistered_protocol.json", "independent_verification.json"):
        path = SCHEDULED_REFERENCE / name; plan["scheduled_reference_pins"][str(path)] = old.sha(path)
    for case in CASES:
        for name in ("raw.json.gz", "service_tape.jsonl.gz"):
            path = SCHEDULED_REFERENCE / case / name; plan["scheduled_reference_pins"][str(path)] = old.sha(path)
    for source in source_paths():
        target = output / "source_archive" / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, target)
        plan["source_before"][str(source)] = old.sha(source)
    old.write(output / "preregistered_protocol.json", plan)
    verify_pins(output, plan)
    return plan


def verify_pins(output, plan, *, runtime=False):
    require(old.sha(base.__file__) == BASE_SHA and plan["schema"] == SCHEMA and plan["contract"] == contract()
        and plan["cases"] == CASES and plan["horizon"] == HORIZON and plan["admission"] == ADMISSION
        and plan["native_branch_budget"] == 3 and plan["baseline_reference"] == str(REFERENCE)
        and plan["baseline_prefix_pins"].get(str(REFERENCE / "receipt.json")) == REFERENCE_RECEIPT_SHA,
        "eligibility_scope_changed")
    require(set(plan["source_before"]) == {str(p) for p in source_paths()}, "eligibility_source_closure_changed")
    require(plan["scheduled_reference"] == str(SCHEDULED_REFERENCE)
        and plan["scheduled_reference_pins"].get(str(SCHEDULED_REFERENCE / "receipt.json")) == SCHEDULED_REFERENCE_SHA,
        "internal_reference_changed")
    for path, digest in plan["scheduled_reference_pins"].items(): require(old.sha(path) == digest, "internal_reference_artifact_changed")
    old.verify_pins(output, plan, runtime=runtime)
    require(old.sha(plan["interpreter"]["path"]) == plan["interpreter"]["sha256"], "interpreter_changed")
    data = old.gzread(output / "input.json.gz")
    for name in CASES:
        path = output / name / "input.json.gz"
        require(old.sha(path) == plan["case_inputs"][name] and old.gzread(path) == case_input(data, name), "case_input_changed")
    for path, digest in plan["baseline_prefix_pins"].items(): require(old.sha(path) == digest, "eligibility_baseline_pin_changed")


def worker(output, name):
    started_ns = time.perf_counter_ns()
    plan = old.read(output / "preregistered_protocol.json"); verify_pins(output, plan)
    require(name in CASES, "worker_case")
    directory = output / name
    with (directory / "worker_claim.json").open("x", encoding="utf8") as f: json.dump({"case": name}, f)
    data = old.gzread(directory / "input.json.gz")
    native = old.load_native(plan["native_binary"]); raw = native.NativeSession(data)
    tape = ServiceTape(raw); owners = sorted({n["resource_owner"] for n in data["node_contracts"]})
    state = None; offset = activations = 0; shards = []; events = []; update = None
    (directory / "segments").mkdir()
    def control(session, horizon):
        nonlocal state, offset, activations
        part = scheduled.run_event_protocol_control(session, owners, horizon=horizon, control_period=60., command_delay=2.,
            publication_delay=.5, retry_period=60., lease_seconds=120., routes=False, forecasts=True,
            predictive=True, prebalance=True, event_budget=100000,
            max_activations=min(500, old.MAX_ACTIVATIONS-activations), state=state, _consume_state=True,
            _public_deadline=None if update is None else lambda now: public_deadline(update, now))
        for key in ("control_records", "native_batches"):
            for row in part[key]: row["trace_sequence"] += offset
        offset += len(part["control_records"]) + len(part["native_batches"])
        activations += len(part["control_records"]); state = part["controller_state"]
        path = directory / "segments" / f"{len(shards):04d}.json.gz"
        old.gzwrite(path, part)
        shards.append({"path": str(path.relative_to(directory)), "sha256": old.sha(path),
            "target": horizon, "status": part["status"], "physical_time": raw.physical_time})
        old.write(directory / "shards.json", shards)
        return part["status"]
    try:
        status = "control_budget_exhausted"
        while status == "control_budget_exhausted" and activations < old.MAX_ACTIVATIONS:
            status = control(tape, ADMISSION)
        require(status == "reached" and raw.physical_time == ADMISSION and state["native_timestamp_complete"], "prefix_incomplete")
        tape.begin(directory / "service_tape.jsonl.gz")
        update = RouteUpdate(tape, plan["source_owner"]); invoke_root(update, tape, events, initial=True)
        boundary = Boundary(tape, update, events)
        target = HORIZON
        while activations < old.MAX_ACTIVATIONS:
            status = control(boundary, target)
            if status == "control_budget_exhausted": continue
            break
        if not update.closed: update.censor()
        tape.close(); verify_pins(output, plan, runtime=True)
        result = {"schema": SCHEMA, "case": name, "root": update.snapshot(), "events": events,
            "worker_started_ns": started_ns, "result_capture_before_seal_ns": time.perf_counter_ns(),
            "physical_time": raw.physical_time, "control_status": status, "owner_activations": activations,
            "api_rows": tape.count, "api_sha256": old.sha(directory / "service_tape.jsonl.gz"),
            "shards_sha256": old.sha(directory / "shards.json"), "input_sha256": old.sha(directory / "input.json.gz"),
            "native_state_sha256": raw.offline_state_sha256(), "native_binary_sha256": old.BINARY_SHA,
            "source_changed": [], "complete_100ms_certified": False}
        old.gzwrite(directory / "raw.json.gz", result)
    except BaseException as error:
        tape.close()
        old.gzwrite(directory / "error_prefix.json.gz", {"schema": SCHEMA, "case": name, "error": repr(error),
            "traceback": traceback.format_exc(), "physical_time": raw.physical_time,
            "root": update.snapshot() if update is not None else None, "events": events,
            "api_rows": tape.count, "shards": shards, "native_state_reconstructed": False})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true"); parser.add_argument("--execute", action="store_true")
    parser.add_argument("--worker", choices=tuple(CASES)); args = parser.parse_args(); output = args.output.resolve()
    require(sum((args.prepare, args.execute, args.worker is not None)) == 1, "eligibility_explicit_mode_required")
    if args.prepare: prepare(output); print("prepared_native_unexecuted"); return
    if args.worker: worker(output, args.worker); return
    began = time.perf_counter(); parent_measured_start_ns = time.perf_counter_ns()
    plan = old.read(output / "preregistered_protocol.json"); verify_pins(output, plan)
    require(all(not (output / name / artifact).exists() for name in CASES
        for artifact in ("worker_claim.json", "raw.json.gz", "error_prefix.json.gz", "segments")), "case_already_attempted")
    with (output / "execution_claim.json").open("x", encoding="utf8") as f: json.dump({"plan_sha256": old.sha(output / "preregistered_protocol.json")}, f)
    receipt = {"schema": SCHEMA, "status": "running", "plan_sha256": old.sha(output / "preregistered_protocol.json"),
        "parent_measured_start_ns": parent_measured_start_ns, "unmeasured_parent_startup_imports": True,
        "cases": {name: {"status": "unknown_unexecuted"} for name in CASES}}
    old.write(output / "receipt.json", receipt)
    for name in CASES:
        command = [sys.executable, "-m", __package__ + ".probe_original_route_update_internal_deadline", "--output", str(output), "--worker", name]
        result = child(command, output / name / "worker.log", began)
        receipt["cases"][name] = {**result, "command": command}
        if name == next(iter(CASES)) and "parent_child_start_ns" in result:
            receipt["shared_parent_setup_ns"] = result["parent_child_start_ns"]-parent_measured_start_ns
        old.write(output / "receipt.json", receipt)
    command = [sys.executable, "-m", __package__ + ".verify_original_route_update_internal_deadline", "--output", str(output), "--write-report"]
    receipt["verification"] = {**child(command, output / "verification.log", began), "command": command}
    receipt["wall_seconds"] = time.perf_counter()-began
    receipt["parent_measured_end_ns"] = time.perf_counter_ns(); receipt["source_changed"] = []
    try: verify_pins(output, plan)
    except BaseException as error: receipt["source_changed"] = [repr(error)]
    receipt["status"] = "completed_finite_probe" if (all(row.get("exit_code") == 0 for row in receipt["cases"].values())
        and receipt["verification"]["exit_code"] == 0 and not receipt["source_changed"]
        and time.perf_counter()-began <= PARENT_SECONDS) else "unknown_incomplete_campaign"
    receipt["wall_seconds"] = time.perf_counter()-began
    old.write(output / "receipt.json", receipt); old.write(output / "branch_ledger.json", receipt["cases"])
    print(json.dumps({"status": receipt["status"], "wall_seconds": receipt["wall_seconds"]}))
    if receipt["status"] != "completed_finite_probe": raise SystemExit(1)


if __name__ == "__main__": main()
