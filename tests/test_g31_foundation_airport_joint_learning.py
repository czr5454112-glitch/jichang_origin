"""Synthetic numerical/evidence contract tests; no native jobs or real fits."""
import copy
import time

import numpy as np
import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_joint_dataset as data
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_learning as learn


def manifest(parent="p1", *, trajectory="t1", split="train", policy="joint-v1"):
    return dict(trajectory_id=trajectory, parent_uid=parent, lineage_family="lineage-"+parent,
                template_family="one-historical-day", split=split, environment_seed=101,
                behavior_seed=17, execution_source_id="source-1", native_domain_id="native-1",
                joint_policy_version=policy, physical_start=0., physical_end=10.,
                calendar_start_epoch_seconds=1000.)


def decision(identity="d1", owner="A", at=0., action="a-ref", *, stock=2., kind="transfer"):
    return dict(decision_id=identity, owner_id=owner, phase="post_priority", decision_time=at,
                current_version=str(at), public_observation_ref="obs-"+owner+str(at),
                legal_catalog_ref="catalog-"+owner+str(at), reference_candidate_id="a-ref",
                requested_action=dict(action_id=action, kind=kind, tray_id="tray-"+identity,
                                      source=0, destination=2),
                actual_submission=None, fallback_reason=None,
                selection_mechanism="randomized", selection_probability=.8,
                execution_probability=None, physical_failure=False,
                features_current=dict(stock=stock, travel=2.),
                features_forecast=dict(demand=3., remote_demand=None),
                forecast_id="forecast-at-"+str(at), mapping_id="map-v1", model_id="B1-producer", model_available_at=900.,
                action_support_key=kind)


def events(completion=8.):
    return [dict(business_bag_id="b1", arrival=0., completion=completion),
            dict(business_bag_id="b2", arrival=3., completion=None),
            dict(business_bag_id="future", arrival=100., completion=None)]


def trajectory(*, parent="p1", identity="t1", split="train", policy="joint-v1",
               process_status="completed", clock=10., completion=8., decisions=None, extra=None):
    m = manifest(parent, trajectory=identity, split=split, policy=policy)
    m.update(extra or {})
    if decisions is None:
        decisions = [decision(), decision("d2", "B", 2., kind="noop"),
                     decision("d3", "A", 4., action="a-alt", stock=None)]
    return data.build_trajectory(m, decisions, events(completion), physical_clock=clock,
                                 process_status=process_status, business_population_complete=True)


def register(trajectories, *, variant="C01", method="mc", paired_labels=(), epochs=3,
             policy="joint-v1", updates=0):
    return learn.make_registration(trajectories, information_variant=variant, seed=17,
        registration_id="synthetic-unit-contract", model_available_at_epoch_seconds=2000.,
        joint_policy_version=policy, method=method, epochs=epochs, td_updates=updates,
        hidden_width=4, paired_labels=paired_labels)


def test_same_owner_intervals_tail_and_unique_system_cost():
    result = trajectory()
    rows = {row["decision_id"]: row for row in result["rows"]}
    assert result["system_J"] == 15.
    assert result["population_count"] == 3  # Future offered business contributes zero.
    assert rows["d1"]["interval_cost"] == 5.
    assert rows["d1"]["actual_next_action"] == rows["d3"]["requested_action"]
    assert rows["d1"]["next_owner_id"] == "A"
    assert rows["d2"]["terminated"] and rows["d2"]["interval_cost"] == 13.
    assert rows["d3"]["terminated"] and rows["d3"]["interval_cost"] == 10.
    assert rows["d2"]["next_decision_time"] == rows["d3"]["next_decision_time"] == 10.
    assert sum(row["interval_cost"] for row in rows.values()) != result["system_J"]


def test_cost_curve_matches_independent_direct_integral_at_event_boundaries_and_inside_bins():
    rng = np.random.default_rng(19)
    actual = []
    for i in range(100):
        arrival = float(rng.integers(0, 100))
        completion = arrival+float(rng.integers(0, 20)) if i % 3 else None
        actual.append(dict(business_bag_id=i, arrival=arrival, completion=completion))
    curve = data.CostIntegral(actual)
    for start in (0., 1., 12.5, 25., 79.2):
        for end in (79.3, 100., 120.):
            assert curve.between(start, end) == pytest.approx(data.interval_cost(actual, start, end))


def test_rejections_no_ack_and_failed_physical_transport_remain_training_outcomes():
    row = decision()
    row.update(reply_or_rejection=dict(status="rejected", reason="receiving_lease"),
               physical_failure=True, request_id="request-1", ack=None, first_leg=None)
    result = trajectory(decisions=[row])
    assert len(result["rows"]) == 1
    assert result["rows"][0]["closed_mc_cost"] == 15.
    assert result["rows"][0]["physical_failure"]
    assert result["success_filter_applied"] is False
    rows, _, _, _ = learn.training_rows([result], register([result]))
    assert len(rows) == 1


