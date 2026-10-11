"""Dependency-incumbent budgets and repeated finite-stock circulation stress."""
import argparse
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter, process_time

from .dependency_admission import execute_dependencies, plan_dependencies, propose_loaded_departures
from .experiment_protocol import create_output_directory
from .joint_bundle_reference import AtomicJointDomain, AtomicJointMPC, solve_atomic_joint
from .joint_transactions import commit_joint_actions
from .learning import RoutingDemandForecast
from .model import Bag, Edge, FixedLocalModule, Network, Node, Snapshot, Tray
from .runtime import Simulation


SOURCES = ("run_joint_seed_stress.py", "joint_bundle_reference.py", "joint_reference.py", "dependency_admission.py",
           "joint_transactions.py", "model.py", "runtime.py", "routing.py", "learning.py", "evaluation.py",
           "prebalance.py", "experiment_protocol.py", "routing_reference.py")


def cycle_scene(size=3, *, travel=1, capacity=1, missing_loaded=False, waves=4):
    nodes = tuple(chr(ord("A") + i) for i in range(size))
    destinations = dict(zip(nodes, nodes[1:] + nodes[:1]))
    network = Network({n: Node(n, n, n, capacity=capacity) for n in nodes},
                      {a + b: Edge(a + b, a, b, travel) for a, b in destinations.items()})
    bags = {"initial:" + n: Bag("initial:" + n, n, destinations[n], 0, travel + 1) for n in nodes
            if not (missing_loaded and n == nodes[-1])}
    trays = {n: Tray(n, n, "loaded", "initial:" + n) if "initial:" + n in bags else Tray(n, n) for n in nodes}
    initial = Snapshot(0, network, trays, bags, module=FixedLocalModule(unload_ticks=1))
    spacing = 2 * travel + 2
    future, forecasts = [], []
    for wave in range(1, waves):
        for n in nodes:
            at, identity = spacing * wave, f"wave{wave}:{n}"
            forecasts.append(RoutingDemandForecast(identity, n, destinations[n], at, at + travel + 1,
                                                    published_at=max(0, at - spacing)))
            future.append(Bag(identity + ":0", n, destinations[n], at, at + travel + 1))
    return {"name": f"cycle{size}_travel{travel}_capacity{capacity}_missing{missing_loaded}",
            "initial": initial, "future": tuple(future), "forecasts": tuple(forecasts),
            "horizon": max(12, spacing * (waves - 1) + travel + 3),
            "factors": {"tray_count": size, "node_capacity": capacity, "travel_ticks": travel,
                        "waves": waves, "missing_initial_loaded_participant": missing_loaded,
                        "source_protection_contract": "module_only", "synthetic_development_only": True}}


