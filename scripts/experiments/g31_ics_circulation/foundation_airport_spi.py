"""Deterministic, supported one-step policy improvement; legacy v1 is unchanged.

Only actual paired labels are accepted. Geometry describes observed support,
not confidence or a nonharm certificate. No fitting occurs on import.
"""
from __future__ import annotations

import copy
import math
import time

import numpy as np

from . import foundation_airport_pair_ranker as legacy
from .foundation_airport_batch_patch import digest

SCHEMA = "g31.foundation.airport_supported_difference_ranker.v1"
CONTRACT = "g31.foundation.airport_spi_contract.v1"
SELECTION_RULE = "validity_then_service_constraints_then_support_then_dev_J_reference_tie"
require = legacy.require


def make_spi_contract(*, allowed_domains, behavior_policy_id, continuation_policy_id,
                      improvement_round=0, max_rowspace_residual=0.25,
                      max_difference_distance=2., max_state_distance=3.,
                      strict_known_direction_nonharm=True):
    require(type(allowed_domains) is list and allowed_domains
        and all(type(x) is dict and x for x in allowed_domains), "explicit_spi_domains")
    require(all(type(x) is str and x for x in (behavior_policy_id, continuation_policy_id))
        and improvement_round in (0, 1), "frozen_spi_policy_lineage")
    limits = [max_rowspace_residual, max_difference_distance, max_state_distance]
    require(all(math.isfinite(x) and x >= 0 for x in limits), "finite_support_limits")
    return {"schema": CONTRACT, "allowed_domains": copy.deepcopy(allowed_domains),
        "policy_alignment": {"behavior_policy_id": behavior_policy_id,
            "continuation_policy_id": continuation_policy_id,
            "improvement_round": improvement_round, "max_policy_replacements": 1,
            "label_horizon_seconds": 1800.},
        "solver_candidates": [{"solver": "truncated_svd", "ridge_lambda": 0.},
            {"solver": "ridge", "ridge_lambda": 1.}, {"solver": "ridge", "ridge_lambda": 10.}],
        "svd_rcond": 1e-10, "zero_difference_atol": 1e-12,
        "max_rowspace_residual": float(max_rowspace_residual),
        "max_difference_distance": float(max_difference_distance),
        "max_state_distance": float(max_state_distance),
        "minimum_train_parents": 2, "minimum_nonzero_contrasts": 2,
        "strict_known_direction_nonharm": bool(strict_known_direction_nonharm),
        "require_nonworse_on_time": True, "require_nonworse_overdue_unfinished": True,
        "minimum_supported_dev_fraction": 0.25,
        "critical_current_missing_features": ["source_free_missing", "destination_free_missing"],
        "waiting_coverage_policy": "captured_counts_age_and_missing_masks_not_global_completeness",
        "inventory_feature_provenance": "current_owner_sensor_only_remote_planning_snapshot_not_current_truth",
        "require_known_forecast_for_loader_demand_accounts": True,
        "selection_rule": SELECTION_RULE, "reference_is_candidate": True,
        "scaler": "train_difference_RMS_without_centering",
        "state_distance_scaler": "train_reference_mean_std_floor_one",
        "development_action_selection": "same_full_K13_catalog_as_deployment",
        "development_unexecuted_winner_label": "unknown_never_actual_patch_or_zero",
        "incomplete_development_J_blocks_promotion": True,
        "development_J_aggregation": "mean_of_parent_mean_registered_root_gains",
        "development_unit": "root_conditioned_pair_not_full_policy_rollout",
        "support_is_statistical_confidence": False, "test_used_for_tuning": False}


