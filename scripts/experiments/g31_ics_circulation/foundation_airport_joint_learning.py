"""Small cost-Q models with observed-next-action SARSA and conservative support.

The fitting entry point is explicit and performs no native simulation. C01 and
C11 are independently initialized models, never a masked copy of one another.
Support is an empirical neighbourhood rule, not an improvement guarantee.
"""
from __future__ import annotations

import copy
import hashlib
import math
from pathlib import Path
import time

import numpy as np

from . import foundation_airport_joint_dataset as dataset

SCHEMA = "g31.foundation.airport_joint_cost_q.v1"
REGISTRATION_SCHEMA = "g31.foundation.airport_joint_fit_registration.v1"
SEEDS = (17, 29, 43)
VARIANTS = ("C01", "C11")
require, number, digest = dataset.require, dataset.number, dataset.digest


def feature_values(row, information_variant):
    """Only explicitly partitioned actor features enter the model; None has a mask."""
    require(information_variant in VARIANTS, "joint_information_variant")
    current = row.get("features_current")
    require(type(current) is dict and current, "joint_current_features")
    values = {"current:"+key: value for key, value in current.items()}
    if information_variant == "C11":
        forecast = row.get("features_forecast")
        require(type(forecast) is dict and forecast, "C11_actual_forecast_features_required")
        values.update({"forecast:"+key: value for key, value in forecast.items()})
    result = {}
    for key in sorted(values):
        value = values[key]
        require(type(key) is str and key, "named_feature")
        result[key] = None if value is None else number(value)
    return result


def fit_normalizer(rows, information_variant):
    """Caller supplies training rows only; unknown is imputed at training mean."""
    values = [feature_values(row, information_variant) for row in rows]
    require(bool(values), "normalizer_training_rows")
    names = sorted(values[0])
    require(all(sorted(row) == names for row in values), "frozen_feature_schema")
    center, scale = [], []
    for name in names:
        observed = [row[name] for row in values if row[name] is not None]
        center.append(float(np.mean(observed)) if observed else 0.)
        scale.append(max(float(np.std(observed)), 1e-9) if observed else 1.)
        if scale[-1] < 1e-8:
            scale[-1] = 1.
    return dict(names=names, center=center, scale=scale,
                missing_representation="mean_imputation_plus_separate_missing_mask",
                fitted_split="train")


def encode_features(row, information_variant, normalizer):
    values = feature_values(row, information_variant)
    require(sorted(values) == normalizer["names"], "runtime_feature_schema")
    result = []
    for name, center, scale in zip(normalizer["names"], normalizer["center"],
                                   normalizer["scale"], strict=True):
        value = values[name]
        result.append(0. if value is None else (value-center)/scale)
    result.extend(float(values[name] is None) for name in normalizer["names"])
    return np.asarray(result, dtype=float)


def source_pins():
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (Path(__file__), Path(dataset.__file__),
                         Path(__file__).with_name("foundation_airport_joint_rules.py"),
                         Path(__file__).with_name("foundation_airport_inventory_projection.py"))}


def make_registration(trajectories, *, information_variant, seed, registration_id,
                      model_available_at_epoch_seconds, joint_policy_version,
                      method="mc", epochs=100, td_updates=0, hidden_width=64,
                      paired_labels=(), paired_weight=.25, gain_threshold=0.,
                      support_min_parents=2, support_max_rms_distance=2.):
    require(information_variant in VARIANTS and seed in SEEDS, "joint_registered_variant_seed")
    require(method in ("mc", "sarsa") and 1 <= epochs <= 100 and type(epochs) is int,
            "finite_fit_epoch_budget")
    require(type(td_updates) is int and 0 <= td_updates <= 5
            and ((method == "mc" and td_updates == 0) or (method == "sarsa" and td_updates > 0)),
            "actual_sarsa_target_updates")
    require(type(hidden_width) is int and 1 <= hidden_width <= 64, "two_layers_at_most_64")
    require(type(support_min_parents) is int and support_min_parents >= 1
            and number(support_max_rms_distance) > 0, "registered_empirical_support_rule")
    require(type(joint_policy_version) is str and joint_policy_version, "registered_joint_policy")
    require(type(registration_id) is str and registration_id, "fit_registration_identity")
    require(number(paired_weight) >= 0 and number(gain_threshold) >= 0, "nonnegative_selection_and_loss_weights")
    return dict(schema=REGISTRATION_SCHEMA, registration_id=registration_id,
                information_variant=information_variant, seed=seed, method=method,
                epochs=epochs, td_updates=td_updates, hidden_width=hidden_width,
                joint_policy_version=joint_policy_version, gamma=1.,
                model_available_at_epoch_seconds=number(model_available_at_epoch_seconds),
                training_dataset_sha256=digest(trajectories), paired_labels_sha256=digest(paired_labels),
                paired_weight=paired_weight, gain_threshold=gain_threshold,
                support_min_parents=support_min_parents,
                support_max_rms_distance=support_max_rms_distance,
                support_max_prototypes_per_key=64, source_sha256=source_pins(),
                test_opened=False, native_jobs_requested=0, fit_calls_requested=1,
                initialization="independent_seeded_from_scratch")


