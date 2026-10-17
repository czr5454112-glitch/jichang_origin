"""One 120-second saved-prefix diagnostic; never a full-day acceptance."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import copy
import hashlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from scripts.experiments.g31_ics_circulation import bounded_windows_job
from scripts.experiments.g31_ics_circulation import bridge_saved_c_digest as routing
from scripts.experiments.g31_ics_circulation import bridge_saved_text_actor as actor
from scripts.experiments.g31_ics_circulation import planning_capture_v2_c_encoder as encoder
from scripts.experiments.g31_ics_circulation import planning_v2_c_encoder_authority as authority
from scripts.experiments.g31_ics_circulation import protocol_control

BASE = ROOT / "outputs/experiments/g31_ics_lt2_sustained_20261014"
ANCHOR = BASE / "bcdm2"
SOURCE = BASE / "original_bridge_serialize_once_prepare_001/bridge"
OLD = BASE / "original_cooperative_bridge_prepare_001/bridge"
LIMIT = 512
SECONDS = 120.0
FROZEN = routing.frozen
ORIGINAL = FROZEN.original
PHYSICAL = FROZEN.base
POLICY = routing.policy


class PrefixCensored(BaseException):
    pass


class UnsupportedBoundary(BaseException):
    pass


class InstrumentationFailure(BaseException):
    pass


def require(value, reason):
    if not value:
        raise ValueError("prefix512:" + reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def startup_environment(source, expected):
    keys = {"PYTHONPATH", "PYTHONHOME", "PYTHONNOUSERSITE", "SETUPTOOLS_USE_DISTUTILS"}
    require(set(expected) == keys, "startup_environment_key_domain")
    result = dict(source)
    for name, value in expected.items():
        if value is None:
            result.pop(name, None)
        else:
            result[name] = value
    result.update(PYTHONIOENCODING="utf-8", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    return result


def invoke_endpoint(tape, profile, name, method, args, kwargs):
    if tape.index == LIMIT:
        profile.mark_censor()
        raise PrefixCensored("before_513th_read")
    if name == "submit_protocol_transfer" and args and args[0]["request_id"].endswith(":single-supply"):
        raise UnsupportedBoundary("first_supply_not_available_from_declared_prefix")
    return method(*args, **kwargs)


class Profile:
    def __init__(self, code_labels, c_labels=None):
        self.codes = code_labels
        self.builtins = c_labels or {}
        self.spans = []
        self.stack = []
        self.censor_at = None
        self.digest_count = 0
        self.error = None

    def mark_censor(self):
        self.censor_at = time.perf_counter_ns()

    def callback(self, frame, event, argument):
        label = self.codes.get(frame.f_code) if event in ("call", "return") else None
        builtin = event in ("c_call", "c_return", "c_exception")
        if builtin:
            label = self.builtins.get(argument)
        if label is None:
            return
        key = (id(frame), id(argument) if builtin else 0)
        now = time.perf_counter_ns()
        if event in ("call", "c_call"):
            if len(self.spans) >= 16384:
                self.error = "span_overflow"
                raise InstrumentationFailure(self.error)
            if label == "complete_digest":
                self.digest_count += 1
                if self.digest_count > 1024:
                    self.error = "digest_overflow"
                    raise InstrumentationFailure(self.error)
            owner = frame.f_locals.get("self")
            owner_values = getattr(owner, "__dict__", {})
            session = owner_values.get("session")
            span = {"id": len(self.spans), "parent": self.stack[-1][1] if self.stack else None,
                    "label": label, "start_ns": now, "end_ns": None,
                    "owner": owner_values.get("owner"),
                    "first_api": getattr(session, "index", None), "child_ns": 0}
            self.spans.append(span)
            self.stack.append((key, span["id"]))
            return
        if not self.stack or self.stack[-1][0] != key:
            self.error = "profile_stack_mismatch"
            raise InstrumentationFailure(self.error)
        _, identity = self.stack.pop()
        span = self.spans[identity]
        span["end_ns"] = now
        span["inclusive_ns"] = now - span["start_ns"]
        span["exclusive_ns"] = span["inclusive_ns"] - span["child_ns"]
        span["outcome"] = "c_exception" if event == "c_exception" else "return_or_unwind"
        if self.censor_at is not None and span["start_ns"] <= self.censor_at <= now:
            span["outcome"] = "interrupted_at_prefix_boundary"
        if span["label"] == "complete_digest":
            span["outcome"] = "returned_digest" if type(argument) is str and len(argument) == 64 else "raised_or_interrupted"
        if self.stack:
            self.spans[self.stack[-1][1]]["child_ns"] += span["inclusive_ns"]

    def report(self):
        require(not self.stack and self.error is None, "profile_unclosed_or_failed")
        totals = {}
        for span in self.spans:
            require(type(span["start_ns"]) is int and type(span["end_ns"]) is int
                    and span["end_ns"] >= span["start_ns"] and span["exclusive_ns"] >= 0,
                    "profile_invalid_clock")
            if span["parent"] is not None:
                parent = self.spans[span["parent"]]
                require(parent["start_ns"] <= span["start_ns"] <= span["end_ns"] <= parent["end_ns"],
                        "profile_containment")
            item = totals.setdefault(span["label"], {"calls": 0, "inclusive_ns": 0, "exclusive_ns": 0})
            item["calls"] += 1
            item["inclusive_ns"] += span["inclusive_ns"]
            item["exclusive_ns"] += span["exclusive_ns"]
        digests = []
        for span in self.spans:
            if span["label"] != "complete_digest":
                continue
            descendants = []
            for child in self.spans[span["id"] + 1:]:
                if child["start_ns"] >= span["end_ns"]:
                    break
                descendants.append(child)
            counts = Counter(child["label"] for child in descendants)
            require(counts["C_try_typed_bytes"] == 1, "one_C_attempt_per_digest")
            require(counts["original_fallback_writer"] <= 1, "fallback_at_most_once")
            digests.append({"span_id": span["id"], "outcome": span["outcome"],
                            "classification": "original_fallback" if counts["original_fallback_writer"] else "direct_C_or_exception",
                            "inclusive_ns": span["inclusive_ns"], "actual_call_counts": dict(counts)})
        return {"spans": self.spans, "totals": totals, "digests": digests,
                "inclusive_exclusive_conservation": True,
                "interpretation": "Instrumented wall time, not CPU or uninstrumented speed; callback/recording overhead remains charged in ancestors or unclassified remainder."}


def prepare(output):
    output.mkdir(parents=True, exist_ok=False)
    anchor = read(ANCHOR / "plan.json")
    original_plan = read(SOURCE / "preregistered_protocol.json")
    bootstrap = Path(original_plan["bootstrap_reference"])
    authority_sources = {Path(name).relative_to(ROOT).as_posix(): expected
                         for name, expected in anchor["source_before"].items()}
    for name, expected in authority_sources.items():
        require(sha(ROOT / name) == sha(ANCHOR / "source" / name) == expected, "frozen_source:" + name)
    authority_sources[Path(__file__).relative_to(ROOT).as_posix()] = sha(__file__)
    pin_paths = [ANCHOR / "plan.json", SOURCE / "preregistered_protocol.json", SOURCE / "input.json.gz",
                 SOURCE / "api/manifest.jsonl", OLD / "api/manifest.jsonl", bootstrap / "api/manifest.jsonl",
                 BASE / "control_timers_bridge_slice_profile_design_001.json"]
    pins = {str(path): sha(path) for path in pin_paths}
    require(pins[str(OLD / "api/manifest.jsonl")] == routing.r.MANIFEST_SHA, "old_complete_manifest")
    selected = {}
    for role, directory, expected_count in (("new", SOURCE / "api", 37270), ("old", OLD / "api", 27218),
                                            ("bootstrap", bootstrap / "api", None)):
        lines = (directory / "manifest.jsonl").read_bytes().splitlines(keepends=True)
        require(len(lines) >= LIMIT and (expected_count is None or len(lines) == expected_count), "manifest_count")
        target = output / role / "api" if role == "bootstrap" else output / role
        target.mkdir(parents=True)
        (target / "manifest.jsonl").write_bytes(b"".join(lines[:LIMIT]))
        rows = []
        for ordinal, line in enumerate(lines[:LIMIT]):
            item = json.loads(line)
            require(item["path"] == f"{ordinal:06d}.json.gz", "selected_ordinal")
            payload = (directory / item["path"]).read_bytes()
            require(hashlib.sha256(payload).hexdigest() == item["sha256"], "selected_hash")
            (target / item["path"]).write_bytes(payload)
            rows.append({**item, "bytes": len(payload)})
        selected[role] = {"source": str(directory), "complete_manifest_sha256": sha(directory / "manifest.jsonl"),
                          "complete_manifest_rows": len(lines), "prefix_manifest_sha256": sha(target / "manifest.jsonl"),
                          "rows": rows}
    plan = {"schema": "g31.bridge.prefix512.instrumented.v1", "rows": LIMIT, "whole_seconds": SECONDS,
            "source_hashes": authority_sources, "input_pins": pins, "prefixes": selected,
            "original_plan": str(SOURCE / "preregistered_protocol.json"),
            "expected_environment": read(authority.PLAN)["python_startup_environment"],
            "scope": "Exact selected compressed bytes only; no raw_final, unselected row read, native execution or complete acceptance.",
            "observer_boundary": "Original nested observer body retained; no supply/cap/relay is permitted in selected prefix. First supply boundary unavailable; reaching it is unknown.",
            "execution": "prepared_unexecuted"}
    write(output / "plan.json", plan)
    return plan


def observer_factory(replay_class, owner_class, bootstrap, profile):
    original = ast.parse(inspect.getsource(FROZEN.full.verify_case))
    classes = [copy.deepcopy(node) for node in original.body[0].body if isinstance(node, ast.ClassDef)]
    require([node.name for node in classes] == ["ObservedTape", "ObservedOwner"], "observer_classes")
    before = ast.dump(ast.Module(body=copy.deepcopy(classes), type_ignores=[]), include_attributes=False)
    replacements = 0
    for node in ast.walk(classes[0]):
        if isinstance(node, ast.Dict):
            for index, value in enumerate(node.values):
                if ast.dump(value, include_attributes=False) == ast.dump(ast.parse("deepcopy(value)", mode="eval").body, include_attributes=False):
                    node.values[index] = ast.parse("observer_result(value, self, ordinal)", mode="eval").body
                    replacements += 1
    require(replacements == 1, "observer_same_text_binding_only")
    inverse = copy.deepcopy(classes)
    for node in ast.walk(inverse[0]):
        if isinstance(node, ast.Dict):
            for index, value in enumerate(node.values):
                if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "observer_result":
                    node.values[index] = ast.parse("deepcopy(value)", mode="eval").body
    require(ast.dump(ast.Module(body=inverse, type_ignores=[]), include_attributes=False) == before, "observer_inverse_AST")
    template = ast.parse("def factory():\n    compared=0\n    prefix_closed=False\n    cap_proofs={}\n    submits={}\n    queries={}\n    frames={}\n    latest={}\n    owner_calls=[]\n    relay_ids=set()\n    first={'at':None}\n    old=bootstrap\n    oldmanifest=bootstrap_manifest\n").body[0]
    template.body.extend(classes)
    template.body.extend(ast.parse("return ObservedTape,ObservedOwner,owner_calls,cap_proofs").body)
    namespace = {**FROZEN.full.verify_case.__globals__,
                 "base": SimpleNamespace(**{**vars(PHYSICAL), "ReplayTape": replay_class}),
                 "policy": SimpleNamespace(**{**vars(POLICY), "BridgeOwner": owner_class}),
                 "bootstrap": bootstrap, "bootstrap_manifest": [json.loads(line) for line in (bootstrap / "api/manifest.jsonl").read_bytes().splitlines()],
                 "observer_result": FROZEN.observer_result}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[template], type_ignores=[])), __file__, "exec"), namespace)
    observed_tape, observed_owner, owner_calls, caps = namespace["factory"]()
    proof = {"original_nested_classes_AST_sha256": hashlib.sha256(before.encode()).hexdigest(),
             "inverse_AST_exact": True, "only_expression_change": "deepcopy(value) to existing same-text observer_result",
             "unavailable_first_supply_boundary": None, "cap_ids": "empty only while prefix contains no cap/relay"}
    return observed_tape, observed_owner, owner_calls, caps, proof


def replay_prefix(output, plan, candidate, progress):
    candidate._verify()
    bundle = routing._bundle(candidate.capture_digest_v2)
    routing_proof = bundle.prove()
    comparison = ORIGINAL.PrefixComparison(output / "old", plan["prefixes"]["old"]["prefix_manifest_sha256"], LIMIT)
    replay_class, actor_proof = actor.replay_type(comparison, progress)
    labels = {POLICY.BridgeOwner.activate.__code__: "complete_activation", routing.base.Owner.activate.__code__: "base_activation",
              protocol_control.ProtocolClient.refresh.__code__: "client_refresh", routing.base.delivered_peer.__code__: "delivered_peer",
              routing.reuse.latest_own_capture.__code__: "latest_own_capture", routing.possession.PossessionGate.consume.__code__: "possession_consume",
              POLICY.received_barrier.__code__: "received_barrier", POLICY.choose_action.__code__: "choose_action",
              encoder.Candidate.capture_digest_v2.__code__: "complete_digest", encoder.Candidate._verify.__code__: "candidate_identity",
              encoder._ORIGINAL.__code__: "original_fallback_writer", actor.read_text_row.__code__: "gzip_and_first_decode",
              PHYSICAL.gzread.__code__: "reference_gzip_and_decode", PHYSICAL.sha.__code__: "file_hash",
              ORIGINAL.PrefixComparison.consume.__code__: "ordered_old_prefix_comparison", ORIGINAL.semantic_api.__code__: "ordered_semantic_encoding"}
    profile = Profile(labels, {candidate._try: "C_try_typed_bytes", encoder._SHA: "SHA256"})
    observed_tape, observed_owner, owner_calls, caps, observer_proof = observer_factory(replay_class, bundle.BridgeOwner, output / "bootstrap", profile)
    nested = [constant for constant in observed_tape.__getattr__.__code__.co_consts if inspect.iscode(constant)]
    require(len(nested) == 1, "observer_endpoint_code")
    labels[nested[0]] = "outer_observer_with_endpoint"
    created_owners = []

    class LimitedTape(observed_tape):
        def __getattr__(self, name):
            method = super().__getattr__(name)

            def endpoint(*args, **kwargs):
                return invoke_endpoint(self, profile, name, method, args, kwargs)

            return endpoint

    class RecordedOwner(observed_owner):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created_owners.append(self)

        def activate(self):
            super().activate()
            if self.supply is not None or self.cap_observed or self.cap_relay:
                raise UnsupportedBoundary("supply_or_cap_outside_prefix_observer_scope")

    run = routing.clone(bundle.policy.run_policy, {**bundle.policy.run_policy.__globals__, "BridgeOwner": RecordedOwner})
    tape = LimitedTape(output / "new")
    prefix_started = time.perf_counter_ns()
    require(sys.getprofile() is None, "existing_profiler")
    status = "unknown_not_censored"
    sys.setprofile(profile.callback)
    try:
        run(tape, read(plan["original_plan"]))
    except PrefixCensored:
        status = "fixed_prefix_censored_no_full_success"
    finally:
        sys.setprofile(None)
        elapsed = time.perf_counter_ns() - prefix_started
        write(output / "profile_partial.json", {"status": status, "spans": profile.spans,
              "open_spans": profile.stack, "error": profile.error, "api_index": tape.index,
              "owner_calls": owner_calls, "prefix_wall_ns": elapsed})
    require(status == "fixed_prefix_censored_no_full_success" and tape.index == comparison.index == LIMIT, "prefix_counts")
    require(len(created_owners) == 2 and not caps and all(owner.supply is None and not owner.cap_observed and not owner.cap_relay for owner in created_owners), "prefix_boundary_conditions")
    require(actor_proof["runtime"]["pending_texts"] == 0 and tape._observer_pending is False, "actor_observer_closed")
    measured = profile.report()
    measured.update(status=status, prefix_wall_ns=elapsed, api_rows=tape.index, old_rows=comparison.index,
                    physical_time=tape.physical_time, owner_calls=owner_calls,
                    completed_activation_spans=sum(span["label"] == "complete_activation" and span["outcome"] != "interrupted_at_prefix_boundary" for span in profile.spans),
                    interrupted_activation_spans=sum(span["label"] == "complete_activation" and span["outcome"] == "interrupted_at_prefix_boundary" for span in profile.spans),
                    actor_proof=actor_proof, observer_proof=observer_proof, routing_proof=routing_proof,
                    unclassified_wall_ns=elapsed-sum(span["inclusive_ns"] for span in profile.spans if span["parent"] is None),
                    original_policy_code_unchanged=run.__code__ is POLICY.run_policy.__code__,
                    original_module_globals_unchanged=bundle.prove()["old_module_globals_unmodified"],
                    native_calls=0, full_saved_acceptance=False, whole_offered_success=False)
    write(output / "profile.json", measured)
    return {key: measured[key] for key in ("status", "api_rows", "old_rows", "physical_time", "totals", "completed_activation_spans", "interrupted_activation_spans", "unclassified_wall_ns")}


def verify_pins(output, plan):
    for name, expected in plan["source_hashes"].items():
        require(sha(ROOT / name) == expected, "source_changed:" + name)
    for name, expected in plan["input_pins"].items():
        require(sha(name) == expected, "input_pin_changed:" + name)
    for role, prefix in plan["prefixes"].items():
        directory = output / role / "api" if role == "bootstrap" else output / role
        require(sha(directory / "manifest.jsonl") == prefix["prefix_manifest_sha256"], "prefix_manifest")
        require(len(list(directory.glob("*.json.gz"))) == LIMIT, "prefix_files")
        for row in prefix["rows"]:
            require(sha(directory / row["path"]) == row["sha256"], "prefix_row_hash")


def worker(output, admission):
    require(sys.stdin.readline() == admission + "\n", "owned_admission")
    plan = read(output / "plan.json")
    report = {"status": "running", "full_saved_acceptance": False, "native_calls": 0, "C_entry": None, "C_exit": None}
    progress = FROZEN.Progress(output)
    candidate = None
    try:
        with progress.stage("entry_sources_and_selected_inputs"):
            verify_pins(output, plan)
        with progress.stage("C_entry_full_dependency_checks"):
            candidate, report["C_entry"] = authority.begin(plan["source_hashes"])
            write(output / "C_entry.json", report["C_entry"])
        with progress.stage("fixed_512_original_policy_prefix"):
            report["prefix"] = replay_prefix(output, plan, candidate, progress)
        report["status"] = "prefix_closed_C_exit_pending"
    except BaseException:
        report["status"] = "unknown_diagnostic_failure"
        report["exception"] = traceback.format_exc()
    finally:
        write(output / "worker_partial.json", report)
        if candidate is not None:
            try:
                with progress.stage("C_exit_full_dependency_checks"):
                    report["C_exit"] = authority.finish(candidate, plan["source_hashes"])
                    write(output / "C_exit.json", report["C_exit"])
                with progress.stage("exit_sources_and_selected_inputs"):
                    verify_pins(output, plan)
                if report["status"] == "prefix_closed_C_exit_pending":
                    report["status"] = "diagnostic_closed_prefix_only"
            except BaseException:
                report["status"] = "unknown_C_exit_failure"
                report["exit_exception"] = traceback.format_exc()
        progress.close()
        write(output / "worker.json", report)
    return 0 if report["status"] == "diagnostic_closed_prefix_only" else 1


def launch(output):
    require(not (output / "launch.json").exists(), "one_attempt_only")
    start = time.perf_counter_ns()
    write(output / "launch.json", {"whole_seconds": SECONDS, "start_ns": start, "status": "started"})
    admission = sha(output / "plan.json")
    expected = read(output / "plan.json")["expected_environment"]
    environment = startup_environment(os.environ, expected)
    command = [sys.executable, str(Path(__file__).resolve()), "--worker", "--output", str(output), "--admission", admission]
    original_environment = dict(os.environ)
    try:
        os.environ.clear()
        os.environ.update(environment)
        with (output / "stdout.log").open("w", encoding="utf-8") as stdout, (output / "stderr.log").open("w", encoding="utf-8") as stderr:
            process = bounded_windows_job.run(command, timeout=SECONDS-(time.perf_counter_ns()-start)/1e9,
                                             stdout=stdout, stderr=stderr, admission=admission, cwd=ROOT)
    finally:
        os.environ.clear()
        os.environ.update(original_environment)
    end = time.perf_counter_ns()
    result = {"status": "unknown", "process": process, "command": command, "start_ns": start, "end_ns": end,
              "elapsed_ns": end-start, "whole_seconds": (end-start)/1e9, "limit_seconds": SECONDS,
              "full_saved_acceptance": False, "native_calls": 0, "source_plan_sha256": admission}
    if process["status"] == "exited" and process["exitcode"] == 0 and (output / "worker.json").exists():
        report = read(output / "worker.json")
        if report["status"] == "diagnostic_closed_prefix_only" and end-start <= int(SECONDS*1e9):
            result["status"] = "closed_prefix_diagnostic_only"
    write(output / "external_wall.json", result)
    print(json.dumps({"status": result["status"], "whole_seconds": result["whole_seconds"], "output": str(output)}))
    return 0 if result["status"] == "closed_prefix_diagnostic_only" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--admission")
    args = parser.parse_args()
    output = args.output.resolve()
    if args.prepare:
        prepare(output)
        print(json.dumps({"status": "prepared_unexecuted", "output": str(output)}))
        return 0
    if args.worker:
        return worker(output, args.admission)
    return launch(output)


if __name__ == "__main__":
    raise SystemExit(main())