def _validate_contract(contract):
    require(contract.get("schema") == CONTRACT and contract["reference_is_candidate"] is True
        and contract["selection_rule"] == SELECTION_RULE, "spi_contract_identity")
    alignment = contract["policy_alignment"]
    require(alignment["max_policy_replacements"] == 1
        and alignment["label_horizon_seconds"] == 1800.
        and alignment["improvement_round"] in (0, 1), "one_step_deployment_contract")
    require(contract["svd_rcond"] > 0 and contract["zero_difference_atol"] >= 0,
        "numerical_rank_tolerances")
    require(all(math.isfinite(contract[key]) and contract[key] >= 0 for key in
        ("max_rowspace_residual", "max_difference_distance", "max_state_distance"))
        and 0 <= contract["minimum_supported_dev_fraction"] <= 1,
        "frozen_support_thresholds")
    return contract


def prepare_spi_pairs(datasets, *, information_variant, split, contract):
    _validate_contract(contract)
    pairs, unavailable = legacy.prepare_pairs(datasets, information_variant=information_variant, split=split)
    for pair in pairs:
        raw = pair["raw"]["pair"]
        require(raw.get("policy_alignment") == contract["policy_alignment"],
            "actual_label_continuation_must_match_spi_contract")
        require(pair["parent"].get("spi_domain") in contract["allowed_domains"], "registered_training_domain")
        require(all(row["parent"].get("spi_domain") == pair["parent"]["spi_domain"]
            for row in pair["raw"]["rows"]), "paired_domain_equality")
    return pairs, unavailable


def solve_difference_matrix(reference, patched, targets, *, solver, ridge_lambda,
                            rcond=1e-10, zero_atol=1e-12):
    """Pure numerical kernel, also used for hand-constructed algebra gates."""
    reference, patched, targets = map(lambda x: np.asarray(x, dtype=float), (reference, patched, targets))
    require(reference.ndim == 2 and patched.shape == reference.shape
        and targets.shape == (len(reference),) and len(reference) > 0
        and all(np.isfinite(x).all() for x in (reference, patched, targets)), "finite_difference_matrix")
    require(solver in ("ridge", "truncated_svd") and ridge_lambda >= 0
        and (solver != "truncated_svd" or ridge_lambda == 0), "registered_difference_solver")
    raw = patched-reference
    active = np.flatnonzero(np.max(np.abs(raw), axis=0) > zero_atol)
    scale = np.sqrt(np.mean(raw[:, active]**2, axis=0))
    x = raw[:, active]/scale
    u, singular, vt = np.linalg.svd(x, full_matrices=False)
    keep = singular > (singular[0]*rcond if len(singular) else 0.)
    basis = vt[keep]
    factors = (1./singular[keep] if solver == "truncated_svd"
        else singular[keep]/(singular[keep]**2+ridge_lambda))
    weights = basis.T @ (factors*(u[:, keep].T @ targets))
    prediction = x @ weights
    state_center = reference.mean(axis=0)
    state_scale = np.maximum(reference.std(axis=0), 1.)
    rank = int(keep.sum())
    return {"active_columns": active.tolist(), "deleted_zero_columns": [
            i for i in range(reference.shape[1]) if i not in active],
        "difference_scale": scale.tolist(), "weights": weights.tolist(),
        "rowspace_basis": basis.tolist(), "train_differences": x.tolist(),
        "state_center": state_center.tolist(), "state_scale": state_scale.tolist(),
        "train_states": ((reference-state_center)/state_scale).tolist(),
        "rank": rank, "singular_values": singular.tolist(),
        "singular_value_basis": "train_RMS_scaled_patch_minus_reference",
        "rank_deficient": rank < len(active),
        "effective_condition_number": float(singular[0]/singular[keep][-1]) if rank else None,
        "full_column_condition_number": (float(singular[0]/singular[-1])
            if rank == len(active) and rank else None),
        "weight_rowspace_residual_l2": float(np.linalg.norm(weights-basis.T@(basis@weights))),
        "train_predictions": prediction.tolist(),
        "train_mse_bag_seconds_squared": float(np.mean((prediction-targets)**2)),
        "scaler_fit_rows": len(reference), "intercept": 0.,
        "zero_initialization_or_adam_used": False}


