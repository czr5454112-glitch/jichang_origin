"""W1 routing diagnostics: old/dynamic regions, strong full graph, tick oracle.

Small fixtures permit full finite-horizon timed enumeration, including one
no-wait cycle whose repeated traversal is needed to reach a release window.
Every occupied edge in the bypass probes comes from authorized physical empty
tray plans. This is candidate-quality diagnostics, not airport acceptance.
"""
from dataclasses import asdict, dataclass, replace
import argparse
import hashlib
import json
from pathlib import Path
from statistics import mean
from time import perf_counter

from .model import Bag, Edge, FixedLocalModule, InFlight, Leg, Network, Node, RouteCandidate, Snapshot, Tray
from .routing import RegionalCandidateGenerator, clear_static_cache
from .routing_reference import FullGraphReferenceGenerator
from .runtime import ExecutionValidator, assert_invariants

ROOT = Path(__file__).resolve().parents[3]


@dataclass
class RoutingCase:
    name: str
    state: Snapshot
    horizon: int


def internal_bypass_case(block_count=5, *, horizon=4, partitions=False):
    nodes = {node: Node(node, "zone", "outer" if partitions and node == "G" else "local", capacity=10)
             for node in ("S", "U", "V", "G")}
    edges = {edge.edge_id: edge for edge in (Edge("S-U", "S", "U", 1), Edge("U-G", "U", "G", 1),
                                            Edge("S-V", "S", "V", 2), Edge("V-G", "V", "G", 2))}
    bag = Bag("bag", "S", "G", 0, 30)
    trays = {"target": Tray("target", "S", "loaded", "bag")}
    trays.update({f"block:{i}": Tray(f"block:{i}", "S") for i in range(block_count)})
    state = Snapshot(0, Network(nodes, edges), trays, {"bag": bag}, module=FixedLocalModule(unload_ticks=0))
    validator = ExecutionValidator()
    for i in range(block_count):
        candidate = RouteCandidate(f"block-plan:{i}", None, f"block:{i}", (Leg("S-U", i, i + 1),),
                                   i + 1, i + 1, state.version, f"block-plan:{i}", True, "U")
        outcome = validator.commit(state, candidate)
        if not outcome.accepted:
            raise RuntimeError(f"Fixture reservation was not authorized: {outcome.reason}")
    assert_invariants(state)
    return RoutingCase("internal_bypass_missing" if block_count == 5 and horizon == 4 and not partitions
                       else f"bypass_b{block_count}_h{horizon}_p{int(partitions)}", state, horizon)


def no_wait_case():
    nodes = {"S": Node("S", "z", "r0", capacity=4),
             "N": Node("N", "z", "r1", capacity=4, can_wait=False),
             "G": Node("G", "z", "r2", capacity=4)}
    edges = {"S-N": Edge("S-N", "S", "N", 1), "N-G": Edge("N-G", "N", "G", 3)}
    bag = Bag("bag", "S", "G", 0, 20)
    state = Snapshot(0, Network(nodes, edges), {"target": Tray("target", "S", "loaded", "bag"),
                                               "block": Tray("block", "N")}, {"bag": bag},
                     module=FixedLocalModule(unload_ticks=0))
    plan = RouteCandidate("authorized-block", None, "block", (Leg("N-G", 0, 3),), 3, 3, 0,
                          "authorized-block", True, "G")
    assert ExecutionValidator().commit(state, plan).accepted
    assert_invariants(state)
    return RoutingCase("no_wait_across_partitions", state, 7)


def no_wait_cycle_case():
    nodes = {name: Node(name, "z", "r", capacity=4, can_wait=name == "G") for name in ("S", "A", "G")}
    edges = {edge.edge_id: edge for edge in (Edge("S-A", "S", "A", 1), Edge("A-S", "A", "S", 1),
                                            Edge("S-G", "S", "G", 3))}
    state = Snapshot(0, Network(nodes, edges), {"target": Tray("target", "S", "loaded", "bag"),
                                               "old": Tray("old", None, "in_transit")},
                     {"bag": Bag("bag", "S", "G", 0, 20)},
                     old_in_transit=(InFlight("old", "S-G", 0, 3),),
                     module=FixedLocalModule(unload_ticks=0))
    assert_invariants(state)
    return RoutingCase("cycle_needed_at_no_wait_source", state, 7)


