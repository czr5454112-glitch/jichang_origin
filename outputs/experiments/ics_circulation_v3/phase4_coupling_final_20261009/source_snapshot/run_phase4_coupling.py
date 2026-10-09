"""W2-start mechanism diagnostics: real predispatch and shared-resource effects.

This is a tiny constructed regression family, not training, a held-out study,
an exact reference, or completion of W2/W3.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import traceback

from .experiment_protocol import create_output_directory, sha256_file, write_new_json
from .phase4_control import ControlSpec, build_engine, digest
from .phase4_coupled_scenarios import coupling_scenes

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = ROOT / "outputs/experiments/ics_circulation_v3/phase4_coupling_20261009"
SOURCES = ("run_phase4_coupling.py", "phase4_control.py", "phase4_coupled_scenarios.py", "experiment_protocol.py",
           "conditional_evaluation.py", "prebalance.py", "learning.py", "evaluation.py", "runtime.py", "model.py", "routing.py", "routing_reference.py")


class ResourceObservations:
    """Physical observations at reachable routing boundaries, not hidden tape."""
    def __init__(self):
        self.rows = []

    def __call__(self, state):
        occupancy = Counter(tray.node for tray in state.trays.values() if tray.node is not None)
        empty_plans = {tray_id: asdict(plan) for tray_id, plan in state.plans.items() if plan.bag_id is None}
        self.rows.append({"time": state.now, "node_occupancy": dict(occupancy),
                          "nodes_at_capacity": [node_id for node_id, node in state.network.nodes.items()
                                                if occupancy[node_id] == node.capacity],
                          "empty_plans": empty_plans, "trays": {key: asdict(tray) for key, tray in state.trays.items()},
                          "visible_bag_ids": sorted(state.bags)})


def source_hashes():
    return {name: sha256_file(Path(__file__).parent / name) for name in SOURCES}


def _run_case(scene, spec):
    observation = ResourceObservations()
    engine = build_engine(scene.initial, scene.forecasts, scene.future_bags, spec, observer=observation)
    result, failure = None, None
    try:
        result = engine.advance(scene.horizon)
    except Exception as error:
        failure = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
    expected = {**scene.initial.bags, **{bag.bag_id: bag for bag in scene.future_bags}}
    tray_loads = {tray_id: ([tray.bag_id] if tray.bag_id else []) for tray_id, tray in scene.initial.trays.items()}
    trace = list(result.trace) if result else list(engine._trace)
    for event in trace:
        if event["event"] == "load":
            tray_loads[event["tray_id"]].append(event["bag_id"])
    slow = engine.slow_controller
    ledger = [{**asdict(bag), "load_time": engine.state.load_times.get(bag_id),
               "completion_time": engine.state.completed.get(bag_id),
               "on_time": bag_id in engine.state.completed and engine.state.completed[bag_id] <= bag.deadline}
              for bag_id, bag in sorted(expected.items())]
    metrics = {"scene": scene.name, "routing": spec.routing, "predictive": spec.predictive,
               "status": "failed" if failure else "completed_run", "all_bag_denominator": len(expected),
               "completed": len(engine.state.completed), "uncompleted": len(expected) - len(engine.state.completed),
               "on_time": sum(item["on_time"] for item in ledger),
               "total_cost": result.total_cost if result else None, "cost_components": result.cost_components if result else None,
               "initial_trays": len(scene.initial.trays), "tray_identity_preserved": set(scene.initial.trays) == set(engine.state.trays),
               "trays_serving_multiple_bags": sum(len(bags) > 1 for bags in tray_loads.values()),
               "per_tray_bag_sequences": tray_loads,
               "physical_nodes_observed_at_capacity": sorted({node for row in observation.rows for node in row["nodes_at_capacity"]}),
               "max_physical_node_occupancy": {node: max((row["node_occupancy"].get(node, 0) for row in observation.rows), default=0)
                                                for node in scene.initial.network.nodes},
               "engine_slow_wrapper_callbacks": int(engine.policy_stats["slow_calls"]),
               "actual_slow_trigger_count": len(slow.trigger_times) if slow else 0,
               "actual_slow_trigger_times": list(slow.trigger_times) if slow else [],
               "accepted_slow_transfers": int(engine.policy_stats["slow_commits"]),
               "invariant_checks": result.invariant_checks if result else engine._checks}
    return {"metrics": metrics, "control_contract": engine.route_selector.contract, "bag_ledger": ledger,
            "route_decisions": engine.route_selector.history, "observed_resources": observation.rows,
            "slow_decisions": slow.history if slow else [], "event_trace": trace,
            "final_snapshot": asdict(engine.state), "failure": failure}


def mechanism_comparison(reactive, predictive):
    def bag(run, identifier):
        return next(row for row in run["bag_ledger"] if row["bag_id"] == identifier)
    def a12(run):
        return [row for row in run["route_decisions"] if row["bag_id"] == "stream:A:12:0"]
    def empty_jb_at12(run):
        return [{"tray_id": tray, **leg} for row in run["observed_resources"] if row["time"] == 12
                for tray, plan in row["empty_plans"].items() for leg in plan["legs"]
                if leg["edge_id"] == "J-B" and leg["depart"] <= 12 < leg["arrive"]]
    actions = [{"trigger_time": row["trigger_time"], **proposal}
               for row in predictive["slow_decisions"] for proposal in row["proposals"]]
    early = [row for row in actions if row["destination_node"] == "B" and row["legs"][0]["depart"] < 10]
    baseline_cost, predicted_cost = reactive["metrics"]["total_cost"], predictive["metrics"]["total_cost"]
    return {"scene": reactive["metrics"]["scene"], "routing": reactive["metrics"]["routing"],
            "reactive_cost": baseline_cost, "predictive_cost": predicted_cost,
            "cost_comparison_available": baseline_cost is not None and predicted_cost is not None,
            "predictive_minus_reactive": None if baseline_cost is None or predicted_cost is None else predicted_cost - baseline_cost,
            "accepted_empty_transfers_before_B10": early,
            "B10_load_times": {"reactive": bag(reactive, "stream:B:10:0")["load_time"],
                               "predictive": bag(predictive, "stream:B:10:0")["load_time"]},
            "A12_route_witnesses": {"reactive": a12(reactive), "predictive": a12(predictive)},
            "empty_shared_JB_occupancy_at12": {"reactive": empty_jb_at12(reactive), "predictive": empty_jb_at12(predictive)},
            "earlier_predispatch_clears_shared_edge": bool(early and empty_jb_at12(reactive) and not empty_jb_at12(predictive)),
            "all_scheduled_bags_complete_in_both": reactive["metrics"]["uncompleted"] == predictive["metrics"]["uncompleted"] == 0}


def run(output=DEFAULT_OUTPUT):
    output = create_output_directory(output)
    before = source_hashes()
    for name in SOURCES:
        destination = output / "source_snapshot" / name
        destination.parent.mkdir(exist_ok=True)
        destination.write_bytes((Path(__file__).parent / name).read_bytes())
    specs = tuple(ControlSpec(routing=routing, predictive=predictive) for routing in ("baseline", "timed", "conditional_timed")
                  for predictive in (False, True))
    write_new_json(output / "protocol.json", {"scope": "W2_START_CONSTRUCTED_MECHANISMS_NOT_HELDOUT_PERFORMANCE_OR_COMPLETE_MPC",
        "specifications": [asdict(spec) for spec in specs], "source_sha256": before,
        "known_development_design_failures": "../phase4_coupling_design_diagnostic_20261009",
        "planned_fixtures": ["scarce", "sufficient", "reversal"], "planned_runs": 18,
        "limitations": ["Five nodes, fixed proxy local module, no airport integration or continuous production trace.",
                        "Labels and deployment can share this builder, but no learned model has been trained or compared here.",
                        "Greedy prebalancing remains firm-first-release, not a multicycle optimizer or exact MPC.",
                        "Optional conditional scoring uses uncertain release hints only in prediction; no export authority is added.",
                        "All generator budgets remain bounded; no real-time or globally feasible scheduling guarantee.",
                        "The sufficient-stock control also declares B capacity3 to make its extra stock compatible with admitted burn-in.",
                        "These mechanism cases were designed with explicit feasibility corrections; they are not fresh independent evidence."]})
    all_runs, comparisons = [], []
    for scene in coupling_scenes():
        write_new_json(output / f"{scene.name}_input.json", {"initial": asdict(scene.initial),
            "forecasts": [asdict(item) for item in scene.forecasts], "future_event_engine_only": [asdict(item) for item in scene.future_bags],
            "horizon": scene.horizon, "provenance": scene.provenance})
        pairs = {}
        for spec in specs:
            row = _run_case(scene, spec)
            write_new_json(output / f"{scene.name}__{spec.routing}__predictive_{spec.predictive}.json", row)
            all_runs.append(row)
            pairs[(spec.routing, spec.predictive)] = row
        for routing in ("baseline", "timed", "conditional_timed"):
            comparisons.append(mechanism_comparison(pairs[(routing, False)], pairs[(routing, True)]))
    checks = {
        "scarce_predispatch_changes_shared_resource_and_reduces_cost": all(row["predictive_minus_reactive"] is not None and row["earlier_predispatch_clears_shared_edge"] and row["predictive_minus_reactive"] < 0 for row in comparisons if row["scene"] == "scarce"),
        "sufficient_stock_has_no_predispatch_or_cost_gain": all(row["predictive_minus_reactive"] is not None and not row["accepted_empty_transfers_before_B10"] and row["predictive_minus_reactive"] == 0 for row in comparisons if row["scene"] == "sufficient"),
        "forecast_reversal_negative_effect_retained": all(row["predictive_minus_reactive"] is not None and row["accepted_empty_transfers_before_B10"] and row["predictive_minus_reactive"] > 0 for row in comparisons if row["scene"] == "reversal"),
        "all_scheduled_bags_complete": all(row["metrics"]["uncompleted"] == 0 for row in all_runs),
        "all_tray_identities_preserved": all(row["metrics"]["tray_identity_preserved"] for row in all_runs)}
    summary = {"scope": "W2_START_MECHANISM_DIAGNOSTIC_NOT_W2_W3_ACCEPTANCE", "run_count": len(all_runs),
               "failed_run_count": sum(row["failure"] is not None for row in all_runs),
               "scheduled_bag_denominator_across_runs": sum(row["metrics"]["all_bag_denominator"] for row in all_runs),
               "completed_across_runs": sum(row["metrics"]["completed"] for row in all_runs),
               "cost_available_comparison_count": sum(row["cost_comparison_available"] for row in comparisons),
               "cost_unavailable_comparisons": [{"scene": row["scene"], "routing": row["routing"]}
                                                 for row in comparisons if not row["cost_comparison_available"]],
               "mechanism_checks": checks, "metrics": [row["metrics"] for row in all_runs],
               "source_sha256": before, "source_changed_during_run": source_hashes() != before,
               "timing_claim": "none; no formal performance comparison", "new_independent_source_count": 0}
    write_new_json(output / "mechanism_comparisons.json", comparisons)
    write_new_json(output / "summary.json", summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    summary = run(args.output)
    print(json.dumps({key: summary[key] for key in ("run_count", "failed_run_count", "scheduled_bag_denominator_across_runs",
                                                  "completed_across_runs", "mechanism_checks", "source_changed_during_run")}, indent=2))
    return 1 if summary["failed_run_count"] or summary["source_changed_during_run"] or not all(summary["mechanism_checks"].values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