def make_spi_registration(datasets, *, information_variant, solver, ridge_lambda,
                          contract, model_available_at_epoch_seconds, registration_id):
    _validate_contract(contract)
    require(information_variant in legacy.VARIANTS
        and {"solver": solver, "ridge_lambda": ridge_lambda} in contract["solver_candidates"],
        "registered_spi_solver")
    return {"schema": SCHEMA+".registration", "registration_id": registration_id,
        "information_variant": information_variant, "solver": solver,
        "ridge_lambda": float(ridge_lambda), "contract": copy.deepcopy(contract),
        "training_dataset_sha256": digest(datasets), "source_pins": spi_source_pins(),
        "model_available_at_epoch_seconds": legacy.number(model_available_at_epoch_seconds),
        "fit_calls_requested": 1, "test_opened": False}


def spi_source_pins():
    from pathlib import Path
    import hashlib
    from . import foundation_airport_prospective_control as control
    from . import foundation_airport_opportunities as opportunities
    paths = (Path(__file__), Path(control.__file__), Path(opportunities.__file__))
    return dict(legacy.source_pins(), **{
        "scripts/experiments/g31_ics_circulation/"+path.name:
            hashlib.sha256(path.read_bytes()).hexdigest() for path in paths})


def fit_difference_ranker(datasets, *, registration, deadline):
    """One deterministic, preregistered solve; no random replicas or epochs."""
    started = time.perf_counter()
    require(time.monotonic() <= deadline and registration["schema"] == SCHEMA+".registration"
        and registration["test_opened"] is False, "registered_spi_fit_before_deadline")
    require(registration["training_dataset_sha256"] == digest(datasets)
        and registration["source_pins"] == spi_source_pins(), "bound_spi_training_bytes")
    contract, variant = registration["contract"], registration["information_variant"]
    pairs, unavailable = prepare_spi_pairs(datasets, information_variant=variant, split="train", contract=contract)
    require(len({_parent_group(p) for p in pairs}) >= contract["minimum_train_parents"],
        "insufficient_closed_training_parents")
    require(sum(abs(p["advantage"]) > 1e-9 for p in pairs) >= contract["minimum_nonzero_contrasts"],
        "insufficient_nonzero_action_information")
    names = sorted(pairs[0]["reference"])
    require(all(sorted(p[arm]) == names for p in pairs for arm in ("reference", "patch")), "spi_feature_schema")
    ref, patch = (np.array([[p[arm][n] for n in names] for p in pairs]) for arm in ("reference", "patch"))
    numerical = solve_difference_matrix(ref, patch, [p["advantage"] for p in pairs],
        solver=registration["solver"], ridge_lambda=registration["ridge_lambda"],
        rcond=contract["svd_rcond"], zero_atol=contract["zero_difference_atol"])
    numerical["active_feature_names"] = [names[i] for i in numerical["active_columns"]]
    numerical["deleted_zero_feature_names"] = [names[i] for i in numerical["deleted_zero_columns"]]
    closed = max(p["parent"]["calendar_start_epoch_seconds"]
        + p["raw"]["pair"]["reference_cost"]["label_end"] for p in pairs)
    require(closed <= registration["model_available_at_epoch_seconds"], "spi_labels_closed_before_availability")
    forecast_contracts = ([legacy._forecast_contract(row) for p in pairs for row in p["raw"]["rows"]]
        if variant == "C11" else [])
    require(not forecast_contracts or all(x == forecast_contracts[0] for x in forecast_contracts),
        "spi_frozen_forecast_model_and_mapping")
    model = {"schema": SCHEMA, "feature_schema": legacy.FEATURE_SCHEMA,
        "information_variant": variant, "architecture": registration["solver"],
        "seed": None, "feature_names": names, "parameters": numerical,
        "registration": copy.deepcopy(registration), "contract": copy.deepcopy(contract),
        "forecast_contract": forecast_contracts[0] if forecast_contracts else None,
        "training_parent_groups": sorted({_parent_group(p) for p in pairs}),
        "training_pair_ids": [p["pair_id"] for p in pairs],
        "unavailable_training_pairs": unavailable, "training_pairs_including_unavailable": len(datasets),
        "training_dataset_sha256": digest(datasets),
        "training_labels_closed_at_epoch_seconds": closed,
        "model_available_at_epoch_seconds": registration["model_available_at_epoch_seconds"],
        "champion_selection_available_at_epoch_seconds": registration.get(
            "development_labels_closed_at_epoch_seconds", registration["model_available_at_epoch_seconds"]),
        "target": "J_reference_minus_J_patch", "difference": "phi_patch_minus_phi_reference",
        "reference_champion": False, "fit_calls": 1, "bootstrap_used": False,
        "protected_takeover_eligible": False, "native_execution_authority": False,
        "wall_seconds": time.perf_counter()-started}
    require(time.monotonic() <= deadline, "spi_fit_wall_budget")
    model["model_id"] = digest(model)
    return model