def save(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def rolling(scene, *, atomic=True, dependency_seed=False, budget=500, cheap_scc=False):
    start, cpu = perf_counter(), process_time()
    engine = Simulation(scene["initial"], scene["future"], control_mode="external", route_mode="whole_route")
    policy = AtomicJointMPC(planning_horizon=12, route_tail_ticks=scene["factors"]["travel_ticks"],
                            atomic_bundles=atomic, dependency_seed=dependency_seed, expansion_limit=budget)
    decisions = []
    while engine.state.now < scene["horizon"]:
        observation = engine.observe()
        wall, tick_cpu = perf_counter(), process_time()
        if cheap_scc:
            proposals, logs = propose_loaded_departures(observation, horizon=12, expansion_limit=500)
            plan = plan_dependencies(observation, proposals)
            execute_dependencies(engine, plan)
            row = {"time": observation.now, "status": "feasible_witness_admission_only", "complete": False,
                   "gap": None, "witnesses": logs, "dependency_plan": asdict(plan)}
        else:
            published = tuple(f for f in scene["forecasts"] if f.published_at <= observation.now)
            plan = policy.plan(observation, published)
            row = {"time": observation.now, "status": plan.status, "complete": plan.complete, "gap": plan.gap,
                   "proxy_cost": plan.total_cost, "diagnostics": plan.diagnostics,
                   "information": policy.history[-1], "commits": []}
            for bundle in plan.first_bundles:
                accepted = commit_joint_actions(engine, bundle)
                row["commits"].append({"proposals": [asdict(p) for p in bundle], "accepted": accepted.accepted, "reason": accepted.reason})
                if not accepted.accepted:
                    raise AssertionError("Frozen observation's first bundle rejected: " + accepted.reason)
        row.update(wall_seconds=perf_counter() - wall, process_cpu_seconds=process_time() - tick_cpu)
        decisions.append(row)
        engine.advance(observation.now + 1)
    physical = engine.result()
    metrics = {"scene": scene["name"], "status": "completed_run", "atomic": atomic,
               "dependency_seed": dependency_seed, "budget": None if cheap_scc else budget, "cheap_scc": cheap_scc,
               "scheduled_bags": len(scene["initial"].bags) + len(scene["future"]), "completed": len(physical.completed),
               "total_cost": physical.total_cost, "cost_components": physical.cost_components,
               "uncompleted": list(physical.uncompleted_bag_ids), "solver_calls": len(decisions),
               "statuses": dict(Counter(r["status"] for r in decisions)), "unknown_gap_calls": sum(r["gap"] is None for r in decisions),
               "no_joint_search_calls": None if cheap_scc else sum(r["diagnostics"]["work_counts"].get("joint_states", 0) == 0 for r in decisions),
               "work": None if cheap_scc else sum(r["diagnostics"]["work_used"] for r in decisions),
               "wall_seconds": perf_counter() - start, "process_cpu_seconds": process_time() - cpu}
    return {"metrics": metrics, "physical": asdict(physical), "decisions": decisions}


def run(output, *, tiny_only=False):
    output = create_output_directory(output)
    code = Path(__file__).parent
    source = {name: (code / name).read_bytes() for name in SOURCES}
    hashes = {name: sha256(data).hexdigest() for name, data in source.items()}
    scenes = (cycle_scene(), cycle_scene(travel=3), cycle_scene(capacity=2), cycle_scene(missing_loaded=True))
    # 4 fixtures x (8 MPC configurations + 1 cheap SCC baseline) = 36 episodes.
    configs = tuple((atomic, seed, budget) for atomic in (False, True) for seed in (False, True) for budget in (500, 2000))
    save(output / "protocol.json", {"source_sha256": hashes, "development_only": True, "tiny_only": tiny_only,
        "tiny_grid": {"size": [2, 3, 4], "horizon": 2, "budget": [40, 80, 160, 320], "dependency_seed": [False, True]},
        "tiny_calls": 24, "planned_rolling_episodes": 0 if tiny_only else 36,
        "rolling_configs": configs, "rolling_scenes": [{"name": s["name"], **s["factors"], "horizon": s["horizon"]} for s in scenes],
        "rolling_horizon": 12, "route_tail": "one maximum edge", "whole_route": True,
        "source_protection_contract": "module_only", "real_future_access": "evaluation kernel only; MPC takes published forecasts",
        "seed_protocol": "independent optional SCC feasible seed; ordinary-reactive and SCC seeds each receive at most quarter of global work; all charged; no candidate-domain truncation",
        "same_algorithm_permission_ablation": True, "cheap_baseline": "fixed-witness SCC loading routes each tick, no forecast optimization or empty moves; same physical atomic permissions",
        "limits": ["Repeated synthetic circulation, not independent deployment confirmation.",
                   "Budget exhaustion gives no nontrivial gap bound.", "A zero-cost incumbent proves its nonnegative proxy objective lower bound only.",
                   "SCC witness failure can miss empty-participant cycles and other route witnesses; exhaustive domain remains independent.",
                   "Root's separate label replay is concurrent: process CPU retained; wall times are not exclusive-machine latency claims."]})
    (output / "source_snapshot").mkdir()
    for name, data in source.items():
        (output / "source_snapshot" / name).write_bytes(data)
    tiny = []
    for size in (2, 3, 4):
        case = cycle_scene(size, waves=1)
        for budget in (40, 80, 160, 320):
            for seed in (False, True):
                result = solve_atomic_joint(case["initial"], domain=AtomicJointDomain(2, expansion_limit=budget, dependency_seed=seed))
                tiny.append({"size": size, "budget": budget, "dependency_seed": seed, "result": asdict(result)})
    save(output / "tiny_grid.json", tiny)
    metrics = []
    def recorded_episode(scene, **kwargs):
        start, cpu = perf_counter(), process_time()
        try:
            return rolling(scene, **kwargs)
        except Exception as error:
            return {"metrics": {"scene": scene["name"], "status": "failed_run", **kwargs,
                "scheduled_bags": len(scene["initial"].bags) + len(scene["future"]), "completed": None,
                "total_cost": None, "wall_seconds": perf_counter() - start, "process_cpu_seconds": process_time() - cpu,
                "failure": {"type": type(error).__name__, "reason": str(error)}}}
    if not tiny_only:
        for index, scene in enumerate(scenes):
            inputs = {"initial": asdict(scene["initial"]), "forecasts": [asdict(f) for f in scene["forecasts"]],
                      "actual_tape_driver_only": [asdict(b) for b in scene["future"]], "horizon": scene["horizon"], "factors": scene["factors"]}
            save(output / (scene["name"] + "_inputs.json"), inputs)
            for atomic, seed, budget in (configs if index % 2 == 0 else tuple(reversed(configs))):
                result = recorded_episode(scene, atomic=atomic, dependency_seed=seed, budget=budget)
                save(output / f'{scene["name"]}_atomic{atomic}_seed{seed}_work{budget}.json', result)
                metrics.append(result["metrics"])
                print(json.dumps(result["metrics"]), flush=True)
            result = recorded_episode(scene, cheap_scc=True)
            save(output / (scene["name"] + "_cheap_scc.json"), result)
            metrics.append(result["metrics"])
            print(json.dumps(result["metrics"]), flush=True)
    summary = {"source_sha256": hashes, "tiny_calls": len(tiny), "rolling_episodes": len(metrics), "metrics": metrics,
               "scheduled_bag_denominator": sum(r["scheduled_bags"] for r in metrics),
               "completed_bags": sum(r["completed"] or 0 for r in metrics),
               "failed_runs": sum(r["status"] == "failed_run" for r in metrics),
               "source_changed_during_run": any((code / name).read_bytes() != data for name, data in source.items())}
    save(output / "summary.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--tiny-only", action="store_true")
    args = parser.parse_args()
    result = run(args.output, tiny_only=args.tiny_only)
    raise SystemExit(int(result["source_changed_during_run"] or result["failed_runs"]))
