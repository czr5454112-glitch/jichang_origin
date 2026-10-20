"""C10 finite selection with only actual two-arm labels; no fitting or native."""
from copy import deepcopy

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_spi_rule_selection as select
from scripts.experiments.g31_ics_circulation import foundation_airport_opportunities as opportunities
from scripts.experiments.g31_ics_circulation.foundation_airport_prospective_control import current_candidate_rows
from scripts.experiments.g31_ics_circulation.foundation_airport_batch_patch import digest
from test_g31_foundation_airport_strong_rule import setup, rows, queue


def dataset(seed=1201, index=0, *, gain=10., harm=0, demand=None):
    obs, baseline = setup()
    for node in (1, 2, 3, 10):
        queue(obs, node, 0)
    old = rows(obs, baseline, demand=demand or {2: [1., 0., 0.]})
    parent = dict(old[0]["parent"], parent_seed=seed, parent_group=f"fixture-{seed}", split="dev")
    forecast = deepcopy(old[0]["forecast_evidence"])
    forecast["plan_receipt"]["parent_group"] = parent["parent_group"]
    receipt = forecast["plan_receipt"]
    receipt["receipt_sha256"] = digest({k: v for k, v in receipt.items() if k != "receipt_sha256"})
    opportunity = opportunities.build_opportunity(obs, baseline,
        continuation_version="airport_common_inventory_pi0_v1", message_delay=2.,
        respect_service_forecasts=False, k_max=13)
    current = current_candidate_rows(obs, baseline, opportunity, parent=parent,
        information_variant="C10", forecast_evidence=forecast, patch_rank=1)
    for row in current:
        row["actual_execution"] = {"attempts": []}
        row["target_return"] = "FORBIDDEN_LABEL"
        row["paired_advantage_bag_seconds"] = "FORBIDDEN_LABEL"
    costs = {"label_start": 100., "label_end": 1900., "physical_population": 1,
        "on_time_by_end": 1, "arrived_unfinished_past_deadline": 0,
        "backlog_integral_bag_seconds": 1000.}
    return {"pair": {"pair_id": f"{seed}:{index}", "parent": parent, "status": "closed_actual_pair",
        "advantage_bag_seconds": gain, "reference_cost": deepcopy(costs),
        "patched_cost": dict(costs, backlog_integral_bag_seconds=1000.-gain),
        "policy_alignment": {"continuation_policy_id": "airport_common_inventory_pi0_v1",
            "max_policy_replacements": 1, "improvement_round": 0},
        "censored_direction_summary": {"population": 1, "known_direction_harm": harm,
            "categories": {"exact_harmed": 0, "reference_only_finished": harm}}},
        "rows": current}


def all_data(**options):
    return [dataset(seed, index, **options) for seed in (1201, 1202, 1203, 1204) for index in (0, 1)]


def test_full_catalog_forecast_can_change_winner_without_reading_labels():
    data = dataset()
    before = deepcopy(data)
    score = select.score_catalog(data)
    assert score["K"] == 4 and score["winner_weight1"] == "a_patch"
    assert score["winner_weight0"] != score["winner_weight1"]
    assert len(score["candidate_diagnostics"]) == 3
    assert not score["outcome_labels_read_for_scores"] and data == before
    data["pair"]["advantage_bag_seconds"] = -9876543.
    for row in data["rows"]:
        row["target_return"] = {"private_future": 999999}
    assert select.score_catalog(data) == score


def test_builder_strips_targets_and_keeps_actual_forecast_and_batch():
    data = dataset()
    candidates = select.public_candidate_rows(data)
    assert len(candidates) == 3
    for pair in candidates:
        for row in pair:
            assert not select.rule.FORBIDDEN.intersection(row)
            assert row["forecast_evidence"] == data["rows"][0]["forecast_evidence"]
            assert row["baseline_decision"] == data["rows"][0]["baseline_decision"]


def test_unexecuted_full_catalog_winner_never_gets_measured_patch_label():
    data = dataset()
    result = select._label_for_winner(data, "a_patch:3")
    assert result["label_support"] == "unsupported_unexecuted_winner"
    assert result["gain_bag_seconds"] is result["known_direction_harm"] is None


