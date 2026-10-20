"""Public feature, data and finite numerical contracts; no model fitting."""
import copy
import time

import numpy as np
import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_pair_ranker as ranker
from test_g31_foundation_airport_learning_public import observation, forecast


def dataset(seed=701, advantage=20., *, split="train"):
    obs = observation()
    for node in obs["node_contracts"]:
        node["capacity"] = 4
    opportunity = {"public_state_digest": ranker.digest(obs), "owner_id": "A", "observed_at": 10.,
        "optional_intents": [], "mandatory_intents": []}
    parent = {"parent_seed": seed, "split": split, "parent_group": "parent-"+str(seed),
        "calendar_start_epoch_seconds": 1700000000. + (seed-700)*86400.}
    pair_id = "fixture-" + str(seed)
    common = {"parent": parent, "pair_id": pair_id, "observation": obs,
        "opportunity": opportunity, "unexecuted_candidate_label": False,
        "paired_advantage_bag_seconds": advantage, "actual_execution": {"attempts": []}}
    reference = dict(copy.deepcopy(common), branch="a_ref", target_return=-1000.,
        semantic_action={"kind": "hold_optional", "tray_id": "E", "source": 0,
            "destination": None, "earliest_departure": None, "transfer_scope": None})
    patch = dict(copy.deepcopy(common), branch="a_patch", target_return=-1000.+advantage,
        semantic_action={"kind": "transfer", "tray_id": "E", "source": 0,
            "destination": 2, "earliest_departure": 12., "transfer_scope": "cross_zone_transfer"})
    return {"pair": {"parent": parent, "pair_id": pair_id, "status": "closed_actual_pair",
        "advantage_bag_seconds": advantage, "action_difference": True,
        "reference_cost": {"label_end": 1810., "physical_population": 1},
        "patched_cost": {"label_end": 1810., "physical_population": 1},
        "per_job_comparison_counts": {"equal": 1}},
        "rows": [reference, patch]}


def forecast_evidence(row):
    start = row["parent"]["calendar_start_epoch_seconds"]
    fc = forecast()
    fc["remaining_support_until"] = 1810.
    manifest = {"schema": "g31.foundation.airport_absolute_forecast_binding.v1",
        "model_id": "actual-source-model", "time_basis": "absolute_epoch_seconds",
        "source_calendar_start_epoch_seconds": start-86400.,
        "original_training_labels_closed_at_sim_time": 43200.,
        "original_model_available_at_sim_time": 57600.,
        "training_labels_closed_at_epoch_seconds": start-43200.,
        "model_available_at_epoch_seconds": start-28800.,
        "original_checkpoint_sha256": "1"*64, "original_training_receipt_sha256": "2"*64,
        "target_plan_template_sha256": "3"*64}
    receipt = {"schema": "g31.foundation.airport_controller_plan_receipt.v1",
        "receipt_kind": "actual_controller_startup_preload", "owner_id": row["observation"]["owner_id"],
        "parent_group": row["parent"]["parent_group"], "model_id": manifest["model_id"],
        "calendar_start_epoch_seconds": start, "target_plan_template_sha256": "3"*64,
        "received_at_physical_seconds": 0., "received_at_epoch_seconds": start,
        "native_message_receipt_claimed": False}
    receipt["receipt_sha256"] = ranker.digest(receipt)
    return {"schema": ranker.FORECAST_SCHEMA, "calendar_start_epoch_seconds": start,
        "forecast_provenance": "actual_callback_received", "actual_callback_consumption": True,
        "plan_receipt": receipt,
        "observed_at_epoch_seconds": start+10., "training_labels_closed_at_epoch_seconds": start-43200.,
        "model_available_at_epoch_seconds": start-28800., "plan_received_at_epoch_seconds": start,
        "public_state_sha256": ranker.digest(row["observation"]), "model_id": manifest["model_id"],
        "producer_manifest": manifest, "provenance_sha256": ranker.digest(manifest),
        "forecast": fc, "forecast_sha256": ranker.digest(fc)}


def model_for(rows):
    features = ranker.action_features(rows[0], information_variant="C01")
    names = sorted(features)
    weights = [0.]*len(names)
    weights[names.index("transfer")] = 1.
    model = {"schema": ranker.SCHEMA, "feature_schema": ranker.FEATURE_SCHEMA,
        "information_variant": "C01", "seed": 17, "model_available_at_epoch_seconds": 1700000000.,
        "feature_names": names, "parameters": {"center": [0.]*len(names), "scale": [1.]*len(names),
            "target_scale": 1., "layers": [{"weight": [weights], "bias": [0.]}]}}
    model["model_id"] = ranker.digest(model)
    return model


def test_current_only_features_ignore_forecasts_targets_and_private_parent_ids():
    row = dataset()["rows"][1]
    before = ranker.action_features(row, information_variant="C01")
    row["forecast_evidence"] = {"secret_future_demand": 999999.}
    row["target_return"] = 9876543.
    row["paired_advantage_bag_seconds"] = -987654.
    row["parent"]["parent_group"] = "another"
    assert ranker.action_features(row, information_variant="C01") == before
    assert not any("forecast" in name or "node_id" in name for name in before)
    assert before["destination_observed_waiting"] == 5.


