"""Bounded mechanism diagnostics on original Nanning topology, not acceptance.

Optional projected inputs must be supplied explicitly as raw/canonical/manifest.
All original and selected-window denominators remain in the output. The primary
budget is deterministic route-search work; wall time is a disclosed safeguard.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import time
import traceback

from .audit_nanning import DEFAULT_PROFILE
from .experiment_protocol import check_output_directory, create_output_directory, write_new_json
from .phase4_control import (ControlSpec, GeneratorFactory, LoggedSelector, PeriodicSlowController,
                             PublishedRoutingSelector, control_contract)
from .phase4_network_workloads import (NetworkAssumptions, SCENE_NAMES, file_sha, load_network,
    make_workload, projected_window, read_projected_tasks, shortest_paths)
from .model import Leg, RouteCandidate
from .prebalance import PredictivePrebalancer
from .routing import clear_static_cache
from .runtime import Simulation, assert_invariants, candidate_reservations, capacity_conflict, effective_reservations

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = ROOT / "outputs/experiments/ics_circulation_v3/phase4_w2_workloads_20261009"
SOURCES = ("run_workload_diagnostics.py", "phase4_network_workloads.py", "phase4_control.py",
           "nanning_routing_benchmark.py", "audit_nanning.py", "experiment_protocol.py",
           "conditional_evaluation.py", "prebalance.py", "learning.py", "evaluation.py",
           "routing.py", "routing_reference.py", "runtime.py", "model.py")


class WorkBudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class DiagnosticBudget:
    max_search_calls: int = 300
    max_search_work: int = 300000
    per_search_work: int = 3000
    max_wall_seconds: float = 15.0
    total_wall_seconds: float = 180.0

    def __post_init__(self):
        if any(type(x) is not int or x < 1 for x in
               (self.max_search_calls, self.max_search_work, self.per_search_work)):
            raise ValueError("work budgets must be positive integers")
        if any(not math.isfinite(v) or v <= 0 for v in (self.max_wall_seconds, self.total_wall_seconds)):
            raise ValueError("wall safeguards must be positive")


class RecordedFactory:
    def __init__(self, spec, budget):
        self.spec, self.budget = spec, budget
        self.rows, self.work, self.started = [], 0, time.perf_counter()
        self.resource_competition = []

    def check(self):
        if len(self.rows) >= self.budget.max_search_calls:
            raise WorkBudgetExceeded("max_search_calls")
        if self.work >= self.budget.max_search_work:
            raise WorkBudgetExceeded("max_search_work")
        if time.perf_counter() - self.started >= self.budget.max_wall_seconds:
            raise WorkBudgetExceeded("wall_safeguard_between_calls_or_ticks")

    def __call__(self, horizon=None):
        return RecordedGenerator(self, GeneratorFactory(self.spec)(horizon))


class RecordedGenerator:
    def __init__(self, owner, generator):
        self.owner, self.generator = owner, generator

    @property
    def last_expansions(self):
        return self.generator.last_expansions

    @property
    def last_search_status(self):
        return self.generator.last_search_status

    def generate(self, snapshot, bag_id, tray_id, k=1):
        return self._call(snapshot, bag_id, tray_id, snapshot.bags[bag_id].destination, k)

    def generate_empty(self, snapshot, tray_id, destination, k=1):
        return self._call(snapshot, None, tray_id, destination, k)

    def _call(self, snapshot, bag_id, tray_id, destination, k):
        self.owner.check()
        self.generator.expansion_limit = min(self.owner.budget.per_search_work,
                                            self.owner.budget.max_search_work - self.owner.work)
        candidates = (self.generator.generate(snapshot, bag_id, tray_id, k) if bag_id is not None else
                      self.generator.generate_empty(snapshot, tray_id, destination, k))
        self.owner.work += self.generator.last_expansions
        self.owner.rows.append({"time": snapshot.now, "bag_id": bag_id, "tray_id": tray_id,
            "origin": snapshot.trays[tray_id].node, "destination": destination,
            "status": self.generator.last_search_status, "work": self.generator.last_expansions,
            "candidate_count": len(candidates)})
        if bag_id is not None:
            diagnostic = empty_capacity_diagnostic(snapshot, bag_id, tray_id, candidates)
            if diagnostic is not None:
                self.owner.resource_competition.append(diagnostic)
        return candidates


def empty_capacity_diagnostic(snapshot, bag_id, tray_id, candidates=()):
    """Read-only calendar subtraction probe, never an executable intervention.

    Compare the same earliest static loaded witness with and without the
    calendar footprint of committed empty transfers. Identity and physical
    state are untouched. This isolates capacity dependence, not full route
    legality or a realizable cancellation of the accepted empty commitment.
    """
    bag, tray = snapshot.bags[bag_id], snapshot.trays[tray_id]
    if tray.node is None:
        return None
    paths = shortest_paths(snapshot.network, tray.node)[1]
    if bag.destination not in paths:
        return None
    empty_ids = {key for key, p in snapshot.plans.items() if p.bag_id is None}
    if not empty_ids:
        return None
    tick, legs = snapshot.now, []
    for edge_id in paths[bag.destination]:
        end = tick + snapshot.network.edges[edge_id].travel_time
        legs.append(Leg(edge_id, tick, end))
        tick = end
    unload = tick + snapshot.module.unload_ticks
    witness = RouteCandidate("capacity-probe-only", bag_id, tray_id, tuple(legs), unload,
        unload + snapshot.module.hold_ticks(bag.destination), snapshot.version, "static_probe")
    proposed = candidate_reservations(snapshot, witness)
    existing = tuple(s for s in effective_reservations(snapshot) if s.tray_id != tray_id)
    overlaps = [s for s in existing if s.tray_id in empty_ids and any(
        s.resource == p.resource and s.start < p.end and p.start < s.end for p in proposed)]
    if not overlaps:
        return None
    full_conflict = capacity_conflict(snapshot, existing + proposed)
    without_conflict = capacity_conflict(snapshot, tuple(s for s in existing if s.tray_id not in empty_ids) + proposed)
    per_resource = []
    for resource in sorted({s.resource for s in overlaps}):
        resource_existing = tuple(s for s in existing if s.resource == resource)
        resource_proposed = tuple(s for s in proposed if s.resource == resource)
        with_empty = capacity_conflict(snapshot, resource_existing + resource_proposed)
        without_empty = capacity_conflict(snapshot, tuple(s for s in resource_existing if s.tray_id not in empty_ids) + resource_proposed)
        per_resource.append({"resource": resource, "conflict_with_empty": with_empty,
                             "conflict_without_empty": without_empty,
                             "binding_empty_occupancy": with_empty is not None and without_empty is None})
    actual = min(candidates, key=lambda c: c.unload_complete) if candidates else None
    return {"time": snapshot.now, "bag_id": bag_id, "tray_id": tray_id,
            "static_witness": asdict(witness), "competing_empty_slots": [asdict(s) for s in overlaps],
            "full_capacity_conflict": full_conflict, "without_committed_empty_capacity_conflict": without_conflict,
            "resources": per_resource, "selected_candidate_available": actual is not None,
            "candidate_unload_delay_vs_static": actual.unload_complete - unload if actual else None,
            "candidate_uses_different_path": tuple(l.edge_id for l in actual.legs) != tuple(l.edge_id for l in legs) if actual else None,
            "counterfactual_executed": False,
            "scope": "capacity-only subtraction of irrevocable empty occupancy; no permission to delete or cancel a physical tray or plan"}


class NetworkObserver:
    def __init__(self):
        self.full_nodes, self.mixed_edges, self.used_cross_edges = Counter(), Counter(), Counter()
        self.maximum_node_occupancy, self.maximum_edge_occupancy = Counter(), Counter()
        self.receiving_busy, self.observations, self.no_wait_parked_observations = 0, 0, 0

    def __call__(self, state):
        self.observations += 1
        occupants = Counter(t.node for t in state.trays.values() if t.node is not None)
        for node, count in occupants.items():
            self.maximum_node_occupancy[node] = max(self.maximum_node_occupancy[node], count)
            if count >= state.network.nodes[node].capacity:
                self.full_nodes[node] += 1
            # Observation precedes immediate departures; this is not itself a
            # stranded-no-wait violation. End-of-tick safety is asserted by owner.
            if not state.network.nodes[node].can_wait:
                self.no_wait_parked_observations += count
        active = defaultdict(set)
        for plan in state.plans.values():
            for leg in plan.legs:
                if leg.depart <= state.now < leg.arrive:
                    active[leg.edge_id].add((plan.tray_id, "empty" if plan.bag_id is None else "loaded"))
            if plan.bag_id is not None and plan.legs[-1].arrive <= state.now < plan.unload_complete:
                self.receiving_busy += 1
        for edge_id, users in active.items():
            edge = state.network.edges[edge_id]
            self.maximum_edge_occupancy[edge_id] = max(self.maximum_edge_occupancy[edge_id], len(users))
            if len({mode for _, mode in users}) > 1:
                self.mixed_edges[edge_id] += 1
            if state.network.nodes[edge.source].logistics_zone != state.network.nodes[edge.target].logistics_zone:
                self.used_cross_edges[edge_id] += 1

    def summary(self):
        return {"observations": self.observations, "node_at_capacity_ticks": dict(self.full_nodes),
                "max_node_occupancy": dict(self.maximum_node_occupancy),
                "max_edge_occupancy": dict(self.maximum_edge_occupancy),
                "loaded_empty_simultaneous_edge_ticks": dict(self.mixed_edges),
                "cross_system_edge_ticks": dict(self.used_cross_edges), "receiving_busy_observations": self.receiving_busy,
                "no_wait_predeparture_observations": self.no_wait_parked_observations}


def run_case(scene, *, predictive, budget=DiagnosticBudget(), per_search_work=None):
    clear_static_cache()
    spec = ControlSpec(routing="baseline", predictive=predictive, slow_period=4,
        planning_horizon=180, route_mode="whole_route", candidate_count=1,
        expansion_limit=per_search_work or budget.per_search_work, static_path_limit=8)
    if per_search_work is not None:
        budget = DiagnosticBudget(budget.max_search_calls, budget.max_search_work, per_search_work,
                                  budget.max_wall_seconds, budget.total_wall_seconds)
    factory = RecordedFactory(spec, budget)
    contract = control_contract(spec, scene.forecasts, start_tick=scene.initial.now)
    selector = LoggedSelector(PublishedRoutingSelector(spec, scene.forecasts), contract)
    controller = (PeriodicSlowController(PredictivePrebalancer((), planning_horizon=spec.planning_horizon,
                    planning_budget_ms=None, generator_factory=factory), period=spec.slow_period,
                    first_trigger_at=scene.initial.now, contract=contract,
                    forecast_publications=scene.forecasts) if predictive else None)
    observer = NetworkObserver()
    engine = Simulation(scene.initial, scene.future_bags, route_mode=spec.route_mode, generator_factory=factory,
        route_selector=selector, slow_controller=controller, observer=observer,
        search_horizon=spec.planning_horizon, candidate_count=spec.candidate_count)
    # Simulation clones policy state. Reconnect only the accounting wrapper so
    # loaded, reactive-empty and slow searches share the same diagnostic budget.
    selector, controller = engine.route_selector, engine.slow_controller
    if controller is not None:
        controller.controller.generator_factory = factory
    failure, exhausted, result = None, None, None
    try:
        while engine.state.now < scene.horizon:
            factory.check()
            result = engine.advance(engine.state.now + 1)
    except WorkBudgetExceeded as error:
        exhausted = str(error)
    except Exception as error:
        failure = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
    expected = {**scene.initial.bags, **{b.bag_id: b for b in scene.future_bags}}
    completed = set(expected) & set(engine.state.completed)
    loads = {key: [tray.bag_id] if tray.bag_id else [] for key, tray in scene.initial.trays.items()}
    for event in engine._trace:
        if event["event"] == "load":
            loads[event["tray_id"]].append(event["bag_id"])
    rows = [{**asdict(bag), "observed": bag.bag_id in engine.state.bags,
             "load_time": engine.state.load_times.get(bag.bag_id),
             "completion_time": engine.state.completed.get(bag.bag_id)} for bag in expected.values()]
    structural = scene.provenance.get("explicit_unreachable_case")
    search_statuses = Counter(row["status"] for row in factory.rows)
    status = ("execution_failure" if failure else "budget_exhausted" if exhausted else
              "completed_all" if len(completed) == len(expected) else
              "structural_outbound_unreachable_present" if structural and structural["status"] == "outbound_unreachable" else
              "return_unreachable_and_unfinished" if structural and structural["status"] == "return_unreachable" else
              "budget_exhausted" if search_statuses["expansion_budget_exhausted"] else "unfinished_at_horizon")
    admitted = {r["bag_id"] for r in selector.history}
    admitted.update(p.bag_id for p in scene.initial.plans.values() if p.bag_id)
    protected = [b for b in expected.values() if b.protected]
    slow_actions = [{"trigger_time": entry["trigger_time"], **proposal}
                    for entry in (controller.history if controller else []) for proposal in entry["proposals"]]
    early = [action for action in slow_actions if any(b.origin == action["destination_node"] and
             b.arrival > action["legs"][0]["depart"] for b in expected.values())]
    invariant_error = None
    try:
        assert_invariants(engine.state)
    except Exception as error:
        invariant_error = str(error)
    metrics = {"scene": scene.name, "predictive": predictive, "status": status,
        "horizon": scene.horizon, "stopped_at": engine.state.now,
        "all_scheduled_bag_denominator": len(expected), "observed_bags": len(engine.state.bags),
        "completed": len(completed), "uncompleted_including_unobserved": len(expected) - len(completed),
        "future_unobserved": sum(not row["observed"] for row in rows),
        "on_time": sum(r["completion_time"] is not None and r["completion_time"] <= r["deadline"] for r in rows),
        "total_cost": result.total_cost if not failure and not exhausted and result else None,
        "cost_comparison_requires_same_horizon": True,
        "invariant_error": invariant_error, "invariant_checks": engine._checks,
        "initial_trays": len(scene.initial.trays), "tray_identity_preserved": set(engine.state.trays) == set(scene.initial.trays),
        "trays_serving_multiple_bags": sum(len(bags) > 1 for bags in loads.values()),
        "per_tray_bag_sequences": loads, "protected_bags": len(protected),
        "protected_admitted": sum(b.bag_id in admitted for b in protected),
        "protected_admitted_late": [b.bag_id for b in protected if b.bag_id in admitted and
                                    engine.state.completed.get(b.bag_id, -1) > b.deadline],
        "protected_unadmitted": [b.bag_id for b in protected if b.bag_id not in admitted],
        "accepted_slow_transfers": len(slow_actions), "slow_transfers_before_a_future_origin_demand": len(early),
        "actual_slow_trigger_times": list(controller.trigger_times) if controller else [],
        "search_calls": len(factory.rows), "search_work": factory.work,
        "search_status_counts": dict(search_statuses), "budget_stop": exhausted,
        "loaded_queries_overlapping_empty_reservations": len(factory.resource_competition),
        "binding_empty_resource_queries": sum(any(x["binding_empty_occupancy"] for x in row["resources"])
                                               for row in factory.resource_competition),
        "binding_empty_edge_queries": sum(any(x["binding_empty_occupancy"] and x["resource"].startswith("edge:")
                                                   for x in row["resources"]) for row in factory.resource_competition),
        "wall_seconds": time.perf_counter() - factory.started,
        "timing_claim": "shared-machine diagnostic wall time only; deterministic work and call budgets are primary"}
    return {"metrics": metrics, "control_contract": contract, "budget": asdict(budget),
        "resource_activity": observer.summary(), "ledger": rows, "searches": factory.rows,
        "slow_actions": slow_actions, "slow_diagnostics": controller.history if controller else [],
        "capacity_subtraction_diagnostics": factory.resource_competition,
        "route_decisions": selector.history, "event_trace": list(engine._trace),
        "failure": failure, "scope": "bounded original-topology mechanism diagnostic; not field acceptance"}


def run(output=DEFAULT_OUTPUT, *, profile=DEFAULT_PROFILE, names=SCENE_NAMES,
        budget=DiagnosticBudget(), projected_paths=None, rounds=3):
    output = check_output_directory(output)
    if not names or len(set(names)) != len(names) or any(name not in SCENE_NAMES for name in names):
        raise ValueError("scenario names must be a nonempty distinct subset of the predeclared matrix")
    if type(rounds) is not int or rounds < 2:
        raise ValueError("rounds must be at least two")
    network, topology = load_network(profile)
    projected_rows, projected_audit = (), {"status": "not_supplied", "reason": "explicit input paths required; no hidden-directory discovery"}
    if projected_paths is not None:
        projected_rows, projected_audit = read_projected_tasks(*projected_paths, topology)
    sources = {name: file_sha(Path(__file__).parent / name) for name in SOURCES}
    output = create_output_directory(output)
    snapshot = output / "source_snapshot"
    snapshot.mkdir()
    for name in SOURCES:
        (snapshot / name).write_bytes((Path(__file__).parent / name).read_bytes())
    protocol = {"schema": "ics_v3_phase4_network_workloads_protocol_v1", "scenario_names": list(names),
        "rounds": rounds, "controller_pair": ["reactive_baseline", "same_routing_plus_published_predictive"],
        "execution_mode": "whole_route", "budget": asdict(budget), "source_sha256": sources,
        "synthetic_scene_count": len(names), "new_independent_source_count": 0,
        "evaluation_status": "development mechanism matrix, not held-out confirmation",
        "topology_sha256": topology["source_sha256"],
        "projected_window": {"start_seconds": 36000, "duration_seconds": 60, "no_bag_thinning": True},
        "limits": ["No topology editing to create benefits.", "No supplier module or Nanning operating-day evidence.",
                   "Unreachable, unfinished, failed and budget-exhausted runs remain in all denominators.",
                   "A failed bounded search never certifies infeasibility.",
                   "Wall safeguards can vary with shared-machine load; work limits are reproducible."]}
    write_new_json(output / "protocol.json", protocol)
    write_new_json(output / "topology_audit.json", topology)
    write_new_json(output / "projected_task_audit.json", projected_audit)
    all_runs, construction_failures, skipped, manifests = [], [], [], []
    started = time.perf_counter()
    requests = list(names) + (["projected_direct_36000_36060"] if projected_rows else [])
    for name in requests:
        if time.perf_counter() - started >= budget.total_wall_seconds:
            skipped.append({"scene": name, "status": "not_executed_total_wall_budget"})
            continue
        try:
            scene = (projected_window(projected_rows, network, topology) if name.startswith("projected_") else
                     make_workload(name, network, topology, rounds=rounds))
        except Exception as error:
            construction_failures.append({"scene": name, "type": type(error).__name__, "message": str(error),
                                           "traceback": traceback.format_exc()})
            continue
        manifest = {"name": scene.name, "provenance": scene.provenance, "horizon": scene.horizon,
                    "all_scheduled_bag_denominator": len(scene.initial.bags) + len(scene.future_bags),
                    "forecasts": [asdict(f) for f in scene.forecasts],
                    "evaluation_only_future_bags": [asdict(b) for b in scene.future_bags]}
        manifests.append(manifest)
        write_new_json(output / f"{name}__workload.json", manifest)
        for predictive in ((False,) if name.startswith("projected_") else (False, True)):
            if time.perf_counter() - started >= budget.total_wall_seconds:
                skipped.append({"scene": name, "predictive": predictive, "status": "not_executed_total_wall_budget",
                                "all_scheduled_bag_denominator": manifest["all_scheduled_bag_denominator"]})
                continue
            case = run_case(scene, predictive=predictive, budget=budget,
                            per_search_work=1 if name == "budget_probe" else None)
            write_new_json(output / f"{name}__predictive_{predictive}.json", case)
            all_runs.append(case)
    paired = []
    for name in names:
        matches = {r["metrics"]["predictive"]: r for r in all_runs if r["metrics"]["scene"] == name}
        if set(matches) == {False, True}:
            before, after = matches[False]["metrics"], matches[True]["metrics"]
            cost_pair = before["total_cost"] is not None and after["total_cost"] is not None
            paired.append({"scene": name, "reactive_status": before["status"], "predictive_status": after["status"],
                "reactive_completed": before["completed"], "predictive_completed": after["completed"],
                "scheduled_each": before["all_scheduled_bag_denominator"],
                "reactive_cost": before["total_cost"], "predictive_cost": after["total_cost"],
                "predictive_minus_reactive": after["total_cost"] - before["total_cost"] if cost_pair else None,
                "accepted_predispatches": after["slow_transfers_before_a_future_origin_demand"]})
    summary = {"schema": "ics_v3_phase4_network_workloads_summary_v1", "source_sha256": sources,
        "source_changed_during_run": sources != {name: file_sha(Path(__file__).parent / name) for name in SOURCES},
        "planned_synthetic_runs": len(names) * 2, "planned_projected_runs": int(bool(projected_rows)),
        "executed_runs": len(all_runs), "status_counts": dict(Counter(r["metrics"]["status"] for r in all_runs)),
        "construction_failures": construction_failures, "not_executed": skipped,
        "run_metrics": [r["metrics"] for r in all_runs], "paired_comparisons": paired,
        "scheduled_bag_denominator_across_executed_runs": sum(r["metrics"]["all_scheduled_bag_denominator"] for r in all_runs),
        "completed_across_executed_runs": sum(r["metrics"]["completed"] for r in all_runs),
        "all_projected_original_bag_denominator": len(projected_rows) if projected_rows else None,
        "static_od_denominator": topology["all_loader_unloader_od_count"], "static_od_classes": topology["od_class_counts"],
        "total_search_work": sum(r["metrics"]["search_work"] for r in all_runs),
        "total_search_calls": sum(r["metrics"]["search_calls"] for r in all_runs),
        "wall_seconds": time.perf_counter() - started, "new_independent_source_count": 0,
        "acceptance_claim": False, "unsupported_lifecycle_retained_in_source_denominator": True}
    write_new_json(output / "summary.json", summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--scenes", nargs="+", choices=SCENE_NAMES, default=SCENE_NAMES)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--max-search-calls", type=int, default=300)
    parser.add_argument("--max-search-work", type=int, default=300000)
    parser.add_argument("--per-search-work", type=int, default=3000)
    parser.add_argument("--max-wall-seconds", type=float, default=15.)
    parser.add_argument("--total-wall-seconds", type=float, default=180.)
    parser.add_argument("--projected-raw", type=Path)
    parser.add_argument("--projected-canonical", type=Path)
    parser.add_argument("--projected-manifest", type=Path)
    args = parser.parse_args(argv)
    paths = (args.projected_raw, args.projected_canonical, args.projected_manifest)
    if any(paths) and not all(paths):
        parser.error("supply all three projected raw/canonical/manifest paths")
    summary = run(args.output, profile=args.profile, names=tuple(args.scenes), rounds=args.rounds,
        budget=DiagnosticBudget(args.max_search_calls, args.max_search_work, args.per_search_work,
                                args.max_wall_seconds, args.total_wall_seconds),
        projected_paths=paths if all(paths) else None)
    print(json.dumps({k: summary[k] for k in ("executed_runs", "status_counts", "static_od_classes",
                     "all_projected_original_bag_denominator", "wall_seconds")}, ensure_ascii=False))
    return int(bool(summary["construction_failures"] or summary["not_executed"] or
                    summary["status_counts"].get("execution_failure") or summary["source_changed_during_run"]))


if __name__ == "__main__":
    raise SystemExit(main())
