"""No-intervention dispatcher equivalence on three fixed original-map workloads."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter, process_time
import traceback

from .audit_nanning import DEFAULT_PROFILE
from .experiment_protocol import create_output_directory, write_new_json
from .phase4_control import ControlSpec, PeriodicSlowController, control_contract
from .phase4_network_workloads import file_sha, load_network, make_workload
from .prebalance import PredictivePrebalancer
from .role_coverage import CursorSimulation
from .routing import clear_static_cache
from .run_network_opportunities import OpportunityObserver, OpportunitySelector
from .run_role_coverage import SOURCES as ROLE_SOURCES
from .run_workload_diagnostics import DiagnosticBudget, RecordedFactory, SOURCES as NETWORK_SOURCES, WorkBudgetExceeded
from .runtime import Simulation, assert_invariants


SCENES = ("cross_cycle", "counterflow", "near_full")
BUDGET = DiagnosticBudget(max_search_calls=300, max_search_work=300000, per_search_work=3000,
                          max_wall_seconds=300., total_wall_seconds=1800.)
SOURCES = tuple(dict.fromkeys(("run_cursor_original_map.py", "run_network_opportunities.py", *ROLE_SOURCES, *NETWORK_SOURCES)))


def semantic(value):
    if isinstance(value, dict):
        return {key: semantic(item) for key, item in value.items()
                if not key.endswith("_ms") and key not in {"wall_seconds", "cpu_seconds", "process_cpu_seconds"}}
    if isinstance(value, (tuple, list)):
        return [semantic(v) for v in value]
    return value


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def normalized_opportunities(case):
    """Keep generated and owner-authorized counts at their distinct stages.

    Runtime attempts each loaded tray at most once per tick. Reject ambiguous
    diagnostic identities rather than assigning an observed selector call to a
    different attempt. Missing selectors mean zero authorized options.
    """
    loaded = [row for row in case["searches"] if row["bag_id"] is not None]
    opportunities = case["opportunities"]
    if len(loaded) != len(opportunities):
        raise ValueError("loaded attempt and opportunity denominators differ")
    def identity(row):
        return row["time"], row["bag_id"], row["tray_id"]
    calls = {identity(row): row for row in case["route_history"]}
    if len(calls) != len(case["route_history"]) or len({identity(row) for row in loaded}) != len(loaded):
        raise ValueError("ambiguous repeated loaded attempt identity")
    normalized = []
    for search, opportunity in zip(loaded, opportunities):
        key = identity(search)
        if key != identity(opportunity) or search["origin"] != opportunity["node"]:
            raise ValueError("attempt identity or actual node differs")
        call = calls.pop(key, None)
        authorized = 0 if call is None else call["candidate_count"]
        if not 0 <= authorized <= search["candidate_count"]:
            raise ValueError("authorized candidates exceed generated candidates")
        if call is not None and call["node"] != search["origin"]:
            raise ValueError("selector observed another source node")
        if case["metrics"]["engine"] == "cursor" and opportunity["candidate_count"] != authorized:
            raise ValueError("actual cursor hook disagrees with authorized selector count")
        row = {key: opportunity[key] for key in ("time", "node", "role", "bag_id", "tray_id", "protected")}
        row.update(candidate_count=authorized, authorized_candidate_count=authorized,
                   generated_candidate_count=search["candidate_count"])
        normalized.append(row)
    if calls:
        raise ValueError("selector call missing from loaded generation denominator")
    return normalized


def compare_cases(left, right):
    fields = ("result", "route_history", "slow_history", "slow_trigger_times", "slow_next_trigger_at", "searches", "observer_boundaries")
    comparisons = {field: semantic(left[field]) == semantic(right[field]) for field in fields}
    comparisons["attempt_role_node_denominator"] = normalized_opportunities(left) == normalized_opportunities(right)
    return comparisons


def run_case(scene, kind, budget=BUDGET):
    clear_static_cache()
    spec = ControlSpec(routing="timed", predictive=True, slow_period=2, planning_horizon=180,
                      route_mode="next_edge", candidate_count=4, expansion_limit=budget.per_search_work,
                      static_path_limit=8)
    factory = RecordedFactory(spec, budget)
    contract = control_contract(spec, scene.forecasts, start_tick=scene.initial.now)
    slow = PeriodicSlowController(PredictivePrebalancer((), planning_horizon=180,
        planning_budget_ms=None, generator_factory=factory), period=2, first_trigger_at=scene.initial.now,
        contract=contract, forecast_publications=scene.forecasts)
    base = Simulation(scene.initial, scene.future_bags, route_mode="next_edge", generator_factory=factory,
        route_selector=OpportunitySelector(spec, scene.forecasts), slow_controller=slow,
        observer=OpportunityObserver(), search_horizon=180, candidate_count=4)
    engine = base if kind == "original" else CursorSimulation.from_base_checkpoint(base.checkpoint(), contract=contract)
    # Restore deliberately deep-copies policy/generator state. Each run gets one
    # fresh accounting owner shared by all its loaded/reactive/slow searches.
    # No accounting object is shared between the compared physical episodes.
    engine.generator_factory = factory
    engine._generator.owner = factory
    engine.slow_controller.controller.generator_factory = factory
    opportunities = []
    if kind == "cursor":
        def record(current, tray, options):
            bag = current.state.bags[tray.bag_id]
            role = ("arrival_at_destination" if tray.node == bag.destination else
                    "origin" if tray.node == bag.origin else "continuation")
            opportunities.append({"time": current.state.now, "node": tray.node, "role": role,
                                  "bag_id": bag.bag_id, "tray_id": tray.tray_id,
                                  "candidate_count": len(options), "protected": bag.protected,
                                  "cursor_stage": current._cursor.stage_index,
                                  "cursor_route_index": current._cursor.route_index})
        engine._decision_callback = record
    started, cpu = perf_counter(), process_time()
    failure, budget_stop = None, None
    try:
        while engine.state.now < scene.horizon:
            factory.check()
            engine.advance(engine.state.now + 1)
        assert_invariants(engine.state)
    except WorkBudgetExceeded as exc:
        budget_stop = str(exc)
    except Exception as exc:
        failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    elapsed, cpu_elapsed = perf_counter() - started, process_time() - cpu
    result = engine.result() if failure is None else None
    all_bags = {**scene.initial.bags, **{b.bag_id: b for b in scene.future_bags}}
    searches = [r for r in factory.rows if r["bag_id"] is not None]
    if kind == "original":
        for row in searches:
            bag = all_bags[row["bag_id"]]
            role = ("arrival_at_destination" if row["origin"] == bag.destination else
                    "origin" if row["origin"] == bag.origin else "continuation")
            opportunities.append({"time": row["time"], "node": row["origin"], "role": role,
                                  "bag_id": bag.bag_id, "tray_id": row["tray_id"],
                                  "candidate_count": row["candidate_count"], "protected": bag.protected})
    raw_opportunities = opportunities
    if failure is None:
        opportunities = normalized_opportunities({"metrics": {"engine": kind}, "searches": factory.rows,
            "route_history": engine.route_selector.history, "opportunities": raw_opportunities})
    candidate_histogram = Counter(r["candidate_count"] for r in opportunities)
    status = "execution_failure" if failure else "budget_exhausted" if budget_stop else "reached_horizon"
    metrics = {"scene": scene.name, "engine": kind, "status": status, "stopped_at": engine.state.now,
               "horizon": scene.horizon, "scheduled_bags": len(all_bags), "observed_bags": len(engine.state.bags),
               "completed_bags": len(set(all_bags) & set(engine.state.completed)), "search_calls": len(factory.rows),
               "search_work": factory.work, "budget_stop": budget_stop, "actual_selector_calls": len(engine.route_selector.history),
               "loaded_attempt_count": len(searches), "loaded_attempts_without_selector": len(searches) - len(engine.route_selector.history),
               "candidate_count_histogram": dict(candidate_histogram), "actual_nodes": dict(Counter(r["node"] for r in opportunities)),
               "generated_candidate_count_histogram": dict(Counter(r["candidate_count"] for r in searches)),
               "actual_roles": dict(Counter(r["role"] for r in opportunities)),
               "slow_trigger_count": len(engine.slow_controller.trigger_times),
               "wall_seconds": elapsed, "cpu_seconds": cpu_elapsed}
    return {"metrics": metrics, "result": None if result is None else asdict(result),
            "control_contract": contract, "searches": factory.rows, "opportunities": opportunities,
            "raw_opportunities": raw_opportunities,
            "route_history": engine.route_selector.history, "slow_history": engine.slow_controller.history,
            "slow_trigger_times": engine.slow_controller.trigger_times, "slow_next_trigger_at": engine.slow_controller.next_trigger_at,
            "observer_boundaries": engine.observer.boundaries, "failure": failure}


def run(output, *, profile=DEFAULT_PROFILE, names=SCENES, budget=BUDGET):
    if not names or len(set(names)) != len(names) or not set(names) <= set(SCENES):
        raise ValueError("choose a distinct nonempty subset of the three declared workloads")
    output = create_output_directory(output)
    source = Path(__file__).parent
    hashes = {name: file_sha(source / name) for name in SOURCES}
    (output / "source_snapshot").mkdir()
    for name in SOURCES:
        (output / "source_snapshot" / name).write_bytes((source / name).read_bytes())
    write_new_json(output / "protocol.json", {"schema": "ics_v3_cursor_original_map_equivalence_v1",
        "all_planned_scenes": SCENES, "selected_scenes": names, "source_sha256": hashes, "budget": asdict(budget),
        "purpose": "No-intervention equivalence of original and cursor dispatcher, not a policy-performance comparison or new labels",
        "spec": {"routing": "timed", "planning_horizon": 180, "slow_period": 2, "candidate_count": 4, "static_path_limit": 8},
        "same_budget_semantics": "Each engine gets a fresh RecordedFactory; its loaded and slow generator references are explicitly rebound to the same per-run counter after checkpoint copying.",
        "work_primary": "300 searches, 300000 total expansions, 3000 per search; no wall cutoff inside a search",
        "wall_safeguard": "300 seconds per engine; 1800 seconds for this bounded validation, not the earlier 20-second opportunity cutoff",
        "comparison": "Complete result including every physical trace event, cost component and final ledger; only wall/CPU timing fields excluded. All route actions, slow actions, slow phase, searches and observations compared separately.",
        "denominators": "All loaded search attempts including zero candidates retained. Generated counts stay separate; common authorized counts come from actual selector calls (or zero when none), verified against the cursor hook. Raw opportunities are retained.",
        "operational_scope": "Original graph with existing synthetic stock/service/permission workload assumptions; no field calibration, no effects/generalization claim"})
    network, topology = load_network(profile)
    write_new_json(output / "topology_audit.json", topology)
    cases, pairs, skipped = [], [], []
    started = perf_counter()
    for name in names:
        scene = make_workload(name, network, topology, rounds=3)
        input_data = {"scene": name, "initial": asdict(scene.initial), "forecasts": [asdict(f) for f in scene.forecasts],
                      "evaluation_only_future": [asdict(b) for b in scene.future_bags], "horizon": scene.horizon,
                      "provenance": scene.provenance}
        input_sha = digest(input_data)
        write_new_json(output / (name + "_input.json"), {**input_data, "input_sha256": input_sha})
        local = {}
        for kind in ("original", "cursor"):
            if perf_counter() - started >= budget.total_wall_seconds:
                skipped.append({"scene": name, "engine": kind, "status": "not_executed_total_wall_safeguard"})
                continue
            case = run_case(scene, kind, budget)
            case["input_sha256"] = input_sha
            write_new_json(output / f"{name}_{kind}.json", case)
            local[kind] = case
            cases.append(case["metrics"])
            print(json.dumps(case["metrics"], ensure_ascii=False), flush=True)
        if len(local) == 2:
            left, right = local["original"], local["cursor"]
            comparisons = compare_cases(left, right)
            pair = {"scene": name, "input_sha256": input_sha, "comparisons": comparisons,
                    "all_equal": all(comparisons.values()),
                    "both_reached_horizon": all(c["metrics"]["status"] == "reached_horizon" for c in local.values()),
                    "same_budget_stop": left["metrics"]["budget_stop"] == right["metrics"]["budget_stop"],
                    "semantic_result_sha256": {kind: digest(semantic(case["result"])) for kind, case in local.items()}}
            pairs.append(pair)
            write_new_json(output / (name + "_comparison.json"), pair)
    summary = {"planned_runs": 6, "executed_runs": len(cases), "not_executed": skipped,
               "unselected_planned_scenes": [name for name in SCENES if name not in names], "run_metrics": cases,
               "paired_comparisons": pairs, "all_pairs_equal": bool(pairs) and all(p["all_equal"] for p in pairs),
               "all_selected_reached_horizon": all(p["both_reached_horizon"] for p in pairs) and not skipped,
               "source_sha256": hashes, "source_changed_during_run": hashes != {name: file_sha(source / name) for name in SOURCES},
               "wall_seconds": perf_counter() - started, "labels_generated": 0, "new_independent_source_count": 0}
    write_new_json(output / "summary.json", summary)
    write_new_json(output / "manifest.json", {str(p.relative_to(output)).replace("\\", "/"): file_sha(p)
                                              for p in sorted(output.rglob("*")) if p.is_file()})
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--scenes", nargs="+", choices=SCENES, default=SCENES)
    args = parser.parse_args()
    result = run(args.output, profile=args.profile, names=tuple(args.scenes))
    print(json.dumps({k: v for k, v in result.items() if k not in {"run_metrics", "source_sha256"}}, indent=2))
    raise SystemExit(int(not result["all_pairs_equal"] or result["source_changed_during_run"]))