def test_C11_requires_actual_calendar_bound_forecast_and_preserves_missing():
    row = dataset()["rows"][1]
    with pytest.raises(ValueError, match="C11_requires_actual"):
        ranker.action_features(row, information_variant="C11")
    row["forecast_evidence"] = forecast_evidence(row)
    features = ranker.action_features(row, information_variant="C11")
    assert features["destination_forecast_300"] == 5.
    assert features["source_forecast_300_missing"] == 1.


def test_C11_offline_plan_reconstruction_is_not_actual_receipt():
    row = dataset()["rows"][1]
    row["forecast_evidence"] = forecast_evidence(row)
    row["forecast_evidence"].update(forecast_provenance="offline_reconstruction_from_predeclared_static_schedule",
        actual_callback_consumption=False, plan_received_at_epoch_seconds=None)
    with pytest.raises(ValueError, match="actual_recorded_plan_receipt"):
        ranker.action_features(row, information_variant="C11")


def test_C11_owner_preload_receipt_cannot_be_reassigned():
    row = dataset()["rows"][1]
    row["forecast_evidence"] = forecast_evidence(row)
    receipt = row["forecast_evidence"]["plan_receipt"]
    receipt["owner_id"] = "another"
    receipt["receipt_sha256"] = ranker.digest({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    with pytest.raises(ValueError, match="owner_startup_plan_receipt"):
        ranker.action_features(row, information_variant="C11")


@pytest.mark.parametrize("mutation,reason", [
    ("future", "availability_and_plan"),
    ("stale", "absolute_current"),
    ("private_current", "absolute_current"),
    ("reset_clock", "original_availability"),
    ("forecast_bytes", "static_plan_forecast"),
])
def test_C11_invalid_forecast_binding_fails_closed(mutation, reason):
    row = dataset()["rows"][1]
    row["forecast_evidence"] = forecast_evidence(row)
    evidence = row["forecast_evidence"]
    if mutation == "future":
        evidence["model_available_at_epoch_seconds"] = evidence["observed_at_epoch_seconds"]+1
    elif mutation == "stale":
        evidence["observed_at_epoch_seconds"] -= 1
    elif mutation == "private_current":
        evidence["public_state_sha256"] = "other"
    elif mutation == "reset_clock":
        evidence["producer_manifest"]["original_model_available_at_sim_time"] = 0.
        evidence["provenance_sha256"] = ranker.digest(evidence["producer_manifest"])
    else:
        evidence["forecast"]["new_demand_mean_by_region"]["airport_node_2"][0] += 1
    with pytest.raises(ValueError, match=reason):
        ranker.action_features(row, information_variant="C11")


def test_training_sufficiency_rejects_zero_single_parent_and_one_direction():
    zeros = ranker.sufficiency([dataset(701, 0.), dataset(702, 0.)], information_variant="C01")
    assert not zeros["eligible_to_fit"] and zeros["zero_advantages"] == 2
    direction = ranker.sufficiency([dataset(701, 10.), dataset(702, 20.)], information_variant="C01")
    assert not direction["eligible_to_fit"]
    valid = ranker.sufficiency([dataset(701, 10.), dataset(702, -20.)], information_variant="C01")
    assert valid["eligible_to_fit"] and valid["actual_action_differences"] == 2


def test_resource_descendants_cannot_inflate_independent_parent_count():
    first, second = dataset(701, 10.), dataset(701, -20.)
    second["pair"]["pair_id"] += "-18trays"
    second["pair"]["parent"]["fleet_count"] = 18
    for row in second["rows"]:
        row["pair_id"] = second["pair"]["pair_id"]
        row["parent"]["fleet_count"] = 18
    gate = ranker.sufficiency([first, second], information_variant="C01")
    assert gate["train_parent_groups"] == 1 and not gate["eligible_to_fit"]


def test_invalid_parent_relabel_and_target_rewrite_rejected():
    data = dataset(901, 20., split="test")
    with pytest.raises(ValueError, match="split_no_leakage"):
        ranker.prepare_pairs([data], information_variant="C01", split="train")
    data = dataset()
    data["rows"][1]["target_return"] += 1
    with pytest.raises(ValueError, match="realized_paired_target"):
        ranker.prepare_pairs([data], information_variant="C01", split="train")


@pytest.mark.parametrize("mutation", ["absent", "incomplete", "unknown_category", "zero_count"])
def test_missing_or_incomplete_harm_denominators_fail_closed(mutation):
    data = dataset()
    if mutation == "absent":
        del data["pair"]["per_job_comparison_counts"]
    elif mutation == "incomplete":
        data["pair"]["reference_cost"]["physical_population"] = 2
    elif mutation == "unknown_category":
        data["pair"]["per_job_comparison_counts"] = {"probably_fine": 1}
    else:
        data["pair"]["per_job_comparison_counts"] = {"harmed": 0, "equal": 1}
    with pytest.raises(ValueError, match="per_job_comparison"):
        ranker.prepare_pairs([data], information_variant="C01", split="train")


def test_censored_pairs_remain_in_denominator_with_no_invented_label():
    data = dataset()
    data["pair"].update(status="not_comparable", reason="timeout", advantage_bag_seconds=None)
    data["rows"] = []
    pairs, unavailable = ranker.prepare_pairs([data], information_variant="C01", split="train")
    assert pairs == [] and unavailable[0]["reason"] == "timeout"


def test_primary_fit_requires_explicit_registration_before_any_training():
    with pytest.raises(ValueError, match="preregistered_fit"):
        ranker.fit_ranker([dataset(701, 10.), dataset(702, -20.)],
            information_variant="C01", seed=17, architecture="linear", registration={},
            deadline=time.monotonic()+1)


def test_frozen_numerical_prediction_dev_regret_and_test_rejection():
    data = dataset(801, -20., split="dev")
    model = model_for(data["rows"])
    assert ranker.predict_advantage(model, *data["rows"]) == 1.
    result = ranker.evaluate_on_dev(model, [data])
    assert result["mean_paired_regret"] == 20.
    with pytest.raises(ValueError, match="split_no_leakage"):
        ranker.select_on_dev([model], [dataset(901, 10., split="test")])
    model["parameters"]["target_scale"] = 2.
    with pytest.raises(ValueError, match="immutable_model"):
        ranker.predict_advantage(model, *data["rows"])


def test_prepared_predictor_detaches_weights_validates_each_current_once_and_reads_no_files(monkeypatch):
    data = dataset(801, -20., split="dev")
    model = model_for(data["rows"])
    model.pop("model_id")
    model["registration"] = {"feature_source_sha256": ranker.source_pins()}
    model["model_id"] = ranker.digest(model)
    predict = ranker.prepare_predictor(model)
    model["parameters"]["layers"][0]["weight"][0][:] = [99.]*len(model["feature_names"])
    def forbidden():
        raise AssertionError("Callback must not reread static source files")
    monkeypatch.setattr(ranker, "source_pins", forbidden)
    calls = []
    original = ranker.public.validate_public
    def counted(observation):
        calls.append(observation["now"])
        return original(observation)
    monkeypatch.setattr(ranker.public, "validate_public", counted)
    assert predict(*data["rows"]) == 1.
    assert calls == [10.]
    data["rows"][1]["opportunity"]["public_state_digest"] = "stale"
    with pytest.raises(ValueError, match="opportunity_current_binding"):
        predict(*data["rows"])
    assert calls == [10., 10.]


def test_prepared_predictor_does_not_cache_parent_availability():
    data = dataset(801, 20., split="dev")
    model = model_for(data["rows"])
    predict = ranker.prepare_predictor(model)
    assert predict(*data["rows"]) == 1.
    for row in data["rows"]:
        row["parent"]["calendar_start_epoch_seconds"] = 1.
    with pytest.raises(ValueError, match="current_model_availability"):
        predict(*data["rows"])


def test_C11_frozen_model_rejects_current_forecast_mapping_change():
    data = dataset(801, 20., split="dev")
    for row in data["rows"]:
        row["forecast_evidence"] = forecast_evidence(row)
    model = model_for(data["rows"])
    model.pop("model_id")
    names = sorted(ranker.action_features(data["rows"][0], information_variant="C11"))
    weights = [0.]*len(names)
    weights[names.index("transfer")] = 1.
    model.update(information_variant="C11", feature_names=names,
        forecast_contract=ranker._forecast_contract(data["rows"][0]),
        parameters={"center": [0.]*len(names), "scale": [1.]*len(names),
            "target_scale": 1., "layers": [{"weight": [weights], "bias": [0.]}]})
    model["model_id"] = ranker.digest(model)
    assert ranker.predict_advantage(model, *data["rows"]) == 1.
    evidence = data["rows"][1]["forecast_evidence"]
    evidence["forecast"]["mapping_version"] = "new"
    evidence["forecast_sha256"] = ranker.digest(evidence["forecast"])
    with pytest.raises(ValueError, match="current_frozen_forecast"):
        ranker.predict_advantage(model, *data["rows"])


def test_pair_difference_backprop_matches_finite_difference_without_fitting():
    layers = [{"weight": np.array([[.2, -.3], [.1, .4]]), "bias": np.array([.2, .1])},
        {"weight": np.array([[.5, -.2]]), "bias": np.array([.1])}]
    x = np.array([[.1, .8], [.9, -.2]])
    derivative = np.array([[-1.], [1.]])
    gradients = ranker._backward(ranker._forward(x, layers), derivative, layers)
    epsilon = 1e-6
    for index, layer in enumerate(layers):
        for key, array in layer.items():
            for coordinate in np.ndindex(array.shape):
                plus, minus = copy.deepcopy(layers), copy.deepcopy(layers)
                plus[index][key][coordinate] += epsilon
                minus[index][key][coordinate] -= epsilon
                a = ranker._forward(x, plus)[-1]
                b = ranker._forward(x, minus)[-1]
                numerical = ((a[1, 0]-a[0, 0])-(b[1, 0]-b[0, 0]))/(2*epsilon)
                assert gradients[index][key][coordinate] == pytest.approx(numerical, abs=1e-8)