def _parent_group(pair):
    return str(legacy._parent_group(pair["parent"]))


def make_reference_champion(*, information_variant, contract, model_available_at_epoch_seconds,
                            champion_selection_available_at_epoch_seconds=None):
    _validate_contract(contract)
    require(information_variant in legacy.VARIANTS, "reference_information_variant")
    model = {"schema": SCHEMA, "architecture": "reference_rule", "seed": None,
        "information_variant": information_variant, "contract": copy.deepcopy(contract),
        "reference_champion": True, "fit_calls": 0,
        "model_available_at_epoch_seconds": legacy.number(model_available_at_epoch_seconds),
        "champion_selection_available_at_epoch_seconds": legacy.number(
            champion_selection_available_at_epoch_seconds if champion_selection_available_at_epoch_seconds is not None
            else model_available_at_epoch_seconds),
        "protected_takeover_eligible": False, "native_execution_authority": False}
    model["model_id"] = digest(model)
    return model


def support_diagnostics(parameters, reference, patched, contract):
    reference, patched = np.asarray(reference, dtype=float), np.asarray(patched, dtype=float)
    require(reference.ndim == 1 and patched.shape == reference.shape
        and np.isfinite(reference).all() and np.isfinite(patched).all(), "finite_current_difference")
    raw = patched-reference
    active = np.asarray(parameters["active_columns"], dtype=int)
    removed = np.asarray(parameters["deleted_zero_columns"], dtype=int)
    d = raw[active]/np.asarray(parameters["difference_scale"])
    require(np.isfinite(d).all(), "finite_normalized_difference")
    basis = np.asarray(parameters["rowspace_basis"]).reshape(parameters["rank"], len(active))
    residual = float(np.linalg.norm(d-basis.T@(basis@d)))
    relative = residual/max(float(np.linalg.norm(d)), 1e-12)
    train = np.asarray(parameters["train_differences"])
    nearest = float(np.min(np.linalg.norm(train-d, axis=1)))/math.sqrt(max(1, len(active)))
    state = (reference-np.asarray(parameters["state_center"]))/np.asarray(parameters["state_scale"])
    state_distance = float(np.min(np.linalg.norm(np.asarray(parameters["train_states"])-state, axis=1)))/math.sqrt(len(state))
    reasons = []
    if parameters["rank"] == 0: reasons.append("no_identifiable_difference_direction")
    if len(removed) and np.max(np.abs(raw[removed])) > contract["zero_difference_atol"]:
        reasons.append("new_action_difference_in_train_zero_column")
    if relative > contract["max_rowspace_residual"]: reasons.append("outside_training_rowspace")
    if nearest > contract["max_difference_distance"]: reasons.append("far_from_supported_action_differences")
    if state_distance > contract["max_state_distance"]: reasons.append("far_from_supported_public_states")
    raw_gain = float(d@np.asarray(parameters["weights"]))
    return {"supported": not reasons, "fallback_reasons": reasons,
        "rowspace_residual_l2": residual, "relative_rowspace_residual": relative,
        "nearest_difference_distance": nearest, "nearest_public_state_distance": state_distance,
        "raw_predicted_advantage": raw_gain, "advantage": 0. if reasons else raw_gain,
        "statistical_confidence_claimed": False}


