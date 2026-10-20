"""Synthetic linear algebra and control gates; no campaign fit/native runs."""
from copy import deepcopy

import numpy as np
import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_spi as spi
from scripts.experiments.g31_ics_circulation import foundation_airport_pair_ranker as ranker
from scripts.experiments.g31_ics_circulation import foundation_airport_pair_training_campaign as training
from scripts.experiments.g31_ics_circulation import foundation_airport_prospective_control as control
from scripts.experiments.g31_ics_circulation.foundation_airport_service_metrics import compare_completion_outcomes
from test_g31_foundation_airport_pair_ranker import dataset
from test_g31_foundation_airport_prospective_control import make, parent
from test_g31_foundation_airport_pairs import fixture
from test_g31_foundation_airport_pairs import PARENT, bind
from scripts.experiments.g31_ics_circulation import foundation_airport_paired_continuation as paired


DOMAIN = {"fleet": 22, "layout_id": "fixture", "plan_family_id": "fixture", "physical_contract_id": "fixture"}


def contract():
    return spi.make_spi_contract(allowed_domains=[DOMAIN], behavior_policy_id="pi0",
        continuation_policy_id="pi0")


def numerical():
    return spi.solve_difference_matrix([[0., 0., 5.], [0., 0., 7.]],
        [[1., 2., 5.], [2., 4., 7.]], [3., 6.],
        solver="truncated_svd", ridge_lambda=0.)


def test_minimum_norm_rank_one_and_train_zero_column_removed():
    result = numerical()
    assert result["rank"] == 1
    assert result["deleted_zero_columns"] == [2]
    assert result["rank_deficient"] and result["full_column_condition_number"] is None
    assert result["effective_condition_number"] == pytest.approx(1.)
    assert result["weight_rowspace_residual_l2"] < 1e-12
    assert result["train_predictions"] == pytest.approx([3., 6.])
    # Equal normalized columns imply equal minimum-norm coordinates.
    assert result["weights"][0] == pytest.approx(result["weights"][1])


def test_ridge_is_deterministic_and_has_no_random_nullspace_component():
    args = ([[0., 0.], [0., 0.]], [[1., 2.], [2., 4.]], [3., 6.])
    a = spi.solve_difference_matrix(*args, solver="ridge", ridge_lambda=1.)
    b = spi.solve_difference_matrix(*args, solver="ridge", ridge_lambda=1.)
    assert a == b and a["weight_rowspace_residual_l2"] < 1e-12
    assert a["train_predictions"][1] < 6.


def test_new_nullspace_direction_and_train_zero_column_fall_back():
    params = numerical()
    good = spi.support_diagnostics(params, [0., 0., 5.], [1., 2., 5.], contract())
    assert good["supported"] and good["advantage"] == pytest.approx(3.)
    bad = spi.support_diagnostics(params, [0., 0., 5.], [1., -2., 5.], contract())
    assert not bad["supported"] and bad["advantage"] == 0.
    assert "outside_training_rowspace" in bad["fallback_reasons"]
    unseen = spi.support_diagnostics(params, [0., 0., 5.], [1., 2., 6.], contract())
    assert "new_action_difference_in_train_zero_column" in unseen["fallback_reasons"]


def test_distance_fallback_is_separate_from_rowspace():
    result = spi.support_diagnostics(numerical(), [0., 0., 5.], [100., 200., 5.], contract())
    assert result["relative_rowspace_residual"] < 1e-10
    assert "far_from_supported_action_differences" in result["fallback_reasons"]
    result = spi.support_diagnostics(numerical(), [100., 100., 5.], [101., 102., 5.], contract())
    assert "far_from_supported_public_states" in result["fallback_reasons"]


def test_all_zero_differences_are_supported_by_no_action_direction():
    params = spi.solve_difference_matrix([[1., 2.]], [[1., 2.]], [10.],
        solver="truncated_svd", ridge_lambda=0.)
    result = spi.support_diagnostics(params, [1., 2.], [1., 2.], contract())
    assert not result["supported"] and result["advantage"] == 0.
    assert params["rank"] == 0 and params["weights"] == []