@pytest.mark.parametrize("status,clock", [("timeout", 9.), ("crashed", 10.), ("missing", 10.)])
def test_unclosed_executions_preserve_rows_but_never_zero_terminal(status, clock):
    result = trajectory(process_status=status, clock=clock)
    assert result["system_J"] is None
    assert len(result["rows"]) == 3
    assert all(row["interval_cost"] is None and row["closed_mc_cost"] is None
               and row["truncated"] and not row["terminated"] for row in result["rows"])
    with pytest.raises(ValueError, match="no_closed_actual_training_rows"):
        learn.training_rows([result], register([result]))


def test_no_duplicate_owner_tick_or_cross_policy_splicing_or_fake_probability():
    rows = [decision(), decision("duplicate", "A", 0.)]
    with pytest.raises(ValueError, match="one_decision_per_owner_tick"):
        trajectory(decisions=rows)
    row = decision()
    row["joint_policy_version"] = "another-policy"
    with pytest.raises(ValueError, match="joint_policy_frozen"):
        trajectory(decisions=[row])
    row = decision()
    row["selection_mechanism"] = "deterministic"
    with pytest.raises(ValueError, match="deterministic_is_not"):
        trajectory(decisions=[row])
    row["selection_probability"] = None
    assert trajectory(decisions=[row])["rows"][0]["selection_probability"] is None


def test_parent_split_and_train_only_normalization():
    train, dev = trajectory(), trajectory(identity="d", split="dev")
    with pytest.raises(ValueError, match="parent_lineage_split_collision"):
        data.validate_split_lineage([train, dev])
    with pytest.raises(ValueError, match="only_train_data"):
        learn.training_rows([dev], register([dev]))
    changed = trajectory(parent="other", identity="other", policy="different")
    with pytest.raises(ValueError, match="single_frozen_continuation"):
        learn.training_rows([train, changed], register([train, changed]))


def test_missing_stock_differs_from_structural_zero_and_C01_ignores_forecast():
    unknown, zero = decision(stock=None), decision(stock=0.)
    normalizer = learn.fit_normalizer([unknown, zero], "C01")
    before = learn.encode_features(zero, "C01", normalizer)
    zero["features_forecast"] = {"future_secret": 9999.}
    assert np.array_equal(before, learn.encode_features(zero, "C01", normalizer))
    assert not np.array_equal(before, learn.encode_features(unknown, "C01", normalizer))
    assert not any("forecast" in key for key in normalizer["names"])


def test_C11_requires_forecast_binding_and_model_after_training_closure():
    result = trajectory()
    registration = register([result], variant="C11")
    assert len(learn.training_rows([result], registration)[0]) == 3
    result["rows"][0]["model_available_at"] = 2001.
    with pytest.raises(ValueError, match="C11_forecast_available"):
        learn.training_rows([result], registration)
    result = trajectory()
    registration["model_available_at_epoch_seconds"] = 1009.
    with pytest.raises(ValueError, match="training_labels_closed"):
        learn.training_rows([result], registration)


def test_sarsa_uses_actual_successor_cost_and_terminal_tail_without_bootstrap():
    rows = trajectory()["rows"]
    targets = learn.sarsa_targets(rows, [20., 999999., 999999.])
    assert list(targets) == [25., 13., 10.]
    altered = copy.deepcopy(rows)
    altered[0]["next_owner_id"] = "B"
    with pytest.raises(ValueError, match="actual_same_owner_policy_successor"):
        learn.sarsa_targets(altered, [20., 1., 1.])
    altered = copy.deepcopy(rows)
    altered[0]["next_joint_policy_version"] = "another"
    with pytest.raises(ValueError, match="actual_same_owner_policy_successor"):
        learn.sarsa_targets(altered, [20., 1., 1.])


def test_real_cross_tray_pair_requires_bound_prefix_and_closed_costs():
    pairing = dict(root_id="root", physical_control_prefix_sha256="prefix",
                   delivered_messages_sha256="messages", exogenous_input_sha256="rng",
                   continuation_policy_version="joint-v1")
    ref_row, alt_row = decision(), decision("alt", action="a-alt")
    alt_row["requested_action"].update(source=1, tray_id="different-actual-tray")
    reference = trajectory(identity="ref", decisions=[ref_row], extra=dict(pairing=pairing))
    alternative = trajectory(identity="alt", decisions=[alt_row], completion=7., extra=dict(pairing=pairing))
    pair = data.make_paired_label(reference, alternative, reference_decision_id="d1",
                                  alternative_decision_id="alt", pairing=pairing)
    assert pair["delta_J"] == pair["delta_continuation_cost"] == -1.
    alternative["manifest"]["pairing"]["exogenous_input_sha256"] = "other"
    with pytest.raises(ValueError, match="actual_branch_pair_binding"):
        data.make_paired_label(reference, alternative, reference_decision_id="d1",
                               alternative_decision_id="alt", pairing=pairing)