def _validate_parameters(parameters, width):
    active, removed = parameters["active_columns"], parameters["deleted_zero_columns"]
    require(active == sorted(set(active)) and removed == sorted(set(removed))
        and sorted(active+removed) == list(range(width)), "spi_column_partition")
    scale, weights = (np.asarray(parameters[key], dtype=float)
        for key in ("difference_scale", "weights"))
    rank = parameters["rank"]
    require(type(rank) is int and 0 <= rank <= len(active), "spi_saved_rank")
    basis = np.asarray(parameters["rowspace_basis"], dtype=float).reshape(rank, len(active))
    differences = np.asarray(parameters["train_differences"], dtype=float)
    states = np.asarray(parameters["train_states"], dtype=float)
    center, state_scale = (np.asarray(parameters[key], dtype=float)
        for key in ("state_center", "state_scale"))
    require(scale.shape == weights.shape == (len(active),) and np.all(scale > 0)
        and center.shape == state_scale.shape == (width,) and np.all(state_scale > 0)
        and differences.ndim == states.ndim == 2
        and differences.shape[1] == len(active) and states.shape == (len(differences), width)
        and len(differences) > 0
        and all(np.isfinite(a).all() for a in (scale, weights, basis, differences, states, center, state_scale)),
        "spi_finite_parameter_shapes")
    require(np.allclose(basis@basis.T, np.eye(rank), atol=1e-8, rtol=1e-8)
        and np.linalg.norm(weights-basis.T@(basis@weights)) <= 1e-8*(1+np.linalg.norm(weights)),
        "spi_weights_have_no_unidentified_nullspace_component")


def prepare_supported_predictor(model, *, development_evaluation=False):
    model = copy.deepcopy(model)
    require(model["schema"] == SCHEMA and model["model_id"] == digest({
        k: v for k, v in model.items() if k != "model_id"}), "immutable_spi_model_identity")
    contract = _validate_contract(model["contract"])
    if not model["reference_champion"]:
        require(model["registration"]["source_pins"] == spi_source_pins(), "spi_runtime_source_pins")
        require(model["feature_names"] == sorted(set(model["feature_names"]))
            and model["feature_names"], "spi_unique_feature_names")
        _validate_parameters(model["parameters"], len(model["feature_names"]))

    def predict(reference, patched):
        try:
            require(reference["parent"] == patched["parent"]
                and reference["parent"].get("spi_domain") in contract["allowed_domains"],
                "current_outside_frozen_domain")
            available = model["model_available_at_epoch_seconds"]
            if not development_evaluation:
                available = max(available, model.get("champion_selection_available_at_epoch_seconds", available))
            require(legacy._absolute_now(reference) == legacy._absolute_now(patched) >= available,
                "spi_model_or_champion_not_yet_available")
            if model["reference_champion"]:
                return {"advantage": 0., "supported": True, "reference_champion": True,
                    "fallback_reasons": [], "statistical_confidence_claimed": False}
            vectors = legacy._pair_features(reference, patched, model["information_variant"])
            require(reference["semantic_action"]["tray_id"] == patched["semantic_action"]["tray_id"],
                "spi_same_intervention_tray")
            if model["information_variant"] == "C11":
                require(all(legacy._forecast_contract(row) == model["forecast_contract"]
                    for row in (reference, patched)), "spi_current_forecast_contract")
            names = model["feature_names"]
            require(all(sorted(v) == names for v in vectors), "spi_feature_names")
            for row, vector in zip((reference, patched), vectors, strict=True):
                for feature in contract["critical_current_missing_features"]:
                    require(vector[feature] == 0., "missing_critical_current:" + feature)
                if model["information_variant"] == "C11" and contract["require_known_forecast_for_loader_demand_accounts"]:
                    loaders = row["observation"]["static_role_contract"]["loader_nodes"]
                    roles = (("source", row["semantic_action"]["source"]), (
                        "destination", row["semantic_action"].get("destination")))
                    for role, node in roles:
                        if node in loaders:
                            for window in (300, 900, 1800):
                                feature = f"{role}_forecast_{window}_missing"
                                require(vector[feature] == 0., "missing_critical_loader_forecast:" + feature)
            return support_diagnostics(model["parameters"],
                [vectors[0][n] for n in names], [vectors[1][n] for n in names], contract)
        except (ValueError, KeyError, TypeError) as exc:
            return {"advantage": 0., "supported": False, "fallback_reasons": [str(exc)],
                "statistical_confidence_claimed": False}
    return predict


