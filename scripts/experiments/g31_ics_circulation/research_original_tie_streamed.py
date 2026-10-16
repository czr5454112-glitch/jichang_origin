"""Versioned matched original comparison with complete streamed diagnostics.

The two earlier monolithic180s attempts remain censored. This driver changes
diagnostic retention and private state ownership only; small native conformance
must pass before admitting the full two-arm mechanism comparison.
"""
from __future__ import annotations
import argparse
import copy
import gc
import gzip
import json
from pathlib import Path
import subprocess
import sys
import time
from . import research_original_tie_comparison as original
from .original_workload import digest, json_digest, write_json
from .native_host import audit_result

VERSION = "g31.lt2.original_tie_streamed.v2"
SHORT_HORIZON = 10000.
HORIZON = original.HORIZON
SHARD_ACTIVATIONS = 500
MAX_ACTIVATIONS = 100000
ARMS = ("conformance_unbroken", "conformance_streamed", "control", "candidate")


class InjectionBoundary(original.ComparisonBoundary):
    """Measure legacy reads or skip observations that cannot affect the intent.

ChainIntent reads only current owner/time/trays/jobs/node contracts. The existing
native policy projection contains those exact fields and omits full ACK history.
Once the four-step intent is terminal, observe() was already an unconditional
no-op; a control arm never invokes observe() at all.
"""
    def __init__(self, native, path, commands, enabled, *, legacy_observation):
        super().__init__(native, path, commands, enabled)
        self.legacy_observation = legacy_observation
        self.metrics = {"owner_boundaries": 0, "full_view_reads": 0, "policy_view_reads": 0,
            "skipped_unused_reads": 0, "refresh_wall_seconds": 0., "view_wall_seconds": 0.}

    def advance_until_owner_notification(self, owners, after, horizon, *, max_events):
        response = self.native.advance_until_owner_notification(owners, after, horizon, max_events=max_events)
        if response.get("timestamp_complete"):
            for owner in sorted(response.get("notifications", {})):
                self.metrics["owner_boundaries"] += 1
                terminal = self.intent.status in {"rejected_intent", "observed_path_divergence", "all_four_intents_and_edges_observed"}
                if not self.legacy_observation and (not self.enabled or terminal):
                    self.metrics["skipped_unused_reads"] += 1
                    continue
                started = time.perf_counter(); self.client.refresh(owner_id=owner)
                self.metrics["refresh_wall_seconds"] += time.perf_counter() - started
                started = time.perf_counter()
                if self.legacy_observation:
                    view = self.native.observe_protocol(owner); self.metrics["full_view_reads"] += 1
                else:
                    view = self.native.observe_protocol_control_policy(owner); self.metrics["policy_view_reads"] += 1
                self.metrics["view_wall_seconds"] += time.perf_counter() - started
                if self.enabled: self.intent.observe(view, self.client)
        return response


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def gz(path, value, *, fast_export=False):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(temporary, "wt", encoding="utf-8", compresslevel=1 if fast_export else 9) as stream:
        if fast_export:
            stream.write(json.dumps(value, allow_nan=False))
        else:
            json.dump(value, stream, allow_nan=False)
    temporary.replace(path)