def test_valid_complete_positive_development_can_select_forecast_rule():
    evaluation = select.evaluate_datasets(all_data(), select.selection_contract())
    assert evaluation["selected_method"] == "strong_rule_weight1"
    chosen = evaluation["methods"][2]
    assert chosen["supported_fraction"] == 1.
    assert chosen["complete_parent_balanced_paired_gain"] == 10.
    assert len(chosen["per_parent"]) == 4
    assert all(r["registered_root_count"] == 2 for r in chosen["per_parent"])
    assert evaluation["diagnostic_denominators"]["registered_root_slots"] == 8
    assert evaluation["diagnostic_denominators"]["nonreference_candidate_rows"] == 24
    assert not evaluation["full_policy_development_return_claimed"]


def test_censored_harm_blocks_positive_rule_gain_and_preserves_reference():
    evaluation = select.evaluate_datasets(all_data(harm=1), select.selection_contract())
    assert evaluation["selected_method"] == "reference"
    assert "known_service_constraint_violation" in evaluation["methods"][2]["promotion_blockers"]


def test_unexecuted_winner_blocks_complete_J_not_imputed_to_zero():
    data = all_data()
    data[0] = dataset(1201, 0, demand={3: [10., 0., 0.]})
    evaluation = select.evaluate_datasets(data, select.selection_contract())
    selected = evaluation["methods"][2]
    assert selected["supported_fraction"] >= .25
    assert selected["complete_parent_balanced_paired_gain"] is None
    assert "incomplete_development_J_unknown" in selected["promotion_blockers"]
    assert evaluation["selected_method"] == "reference"


def test_nonpositive_gain_and_service_tradeoff_never_force_strong_rule():
    data = all_data(gain=0.)
    assert select.evaluate_datasets(data, select.selection_contract())["selected_method"] == "reference"
    data = all_data(gain=10.)
    data[0]["pair"]["patched_cost"]["on_time_by_end"] = 0
    assert select.evaluate_datasets(data, select.selection_contract())["selected_method"] == "reference"


def test_no_eligible_slot_retained_in_denominator_and_all_method_unknowns():
    data = all_data()
    data[0]["pair"].update(status="not_comparable", reason="one_or_both_registered_cells_have_no_eligible_anchor")
    data[0]["rows"] = []
    result = select.evaluate_datasets(data, select.selection_contract())
    assert result["registered_pair_count"] == 8
    assert result["diagnostic_denominators"]["registered_no_eligible_root_slots"] == 1
    assert result["diagnostic_denominators"]["valid_saved_public_views"] == 7
    assert result["selected_method"] == "reference"


def test_missing_captured_waiting_is_unknown_not_actual_no_demand():
    data = dataset()
    prepared = select.rule._prepare(*select.public_candidate_rows(data)[0])
    values = list(prepared)
    values[8] = deepcopy(prepared[8])
    for coverage in values[8].values():
        coverage["waiting_exact_captured_count"] = False
    regimes = select._shortage_regime(tuple(values), data["rows"][1]["semantic_action"])
    assert all(r["regime"] == "unknown_account_coverage" for r in regimes)


def test_read_only_dev_scope_checked_before_open(monkeypatch):
    refs = [{"parent": {"parent_seed": 1301+i//2, "parent_group": str(i//2), "split": "test"},
        "dataset": {"path": f"must-not-open-{i}", "sha256": "0"*64}} for i in range(8)]
    monkeypatch.setattr(select, "_read", lambda _: pytest.fail("test dataset opened"))
    with pytest.raises(ValueError, match="reject_nondev_metadata"):
        select.load_dev_inputs(refs, select.selection_contract())


def test_freeze_roundtrip_binds_selection_inputs_and_source(tmp_path):
    refs = []
    for index, data in enumerate(all_data(harm=1)):
        path = tmp_path/f"dummy-{index}.json"
        path.write_text(select.json.dumps(data), encoding="utf8")
        refs.append({"parent": data["pair"]["parent"], "dataset": {
            "path": str(path), "sha256": select.hashlib.sha256(path.read_bytes()).hexdigest()}})
    ref = select.select_and_freeze(refs, output=tmp_path/"dummy_rule.json")
    rule = select.validate_rule_selection(ref)
    assert rule["selected"] == "reference" and rule["forecast_weight"] == 0
    assert rule["evaluation"]["registered_pair_count"] == 8 and rule["fit_calls"] == 0
    assert rule["contract"]["max_policy_replacements_per_parent"] == 1
