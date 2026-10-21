"""Train-only smoothed loader probabilities, separate from frozen mapping v2."""
from __future__ import annotations

from collections import Counter
import copy
import math

from . import foundation_airport_calendar_forecast as calendar
from . import foundation_airport_feasible_domain as frozen
from . import foundation_airport_flight as flight

SCHEMA = "g31.foundation.airport_role_mapping.train_frequency.v1"
VERSION = "airport151_train_frequency_smoothing_v1"
digest = frozen.digest


def require(value, reason):
    if not value:
        raise ValueError("airport_loader_mapping:" + reason)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def fit_loader_mapping(labels, prior=None, *, train_parent_ids,
                       training_labels_closed_at_epoch_seconds,
                       model_available_at_epoch_seconds, input_domain,
                       alpha=8., minimum_region_labels=1):
    """Use observed entry labels only, with explicit split and time bounds.

    Each label requires label_id, parent_id, split, region, loader and
    observed_at_epoch_seconds. The caller must provide producer-bound labels;
    this validator cannot certify that a falsely described crosswalk is causal.
    """
    prior = calendar.static_mapping() if prior is None else copy.deepcopy(prior)
    frozen.validate_mapping(prior)
    require(finite(alpha) and alpha > 0, "positive_smoothing")
    require(type(minimum_region_labels) is int and minimum_region_labels >= 1, "minimum_train_labels")
    closed, available = training_labels_closed_at_epoch_seconds, model_available_at_epoch_seconds
    require(finite(closed) and finite(available) and closed <= available, "training_before_availability")
    parents = list(train_parent_ids)
    require(parents and len(set(parents)) == len(parents) and all(type(p) is str and p for p in parents),
            "explicit_unique_train_parent_ids")
    require(type(input_domain) is dict and input_domain and input_domain.get("split") == "train",
            "registered_train_input_domain")
    require(input_domain.get("labels_kind") == "observed_entry_labels"
            and input_domain.get("uses_future_crosswalk") is False, "observed_labels_not_future_assignment")
    counts, identities, at_values = {region: Counter() for region in flight.REGIONS}, set(), []
    labels = list(labels)
    for row in labels:
        require(row.get("split") == "train" and row.get("parent_id") in parents, "train_only_parent")
        require(row.get("label_id") not in identities and isinstance(row.get("label_id"), str), "unique_observed_label")
        identities.add(row["label_id"])
        at = row.get("observed_at_epoch_seconds")
        require(finite(at) and at <= closed, "label_observed_before_closed_boundary")
        region, node = row.get("region"), row.get("loader")
        require(region in counts and type(node) is int and node in prior["regions"][region]["nodes"],
                "label_region_role_domain")
        require(row.get("provenance_kind") == "observed_entry", "label_requires_observed_entry_provenance")
        counts[region][node] += 1
        at_values.append(at)
    regions = {}
    for region, old in prior["regions"].items():
        count = sum(counts[region].values())
        enough = count >= minimum_region_labels
        weights = [((counts[region][node] + alpha*weight)/(count+alpha) if enough else weight)
                   for node, weight in zip(old["nodes"], old["weights"])]
        regions[region] = {"nodes": list(old["nodes"]), "weights": weights,
            "observed_train_counts": [counts[region][node] for node in old["nodes"]],
            "observed_train_count": count, "fallback_to_prior": not enough,
            "rule": "train_frequency_dirichlet_prior_mean" if enough else "insufficient_train_labels_prior"}
    result = {"schema": SCHEMA, "version": VERSION, "business_contract_version": frozen.VERSION,
        "business_semantic_sha256": frozen.BUSINESS_SHA, "source_regions": list(flight.REGIONS),
        "regions": regions, "source_mapping_version": prior["version"], "source_mapping_sha256": prior["sha256"],
        "alpha": float(alpha), "minimum_region_labels": minimum_region_labels,
        "train_parent_ids": sorted(parents), "input_domain": copy.deepcopy(input_domain),
        "training_labels_sha256": digest(labels), "training_label_count": len(labels),
        "earliest_label_observed_at_epoch_seconds": min(at_values, default=None),
        "latest_label_observed_at_epoch_seconds": max(at_values, default=None),
        "training_labels_closed_at_epoch_seconds": closed, "model_available_at_epoch_seconds": available,
        "dev_or_test_labels_used": False, "uses_balanced_assignment_or_whole_day_group_counts": False,
        "real_advance_loader_assignment_known": False,
        "independent_real_airport_days_claimed": False,
        "node_uncertainty_status": "unknown_dependent_projection"}
    result["sha256"] = digest(result)
    validate_mapping(result)
    return result


