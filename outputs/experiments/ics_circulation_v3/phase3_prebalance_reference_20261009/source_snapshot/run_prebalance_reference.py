"""Matched phase-3 greedy/reference evaluation; truth belongs only to this runner."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import csv
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean
from time import perf_counter
import traceback

from .phase2_scenarios import make_scene
from .prebalance import PredictivePrebalancer, synthetic_prebalance_fixtures
from .prebalance_reference import BoundedForecastPrebalancer
from .routing import RegionalCandidateGenerator
from .runtime import COST_WEIGHTS, Simulation


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = ROOT / "outputs/experiments/ics_circulation_v3/phase3_prebalance_reference_20261009"
HOLDOUT_NAMESPACE = "phase3_prebalance_reference_holdout_v1"
DEFAULT_SEED = 1457
# Complete local import closure for this entrypoint, including lazy fixture
# imports. Independent learning/service runners are not executed dependencies.
SOURCE_FILES = ("__init__.py", "model.py", "runtime.py", "routing.py", "evaluation.py",
                "learning.py", "phase2_scenarios.py", "prebalance.py",
                "prebalance_reference.py", "run_prebalance_reference.py")


def regional_factory():
    return RegionalCandidateGenerator(horizon=80, deadline_ms=None)


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _hash(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _sources():
    folder = Path(__file__).resolve().parent
    return {name: sha256((folder / name).read_bytes()).hexdigest() for name in SOURCE_FILES}


@dataclass(frozen=True)
class EvaluationCase:
    source_group: str
    family: str
    state: object
    forecasts: tuple
    future_bags: tuple  # Runner-only, never passed to either controller.
    horizon: int
    route_mode: str
    proxy_destinations: dict


def _cases(groups, seed):
    cases = [EvaluationCase(fixture.name, "mechanism_fixture", fixture.snapshot, fixture.forecasts,
                            fixture.future_bags, fixture.horizon, "whole_route", {"A": "B", "B": "A"})
             for fixture in synthetic_prebalance_fixtures()]
    for index in range(groups):
        scene = make_scene(index, HOLDOUT_NAMESPACE)
        cases.append(EvaluationCase(scene.source_group, "new_synthetic_holdout", scene.initial,
                                    scene.forecasts, scene.future(seed), scene.horizon, "next_edge", {}))
    return cases


def run(output: Path = DEFAULT_OUTPUT, *, groups=8, future_seed=DEFAULT_SEED,
        max_rollouts=12, max_transfer_depth=2, diagnostic=False):
    if groups < 0:
        raise ValueError("groups must be nonnegative")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("output must be a new or empty directory; existing experiment records are immutable")
    output.mkdir(parents=True, exist_ok=True)
    hashes_before = _sources()
    snapshot_dir = output / "source_snapshot"
    snapshot_dir.mkdir(exist_ok=True)
    for name in hashes_before:
        (snapshot_dir / name).write_bytes((Path(__file__).resolve().parent / name).read_bytes())
    settings = {
        "planning_horizon": 40, "forecast_publication_ttl": 60, "score_horizon": 32,
        "max_rollouts_per_decision": max_rollouts, "max_transfer_depth": max_transfer_depth,
        "paths_per_request": 2, "max_pool_per_state": 8, "max_search_calls_per_decision": 32,
        "proxy_continuation": "fixed_earliest_route_plus_reactive_empty_dispatch",
        "proxy_deadline_slack_for_anonymous_forecasts": 20,
        "wall_clock_cutoffs_enabled": False,
        "forecast_destinations_for_four_fixtures": {"A": "B", "B": "A"},
    }
    _write(output / "declared_protocol.json", {"settings": settings, "future_seed": future_seed,
                                              "holdout_namespace": HOLDOUT_NAMESPACE, "groups": groups,
                                              "diagnostic": diagnostic})
    rows, manifests, comparisons = [], [], []
    for case_index, case in enumerate(_cases(groups, future_seed)):
        state_data = asdict(case.state)
        forecasts = [asdict(forecast) for forecast in case.forecasts]
        truth = [asdict(bag) for bag in case.future_bags]
        expected = {**case.state.bags, **{bag.bag_id: bag for bag in case.future_bags}}
        identities = {"initial_sha256": _hash(state_data), "forecast_sha256": _hash(forecasts), "future_sha256": _hash(truth)}
        manifests.append({"source_group": case.source_group, "family": case.family, "state": state_data,
                          "forecasts": forecasts, "future_event_engine_only": truth, "horizon": case.horizon,
                          "route_mode": case.route_mode, **identities})
        group_rows = []
        for policy in ("reactive_only", "predictive_greedy", "bounded_forecast_reference"):
            shared = {"planning_horizon": settings["planning_horizon"], "max_forecast_age": 60,
                      "generator_factory": regional_factory, "planning_budget_ms": None}
            controller = (PredictivePrebalancer(case.forecasts, **shared) if policy == "predictive_greedy" else
                          BoundedForecastPrebalancer(case.forecasts, score_horizon=32, max_rollouts=max_rollouts,
                                                     max_transfer_depth=max_transfer_depth, paths_per_request=2,
                                                     max_pool_per_state=8, max_search_calls=32,
                                                     proxy_destinations=case.proxy_destinations,
                                                     proxy_route_mode=case.route_mode, **shared)
                          if policy == "bounded_forecast_reference" else None)
            engine = Simulation(case.state, case.future_bags, route_mode=case.route_mode,
                                generator_factory=regional_factory, slow_controller=controller,
                                reactive_empty_dispatch=True)
            started = perf_counter()
            result, failure = None, None
            try:
                result = engine.advance(case.horizon)
            except Exception as error:
                failure = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
            elapsed_ms = (perf_counter() - started) * 1000
            history = engine.slow_controller.history if engine.slow_controller is not None else []
            actual_ledger = [{**asdict(bag), "load_time": engine.state.load_times.get(bag_id),
                              "completion_time": engine.state.completed.get(bag_id),
                              "on_time": bag_id in engine.state.completed and engine.state.completed[bag_id] <= bag.deadline}
                             for bag_id, bag in sorted(expected.items())]
            proxy_calls = sum(call.get("rollout_calls", 0) for call in history)
            row = {"source_group": case.source_group, "family": case.family, "policy": policy,
                   "status": "failed" if failure else "completed_run", "route_mode": case.route_mode,
                   **identities, "actual_bag_count": len(expected), "completed_count": len(engine.state.completed),
                   "uncompleted_count": len(expected) - len(engine.state.completed),
                   "on_time_count": sum(item["on_time"] for item in actual_ledger),
                   "total_cost": result.total_cost if result else None,
                   **(result.cost_components if result else {key: None for key in COST_WEIGHTS}),
                   "empty_transfer_commits": int(engine.policy_stats["slow_commits"]),
                   "slow_controller_calls": int(engine.policy_stats["slow_calls"]),
                   "full_proxy_simulator_calls": proxy_calls,
                   "full_evaluation_simulator_calls": 1,
                   "failed_proxy_rollouts": sum(len(call.get("failed_proxy_rollouts", ())) for call in history),
                   "candidate_generation_calls": sum(call["search_calls"] for call in history),
                   "bounded_partial_decisions": sum(call.get("status") == "partial_bounded_search" for call in history),
                   "max_proxy_calls_at_one_decision": max((call.get("rollout_calls", 0) for call in history), default=0),
                   "max_decision_ms": max((call["elapsed_ms"] for call in history), default=0),
                   "proxy_rollout_ms": sum(call.get("rollout_ms", 0) for call in history),
                   "slow_controller_ms": engine.policy_stats["slow_ms"], "runtime_ms": elapsed_ms,
                   "finite_tray_ids_preserved": set(engine.state.trays) == set(case.state.trays),
                   "all_arrived_bag_ids_preserved": set(engine.state.bags) == {bag_id for bag_id, bag in expected.items() if bag.arrival <= engine.state.now},
                   "invariant_checks": result.invariant_checks if result else engine._checks,
                   "failure_type": failure["type"] if failure else None}
            rows.append(row)
            group_rows.append(row)
            _write(output / f"case_{case_index:03d}__{policy}.json",
                   {"metrics": row, "actual_bag_ledger": actual_ledger, "final_snapshot": asdict(engine.state),
                    "trace": list(result.trace) if result else list(engine._trace), "controller_history": history,
                    "failure": failure})
        by_name = {row["policy"]: row for row in group_rows}
        greedy, reference = by_name["predictive_greedy"], by_name["bounded_forecast_reference"]
        delta = None if reference["total_cost"] is None or greedy["total_cost"] is None else reference["total_cost"] - greedy["total_cost"]
        comparisons.append({"source_group": case.source_group, "family": case.family,
                            "reference_minus_greedy_cost": delta,
                            "reference_minus_greedy_completed": reference["completed_count"] - greedy["completed_count"],
                            "reference_minus_greedy_on_time": reference["on_time_count"] - greedy["on_time_count"],
                            "matched_observations_initial_and_truth": len({tuple(row[key] for key in identities) for row in group_rows}) == 1})
    hashes_after = _sources()
    by_policy = {}
    for policy in ("reactive_only", "predictive_greedy", "bounded_forecast_reference"):
        selected = [row for row in rows if row["policy"] == policy]
        costs = [row["total_cost"] for row in selected if row["total_cost"] is not None]
        by_policy[policy] = {"run_count": len(selected), "failed_runs": sum(row["status"] == "failed" for row in selected),
                             "cost_available_count": len(costs), "mean_cost": mean(costs) if costs else None,
                             "all_bags_denominator": sum(row["actual_bag_count"] for row in selected),
                             "completed_count": sum(row["completed_count"] for row in selected),
                             "on_time_count": sum(row["on_time_count"] for row in selected),
                             "full_proxy_simulator_calls": sum(row["full_proxy_simulator_calls"] for row in selected),
                             "full_evaluation_simulator_calls": len(selected),
                             "failed_proxy_rollouts": sum(row["failed_proxy_rollouts"] for row in selected),
                             "empty_transfer_commits": sum(row["empty_transfer_commits"] for row in selected),
                             "bounded_partial_decisions": sum(row["bounded_partial_decisions"] for row in selected),
                             "mean_runtime_ms": mean(row["runtime_ms"] for row in selected),
                             "max_decision_ms": max(row["max_decision_ms"] for row in selected)}
    valid_deltas = [row["reference_minus_greedy_cost"] for row in comparisons if row["reference_minus_greedy_cost"] is not None]
    family_comparisons = {}
    for family in ("mechanism_fixture", "new_synthetic_holdout"):
        paired = [row for row in comparisons if row["family"] == family]
        deltas = [row["reference_minus_greedy_cost"] for row in paired if row["reference_minus_greedy_cost"] is not None]
        family_comparisons[family] = {
            "source_group_count": len(paired), "cost_pairs_available": len(deltas),
            "mean_cost_delta": mean(deltas) if deltas else None,
            "better": sum(value < -1e-9 for value in deltas),
            "equal": sum(abs(value) <= 1e-9 for value in deltas),
            "worse": sum(value > 1e-9 for value in deltas),
            "completed_delta": sum(row["reference_minus_greedy_completed"] for row in paired),
            "on_time_delta": sum(row["reference_minus_greedy_on_time"] for row in paired),
        }
    summary = {
        "schema": "czr005.ics_circulation_v3.phase3_prebalance_reference.v1", "diagnostic": diagnostic,
        "scope": "FOUR_MECHANISM_FIXTURES_AND_FRESH_SYNTHETIC_SOURCE_GROUPS_NOT_REAL_AIRPORT_VALIDATION",
        "run_count": len(rows), "mechanism_fixture_count": 4, "fresh_source_group_count": groups,
        "holdout_namespace": HOLDOUT_NAMESPACE, "future_seed": future_seed,
        "settings": settings, "weights": COST_WEIGHTS, "source_sha256": hashes_before,
        "source_hash_scope": "entrypoint_plus_complete_local_import_dependency_closure",
        "source_changed_during_run": hashes_before != hashes_after, "source_sha256_after": hashes_after,
        "all_matched_inputs": all(row["matched_observations_initial_and_truth"] for row in comparisons),
        "all_finite_tray_ids_preserved": all(row["finite_tray_ids_preserved"] for row in rows),
        "all_arrived_bag_ids_preserved": all(row["all_arrived_bag_ids_preserved"] for row in rows),
        "failed_run_count": sum(row["status"] == "failed" for row in rows), "by_policy": by_policy,
        "reference_vs_greedy_by_family": family_comparisons,
        "reference_vs_greedy": {"cost_pairs_available": len(valid_deltas),
                                "mean_cost_delta": mean(valid_deltas) if valid_deltas else None,
                                "better": sum(value < -1e-9 for value in valid_deltas),
                                "equal": sum(abs(value) <= 1e-9 for value in valid_deltas),
                                "worse": sum(value > 1e-9 for value in valid_deltas)},
        "limitations": [
            "The reference chooses the best successfully scored explicit action sequence under one published-forecast proxy, not a globally optimal MPC.",
            "The action family has bounded transfer depth, bounded path witnesses and earliest/need-time departure variants; truncated searches and unscored actions are logged.",
            "Candidates are independently generated for current empty donors and destinations with first-use inventory deficits; speculative buffer moves and future-available donor dispatches are outside this action family.",
            "No-transfer is included. Source inventory and demand-prefix protections reuse the greedy implementation; module and receiver permissions still pass the unchanged validator.",
            "Hard loaded obligations are admitted before control; old transfers and accepted plans are never cancelled.",
            "Only the evaluation runner reads actual future bags. The scoring continuation is fixed causal reactive control without recursive predictive decisions.",
            "Forecast-only decisions can worsen true closed-loop outcomes; negative comparisons and all scheduled bags remain in the report.",
            "The four old mechanism fixtures are not held out; the separately named new synthetic source groups are held out from prior training and selection.",
            "Additional rollout/search work is fully counted. This reference is not claimed to meet a 100 ms production deadline.",
        ],
    }
    _write(output / "manifest.json", manifests)
    _write(output / "metrics.json", rows)
    _write(output / "comparisons.json", comparisons)
    _write(output / "summary.json", summary)
    with (output / "metrics.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--groups", type=int, default=8)
    parser.add_argument("--future-seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--max-rollouts", type=int, default=12)
    parser.add_argument("--max-transfer-depth", type=int, default=2)
    parser.add_argument("--diagnostic", action="store_true")
    args = parser.parse_args(argv)
    result = run(args.output, groups=args.groups, future_seed=args.future_seed,
                 max_rollouts=args.max_rollouts, max_transfer_depth=args.max_transfer_depth,
                 diagnostic=args.diagnostic)
    print(json.dumps({key: result[key] for key in ("run_count", "failed_run_count", "source_changed_during_run", "by_policy", "reference_vs_greedy")}, ensure_ascii=False, indent=2))
    return 1 if result["failed_run_count"] or result["source_changed_during_run"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
