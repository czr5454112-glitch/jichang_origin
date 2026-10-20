"""Hand-written audit fixtures only; no real results, fitting or native calls."""
from copy import deepcopy
import hashlib
from itertools import combinations
import json

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_inventory_spi_effects as effects


def fixture_grid(costs=None):
    default = {"R0_current_stock_v1": 1020., "C00": 1000., "C10": 980., "C01": 990., "C11": 960.}
    rows, comparisons = [], []
    for parent in effects.PARENTS:
        for method in effects.METHODS:
            cost = default[method] if costs is None else costs[(parent, method)]
            rows.append({"name": f"DUMMY_{parent}_{method}", "registered_parent_seed": parent,
                "registered_method": method, "status": "complete", "audit_status": "closed_cost_verified",
                "full_window_cost": {"backlog_integral_bag_seconds": cost, "completed_by_end": 10,
                    "on_time_by_end": 8, "arrived_unfinished_past_deadline": 3, "physical_population": 100},
                "physical": {"global_progress": {"longest_no_edge_progress_seconds": 60.,
                    "longest_no_edge_progress_interval": [7200., 7260.]},
                    "failed_legs": 0, "final_quarantined_trays": 0},
                "missing_evidence": [], "errors": []})
        for a, b in combinations(effects.METHODS, 2):
            a_cost = default[a] if costs is None else costs[(parent, a)]
            b_cost = default[b] if costs is None else costs[(parent, b)]
            categories = {key: 0 for key in effects.DIRECTION_KEYS}
            categories["exact_equal"] = 10
            categories["both_arrived_unfinished"] = 80
            categories["both_not_yet_arrived"] = 10
            comparisons.append({"parent_seed": parent, "reference_method": a, "candidate_method": b,
                "reference": f"DUMMY_{parent}_{a}", "candidate": f"DUMMY_{parent}_{b}",
                "status": "closed_same_parent_comparison", "advantage_bag_seconds": a_cost-b_cost,
                "relative_J_gain": (a_cost-b_cost)/a_cost if a_cost else None,
                "completed_delta": 0, "on_time_delta": 0, "overdue_unfinished_delta": 0,
                "completion_direction": {"categories": categories, "population": 100,
                    "known_direction_harm": 0, "known_direction_improvement": 0,
                    "completion_times_imputed": False, "unknown_incomplete_legacy": 90,
                    "maximum_censored_delay_lower_bound_seconds": 0.,
                    "sum_censored_delay_lower_bound_seconds": 0.}})
    return {"schema": effects.AUDIT_SCHEMA, "registered_parent_count": 8, "registered_method_count": 5,
        "registered_run_count": 40, "rows": rows, "comparisons": comparisons}


def cell(grid, parent, method):
    return next(r for r in grid["rows"]
        if r["registered_parent_seed"] == parent and r["registered_method"] == method)


def comparison(grid, parent, a, b):
    return next(r for r in grid["comparisons"]
        if r["parent_seed"] == parent and r["reference_method"] == a and r["candidate_method"] == b)


def test_five_method_means_all_ten_pairs_four_main_effects_and_interaction():
    report = effects.build_effects(fixture_grid())
    assert len(report["methods"]) == 5 and len(report["paired_effects"]) == 10
    assert report["methods"]["C11"]["complete_eight_parent_mean_J_bag_seconds"] == 960.
    assert report["main_effect_keys"] == list(effects.MAIN_EFFECTS)
    assert len(report["R0_effect_keys"]) == 4
    expected = {"C00_minus_C01": 10., "C10_minus_C11": 20.,
                "C00_minus_C10": 20., "C01_minus_C11": 30.}
    for key, value in expected.items():
        row = report["paired_effects"][key]
        assert row["complete_eight_parent_mean_gain_bag_seconds"] == value
        assert row["cost_direction_counts"]["candidate_better"] == 8
        assert row["registered_parent_count"] == row["known_parent_count"] == 8
    assert report["interaction"]["complete_eight_parent_mean_gain_bag_seconds"] == 10.
    assert report["interaction"]["relative_gain_of_mean_J"] == .01
    assert not report["interaction"]["engineering_threshold_applied"]
    assert not report["strict_nonharm_certified"] and not report["confidence_intervals_or_p_values_computed"]


def test_relative_mean_and_ratio_of_means_are_explicitly_different():
    costs = {(parent, method): 1000. for parent in effects.PARENTS for method in effects.METHODS}
    costs[(1301, "C00")] = 100.
    costs[(1301, "C01")] = 90.
    costs[(1302, "C01")] = 900.
    report = effects.build_effects(fixture_grid(costs))
    row = report["paired_effects"]["C00_minus_C01"]
    assert row["complete_mean_of_paired_relative_gains"] == pytest.approx(.2/8)
    assert row["relative_gain_of_mean_J"] == pytest.approx(110./7100.)
    assert row["complete_mean_of_paired_relative_gains"] != row["relative_gain_of_mean_J"]