def read_gz(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream: return json.load(stream)


def semantic_calls(calls):
    return [{k: v for k, v in row.items() if k != "submit_compute_ms"} for row in calls]


def semantic_result(result):
    # Returned per-call advance/continuation and native wall counters differ
    # with segmentation. Every physical row and native decision is compared.
    return {k: v for k, v in result.items() if k not in {"advance", "control_continuation", "native_event_ms"}}


def conformance(left, right, protocol):
    checks = {"both_reached_horizon": all(a.get("status") == "reached" and
            a.get("result", {}).get("advance", {}).get("horizon_complete") is True and
            a["result"]["advance"]["physical_time"] == SHORT_HORIZON for a in (left, right)),
        "input_identity": left.get("input_sha256") == right.get("input_sha256"),
        "binary_identity": left.get("binary_sha256") == right.get("binary_sha256"),
        "initial_native_seal": left.get("checkpoint_identity") == right.get("checkpoint_identity"),
        "final_native_seal": left.get("native_state_sha256") == right.get("native_state_sha256"),
        "controller_state": left.get("controller_state") == right.get("controller_state"),
        "physics_and_native_decisions": semantic_result(left.get("result", {})) == semantic_result(right.get("result", {})),
        "ordinary_calls_and_retries": semantic_calls(left.get("all_control_calls", [])) == semantic_calls(right.get("all_control_calls", [])),
        "injected_calls_and_retries": semantic_calls(left.get("route_calls", [])) == semantic_calls(right.get("route_calls", [])),
        "injected_intent_ack_and_edges": left.get("intent") == right.get("intent"),
        "injected_outbox": left.get("route_outbox") == right.get("route_outbox"),
        "owner_activation_count": left.get("activation_count") == right.get("activation_count"),
        "both_physical_audits_passed": all(a.get("physical_audit", {}).get("status") == "passed" for a in (left, right)),
        "source_unchanged": left.get("source_changed") == right.get("source_changed") == []}
    required = ("input_sha256", "binary_sha256", "checkpoint_identity", "native_state_sha256", "controller_state", "intent")
    checks["required_identities_present"] = all(all(a.get(k) for k in required) for a in (left, right))
    checks["four_actual_commands"] = all(a.get("intent", {}).get("status") == "all_four_intents_and_edges_observed" and
        len(a.get("intent", {}).get("decisions", [])) == 4 for a in (left, right))
    checks["actual_gate_revalidated"] = all(original.validate_gate({**a,
        "status": a.get("intent", {}).get("status"), "actual_native_clock": SHORT_HORIZON},
        protocol, protocol["expected_binary_sha256"]) for a in (left, right))
    return {"status": "passed" if all(checks.values()) else "unknown_or_failed_conformance", "checks": checks,
        "scope": "Exact candidate H10000 continuation/physics only; no general equivalence or100ms certification."}


def prepare(output, input_file, paths, gate_receipt, binary_sha, timeout, *, fast_export=False):
    native_build = Path(__file__).resolve().parents[3] / "outputs/experiments/g31_ics_lt2_sustained_20261014/native019_build_001/receipt.json"
    built = json.loads(native_build.read_text())
    if built.get("source_changed") != [] or binary_sha not in built["binary_sha256"].values():
        raise ValueError("tie_stream:native019_compilation_authority_mismatch")
    protocol = original.prepare(output, input_file, paths)
    sources = [Path(__file__), *map(Path, protocol["source_sha256"])]
    protocol.update(schema=VERSION, native_branch_budget=4, order=list(ARMS), expected_binary_sha256=binary_sha,
        gate_receipt_sha256=digest(gate_receipt), hard_timeout_per_full_arm_seconds=timeout,
        conformance_horizon=SHORT_HORIZON, conformance_timeout_seconds=60., activation_shard_budget=SHARD_ACTIVATIONS,
        max_activations_per_arm=MAX_ACTIVATIONS,
        diagnostic_export={"fast_export": fast_export, "gzip_level": 1 if fast_export else 9,
            "encoding": "bulk_dumps" if fast_export else "iterative_dump", "decompressed_json_bytes_unchanged": True},
        source_sha256={str(s.resolve()): digest(s) for s in sources},
        compiled_native_authority={"build_receipt_path": str(native_build), "build_receipt_sha256": digest(native_build),
            "binary_sha256": binary_sha, "scope": "Previously compiled native019 and its recorded build-time C++ hashes; current native023 C++ files are not this binary's source authority."},
        diagnostic_change="Every raw controller record/checkpoint/call/native boundary is saved in ordered gzip shards; prior diagnostics are released after saving. GC remains enabled and its actual callbacks are streamed separately.",
        policy_change="None intended. Full arms use private consume-state ownership and omit wrapper full-history reads when control-disabled or intent-terminal; active injection uses exact owner policy projection. Conformance compares original full-view public-copy unbroken with private-consume500-activation shards before admission.",
        physical_horizon_change="None: each controller call requests the same finalH; only owner-activation cuts form shards, including incomplete native timestamps.",
        source_persistence="Actual native seal at every saved boundary plus immutable complete raw tape; JSON alone is not a restored native session.",
        prior_attempts="original_tie_comparison_native_001/control and candidate each180s unknown_hard_timeout remain unchanged.",
        timeout_diagnosis="Old wrapper statically rereads full growing native request/ACK history at every notification even when disabled/terminal. Its duration and GC/retention contribution were not measured in the two censored attempts. New wrapper read counters/times and GC callbacks are explicit.",
        admission="Original native gate verified and both short conformance arms pass all exact checks; otherwise full arms not admitted.")
    for source in sources: (output / "source_archive" / source.name).write_bytes(source.read_bytes())
    (output / "compiled_native019_build_receipt.json").write_bytes(native_build.read_bytes())
    write_json(output / "preregistered_protocol.json", protocol)
    write_json(output / "branch_ledger.json", {arm: {"status": "unknown_unexecuted"} for arm in ARMS})
    return protocol


def iter_calls(arm_dir):
    manifest = json.loads((arm_dir / "shards.json").read_text())
    sequence = 0
    for shard in manifest["shards"]:
        path = arm_dir / shard["path"]
        if digest(path) != shard["sha256"]: raise ValueError("tie_stream:shard_identity")
        part = read_gz(path)["run"]
        traces = sorted(row["trace_sequence"] for key in ("control_records", "native_batches") for row in part[key])
        if traces != list(range(sequence, sequence + len(traces))): raise ValueError("tie_stream:trace_gap_or_reorder")
        sequence += len(traces)
        yield from part["client_calls"]


def assess_match(data, arms, protocol):
    report = original.assess(data, arms)
    if set(arms) == {"control", "candidate"}:
        identities = ("checkpoint_identity", "input_sha256", "binary_sha256", "gate_receipt_sha256")
        valid = all(arms["control"].get(k) and arms["control"].get(k) == arms["candidate"].get(k) for k in identities)
        valid = valid and all(a.get("input_sha256") == protocol["input_sha256"] and
            a.get("binary_sha256") == protocol["expected_binary_sha256"] and
            a.get("gate_receipt_sha256") == protocol["gate_receipt_sha256"] and
            a.get("source_changed") == [] for a in arms.values())
        if not valid:
            report.update(status="unknown_source_or_checkpoint_mismatch", storage_order_mechanism="unknown",
                strict_full_population_protection="unknown", strict_horizon_offered_protection="unknown", gain_all_jobs=None)
    return report


def worker(args):
    output, arm = args.output, args.arm
    protocol = json.loads((output / "preregistered_protocol.json").read_text())
    if digest(args.binary) != protocol["expected_binary_sha256"]: raise ValueError("tie_stream:binary_changed")
    if any(digest(Path(s)) != h for s, h in protocol["source_sha256"].items()): raise ValueError("tie_stream:source_changed")
    data = read_gz(output / "input.json.gz")
    if json_digest(data) != protocol["input_sha256"]: raise ValueError("tie_stream:input_changed")
    gate = json.loads(args.gate_receipt.read_text())
    if digest(args.gate_receipt) != protocol["gate_receipt_sha256"] or not original.validate_gate(gate, protocol, protocol["expected_binary_sha256"]):
        raise ValueError("tie_stream:gate_not_verified")
    arm_dir = output / arm; arm_dir.mkdir(exist_ok=False); (arm_dir / "segments").mkdir()
    native = original.chain.load_native(args.binary); session = native.NativeSession(data)
    initial_seal = session.offline_state_sha256()
    chosen = protocol["hypothesis"]
    wrapped = InjectionBoundary(session, chosen["path"], chosen["commands"], arm != "control",
        legacy_observation=arm == "conformance_unbroken")
    owners = sorted({n["resource_owner"] for n in data["node_contracts"]})
    horizon = SHORT_HORIZON if arm.startswith("conformance_") else HORIZON
    consume = arm != "conformance_unbroken"
    shard_budget = SHARD_ACTIVATIONS if consume else MAX_ACTIVATIONS
    state, final_result, status = None, None, "unknown_unexecuted"
    activations = trace_offset = segment = route_offset = 0
    wall_started = time.perf_counter(); gc_open = {}; gc_count = 0; controller_seconds = 0.; seal_seconds = 0.; export_seconds = 0.
    def export(path, value):
        nonlocal export_seconds
        started_export = time.perf_counter()
        gz(path, value, fast_export=protocol["diagnostic_export"]["fast_export"])
        export_seconds += time.perf_counter() - started_export
    manifest = {"schema": VERSION, "shards": [], "all_raw_records_retained": True,
        "cross_process_native_checkpoint": False, "source_identity": protocol["source_sha256"],
        "input_sha256": protocol["input_sha256"], "initial_native_seal": initial_seal}
    atomic_json(arm_dir / "shards.json", manifest)
    gc_file = (arm_dir / "gc_events.jsonl").open("w", encoding="utf-8", buffering=1)
    inside = [False]
    def gc_callback(phase, info):
        nonlocal gc_count
        generation = info["generation"]
        if phase == "start": gc_open[generation] = (time.perf_counter_ns(), inside[0], session.physical_time)
        elif generation in gc_open:
            start, in_control, at = gc_open.pop(generation); gc_count += 1
            gc_file.write(json.dumps({"generation": generation, "start_ns": start, "end_ns": time.perf_counter_ns(),
                "inside_controller": in_control, "physical_time_at_start": at, "collected": info["collected"],
                "uncollectable": info["uncollectable"]}) + "\n")
    gc.callbacks.append(gc_callback)
    try:
        while activations < MAX_ACTIVATIONS:
            started = time.perf_counter(); inside[0] = True
            part = original.chain.run_event_protocol_control(wrapped, owners, horizon=horizon, control_period=60.,
                command_delay=2., publication_delay=.5, retry_period=60., lease_seconds=120., routes=False,
                forecasts=True, predictive=True, prebalance=True, event_budget=100000,
                max_activations=min(shard_budget, MAX_ACTIVATIONS - activations), state=state, _consume_state=consume)
            inside[0] = False; controller_seconds += time.perf_counter() - started
            for key in ("control_records", "native_batches"):
                for row in part[key]: row["trace_sequence"] += trace_offset
            trace_offset += len(part["control_records"]) + len(part["native_batches"])
            activations += len(part["control_records"]); status = part["status"]
            # The actual native seal is diagnostic only and never enters the
            # wrapper or an owner decision. A cut may still need timestamp drain.
            seal_started = time.perf_counter(); seal = session.offline_state_sha256()
            this_seal_seconds = time.perf_counter() - seal_started; seal_seconds += this_seal_seconds
            payload = {"run": part, "route_calls": wrapped.client.calls[route_offset:],
                "route_outbox": wrapped.client.state, "intent": vars(wrapped.intent),
                "native_state_sha256": seal, "native_physical_time": session.physical_time,
                "native_timestamp_complete": part["controller_state"]["native_timestamp_complete"],
                "native_seal_wall_seconds": this_seal_seconds, "wrapper_metrics": wrapped.metrics}
            route_offset = len(wrapped.client.calls)
            shard_path = arm_dir / "segments" / f"{segment:04d}.json.gz"
            export(shard_path, payload)
            manifest["shards"].append({"path": str(shard_path.relative_to(arm_dir)), "sha256": digest(shard_path),
                "status": status, "physical_time": session.physical_time, "native_state_sha256": seal,
                "native_seal_wall_seconds": this_seal_seconds,
                "counts": {k: len(part[k]) for k in ("control_records", "native_batches", "client_calls")}})
            atomic_json(arm_dir / "shards.json", manifest)
            atomic_json(arm_dir / "heartbeat.json", {"stage": "shard_saved", "segment": segment, "status": status,
                "physical_time": session.physical_time, "owner_activations": activations,
                "offered_full_input": len(data["jobs"]), "arrived": sum(j["arrival"] <= session.physical_time for j in data["jobs"]),
                "controller_seconds": controller_seconds, "wall_seconds": time.perf_counter() - wall_started,
                "diagnostic_export_seconds": export_seconds,
                "gc_events": gc_count, "native_state_sha256": seal, "native_seal_seconds": seal_seconds,
                "wrapper_metrics": wrapped.metrics})
            segment += 1
            state, final_result = part["controller_state"], part["result"]
            del payload, part
            if status != "control_budget_exhausted": break
        raw = {"status": status, "result": final_result, "controller_state": state,
            "intent": vars(wrapped.intent), "route_calls": wrapped.client.calls, "route_outbox": wrapped.client.state,
            "activation_count": activations, "checkpoint_identity": initial_seal,
            "native_state_sha256": session.offline_state_sha256(), "input_sha256": protocol["input_sha256"],
            "binary_sha256": protocol["expected_binary_sha256"], "gate_receipt_sha256": protocol["gate_receipt_sha256"],
            "wall_seconds": time.perf_counter() - wall_started, "controller_seconds": controller_seconds,
            "native_seal_seconds": seal_seconds,
            "diagnostic_export_seconds_before_final_raw": export_seconds,
            "wrapper_metrics": wrapped.metrics,
            "physical_audit": {"status": "unknown_missing_or_censored_result"},
            "complete_request_100ms_certified": False}
        if arm.startswith("conformance_"): raw["all_control_calls"] = list(iter_calls(arm_dir))
        if final_result:
            replay = copy.deepcopy(data)
            replay["transfers"] += [{**c["request"], "issued_at": c["at"]} for c in iter_calls(arm_dir) if c["kind"] == "transfer" and not c["retry"]]
            try: raw["physical_audit"] = audit_result(replay, final_result)
            except (AssertionError, ValueError, KeyError) as error: raw["physical_audit"] = {"status": "failed", "reason": str(error)}
        raw["source_changed"] = [s for s, h in protocol["source_sha256"].items() if digest(Path(s)) != h]
        export(output / f"{arm}.json.gz", raw)
        atomic_json(arm_dir / "heartbeat.json", {"stage": "worker_finished", "status": status,
            "physical_time": session.physical_time, "owner_activations": activations,
            "diagnostic_export_seconds": export_seconds,
            "wall_seconds": time.perf_counter() - wall_started, "native_state_sha256": raw["native_state_sha256"]})
    finally:
        inside[0] = False; gc.callbacks.remove(gc_callback); gc_file.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True); parser.add_argument("--input", type=Path)
    parser.add_argument("--paths", type=Path); parser.add_argument("--gate-receipt", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True); parser.add_argument("--expected-binary-sha256", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=600.)
    parser.add_argument("--fast-lossless-export", action="store_true")
    parser.add_argument("--execute", action="store_true"); parser.add_argument("--worker", action="store_true")
    parser.add_argument("--arm", choices=ARMS)
    args = parser.parse_args()
    if args.worker: worker(args); return
    protocol = prepare(args.output, args.input, args.paths, args.gate_receipt, args.expected_binary_sha256, args.timeout_seconds,
        fast_export=args.fast_lossless_export)
    if not args.execute: print("prepared_no_native_calls:2conformance_plus2matched"); return
    ledger = {arm: {"status": "unknown_unexecuted"} for arm in ARMS}; arms = {}; proof = None
    for arm in ARMS:
        if arm == "control":
            if set(arms) != set(ARMS[:2]): proof = {"status": "unknown_missing_conformance_arm"}
            else: proof = conformance(arms[ARMS[0]], arms[ARMS[1]], protocol)
            atomic_json(args.output / "conformance.json", proof)
            if proof["status"] != "passed":
                for later in ARMS[2:]: ledger[later] = {"status": "not_admitted_conformance"}
                break
            arms.clear()
        command = [sys.executable, "-m", __spec__.name, "--worker", "--output", str(args.output),
            "--gate-receipt", str(args.gate_receipt), "--binary", str(args.binary),
            "--expected-binary-sha256", args.expected_binary_sha256, "--arm", arm]
        started = time.perf_counter()
        with (args.output / f"{arm}.stdout.log").open("w", encoding="utf-8") as stdout, (args.output / f"{arm}.stderr.log").open("w", encoding="utf-8") as stderr:
            try:
                result = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=60. if arm.startswith("conformance_") else args.timeout_seconds)
                raw_path = args.output / f"{arm}.json.gz"
                if result.returncode or not raw_path.exists(): ledger[arm] = {"status": "unknown_failed", "exit_code": result.returncode}
                else: arms[arm] = read_gz(raw_path); ledger[arm] = {"status": arms[arm]["status"], "exit_code": result.returncode}
            except subprocess.TimeoutExpired: ledger[arm] = {"status": "unknown_hard_timeout"}
        ledger[arm]["wall_seconds"] = time.perf_counter() - started
        ledger[arm]["parent_observed_source_changed"] = [s for s, h in protocol["source_sha256"].items() if digest(Path(s)) != h]
        atomic_json(args.output / "branch_ledger.json", ledger)
    atomic_json(args.output / "branch_ledger.json", ledger)
    report = assess_match(read_gz(args.output / "input.json.gz"), {k: v for k, v in arms.items() if k in ARMS[2:]}, protocol)
    report.update(branch_ledger=ledger, conformance=proof, schema=VERSION,
        source_changed=sorted({s for row in ledger.values() for s in row.get("parent_observed_source_changed", [])}))
    if report["source_changed"]:
        report.update(status="unknown_source_changed", storage_order_mechanism="unknown", gain_all_jobs=None,
            strict_full_population_protection="unknown", strict_horizon_offered_protection="unknown")
    atomic_json(args.output / "receipt.json", report)


if __name__ == "__main__": main()
