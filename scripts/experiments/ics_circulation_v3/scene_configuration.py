"""Full-information scene-start configuration selection, not PPL/AIPW.

The selector reads one initial observable feature vector and selects one of
four complete causal controllers for the entire episode. A depth-one stump
uses training-only thresholds and leaf actions; validation only gates it
against the training-selected best fixed configuration.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from numbers import Real
from statistics import mean

from .joint_control import JointPolicy
from .learning import active_forecasts, shortest_edges
from .model import Snapshot
from .prebalance import known_supply


CONFIGURATIONS = (
    JointPolicy("baseline", "reactive_only", False, "route_then_prebalance"),
    JointPolicy("timed", "reactive_only", False, "route_then_prebalance"),
    JointPolicy("timed", "predictive_route_first", True, "route_then_prebalance"),
    JointPolicy("timed", "predictive_prebalance_first", True, "prebalance_then_route"),
)
CONFIGURATION_IDS = tuple(policy.policy_id for policy in CONFIGURATIONS)
FEATURE_NAMES = tuple(sorted((
    "source_empty_stock", "destination_empty_stock", "total_empty_stock", "total_tray_count",
    "loaded_tray_count", "visible_waiting_bags", "known_inflight_count",
    "inflight_destination_earliest_ticks", "destination_empty_release_earliest_ticks",
    "forecast_total_count", "forecast_source_origin_count", "forecast_destination_origin_count",
    "forecast_earliest_ticks", "forecast_destination_earliest_ticks",
    "forecast_demand_before_target_release", "forecast_shared_edges_proxy",
    "target_static_travel_ticks", "target_unload_hold_ticks", "target_deadline_slack",
    "initial_reservation_count",
)))


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite and numeric")
    return float(value)


def _features(features):
    if not isinstance(features, Mapping) or set(features) != set(FEATURE_NAMES):
        raise ValueError("Initial observable feature schema mismatch")
    return {name: _finite(features[name], name) for name in FEATURE_NAMES}


def initial_features(snapshot: Snapshot, published_forecasts: Sequence, *, target_bag_id: str,
                     horizon: int) -> dict[str, float]:
    """No scene, future tape, source ID, seed or truth metadata is accepted."""
    if type(horizon) is not int or horizon <= snapshot.now or target_bag_id not in snapshot.bags:
        raise ValueError("Need a visible target and future horizon")
    target = snapshot.bags[target_bag_id]
    carried = {tray.bag_id for tray in snapshot.trays.values() if tray.bag_id is not None}
    in_flight = {flight.tray_id for flight in snapshot.old_in_transit}
    empty = [tray for tray in snapshot.trays.values()
             if tray.mode == "empty" and tray.bag_id is None and tray.node is not None
             and tray.available_at <= snapshot.now and tray.tray_id not in snapshot.plans
             and tray.tray_id not in in_flight and tray.tray_id not in snapshot.empty_targets]
    forecasts = active_forecasts(snapshot, published_forecasts)
    sentinel = horizon - snapshot.now + 1
    route = shortest_edges(snapshot, target.origin, target.destination)
    travel = sum(snapshot.network.edges[edge].travel_time for edge in route) if route is not None else sentinel
    service = snapshot.module.unload_ticks + snapshot.module.hold_ticks(target.destination)
    target_edges = set(route or ())
    shared = sum(f.count * len(target_edges & set(shortest_edges(snapshot, f.node, f.destination) or ()))
                 for f in forecasts)
    destination_forecasts = [f for f in forecasts if f.node == target.destination]
    arrival_times = [max(0, flight.arrive - snapshot.now) for flight in snapshot.old_in_transit
                     if snapshot.network.edges[flight.edge_id].target == target.destination]
    release_times = [max(0, event.at - snapshot.now) for event in known_supply(snapshot)
                     if event.node == target.destination]
    return _features({
        "source_empty_stock": sum(tray.node == target.origin for tray in empty),
        "destination_empty_stock": sum(tray.node == target.destination for tray in empty),
        "total_empty_stock": len(empty), "total_tray_count": len(snapshot.trays),
        "loaded_tray_count": sum(tray.bag_id is not None for tray in snapshot.trays.values()),
        "visible_waiting_bags": sum(bag_id not in carried and bag_id not in snapshot.completed for bag_id in snapshot.bags),
        "known_inflight_count": len(snapshot.old_in_transit),
        "inflight_destination_earliest_ticks": min(arrival_times, default=sentinel),
        "destination_empty_release_earliest_ticks": min(release_times, default=sentinel),
        "forecast_total_count": sum(f.count for f in forecasts),
        "forecast_source_origin_count": sum(f.count for f in forecasts if f.node == target.origin),
        "forecast_destination_origin_count": sum(f.count for f in destination_forecasts),
        "forecast_earliest_ticks": min((f.at - snapshot.now for f in forecasts), default=sentinel),
        "forecast_destination_earliest_ticks": min((f.at - snapshot.now for f in destination_forecasts), default=sentinel),
        "forecast_demand_before_target_release": sum(f.count for f in destination_forecasts
                                                    if f.at <= snapshot.now + travel + service),
        "forecast_shared_edges_proxy": shared, "target_static_travel_ticks": travel,
        "target_unload_hold_ticks": service, "target_deadline_slack": target.deadline - snapshot.now - travel,
        "initial_reservation_count": len(snapshot.reservations),
    })


def _rows(rows: Sequence[dict], *, required_split: str | None = None, require_complete: bool = True):
    if not rows:
        raise ValueError("Need nonempty full-information rows")
    groups = set()
    result = []
    for row in rows:
        group = row.get("source_group")
        if not isinstance(group, str) or not group or group in groups:
            raise ValueError("Need one unique row per source group")
        if required_split is not None and row.get("split") != required_split:
            raise ValueError(f"Only {required_split} rows may be used here")
        if not isinstance(row.get("costs"), Mapping) or set(row["costs"]) != set(CONFIGURATION_IDS):
            raise ValueError("Every source requires all four configuration costs")
        costs = {name: (_finite(value, "episode cost") if value is not None else None)
                 for name, value in row["costs"].items()}
        if require_complete and any(value is None for value in costs.values()):
            raise ValueError("Failed or missing episodes cannot be dropped from fitting/selection")
        groups.add(group)
        result.append({"source_group": group, "split": row.get("split"),
                       "features": _features(row["features"]), "costs": costs})
    return sorted(result, key=lambda row: row["source_group"])


@dataclass(frozen=True)
class SceneSelector:
    kind: str
    split_feature: str | None
    threshold: float | None
    left_configuration: str
    right_configuration: str
    training_metadata: dict

    def __post_init__(self):
        if self.kind not in {"best_fixed", "stump", "stump_fallback_fixed"}:
            raise ValueError("Unknown scene selector kind")
        if self.left_configuration not in CONFIGURATION_IDS or self.right_configuration not in CONFIGURATION_IDS:
            raise ValueError("Unknown complete episode configuration")
        if self.kind == "stump":
            if self.split_feature not in FEATURE_NAMES:
                raise ValueError("Unknown stump feature")
            _finite(self.threshold, "threshold")
        elif self.split_feature is not None or self.threshold is not None or self.left_configuration != self.right_configuration:
            raise ValueError("Fixed selectors cannot contain a split")
        try:
            copy = json.loads(json.dumps(self.training_metadata, allow_nan=False))
        except (TypeError, ValueError) as exc:
            raise ValueError("Selector metadata must be finite JSON") from exc
        object.__setattr__(self, "training_metadata", copy)

    def select(self, features: Mapping) -> str:
        values = _features(features)
        return (self.left_configuration if self.split_feature is None or values[self.split_feature] <= self.threshold
                else self.right_configuration)

    def to_dict(self):
        return {"schema": "ics_v3_scene_start_selector_v1", **asdict(self)}

    @classmethod
    def from_dict(cls, value):
        keys = {"schema", "kind", "split_feature", "threshold", "left_configuration", "right_configuration", "training_metadata"}
        if not isinstance(value, Mapping) or set(value) != keys or value["schema"] != "ics_v3_scene_start_selector_v1":
            raise ValueError("Invalid scene selector schema")
        return cls(**{key: deepcopy(value[key]) for key in keys - {"schema"}})


def fit_selectors(training_rows: Sequence[dict], *, min_leaf_groups: int = 8) -> tuple[SceneSelector, SceneSelector]:
    """Fit both policies solely on training costs; no validation input exists."""
    if type(min_leaf_groups) is not int or min_leaf_groups < 1:
        raise ValueError("min_leaf_groups must be a positive integer")
    rows = _rows(training_rows, required_split="train")
    def best_action(subset):
        sums = [sum(row["costs"][config] for row in subset) for config in CONFIGURATION_IDS]
        index = min(range(4), key=lambda i: (sums[i], i))
        return index, sums[index]
    fixed_action, fixed_sum = best_action(rows)
    fingerprint = hashlib.sha256(json.dumps(rows, sort_keys=True, allow_nan=False).encode()).hexdigest()
    common = {"training_groups": len(rows), "source_groups": [r["source_group"] for r in rows],
              "training_data_sha256": fingerprint, "min_leaf_groups": min_leaf_groups,
              "features": list(FEATURE_NAMES), "configurations": list(CONFIGURATION_IDS),
              "threshold_source": "adjacent_distinct_training_feature_midpoints",
              "tie_break": "cost_sum_then_feature_then_threshold_then_configuration_order"}
    config = CONFIGURATION_IDS[fixed_action]
    fixed = SceneSelector("best_fixed", None, None, config, config,
                          {**common, "training_mean_cost": fixed_sum / len(rows)})
    best, eligible = None, 0
    for feature in FEATURE_NAMES:
        values = sorted({row["features"][feature] for row in rows})
        for a, b in zip(values, values[1:]):
            threshold = a / 2. + b / 2.
            if threshold >= b:  # adjacent floating-point values may round upward
                threshold = a
            left = [row for row in rows if row["features"][feature] <= threshold]
            right = [row for row in rows if row["features"][feature] > threshold]
            if min(len(left), len(right)) < min_leaf_groups:
                continue
            eligible += 1
            l_action, l_sum = best_action(left)
            r_action, r_sum = best_action(right)
            candidate = (l_sum + r_sum, feature, threshold, l_action, r_action, len(left), len(right))
            if best is None or candidate[:5] < best[:5]:
                best = candidate
    if best is None:
        stump = SceneSelector("stump_fallback_fixed", None, None, config, config,
                              {**common, "eligible_thresholds": 0, "training_mean_cost": fixed_sum / len(rows)})
    else:
        cost, feature, threshold, left, right, left_count, right_count = best
        stump = SceneSelector("stump", feature, threshold, CONFIGURATION_IDS[left], CONFIGURATION_IDS[right],
                              {**common, "eligible_thresholds": eligible, "training_mean_cost": cost / len(rows),
                               "leaf_group_counts": [left_count, right_count]})
    return fixed, stump


def select_on_validation(fixed: SceneSelector, stump: SceneSelector, validation_rows: Sequence[dict]):
    rows = _rows(validation_rows, required_split="validation")
    training = set(fixed.training_metadata["source_groups"]) | set(stump.training_metadata["source_groups"])
    if training & {row["source_group"] for row in rows}:
        raise ValueError("Validation source groups overlap training")
    costs = {name: mean(row["costs"][model.select(row["features"])] for row in rows)
             for name, model in (("best_fixed", fixed), ("stump", stump))}
    winner = "stump" if costs["stump"] < costs["best_fixed"] - 1e-12 else "best_fixed"
    return (stump if winner == "stump" else fixed), {"selected": winner, "mean_cost": costs,
                                                   "validation_groups": len(rows), "tie_prefers": "best_fixed",
                                                   "no_threshold_or_leaf_refit": True}


def evaluate_stored(rows: Sequence[dict], selector: SceneSelector) -> dict:
    """Exact lookup of complete-episode outcomes; runs no policy/simulator."""
    validated = _rows(rows, require_complete=False)
    decisions = []
    for row in validated:
        chosen = selector.select(row["features"])
        cost = row["costs"][chosen]
        baseline = row["costs"][CONFIGURATION_IDS[0]]
        oracle = min(row["costs"].values()) if all(v is not None for v in row["costs"].values()) else None
        decisions.append({"source_group": row["source_group"], "configuration": chosen, "cost": cost,
                          "delta_from_baseline": cost - baseline if cost is not None and baseline is not None else None,
                          "regret_to_best_recorded_configuration": cost - oracle if cost is not None and oracle is not None else None})
    costs = [row["cost"] for row in decisions if row["cost"] is not None]
    deltas = [row["delta_from_baseline"] for row in decisions if row["delta_from_baseline"] is not None]
    regrets = [row["regret_to_best_recorded_configuration"] for row in decisions if row["regret_to_best_recorded_configuration"] is not None]
    return {"source_groups": len(validated), "cost_available_count": len(costs), "failed_selected_episodes": len(validated) - len(costs),
            "mean_cost": mean(costs) if costs else None, "paired_baseline_count": len(deltas),
            "mean_delta_from_baseline": mean(deltas) if deltas else None,
            "regret_available_count": len(regrets), "mean_regret": mean(regrets) if regrets else None,
            "selection_counts": {name: sum(d["configuration"] == name for d in decisions) for name in CONFIGURATION_IDS},
            "additional_simulation_calls": 0, "decisions": decisions}
