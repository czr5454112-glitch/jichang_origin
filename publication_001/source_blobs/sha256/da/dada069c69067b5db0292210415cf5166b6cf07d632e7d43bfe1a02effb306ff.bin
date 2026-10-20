"""Leakage-safe offline evaluation for G4IRSF16.

This module deliberately keeps scientific outcomes separate from the runtime
model contract.  Rule parameters are derived from ``train`` only, model
thresholds from ``calibration`` only, and promotion is decided on
``validation``.  ``final_audit`` rows are never read by the selection helpers.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from .model import DEPLOYMENT_FEATURES, one_sided_mean_lcb


SELECTABLE_SPLITS = ("train", "calibration", "validation")
I4_GATE = {
    "beneficial_precision_min": 0.90,
    "harmful_activation_rate_max": 0.005,
    "high_confidence_harmful_rate_max": 0.005,
    "ece_max": 0.08,
    "activation_coverage_min": 0.0025,
    "activation_coverage_max": 0.05,
    "risk_adjusted_utility_lcb_min_exclusive": 0.0,
}
I3_GATE = {
    "beneficial_precision_min": 0.95,
    "harmful_activation_rate_max": 0.0025,
}
RISK_BUDGETS = {
    "B0_conservative": {
        "externality_probability_ucb": 0.10,
        "cvar95_seconds": 0.5,
        "promotion_allowed": True,
    },
    "B1_balanced": {
        "externality_probability_ucb": 0.25,
        "cvar95_seconds": 2.0,
        "promotion_allowed": True,
    },
    "B2_permissive_diagnostic": {
        "externality_probability_ucb": 0.50,
        "cvar95_seconds": 10.0,
        "promotion_allowed": False,
    },
}


class OfflineContractError(ValueError):
    """Raised when a split, feature, or audit boundary is violated."""


@dataclass(frozen=True)
class RuleDefinition:
    name: str
    description: str
    mask: Callable[[Mapping[str, Any]], bool]
    parameters: Mapping[str, float] = field(default_factory=dict)


def selectable_rows(rows: Sequence[Mapping[str, Any]], split: str) -> list[Mapping[str, Any]]:
    if split not in SELECTABLE_SPLITS:
        raise OfflineContractError(f"FINAL_AUDIT_SELECTION_FORBIDDEN:{split}")
    selected = [row for row in rows if row.get("split") == split]
    if any(row.get("final_audit_status") == "SEALED_NOT_CONSUMED" for row in selected):
        raise OfflineContractError("FINAL_AUDIT_ROW_ENTERED_SELECTION")
    return selected


def deployment_matrix(rows: Sequence[Mapping[str, Any]]) -> np.ndarray:
    values: list[list[float]] = []
    for row in rows:
        projected: list[float] = []
        for name in DEPLOYMENT_FEATURES:
            value = row.get(name)
            if value is None:
                projected.append(float("nan"))
            elif isinstance(value, bool) or not isinstance(value, (int, float)):
                raise OfflineContractError(f"NON_NUMERIC_DEPLOYMENT_FEATURE:{name}")
            else:
                projected.append(float(value))
        values.append(projected)
    return np.asarray(values, dtype=float)


def observed_utility(row: Mapping[str, Any]) -> float:
    """Use H_system risk utility when observed, otherwise direct benefit."""

    risk_utility = row.get("risk_adjusted_utility_seconds")
    if risk_utility is not None:
        return float(risk_utility)
    return float(row["direct_benefit_seconds"])


def _finite(values: Sequence[float]) -> list[float]:
    return [float(value) for value in values if math.isfinite(float(value))]


def activation_summary(
    rows: Sequence[Mapping[str, Any]],
    activations: Sequence[bool],
) -> dict[str, Any]:
    if len(rows) != len(activations):
        raise OfflineContractError("ACTIVATION_ROW_COUNT_MISMATCH")
    activated = [row for row, flag in zip(rows, activations, strict=True) if flag]
    label_counts = Counter(str(row["signed_class"]) for row in activated)
    utilities = _finite([observed_utility(row) for row in activated])
    direct = _finite([float(row["direct_benefit_seconds"]) for row in activated])
    cvars = _finite(
        [
            float(row["other_bag_cvar95_harm_seconds"])
            for row in activated
            if row.get("other_bag_cvar95_harm_seconds") is not None
        ]
    )
    count = len(rows)
    activation_count = len(activated)
    beneficial = label_counts["BENEFICIAL"]
    harmful = label_counts["HARMFUL"]
    neutral = activation_count - beneficial - harmful
    total_beneficial = sum(row["signed_class"] == "BENEFICIAL" for row in rows)
    return {
        "row_count": count,
        "activation_count": activation_count,
        "activation_coverage": activation_count / count if count else 0.0,
        "beneficial_activation_count": beneficial,
        "harmful_activation_count": harmful,
        "neutral_activation_count": neutral,
        "beneficial_precision": beneficial / activation_count if activation_count else 0.0,
        "beneficial_recall": beneficial / total_beneficial if total_beneficial else 0.0,
        # Harmful activation is an eligible-state budget, not classifier recall.
        "harmful_activation_rate": harmful / count if count else 0.0,
        "high_confidence_harmful_precision": (
            harmful / activation_count if activation_count else 0.0
        ),
        "neutral_activation_rate": neutral / count if count else 0.0,
        "target_panel_abstention_rate": (
            1.0 - activation_count / count if count else 1.0
        ),
        "direct_benefit_sum_seconds": math.fsum(direct),
        "direct_benefit_mean_seconds": statistics.fmean(direct) if direct else None,
        "risk_adjusted_utility_sum_seconds": math.fsum(utilities),
        "risk_adjusted_utility_mean_seconds": statistics.fmean(utilities) if utilities else None,
        "risk_adjusted_utility_lcb_seconds": (
            one_sided_mean_lcb(utilities) if len(utilities) >= 2 else None
        ),
        "externality_cvar95_mean_seconds": statistics.fmean(cvars) if cvars else None,
        "externality_cvar95_max_seconds": max(cvars) if cvars else None,
    }


def _quantile(rows: Sequence[Mapping[str, Any]], name: str, q: float) -> float:
    values = [
        float(row[name])
        for row in rows
        if row.get(name) is not None and math.isfinite(float(row[name]))
    ]
    if not values:
        raise OfflineContractError(f"RULE_FEATURE_UNOBSERVED:{name}")
    return float(np.quantile(np.asarray(values, dtype=float), q))


def _number(row: Mapping[str, Any], name: str) -> float | None:
    value = row.get(name)
    if value is None or isinstance(value, bool):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _all(*checks: bool) -> bool:
    return all(checks)


def i4_rules(train_rows: Sequence[Mapping[str, Any]]) -> tuple[RuleDefinition, ...]:
    age95 = _quantile(train_rows, "wait_age_seconds", 0.95)
    age75 = _quantile(train_rows, "wait_age_seconds", 0.75)
    slack75 = _quantile(train_rows, "deadline_slack_seconds", 0.75)
    queue90 = _quantile(train_rows, "target_queue_length", 0.90)
    target_wait90 = _quantile(train_rows, "target_next_available_wait_seconds", 0.90)
    margin10 = _quantile(train_rows, "f2_model_margin", 0.10)
    incoming75 = _quantile(train_rows, "target_scheduled_incoming", 0.75)
    queue25 = _quantile(train_rows, "target_queue_length", 0.25)
    incoming25 = _quantile(train_rows, "target_scheduled_incoming", 0.25)

    def ge(row: Mapping[str, Any], name: str, threshold: float) -> bool:
        value = _number(row, name)
        return value is not None and value >= threshold

    def le(row: Mapping[str, Any], name: str, threshold: float) -> bool:
        value = _number(row, name)
        return value is not None and value <= threshold

    return (
        RuleDefinition("H0", "never hold; exact frozen F2", lambda row: False),
        RuleDefinition(
            "H1",
            f"wait_age >= train p95 ({age95:.6g})",
            lambda row: ge(row, "wait_age_seconds", age95),
            {"wait_age_seconds_min": age95},
        ),
        RuleDefinition(
            "H2",
            "wait-age and slack train upper-quartile",
            lambda row: _all(ge(row, "wait_age_seconds", age75), ge(row, "deadline_slack_seconds", slack75)),
        ),
        RuleDefinition(
            "H3",
            "destination queue/calendar train p90",
            lambda row: ge(row, "target_queue_length", queue90) or ge(row, "target_next_available_wait_seconds", target_wait90),
        ),
        RuleDefinition(
            "H4",
            "storage-out aware with positive wait",
            lambda row: _all(bool(row.get("storage_out_leg")), ge(row, "wait_age_seconds", age75)),
        ),
        RuleDefinition(
            "H5",
            "low F2 margin plus local contention",
            lambda row: _all(
                le(row, "f2_model_margin", margin10),
                ge(row, "target_queue_length", queue90),
                ge(row, "target_scheduled_incoming", incoming75),
            ),
            {
                "f2_model_margin_max": margin10,
                "target_queue_length_min": queue90,
                "target_scheduled_incoming_min": incoming75,
            },
        ),
        RuleDefinition(
            "H6",
            "conservative local externality proxy",
            lambda row: _all(
                le(row, "target_queue_length", queue25),
                le(row, "target_scheduled_incoming", incoming25),
                ge(row, "deadline_slack_seconds", 0.0),
                not bool(row.get("advertised_fault")),
            ),
        ),
    )


def i3_rules(train_rows: Sequence[Mapping[str, Any]]) -> tuple[RuleDefinition, ...]:
    queue25 = _quantile(train_rows, "target_queue_length", 0.25)
    wait25 = _quantile(train_rows, "target_next_available_wait_seconds", 0.25)
    margin10 = _quantile(train_rows, "f2_model_margin", 0.10)

    subgroup_counts: dict[tuple[str, int], Counter[str]] = {}
    for row in train_rows:
        key = (str(row.get("task_class")), int(row.get("current_node_type", -1)))
        subgroup_counts.setdefault(key, Counter())[str(row["signed_class"])] += 1
    eligible_groups = [
        (counts["BENEFICIAL"] / sum(counts.values()), sum(counts.values()), key)
        for key, counts in subgroup_counts.items()
        if counts["BENEFICIAL"] >= 2
    ]
    verified_group = max(eligible_groups, default=(0.0, 0, ("NONE", -1)))[2]

    def value(row: Mapping[str, Any], name: str) -> float | None:
        return _number(row, name)

    def improving(row: Mapping[str, Any]) -> bool:
        delta = value(row, "static_potential_delta_seconds")
        # The data/runtime contract defines positive as an intervention with
        # lower remaining static route cost than frozen F2.
        return delta is not None and delta > 0.0

    def low_risk(row: Mapping[str, Any]) -> bool:
        queue = value(row, "target_queue_length")
        wait = value(row, "target_next_available_wait_seconds")
        return queue is not None and wait is not None and queue <= queue25 and wait <= wait25

    def positive_slack(row: Mapping[str, Any]) -> bool:
        slack = _number(row, "deadline_slack_seconds")
        return slack is not None and slack > 0.0

    def low_margin(row: Mapping[str, Any]) -> bool:
        margin = _number(row, "f2_model_margin")
        return margin is not None and margin <= margin10

    return (
        RuleDefinition("R0", "never override; exact frozen F2", lambda row: False),
        RuleDefinition("R1", "permit only improving static potential", improving),
        RuleDefinition("R2", "static potential plus low local queue/calendar risk", lambda row: improving(row) and low_risk(row)),
        RuleDefinition(
            "R3",
            f"train-only verified ID-free subgroup task_class/node_type={verified_group}",
            lambda row: (str(row.get("task_class")), int(row.get("current_node_type", -1))) == verified_group and improving(row),
        ),
        RuleDefinition(
            "R4",
            "ID-free conservative potential/slack/margin/fault rule",
            lambda row: _all(
                improving(row),
                positive_slack(row),
                low_margin(row),
                not bool(row.get("advertised_fault")),
            ),
        ),
    )


def evaluate_rules(
    rows: Sequence[Mapping[str, Any]],
    rules: Sequence[RuleDefinition],
    *,
    kind: str,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for split in SELECTABLE_SPLITS:
        split_rows = selectable_rows(rows, split)
        for rule in rules:
            summary = activation_summary(split_rows, [rule.mask(row) for row in split_rows])
            output.append(
                {
                    "schema": "czr005.g4irsf16.rule_ab.v1",
                    "kind": kind,
                    "rule": rule.name,
                    "split": split,
                    "description": rule.description,
                    "parameters": dict(rule.parameters),
                    **summary,
                }
            )
    return output


def choose_rule(rule_rows: Sequence[Mapping[str, Any]], *, kind: str) -> tuple[str, bool]:
    gate = I4_GATE if kind == "I4" else I3_GATE
    calibration = [row for row in rule_rows if row["split"] == "calibration"]
    ranked = sorted(
        [row for row in calibration if int(row["activation_count"]) > 0],
        key=lambda row: (
            int(float(row["harmful_activation_rate"]) <= gate["harmful_activation_rate_max"]),
            int((row["risk_adjusted_utility_lcb_seconds"] or -math.inf) > 0.0),
            float(row["beneficial_precision"]),
            -(float(row["harmful_activation_rate"])),
            float(row["risk_adjusted_utility_lcb_seconds"] or -math.inf),
            -(float(row["activation_coverage"])),
        ),
        reverse=True,
    )
    chosen = ranked[0] if ranked else None
    if chosen is None:
        return ("H0" if kind == "I4" else "R0", False)
    validation = next(
        row
        for row in rule_rows
        if row["split"] == "validation" and row["rule"] == chosen["rule"]
    )
    promoted = (
        validation["activation_count"] > 0
        and float(validation["beneficial_precision"]) >= gate["beneficial_precision_min"]
        and float(validation["harmful_activation_rate"]) <= gate["harmful_activation_rate_max"]
        and (validation["risk_adjusted_utility_lcb_seconds"] or -math.inf) > 0.0
    )
    return str(chosen["rule"]), bool(promoted)


def gate_i4(metrics: Mapping[str, Any], *, ece: float) -> dict[str, Any]:
    checks = {
        "beneficial_precision": float(metrics["beneficial_precision"]) >= I4_GATE["beneficial_precision_min"],
        "harmful_activation_rate": float(metrics["harmful_activation_rate"]) <= I4_GATE["harmful_activation_rate_max"],
        "high_confidence_harmful_precision": float(metrics["high_confidence_harmful_precision"]) <= I4_GATE["high_confidence_harmful_rate_max"],
        "ece": float(ece) <= I4_GATE["ece_max"],
        "coverage_lower": float(metrics["activation_coverage"]) >= I4_GATE["activation_coverage_min"],
        "coverage_upper": float(metrics["activation_coverage"]) <= I4_GATE["activation_coverage_max"],
        "utility_lcb": (metrics["risk_adjusted_utility_lcb_seconds"] or -math.inf) > 0.0,
        "activation_support": int(metrics["activation_count"]) > 0,
    }
    return {
        "status": "PASS_I4_OFFLINE_GATE" if all(checks.values()) else "I4_SELECTIVE_MODEL_NO_GO",
        "checks": checks,
        "thresholds": dict(I4_GATE),
        "metrics": dict(metrics),
        "ece": float(ece),
    }


def oracle_rows(rows: Sequence[Mapping[str, Any]], *, kind: str) -> list[dict[str, Any]]:
    panel = [row for row in rows if row.get("split") in SELECTABLE_SPLITS]
    ordered = sorted(panel, key=observed_utility, reverse=True)
    output: list[dict[str, Any]] = []
    for coverage in (0.0025, 0.005, 0.01, 0.02, 0.05, 1.0):
        count = len(panel) if coverage == 1.0 else max(1, math.ceil(len(panel) * coverage))
        chosen_ids = {id(row) for row in ordered[:count] if observed_utility(row) > 0.0}
        summary = activation_summary(panel, [id(row) in chosen_ids for row in panel])
        output.append(
            {
                "schema": "czr005.g4irsf16.oracle_coverage.v1",
                "kind": kind,
                "oracle": "risk_constrained" if coverage == 1.0 else f"top_{coverage * 100:g}_percent",
                "selection_partition": "train+calibration+validation;final_audit_sealed",
                **summary,
            }
        )
    return output


def authorization(rows_i3: Sequence[Mapping[str, Any]], rows_i4: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def support(rows: Sequence[Mapping[str, Any]]) -> dict[str, Counter[str]]:
        return {
            split: Counter(str(row["signed_class"]) for row in rows if row.get("split") == split)
            for split in SELECTABLE_SPLITS
        }

    i3 = support(rows_i3)
    i4 = support(rows_i4)
    i3_checks = {
        "beneficial_train_ge_24": i3["train"]["BENEFICIAL"] >= 24,
        "beneficial_calibration_ge_6": i3["calibration"]["BENEFICIAL"] >= 6,
        "beneficial_validation_ge_6": i3["validation"]["BENEFICIAL"] >= 6,
    }
    i4_total = sum((counts for counts in i4.values()), Counter())
    i4_checks = {
        "beneficial_selectable_total_ge_24": i4_total["BENEFICIAL"] >= 24,
        "harmful_selectable_total_ge_128": i4_total["HARMFUL"] >= 128,
        "train_has_beneficial": i4["train"]["BENEFICIAL"] > 0,
        "calibration_has_beneficial": i4["calibration"]["BENEFICIAL"] > 0,
        "validation_has_beneficial": i4["validation"]["BENEFICIAL"] > 0,
    }
    i3_preaudit_authorized = all(i3_checks.values())
    i4_authorized = all(i4_checks.values())
    return {
        "schema": "czr005.g4irsf16.learning_task_authorization.v1",
        "selection_policy": "train_fit;calibration_thresholds;validation_promotion;final_audit_sealed",
        "i3_rare_override": {
            "status": (
                "I3_PENDING_FINAL_AUDIT"
                if i3_preaudit_authorized
                else "I3_REROUTE_MODEL_NOT_AUTHORIZED"
            ),
            "checks": i3_checks,
            "support": {split: dict(counts) for split, counts in i3.items()},
            "final_audit_gate": "NOT_EVALUATED_SEALED",
            "risk_veto_training_authorized": True,
            "candidate_complete_campaign_authorized": False,
        },
        "i4_selective_hold": {
            "status": "AUTHORIZED_FOR_OFFLINE_TRAINING" if i4_authorized else "NOT_AUTHORIZED",
            "checks": i4_checks,
            "support": {split: dict(counts) for split, counts in i4.items()},
        },
        "final_audit": {
            "status": "SEALED_NOT_CONSUMED",
            "row_count": sum(
                row.get("split") == "final_audit" for row in [*rows_i3, *rows_i4]
            ),
            "label_support_read_for_authorization": False,
            "row_level_outcomes_used_for_selection": False,
        },
    }