def test_failed_cell_retained_unknown_without_partial_parent_mean():
    grid = fixture_grid()
    row = cell(grid, 1308, "C11")
    row.update(status="censored_budget", audit_status="retained_incomplete_no_gain", full_window_cost=None)
    for value in grid["comparisons"]:
        if value["parent_seed"] == 1308 and value["candidate_method"] == "C11":
            value.update(status="unknown_incomplete_or_unverified", advantage_bag_seconds=None)
    report = effects.build_effects(grid)
    assert report["methods"]["C11"]["complete_eight_parent_mean_J_bag_seconds"] is None
    assert report["methods"]["C11"]["closed_cost_parent_count"] == 7
    assert report["status_counts"]["censored_budget"] == 1
    effect = report["paired_effects"]["C10_minus_C11"]
    assert effect["registered_parent_count"] == 8 and effect["known_parent_count"] == 7
    assert effect["complete_eight_parent_mean_gain_bag_seconds"] is None
    assert effect["relative_gain_of_mean_J"] is None and effect["engineering_threshold_reached"] is None
    assert effect["cost_direction_counts"]["unknown"] == 1
    assert report["paired_effects"]["C00_minus_C01"]["complete_eight_parent_mean_gain_bag_seconds"] == 10.
    assert report["interaction"]["complete_eight_parent_mean_gain_bag_seconds"] is None
    loo = effect["leave_one_parent_out"]
    assert loo["positive_mean_survives_removal_of_every_parent"] is None
    assert next(r for r in loo["entries"] if r["omitted_parent_seed"] == 1308)["known_remaining_parent_count"] == 7


def test_missing_comparison_is_unknown_even_when_both_closed_costs_exist():
    grid = fixture_grid()
    missing = comparison(grid, 1304, "C10", "C11")
    grid["comparisons"].remove(missing)
    report = effects.build_effects(grid)
    assert report["methods"]["C10"]["closed_cost_parent_count"] == 8
    assert report["paired_effects"]["C10_minus_C11"]["unknown_parent_ids"] == [1304]
    assert report["interaction"]["unknown_parent_ids"] == [1304]


def test_source_mismatch_descriptive_diagnostic_cannot_become_formal_gain():
    grid = fixture_grid()
    row = comparison(grid, 1301, "C10", "C11")
    row.update(status="not_comparable_contract_mismatch", advantage_bag_seconds=None,
        physical_cost_diagnostic={"reference_minus_candidate_J_bag_seconds": 9999999.,
                                  "formal_same_runtime_comparison": False})
    report = effects.build_effects(grid)
    point = report["paired_effects"]["C10_minus_C11"]["points"][0]
    assert point["advantage_bag_seconds"] is None and point["status"] == "unknown"
    assert report["paired_effects"]["C10_minus_C11"]["complete_eight_parent_mean_gain_bag_seconds"] is None


def test_single_parent_gain_dependency_preserves_progress_evidence_without_causality():
    costs = {(parent, method): 1000. for parent in effects.PARENTS for method in effects.METHODS}
    for parent in effects.PARENTS:
        costs[(parent, "C11")] = 900. if parent == 1301 else 1001.
    grid = fixture_grid(costs)
    cell(grid, 1301, "C10")["physical"]["global_progress"].update(
        longest_no_edge_progress_seconds=50000., longest_no_edge_progress_interval=[9400., 59400.])
    row = effects.build_effects(grid)["paired_effects"]["C10_minus_C11"]
    assert row["complete_eight_parent_mean_gain_bag_seconds"] == pytest.approx(93./8)
    loo = row["leave_one_parent_out"]
    assert loo["positive_gain_occurs_only_in_one_parent"]
    assert loo["parent_removal_eliminates_positive_mean"] == [1301]
    assert loo["positive_mean_survives_removal_of_every_parent"] is False
    omitted = loo["entries"][0]
    assert omitted["complete_mean_gain_bag_seconds"] == -1.
    assert omitted["omitted_parent_physical_diagnostics"]["reference"]["global_progress"]["longest_no_edge_progress_seconds"] == 50000.
    assert loo["caused_by_single_stalled_parent"] == "not_established_by_leave_one_out"


def test_engineering_flag_does_not_hide_exact_or_censored_harm():
    grid = fixture_grid()
    value = comparison(grid, 1301, "C10", "C11")["completion_direction"]
    value["categories"]["exact_equal"] -= 2
    value["categories"]["exact_harmed"] = 1
    value["categories"]["reference_only_finished"] = 1
    value.update(known_direction_harm=2, unknown_incomplete_legacy=91,
        maximum_censored_delay_lower_bound_seconds=80., sum_censored_delay_lower_bound_seconds=80.)
    report = effects.build_effects(grid)["paired_effects"]["C10_minus_C11"]
    assert report["engineering_threshold_reached"] is True
    assert report["service"]["known_direction_harm_zero_all_parents"] is False
    assert report["service"]["registered_service_constraints_satisfied"] is False
    assert report["service"]["complete_known_direction_harm_sum"] == 2
    assert report["points"][0]["completion_direction"]["sum_censored_delay_lower_bound_seconds"] == 80.
    assert not report["strict_nonharm_certified"]
    assert not report["engineering_flag_is_significance_or_noninferiority"]


