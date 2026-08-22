"""Compact offline evidence and learning for G25 CLCR.

The input is a set of same-checkpoint corridor action groups.  Every group
contains the S4 action and all counterfactual first edges run from the same
checkpoint.  Checkpoint identity and time are used only for grouping and the
chronological split; neither can enter an exported runtime artifact.

The module deliberately implements only the G25 ladder: one congestion
threshold, a two-head ridge model, an optional one-hidden-layer MLP, and an
optional online EWMA bias over the linear model.  It does not create policies
unless called with measured paired rows.
"""

from __future__ import annotations

import argparse
import csv
import copy
import json
import math
import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np


ARTIFACT_SCHEMA = "czr005.g4irsf25.clcr.v1"
PAIR_SCHEMA = "czr005.g4irsf25.short_horizon_pair.v1"
FEATURE_NAMES = (
    "s4_score_delta",
    "travel_time_delta",
    "static_potential_delta",
    "target_queue_delta",
    "target_scheduled_incoming_delta",
    "corridor_wait_delta",
    "target_wait_delta",
    "goal_conditioned_differential_delta",
    "estimated_service_rate_delta",
    "service_weighted_pressure_delta",
    "two_hop_pressure_delta",
    "recent_visit_delta",
    "current_bag_age_seconds",
    "deadline_headroom_seconds",
    "recent_corridor_short_ewma_seconds",
    "recent_corridor_long_ewma_seconds",
    "recent_corridor_trend_seconds",
    "recent_corridor_feedback_age_seconds",
    "recent_corridor_feedback_sample_log1p",
    "recent_corridor_timeout_rate",
    "arm_support_log1p",
)
FEATURE_COUNT = len(FEATURE_NAMES)
GATE_METRICS = (
    "target_queue_plus_incoming",
    "service_weighted_pressure",
    "corridor_trend",
)
LOCAL_CEILING_FEATURE_INDICES = (3, 4, 5, 6, 8, 9, 10, 14, 15, 16, 17, 18, 19, 20)
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
G24_DECISION_SUMMARY_PATH = REPOSITORY_ROOT / "outputs" / "tables" / "g4irsf24_decision_summary.json"
G24_CORRIDOR_SOURCE = "outputs/tables/g4irsf24_decision_summary.json#reconvergent_corridor.corridors"
MODEL_METRICS_PATH = REPOSITORY_ROOT / "outputs" / "tables" / "g4irsf25_model_metrics.csv"
THRESHOLD_REPORT_PATH = REPOSITORY_ROOT / "outputs" / "reports" / "g4irsf25_threshold_gate.md"
CONTEXTUAL_REPORT_PATH = REPOSITORY_ROOT / "outputs" / "reports" / "g4irsf25_contextual_learning.md"
T0_FAIRNESS_CAP_CANDIDATES = (30.0, 60.0)
ARTIFACT_FILENAMES = {
    "t0": "g4irsf25_t0_threshold.json",
    "l1": "g4irsf25_clcr_l1.json",
    "l2": "g4irsf25_clcr_l2.json",
    "l3": "g4irsf25_clcr_l3.json",
}


class CLCRLearningError(ValueError):
    """Raised when measured paired evidence violates the compact contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CLCRLearningError(message)


def _portable_evidence_path(path: Path) -> str:
    """Keep repository evidence paths portable without hashing their content."""

    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(REPOSITORY_ROOT.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _g24_corridor_source(path: Path) -> str:
    return (
        f"{_portable_evidence_path(path)}"
        "#reconvergent_corridor.corridors"
    )


def _number(value: Any, label: str) -> float:
    _require(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value)),
        f"{label} must be finite",
    )
    return float(value)


def _integer(value: Any, label: str) -> int:
    _require(isinstance(value, int) and not isinstance(value, bool), f"{label} must be an integer")
    return int(value)


def _boolean(value: Any, label: str) -> bool:
    _require(isinstance(value, bool), f"{label} must be a boolean")
    return bool(value)


def _first(mapping: Mapping[str, Any], names: Sequence[str], label: str) -> Any:
    for name in names:
        if name in mapping:
            return mapping[name]
    raise CLCRLearningError(f"missing {label}")


def _feature_vector(raw: Any) -> list[float]:
    if isinstance(raw, Mapping):
        missing = [name for name in FEATURE_NAMES if name not in raw]
        if missing:
            raise CLCRLearningError(f"features missing {missing[0]}")
        return [_number(raw[name], f"features.{name}") for name in FEATURE_NAMES]
    _require(isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)), "features must be a vector or object")
    _require(len(raw) == FEATURE_COUNT, f"features must have exactly {FEATURE_COUNT} entries")
    return [_number(value, f"features[{index}]") for index, value in enumerate(raw)]


def _normalise_arm(raw: Mapping[str, Any], group: Mapping[str, Any]) -> dict[str, Any]:
    branch = _integer(group["branch_node"], "branch_node")
    first_edge = _integer(_first(raw, ("first_edge", "action", "selected_first_edge"), "first_edge"), "first_edge")
    rejoin = _integer(_first(raw, ("rejoin_node", "reconvergence_node"), "rejoin_node"), "rejoin_node")
    corridor_raw = _first(raw, ("corridor_nodes", "registered_corridor_nodes"), "corridor_nodes")
    _require(isinstance(corridor_raw, list) and corridor_raw, "corridor_nodes must be a non-empty list")
    corridor = [_integer(value, "corridor node") for value in corridor_raw]
    _require(branch in corridor and first_edge in corridor and rejoin in corridor, "corridor_nodes must contain branch, first edge, and rejoin")
    support = _integer(raw.get("support", raw.get("arm_support", 0)), "support")
    _require(support >= 0, "support cannot be negative")
    features = _feature_vector(_first(raw, ("features", "local_features"), "features"))
    local_cost = _number(
        _first(
            raw,
            ("local_system_cost_seconds", "local_system_cost", "local_queue_area_bag_seconds"),
            "local system cost",
        ),
        "local system cost",
    )
    private_cost = _number(
        _first(
            raw,
            ("private_cost_seconds", "private_cost", "private_bag_cost_seconds"),
            "private cost",
        ),
        "private cost",
    )
    _require(local_cost >= 0.0 and private_cost >= 0.0, "observed costs cannot be negative")
    safe = _boolean(raw.get("safe", True), "safe")
    timeout = _boolean(raw.get("timeout", False), "timeout")
    return {
        "first_edge": first_edge,
        "rejoin_node": rejoin,
        "corridor_nodes": corridor,
        "support": support,
        "static_duration_seconds": _number(raw.get("static_duration_seconds", 0.0), "static_duration_seconds"),
        "features": features,
        "local_system_cost_seconds": local_cost,
        "private_cost_seconds": private_cost,
        "safe": safe,
        "timeout": timeout,
    }


def _normalise_group(raw: Mapping[str, Any]) -> dict[str, Any]:
    checkpoint = _first(raw, ("checkpoint_id", "checkpoint_key", "group_id"), "checkpoint_id")
    _require(isinstance(checkpoint, (str, int)) and not isinstance(checkpoint, bool), "checkpoint_id must be a string or integer")
    branch = _integer(_first(raw, ("branch_node", "branch"), "branch_node"), "branch_node")
    goal = _integer(_first(raw, ("goal_node", "goal"), "goal_node"), "goal_node")
    s4_edge = _integer(_first(raw, ("s4_first_edge", "s4_action", "baseline_first_edge"), "s4_first_edge"), "s4_first_edge")
    checkpoint_time = _number(
        _first(raw, ("checkpoint_time_seconds", "checkpoint_time", "decision_time"), "checkpoint_time_seconds"),
        "checkpoint_time_seconds",
    )
    load_scale = _number(raw.get("load_scale", raw.get("copies", 1.0)), "load_scale")
    _require(load_scale > 0.0, "load_scale must be positive")
    leg = str(raw.get("leg", "unknown"))
    task_class = str(raw.get("task_class", "unknown"))
    group_stub = {"branch_node": branch}
    arms_raw = _first(raw, ("arms", "actions"), "arms")
    _require(isinstance(arms_raw, list) and len(arms_raw) >= 2, "each checkpoint needs at least two arms")
    arms = [_normalise_arm(arm, group_stub) for arm in arms_raw if isinstance(arm, Mapping)]
    _require(len(arms) == len(arms_raw), "every arm must be an object")
    edges = [arm["first_edge"] for arm in arms]
    _require(len(edges) == len(set(edges)), "first edges must be unique within a checkpoint")
    _require(edges.count(s4_edge) == 1, "the S4 first edge must appear exactly once")
    s4_arm = next(arm for arm in arms if arm["first_edge"] == s4_edge)
    _require(s4_arm["safe"], "the observed S4 arm must be safe")
    gate_raw = raw.get("gate_metrics", raw.get("local_gate_metrics", {}))
    _require(isinstance(gate_raw, Mapping), "gate_metrics must be an object")
    gate_metrics = {
        name: _number(value, f"gate_metrics.{name}")
        for name, value in gate_raw.items()
        if name in GATE_METRICS
    }
    return {
        "schema": PAIR_SCHEMA,
        "checkpoint_id": str(checkpoint),
        "checkpoint_time_seconds": checkpoint_time,
        "load_scale": load_scale,
        "branch_node": branch,
        "goal_node": goal,
        "leg": leg,
        "task_class": task_class,
        "s4_first_edge": s4_edge,
        "gate_metrics": gate_metrics,
        "arms": sorted(arms, key=lambda arm: arm["first_edge"]),
    }


def normalise_paired_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Validate and canonicalise already-grouped same-checkpoint action rows."""

    groups: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in rows:
        _require(isinstance(raw, Mapping), "paired row must be an object")
        group = _normalise_group(raw)
        checkpoint = group["checkpoint_id"]
        _require(checkpoint not in seen, f"duplicate checkpoint_id {checkpoint}")
        seen.add(checkpoint)
        groups.append(group)
    _require(groups, "paired dataset is empty")
    return sorted(groups, key=lambda row: (row["checkpoint_time_seconds"], row["checkpoint_id"]))


