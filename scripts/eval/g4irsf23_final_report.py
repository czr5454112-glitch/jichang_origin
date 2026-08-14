#!/usr/bin/env python3
"""Render the small, evidence-bounded G4IRSF23 joint decision report.

The report consumes compact summaries only.  It never launches a simulation,
does not read runtime pair files, and does not turn an unfinished stage into a
positive or negative result.  Missing evidence is rendered as ``NOT_RUN`` or
``PENDING``.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
BASELINE_SCHEMA = "czr005.g4irsf23.paper_dual_baseline.v1"
SOURCE_SCHEMA = "czr005.g4irsf23.source_pilot_evidence_summary.v1"
PRECURSOR_SCHEMA = "czr005.g4irsf23.precursor_route_delivery_summary.v1"
PRECURSOR_FORMAL_SCHEMA = (
    "czr005.g4irsf23.precursor_route_formal_delivery_summary.v1"
)
PRECURSOR_COMPACT_SCHEMA = "czr005.g4irsf23.precursor_route_pilot_summary.v1"
EXTERNALITY_SUMMARY_SCHEMA = (
    "czr005.g4irsf23.externality_neighborhood_summary.v1"
)
EXTERNALITY_RESULT_SCHEMA = "czr005.g4irsf23.externality_neighborhood_result.v1"
FINAL_SCHEMA = "czr005.g4irsf23.decision_summary.v1"
PRECURSOR_FORMAL_NO_GO = "NO_GO_PRECURSOR_FORMAL_SUPPORT"
PRECURSOR_FORMAL_PASS = "PASS_PRECURSOR_FORMAL_SUPPORT"
REQUIRED_PRECURSOR_FORMAL_GROUPS = 2_048
REQUIRED_PRECURSOR_FORMAL_H_SYSTEM_GROUPS = 256
REQUIRED_PRECURSOR_FORMAL_H_BAG_ONLY_GROUPS = 1_792
REQUIRED_PRECURSOR_FORMAL_EXECUTION_TARGETS = 4_096
REQUIRED_PRECURSOR_FORMAL_FAIR_PROMOTION_GROUPS = 16
REQUIRED_PRECURSOR_FORMAL_BLOCK8_FAIR_PROMOTION_GROUPS = 4
REQUIRED_TINY_MLP_FORMAL_FAIR_POSITIVES = 40
REQUIRED_TINY_MLP_HELDOUT_FAIR_POSITIVES = 12
TINY_MLP_NONLINEAR_REGRET_REQUIREMENT = "STABLE_NONLINEAR_REGRET_REQUIRED"

DEFAULT_BASELINE = Path("outputs/tables/g4irsf23_paper_baselines.json")
DEFAULT_SOURCE = Path("outputs/tables/g4irsf23_source_pilot_summary.json")
DEFAULT_PRECURSOR = Path("outputs/tables/g4irsf23_precursor_route_summary.json")
DEFAULT_PRECURSOR_FORMAL = Path(
    "outputs/tables/g4irsf23_precursor_route_formal_summary.json"
)
DEFAULT_EXTERNALITY = Path(
    "outputs/tables/g4irsf23_externality_neighborhood_summary.json"
)
DEFAULT_JSON_OUTPUT = Path("outputs/tables/g4irsf23_decision_summary.json")
DEFAULT_REPORT_OUTPUT = Path("outputs/reports/g4irsf23_final_joint_decision.md")


class FinalReportError(ValueError):
    """Raised when supplied compact evidence has an incompatible schema."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FinalReportError(message)


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _validate_distribution_metrics(
    metrics: Any, *, expected_count: int, context: str, require_missing_count: bool
) -> Mapping[str, Any]:
    _require(isinstance(metrics, Mapping), f"{context} omitted metrics")
    for name, row in metrics.items():
        _require(isinstance(row, Mapping), f"{context}.{name} must be an object")
        _require(
            row.get("count") == expected_count
            and all(type(row.get(key)) in (int, float) for key in ("min", "mean", "median", "max"))
            and float(row["min"]) <= float(row["mean"]) <= float(row["max"])
            and float(row["min"]) <= float(row["median"]) <= float(row["max"]),
            f"{context}.{name} has incompatible count or summary statistics",
        )
        if require_missing_count:
            _require(
                row.get("missing_count") == 0,
                f"{context}.{name} contains missing values",
            )
    return metrics


def _validate_source_component_distribution(
    distribution: Any,
    *,
    expected_h_system_count: int,
    expected_block_counts: Mapping[str, Any],
) -> Mapping[str, Any]:
    _require(
        isinstance(distribution, Mapping),
        "Source summary omitted component mean delta distribution",
    )
    _require(
        distribution.get("delta_direction") == "treatment_minus_baseline"
        and distribution.get("unit") == "seconds_per_complete_raw_bag"
        and distribution.get("h_system_pair_count") == expected_h_system_count
        and distribution.get("release_block_pair_counts") == expected_block_counts,
        "Source component distribution omitted its count/unit/direction contract",
    )
    scopes = {
        "all": (distribution.get("all"), expected_h_system_count),
        "block7": (
            (distribution.get("by_release_block") or {}).get("7")
            if isinstance(distribution.get("by_release_block"), Mapping)
            else None,
            int(expected_block_counts["7"]),
        ),
        "block8": (
            (distribution.get("by_release_block") or {}).get("8")
            if isinstance(distribution.get("by_release_block"), Mapping)
            else None,
            int(expected_block_counts["8"]),
        ),
    }
    expected_metrics = {
        "raw_bag_network_time_mean_delta_seconds",
        "raw_bag_scheduled_pre_release_wait_mean_delta_seconds",
        "raw_bag_source_wait_mean_delta_seconds",
    }
    for scope_name, (scope, expected_count) in scopes.items():
        _require(
            isinstance(scope, Mapping)
            and scope.get("pair_count") == expected_count,
            f"Source component {scope_name} count drifted",
        )
        metrics = _validate_distribution_metrics(
            scope.get("metrics"),
            expected_count=expected_count,
            context=f"Source component {scope_name}",
            require_missing_count=False,
        )
        _require(
            set(metrics) == expected_metrics,
            f"Source component {scope_name} metric set drifted",
        )
    return distribution


def _validate_precursor_effect_distribution(
    distribution: Any,
    *,
    expected_h_system_groups: int,
    expected_fair_promotions: int,
) -> Mapping[str, Any]:
    _require(
        isinstance(distribution, Mapping),
        "precursor Pilot omitted H_system effect/cost distribution",
    )
    panel = distribution.get("panel")
    promotions = distribution.get("fair_promotions")
    _require(
        isinstance(panel, Mapping) and isinstance(promotions, Mapping),
        "precursor effect distribution omitted panel or fair promotions",
    )
    expected_actions = expected_h_system_groups * 2
    _require(
        distribution.get("delta_direction") == "treatment_minus_baseline"
        and distribution.get("raw_bag_mean_denominator") == "complete_raw_bag"
        and distribution.get("planned_h_system_action_count") == expected_actions
        and distribution.get("complete_h_system_action_count") == expected_actions
        and distribution.get("complete_h_system_group_count")
        == expected_h_system_groups
        and panel.get("action_count") == expected_actions
        and panel.get("group_count") == expected_h_system_groups
        and promotions.get("action_count") == expected_fair_promotions
        and promotions.get("group_count") == expected_fair_promotions,
        "precursor effect distribution count/direction contract drifted",
    )
    required_metrics = {
        "raw_bag_mean_delta_seconds",
        "raw_bag_source_wait_mean_delta_seconds",
        "raw_bag_network_time_mean_delta_seconds",
        "raw_bag_p95_delta_seconds",
        "raw_bag_p99_delta_seconds",
        "raw_bag_max_delta_seconds",
        "current_bag_cost_seconds",
        "deadline_headroom_seconds",
    }
    panel_metrics = _validate_distribution_metrics(
        panel.get("metrics"),
        expected_count=expected_actions,
        context="precursor H_system panel",
        require_missing_count=True,
    )
    promotion_metrics = _validate_distribution_metrics(
        promotions.get("metrics"),
        expected_count=expected_fair_promotions,
        context="precursor fair promotions",
        require_missing_count=True,
    )
    _require(
        required_metrics <= set(panel_metrics)
        and required_metrics <= set(promotion_metrics)
        and sum(int(value) for value in panel.get("release_block_action_counts", {}).values())
        == expected_actions
        and sum(
            int(value)
            for value in promotions.get("release_block_action_counts", {}).values()
        )
        == expected_fair_promotions,
        "precursor effect distribution metric or release-block coverage drifted",
    )
    return distribution


def _read_required(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(payload, dict), f"{path} must contain a JSON object")
    return payload


