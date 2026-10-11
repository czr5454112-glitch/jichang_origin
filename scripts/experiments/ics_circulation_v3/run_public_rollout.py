"""Development stress/nominal comparison using equal routing candidates.

Public rollout has an explicitly larger compute allowance. There is no hidden
tape access, model selection, fresh-confirmation claim, or best-seed reporting.
"""
import argparse
from dataclasses import asdict, replace
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time
import traceback

from .experiment_protocol import create_output_directory, write_new_json
from .label_stability import digest, sampled_futures, sustained_scenes
from .phase4_control import ControlSpec, build_engine
from .public_rollout import build_public_rollout_engine
from .role_coverage import CursorSimulation


SOURCES = ("run_public_rollout.py", "public_rollout.py", "role_coverage.py", "label_stability.py",
           "feedback_scenarios.py", "phase4_control.py", "joint_feedback.py", "conditional_evaluation.py",
           "learning.py", "prebalance.py", "evaluation.py", "runtime.py", "model.py", "routing.py",
           "routing_reference.py", "experiment_protocol.py", "role_features.py", "nonlinear_learning.py")
POLICIES = ("baseline", "timed", "conditional_timed", "public_rollout")


def deployment_tapes(scene):
    seed = int(digest([scene.name, "role_recovery_deployment_v1"])[:16], 16)
    return [("nominal", scene.future_bags)] + [
        (f"stress_{index}", tape) for index, tape in enumerate(
            sampled_futures(scene.future_bags, scene.initial, count=8, seed=seed))]


def run_case(scene, policy):
    spec = ControlSpec(routing="timed", planning_horizon=20, slow_period=2)
    if policy == "public_rollout":
        engine = build_public_rollout_engine(scene, spec)
    else:
        baseline = build_engine(scene.initial, scene.forecasts, scene.future_bags, replace(spec, routing=policy))
        engine = CursorSimulation.from_base_checkpoint(baseline.checkpoint(), contract=baseline.control_contract)
    wall, cpu = perf_counter(), process_time()
    result = engine.advance(scene.horizon)
    bags = {**scene.initial.bags, **{b.bag_id: b for b in scene.future_bags}}
    costs = engine.route_selector.selector.history if policy == "public_rollout" else []
    # Visits and looping decisions are described from actual accepted calls.
    histories = engine.route_selector.history
    arrived, leave = 0, 0
    for row in histories:
        bag = bags[row["bag_id"]]
        chosen = row["chosen"]
        if not chosen["legs"]:
            arrived += 1
        elif scene.initial.network.edges[chosen["legs"][0]["edge_id"]].source == bag.destination:
            arrived += 1
            leave += 1
    metrics = {"status": "completed_run", "total_cost": result.total_cost,
               "cost_components": result.cost_components, "scheduled_bags": len(bags),
               "completed": len(result.completed), "unfinished": list(result.uncompleted_bag_ids),
               "on_time": sum(b in result.completed and result.completed[b] <= bag.deadline for b, bag in bags.items()),
               "selector_calls": len(histories), "arrival_at_destination_calls": arrived,
               "departures_from_destination": leave,
               "internal_rollouts": sum(len(r["rollouts"]) for r in costs),
               "rollout_cpu_seconds": sum(r["process_cpu_seconds"] for r in costs),
               "process_cpu_seconds": process_time() - cpu, "wall_seconds": perf_counter() - wall}
    return {"metrics": metrics, "result": asdict(result), "route_history": histories,
            "control_contract": engine.control_contract,
            "public_rollouts": costs, "slow_history": engine.slow_controller.history,
            "slow_trigger_times": engine.slow_controller.trigger_times,
            "forecast_publications": [asdict(f) for f in scene.forecasts]}


def run(output):
    output = create_output_directory(output)
    code = Path(__file__).parent
    sources = {name: (code / name).read_bytes() for name in SOURCES}
    (output / "source_snapshot").mkdir()
    for name, value in sources.items():
        (output / "source_snapshot" / name).write_bytes(value)
    write_new_json(output / "protocol.json", {
        "schema": "ics_v3_public_rollout_role_development_v1", "policies": POLICIES,
        "stream_names": [s.name for s in sustained_scenes()], "scenarios_per_stream": 9, "planned_runs": 144,
        "stress_rule": "sampled_futures from initial observable state; count8; sha256([stream,role_recovery_deployment_v1]) first16hex seed",
        "same_tape_for_all_policies": True, "continuation_horizon": 20, "slow_period": 2,
        "candidate_count": 4, "route_mode": "next_edge", "extra_rollout_budget_per_call": 4,
        "rollout_continuation": "timed; freeze currently published forecasts and exact current routing cursor/slow phase",
        "future_true_tape_access": "actual_event_engine_only", "confirmation": False,
        "source_sha256": {name: sha256(value).hexdigest() for name, value in sources.items()},
        "limits": ["four reused development streams, no independent airport days",
                   "extra online compute is not matched to cheap scorer budget",
                   "proxy future is currently published point forecast, not sampled or actual future",
                   "stress draws share a synthetic family, not calibrated operational distributions"]})
    rows, failures = [], []
    for original in sustained_scenes():
        for tape_name, tape in deployment_tapes(original):
            scene = replace(original, future_bags=tape)
            write_new_json(output / f"{scene.name}__{tape_name}_inputs.json", {
                "initial": asdict(scene.initial), "forecasts": [asdict(f) for f in scene.forecasts],
                "event_engine_only_tape": [asdict(b) for b in tape], "horizon": scene.horizon})
            for policy in POLICIES:
                identity = f"{scene.name}__{tape_name}__{policy}"
                try:
                    result = run_case(scene, policy)
                except Exception as error:
                    result = {"metrics": {"status": "failed_run", "total_cost": None,
                        "scheduled_bags": len(scene.initial.bags) + len(tape), "completed": None},
                        "failure": {"type": type(error).__name__, "reason": str(error), "traceback": traceback.format_exc()}}
                    failures.append(identity)
                row = {"identity": identity, "scene": scene.name, "tape": tape_name, "policy": policy,
                       **result["metrics"]}
                rows.append(row)
                write_new_json(output / (identity + ".json"), result)
                print(row, flush=True)
    summary = {"runs": len(rows), "failures": failures, "rows": rows,
               "scheduled_bag_denominator": sum(r["scheduled_bags"] for r in rows),
               "completed_bags": sum(r["completed"] or 0 for r in rows),
               "source_changed_during_run": any((code / n).read_bytes() != v for n, v in sources.items())}
    write_new_json(output / "summary.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run(args.output)
    raise SystemExit(int(bool(result["failures"]) or result["source_changed_during_run"]))