def test_missing_or_invalid_direction_is_unknown_not_zero_harm():
    grid = fixture_grid()
    comparison(grid, 1303, "C00", "C01")["completion_direction"]["known_direction_harm"] = 7
    row = effects.build_effects(grid)["paired_effects"]["C00_minus_C01"]
    assert row["known_parent_count"] == 8  # Cost remains known.
    assert row["points"][2]["known_direction_harm"] is None
    assert row["service"]["known_direction_harm_zero_all_parents"] is None
    assert row["service"]["complete_eight_parent_category_totals"] is None


def test_zero_baseline_J_has_unknown_relative_gain_not_division_or_fake_zero():
    costs = {(parent, method): 0. for parent in effects.PARENTS for method in effects.METHODS}
    row = effects.build_effects(fixture_grid(costs))["paired_effects"]["C00_minus_C01"]
    assert row["complete_eight_parent_mean_gain_bag_seconds"] == 0.
    assert row["complete_mean_of_paired_relative_gains"] is None
    assert row["relative_gain_of_mean_J"] is None and row["engineering_threshold_reached"] is None
    assert row["cost_direction_counts"]["equal_within_numeric_tolerance"] == 8


def test_gain_or_service_arithmetic_mismatch_fails_closed_separately():
    grid = fixture_grid()
    comparison(grid, 1301, "C00", "C01")["advantage_bag_seconds"] = 1000000.
    comparison(grid, 1302, "C00", "C01")["on_time_delta"] = 10
    row = effects.build_effects(grid)["paired_effects"]["C00_minus_C01"]
    assert row["points"][0]["advantage_bag_seconds"] is None
    assert row["points"][1]["advantage_bag_seconds"] == 10.
    assert row["points"][1]["on_time_delta"] is None
    assert row["service"]["on_time_non_decreasing_all_parents"] is None


def test_duplicate_or_missing_registered_cells_and_comparisons_are_rejected():
    grid = fixture_grid()
    grid["rows"][-1] = deepcopy(grid["rows"][0])
    with pytest.raises(ValueError, match="complete_unique_registered_roster"):
        effects.build_effects(grid)
    grid = fixture_grid()
    grid["comparisons"].append(deepcopy(grid["comparisons"][0]))
    with pytest.raises(ValueError, match="registered_unique_comparison_orientation"):
        effects.build_effects(grid)
    grid = fixture_grid()
    grid["rows"].pop()
    with pytest.raises(ValueError, match="complete_unique_registered_roster"):
        effects.build_effects(grid)


def test_bound_artifact_writer_never_reads_other_files_and_refuses_changed_input(tmp_path):
    path = tmp_path / "DUMMY_audit.json"
    path.write_text(json.dumps(fixture_grid()))
    reference = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    output = tmp_path / "DUMMY_effects.json"
    result = effects.write_effects(reference, output=output)
    report = json.loads(output.read_text())
    assert report["source_audit"] == reference and report["registered_run_count"] == 40
    assert result["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    path.write_text("{}")
    with pytest.raises(ValueError, match="bound_audit_bytes"):
        effects.write_effects(reference, output=tmp_path / "must_not_exist.json")
    assert not (tmp_path / "must_not_exist.json").exists()


def test_integration_accepts_actual_audit_grid_schema_from_dummy_artifacts(tmp_path):
    from scripts.experiments.g31_ics_circulation import foundation_airport_inventory_spi_audit as audit
    from test_g31_airport_inventory_spi_audit import fixture_run
    run_root = tmp_path / "runs"
    fixture_run(run_root, "reference")
    fixture_run(run_root, "candidate", completions={"j0": 7290., "j1": 7390., "j2": 7490., "j3": 7590.})
    specs = [{"parent_seed": parent, "method": method,
        "name": ("reference" if (parent, method) == (1301, "C00")
                 else "candidate" if (parent, method) == (1301, "C11")
                 else f"DUMMY_NOT_STARTED_{parent}_{method}")}
        for parent in effects.PARENTS for method in effects.METHODS]
    grid = audit.audit_grid(tmp_path, specs, expected_population=7)
    result = effects.build_effects(grid)
    compared = result["paired_effects"]["C00_minus_C11"]
    assert compared["known_parent_count"] == 1
    assert compared["points"][0]["advantage_bag_seconds"] == 40.
    assert compared["complete_eight_parent_mean_gain_bag_seconds"] is None
    assert result["status_counts"]["not_started"] == 38
    assert compared["service"]["known_completion_direction_parent_count"] == 1