def score_development_catalog(model, dataset, predict):
    """Reproduce deployed catalog ranking using only the saved public current."""
    from .foundation_airport_prospective_control import current_candidate_rows
    raw, (reference, patch) = dataset["pair"], dataset["rows"]
    require(reference["parent"] == patch["parent"] == raw["parent"]
        and reference["observation"] == patch["observation"]
        and reference["opportunity"] == patch["opportunity"]
        and reference["baseline_decision"] == patch["baseline_decision"],
        "spi_same_dev_public_current_and_baseline")
    opportunity = reference["opportunity"]
    require(opportunity["K_max"] == 13 and 1 < opportunity["K"] <= 13
        and len(opportunity["candidates"]) == opportunity["K"]
        and len({a["action_id"] for a in opportunity["candidates"]}) == opportunity["K"]
        and opportunity["candidates"][0]["kind"] == "a_ref"
        and opportunity["catalog_uses_future_plan"] is False,
        "spi_same_full_registered_development_catalog")
    require(patch["action"]["action_id"] in
        {a["action_id"] for a in opportunity["candidates"][1:]},
        "spi_actual_patch_in_saved_catalog")
    forecast = None
    if model["information_variant"] == "C11":
        forecast = reference.get("forecast_evidence")
        require(type(forecast) is dict and forecast == patch.get("forecast_evidence"),
            "spi_same_actual_dev_forecast")
    winner, gain, ranked = opportunity["candidates"][0]["action_id"], 0., []
    for rank in range(1, opportunity["K"]):
        rows = current_candidate_rows(reference["observation"], reference["baseline_decision"],
            opportunity, parent=raw["parent"], information_variant=model["information_variant"],
            forecast_evidence=forecast, patch_rank=rank, copy_inputs=False)
        if rows[1]["action"]["action_id"] == patch["action"]["action_id"]:
            require(rows[0]["semantic_action"] == reference["semantic_action"]
                and rows[1]["semantic_action"] == patch["semantic_action"],
                "spi_measured_action_semantics_match_catalog")
        explanation = predict(*rows)
        value = explanation["advantage"]
        require(type(value) in (int, float) and math.isfinite(value), "spi_finite_dev_catalog_score")
        if explanation.get("supported") is not True:
            value = 0.
        action_id = opportunity["candidates"][rank]["action_id"]
        ranked.append({"patch_rank": rank, "action_id": action_id,
            "advantage": value, "support": explanation})
        # Exact deployed rule: reference for nonpositive scores, first catalog
        # action wins a positive tie. No labels enter candidate generation.
        if value > gain:
            winner, gain = action_id, value
    return {"selected_action_id": winner, "predicted_advantage": gain,
        "actual_patch_action_id": patch["action"]["action_id"], "candidate_scores": ranked,
        "any_nonreference_feature_support": any(r["support"].get("supported") is True for r in ranked),
        "full_catalog_scored": True, "outcome_labels_used_for_ranking": False}


