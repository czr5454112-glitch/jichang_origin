"""Finite caller-admitted original-map first-hop update; elapsed bounds only.

Job4/epoch9600 deliberately come from the saved waiting112 witness. This is a
witnessed-case diagnostic, not unbiased business admission or route maintenance.
No existing controller, physical rule, native binary or saved experiment changes.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
from copy import deepcopy
import gzip
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

from . import research_original_waiting112 as old
from .business_update_outbox import BusinessUpdateOutbox
from .protocol_control import ProtocolClient

ROOT, OUT = old.ROOT, old.OUTPUTS
SCHEMA = "g31.original_caller_route_update.v1"
CASES = {"baseline": 0, "drop_first_ack": 1, "ack_withheld_in_window": 100}
JOB = "projected:1x:4"
ADMISSION, HORIZON = 9600., 9900.
PARENT_SECONDS = 600.
ROOT_ID = "caller:job4:first-hop:9600"
ENDPOINTS = frozenset(("advance_to", "advance_until_owner_notification", "result_at",
    "observe_protocol", "observe_protocol_control", "observe_protocol_control_policy",
    "observe_protocol_control_policy_recent", "protocol_demand_signature", "protocol_request",
    "protocol_command", "submit_protocol_transfer", "submit_protocol_command"))


def require(ok, why):
    if not ok: raise ValueError("original_route_update:" + why)


def source_paths():
    pending = [Path(__file__), Path(__file__).with_name("verify_original_route_update.py"),
        ROOT / "tests/test_g31_circulation_original_route_update.py"]
    found = set()
    def enqueue(target):
        for p in (target.with_suffix(".py"), target / "__init__.py"):
            if p.is_file() and p.resolve().is_relative_to(ROOT):
                pending.append(p)
                for ancestor in p.parents:
                    if ancestor == ROOT: break
                    if (ancestor / "__init__.py").is_file(): pending.append(ancestor / "__init__.py")
    while pending:
        p = pending.pop().resolve()
        if p in found: continue
        require(p.is_file(), "source_missing")
        found.add(p)
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8-sig"))):
            if isinstance(node, ast.ImportFrom):
                for base in ([p.parent] if node.level else [ROOT, ROOT / "src"]):
                    for _ in range(max(node.level - 1, 0)): base = base.parent
                    if node.module: base = base.joinpath(*node.module.split(".")); enqueue(base)
                    for alias in node.names:
                        if alias.name != "*": enqueue(base / alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    for base in (ROOT, ROOT / "src"): enqueue(base.joinpath(*alias.name.split(".")))
    return sorted(found)


def case_input(base, name):
    require(name in CASES, "undeclared_case")
    old.verify_input(base)
    require(base["owner_protocol"]["drop_ack_packets"] == 0, "base_ack_factor_changed")
    result = deepcopy(base)
    result["owner_protocol"]["drop_ack_packets"] = CASES[name]
    return result


def contract():
    return {"schema": SCHEMA, "cases": CASES, "job": JOB, "admission": ADMISSION, "horizon": HORIZON,
        "parent_seconds": PARENT_SECONDS, "roots_per_case": 1, "max_new_physical_requests_per_root": 1,
        "research_domain": "All28506 original jobs/22trays with explicitly authorized suffix-reroute input; original permission-false input is not changed.",
        "selection": "Job4 and epoch9600 preregistered from previous waiting112 witness; finite witnessed-case regression, not unbiased original business arrivals.",
        "admission_rule": "Caller root admitted before first request-specific fresh view/candidate. Ordinary background R2 prefix cannot supply a cached decision view.",
        "completion": "Actual delivered terminal ACK plus first actual next-hop evidence for an updated preference; delivered rejection is finite failure. Updated ACK alone or future reservation alone cannot close. Full same-timestamp drain and response codec required.",
        "finite_scope": "One first-hop diversion attempt. No continuing route-maintenance service is promised; retry retains same immutable ID/root. No proactive replan/renewal occurs. Future maintenance is outside this declared finite contract, not implicitly certified.",
        "censor": "At9900 missing ACK/no observed hop/no qualifying state remains open. Submission-only rejection without delivered terminal ACK is unknown.",
        "fault_scope": "Drop count applies natively per immutable request to ALL requests from setup, including background R2; prefix differences retained without outcome screening.",
        "timing": "Whole warm root lifetime including all intervening controller/native work, queries, validations, retries, drain, codec and evidence writes. Child-cold starts at actual parent subprocess launch, including child startup/import and complete prefix. Measured parent setup is charged fully to each root; parent startup/import before module instrumentation remains unknown without an external launch receipt. Whole observed child/campaign wall retained. Elapsed bounds, not exclusive compute or100ms certification.",
        "native_phase_instrumentation": False, "complete_100ms_certified": False}


class ServiceTape:
    """All warm native calls, streamed losslessly; setup uses returned raw shards."""
    def __init__(self, native):
        self.native, self.count, self.role_name = native, 0, "controller"
        self.stream = None
    @property
    def physical_time(self): return self.native.physical_time
    def begin(self, path): self.stream = gzip.open(path, "wt", encoding="utf8", compresslevel=1)
    def close(self):
        if self.stream is not None: self.stream.close(); self.stream = None
    @contextmanager
    def role(self, name):
        prior = self.role_name; self.role_name = name
        try: yield
        finally: self.role_name = prior
    def __getattr__(self, name):
        require(name in ENDPOINTS, "unclassified_native_endpoint:" + name)
        def invoke(*args, **kwargs):
            if self.stream is None: return getattr(self.native, name)(*args, **kwargs)
            row = {"ordinal": self.count, "endpoint": name, "role": self.role_name,
                "args": deepcopy(list(args)), "kwargs": deepcopy(kwargs),
                "before": self.physical_time, "start_ns": time.perf_counter_ns()}
            self.count += 1
            try:
                result = getattr(self.native, name)(*args, **kwargs)
                row["result"] = result
                return result
            except BaseException as error:
                row["error"] = repr(error); raise
            finally:
                row.update(after=self.physical_time, end_ns=time.perf_counter_ns())
                # Encoding occurs before returning the native object to a caller
                # that may annotate it. No mutable result escapes before capture.
                self.stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                self.stream.flush()
        return invoke
    def observe_protocol_control_policy(self, owner): return self.__getattr__("observe_protocol_control_policy")(owner)
    def observe_protocol_control_policy_recent(self, owner, validity):
        return self.__getattr__("observe_protocol_control_policy_recent")(owner, validity)


class SubmissionBridge:
    """WaitingIntent proposes; actual exclusive bridge binds the caller's job."""
    def __init__(self, bridge): self.bridge = bridge
    @property
    def state(self): return self.bridge.client.state
    def submit(self, owner, kind, payload, *, request_id):
        require(owner == self.bridge.owner and kind == "route" and payload["business_bag_id"] == JOB,
            "candidate_outside_admitted_job")
        return self.bridge.submit(ROOT_ID, kind, payload, required_terminal_statuses=("updated",))