def test_reference_model_is_real_and_invalid_domain_falls_back():
    model = spi.make_reference_champion(information_variant="C01", contract=contract(),
        model_available_at_epoch_seconds=1700000000.)
    rows = dataset()["rows"]
    for row in rows:
        row["parent"]["spi_domain"] = deepcopy(DOMAIN)
    predict = ranker.prepare_predictor(model)
    assert predict(*rows)["reference_champion"] and predict(*rows)["advantage"] == 0.
    rows[1]["parent"]["spi_domain"]["fleet"] = 26
    assert not predict(*rows)["supported"]


def test_dev_tie_and_harmful_positive_candidate_leave_reference(monkeypatch):
    ref = spi.make_reference_champion(information_variant="C01", contract=contract(),
        model_available_at_epoch_seconds=1700000000.)
    candidate = dict(ref, reference_champion=False, model_id="learned")
    def result(model, _data):
        return {"model_id": model["model_id"], "reference_champion": model["reference_champion"],
            "failures": 0, "service_constraint_violation": not model["reference_champion"],
            "support_constraint_violation": False, "total_gain_bag_seconds": 100.,
            "incomplete_development_J": False, "complete_parent_balanced_paired_gain": 100.}
    monkeypatch.setattr(spi, "evaluate_spi_on_dev", result)
    assert spi.select_spi_on_dev([candidate, ref], [])["reference_champion"]
    monkeypatch.setattr(spi, "evaluate_spi_on_dev", lambda model, _: dict(result(model, _),
        service_constraint_violation=False, total_gain_bag_seconds=0.,
        complete_parent_balanced_paired_gain=0.))
    assert spi.select_spi_on_dev([candidate, ref], [])["reference_champion"]


def test_exact_zero_harm_does_not_hide_reference_only_finished():
    result = compare_completion_outcomes([{"business_bag_id": "j", "arrival": 0.}],
        {"j": 9.}, {}, cutoff=10.)
    assert result["categories"]["exact_harmed"] == 0
    assert result["known_direction_harm"] == 1
    assert result["maximum_censored_delay_lower_bound_seconds"] == 1.


def test_one_policy_replacement_then_rule_across_later_ticks():
    planning = make(lambda *_: 1., continuation_version="pi0",
        deployment_contract=contract()["policy_alignment"])
    obs, baseline = fixture()
    assert planning(obs, predictive=True)["batch_patch"]["kind"] == "replace_optional"
    obs["now"] += 60.
    assert planning(obs, predictive=True) == baseline
    assert planning.report()["state"]["policy_replacements_proposed"] == 1
    assert planning.records[-1]["status"] == "fixed_continuation_after_one_replacement"


def test_reference_champion_never_calls_forecast_or_selector():
    def forbidden(*_args, **_kwargs):
        raise AssertionError("reference has no learned intervention")
    planner = make(forbidden, information_variant="C11", forecast_at=forbidden,
        reference_champion=True, continuation_version="pi0",
        deployment_contract=contract()["policy_alignment"])
    obs, baseline = fixture()
    assert planner(obs, predictive=True) == baseline
    assert planner.records[-1]["status"] == "reference_champion"


def test_unsupported_positive_raw_prediction_cannot_change_action():
    planner = make(lambda *_: {"supported": False, "advantage": 1000.})
    obs, baseline = fixture()
    assert planner(obs, predictive=True) == baseline
    assert planner.records[-1]["candidate_scores"][0]["advantage"] == 0.


def test_test_metadata_rejected_before_dataset_open(monkeypatch):
    monkeypatch.setattr(training, "read_bound", lambda _: pytest.fail("test bytes opened"))
    with pytest.raises(ValueError, match="declared_split_before_open"):
        training._load_spi_inputs([{"parent": {"split": "test"}, "dataset": {}}], split="train")


def test_pair_label_continuation_mismatch_fails_closed():
    data = dataset()
    data["pair"]["policy_alignment"] = dict(contract()["policy_alignment"], continuation_policy_id="wrong")
    data["pair"]["parent"]["spi_domain"] = DOMAIN
    for row in data["rows"]:
        row["parent"]["spi_domain"] = DOMAIN
    with pytest.raises(ValueError, match="label_continuation"):
        spi.prepare_spi_pairs([data], information_variant="C01", split="train", contract=contract())


