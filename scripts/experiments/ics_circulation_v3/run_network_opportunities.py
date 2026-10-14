"""Actual Nanning routing-call opportunities; no labels or model training.

The three declared development workloads retain original directed edges. Both
policies receive the same published forecasts and predictive controller. Search
failures and work-budget stops stay in the denominator. Action keys include
conditional state; physical-prefix signatures deliberately do not.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from time import perf_counter, process_time
import traceback

from .audit_nanning import DEFAULT_PROFILE
from .experiment_protocol import check_output_directory, create_output_directory, write_new_json
from .phase4_control import ControlSpec, PeriodicSlowController, PublishedRoutingSelector, control_contract
from .phase4_network_workloads import file_sha, load_network, make_workload
from .prebalance import PredictivePrebalancer
from .routing import clear_static_cache
from .runtime import ExecutionValidator, Simulation, actual_action_key, assert_invariants
from .run_workload_diagnostics import (DiagnosticBudget, NetworkObserver, RecordedFactory,
    SOURCES as WORKLOAD_SOURCES, WorkBudgetExceeded, empty_capacity_diagnostic)

SCENES = ("cross_cycle", "counterflow", "near_full")
SOURCES = ("run_network_opportunities.py", *WORKLOAD_SOURCES)
DEFAULT_OUTPUT = Path(__file__).resolve().parents[3] / "outputs/experiments/ics_circulation_v3/phase4_w3_network_opportunities_20261009"
DEFAULT_BUDGET = DiagnosticBudget(max_wall_seconds=20.)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def physical_prefix(snapshot, candidate, route_mode="next_edge"):
    """Diagnostic geometry/time only; never an authorization key replacement."""
    prefix = ExecutionValidator._safe_prefix(snapshot, candidate) if route_mode == "next_edge" else candidate
    destination = (snapshot.network.edges[prefix.legs[-1].edge_id].target if prefix.legs
                   else snapshot.trays[prefix.tray_id].node)
    return {"tray_id": prefix.tray_id, "bag_id": prefix.bag_id,
            "legs": [asdict(leg) for leg in prefix.legs], "destination_node": destination,
            "unload_complete": prefix.unload_complete, "usable_at": prefix.usable_at,
            "prefix_only": prefix.prefix_only}


def physical_projection(state):
    """No candidate IDs, watermarks or retained conditional witnesses."""
    return {"time": state.now, "trays": {k: asdict(v) for k, v in state.trays.items()},
            "visible_bags": {k: asdict(v) for k, v in state.bags.items()},
            "completed": state.completed, "load_times": state.load_times,
            "reservations": [asdict(r) for r in state.reservations],
            "plans": {k: physical_prefix(state, p, "whole_route") for k, p in state.plans.items()},
            "old_in_transit": [asdict(f) for f in state.old_in_transit],
            "empty_targets": state.empty_targets}


class OpportunitySelector:
    def __init__(self, spec, forecasts):
        self.spec = spec
        self.selector = PublishedRoutingSelector(spec, forecasts)
        self.history = []

    def __call__(self, state, candidates):
        chosen = self.selector(state, candidates)
        prefixes = [physical_prefix(state, c, self.spec.route_mode) for c in candidates]
        keys = [actual_action_key(state, c, route_mode=self.spec.route_mode) for c in candidates]
        tray = state.trays[chosen.tray_id]
        # State is supplied by runtime after earlier same-tick admissions, not
        # reconstructed from the initial condition or an external replay.
        observed = asdict(state)
        observed.pop("network")
        self.history.append({"time": state.now, "version": state.version,
            "node": tray.node, "tray_id": tray.tray_id, "bag_id": tray.bag_id,
            "protected": state.bags[tray.bag_id].protected,
            "candidate_count": len(candidates), "actual_action_distinct": len(set(keys)),
            "physical_prefix_distinct": len({digest(p) for p in prefixes}),
            "actual_action_keys": keys, "physical_prefixes": prefixes,
            "candidates": [asdict(c) for c in candidates], "chosen_index": candidates.index(chosen),
            "chosen_action_key": actual_action_key(state, chosen, route_mode=self.spec.route_mode),
            "chosen_physical_prefix": physical_prefix(state, chosen, self.spec.route_mode),
            "observable_state_without_static_network": observed,
            "physical_projection_sha256": digest(physical_projection(state)),
            "capacity_subtraction_diagnostic": empty_capacity_diagnostic(state, tray.bag_id, tray.tray_id, candidates)})
        return chosen


class OpportunityObserver(NetworkObserver):
    def __init__(self):
        super().__init__()
        self.boundaries = []

    def __call__(self, state):
        super().__call__(state)
        self.boundaries.append({"time": state.now,
            "physical_projection_sha256": digest(physical_projection(state)),
            "visible_bag_count": len(state.bags), "completed": len(state.completed),
            "waiting_bag_count": sum(b not in state.completed and b not in state.load_times for b in state.bags),
            "eligible_loaded_count": sum(t.mode == "loaded" and t.tray_id not in state.plans
                                           for t in state.trays.values())})


def run_case(scene, routing, budget=DEFAULT_BUDGET):
    if routing not in {"baseline", "timed"}:
        raise ValueError("routing must be baseline or timed")
    clear_static_cache()
    spec = ControlSpec(routing=routing, predictive=True, slow_period=2, planning_horizon=180,
        route_mode="next_edge", candidate_count=4, expansion_limit=budget.per_search_work, static_path_limit=8)
    factory = RecordedFactory(spec, budget)
    contract = control_contract(spec, scene.forecasts, start_tick=scene.initial.now)
    selector = OpportunitySelector(spec, scene.forecasts)
    slow = PeriodicSlowController(PredictivePrebalancer((), planning_horizon=spec.planning_horizon,
        planning_budget_ms=None, generator_factory=factory), period=spec.slow_period,
        first_trigger_at=scene.initial.now, contract=contract, forecast_publications=scene.forecasts)
    observer = OpportunityObserver()
    engine = Simulation(scene.initial, scene.future_bags, route_mode=spec.route_mode, generator_factory=factory,
        route_selector=selector, slow_controller=slow, observer=observer,
        search_horizon=spec.planning_horizon, candidate_count=spec.candidate_count)
    selector, slow = engine.route_selector, engine.slow_controller
    slow.controller.generator_factory = factory
    started, cpu = perf_counter(), process_time()
    failure, exhausted = None, None
    try:
        while engine.state.now < scene.horizon:
            factory.check()
            engine.advance(engine.state.now + 1)
        assert_invariants(engine.state)
    except WorkBudgetExceeded as error:
        exhausted = str(error)
    except Exception as error:
        failure = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
    all_bags = {**scene.initial.bags, **{b.bag_id: b for b in scene.future_bags}}
    loaded_queries = [row for row in factory.rows if row["bag_id"] is not None]
    queries_without_callbacks = len(loaded_queries) - len(selector.history)
    completed = len(set(all_bags) & set(engine.state.completed))
    reached = engine.state.now == scene.horizon and failure is None and exhausted is None
    result = engine.result() if failure is None else None
    status = ("execution_failure" if failure else "budget_exhausted" if exhausted else
              "completed_all" if completed == len(all_bags) else "unfinished_at_horizon")
    metrics = {"scene": scene.name, "routing": routing, "status": status,
        "stopped_at": engine.state.now, "horizon": scene.horizon, "reached_horizon": reached,
        "scheduled_bags": len(all_bags), "completed": completed,
        "uncompleted_including_unobserved": len(all_bags) - completed,
        "future_unobserved": len(set(all_bags) - set(engine.state.bags)),
        "total_cost": result.total_cost if reached else None,
        "routing_boundaries": len(observer.boundaries), "actual_selector_calls": len(selector.history),
        "loaded_search_calls": len(loaded_queries), "loaded_queries_without_selector": queries_without_callbacks,
        "loaded_zero_candidate_queries": sum(row["candidate_count"] == 0 for row in loaded_queries),
        "selector_candidate_count_histogram": dict(Counter(row["candidate_count"] for row in selector.history)),
        "action_distinct_histogram": dict(Counter(row["actual_action_distinct"] for row in selector.history)),
        "physical_prefix_distinct_histogram": dict(Counter(row["physical_prefix_distinct"] for row in selector.history)),
        "multiple_action_calls": sum(row["actual_action_distinct"] > 1 for row in selector.history),
        "multiple_physical_prefix_calls": sum(row["physical_prefix_distinct"] > 1 for row in selector.history),
        "noninitial_selector_calls": sum(row["time"] > scene.initial.now for row in selector.history),
        "source_bag_count_with_selector": len({row["bag_id"] for row in selector.history}),
        "source_tray_count_with_selector": len({row["tray_id"] for row in selector.history}),
        "binding_empty_resource_queries": sum(any(r["binding_empty_occupancy"] for r in row["resources"])
                                               for row in factory.resource_competition),
        "search_calls": len(factory.rows), "search_work": factory.work, "budget_stop": exhausted,
        "accepted_slow_transfers": sum(len(row["proposals"]) for row in slow.history),
        "actual_slow_trigger_times": slow.trigger_times,
        "wall_seconds": perf_counter() - started, "cpu_seconds": process_time() - cpu}
    return {"metrics": metrics, "control_contract": contract, "budget": asdict(budget),
        "selector_calls": selector.history, "routing_boundaries": observer.boundaries,
        "searches": factory.rows, "resource_activity": observer.summary(),
        "capacity_subtraction_diagnostics": factory.resource_competition, "slow_history": slow.history,
        "ledger": [{**asdict(b), "observed": b.bag_id in engine.state.bags,
            "load_time": engine.state.load_times.get(b.bag_id), "completed_at": engine.state.completed.get(b.bag_id)}
            for b in all_bags.values()], "event_trace": list(engine._trace), "failure": failure}


def run(output=DEFAULT_OUTPUT, *, profile=DEFAULT_PROFILE, names=SCENES, budget=DEFAULT_BUDGET):
    output = check_output_directory(output)
    if not names or len(set(names)) != len(names) or not set(names) <= set(SCENES):
        raise ValueError("select a nonempty distinct subset of the three predeclared scenes")
    network, topology = load_network(profile)
    scenes = [make_workload(name, network, topology, rounds=3) for name in names]
    source = Path(__file__).parent
    hashes = {name: file_sha(source / name) for name in SOURCES}
    output = create_output_directory(output)
    snapshot = output / "source_snapshot"
    snapshot.mkdir()
    for name in SOURCES:
        (snapshot / name).write_bytes((source / name).read_bytes())
    write_new_json(output / "protocol.json", {"schema": "ics_v3_network_opportunities_v1",
        "scope": "development observed-state opportunity diagnosis only; no labels or fitted model",
        "scenes": list(names), "policies": ["baseline", "timed"], "predictive_shared": True,
        "slow_period": 2, "route_mode": "next_edge", "candidate_count": 4, "planning_horizon": 180,
        "budget": asdict(budget), "source_sha256": hashes, "topology_sha256": topology["source_sha256"],
        "source_role": "same synthetic development flows on original graph; not operational records",
        "planned_runs": len(scenes) * 2, "new_independent_source_count": 0,
        "planned_bag_denominator": 2 * sum(len(s.initial.bags) + len(s.future_bags) for s in scenes),
        "opportunity_denominators": "actual routing selector calls; zero-candidate loaded searches counted separately",
        "key_distinction": "actual_action_key includes conditional state; physical_prefix_distinct hashes only owner-retained geometry/times",
        "limits": ["bounded candidate generator is not a feasibility or completeness oracle",
                   "same-time state projection difference is descriptive trajectory divergence, not a statistical distribution test",
                   "no new independence claim; original operating/service/permission gaps remain",
                   "wall guard is shared-machine dependent; deterministic work bounds are primary"]})
    write_new_json(output / "topology_audit.json", topology)
    cases, skipped, pairs = [], [], []
    started = perf_counter()
    for scene in scenes:
        write_new_json(output / f"{scene.name}__workload.json", {"provenance": scene.provenance,
            "initial": asdict(scene.initial), "forecasts": [asdict(f) for f in scene.forecasts],
            "evaluation_only_future_bags": [asdict(b) for b in scene.future_bags], "horizon": scene.horizon})
        local = {}
        for routing in ("baseline", "timed"):
            if perf_counter() - started >= budget.total_wall_seconds:
                skipped.append({"scene": scene.name, "routing": routing, "status": "not_executed_total_wall_budget",
                    "scheduled_bags": len(scene.initial.bags) + len(scene.future_bags)})
                continue
            case = run_case(scene, routing, budget)
            write_new_json(output / f"{scene.name}__{routing}.json", case)
            cases.append(case)
            local[routing] = case
            print({k: case["metrics"][k] for k in ("scene", "routing", "status", "completed", "actual_selector_calls",
                                                 "multiple_physical_prefix_calls", "search_work")}, flush=True)
        if len(local) == 2:
            baseline, timed = (local[k]["metrics"] for k in ("baseline", "timed"))
            left, right = ({r["time"]: r["physical_projection_sha256"] for r in local[k]["routing_boundaries"]}
                           for k in ("baseline", "timed"))
            common = sorted(left.keys() & right.keys())
            comparable = all(m["reached_horizon"] for m in (baseline, timed)) and baseline["completed"] == timed["completed"]
            pairs.append({"scene": scene.name, "baseline_status": baseline["status"], "timed_status": timed["status"],
                "scheduled_each": baseline["scheduled_bags"], "baseline_completed": baseline["completed"],
                "timed_completed": timed["completed"], "common_observed_ticks": len(common),
                "different_physical_projection_ticks": sum(left[t] != right[t] for t in common),
                "baseline_cost": baseline["total_cost"], "timed_cost": timed["total_cost"],
                "cost_comparable_same_horizon_and_completion": comparable,
                "timed_minus_baseline": timed["total_cost"] - baseline["total_cost"] if comparable else None})
    summary = {"schema": "ics_v3_network_opportunities_summary_v1", "source_sha256": hashes,
        "source_changed_during_run": hashes != {name: file_sha(source / name) for name in SOURCES},
        "planned_runs": len(scenes) * 2, "executed_runs": len(cases), "not_executed": skipped,
        "status_counts": dict(Counter(c["metrics"]["status"] for c in cases)),
        "planned_bag_denominator": 2 * sum(len(s.initial.bags) + len(s.future_bags) for s in scenes),
        "executed_bag_denominator": sum(c["metrics"]["scheduled_bags"] for c in cases),
        "run_metrics": [c["metrics"] for c in cases], "paired_comparisons": pairs,
        "total_search_work": sum(c["metrics"]["search_work"] for c in cases),
        "total_search_calls": sum(c["metrics"]["search_calls"] for c in cases),
        "wall_seconds": perf_counter() - started, "labels_generated": 0, "new_independent_source_count": 0}
    write_new_json(output / "summary.json", summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--scenes", nargs="+", choices=SCENES, default=SCENES)
    args = parser.parse_args(argv)
    summary = run(args.output, profile=args.profile, names=tuple(args.scenes))
    print(json.dumps({k: summary[k] for k in ("executed_runs", "status_counts", "total_search_work", "wall_seconds")}))
    return int(bool(summary["not_executed"] or summary["source_changed_during_run"]
                    or summary["status_counts"].get("execution_failure")))


if __name__ == "__main__":
    raise SystemExit(main())