def validate_mapping(mapping, *, now_epoch_seconds=None):
    require(mapping.get("schema") == SCHEMA and mapping.get("version") == VERSION,
            "new_mapping_identity_required")
    require(mapping["sha256"] == digest({k: v for k, v in mapping.items() if k != "sha256"}), "mapping_digest")
    prior = calendar.static_mapping()
    require(mapping["source_mapping_sha256"] == prior["sha256"]
            and mapping["business_semantic_sha256"] == frozen.BUSINESS_SHA, "frozen_prior_and_business")
    closed, available = mapping["training_labels_closed_at_epoch_seconds"], mapping["model_available_at_epoch_seconds"]
    require(finite(closed) and finite(available) and closed <= available,
            "training_availability_order")
    if now_epoch_seconds is not None:
        require(mapping["model_available_at_epoch_seconds"] <= now_epoch_seconds, "mapping_not_yet_available")
    require(mapping["input_domain"].get("split") == "train"
            and mapping["input_domain"].get("labels_kind") == "observed_entry_labels"
            and mapping["input_domain"].get("uses_future_crosswalk") is False
            and mapping["dev_or_test_labels_used"] is False
            and mapping["uses_balanced_assignment_or_whole_day_group_counts"] is False, "train_only_contract")
    parents = mapping["train_parent_ids"]
    require(type(parents) is list and parents and len(set(parents)) == len(parents)
            and all(type(parent) is str and parent for parent in parents), "explicit_unique_train_parent_ids")
    count = mapping["training_label_count"]
    require(type(count) is int and count >= 0, "training_label_count")
    minimum = mapping["minimum_region_labels"]
    require(type(minimum) is int and minimum >= 1, "minimum_train_labels")
    first, last = mapping["earliest_label_observed_at_epoch_seconds"], mapping["latest_label_observed_at_epoch_seconds"]
    require((count == 0 and first is None and last is None)
            or (count > 0 and finite(first) and finite(last) and first <= last <= closed),
            "observed_label_bounds_before_closed")
    require(set(mapping["regions"]) == set(flight.REGIONS), "complete_region_domain")
    alpha = mapping["alpha"]
    require(finite(alpha) and alpha > 0, "positive_smoothing")
    for region, row in mapping["regions"].items():
        old = prior["regions"][region]
        require(row["nodes"] == old["nodes"], "unchanged_role_support")
        counts, weights = row["observed_train_counts"], row["weights"]
        require(len(counts) == len(weights) == len(old["nodes"])
                and all(type(x) is int and x >= 0 for x in counts), "counts_shape")
        total = sum(counts)
        require(total == row["observed_train_count"], "count_total")
        enough = total >= mapping["minimum_region_labels"]
        expected = [(count+alpha*weight)/(total+alpha) if enough else weight
                    for count, weight in zip(counts, old["weights"])]
        require(weights == expected and row["fallback_to_prior"] is (not enough), "recomputed_train_smoothing")
        require(abs(math.fsum(weights)-1.) <= 1e-12, "probabilities_sum_one")
    require(sum(row["observed_train_count"] for row in mapping["regions"].values()) == mapping["training_label_count"],
            "complete_training_count")


def project_forecast(forecast, mapping, *, now, owner, now_epoch_seconds=None):
    """Project the same B1 regional means; do not fabricate node intervals."""
    validate_mapping(mapping, now_epoch_seconds=now if now_epoch_seconds is None else now_epoch_seconds)
    require(forecast.get("schema") == "g31.foundation.new_demand_forecast.v1"
            and forecast["forecast_origin"] == now and forecast["owner_scope"] == owner,
            "current_owner_forecast")
    require(set(forecast["new_demand_mean_by_region"]) == set(flight.REGIONS), "regional_forecast_required")
    bins = len(forecast["bin_edges_seconds"])-1
    means = {f"airport_node_{node}": [0.] * bins for node in sorted(frozen.ACTIVE_LOADERS)}
    missing = {node: [False] * bins for node in means}
    raw_totals, projected_totals = [0.] * bins, [0.] * bins
    for region, target in mapping["regions"].items():
        values = forecast["new_demand_mean_by_region"][region]
        mask = forecast["missing_mask_by_region"][region]
        mask = [mask] * bins if type(mask) is bool else list(mask)
        require(len(values) == bins == len(mask), "forecast_grid_shape")
        for index, (value, absent) in enumerate(zip(values, mask)):
            require(type(absent) is bool, "boolean_missing_mask")
            if not absent:
                require(finite(value) and value >= 0, "nonnegative_forecast_mass")
                raw_totals[index] += value
            for node, weight in zip(target["nodes"], target["weights"]):
                key = f"airport_node_{node}"
                missing[key][index] |= absent and weight > 0
                if not absent:
                    means[key][index] += value*weight
    projected_totals = [math.fsum(values[index] for values in means.values()) for index in range(bins)]
    residuals = [mapped-raw for raw, mapped in zip(raw_totals, projected_totals)]
    require(all(abs(delta) <= 1e-12*max(1., raw) for delta, raw in zip(residuals, raw_totals)), "mean_mass_conservation")
    for key in means:
        means[key] = [None if absent else value for value, absent in zip(means[key], missing[key])]
    result = copy.deepcopy(forecast)
    result.update(new_demand_mean_by_region=means, missing_mask_by_region=missing,
        uncertainty_by_region={key: None for key in means}, window_summaries_by_region={},
        source_regional_forecast_sha256=digest(forecast), airport_mapping_sha256=mapping["sha256"],
        source_mapping_version=forecast.get("mapping_version"), mapping_version=VERSION,
        airport_mapping_version=VERSION, business_contract_version=frozen.VERSION,
        business_semantic_sha256=frozen.BUSINESS_SHA,
        loader_mapping_model_available_at_epoch_seconds=mapping["model_available_at_epoch_seconds"],
        loader_mapping_training_labels_closed_at_epoch_seconds=mapping["training_labels_closed_at_epoch_seconds"],
        region_mapping_scope="observed_train_entry_smoothed_frequency",
        node_uncertainty_status="unknown_dependent_projection", projection_audit={
            "raw_known_mass_per_bin": raw_totals, "mapped_known_mass_per_bin": projected_totals,
            "floating_point_residual_per_bin": residuals, "mean_mass_conserved": True,
            "missing_mass_imputed_as_zero": False})
    return result