def test_champion_selection_clock_is_after_dev_but_dev_uses_train_weight_clock():
    rows = dataset()["rows"]
    for row in rows:
        row["parent"]["spi_domain"] = deepcopy(DOMAIN)
    now = ranker._absolute_now(rows[0])
    model = spi.make_reference_champion(information_variant="C01", contract=contract(),
        model_available_at_epoch_seconds=now-1.,
        champion_selection_available_at_epoch_seconds=now+1800.)
    assert spi.prepare_supported_predictor(model, development_evaluation=True)(*rows)["supported"]
    assert not spi.prepare_supported_predictor(model)(*rows)["supported"]


def test_paired_behavior_memory_bound_and_continuation_switch_is_explicit():
    obs, baseline = fixture()
    class Behavior:
        def __init__(self):
            self.calls = 0
        def __call__(self, *_args, **_kwargs):
            self.calls += 1
            return deepcopy(baseline)
        def state_snapshot(self):
            return {"calls": self.calls, "one_improvement_already_used": True}
    behavior, continuation = Behavior(), Behavior()
    planning = paired.PairedPlanner(behavior, branch="a_patch", window=[100., 300.],
        parent=PARENT, continuation_version="pi0", continuation_planner=continuation,
        policy_alignment=contract()["policy_alignment"])
    planning(obs, predictive=True)
    state = planning.selected["selector_state_before_action"]
    assert state["behavior_planner_state"]["calls"] == 1
    assert state["continuation_planner_state"]["calls"] == 0
    bind(planning, obs)
    obs["now"] += 60.
    planning(obs, predictive=True)
    assert behavior.calls == continuation.calls == 1
    assert planning.report()["policy_alignment"] == contract()["policy_alignment"]


def test_zero_label_campaign_freezes_real_reference_without_any_fit(tmp_path, monkeypatch):
    from pathlib import Path
    from test_g31_foundation_airport_pair_training_campaign import pair, input_refs
    def archive(directory):
        root = Path(training.__file__).resolve().parents[3]
        result = {}
        for logical, sha in training._spi_sources().items():
            target = directory/"source"/logical
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((root/logical).read_bytes())
            result[logical] = {"sha256": sha, "archive": training.file_ref(target)}
        return result
    monkeypatch.setattr(training, "_source_archive", archive)
    monkeypatch.setattr(spi, "fit_difference_ranker", lambda *_a, **_k: pytest.fail("zero data must not fit"))
    groups = {}
    for split, seeds in (("train", (701, 702)), ("dev", (801, 802))):
        groups[split] = []
        for seed in seeds:
            data = pair(seed, 0., split=split)
            data["pair"]["parent"]["spi_domain"] = deepcopy(DOMAIN)
            data["pair"]["policy_alignment"] = contract()["policy_alignment"]
            data["pair"]["censored_direction_summary"] = compare_completion_outcomes(
                [{"business_bag_id": "j", "arrival": 0.}], {"j": 9.}, {"j": 9.}, cutoff=1810.)
            for cost in ("reference_cost", "patched_cost"):
                data["pair"][cost].update(on_time_by_end=1, arrived_unfinished_past_deadline=0)
            for row in data["rows"]:
                row["parent"]["spi_domain"] = deepcopy(DOMAIN)
            refs = input_refs(tmp_path/"inputs", data)
            refs["parent"] = deepcopy(data["pair"]["parent"])
            groups[split].append(refs)
    reference = training.prepare_spi_manifest(output=tmp_path/"campaign",
        train_inputs=groups["train"], dev_inputs=groups["dev"], contract=contract(),
        model_available_at_epoch_seconds=1700000000.+3*86400.)
    manifest = training.read_bound(reference)
    assert len(manifest["chain_plans"]) == 2 and manifest["random_seed_replicas"] == 0
    for chain_ref in manifest["chain_plans"]:
        plan = training.read_bound(chain_ref)
        assert plan["fit_calls_planned"] == 0
        receipt = training.read_bound(training.run_spi_chain(chain_ref))
        assert receipt["reference_champion"] and receipt["fit_calls_started"] == 0
    frozen_ref = training.freeze_spi(reference, output=tmp_path/"frozen.json")
    frozen = training.validate_spi_freeze(frozen_ref)
    assert len(frozen["models"]) == 2 and all(m["reference_champion"] for m in frozen["models"])
    with pytest.raises(ValueError, match="no_unregistered_retry"):
        training.run_spi_chain(manifest["chain_plans"][0])


