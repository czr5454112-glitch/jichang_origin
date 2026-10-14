"""Matched joint-control experiment; run with --groups 2 before the full 24."""
from __future__ import annotations

from .experiment_protocol import check_output_directory, create_output_directory

import argparse
from collections import Counter
import csv
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
from statistics import mean
from time import perf_counter
import traceback

from .joint_control import build_engine, policies
from .phase2_scenarios import make_scene
from .runtime import COST_WEIGHTS


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = ROOT / "outputs/experiments/ics_circulation_v3/phase2_joint_20261009"


def _write(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def source_hashes():
    directory = Path(__file__).resolve().parent
    return {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in (
        "experiment_protocol.py", "model.py", "runtime.py", "routing.py", "prebalance.py", "learning.py", "evaluation.py",
        "phase2_scenarios.py", "joint_control.py", "run_joint_control.py")}


def _bag_ledger(expected, result, final_tick):
    ledger = []
    for bag_id, bag in sorted(expected.items()):
        complete = result.completed.get(bag_id) if result else None
        observed = result is not None and bag_id in result.final_snapshot.bags
        loaded = result.final_snapshot.load_times.get(bag_id) if result else None
        status = ("completed_on_time" if complete is not None and complete <= bag.deadline else
                  "completed_late" if complete is not None else
                  "not_observed_before_failure_or_horizon" if not observed else
                  "uncompleted_loaded" if loaded is not None else "uncompleted_waiting")
        ledger.append({**asdict(bag), "observed": observed, "load_time": loaded,
                       "completion_time": complete, "status": status,
                       "deadline_failed_by_final_tick": complete > bag.deadline if complete is not None else final_tick > bag.deadline,
                       "tray_wait_observed": max(0, min(final_tick, loaded if loaded is not None else final_tick) - bag.arrival)})
    return ledger


def run(output: Path = DEFAULT_OUTPUT, *, groups=24, future_seed=991):
    if groups < 1:
        raise ValueError("groups must be positive")
    output = create_output_directory(output)
    before = source_hashes()
    started = perf_counter()
    rows, manifests, comparisons = [], [], []
    for index in range(groups):
        scene = make_scene(index, "joint")
        # The same immutable tape goes only to each independent event engine.
        # Both controller constructors receive the published forecast objects.
        future = scene.future(future_seed)
        initial = asdict(scene.initial)
        future_rows = [asdict(bag) for bag in future]
        forecast_rows = [asdict(forecast) for forecast in scene.forecasts]
        expected = {**scene.initial.bags, **{bag.bag_id: bag for bag in future}}
        assert len(expected) == len(scene.initial.bags) + len(future), "duplicate bag denominator"
        initial_hash, future_hash, forecast_hash = _hash(initial), _hash(future_rows), _hash(forecast_rows)
        manifests.append({"source_group": scene.source_group, "split": scene.split,
                          "initial": initial, "future_event_engine_only": future_rows,
                          "forecasts": forecast_rows, "horizon": scene.horizon,
                          "truth_shift": scene.truth_shift, "future_seed": future_seed,
                          "initial_sha256": initial_hash, "future_sha256": future_hash,
                          "forecast_sha256": forecast_hash, "all_scheduled_bag_ids": sorted(expected)})
        group_rows = []
        for policy in policies():
            engine = build_engine(scene, future, policy)
            result, failure = None, None
            begin = perf_counter()
            try:
                result = engine.advance(scene.horizon)
            except Exception as error:
                failure = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
                try:
                    result = engine.result()
                except Exception:
                    pass  # The failed run still remains in every denominator.
            elapsed = (perf_counter() - begin) * 1000
            ledger = _bag_ledger(expected, result, engine.state.now)
            history = engine.slow_controller.history if engine.slow_controller is not None else []
            traces = list(result.trace) if result is not None else list(engine._trace)
            stats = dict(engine.policy_stats)
            completed = len(result.completed) if result else len(engine.state.completed)
            on_time = sum(item["status"] == "completed_on_time" for item in ledger)
            deadline_failed = sum(item["deadline_failed_by_final_tick"] for item in ledger)
            identity_ok = set(engine.state.trays) == set(scene.initial.trays)
            observed_expected = {bag_id for bag_id, bag in expected.items() if bag.arrival <= engine.state.now}
            bag_ledger_ok = set(engine.state.bags) == observed_expected
            rejection_reasons = Counter(item["reason"] for call in history for item in call["candidate_rejections"])
            row = {
                "source_group": scene.source_group, "policy_id": policy.policy_id,
                **asdict(policy), "route_mode": "next_edge", "status": "failed" if failure else "completed_run",
                "initial_sha256": initial_hash, "future_sha256": future_hash, "forecast_sha256": forecast_hash,
                "actual_bag_count": len(expected), "arrived_by_horizon_count": sum(bag.arrival <= scene.horizon for bag in expected.values()),
                "completed_count": completed, "uncompleted_count": len(expected) - completed,
                "on_time_count": on_time, "on_time_fraction": on_time / len(expected) if expected else None,
                "deadline_failed_count": deadline_failed,
                "protected_bag_count": sum(bag.protected for bag in expected.values()),
                "protected_deadline_failed_count": sum(item["protected"] and item["deadline_failed_by_final_tick"] for item in ledger),
                "waiting_count": len(result.waiting_bag_ids) if result else None,
                "finite_tray_ids_preserved": identity_ok, "all_arrived_bag_ids_preserved": bag_ledger_ok,
                "invariant_checks": result.invariant_checks if result else engine._checks,
                "final_tick": engine.state.now, "total_cost": result.total_cost if result and not failure else None,
                **({key: result.cost_components[key] for key in COST_WEIGHTS} if result else {key: None for key in COST_WEIGHTS}),
                **stats, "runtime_ms": elapsed,
                "reactive_commits": sum(event["event"] == "empty_dispatch" for event in traces),
                "slow_max_call_ms": max((call["elapsed_ms"] for call in history), default=0),
                "failure_type": failure["type"] if failure else None,
            }
            rows.append(row)
            group_rows.append(row)
            name = f"group_{index:03d}__{policy.policy_id}.json"
            _write(output / name, {
                "metrics": row, "weights": COST_WEIGHTS, "forecasts": forecast_rows,
                "bag_ledger": ledger, "initial_tray_ids": sorted(scene.initial.trays),
                "final_snapshot": asdict(engine.state), "trace": traces,
                "actions": [event for event in traces if event["event"] in {
                    "route_commit", "slow_commit", "empty_dispatch", "empty_continue", "intervention_commit", "depart", "prefix_arrive"}],
                "routing_decisions": engine.route_selector.history,
                "slow_controller_history": history, "slow_rejection_reasons": dict(rejection_reasons),
                "failure": failure,
            })
        baseline = next(row for row in group_rows if row["policy_id"] == "baseline__reactive_only")
        for row in group_rows:
            comparisons.append({"source_group": scene.source_group, "policy_id": row["policy_id"],
                                "baseline_cost": baseline["total_cost"], "policy_cost": row["total_cost"],
                                "delta_from_baseline_reactive": None if baseline["total_cost"] is None or row["total_cost"] is None
                                else row["total_cost"] - baseline["total_cost"],
                                "paired_inputs_equal": all(row[key] == baseline[key] for key in (
                                    "initial_sha256", "future_sha256", "forecast_sha256"))})
    by_policy = {}
    for policy in policies():
        selected = [row for row in rows if row["policy_id"] == policy.policy_id]
        valid_costs = [row["total_cost"] for row in selected if row["total_cost"] is not None]
        deltas = [row["delta_from_baseline_reactive"] for row in comparisons
                  if row["policy_id"] == policy.policy_id and row["delta_from_baseline_reactive"] is not None]
        by_policy[policy.policy_id] = {
            "run_count": len(selected), "failed_runs": sum(row["status"] == "failed" for row in selected),
            "cost_available_count": len(valid_costs), "mean_cost": mean(valid_costs) if valid_costs else None,
            "mean_delta_from_baseline_reactive": mean(deltas) if deltas else None,
            "all_bags_denominator": sum(row["actual_bag_count"] for row in selected),
            "completed_count": sum(row["completed_count"] for row in selected),
            "on_time_count": sum(row["on_time_count"] for row in selected),
            "deadline_failed_count": sum(row["deadline_failed_count"] for row in selected),
            "protected_deadline_failed_count": sum(row["protected_deadline_failed_count"] for row in selected),
            "slow_commits": sum(row["slow_commits"] for row in selected),
            "mean_runtime_ms": mean(row["runtime_ms"] for row in selected),
            "mean_route_generation_ms": mean(row["generation_ms"] for row in selected),
            "mean_route_selection_ms": mean(row["selection_ms"] for row in selected),
            "mean_slow_ms": mean(row["slow_ms"] for row in selected),
        }
    after = source_hashes()
    summary = {
        "schema": "czr005.ics_circulation_v3.joint_control.v1",
        "scope": "INDEPENDENT_SYNTHETIC_GROUPS_FIXED_LOCAL_MODULE_PROXY",
        "group_count": groups, "policy_count": len(policies()), "run_count": len(rows), "future_seed": future_seed,
        "weights": COST_WEIGHTS, "route_mode": "next_edge", "runtime_python": platform.python_version(),
        "all_input_pairs_equal": all(row["paired_inputs_equal"] for row in comparisons),
        "all_finite_tray_ids_preserved": all(row["finite_tray_ids_preserved"] for row in rows),
        "all_arrived_bag_ids_preserved": all(row["all_arrived_bag_ids_preserved"] for row in rows),
        "failed_run_count": sum(row["status"] == "failed" for row in rows),
        "source_sha256": before, "source_changed_during_run": before != after,
        "source_sha256_after": after, "elapsed_ms": (perf_counter() - started) * 1000,
        "by_policy": by_policy,
        "limitations": [
            "All groups, forecasts and module parameters are synthetic assumptions; no airport integration is claimed.",
            "The future tape is event-engine-only; policies receive the same published forecasts and currently observable state.",
            "Prefix plans are conservatively excluded from terminal empty supply; no fictitious intermediate release is counted.",
            "Coordination changes sequential proposal priority, never an accepted prefix or entered edge.",
            "Protected loaded tasks request full admission before both soft coordination orders; failed admission remains explicit and retains the bag.",
            "Protected bags freeze their full accepted witness even in next_edge mode; only nonprotected bags use prefix intervention.",
            "Nonprotected full-route witnesses are checked at each prefix decision; global recursive feasibility is not established.",
            "Wall-clock search cutoffs are disabled for paired reproducibility; measured times are not deployment guarantees.",
            "Failed runs remain explicit in counts and denominators; means disclose the number of costs available.",
        ],
    }
    _write(output / "manifest.json", manifests)
    _write(output / "metrics.json", rows)
    _write(output / "comparisons.json", comparisons)
    _write(output / "summary.json", summary)
    with (output / "metrics.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--groups", type=int, default=24)
    parser.add_argument("--future-seed", type=int, default=991)
    args = parser.parse_args(argv)
    result = run(args.output, groups=args.groups, future_seed=args.future_seed)
    print(json.dumps({key: result[key] for key in ("group_count", "run_count", "failed_run_count", "source_changed_during_run", "by_policy")}, indent=2))
    return 1 if result["failed_run_count"] or result["source_changed_during_run"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