def evaluate_spi_on_dev(model, datasets):
    pairs, unavailable = prepare_spi_pairs(datasets, information_variant=model["information_variant"],
        split="dev", contract=model["contract"])
    require(pairs, "spi_closed_dev_pairs_required")
    train_groups = set(model.get("training_parent_groups", []))
    require(not train_groups.intersection(_parent_group(p) for p in pairs), "spi_parent_split_overlap")
    predict, rows = prepare_supported_predictor(model, development_evaluation=True), []
    for p in pairs:
        raw, (ref, patch) = p["raw"]["pair"], p["raw"]["rows"]
        if model["reference_champion"]:
            catalog = {"selected_action_id": "a_ref", "actual_patch_action_id": None,
                "candidate_scores": [], "any_nonreference_feature_support": False,
                "full_catalog_scored": False, "reference_champion": True}
        else:
            try:
                catalog = score_development_catalog(model, p["raw"], predict)
            except (ValueError, KeyError, TypeError) as exc:
                # The deployed actor also falls back to reference on malformed
                # current context. This is not measured feature support.
                catalog = {"selected_action_id": "a_ref", "actual_patch_action_id": None,
                    "candidate_scores": [], "any_nonreference_feature_support": False,
                    "full_catalog_scored": False, "fallback_reason": str(exc)}
        winner = catalog["selected_action_id"]
        choose = winner != "a_ref" and winner == catalog["actual_patch_action_id"]
        label_supported = winner == "a_ref" or choose
        supported = label_supported and (model["reference_champion"]
            or catalog["any_nonreference_feature_support"])
        direction = raw.get("censored_direction_summary")
        require(type(direction) is dict and "known_direction_harm" in direction,
            "explicit_exact_and_censored_harm_required")
        categories = direction["categories"]
        require(sum(categories.values()) == raw["reference_cost"]["physical_population"]
            and all(type(count) is int and count >= 0 for count in categories.values())
            and direction["known_direction_harm"] ==
                categories["exact_harmed"]+categories["reference_only_finished"]
            and direction["unknown_incomplete_legacy"] ==
                legacy._comparison_counts(raw).get("unknown_incomplete", 0),
            "complete_exact_and_censored_direction_population")
        costs = raw["reference_cost"], raw["patched_cost"]
        attempts = (patch if choose else ref)["actual_execution"]["attempts"] if label_supported else []
        failures = sum(not a["positive_delivered_ack"] or
            (a.get("native_transfer_at_export") or {}).get("status") == "failed" for a in attempts)
        on_time = ((costs[1]["on_time_by_end"]-costs[0]["on_time_by_end"] if choose else 0)
            if label_supported else None)
        overdue = ((costs[1]["arrived_unfinished_past_deadline"]-costs[0]["arrived_unfinished_past_deadline"] if choose else 0)
            if label_supported else None)
        gain = (p["advantage"] if choose else 0.) if label_supported else None
        rows.append({"pair_id": p["pair_id"], "parent_group": _parent_group(p),
            "choose_patch": choose, "support": {"supported": supported},
            "catalog": catalog, "label_supported": label_supported,
            "label_support": ("actual_patch" if choose else "actual_reference") if label_supported
                else "unsupported_unexecuted_full_catalog_winner",
            "failures": failures,
            "known_direction_harmed": (direction["known_direction_harm"] if choose else 0)
                if label_supported else None,
            "unknown_completion_count": legacy._comparison_counts(raw).get("unknown_incomplete", 0),
            "on_time_delta": on_time, "overdue_unfinished_delta": overdue,
            "gain_bag_seconds": gain,
            "paired_regret": max(0., p["advantage"])-gain if gain is not None else None})
    c = model["contract"]
    failures = len(unavailable)+sum(r["failures"] for r in rows)
    harmed = sum(r["known_direction_harmed"] for r in rows if r["known_direction_harmed"] is not None)
    service_violation = ((c["strict_known_direction_nonharm"] and harmed > 0)
        or (c["require_nonworse_on_time"] and any(r["on_time_delta"] is not None
            and r["on_time_delta"] < 0 for r in rows))
        or (c["require_nonworse_overdue_unfinished"] and any(r["overdue_unfinished_delta"] is not None
            and r["overdue_unfinished_delta"] > 0 for r in rows)))
    coverage = sum(r["support"]["supported"] for r in rows)/(len(rows)+len(unavailable))
    support_violation = not model["reference_champion"] and coverage < c["minimum_supported_dev_fraction"]
    parent_rows = []
    for group in sorted({legacy._parent_group(d["pair"]["parent"]) for d in datasets}):
        registered = sum(legacy._parent_group(d["pair"]["parent"]) == group for d in datasets)
        actual = [r for r in rows if r["parent_group"] == group]
        known = [r["gain_bag_seconds"] for r in actual if r["gain_bag_seconds"] is not None]
        parent_rows.append({"parent_group": group, "registered_root_count": registered,
            "closed_pair_count": len(actual), "known_selected_action_label_count": len(known),
            "complete_mean_gain_bag_seconds": math.fsum(known)/registered if len(known) == registered else None,
            "known_partial_gain_bag_seconds": math.fsum(known)})
    complete = all(r["complete_mean_gain_bag_seconds"] is not None for r in parent_rows)
    balanced = (math.fsum(r["complete_mean_gain_bag_seconds"] for r in parent_rows)/len(parent_rows)
        if complete else None)
    known_regrets = [r["paired_regret"] for r in rows if r["paired_regret"] is not None]
    return {"model_id": model["model_id"], "reference_champion": model["reference_champion"],
        "rows": rows, "failures": failures, "service_constraint_violation": bool(service_violation),
        "known_direction_harmed": harmed, "support_fraction": coverage,
        "support_constraint_violation": bool(support_violation),
        "total_gain_bag_seconds": math.fsum(r["gain_bag_seconds"] for r in rows) if complete else None,
        "complete_parent_balanced_paired_gain": balanced, "incomplete_development_J": not complete,
        "known_partial_gain_bag_seconds": math.fsum(r["gain_bag_seconds"] for r in rows
            if r["gain_bag_seconds"] is not None),
        "mean_paired_regret": math.fsum(known_regrets)/len(rows) if complete else None,
        "per_parent": parent_rows, "registered_root_count": len(datasets),
        "full_policy_development_return_claimed": False,
        "unavailable_pairs": unavailable, "strict_nonharm_certified": False}


