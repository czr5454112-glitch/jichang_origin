"""Complete 36-tape x four-cell continuation/tie development ablation."""
import argparse
import ast
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, replace
import gzip
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter, process_time
import traceback

from .empty_factorial import FACTORS, SETTINGS, build_empty_factorial_engine
from .experiment_protocol import create_output_directory, write_new_json
from .experiment_resources import memory_snapshot
from .label_stability import sustained_scenes
from .network_full_cycle import cycle_state, forecast_expiry, physical_result
from .phase4_control import ControlSpec
from .run_empty_improvement import endpoint
from .run_public_rollout import deployment_tapes


CODE = Path(__file__).parent
SPEC = ControlSpec(routing="timed", planning_horizon=20, slow_period=2)
OLD = Path("outputs/experiments/ics_circulation_v3/phase4_w3_empty_improvement_20261010")


def json_equal(left, right):
    """Compare Python dataclass projections to frozen JSON without field loss."""
    return json.loads(json.dumps(left)) == json.loads(json.dumps(right))


def sources():
    found, queue = set(), [Path(__file__).name, "__init__.py"]
    while queue:
        name = queue.pop()
        if name in found:
            continue
        found.add(name)
        tree = ast.parse((CODE / name).read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 1:
                modules = [node.module.split(".")[0]] if node.module else [a.name for a in node.names]
                queue.extend(m + ".py" for m in modules if (CODE / (m + ".py")).is_file() and m + ".py" not in found)
    return {name: sha256((CODE / name).read_bytes()).hexdigest() for name in sorted(found)}


def deploy(scene, factors):
    wall, cpu = perf_counter(), process_time()
    engine = build_empty_factorial_engine(scene, factors, spec=SPEC, settings=SETTINGS)
    bags = dict(scene.initial.bags)
    for bag in scene.future_bags:
        if bag.bag_id in bags:
            raise ValueError("duplicate task identity")
        bags[bag.bag_id] = bag
    expiry = forecast_expiry(engine)
    h80 = scene.initial.now + 80
    cap = max(h80, expiry, max((b.arrival for b in bags.values()), default=scene.initial.now)) + 240
    quiet_since = quiet_triggers = None
    endpoints, milestones = {}, {}
    status = "tick_cap_censored"
    while engine.state.now < cap:
        engine.advance(engine.state.now + 1)
        state, now = cycle_state(engine, bags, expiry), engine.state.now
        if now == h80:
            endpoints["h80"] = endpoint(engine, bags, expiry)
        for flag in ("task_complete", "transport_drained"):
            if state[flag] and flag not in milestones:
                milestones[flag] = now
        if not (state["transport_drained"] and state["forecast_expired"]):
            quiet_since = quiet_triggers = None
        elif quiet_since is None:
            quiet_since, quiet_triggers = now, len(engine.slow_controller.trigger_times)
        elif now >= h80 and now - quiet_since >= SPEC.slow_period and len(engine.slow_controller.trigger_times) > quiet_triggers:
            status = "controller_quiescent"
            milestones["controller_quiescent"] = {"time": now, "quiet_since": quiet_since,
                "actual_slow_triggers": len(engine.slow_controller.trigger_times) - quiet_triggers}
            break
    endpoints["final"] = endpoint(engine, bags, expiry)
    history = engine.slow_controller.history
    diagnostics = [h["diagnostics"] for h in history]
    proxy = [r for d in diagnostics for r in d["scored_actions"]]
    metrics = {"status": status, "h80": endpoints["h80"]["metrics"], "final": endpoints["final"]["metrics"],
        "stopped_at": engine.state.now, "physical_proxy_calls": len(proxy),
        "proxy_statuses": dict(Counter(r["status"] for r in proxy)),
        "changed_greedy_actions": sum(d["actual_sequence_changed"] for d in diagnostics),
        "fallback_calls": sum(d["fallback_to_greedy"] for d in diagnostics),
        "internal_search_calls": sum(d["greedy_diagnostics"]["search_calls"] + d["proposal_search_calls"]
            + sum(r["search_calls"] for r in d["scored_actions"]) for d in diagnostics),
        "internal_search_work": sum(d["greedy_diagnostics"]["search_expansions"] + d["proposal_search_work"]
            + sum(r["search_work"] for r in d["scored_actions"]) for d in diagnostics),
        "omitted_identical_actions": sum(d.get("mandatory_identical_actions_not_simulated", 0) for d in diagnostics),
        "unscored_enumerated_actions": sum(d["unscored_enumerated_actions"] for d in diagnostics),
        "unexplored_sequence_nodes": sum(d["unexplored_sequence_nodes"] for d in diagnostics),
        "unsearched_requests": sum(d["proposal_unsearched_requests"] for d in diagnostics),
        "proposal_pool_discarded_valid": sum(d["proposal_pool_discarded_valid"] for d in diagnostics),
        "process_cpu_seconds": process_time() - cpu, "wall_seconds": perf_counter() - wall,
        "memory": memory_snapshot()}
    return {"metrics": metrics, "endpoints": endpoints, "milestones": milestones, "cap_at": cap,
        "forecast_expired_at": expiry, "slow_history": history,
        "slow_trigger_times": engine.slow_controller.trigger_times,
        "route_history": engine.route_selector.history, "control_contract": engine.control_contract}


def worker(output, scene_index, tape_index, factor_index, expected_sources):
    wall, cpu = perf_counter(), process_time()
    factors = FACTORS[factor_index]
    identity = f"s{scene_index}_t{tape_index}_{factors.policy_id}"
    if sources() != expected_sources:
        raise ValueError("source changed before worker")
    original = sustained_scenes()[scene_index]
    tape_name, tape = deployment_tapes(original)[tape_index]
    scene = replace(original, future_bags=tape)
    record = None
    try:
        record = deploy(scene, factors)
        if factor_index == 0:
            old_path = OLD / "cases" / f"s{scene_index}_t{tape_index}_empty12_h40.json.gz"
            old_bytes = old_path.read_bytes()
            old = json.loads(gzip.decompress(old_bytes))
            equal = {end: physical_result(record["endpoints"][end]["result"]) == physical_result(old["endpoints"][end]["result"])
                     for end in ("h80", "final")}
            equal["route_history"] = json_equal(record["route_history"], old["route_history"])
            equal["slow_actions"] = json_equal([(h["trigger_time"], h["proposals"]) for h in record["slow_history"]], [
                (h["trigger_time"], h["proposals"]) for h in old["slow_history"]])
            record["original_default_reproduction"] = {"file": str(old_path), "sha256": sha256(old_bytes).hexdigest(), "equal": equal}
            if not all(equal.values()):
                raise ValueError("default hook behavior failed original frozen physical reproduction")
    except Exception as error:
        if record is None:
            record = {"metrics": {"status": "execution_failure", "scheduled": len(scene.initial.bags) + len(tape),
                "process_cpu_seconds": process_time() - cpu, "wall_seconds": perf_counter() - wall}}
        else:
            record["metrics"]["status"] = "artifact_verification_failure"
        record["failure"] = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
    record.update(identity=identity, scene=scene.name, tape=tape_name, policy=factors.policy_id, factors=asdict(factors),
        source_changed_during_case=sources() != expected_sources,
        invocation_cpu_before_gzip=process_time() - cpu, invocation_wall_before_gzip=perf_counter() - wall)
    path = Path(output) / "cases" / (identity + ".json.gz")
    with gzip.open(path, "xt", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return {"identity": identity, "scene": scene.name, "tape": tape_name, "policy": factors.policy_id,
        **record["metrics"], "source_changed_during_case": record["source_changed_during_case"],
        "file": path.name, "sha256": sha256(path.read_bytes()).hexdigest(),
        "invocation_cpu_seconds": process_time() - cpu, "invocation_wall_seconds": perf_counter() - wall}


def run(output, workers=6):
    output = create_output_directory(output).resolve()
    wall, cpu = perf_counter(), process_time()
    frozen = sources()
    (output / "cases").mkdir()
    (output / "source_snapshot").mkdir()
    for name in frozen:
        (output / "source_snapshot" / name).write_bytes((CODE / name).read_bytes())
    tests = ("test_ics_circulation_v3_empty_improvement.py", "test_ics_circulation_v3_empty_improvement_audit.py",
             "test_ics_circulation_v3_empty_factorial.py")
    test_root = Path(__file__).resolve().parents[3] / "tests"
    (output / "test_snapshot").mkdir()
    test_hashes = {}
    for name in tests:
        data = (test_root / name).read_bytes()
        (output / "test_snapshot" / name).write_bytes(data)
        test_hashes[name] = sha256(data).hexdigest()
    inputs = []
    for si, original in enumerate(sustained_scenes()):
        for ti, (tape_name, tape) in enumerate(deployment_tapes(original)):
            inputs.append({"scene_index": si, "tape_index": ti, "scene": original.name, "tape": tape_name,
                "initial": asdict(original.initial), "published_forecasts": [asdict(f) for f in original.forecasts],
                "actual_tasks_event_engine_only": [asdict(b) for b in tape]})
    # The old immutable manifest is JSON, so normalize tuple-valued dataclass
    # fields before the exact structural comparison (no identity fields lost).
    inputs = json.loads(json.dumps(inputs))
    old_inputs = json.loads((OLD / "inputs.json").read_text())
    if inputs != old_inputs:
        raise ValueError("new factorial input matrix differs from original 36 tapes")
    write_new_json(output / "inputs.json", inputs)
    write_new_json(output / "protocol.json", {"schema": "ics_empty_continuation_tie_factorial_v1",
        "development_only": True, "planned_episodes": 144, "units": len(inputs), "factors": [asdict(f) for f in FACTORS],
        "spec": asdict(SPEC), "settings": asdict(SETTINGS), "workers": workers,
        "source_sha256": frozen, "tests_sha256": test_hashes,
        "information": "same currently published point forecast; real tasks only enter outer Simulation",
        "common_domain": "same mandatory greedy/no-transfer, fair empty candidates, depth2, rollout12,score40,query/work caps",
        "factor_continuation": "timed plus periodic greedy vs first of normal K4 plus reactive and no future slow; both planning20 and exact after-slow cursor",
        "factor_tie": "keep incumbent vs fewer transfers then unchanged physical action key within absolute tolerance1e-9",
        "legacy_difference": "earliest proxy is K4/planning20; old legacy used K1/search_horizon40 and snapshot restart",
        "actual_control": "all four cells use timed K4 routing and repeating causal slow optimizer",
        "stopping": "same h80 and full-tape transport/forecast TTL quiescence as original252, max tail240",
        "reproduction": "every timed_greedy/incumbent full physical endpoint,routehistory and slow action sequence must match old empty12_h40",
        "original_inputs_sha256": sha256((OLD / "inputs.json").read_bytes()).hexdigest(),
        "claim": "complete development mechanism ablation; do not retain only the best cell or claim independent confirmation"})
    rows = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(worker, str(output), i["scene_index"], i["tape_index"], fi, frozen): (i, fi)
                for number, i in enumerate(inputs)
                for fi in (range(4) if number % 2 == 0 else reversed(range(4)))}
        for job in as_completed(jobs):
            try:
                row = job.result()
            except Exception as error:
                inp, fi = jobs[job]
                row = {"identity": f"s{inp['scene_index']}_t{inp['tape_index']}_{FACTORS[fi].policy_id}",
                    "scene": inp["scene"], "tape": inp["tape"], "policy": FACTORS[fi].policy_id,
                    "status": "worker_failure", "invocation_cpu_seconds": None, "invocation_wall_seconds": None,
                    "source_changed_during_case": sources() != frozen,
                    "failure": {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}}
                path = output / "cases" / (row["identity"] + ".worker_failure.json")
                write_new_json(path, row)
                row.update(file=path.name, sha256=sha256(path.read_bytes()).hexdigest())
            rows.append(row)
            print(json.dumps({k: row[k] for k in ("identity", "status", "invocation_cpu_seconds")}), flush=True)
    summary = {"planned_episodes": 144, "recorded_episodes": len(rows), "rows": sorted(rows, key=lambda r: r["identity"]),
        "statuses": dict(Counter(r["status"] for r in rows)), "source_changed_during_run": sources() != frozen,
        "case_source_changed": any(r["source_changed_during_case"] for r in rows),
        "case_invocation_cpu_seconds_recorded": sum(r["invocation_cpu_seconds"] or 0 for r in rows),
        "cases_with_unavailable_invocation_accounting": sum(r["invocation_cpu_seconds"] is None for r in rows),
        "coordinator_wall_seconds": perf_counter() - wall, "parent_cpu_seconds": process_time() - cpu}
    write_new_json(output / "summary.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    result = run(args.output, args.workers)
    raise SystemExit(int(result["source_changed_during_run"] or result["case_source_changed"]
        or result["statuses"].get("execution_failure", 0) or result["statuses"].get("worker_failure", 0)
        or result["statuses"].get("artifact_verification_failure", 0)))
