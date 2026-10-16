import copy
import pytest
from scripts.experiments.g31_ics_circulation import preference_matrix_contract as matrix


def complete_rows():
    rows = matrix.matrix_protocol()["rows"]
    for row in rows.values():
        times = {job:10. for job in matrix.JOBS}
        row.update(status="assessed", summary={"business_complete":True, "common_horizon_complete":True,
            "audit":{"status":"passed"}, "selected_actions_executed":True, "all_required_inputs_verified":True,
            "completion":times, "completion_sum":50.,
            "initial_actual_next":1 if row["vector"]["initial_action"] == "native_default" else 2,
            "first_reuse_actual_next":3 if row["vector"]["later_action"] == "native_default" else 8})
    return rows


def test_exact_full_six_by_32_preregistered_budget():
    plan = matrix.matrix_protocol()
    assert len(plan["rows"]) == plan["native_branch_budget"] == 192
    assert len(plan["case_groups"]) == 6
    assert all(len(keys) == 32 for keys in plan["case_groups"].values())
    assert plan["per_case_parent_timeout_seconds"] == 180.
    assert plan["total_parent_timeout_budget_seconds"] == 6 * 180.
    for case_id, keys in plan["case_groups"].items():
        assert len({matrix.key_for(plan["rows"][key]["vector"]) for key in keys}) == 32
        assert plan["incumbent_keys"][case_id] in keys


def test_every_fixed_initial_family_has_all_four_windows_and_both_late_choices():
    result = matrix.compare(complete_rows())
    assert result["status"] == "complete_declared_denominator"
    for group in result["cases"].values():
        for family in group["fixed_initial_families"].values():
            assert family["status"] == "complete_assessed_finite_reference"
            assert family["member_count"] == 16


@pytest.mark.parametrize("mutation", ["missing_row", "changed_vector", "changed_case", "changed_method"])
def test_incomplete_or_misbound_total_denominator_unknown(mutation):
    rows = complete_rows(); key = next(iter(rows))
    if mutation == "missing_row": rows.pop(key)
    elif mutation == "changed_vector": rows[key]["vector"]["return_delay"] = 9.
    elif mutation == "changed_case": rows[key]["case"]["receiver_load"] = 99.
    else: rows[key]["method"] = "selected_success_only"
    assert matrix.compare(rows)["status"] == "unknown_incomplete_or_misbound_denominator"


@pytest.mark.parametrize("mutation", ["not_executed", "missing_input", "no_ack_action", "incomplete_horizon", "physical_failure", "bool_time", "unfinished", "wrong_sum"])
def test_unfinished_invalid_and_unexecuted_cells_never_become_protected(mutation):
    rows = complete_rows(); key = list(rows)[1]; row = rows[key]; value = row["summary"]
    if mutation == "not_executed": row["status"] = "unknown_unexecuted"
    elif mutation == "missing_input": value["all_required_inputs_verified"] = False
    elif mutation == "no_ack_action": value["selected_actions_executed"] = False
    elif mutation == "incomplete_horizon": value["common_horizon_complete"] = False
    elif mutation == "physical_failure": value["audit"]["status"] = "failed"
    elif mutation == "bool_time": value["completion"]["receiver"] = True
    elif mutation == "unfinished": value["completion"]["receiver"] = -1.
    else: value["completion_sum"] += 1.
    result = matrix.compare(rows)["cases"][row["case"]["case_id"]]
    assert result["rows"][key]["strict_protected_vs_incumbent"] is None
    assert result["fixed_initial_families"][row["vector"]["initial_action"]]["best_protected_key"] is None


def test_updated_but_same_actual_edge_is_not_causal_route_witness():
    rows = complete_rows()
    key = next(k for k,r in rows.items() if r["vector"]["initial_action"] == "prefer_2")
    control = {**rows[key]["vector"], "initial_action":"native_default"}
    control_key = next(k for k,r in rows.items() if r["case"] == rows[key]["case"] and r["vector"] == control)
    rows[control_key]["summary"]["initial_actual_next"] = 2
    contrast = matrix.compare(rows)["cases"][rows[key]["case"]["case_id"]]["rows"][key]["paired_route_contrasts"]["initial_action"]
    assert contrast["status"] == "no_actual_edge_change"


def test_reported_execution_does_not_override_missing_requested_edge():
    rows = complete_rows()
    row = next(r for r in rows.values() if r["vector"]["initial_action"] == "prefer_2")
    row["summary"]["initial_actual_next"] = 1
    assert matrix.valid(row) is False


def test_new_prefix_edge_difference_needs_matching_default_cell():
    rows = complete_rows()
    key = next(k for k,r in rows.items() if r["vector"]["later_action"] == "prefer_8")
    result = matrix.compare(rows)["cases"][rows[key]["case"]["case_id"]]["rows"][key]
    contrast = result["paired_route_contrasts"]["later_action"]
    assert contrast["status"] == "actual_edge_changed"
    rows[contrast["matched_default_key"]]["status"] = "unknown_timeout"
    contrast = matrix.compare(rows)["cases"][rows[key]["case"]["case_id"]]["rows"][key]["paired_route_contrasts"]["later_action"]
    assert contrast["status"] == "unknown" and contrast["strict_all_five_protection"] is None
