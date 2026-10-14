"""Executable witnesses for three interfaces that aggregate stock cannot cover."""
from dataclasses import asdict, replace

from .evaluation import AnalyticDeltaEvaluator, ForecastDemand, ReleaseChange
from .model import Bag, Edge, Network, Node, Snapshot, Tray
from .runtime import CandidateGenerator, ExecutionValidator, simulate
from .scenarios import pilot_scenes


def run_counterexamples() -> list[dict]:
    scene = pilot_scenes()[13]  # No initial B stock, four-tick fixed module hold.
    baseline = CandidateGenerator(horizon=48).generate(scene.state, scene.target_bag_id, scene.target_tray_id, k=1)[0]
    at_unload = simulate(scene.state, baseline, (), baseline.unload_complete)
    tray = at_unload.final_trays[scene.target_tray_id]
    assert scene.target_bag_id in at_unload.completed
    assert tray.mode == "holding" and tray.available_at > at_unload.final_snapshot.now
    change = ReleaseChange("B", baseline.unload_complete, baseline.usable_at)
    release = {
        "name": "unloaded_does_not_mean_usable",
        "unload_complete": baseline.unload_complete, "usable_at": baseline.usable_at,
        "tray_mode_at_unload": tray.mode,
        "premature_supply_error_by_tick": {str(t): change.cumulative_delta(t)
                                          for t in range(baseline.unload_complete, baseline.usable_at + 1)},
        "passed": True,
    }

    scene = pilot_scenes()[12]
    candidate = CandidateGenerator(horizon=48).generate(scene.state, scene.target_bag_id, scene.target_tray_id, k=1)[0]
    early, late = scene.state.clone(), scene.state.clone()
    flight = early.old_in_transit[0]
    early.old_in_transit = (replace(flight, depart=-24, arrive=6),)
    late.old_in_transit = (replace(flight, depart=-12, arrive=18),)
    evaluator = AnalyticDeltaEvaluator(48, (ForecastDemand("B", 10, 2),))
    demand = (Bag("bag:new:1", "B", "A", 10, 22), Bag("bag:new:2", "B", "A", 10, 22))
    early_result, late_result = (simulate(state, candidate, demand, 48) for state in (early, late))
    assert early.trays == late.trays
    assert early_result.cost_components["tray_wait"] < late_result.cost_components["tray_wait"]
    transit = {
        "name": "same_inventory_different_irrevocable_transit",
        "same_initial_tray_records": early.trays == late.trays,
        "arrival_ticks": [6, 18],
        "analytic_cost": [evaluator.absolute(state, candidate) for state in (early, late)],
        "rollout_tray_wait": [result.cost_components["tray_wait"] for result in (early_result, late_result)],
        "rollout_total_cost": [result.total_cost for result in (early_result, late_result)],
        "passed": True,
    }

    network = Network({n: Node(n, n, f"control:{n}") for n in ("A", "B")},
                      {"shared": Edge("shared", "A", "B", 2)})
    bags = {f"bag:{i}": Bag(f"bag:{i}", "A", "B", 0, 20) for i in (1, 2)}
    state = Snapshot(0, network, {f"tray:{i}": Tray(f"tray:{i}", "A", "loaded", f"bag:{i}")
                                 for i in (1, 2)}, bags)
    generator, validator = CandidateGenerator(), ExecutionValidator()
    first = generator.generate(state, "bag:1", "tray:1", 1)[0]
    second = generator.generate(state, "bag:2", "tray:2", 1)[0]
    independently_legal = validator.validate(state, first).accepted and validator.validate(state, second).accepted
    first_commit = validator.commit(state, first)
    stale_commit = validator.commit(state, second)
    refreshed_commit = validator.commit(state, replace(second, dependency_version=state.version))
    assert independently_legal and first_commit.accepted and not stale_commit.accepted and not refreshed_commit.accepted
    shared = {
        "name": "two_controllers_cannot_consume_the_same_capacity",
        "independently_legal_before_commit": independently_legal,
        "first_commit": asdict(first_commit), "stale_commit": asdict(stale_commit),
        "refreshed_but_conflicting_commit": asdict(refreshed_commit),
        "owner_model": "single_threaded_serialized_owner_not_distributed_transaction",
        "passed": True,
    }
    return [release, transit, shared]