class RouteUpdate:
    def __init__(self, session, owner, *, clock=time.perf_counter_ns):
        self.session, self.owner, self._clock = session, owner, clock
        self.clock_trace, self.steps = [], []
        self.intent, self.client, self.bridge = old.WaitingIntent(), None, None
        self.started_ns = self.returned_ns = self.censored_ns = None
        self.returned = None
        self.next_probe = ADMISSION
    def clock(self):
        value = self._clock(); self.clock_trace.append(value); return value
    @property
    def closed(self): return self.returned_ns is not None
    def _view(self, initial):
        view = self.bridge.observe(ROOT_ID, compact=False) if initial else self.client.view(self.owner, compact=False)
        require(view["owner_id"] == self.owner and view["now"] == self.session.physical_time,
            "foreign_or_stale_view")
        # Exact received public view remains on the API tape. Only the tray
        # candidate list is restricted to the explicitly admitted business job.
        selected = deepcopy(view)
        selected["trays"] = [t for t in selected["trays"] if t["business_bag_id"] == JOB]
        return selected
    def start(self):
        require(self.started_ns is None and self.session.physical_time == ADMISSION, "admission_epoch")
        self.started_ns = self.clock()
        self.client = ProtocolClient(self.session, retry_period=60.)
        self.bridge = BusinessUpdateOutbox(self.client, self.owner, clock=self.clock)
        self.bridge.admit(ROOT_ID, business_job_id=JOB, trigger_id="preregistered:job4:9600",
            trigger_kind="explicit_witnessed_application_offer",
            completion_contract={"kind": "one_shot_update", "goal_id": "first_hop_or_delivered_failure",
                "terminal_failure_allowed": True})
        self._step(initial=True)
    def step(self):
        require(self.started_ns is not None and not self.closed and self.censored_ns is None, "step_outside_root")
        self._step(initial=False)
    def _step(self, *, initial):
        now = self.session.physical_time
        require(ADMISSION <= now <= HORIZON, "step_outside_window")
        if not initial: self.bridge.refresh()
        view = self._view(initial)
        self.intent.observe(view, SubmissionBridge(self.bridge))
        self.next_probe = now + 60.
        disposition = None
        if self.intent.status == "updated_ack_and_actual_edge": disposition = "completed"
        elif self.intent.status in {"delivered_rejection", "updated_but_other_edge"}: disposition = "terminal_failure"
        if disposition is not None:
            response = {"root": ROOT_ID, "job": JOB, "disposition": disposition, "intent": self.intent.snapshot()}
            returned = self.bridge.finish(ROOT_ID, response, disposition=disposition,
                classification_complete=True, event_budget=100000)
            if returned["status"] == "returned":
                self.returned = json.dumps(returned, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
                self.returned_ns = self.clock()
        self.steps.append({"at": now, "initial": initial, "status": self.intent.status,
            "closed": self.closed, "next_probe": self.next_probe})
    def censor(self):
        require(not self.closed and self.censored_ns is None, "censor_closed_or_twice")
        self.censored_ns = self.clock()
    def snapshot(self):
        return {"owner": self.owner, "root": ROOT_ID, "job": JOB, "started_ns": self.started_ns,
            "returned_ns": self.returned_ns, "censored_ns": self.censored_ns, "returned": self.returned,
            "clock_trace": self.clock_trace, "steps": self.steps, "intent": self.intent.snapshot(),
            "client_state": self.client.state, "client_calls": self.client.calls,
            "lineage": self.bridge.lineage.roots, "protocol_lineage": self.bridge.lineage.protocol,
            "report": self.bridge.report(ROOT_ID)}


def invoke_root(update, tape, events, initial=False):
    start = tape.count
    at = tape.physical_time
    with tape.role("request"):
        update.start() if initial else update.step()
    events.append({"at": at, "initial": initial, "first_api": start, "after_api": tape.count})


class Boundary:
    def __init__(self, tape, update, events): self.tape, self.update, self.events = tape, update, events
    @property
    def physical_time(self): return self.tape.physical_time
    def __getattr__(self, name): return getattr(self.tape, name)
    def observe_protocol_control_policy(self, owner): return self.tape.observe_protocol_control_policy(owner)
    def observe_protocol_control_policy_recent(self, owner, validity): return self.tape.observe_protocol_control_policy_recent(owner, validity)
    def advance_until_owner_notification(self, owners, after, horizon, *, max_events):
        result = self.tape.advance_until_owner_notification(owners, after, horizon, max_events=max_events)
        u = self.update; now = self.physical_time
        if (not u.closed and u.censored_ns is None and result.get("timestamp_complete") is True and
            (now >= u.next_probe or u.intent.decision is not None and u.owner in result.get("notifications", {}))):
            invoke_root(u, self.tape, self.events)
        return result


def prepare(output):
    # This creates a NEW package. The waiting112 input/build/acceptance authority
    # is reused without modifying any prior artifact or current compiled source.
    plan = old.prepare(output, OUT / "original_tie_streamed_native_002",
        ROOT / "build_lt_session_026/python/czr005_circulation.cp311-win_amd64.pyd", PARENT_SECONDS)
    plan.update(schema=SCHEMA, contract=contract(), cases=CASES, status="prepared_native_unexecuted",
        horizon=HORIZON, admission=ADMISSION, native_branch_budget=len(CASES),
        rule="Explicit caller job4 at9600 before fresh request observation; inherited two-current-view waiting112 guards restricted to this job.",
        completion=contract()["completion"], stop="First returned controller shard after root completion, otherwise9900 or bounded budget; missingACK/nohop staysopen.")
    for source in source_paths():
        target = output / "source_archive" / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, target)
        plan["source_before"][str(source)] = old.sha(source)
    base = old.gzread(output / "input.json.gz")
    plan["case_inputs"] = {}
    for name in CASES:
        directory = output / name; directory.mkdir()
        old.gzwrite(directory / "input.json.gz", case_input(base, name))
        plan["case_inputs"][name] = old.sha(directory / "input.json.gz")
    plan["interpreter"] = {"path": sys.executable, "sha256": old.sha(sys.executable)}
    old.write(output / "preregistered_protocol.json", plan)
    old.write(output / "branch_ledger.json", {name: {"status": "unknown_unexecuted"} for name in CASES})
    return plan