def _validate_forecast_record(row):
    metadata = row.get("metadata") or {}
    forecast_id = row.get("forecast_id") or metadata.get("forecast_id")
    mapping_id = row.get("mapping_id") or metadata.get("mapping_id")
    producer_id = row.get("model_id") or metadata.get("model_id")
    available = row.get("model_available_at")
    if available is None:
        available = metadata.get("model_available_at")
    require(type(forecast_id) is str and forecast_id and type(mapping_id) is str and mapping_id
            and type(producer_id) is str and producer_id, "C11_forecast_producer_and_mapping_identity")
    require(available is not None and 0 < number(available) <= number(row["calendar_time"]),
            "C11_forecast_available_before_decision")
    return dict(forecast_id=forecast_id, mapping_id=mapping_id, model_id=producer_id,
                model_available_at=available)


def training_rows(trajectories, registration):
    dataset.validate_split_lineage(trajectories)
    rows, omitted, closed_epochs, forecast_contracts = [], [], [], []
    version = registration["joint_policy_version"]
    for trajectory in trajectories:
        require(trajectory.get("schema") == dataset.SCHEMA, "joint_trajectory_schema")
        manifest = dataset.validate_manifest(trajectory["manifest"])
        require(manifest["split"] == "train", "only_train_data_may_fit_or_normalize")
        require(manifest["joint_policy_version"] == version, "single_frozen_continuation_policy_per_fit")
        if trajectory["scientific_status"] != "closed_finite_horizon":
            omitted.append(dict(trajectory_id=manifest["trajectory_id"], reason="censored_unknown"))
            continue
        closed_epochs.append(manifest["calendar_start_epoch_seconds"]+manifest["physical_end"])
        for raw in trajectory["rows"]:
            require(not raw["truncated"] and raw["target_status"] == "observed_closed"
                    and raw["closed_mc_cost"] is not None and raw["interval_cost"] is not None,
                    "closed_actual_cost_targets")
            require(raw["joint_policy_version"] == version and not raw["unexecuted_candidate_label"],
                    "actual_policy_actions_only")
            if raw["terminated"]:
                require(raw["next_decision_id"] is None and raw["actual_next_action"] is None
                        and raw["next_decision_time"] == manifest["physical_end"], "terminal_tail_to_common_end")
            else:
                require(raw["next_decision_id"] is not None and raw["actual_next_action"] is not None
                        and raw["next_owner_id"] == raw["owner_id"]
                        and raw["next_joint_policy_version"] == version
                        and raw["next_decision_time"] > raw["decision_time"], "actual_same_owner_sarsa_successor")
            row = copy.deepcopy(raw)
            row["parent_uid"] = manifest["parent_uid"]
            row["trajectory_id"] = manifest["trajectory_id"]
            if registration["information_variant"] == "C11":
                forecast_contracts.append(_validate_forecast_record(row))
            rows.append(row)
    require(rows, "no_closed_actual_training_rows")
    require(max(closed_epochs) <= registration["model_available_at_epoch_seconds"],
            "training_labels_closed_before_model_availability")
    # Forecast ID may include its origin; producer/mapping availability is frozen.
    if forecast_contracts:
        require(len({(x["mapping_id"], x["model_id"], x["model_available_at"]) for x in forecast_contracts}) == 1,
                "one_frozen_forecast_mapping_and_availability")
    return rows, omitted, max(closed_epochs), forecast_contracts


def _forward(x, layers):
    activations = [x]
    for index, layer in enumerate(layers):
        x = x @ layer["weight"].T + layer["bias"]
        if index < len(layers)-1:
            x = np.tanh(x)
        activations.append(x)
    return activations


def _backward(activations, derivative, layers):
    gradients = []
    for index in range(len(layers)-1, -1, -1):
        if index < len(layers)-1:
            derivative = derivative*(1.-activations[index+1]**2)
        gradients.append(dict(weight=derivative.T @ activations[index], bias=derivative.sum(axis=0)))
        derivative = derivative @ layers[index]["weight"]
    return list(reversed(gradients))


