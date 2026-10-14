"""Run matched synthetic closed-loop non-learning prebalancing comparisons."""
from __future__ import annotations

from .experiment_protocol import check_output_directory, create_output_directory

import argparse
from collections import Counter
import csv
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from time import perf_counter

from .prebalance import PredictivePrebalancer, synthetic_prebalance_fixtures
from .runtime import Simulation


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = ROOT / "outputs/experiments/ics_circulation_v3/phase2_prebalance_20261009"


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _hash(value) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _write(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _sources() -> dict[str, str]:
    directory = Path(__file__).resolve().parent
    return {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in ("run_prebalance.py", "prebalance.py", "model.py", "runtime.py", "evaluation.py")}


def run(output: Path = DEFAULT_OUTPUT, *, route_mode: str = "whole_route") -> dict:
    """Same snapshot and exogenous tape under four independently toggled policies."""
    if route_mode not in {"whole_route", "next_edge"}:
        raise ValueError("route_mode must be whole_route or next_edge")
    output = create_output_directory(output)
    source_hashes = _sources()
    rows, traces, controller_logs, manifests = [], {}, {}, []
    policies = (
        ("no_empty_dispatch", False, False),
        ("reactive_only", False, True),
        ("predictive_only", True, False),
        ("predictive_plus_reactive", True, True),
    )
    for fixture in synthetic_prebalance_fixtures():
        initial = asdict(fixture.snapshot)
        future = [asdict(bag) for bag in fixture.future_bags]
        input_hash, future_hash = _hash(initial), _hash(future)
        manifests.append({"fixture": fixture.name, "initial_state": initial, "future_bags_event_engine_only": future,
                          "forecasts": [asdict(forecast) for forecast in fixture.forecasts],
                          "horizon": fixture.horizon, "initial_sha256": input_hash, "future_sha256": future_hash})
        actual_bags = {**fixture.snapshot.bags, **{bag.bag_id: bag for bag in fixture.future_bags}}
        for policy, predictive, reactive in policies:
            controller = PredictivePrebalancer(fixture.forecasts, planning_budget_ms=100) if predictive else None
            engine = Simulation(fixture.snapshot, fixture.future_bags,
                                route_mode=route_mode, slow_controller=controller,
                                reactive_empty_dispatch=reactive)
            begin = perf_counter()
            result = engine.advance(fixture.horizon)
            runtime_ms = (perf_counter() - begin) * 1000
            scene_policy = f"{fixture.name}/{policy}"
            traces[scene_policy] = list(result.trace)
            # Simulation owns an isolated policy instance; inspect that instance,
            # not the caller's untouched construction object.
            history = engine.slow_controller.history if predictive else []
            controller_logs[scene_policy] = history
            actions = [event for event in result.trace if event["event"] in {
                "slow_commit", "empty_dispatch", "depart", "old_arrive", "load", "unload_complete",
            }]
            on_time = sum(bag_id in result.completed and result.completed[bag_id] <= bag.deadline
                          for bag_id, bag in actual_bags.items())
            waits = [max(0, result.final_snapshot.load_times.get(bag_id, fixture.horizon) - bag.arrival)
                     for bag_id, bag in actual_bags.items()]
            reasons = Counter(row["reason"] for call in history for row in call["candidate_rejections"])
            row = {
                "fixture": fixture.name, "policy": policy, "route_mode": route_mode,
                "predictive_enabled": predictive, "reactive_enabled": reactive,
                "initial_sha256": input_hash, "future_sha256": future_hash,
                "actual_bag_count": len(actual_bags), "completed_count": len(result.completed),
                "on_time_count": on_time, "on_time_fraction": on_time / len(actual_bags) if actual_bags else None,
                "uncompleted_count": len(result.uncompleted_bag_ids),
                "waiting_count_at_horizon": len(result.waiting_bag_ids),
                "max_tray_wait_ticks": max(waits, default=0),
                "total_cost": result.total_cost, **result.cost_components,
                "slow_commits": int(result.policy_stats["slow_commits"]),
                "reactive_commits": sum(event["event"] == "empty_dispatch" for event in result.trace),
                "invariant_checks": result.invariant_checks,
                "finite_tray_ids_preserved": set(result.final_trays) == set(fixture.snapshot.trays),
                "runtime_ms": runtime_ms, "slow_ms": result.policy_stats["slow_ms"],
                "max_planning_call_ms": max((call["elapsed_ms"] for call in history), default=0),
                "search_calls": sum(call["search_calls"] for call in history),
                "initial_old_in_transit_count": len(fixture.snapshot.old_in_transit),
            }
            rows.append(row)
            _write(output / (fixture.name + "__" + policy + "__actions.json"),
                   {"actions": actions, "proposal_details": [detail for call in history for detail in call["proposal_details"]],
                    "candidate_rejection_reasons": dict(reasons)})
    comparisons = []
    for fixture in synthetic_prebalance_fixtures():
        group = {row["policy"]: row for row in rows if row["fixture"] == fixture.name}
        baseline, treated = group["reactive_only"], group["predictive_plus_reactive"]
        comparisons.append({"fixture": fixture.name,
                            "reactive_cost": baseline["total_cost"], "predictive_plus_reactive_cost": treated["total_cost"],
                            "cost_delta": treated["total_cost"] - baseline["total_cost"],
                            "tray_wait_delta": treated["tray_wait"] - baseline["tray_wait"],
                            "matched_initial_and_future": len({(row["initial_sha256"], row["future_sha256"]) for row in group.values()}) == 1})
    source_hashes_after = _sources()
    summary = {
        "schema": "czr005.ics_circulation_v3.prebalance_closed_loop.v1",
        "scope": "FOUR_SYNTHETIC_MECHANISMS_FIXED_LOCAL_MODULE_PROXY_NOT_AIRPORT_VALIDATION",
        "route_mode": route_mode, "policy_count": len(policies), "run_count": len(rows),
        "source_sha256": source_hashes, "source_changed_during_run": source_hashes_after != source_hashes,
        "all_matched": all(row["matched_initial_and_future"] for row in comparisons),
        "all_finite_tray_ids_preserved": all(row["finite_tray_ids_preserved"] for row in rows),
        "comparisons": comparisons,
        "limitations": [
            "All capacities, durations, forecasts and future arrivals are explicit synthetic assumptions.",
            "This is bounded greedy first-use supply accounting, not a global optimum or MPC.",
            "Forecasts are observations; future_bags are passed only to the event engine.",
            "The demand reversal is deliberately retained even when predictive transfers worsen service.",
            "Only physical simulator invariants are checked; no production supplier integration or distributed guarantee is claimed.",
            "The wall-clock budget is checked between generator calls; it is not a hard real-time interrupt.",
        ],
    }
    _write(output / "manifest.json", manifests)
    _write(output / "summary.json", summary)
    _write(output / "metrics.json", rows)
    _write(output / "traces.json", traces)
    _write(output / "controller_diagnostics.json", controller_logs)
    with (output / "metrics.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--route-mode", choices=("whole_route", "next_edge"), default="whole_route")
    args = parser.parse_args(argv)
    print(json.dumps(run(args.output, route_mode=args.route_mode), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