def verify_pins(output, plan, *, runtime=False):
    require(plan["schema"] == SCHEMA and plan["contract"] == contract() and plan["cases"] == CASES and
        plan["horizon"] == HORIZON and plan["admission"] == ADMISSION and plan["native_branch_budget"] == len(CASES), "plan_changed")
    old.verify_pins(output, plan, runtime=runtime)
    require(old.sha(plan["interpreter"]["path"]) == plan["interpreter"]["sha256"], "interpreter_changed")
    base = old.gzread(output / "input.json.gz")
    for name in CASES:
        path = output / name / "input.json.gz"
        require(old.sha(path) == plan["case_inputs"][name] and old.gzread(path) == case_input(base, name), "case_input_changed")


def worker(output, name):
    started_ns = time.perf_counter_ns()
    plan = old.read(output / "preregistered_protocol.json"); verify_pins(output, plan)
    require(name in CASES, "worker_case")
    directory = output / name
    with (directory / "worker_claim.json").open("x", encoding="utf8") as f: json.dump({"case": name}, f)
    data = old.gzread(directory / "input.json.gz")
    native = old.load_native(plan["native_binary"])
    raw = native.NativeSession(data)
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
        activations += len(part["control_records"])
        state = part["controller_state"]
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
        update = RouteUpdate(tape, plan["source_owner"])
        invoke_root(update, tape, events, initial=True)
        boundary = Boundary(tape, update, events)
        while not update.closed and activations < old.MAX_ACTIVATIONS:
            status = control(boundary, HORIZON)
            if status != "control_budget_exhausted": break
        if not update.closed: update.censor()
        tape.close()
        verify_pins(output, plan, runtime=True)
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


