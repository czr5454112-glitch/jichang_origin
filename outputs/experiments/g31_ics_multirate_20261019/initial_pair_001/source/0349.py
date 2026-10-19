"""Independent first eligibility wakeup; unchanged route guards and transport.

The new controller call ends at a deadline derived inside the admitted root
from its first fresh public view. Native responses are never rewritten.
"""
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

old, ROOT, OUT = base.old, base.ROOT, base.OUT
SCHEMA = "g31.original_caller_route_update_eligibility.v1"
CASES, JOB, ADMISSION, HORIZON = base.CASES, base.JOB, base.ADMISSION, base.HORIZON
PARENT_SECONDS, ROOT_ID, ENDPOINTS = base.PARENT_SECONDS, base.ROOT_ID, base.ENDPOINTS
ServiceTape, Boundary, invoke_root = base.ServiceTape, base.Boundary, base.invoke_root
case_input, require, child = base.case_input, base.require, base.child
BASE_SHA = "43ddfc061084d8228b56f23ee19b90ba6197a17b52edc41a8f2d9d7c987c5a8e"
REFERENCE = OUT / "original_route_update_prepare_001"
REFERENCE_RECEIPT_SHA = "fbba7fb2f1c9358ffbe8c2d7982c2152ae2bf325467e26c8fe7f45e435a453d7"


def contract():
    result = deepcopy(base.contract()); result["schema"] = SCHEMA
    result["scheduling_amendment"] = {
        "first_wakeup": "After initial root-local fresh observation, use first candidate observation time plus unchanged2s wire plus source service. Re-observe and apply ALL existing guards at the resulting complete native boundary; time alone never authorizes a command.",
        "implementation": "Call unchanged event controller with that one extra real horizon, preserving its exact returned state/start/periodic phase/pending owners. Record actual target and every native response. After this horizon use9900 as before. No rewritten horizon_reached or invented notice.",
        "fallback": "No initial qualifying candidate means no added horizon. Lost identity/full receiver/no qualifying candidate at first wake remains under original60s polling and native notice rules. One immutable route request and60s retries remain unchanged.",
        "timing": "Root still starts9600 before fresh observation. Full warm/cold envelopes and all extra result/shard/codec costs retained. This changes causal request scheduling, so post-submission physical tapes need not equal the earlier60s version. No predicted100ms result."}
    return result


def eligibility_deadline(first_at, service):
    require(type(first_at) in (int, float) and type(service) in (int, float)
        and math.isfinite(first_at) and math.isfinite(service) and first_at >= 0 and service >= 0,
        "eligibility_invalid_time")
    duration = old.WIRE + service
    due = first_at + duration
    # Preserve the existing subtraction guard despite floating-point rounding.
    if due-first_at < duration: due = math.nextafter(due, math.inf)
    require(math.isfinite(due) and due > first_at and due-first_at >= duration, "eligibility_invalid_deadline")
    return due


class RouteUpdate(base.RouteUpdate):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.eligibility_schedule = None
        self._initial_service = None

    def _view(self, initial):
        view = super()._view(initial)
        if initial:
            # This is the actual root's fresh view, not a prior prefix cache.
            values = [r[2] for r in view["node_records"] if r[0] == 112]
            require(len(values) == 1, "eligibility_source_service_coverage")
            self._initial_service = values[0]
        return view

    def _step(self, *, initial):
        if not initial and self.eligibility_schedule is not None and self.eligibility_schedule["fired_at"] is None:
            require(self.session.physical_time >= min(self.eligibility_schedule["deadline"], HORIZON),
                "eligibility_early_second_observation")
        super()._step(initial=initial)
        if initial and self.intent.candidates:
            first = min(row["at"] for row in self.intent.candidates.values())
            due = eligibility_deadline(first, self._initial_service)
            self.eligibility_schedule = {"first_observed_at": first, "source_service_seconds": self._initial_service,
                "wire_seconds": old.WIRE, "deadline": due, "fired_at": None,
                "source": "initial_admitted_root_fresh_view", "initial_candidate_count": len(self.intent.candidates)}
            self.next_probe = min(due, HORIZON)
            self.steps[-1]["next_probe"] = self.next_probe
        elif self.eligibility_schedule is not None and self.eligibility_schedule["fired_at"] is None:
            self.eligibility_schedule["fired_at"] = self.session.physical_time

    def snapshot(self):
        return {**super().snapshot(), "eligibility_schedule": deepcopy(self.eligibility_schedule)}


def initial_warm_target(update):
    schedule = update.eligibility_schedule
    return min(HORIZON, schedule["deadline"]) if schedule is not None else HORIZON


def source_paths():
    # Base has an exact transitive closure, including its original verifier and
    # tests. The new three files import only that closure and Python stdlib.
    return sorted(set(base.source_paths()) | {Path(__file__).resolve(),
        Path(__file__).with_name("verify_original_route_update_eligibility.py").resolve(),
        ROOT / "tests/test_g31_circulation_original_route_update_eligibility.py"})


def prepare(output):
    require(old.sha(base.__file__) == BASE_SHA, "eligibility_base_changed")
    original_receipt = old.read(REFERENCE / "receipt.json")
    require(old.sha(REFERENCE / "receipt.json") == REFERENCE_RECEIPT_SHA
        and original_receipt["status"] == "completed_finite_probe" and original_receipt["source_changed"] == [],
        "eligibility_reference_not_accepted")
    plan = base.prepare(output)
    plan.update(schema=SCHEMA, contract=contract(), baseline_reference=str(REFERENCE),
        rule="Original caller root at9600; one additional true controller horizon from first fresh public service bound; unchanged physical candidate guards.")
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
        part = old.run_event_protocol_control(session, owners, horizon=horizon, control_period=60., command_delay=2.,
            publication_delay=.5, retry_period=60., lease_seconds=120., routes=False, forecasts=True,
            predictive=True, prebalance=True, event_budget=100000,
            max_activations=min(500, old.MAX_ACTIVATIONS-activations), state=state, _consume_state=True)
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
        target = initial_warm_target(update)
        while not update.closed and activations < old.MAX_ACTIVATIONS:
            status = control(boundary, target)
            if status == "control_budget_exhausted": continue
            if status == "reached" and target < HORIZON:
                require(raw.physical_time == target and state["native_timestamp_complete"], "eligibility_horizon_not_complete")
                target = HORIZON
                continue
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
        command = [sys.executable, "-m", __package__ + ".probe_original_route_update_eligibility", "--output", str(output), "--worker", name]
        result = child(command, output / name / "worker.log", began)
        receipt["cases"][name] = {**result, "command": command}
        if name == next(iter(CASES)) and "parent_child_start_ns" in result:
            receipt["shared_parent_setup_ns"] = result["parent_child_start_ns"]-parent_measured_start_ns
        old.write(output / "receipt.json", receipt)
    command = [sys.executable, "-m", __package__ + ".verify_original_route_update_eligibility", "--output", str(output), "--write-report"]
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