def sarsa_targets(rows, next_costs):
    """No minimum over unexecuted legal candidates and no bootstrap at the end."""
    require(len(rows) == len(next_costs), "sarsa_target_shape")
    result = []
    for row, next_cost in zip(rows, next_costs, strict=True):
        require(not row["truncated"] and row["interval_cost"] is not None, "no_censored_sarsa_target")
        if row["terminated"]:
            require(row["actual_next_action"] is None, "terminal_has_no_next_action")
            result.append(number(row["interval_cost"]))
        else:
            require(row["actual_next_action"] is not None and row["next_owner_id"] == row["owner_id"]
                    and row["next_joint_policy_version"] == row["joint_policy_version"],
                    "actual_same_owner_policy_successor")
            next_cost = next_cost.item() if isinstance(next_cost, np.floating) else next_cost
            result.append(number(row["interval_cost"])+number(next_cost))
    return np.asarray(result)


def fit_model(trajectories, registration, *, paired_labels=(), deadline=None):
    """One registered fit, <=100 epochs total including <=5 frozen TD updates."""
    require(registration.get("schema") == REGISTRATION_SCHEMA
            and registration["source_sha256"] == source_pins()
            and registration["training_dataset_sha256"] == digest(trajectories)
            and registration["paired_labels_sha256"] == digest(paired_labels)
            and registration["test_opened"] is False, "frozen_fit_registration")
    require(1 <= registration["epochs"] <= 100 and 0 <= registration["td_updates"] <= 5,
            "finite_fit_budget")
    require(registration["seed"] in SEEDS and registration["information_variant"] in VARIANTS
            and 1 <= registration["hidden_width"] <= 64
            and registration["gamma"] == 1.
            and ((registration["method"] == "mc" and registration["td_updates"] == 0)
                 or (registration["method"] == "sarsa" and registration["td_updates"] > 0)),
            "registered_model_and_learning_contract")
    rows, omitted, labels_closed, contracts = training_rows(trajectories, registration)
    variant = registration["information_variant"]
    normalizer = fit_normalizer(rows, variant)
    x = np.stack([encode_features(row, variant, normalizer) for row in rows])
    next_x = x.copy()
    for i, row in enumerate(rows):
        if not row["terminated"]:
            next_x[i] = encode_features(dict(features_current=row["next_features_current"],
                features_forecast=row["next_features_forecast"]), variant, normalizer)
    mc = np.asarray([number(row["closed_mc_cost"]) for row in rows])
    center = float(np.mean(mc))
    scale = max(float(np.std(mc)), 1.)
    paired_x, paired_y = [], []
    dataset_ids = {trajectory["dataset_id"] for trajectory in trajectories}
    for pair in paired_labels:
        require(pair["schema"] == dataset.PAIR_SCHEMA and pair["split"] == "train"
                and pair["continuation_policy_version"] == registration["joint_policy_version"]
                and pair["reference_dataset_id"] in dataset_ids
                and pair["alternative_dataset_id"] in dataset_ids, "measured_training_pair_same_continuation")
        for prefix in ("reference", "alternative"):
            paired_x.append(encode_features(dict(features_current=pair[prefix+"_features_current"],
                features_forecast=pair[prefix+"_features_forecast"]), variant, normalizer))
        paired_y.append(number(pair["delta_J"]))
    pair_array = np.stack(paired_x) if paired_x else None
    pair_y = np.asarray(paired_y)
    pair_scale = max(float(np.std(pair_y)), float(np.mean(np.abs(pair_y))), 1.) if len(pair_y) else 1.
    rng = np.random.default_rng(registration["seed"])
    width = registration["hidden_width"]
    widths = (x.shape[1], width, width, 1)
    layers = [dict(weight=rng.normal(0., 1./math.sqrt(a), size=(b, a)), bias=np.zeros(b))
              for a, b in zip(widths[:-1], widths[1:], strict=True)]
    first = [{key: np.zeros_like(value) for key, value in layer.items()} for layer in layers]
    second = copy.deepcopy(first)
    target = mc.copy()
    curve, updates, started = [], [], time.perf_counter()
    total_epochs = registration["epochs"]
    # MC initialization receives the first block; each later block freezes targets.
    boundaries = {max(1, int(total_epochs*j/(registration["td_updates"]+1)))
                  for j in range(1, registration["td_updates"]+1)}
    require(len(boundaries) == registration["td_updates"]
            and max(boundaries, default=0) < total_epochs, "enough_epochs_for_registered_target_updates")
    for epoch in range(total_epochs):
        require(deadline is None or time.monotonic() <= deadline, "training_wall_budget")
        if epoch in boundaries:
            next_costs = _forward(next_x, layers)[-1][:, 0]*scale+center
            target = sarsa_targets(rows, next_costs)
            updates.append(dict(epoch=epoch, target_sha256=digest(target.tolist()),
                                target_action="actual_next_action", gamma=1.))
        activations = _forward(x, layers)
        errors = activations[-1][:, 0]-(target-center)/scale
        gradients = _backward(activations, (2.*errors/len(x))[:, None], layers)
        pair_mse = None
        if pair_array is not None and registration["paired_weight"]:
            pair_a = _forward(pair_array, layers)
            pair_errors = ((pair_a[-1][1::2, 0]-pair_a[-1][::2, 0])*scale-pair_y)/pair_scale
            derivative = np.zeros((len(pair_array), 1))
            derivative[1::2, 0] = 2.*pair_errors*scale/pair_scale/len(pair_y)
            derivative[::2, 0] = -derivative[1::2, 0]
            pair_gradients = _backward(pair_a, derivative, layers)
            for grad, auxiliary in zip(gradients, pair_gradients, strict=True):
                for key in grad:
                    grad[key] += registration["paired_weight"]*auxiliary[key]
            pair_mse = float(np.mean(pair_errors**2)*pair_scale**2)
        loss = float(np.mean(errors**2))
        require(math.isfinite(loss), "finite_training_loss")
        if epoch % 10 == 0 or epoch == total_epochs-1 or epoch in boundaries:
            curve.append(dict(epoch=epoch, target_cost_mse=loss*scale**2,
                              paired_delta_mse=pair_mse, target_updates=len(updates)))
        for index, layer in enumerate(layers):
            for key in layer:
                gradient = np.clip(gradients[index][key], -10., 10.)
                first[index][key] = .9*first[index][key]+.1*gradient
                second[index][key] = .999*second[index][key]+.001*gradient**2
                layer[key] -= .003*(first[index][key]/(1.-.9**(epoch+1)))/(
                    np.sqrt(second[index][key]/(1.-.999**(epoch+1)))+1e-8)
    support, pool = {}, {}
    # Keep a bounded, deterministic subset of observed points. Dropping a point
    # can only reduce this neighbourhood's support, never invent support.
    for row, vector in zip(rows, x, strict=True):
        by_parent = pool.setdefault(row["action_support_key"], {})
        group = by_parent.setdefault(row["parent_uid"], [])
        entry = dict(parent_uid=row["parent_uid"], vector=vector.tolist())
        if entry not in group and len(group) < registration["support_max_prototypes_per_key"]:
            group.append(entry)
    for key, by_parent in pool.items():
        group = support.setdefault(key, [])
        for index in range(registration["support_max_prototypes_per_key"]):
            for parent in sorted(by_parent):
                if index < len(by_parent[parent]) and len(group) < registration["support_max_prototypes_per_key"]:
                    group.append(by_parent[parent][index])
    model = dict(schema=SCHEMA, information_variant=variant, seed=registration["seed"],
                 feature_schema="explicit_current_forecast_partition.v1", normalizer=normalizer,
                 parameters=dict(target_center=center, target_scale=scale,
                    layers=[{key: value.tolist() for key, value in layer.items()} for layer in layers]),
                 registration=copy.deepcopy(registration), support=support,
                 training_parent_uids=sorted({row["parent_uid"] for row in rows}),
                 training_row_count=len(rows), censored_trajectories=omitted,
                 training_labels_closed_at_epoch_seconds=labels_closed,
                 model_available_at_epoch_seconds=registration["model_available_at_epoch_seconds"],
                 forecast_contract=(dict(mapping_id=contracts[0]["mapping_id"], model_id=contracts[0]["model_id"],
                    model_available_at=contracts[0]["model_available_at"]) if contracts else None),
                 training_curve=curve, target_updates=updates,
                 training_method="actual_same_owner_SARSA" if updates else "closed_behavior_MC_regression",
                 gamma=1., target="future_cost_bag_seconds_lower_is_better", paired_target="J_alternative_minus_J_reference",
                 optimal_Q_established=False, policy_iteration_established=False,
                 native_control_benefit_established=False, success_filter_applied=False,
                 native_execution_authority=False, wall_seconds=time.perf_counter()-started)
    model["model_id"] = digest(model)
    return model


