"""Predeclared nine-scene, two-work-budget MPC comparison against frozen feedback runs."""
import argparse
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter, process_time

from .experiment_protocol import create_output_directory
from .feedback_scenarios import feedback_scene
from .joint_reference import JointMPC
from .runtime import Simulation


SOURCES = ("run_joint_mpc_comparison.py", "joint_reference.py", "feedback_scenarios.py", "runtime.py", "model.py",
           "routing.py", "learning.py", "evaluation.py", "experiment_protocol.py")
MODES = ("route_then_prebalance", "prebalance_then_route", "one_round_feedback")
BUDGETS = (5000, 25000)


def save(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def run_episode(scene, work_budget):
    wall, cpu = perf_counter(), process_time()
    engine = Simulation(scene.initial, scene.future_bags, control_mode="external", route_mode="whole_route")
    tail = max(edge.travel_time for edge in scene.initial.network.edges.values())
    controller = JointMPC(planning_horizon=20, route_tail_ticks=tail, expansion_limit=work_budget, deadline_ms=None)
    decisions, failures = [], []
    while engine.state.now < scene.horizon:
        observation = engine.observe()
        start, begin_cpu = perf_counter(), process_time()
        row = {"time": observation.now, "observed_bag_ids": sorted(observation.bags)}
        try:
            published = tuple(forecast for forecast in scene.forecasts if forecast.published_at <= observation.now)
            plan = controller.plan(observation, published)
            row.update({"status": plan.status, "complete": plan.complete,
                        "proxy_cost": plan.total_cost, "lower_bound": plan.lower_bound, "gap": plan.gap,
                        "diagnostics": plan.diagnostics, "information": controller.history[-1],
                        "first_actions": [asdict(candidate) for candidate in plan.first_actions], "commit_results": []})
            for candidate in plan.first_actions:
                accepted = engine.intervene(candidate)
                row["commit_results"].append({"accepted": accepted.accepted, "reason": accepted.reason})
                if not accepted.accepted:
                    break
        except Exception as error:
            row.update({"status": "local_processing_failure", "complete": False, "gap": None,
                        "failure": {"type": type(error).__name__, "reason": str(error)}})
            failures.append(row["failure"])
        row.update(wall_seconds=perf_counter() - start, process_cpu_seconds=process_time() - begin_cpu)
        decisions.append(row)
        engine.advance(observation.now + 1)
    result = engine.result()
    return {"metrics": {"scene": scene.name, "condition": scene.factors["condition"], "work_budget": work_budget,
                         "status": "completed_run", "scheduled_bags": len(scene.initial.bags) + len(scene.future_bags),
                         "completed": len(result.completed), "total_cost": result.total_cost,
                         "uncompleted": list(result.uncompleted_bag_ids), "cost_components": result.cost_components,
                         "solver_calls": len(decisions), "solver_statuses": dict(Counter(r["status"] for r in decisions)),
                         "unknown_gap_calls": sum(r["gap"] is None for r in decisions),
                         "no_joint_search_calls": sum(r.get("diagnostics", {}).get("work_counts", {}).get("joint_states", 0) == 0 for r in decisions),
                         "joint_state_expansions": sum(r.get("diagnostics", {}).get("work_counts", {}).get("joint_states", 0) for r in decisions),
                         "total_work": sum(r.get("diagnostics", {}).get("work_used", 0) for r in decisions),
                         "commit_rejections": sum(not c["accepted"] for r in decisions for c in r.get("commit_results", [])),
                         "local_failure_count": len(failures), "route_tail_ticks": tail,
                         "wall_seconds": perf_counter() - wall, "process_cpu_seconds": process_time() - cpu,
                         "solver_wall_seconds": sum(r["wall_seconds"] for r in decisions),
                         "solver_process_cpu_seconds": sum(r["process_cpu_seconds"] for r in decisions)},
            "result": asdict(result), "decisions": decisions}


def run(output, baseline_output):
    output = create_output_directory(output)
    baseline_output = Path(baseline_output)
    code = Path(__file__).parent
    content = {name: (code / name).read_bytes() for name in SOURCES}
    hashes = {name: sha256(value).hexdigest() for name, value in content.items()}
    baseline_summary_bytes = (baseline_output / "summary.json").read_bytes()
    baseline_summary = json.loads(baseline_summary_bytes)
    scenes = tuple(feedback_scene(shared_travel=travel, detour_extra=1, demand_shift=0, condition=condition)
                   for travel in (2, 4, 6) for condition in ("matched", "no_demand", "reversal"))
    old_cases, old_hashes = {}, {}
    for scene in scenes:
        data = (baseline_output / f"{scene.name}.json").read_bytes()
        old = json.loads(data)
        # JSON normalization makes tuple/list representations identical; every
        # physical/input field must match before a baseline outcome is reused.
        normalized = json.loads(json.dumps({"initial": asdict(scene.initial),
            "published_forecasts": [asdict(f) for f in scene.forecasts],
            "future_tape_driver_only": [asdict(b) for b in scene.future_bags], "factors": scene.factors}))
        if any(old[key] != value for key, value in normalized.items()):
            raise ValueError("Frozen baseline scene differs: " + scene.name)
        if {run["metrics"]["mode"] for run in old["runs"]} != set(MODES):
            raise ValueError("Missing baseline mode: " + scene.name)
        old_cases[scene.name], old_hashes[scene.name] = old, sha256(data).hexdigest()
    save(output / "protocol.json", {"scope": "predeclared_development_matched_nine_scene_budget_comparison",
        "new_independent_scene_count": 0, "source_sha256": hashes, "planned_mpc_episodes": 18,
        "planned_mpc_decisions": 576, "scene_names": [s.name for s in scenes], "budgets": BUDGETS,
        "planning_horizon": 20, "route_tail_ticks": "maximum static edge travel in each scene",
        "route_mode": "whole_route", "control_mode": "external", "all_same_tick_work_counted": True,
        "order": "budget order alternates by scene index; scenes predeclared lexicographic factor order",
        "baseline_output": str(baseline_output), "baseline_summary_sha256": sha256(baseline_summary_bytes).hexdigest(),
        "baseline_case_sha256": old_hashes, "baseline_source_sha256": baseline_summary["source_sha256"],
        "shared_kernel_hash_match": {name: baseline_summary["source_sha256"].get(name) == hashes[name]
                                     for name in ("runtime.py", "model.py", "feedback_scenarios.py")},
        "permission_comparison": "same validator/module/FIFO/irrevocable whole_route obligations; greedy donor-prefix screening is a policy restriction, not imposed on full integer joint domain",
        "information_comparison": "same initial snapshot and forecast publication stream; actual tape is evaluation-driver-only",
        "compute_comparison": "all MPC proxy construction/seeding/search/reconstruction and commit work timed; baseline timing is retained historical measurement, not a fresh matched machine timing run",
        "limits": ["No real-world MPC optimum claim even if a forecast proxy solve is complete.",
                   "Budget-exhausted gap remains unknown; no candidate-pool completeness claim.",
                   "Each MPC tick may commit several trays but at most once per tray, and cannot revoke prior commitments."]})
    archive = output / "source_snapshot"
    archive.mkdir()
    for name, value in content.items():
        (archive / name).write_bytes(value)
    metrics = []
    for index, scene in enumerate(scenes):
        order = BUDGETS if index % 2 == 0 else tuple(reversed(BUDGETS))
        for budget in order:
            start, cpu = perf_counter(), process_time()
            try:
                episode = run_episode(scene, budget)
            except Exception as error:
                episode = {"metrics": {"scene": scene.name, "condition": scene.factors["condition"], "work_budget": budget,
                    "status": "failed_run", "scheduled_bags": len(scene.initial.bags) + len(scene.future_bags),
                    "completed": None, "total_cost": None, "wall_seconds": perf_counter() - start,
                    "process_cpu_seconds": process_time() - cpu,
                    "failure": {"type": type(error).__name__, "reason": str(error)}}}
            row = episode["metrics"]
            row["mpc_minus_frozen_modes"] = {old["metrics"]["mode"]:
                row["total_cost"] - old["metrics"]["total_cost"] if row["total_cost"] is not None and old["metrics"]["total_cost"] is not None else None
                for old in old_cases[scene.name]["runs"]}
            episode["baseline_metrics"] = [run["metrics"] for run in old_cases[scene.name]["runs"]]
            save(output / f"{scene.name}_work{budget}.json", episode)
            metrics.append(row)
            print(json.dumps({key: row.get(key) for key in ("scene", "work_budget", "status", "total_cost", "no_joint_search_calls", "wall_seconds")}), flush=True)
    marginal = []
    for scene in scenes:
        by_budget = {row["work_budget"]: row for row in metrics if row["scene"] == scene.name}
        low, high = by_budget[5000], by_budget[25000]
        marginal.append({"scene": scene.name, "cost_25000_minus_5000": high["total_cost"] - low["total_cost"]
                         if high["total_cost"] is not None and low["total_cost"] is not None else None,
                         "cpu_25000_minus_5000_seconds": high["process_cpu_seconds"] - low["process_cpu_seconds"]})
    summary = {"episode_count": len(metrics), "failed_episode_count": sum(m["status"] != "completed_run" for m in metrics),
               "scheduled_bag_denominator": sum(m["scheduled_bags"] for m in metrics),
               "completed_bags": sum(m["completed"] or 0 for m in metrics), "metrics": metrics, "budget_marginal": marginal,
               "source_sha256": hashes, "source_changed_during_run": any((code / name).read_bytes() != value for name, value in content.items())}
    save(output / "summary.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--baseline-output", default="outputs/experiments/ics_circulation_v3/phase4_w2_feedback_factorial_20261009")
    args = parser.parse_args()
    summary = run(args.output, args.baseline_output)
    raise SystemExit(int(summary["failed_episode_count"] > 0 or summary["source_changed_during_run"]))