def test_development_censored_harm_blocks_positive_measured_gain(monkeypatch):
    data = dataset(801, 20., split="dev")
    data["pair"]["parent"]["spi_domain"] = deepcopy(DOMAIN)
    data["pair"]["policy_alignment"] = contract()["policy_alignment"]
    data["pair"]["per_job_comparison_counts"] = {"unknown_incomplete": 1}
    data["pair"]["censored_direction_summary"] = compare_completion_outcomes(
        [{"business_bag_id": "j", "arrival": 0.}], {"j": 9.}, {}, cutoff=1810.)
    for cost in ("reference_cost", "patched_cost"):
        data["pair"][cost].update(on_time_by_end=0, arrived_unfinished_past_deadline=1)
    for row in data["rows"]:
        row["parent"]["spi_domain"] = deepcopy(DOMAIN)
    reference = spi.make_reference_champion(information_variant="C01", contract=contract(),
        model_available_at_epoch_seconds=1700000000.)
    candidate = dict(reference, reference_champion=False, model_id="manual-fixture")
    monkeypatch.setattr(spi, "prepare_supported_predictor", lambda model, **_: lambda *_a: {
        "advantage": 0. if model["reference_champion"] else 10., "supported": True})
    monkeypatch.setattr(spi, "score_development_catalog", lambda *_: {
        "selected_action_id": "a_patch", "actual_patch_action_id": "a_patch",
        "any_nonreference_feature_support": True})
    evaluation = spi.evaluate_spi_on_dev(candidate, [data])
    assert evaluation["total_gain_bag_seconds"] == 20.
    assert evaluation["known_direction_harmed"] == 1 and evaluation["service_constraint_violation"]
    assert spi.select_spi_on_dev([reference, candidate], [data])["reference_champion"]


def test_full_catalog_scores_each_legal_candidate_but_changes_one_tray():
    seen = []
    def score(reference, patch):
        destination = patch["semantic_action"]["destination"]
        seen.append(destination)
        return 2. if destination == 3 else 0.
    planner = make(score, k_max=13, score_all_candidates=True,
        continuation_version="pi0", deployment_contract=contract()["policy_alignment"])
    obs, baseline = fixture()
    chosen = planner(obs, predictive=True, message_delay=2.)
    assert set(seen) == {2, 3, None}
    assert chosen["intents"][0]["destination"] == 3
    assert chosen["intents"][1:] == baseline["intents"][1:]
    assert planner.report()["state"]["policy_replacements_proposed"] == 1


def full_catalog_data(seed=1201, index=0, gain=20.):
    from test_g31_foundation_airport_spi_rule_selection import dataset as full_dataset
    data = full_dataset(seed, index, gain=gain)
    data["pair"]["parent"]["spi_domain"] = deepcopy(DOMAIN)
    data["pair"]["policy_alignment"] = contract()["policy_alignment"]
    data["pair"]["per_job_comparison_counts"] = {"equal": 1}
    data["pair"]["action_difference"] = True
    data["pair"]["censored_direction_summary"] = compare_completion_outcomes(
        [{"business_bag_id": "j", "arrival": 0.}], {"j": 9.}, {"j": 9.}, cutoff=1900.)
    for i, row in enumerate(data["rows"]):
        row.update(pair_id=data["pair"]["pair_id"], unexecuted_candidate_label=False,
            target_return=-1000.+i*gain, paired_advantage_bag_seconds=gain)
        row["parent"]["spi_domain"] = deepcopy(DOMAIN)
    return data