def test_small_numerical_fit_has_finite_cost_and_explicit_actual_TD_targets():
    trajectories = [trajectory(), trajectory(parent="p2", identity="t2", completion=7.)]
    registration = register(trajectories, method="sarsa", epochs=6, updates=2)
    model = learn.fit_model(trajectories, registration, deadline=time.monotonic()+20.)
    assert len(model["target_updates"]) == 2
    assert model["training_method"] == "actual_same_owner_SARSA"
    assert model["normalizer"]["fitted_split"] == "train"
    assert model["policy_iteration_established"] is False
    assert model["optimal_Q_established"] is False
    score = learn.predict_cost(model, decision(), calendar_time=2001.)
    assert np.isfinite(score["cost"]) and score["supported"]
    far = decision(stock=100000.)
    assert not learn.predict_cost(model, far, calendar_time=2001.)["supported"]
    with pytest.raises(ValueError, match="current_model_available"):
        learn.predict_cost(model, decision(), calendar_time=1999.)


def test_supported_selector_compares_actual_reference_with_other_tray():
    scores = {"ref": dict(cost=100., supported=True), "alt": dict(cost=90., supported=True),
              "unsupported": dict(cost=-999., supported=False)}
    candidates = {key: dict(action_support_key=key) for key in scores}
    model = dict(registration=dict(gain_threshold=0.))
    predict = lambda row, calendar_time: scores[row["action_support_key"]]
    result = learn.select_supported_action(model, candidates, "ref", calendar_time=1., predictor=predict)
    assert result["action_id"] == "alt" and result["estimated_gain"] == 10.
    scores["ref"]["supported"] = False
    assert learn.select_supported_action(model, candidates, "ref", calendar_time=1.,
                                          predictor=predict)["action_id"] == "ref"


def test_iteration_claim_requires_actual_deployed_model_recollection():
    initial_data = [trajectory()]
    initial = learn.fit_model(initial_data, register(initial_data, epochs=2))
    recollected = [trajectory(policy="joint-v2", extra=dict(deployed_model_id=initial["model_id"]))]
    final = learn.fit_model(recollected, register(recollected, method="sarsa", policy="joint-v2", epochs=3, updates=1))
    evidence = learn.policy_iteration_evidence(initial, recollected, final)
    assert evidence["nontrivial_policy_iteration"] and evidence["actual_nonreference_proposals"] == 1
    assert evidence["multistep_policy_evaluation"] and not evidence["held_out_control_benefit_established"]
    recollected[0]["manifest"]["deployed_model_id"] = "not-the-model"
    with pytest.raises(ValueError, match="actual_recollection_model_binding"):
        learn.policy_iteration_evidence(initial, recollected, final)


def test_large_cost_pair_accepts_ULP_roundoff_but_rejects_real_prefix_mismatch():
    pairing = dict(root_id="root", physical_control_prefix_sha256="prefix", delivered_messages_sha256="messages",
                   exogenous_input_sha256="rng", continuation_policy_version="joint-v1")
    reference = trajectory(identity="ref", decisions=[decision()], extra=dict(pairing=pairing))
    alternative = trajectory(identity="alt", decisions=[decision("alt", action="alt")], extra=dict(pairing=pairing))
    start, root, end_ref, end_alt = 56124845.79660357, 151906671.6490603, 974225993.1685759, 974223187.3249333
    reference["system_J"], alternative["system_J"] = end_ref-start, end_alt-start
    reference["rows"][0]["closed_mc_cost"], alternative["rows"][0]["closed_mc_cost"] = end_ref-root, end_alt-root
    pair = data.make_paired_label(reference, alternative, reference_decision_id="d1", alternative_decision_id="alt", pairing=pairing)
    assert 1e-8 < abs(pair["equal_prefix_cost_residual"]) <= pair["equal_prefix_cost_roundoff_tolerance"]
    alternative["rows"][0]["closed_mc_cost"] += 1.
    with pytest.raises(ValueError, match="equal_prefix_cost_required"):
        data.make_paired_label(reference, alternative, reference_decision_id="d1", alternative_decision_id="alt", pairing=pairing)
