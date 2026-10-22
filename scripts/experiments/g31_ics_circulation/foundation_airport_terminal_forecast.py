"""Demand-only time representations for terminal-flow comparisons.

Rebinning integrates the supplied piecewise-uniform means. It neither queries
the B1 CDF nor retains its finer cumulative features. Bin intervals are (a,b];
physical supply ETAs and control ticks are outside this module. Dependent-bin
quantiles cannot be recovered from marginal intervals and remain unavailable.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math

SCHEMA = "g31.terminal_demand_representation.v1"
WINDOWS = (60, 300, 900, 1800)


def require(value, reason):
    if not value:
        raise ValueError("terminal_forecast:" + reason)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def validate_edges(edges, *, horizon_seconds=None):
    require(type(edges) in (list, tuple) and len(edges) >= 2, "nonempty_grid")
    require(all(finite(x) for x in edges) and edges[0] == 0.
            and all(a < b for a, b in zip(edges, edges[1:])), "increasing_relative_edges_from_zero")
    require(0 < edges[-1] <= 1800., "bounded_horizon")
    if horizon_seconds is not None:
        require(edges[-1] == horizon_seconds, "grid_must_cover_same_horizon")
    return [float(x) for x in edges]


def bin_edges(mode="60", *, horizon_seconds=1800., first_bin_seconds=None):
    """Origin-relative bins, with an explicitly clipped last (and optional first) bin.

    near_fine is 60 seconds through 300, then 300 seconds through 1800.
    first_bin_seconds supports an explicitly declared initial partial bin;
    it is not implicitly aligned to wall-clock minutes.
    """
    require(finite(horizon_seconds) and 0 < horizon_seconds <= 1800., "bounded_horizon")
    require(str(mode) in ("60", "300", "600", "near_fine"), "registered_bin_mode")
    near = str(mode) == "near_fine"
    width = 60. if near else float(mode)
    require(first_bin_seconds is None or (finite(first_bin_seconds)
            and 0 < first_bin_seconds <= width), "initial_partial_bin_width")
    edges = [0.]
    if first_bin_seconds is not None:
        edges.append(min(float(first_bin_seconds), float(horizon_seconds)))
    while edges[-1] < horizon_seconds:
        step = 60. if near and edges[-1] < 300. else (300. if near else width)
        end = min(edges[-1] + step, float(horizon_seconds))
        if near and edges[-1] < 300.:
            end = min(end, 300.)
        edges.append(end)
    return validate_edges(edges, horizon_seconds=horizon_seconds)


def _region(forecast, station):
    key = f"airport_node_{station}" if type(station) is int else station
    require(type(key) is str and key in forecast["new_demand_mean_by_region"], "known_destination_station")
    values = forecast["new_demand_mean_by_region"][key]
    edges = validate_edges(forecast["bin_edges_seconds"])
    mask = forecast["missing_mask_by_region"].get(key, True)
    mask = [mask] * (len(edges)-1) if type(mask) is bool else mask
    require(type(values) is list and type(mask) is list and len(values) == len(mask) == len(edges)-1,
            "forecast_grid_shape")
    require(all(type(absent) is bool for absent in mask), "boolean_missing_mask")
    require(all(absent or finite(value) and value >= 0 for value, absent in zip(values, mask)),
            "nonnegative_known_mass")
    return key, edges, values, mask


def _integrate(edges, values, mask, left, right):
    total = []
    for a, b, value, absent in zip(edges, edges[1:], values, mask):
        overlap = max(0., min(right, b)-max(left, a))
        if overlap:
            if absent:
                return None
            total.append(value * overlap / (b-a))
    return math.fsum(total)


def expected_arrivals(forecast, interval_start, interval_end, *, owner, station):
    """Piecewise-uniform mean on an absolute physical-time interval, or unknown.

    None denotes missing coverage/data; an interval outside the forecast is not
    extrapolated as zero. This is intentionally not an exact CDF query.
    """
    require(owner == forecast.get("owner_scope"), "owner_scope")
    require(finite(interval_start) and finite(interval_end) and interval_start <= interval_end,
            "ordered_finite_interval")
    _, edges, values, mask = _region(forecast, station)
    origin = forecast["forecast_origin"]
    require(finite(origin), "finite_forecast_origin")
    left, right = interval_start-origin, interval_end-origin
    if left < edges[0] or right > edges[-1]:
        return None
    return _integrate(edges, values, mask, left, right)


def rebin_forecast(forecast, *, bin_edges_seconds):
    """Return only the requested representation of the same 1800-second mass.

    No marginal variance or quantile is added across bins. Existing CDF window
    summaries are replaced by coarse-bin integrations, including windows that
    cut a coarse bin. Source hashes remain provenance, never fine demand data.
    """
    old_edges = validate_edges(forecast["bin_edges_seconds"])
    edges = validate_edges(bin_edges_seconds, horizon_seconds=old_edges[-1])
    require(forecast.get("native_execution_authority") is False, "demand_has_no_execution_authority")
    result = copy.deepcopy(forecast)
    origin = forecast["forecast_origin"]
    result.update(bin_edges_seconds=edges, absolute_bin_edges=[origin+x for x in edges],
                  remaining_support_until=origin+edges[-1])
    means, masks = {}, {}
    for station in forecast["new_demand_mean_by_region"]:
        _, source_edges, values, missing = _region(forecast, station)
        means[station] = [_integrate(source_edges, values, missing, a, b)
                          for a, b in zip(edges, edges[1:])]
        masks[station] = [x is None for x in means[station]]
        if not any(missing):
            require(math.isclose(math.fsum(values), math.fsum(means[station]), rel_tol=1e-12, abs_tol=1e-12),
                    "mass_conservation")
    result.update(new_demand_mean_by_region=means, missing_mask_by_region=masks,
                  uncertainty_by_region={station: None for station in means},
                  window_summaries_by_region={})
    for station in means:
        summaries = {}
        for window in WINDOWS:
            mean = expected_arrivals(result, origin, origin+window,
                                     owner=result["owner_scope"], station=station)
            summaries[str(window)] = None if mean is None else {
                "mean": mean, "lower": None, "upper": None, "variance": None,
                "level": None, "method": "integral_of_published_piecewise_uniform_bins"}
        result["window_summaries_by_region"][station] = summaries
    # Per-bin projection audits refer to the source representation. Do not leave
    # stale fine-grid arrays in a coarse actor payload.
    if "projection_audit" in result:
        result["projection_audit"] = {
            "source_projection_audit_sha256": digest(forecast["projection_audit"]),
            "mean_mass_conserved": True, "missing_mass_imputed_as_zero": False,
            "audit_basis": "known_station_total_before_and_after_representation_change"}
    result["demand_representation"] = {
        "schema": SCHEMA, "source_forecast_sha256": digest(forecast),
        "integration": "piecewise_uniform_source_bin_mass",
        "window_summaries": "published_bins_only_no_hidden_CDF_queries",
        "interval_convention": "left_open_right_closed",
        "first_and_last_bin": "exact_requested_edges_partial_overlap_mass_by_duration",
        "uncertainty": "unavailable_without_joint_bin_covariance_or_model_interval_query",
        "supply_times_rounded": False, "control_tick_changed": False,
        "future_truth_used": False, "horizon_seconds": edges[-1]}
    result["node_uncertainty_status"] = "unknown_dependent_bins_and_loader_projection"
    return result


def predictor_transform(model, forecast, *, now, parent_id=None):
    """Demand-only adapter; the calibration module never selects transport actions."""
    from .foundation_airport_terminal_predictor import transform
    return transform(model, forecast, now=now, parent_id=parent_id)
