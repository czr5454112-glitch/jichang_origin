from copy import deepcopy

import pytest

from scripts.experiments.g31_ics_circulation.assess_r1_reuse import assess


def receipt():
    return {"status": "executed", "source_changed": [], "branches": {
        name: {"status": "reached", "R1_ack": {"status": "updated"},
               "jobs": [{"business_bag_id": "a", "completed_at": cost}]}
        for name, cost in [("reactive_control", 10.), ("reactive_next_2", 11.),
                           ("predictive_control", 8.), ("predictive_next_2", 12.)]}}


def test_interaction_uses_four_complete_cells():
    report = assess(receipt())
    assert report["factorial"][0]["kappa_completion_sum_seconds"] == 3.
    assert report["factorial"][0]["factorial_completion_sum_seconds"] == 3.
    assert report["comparison_scope"] == "R1_next_hop_by_R2_continuation_policy_factorial_contrast"
    assert not report["same_continuation_joint_action_kappa"]
    assert report["business_denominator_scope"] == "observed_branch_ids_only_no_offered_manifest"
    assert report["best_enumerated_minus_control_seconds"] == {"reactive": 0., "predictive": 0.}
    assert not report["joint_nonseparability_claim"]  # no automatic broad scientific claim


def test_censored_failed_or_source_changed_cell_cannot_be_zero_headroom():
    for mutation in ["censored", "rejected", "changed", "missing"]:
        r = deepcopy(receipt())
        if mutation == "censored":
            r["branches"]["predictive_next_2"]["jobs"][0]["completed_at"] = -1.
        elif mutation == "rejected":
            r["branches"]["predictive_next_2"]["R1_ack"]["status"] = "rejected"
        elif mutation == "changed":
            r["source_changed"] = ["controller.py"]
        else:
            del r["branches"]["predictive_next_2"]
        assert assess(r)["status"] == "unknown"


@pytest.mark.parametrize("cell", ["reactive_control", "predictive_control", "reactive_next_2", "predictive_next_2"])
def test_every_factorial_cell_is_required_without_keyerror_or_zero_contrast(cell):
    r = receipt(); del r["branches"][cell]
    report = assess(r)
    assert report["status"] == "unknown"
    assert "factorial" not in report and "best_enumerated_minus_control_seconds" not in report


@pytest.mark.parametrize("field,value", [("completed_at", float("nan")), ("completed_at", float("inf")),
    ("completed_at", -float("inf")), ("completed_at", None), ("completed_at", True), ("loaded_at", float("nan"))])
def test_nonfinite_or_missing_business_time_cannot_generate_nan_or_zero_result(field, value):
    r = receipt(); r["branches"]["predictive_next_2"]["jobs"][0][field] = value
    report = assess(r)
    assert report["status"] == "unknown" and report["reason"] == "missing_or_nonfinite_business_time"


def test_consistently_duplicated_job_identity_is_not_a_complete_denominator():
    r = receipt()
    for branch in r["branches"].values():
        branch["jobs"].append(deepcopy(branch["jobs"][0]))
    assert assess(r)["reason"] == "duplicate_or_invalid_business_identity"


def test_offered_selection_prevents_all_cells_silently_dropping_same_job():
    r = receipt()
    selection = {"selected_business_ids": ["a", "b"], "witness_offered": 2, "mother_offered": 28506}
    assert assess(r, selection=selection)["status"] == "unknown"
    r["expected_business_ids"] = ["a", "b"]
    assert assess(r)["status"] == "unknown"
    for branch in r["branches"].values():
        branch["jobs"].append({"business_bag_id": "b", "completed_at": 20.})
    r["branches"]["predictive_next_2"]["jobs"].reverse()
    report = assess(r, selection=selection)
    assert report["status"] == "assessed" and report["business_ids"] == ["a", "b"]
    assert report["business_denominator_scope"] == "declared_offered_ids"
    assert report["factorial"][0]["factorial_completion_sum_seconds"] == 3.


def test_conflicting_or_duplicate_offered_contract_is_unknown():
    r = receipt(); r["expected_business_ids"] = ["a"]
    assert assess(r, selection={"selected_business_ids": ["b"]})["reason"] == "conflicting_offered_business_ids"
    assert assess(r, selection={"selected_business_ids": ["a", "a"]})["reason"] == "invalid_offered_business_ids"
    assert assess(r, selection={"selected_business_ids": ["a"], "witness_offered": 2})["reason"] == "offered_business_count_mismatch"


def test_missing_status_or_partial_horizon_is_unknown_even_with_positive_completion():
    for mutate in (lambda b: b.pop("status"), lambda b: b.update(horizon_complete=False),
                   lambda b: b["jobs"][0].update(status="waiting")):
        r = receipt(); mutate(r["branches"]["predictive_next_2"])
        assert assess(r)["status"] == "unknown"


def test_unregistered_extra_cell_cannot_invent_negative_headroom():
    r = receipt()
    r["branches"]["reactive_unregistered"] = {"status": "reached", "jobs": [{"business_bag_id": "a", "completed_at": 0.}]}
    assert assess(r)["reason"] == "unexpected_factorial_cell"