def routing_cases():
    cases = [internal_bypass_case()]
    cases.extend(internal_bypass_case(blocks, horizon=horizon, partitions=partitioned)
                 for blocks, horizon, partitioned in ((0, 6, False), (2, 6, False), (5, 7, False),
                                                       (5, 4, True), (7, 3, False)))
    cases.append(no_wait_case())
    cases.append(no_wait_cycle_case())
    closed = internal_bypass_case(0, horizon=5)
    closed.name = "zero_capacity_short_edge_bypass"
    closed.state.network.edges["S-U"] = replace(closed.state.network.edges["S-U"], capacity=0)
    cases.append(closed)
    unreachable = internal_bypass_case(0, horizon=5)
    unreachable.name = "static_unreachable"
    unreachable.state.network.edges["S-U"] = replace(unreachable.state.network.edges["S-U"], capacity=0)
    unreachable.state.network.edges["S-V"] = replace(unreachable.state.network.edges["S-V"], capacity=0)
    cases.append(unreachable)
    reception = internal_bypass_case(0, horizon=7)
    reception.name = "destination_reception_window"
    reception.state.module = FixedLocalModule(unload_ticks=0, hold_by_node={"G": 2}, reception_capacity=1)
    reception.state.trays["holding"] = Tray("holding", "G", "holding", available_at=5)
    cases.append(reception)
    full = internal_bypass_case(0, horizon=6)
    full.name = "destination_permanent_occupancy"
    full.state.network.nodes["G"] = replace(full.state.network.nodes["G"], capacity=1)
    full.state.trays["resident"] = Tray("resident", "G")
    cases.append(full)
    return tuple(cases)