def read_compact_pairs(path: Path) -> list[dict[str, Any]]:
    """Read a compact JSON document or JSONL file of paired groups."""

    text = path.read_text(encoding="utf-8")
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        document = [json.loads(line) for line in text.splitlines() if line.strip()]
    if isinstance(document, Mapping):
        document = _first(document, ("pairs", "groups", "rows"), "pairs")
    _require(isinstance(document, list), "paired input must be a JSON list, object with pairs, or JSONL")
    return normalise_paired_rows(document)


def checkpoint_group_chronological_split(
    groups: Sequence[Mapping[str, Any]],
    *,
    train_fraction: float = 0.6,
    validation_fraction: float = 0.2,
) -> dict[str, list[dict[str, Any]]]:
    """Keep checkpoint groups and equal-time checkpoints in contiguous folds."""

    _require(0.0 < train_fraction < 1.0, "train_fraction must be between zero and one")
    _require(0.0 < validation_fraction < 1.0, "validation_fraction must be between zero and one")
    _require(train_fraction + validation_fraction < 1.0, "split fractions must leave a test tail")
    ordered = sorted((dict(group) for group in groups), key=lambda row: (row["checkpoint_time_seconds"], row["checkpoint_id"]))
    buckets: list[list[dict[str, Any]]] = []
    for group in ordered:
        if not buckets or buckets[-1][0]["checkpoint_time_seconds"] != group["checkpoint_time_seconds"]:
            buckets.append([])
        buckets[-1].append(group)
    _require(len(buckets) >= 3, "chronological split needs at least three distinct checkpoint times")
    cumulative = np.cumsum([len(bucket) for bucket in buckets])
    train_target = len(ordered) * train_fraction
    validation_target = len(ordered) * (train_fraction + validation_fraction)
    train_cut = min(range(1, len(buckets) - 1), key=lambda index: abs(float(cumulative[index - 1]) - train_target))
    validation_cut = min(
        range(train_cut + 1, len(buckets)),
        key=lambda index: abs(float(cumulative[index - 1]) - validation_target),
    )
    split = {
        "train": [row for bucket in buckets[:train_cut] for row in bucket],
        "validation": [row for bucket in buckets[train_cut:validation_cut] for row in bucket],
        "test": [row for bucket in buckets[validation_cut:] for row in bucket],
    }
    _require(all(split.values()), "chronological split produced an empty partition")
    checkpoint_sets = [{row["checkpoint_id"] for row in partition} for partition in split.values()]
    _require(not (checkpoint_sets[0] & checkpoint_sets[1] or checkpoint_sets[0] & checkpoint_sets[2] or checkpoint_sets[1] & checkpoint_sets[2]), "checkpoint leakage across folds")
    return split


def _s4_arm(group: Mapping[str, Any]) -> Mapping[str, Any]:
    return next(arm for arm in group["arms"] if arm["first_edge"] == group["s4_first_edge"])


def _oracle_arm(group: Mapping[str, Any]) -> Mapping[str, Any]:
    safe = [arm for arm in group["arms"] if arm["safe"]]
    _require(safe, "checkpoint has no safe arm")
    return min(safe, key=lambda arm: (arm["local_system_cost_seconds"], arm["private_cost_seconds"], arm["first_edge"]))


def _percentile(values: Sequence[float], percentile: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=float), percentile)) if values else 0.0