def prepare_predictor(model):
    """Validate/load weights once; caller keeps this closure across decisions."""
    frozen = copy.deepcopy(model)
    require(frozen.get("schema") == SCHEMA and frozen.get("model_id") ==
            digest({key: value for key, value in frozen.items() if key != "model_id"}), "frozen_cost_model")
    require(frozen["registration"]["source_sha256"] == source_pins(), "frozen_model_runtime_feature_sources")
    parameters = frozen["parameters"]
    layers = [{key: np.asarray(value, dtype=float) for key, value in layer.items()}
              for layer in parameters["layers"]]
    width = 2*len(frozen["normalizer"]["names"])
    for layer in layers:
        require(layer["weight"].ndim == 2 and layer["weight"].shape[1] == width
                and layer["bias"].shape == (layer["weight"].shape[0],)
                and all(np.isfinite(value).all() for value in layer.values()), "cost_model_layer_shape")
        width = layer["weight"].shape[0]
    require(width == 1, "scalar_cost_Q")

    def predict(row, *, calendar_time):
        require(number(calendar_time) >= frozen["model_available_at_epoch_seconds"], "current_model_available")
        if frozen["information_variant"] == "C11":
            binding = _validate_forecast_record(dict(row, calendar_time=calendar_time))
            require(all(binding[key] == frozen["forecast_contract"][key]
                        for key in ("mapping_id", "model_id", "model_available_at")), "runtime_frozen_forecast_contract")
        vector = encode_features(row, frozen["information_variant"], frozen["normalizer"])
        cost = float(_forward(vector[None, :], layers)[-1][0, 0]*parameters["target_scale"]
                     + parameters["target_center"])
        require(math.isfinite(cost), "finite_predicted_cost")
        neighbours = frozen["support"].get(row["action_support_key"], [])
        radius = frozen["registration"]["support_max_rms_distance"]
        parents = {item["parent_uid"] for item in neighbours
                   if float(np.sqrt(np.mean((vector-np.asarray(item["vector"]))**2))) <= radius}
        return dict(cost=cost, supported=len(parents) >= frozen["registration"]["support_min_parents"],
                    support_parent_count=len(parents), support_rule="observed_category_and_feature_neighbourhood")
    return predict