def child(command, log, began):
    remaining = PARENT_SECONDS - (time.perf_counter() - began)
    if remaining <= 0: return {"status": "unknown_parent_budget", "exit_code": None}
    child_started_ns = time.perf_counter_ns()
    with log.open("wb") as stream:
        try:
            value = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=remaining)
            result = {"status": "child_finished" if value.returncode == 0 else "unknown_child_failure",
                "exit_code": value.returncode, "allowed_seconds": remaining}
        except subprocess.TimeoutExpired:
            result = {"status": "unknown_hard_timeout", "exit_code": None, "allowed_seconds": remaining}
    child_finished_ns = time.perf_counter_ns()
    return {**result, "parent_child_start_ns": child_started_ns, "parent_child_end_ns": child_finished_ns,
        "whole_child_wall_seconds": (child_finished_ns-child_started_ns)/1e9}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--prepare", action="store_true")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--worker", choices=tuple(CASES))
    args = p.parse_args(); output = args.output.resolve()
    if args.prepare: prepare(output); print("prepared_native_unexecuted"); return
    if args.worker: worker(output, args.worker); return
    require(args.execute, "explicit_mode_required")
    began = time.perf_counter(); parent_measured_start_ns = time.perf_counter_ns()
    plan = old.read(output / "preregistered_protocol.json"); verify_pins(output, plan)
    require(all(not (output / name / artifact).exists() for name in CASES
        for artifact in ("worker_claim.json", "raw.json.gz", "error_prefix.json.gz", "segments")), "case_already_attempted")
    with (output / "execution_claim.json").open("x", encoding="utf8") as f: json.dump({"plan_sha256": old.sha(output / "preregistered_protocol.json")}, f)
    receipt = {"schema": SCHEMA, "status": "running", "plan_sha256": old.sha(output / "preregistered_protocol.json"),
        "parent_measured_start_ns": parent_measured_start_ns,
        "unmeasured_parent_startup_imports": True,
        "cases": {name: {"status": "unknown_unexecuted"} for name in CASES}}
    old.write(output / "receipt.json", receipt)
    for name in CASES:
        command = [sys.executable, "-m", __package__ + ".probe_original_route_update", "--output", str(output), "--worker", name]
        result = child(command, output / name / "worker.log", began)
        receipt["cases"][name] = {**result, "command": command}
        if name == next(iter(CASES)) and "parent_child_start_ns" in result:
            receipt["shared_parent_setup_ns"] = result["parent_child_start_ns"]-parent_measured_start_ns
        old.write(output / "receipt.json", receipt)
    command = [sys.executable, "-m", __package__ + ".verify_original_route_update", "--output", str(output), "--write-report"]
    receipt["verification"] = {**child(command, output / "verification.log", began), "command": command}
    receipt["wall_seconds"] = time.perf_counter()-began
    receipt["parent_measured_end_ns"] = time.perf_counter_ns()
    receipt["source_changed"] = []
    try: verify_pins(output, plan)
    except BaseException as error: receipt["source_changed"] = [repr(error)]
    receipt["status"] = "completed_finite_probe" if (all(row["exit_code"] == 0 for row in receipt["cases"].values())
        and receipt["verification"]["exit_code"] == 0 and not receipt["source_changed"]
        and time.perf_counter()-began <= PARENT_SECONDS) else "unknown_incomplete_campaign"
    receipt["wall_seconds"] = time.perf_counter()-began
    old.write(output / "receipt.json", receipt)
    old.write(output / "branch_ledger.json", receipt["cases"])
    print(json.dumps({"status": receipt["status"], "wall_seconds": receipt["wall_seconds"]}))
    if receipt["status"] != "completed_finite_probe": raise SystemExit(1)


if __name__ == "__main__": main()