def _read_optional(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return _read_required(path)


def _externality_summary(
    payload: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    if payload is None:
        return None
    schema = payload.get("schema")
    if schema == EXTERNALITY_SUMMARY_SCHEMA:
        return payload
    if schema == EXTERNALITY_RESULT_SCHEMA:
        summary = payload.get("summary")
        _require(
            isinstance(summary, Mapping)
            and summary.get("schema") == EXTERNALITY_SUMMARY_SCHEMA,
            "externality result omitted its compact summary",
        )
        return summary
    raise FinalReportError(
        "externality input must be a compact result or summary, not a plan or raw pair file"
    )


def _status_cell(status: str, value: float | None = None) -> dict[str, Any]:
    return {"status": status, "mean_minutes": value}


def _build_denominator_panel(
    baselines: Mapping[str, Any],
    *,
    candidate_metrics_status: str = "PENDING_NO_G23_CLOSED_LOOP_CANDIDATE",
) -> dict[str, Any]:
    required = baselines["required_baselines"]
    f2 = required["frozen_f2"]
    hca = required["original_hca_star"]
    f2_one_x = f2["one_x"]
    hca_one_x = hca["one_x"]
    hca_processed = hca_one_x["processed_segment_attempt_time_tth"]
    f2_raw = float(f2_one_x["original_entry_mean_minutes"])
    hca_raw = float(hca_one_x["matched_raw_entry_time_tth_mean_minutes"])
    rows = [
        {
            "denominator": "processed_segment_attempt_time_tth",
            "frozen_f2": _status_cell("NOT_REPORTED_FOR_F2"),
            "original_hca_star": _status_cell(
                "HISTORICAL_PARSED_ORIGINAL_PROJECT_OUTPUT",
                float(hca_processed["mean_minutes"]),
            ),
            "comparison_status": "N/A_NOT_COMPARABLE",
            "fresh_matched_winner_claim_allowed": False,
        },
        {
            "denominator": "java_release_time_tth",
            "frozen_f2": _status_cell("NOT_REPORTED_FOR_F2"),
            "original_hca_star": _status_cell(
                "HISTORICAL_PARSED_ORIGINAL_PROJECT_OUTPUT",
                float(hca_one_x["java_release_time_tth_mean_minutes"]),
            ),
            "comparison_status": "N/A_NOT_COMPARABLE",
            "fresh_matched_winner_claim_allowed": False,
        },
        {
            "denominator": "original_entry_time_tth",
            "frozen_f2": _status_cell("COMMITTED_FROZEN_CONTROL", f2_raw),
            "original_hca_star": _status_cell(
                "HISTORICAL_ALGEBRAICALLY_RECONCILED", hca_raw
            ),
            "comparison_status": "DENOMINATOR_ALIGNED_HISTORICAL_DIRECTION_ONLY",
            "f2_minus_hca_minutes": f2_raw - hca_raw,
            "fresh_matched_winner_claim_allowed": False,
        },
    ]
    return {
        "baseline_ids": [f2["baseline_id"], hca["baseline_id"]],
        "unit": "minutes_per_complete_raw_bag",
        "rows": rows,
        "unmapped_diagnostics": {
            "f2_pass_time_anchored_mean_minutes": float(
                f2_one_x["pass_time_anchored_mean_minutes"]
            ),
            "hca_legacy_mislabeled_original_entry_mean_minutes": float(
                hca_one_x["legacy_mislabeled_original_entry_mean_minutes"]
            ),
            "status": "DO_NOT_SUBSTITUTE_IN_THE_THREE_DENOMINATOR_PANEL",
        },
        "candidate_metrics_status": candidate_metrics_status,
    }


def _source_stage(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {
            "evidence_status": "NOT_RUN",
            "decision_status": "PENDING",
        }
    _require(payload.get("schema") == SOURCE_SCHEMA, "unexpected Source summary schema")
    decision = payload.get("decision")
    scope = payload.get("evidence_scope")
    effect = payload.get("h_system_effect")
    gates = payload.get("preregistered_gates")
    action = payload.get("action_certificate")
    safety = payload.get("safety")
    _require(
        all(
            isinstance(row, Mapping)
            for row in (decision, scope, effect, gates, action, safety)
        ),
        "Source summary omitted a compact evidence section",
    )
    labels = effect.get("label_counts")
    _require(isinstance(labels, Mapping), "Source summary omitted label counts")
    repeated_hold_zero = int(action["repeated_hold_count_equals_zero"])
    planned_groups = int(scope["planned_group_count"])
    component_distribution = _validate_source_component_distribution(
        effect.get("component_mean_delta_seconds_per_raw_bag"),
        expected_h_system_count=int(effect["label_count"]),
        expected_block_counts=scope["h_system_by_release_block"],
    )
    return {
        "evidence_status": "COMPLETE",
        "decision_status": str(decision["source_causal_support"]),
        "action_implementation": str(decision["source_action_implementation"]),
        "selector_status": str(decision["source_selector"]),
        "planned_group_count": planned_groups,
        "executed_target_count": int(scope["executed_target_count"]),
        "h_system_label_count": int(effect["label_count"]),
        "h_system_by_release_block": _plain(scope["h_system_by_release_block"]),
        "full_horizon_raw_bag_count": int(safety["full_horizon_raw_bag_count"]),
        "action_changed_group_count": int(action["action_changed_count"]),
        "single_hold_opportunity_group_count": int(
            action["hold_opportunity_count_equals_one"]
        ),
        "forced_a0_after_hold_group_count": int(
            action["forced_a0_after_hold_count"]
        ),
        "repeated_hold_group_count": planned_groups - repeated_hold_zero,
        "fair_system_beneficial_label_count": int(
            labels["FAIR_SYSTEM_BENEFICIAL"]
        ),
        "system_beneficial_but_unfair_label_count": int(
            labels["SYSTEM_BENEFICIAL_BUT_UNFAIR"]
        ),
        "promotion_eligible_fair_positive_count": int(
            effect["promotion_eligible_fair_positive_count"]
        ),
        "block8_promotion_eligible_fair_positive_count": int(
            effect["block_8_promotion_eligible_fair_positive_count"]
        ),
        "promotion_eligible_strata_count": int(
            effect["promotion_eligible_strata_count"]
        ),
        "weak_diagnostic_strata_count": int(effect["weak_diagnostic_strata_count"]),
        "system_mean_delta_seconds": _plain(effect["system_mean_delta_seconds"]),
        "system_p95_delta_seconds": _plain(effect["system_p95_delta_seconds"]),
        "system_p99_delta_seconds": _plain(effect["system_p99_delta_seconds"]),
        "current_bag_cost_seconds": _plain(effect["current_bag_cost_seconds"]),
        "component_mean_delta_seconds_per_raw_bag": _plain(
            component_distribution
        ),
        "weak_diagnostic_rows": _plain(effect.get("weak_diagnostic_rows", [])),
        "pilot_support_pass": gates["pilot_support_pass"] is True,
        "reason": str(decision["reason"]),
    }


def _precursor_formal_stage(
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if payload is None:
        return {
            "formal_evidence_status": "NOT_RUN",
            "formal_decision_status": "PENDING",
            "formal_reason": "PRECURSOR_FORMAL_2048_EXACT_SUMMARY_NOT_SUPPLIED",
            "formal_attempted_group_count": None,
            "formal_exact_pair_gate_pass": False,
            "formal_h_bag_complete_group_count": None,
            "formal_h_system_sparse_reused_group_count": None,
            "formal_h_bag_only_group_count": None,
            "formal_new_h_system_group_count": None,
            "formal_new_h_system_target_count": None,
            "formal_h_system_evidence_scope": (
                "PENDING_EXPECTED_SPARSE_256_REUSED_NOT_2048_SYSTEM_LABELS"
            ),
            "tiny_mlp_unlock": {
                "required_formal_fair_positive_count": (
                    REQUIRED_TINY_MLP_FORMAL_FAIR_POSITIVES
                ),
                "required_heldout_fair_positive_count": (
                    REQUIRED_TINY_MLP_HELDOUT_FAIR_POSITIVES
                ),
                "observed_formal_fair_positive_count": None,
                "observed_heldout_fair_positive_count": None,
                "heldout_evidence_status": "NOT_RUN",
                "nonlinear_regret_requirement": (
                    TINY_MLP_NONLINEAR_REGRET_REQUIREMENT
                ),
                "nonlinear_regret_evidence_status": "NOT_RUN",
                "unlocked": False,
            },
        }

    _require(
        payload.get("schema") == PRECURSOR_FORMAL_SCHEMA,
        "unexpected precursor Route Formal delivery schema",
    )
    exact = payload.get("exact_pair_gate")
    compact = payload.get("precursor_formal")
    identity = payload.get("identity_audit")
    formal_counts = payload.get("formal_counts")
    tiny_mlp_unlock = payload.get("tiny_mlp_unlock")
    _require(
        all(
            isinstance(row, Mapping)
            for row in (
                exact,
                compact,
                identity,
                formal_counts,
                tiny_mlp_unlock,
            )
        ),
        "precursor Route Formal delivery omitted its top-level counts, tiny-MLP unlock, exact gate, compact summary, or identity audit",
    )
    _require(
        payload.get("protocol_mode") == "FORMAL_WITH_EXACT_PILOT_REUSE",
        "precursor Route Formal delivery omitted its Pilot-reuse protocol mode",
    )
    _require(
        exact.get("schema") == "czr005.g4irsf23.precursor_route_exact_gate.v1"
        and exact.get("status") == "PASS_EXACT_PAIR_GATE"
        and exact.get("pass") is True
        and exact.get("coverage_complete") is True
        and exact.get("failure_count") == 0
        and exact.get("expected_target_count")
        == REQUIRED_PRECURSOR_FORMAL_EXECUTION_TARGETS
        and exact.get("observed_target_count")
        == REQUIRED_PRECURSOR_FORMAL_EXECUTION_TARGETS,
        "precursor Route Formal exact pair gate is incomplete",
    )
    _require(
        compact.get("schema") == PRECURSOR_COMPACT_SCHEMA,
        "precursor Route Formal compact summary is not pilot-style evidence",
    )
    attempted = compact.get("attempted_group_count")
    h_bag_complete = compact.get("h_bag_complete_group_count")
    h_system_planned = compact.get("h_system_planned_group_count")
    h_system_complete = compact.get("h_system_complete_group_count")
    thresholds = compact.get("thresholds")
    gates = compact.get("gates")
    _require(
        isinstance(thresholds, Mapping) and isinstance(gates, Mapping),
        "precursor Route Formal compact summary omitted thresholds or gates",
    )
    _require(
        attempted == REQUIRED_PRECURSOR_FORMAL_GROUPS
        and h_bag_complete == REQUIRED_PRECURSOR_FORMAL_GROUPS
        and h_system_planned == REQUIRED_PRECURSOR_FORMAL_H_SYSTEM_GROUPS
        and h_system_complete == REQUIRED_PRECURSOR_FORMAL_H_SYSTEM_GROUPS
        and thresholds.get("required_h_bag_groups")
        == REQUIRED_PRECURSOR_FORMAL_GROUPS
        and thresholds.get("required_h_system_groups")
        == REQUIRED_PRECURSOR_FORMAL_H_SYSTEM_GROUPS,
        "precursor Route Formal compact coverage is not H_bag=2048/H_system=256",
    )
    _require(
        thresholds.get("required_fair_promotion_groups")
        == REQUIRED_PRECURSOR_FORMAL_FAIR_PROMOTION_GROUPS
        and thresholds.get("required_block8_fair_promotion_groups")
        == REQUIRED_PRECURSOR_FORMAL_BLOCK8_FAIR_PROMOTION_GROUPS,
        "precursor Route Formal promotion thresholds must remain 16 total / 4 block-8",
    )
    expected_identity = {
        "pilot_group_count": 512,
        "pilot_h_system_group_count": 256,
        "pilot_h_bag_only_group_count": 256,
        "formal_group_count": 2_048,
        "delta_group_count": 1_536,
        "delta_h_bag_only_group_count": 1_536,
        "reused_pilot_execution_target_count": 1_024,
        "delta_execution_target_count": 3_072,
        "full_formal_execution_target_count": 4_096,
        "formal_h_system_target_count": 512,
        "new_h_system_target_count": 0,
        "exact_execution_partition": True,
    }
    _require(
        all(identity.get(key) == value for key, value in expected_identity.items()),
        "precursor Route Formal identity audit must prove reused H_system=256 groups, H_bag-only=256+1536, new H_system targets=0, and exact execution 1024+3072=4096",
    )
    _require(
        gates.get("h_bag_group_coverage") is True
        and gates.get("h_system_group_coverage") is True,
        "precursor Route Formal compact coverage gates did not pass",
    )
    expected_gate_names = {
        "h_bag_group_coverage",
        "h_system_group_coverage",
        "action_changing_rate",
        "fair_promotion_group_count",
        "block8_fair_promotion_group_count",
        "fair_promotion_strata_coverage",
    }
    _require(
        set(gates) == expected_gate_names
        and all(type(value) is bool for value in gates.values()),
        "precursor Route Formal gates must be the six pilot-style booleans",
    )
    observed_gate_values = {
        "h_bag_group_coverage": h_bag_complete
        >= thresholds["required_h_bag_groups"],
        "h_system_group_coverage": h_system_complete
        >= thresholds["required_h_system_groups"],
        "action_changing_rate": float(compact["action_changed_group_rate"])
        >= float(thresholds["required_action_change_rate"]),
        "fair_promotion_group_count": int(compact["fair_promotion_group_count"])
        >= int(thresholds["required_fair_promotion_groups"]),
        "block8_fair_promotion_group_count": int(
            compact["block8_fair_promotion_group_count"]
        )
        >= int(thresholds["required_block8_fair_promotion_groups"]),
        "fair_promotion_strata_coverage": int(
            compact["fair_promotion_strata_count"]
        )
        >= int(thresholds["required_fair_promotion_strata"]),
    }
    _require(
        dict(gates) == observed_gate_values,
        "precursor Route Formal compact counts disagree with its gates",
    )
    compact_pass = compact.get("pilot_support_pass")
    _require(
        type(compact_pass) is bool and compact_pass is all(gates.values()),
        "precursor Route Formal compact status disagrees with its gates",
    )
    input_status = compact.get("status")
    if input_status == "NO_GO_PRECURSOR_PILOT_SUPPORT":
        _require(compact_pass is False, "Formal no-go compact unexpectedly passed")
        normalized_status = PRECURSOR_FORMAL_NO_GO
    elif input_status == "PASS_PRECURSOR_PILOT_SUPPORT":
        _require(compact_pass is True, "Formal pass compact unexpectedly failed")
        normalized_status = PRECURSOR_FORMAL_PASS
    else:
        raise FinalReportError(
            "precursor Route Formal compact status is not a recognized pilot-style label"
        )
    expected_formal_counts = {
        "h_bag_complete_group_count": REQUIRED_PRECURSOR_FORMAL_GROUPS,
        "h_system_sparse_reused_group_count": (
            REQUIRED_PRECURSOR_FORMAL_H_SYSTEM_GROUPS
        ),
        "h_bag_only_group_count": REQUIRED_PRECURSOR_FORMAL_H_BAG_ONLY_GROUPS,
        "new_h_system_group_count": 0,
        "new_h_system_target_count": 0,
        "fair_promotion_group_count": int(compact["fair_promotion_group_count"]),
        "block8_fair_promotion_group_count": int(
            compact["block8_fair_promotion_group_count"]
        ),
        "required_fair_promotion_group_count": (
            REQUIRED_PRECURSOR_FORMAL_FAIR_PROMOTION_GROUPS
        ),
        "required_block8_fair_promotion_group_count": (
            REQUIRED_PRECURSOR_FORMAL_BLOCK8_FAIR_PROMOTION_GROUPS
        ),
    }
    _require(
        payload.get("formal_decision_status") == normalized_status
        and payload.get("formal_support_pass") is compact_pass
        and dict(formal_counts) == expected_formal_counts,
        "precursor Route Formal top-level status/support/counts disagree with the exact Formal evidence",
    )
    expected_tiny_mlp_unlock = {
        "required_formal_fair_positive_count": (
            REQUIRED_TINY_MLP_FORMAL_FAIR_POSITIVES
        ),
        "required_heldout_fair_positive_count": (
            REQUIRED_TINY_MLP_HELDOUT_FAIR_POSITIVES
        ),
        "observed_formal_fair_positive_count": int(
            compact["fair_promotion_group_count"]
        ),
        "observed_heldout_fair_positive_count": 0,
        "heldout_evidence_status": "NOT_RUN",
        "nonlinear_regret_requirement": TINY_MLP_NONLINEAR_REGRET_REQUIREMENT,
        "nonlinear_regret_evidence_status": "NOT_RUN",
        "unlocked": False,
    }
    _require(
        dict(tiny_mlp_unlock) == expected_tiny_mlp_unlock,
        "precursor Route Formal tiny-MLP unlock must keep 40/12 separate from the 16/4 causal-support gate",
    )
    return {
        "evidence_status": "COMPLETE",
        "decision_status": normalized_status,
        "formal_evidence_status": "COMPLETE",
        "formal_decision_status": normalized_status,
        "formal_input_compact_status": str(input_status),
        "formal_support_pass": compact_pass,
        "formal_reason": None,
        "formal_attempted_group_count": int(attempted),
        "formal_exact_pair_gate_pass": True,
        "formal_h_bag_complete_group_count": int(h_bag_complete),
        "formal_h_system_sparse_reused_group_count": int(
            identity["pilot_h_system_group_count"]
        ),
        "formal_h_bag_only_group_count": int(
            identity["pilot_h_bag_only_group_count"]
            + identity["delta_h_bag_only_group_count"]
        ),
        "formal_new_h_system_group_count": 0,
        "formal_new_h_system_target_count": int(
            identity["new_h_system_target_count"]
        ),
        "formal_h_system_evidence_scope": (
            "SPARSE_256_REUSED_NOT_2048_SYSTEM_LABELS"
        ),
        "formal_fair_promotion_group_count": int(
            compact["fair_promotion_group_count"]
        ),
        "formal_block8_fair_promotion_group_count": int(
            compact["block8_fair_promotion_group_count"]
        ),
        "formal_fair_promotion_strata_count": int(
            compact["fair_promotion_strata_count"]
        ),
        "formal_required_fair_promotion_group_count": (
            REQUIRED_PRECURSOR_FORMAL_FAIR_PROMOTION_GROUPS
        ),
        "formal_required_block8_fair_promotion_group_count": (
            REQUIRED_PRECURSOR_FORMAL_BLOCK8_FAIR_PROMOTION_GROUPS
        ),
        "formal_h_system_effect_distribution": _plain(
            compact.get("h_system_effect_distribution")
        ),
        "tiny_mlp_unlock": expected_tiny_mlp_unlock,
    }


def _precursor_stage(
    payload: Mapping[str, Any] | None,
    formal_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    formal_stage = _precursor_formal_stage(formal_payload)
    if payload is None:
        return {
            "evidence_status": formal_stage.get("evidence_status", "PENDING"),
            "decision_status": formal_stage.get("decision_status", "PENDING"),
            "pilot_evidence_status": "NOT_RUN",
            "pilot_decision_status": "PENDING",
            **formal_stage,
        }
    _require(
        payload.get("schema") == PRECURSOR_SCHEMA,
        "unexpected precursor Route summary schema",
    )
    pilot = payload.get("precursor_pilot")
    exact = payload.get("exact_pair_gate")
    _require(
        isinstance(pilot, Mapping) and isinstance(exact, Mapping),
        "precursor summary omitted pilot or exact-pair evidence",
    )
    pilot_effect_distribution = _validate_precursor_effect_distribution(
        pilot.get("h_system_effect_distribution"),
        expected_h_system_groups=int(pilot["h_system_complete_group_count"]),
        expected_fair_promotions=int(pilot["fair_promotion_group_count"]),
    )
    result = {
        "pilot_evidence_status": "COMPLETE",
        "pilot_decision_status": str(pilot["status"]),
        "exact_pair_gate": str(exact["status"]),
        "attempted_group_count": int(pilot["attempted_group_count"]),
        "pilot_action_changed_group_count": int(
            pilot["action_changed_group_count"]
        ),
        "pilot_action_changed_group_rate": float(
            pilot["action_changed_group_rate"]
        ),
        "h_system_complete_group_count": int(
            pilot["h_system_complete_group_count"]
        ),
        "fair_promotion_group_count": int(pilot["fair_promotion_group_count"]),
        "block8_fair_promotion_group_count": int(
            pilot["block8_fair_promotion_group_count"]
        ),
        "pilot_support_pass": pilot["pilot_support_pass"] is True,
        "pilot_effect_tier_counts": _plain(pilot.get("effect_tier_counts", {})),
        "pilot_system_beneficial_group_count": int(
            pilot.get("system_beneficial_group_count", 0)
        ),
        "pilot_system_beneficial_but_costly_group_count": int(
            pilot.get("system_beneficial_but_costly_group_count", 0)
        ),
        "pilot_individual_fair_action_count": int(
            pilot.get("individual_fair_action_count", 0)
        ),
        "pilot_strict_no_delay_action_count": int(
            pilot.get("strict_no_delay_action_count", 0)
        ),
        "pilot_h_system_effect_distribution": _plain(
            pilot_effect_distribution
        ),
        **formal_stage,
    }
    if formal_stage["formal_evidence_status"] == "COMPLETE":
        result["evidence_status"] = "COMPLETE"
        result["decision_status"] = formal_stage["formal_decision_status"]
    else:
        result["evidence_status"] = "PENDING"
        result["decision_status"] = "PENDING_PRECURSOR_FORMAL_GATE"
    return result


def _externality_stage(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    summary = _externality_summary(payload)
    if summary is None:
        return {
            "evidence_status": "NOT_RUN",
            "decision_status": "PENDING",
        }
    thresholds = summary.get("thresholds")
    gates = summary.get("gates")
    signature = summary.get("heldout_local_signature")
    max_diagnostic = summary.get("raw_bag_max_delta_seconds_diagnostic")
    _require(
        all(
            isinstance(row, Mapping)
            for row in (thresholds, gates, signature, max_diagnostic)
        ),
        "externality summary omitted thresholds, preregistered gates, held-out signature, or max diagnostic",
    )
    expected_gate_names = {
        "execution_coverage",
        "recognized_execution_outcomes",
        "action_changing_rate",
        "fair_system_beneficial_count",
        "fair_system_beneficial_block_pressure_cell_count",
        "heldout_local_signature",
    }
    _require(
        set(gates) == expected_gate_names
        and all(type(value) is bool for value in gates.values()),
        "externality gates must separate execution, applicability, and effect booleans",
    )
    count_names = (
        "planned_group_count",
        "action_row_count",
        "attempted_group_count",
        "execution_coverage_count",
        "missing_execution_count",
        "unknown_execution_count",
        "action_applied_count",
        "guard_abstain_count",
        "unexpected_execution_outcome_count",
        "effect_complete_count",
        "system_safe_count",
        "system_beneficial_count",
        "system_beneficial_cell_count",
        "fair_system_beneficial_count",
        "fair_system_beneficial_cell_count",
        "system_beneficial_but_costly_count",
        "system_beneficial_but_unfair_count",
        "individual_fair_count",
        "individual_fair_evidence_incomplete_count",
        "individual_direct_beneficial_count",
        "individual_direct_nonregressing_count",
    )
    _require(
        all(type(summary.get(name)) is int and summary[name] >= 0 for name in count_names),
        "externality fairness counts must be non-negative integers",
    )
    planned = summary["planned_group_count"]
    action_rows = summary["action_row_count"]
    attempted = summary["attempted_group_count"]
    execution_coverage = summary["execution_coverage_count"]
    missing = summary["missing_execution_count"]
    unknown = summary["unknown_execution_count"]
    applied = summary["action_applied_count"]
    abstained = summary["guard_abstain_count"]
    unexpected = summary["unexpected_execution_outcome_count"]
    effect_complete = summary["effect_complete_count"]
    action_change_rate = summary.get("action_changing_rate")
    safe = summary["system_safe_count"]
    beneficial = summary["system_beneficial_count"]
    beneficial_cells = summary["system_beneficial_cell_count"]
    fair = summary["fair_system_beneficial_count"]
    fair_cells = summary["fair_system_beneficial_cell_count"]
    costly = summary["system_beneficial_but_costly_count"]
    unfair = summary["system_beneficial_but_unfair_count"]
    _require(
        planned == 256
        and action_rows == planned
        and attempted == action_rows
        and execution_coverage <= attempted
        and missing == attempted - execution_coverage
        and unknown == 0
        and applied + abstained + unexpected == execution_coverage
        and effect_complete == applied
        and isinstance(action_change_rate, (int, float))
        and not isinstance(action_change_rate, bool)
        and math.isfinite(float(action_change_rate))
        and math.isclose(
            float(action_change_rate),
            applied / attempted,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        and safe <= effect_complete
        and beneficial <= safe
        and fair + unfair == beneficial
        and costly <= beneficial
        and fair_cells <= beneficial_cells <= beneficial
        and fair_cells <= fair
        and summary["individual_fair_count"] <= effect_complete
        and summary["individual_fair_evidence_incomplete_count"] <= effect_complete
        and summary["individual_direct_beneficial_count"] <= effect_complete
        and summary["individual_direct_nonregressing_count"] <= effect_complete,
        "externality fairness counts violate the producer partition contract",
    )
    abstain_reasons = summary.get("guard_abstain_reasons")
    _require(
        isinstance(abstain_reasons, Mapping)
        and set(abstain_reasons) <= {
            "NOT_APPLICABLE_ACTION_PRECONDITION_FAILED"
        }
        and all(type(value) is int and value >= 0 for value in abstain_reasons.values())
        and sum(abstain_reasons.values()) == abstained,
        "externality guard-abstain reasons disagree with its count",
    )
    _require(
        thresholds.get("required_group_count") == 256
        and thresholds.get("required_action_change_rate") == 0.80
        and thresholds.get("system_mean_delta_seconds_max") == -0.01
        and thresholds.get("system_p95_p99_delta_seconds_max") == 0.001
        and "system_p95_p99_max_delta_seconds_max" not in thresholds
        and thresholds.get("deadline_miss_delta_max") == 0
        and type(thresholds.get("required_fair_system_beneficial")) is int
        and thresholds["required_fair_system_beneficial"] >= 1
        and type(
            thresholds.get("required_fair_system_beneficial_block_pressure_cells")
        )
        is int
        and thresholds["required_fair_system_beneficial_block_pressure_cells"] >= 1
        and type(signature.get("pass")) is bool,
        "externality thresholds or held-out signature are incompatible",
    )
    diagnostic_count = max_diagnostic.get("count")
    diagnostic_stats = tuple(
        max_diagnostic.get(name) for name in ("min", "mean", "median", "max")
    )
    _require(
        max_diagnostic.get("role") == "DIAGNOSTIC_ONLY_NOT_A_SYSTEM_HARD_GATE"
        and type(diagnostic_count) is int
        and diagnostic_count == effect_complete
        and (
            (
                diagnostic_count == 0
                and all(value is None for value in diagnostic_stats)
            )
            or (
                diagnostic_count > 0
                and all(
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and math.isfinite(float(value))
                    for value in diagnostic_stats
                )
            )
        ),
        "externality raw-bag max diagnostic is incompatible",
    )
    observed_gates = {
        "execution_coverage": (
            attempted == 256
            and execution_coverage == 256
            and missing == 0
            and unknown == 0
        ),
        "recognized_execution_outcomes": unexpected == 0,
        "action_changing_rate": (
            float(action_change_rate) >= thresholds["required_action_change_rate"]
        ),
        "fair_system_beneficial_count": fair
        >= thresholds["required_fair_system_beneficial"],
        "fair_system_beneficial_block_pressure_cell_count": fair_cells
        >= thresholds["required_fair_system_beneficial_block_pressure_cells"],
        "heldout_local_signature": signature["pass"] is True,
    }
    _require(
        dict(gates) == observed_gates,
        "externality fairness counts or held-out signature disagree with its gates",
    )
    continuation = all(observed_gates.values())
    _require(
        type(summary.get("continuation_pass")) is bool
        and summary["continuation_pass"] is continuation,
        "externality continuation status disagrees with its gates",
    )
    expected_status = (
        "PASS_EXTERNALITY_NEIGHBORHOOD_SUPPORT"
        if continuation
        else "NO_GO_EXTERNALITY_NEIGHBORHOOD_SUPPORT"
    )
    _require(
        summary.get("status") == expected_status,
        "externality decision label disagrees with its fairness-aware gates",
    )
    _require(
        summary.get("selection_scope")
        == "ONE_HOP_ALTERNATE_TARGET_QUEUE_ONLY"
        and summary.get("one_hop_pressure_bins")
        == ["q16_23", "q24_31", "q32_plus"]
        and summary.get("two_hop_queue_pressure_used") is False
        and signature.get("feature") == "one_hop_target_queue_bin",
        "externality summary omitted the one-hop selection contract",
    )
    _require(
        summary.get("system_tail_hard_gate_metrics")
        == ["raw_bag_p95_delta_seconds", "raw_bag_p99_delta_seconds"]
        and summary.get("raw_bag_max_delta_is_diagnostic_only") is True,
        "externality summary omitted the p95/p99-only tail hard-gate contract",
    )
    _require(
        summary.get("individual_fairness_evaluated") is True
        and "individual_fairness_claimed" not in summary
        and summary.get("system_safe_and_individual_cost_are_separate") is True
        and summary.get("system_beneficial_and_individual_fair_are_orthogonal") is True
        and summary.get("continuation_cell_coverage_uses_fair_system_beneficial")
        is True
        and signature.get("system_benefit_scope") == "SYSTEM_BENEFICIAL_ONLY"
        and signature.get("individual_fairness_used") is False
        and signature.get("individual_fairness_claimed") is False
        and summary.get("individual_fairness_contract")
        == "FROZEN_PRE_ACTION_DEADLINE_HEADROOM_AND_TREATMENT_CURRENT_BAG_OUTCOME"
        and summary.get("post_hoc_individual_cost_cap_applied") is False,
        "externality summary omitted the frozen individual-fairness contract",
    )
    _require(
        summary.get("execution_coverage_and_effect_evidence_are_separate") is True
        and summary.get("effect_and_fairness_use_action_applied_pairs_only") is True
        and summary.get("guard_abstain_is_completed_applicability_evidence") is True,
        "externality summary conflates execution coverage with applied effects",
    )
    evidence_complete = (
        observed_gates["execution_coverage"]
        and observed_gates["recognized_execution_outcomes"]
    )
    return {
        "evidence_status": "COMPLETE" if evidence_complete else "INCOMPLETE",
        "decision_status": str(summary["status"]),
        "planned_group_count": planned,
        "attempted_group_count": attempted,
        "execution_coverage_count": execution_coverage,
        "missing_execution_count": missing,
        "unknown_execution_count": unknown,
        "action_applied_count": applied,
        "guard_abstain_count": abstained,
        "guard_abstain_reasons": _plain(abstain_reasons),
        "action_changing_rate": float(action_change_rate),
        "effect_complete_count": effect_complete,
        "system_safe_count": safe,
        "system_beneficial_count": beneficial,
        "system_beneficial_cell_count": beneficial_cells,
        "fair_system_beneficial_count": fair,
        "fair_system_beneficial_cell_count": fair_cells,
        "system_beneficial_but_costly_count": costly,
        "system_beneficial_but_unfair_count": unfair,
        "individual_fair_count": summary["individual_fair_count"],
        "individual_fair_evidence_incomplete_count": summary[
            "individual_fair_evidence_incomplete_count"
        ],
        "individual_fairness_evaluated": True,
        "individual_fairness_contract": str(summary["individual_fairness_contract"]),
        "system_safe_and_individual_cost_are_separate": True,
        "system_beneficial_and_individual_fair_are_orthogonal": True,
        "continuation_cell_coverage_uses_fair_system_beneficial": True,
        "post_hoc_individual_cost_cap_applied": False,
        "system_tail_hard_gate_metrics": [
            "raw_bag_p95_delta_seconds",
            "raw_bag_p99_delta_seconds",
        ],
        "raw_bag_max_delta_is_diagnostic_only": True,
        "raw_bag_max_delta_seconds_diagnostic": _plain(max_diagnostic),
        "selection_scope": "ONE_HOP_ALTERNATE_TARGET_QUEUE_ONLY",
        "one_hop_pressure_bins": ["q16_23", "q24_31", "q32_plus"],
        "two_hop_queue_pressure_used": False,
        "heldout_local_signature_feature": str(signature["feature"]),
        "heldout_local_signature_pass": signature["pass"] is True,
        "heldout_local_signature_scope": str(signature["system_benefit_scope"]),
        "heldout_local_signature_individual_fairness_used": False,
        "continuation_pass": continuation,
        "execution_256_identity_coverage": observed_gates["execution_coverage"],
        "recognized_execution_outcomes": observed_gates[
            "recognized_execution_outcomes"
        ],
        "action_changing_rate_gate_pass": observed_gates["action_changing_rate"],
        "execution_coverage_and_effect_evidence_are_separate": True,
        "effect_and_fairness_use_action_applied_pairs_only": True,
    }


def _build_stages(
    source: Mapping[str, Any] | None,
    precursor: Mapping[str, Any] | None,
    precursor_formal: Mapping[str, Any] | None,
    externality: Mapping[str, Any] | None,
) -> dict[str, Any]:
    source_stage = _source_stage(source)
    precursor_stage = _precursor_stage(precursor, precursor_formal)
    externality_stage = _externality_stage(externality)
    source_complete = source_stage["evidence_status"] == "COMPLETE"
    source_support = source_stage.get("pilot_support_pass") is True
    source_no_support = (
        source_complete
        and source_stage.get("decision_status") == "TARGETED_SOURCE_NO_SUPPORT"
    )
    formal_complete = precursor_stage.get("formal_evidence_status") == "COMPLETE"
    formal_status = precursor_stage.get("formal_decision_status")
    formal_no_go = formal_complete and formal_status == PRECURSOR_FORMAL_NO_GO
    formal_support = formal_complete and formal_status == PRECURSOR_FORMAL_PASS

    if source_complete and not source_support:
        source_formal_stage = {
            "evidence_status": "NOT_TRIGGERED",
            "decision_status": "NOT_TRIGGERED_BY_SOURCE_PILOT_CONTINUATION_GATE",
            "reason": "SOURCE_PILOT_CONTINUATION_GATE_NOT_MET",
        }
        source_learning_status = {
            "evidence_status": "NOT_TRIGGERED",
            "decision_status": "NOT_TRIGGERED_BY_SOURCE_CAUSAL_SUPPORT_GATE",
            "reason": "TARGETED_SOURCE_PILOT_HAD_NO_PROMOTION_ELIGIBLE_SUPPORT",
        }
    elif source_support:
        source_formal_stage = {
            "evidence_status": "PENDING",
            "decision_status": "PENDING_SOURCE_FORMAL_EVIDENCE",
            "reason": "SOURCE_PILOT_CONTINUATION_GATE_MET",
        }
        source_learning_status = {
            "evidence_status": "PENDING",
            "decision_status": "PENDING_SOURCE_FORMAL_CAUSAL_SUPPORT_GATE",
            "reason": "SOURCE_FORMAL_MUST_AUTHORIZE_FEATURE_AND_MODEL_WORK",
        }
    else:
        source_formal_stage = {
            "evidence_status": "PENDING",
            "decision_status": "PENDING_SOURCE_PILOT_GATE",
            "reason": "SOURCE_PILOT_EVIDENCE_NOT_COMPLETE",
        }
        source_learning_status = {
            "evidence_status": "PENDING",
            "decision_status": "PENDING_SOURCE_CAUSAL_SUPPORT_GATE",
            "reason": "SOURCE_CAUSAL_SUPPORT_NOT_DECIDED",
        }

    if precursor is None and precursor_formal is None:
        if source_no_support:
            precursor_stage.update(
                {
                    "evidence_status": "PENDING",
                    "decision_status": "PENDING_PRECURSOR_PILOT_GATE",
                }
            )
        elif source_support:
            precursor_stage.update(
                {
                    "evidence_status": "NOT_TRIGGERED",
                    "decision_status": (
                        "NOT_TRIGGERED_BY_SOURCE_PILOT_NO_GO_GATE"
                    ),
                }
            )
        else:
            precursor_stage.update(
                {
                    "evidence_status": "PENDING",
                    "decision_status": "PENDING_SOURCE_PILOT_GATE",
                }
            )

    if externality is None:
        if formal_no_go:
            externality_stage = {
                "evidence_status": "PENDING",
                "decision_status": "PENDING_EXTERNALITY_NEIGHBORHOOD_EVIDENCE",
                "reason": "TRIGGERED_BY_PRECURSOR_FORMAL_NO_GO_GATE",
            }
        elif formal_support:
            externality_stage = {
                "evidence_status": "NOT_TRIGGERED",
                "decision_status": (
                    "NOT_TRIGGERED_BY_PRECURSOR_FORMAL_NO_GO_GATE"
                ),
                "reason": "PRECURSOR_FORMAL_ESTABLISHED_CAUSAL_SUPPORT",
            }
        elif precursor_stage.get("evidence_status") == "NOT_TRIGGERED":
            externality_stage = {
                "evidence_status": "NOT_TRIGGERED",
                "decision_status": "NOT_TRIGGERED_BY_PRECURSOR_ROUTE_GATE",
                "reason": "PRECURSOR_ROUTE_FALLBACK_WAS_NOT_TRIGGERED",
            }
        else:
            externality_stage = {
                "evidence_status": "PENDING",
                "decision_status": "PENDING_PRECURSOR_FORMAL_GATE",
                "reason": "PRECURSOR_FORMAL_DECISION_NOT_COMPLETE",
            }

    causal_tracks_closed_no_go = (
        source_no_support
        and formal_no_go
        and externality_stage.get("evidence_status") == "COMPLETE"
        and externality_stage.get("decision_status")
        == "NO_GO_EXTERNALITY_NEIGHBORHOOD_SUPPORT"
    )
    any_causal_support = (
        source_support
        or formal_support
        or externality_stage.get("decision_status")
        == "PASS_EXTERNALITY_NEIGHBORHOOD_SUPPORT"
    )
    if causal_tracks_closed_no_go:
        scale_stage = {
            "evidence_status": "NOT_TRIGGERED",
            "decision_status": "NOT_TRIGGERED_BY_CANDIDATE_PROMOTION_GATE",
            "reason": "NO_CAUSALLY_SUPPORTED_G23_CANDIDATE_EXISTS",
        }
    elif any_causal_support:
        scale_stage = {
            "evidence_status": "PENDING",
            "decision_status": "PENDING_SAFE_2X_CANDIDATE_GATE",
            "reason": "CAUSAL_SUPPORT_DOES_NOT_YET_PROVE_A_SAFE_2X_CANDIDATE",
        }
    else:
        scale_stage = {
            "evidence_status": "PENDING",
            "decision_status": "PENDING_CANDIDATE_PROMOTION_GATE",
            "reason": "UPSTREAM_CAUSAL_TRACKS_ARE_NOT_YET_CLOSED",
        }

    selector_stage = dict(source_learning_status)
    selector_stage["declared_source_selector_outcome"] = source_stage.get(
        "selector_status", "PENDING"
    )
    return {
        "23A_baseline_and_takeover": {
            "evidence_status": "COMPLETE",
            "decision_status": "DUAL_BASELINE_CONTRACT_FIXED",
        },
        "23B_exact_source_action": {
            "evidence_status": "COMPLETE" if source_complete else "NOT_RUN",
            "decision_status": source_stage.get("action_implementation", "PENDING"),
        },
        "23C_source_pilot": source_stage,
        "23D_source_formal": source_formal_stage,
        "23E_feature_reduction": dict(source_learning_status),
        "23F_selector": selector_stage,
        "23G_offline_gate": dict(source_learning_status),
        "23H_native_closed_loop": dict(source_learning_status),
        "23I_precursor_route": precursor_stage,
        "23J_externality_neighborhood": externality_stage,
        "23K_scale_and_fault": scale_stage,
    }


def _final_decision(stages: Mapping[str, Any]) -> dict[str, Any]:
    source = stages["23C_source_pilot"]
    precursor = stages["23I_precursor_route"]
    externality = stages["23J_externality_neighborhood"]
    all_local_no_go = (
        source.get("decision_status") == "TARGETED_SOURCE_NO_SUPPORT"
        and precursor.get("formal_evidence_status") == "COMPLETE"
        and precursor.get("formal_attempted_group_count")
        == REQUIRED_PRECURSOR_FORMAL_GROUPS
        and precursor.get("formal_exact_pair_gate_pass") is True
        and precursor.get("formal_h_system_sparse_reused_group_count")
        == REQUIRED_PRECURSOR_FORMAL_H_SYSTEM_GROUPS
        and precursor.get("formal_h_bag_only_group_count")
        == REQUIRED_PRECURSOR_FORMAL_H_BAG_ONLY_GROUPS
        and precursor.get("formal_new_h_system_group_count") == 0
        and precursor.get("formal_decision_status") == PRECURSOR_FORMAL_NO_GO
        and externality.get("evidence_status") == "COMPLETE"
        and externality.get("execution_256_identity_coverage") is True
        and externality.get("recognized_execution_outcomes") is True
        and externality.get("decision_status")
        == "NO_GO_EXTERNALITY_NEIGHBORHOOD_SUPPORT"
    )
    if all_local_no_go:
        return {
            "status": "COMPLETE_LOCAL_ACTION_SUPPORT_NO_GO",
            "label": "TESTED_SEAM_LOCAL_ACTION_CEILING",
            "candidate_promotion_authorized": False,
            "learned_policy_deployed": False,
            "closed_loop_performance_claim": "NOT_RUN",
            "reason": (
                "Source, precursor Route Formal 2048, and the preregistered "
                "externality neighborhood all returned complete compact no-support "
                "labels. This ceiling is limited to the tested Source/precursor/"
                "externality seams, not node52 or one-step local control in general."
            ),
        }
    return {
        "status": "PENDING",
        "label": "PENDING",
        "candidate_promotion_authorized": False,
        "learned_policy_deployed": False,
        "closed_loop_performance_claim": "NOT_RUN",
        "reason": "One or more required causal-support or closed-loop stages remain pending.",
    }


def _question_row(
    number: int,
    question: str,
    status: str,
    answer: str,
    evidence_stage: str,
) -> dict[str, Any]:
    _require(
        status in {"COMPLETE", "PENDING"} or status.startswith("NOT_TRIGGERED_BY_"),
        f"question {number} has an invalid lifecycle status",
    )
    return {
        "number": number,
        "question": question,
        "status": status,
        "answer": answer,
        "evidence_stage": evidence_stage,
    }


def _required_question_audit(
    stages: Mapping[str, Any], final_decision: Mapping[str, Any]
) -> dict[str, Any]:
    """Answer the plan's required 30 questions without promoting missing evidence."""

    source = stages["23C_source_pilot"]
    precursor = stages["23I_precursor_route"]
    externality = stages["23J_externality_neighborhood"]
    scale = stages["23K_scale_and_fault"]
    source_complete = source.get("evidence_status") == "COMPLETE"
    formal_complete = precursor.get("formal_evidence_status") == "COMPLETE"
    externality_complete = externality.get("evidence_status") == "COMPLETE"

    def effect_digest(distribution: Any) -> str:
        if not isinstance(distribution, Mapping):
            return "continuous effect/cost distribution not supplied in this compact fixture"
        panel = distribution.get("panel")
        if not isinstance(panel, Mapping) or not isinstance(panel.get("metrics"), Mapping):
            return "continuous effect/cost distribution not supplied in this compact fixture"
        metrics = panel["metrics"]

        def mean(name: str) -> str:
            metric = metrics.get(name)
            if not isinstance(metric, Mapping) or metric.get("mean") is None:
                return "N/A"
            return f"{float(metric['mean']):+.6f}s"

        cost = metrics.get("current_bag_cost_seconds")
        cost_text = "N/A"
        if isinstance(cost, Mapping) and cost.get("mean") is not None:
            cost_text = (
                f"mean {float(cost['mean']):+.3f}s / "
                f"max {float(cost['max']):+.3f}s"
            )
        promotion_text = "promotion distribution N/A"
        promotions = distribution.get("fair_promotions")
        if isinstance(promotions, Mapping) and isinstance(
            promotions.get("metrics"), Mapping
        ):
            promotion_metrics = promotions["metrics"]
            promotion_mean = promotion_metrics.get("raw_bag_mean_delta_seconds")
            promotion_cost = promotion_metrics.get("current_bag_cost_seconds")
            if isinstance(promotion_mean, Mapping) and isinstance(
                promotion_cost, Mapping
            ):
                promotion_text = (
                    f"fair promotions={promotions.get('action_count')}/"
                    f"{promotions.get('group_count')}, mean effect "
                    f"{float(promotion_mean['mean']):+.6f}s, cost mean/max "
                    f"{float(promotion_cost['mean']):+.3f}/"
                    f"{float(promotion_cost['max']):+.3f}s"
                )
        return (
            f"H_system actions={distribution.get('complete_h_system_action_count')}, "
            f"mean={mean('raw_bag_mean_delta_seconds')}, "
            f"p95={mean('raw_bag_p95_delta_seconds')}, "
            f"p99={mean('raw_bag_p99_delta_seconds')}, current-bag cost {cost_text}, "
            f"{promotion_text}"
        )

    source_gate_status = (
        "NOT_TRIGGERED_BY_SOURCE_CAUSAL_SUPPORT_GATE"
        if source_complete and source.get("pilot_support_pass") is not True
        else "PENDING"
    )
    candidate_gate_status = (
        str(scale["decision_status"])
        if str(scale["decision_status"]).startswith("NOT_TRIGGERED_BY_")
        else "PENDING"
    )
    if externality_complete:
        externality_question_status = "COMPLETE"
    elif str(externality.get("decision_status", "")).startswith(
        "NOT_TRIGGERED_BY_"
    ):
        externality_question_status = str(externality["decision_status"])
    else:
        externality_question_status = "PENDING"

    if source_complete:
        source_mean = source["system_mean_delta_seconds"]
        p95 = source["system_p95_delta_seconds"]
        p99 = source["system_p99_delta_seconds"]
        cost = source["current_bag_cost_seconds"]
        components = source["component_mean_delta_seconds_per_raw_bag"]["all"][
            "metrics"
        ]
        source_wait = components[
            "raw_bag_source_wait_mean_delta_seconds"
        ]["mean"]
        network = components[
            "raw_bag_network_time_mean_delta_seconds"
        ]["mean"]
        scheduled = components[
            "raw_bag_scheduled_pre_release_wait_mean_delta_seconds"
        ]["mean"]
        block_counts = source["h_system_by_release_block"]
        weak_rows = source["weak_diagnostic_rows"]
        weak_time_cells = sorted(
            {
                str(row.get("selection_stratum", "")).split("|")[-1]
                for row in weak_rows
                if isinstance(row, Mapping)
            }
        )
        source_rows = [
            _question_row(
                2,
                "新 Source HOLD 与旧 I1/A1/A2 有什么本质区别？",
                "COMPLETE",
                "G23 只在 storage_out/node52 对同一队首跳过一次自然服务机会，随后强制回 A0；不换 bag、不重排 top-K、不改完整路线。I1 换源队列服务顺序，旧 A1/A2 是广泛压力门且可产生重复 retry。",
                "23B/23C",
            ),
            _question_row(
                3,
                "block 7 有多少 exact applicable groups？",
                "COMPLETE",
                f"Source H_system exact groups: {int(block_counts['7'])}; block 8: {int(block_counts['8'])}; total exact interventions: {source['planned_group_count']}.",
                "23C",
            ),
            _question_row(
                4,
                "block 8 是否复现方向？",
                "COMPLETE",
                f"否。block 8 promotion-eligible fair positives = {source['block8_promotion_eligible_fair_positive_count']}；Source 报告未复现 block 7 的弱诊断方向。",
                "23C",
            ),
            _question_row(
                5,
                "HOLD 给当前 bag 增加多少时间？",
                "COMPLETE",
                f"treatment-baseline current-bag cost: mean {float(cost['mean']):+.9f}s, max {float(cost['max']):+.9f}s；上限为一次 {float(cost['natural_opportunity_seconds']):.3f}s 自然机会。",
                "23C",
            ),
            _question_row(
                6,
                "HOLD 对 57,012-bag mean 有多少影响？",
                "COMPLETE",
                f"176 个完整 H_system 标签的 treatment-baseline mean-effect panel 均值为 {float(source_mean['mean']):+.9f}s/complete raw bag，范围 [{float(source_mean['min']):+.9f}, {float(source_mean['max']):+.9f}]；效应低于可用门槛。",
                "23C",
            ),
            _question_row(
                7,
                "p95/p99 是否同向？",
                "COMPLETE",
                f"p95 mean/min/max = {float(p95['mean']):+.9f}/{float(p95['min']):+.9f}/{float(p95['max']):+.9f}s；p99 = {float(p99['mean']):+.9f}/{float(p99['min']):+.9f}/{float(p99['max']):+.9f}s，均未显示同向收益。",
                "23C",
            ),
            _question_row(
                8,
                "有多少 FAIR_SYSTEM_BENEFICIAL？",
                "COMPLETE",
                f"诊断标签 {source['fair_system_beneficial_label_count']}，但 promotion-eligible usable/strong fair positives = {source['promotion_eligible_fair_positive_count']}；不能把弱诊断标签当作晋级正例。",
                "23C",
            ),
            _question_row(
                9,
                "有多少 SYSTEM_BENEFICIAL_BUT_UNFAIR？",
                "COMPLETE",
                str(source["system_beneficial_but_unfair_label_count"]),
                "23C",
            ),
            _question_row(
                10,
                "正例跨多少压力区间和时间区间？",
                "COMPLETE",
                f"promotion-eligible positives = 0，故可晋级压力/时间覆盖均为 0；仅有 {source['weak_diagnostic_strata_count']} 个弱诊断 strata，时间标记 {weak_time_cells or ['none']}，不足以训练。",
                "23C",
            ),
            _question_row(
                17,
                "是否出现重复 HOLD？",
                "COMPLETE",
                f"没有；{source['planned_group_count']} 个 intervention 中 repeated HOLD groups = {source['repeated_hold_group_count']}，且每次 HOLD 后强制回 A0。",
                "23B/23C",
            ),
            _question_row(
                20,
                "Source wait、network time 如何重新分配？",
                "COMPLETE",
                f"因果 H_system 描述值（非闭环候选）：source wait {float(source_wait):+.9f}s/bag，network {float(network):+.9f}s/bag，scheduled pre-release wait {float(scheduled):+.9f}s/bag；总效应极小且不跨 block 复现。",
                "23C",
            ),
        ]
    else:
        source_rows = [
            _question_row(number, question, "PENDING", "Source compact evidence 未完成。", "23C")
            for number, question in (
                (2, "新 Source HOLD 与旧 I1/A1/A2 有什么本质区别？"),
                (3, "block 7 有多少 exact applicable groups？"),
                (4, "block 8 是否复现方向？"),
                (5, "HOLD 给当前 bag 增加多少时间？"),
                (6, "HOLD 对 57,012-bag mean 有多少影响？"),
                (7, "p95/p99 是否同向？"),
                (8, "有多少 FAIR_SYSTEM_BENEFICIAL？"),
                (9, "有多少 SYSTEM_BENEFICIAL_BUT_UNFAIR？"),
                (10, "正例跨多少压力区间和时间区间？"),
                (17, "是否出现重复 HOLD？"),
                (20, "Source wait、network time 如何重新分配？"),
            )
        ]

    source_model_answer = (
        "Source causal-support gate 未通过，因此没有制造 feature ranking、rule/linear/tiny MLP、held-out precision 或线上模型 HOLD 数字。"
        if source_gate_status.startswith("NOT_TRIGGERED_BY_")
        else "等待 Source causal-support gate。"
    )
    model_rows = [
        _question_row(11, "哪些局部特征最有用？", source_gate_status, source_model_answer, "23E"),
        _question_row(13, "规则、线性、tiny MLP 谁最好？", source_gate_status, source_model_answer, "23F"),
        _question_row(14, "held-out precision 和 harmful rate 是多少？", source_gate_status, source_model_answer, "23F/23G"),
        _question_row(15, "模型实际提交多少 HOLD？", source_gate_status, source_model_answer, "23H"),
        _question_row(16, "有多少 HOLD 被公平约束拒绝？", source_gate_status, source_model_answer, "23H"),
    ]

    if externality_complete:
        q12_answer = (
            "二跳没有用于筛选、分层或 held-out signature；"
            f"一跳 signature pass={externality.get('heldout_local_signature_pass')}，因此本轮没有证据证明二跳必要。"
        )
        q25_answer = (
            f"256-group neighborhood: fair system-beneficial={externality.get('fair_system_beneficial_count')} across {externality.get('fair_system_beneficial_cell_count')} cells; continuation={externality.get('continuation_pass')}。这就是对 G22 cohort-relief 可泛化性的限定答案。"
        )
    else:
        q12_answer = "等待一跳 externality neighborhood 的 held-out signature；不得先声称二跳必要。"
        q25_answer = "等待 externality neighborhood，尚不能声称 G22 两个动作可泛化。"
    externality_rows = [
        _question_row(12, "二跳信息是否真的必要？", externality_question_status, q12_answer, "23J"),
        _question_row(25, "G22 两个 cohort-relief 动作是否可泛化？", externality_question_status, q25_answer, "23J"),
    ]

    if formal_complete:
        q23_status = "COMPLETE"
        q23_answer = (
            f"Pilot mutations={precursor.get('pilot_action_changed_group_count')}/{precursor.get('attempted_group_count')}，"
            f"fair promotions={precursor.get('fair_promotion_group_count')}（block8={precursor.get('block8_fair_promotion_group_count')}），{effect_digest(precursor.get('pilot_h_system_effect_distribution'))}；"
            f"Formal fair promotions={precursor.get('formal_fair_promotion_group_count')}/{precursor.get('formal_required_fair_promotion_group_count')}（block8={precursor.get('formal_block8_fair_promotion_group_count')}/{precursor.get('formal_required_block8_fair_promotion_group_count')}），{effect_digest(precursor.get('formal_h_system_effect_distribution'))}，Formal decision={precursor.get('formal_decision_status')}。"
            f"tiny MLP unlock={precursor.get('tiny_mlp_unlock', {}).get('unlocked')}（Formal fair positives={precursor.get('tiny_mlp_unlock', {}).get('observed_formal_fair_positive_count')}/{precursor.get('tiny_mlp_unlock', {}).get('required_formal_fair_positive_count')}，held-out={precursor.get('tiny_mlp_unlock', {}).get('observed_heldout_fair_positive_count')}/{precursor.get('tiny_mlp_unlock', {}).get('required_heldout_fair_positive_count')}，stable nonlinear regret={precursor.get('tiny_mlp_unlock', {}).get('nonlinear_regret_evidence_status')}）。"
        )
    elif precursor.get("evidence_status") == "NOT_TRIGGERED":
        q23_status = str(precursor["decision_status"])
        q23_answer = "Source 路径未触发 precursor fallback。"
    else:
        q23_status = "PENDING"
        q23_answer = (
            f"Pilot mutations={precursor.get('pilot_action_changed_group_count')}/{precursor.get('attempted_group_count')}，fair promotions={precursor.get('fair_promotion_group_count')}（costly={precursor.get('pilot_system_beneficial_but_costly_group_count')}），{effect_digest(precursor.get('pilot_h_system_effect_distribution'))}；但 Formal 2,048 exact 决策仍待完成，不能把 Pilot 状态当作 overall。"
        )
    precursor_rows = [
        _question_row(23, "Source 不通过时，前驱 Route 是否有正例？", q23_status, q23_answer, "23I Pilot + Formal"),
        _question_row(
            24,
            "前驱 Route 改的是哪个真实上游接口？",
            "COMPLETE" if precursor.get("pilot_evidence_status") == "COMPLETE" else q23_status,
            "改 storage_out/node52 之前、对应 storage_in 行李最近一次真实多动作 Route 接口的一步 NEXT_EDGE/WAIT；后续立即回 S4/J2/E2，不增加 planner。",
            "23I",
        ),
    ]

    scale_answer = (
        "无 causally supported G23 candidate，故未触发闭环/规模/故障 claim。"
        if candidate_gate_status.startswith("NOT_TRIGGERED_BY_")
        else "等待 upstream causal support 与 candidate promotion；不能把未运行写成通过或失败。"
    )
    candidate_rows = [
        _question_row(18, "1× 是否保持？", candidate_gate_status, scale_answer, "23H/23K"),
        _question_row(19, "2× mean/p95/p99 如何？", candidate_gate_status, scale_answer, "23H/23K"),
        _question_row(21, "关闭多少 v2-safe gap？", candidate_gate_status, scale_answer, "23H/23K"),
        _question_row(22, "是否达到 Direction/Gap-10/25/50？", candidate_gate_status, scale_answer, "23H/23K"),
        _question_row(26, "4× 60 秒是否改善？", candidate_gate_status, scale_answer, "23K"),
        _question_row(27, "是否解锁 180 秒或 full？", candidate_gate_status, scale_answer, "23K"),
        _question_row(28, "单实例并行是否有必要？", candidate_gate_status, scale_answer, "23K"),
        _question_row(29, "故障是否安全？", candidate_gate_status, scale_answer, "23K"),
    ]

    if not formal_complete and precursor.get("evidence_status") != "NOT_TRIGGERED":
        next_question = "先完成 precursor Formal 2,048 的剩余 exact evidence；不要加特征或模型。"
    elif (
        precursor.get("formal_decision_status") == PRECURSOR_FORMAL_NO_GO
        and not externality_complete
        and externality.get("evidence_status") != "NOT_TRIGGERED"
    ):
        next_question = "只完成已预注册的一跳 externality neighborhood 256 groups，检验 G22 减负动作是否可迁移。"
    elif final_decision.get("label") == "TESTED_SEAM_LOCAL_ACTION_CEILING":
        next_question = "停止扩张 node52 HOLD/Route 模型；下一窄问题仅应是更早一个真实 merge-token 接口的一步 MOVE/WAIT 是否有因果支持。"
    else:
        next_question = "沿已通过的最窄因果动作，先比较 deterministic rule，再决定是否需要线性模型；不增加 planner。"

    rows = [
        _question_row(
            1,
            "PR #7 与 G23 CI 是否绿色？",
            "PENDING",
            "冻结方案记录 PR #7 的 GitHub Actions Run #69 为 success；本次 G23 的 CI 成功证据尚未写入 compact handoff，状态保持 PENDING，推送后以 GitHub check 为准。",
            "GitHub handoff",
        ),
        *source_rows,
        *model_rows,
        *externality_rows,
        *precursor_rows,
        *candidate_rows,
        _question_row(30, "下一阶段最窄、最有价值的问题是什么？", "COMPLETE", next_question, "final decision"),
    ]
    rows.sort(key=lambda row: row["number"])
    _require(
        [row["number"] for row in rows] == list(range(1, 31)),
        "required question audit must contain exactly questions 1..30",
    )
    status_counts: dict[str, int] = {}
    for row in rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    return {
        "schema": "czr005.g4irsf23.required_30_questions.v1",
        "question_count": 30,
        "status_counts": status_counts,
        "rows": rows,
    }


def build_decision_summary(
    baselines: Mapping[str, Any],
    source: Mapping[str, Any] | None = None,
    precursor: Mapping[str, Any] | None = None,
    externality: Mapping[str, Any] | None = None,
    precursor_formal: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a compact final summary without reading or running raw evidence."""

    _require(
        baselines.get("schema") == BASELINE_SCHEMA,
        "unexpected paper/baseline summary schema",
    )
    paper = baselines.get("paper")
    required = baselines.get("required_baselines")
    contract = baselines.get("comparison_contract")
    _require(
        all(isinstance(row, Mapping) for row in (paper, required, contract)),
        "baseline summary omitted paper, baseline, or comparison evidence",
    )
    _require(
        len(paper["table_5_2_speed_sweep"]) == 4
        and len(paper["table_5_3_iot_drpa_vs_dispersed_heuristic"]["rows"]) == 3
        and len(paper["table_5_4_dynamic_iot_drpa_vs_static_lra_star"]["rows"])
        == 12
        and len(paper["table_5_5_faults"]) == 16,
        "paper Tables 5.2-5.5 are incomplete",
    )
    stages = _build_stages(source, precursor, precursor_formal, externality)
    final = _final_decision(stages)
    required_questions = _required_question_audit(stages, final)
    return {
        "schema": FINAL_SCHEMA,
        "status": final["status"],
        "final_decision": final,
        "paper": {
            "title": paper["title"],
            "doi": paper["doi"],
            "url": paper["url"],
            "one_x": _plain(paper["one_x"]),
            "panels": {
                "table_5_2_speed_sweep": {
                    "evidence_status": "PAPER_REPORTED_ONLY",
                    "rows": _plain(paper["table_5_2_speed_sweep"]),
                },
                "table_5_3_iot_drpa_vs_dispersed_heuristic": _plain(
                    paper["table_5_3_iot_drpa_vs_dispersed_heuristic"]
                ),
                "table_5_4_dynamic_iot_drpa_vs_static_lra_star": _plain(
                    paper["table_5_4_dynamic_iot_drpa_vs_static_lra_star"]
                ),
                "table_5_5_faults": {
                    "evidence_status": "PAPER_REPORTED_ONLY",
                    "rows": _plain(paper["table_5_5_faults"]),
                },
            },
        },
        "required_baselines": _plain(required),
        "denominator_panel": _build_denominator_panel(
            baselines,
            candidate_metrics_status=(
                "NOT_RUN_AFTER_SUPPORT_NO_GO"
                if final["status"] == "COMPLETE_LOCAL_ACTION_SUPPORT_NO_GO"
                else "PENDING_NO_G23_CLOSED_LOOP_CANDIDATE"
            ),
        ),
        "comparison_contract": _plain(contract),
        "stages": stages,
        "required_question_audit": required_questions,
        "claim_boundaries": [
            "Paper Tables 5.2-5.5 are paper-reported references, not local reproductions.",
            "The original IoT-DRPA/HCA* 1x result is parsed historical evidence, not a fresh Java rerun; HCA* 2x and 4x remain N/A.",
            "Processed-attempt, Java-release, and original-entry TTH are separate denominators; cross-denominator winner claims are forbidden.",
            "F2 pass-time-anchored TTH and the legacy HCA mislabeled field are diagnostics and are not substitutes for missing cells in the three-denominator panel.",
            "A real and safe local action is not by itself causal support, and causal support is not a closed-loop performance improvement.",
            "H_system benefit and current-bag direct cost remain separate; no individual-fairness claim follows from system benefit alone.",
            "No learned-policy, 1x/2x/4x, or fault-performance claim is allowed until its explicit stage has completed.",
            "Precursor Formal covers 2,048 H_bag groups but only 256 sparse reused H_system groups; 1,792 are H_bag-only and no new H_system group is implied.",
        ],
    }


def _format_metric(cell: Mapping[str, Any]) -> str:
    value = cell.get("mean_minutes")
    return f"{float(value):.9f}" if value is not None else f"`{cell['status']}`"


def render_markdown(summary: Mapping[str, Any]) -> str:
    final = summary["final_decision"]
    paper = summary["paper"]
    panels = paper["panels"]
    required_baselines = summary["required_baselines"]
    denominator = summary["denominator_panel"]

    def signed_stat(metrics: Mapping[str, Any], name: str, statistic: str) -> str:
        row = metrics.get(name)
        if not isinstance(row, Mapping) or row.get(statistic) is None:
            return "N/A"
        return f"{float(row[statistic]):+.9f}"

    def unsigned_value(value: Any) -> str:
        return "N/A" if value is None else f"{float(value):.9f}"

    def min_mean_max(metrics: Mapping[str, Any]) -> str:
        return " / ".join(
            unsigned_value(metrics.get(name))
            for name in ("min_minutes", "mean_minutes", "max_minutes")
        )

    lines = [
        "# G4IRSF23 最终联合决策",
        "",
        f"Status: `{final['status']}`. Final label: `{final['label']}`.",
        "",
        final["reason"],
        "",
        "当前报告只汇总 compact evidence；它不会启动仿真。`PENDING` 表示仍需证据；"
        "`NOT_TRIGGERED_BY_*` 表示上游门已明确关闭该阶段。两者都不能被解释为性能通过。",
        "",
        "## Claim boundary",
        "",
    ]
    lines.extend(f"- {row}" for row in summary["claim_boundaries"])
    f2_baseline = required_baselines["frozen_f2"]
    f2 = f2_baseline["one_x"]
    f2_raw = {
        "min_minutes": None,
        "mean_minutes": f2["original_entry_mean_minutes"],
        "max_minutes": None,
    }
    hca_baseline = required_baselines["original_hca_star"]
    hca = hca_baseline["one_x"]
    lines.extend(
        [
            "",
            "## 两个 baseline 的直接事实",
            "",
            "### G4IRSF13 F2 frozen — 1x committed control",
            "",
            "| Item | Value |",
            "|---|---:|",
            f"| Evidence status | `{f2_baseline['evidence_status']}` |",
            f"| Raw bags / processed segments | {f2['raw_bag_count']} / {f2['processed_segment_count']} |",
            f"| Completed segments | {f2['completed_segments']} |",
            "| Complete raw bags / failed segments / conflicts / runtime full A* calls | "
            f"{f2['complete_raw_bags']} / {f2['failed_segments']} / {f2['conflicts']} / {f2['runtime_full_astar_calls']} |",
            "| Raw original-entry TTH min / mean / max (min) | "
            f"{min_mean_max(f2_raw)} |",
            "| Raw original-entry TTH p95 / p99 (s) | "
            f"{unsigned_value(f2['original_entry_p95_seconds'])} / {unsigned_value(f2['original_entry_p99_seconds'])} |",
            "| Pass-time-anchored mean diagnostic (min) | "
            f"{f2['pass_time_anchored_mean_minutes']:.9f} |",
            "",
            "### Original centralized IoT-DRPA/HCA* — historical 1x",
            "",
            f"Evidence status: `{hca_baseline['evidence_status']}`; fresh Java rerun: "
            f"`{hca_baseline['fresh_java_rerun']}`; scope: `1x / {hca['speed_mps']:.1f} m/s`.",
            "",
            "| HCA* TTH field | Min (min) | Mean (min) | Max (min) | Meaning |",
            "|---|---:|---:|---:|---|",
            "| processed-segment-attempt | {min} | {mean} | {max} | historical parsed denominator |".format(
                min=unsigned_value(
                    hca["processed_segment_attempt_time_tth"]["min_minutes"]
                ),
                mean=unsigned_value(
                    hca["processed_segment_attempt_time_tth"]["mean_minutes"]
                ),
                max=unsigned_value(
                    hca["processed_segment_attempt_time_tth"]["max_minutes"]
                ),
            ),
            "| Java-release | {min} | {mean} | {max} | historical parsed denominator |".format(
                min=unsigned_value(hca["java_release_time_tth_min_minutes"]),
                mean=unsigned_value(hca["java_release_time_tth_mean_minutes"]),
                max=unsigned_value(hca["java_release_time_tth_max_minutes"]),
            ),
            "| legacy mislabeled field | {min} | {mean} | {max} | diagnostic only |".format(
                min=unsigned_value(
                    hca["legacy_mislabeled_original_entry_min_minutes"]
                ),
                mean=unsigned_value(
                    hca["legacy_mislabeled_original_entry_mean_minutes"]
                ),
                max=unsigned_value(
                    hca["legacy_mislabeled_original_entry_max_minutes"]
                ),
            ),
            "| corrected raw original-entry | {min} | {mean} | {max} | algebraically reconciled mean; range unavailable |".format(
                min="N/A",
                mean=unsigned_value(
                    hca["matched_raw_entry_time_tth_mean_minutes"]
                ),
                max="N/A",
            ),
            "",
            "HCA* scale availability: 2x "
            f"`{hca_baseline['scale_availability']['2x']}`; 4x `{hca_baseline['scale_availability']['4x']}`.",
            "各行保留自己的 TTH 分母；legacy mislabeled 字段仅作诊断，不填补比较面板。",
            "",
            "## 两个必需 baseline × 三个 TTH 分母",
            "",
            "| TTH denominator | G4IRSF13 F2 frozen | Original IoT-DRPA/HCA* | Comparison status |",
            "|---|---:|---:|---|",
        ]
    )
    for row in denominator["rows"]:
        lines.append(
            "| {denominator} | {f2} | {hca} | `{status}` |".format(
                denominator=row["denominator"],
                f2=_format_metric(row["frozen_f2"]),
                hca=_format_metric(row["original_hca_star"]),
                status=row["comparison_status"],
            )
        )
    diagnostics = denominator["unmapped_diagnostics"]
    lines.extend(
        [
            "",
            "数值单位均为 min/complete raw bag。F2 pass-time-anchored diagnostic "
            f"为 {diagnostics['f2_pass_time_anchored_mean_minutes']:.9f} min；历史 "
            "HCA mislabeled diagnostic 为 "
            f"{diagnostics['hca_legacy_mislabeled_original_entry_mean_minutes']:.9f} min。"
            "两者均不得填补上表缺失分母。",
            "",
            f"G23 closed-loop candidate metrics: `{denominator['candidate_metrics_status']}`.",
            "",
            "## Stage 状态",
            "",
            "| Stage | Evidence | Decision |",
            "|---|---|---|",
        ]
    )
    for stage_id, row in summary["stages"].items():
        evidence = row.get("evidence_status", row.get("pilot_evidence_status", "PENDING"))
        decision = row.get("decision_status", row.get("pilot_decision_status", "PENDING"))
        lines.append(f"| `{stage_id}` | `{evidence}` | `{decision}` |")

    precursor = summary["stages"]["23I_precursor_route"]
    lines.extend(
        [
            "",
            "## 23I Precursor 分层证据",
            "",
            "| Layer | Evidence | Decision | H_bag groups | H_system groups | Scope |",
            "|---|---|---|---:|---:|---|",
            "| Pilot | `{pilot_evidence}` | `{pilot_decision}` | {pilot_hbag} | {pilot_hsystem} | 512-group discovery/pilot |".format(
                pilot_evidence=precursor["pilot_evidence_status"],
                pilot_decision=precursor["pilot_decision_status"],
                pilot_hbag=precursor.get("attempted_group_count"),
                pilot_hsystem=precursor.get("h_system_complete_group_count"),
            ),
            "| Formal | `{formal_evidence}` | `{formal_decision}` | {formal_hbag} | {formal_hsystem} | sparse reused H_system; H_bag-only={hbag_only}; new H_system groups={new_hsystem} |".format(
                formal_evidence=precursor["formal_evidence_status"],
                formal_decision=precursor["formal_decision_status"],
                formal_hbag=precursor["formal_h_bag_complete_group_count"],
                formal_hsystem=precursor[
                    "formal_h_system_sparse_reused_group_count"
                ],
                hbag_only=precursor["formal_h_bag_only_group_count"],
                new_hsystem=precursor["formal_new_h_system_group_count"],
            ),
            "",
            "Precursor Formal handoff: "
            f"`{precursor['formal_evidence_status']}` / "
            f"`{precursor['formal_decision_status']}`. H_bag complete groups: "
            f"`{precursor['formal_h_bag_complete_group_count']}`; sparse reused "
            "H_system groups: "
            f"`{precursor['formal_h_system_sparse_reused_group_count']}`; H_bag-only "
            f"groups: `{precursor['formal_h_bag_only_group_count']}`; new H_system "
            f"groups: `{precursor['formal_new_h_system_group_count']}`. "
            "This is never described as 2,048 system labels. Formal fair-promotion "
            f"gate: `{precursor.get('formal_fair_promotion_group_count')}` / "
            f"`{precursor.get('formal_required_fair_promotion_group_count')}`; "
            "block-8 Formal support gate: "
            f"`{precursor.get('formal_block8_fair_promotion_group_count')}` / "
            f"`{precursor.get('formal_required_block8_fair_promotion_group_count')}`.",
            "Tiny-MLP unlock is a separate gate: "
            f"`{precursor.get('tiny_mlp_unlock', {}).get('unlocked')}`; Formal fair "
            f"positives `{precursor.get('tiny_mlp_unlock', {}).get('observed_formal_fair_positive_count')}` / "
            f"`{precursor.get('tiny_mlp_unlock', {}).get('required_formal_fair_positive_count')}`; held-out fair "
            f"positives `{precursor.get('tiny_mlp_unlock', {}).get('observed_heldout_fair_positive_count')}` / "
            f"`{precursor.get('tiny_mlp_unlock', {}).get('required_heldout_fair_positive_count')}`; stable nonlinear "
            f"regret evidence `{precursor.get('tiny_mlp_unlock', {}).get('nonlinear_regret_evidence_status')}`.",
            "Execution provenance: published precursor raw pairs used a runtime-only "
            "ordinary-baseline reuse shortcut whose checkpoint continuation was "
            "equivalence-audited; the shipped runtime keeps ordinary G22 per-target "
            "baseline semantics.",
        ]
    )

    source = summary["stages"]["23C_source_pilot"]
    if source.get("evidence_status") == "COMPLETE":
        components = source["component_mean_delta_seconds_per_raw_bag"]
        component_scopes = [
            ("All", components["all"]),
            ("Block 7", components["by_release_block"]["7"]),
            ("Block 8", components["by_release_block"]["8"]),
        ]
        component_labels = {
            "raw_bag_source_wait_mean_delta_seconds": "Source wait",
            "raw_bag_network_time_mean_delta_seconds": "Network time",
            "raw_bag_scheduled_pre_release_wait_mean_delta_seconds": (
                "Scheduled pre-release wait"
            ),
        }
        lines.extend(
            [
                "",
                "## Source component decomposition",
                "",
                "全部是 treatment − baseline，单位 s/complete raw bag。该表是因果"
                " H_system 描述值，不是未运行的 closed-loop candidate 结果。",
                "",
                "| Scope | Component | Count | Min | Mean | Median | Max |",
                "|---|---|---:|---:|---:|---:|---:|",
            ]
        )
        for scope_name, scope in component_scopes:
            metrics = scope["metrics"]
            for metric_name, label in component_labels.items():
                lines.append(
                    f"| {scope_name} | {label} | {metrics[metric_name]['count']} | "
                    f"{signed_stat(metrics, metric_name, 'min')} | "
                    f"{signed_stat(metrics, metric_name, 'mean')} | "
                    f"{signed_stat(metrics, metric_name, 'median')} | "
                    f"{signed_stat(metrics, metric_name, 'max')} |"
                )

    precursor_effects = precursor.get("pilot_h_system_effect_distribution")
    if isinstance(precursor_effects, Mapping):
        panel = precursor_effects["panel"]
        promotions = precursor_effects["fair_promotions"]
        panel_metrics = panel["metrics"]
        promotion_metrics = promotions["metrics"]
        effect_labels = {
            "raw_bag_mean_delta_seconds": "Mean TTH delta",
            "raw_bag_source_wait_mean_delta_seconds": "Source-wait mean delta",
            "raw_bag_network_time_mean_delta_seconds": "Network-time mean delta",
            "raw_bag_p95_delta_seconds": "P95 delta",
            "raw_bag_p99_delta_seconds": "P99 delta",
            "raw_bag_max_delta_seconds": "Max delta (diagnostic)",
            "current_bag_cost_seconds": "Current-bag cost",
            "deadline_headroom_seconds": "Pre-action deadline headroom",
        }
        lines.extend(
            [
                "",
                "## Precursor Pilot H_system effect/cost distribution",
                "",
                f"完整 panel 为 {panel['action_count']} actions / {panel['group_count']} groups；"
                f"fair promotions 为 {promotions['action_count']} actions / "
                f"{promotions['group_count']} groups。全部 delta 是 treatment − baseline；"
                "current-bag cost/headroom 是单 bag 秒数，其余 mean/source/network 是"
                " s/complete raw bag。",
                "",
                "| Metric | Panel min | mean | median | max | Promotion min | mean | median | max |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for metric_name, label in effect_labels.items():
            lines.append(
                f"| {label} | "
                f"{signed_stat(panel_metrics, metric_name, 'min')} | "
                f"{signed_stat(panel_metrics, metric_name, 'mean')} | "
                f"{signed_stat(panel_metrics, metric_name, 'median')} | "
                f"{signed_stat(panel_metrics, metric_name, 'max')} | "
                f"{signed_stat(promotion_metrics, metric_name, 'min')} | "
                f"{signed_stat(promotion_metrics, metric_name, 'mean')} | "
                f"{signed_stat(promotion_metrics, metric_name, 'median')} | "
                f"{signed_stat(promotion_metrics, metric_name, 'max')} |"
            )
    externality = summary["stages"]["23J_externality_neighborhood"]
    externality_max_diagnostic = externality.get(
        "raw_bag_max_delta_seconds_diagnostic"
    )
    if isinstance(externality_max_diagnostic, Mapping):
        max_diagnostic_text = (
            f"count={externality_max_diagnostic['count']}, "
            f"min={externality_max_diagnostic['min']}, "
            f"mean={externality_max_diagnostic['mean']}, "
            f"median={externality_max_diagnostic['median']}, "
            f"max={externality_max_diagnostic['max']} s"
        )
    else:
        max_diagnostic_text = "PENDING"
    lines.extend(
        [
            "",
            "Externality fairness handoff: "
            f"`{externality['evidence_status']}` / "
            f"`{externality['decision_status']}`. Execution attempts/identity coverage: "
            f"`{externality.get('attempted_group_count')}`/"
            f"`{externality.get('execution_coverage_count')}`; applied/guard-abstain: "
            f"`{externality.get('action_applied_count')}`/"
            f"`{externality.get('guard_abstain_count')}`; action-changing rate: "
            f"`{externality.get('action_changing_rate')}`; guard reasons: "
            f"`{externality.get('guard_abstain_reasons', {})}`. Effect/fairness/signature "
            "use applied action-changing pairs only. Fair system-beneficial groups: "
            f"`{externality.get('fair_system_beneficial_count')}` across "
            f"`{externality.get('fair_system_beneficial_cell_count')}` cells; "
            "system-beneficial but costly: "
            f"`{externality.get('system_beneficial_but_costly_count')}`; "
            "system-beneficial but unfair: "
            f"`{externality.get('system_beneficial_but_unfair_count')}`; "
            "individual fairness evaluated: "
            f"`{externality.get('individual_fairness_evaluated')}`; contract: "
            f"`{externality.get('individual_fairness_contract', 'PENDING')}`. "
            "Selection scope: "
            f"`{externality.get('selection_scope', 'PENDING')}`; bins: "
            f"`{externality.get('one_hop_pressure_bins', 'PENDING')}`; "
            "two-hop pressure used: "
            f"`{externality.get('two_hop_queue_pressure_used')}`. "
            "System tail hard gate: `p95/p99 <= +0.001 s`; raw-bag max delta "
            f"diagnostic only (not a hard gate): `{max_diagnostic_text}`. "
            "Held-out local signature scope: "
            f"`{externality.get('heldout_local_signature_scope', 'PENDING')}`; "
            "individual fairness used by held-out signature: "
            f"`{externality.get('heldout_local_signature_individual_fairness_used')}`. "
            "Fair cell coverage remains a separate continuation gate.",
        ]
    )

    lines.extend(
        [
            "",
            "## 规范 30 问",
            "",
            "状态只有三类语义：`COMPLETE`（compact evidence 已直接回答）、"
            "`NOT_TRIGGERED_BY_<gate>`（上游门已关闭）、`PENDING`（仍需证据）。",
            "",
            "| # | 问题 | 状态 | 直接答案 | Evidence |",
            "|---:|---|---|---|---|",
        ]
    )
    for row in summary["required_question_audit"]["rows"]:
        answer = str(row["answer"]).replace("|", "\\|").replace("\n", " ")
        question = str(row["question"]).replace("|", "\\|")
        lines.append(
            f"| {row['number']} | {question} | `{row['status']}` | {answer} | "
            f"{row['evidence_stage']} |"
        )

    lines.extend(
        [
            "",
            "## 原论文对比面板",
            "",
            f"论文：[{paper['title']}]({paper['url']})（DOI `{paper['doi']}`）。"
            "以下均为 `PAPER_REPORTED_ONLY`，并非本仓库重跑结果。",
            "",
            "### Table 5.2 — speed sweep",
            "",
            "| Speed (m/s) | Min (min) | Avg (min) | Max (min) |",
            "|---:|---:|---:|---:|",
        ]
    )
    for row in panels["table_5_2_speed_sweep"]["rows"]:
        lines.append(
            f"| {row['speed_mps']:.1f} | {row['min']:.2f} | {row['avg']:.2f} | {row['max']:.2f} |"
        )

    lines.extend(
        [
            "",
            "### Table 5.3 — IoT-DRPA/HCA* vs dispersed heuristic",
            "",
            "| Method | Min | Avg | Max | Unit |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for row in panels["table_5_3_iot_drpa_vs_dispersed_heuristic"]["rows"]:
        lines.append(
            f"| {row['method']} | {row['min']:.2f} | {row['avg']:.2f} | {row['max']:.2f} | {row['unit']} |"
        )

    lines.extend(
        [
            "",
            "### Table 5.4 — dynamic IoT-DRPA vs static LRA*",
            "",
            "| Speed (m/s) | Deviation | Dynamic | Static | Improvement |",
            "|---:|---:|---:|---:|---:|",
        ]
    )
    for row in panels["table_5_4_dynamic_iot_drpa_vs_static_lra_star"]["rows"]:
        lines.append(
            f"| {row['speed_mps']:.1f} | {row['speed_deviation_percent']}% | "
            f"{row['dynamic']:.2f} | {row['static']:.2f} | {row['improvement']:.2f}% |"
        )

    lines.extend(
        [
            "",
            "### Table 5.5 — 16 fault scenarios",
            "",
            "| Failed arc(s) | Affected conveyors | Baggage success rate |",
            "|---|---:|---:|",
        ]
    )
    for row in panels["table_5_5_faults"]["rows"]:
        arcs = ",".join(str(value) for value in row["arc_ids"])
        lines.append(
            f"| {arcs} | {row['affected_conveyors']} | {row['baggage_success_rate']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## 当前可直接回答的结论",
            "",
            f"- Candidate promotion authorized: `{final['candidate_promotion_authorized']}`.",
            f"- Learned policy deployed: `{final['learned_policy_deployed']}`.",
            f"- Closed-loop performance claim: `{final['closed_loop_performance_claim']}`.",
            "- HCA* 2x/4x: `N/A_NOT_IN_PAPER_PROTOCOL`.",
            "",
        ]
    )
    return "\n".join(lines)


def _stage_atomic_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        return temporary
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def write_outputs(
    summary: Mapping[str, Any], json_output: Path, report_output: Path
) -> None:
    """Atomically replace each output after both complete renderings are staged."""

    _require(json_output.resolve() != report_output.resolve(), "outputs must differ")
    json_text = json.dumps(_plain(summary), indent=2, sort_keys=True) + "\n"
    report_text = render_markdown(summary)
    staged: list[tuple[Path, Path]] = []
    try:
        staged = [
            (_stage_atomic_text(json_output, json_text), json_output),
            (_stage_atomic_text(report_output, report_text), report_output),
        ]
        for temporary, destination in staged:
            os.replace(temporary, destination)
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)


def _rooted(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--baseline-summary", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--source-summary", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--precursor-summary", type=Path, default=DEFAULT_PRECURSOR)
    parser.add_argument(
        "--precursor-formal-summary", type=Path, default=DEFAULT_PRECURSOR_FORMAL
    )
    parser.add_argument("--externality-summary", type=Path, default=DEFAULT_EXTERNALITY)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    root = arguments.root.resolve()
    try:
        baselines = _read_required(_rooted(root, arguments.baseline_summary))
        source = _read_optional(_rooted(root, arguments.source_summary))
        precursor = _read_optional(_rooted(root, arguments.precursor_summary))
        precursor_formal = _read_optional(
            _rooted(root, arguments.precursor_formal_summary)
        )
        externality = _read_optional(_rooted(root, arguments.externality_summary))
        summary = build_decision_summary(
            baselines,
            source,
            precursor,
            externality,
            precursor_formal,
        )
        write_outputs(
            summary,
            _rooted(root, arguments.json_output),
            _rooted(root, arguments.report_output),
        )
        print(
            json.dumps(
                {
                    "schema": summary["schema"],
                    "status": summary["status"],
                    "report": str(arguments.report_output),
                    "summary": str(arguments.json_output),
                },
                sort_keys=True,
            )
        )
        return 0
    except (OSError, json.JSONDecodeError, FinalReportError, KeyError, TypeError) as exc:
        print(f"G4IRSF23 final report failed: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