def _opportunity_summary(groups: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    gains: list[float] = []
    alternative_gains: list[float] = []
    for group in groups:
        s4 = _s4_arm(group)
        best = _oracle_arm(group)
        gain = s4["local_system_cost_seconds"] - best["local_system_cost_seconds"]
        gains.append(gain)
        if best["first_edge"] != group["s4_first_edge"] and gain > 0.0:
            alternative_gains.append(gain)
    count = len(groups)
    fraction = len(alternative_gains) / count if count else 0.0
    mean_positive = float(np.mean(alternative_gains)) if alternative_gains else 0.0
    baseline = [float(_s4_arm(group)["local_system_cost_seconds"]) for group in groups]
    return {
        "branch_decisions": count,
        "useful_opportunities": len(alternative_gains),
        "alternative_win_fraction": fraction,
        "mean_gain_when_alternative_wins": mean_positive,
        "opportunity_mass": count * fraction * mean_positive,
        "mean_possible_improvement": float(np.mean(gains)) if gains else 0.0,
        "mean_possible_improvement_fraction": (float(np.sum(gains)) / float(np.sum(baseline))) if sum(baseline) > 0.0 else 0.0,
        "p50_possible_improvement": _percentile(gains, 50),
        "p95_possible_improvement": _percentile(gains, 95),
        "p99_possible_improvement": _percentile(gains, 99),
    }


def _stable_reversal_branches(groups: Sequence[Mapping[str, Any]]) -> list[int]:
    winners: dict[int, Counter[int]] = defaultdict(Counter)
    for group in groups:
        winners[int(group["branch_node"])][_oracle_arm(group)["first_edge"]] += 1
    stable: list[int] = []
    for branch, counts in winners.items():
        total = sum(counts.values())
        minimum = max(2, int(math.ceil(total * 0.10)))
        if sum(count >= minimum for count in counts.values()) >= 2:
            stable.append(branch)
    return sorted(stable)


def _local_observation_ceiling(groups: Sequence[Mapping[str, Any]], bins: int = 3) -> dict[str, Any]:
    _require(bins >= 2, "local ceiling needs at least two bins")
    boundaries: dict[int, np.ndarray] = {}
    for index in LOCAL_CEILING_FEATURE_INDICES:
        values = np.asarray([arm["features"][index] for group in groups for arm in group["arms"]], dtype=float)
        boundaries[index] = np.unique(np.quantile(values, np.linspace(0.0, 1.0, bins + 1)[1:-1]))

    def signature(group: Mapping[str, Any]) -> tuple[Any, ...]:
        arm_signatures = []
        for arm in sorted(group["arms"], key=lambda item: item["first_edge"]):
            encoded = tuple(int(np.searchsorted(boundaries[index], arm["features"][index], side="right")) for index in LOCAL_CEILING_FEATURE_INDICES)
            arm_signatures.append((arm["first_edge"], encoded))
        return (group["branch_node"], tuple(arm_signatures))

    cells: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for group in groups:
        cells[signature(group)].append(group)
    chosen_by_cell: dict[tuple[Any, ...], int] = {}
    for key, members in cells.items():
        counts = Counter(_oracle_arm(group)["first_edge"] for group in members)
        chosen_by_cell[key] = min(counts, key=lambda edge: (-counts[edge], edge))
    correct = 0
    regrets: list[float] = []
    improvements: list[float] = []
    for group in groups:
        chosen_edge = chosen_by_cell[signature(group)]
        chosen = next(arm for arm in group["arms"] if arm["first_edge"] == chosen_edge)
        oracle = _oracle_arm(group)
        s4 = _s4_arm(group)
        correct += chosen_edge == oracle["first_edge"]
        regrets.append(chosen["local_system_cost_seconds"] - oracle["local_system_cost_seconds"])
        improvements.append(s4["local_system_cost_seconds"] - chosen["local_system_cost_seconds"])
    singleton_members = sum(len(members) for members in cells.values() if len(members) == 1)
    s4_accuracy = sum(group["s4_first_edge"] == _oracle_arm(group)["first_edge"] for group in groups) / len(groups)
    return {
        "method": "optimistic_quantile_cell_majority",
        "feature_indices": list(LOCAL_CEILING_FEATURE_INDICES),
        "bin_count": bins,
        "cell_count": len(cells),
        "singleton_checkpoint_fraction": singleton_members / len(groups),
        "majority_action_accuracy": correct / len(groups),
        "pairwise_ranking_ceiling": correct / len(groups),
        "s4_action_accuracy": s4_accuracy,
        "mean_local_regret_ceiling": float(np.mean(regrets)),
        "mean_improvement_over_s4": float(np.mean(improvements)),
    }


def compute_action_ceilings(groups: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Compute full-state, local-observation, and opportunity ceilings once."""

    _require(bool(groups), "cannot compute ceilings for an empty dataset")
    by_branch = {
        str(branch): _opportunity_summary([group for group in groups if group["branch_node"] == branch])
        for branch in sorted({int(group["branch_node"]) for group in groups})
    }
    by_load = {
        str(load): _opportunity_summary([group for group in groups if group["load_scale"] == load])
        for load in sorted({float(group["load_scale"]) for group in groups})
    }
    by_leg = {
        leg: _opportunity_summary([group for group in groups if group["leg"] == leg])
        for leg in sorted({str(group["leg"]) for group in groups})
    }
    stable = _stable_reversal_branches(groups)
    full = _opportunity_summary(groups)
    full["stable_action_reversal_branches"] = stable
    full["stable_action_reversal_branch_count"] = len(stable)
    full["by_branch"] = by_branch
    full["by_load"] = by_load
    full["by_leg"] = by_leg
    return {
        "full_state": full,
        "local_observation": _local_observation_ceiling(groups),
        "opportunity_mass": full["opportunity_mass"],
    }


def _samples(groups: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for group in groups:
        s4 = _s4_arm(group)
        for arm in group["arms"]:
            observed_system_delta = (
                arm["local_system_cost_seconds"]
                - s4["local_system_cost_seconds"]
            )
            samples.append(
                {
                    "group": group,
                    "arm": arm,
                    "key": (int(group["branch_node"]), int(arm["first_edge"])),
                    "features": arm["features"],
                    "observed_system_delta": observed_system_delta,
                    # Native ranking adds this prediction to the already
                    # computed S4 score.  Removing the S4 gap here prevents
                    # double-counting it at runtime.
                    "system_residual": observed_system_delta - arm["features"][0],
                    "private_delta": arm["private_cost_seconds"] - s4["private_cost_seconds"],
                }
            )
    return samples


def _normalization(samples: Sequence[Mapping[str, Any]]) -> dict[str, list[float]]:
    matrix = np.asarray([sample["features"] for sample in samples], dtype=float)
    mean = matrix.mean(axis=0)
    scale = matrix.std(axis=0)
    scale[scale < 1.0e-9] = 1.0
    minimum = matrix.min(axis=0)
    maximum = matrix.max(axis=0)
    padding = np.maximum((maximum - minimum) * 0.10, scale * 0.25)
    lower = minimum - padding
    upper = maximum + padding
    # Paired checkpoints intentionally start without online history.  These
    # six runtime-owned values leave that initial point after the first
    # completed corridor, so use their explicit bounded semantics instead of
    # treating the all-zero training snapshot as an OOD contract.
    lower[14:20] = np.asarray([0.0, 0.0, -600.0, 0.0, 0.0, 0.0])
    upper[14:20] = np.asarray([600.0, 600.0, 600.0, 600.0, 20.0, 1.0])
    return {
        "mean": mean.tolist(),
        "scale": scale.tolist(),
        "min": lower.tolist(),
        "max": upper.tolist(),
    }


def _arm_descriptors(groups: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    observations: dict[tuple[int, int], list[tuple[Mapping[str, Any], Mapping[str, Any]]]] = defaultdict(list)
    for group in groups:
        for arm in group["arms"]:
            observations[(int(group["branch_node"]), int(arm["first_edge"]))].append((group, arm))
    descriptors: list[dict[str, Any]] = []
    for (branch, edge), rows in sorted(observations.items()):
        rejoin_values = {int(arm["rejoin_node"]) for _, arm in rows}
        corridor_values = {tuple(arm["corridor_nodes"]) for _, arm in rows}
        support_values = {int(arm["support"]) for _, arm in rows}
        _require(len(rejoin_values) == 1 and len(corridor_values) == 1, f"arm {branch}->{edge} changed its corridor contract")
        _require(len(support_values) == 1, f"arm {branch}->{edge} changed its historic support")
        descriptors.append(
            {
                "branch_node": branch,
                "first_edge": edge,
                "rejoin_node": next(iter(rejoin_values)),
                "corridor_nodes": list(next(iter(corridor_values))),
                "support": next(iter(support_values)),
                "training_support": len(rows),
                "static_duration_seconds": float(np.median([arm["static_duration_seconds"] for _, arm in rows])),
                "t0_system_delta_seconds": 0.0,
                "t0_private_delta_seconds": 0.0,
                "system_intercept": 0.0,
                "private_intercept": 0.0,
            }
        )
    return descriptors


def _common_artifact(
    *,
    mode: str,
    groups: Sequence[Mapping[str, Any]],
    normalization: Mapping[str, Sequence[float]],
    model: Mapping[str, Any] | None,
    min_support: int,
    margin_seconds: float,
    private_cap_seconds: float,
    training_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    artifact: dict[str, Any] = {
        "schema": ARTIFACT_SCHEMA,
        "mode": mode,
        "feature_names": list(FEATURE_NAMES),
        "record_trajectories": False,
        "min_support": int(min_support),
        "margin_seconds": float(margin_seconds),
        "private_cap_seconds": float(private_cap_seconds),
        "t0_metric": "target_queue_plus_incoming",
        "l3_short_alpha": 0.20,
        "l3_long_alpha": 0.02,
        "l3_bias_cap_seconds": 30.0,
        "trajectory_max_seconds": 600.0,
        "normalization": {name: [float(value) for value in normalization.get(name, ())] for name in ("mean", "scale", "min", "max")},
        "arms": _arm_descriptors(groups),
    }
    if model is not None:
        artifact["model"] = dict(model)
    if training_metadata is not None:
        artifact["training_metadata"] = dict(training_metadata)
    return artifact


def fit_l1_ridge(
    groups: Sequence[Mapping[str, Any]],
    *,
    ridge: float = 1.0,
    min_support: int = 8,
    margin_seconds: float = 0.5,
    private_cap_seconds: float = 60.0,
) -> dict[str, Any]:
    """Fit shared two-head ridge weights plus a constant arm intercept."""

    _require(ridge >= 0.0 and math.isfinite(ridge), "ridge must be finite and non-negative")
    samples = _samples(groups)
    _require(samples, "cannot fit L1 without samples")
    normalization = _normalization(samples)
    matrix = np.asarray([sample["features"] for sample in samples], dtype=float)
    matrix = (matrix - np.asarray(normalization["mean"])) / np.asarray(normalization["scale"])
    keys = sorted({sample["key"] for sample in samples})
    key_index = {key: index for index, key in enumerate(keys)}
    one_hot = np.zeros((len(samples), len(keys)), dtype=float)
    for row, sample in enumerate(samples):
        one_hot[row, key_index[sample["key"]]] = 1.0
    design = np.concatenate((matrix, one_hot), axis=1)
    targets = np.asarray([[sample["system_residual"], sample["private_delta"]] for sample in samples], dtype=float)
    penalty = np.diag([ridge] * FEATURE_COUNT + [1.0e-9] * len(keys))
    coefficients = np.linalg.solve(design.T @ design + penalty, design.T @ targets)
    artifact = _common_artifact(
        mode="l1",
        groups=groups,
        normalization=normalization,
        model={
            "system_weights": coefficients[:FEATURE_COUNT, 0].tolist(),
            "private_weights": coefficients[:FEATURE_COUNT, 1].tolist(),
        },
        min_support=min_support,
        margin_seconds=margin_seconds,
        private_cap_seconds=private_cap_seconds,
        training_metadata={
            "checkpoint_count": len(groups),
            "arm_sample_count": len(samples),
            "ridge": ridge,
            "system_target_semantics": "observed_local_system_arm_vs_s4_delta_minus_s4_score_delta",
            "private_target_semantics": "observed_private_arm_vs_s4_delta",
        },
    )
    descriptors = {(arm["branch_node"], arm["first_edge"]): arm for arm in artifact["arms"]}
    for key, index in key_index.items():
        descriptors[key]["system_intercept"] = float(coefficients[FEATURE_COUNT + index, 0])
        descriptors[key]["private_intercept"] = float(coefficients[FEATURE_COUNT + index, 1])
    return artifact


def _gate_value(group: Mapping[str, Any], metric: str) -> float:
    _require(metric in GATE_METRICS, f"unsupported T0 metric {metric}")
    if metric in group["gate_metrics"]:
        return float(group["gate_metrics"][metric])
    if metric == "target_queue_plus_incoming":
        return max(float(arm["features"][3] + arm["features"][4]) for arm in group["arms"])
    if metric == "service_weighted_pressure":
        return max(float(arm["features"][9]) for arm in group["arms"])
    return max(float(arm["features"][16]) for arm in group["arms"])


def read_g24_corridor_residuals(path: Path = G24_DECISION_SUMMARY_PATH) -> list[dict[str, Any]]:
    """Read the eight frozen G24 reconvergent-corridor residuals.

    T0 is a thresholded replay of the G24 policy, not a model fitted from the
    G25 counterfactual labels. Those labels may select only the threshold and
    the 30/60-second fairness cap.
    """

    document = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(document, Mapping), "G24 decision summary must be an object")
    reconvergent = document.get("reconvergent_corridor")
    _require(isinstance(reconvergent, Mapping), "G24 decision summary missing reconvergent_corridor")
    raw_corridors = reconvergent.get("corridors")
    _require(isinstance(raw_corridors, list), "G24 decision summary missing reconvergent_corridor.corridors")
    _require(len(raw_corridors) == 8, "G24 T0 source must contain exactly eight corridor arms")
    corridors: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for index, raw in enumerate(raw_corridors):
        _require(isinstance(raw, Mapping), f"G24 corridor[{index}] must be an object")
        branch = _integer(raw.get("from"), f"G24 corridor[{index}].from")
        first_edge = _integer(raw.get("to"), f"G24 corridor[{index}].to")
        rejoin = _integer(raw.get("reconvergence"), f"G24 corridor[{index}].reconvergence")
        corridor_raw = raw.get("path")
        _require(isinstance(corridor_raw, list) and corridor_raw, f"G24 corridor[{index}].path must be non-empty")
        corridor = [_integer(value, f"G24 corridor[{index}].path") for value in corridor_raw]
        _require(
            corridor[0] == branch and first_edge in corridor and corridor[-1] == rejoin,
            f"G24 corridor[{index}] path does not match its endpoints",
        )
        key = (branch, first_edge)
        _require(key not in seen, f"duplicate G24 corridor arm {branch}->{first_edge}")
        seen.add(key)
        support = _integer(raw.get("support"), f"G24 corridor[{index}].support")
        _require(support >= 0, f"G24 corridor[{index}].support cannot be negative")
        corridors.append(
            {
                "branch_node": branch,
                "first_edge": first_edge,
                "rejoin_node": rejoin,
                "corridor_nodes": corridor,
                "support": support,
                "static_duration_seconds": _number(
                    raw.get("static_duration_seconds"),
                    f"G24 corridor[{index}].static_duration_seconds",
                ),
                "residual_seconds": _number(
                    raw.get("residual_seconds"),
                    f"G24 corridor[{index}].residual_seconds",
                ),
                "dynamic_duration_seconds": _number(
                    raw.get("dynamic_duration_seconds"),
                    f"G24 corridor[{index}].dynamic_duration_seconds",
                ),
            }
        )
    return sorted(corridors, key=lambda row: (row["branch_node"], row["first_edge"]))


def _g24_t0_arm_descriptors(
    train_groups: Sequence[Mapping[str, Any]],
    *,
    g24_decision_summary_path: Path,
) -> list[dict[str, Any]]:
    training_support = Counter(
        (int(group["branch_node"]), int(arm["first_edge"]))
        for group in train_groups
        for arm in group["arms"]
    )
    return [
        {
            "branch_node": int(row["branch_node"]),
            "first_edge": int(row["first_edge"]),
            "rejoin_node": int(row["rejoin_node"]),
            "corridor_nodes": list(row["corridor_nodes"]),
            "support": int(row["support"]),
            "training_support": int(training_support[(row["branch_node"], row["first_edge"])]),
            "static_duration_seconds": float(row["static_duration_seconds"]),
            "t0_system_delta_seconds": float(row["residual_seconds"]),
            # The G24 dynamic corridor duration is the only frozen per-arm
            # private-cost estimate available to this non-learning control.
            # Keeping it preserves the same relative fairness guard used by
            # L1 without fitting any G25 pair label.
            "t0_private_delta_seconds": float(row["dynamic_duration_seconds"]),
            "system_intercept": 0.0,
            "private_intercept": 0.0,
        }
        for row in read_g24_corridor_residuals(g24_decision_summary_path)
    ]


def build_t0_artifact(
    train_groups: Sequence[Mapping[str, Any]],
    *,
    metric: str,
    enter_pressure: float,
    exit_pressure: float,
    min_support: int = 8,
    margin_seconds: float = 0.5,
    private_cap_seconds: float = 60.0,
    g24_decision_summary_path: Path = G24_DECISION_SUMMARY_PATH,
) -> dict[str, Any]:
    _require(metric in GATE_METRICS, f"unsupported T0 metric {metric}")
    _require(math.isfinite(enter_pressure) and math.isfinite(exit_pressure) and exit_pressure <= enter_pressure, "T0 thresholds must be finite with exit <= enter")
    _require(
        float(private_cap_seconds) in T0_FAIRNESS_CAP_CANDIDATES,
        "T0 fairness cap must be one of the registered 30/60-second choices",
    )
    resolved_g24_source = g24_decision_summary_path.expanduser().resolve()
    residual_source = _g24_corridor_source(resolved_g24_source)
    artifact = _common_artifact(
        mode="t0",
        groups=train_groups,
        normalization={"mean": [], "scale": [], "min": [], "max": []},
        model=None,
        min_support=min_support,
        margin_seconds=margin_seconds,
        private_cap_seconds=private_cap_seconds,
        training_metadata={
            "threshold_train_checkpoint_count": len(train_groups),
            "metric": metric,
            "residual_source": residual_source,
            "residual_contract": "FROZEN_G24_NO_PAIRED_REFIT",
            "paired_label_usage": "THRESHOLD_AND_30_OR_60_SECOND_FAIRNESS_CAP_SELECTION_ONLY",
        },
    )
    artifact["arms"] = _g24_t0_arm_descriptors(
        train_groups,
        g24_decision_summary_path=resolved_g24_source,
    )
    artifact["t0_metric"] = metric
    artifact["t0_enter_pressure"] = float(enter_pressure)
    artifact["t0_exit_pressure"] = float(exit_pressure)
    return artifact


def _arm_lookup(artifact: Mapping[str, Any]) -> dict[tuple[int, int], Mapping[str, Any]]:
    return {(int(arm["branch_node"]), int(arm["first_edge"])): arm for arm in artifact["arms"]}


def _predict(artifact: Mapping[str, Any], group: Mapping[str, Any], arm: Mapping[str, Any]) -> tuple[float, float, bool]:
    descriptor = _arm_lookup(artifact).get((int(group["branch_node"]), int(arm["first_edge"])))
    if descriptor is None or int(descriptor.get("training_support", 0)) < int(artifact["min_support"]):
        return 0.0, 0.0, True
    mode = str(artifact["mode"])
    if mode == "t0":
        return float(descriptor["t0_system_delta_seconds"]), float(descriptor["t0_private_delta_seconds"]), False
    normalization = artifact["normalization"]
    features = np.asarray(arm["features"], dtype=float)
    minimum = np.asarray(normalization["min"], dtype=float)
    maximum = np.asarray(normalization["max"], dtype=float)
    ood = bool(np.any(features < minimum) or np.any(features > maximum)) if len(minimum) else False
    features = (features - np.asarray(normalization["mean"], dtype=float)) / np.asarray(normalization["scale"], dtype=float)
    model = artifact["model"]
    if mode == "l2":
        hidden = np.maximum(0.0, np.asarray(model["hidden_weights"], dtype=float) @ features + np.asarray(model["hidden_bias"], dtype=float))
        system = float(model["hidden_system_bias"] + np.dot(model["hidden_system_weights"], hidden))
        private = float(model["hidden_private_bias"] + np.dot(model["hidden_private_weights"], hidden))
    else:
        system = float(np.dot(model["system_weights"], features))
        private = float(np.dot(model["private_weights"], features))
    system += float(descriptor["system_intercept"])
    private += float(descriptor["private_intercept"])
    return system, private, ood


def evaluate_artifact(groups: Sequence[Mapping[str, Any]], artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate offline ranking, guards, regret, coverage, and calibration."""

    system_errors: list[float] = []
    private_errors: list[float] = []
    ranking_correct = 0
    mutations = 0
    beneficial_mutations = 0
    harmful_mutations = 0
    useful_opportunities = 0
    captured_opportunities = 0
    harmful_alternatives = 0
    harmful_rejected = 0
    regrets: list[float] = []
    safety_failures = 0
    selected_rows: list[dict[str, Any]] = []
    margin = float(artifact["margin_seconds"])
    private_cap = float(artifact["private_cap_seconds"])

    def hard_protected(arm: Mapping[str, Any]) -> bool:
        features = arm["features"]
        return bool(
            float(features[12]) >= 600.0 - 1.0e-9
            or float(features[13]) <= private_cap + 1.0e-9
            or float(features[11]) > 0.0
        )

    ordered_groups = sorted(
        groups,
        key=lambda group: (
            float(group["load_scale"]),
            float(group["checkpoint_time_seconds"]),
            str(group["checkpoint_id"]),
        ),
    )
    t0_gate_open: dict[tuple[float, int], bool] = {}
    for group in ordered_groups:
        s4 = _s4_arm(group)
        oracle = _oracle_arm(group)
        useful = oracle["first_edge"] != group["s4_first_edge"] and oracle["local_system_cost_seconds"] < s4["local_system_cost_seconds"]
        useful_opportunities += useful
        predictions: dict[int, tuple[float, float, bool]] = {}
        for arm in group["arms"]:
            predictions[int(arm["first_edge"])] = _predict(
                artifact, group, arm
            )
        baseline_prediction = predictions[int(group["s4_first_edge"])]
        for arm in group["arms"]:
            prediction = predictions[int(arm["first_edge"])]
            true_system = arm["local_system_cost_seconds"] - s4["local_system_cost_seconds"]
            true_private = arm["private_cost_seconds"] - s4["private_cost_seconds"]
            predicted_system_delta = (
                arm["features"][0]
                + prediction[0]
                - baseline_prediction[0]
            )
            predicted_private_delta = prediction[1] - baseline_prediction[1]
            system_errors.append(abs(predicted_system_delta - true_system))
            private_errors.append(abs(predicted_private_delta - true_private))
        adjusted = {
            int(arm["first_edge"]): float(arm["features"][0] + predictions[arm["first_edge"]][0])
            for arm in group["arms"]
        }
        for arm in group["arms"]:
            if arm["first_edge"] == group["s4_first_edge"]:
                continue
            true_system = arm["local_system_cost_seconds"] - s4["local_system_cost_seconds"]
            if true_system > 0.0:
                harmful_alternatives += 1
                prediction = predictions[arm["first_edge"]]
                improvement = adjusted[int(group["s4_first_edge"])] - adjusted[int(arm["first_edge"])]
                private_difference = prediction[1] - baseline_prediction[1]
                eligible = (
                    not baseline_prediction[2]
                    and not prediction[2]
                    and improvement >= margin
                    and private_difference <= private_cap
                    and not hard_protected(arm)
                )
                harmful_rejected += not eligible
        rankable = [arm for arm in group["arms"] if not predictions[arm["first_edge"]][2]]
        predicted_best = (
            min(rankable, key=lambda arm: (adjusted[arm["first_edge"]], arm["first_edge"]))
            if rankable
            else s4
        )
        ranking_correct += predicted_best["first_edge"] == oracle["first_edge"]
        gate_open = True
        if artifact["mode"] == "t0":
            gate_key = (float(group["load_scale"]), int(group["branch_node"]))
            pressure = _gate_value(group, str(artifact["t0_metric"]))
            threshold = (
                float(artifact["t0_exit_pressure"])
                if t0_gate_open.get(gate_key, False)
                else float(artifact["t0_enter_pressure"])
            )
            gate_open = pressure + 1.0e-9 >= threshold
            t0_gate_open[gate_key] = gate_open
        selected = s4
        if not baseline_prediction[2] and gate_open and predicted_best["first_edge"] != group["s4_first_edge"]:
            proposal = predictions[predicted_best["first_edge"]]
            improvement = adjusted[int(group["s4_first_edge"])] - adjusted[int(predicted_best["first_edge"])]
            private_difference = proposal[1] - baseline_prediction[1]
            if (
                improvement >= margin
                and private_difference <= private_cap
                and not hard_protected(predicted_best)
            ):
                selected = predicted_best
        mutated = selected["first_edge"] != group["s4_first_edge"]
        mutations += mutated
        observed_delta = selected["local_system_cost_seconds"] - s4["local_system_cost_seconds"]
        beneficial_mutations += mutated and observed_delta < 0.0
        harmful_mutations += mutated and observed_delta > 0.0
        captured_opportunities += useful and selected["first_edge"] == oracle["first_edge"]
        safety_failures += mutated and not selected["safe"]
        regrets.append(selected["local_system_cost_seconds"] - oracle["local_system_cost_seconds"])
        selected_rows.append(
            {
                "group": group,
                "predicted_delta": (
                    adjusted[int(selected["first_edge"])]
                    - adjusted[int(group["s4_first_edge"])]
                    if mutated
                    else 0.0
                ),
                "observed_delta": observed_delta,
            }
        )

    def calibration(key_fn: Any) -> dict[str, Any]:
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in selected_rows:
            buckets[str(key_fn(row["group"]))].append(row)
        return {
            key: {
                "count": len(rows),
                "predicted_delta_mean": float(np.mean([row["predicted_delta"] for row in rows])),
                "observed_delta_mean": float(np.mean([row["observed_delta"] for row in rows])),
                "calibration_gap": float(np.mean([row["predicted_delta"] - row["observed_delta"] for row in rows])),
            }
            for key, rows in sorted(buckets.items())
        }

    ordered_times = sorted(float(group["checkpoint_time_seconds"]) for group in groups)
    tail_boundary = _percentile(ordered_times, 75)
    return {
        "checkpoint_count": len(groups),
        "arm_sample_count": len(system_errors),
        "system_mae": float(np.mean(system_errors)),
        "private_mae": float(np.mean(private_errors)),
        "pairwise_ranking_accuracy": ranking_correct / len(groups),
        "beneficial_precision": beneficial_mutations / mutations if mutations else 0.0,
        "harmful_recall": harmful_rejected / harmful_alternatives if harmful_alternatives else 1.0,
        "expected_regret": float(np.mean(regrets)),
        "mutation_count": mutations,
        "mutation_decision_coverage": mutations / len(groups),
        "useful_opportunity_count": useful_opportunities,
        "useful_opportunity_coverage": captured_opportunities / useful_opportunities if useful_opportunities else 0.0,
        "harmful_mutation_count": harmful_mutations,
        "harmful_mutation_rate": harmful_mutations / mutations if mutations else 0.0,
        "safety_failure_count": safety_failures,
        "calibration_by_load": calibration(lambda group: group["load_scale"]),
        "calibration_by_branch": calibration(lambda group: group["branch_node"]),
        "calibration_by_time_tail": calibration(lambda group: "tail" if group["checkpoint_time_seconds"] >= tail_boundary else "body"),
    }


def select_t0_threshold(
    train_groups: Sequence[Mapping[str, Any]],
    validation_groups: Sequence[Mapping[str, Any]],
    *,
    metric: str = "target_queue_plus_incoming",
    quantiles: Sequence[float] = (0.50, 0.70, 0.85, 0.95),
    min_support: int = 8,
    margin_seconds: float = 0.5,
    g24_decision_summary_path: Path = G24_DECISION_SUMMARY_PATH,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Select one threshold and one of the two registered fairness caps."""

    _require(bool(train_groups) and bool(validation_groups), "T0 selection needs train and validation groups")
    _require(all(0.0 < value < 1.0 for value in quantiles), "T0 quantiles must be between zero and one")
    train_values = np.asarray([_gate_value(group, metric) for group in train_groups], dtype=float)
    candidates = sorted({float(np.quantile(train_values, value)) for value in quantiles})
    results: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    for enter in candidates:
        # Paired labels are a sparse sample of route events, while deployment
        # sees every event.  A stateful hysteresis sequence therefore cannot
        # be replayed faithfully offline; keep T0 as the intended simple,
        # stateless one-threshold control by setting exit == enter.
        exit_pressure = enter
        for private_cap_seconds in T0_FAIRNESS_CAP_CANDIDATES:
            artifact = build_t0_artifact(
                train_groups,
                metric=metric,
                enter_pressure=enter,
                exit_pressure=exit_pressure,
                min_support=min_support,
                margin_seconds=margin_seconds,
                private_cap_seconds=private_cap_seconds,
                g24_decision_summary_path=g24_decision_summary_path,
            )
            metrics = evaluate_artifact(validation_groups, artifact)
            metrics.update(
                {
                    "enter_pressure": enter,
                    "exit_pressure": exit_pressure,
                    "private_cap_seconds": private_cap_seconds,
                }
            )
            artifacts.append(artifact)
            results.append(metrics)
    best = min(
        range(len(results)),
        key=lambda index: (
            results[index]["safety_failure_count"],
            results[index]["harmful_mutation_rate"],
            results[index]["expected_regret"],
            -results[index]["beneficial_precision"],
            -results[index]["mutation_count"],
        ),
    )
    selected = artifacts[best]
    selected_metadata = selected.get("training_metadata", {})
    _require(
        isinstance(selected_metadata, Mapping),
        "selected T0 artifact lacks training metadata",
    )
    return selected, {
        "metric": metric,
        "threshold_candidate_count": len(candidates),
        "fairness_cap_candidates_seconds": list(T0_FAIRNESS_CAP_CANDIDATES),
        "candidate_count": len(results),
        "selected_index": best,
        "selection_folds": ["train", "validation"],
        "held_out_test_used_for_selection": False,
        "residual_source": selected_metadata.get(
            "residual_source", _g24_corridor_source(g24_decision_summary_path)
        ),
        "residual_refit_from_pairs": False,
        "candidates": results,
    }


def select_l1_ridge(
    train_groups: Sequence[Mapping[str, Any]],
    validation_groups: Sequence[Mapping[str, Any]],
    *,
    ridge_candidates: Sequence[float] = (0.1, 1.0, 10.0),
    min_support: int = 8,
    margin_seconds: float = 0.5,
    private_cap_seconds: float = 60.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    _require(1 <= len(ridge_candidates) <= 5, "use one to five bounded ridge candidates")
    artifacts: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    for ridge in ridge_candidates:
        artifact = fit_l1_ridge(
            train_groups,
            ridge=float(ridge),
            min_support=min_support,
            margin_seconds=margin_seconds,
            private_cap_seconds=private_cap_seconds,
        )
        metrics = evaluate_artifact(validation_groups, artifact)
        metrics["ridge"] = float(ridge)
        artifacts.append(artifact)
        results.append(metrics)
    best = min(
        range(len(results)),
        key=lambda index: (
            results[index]["safety_failure_count"],
            results[index]["harmful_mutation_rate"],
            results[index]["expected_regret"],
            -results[index]["pairwise_ranking_accuracy"],
            -results[index]["mutation_count"],
        ),
    )
    return artifacts[best], {"candidate_count": len(results), "selected_index": best, "candidates": results}


def decide_l2_trigger(ceilings: Mapping[str, Any], l1_metrics: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Apply the documented oracle trigger without manufacturing an L2 policy."""

    full = ceilings["full_state"]
    local = ceilings["local_observation"]
    reasons: list[str] = []
    if float(full["mean_possible_improvement_fraction"]) >= 0.01:
        reasons.append("full_state_mean_gain_at_least_1pct")
    if int(full["useful_opportunities"]) >= 100:
        reasons.append("at_least_100_useful_opportunities")
    if int(full["stable_action_reversal_branch_count"]) >= 2:
        reasons.append("stable_reversals_on_at_least_two_branches")
    if float(local["pairwise_ranking_ceiling"]) > float(local["s4_action_accuracy"]) + 0.02:
        reasons.append("local_ceiling_above_s4_ordering")
    if l1_metrics is not None and float(l1_metrics["pairwise_ranking_accuracy"]) > float(local["s4_action_accuracy"]) and float(l1_metrics["expected_regret"]) > 0.05 * max(float(full["mean_possible_improvement"]), 1.0e-9):
        reasons.append("l1_has_direction_but_remaining_regret")
    return {"triggered": bool(reasons), "reasons": reasons}


def fit_l2_tiny_mlp(
    groups: Sequence[Mapping[str, Any]],
    *,
    hidden_units: int = 16,
    alpha: float = 1.0e-3,
    random_state: int = 25,
    min_support: int = 8,
    margin_seconds: float = 0.5,
    private_cap_seconds: float = 60.0,
) -> dict[str, Any]:
    """Fit one deterministic, one-hidden-layer, two-output MLP."""

    _require(1 <= hidden_units <= 32, "tiny MLP hidden_units must be between 1 and 32")
    try:
        from sklearn.neural_network import MLPRegressor
    except ImportError as exc:  # pragma: no cover - project dependency in normal environments
        raise CLCRLearningError("scikit-learn is required only when L2 is triggered") from exc
    samples = _samples(groups)
    normalization = _normalization(samples)
    matrix = np.asarray([sample["features"] for sample in samples], dtype=float)
    matrix = (matrix - np.asarray(normalization["mean"])) / np.asarray(normalization["scale"])
    keys = sorted({sample["key"] for sample in samples})
    intercepts = {
        key: np.mean(
            np.asarray(
                [[sample["system_residual"], sample["private_delta"]] for sample in samples if sample["key"] == key],
                dtype=float,
            ),
            axis=0,
        )
        for key in keys
    }
    targets = np.asarray(
        [
            [sample["system_residual"], sample["private_delta"]] - intercepts[sample["key"]]
            for sample in samples
        ],
        dtype=float,
    )
    target_mean = targets.mean(axis=0)
    target_scale = targets.std(axis=0)
    target_scale[target_scale < 1.0e-9] = 1.0
    scaled_targets = (targets - target_mean) / target_scale
    model = MLPRegressor(
        hidden_layer_sizes=(hidden_units,),
        activation="relu",
        solver="lbfgs",
        alpha=alpha,
        max_iter=500,
        random_state=random_state,
        tol=1.0e-7,
    )
    model.fit(matrix, scaled_targets)
    output_weights = np.asarray(model.coefs_[1], dtype=float)
    output_bias = np.asarray(model.intercepts_[1], dtype=float)
    artifact = _common_artifact(
        mode="l2",
        groups=groups,
        normalization=normalization,
        model={
            "hidden_weights": np.asarray(model.coefs_[0], dtype=float).T.tolist(),
            "hidden_bias": np.asarray(model.intercepts_[0], dtype=float).tolist(),
            "hidden_system_weights": (output_weights[:, 0] * target_scale[0]).tolist(),
            "hidden_private_weights": (output_weights[:, 1] * target_scale[1]).tolist(),
            "hidden_system_bias": float(output_bias[0] * target_scale[0] + target_mean[0]),
            "hidden_private_bias": float(output_bias[1] * target_scale[1] + target_mean[1]),
        },
        min_support=min_support,
        margin_seconds=margin_seconds,
        private_cap_seconds=private_cap_seconds,
        training_metadata={
            "checkpoint_count": len(groups),
            "arm_sample_count": len(samples),
            "hidden_units": hidden_units,
            "alpha": alpha,
            "random_state": random_state,
            "system_target_semantics": "observed_local_system_arm_vs_s4_delta_minus_s4_score_delta",
            "private_target_semantics": "observed_private_arm_vs_s4_delta",
        },
    )
    descriptors = {(arm["branch_node"], arm["first_edge"]): arm for arm in artifact["arms"]}
    for key, values in intercepts.items():
        descriptors[key]["system_intercept"] = float(values[0])
        descriptors[key]["private_intercept"] = float(values[1])
    return artifact


def feedback_residual_correlation(groups: Sequence[Mapping[str, Any]], artifact: Mapping[str, Any]) -> float:
    residuals: list[float] = []
    feedback: list[list[float]] = []
    for sample in _samples(groups):
        predicted, _, ood = _predict(artifact, sample["group"], sample["arm"])
        if not ood:
            residuals.append(sample["system_residual"] - predicted)
            feedback.append([sample["features"][index] for index in (16, 17, 18, 19)])
    if len(residuals) < 3 or np.std(residuals) < 1.0e-12:
        return 0.0
    correlations: list[float] = []
    for column in np.asarray(feedback, dtype=float).T:
        if np.std(column) >= 1.0e-12:
            correlations.append(abs(float(np.corrcoef(residuals, column)[0, 1])))
    return max(correlations, default=0.0)


def decide_l3_trigger(
    validation_metrics: Mapping[str, Any],
    test_metrics: Mapping[str, Any],
    *,
    residual_feedback_correlation: float,
    load_direction_changed: bool = False,
) -> dict[str, Any]:
    reasons: list[str] = []
    validation_good = float(validation_metrics["pairwise_ranking_accuracy"]) >= 0.55
    chronological_drift = (
        float(test_metrics["pairwise_ranking_accuracy"]) + 0.05 < float(validation_metrics["pairwise_ranking_accuracy"])
        or float(test_metrics["system_mae"]) > 1.25 * max(float(validation_metrics["system_mae"]), 1.0e-9)
    )
    if validation_good and chronological_drift:
        reasons.append("validation_direction_with_chronological_test_drift")
    if load_direction_changed:
        reasons.append("load_direction_changed")
    if abs(float(residual_feedback_correlation)) >= 0.20:
        reasons.append("recent_corridor_feedback_explains_residual")
    return {
        "triggered": bool(reasons),
        "reasons": reasons,
        "residual_feedback_correlation": float(residual_feedback_correlation),
    }


def build_l3_bias_artifact(
    l1_artifact: Mapping[str, Any],
    *,
    short_alpha: float = 0.20,
    long_alpha: float = 0.02,
    bias_cap_seconds: float = 30.0,
    trigger: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    _require(l1_artifact.get("mode") == "l1", "L3 bias artifact requires the selected L1 base")
    _require(0.0 < short_alpha <= 1.0 and 0.0 < long_alpha <= 1.0, "L3 EWMA alphas must be in (0, 1]")
    _require(math.isfinite(bias_cap_seconds) and bias_cap_seconds >= 0.0, "L3 bias cap must be finite and non-negative")
    artifact = copy.deepcopy(dict(l1_artifact))
    artifact["mode"] = "l3"
    artifact["l3_short_alpha"] = float(short_alpha)
    artifact["l3_long_alpha"] = float(long_alpha)
    artifact["l3_bias_cap_seconds"] = float(bias_cap_seconds)
    artifact.setdefault("training_metadata", {})["l3_trigger"] = dict(trigger or {})
    return artifact


def train_evidence_ladder(
    groups: Sequence[Mapping[str, Any]],
    *,
    min_support: int = 8,
    margin_seconds: float = 0.5,
    private_cap_seconds: float = 60.0,
    g24_decision_summary_path: Path = G24_DECISION_SUMMARY_PATH,
    input_dataset_path: Path | None = None,
) -> dict[str, Any]:
    """Run the bounded T0/L1/L2/L3 decision ladder on measured evidence."""

    resolved_g24_source = g24_decision_summary_path.expanduser().resolve()
    split = checkpoint_group_chronological_split(groups)
    # The all-row ceiling remains a descriptive oracle. Optional model
    # complexity is decided without the chronological test tail.
    ceilings = compute_action_ceilings(groups)
    trigger_groups = [*split["train"], *split["validation"]]
    l2_trigger_ceilings = compute_action_ceilings(trigger_groups)
    t0, t0_selection = select_t0_threshold(
        split["train"],
        split["validation"],
        min_support=min_support,
        margin_seconds=margin_seconds,
        g24_decision_summary_path=resolved_g24_source,
    )
    l1, l1_selection = select_l1_ridge(
        split["train"],
        split["validation"],
        min_support=min_support,
        margin_seconds=margin_seconds,
        private_cap_seconds=private_cap_seconds,
    )
    metrics = {
        "t0_validation": evaluate_artifact(split["validation"], t0),
        "t0_test": evaluate_artifact(split["test"], t0),
        "l1_validation": evaluate_artifact(split["validation"], l1),
        "l1_test": evaluate_artifact(split["test"], l1),
    }
    l2_trigger = decide_l2_trigger(
        l2_trigger_ceilings, metrics["l1_validation"]
    )
    l2_trigger["evidence_scope"] = "TRAIN_AND_VALIDATION_ONLY"
    l2_trigger["checkpoint_count"] = len(trigger_groups)
    artifacts: dict[str, dict[str, Any]] = {"t0": t0, "l1": l1}
    if l2_trigger["triggered"]:
        l2 = fit_l2_tiny_mlp(
            split["train"],
            min_support=min_support,
            margin_seconds=margin_seconds,
            private_cap_seconds=private_cap_seconds,
        )
        artifacts["l2"] = l2
        metrics["l2_validation"] = evaluate_artifact(split["validation"], l2)
        metrics["l2_test"] = evaluate_artifact(split["test"], l2)
    correlation = feedback_residual_correlation(split["test"], l1)
    l3_trigger = decide_l3_trigger(
        metrics["l1_validation"],
        metrics["l1_test"],
        residual_feedback_correlation=correlation,
    )
    if l3_trigger["triggered"]:
        artifacts["l3"] = build_l3_bias_artifact(l1, trigger=l3_trigger)
    return {
        "split_counts": {name: len(rows) for name, rows in split.items()},
        "ceilings": ceilings,
        "l2_trigger_ceilings": l2_trigger_ceilings,
        "t0_selection": t0_selection,
        "l1_selection": l1_selection,
        "l2_trigger": l2_trigger,
        "l3_trigger": l3_trigger,
        "metrics": metrics,
        "provenance": {
            "paired_input_dataset": (
                _portable_evidence_path(input_dataset_path)
                if input_dataset_path is not None
                else "IN_MEMORY_GROUPS"
            ),
            "g24_corridor_source": _g24_corridor_source(
                resolved_g24_source
            ),
        },
        "artifacts": artifacts,
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


MODEL_METRIC_FIELDS = (
    "model",
    "split",
    "checkpoint_count",
    "arm_sample_count",
    "system_mae_seconds",
    "private_mae_seconds",
    "pairwise_ranking_accuracy",
    "beneficial_precision",
    "harmful_recall",
    "expected_regret_seconds",
    "mutation_count",
    "mutation_decision_coverage",
    "useful_opportunity_count",
    "useful_opportunity_coverage",
    "harmful_mutation_count",
    "harmful_mutation_rate",
    "safety_failure_count",
)


def _model_metric_rows(metrics: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Flatten measured validation/test metrics without inventing missing stages."""

    rows: list[dict[str, Any]] = []
    for model in ("t0", "l1", "l2", "l3"):
        for split in ("validation", "test"):
            raw = metrics.get(f"{model}_{split}")
            if not isinstance(raw, Mapping):
                continue
            rows.append(
                {
                    "model": model,
                    "split": split,
                    "checkpoint_count": raw.get("checkpoint_count", ""),
                    "arm_sample_count": raw.get("arm_sample_count", ""),
                    "system_mae_seconds": raw.get("system_mae", ""),
                    "private_mae_seconds": raw.get("private_mae", ""),
                    "pairwise_ranking_accuracy": raw.get("pairwise_ranking_accuracy", ""),
                    "beneficial_precision": raw.get("beneficial_precision", ""),
                    "harmful_recall": raw.get("harmful_recall", ""),
                    "expected_regret_seconds": raw.get("expected_regret", ""),
                    "mutation_count": raw.get("mutation_count", ""),
                    "mutation_decision_coverage": raw.get("mutation_decision_coverage", ""),
                    "useful_opportunity_count": raw.get("useful_opportunity_count", ""),
                    "useful_opportunity_coverage": raw.get("useful_opportunity_coverage", ""),
                    "harmful_mutation_count": raw.get("harmful_mutation_count", ""),
                    "harmful_mutation_rate": raw.get("harmful_mutation_rate", ""),
                    "safety_failure_count": raw.get("safety_failure_count", ""),
                }
            )
    return rows


def write_model_metrics_csv(path: Path, metrics: Mapping[str, Any]) -> None:
    """Write one compact row per actually evaluated model/split."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=MODEL_METRIC_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(_model_metric_rows(metrics))


def _report_value(value: Any) -> str:
    if value is None or value == "":
        return "NOT_MEASURED"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.6f}"
    if isinstance(value, (list, tuple)):
        return ", ".join(_report_value(item) for item in value) or "none"
    return str(value)


def _metric_markdown_rows(metrics: Mapping[str, Any], model: str) -> list[str]:
    rows: list[str] = []
    for split in ("validation", "test"):
        raw = metrics.get(f"{model}_{split}")
        if not isinstance(raw, Mapping):
            continue
        rows.append(
            "| {split} | {mae} | {ranking} | {precision} | {harm} | {regret} | {mutations} | {safety} |".format(
                split=split,
                mae=_report_value(raw.get("system_mae")),
                ranking=_report_value(raw.get("pairwise_ranking_accuracy")),
                precision=_report_value(raw.get("beneficial_precision")),
                harm=_report_value(raw.get("harmful_mutation_rate")),
                regret=_report_value(raw.get("expected_regret")),
                mutations=_report_value(raw.get("mutation_count")),
                safety=_report_value(raw.get("safety_failure_count")),
            )
        )
    return rows


def write_threshold_report(
    path: Path,
    result: Mapping[str, Any],
    artifacts: Mapping[str, Mapping[str, Any]],
) -> None:
    """Document the frozen-residual T0 gate and its untouched test result."""

    artifact = artifacts.get("t0", {})
    selection = result.get("t0_selection", {})
    metrics = result.get("metrics", {})
    if not isinstance(selection, Mapping):
        selection = {}
    if not isinstance(metrics, Mapping):
        metrics = {}
    metadata = artifact.get("training_metadata", {}) if isinstance(artifact, Mapping) else {}
    if not isinstance(metadata, Mapping):
        metadata = {}
    provenance = result.get("provenance", {})
    if not isinstance(provenance, Mapping):
        provenance = {}
    table_rows = _metric_markdown_rows(metrics, "t0")
    lines = [
        "# G4IRSF25 T0 threshold gate",
        "",
        "Status: TRAINED_FROM_PAIRED_EVIDENCE",
        "",
        "## Evidence inputs",
        "",
        f"- Paired dataset: `{_report_value(provenance.get('paired_input_dataset'))}`",
        f"- G24 corridor source: `{_report_value(provenance.get('g24_corridor_source', metadata.get('residual_source')))}`",
        "",
        "## Frozen G24 residual",
        "",
        f"- Contract: `{_report_value(metadata.get('residual_contract', 'FROZEN_G24_NO_PAIRED_REFIT'))}`",
        f"- Source: `{_report_value(metadata.get('residual_source', G24_CORRIDOR_SOURCE))}`",
        "- G25 paired labels select only the gate and fairness cap; they do not refit the eight G24 arm residuals.",
        "- Per-arm private estimates remain the frozen G24 `dynamic_duration_seconds` values.",
        "",
        "## Selected bounded gate",
        "",
        f"- Metric: `{_report_value(artifact.get('t0_metric'))}`",
        f"- Single threshold: `{_report_value(artifact.get('t0_enter_pressure'))}`",
        f"- Exit threshold: `{_report_value(artifact.get('t0_exit_pressure'))}` (equal to entry; no sparse-offline hysteresis reconstruction)",
        f"- Registered fairness-cap search: `{_report_value(selection.get('fairness_cap_candidates_seconds', list(T0_FAIRNESS_CAP_CANDIDATES)))}` seconds",
        f"- Selected private cap: `{_report_value(artifact.get('private_cap_seconds'))}` seconds",
        f"- Threshold candidates: `{_report_value(selection.get('threshold_candidate_count'))}`",
        "",
        "## Held-out protocol",
        "",
        f"- Selection folds: `{_report_value(selection.get('selection_folds', ['train', 'validation']))}`",
        f"- Held-out test used for selection: `{_report_value(selection.get('held_out_test_used_for_selection', False))}`",
        "- The chronological test tail is evaluated once after threshold/cap selection.",
        "",
        "| split | system MAE (s) | ranking | beneficial precision | harmful mutation rate | regret (s) | mutations | safety failures |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        *(table_rows or ["| NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |"]),
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_contextual_report(
    path: Path,
    result: Mapping[str, Any],
    artifacts: Mapping[str, Mapping[str, Any]],
) -> None:
    """Document ceilings, L1 evidence, and evidence-gated optional stages."""

    ceilings = result.get("ceilings", {})
    full = ceilings.get("full_state", {}) if isinstance(ceilings, Mapping) else {}
    local = ceilings.get("local_observation", {}) if isinstance(ceilings, Mapping) else {}
    metrics = result.get("metrics", {})
    if not isinstance(full, Mapping):
        full = {}
    if not isinstance(local, Mapping):
        local = {}
    if not isinstance(metrics, Mapping):
        metrics = {}
    provenance = result.get("provenance", {})
    if not isinstance(provenance, Mapping):
        provenance = {}
    l2_trigger = result.get("l2_trigger", {})
    l3_trigger = result.get("l3_trigger", {})
    if not isinstance(l2_trigger, Mapping):
        l2_trigger = {}
    if not isinstance(l3_trigger, Mapping):
        l3_trigger = {}

    def trigger_lines(level: str, trigger: Mapping[str, Any]) -> list[str]:
        triggered = bool(trigger.get("triggered", False))
        reasons = trigger.get("reasons", [])
        status = "TRIGGERED" if triggered else "NOT_TRIGGERED"
        lines = [
            f"### {level}",
            "",
            f"- Status: `{status}`",
            f"- Evidence reasons: `{_report_value(reasons)}`",
            f"- Artifact emitted: `{_report_value(level.lower() in artifacts)}`",
        ]
        if level == "L3":
            lines.extend(
                [
                    f"- Residual/feedback correlation: `{_report_value(trigger.get('residual_feedback_correlation'))}`",
                    "- Adaptive online benefit is `NOT_MEASURED` here; it requires native closed-loop evidence and is not fabricated from static pairs.",
                ]
            )
        elif not triggered:
            lines.append("- Metrics: `NOT_MEASURED` because this optional model was not trained.")
        return lines

    l1_rows = _metric_markdown_rows(metrics, "l1")
    l2_rows = _metric_markdown_rows(metrics, "l2")
    lines = [
        "# G4IRSF25 contextual corridor learning",
        "",
        "Status: OFFLINE_EVIDENCE_COMPLETE; native policy selection is intentionally outside this report.",
        "",
        "## Evidence inputs",
        "",
        f"- Paired dataset: `{_report_value(provenance.get('paired_input_dataset'))}`",
        f"- G24 corridor source: `{_report_value(provenance.get('g24_corridor_source'))}`",
        "- Paths are trace metadata only and are not runtime model features.",
        "",
        "## Action and opportunity ceilings",
        "",
        f"- Full-state useful opportunities: `{_report_value(full.get('useful_opportunities'))}` / `{_report_value(full.get('branch_decisions'))}`",
        f"- Full-state mean possible improvement fraction: `{_report_value(full.get('mean_possible_improvement_fraction'))}`",
        f"- Opportunity mass: `{_report_value(ceilings.get('opportunity_mass') if isinstance(ceilings, Mapping) else None)}`",
        f"- Stable reversal branches: `{_report_value(full.get('stable_action_reversal_branches'))}`",
        f"- Local-observation ranking ceiling: `{_report_value(local.get('pairwise_ranking_ceiling'))}`",
        f"- S4 action accuracy in the same paired rows: `{_report_value(local.get('s4_action_accuracy'))}`",
        f"- Local ceiling mean regret: `{_report_value(local.get('mean_local_regret_ceiling'))}` seconds",
        "",
        "## L1 two-head ridge",
        "",
        "| split | system MAE (s) | ranking | beneficial precision | harmful mutation rate | regret (s) | mutations | safety failures |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        *(l1_rows or ["| NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |"]),
        "",
        "## Optional evidence gates",
        "",
        *trigger_lines("L2", l2_trigger),
    ]
    if l2_rows:
        lines.extend(
            [
                "",
                "| split | system MAE (s) | ranking | beneficial precision | harmful mutation rate | regret (s) | mutations | safety failures |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
                *l2_rows,
            ]
        )
    lines.extend(["", *trigger_lines("L3", l3_trigger), ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _stage_and_publish_outputs(
    writers: Sequence[tuple[Path, Callable[[Path], None]]],
    *,
    remove_after_success: Sequence[Path] = (),
) -> None:
    """Fully stage sibling files before replacing any published output."""

    normalized = [
        (target.expanduser().resolve(), writer) for target, writer in writers
    ]
    targets = [target for target, _writer in normalized]
    _require(len(targets) == len(set(targets)), "learning output paths must be unique")
    removals = [path.expanduser().resolve() for path in remove_after_success]
    _require(
        not (set(targets) & set(removals)),
        "a current learning output cannot also be retired",
    )
    staged: list[tuple[Path, Path]] = []
    try:
        for target, writer in normalized:
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
            )
            os.close(descriptor)
            temporary = Path(temporary_name)
            try:
                writer(temporary)
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
            staged.append((target, temporary))

        prior = {
            path: path.read_bytes() if path.is_file() else None
            for path in [*targets, *removals]
        }
        try:
            for target, temporary in staged:
                os.replace(temporary, target)
            for obsolete in removals:
                obsolete.unlink(missing_ok=True)
        except BaseException:
            # Publishing spans several directories, so restore the small prior
            # files if a replace/remove fails after staging completed.
            for path, payload in prior.items():
                if payload is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(payload)
            raise
    finally:
        for _target, temporary in staged:
            temporary.unlink(missing_ok=True)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Measured compact paired JSON or JSONL")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--min-support", type=int, default=8)
    parser.add_argument("--margin-seconds", type=float, default=0.5)
    parser.add_argument("--private-cap-seconds", type=float, default=60.0)
    parser.add_argument(
        "--model-metrics-csv",
        type=Path,
        default=MODEL_METRICS_PATH,
        help="Per-model validation/test metrics CSV (defaults to the exact repository delivery path)",
    )
    parser.add_argument(
        "--threshold-report",
        type=Path,
        default=THRESHOLD_REPORT_PATH,
        help="T0 evidence report (defaults to the exact repository delivery path)",
    )
    parser.add_argument(
        "--contextual-report",
        type=Path,
        default=CONTEXTUAL_REPORT_PATH,
        help="Contextual learning evidence report (defaults to the exact repository delivery path)",
    )
    parser.add_argument(
        "--g24-decision-summary",
        type=Path,
        default=G24_DECISION_SUMMARY_PATH,
        help="Published G24 decision summary containing the frozen eight-arm corridor residual",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        resolved_input = args.input.expanduser().resolve()
        resolved_g24_source = args.g24_decision_summary.expanduser().resolve()
        groups = read_compact_pairs(resolved_input)
        result = train_evidence_ladder(
            groups,
            min_support=args.min_support,
            margin_seconds=args.margin_seconds,
            private_cap_seconds=args.private_cap_seconds,
            g24_decision_summary_path=resolved_g24_source,
            input_dataset_path=resolved_input,
        )
        artifacts = result["artifacts"]
        evidence = {key: value for key, value in result.items() if key != "artifacts"}
        evidence["provenance"] = {
            "paired_input_dataset": _portable_evidence_path(resolved_input),
            "g24_corridor_source": _g24_corridor_source(resolved_g24_source),
        }

        writers: list[tuple[Path, Callable[[Path], None]]] = []
        for name, artifact in artifacts.items():
            _require(name in ARTIFACT_FILENAMES, f"unknown learning artifact {name}")
            writers.append(
                (
                    args.output_dir / ARTIFACT_FILENAMES[name],
                    lambda path, payload=artifact: _write_json(path, payload),
                )
            )
        writers.extend(
            [
                (
                    args.output_dir / "g4irsf25_clcr_learning_evidence.json",
                    lambda path: _write_json(path, evidence),
                ),
                (
                    args.model_metrics_csv,
                    lambda path: write_model_metrics_csv(
                        path, evidence.get("metrics", {})
                    ),
                ),
                (
                    args.threshold_report,
                    lambda path: write_threshold_report(
                        path, evidence, artifacts
                    ),
                ),
                (
                    args.contextual_report,
                    lambda path: write_contextual_report(
                        path, evidence, artifacts
                    ),
                ),
            ]
        )
        stale_optional = [
            args.output_dir / ARTIFACT_FILENAMES[name]
            for name in ("l2", "l3")
            if name not in artifacts
        ]
        _stage_and_publish_outputs(
            writers, remove_after_success=stale_optional
        )
        print(json.dumps({"checkpoint_count": len(groups), "outputs": str(args.output_dir)}, sort_keys=True))
        return 0
    except (CLCRLearningError, OSError, json.JSONDecodeError, np.linalg.LinAlgError) as exc:
        print(f"G25 CLCR learning failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
