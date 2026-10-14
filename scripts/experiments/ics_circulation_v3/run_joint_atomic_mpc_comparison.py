"""Paired atomic MPC budgets and same-search admission-permission ablation."""
import argparse
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter, process_time

from .experiment_protocol import create_output_directory
from .feedback_scenarios import feedback_scene
from .joint_bundle_reference import AtomicJointMPC
from .joint_transactions import commit_joint_actions
from .runtime import Simulation


SOURCES = ("run_joint_atomic_mpc_comparison.py", "joint_bundle_reference.py", "joint_reference.py",
           "joint_transactions.py", "feedback_scenarios.py", "model.py", "runtime.py", "routing.py",
           "learning.py", "evaluation.py", "prebalance.py", "experiment_protocol.py", "dependency_admission.py")


def save(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def run_episode(scene, work_budget, atomic_bundles, source_protection_contract="module_only"):
    start, cpu = perf_counter(), process_time()
    engine = Simulation(scene.initial, scene.future_bags, control_mode="external", route_mode="whole_route")
    tail = max(e.travel_time for e in scene.initial.network.edges.values())
    policy = AtomicJointMPC(planning_horizon=20, route_tail_ticks=tail, expansion_limit=work_budget,
                            atomic_bundles=atomic_bundles, source_protection_contract=source_protection_contract)
    decisions = []
    while engine.state.now < scene.horizon:
        observation = engine.observe()
        tick_wall, tick_cpu = perf_counter(), process_time()
        row = {"time": observation.now, "observed_bag_ids": sorted(observation.bags)}
        try:
            forecasts = tuple(f for f in scene.forecasts if f.published_at <= observation.now)
            plan = policy.plan(observation, forecasts)
            row.update({"status": plan.status, "complete": plan.complete, "proxy_cost": plan.total_cost,
                        "gap": plan.gap, "lower_bound": plan.lower_bound, "diagnostics": plan.diagnostics,
                        "first_bundles": [[asdict(p) for p in bundle] for bundle in plan.first_bundles],
                        "information": policy.history[-1], "commit_results": []})
            for bundle in plan.first_bundles:
                accepted = commit_joint_actions(engine, bundle)
                row["commit_results"].append({"size": len(bundle), "accepted": accepted.accepted, "reason": accepted.reason})
                if not accepted.accepted:
                    break
        except Exception as error:
            row.update({"status": "local_processing_failure", "complete": False, "gap": None,
                        "failure": {"type": type(error).__name__, "reason": str(error)}})
        row.update(wall_seconds=perf_counter() - tick_wall, process_cpu_seconds=process_time() - tick_cpu)
        decisions.append(row)
        engine.advance(observation.now + 1)
    physical = engine.result()
    metrics = {"scene": scene.name, "condition": scene.factors["condition"], "status": "completed_run",
               "work_budget": work_budget, "atomic_bundles": atomic_bundles,
               "source_protection_contract": source_protection_contract, "planning_horizon": 20, "route_tail_ticks": tail,
               "scheduled_bags": len(scene.initial.bags) + len(scene.future_bags), "completed": len(physical.completed),
               "uncompleted": list(physical.uncompleted_bag_ids), "cost_components": physical.cost_components,
               "total_cost": physical.total_cost, "solver_calls": len(decisions),
               "solver_statuses": dict(Counter(r["status"] for r in decisions)),
               "unknown_gap_calls": sum(r["gap"] is None for r in decisions),
               "no_joint_search_calls": sum(r.get("diagnostics", {}).get("work_counts", {}).get("joint_states", 0) == 0 for r in decisions),
               "total_work": sum(r.get("diagnostics", {}).get("work_used", 0) for r in decisions),
               "multi_tray_commits": sum(c["accepted"] and c["size"] > 1 for r in decisions for c in r.get("commit_results", [])),
               "commit_rejections": sum(not c["accepted"] for r in decisions for c in r.get("commit_results", [])),
               "local_failure_count": sum("failure" in r for r in decisions),
               "wall_seconds": perf_counter() - start, "process_cpu_seconds": process_time() - cpu}
    return {"metrics": metrics, "result": asdict(physical), "decisions": decisions}


def run(output, *, smoke=False, baseline_output="outputs/experiments/ics_circulation_v3/phase4_w2_feedback_factorial_20261009"):
    output = create_output_directory(output)
    code = Path(__file__).parent
    contents = {name: (code / name).read_bytes() for name in SOURCES}
    hashes = {name: sha256(data).hexdigest() for name, data in contents.items()}
    scenes = tuple(feedback_scene(shared_travel=travel, detour_extra=1, demand_shift=0, condition=condition)
                   for travel in ((2,) if smoke else (2, 4, 6))
                   for condition in (("matched",) if smoke else ("matched", "no_demand", "reversal")))
    configurations = ((False, 5000), (True, 5000)) if smoke else ((False, 5000), (True, 5000), (True, 25000))
    baseline_summary_bytes = (Path(baseline_output) / "summary.json").read_bytes()
    baseline_summary = json.loads(baseline_summary_bytes)
    kernel_match = {name: baseline_summary["source_sha256"].get(name) == hashes[name]
                    for name in ("model.py", "runtime.py", "feedback_scenarios.py")}
    if not all(kernel_match.values()):
        raise ValueError("Physical kernel differs from frozen baseline")
    baselines, baseline_hashes = {}, {}
    for scene in scenes:
        data = (Path(baseline_output) / (scene.name + ".json")).read_bytes()
        row = json.loads(data)
        normalized = json.loads(json.dumps({"initial": asdict(scene.initial), "published_forecasts": [asdict(f) for f in scene.forecasts],
            "future_tape_driver_only": [asdict(b) for b in scene.future_bags], "factors": scene.factors}))
        if any(row[key] != value for key, value in normalized.items()):
            raise ValueError("Historical baseline scene mismatch: " + scene.name)
        baselines[scene.name], baseline_hashes[scene.name] = row, sha256(data).hexdigest()
    save(output / "protocol.json", {"source_sha256": hashes, "development_only": True, "smoke": smoke,
        "scene_names": [s.name for s in scenes], "configurations": configurations,
        "planned_episodes": len(scenes) * len(configurations), "planned_decisions": sum(s.horizon for s in scenes) * len(configurations),
        "same_search_permission_ablation": "sequential vs atomic at work 5000; same algorithm, forecasts, module_only source guard",
        "compute_ablation": "atomic work 5000 vs 25000; seeds, route preprocessing, completion probes all charged",
        "planning_horizon": 20, "route_tail": "maximum static edge travel", "route_mode": "whole_route",
        "source_protection_contract": "module_only", "search_change": "independent warm/reactive incumbents and exact-phase initial-prefix completion probes",
        "old_sequential_outputs_unchanged": True, "information": "published forecasts only; actual event tape hidden in external engine",
        "source_domain_warning": "historical greedy screens additionally protect first-known-supply prefixes; separate source-reuse diagnostic quantifies that conservative restriction",
        "baseline_output": str(baseline_output), "baseline_case_sha256": baseline_hashes,
        "baseline_summary_sha256": sha256(baseline_summary_bytes).hexdigest(), "shared_kernel_hash_match": kernel_match,
        "timing_limit": "historical baseline durations are not fresh paired exclusive-CPU measurements",
        "order": "configuration order alternates by scene; factor list fixed before execution",
        "certificate": "only fully exhausted declared finite atomic/sequential proxy domain; incomplete gap unknown; no true future optimum claim"})
    (output / "source_snapshot").mkdir()
    for name, data in contents.items():
        (output / "source_snapshot" / name).write_bytes(data)
    rows = []
    for index, scene in enumerate(scenes):
        order = configurations if index % 2 == 0 else tuple(reversed(configurations))
        for atomic, budget in order:
            start, cpu = perf_counter(), process_time()
            try:
                result = run_episode(scene, budget, atomic)
            except Exception as error:
                result = {"metrics": {"scene": scene.name, "condition": scene.factors["condition"], "work_budget": budget,
                    "atomic_bundles": atomic, "status": "failed_run", "total_cost": None, "completed": None,
                    "scheduled_bags": len(scene.initial.bags) + len(scene.future_bags),
                    "wall_seconds": perf_counter() - start, "process_cpu_seconds": process_time() - cpu,
                    "failure": {"type": type(error).__name__, "reason": str(error)}}}
            row = result["metrics"]
            result["baseline_metrics"] = [r["metrics"] for r in baselines[scene.name]["runs"]]
            row["minus_historical_baselines"] = {r["mode"]: row["total_cost"] - r["total_cost"]
                if row["total_cost"] is not None and r["total_cost"] is not None else None for r in result["baseline_metrics"]}
            save(output / f"{scene.name}_atomic{atomic}_work{budget}.json", result)
            rows.append(row)
            print(json.dumps({key: row.get(key) for key in ("scene", "atomic_bundles", "work_budget", "status", "total_cost", "wall_seconds")}), flush=True)
    summary = {"source_sha256": hashes, "metrics": rows, "episode_count": len(rows),
        "failed_episode_count": sum(r["status"] != "completed_run" for r in rows),
        "scheduled_bag_denominator": sum(r["scheduled_bags"] for r in rows),
        "completed_bags": sum(r["completed"] or 0 for r in rows),
        "source_changed_during_run": any((code / name).read_bytes() != data for name, data in contents.items())}
    save(output / "summary.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--baseline-output", default="outputs/experiments/ics_circulation_v3/phase4_w2_feedback_factorial_20261009")
    args = parser.parse_args()
    result = run(args.output, smoke=args.smoke, baseline_output=args.baseline_output)
    raise SystemExit(int(result["failed_episode_count"] > 0 or result["source_changed_during_run"]))