def predict_cost(model, row, *, calendar_time):
    return prepare_predictor(model)(row, calendar_time=calendar_time)


def select_supported_action(model, candidates, reference_candidate_id, *, calendar_time, predictor=None):
    """Reference is the actual action (possibly another tray), not a synthetic hold."""
    require(reference_candidate_id in candidates and candidates, "actual_reference_in_joint_catalog")
    predict = predictor or prepare_predictor(model)
    scores = {identity: predict(row, calendar_time=calendar_time) for identity, row in candidates.items()}
    reference = scores[reference_candidate_id]
    supported = [identity for identity, score in scores.items() if score["supported"]]
    selected, reason = reference_candidate_id, "reference_fallback_no_supported_positive_gain"
    gain = 0.
    if reference["supported"] and supported:
        best = min(supported, key=lambda identity: (scores[identity]["cost"], identity))
        candidate_gain = reference["cost"]-scores[best]["cost"]
        if candidate_gain > model["registration"]["gain_threshold"]:
            selected, gain, reason = best, candidate_gain, "supported_positive_estimated_gain"
    return dict(action_id=selected, reference_candidate_id=reference_candidate_id,
                estimated_gain=gain, reason=reason, scores=scores,
                estimated_gain_is_realized_benefit=False, native_execution_authority=False)


def policy_iteration_evidence(initial_model, recollected, final_model):
    """Require deployed-policy provenance and changed actual proposals, not fit count."""
    source = initial_model["model_id"]
    expected = final_model["registration"]["joint_policy_version"]
    require(recollected and all(t["manifest"].get("deployed_model_id") == source
            and t["manifest"]["joint_policy_version"] == expected
            and t["manifest"]["split"] == "train" for t in recollected), "actual_recollection_model_binding")
    require(final_model["registration"]["training_dataset_sha256"] == digest(recollected),
            "final_fit_uses_actual_recollection")
    closed = [t for t in recollected if t["scientific_status"] == "closed_finite_horizon"]
    changed = sum(row["requested_action"]["action_id"] != row["reference_candidate_id"]
                  for trajectory in closed for row in trajectory["rows"])
    return dict(schema="g31.foundation.airport_joint_policy_iteration_evidence.v1",
                initial_model_id=source, final_model_id=final_model["model_id"],
                recollection_dataset_ids=[t["dataset_id"] for t in recollected],
                closed_recollection_trajectories=len(closed), actual_nonreference_proposals=changed,
                actual_policy_recollection=bool(closed), nontrivial_policy_iteration=bool(closed and changed),
                multistep_policy_evaluation=bool(final_model["target_updates"]),
                held_out_control_benefit_established=False)
