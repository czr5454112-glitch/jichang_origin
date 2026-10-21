"""Prepared, immutable static B1 calendar inputs; fresh numerical prediction per call.

The historical calendar and array predictor modules remain untouched. This
provider validates and detaches a fixed binding and real startup receipts once.
Its arithmetic retains the original per-region, per-flight accumulation order.
No future counts, outcome labels, current observations, or predictions are cached.
"""
from __future__ import annotations

import copy
import json
import math
from types import MappingProxyType

from . import foundation_airport_joint_calendar as calendar
from . import foundation_airport_learning_public as public

original = calendar.original
np = original.np
VERSION = "g31.foundation.airport_joint_calendar_prepared.v1"


def require(condition, reason):
    if not condition:
        raise ValueError("airport_calendar_prepared:" + reason)


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf8")


def _readonly_array(values):
    # Bytes-backed arrays cannot be made writeable through NumPy setflags.
    return np.frombuffer(np.asarray(values, dtype=float).tobytes(), dtype=float)


def _regional(template_bytes, params, contexts, edges, windows, absolute_now, horizon):
    result = json.loads(template_bytes)
    result.update(forecast_origin=float(absolute_now),
        absolute_bin_edges=(absolute_now + edges).tolist(),
        remaining_support_until=absolute_now + horizon)
    for region, shape, rate, cdf_edges, cdf_values in params:
        mean, variance = np.zeros(len(edges)-1), np.zeros(len(edges)-1)
        window_mean, window_variance = np.zeros(len(original.WINDOWS)), np.zeros(len(original.WINDOWS))
        for entry in contexts.entries:
            if entry.plan_status == "cancelled":
                continue
            std = entry.scheduled_event_at
            # Exactly the original arrays.predict arithmetic and flight order.
            cdf = np.interp(absolute_now + edges - std, cdf_edges, cdf_values)
            mass = np.diff(cdf)
            mean += shape / rate * mass
            variance += shape / rate ** 2 * mass ** 2
            start = float(np.interp(absolute_now - std, cdf_edges, cdf_values))
            mass_w = np.interp(absolute_now + windows - std, cdf_edges, cdf_values) - start
            window_mean += shape / rate * mass_w
            window_variance += shape / rate ** 2 * mass_w ** 2
        intervals = original._interval(window_mean, window_variance)
        result["new_demand_mean_by_region"][region] = mean.tolist()
        result["uncertainty_by_region"][region] = original._interval(mean, variance)
        result["missing_mask_by_region"][region] = False
        result["window_summaries_by_region"][region] = {str(window):
            ({"mean": float(window_mean[i]), "lower": intervals["lower"][i], "upper": intervals["upper"][i],
              "variance": intervals["variance"][i], "level": .90} if window <= horizon else None)
            for i, window in enumerate(original.WINDOWS)}
    result.update(observed_count_update=False, updated_flight_region_count=0)
    return result


