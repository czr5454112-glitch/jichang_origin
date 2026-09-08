"""Read-only structural audit of the user-directed reduced paper-suite scope.

Reads frozen protocol/topology metadata; does not load experiment cell results,
rank methods, edit a production protocol, or invoke a simulator.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SELECTED_SCENARIOS = (1, 2, 9, 14)
SELECTED_SEEDS = (104729, 130363, 155921)
EXPECTED_LINES = {1: [1], 2: [2], 9: [1, 7], 14: [2, 4, 6]}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def closure(edges: set[tuple[int, int]], initial: set[tuple[int, int]]):
    nodes = {node for edge in edges for node in edge}
    incoming = {n: {e for e in edges if e[1] == n} for n in nodes}
    outgoing = {n: {e for e in edges if e[0] == n} for n in nodes}
    disabled = set(initial)
    while True:
        updated = set(disabled)
        for node in nodes:
            # Empty endpoint adjacency is not itself a failure.
            if outgoing[node] and outgoing[node] <= disabled:
                updated.update(incoming[node])
            if incoming[node] and incoming[node] <= disabled:
                updated.update(outgoing[node])
        if updated == disabled:
            return disabled
        disabled = updated


def audit(worktree: Path):
    protocol_path = worktree / "configs/eval/feng_paper_suite_fault_20260907.json"
    protocol = read_json(protocol_path)
    assert list(SELECTED_SEEDS) == protocol["seeds"][:3]
    assert protocol["cell_count"] == 1280
    assert protocol["methods"] == [
        "G31_S4_ADVERTISED_FAULT_REPAIR_V1", "HCA_TIME_LABEL_REPAIR_V3"
    ]
    assert protocol["speeds_mps"] == [2.5]
    assert protocol["load_factors"] == [1.0, 2.0]
    assert protocol["horizon_seconds"] == 98259
    source_path = Path(protocol["source_contract"]["path"])
    nanning_path = Path(protocol["nanning_selection"]["path"])
    assert sha256(source_path) == protocol["source_contract"]["sha256"]
    assert sha256(nanning_path) == protocol["nanning_selection"]["sha256"]
    source = read_json(source_path)
    nanning = read_json(nanning_path)
    assert protocol["nanning_selection"]["algorithm_outcomes_used"] is False
    assert nanning["selection_inputs"]["algorithm_outcomes_consulted"] is False
    map2_lines = {int(k): tuple(v) for k, v in source["map2_fault_id_to_edge"].items()}
    nanning_lines = {int(x["line_id"]): tuple(x["edge"]) for x in nanning["lines"]}
    references = []

    def reference(path: Path, role: str):
        references.append({"role": role, "path": str(path), "sha256": sha256(path)})

    reference(protocol_path, "unchanged_parent_fault_protocol")
    reference(source_path, "paper_map2_line_mapping")
    reference(nanning_path, "prior_outcome_independent_nanning_mapping")
    records = []
    for map_name in ("map2", "nanning"):
        map_spec = protocol["scenario_maps"][map_name]
        profile_path = Path(map_spec["map_profile_path"])
        profile = read_json(profile_path)
        edges = {(e["start"], e["end"]) for e in profile["edges"]}
        assert len(edges) == map_spec["directed_edge_count"]
        if "map_profile_sha256" in map_spec:
            assert sha256(profile_path) == map_spec["map_profile_sha256"]
        reference(profile_path, f"{map_name}_directed_topology")
        by_index = {s["scenario_index"]: s for s in map_spec["scenarios"]}
        line_mapping = map2_lines if map_name == "map2" else nanning_lines
        for scenario_index in SELECTED_SCENARIOS:
            spec = by_index[scenario_index]
            assert spec["paper_line_ids"] == EXPECTED_LINES[scenario_index]
            initial = {tuple(e) for e in spec["initial_failed_edges"]}
            assert initial == {line_mapping[n] for n in EXPECTED_LINES[scenario_index]}
            assert initial <= edges
            calculated = closure(edges, initial)
            assert calculated == {tuple(e) for e in spec["affected_edges"]}
            assert calculated == {tuple(e) for e in spec["failed_edges"]}
            assert len(calculated) == spec["affected_count"]
            redundant = sorted(e for e in initial if closure(edges, initial - {e}) == calculated)
            records.append({
                "map": map_name, "scenario_index": scenario_index,
                "line_ids": EXPECTED_LINES[scenario_index],
                "initial_failed_edges": sorted(initial),
                "initial_failed_edge_count": len(initial),
                "disabled_edges": sorted(calculated),
                "disabled_edge_count": len(calculated),
                "extra_disabled_edges_from_propagation": len(calculated) - len(initial),
                "redundant_initial_edges_under_common_closure": redundant,
                "recomputed_closure_matches_frozen_protocol": True,
            })
    fault_cells = 2 * 2 * len(SELECTED_SCENARIOS) * len(SELECTED_SEEDS) * 2
    base_cells = 2 * 2 * 3 * 10 * 4
    assert (base_cells, fault_cells, base_cells + fault_cells) == (480, 96, 576)
    base_hours, original_fault_hours = 14.0, 37.0
    reduced_fault_hours = original_fault_hours * fault_cells / protocol["cell_count"]
    return {
        "schema": "czr005.paper_suite.reduced_scope_structural_review.v1",
        "status": "SCOPE_STRUCTURAL_REVIEW_PASS",
        "scope_amendment": "user_directed_prospective_reduction_after_prior_preflight_observation",
        "original_blinded_preregistration_claimed": False,
        "new_simulations_run_by_this_audit": 0,
        "experimental_cell_results_read_by_this_auditor": 0,
        "algorithm_rankings_used_for_selection": False,
        "production_protocol_modified_by_this_auditor": False,
        "existing_results_to_be_preserved": True,
        "fault_scenarios": list(SELECTED_SCENARIOS),
        "fault_seeds": list(SELECTED_SEEDS),
        "seed_selection_rule": "first_three_in_original_fixed_order_no_replacement",
        "maps": ["map2", "nanning"], "load_factors": [1.0, 2.0],
        "fault_speed_mps": 2.5, "fault_methods": protocol["methods"],
        "base_cell_count_unchanged": base_cells,
        "fault_cell_count_reduced": fault_cells,
        "total_cell_count_reduced": base_cells + fault_cells,
        "original_fault_cell_count": protocol["cell_count"],
        "original_total_cell_count": base_cells + protocol["cell_count"],
        "horizon_seconds_unchanged": 98259,
        "scientific_contract": {
            "information": "failures_and_common_propagation_closure_known_before_first_routing",
            "repair_within_horizon": False,
            "population": "all_original_raw_bags_and_canonical_legs_no_reachability_prefilter",
            "timing": "THT_only_when_entire_population_completes_otherwise_null",
            "inference_scope": "selected_four_scenarios_and_three_paired_seeds_only",
            "three_seed_limit": "low_replication_precision_do_not_infer_all_16_failure_patterns",
            "nanning_mapping": "prior_graph_and_workload_based_adaptation_not_original_paper_geometry",
        },
        "structural_checks": records,
        "runtime_estimate": {
            "basis": "parent_supplied_prior_budget_linear_same_concurrency_average_cost_approximation",
            "original_base_hours": base_hours,
            "original_fault_hours_for_1280_cells": original_fault_hours,
            "estimated_reduced_fault_hours": reduced_fault_hours,
            "estimated_total_hours_from_zero": base_hours + reduced_fault_hours,
            "original_total_hours": base_hours + original_fault_hours,
            "estimated_hours_saved": original_fault_hours - reduced_fault_hours,
            "fault_cell_reduction_fraction": 1 - fault_cells / protocol["cell_count"],
            "estimated_total_time_reduction_fraction": 1 - (base_hours + reduced_fault_hours) / (base_hours + original_fault_hours),
            "remaining_eta_claimed": False,
            "limitations": "cost_varies_by_map_method_load_scenario_and_contention_existing_completed_cells_not_subtracted",
        },
        "sources": references,
        "auditor": {"path": str(Path(__file__).resolve()), "sha256": sha256(Path(__file__))},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worktree", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("scope_review.json"))
    args = parser.parse_args()
    payload = audit(args.worktree.resolve())
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "base": 480, "fault": 96,
                      "total": 576, "closure_checks": len(payload["structural_checks"]),
                      "output": str(args.output.resolve())}))


if __name__ == "__main__":
    main()
