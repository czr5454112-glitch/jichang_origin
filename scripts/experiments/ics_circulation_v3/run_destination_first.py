"""Frozen-model destination-first development comparison; no fitting or labels."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, replace
import json
from pathlib import Path
from time import perf_counter, process_time

from .destination_first import DestinationFirstSelector, LoggedReferenceSelector, OpportunityRecorder
from .experiment_protocol import create_output_directory
from .experiment_resources import memory_snapshot
from .nonlinear_learning import MLPValueModel
from .phase4_control import build_engine
from . import run_paired_recovery as old


SOURCES = tuple(dict.fromkeys(("destination_first.py", "run_destination_first.py", "experiment_resources.py", "routing_cache_contract.py", *old.SOURCES)))
TEST_FILE = Path(__file__).resolve().parents[3] / "tests/test_ics_circulation_v3_destination_first.py"
PROTOCOL = {
    "schema": "ics_v3_validated_destination_first_v1",
    "purpose": "Post-hoc motivated simple rule comparison on reused synthetic development streams; not dominance pruning or confirmation.",
    "streams": old.PROTOCOL["streams"], "spec": asdict(old.SPEC), "normal_candidate_count": 4,
    "realizations": ["nominal"] + [f"stress_{i}" for i in range(8)],
    "families": {"controls": 2, "r0_paired23_and_physical31": 12, "r1_own_physical31": 6, "shared_physical31": 6},
    "policies_per_stream": 26, "variants": ["original", "destination_first"], "units": 36,
    "episodes_per_unit": 52, "episodes": 1872, "new_labels": 0, "new_fits": 0,
    "rule": "At a real loaded decision boundary, choose the first complete zero-edge candidate in the normal pool only when current node is the bag destination and unchanged ExecutionValidator accepts it. Otherwise keep the original delegate choice.",
    "delegate": "Exactly one call per selector invocation; retain its original choice, scores and features before any override. Baseline/single-candidate shortcuts log no invented scores.",
    "authorization": "No direct state mutation, no generated replacement candidate, no cancellation; runtime revalidates and commits normally.",
    "freeze": "Predeclare before smoke/formal, freeze current dependency closure after coordination. Keep archived old sources and compare original replay physics to saved originals, without requiring current bytes to equal historical sources.",
    "units_immutable": "Each stream/tape unit contains all 26 policies times both variants; a completed unit may only be reused with identical protocol/input/source hashes.",
    "limits": ["All 36 tapes were used in earlier development; no fresh generalization claim.",
        "No seed, model, objective or schema selection and no new fitting.",
        "Rule changes the policy; it is not a proved globally dominating action or a new supplier requirement.",
        "Observational override counts have different policy trajectories and are not matched-state causal effects.",
        "Memory peaks cover the worker process lifetime including imports and previous units. Sum of worker peaks is not a simultaneous aggregate peak.",
        "CPU/wall are descriptive shared-machine measurements; there is no outcome-dependent time cutoff."],
}


def source_hashes():
    return {name: old.sha(Path(__file__).parent / name) for name in SOURCES}


def verify_archive(root, stages):
    """Verify historical evidence against its archive, never against live code."""
    root = Path(root)
    protocol = old.read(root / "protocol.json")
    for name, checksum in protocol["source_sha256"].items():
        if old.sha(root / "source_snapshot" / name) != checksum:
            raise ValueError("historical source snapshot changed: " + name)
    for stage in stages:
        folder = root / stage
        manifest = old.read(folder / "stage_manifest.json")
        if manifest["protocol_sha256"] != old.sha(root / "protocol.json") or manifest["source_changed_during_run"]:
            raise ValueError("historical stage was not frozen")
        if "input_manifest_sha256" in manifest and manifest["input_manifest_sha256"] != old.sha(root / "input_manifest.json"):
            raise ValueError("historical stage input manifest changed")
        actual = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
        if actual != set(manifest["files_sha256"]) | {"stage_manifest.json"}:
            raise ValueError("historical stage file denominator changed")
        if any(old.sha(folder / name) != checksum for name, checksum in manifest["files_sha256"].items()):
            raise ValueError("historical stage checksum mismatch")


def prepare(output, master, shared):
    master, shared = Path(master).resolve(), Path(shared).resolve()
    verify_archive(master, ("r0", "r1", "evaluation"))
    verify_archive(shared, ("fit", "evaluation"))
    original_summary, shared_summary = old.read(master / "evaluation/summary.json"), old.read(shared / "evaluation/summary.json")
    if original_summary["deployment_runs"] != 720 or shared_summary["deployment_runs"] != 288 or original_summary["failures"] or shared_summary["failures"]:
        raise ValueError("complete historical deployment denominators required")
    output = create_output_directory(output)
    old.save(output / "protocol.json", PROTOCOL)
    refs = {}
    for label, root, stages in (("master", master, ("r0", "r1", "evaluation")), ("shared", shared, ("fit", "evaluation"))):
        names = ["protocol.json"] + [f"{stage}/stage_manifest.json" for stage in stages]
        names += [f"{stage}/{name}" for stage in stages if stage != "evaluation" for name in ("frozen_models.json", "folds_and_bounds.json")]
        refs[label] = {"directory": str(root), "files_sha256": {name: old.sha(root / name) for name in names},
                       "archived_source_sha256": old.read(root / "protocol.json")["source_sha256"]}
    old.save(output / "input_manifest.json", refs)
    return {"predeclared": True, "source_frozen": False, "episodes": 1872}


def verify_inputs(output):
    refs = old.read(Path(output) / "input_manifest.json")
    for ref in refs.values():
        root = Path(ref["directory"])
        if any(old.sha(root / name) != checksum for name, checksum in ref["files_sha256"].items()):
            raise ValueError("historical inputs changed")
    return refs


def freeze_sources(output):
    output = Path(output)
    verify_inputs(output)
    if old.read(output / "protocol.json") != json.loads(json.dumps(PROTOCOL)):
        raise ValueError("predeclared protocol changed")
    hashes = source_hashes()
    folder = output / "source_snapshot"
    folder.mkdir()
    for name in SOURCES:
        (folder / name).write_bytes((Path(__file__).parent / name).read_bytes())
    (folder / "tests").mkdir()
    (folder / "tests" / TEST_FILE.name).write_bytes(TEST_FILE.read_bytes())
    refs = old.read(output / "input_manifest.json")
    historical_diff = {label: {name: {"old": value, "current": hashes.get(name)}
        for name, value in ref["archived_source_sha256"].items() if hashes.get(name) != value} for label, ref in refs.items()}
    old.save(output / "source_manifest.json", {"source_sha256": hashes,
        "test_sha256": {TEST_FILE.name: old.sha(TEST_FILE)},
        "historical_source_differences": historical_diff, "protocol_sha256": old.sha(output / "protocol.json"),
        "input_manifest_sha256": old.sha(output / "input_manifest.json")})
    return {"source_frozen": True, "source_count": len(hashes), "historical_source_differences": historical_diff}


def verify_frozen(output):
    output = Path(output)
    if old.read(output / "protocol.json") != json.loads(json.dumps(PROTOCOL)):
        raise ValueError("protocol changed")
    manifest = old.read(output / "source_manifest.json")
    if manifest["source_sha256"] != source_hashes():
        raise ValueError("current dependency sources changed")
    if manifest["protocol_sha256"] != old.sha(output / "protocol.json") or manifest["input_manifest_sha256"] != old.sha(output / "input_manifest.json"):
        raise ValueError("protocol/input changed after freeze")
    if any(old.sha(output / "source_snapshot" / n) != h for n, h in manifest["source_sha256"].items()):
        raise ValueError("new source archive changed")
    if old.sha(TEST_FILE) != manifest["test_sha256"][TEST_FILE.name] or old.sha(output / "source_snapshot/tests" / TEST_FILE.name) != manifest["test_sha256"][TEST_FILE.name]:
        raise ValueError("frozen targeted tests changed")
    return verify_inputs(output)


def policy_options(refs, stream):
    options = [(kind, None, None, None, "master") for kind in ("baseline", "timed")]
    for family, source, stage, expected in (("r0", "master", "r0", 12), ("r1", "master", "r1", 6), ("shared", "shared", "fit", 6)):
        root = Path(refs[source]["directory"])
        models, meta = old.read(root / stage / "frozen_models.json"), old.read(root / stage / "folds_and_bounds.json")
        selected = []
        for name, model in models.items():
            fold = meta["folds"][name]
            if fold["held_out_stream"] == stream:
                selected.append((family + "__" + name.split("__", 1)[1], MLPValueModel.from_dict(model), meta["bounds"][name], fold["schema"], source))
        if len(selected) != expected:
            raise ValueError("frozen policy family denominator differs")
        options.extend(sorted(selected, key=lambda row: row[0]))
    if len(options) != 26 or len({option[0] for option in options}) != 26:
        raise ValueError("missing or duplicate frozen policies")
    return options


def semantic(value):
    if isinstance(value, dict):
        return {k: semantic(v) for k, v in value.items() if not k.endswith("_ms") and k not in {"wall_seconds", "cpu_seconds"}}
    if isinstance(value, (list, tuple)):
        return [semantic(v) for v in value]
    return value


PHYSICS_FIELDS = ("result", "boundaries", "route_history", "slow_history", "slow_trigger_times")


def compare_physics(actual, expected):
    # Process-global topology warmth changes search work, not reservations or
    # chosen routes. Keep that discrepancy explicitly, rather than calling the
    # entire non-timing record identical or allowing it to mask real changes.
    left, right = {}, {}
    for key in PHYSICS_FIELDS:
        left[key], right[key] = semantic(actual.get(key)), semantic(expected.get(key))
    strict = [key for key in PHYSICS_FIELDS if left[key] != right[key]]
    search_work = []
    for side, projection in (("actual", left), ("old", right)):
        for event in projection["slow_history"] or []:
            if "search_expansions" in event.get("diagnostics", {}):
                count = event["diagnostics"].pop("search_expansions")
                search_work.append({"side": side, "time": event["trigger_time"], "search_expansions": count})
    differences = [key for key in PHYSICS_FIELDS if left[key] != right[key]]
    return {"equal": not differences, "differing_fields": differences,
            "non_timing_record_differing_fields": strict,
            "slow_search_work": search_work if strict else [],
            "excluded": "wall/CPU timings, *_ms counters, and separately retained slow search_expansions; contracts/source metadata are not physical fields"}


def deploy(scene, policy, model, bounds, schema, *, enabled):
    wall, cpu = perf_counter(), process_time()
    delegate = (old.RecoverySelector(model, bounds, scene.forecasts, schema=schema) if model else
                LoggedReferenceSelector(policy, scene.forecasts, old.SPEC.planning_horizon))
    wrapper = DestinationFirstSelector(delegate, enabled=enabled, route_mode=old.SPEC.route_mode)
    manifest = {"implementation": "DestinationFirstSelector", "enabled": enabled,
        "delegate": old.selector_manifest(model, bounds, schema) if model else {"implementation": "LoggedReferenceSelector", "kind": policy}}
    engine = build_engine(scene.initial, scene.forecasts, scene.future_bags, replace(old.SPEC, routing="external"),
                          route_selector=wrapper, selector_manifest=manifest)
    engine._generator = OpportunityRecorder(engine._generator)
    boundaries = []
    while engine.state.now < scene.horizon:
        state = engine.observe()
        boundaries.append({"time": state.now, "state_sha256": old.digest(asdict(state)), "completed": len(state.completed), "visible_bags": sorted(state.bags)})
        engine.advance(state.now + 1)
    result = engine.result()
    wrapper = engine.route_selector.selector
    routed = {(h["time"], h["bag_id"], h["tray_id"]): h for h in engine.route_selector.history}
    if len(routed) != len(engine.route_selector.history):
        raise ValueError("ambiguous loaded invocation identity")
    opportunities = engine._generator.history
    for item in opportunities:
        routed_item = routed.get((item["time"], item["bag_id"], item["tray_id"]))
        item["authorized_candidate_count"] = routed_item["candidate_count"] if routed_item else 0
    if sum(o["authorized_candidate_count"] > 0 for o in opportunities) != len(routed):
        raise ValueError("loaded attempt denominator does not match selector calls")
    bags = {**scene.initial.bags, **{b.bag_id: b for b in scene.future_bags}}
    history = wrapper.delegate.history if model else []
    metrics = {"status": "completed_run", "total_cost": result.total_cost, "cost_components": result.cost_components,
        "scheduled_bags": len(bags), "completed": len(result.completed), "uncompleted": list(result.uncompleted_bag_ids),
        "on_time": sum(k in result.completed and result.completed[k] <= b.deadline for k, b in bags.items()),
        "selector_calls": len(wrapper.history), "loaded_attempts": len(opportunities),
        "zero_authorized_loaded_attempts": sum(o["authorized_candidate_count"] == 0 for o in opportunities),
        "at_destination_loaded_attempts": sum(o["at_destination"] for o in opportunities),
        "eligible_unload_calls": sum(h["eligible"] for h in wrapper.history),
        "no_legal_unload_calls": sum(h["at_destination"] and not h["eligible"] for h in wrapper.history),
        "overrides": sum(h["overridden"] for h in wrapper.history),
        "candidate_feature_vectors": sum(len(h["features"]) for h in history),
        "out_of_range_vectors": sum(bool(v) for h in history for v in h["outside_training_range"]),
        "wall_seconds": perf_counter() - wall, "cpu_seconds": process_time() - cpu}
    return {"metrics": metrics, "control_contract": engine.control_contract, "result": asdict(result), "boundaries": boundaries,
        "route_history": engine.route_selector.history, "learned_feature_history": history,
        "delegate_history": wrapper.delegate.history, "destination_first_history": wrapper.history,
        "loaded_opportunities": opportunities, "slow_history": engine.slow_controller.history,
        "slow_trigger_times": engine.slow_controller.trigger_times}


def unit_scenes():
    return {scene.name + "__" + realization: (realization, scene)
            for base in old.sustained_scenes() for realization, scene in old.deployment_scenes(base)}


def verify_unit(output, unit):
    folder = Path(output) / "units" / unit
    manifest = old.read(folder / "manifest.json")
    if manifest["source_manifest_sha256"] != old.sha(Path(output) / "source_manifest.json"):
        raise ValueError("unit source freeze differs")
    if {p.name for p in folder.iterdir() if p.is_file()} != set(manifest["files_sha256"]) | {"manifest.json"}:
        raise ValueError("unit file denominator changed")
    if any(old.sha(folder / n) != h for n, h in manifest["files_sha256"].items()):
        raise ValueError("unit artifact changed")
    return old.read(folder / "summary.json")


def run_unit(output, unit):
    output = Path(output)
    wall, cpu, mem_before = perf_counter(), process_time(), memory_snapshot()
    refs = verify_frozen(output)
    folder = output / "units" / unit
    if folder.exists():
        return verify_unit(output, unit)
    realization, scene = unit_scenes()[unit]
    options = policy_options(refs, scene.name)
    folder.mkdir(parents=True)
    scene_input = old.scene_inputs(scene)
    input_sha = old.digest(scene_input)
    old.save(folder / "inputs.json", {"input_sha256": input_sha, **scene_input})
    records, comparisons = [], []
    for policy, model, bounds, schema, archive in options:
        previous_folder = Path(refs[archive]["directory"]) / "evaluation" / unit
        previous_input = old.read(previous_folder / "inputs.json")
        previous_input.pop("input_sha256", None)
        if old.digest(previous_input) != input_sha:
            raise ValueError("previous tape/input differs")
        for variant in PROTOCOL["variants"]:
            start, run_cpu = perf_counter(), process_time()
            try:
                actual = deploy(scene, policy, model, bounds, schema, enabled=variant == "destination_first")
                if variant == "original":
                    previous = previous_folder / (policy + ".json")
                    comparison = {"policy": policy, "old_record": str(previous), "old_record_sha256": old.sha(previous),
                                  **compare_physics(actual, old.read(previous))}
                    comparisons.append(comparison)
                    actual["old_physics_comparison"] = comparison
            except Exception as error:
                actual = {"metrics": {"status": "failed_run", "total_cost": None, "completed": None,
                    "scheduled_bags": len(scene.initial.bags) + len(scene.future_bags), "on_time": None,
                    "wall_seconds": perf_counter() - start, "cpu_seconds": process_time() - run_cpu,
                    "failure": {"type": type(error).__name__, "reason": str(error)}}}
            actual["metrics"].update(stream=scene.name, realization=realization, policy=policy, variant=variant, input_sha256=input_sha)
            records.append(actual["metrics"])
            old.save(folder / (policy + "__" + variant + ".json"), actual)
    verify_frozen(output)
    summary = {"unit": unit, "episodes": len(records), "records": records,
        "original_physics_comparisons": comparisons, "original_physics_mismatches": [v for v in comparisons if not v["equal"]],
        "failures": [v for v in records if v["status"] != "completed_run"],
        "wall_seconds": perf_counter() - wall, "cpu_seconds": process_time() - cpu,
        "memory_before": mem_before, "memory_after": memory_snapshot()}
    old.save(folder / "summary.json", summary)
    old.save(folder / "manifest.json", {"source_manifest_sha256": old.sha(output / "source_manifest.json"),
        "files_sha256": {p.name: old.sha(p) for p in sorted(folder.iterdir()) if p.is_file()}})
    print(json.dumps({"unit": unit, "episodes": len(records), "failures": len(summary["failures"]), "old_mismatches": len(summary["original_physics_mismatches"])}), flush=True)
    return summary


def merge(output):
    output = Path(output)
    refs = verify_frozen(output)
    units = [verify_unit(output, unit) for unit in unit_scenes()]
    records = [row for unit in units for row in unit["records"]]
    if len(records) != 1872 or any(unit["episodes"] != 52 for unit in units):
        raise ValueError("incomplete destination-first denominator")
    for label, stages in (("master", ("r0", "r1", "evaluation")), ("shared", ("fit", "evaluation"))):
        verify_archive(refs[label]["directory"], stages)
    result = {"episodes": len(records), "units": len(units), "records": records,
        "scheduled_bag_denominator": sum(r["scheduled_bags"] for r in records),
        "completed_bags": sum(r["completed"] or 0 for r in records),
        "on_time_bags": sum(r["on_time"] or 0 for r in records),
        "failures": [r for r in records if r["status"] != "completed_run"],
        "original_physics_comparisons": sum(len(u["original_physics_comparisons"]) for u in units),
        "original_physics_mismatches": [r for u in units for r in u["original_physics_mismatches"]],
        "unit_cpu_seconds_sum": sum(u["cpu_seconds"] for u in units),
        "unit_wall_seconds_sum_not_makespan": sum(u["wall_seconds"] for u in units),
        "memory_by_unit": {u["unit"]: {"before": u["memory_before"], "after": u["memory_after"]} for u in units},
        "source_changed_during_run": False, "new_labels": 0, "new_fits": 0, "limits": PROTOCOL["limits"]}
    old.save(output / "summary.json", result)
    old.save(output / "manifest.json", {"source_manifest_sha256": old.sha(output / "source_manifest.json"),
        "summary_sha256": old.sha(output / "summary.json"),
        "unit_manifest_sha256": {unit: old.sha(output / "units" / unit / "manifest.json") for unit in unit_scenes()}})
    return result


def run_all(output, workers=1):
    if type(workers) is not int or not 1 <= workers <= 4:
        raise ValueError("worker budget must be an integer in 1..4")
    verify_frozen(output)
    if workers == 1:
        for unit in unit_scenes():
            run_unit(output, unit)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            jobs = [pool.submit(run_unit, str(output), unit) for unit in unit_scenes()]
            for job in as_completed(jobs):
                job.result()
    return merge(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--stage", required=True, choices=("prepare", "freeze", "unit", "merge", "all"))
    parser.add_argument("--master", type=Path)
    parser.add_argument("--shared", type=Path)
    parser.add_argument("--unit")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    if args.stage == "prepare":
        if args.master is None or args.shared is None:
            parser.error("prepare requires both archived --master and --shared")
        result = prepare(args.output, args.master, args.shared)
    elif args.stage == "freeze":
        result = freeze_sources(args.output)
    elif args.stage == "unit":
        if args.unit not in unit_scenes():
            parser.error("unit must be one declared stream__realization")
        result = run_unit(args.output, args.unit)
    elif args.stage == "all":
        result = run_all(args.output, args.workers)
    else:
        result = merge(args.output)
    print(json.dumps({k: v for k, v in result.items() if k not in {"records", "memory_by_unit"}}, indent=2))
    raise SystemExit(int(bool(result.get("failures") or result.get("original_physics_mismatches"))))