def prepare_forecast_provider(binding, receipts, *, horizon_seconds=1800, loader_mapping=None):
    """Return forecast_at(*, observation, parent), using only supplied actual receipts.

    Calling this never records a receipt or creates/advances a native session.
    Caller-owned dictionaries and returned evidence cannot mutate prepared state.
    """
    detached = copy.deepcopy(binding)
    checkpoint, manifest = calendar._validate_binding(detached)
    calendar.airport.validate_mapping(detached["mapping"])
    if loader_mapping is not None:
        from . import foundation_airport_loader_mapping as trained_mapping
        trained_mapping.validate_mapping(loader_mapping)
        loader_mapping_bytes = _json_bytes(loader_mapping)
    else:
        loader_mapping_bytes = None
    require(type(horizon_seconds) is int and 0 < horizon_seconds <= 1800
            and horizon_seconds % 60 == 0, "bounded_forecast_grid")
    require(type(receipts) is dict and receipts, "actual_owner_receipts_required")
    require(all(type(owner) is str and owner for owner in receipts), "receipt_owner_keys")
    start = manifest["target_parent"]["calendar_start_epoch_seconds"]
    parent_bytes = _json_bytes(manifest["target_parent"])
    manifest_bytes = _json_bytes(manifest)
    mapping_bytes = _json_bytes(detached["mapping"])
    manifest_source_digest = calendar.digest(manifest)
    manifest_public_digest = calendar.public_digest(manifest)
    binding_digest = detached["binding_sha256"]
    closed, available = manifest["training_labels_closed_at_epoch_seconds"], manifest["model_available_at_epoch_seconds"]
    declared_received = detached["absolute_plan_template"]["received_at"]
    parameter_rows = []
    for region in checkpoint["regions"]:
        param = checkpoint["parameters"][region]
        parameter_rows.append((region, param["shape"], param["rate"],
            _readonly_array(param["cdf_edges"]), _readonly_array(param["cdf_values"])))
    parameters = tuple(parameter_rows)
    edges = _readonly_array(np.arange(0, horizon_seconds + 60, 60, dtype=float))
    # The original predictor uses integer WINDOWS and identical float addition.
    windows = np.frombuffer(np.asarray(original.WINDOWS).tobytes(), dtype=np.asarray(original.WINDOWS).dtype)
    owners = {}
    for owner, supplied_receipt in receipts.items():
        receipt = copy.deepcopy(supplied_receipt)
        received = calendar._receipt(detached, receipt, now=0., owner=owner)
        require(received == start and receipt["received_at_physical_seconds"] == 0.
                and receipt.get("native_message_receipt_claimed") is False, "actual_startup_receipt_only")
        plan = copy.deepcopy(detached["absolute_plan_template"])
        plan.update(owner_scope=owner, received_at=received)
        context = calendar.contexts.adapt_context(plan, owner=owner, now=start,
                                                  expected_time_basis=checkpoint["time_basis"])
        require(context is not None and all(e.scheduled_event_type == "STD" for e in context.entries),
                "live_STD_context_required")
        _, _, template = original._base(checkpoint, now=start, owner=owner, regions=None,
            bin_seconds=60, horizon_seconds=horizon_seconds, context=context)
        template.update(status="forecast", method="flight_gamma_poisson",
            context_availability_basis=context.availability_basis, plan_group_count=len(context.entries))
        owners[owner] = (_json_bytes(receipt), context, _json_bytes(template), calendar.digest(plan), received)
    owners = MappingProxyType(owners)
    # No caller-owned mutable structure is retained in the closure.

    def forecast_at(*, observation, parent):
        now, owner, _, _, _ = public.validate_public(observation)
        require(math.isfinite(now) and 0 <= now <= 86400., "physical_day_clock")
        require(_json_bytes(calendar._target_parent(parent)) == parent_bytes, "current_parent_binding")
        require(owner in owners, "current_owner_has_actual_receipt")
        absolute_now = start + now
        require(closed <= available < absolute_now, "model_unavailable_at_absolute_now")
        receipt_bytes, context, template_bytes, plan_digest, received = owners[owner]
        require(received <= absolute_now and context.received_at <= absolute_now,
                "plan_unavailable_at_current_clock")
        require(context.validity_policy.valid_until is None or absolute_now < context.validity_policy.valid_until,
                "fixed_plan_expired_requires_new_provider")
        receipt = json.loads(receipt_bytes)
        regional = _regional(template_bytes, parameters, context, edges, windows,
                             absolute_now, horizon_seconds)
        if loader_mapping_bytes is None:
            projected = calendar.airport.project_forecast(regional, json.loads(mapping_bytes),
                                                           now=absolute_now, owner=owner)
        else:
            projected = trained_mapping.project_forecast(regional, json.loads(loader_mapping_bytes),
                                                          now=absolute_now, owner=owner)
        absolute = {
            "time_basis": copy.deepcopy(calendar.ABSOLUTE_TIME_BASIS), "forecast_origin": absolute_now,
            "absolute_bin_edges": projected["absolute_bin_edges"],
            "remaining_support_until": projected["remaining_support_until"],
            "information_cutoffs": copy.deepcopy(projected["information_cutoffs"]),
            "owner_plan_sha256": plan_digest, "absolute_regional_forecast_sha256": calendar.digest(regional),
            "absolute_projected_forecast_sha256": calendar.digest(projected),
        }
        current_manifest = json.loads(manifest_bytes)
        projected["forecast_origin"] = float(now)
        projected["absolute_bin_edges"] = [value-start for value in projected["absolute_bin_edges"]]
        projected["remaining_support_until"] -= start
        projected["information_cutoffs"] = {key: None if value is None else value-start
                                            for key, value in projected["information_cutoffs"].items()}
        projected["time_basis"] = {"unit": "seconds", "origin": current_manifest["target_parent"]["calendar_start"],
            "timezone": "Asia/Shanghai", "conversion_version": calendar.VERSION + ":epoch_minus_target_start"}
        projected["calendar_provenance"] = {
            "schema": calendar.VERSION, "binding_sha256": binding_digest,
            "producer_manifest_sha256": manifest_source_digest, "absolute": absolute,
            "calendar_start_epoch_seconds": start,
            "negative_source_day_cutoffs_are_prior_calendar_day": True,
            "parameter_reuse_not_new_fit": True, "observed_future_counts_used": False,
            "forecast_provenance": "actual_callback_received", "actual_callback_consumption": True,
            "actual_plan_receipt": copy.deepcopy(receipt), "declared_static_availability_is_not_actual_receipt": False,
        }
        return {
            "schema": "g31.foundation.airport_pair_absolute_forecast.v1",
            "calendar_start_epoch_seconds": start, "observed_at_epoch_seconds": absolute_now,
            "training_labels_closed_at_epoch_seconds": closed, "model_available_at_epoch_seconds": available,
            "plan_received_at_epoch_seconds": received, "declared_plan_available_at_epoch_seconds": declared_received,
            "forecast_provenance": "actual_callback_received", "actual_callback_consumption": True,
            "plan_receipt": receipt, "public_state_sha256": calendar.public_digest(observation),
            "model_id": current_manifest["model_id"], "forecast": projected,
            "forecast_sha256": calendar.public_digest(projected), "producer_manifest": current_manifest,
            "provenance_sha256": manifest_public_digest,
        }

    return forecast_at
