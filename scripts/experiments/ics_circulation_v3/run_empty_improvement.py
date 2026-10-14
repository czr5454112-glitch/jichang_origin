"""Frozen paired development comparison of direct empty-control improvement."""
from __future__ import annotations

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

from .empty_improvement import EmptyImprovementSettings, build_empty_improvement_engine
from .experiment_protocol import create_output_directory, write_new_json
from .experiment_resources import memory_snapshot
from .label_stability import sustained_scenes
from .network_full_cycle import cycle_state, forecast_expiry
from .phase4_control import ControlSpec, build_engine, digest
from .prebalance_reference import BoundedForecastPrebalancer
from .public_rollout import build_public_rollout_engine
from .routing_cache_contract import enable_replay_cache
from .run_public_rollout import deployment_tapes


POLICIES = ("greedy", "legacy_empty12", "public_fast4", "empty2_h40",
            "empty12_h40", "empty24_h40", "empty24_h80")
SPEC = ControlSpec(routing="timed", planning_horizon=20, slow_period=2)
CODE = Path(__file__).parent


def source_files():
    """Freeze the transitive local import closure, including function imports."""
    found, queue = set(), [Path(__file__).name]
    while queue:
        name = queue.pop()
        if name in found:
            continue
        found.add(name)
        tree = ast.parse((CODE / name).read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 1:
                modules = [node.module.split(".")[0]] if node.module else [a.name for a in node.names]
                for module in modules:
                    relative = module + ".py"
                    if (CODE / relative).is_file() and relative not in found:
                        queue.append(relative)
    return sorted(found)


def source_hashes():
    return {n: sha256((CODE / n).read_bytes()).hexdigest() for n in source_files()}


def build_case(scene, policy):
    if policy == "greedy":
        return build_empty_improvement_engine(scene, SPEC, enabled=False)
    if policy == "public_fast4":
        engine = build_public_rollout_engine(scene, SPEC)
        enable_replay_cache(engine)
        return engine
    if policy == "legacy_empty12":
        engine = build_engine(scene.initial, scene.forecasts, scene.future_bags, SPEC)
        engine.slow_controller.controller = BoundedForecastPrebalancer(
            planning_horizon=20, score_horizon=40, max_rollouts=12,
            proxy_route_mode="next_edge", generator_factory=engine.generator_factory)
        contract = engine.control_contract
        contract["continuation"]["prebalancer"] = "BoundedForecastPrebalancer"
        contract["continuation"]["reference_continuation"] = "earliest_reactive_no_slow"
        contract["continuation"]["slow_proposal_budget"] = 2
        contract["continuation"]["reference_settings"] = {
            "planning_horizon": 20, "score_horizon": 40, "max_rollouts": 12,
            "max_transfer_depth": 2, "paths_per_request": 2, "max_pool_per_state": 8,
            "max_search_calls": 32, "proxy_route_mode": "next_edge",
            "proxy_simulation_search_horizon": 40,
            "proposal_generator_default_horizon": 20,
            "proxy_slow_controller": None, "proxy_reactive_empty_dispatch": True}
        contract["continuation_sha256"] = digest(contract["continuation"])
        contract.pop("contract_sha256", None)
        contract["contract_sha256"] = digest(contract)
        enable_replay_cache(engine)
        return engine
    if policy not in POLICIES:
        raise ValueError("unknown predeclared policy")
    count, horizon = policy.removeprefix("empty").split("_h")
    return build_empty_improvement_engine(scene, SPEC, settings=EmptyImprovementSettings(
        max_rollouts=int(count), score_horizon=int(horizon)))


def endpoint(engine, bags, expiry):
    result = engine.result()
    completed = result.completed
    return {"time": engine.state.now, "result": asdict(result),
        "cycle": cycle_state(engine, bags, expiry),
        "metrics": {"total_cost": result.total_cost, "cost_components": result.cost_components,
            "scheduled": len(bags), "completed": len(completed),
            "unfinished": sorted(set(bags) - completed.keys()),
            "on_time": sum(k in completed and completed[k] <= b.deadline for k, b in bags.items()),
            "completion_times": dict(completed),
            "flow_times_completed": {k: completed[k] - bags[k].arrival for k in completed},
            "censored_elapsed": {k: max(0, engine.state.now - b.arrival) for k, b in bags.items() if k not in completed},
            "protected_scheduled": sum(b.protected for b in bags.values()),
            "protected_completed": sum(b.protected and k in completed for k, b in bags.items()),
            "protected_on_time": sum(b.protected and k in completed and completed[k] <= b.deadline for k, b in bags.items())}}


def deploy(scene, policy):
    wall, cpu = perf_counter(), process_time()
    engine = build_case(scene, policy)
    bags = dict(scene.initial.bags)
    for bag in scene.future_bags:
        if bag.bag_id in bags:
            raise ValueError("duplicate evaluation task identity")
        bags[bag.bag_id] = bag
    expiry = forecast_expiry(engine)
    h80 = scene.initial.now + 80
    cap = max(h80, expiry, max((b.arrival for b in bags.values()), default=scene.initial.now)) + 240
    quiet_since = quiet_triggers = None
    endpoints, milestones = {}, {}
    status = "tick_cap_censored"
    while engine.state.now < cap:
        engine.advance(engine.state.now + 1)
        state = cycle_state(engine, bags, expiry)
        now = engine.state.now
        if now == h80:
            endpoints["h80"] = endpoint(engine, bags, expiry)
        for flag in ("task_complete", "transport_drained"):
            if state[flag] and flag not in milestones:
                milestones[flag] = now
        quiet = state["transport_drained"] and state["forecast_expired"]
        if not quiet:
            quiet_since = quiet_triggers = None
        elif quiet_since is None:
            quiet_since = now
            quiet_triggers = len(engine.slow_controller.trigger_times)
        elif (now >= h80 and now - quiet_since >= SPEC.slow_period
              and len(engine.slow_controller.trigger_times) > quiet_triggers):
            status = "controller_quiescent"
            milestones["controller_quiescent"] = {"time": now, "quiet_since": quiet_since,
                "actual_slow_triggers": len(engine.slow_controller.trigger_times) - quiet_triggers}
            break
    endpoints["final"] = endpoint(engine, bags, expiry)
    slow = engine.slow_controller.history
    rollout_rows = [r for item in slow for r in item.get("diagnostics", {}).get("scored_actions", ())]
    public = getattr(engine.route_selector.selector, "history", []) if policy == "public_fast4" else []
    metrics = {"status": status, "h80": endpoints["h80"]["metrics"],
        "final": endpoints["final"]["metrics"], "stopped_at": engine.state.now,
        "slow_triggers": len(slow), "changed_greedy_actions": sum(
            bool(s["diagnostics"].get("actual_sequence_changed")) for s in slow),
        "selected_action_indices": dict(Counter(str(s["diagnostics"].get("selected_action_index")) for s in slow)),
        "proxy_statuses": dict(Counter(r.get("status", "legacy_recorded") for r in rollout_rows)),
        "physical_slow_proxy_rollouts": len(rollout_rows),
        "physical_fast_proxy_rollouts": sum(len(r["rollouts"]) for r in public),
        "new_method_internal_search_calls": sum(
            s["diagnostics"].get("greedy_diagnostics", {}).get("search_calls", 0)
            + s["diagnostics"].get("proposal_search_calls", 0)
            + sum(r.get("search_calls", 0) for r in s["diagnostics"].get("scored_actions", ()))
            for s in slow) if policy.startswith("empty") else None,
        "new_method_internal_search_work": sum(
            s["diagnostics"].get("greedy_diagnostics", {}).get("search_expansions", 0)
            + s["diagnostics"].get("proposal_search_work", 0)
            + sum(r.get("search_work", 0) for r in s["diagnostics"].get("scored_actions", ()))
            for s in slow) if policy.startswith("empty") else None,
        "internal_count_scope": "new method: greedy proposal + enhancement proposal + every proxy query; excludes actual outer execution, not instruction or hard wall budget",
        "fallback_calls": sum(bool(s["diagnostics"].get("fallback_to_greedy")) for s in slow),
        "process_cpu_seconds": process_time() - cpu, "wall_seconds": perf_counter() - wall,
        "memory": memory_snapshot()}
    return {"metrics": metrics, "endpoints": endpoints, "milestones": milestones,
        "cap_at": cap, "forecast_expired_at": expiry, "slow_history": slow,
        "slow_trigger_times": engine.slow_controller.trigger_times,
        "route_history": engine.route_selector.history, "public_rollouts": public,
        "control_contract": engine.control_contract}


def worker(output, scene_index, tape_index, policy, expected_sources):
    started, cpu = perf_counter(), process_time()
    output = Path(output)
    identity = f"s{scene_index}_t{tape_index}_{policy}"
    if source_hashes() != expected_sources:
        raise ValueError("source changed before case")
    original = sustained_scenes()[scene_index]
    tape_name, tape = deployment_tapes(original)[tape_index]
    scene = replace(original, future_bags=tape)
    try:
        record = deploy(scene, policy)
    except Exception as exc:
        record = {"metrics": {"status": "execution_failure",
            "scheduled": len(scene.initial.bags) + len(tape), "process_cpu_seconds": process_time() - cpu,
            "wall_seconds": perf_counter() - started, "memory": memory_snapshot()},
            "failure": {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}}
    record.update(identity=identity, scene=scene.name, tape=tape_name, policy=policy,
        source_changed_during_case=source_hashes() != expected_sources)
    path = output / "cases" / (identity + ".json.gz")
    with gzip.open(path, "xt", encoding="utf-8") as stream:
        json.dump(record, stream, allow_nan=False, separators=(",", ":"))
    row = {k: record[k] for k in ("identity", "scene", "tape", "policy", "source_changed_during_case")}
    row.update(record["metrics"])
    row.update(file=path.name, sha256=sha256(path.read_bytes()).hexdigest(),
               invocation_cpu_seconds=process_time() - cpu, invocation_wall_seconds=perf_counter() - started)
    return row


def summarize(rows, planned):
    pairs = {}
    by_key = {(r["scene"], r["tape"], r["policy"]): r for r in rows}
    for policy in POLICIES[1:]:
        for end in ("h80", "final"):
            usable = [(r, by_key.get((r["scene"], r["tape"], "greedy"))) for r in rows if r["policy"] == policy]
            usable = [(a, b) for a, b in usable if b and end in a and end in b]
            deltas = [a[end]["total_cost"] - b[end]["total_cost"] for a, b in usable]
            pairs[policy + ":" + end] = {"pairs": len(usable),
                "better": sum(d < -1e-8 for d in deltas), "equal": sum(abs(d) <= 1e-8 for d in deltas),
                "worse": sum(d > 1e-8 for d in deltas), "cost_delta": sum(deltas),
                "completed_delta": sum(a[end]["completed"] - b[end]["completed"] for a, b in usable),
                "on_time_delta": sum(a[end]["on_time"] - b[end]["on_time"] for a, b in usable),
                "both_quiescent": sum(a["status"] == b["status"] == "controller_quiescent" for a, b in usable)}
    return {"planned_episodes": planned, "recorded_episodes": len(rows), "rows": rows, "pairs": pairs,
        "statuses": dict(Counter(r["status"] for r in rows)),
        "case_invocation_cpu_seconds_recorded": sum(r["invocation_cpu_seconds"] or 0 for r in rows),
        "case_invocation_wall_sum_seconds_recorded": sum(r["invocation_wall_seconds"] or 0 for r in rows),
        "cases_with_unavailable_invocation_accounting": sum(r["invocation_cpu_seconds"] is None for r in rows),
        "case_source_changed": any(r["source_changed_during_case"] for r in rows)}


def run(output, *, workers=6, pilot=False):
    output = create_output_directory(output).resolve()
    wall, cpu = perf_counter(), process_time()
    sources = source_hashes()
    (output / "source_snapshot").mkdir()
    (output / "cases").mkdir()
    for name in sources:
        (output / "source_snapshot" / name).write_bytes((CODE / name).read_bytes())
    units = [(s, t) for s in range(4) for t in range(9) if not pilot or t == 0]
    protocol = {"schema": "ics_v3_one_step_empty_development_v1", "pilot": pilot,
        "spec": asdict(SPEC), "policies": POLICIES, "units": units,
        "planned_episodes": len(units) * len(POLICIES), "source_sha256": sources,
        "settings_base": asdict(EmptyImprovementSettings()), "workers": workers,
        "source_role": "reused_development_only_no_fits_no_new_independent_sources",
        "input_rule": "all four sustained scenes; original nominal and SHA-derived 8 deployment tapes",
        "stopping": "read h80; entire tape complete + transport drained + all forecast TTL60 expired + actual slow trigger over full period; tail cap240",
        "budget": "new method mandatory greedy/no-transfer then bounded sequences; 2/12/24 count,40/80 score; query caps per branch; no outcome dependent episode time stop",
        "continuation": "new empty branches timed/greedy after real slow cursor; deployed next slow repeats improvement; not recursive matched value",
        "legacy": "unchanged bounded empty method with earliest/reactive/no-slow continuation, different action order and max12",
        "public_fast": "four normal K candidates, point forecast rollout20, greedy slow",
        "memory_scope": "per process lifetime peaks, not concurrent aggregate"}
    write_new_json(output / "protocol.json", protocol)
    inputs = []
    for si, ti in units:
        scene = sustained_scenes()[si]
        name, tape = deployment_tapes(scene)[ti]
        inputs.append({"scene_index": si, "tape_index": ti, "scene": scene.name, "tape": name,
            "initial": asdict(scene.initial), "published_forecasts": [asdict(f) for f in scene.forecasts],
            "actual_tasks_event_engine_only": [asdict(b) for b in tape]})
    write_new_json(output / "inputs.json", inputs)
    rows = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(worker, str(output), si, ti, policy, sources): (si, ti, policy)
                for index, (si, ti) in enumerate(units)
                for policy in (POLICIES if index % 2 == 0 else tuple(reversed(POLICIES)))}
        for job in as_completed(jobs):
            try:
                row = job.result()
            except Exception as exc:
                si, ti, policy = jobs[job]
                scene = sustained_scenes()[si]
                tape_name, tape = deployment_tapes(scene)[ti]
                row = {"identity": f"s{si}_t{ti}_{policy}", "scene": scene.name,
                    "tape": tape_name, "policy": policy, "status": "worker_failure",
                    "scheduled": len(scene.initial.bags) + len(tape),
                    "source_changed_during_case": source_hashes() != sources,
                    "invocation_cpu_seconds": None, "invocation_wall_seconds": None,
                    "resource_accounting": "unavailable_worker_did_not_return; recorded_sum_is_lower_bound",
                    "failure": {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}}
                failure_path = output / "cases" / (row["identity"] + ".worker_failure.json")
                write_new_json(failure_path, row)
                row.update(file=failure_path.name, sha256=sha256(failure_path.read_bytes()).hexdigest())
            rows.append(row)
            print(json.dumps({k: row[k] for k in ("identity", "status", "invocation_cpu_seconds")}), flush=True)
    summary = summarize(sorted(rows, key=lambda r: r["identity"]), protocol["planned_episodes"])
    summary.update(source_changed_during_run=source_hashes() != sources,
        parent_cpu_seconds=process_time() - cpu, coordinator_wall_seconds=perf_counter() - wall,
        protocol_sha256=sha256((output / "protocol.json").read_bytes()).hexdigest(),
        inputs_sha256=sha256((output / "inputs.json").read_bytes()).hexdigest())
    write_new_json(output / "summary.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--pilot", action="store_true")
    args = parser.parse_args()
    result = run(args.output, workers=args.workers, pilot=args.pilot)
    raise SystemExit(int(result["source_changed_during_run"] or result["case_source_changed"]
                         or result["statuses"].get("execution_failure", 0) > 0
                         or result["statuses"].get("worker_failure", 0) > 0))