def predict_calendar(binding, mapping, *, now, owner, horizon_seconds=1800, plan_receipt=None):
    """New adapter keeps the frozen B1 binding and v2 validator untouched.

    This directly retains the B1 regional vector; it does not try to invert the
    old node projection, whose uniform standard-loader weights lose regions.
    """
    checkpoint, manifest = calendar._validate_binding(binding)
    require(finite(now) and 0 <= now <= 86400., "physical_day_clock")
    require(type(horizon_seconds) is int and 0 < horizon_seconds <= 1800, "forecast_horizon")
    start = manifest["target_parent"]["calendar_start_epoch_seconds"]
    absolute_now = start+now
    require(manifest["training_labels_closed_at_epoch_seconds"]
            <= manifest["model_available_at_epoch_seconds"] < absolute_now, "B1_model_availability")
    validate_mapping(mapping, now_epoch_seconds=absolute_now)
    received = calendar._receipt(binding, plan_receipt, now=now, owner=owner)
    plan = copy.deepcopy(binding["absolute_plan_template"])
    plan["owner_scope"] = owner
    if received is not None:
        plan["received_at"] = received
    regional = calendar.arrays.predict(plan, checkpoint, now=absolute_now, owner=owner,
        observed_counts=None, horizon_seconds=horizon_seconds)
    projected = project_forecast(regional, mapping, now=absolute_now, owner=owner)
    absolute = {"time_basis": copy.deepcopy(calendar.ABSOLUTE_TIME_BASIS), "forecast_origin": absolute_now,
        "absolute_bin_edges": projected["absolute_bin_edges"], "remaining_support_until": projected["remaining_support_until"],
        "information_cutoffs": copy.deepcopy(projected["information_cutoffs"]), "owner_plan_sha256": digest(plan),
        "absolute_regional_forecast_sha256": digest(regional), "absolute_projected_forecast_sha256": digest(projected)}
    projected["forecast_origin"] = float(now)
    projected["absolute_bin_edges"] = [x-start for x in projected["absolute_bin_edges"]]
    projected["remaining_support_until"] -= start
    projected["information_cutoffs"] = {key: None if value is None else value-start
                                        for key, value in projected["information_cutoffs"].items()}
    projected["time_basis"] = {"unit": "seconds", "origin": manifest["target_parent"]["calendar_start"],
        "timezone": "Asia/Shanghai", "conversion_version": VERSION+":epoch_minus_target_start"}
    projected["calendar_provenance"] = {"schema": VERSION, "binding_sha256": binding["binding_sha256"],
        "producer_manifest_sha256": digest(manifest), "absolute": absolute,
        "calendar_start_epoch_seconds": start, "parameter_reuse_not_new_B1_fit": True,
        "loader_mapping_sha256": mapping["sha256"], "observed_future_counts_used": False,
        "forecast_provenance": "offline_reconstruction_from_predeclared_static_schedule" if received is None else "actual_callback_received",
        "actual_callback_consumption": received is not None, "actual_plan_receipt": copy.deepcopy(plan_receipt),
        "declared_static_availability_is_not_actual_receipt": received is None}
    return projected
