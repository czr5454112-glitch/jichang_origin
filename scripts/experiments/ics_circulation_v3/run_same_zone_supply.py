"""Predeclared same-zone supply mechanism, nominal deployment and error tapes."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
import gzip
import json
from pathlib import Path
import pickle
from time import perf_counter, process_time
import traceback

from .experiment_protocol import create_output_directory, write_new_json
from .experiment_resources import memory_snapshot
from .model import Bag
from .network_full_cycle import compare_old_result
from .network_role_labels import SPEC
from .phase4_control import build_engine
from .phase4_network_workloads import file_sha, load_network, make_workload
from .role_coverage import CursorSimulation, digest
from .routing_cache_contract import enable_replay_cache, routing_cache_state
from .runtime import actual_action_key
from .same_zone_experiment import (CASE_BUDGET, POLICIES, SEEDS, TAIL_CAP,
                                   install_supply_policy, run_observed_cycle, saved_error_tapes)


ROOT = Path(__file__).resolve().parents[3]
SOURCE = Path(__file__).parent
BASE = ROOT / "outputs/experiments/ics_circulation_v3"
PRIMARY = BASE / "phase4_w3_network_role_labels_parallel_20261009"
NOMINAL = BASE / "phase4_w3_network_nominal_opportunities_repaired_20261010"
DEFAULT_OUTPUT = BASE / "phase4_w3_same_zone_supply_20261010"
SCENES = tuple(SEEDS)
STAGES = ("mechanism", "nominal_pilot", "full")


def read(path):
    path = Path(path)
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_gzip(path, value):
    with gzip.open(path, "xt", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def exact_json_value(left, right):
    """Compare every persisted field; normalize only JSON tuple/list encoding."""
    return json.loads(json.dumps(left, allow_nan=False)) == json.loads(json.dumps(right, allow_nan=False))


def input_paths():
    paths = [PRIMARY / "protocol.json", PRIMARY / "manifest.json", NOMINAL / "protocol.json",
             NOMINAL / "collection_reuse_manifest.json", NOMINAL / "full/summary.json",
             NOMINAL / "full/manifest.json", NOMINAL / "collections/counterflow/d0040.json",
             NOMINAL / "collections/counterflow/d0040.pkl"]
    for ordinal in (0, 1):
        paths.append(NOMINAL / "full" / f"counterflow_d0040_c{ordinal}.json.gz")
    for scene in SCENES:
        paths.extend(PRIMARY / scene / name for name in
            (scene + "_input.json", scene + "_collection.json", "original_profile.json", "manifest.json"))
    return paths


def exact_original_scene(name):
    folder = PRIMARY / name
    network, provenance = load_network(folder / "original_profile.json")
    scene = make_workload(name, network, provenance, rounds=3)
    actual = json.loads(json.dumps({"initial": asdict(scene.initial),
        "forecasts": [asdict(f) for f in scene.forecasts],
        "future_engine_only": [asdict(b) for b in scene.future_bags], "horizon": scene.horizon}))
    saved = read(folder / (name + "_input.json"))
    if any(saved[key] != value for key, value in actual.items()):
        raise ValueError("original saved initial/forecasts/tape/horizon differ: " + name)
    return scene


def validate_input_bindings():
    primary_manifest = read(PRIMARY / "manifest.json")
    if file_sha(PRIMARY / "protocol.json") != primary_manifest["protocol_sha256"]:
        raise ValueError("old primary protocol manifest binding failed")
    for scene in SCENES:
        folder = PRIMARY / scene
        if file_sha(folder / "manifest.json") != primary_manifest["scene_manifest_sha256"][scene]:
            raise ValueError("old scene manifest binding failed: " + scene)
        scene_manifest = read(folder / "manifest.json")
        for name in (scene + "_input.json", scene + "_collection.json", "original_profile.json"):
            if file_sha(folder / name) != scene_manifest[name]:
                raise ValueError("old scene file binding failed: " + name)
    nominal_protocol = read(NOMINAL / "protocol.json")
    for name, expected in nominal_protocol["source_sha256"].items():
        if file_sha(SOURCE / name) != expected:
            raise ValueError("audited nominal source changed: " + name)
    for name, expected in nominal_protocol["input_sha256"].items():
        if file_sha(ROOT / name) != expected:
            raise ValueError("audited nominal original input changed: " + name)
    manifest = read(NOMINAL / "full/manifest.json")
    for name in ("summary.json", "counterflow_d0040_c0.json.gz", "counterflow_d0040_c1.json.gz"):
        if file_sha(NOMINAL / "full" / name) != manifest[name]:
            raise ValueError("audited nominal branch binding failed: " + name)
    reuse = read(NOMINAL / "collection_reuse_manifest.json")
    if file_sha(Path(reuse["prior"]) / "manifest.json") != reuse["prior_manifest_sha256"]:
        raise ValueError("prior real checkpoint collection manifest changed")
    for suffix in ("json", "pkl"):
        relative = str(Path("collections/counterflow") / ("d0040." + suffix))
        if file_sha(NOMINAL / relative) != reuse["files"][relative]:
            raise ValueError("reused actual checkpoint collection changed")


def planned_rows(stage):
    if stage == "mechanism":
        return [{"case_id": f"counterflow_d0040_c{c}__{policy}", "scene": "counterflow",
                 "candidate": c, "policy": policy, "tape_id": "checkpoint_nominal", "kind": "checkpoint"}
                for c in (0, 1) for policy in POLICIES]
    if stage not in ("nominal_pilot", "full"):
        raise ValueError("unknown predeclared stage")
    tapes = ("nominal",) if stage == "nominal_pilot" else ("nominal", *(f"error{i:02d}" for i in range(8)))
    return [{"case_id": f"{scene}__{tape}__{policy}", "scene": scene, "candidate": None,
             "policy": policy, "tape_id": tape, "kind": "initial_deployment"}
            for scene in SCENES for tape in tapes for policy in POLICIES]


def prepare(output):
    started, cpu = perf_counter(), process_time()
    output = create_output_directory(output)
    validate_input_bindings()
    for filename, expected in read(PRIMARY / "protocol.json")["source_sha256"].items():
        if file_sha(SOURCE / filename) != expected:
            raise ValueError("frozen original implementation differs: " + filename)
    source = {p.name: file_sha(p) for p in sorted(SOURCE.glob("*.py"))}
    if not {"same_zone_supply.py", "same_zone_experiment.py", "run_same_zone_supply.py"} <= source.keys():
        raise ValueError("complete new method and runner source required before freezing")
    tests = {p.name: file_sha(p) for p in sorted((ROOT / "tests").glob("test_ics_circulation_v3_*.py"))}
    inputs = {str(p.resolve()): file_sha(p) for p in input_paths()}
    snapshot, test_snapshot = output / "source_snapshot", output / "test_snapshot"
    snapshot.mkdir()
    test_snapshot.mkdir()
    for name in source:
        (snapshot / name).write_bytes((SOURCE / name).read_bytes())
    for name in tests:
        (test_snapshot / name).write_bytes((ROOT / "tests" / name).read_bytes())
    tapes = {}
    for name in SCENES:
        scene = exact_original_scene(name)
        local = {"nominal": scene.future_bags,
                 **{f"error{i:02d}": tape for i, tape in enumerate(saved_error_tapes(scene))}}
        tapes[name] = {tape_id: {"future_engine_only": [asdict(b) for b in tape],
                                 "sha256": digest([asdict(b) for b in tape]),
                                 "future_task_count": len(tape),
                                 "expected_task_count": len(scene.initial.bags) + len(tape)}
                       for tape_id, tape in local.items()}
    write_new_json(output / "saved_tapes.json", tapes)
    protocol = {"schema": "ics_v3_same_zone_supply_experiment_v1", "source_sha256": source,
        "test_sha256": tests, "input_sha256": inputs, "saved_tapes_sha256": file_sha(output / "saved_tapes.json"),
        "spec": asdict(SPEC), "policies": list(POLICIES), "workers": 3,
        "stage_planned_cases": {stage: planned_rows(stage) for stage in STAGES},
        "case_budget": asdict(CASE_BUDGET), "tail_cap": TAIL_CAP,
        "fixed_endpoint": "checkpoint start+80 or original scene horizon; final stop also requires complete controller drain",
        "milestones": "first task completion, first transport drain and first certified controller quiescence recorded separately; observation may continue to fixed endpoint",
        "censoring": "finite calls/work/wall/tick cutoff is censored, never true infeasibility; every requested case retained",
        "error_tapes": {"seeds": SEEDS, "count_per_scene": 8, "cancellation_probability": "1/8",
            "jitter_choices": [-2, 0, 2], "order": "bag_id sorted; protected bags copied without consuming RNG draws",
            "protected": "never cancel, jitter or change identity/OD/deadline", "slack": "deadline shifts by same amount as arrival",
            "forecast": "all policies retain exactly original publication schedule and predictions, never replaced by evaluation truth"},
        "mechanism_scope": "fixed prior counterflow d40 c0/c1; conditional interaction diagnostic, no additive deployment gain",
        "policy_scope": "centralized W3 Snapshot authority unchanged; same-zone donor domain enlarged, not identical conservative action domain",
        "budget_comparator": "old64 doubles only original cross-zone candidate bound; same_zone32plus32 has independent32 cross+32 same candidate queries; actual CPU/work may differ",
        "new_independent_source_count": 0,
        "source_scope": "three reused synthetic development flows on unchanged original graph; nominal repeats and error tapes are correlated sensitivity instances",
        "resource_scope": "case invocation includes setup, physical cycle, tracing and output serialization; cycle CPU is nested; stages repeated separately",
        "preparation_cpu_seconds": process_time() - cpu, "preparation_wall_seconds": perf_counter() - started}
    write_new_json(output / "protocol.json", protocol)
    write_new_json(output / "input_manifest.json", inputs)
    write_new_json(output / "preparation_manifest.json", {str(p.relative_to(output)): file_sha(p)
        for p in sorted(output.rglob("*")) if p.is_file()})
    return protocol


def verify(output, *, tests=True):
    output = Path(output)
    protocol = read(output / "protocol.json")
    manifest = read(output / "preparation_manifest.json")
    if any(file_sha(output / name) != expected for name, expected in manifest.items()):
        raise ValueError("frozen experiment preparation changed")
    for name, expected in protocol["source_sha256"].items():
        if file_sha(SOURCE / name) != expected:
            raise ValueError("frozen source changed: " + name)
    if tests:
        for name, expected in protocol["test_sha256"].items():
            if file_sha(ROOT / "tests" / name) != expected:
                raise ValueError("frozen test changed: " + name)
    for path, expected in protocol["input_sha256"].items():
        if file_sha(path) != expected:
            raise ValueError("pinned original input changed: " + path)
    return protocol


def restored_d40():
    meta = read(NOMINAL / "collections/counterflow/d0040.json")
    path = NOMINAL / meta["checkpoint_file"]
    reuse = read(NOMINAL / "collection_reuse_manifest.json")
    if file_sha(path) != meta["checkpoint_sha256"] or file_sha(path) != reuse["files"][meta["checkpoint_file"]]:
        raise ValueError("locally generated checkpoint bytes changed")
    # Trusted local checkpoint was generated by the previous audited collection;
    # never deserialize a user-provided or external pickle.
    with path.open("rb") as stream:
        payload = pickle.load(stream)
    checkpoint = payload["checkpoint"]
    engine = CursorSimulation.from_checkpoint(checkpoint)
    checks = {"state": digest(asdict(engine.state)) == meta["state_sha256"],
        "cursor": json.loads(json.dumps(asdict(engine._cursor))) == meta["cursor"],
        "clock": engine.slow_controller.next_trigger_at == meta["next_slow_trigger_at"],
        "cache": json.loads(json.dumps(routing_cache_state(engine))) == meta["routing_cache"],
        "pool": json.loads(json.dumps([asdict(p) for p in payload["pool"]])) == meta["candidates"],
        "tape": digest([asdict(b) for b in payload["future"]]) == meta["future_sha256"],
        "pending_tape": sorted((asdict(b) for bags in engine._arrivals.values() for b in bags), key=lambda x: x["bag_id"])
            == sorted((asdict(b) for b in payload["future"]), key=lambda x: x["bag_id"])}
    if not all(checks.values()):
        raise ValueError("actual d40 checkpoint binding failed: " + str(checks))
    return engine, payload, meta, checks


def case_metrics(outcome, ledger):
    result = outcome["result"]
    return {"status": outcome["status"], "stopped_at": outcome["stopped_at"],
        "total_cost": None if result is None else result["total_cost"],
        "cost_components": None if result is None else result["cost_components"],
        "task_ledger_count": len(ledger), "observed": sum(row["observed"] for row in ledger),
        "completed": sum(row["completed_at"] is not None for row in ledger),
        "on_time": sum(row["completed_at"] is not None and row["completed_at"] <= row["deadline"] for row in ledger),
        "protected_expected": sum(row["protected"] for row in ledger),
        "protected_completed": sum(row["protected"] and row["completed_at"] is not None for row in ledger),
        "protected_on_time": sum(row["protected"] and row["completed_at"] is not None and row["completed_at"] <= row["deadline"] for row in ledger),
        "protected_unadmitted_decisions": outcome["last_cycle_state"]["protected_unadmitted_decisions"],
        "first_milestone_times": {k: v["time"] for k, v in outcome["milestones"].items()},
        "actual_loaded_generation_attempts": len(outcome["opportunities"]),
        "loaded_zero_candidate_attempts": sum(r["candidate_count"] == 0 for r in outcome["opportunities"]),
        "actual_selector_calls": len(outcome["selector_history_suffix"]),
        "forced_selector_interventions": int(outcome["forced_intervention"] is not None),
        "slow_actual_calls": len(outcome["slow_calls"]), "search_calls": outcome["search_calls"],
        "search_work": outcome["search_work"], "cycle_cpu_seconds_nested": outcome["cpu_seconds"],
        "cycle_wall_seconds_nested": outcome["wall_seconds"]}


def run_case(output, stage, row):
    started, cpu = perf_counter(), process_time()
    output = Path(output)
    target = output / stage / (row["case_id"] + ".json.gz")
    physical_call_started, outcome = False, None
    metadata, comparison, active_contract, ledger = {}, None, None, None
    try:
        verify(output)
        forced = None
        if row["kind"] == "checkpoint":
            engine, payload, meta, checks = restored_d40()
            forced = payload["pool"][row["candidate"]]
            all_bags = {**engine.state.bags, **{b.bag_id: b for b in payload["future"]}}
            endpoint = engine.state.now + 80
            metadata = {"checkpoint_sha256": meta["checkpoint_sha256"], "binding_checks": checks,
                        "future_sha256": meta["future_sha256"],
                        "intervention_action_key": actual_action_key(engine.state, forced, route_mode="next_edge")}
        else:
            scene = exact_original_scene(row["scene"])
            saved = read(output / "saved_tapes.json")[row["scene"]][row["tape_id"]]
            future = tuple(Bag(**b) for b in saved["future_engine_only"])
            if digest([asdict(b) for b in future]) != saved["sha256"]:
                raise ValueError("saved fixed sensitivity tape changed")
            base = build_engine(scene.initial, scene.forecasts, future, SPEC)
            enable_replay_cache(base)
            engine = CursorSimulation.from_base_checkpoint(base.checkpoint(), contract=base.control_contract)
            all_bags = {**scene.initial.bags, **{b.bag_id: b for b in future}}
            endpoint = scene.horizon
            metadata = {"original_saved_initial_exact": True, "future_sha256": saved["sha256"],
                        "forecast_sha256": digest([asdict(f) for f in scene.forecasts])}
        metadata["policy"] = install_supply_policy(engine, row["policy"])
        inner = engine.slow_controller.controller
        active_contract = {"schema": "ics_v3_active_supply_policy_overlay_v1",
            "authoritative_interpretation": "this active overlay supersedes differing supply fields in the inherited construction contract; fast selection and physical authority are unchanged",
            "base_construction_contract": engine.control_contract,
            "base_contract_is_not_the_modified_continuation_identity": row["policy"] != "old32",
            "policy": row["policy"], "controller_class": type(inner).__module__ + "." + type(inner).__name__,
            "effective_controller_scalar_parameters": {k: v for k, v in vars(inner).items()
                if isinstance(v, (str, int, float, bool)) or v is None},
            "source_sha256": {name: file_sha(SOURCE / name) for name in
                ("same_zone_supply.py", "same_zone_experiment.py", "run_same_zone_supply.py", "prebalance.py")},
            "centralized_authority": "same full W3 observable Snapshot; same-zone cross-owner proposals still require original ExecutionValidator permissions",
            "guard_contract": "new same-zone guard is defined by the pinned same_zone_supply.py and per-call proof/budget diagnostics; old cross-zone guard unchanged",
            "future_access": "engine only; slow receives only currently published original forecasts",
            "clock": {"period": engine.slow_controller.period, "next_trigger_at": engine.slow_controller.next_trigger_at}}
        active_contract["active_contract_sha256"] = digest(active_contract)
        physical_call_started = True
        outcome = run_observed_cycle(engine, all_bags, minimum_observation_at=endpoint, forced_candidate=forced)
        state = engine.state
        ledger = [{**asdict(b), "observed": k in state.bags, "load_time": state.load_times.get(k),
                   "completed_at": state.completed.get(k)} for k, b in sorted(all_bags.items())]
        replication_not_comparable = None
        if row["policy"] == "old32" and (outcome["result"] is None or outcome["original_endpoint"] is None):
            replication_not_comparable = "physical result or fixed endpoint missing; retain the actual failure/censor status"
        elif row["policy"] == "old32":
            if row["kind"] == "checkpoint":
                old = read(NOMINAL / "full" / f"counterflow_d0040_c{row['candidate']}.json.gz")
                comparison = {"result": compare_old_result(old["result"], outcome["result"]),
                    "searches_exact": old["searches"] == outcome["searches"],
                    "cache_before_exact": exact_json_value(old["cache_before"], outcome["cache_before"]),
                    "stop_exact": old["stopped_at"] == outcome["stopped_at"],
                    "h80": compare_old_result(old["endpoints"][str(endpoint)]["result"], outcome["original_endpoint"]["result"])}
            elif row["tape_id"] == "nominal":
                old = read(PRIMARY / row["scene"] / (row["scene"] + "_collection.json"))
                prefix = outcome["searches"][:outcome["original_endpoint"]["search_calls"]]
                comparison = {"result": compare_old_result(old["result"], outcome["original_endpoint"]["result"]),
                              "searches_exact": old["metadata"]["searches"] == prefix}
        record = {"case": row, "input_binding": metadata, "active_policy_contract": active_contract,
                  "old32_replication": comparison,
                  "replication_not_comparable": replication_not_comparable,
                  **outcome, "evaluation_ledger": ledger, "metrics": case_metrics(outcome, ledger)}
        write_gzip(target, record)
        verify(output)
        equal = None if comparison is None else all(v.get("equal", False) if isinstance(v, dict) else v for v in comparison.values())
        metrics = record["metrics"]
        status = metrics["status"] if equal is not False else "old32_replication_mismatch"
        return {**row, **metrics, "status": status, "old32_replication_equal": equal,
            "actual_physical_call": physical_call_started, "file": str(target.relative_to(output)),
            "sha256": file_sha(target), "invocation_cpu_seconds": process_time() - cpu,
            "invocation_wall_seconds": perf_counter() - started, "memory": memory_snapshot(),
            "sources_inputs_tests_unchanged": True}
    except Exception as error:
        failure_detail = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
        recovery_path, recovery_error = None, None
        if outcome is not None:
            recovery_path = target.with_suffix(".recovery.json")
            try:
                write_new_json(recovery_path, {"case": row, "failure": failure_detail,
                    "input_binding": metadata, "active_policy_contract": active_contract,
                    "outcome": outcome, "evaluation_ledger": ledger, "old32_replication": comparison})
            except Exception as recovery:
                recovery_error = {"type": type(recovery).__name__, "message": str(recovery),
                                  "traceback": traceback.format_exc()}
        failure = {**row, "status": "invocation_failure", "actual_physical_call": physical_call_started,
            "physical_result_status": None if outcome is None else outcome["status"],
            "retained_raw_file": str(target.relative_to(output)) if target.exists() else None,
            "recovered_outcome_file": str(recovery_path.relative_to(output)) if recovery_path and recovery_path.exists() else None,
            "recovery_failure": recovery_error, "failure": failure_detail,
            "invocation_cpu_seconds": process_time() - cpu, "invocation_wall_seconds": perf_counter() - started,
            "memory": memory_snapshot(), "sources_inputs_tests_unchanged": False}
        write_new_json(target.with_suffix(".failure.json"), failure)
        return failure


def run(output, stage):
    started, cpu = perf_counter(), process_time()
    output = Path(output).resolve()
    protocol = verify(output)
    rows = protocol["stage_planned_cases"][stage]
    directory = create_output_directory(output / stage)
    write_new_json(directory / "requested_cases.json", rows)
    results = []
    with ProcessPoolExecutor(max_workers=protocol["workers"]) as pool:
        jobs = {pool.submit(run_case, output, stage, row): row for row in rows}
        for job in as_completed(jobs):
            row = jobs[job]
            try:
                value = job.result()
            except Exception as error:
                value = {**row, "status": "worker_failure", "actual_physical_call": None,
                    "invocation_cpu_seconds": None, "invocation_wall_seconds": None,
                    "failure": {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()},
                    "resource_accounting": "worker expense and call-start status unknown; never imputed zero"}
                write_new_json(directory / (row["case_id"] + ".worker_failure.json"), value)
            results.append(value)
            print(json.dumps({"stage": stage, "case": row["case_id"], "status": value["status"],
                "recorded": len(results), "planned": len(rows), "cost": value.get("total_cost")}), flush=True)
    immutable_error = None
    try:
        verify(output)
    except Exception as error:
        immutable_error = {"type": type(error).__name__, "message": str(error)}
    summary = {"stage": stage, "planned_cases": len(rows), "rows": sorted(results, key=lambda r: r["case_id"]),
        "status_counts": dict(Counter(r["status"] for r in results)),
        "actual_physical_calls_recorded": sum(r["actual_physical_call"] is True for r in results),
        "unknown_physical_call_statuses": sum(r["actual_physical_call"] is None for r in results),
        "case_invocation_cpu_seconds_recorded": sum(r["invocation_cpu_seconds"] or 0 for r in results),
        "case_invocation_wall_seconds_sum_not_makespan": sum(r["invocation_wall_seconds"] or 0 for r in results),
        "unknown_resource_cases": sum(r["invocation_cpu_seconds"] is None for r in results),
        "complete_resource_accounting": all(r["invocation_cpu_seconds"] is not None for r in results),
        "parent_cpu_seconds": process_time() - cpu, "wall_makespan_seconds": perf_counter() - started,
        "sources_inputs_tests_unchanged": immutable_error is None, "immutability_failure": immutable_error}
    write_new_json(directory / "summary.json", summary)
    write_new_json(directory / "manifest.json", {str(p.relative_to(directory)): file_sha(p)
        for p in sorted(directory.rglob("*")) if p.is_file()})
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--stage", choices=STAGES)
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        prepare(args.output)
    if args.stage:
        summary = run(args.output, args.stage)
        print(json.dumps({k: summary[k] for k in ("stage", "planned_cases", "status_counts", "case_invocation_cpu_seconds_recorded", "wall_makespan_seconds")}))
    if not args.prepare and args.stage is None:
        parser.error("choose --prepare and/or --stage")