def models_with_mock_score(monkeypatch, score):
    reference = spi.make_reference_champion(information_variant="C01", contract=contract(),
        model_available_at_epoch_seconds=1700000000.)
    candidate = dict(reference, reference_champion=False, model_id="DUMMY_not_fitted")
    monkeypatch.setattr(spi, "prepare_supported_predictor", lambda _model, **_:
        lambda ref, patch: {"advantage": score(ref, patch), "supported": True})
    return reference, candidate


def test_unexecuted_catalog_winner_cannot_inherit_positive_executed_patch_label(monkeypatch):
    data = full_catalog_data()
    reference, candidate = models_with_mock_score(monkeypatch,
        lambda _ref, patch: 30. if patch["semantic_action"]["destination"] == 3 else 10.)
    evaluation = spi.evaluate_spi_on_dev(candidate, [data])
    row = evaluation["rows"][0]
    assert row["catalog"]["selected_action_id"] != data["rows"][1]["action"]["action_id"]
    assert row["label_support"] == "unsupported_unexecuted_full_catalog_winner"
    assert row["gain_bag_seconds"] is row["known_direction_harmed"] is row["on_time_delta"] is None
    assert evaluation["incomplete_development_J"]
    assert evaluation["complete_parent_balanced_paired_gain"] is evaluation["total_gain_bag_seconds"] is None
    assert spi.select_spi_on_dev([reference, candidate], [data])["reference_champion"]


def test_full_catalog_scoring_has_no_targets_and_matches_deployed_tie_order(monkeypatch):
    data = full_catalog_data()
    seen = []
    def score(ref, patch):
        assert all("target_return" not in r and "actual_execution" not in r for r in (ref, patch))
        seen.append(patch["action"]["action_id"])
        return 2.
    reference, candidate = models_with_mock_score(monkeypatch, score)
    evaluation = spi.evaluate_spi_on_dev(candidate, [data])
    assert len(seen) == data["rows"][0]["opportunity"]["K"] - 1
    assert evaluation["rows"][0]["catalog"]["selected_action_id"] == seen[0]
    assert evaluation["rows"][0]["choose_patch"]
    assert evaluation["complete_parent_balanced_paired_gain"] == 20.
    assert not spi.select_spi_on_dev([reference, candidate], [data])["reference_champion"]


def test_parent_balancing_uses_all_registered_roots_and_unknown_blocks_partial_mean(monkeypatch):
    _, candidate = models_with_mock_score(monkeypatch, lambda *_: 1.)
    datasets = [full_catalog_data(1201, 0, 30.), full_catalog_data(1201, 1, 10.),
                full_catalog_data(1202, 0, 2.)]
    evaluation = spi.evaluate_spi_on_dev(candidate, datasets)
    assert evaluation["total_gain_bag_seconds"] == 42.
    assert evaluation["complete_parent_balanced_paired_gain"] == 11.
    unavailable = deepcopy(datasets[-1])
    unavailable["pair"].update(status="not_comparable", reason="no_eligible_anchor")
    unavailable["rows"] = []
    datasets.append(unavailable)
    evaluation = spi.evaluate_spi_on_dev(candidate, datasets)
    assert evaluation["support_fraction"] == .75
    assert evaluation["known_partial_gain_bag_seconds"] == 42.
    assert evaluation["incomplete_development_J"] and evaluation["complete_parent_balanced_paired_gain"] is None


def test_out_of_support_high_score_cannot_win_development_catalog(monkeypatch):
    data = full_catalog_data()
    _, candidate = models_with_mock_score(monkeypatch, lambda *_: 1.)
    monkeypatch.setattr(spi, "prepare_supported_predictor", lambda *_a, **_kw:
        lambda _ref, patch: {"advantage": 99999. if patch["semantic_action"]["destination"] == 3 else 1.,
            "supported": patch["semantic_action"]["destination"] != 3})
    evaluation = spi.evaluate_spi_on_dev(candidate, [data])
    assert evaluation["rows"][0]["choose_patch"]
    assert evaluation["total_gain_bag_seconds"] == 20.