def _cost(candidate, now):
    travel = sum(leg.arrive - leg.depart for leg in candidate.legs)
    arrival = candidate.legs[-1].arrive if candidate.legs else now
    return travel + 2 * (arrival - now - travel)


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(output: Path, *, repeats=3, expansion_limit=5000, deadline_ms=80., prior_output: Path | None = None):
    if type(repeats) is not int or repeats < 1:
        raise ValueError("repeats must be a positive integer")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use a new output directory; historical evidence is not overwritten")
    output.mkdir(parents=True, exist_ok=True)
    files = ("routing.py", "routing_reference.py", "run_phase4_routing.py", "model.py", "runtime.py")
    before = {name: _hash(Path(__file__).parent / name) for name in files}
    cases = routing_cases()
    rows, oracles = [], []
    for case in cases:
        oracle = FullGraphReferenceGenerator(horizon=case.horizon, expansion_limit=20000,
                                             deadline_ms=None, integer_ticks=True)
        clear_static_cache()
        exact = oracle.generate(case.state, "bag", "target", 256)
        enumerated = (oracle.last_diagnostics.get("finite_horizon_exhausted", False)
                      and not oracle.last_diagnostics.get("state_label_truncations", 0))
        feasibility_certified = bool(exact) or oracle.last_diagnostics.get("finite_horizon_exhausted", False) or oracle.last_search_status == "static_unreachable"
        oracle_feasible = bool(exact) if feasibility_certified else None
        earliest = min((c.legs[-1].arrive if c.legs else case.state.now for c in exact), default=None)
        best_cost = min((_cost(c, case.state.now) for c in exact), default=None)
        exact_paths = {tuple(leg.edge_id for leg in c.legs) for c in exact}
        oracles.append({"case": case.name, "feasible": oracle_feasible, "feasibility_certified": feasibility_certified,
                        "earliest_arrival": earliest,
                        "minimum_diagnostic_cost": best_cost, "all_timed_candidates_enumerated": enumerated,
                        "timed_candidate_count": len(exact), "physical_path_count": len(exact_paths),
                        "status": oracle.last_search_status, "diagnostics": oracle.last_diagnostics})
        specs = (("old_single_witness", lambda: RegionalCandidateGenerator(horizon=case.horizon,
                    expansion_limit=expansion_limit, deadline_ms=deadline_ms, dynamic_local=False)),
                 ("dynamic_local", lambda: RegionalCandidateGenerator(horizon=case.horizon,
                    expansion_limit=expansion_limit, deadline_ms=deadline_ms, dynamic_local=True, local_label_limit=3)),
                 ("strong_full_graph_event", lambda: FullGraphReferenceGenerator(horizon=case.horizon,
                    expansion_limit=expansion_limit, deadline_ms=deadline_ms)))
        for repeat in range(repeats):
            order = specs[repeat % 3:] + specs[:repeat % 3]
            for order_index, (name, factory) in enumerate(order):
                clear_static_cache()
                for cache_mode in ("cold", "warm"):
                    generator = factory()
                    state = case.state.clone()
                    begin = perf_counter()
                    candidates = generator.generate(state, "bag", "target", 3)
                    generated_ms = (perf_counter() - begin) * 1000
                    begin = perf_counter()
                    validations = [ExecutionValidator().validate(state, c) for c in candidates]
                    validation_ms = (perf_counter() - begin) * 1000
                    begin = perf_counter()
                    next_edge_accepted = sum(ExecutionValidator().validate(state, c, route_mode="next_edge").accepted
                                             for c in candidates)
                    next_edge_validation_ms = (perf_counter() - begin) * 1000
                    begin = perf_counter()
                    commit = ExecutionValidator().commit(state, candidates[0]) if candidates else None
                    commit_ms = (perf_counter() - begin) * 1000
                    arrivals = [c.legs[-1].arrive if c.legs else state.now for c in candidates]
                    paths = {tuple(leg.edge_id for leg in c.legs) for c in candidates}
                    rows.append({"case": case.name, "repeat": repeat, "planner": name, "order_index": order_index,
                                 "cache": cache_mode, "candidate_count": len(candidates), "status": generator.last_search_status,
                                 "all_returned_valid": all(v.accepted for v in validations),
                                 "route_mode": "whole_route", "next_edge_authorized_candidates": next_edge_accepted,
                                 "next_edge_validation_ms_outside_local_total": next_edge_validation_ms,
                                 "commit_accepted": commit.accepted if commit else None,
                                 "oracle_feasible": oracle_feasible, "oracle_feasibility_certified": feasibility_certified,
                                 "oracle_complete_enumeration": enumerated,
                                 "oracle_earliest_arrival": earliest, "best_candidate_arrival": min(arrivals, default=None),
                                 "earliest_arrival_gap": min(arrivals) - earliest if candidates and earliest is not None else None,
                                 "candidate_set_diagnostic_cost_gap": min(_cost(c, state.now) for c in candidates) - best_cost
                                     if candidates and best_cost is not None and enumerated else None,
                                 "physical_path_coverage": len(paths & exact_paths) / len(exact_paths) if exact_paths and enumerated else None,
                                 "generation_ms": generated_ms, "validation_ms": validation_ms, "commit_ms": commit_ms,
                                 "local_total_ms": generated_ms + validation_ms + commit_ms,
                                 "expansions": generator.last_expansions, "diagnostics": generator.last_diagnostics,
                                 "candidates": [asdict(c) for c in candidates]})
    summary = {"schema": "ics_v3_phase4_dynamic_routing_diagnostics_v1", "case_count": len(cases),
               "route_mode": "whole_route",
               "oracle_domain": "finite integer departure/arrival ticks within each horizon, waiting and cycles allowed, whole_route authorization only",
               "request_count": len(rows), "repeats": repeats, "requested_k": 3,
               "expansion_limit": expansion_limit, "deadline_ms": deadline_ms, "source_sha256": before,
               "source_changed_during_run": before != {name: _hash(Path(__file__).parent / name) for name in files},
               "diagnostic_cost": "travel_ticks + 2*waiting_ticks; declared small-graph quality measure, not business benefit",
               "by_planner_cache": {},
               "limitations": ["All graphs are small declared proxy fixtures; no new airport or distributed-control claim.",
                               "Dynamic local label cap can omit paths/windows; event mode is not labelled complete.",
                               "Local output cap is unchanged; at most 4*cap eligible labels per anchor are probed under the shared work/time budget and shortlisted by physical-path/time-window diversity.",
                               "The integer earliest certificate is for whole_route, not next_edge; next_edge authorization counts are observational and outside reported local timing.",
                               "Remote no-wait-chain calendars remain visible; private regional observations are not implemented here.",
                               "Deadline is checked cooperatively; local time includes cold preprocessing and failed queries.",
                               "Physical-path coverage is reported only against fully enumerated finite-horizon integer fixtures."]}
    for name in ("old_single_witness", "dynamic_local", "strong_full_graph_event"):
        for cache in ("cold", "warm"):
            selected = [r for r in rows if r["planner"] == name and r["cache"] == cache]
            feasible = [r for r in selected if r["oracle_feasible"]]
            summary["by_planner_cache"][f"{name}:{cache}"] = {
                "requests": len(selected), "oracle_feasible_requests": len(feasible),
                "oracle_unknown_requests": sum(r["oracle_feasible"] is None for r in selected),
                "covered_feasible_requests": sum(r["candidate_count"] > 0 for r in feasible),
                "returned_invalid_requests": sum(not r["all_returned_valid"] for r in selected),
                "failed_commit_requests": sum(r["commit_accepted"] is False for r in selected),
                "returned_candidate_count": sum(r["candidate_count"] for r in selected),
                "next_edge_authorized_candidate_count": sum(r["next_edge_authorized_candidates"] for r in selected),
                "earliest_arrival_matches": sum(r["earliest_arrival_gap"] == 0 for r in feasible),
                "over_declared_deadline": sum(r["local_total_ms"] > deadline_ms for r in selected) if deadline_ms is not None else None,
                "mean_local_ms_all_requests": mean(r["local_total_ms"] for r in selected),
                "max_local_ms_all_requests": max(r["local_total_ms"] for r in selected)}
    for filename, value in (("summary.json", summary), ("oracle.json", oracles),
                            ("cases.json", [{"name": c.name, "horizon": c.horizon, "initial": asdict(c.state)} for c in cases])):
        (output / filename).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (output / "requests.jsonl").write_text("".join(json.dumps(r, allow_nan=False) + "\n" for r in rows), encoding="utf-8")
    archive = output / "source_snapshot"
    archive.mkdir()
    for name in files:
        (archive / name).write_bytes((Path(__file__).parent / name).read_bytes())
    if prior_output is not None:
        prior_summary_path = prior_output / "summary.json"
        prior_summary = json.loads(prior_summary_path.read_text(encoding="utf-8"))
        prior_rows = [json.loads(line) for line in (prior_output / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
        selection = lambda items: [row for row in items if row["case"] == "destination_reception_window"
                                  and row["repeat"] == 0 and row["cache"] == "cold"]
        record = {"prior_output": str(prior_output), "prior_summary_sha256": _hash(prior_summary_path),
                  "prior_source_sha256": prior_summary["source_sha256"], "historical_files_modified": False,
                  "reproduced_before_fix": ["terminal-invalid arrivals consumed local cap before execution validation",
                                            "several time windows on one physical path displaced another path at fixed cap"],
                  "mechanism_change": "Only terminal-valid labels enter the bounded probe pool; fixed-size output prioritizes distinct physical edge paths, then departure/arrival windows.",
                  "not_claimed": "No complete candidate-domain or general optimality proof; same-state caps and bounded probing can still omit routes/windows.",
                  "prior_reception_rows": selection(prior_rows), "repaired_reception_rows": selection(rows)}
        (output / "repair_record.json").write_text(json.dumps(record, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    if summary["source_changed_during_run"]:
        raise RuntimeError("Source changed during diagnostics; retain as diagnostic only")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--prior-output", type=Path)
    args = parser.parse_args()
    run(args.output, repeats=args.repeats, prior_output=args.prior_output)