def select_spi_on_dev(models, datasets):
    require(models and len({m["information_variant"] for m in models}) == 1
        and len({digest(m["contract"]) for m in models}) == 1, "same_spi_selection_contract")
    require(sum(m["reference_champion"] for m in models) == 1, "reference_must_be_real_champion_candidate")
    results = [evaluate_spi_on_dev(m, datasets) for m in models]
    def key(r):
        return (r["failures"], r["service_constraint_violation"], r["support_constraint_violation"],
            -r["complete_parent_balanced_paired_gain"], not r["reference_champion"], r["model_id"])
    reference = next(r for r in results if r["reference_champion"])
    eligible = [r for r in results if not r["reference_champion"] and not r["failures"]
        and not r["service_constraint_violation"] and not r["support_constraint_violation"]
        and not r["incomplete_development_J"]
        and r["complete_parent_balanced_paired_gain"] is not None
        and r["complete_parent_balanced_paired_gain"] > 0.]
    chosen = min(eligible, key=key) if eligible else reference
    return {"schema": SCHEMA+".selection", "selection_rule": SELECTION_RULE,
        "selected_model_id": chosen["model_id"], "reference_champion": chosen["reference_champion"],
        "candidate_model_ids": [m["model_id"] for m in models], "development_results": results,
        "development_dataset_sha256": digest(datasets), "frozen_before_test": True,
        "protected_takeover_eligible": False, "test_used_for_selection": False}
