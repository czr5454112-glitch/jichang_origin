#!/usr/bin/env python3
"""Independent validator for the G4IRSF14 F--M fail-closed bundle.

This module deliberately does not import the completion generator.  It
independently fixes the output inventory, schemas, stage states, CSV columns,
row hashes, dependency graph, and negative-result semantics.  It does reuse
the already-sealed Stage-E *static payload* validator; unlike the Stage-E
current-disk entrypoint, that validation never requires the generation
machine's absolute extension-module path to exist.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT, ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from scripts.eval.g4irsf14_opportunity_census import (  # noqa: E402
    BUNDLE_PATHS as STAGE_E_BUNDLE_PATHS,
    CLONE_MANIFEST_PATH as STAGE_E_MANIFEST_PATH,
    OpportunityCensusError,
    validate_blocker_bundle_payloads,
)


MAP_RAW_SHA256 = (
    "9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4"
)
TASK_RAW_SHA256 = (
    "968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f"
)
MIN_FORMAL_INTERVENTIONS = 2_000

UPSTREAM_CENSUS = Path("outputs/tables/g4irsf14_opportunity_census.json")
UPSTREAM_MERGE_TABLE = Path("outputs/tables/g4irsf14_merge_rule_ab.csv")
UPSTREAM_MERGE_CONFIG = Path(
    "artifacts/configs/g4irsf14_merge_grant_protocol.json"
)
BASELINE_REGISTRY = Path("artifacts/gates/g4irsf14_baseline_registry.json")
F2_FROZEN_CONTROL = Path("artifacts/policies/g4irsf14_f2_frozen_control.json")
FAULT_FROZEN_CONTROL = Path(
    "artifacts/policies/g4irsf14_fault_frozen_control.json"
)
G13_FINAL_BUNDLE = Path(
    "artifacts/policies/g4irsf13_final_candidate_bundle.json"
)
G13_FAULT_BUNDLE = Path(
    "artifacts/policies/g4irsf13_fault_control_bundle.json"
)
MAP_PATH = Path("data/processed/maps/map2.json")
TASK_PATH = Path("data/processed/tasks/inputdata.jsonl")
GENERATOR_PATH = Path("scripts/eval/g4irsf14_fail_closed_completion.py")
VALIDATOR_PATH = Path("scripts/validate_g4irsf14_fail_closed_completion.py")
STAGE_E_STATIC_VALIDATOR_PATH = Path(
    "scripts/eval/g4irsf14_opportunity_census.py"
)
HASH_POLICY_PATH = Path(".gitattributes")

PINNED_F2_MEAN_MINUTES = 41.514218717973414
PINNED_V2_SAFE_MEAN_MINUTES = 41.49530698780892
PINNED_F2_GAP_SECONDS_PER_BAG = 1.1347038098698192

PINNED_UPSTREAM_SHA256: Mapping[Path, str] = {
    UPSTREAM_CENSUS: (
        "365d2a8f860944616f5e7199be2c3c86b3d07dc743ba793b978b0fedf4586de3"
    ),
    STAGE_E_MANIFEST_PATH: (
        "f5b8c2629f627728aa774bf1117f8a6f1eef90ad6be2417a35ed962ad2e0fa0f"
    ),
    UPSTREAM_MERGE_TABLE: (
        "8808a79443a20bf2bfdee35ead5789b52d76a0ea386153ffd267a78020dc31c1"
    ),
    UPSTREAM_MERGE_CONFIG: (
        "e36e81bcc4aafa1b3d222fdd0d634dae687fa337d706c7af28c38141585298e4"
    ),
    BASELINE_REGISTRY: (
        "331338197366eb51e604d4f18296d6c41a54a6a426eee5963648223ae9f24e46"
    ),
    F2_FROZEN_CONTROL: (
        "2e2c66244ceb4ff1b514da211487d8c5223f7a29304548309856824297eccfaf"
    ),
    FAULT_FROZEN_CONTROL: (
        "2ecda35d534d694239f217fb4c8143efff1c969557f1cca581d8e28f1b0838de"
    ),
    G13_FINAL_BUNDLE: (
        "202b6fbf4608ceaeba9bb215a02ece5473471330705358bb191ff9d2f8f95fc8"
    ),
    G13_FAULT_BUNDLE: (
        "2725cde581268aacc2bd37ad15e6b1c19fe4204c04f233eaa947d55986ac2272"
    ),
}

RULE_REPORT = Path("outputs/reports/g4irsf14_rule_upper_bound.md")
RULE_TABLE = Path("outputs/tables/g4irsf14_rule_upper_bound_gate.csv")
RULE_GATE = Path("artifacts/gates/g4irsf14_rule_upper_bound_gate.json")
PIBT_REPORT = Path("outputs/reports/g4irsf14_pibt_blocker_taxonomy.md")
PIBT_REASONS_TABLE = Path(
    "outputs/tables/g4irsf14_pibt_failure_reasons.csv"
)
PIBT_COMMIT_TABLE = Path(
    "outputs/tables/g4irsf14_pibt_feasible_commit_ab.csv"
)
LEARNING_DATA_REPORT = Path(
    "outputs/reports/g4irsf14_learning_data_report.md"
)
OFFLINE_REPORT = Path("outputs/reports/g4irsf14_offline_training_report.md")
ROUTE_OFFLINE_TABLE = Path("outputs/tables/g4irsf14_route_offline_ab.csv")
MERGE_OFFLINE_TABLE = Path("outputs/tables/g4irsf14_merge_offline_ab.csv")
ADMISSION_OFFLINE_TABLE = Path(
    "outputs/tables/g4irsf14_admission_offline_ab.csv"
)
LEARNING_GATE = Path(
    "artifacts/gates/g4irsf14_learning_preclosed_loop_gate.json"
)
CLOSED_LOOP_REPORT = Path(
    "outputs/reports/g4irsf14_closed_loop_ladder.md"
)
CLOSED_LOOP_TABLE = Path(
    "outputs/tables/g4irsf14_closed_loop_ladder.csv"
)
CLOSED_LOOP_GATE = Path("artifacts/gates/g4irsf14_closed_loop_gate.json")
FAULT_REPORT = Path("outputs/reports/g4irsf14_fault_regression.md")
FAULT_TABLE = Path("outputs/tables/g4irsf14_fault_regression_ab.csv")
RUNTIME_REPORT = Path("outputs/reports/g4irsf14_runtime_profile.md")
RUNTIME_TABLE = Path("outputs/tables/g4irsf14_runtime_stage_profile.csv")
FINAL_REPORT = Path(
    "outputs/reports/g4irsf14_original_scale_joint_decision.md"
)
FINAL_TABLE = Path("outputs/tables/g4irsf14_original_scale_joint_ab.csv")
FINAL_BUNDLE = Path(
    "artifacts/policies/g4irsf14_final_candidate_bundle.json"
)
SCALE_GATE = Path("artifacts/gates/g4irsf14_scale_unlock_gate.json")
DOWNSTREAM_GATE = Path(
    "artifacts/gates/g4irsf14_downstream_fail_closed_gate.json"
)

OUTPUT_PATHS = (
    RULE_REPORT,
    RULE_TABLE,
    RULE_GATE,
    PIBT_REPORT,
    PIBT_REASONS_TABLE,
    PIBT_COMMIT_TABLE,
    LEARNING_DATA_REPORT,
    OFFLINE_REPORT,
    ROUTE_OFFLINE_TABLE,
    MERGE_OFFLINE_TABLE,
    ADMISSION_OFFLINE_TABLE,
    LEARNING_GATE,
    CLOSED_LOOP_REPORT,
    CLOSED_LOOP_TABLE,
    CLOSED_LOOP_GATE,
    FAULT_REPORT,
    FAULT_TABLE,
    RUNTIME_REPORT,
    RUNTIME_TABLE,
    FINAL_REPORT,
    FINAL_TABLE,
    FINAL_BUNDLE,
    SCALE_GATE,
    DOWNSTREAM_GATE,
)

UPSTREAM_IDENTITY_PATHS = (
    UPSTREAM_CENSUS,
    STAGE_E_MANIFEST_PATH,
    UPSTREAM_MERGE_TABLE,
    UPSTREAM_MERGE_CONFIG,
    BASELINE_REGISTRY,
    F2_FROZEN_CONTROL,
    FAULT_FROZEN_CONTROL,
    G13_FINAL_BUNDLE,
    G13_FAULT_BUNDLE,
    MAP_PATH,
    TASK_PATH,
    GENERATOR_PATH,
    VALIDATOR_PATH,
    STAGE_E_STATIC_VALIDATOR_PATH,
    HASH_POLICY_PATH,
)

REGISTRY_INHERITED_PATHS = (
    Path("artifacts/gates/g4irsf13_baseline_freeze_manifest.json"),
    Path("artifacts/gates/g4irsf13_kl_unlock_decision.json"),
    Path("artifacts/models/g4e_risk_calibrated_policy.json"),
    Path("artifacts/policies/g4irsf12_denominator_reconciliation.json"),
    Path("artifacts/policies/g4irsf13_f2_frozen_baseline.json"),
    Path("artifacts/policies/g4irsf13_fault_control_bundle.json"),
    Path("artifacts/policies/g4irsf13_final_candidate_bundle.json"),
    Path("outputs/reports/g4irsf13_fault_recovery_results.md"),
    Path("outputs/reports/g4irsf13_original_scale_joint_decision.md"),
    Path("outputs/tables/g4irsf13_fault_causal_ab.csv"),
    Path("outputs/tables/g4irsf13_original_scale_joint_ab.csv"),
)

STAGE_E_STATIC_PATHS = tuple(
    sorted(
        set(STAGE_E_BUNDLE_PATHS.values()) | {STAGE_E_MANIFEST_PATH},
        key=lambda item: item.as_posix(),
    )
)

STAGE_E_SOURCE_PATHS = (
    Path("CMakeLists.txt"),
    Path("artifacts/models/g4e_risk_calibrated_policy.json"),
    Path("cpp/ics_core/bindings/czr005_cpp.cpp"),
    Path("cpp/ics_core/runtime/bounded_local_pibt.hpp"),
    Path("cpp/ics_core/runtime/destination_merge_grant.hpp"),
    Path("cpp/ics_core/runtime/event_driven_junction.hpp"),
    Path("cpp/ics_core/runtime/g4irsf14_causal_intervention.hpp"),
    Path("cpp/ics_core/runtime/g4irsf14_state_clone.hpp"),
    Path("scripts/eval/g4irsf11_fixed_map.py"),
    Path("scripts/eval/g4irsf12_reproducible_harness.py"),
    Path("scripts/eval/g4irsf14_opportunity_census.py"),
    Path("scripts/eval/g4irsf14_state_clone_validation.py"),
    Path("scripts/validate_g4irsf14_state_clone_artifacts.py"),
    Path("src/czr005/cpp_backend.py"),
)

# Public for tests and evidence-bundle packagers.  It contains every file read
# through the validator's explicit ``root`` argument; normal Python module
# dependencies are supplied by the repository/package that runs the validator.
# No generated binary is included or resolved.
REQUIRED_BUNDLE_FILES = tuple(
    sorted(
        set(OUTPUT_PATHS)
        | set(UPSTREAM_IDENTITY_PATHS)
        | set(STAGE_E_STATIC_PATHS)
        | set(STAGE_E_SOURCE_PATHS)
        | set(REGISTRY_INHERITED_PATHS),
        key=lambda item: item.as_posix(),
    )
)

PIBT_CANONICAL_REASONS = (
    "OWNER_NOT_IN_READY_SLICE",
    "OWNER_IN_TRANSIT_IMMOVABLE",
    "NO_ALTERNATIVE_EDGE",
    "ALTERNATIVE_NOT_SHIELD_SAFE",
    "DESTINATION_SLOT_UNAVAILABLE",
    "QUEUE_CAPACITY_BLOCK",
    "CREDIT_OR_GRANT_MISSING",
    "CREDIT_OR_GRANT_STALE",
    "FAULT_GENERATION_CHANGED",
    "LOCAL_RESOURCE_CONFLICT",
    "WAIT_FOR_CYCLE",
    "DEPTH_LIMIT",
    "PREPARE_REJECT",
    "VALIDATE_REJECT",
    "COMMIT_REJECT",
    "ROLLBACK",
    "OTHER_EXPLICIT",
)

STAGE_STATUS = {
    "F": "NOT_RUN_UPSTREAM_CAUSAL_GATE",
    "G": "TAXONOMY_MEASUREMENT_NOT_RUN_ZERO_APPLICABLE_SUPPORT",
    "H": "INSUFFICIENT_CAUSAL_DATA_NOT_RUN",
    "I": "FAIL_CLOSED",
    "J": "NOT_RUN_OFFLINE_GATE_FAILED",
    "K": "NOT_RUN_NO_ELIGIBLE_NEW_CANDIDATE",
    "L": "NO_OPTIMIZATION_NOT_RUN",
    "M": "PARTIAL_WITH_EXPLICIT_BLOCKER",
}

ROUTE_MODELS = (
    ("A0", "frozen F2 reference"),
    ("A1", "clipped linear residual"),
    ("A2", "pairwise logistic"),
    ("A3", "feature-pruned tiny MLP"),
)
MERGE_MODELS = (
    ("B0", "FIFO/rule reference"),
    ("B1", "pairwise linear ranker"),
    ("B2", "pairwise tiny MLP"),
    ("B3", "listwise shared bag encoder"),
    ("B4", "DeepSets-style context ranker"),
    ("B5", "one-head tiny set-attention ranker"),
    ("B6", "best plus calibrated abstention"),
)
ADMISSION_MODELS = (
    ("C0", "admission rule off reference"),
    ("C1", "calibrated logistic hold/release"),
    ("C2", "tiny MLP"),
    ("C3", "best plus abstention"),
)
CLOSED_CANDIDATES = (
    ("J0", "F2 immediate frozen reference"),
    ("J1", "best batched no-learning"),
    ("J2", "best merge-grant rule"),
    ("J3", "learned merge ranker"),
    ("J4", "learned merge plus route residual"),
    ("J5", "learned merge plus selective admission"),
    ("J6", "complete learned stack plus P2 plus shield"),
)
PLANNED_NEGATIVE_COHORTS = (
    "F2_ALREADY_BETTER_THAN_V2",
    "NODES_19_22",
    "LATE_BAND",
    "SOURCES_5_4_3",
    "GOAL_48",
    "LOW_CONTENTION",
    "UNIQUE_OUTGOING",
    "NO_BENEFIT_HOLD",
    "P2_NO_BENEFIT_STATES",
)
PLANNED_SPLIT_DIMENSIONS = (
    "RAW_BAG",
    "TIME_BLOCK",
    "SOURCE",
    "GOAL",
    "JUNCTION_MERGE",
    "EBS_DIRECT",
    "CAUSAL_INTERVENTION_GROUP",
    "READY_SET_SIGNATURE",
    "TAIL_NON_TAIL",
)
REQUIRED_GENERALIZATION_ABLATIONS = (
    "NO_ABSOLUTE_NODE_ID",
    "SHARED_MODEL_ABLATION",
    "NODE_SPECIFIC_BIAS_ABLATION",
    "HELD_OUT_TIME_SOURCE_GOAL",
    "NO_TASK_ID_MEMORY",
)

RULE_COLUMNS = (
    "generation_id",
    "input_identity_sha256",
    "stage",
    "rule_id",
    "rule_family",
    "status",
    "execution_status",
    "planned_rule_count",
    "eligible_rule_count",
    "stage_d_mechanism_rule_count",
    "causal_label_count",
    "formal_causal_eligible",
    "diagnostic_only",
    "runtime_deployable_by_design",
    "stage_d_reference_scope",
    "stage_d_equivalent_rule_id",
    "observed_mean_delta_vs_m0_seconds",
    "observed_p95_delta_vs_m0_seconds",
    "causal_upper_bound_seconds_per_bag",
    "metric_status",
    "reason",
    "row_sha256",
)
PIBT_REASON_COLUMNS = (
    "generation_id",
    "input_identity_sha256",
    "stage",
    "status",
    "reason_ordinal",
    "primary_reason",
    "failure_count",
    "denominator_count",
    "rate",
    "measurement_status",
    "taxonomy_static_inventory_complete",
    "taxonomy_runtime_complete",
    "row_sha256",
)
PIBT_COMMIT_COLUMNS = (
    "generation_id",
    "input_identity_sha256",
    "stage",
    "candidate_id",
    "status",
    "execution_status",
    "attempt_count",
    "prefilter_candidate_count",
    "applicable_ready_slice_boundary_count",
    "prepare_count",
    "validate_count",
    "commit_count",
    "rollback_count",
    "raw_commit_numerator",
    "raw_attempt_denominator",
    "raw_commit_per_attempt_rate",
    "raw_commit_per_attempt_status",
    "feasible_commit_numerator",
    "feasible_attempt_denominator",
    "feasible_commit_per_feasible_attempt_rate",
    "feasible_commit_per_feasible_attempt_status",
    "resolved_contention_numerator",
    "applicable_contention_denominator",
    "resolved_per_applicable_rate",
    "resolved_per_applicable_status",
    "system_benefit_numerator_seconds",
    "committed_transaction_denominator",
    "system_benefit_per_committed_transaction",
    "system_benefit_per_committed_transaction_status",
    "metric_status",
    "row_sha256",
)
OFFLINE_COLUMNS = (
    "generation_id",
    "input_identity_sha256",
    "stage",
    "task",
    "candidate_id",
    "candidate_family",
    "status",
    "execution_status",
    "causal_training_row_count",
    "causal_validation_row_count",
    "causal_audit_row_count",
    "metric_name",
    "metric_value",
    "metric_status",
    "model_artifact",
    "reason",
    "row_sha256",
)
CLOSED_COLUMNS = (
    "generation_id",
    "input_identity_sha256",
    "stage",
    "candidate_id",
    "candidate_description",
    "status",
    "execution_status",
    "scale",
    "evaluation_status",
    "repeat_count",
    "original_entry_mean_minutes",
    "delta_vs_f2_seconds_per_bag",
    "delta_vs_v2_safe_seconds_per_bag",
    "hard_gate_status",
    "performance_gate_status",
    "mechanism_gate_status",
    "learning_contribution_status",
    "tail_gate_status",
    "reason",
    "row_sha256",
)
FAULT_COLUMNS = (
    "generation_id",
    "input_identity_sha256",
    "stage",
    "case_group",
    "status",
    "execution_status",
    "candidate_id",
    "repeat_count",
    "unsafe_entry_count",
    "hard_failure_count",
    "fault_policy_benefit",
    "unsafe_entry_zero_status",
    "fault_generation_monotone_status",
    "stale_grant_rejected_status",
    "repair_reentry_once_status",
    "credit_grant_cleanup_status",
    "p2_transaction_atomic_status",
    "metric_status",
    "reference_scope",
    "reason",
    "row_sha256",
)
RUNTIME_COLUMNS = (
    "generation_id",
    "input_identity_sha256",
    "stage",
    "scope",
    "status",
    "execution_status",
    "profile_run_count",
    "wall_seconds",
    "events_per_second",
    "peak_memory_bytes",
    "metric_status",
    "optimization_change_count",
    "reason",
    "row_sha256",
)
FINAL_COLUMNS = (
    "generation_id",
    "input_identity_sha256",
    "stage",
    "candidate_id",
    "candidate_role",
    "evidence_scope",
    "status",
    "execution_status",
    "original_entry_mean_minutes",
    "delta_vs_v2_safe_seconds_per_bag",
    "strict_win_vs_v2_safe",
    "learning_contribution_proven",
    "fault_regression_pass",
    "promotion_status",
    "row_sha256",
)

CSV_SCHEMAS = {
    RULE_TABLE: RULE_COLUMNS,
    PIBT_REASONS_TABLE: PIBT_REASON_COLUMNS,
    PIBT_COMMIT_TABLE: PIBT_COMMIT_COLUMNS,
    ROUTE_OFFLINE_TABLE: OFFLINE_COLUMNS,
    MERGE_OFFLINE_TABLE: OFFLINE_COLUMNS,
    ADMISSION_OFFLINE_TABLE: OFFLINE_COLUMNS,
    CLOSED_LOOP_TABLE: CLOSED_COLUMNS,
    FAULT_TABLE: FAULT_COLUMNS,
    RUNTIME_TABLE: RUNTIME_COLUMNS,
    FINAL_TABLE: FINAL_COLUMNS,
}

REPORT_STATUS_MARKERS = {
    RULE_REPORT: STAGE_STATUS["F"],
    PIBT_REPORT: STAGE_STATUS["G"],
    LEARNING_DATA_REPORT: STAGE_STATUS["H"],
    OFFLINE_REPORT: STAGE_STATUS["I"],
    CLOSED_LOOP_REPORT: STAGE_STATUS["J"],
    FAULT_REPORT: STAGE_STATUS["K"],
    RUNTIME_REPORT: STAGE_STATUS["L"],
    FINAL_REPORT: "PARTIAL_WITH_EXPLICIT_BLOCKER",
}

REPORT_REQUIRED_MARKERS = {
    RULE_REPORT: (
        "formal eligible count = 0",
        "正式 matched H_bag/H_system 标签数为 0",
        "不能声称规则有收益",
    ),
    PIBT_REPORT: (
        "G4IRSF14 attempt = 0",
        "denominator=0",
        "`NOT_MEASURED`",
        "不是 runtime taxonomy complete",
    ),
    LEARNING_DATA_REPORT: (
        "completed matched causal labels = 0",
        "train、validation、audit 都为 0 行",
        "没有产生任何模型文件",
    ),
    OFFLINE_REPORT: (
        "训练执行：`NOT_RUN`",
        "离线门：`FAIL_CLOSED`",
        "所有模型族均禁止拟合",
    ),
    CLOSED_LOOP_REPORT: (
        "共 42 个计划单元均未运行",
        "任何一级都不得启动",
        "没有候选",
    ),
    FAULT_REPORT: (
        "same-timestamp fault 均未运行",
        "六项保持门均为 `NOT_EVALUATED`",
    ),
    RUNTIME_REPORT: (
        "未运行 profiler",
        "没有 wall-time、吞吐或内存指标",
    ),
}

REPORT_FORBIDDEN_CLAIMS = {
    RULE_REPORT: ("stage f 已通过", "规则严格胜过 v2-safe"),
    PIBT_REPORT: (
        "runtime taxonomy complete = true",
        "g4irsf14 attempt > 0",
    ),
    LEARNING_DATA_REPORT: ("训练已完成", "已生成模型"),
    OFFLINE_REPORT: ("训练已完成", "已生成模型"),
    CLOSED_LOOP_REPORT: ("promotion allowed", "候选已晋级"),
    FAULT_REPORT: ("g4irsf14 fault regression pass",),
    RUNTIME_REPORT: ("profiler 已完成", "优化已完成"),
}

FINAL_BOUND_PATHS = (
    RULE_REPORT,
    RULE_TABLE,
    RULE_GATE,
    PIBT_REPORT,
    PIBT_REASONS_TABLE,
    PIBT_COMMIT_TABLE,
    LEARNING_DATA_REPORT,
    OFFLINE_REPORT,
    ROUTE_OFFLINE_TABLE,
    MERGE_OFFLINE_TABLE,
    ADMISSION_OFFLINE_TABLE,
    LEARNING_GATE,
    CLOSED_LOOP_REPORT,
    CLOSED_LOOP_TABLE,
    CLOSED_LOOP_GATE,
    FAULT_REPORT,
    FAULT_TABLE,
    RUNTIME_REPORT,
    RUNTIME_TABLE,
    FINAL_REPORT,
    FINAL_TABLE,
)

FAULT_CASES = (
    "G0_NO_FAULT_CONTROL",
    "G1_PHYSICAL_SHIELD",
    "G2_DDI_LOCAL_POLICY",
    "G3_DDI_PLUS_P2",
    "G5_DELAYED_FAULT",
    "G6_DROPPED_FAULT",
    "G7_REPAIR_REOPEN",
    "INFORMATIVE_MULTI_FAULT",
    "GRANT_ISSUE_TO_FAULT",
    "PREPARE_COMMIT_TO_FAULT",
    "SAME_TIMESTAMP_BATCH_AND_FAULT_EVENT",
)


class CompletionValidationError(ValueError):
    """A committed fail-closed artifact is missing or semantically unsafe."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CompletionValidationError(message)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    _require(path.is_file(), f"MISSING_FILE:{path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def semantic_text_sha256(path: Path) -> str:
    _require(path.is_file(), f"MISSING_SEMANTIC_SOURCE:{path}")
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CompletionValidationError(
            f"SEMANTIC_SOURCE_NOT_UTF8:{path}"
        ) from exc
    normalized = text.replace("\r\n", "\n")
    _require("\r" not in normalized, f"SEMANTIC_SOURCE_LONE_CR:{path}")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _exact_keys(
    value: Mapping[str, Any],
    expected: Sequence[str] | set[str],
    label: str,
) -> None:
    expected_set = set(expected)
    observed = set(value)
    _require(
        observed == expected_set,
        (
            f"{label}_KEYS_DRIFT:"
            f"missing={sorted(expected_set - observed)}:"
            f"extra={sorted(observed - expected_set)}"
        ),
    )


def _mapping(value: Any, label: str) -> dict[str, Any]:
    _require(isinstance(value, dict), f"{label}_NOT_OBJECT")
    return dict(value)


def _array(value: Any, label: str) -> list[Any]:
    _require(isinstance(value, list), f"{label}_NOT_ARRAY")
    return list(value)


def _strict_int(value: Any, label: str) -> int:
    _require(
        isinstance(value, int) and not isinstance(value, bool),
        f"{label}_NOT_INTEGER",
    )
    return int(value)


def _strict_number(value: Any, label: str) -> float:
    _require(
        isinstance(value, (int, float)) and not isinstance(value, bool),
        f"{label}_NOT_NUMBER",
    )
    result = float(value)
    _require(math.isfinite(result), f"{label}_NONFINITE")
    return result


def _load_json(root: Path, relative: Path) -> dict[str, Any]:
    path = root / relative
    _require(path.is_file(), f"MISSING_JSON:{relative.as_posix()}")

    def reject_duplicate_keys(
        pairs: Sequence[tuple[str, Any]],
    ) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            _require(
                key not in value,
                f"DUPLICATE_JSON_KEY:{relative.as_posix()}:{key}",
            )
            value[key] = item
        return value

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CompletionValidationError(
            f"INVALID_JSON:{relative.as_posix()}:{type(exc).__name__}"
        ) from exc
    return _mapping(value, f"JSON_{relative.as_posix()}")


def _validate_self_hash(
    value: Mapping[str, Any],
    *,
    label: str,
    field: str = "self_sha256",
) -> str:
    declared = value.get(field)
    _require(
        isinstance(declared, str)
        and len(declared) == 64
        and all(character in "0123456789abcdef" for character in declared),
        f"{label}_SELF_HASH_MALFORMED",
    )
    projection = dict(value)
    projection.pop(field, None)
    _require(
        canonical_sha256(projection) == declared,
        f"{label}_SELF_HASH_DRIFT",
    )
    return declared


def _read_csv(
    root: Path,
    relative: Path,
    columns: Sequence[str],
) -> list[dict[str, str]]:
    path = root / relative
    _require(path.is_file(), f"MISSING_CSV:{relative.as_posix()}")
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            _require(
                reader.fieldnames == list(columns),
                f"CSV_COLUMNS_DRIFT:{relative.as_posix()}",
            )
            rows = list(reader)
    except UnicodeError as exc:
        raise CompletionValidationError(
            f"INVALID_UTF8_CSV:{relative.as_posix()}"
        ) from exc
    for index, row in enumerate(rows):
        _require(
            set(row) == set(columns) and all(value is not None for value in row.values()),
            f"CSV_ROW_SHAPE_DRIFT:{relative.as_posix()}:{index}",
        )
        projection = dict(row)
        declared = projection.pop("row_sha256", "")
        _require(
            declared == canonical_sha256(projection),
            f"CSV_ROW_HASH_DRIFT:{relative.as_posix()}:{index}",
        )
    return rows


def _binding_for(root: Path, relative: Path) -> dict[str, Any]:
    path = root / relative
    _require(path.is_file(), f"MISSING_BOUND_OUTPUT:{relative.as_posix()}")
    return {
        "path": relative.as_posix(),
        "sha256": file_sha256(path),
        "byte_count": path.stat().st_size,
    }


def _validate_binding_map(
    root: Path,
    value: Any,
    expected_paths: Sequence[Path],
    label: str,
) -> None:
    bindings = _mapping(value, f"{label}_BINDINGS")
    expected = {path.as_posix() for path in expected_paths}
    _require(set(bindings) == expected, f"{label}_BINDING_INVENTORY_DRIFT")
    for relative in expected_paths:
        key = relative.as_posix()
        binding = _mapping(bindings[key], f"{label}_BINDING_{key}")
        _exact_keys(binding, {"path", "sha256", "byte_count"}, f"{label}_{key}")
        _require(
            binding == _binding_for(root, relative),
            f"{label}_BINDING_DRIFT:{key}",
        )


def _validate_stage_e_source_checkout(
    root: Path,
    document: Mapping[str, Any],
) -> None:
    source_bundle = _mapping(
        document.get("source_bundle"),
        "STAGE_E_SOURCE_BUNDLE",
    )
    _exact_keys(
        source_bundle,
        {
            "hash_mode",
            "files",
            "path_manifest_sha256",
            "bundle_sha256",
        },
        "STAGE_E_SOURCE_BUNDLE",
    )
    _require(
        source_bundle.get("hash_mode")
        == "sha256_utf8_after_crlf_to_lf_reject_lone_cr",
        "STAGE_E_SOURCE_HASH_MODE_DRIFT",
    )
    records = [
        _mapping(item, f"STAGE_E_SOURCE_RECORD_{index}")
        for index, item in enumerate(
            _array(source_bundle.get("files"), "STAGE_E_SOURCE_FILES")
        )
    ]
    for index, record in enumerate(records):
        _exact_keys(
            record,
            {"path", "semantic_sha256"},
            f"STAGE_E_SOURCE_RECORD_{index}",
        )
    expected_paths = tuple(
        path.as_posix()
        for path in sorted(
            STAGE_E_SOURCE_PATHS,
            key=lambda item: item.as_posix(),
        )
    )
    observed_paths = tuple(str(record.get("path")) for record in records)
    _require(
        observed_paths == expected_paths,
        "STAGE_E_SOURCE_PATH_INVENTORY_DRIFT",
    )
    root_resolved = root.resolve(strict=True)
    for relative_text, record in zip(
        expected_paths,
        records,
        strict=True,
    ):
        relative = Path(relative_text)
        candidate = (root_resolved / relative).resolve(strict=True)
        try:
            candidate.relative_to(root_resolved)
        except ValueError as exc:
            raise CompletionValidationError(
                f"STAGE_E_SOURCE_ESCAPES_ROOT:{relative_text}"
            ) from exc
        declared = record.get("semantic_sha256")
        _require(
            isinstance(declared, str)
            and len(declared) == 64
            and all(character in "0123456789abcdef" for character in declared),
            f"STAGE_E_SOURCE_HASH_MALFORMED:{relative_text}",
        )
        _require(
            semantic_text_sha256(candidate) == declared,
            f"STAGE_E_SOURCE_CHECKOUT_DRIFT:{relative_text}",
        )
    _require(
        source_bundle.get("path_manifest_sha256")
        == canonical_sha256(list(expected_paths)),
        "STAGE_E_SOURCE_PATH_MANIFEST_DRIFT",
    )
    _require(
        source_bundle.get("bundle_sha256") == canonical_sha256(records),
        "STAGE_E_SOURCE_BUNDLE_HASH_DRIFT",
    )


def _validate_stage_e_static(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    payloads = {
        relative: (root / relative).read_bytes()
        for relative in STAGE_E_STATIC_PATHS
        if (root / relative).is_file()
    }
    _require(
        set(payloads) == set(STAGE_E_STATIC_PATHS),
        "STAGE_E_STATIC_PAYLOAD_INVENTORY_DRIFT",
    )
    try:
        validated = validate_blocker_bundle_payloads(payloads)
    except (OpportunityCensusError, OSError, UnicodeError) as exc:
        raise CompletionValidationError(
            f"STAGE_E_STATIC_BUNDLE_INVALID:{exc}"
        ) from exc
    document = _mapping(validated.get("document"), "STAGE_E_DOCUMENT")
    manifest = _mapping(validated.get("manifest"), "STAGE_E_MANIFEST")
    _validate_stage_e_source_checkout(root, document)
    _require(
        document.get("status") == "PARTIAL_WITH_EXPLICIT_BLOCKER"
        and document.get("formal_pass_claimed") is False
        and document.get("causal_label_count") == 0,
        "STAGE_E_FORMAL_BOUNDARY_DRIFT",
    )
    blocker = _mapping(document.get("blocker"), "STAGE_E_BLOCKER")
    _require(
        blocker.get("minimum_required_complete_interventions")
        == MIN_FORMAL_INTERVENTIONS
        and blocker.get(
            "unique_complete_h_bag_h_system_intervention_count"
        )
        == 0
        and blocker.get("h_system_intervention_count") == 0
        and blocker.get("taxonomy_complete") is False
        and blocker.get("formal_pass_allowed") is False,
        "STAGE_E_BLOCKER_COUNTS_DRIFT",
    )
    support = _mapping(document.get("support"), "STAGE_E_SUPPORT")
    _require(
        set(support)
        == {
            "I1_source_order_swap",
            "I2_merge_request_order_swap",
            "I3_next_edge",
            "I4_hold_release",
            "I5_pibt_trigger",
        },
        "STAGE_E_SUPPORT_COMPONENT_DRIFT",
    )
    for name, raw in support.items():
        component = _mapping(raw, f"STAGE_E_{name}")
        _require(
            component.get("causal_label_count") == 0
            and component.get("formal_horizon_completion_count") == 0,
            f"STAGE_E_FORMAL_SUPPORT_DRIFT:{name}",
        )
    _require(
        support["I1_source_order_swap"].get("multi_ready_boundary_count")
        == 41_679,
        "STAGE_E_I1_SCREENING_COUNT_DRIFT",
    )
    _require(
        support["I2_merge_request_order_swap"].get(
            "eligible_live_multi_request_boundary_count"
        )
        == 1,
        "STAGE_E_I2_SCREENING_COUNT_DRIFT",
    )
    _require(
        support["I3_next_edge"].get("safe_alternative_boundary_lower_bound")
        == 19_898,
        "STAGE_E_I3_SCREENING_COUNT_DRIFT",
    )
    _require(
        support["I4_hold_release"].get(
            "release_to_hold_boundary_lower_bound"
        )
        == 59_049,
        "STAGE_E_I4_SCREENING_COUNT_DRIFT",
    )
    i5 = _mapping(support["I5_pibt_trigger"], "STAGE_E_I5")
    _require(
        i5.get("prefilter_candidate_count") == 1_337
        and i5.get("applicable_ready_slice_boundary_count") == 0
        and i5.get("strict_same_ready_slice_boundary_count") == 0
        and i5.get("exact_zero_proven") is True,
        "STAGE_E_I5_SCREENING_COUNT_DRIFT",
    )
    raw_pibt = _mapping(document.get("p2_raw_counters"), "STAGE_E_PIBT_RAW")
    _require(
        raw_pibt.get("g4irsf14_i5_prefilter_candidate_count") == 1_337
        and raw_pibt.get(
            "g4irsf14_i5_applicable_ready_slice_boundary_count"
        )
        == 0
        and raw_pibt.get("bounded_local_pibt_attempt_count") == 0
        and raw_pibt.get("bounded_local_pibt_not_applicable_count") == 1_337,
        "STAGE_E_PREFILTER_ATTEMPT_CONFLATION",
    )
    _require(
        manifest.get("status") == "PARTIAL_WITH_EXPLICIT_BLOCKER"
        and manifest.get("formal_pass_claimed") is False
        and manifest.get("formal_v3_schema_claimed") is False
        and manifest.get("causal_label_count") == 0,
        "STAGE_E_MANIFEST_BOUNDARY_DRIFT",
    )
    bundle_files = _mapping(
        manifest.get("bundle_files"), "STAGE_E_MANIFEST_FILES"
    )
    expected_counts = {
        "opportunity_census": 1,
        "matched_state_clone_report": 1,
        "clone_fidelity": 1,
        "causal_interventions": 0,
        "causal_component_ledger": 5,
    }
    _require(set(bundle_files) == set(expected_counts), "STAGE_E_FILE_SET_DRIFT")
    for name, count in expected_counts.items():
        binding = _mapping(bundle_files[name], f"STAGE_E_FILE_{name}")
        _require(
            binding.get("record_count") == count,
            f"STAGE_E_RECORD_COUNT_DRIFT:{name}",
        )
    # Intentionally do not resolve or inspect document["binary"]["path"].
    return document, manifest


def _validate_merge_mechanism(root: Path) -> tuple[int, int]:
    config = _load_json(root, UPSTREAM_MERGE_CONFIG)
    _require(
        config.get("schema") == "czr005.g4irsf14.merge_grant_protocol.v2"
        and config.get("status")
        == "PASS_STAGE_D_PRODUCTION_E4_MECHANISM_EVIDENCE"
        and config.get("promotion_status")
        == "NOT_EVALUATED_STAGE_D_MECHANISM_ONLY"
        and config.get("performance_gain_claimed") is False,
        "STAGE_D_MERGE_CLAIM_BOUNDARY_DRIFT",
    )
    bindings = _mapping(config.get("output_sha256"), "STAGE_D_OUTPUT_HASHES")
    _require(
        bindings.get(UPSTREAM_MERGE_TABLE.as_posix())
        == file_sha256(root / UPSTREAM_MERGE_TABLE),
        "STAGE_D_MERGE_TABLE_HASH_DRIFT",
    )
    path = root / UPSTREAM_MERGE_TABLE
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    _require(len(rows) == 10, "STAGE_D_MERGE_ROW_COUNT_DRIFT")
    by_rule = {row.get("rule", ""): row for row in rows}
    _require(set(by_rule) == {f"M{i}" for i in range(10)}, "STAGE_D_RULE_SET_DRIFT")
    executed = 0
    improved = 0
    for index in range(7):
        row = by_rule[f"M{index}"]
        _require(
            row.get("execution_status") == "EXECUTED_PRODUCTION_E4"
            and row.get("hard_gate_pass") == "true"
            and row.get("performance_gain_claimed") == "false"
            and row.get("promotion_status")
            == "NOT_EVALUATED_STAGE_D_MECHANISM_ONLY",
            f"STAGE_D_EXECUTED_RULE_DRIFT:M{index}",
        )
        for field in (
            "mean_completion_delta_vs_m0_seconds",
            "p95_completion_delta_vs_m0_seconds",
        ):
            try:
                value = float(row.get(field, "nan"))
            except ValueError as exc:
                raise CompletionValidationError(
                    f"STAGE_D_BAD_DELTA:M{index}:{field}"
                ) from exc
            _require(math.isfinite(value) and value == 0.0, f"STAGE_D_GAIN:M{index}")
        executed += 1
    for index in range(7, 10):
        row = by_rule[f"M{index}"]
        _require(
            row.get("execution_status") == "REJECTED_FAIL_CLOSED"
            and row.get("online_allowed") == "false"
            and row.get("performance_gain_claimed") == "false",
            f"STAGE_D_NEGATIVE_RULE_DRIFT:M{index}",
        )
    return executed, improved


def _validate_input_identity(
    root: Path,
    identity: Mapping[str, Any],
    stage_e_document: Mapping[str, Any],
    stage_e_manifest: Mapping[str, Any],
    *,
    merge_executed: int,
    merge_improved: int,
) -> str:
    _exact_keys(
        identity,
        {
            "schema",
            "bindings",
            "census_self_sha256",
            "clone_manifest_self_sha256",
            "causal_label_count",
            "formal_horizon_completion_count",
            "pibt_prefilter_candidate_count",
            "pibt_applicable_ready_slice_boundary_count",
            "merge_rule_executed_count",
            "merge_rule_improved_count",
            "f2_raw_entry_mean_minutes",
            "v2_safe_raw_entry_mean_minutes",
            "remaining_gap_seconds_per_bag",
            "identity_sha256",
        },
        "INPUT_IDENTITY",
    )
    _require(
        identity.get("schema")
        == "czr005.g4irsf14.fail_closed_input_identity.v1",
        "INPUT_IDENTITY_SCHEMA_DRIFT",
    )
    declared = identity.get("identity_sha256")
    projection = dict(identity)
    projection.pop("identity_sha256", None)
    _require(
        isinstance(declared, str) and declared == canonical_sha256(projection),
        "INPUT_IDENTITY_SELF_HASH_DRIFT",
    )
    for relative, expected_sha256 in PINNED_UPSTREAM_SHA256.items():
        _require(
            file_sha256(root / relative) == expected_sha256,
            f"PINNED_UPSTREAM_HASH_DRIFT:{relative.as_posix()}",
        )
    _validate_binding_map(
        root,
        identity.get("bindings"),
        UPSTREAM_IDENTITY_PATHS,
        "INPUT_IDENTITY",
    )
    _require(
        identity.get("census_self_sha256")
        == stage_e_document.get("self_sha256")
        and identity.get("clone_manifest_self_sha256")
        == stage_e_manifest.get("self_sha256"),
        "INPUT_IDENTITY_STAGE_E_BINDING_DRIFT",
    )
    _require(
        identity.get("causal_label_count") == 0
        and identity.get("formal_horizon_completion_count") == 0
        and identity.get("pibt_prefilter_candidate_count") == 1_337
        and identity.get("pibt_applicable_ready_slice_boundary_count") == 0
        and identity.get("merge_rule_executed_count") == merge_executed == 7
        and identity.get("merge_rule_improved_count") == merge_improved == 0,
        "INPUT_IDENTITY_EVIDENCE_COUNT_DRIFT",
    )
    _require(
        file_sha256(root / MAP_PATH) == MAP_RAW_SHA256,
        "PROTECTED_MAP_HASH_DRIFT",
    )
    _require(
        file_sha256(root / TASK_PATH) == TASK_RAW_SHA256,
        "PROTECTED_TASK_HASH_DRIFT",
    )
    registry = _load_json(root, BASELINE_REGISTRY)
    _require(
        registry.get("schema") == "czr005.g4irsf14.baseline_registry.v1"
        and registry.get("status") == "PASS_BASELINE_FROZEN",
        "BASELINE_REGISTRY_BOUNDARY_DRIFT",
    )
    _validate_self_hash(
        registry,
        label="BASELINE_REGISTRY",
        field="registry_sha256",
    )
    _require(
        registry.get("comparators")
        == {
            "denominator": "original_entry_time_tth",
            "f2_delta_vs_historical_hca_seconds_per_bag": -97.30317374668473,
            "f2_delta_vs_v2_safe_seconds_per_bag": (
                PINNED_F2_GAP_SECONDS_PER_BAG
            ),
            "f2_raw_entry_mean_minutes": PINNED_F2_MEAN_MINUTES,
            "historical_hca_raw_entry_mean_minutes": 43.13593828041816,
            "v2_safe_raw_entry_mean_minutes": PINNED_V2_SAFE_MEAN_MINUTES,
        },
        "BASELINE_REGISTRY_COMPARATOR_DRIFT",
    )
    _require(
        _mapping(
            registry.get("f2_frozen_control"),
            "BASELINE_REGISTRY_F2",
        ).get("file_sha256")
        == PINNED_UPSTREAM_SHA256[F2_FROZEN_CONTROL]
        and _mapping(
            registry.get("fault_frozen_control"),
            "BASELINE_REGISTRY_FAULT",
        ).get("file_sha256")
        == PINNED_UPSTREAM_SHA256[FAULT_FROZEN_CONTROL],
        "BASELINE_REGISTRY_CONTROL_BINDING_DRIFT",
    )
    inherited = _mapping(
        registry.get("inherited_artifacts"),
        "BASELINE_REGISTRY_INHERITED",
    )
    expected_inherited = {
        path.as_posix() for path in REGISTRY_INHERITED_PATHS
    }
    _require(
        set(inherited) == expected_inherited,
        "BASELINE_REGISTRY_INHERITED_INVENTORY_DRIFT",
    )
    for relative in REGISTRY_INHERITED_PATHS:
        key = relative.as_posix()
        binding = _mapping(
            inherited[key],
            f"BASELINE_REGISTRY_INHERITED_{key}",
        )
        _exact_keys(
            binding,
            {"path", "file_sha256", "access"},
            f"BASELINE_REGISTRY_INHERITED_{key}",
        )
        _require(
            binding.get("path") == key
            and binding.get("access") == "READ_ONLY"
            and binding.get("file_sha256") == file_sha256(root / relative),
            f"BASELINE_REGISTRY_INHERITED_BINDING_DRIFT:{key}",
        )
    f2 = _load_json(root, F2_FROZEN_CONTROL)
    _require(
        f2.get("status") == "PASS_FROZEN_CONTROL",
        "F2_FROZEN_STATUS_DRIFT",
    )
    _validate_self_hash(
        f2, label="F2_FROZEN_CONTROL", field="control_sha256"
    )
    metrics = _mapping(f2.get("metrics"), "F2_METRICS")
    comparators = _mapping(f2.get("comparators"), "F2_COMPARATORS")
    f2_mean = _strict_number(
        metrics.get("original_entry_mean_minutes"), "F2_MEAN"
    )
    v2_mean = _strict_number(
        comparators.get("frozen_v2_safe_original_entry_mean_minutes"),
        "V2_MEAN",
    )
    gap = _strict_number(
        comparators.get("delta_vs_v2_safe_seconds_per_bag"), "F2_GAP"
    )
    _require(
        abs((f2_mean - v2_mean) * 60.0 - gap) < 1e-10 and gap > 0.0,
        "F2_COMPARATOR_ARITHMETIC_DRIFT",
    )
    _require(
        f2_mean == PINNED_F2_MEAN_MINUTES
        and v2_mean == PINNED_V2_SAFE_MEAN_MINUTES
        and gap == PINNED_F2_GAP_SECONDS_PER_BAG,
        "FROZEN_COMPARATOR_METRIC_DRIFT",
    )
    _require(
        identity.get("f2_raw_entry_mean_minutes") == f2_mean
        and identity.get("v2_safe_raw_entry_mean_minutes") == v2_mean
        and identity.get("remaining_gap_seconds_per_bag") == gap,
        "INPUT_IDENTITY_FROZEN_METRIC_DRIFT",
    )
    fault = _load_json(root, FAULT_FROZEN_CONTROL)
    _require(
        fault.get("status") == "FAULT_DISCRIMINATING_PASS_FROZEN",
        "FROZEN_FAULT_CONTROL_DRIFT",
    )
    _validate_self_hash(
        fault, label="FAULT_FROZEN_CONTROL", field="control_sha256"
    )
    g13 = _load_json(root, G13_FINAL_BUNDLE)
    _require(
        g13.get("status") == "COMPLETE"
        and g13.get("decision_status") == "HISTORICAL_ONLY_PASS"
        and g13.get("strict_win_vs_v2_safe") is False
        and g13.get("v3_contribution_proven") is False,
        "G13_FINAL_BOUNDARY_DRIFT",
    )
    _validate_self_hash(g13, label="G13_FINAL", field="bundle_sha256")
    g13_fault = _load_json(root, G13_FAULT_BUNDLE)
    _require(
        g13_fault.get("status") == "FAULT_DISCRIMINATING_PASS",
        "G13_FAULT_BOUNDARY_DRIFT",
    )
    _validate_self_hash(g13_fault, label="G13_FAULT")
    return str(declared)


def _validate_common_rows(
    rows_by_path: Mapping[Path, list[dict[str, str]]],
    *,
    generation_id: str,
    identity_sha256: str,
) -> None:
    for path, rows in rows_by_path.items():
        _require(bool(rows), f"EMPTY_COMPLETION_TABLE:{path.as_posix()}")
        for index, row in enumerate(rows):
            _require(
                row.get("generation_id") == generation_id
                and row.get("input_identity_sha256") == identity_sha256,
                f"CSV_GENERATION_BINDING_DRIFT:{path.as_posix()}:{index}",
            )


def _validate_rule_rows(rows: Sequence[Mapping[str, str]]) -> None:
    expected_ids = tuple(
        [f"R-M{index}" for index in range(8)]
        + [f"R-S{index}" for index in range(6)]
    )
    _require(
        tuple(row.get("rule_id") for row in rows) == expected_ids,
        "RULE_GATE_ROW_INVENTORY_DRIFT",
    )
    for row in rows:
        rule_id = str(row.get("rule_id"))
        equivalent = {
            "R-M0": "M0",
            "R-M1": "M1",
            "R-M2": "M2",
        }.get(rule_id, "")
        diagnostic_only = rule_id in {"R-M7", "R-S5"}
        _require(
            row.get("stage") == "F"
            and row.get("rule_family")
            == ("MERGE_ORDER" if rule_id.startswith("R-M") else "SOURCE_ORDER")
            and row.get("status") == STAGE_STATUS["F"]
            and row.get("execution_status") == "NOT_RUN"
            and row.get("planned_rule_count") == "14"
            and row.get("eligible_rule_count") == "0"
            and row.get("stage_d_mechanism_rule_count") == "7"
            and row.get("causal_label_count") == "0"
            and row.get("formal_causal_eligible") == "false"
            and row.get("diagnostic_only")
            == str(diagnostic_only).lower()
            and row.get("runtime_deployable_by_design")
            == str(not diagnostic_only).lower()
            and row.get("stage_d_reference_scope")
            == "SEPARATE_144_SEGMENT_MECHANISM_EVIDENCE_ONLY"
            and row.get("stage_d_equivalent_rule_id") == equivalent
            and row.get("observed_mean_delta_vs_m0_seconds")
            == ("0" if equivalent else "")
            and row.get("observed_p95_delta_vs_m0_seconds")
            == ("0" if equivalent else "")
            and row.get("causal_upper_bound_seconds_per_bag") == ""
            and row.get("metric_status") == "NOT_MEASURED"
            and row.get("reason")
            == "NO_FORMAL_STAGE_E_MATCHED_INTERVENTION_CAMPAIGN",
            f"RULE_GATE_SEMANTICS_DRIFT:{rule_id}",
        )


def _validate_pibt_rows(
    reasons: Sequence[Mapping[str, str]],
    commits: Sequence[Mapping[str, str]],
) -> None:
    _require(len(reasons) == 17, "PIBT_REASON_ROW_COUNT_DRIFT")
    _require(
        tuple(row.get("primary_reason") for row in reasons)
        == PIBT_CANONICAL_REASONS,
        "PIBT_REASON_INVENTORY_DRIFT",
    )
    for index, row in enumerate(reasons, start=1):
        _require(
            row.get("stage") == "G"
            and row.get("status") == STAGE_STATUS["G"]
            and row.get("reason_ordinal") == str(index)
            and row.get("failure_count") == "0"
            and row.get("denominator_count") == "0"
            and row.get("rate") == ""
            and row.get("measurement_status") == "NOT_RUN"
            and row.get("taxonomy_static_inventory_complete") == "true"
            and row.get("taxonomy_runtime_complete") == "false",
            f"PIBT_ZERO_DENOMINATOR_DRIFT:{index}",
        )
    _require(len(commits) == 1, "PIBT_COMMIT_ROW_COUNT_DRIFT")
    row = commits[0]
    _require(
        row.get("stage") == "G"
        and row.get("candidate_id") == "P2_READY_SLICE_REDESIGN"
        and row.get("status") == STAGE_STATUS["G"]
        and row.get("execution_status") == "NOT_RUN"
        and row.get("attempt_count") == "0"
        and row.get("prefilter_candidate_count") == "1337"
        and row.get("applicable_ready_slice_boundary_count") == "0"
        and row.get("prepare_count") == "0"
        and row.get("validate_count") == "0"
        and row.get("commit_count") == "0"
        and row.get("rollback_count") == "0"
        and row.get("raw_commit_numerator") == "0"
        and row.get("raw_attempt_denominator") == "0"
        and row.get("raw_commit_per_attempt_rate") == ""
        and row.get("raw_commit_per_attempt_status") == "NOT_MEASURED"
        and row.get("feasible_commit_numerator") == "0"
        and row.get("feasible_attempt_denominator") == "0"
        and row.get("feasible_commit_per_feasible_attempt_rate") == ""
        and row.get("feasible_commit_per_feasible_attempt_status")
        == "NOT_MEASURED"
        and row.get("resolved_contention_numerator") == "0"
        and row.get("applicable_contention_denominator") == "0"
        and row.get("resolved_per_applicable_rate") == ""
        and row.get("resolved_per_applicable_status") == "NOT_MEASURED"
        and row.get("system_benefit_numerator_seconds") == ""
        and row.get("committed_transaction_denominator") == "0"
        and row.get("system_benefit_per_committed_transaction") == ""
        and row.get("system_benefit_per_committed_transaction_status")
        == "NOT_MEASURED"
        and row.get("metric_status") == "NOT_MEASURED",
        "PIBT_PREFILTER_ATTEMPT_CONFLATION",
    )


def _validate_offline_rows(
    route: Sequence[Mapping[str, str]],
    merge: Sequence[Mapping[str, str]],
    admission: Sequence[Mapping[str, str]],
) -> None:
    expected = (
        (
            route,
            "ROUTE_RESIDUAL",
            ROUTE_MODELS,
        ),
        (
            merge,
            "MERGE_ORDER_RANKER",
            MERGE_MODELS,
        ),
        (
            admission,
            "ADMISSION_HOLD_RELEASE",
            ADMISSION_MODELS,
        ),
    )
    for rows, task, models in expected:
        _require(
            tuple(
                (row.get("candidate_id"), row.get("candidate_family"))
                for row in rows
            )
            == models,
            f"OFFLINE_CANDIDATE_SET_DRIFT:{task}",
        )
        for row in rows:
            _require(
                row.get("stage") == "H"
                and row.get("task") == task
                and row.get("status") == STAGE_STATUS["H"]
                and row.get("execution_status") == "NOT_RUN"
                and row.get("causal_training_row_count") == "0"
                and row.get("causal_validation_row_count") == "0"
                and row.get("causal_audit_row_count") == "0"
                and row.get("metric_name") == ""
                and row.get("metric_value") == ""
                and row.get("metric_status") == "NOT_MEASURED"
                and row.get("model_artifact") == "",
                f"OFFLINE_NOT_RUN_METRIC_DRIFT:{task}:{row.get('candidate_id')}",
            )
            if row.get("candidate_id") == "B5":
                _require(
                    row.get("reason")
                    == "CAUSAL_READY_SET_ROWS_0_BELOW_REQUIRED_20000",
                    "B5_DATA_GATE_DRIFT",
                )
            else:
                _require(
                    row.get("reason") == "ZERO_MATCHED_CAUSAL_LABELS",
                    f"OFFLINE_BLOCKER_DRIFT:{task}:{row.get('candidate_id')}",
                )


def _validate_closed_rows(rows: Sequence[Mapping[str, str]]) -> None:
    scales = ("motifs", "144", "512", "2048", "8192", "43603")
    _require(
        tuple(
            (
                row.get("candidate_id"),
                row.get("candidate_description"),
                row.get("scale"),
            )
            for row in rows
        )
        == tuple(
            (candidate, description, scale)
            for candidate, description in CLOSED_CANDIDATES
            for scale in scales
        ),
        "CLOSED_LOOP_CANDIDATE_SET_DRIFT",
    )
    for row in rows:
        candidate_id = str(row.get("candidate_id"))
        expected_reason = (
            "FROZEN_REFERENCE_NOT_RERUN"
            if candidate_id == "J0"
            else (
                "F_RULE_UPPER_BOUND_GATE_NOT_RUN"
                if candidate_id in {"J1", "J2"}
                else "I_LEARNING_PRECLOSED_LOOP_GATE_FAIL_CLOSED"
            )
        )
        _require(
            row.get("stage") == "J"
            and row.get("status")
            == (
                "REFERENCE_ONLY_NOT_RERUN"
                if candidate_id == "J0"
                else STAGE_STATUS["J"]
            )
            and row.get("execution_status") == "NOT_RUN"
            and row.get("evaluation_status") == "NOT_EVALUATED"
            and row.get("repeat_count") == "0"
            and row.get("original_entry_mean_minutes") == ""
            and row.get("delta_vs_f2_seconds_per_bag") == ""
            and row.get("delta_vs_v2_safe_seconds_per_bag") == ""
            and row.get("hard_gate_status") == ""
            and row.get("performance_gate_status") == ""
            and row.get("mechanism_gate_status") == ""
            and row.get("learning_contribution_status") == ""
            and row.get("tail_gate_status") == ""
            and row.get("reason") == expected_reason,
            f"CLOSED_LOOP_NOT_RUN_METRIC_DRIFT:{candidate_id}:{row.get('scale')}",
        )


def _validate_fault_rows(rows: Sequence[Mapping[str, str]]) -> None:
    _require(
        tuple(row.get("case_group") for row in rows) == FAULT_CASES,
        "FAULT_CASE_SET_DRIFT",
    )
    for row in rows:
        _require(
            row.get("stage") == "K"
            and row.get("status") == STAGE_STATUS["K"]
            and row.get("execution_status") == "NOT_RUN"
            and row.get("candidate_id") == ""
            and row.get("repeat_count") == "0"
            and row.get("unsafe_entry_count") == ""
            and row.get("hard_failure_count") == ""
            and row.get("fault_policy_benefit") == ""
            and all(
                row.get(field) == "NOT_EVALUATED"
                for field in (
                    "unsafe_entry_zero_status",
                    "fault_generation_monotone_status",
                    "stale_grant_rejected_status",
                    "repair_reentry_once_status",
                    "credit_grant_cleanup_status",
                    "p2_transaction_atomic_status",
                )
            )
            and row.get("metric_status") == "NOT_MEASURED"
            and row.get("reference_scope") == "G4IRSF13_FROZEN_ONLY"
            and row.get("reason") == "NO_STAGE14_CLOSED_LOOP_CANDIDATE",
            f"FAULT_NOT_RUN_METRIC_DRIFT:{row.get('case_group')}",
        )


def _validate_runtime_rows(rows: Sequence[Mapping[str, str]]) -> None:
    _require(len(rows) == 1, "RUNTIME_ROW_COUNT_DRIFT")
    row = rows[0]
    _require(
        row.get("stage") == "L"
        and row.get("scope") == "CPP_RUNTIME_PROFILE"
        and row.get("status") == STAGE_STATUS["L"]
        and row.get("execution_status") == "NOT_RUN"
        and row.get("profile_run_count") == "0"
        and row.get("wall_seconds") == ""
        and row.get("events_per_second") == ""
        and row.get("peak_memory_bytes") == ""
        and row.get("metric_status") == "NOT_MEASURED"
        and row.get("optimization_change_count") == "0"
        and row.get("reason") == "ALGORITHM_AND_CAUSAL_GATES_NOT_CLOSED",
        "RUNTIME_NOT_RUN_METRIC_DRIFT",
    )


def _validate_final_rows(
    rows: Sequence[Mapping[str, str]],
    identity: Mapping[str, Any],
) -> None:
    _require(
        tuple(row.get("candidate_id") for row in rows)
        == (
            "V2_COMPARATOR",
            "M0_F2",
            "M1_RULE",
            "M2_LEARNED_MERGE",
            "M3_LEARNED_STACK",
        ),
        "FINAL_CANDIDATE_ROW_SET_DRIFT",
    )
    v2, f2, *candidates = rows
    _require(
        v2.get("candidate_role") == "frozen v2-safe comparator"
        and v2.get("evidence_scope") == "INHERITED_FROZEN_REFERENCE"
        and v2.get("status") == "REFERENCE_ONLY"
        and v2.get("execution_status") == "NOT_RERUN_G4IRSF14"
        and v2.get("original_entry_mean_minutes")
        == str(identity["v2_safe_raw_entry_mean_minutes"])
        and v2.get("delta_vs_v2_safe_seconds_per_bag") == "0.0"
        and v2.get("strict_win_vs_v2_safe") == "false"
        and v2.get("learning_contribution_proven") == "false"
        and v2.get("fault_regression_pass") == ""
        and v2.get("promotion_status") == "REFERENCE_NOT_CANDIDATE",
        "V2_REFERENCE_ROW_DRIFT",
    )
    _require(
        f2.get("candidate_role")
        == "frozen G4IRSF13 F2 deployment control"
        and f2.get("evidence_scope") == "INHERITED_FROZEN_REFERENCE"
        and f2.get("status") == "HISTORICAL_ONLY_PASS_REFERENCE"
        and f2.get("execution_status") == "NOT_RERUN_G4IRSF14"
        and f2.get("original_entry_mean_minutes")
        == str(identity["f2_raw_entry_mean_minutes"])
        and f2.get("delta_vs_v2_safe_seconds_per_bag")
        == str(identity["remaining_gap_seconds_per_bag"])
        and f2.get("strict_win_vs_v2_safe") == "false"
        and f2.get("learning_contribution_proven") == "false"
        and f2.get("fault_regression_pass") == ""
        and f2.get("promotion_status") == "KEEP_FROZEN_CONTROL",
        "F2_REFERENCE_ROW_DRIFT",
    )
    expected_roles = {
        "M1_RULE": "best eligible Stage F rule",
        "M2_LEARNED_MERGE": "learned merge ranker",
        "M3_LEARNED_STACK": "learned merge route admission plus P2 shield",
    }
    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id"))
        _require(
            candidate.get("candidate_role") == expected_roles[candidate_id]
            and candidate.get("evidence_scope") == "NO_EXECUTION"
            and candidate.get("status") == "NOT_RUN"
            and candidate.get("execution_status") == "NOT_RUN"
            and candidate.get("original_entry_mean_minutes") == ""
            and candidate.get("delta_vs_v2_safe_seconds_per_bag") == ""
            and candidate.get("strict_win_vs_v2_safe") == ""
            and candidate.get("learning_contribution_proven") == ""
            and candidate.get("fault_regression_pass") == ""
            and candidate.get("promotion_status")
            == "PARTIAL_WITH_EXPLICIT_BLOCKER",
            f"FINAL_NOT_RUN_CANDIDATE_METRIC_DRIFT:{candidate_id}",
        )
    _require(all(row.get("stage") == "M" for row in rows), "FINAL_STAGE_DRIFT")


def _validate_reports(root: Path, generation_id: str) -> None:
    for relative, status in REPORT_STATUS_MARKERS.items():
        path = root / relative
        _require(path.is_file(), f"MISSING_REPORT:{relative.as_posix()}")
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError as exc:
            raise CompletionValidationError(
                f"INVALID_UTF8_REPORT:{relative.as_posix()}"
            ) from exc
        _require(
            generation_id in text,
            f"REPORT_GENERATION_BINDING_DRIFT:{relative.as_posix()}",
        )
        _require(
            status in text,
            f"REPORT_STATUS_MARKER_DRIFT:{relative.as_posix()}",
        )
        for marker in REPORT_REQUIRED_MARKERS.get(relative, ()):
            _require(
                marker in text,
                f"REPORT_REQUIRED_SEMANTIC_DRIFT:{relative.as_posix()}:{marker}",
            )
        normalized = text.casefold().replace("`", "")
        for forbidden_claim in (
            "formal_pass_claimed: true",
            "formal_pass_claimed = true",
            "promotion_allowed: true",
            "promotion_allowed = true",
            *REPORT_FORBIDDEN_CLAIMS.get(relative, ()),
        ):
            _require(
                forbidden_claim not in normalized,
                (
                    "REPORT_CONTRADICTORY_CLAIM:"
                    f"{relative.as_posix()}:{forbidden_claim}"
                ),
            )
        if relative == FINAL_REPORT:
            for required_statement in (
                "- Stage 状态：`PARTIAL_WITH_EXPLICIT_BLOCKER`。",
                "- 总结论：`PARTIAL_WITH_EXPLICIT_BLOCKER`。",
                "- 学习：0 个 matched causal labels，训练与闭环均未运行，所以没有学习改善。",
                "- 冻结 F2 仍比 v2-safe 慢 `1.134703809870` 秒/袋。",
            ):
                _require(
                    required_statement in text,
                    f"FINAL_REPORT_FAIL_CLOSED_SUMMARY_DRIFT:{required_statement}",
                )
            for forbidden_claim in (
                "decision_status: pass",
                "deployment_action: promote",
                "stage m 完整通过",
                "g4irsf14 已正式通过",
                "已选定新候选",
                "scale gate 已解锁",
            ):
                _require(
                    forbidden_claim not in normalized,
                    f"FINAL_REPORT_CONTRADICTORY_CLAIM:{forbidden_claim}",
                )
            _require(
                "## 第 25 节的 18 个问题" in text,
                "FINAL_REPORT_QUESTION_SECTION_MISSING",
            )
            for question in range(1, 19):
                _require(
                    len(
                        re.findall(
                            rf"(?m)^{question}\. \*\*",
                            text,
                        )
                    )
                    == 1,
                    f"FINAL_REPORT_QUESTION_INVENTORY_DRIFT:{question}",
                )
            for required in (
                "根阻塞是尚无正式 Stage E matched-intervention campaign",
                "I1/I3/I4",
                "I2",
                "I5",
                "至少 2,000",
                "H_system > 0",
                "H0/Q0 与 H1/Q1",
                "+1.235566",
                "-0.100862",
                "不等于 top 1% 直接决定 p95/p99",
                "grant issue→fault",
                "prepare/commit→fault",
                "same-timestamp fault",
                "stale grant",
                "repair 仅一次",
                "P2 prepare/validate/commit/rollback 原子",
            ):
                _require(
                    required in text,
                    f"FINAL_REPORT_REQUIRED_ANSWER_DRIFT:{required}",
                )


def _validate_gate_base(
    value: Mapping[str, Any],
    *,
    schema: str,
    stage: str,
    status: str,
    generation_id: str,
    identity_sha256: str,
    census_self_sha256: str,
    label: str,
    expected_blockers: Sequence[str],
) -> None:
    _require(value.get("schema") == schema, f"{label}_SCHEMA_DRIFT")
    _require(
        value.get("stage") == stage
        and value.get("status") == status
        and value.get("generated_by")
        == "scripts/eval/g4irsf14_fail_closed_completion.py"
        and value.get("generation_id") == generation_id
        and value.get("input_identity_sha256") == identity_sha256
        and value.get("upstream_census_self_sha256") == census_self_sha256
        and value.get("formal_pass_claimed") is False
        and value.get("causal_label_count") == 0,
        f"{label}_BASE_SEMANTICS_DRIFT",
    )
    blockers = value.get("blockers")
    _require(
        blockers == list(expected_blockers),
        f"{label}_BLOCKERS_DRIFT",
    )


def _not_evaluated_inventory(
    requirements: Sequence[tuple[str, str]],
    *,
    include_satisfied: bool = False,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for requirement, threshold in requirements:
        row: dict[str, Any] = {
            "requirement": requirement,
            "threshold": threshold,
            "observed": None,
            "evaluation_status": "NOT_EVALUATED",
        }
        if include_satisfied:
            row["satisfied"] = False
        rows.append(row)
    return rows


def _validate_learning_threshold_inventory(value: Any) -> None:
    inventory = _mapping(value, "LEARNING_THRESHOLD_INVENTORY")
    _exact_keys(
        inventory,
        {"data", "route", "merge", "admission", "risk_abstention"},
        "LEARNING_THRESHOLD_INVENTORY",
    )
    expected_data = [
        {
            "requirement": "clone_fidelity",
            "threshold": "100%",
            "observed": "100%",
            "evaluation_status": "PASS",
        },
        {
            "requirement": "counterfactual_target_support",
            "threshold": ">0",
            "observed": 0,
            "evaluation_status": "FAIL_CLOSED",
        },
        *_not_evaluated_inventory(
            (
                ("train_validation_audit_overlap", "0"),
                ("candidate_request_completeness", "100%"),
                ("selected_action_grant_coverage", "100%"),
                ("no_future_runtime_leakage", "true"),
            )
        ),
    ]
    expected = {
        "data": expected_data,
        "route": _not_evaluated_inventory(
            (
                ("pairwise_accuracy", ">=0.70"),
                ("top1_accuracy", ">=0.75"),
                ("high_confidence_harmful", "<=0.01"),
                ("ece", "<=0.10"),
                ("f2_preserved_outside_target", ">=0.98"),
                ("positive_causal_precision", ">=0.80"),
            )
        ),
        "merge": _not_evaluated_inventory(
            (
                ("pairwise_grant_order_accuracy", ">=0.75"),
                ("top1_winner_accuracy", ">=0.75"),
                ("high_confidence_harmful_order", "<=0.01"),
                ("starvation_fairness_violation", "=0"),
                ("causal_positive_precision", ">=0.80"),
                ("estimated_recovered_mean_seconds_per_bag", ">=1.50"),
            )
        ),
        "admission": _not_evaluated_inventory(
            (
                ("beneficial_hold_precision", ">=0.80"),
                ("harmful_hold_rate", "<=0.01"),
                ("outside_target_activation", "<=0.02"),
                ("source_wait_offset_by_larger_network_decrease", "true"),
            )
        ),
        "risk_abstention": [
            {
                "requirement": "causal_support_positive",
                "threshold": "true",
                "observed": False,
                "evaluation_status": "FAIL_CLOSED",
            },
            *_not_evaluated_inventory(
                tuple(
                    (requirement, "true")
                    for requirement in (
                        "confidence_gate",
                        "state_in_distribution",
                        "grant_request_completeness",
                        "fault_generation_current",
                        "exact_f2_or_best_rule_fallback",
                    )
                )
            ),
        ],
    }
    _require(inventory == expected, "LEARNING_THRESHOLD_INVENTORY_DRIFT")


def _validate_closed_evaluation_inventory(value: Any) -> None:
    expected = {
        "hard": _not_evaluated_inventory(
            (
                ("complete_selected_bags_segments", "100%"),
                ("failed_count", "=0"),
                ("conflict_count", "=0"),
                ("unsafe_count", "=0"),
                ("runtime_full_astar_calls", "=0"),
                ("runtime_full_cie_calls", "=0"),
                ("global_scan_count", "=0"),
                ("future_route_input_count", "=0"),
                ("unresolved_deadlock_count", "=0"),
                ("reservation_depth", "=1"),
                ("event_or_time_limit_reached", "false"),
                ("deterministic_identity", "true"),
            )
        ),
        "performance": _not_evaluated_inventory(
            (
                ("primary_original_entry_time_tth", "measured"),
                ("strict_win_vs_f2", "true"),
                ("strict_win_vs_v2_safe", "true"),
                ("scheduled_dwell", "measured"),
                ("source_wait", "measured"),
                ("merge_grant_wait", "measured"),
                ("junction_wait", "measured"),
                ("network_time", "measured"),
                ("travel_time", "measured"),
                ("service_time", "measured"),
                ("path_edges", "measured"),
            )
        ),
        "mechanism": _not_evaluated_inventory(
            tuple(
                (requirement, "measured")
                for requirement in (
                    "model_activation_count",
                    "model_abstention_count",
                    "merge_request_count",
                    "merge_grant_count",
                    "grant_benefit",
                    "harmful_grant_count",
                    "p2_feasible_attempt_count",
                    "p2_commit_count",
                    "fault_shield_intervention_count",
                )
            )
        ),
        "learning": _not_evaluated_inventory(
            (("same_framework_learned_vs_best_rule", "learned_strictly_better"),)
        ),
        "tail": _not_evaluated_inventory(
            tuple(
                (metric, "non_regression")
                for metric in (
                    "mean",
                    "median",
                    "p90",
                    "p95",
                    "p99",
                    "max",
                    "top_1_percent_contribution",
                    "early",
                    "tight",
                    "storage",
                    "goal_50",
                    "busy_hour",
                    "source_groups",
                )
            )
        ),
    }
    _require(value == expected, "CLOSED_EVALUATION_INVENTORY_DRIFT")


def _validate_json_gates(
    root: Path,
    *,
    downstream: Mapping[str, Any],
    identity: Mapping[str, Any],
    generation_id: str,
    identity_sha256: str,
) -> dict[str, Any]:
    rule = _load_json(root, RULE_GATE)
    _validate_self_hash(rule, label="RULE_GATE")
    _exact_keys(
        rule,
        {
            "schema",
            "stage",
            "status",
            "generated_by",
            "generation_id",
            "input_identity_sha256",
            "upstream_census_self_sha256",
            "formal_pass_claimed",
            "causal_label_count",
            "blockers",
            "upper_bound_measured",
            "causal_upper_bound_seconds_per_bag",
            "planned_rule_count",
            "eligible_rule_count",
            "result_label_inventory",
            "selected_result_label",
            "diagnostic_only_rule_ids",
            "successive_halving_tiers",
            "elimination_criteria",
            "stage_d_mechanism_rule_count",
            "stage_d_observation",
            "output_bindings",
            "self_sha256",
        },
        "RULE_GATE",
    )
    _validate_gate_base(
        rule,
        schema="czr005.g4irsf14.rule_upper_bound_gate.v1",
        stage="F",
        status=STAGE_STATUS["F"],
        generation_id=generation_id,
        identity_sha256=identity_sha256,
        census_self_sha256=str(identity["census_self_sha256"]),
        label="RULE_GATE",
        expected_blockers=(
            "ZERO_COMPLETE_H_BAG_H_SYSTEM_CAUSAL_LABELS",
            "ORIGINAL_TASK_MINIMUM_2000_MATCHED_INTERVENTIONS_NOT_ESTABLISHED",
        ),
    )
    _require(
        rule.get("upper_bound_measured") is False
        and rule.get("causal_upper_bound_seconds_per_bag") is None
        and rule.get("planned_rule_count") == 14
        and rule.get("eligible_rule_count") == 0
        and rule.get("result_label_inventory")
        == [
            "RULE_NO_GAIN",
            "RULE_LOCAL_GAIN_ONLY",
            "RULE_FULL_GAIN_NOT_V2",
            "RULE_STRICT_V2_WIN",
        ]
        and rule.get("selected_result_label") is None
        and rule.get("diagnostic_only_rule_ids") == ["R-M7", "R-S5"]
        and rule.get("successive_halving_tiers")
        == [
            "REAL_MAP_MOTIF",
            "144",
            "512",
            "2048",
            "8192",
            "FULL_TOP_LE_3",
        ]
        and rule.get("elimination_criteria")
        == [
            "NON_DRAIN",
            "HARD_SAFETY_FAIL",
            "MEAN_LOSS_GT_0_5_SECONDS_PER_BAG_AT_MATCHED_TIER",
            "P95_LOSS_GT_2_SECONDS",
            "P99_LOSS_GT_4_SECONDS",
            "SOURCE_WAIT_GAIN_OFFSET_BY_LARGER_NETWORK_LOSS",
            "FAIRNESS_OR_STARVATION",
            "HIDDEN_FUTURE_READ",
            "NO_EFFECTIVE_ACTION",
        ]
        and rule.get("stage_d_mechanism_rule_count") == 7
        and rule.get("stage_d_observation")
        == {
            "executed_online_rule_count": 7,
            "observed_improved_rule_count": 0,
            "scope": "144_SEGMENT_MECHANISM_ONLY",
        },
        "RULE_GATE_PROMOTION_DRIFT",
    )
    _validate_binding_map(
        root,
        rule.get("output_bindings"),
        (RULE_REPORT, RULE_TABLE),
        "RULE_GATE",
    )

    learning = _load_json(root, LEARNING_GATE)
    _validate_self_hash(learning, label="LEARNING_GATE")
    _exact_keys(
        learning,
        {
            "schema",
            "stage",
            "status",
            "generated_by",
            "generation_id",
            "input_identity_sha256",
            "upstream_census_self_sha256",
            "formal_pass_claimed",
            "causal_label_count",
            "blockers",
            "training_status",
            "runtime_eligible",
            "selected_candidate",
            "model_artifacts_generated",
            "planned_negative_cohorts",
            "planned_split_dimensions",
            "clone_state_interventions_cross_split_allowed",
            "allowed_generalization_controls",
            "required_generalization_ablations",
            "data_gate",
            "offline_metrics",
            "threshold_inventory",
            "output_bindings",
            "self_sha256",
        },
        "LEARNING_GATE",
    )
    _validate_gate_base(
        learning,
        schema="czr005.g4irsf14.learning_preclosed_loop_gate.v1",
        stage="I",
        status=STAGE_STATUS["I"],
        generation_id=generation_id,
        identity_sha256=identity_sha256,
        census_self_sha256=str(identity["census_self_sha256"]),
        label="LEARNING_GATE",
        expected_blockers=(
            "ZERO_MATCHED_CAUSAL_TARGET_SUPPORT",
            "MINIMUM_2000_COMPLETE_INTERVENTIONS_NOT_MET",
            "NO_TRAIN_VALIDATION_AUDIT_SPLIT",
            "NO_ELIGIBLE_MODEL_ARTIFACT",
        ),
    )
    _require(
        learning.get("training_status") == STAGE_STATUS["H"]
        and learning.get("runtime_eligible") is False
        and learning.get("selected_candidate") is None
        and learning.get("model_artifacts_generated") == []
        and learning.get("planned_negative_cohorts")
        == [
            {"name": name, "evaluation_status": "NOT_EVALUATED"}
            for name in PLANNED_NEGATIVE_COHORTS
        ]
        and learning.get("planned_split_dimensions")
        == [
            {"name": name, "evaluation_status": "NOT_EVALUATED"}
            for name in PLANNED_SPLIT_DIMENSIONS
        ]
        and learning.get("clone_state_interventions_cross_split_allowed")
        is False
        and learning.get("allowed_generalization_controls")
        == [
            "SHARED_MODEL",
            "MERGE_SPECIFIC_BIAS",
            "LOCAL_CONTROLLER_CALIBRATION",
        ]
        and learning.get("required_generalization_ablations")
        == [
            {"name": name, "evaluation_status": "NOT_EVALUATED"}
            for name in REQUIRED_GENERALIZATION_ABLATIONS
        ]
        and learning.get("offline_metrics")
        == {"route": None, "merge": None, "admission": None},
        "LEARNING_GATE_ACTIVATION_DRIFT",
    )
    data_gate = _mapping(learning.get("data_gate"), "LEARNING_DATA_GATE")
    _require(
        data_gate
        == {
            "clone_fidelity_exact": True,
            "counterfactual_target_support_positive": False,
            "complete_intervention_count": 0,
            "minimum_complete_intervention_count": MIN_FORMAL_INTERVENTIONS,
            "train_validation_audit_overlap_zero": None,
            "candidate_request_completeness": None,
            "selected_action_grant_coverage": None,
            "no_future_runtime_leakage": None,
        },
        "LEARNING_DATA_GATE_DRIFT",
    )
    _validate_learning_threshold_inventory(learning.get("threshold_inventory"))
    _validate_binding_map(
        root,
        learning.get("output_bindings"),
        (
            LEARNING_DATA_REPORT,
            OFFLINE_REPORT,
            ROUTE_OFFLINE_TABLE,
            MERGE_OFFLINE_TABLE,
            ADMISSION_OFFLINE_TABLE,
        ),
        "LEARNING_GATE",
    )

    closed = _load_json(root, CLOSED_LOOP_GATE)
    _validate_self_hash(closed, label="CLOSED_LOOP_GATE")
    _exact_keys(
        closed,
        {
            "schema",
            "stage",
            "status",
            "generated_by",
            "generation_id",
            "input_identity_sha256",
            "upstream_census_self_sha256",
            "formal_pass_claimed",
            "causal_label_count",
            "blockers",
            "candidate_execution_count",
            "full_scale_execution_count",
            "promotion_allowed",
            "evaluation_inventory",
            "output_bindings",
            "self_sha256",
        },
        "CLOSED_LOOP_GATE",
    )
    _validate_gate_base(
        closed,
        schema="czr005.g4irsf14.closed_loop_gate.v1",
        stage="J",
        status=STAGE_STATUS["J"],
        generation_id=generation_id,
        identity_sha256=identity_sha256,
        census_self_sha256=str(identity["census_self_sha256"]),
        label="CLOSED_LOOP_GATE",
        expected_blockers=(
            "RULE_UPPER_BOUND_GATE_NOT_RUN",
            "LEARNING_PRECLOSED_LOOP_GATE_FAIL_CLOSED",
        ),
    )
    _require(
        closed.get("candidate_execution_count") == 0
        and closed.get("full_scale_execution_count") == 0
        and closed.get("promotion_allowed") is False,
        "CLOSED_LOOP_GATE_EXECUTION_DRIFT",
    )
    _validate_closed_evaluation_inventory(closed.get("evaluation_inventory"))
    _validate_binding_map(
        root,
        closed.get("output_bindings"),
        (CLOSED_LOOP_REPORT, CLOSED_LOOP_TABLE, LEARNING_GATE),
        "CLOSED_LOOP_GATE",
    )

    final = _load_json(root, FINAL_BUNDLE)
    _validate_self_hash(final, label="FINAL_BUNDLE")
    _exact_keys(
        final,
        {
            "schema",
            "stage",
            "status",
            "decision_status",
            "deployment_action",
            "generated_by",
            "generation_id",
            "input_identity",
            "stage_statuses",
            "selected_candidate_id",
            "candidate_selection_status",
            "new_candidate_execution_count",
            "formal_pass_claimed",
            "strict_win_vs_v2_safe",
            "strict_win_vs_v2_safe_evaluation_status",
            "strict_win_vs_v2_safe_gate_satisfied",
            "strict_win_vs_v2_safe_proven",
            "learning_contribution_proven",
            "learning_contribution_evaluation_status",
            "learning_contribution_gate_satisfied",
            "fault_regression_pass",
            "fault_regression_evaluation_status",
            "fault_regression_gate_satisfied",
            "fault_regression_proven",
            "tail_gate_pass",
            "tail_gate_evaluation_status",
            "tail_gate_satisfied",
            "tail_gate_proven",
            "scale_unlocked",
            "model_artifacts_generated",
            "performance",
            "inheritance_boundary",
            "phase_decisions",
            "improvement_statuses",
            "causal_evidence",
            "blocker",
            "fault_regression_requirements",
            "formal_hard_gate_inventory",
            "performance_gate_inventory",
            "mechanism_gate_inventory",
            "repeat_requirement",
            "hash_slice_inventory",
            "output_bindings",
            "self_sha256",
        },
        "FINAL_BUNDLE",
    )
    _require(
        final.get("schema")
        == "czr005.g4irsf14.final_candidate_bundle.v1"
        and final.get("stage") == "M"
        and final.get("status") == STAGE_STATUS["M"]
        and final.get("decision_status") == "PARTIAL_WITH_EXPLICIT_BLOCKER"
        and final.get("deployment_action")
        == "KEEP_G4IRSF13_F2_FROZEN_CONTROL"
        and final.get("generated_by")
        == "scripts/eval/g4irsf14_fail_closed_completion.py"
        and final.get("generation_id") == generation_id
        and final.get("input_identity") == identity
        and final.get("stage_statuses") == STAGE_STATUS
        and final.get("selected_candidate_id") is None
        and final.get("candidate_selection_status")
        == "NO_ELIGIBLE_G4IRSF14_CANDIDATE"
        and final.get("new_candidate_execution_count") == 0
        and final.get("formal_pass_claimed") is False
        and final.get("strict_win_vs_v2_safe") is None
        and final.get("strict_win_vs_v2_safe_evaluation_status")
        == "NOT_EVALUATED"
        and final.get("strict_win_vs_v2_safe_gate_satisfied") is False
        and final.get("strict_win_vs_v2_safe_proven") is False
        and final.get("learning_contribution_proven") is False
        and final.get("learning_contribution_evaluation_status")
        == "NOT_EVALUATED"
        and final.get("learning_contribution_gate_satisfied") is False
        and final.get("fault_regression_pass") is None
        and final.get("fault_regression_evaluation_status") == "NOT_EVALUATED"
        and final.get("fault_regression_gate_satisfied") is False
        and final.get("fault_regression_proven") is False
        and final.get("tail_gate_pass") is None
        and final.get("tail_gate_evaluation_status") == "NOT_EVALUATED"
        and final.get("tail_gate_satisfied") is False
        and final.get("tail_gate_proven") is False
        and final.get("scale_unlocked") is False
        and final.get("model_artifacts_generated") == [],
        "FINAL_BUNDLE_PROMOTION_DRIFT",
    )
    _require(
        final.get("performance")
        == {
            "new_candidate_metrics": None,
            "f2_frozen_reference_mean_minutes": identity[
                "f2_raw_entry_mean_minutes"
            ],
            "v2_safe_frozen_reference_mean_minutes": identity[
                "v2_safe_raw_entry_mean_minutes"
            ],
            "remaining_gap_seconds_per_bag": identity[
                "remaining_gap_seconds_per_bag"
            ],
        },
        "FINAL_PERFORMANCE_BOUNDARY_DRIFT",
    )
    _require(
        final.get("inheritance_boundary")
        == {
            "g4irsf13_f2_status": "HISTORICAL_ONLY_PASS",
            "g4irsf13_f2_is_deployment_control": True,
            "g4irsf14_may_inherit_historical_pass": False,
            "g4irsf14_inherited_promotion_status": "FORBIDDEN",
        },
        "FINAL_INHERITANCE_BOUNDARY_DRIFT",
    )
    _require(
        final.get("phase_decisions")
        == {
            "G4J": "CLOSED",
            "K": "UNKNOWN/CLOSED",
            "L": "NOT_RUN",
            "scale_execution_count": 0,
        },
        "FINAL_PHASE_DECISION_DRIFT",
    )
    _require(
        final.get("improvement_statuses")
        == {
            "architecture": {
                "status": (
                    "MECHANISM_IMPLEMENTED_AND_AUDITABLE_"
                    "ORIGINAL_1X_IMPROVEMENT_NOT_PROVEN"
                ),
                "evaluation_status": "MECHANISM_EVIDENCE_ONLY",
                "proven_improvement": False,
            },
            "rule": {
                "status": STAGE_STATUS["F"],
                "evaluation_status": "NOT_EVALUATED",
                "proven_improvement": False,
            },
            "learning": {
                "status": STAGE_STATUS["H"],
                "evaluation_status": "NOT_EVALUATED",
                "proven_improvement": False,
            },
        },
        "FINAL_IMPROVEMENT_STATUS_DRIFT",
    )
    _require(
        final.get("causal_evidence")
        == {
            "complete_matched_intervention_count": 0,
            "h_system_intervention_count": 0,
            "minimum_required_complete_interventions": MIN_FORMAL_INTERVENTIONS,
            "pibt_prefilter_candidate_count": 1_337,
            "pibt_applicable_ready_slice_boundary_count": 0,
            "scope": (
                "EXACT_CLONE_NOOP_AND_SCREENING_ONLY_NOT_ACTION_CHANGING_"
                "CAUSAL_OUTCOME"
            ),
        },
        "FINAL_CAUSAL_COUNT_DRIFT",
    )
    _require(
        final.get("blocker")
        == {
            "code": "NO_FORMAL_STAGE_E_MATCHED_INTERVENTION_CAMPAIGN",
            "child_blockers": [
                "ZERO_COMPLETE_LABELS",
                "MIN_2000_UNMET",
                "H_SYSTEM_ZERO",
                "I2_LIVE_SUPPORT_ONLY_1",
                "I5_APPLICABLE_SUPPORT_ZERO",
            ],
            "next_required_action": (
                "MAKE_THE_PREREGISTERED_EXACT_BINARY_NATIVE_CAMPAIGN_"
                "EXECUTABLE_AND_OBTAIN_COMPLETE_H_BAG_H_SYSTEM_OUTCOMES_"
                "FOR_SUPPORTED_I1_I3_I4_WHILE_RESTORING_OR_REDESIGNING_"
                "I2_PRIMARY_MERGE_SUPPORT_AND_I5_APPLICABLE_OPPORTUNITIES_"
                "THEN_REACH_AT_LEAST_2000_COMPLETE_LABELS_WITH_NONZERO_"
                "H_SYSTEM;DO_NOT_TRAIN_UNTIL_THE_COMPLETE_STAGE_E_GATE_PASSES"
            ),
        },
        "FINAL_BLOCKER_DRIFT",
    )
    fault_requirements = (
        "G0_G1_G2_G3_G5_G6_G7_CASE_MATRIX_COMPLETE",
        "GRANT_ISSUE_TO_FAULT",
        "PREPARE_COMMIT_TO_FAULT",
        "SAME_TIMESTAMP_BATCH_AND_FAULT_EVENT",
        "STALE_GRANT_REPAIR_ONCE_AND_CLEANUP",
        "P2_PREPARE_VALIDATE_COMMIT_ROLLBACK_ATOMIC",
    )
    _require(
        final.get("fault_regression_requirements")
        == [
            {
                "requirement": requirement,
                "observed": None,
                "evaluation_status": "NOT_EVALUATED",
                "satisfied": False,
            }
            for requirement in fault_requirements
        ],
        "FINAL_FAULT_REQUIREMENT_INVENTORY_DRIFT",
    )
    _require(
        final.get("formal_hard_gate_inventory")
        == _not_evaluated_inventory(
            (
                ("exact_original_entry_time_denominator", "true"),
                ("complete_raw_bags", "=28506"),
                ("complete_segments", "=43603"),
                ("failed_count", "=0"),
                ("conflict_count", "=0"),
                ("unsafe_entry_count", "=0"),
                ("runtime_full_astar_calls", "=0"),
                ("runtime_full_cie_calls", "=0"),
                ("global_reservation_scan_count", "=0"),
                ("future_route_input_count", "=0"),
                ("unresolved_deadlock_count", "=0"),
                ("reservation_depth", "=1"),
                ("event_limit_reached", "false"),
                ("time_limit_reached", "false"),
                ("deterministic_identity", "true"),
                ("fault_regression", "pass"),
                ("protected_files_clean", "true"),
            ),
            include_satisfied=True,
        ),
        "FINAL_HARD_GATE_INVENTORY_DRIFT",
    )
    _require(
        final.get("performance_gate_inventory")
        == _not_evaluated_inventory(
            (
                ("strict_win_vs_v2_safe_mean_minutes", "<41.495306987809"),
                ("strong_pass_margin_seconds_per_bag", ">=0.25"),
                ("small_margin_pass", "strict_win_and_margin<0.25"),
                ("tail_gate", "pass"),
            ),
            include_satisfied=True,
        ),
        "FINAL_PERFORMANCE_GATE_INVENTORY_DRIFT",
    )
    _require(
        final.get("mechanism_gate_inventory")
        == _not_evaluated_inventory(
            (
                ("source_network_grant_decomposition", "complete"),
                ("learning_ablation", "complete"),
            ),
            include_satisfied=True,
        ),
        "FINAL_MECHANISM_GATE_INVENTORY_DRIFT",
    )
    _require(
        final.get("repeat_requirement")
        == {
            "required": 5,
            "actual": 0,
            "evaluation_status": "NOT_EVALUATED",
            "satisfied": False,
            "deterministic_repeats_are_independent_samples": False,
        },
        "FINAL_REPEAT_REQUIREMENT_DRIFT",
    )
    _require(
        final.get("hash_slice_inventory")
        == {
            "hashes": [
                {
                    "name": name,
                    "observed": None,
                    "evaluation_status": "NOT_EVALUATED",
                }
                for name in (
                    "repeat_result_hashes",
                    "binary_sha256",
                    "source_bundle_sha256",
                    "model_sha256",
                    "map_sha256",
                    "task_sha256",
                )
            ],
            "slices": [
                {
                    "name": name,
                    "observed": None,
                    "evaluation_status": "NOT_EVALUATED",
                }
                for name in (
                    "hour",
                    "source",
                    "goal",
                    "ebs_direct",
                    "contention",
                    "top_tail",
                    "no_divergence",
                    "grant_active",
                    "p2_active",
                )
            ],
        },
        "FINAL_HASH_SLICE_INVENTORY_DRIFT",
    )
    _validate_binding_map(
        root,
        final.get("output_bindings"),
        FINAL_BOUND_PATHS,
        "FINAL_BUNDLE",
    )

    scale = _load_json(root, SCALE_GATE)
    _validate_self_hash(scale, label="SCALE_GATE")
    _exact_keys(
        scale,
        {
            "schema",
            "stage",
            "status",
            "generated_by",
            "generation_id",
            "input_identity_sha256",
            "upstream_census_self_sha256",
            "formal_pass_claimed",
            "causal_label_count",
            "blockers",
            "all_five_gates_pass",
            "scale_execution_count",
            "allowed_scales",
            "forbidden_current_scales",
            "conditions",
            "output_bindings",
            "self_sha256",
        },
        "SCALE_GATE",
    )
    _validate_gate_base(
        scale,
        schema="czr005.g4irsf14.scale_unlock_gate.v1",
        stage="M",
        status="LOCKED",
        generation_id=generation_id,
        identity_sha256=identity_sha256,
        census_self_sha256=str(identity["census_self_sha256"]),
        label="SCALE_GATE",
        expected_blockers=(
            "STRICT_V2_SAFE_WIN_NOT_PROVEN",
            "LEARNING_CONTRIBUTION_NOT_PROVEN",
            "FAULT_REGRESSION_NOT_RUN",
            "NUMERIC_DEMAND_CALIBRATION_NOT_COMPLETE",
            "ORIGINAL_TASK_GENERATION_AUDIT_NOT_PROMOTED_FOR_SCALE",
        ),
    )
    _require(
        scale.get("all_five_gates_pass") is False
        and scale.get("scale_execution_count") == 0
        and scale.get("allowed_scales") == []
        and scale.get("forbidden_current_scales")
        == ["1.1x", "1.2x", "1.3x", "2x", "4x", "8x", "16x", "32x", "2x+"]
        and scale.get("conditions")
        == {
            "strict_v2_safe_win": {
                "evaluation_status": "NOT_EVALUATED",
                "satisfied": False,
                "evidence": "NO_ELIGIBLE_G4IRSF14_CANDIDATE",
            },
            "learning_contribution_proven": {
                "evaluation_status": "NOT_EVALUATED",
                "satisfied": False,
                "evidence": "LEARNING_NOT_RUN",
            },
            "fault_regression_pass": {
                "evaluation_status": "NOT_EVALUATED",
                "satisfied": False,
                "evidence": "NO_ELIGIBLE_NEW_CANDIDATE",
            },
            "numeric_demand_calibration_complete": {
                "evaluation_status": "NOT_EVALUATED",
                "satisfied": False,
                "evidence": "SCALE_CALIBRATION_NOT_RUN",
            },
            "original_task_generation_audit_pass": {
                "evaluation_status": "NOT_EVALUATED",
                "satisfied": False,
                "evidence": "SCALE_GENERATION_AUDIT_NOT_RUN",
            },
        },
        "SCALE_GATE_UNLOCK_DRIFT",
    )
    _validate_binding_map(
        root,
        scale.get("output_bindings"),
        (FINAL_REPORT, FINAL_TABLE, FINAL_BUNDLE),
        "SCALE_GATE",
    )

    _require(
        downstream.get("input_identity") == identity,
        "DOWNSTREAM_INPUT_IDENTITY_DRIFT",
    )
    return final


def _validate_no_models(root: Path) -> None:
    models = root / "artifacts/models"
    if not models.is_dir():
        return
    observed = sorted(
        path.relative_to(root).as_posix()
        for path in models.rglob("*")
        if path.is_file()
        and path.name.casefold().startswith("g4irsf14_")
    )
    _require(not observed, f"UNAUTHORIZED_G4IRSF14_MODELS:{observed}")


def validate_fail_closed_completion(root: Path = ROOT) -> dict[str, Any]:
    """Validate the committed 24-file F--M fail-closed bundle.

    The function is read-only.  It validates the Stage-E six-file payload
    statically and therefore remains portable even when the generation
    machine's absolute binary path is unavailable.
    """

    root = root.resolve()
    _require(root.is_dir(), f"ROOT_NOT_DIRECTORY:{root}")
    for relative in REQUIRED_BUNDLE_FILES:
        _require(
            (root / relative).is_file(),
            f"REQUIRED_FILE_MISSING:{relative.as_posix()}",
        )

    stage_e_document, stage_e_manifest = _validate_stage_e_static(root)
    merge_executed, merge_improved = _validate_merge_mechanism(root)

    downstream = _load_json(root, DOWNSTREAM_GATE)
    _validate_self_hash(downstream, label="DOWNSTREAM_GATE")
    _exact_keys(
        downstream,
        {
            "schema",
            "status",
            "generated_by",
            "generation_id",
            "input_identity",
            "stage_statuses",
            "formal_pass_claimed",
            "promotion_allowed",
            "model_artifacts_generated",
            "new_experiment_execution_count",
            "causal_label_count",
            "pibt_measurement",
            "not_run_is_not_pass",
            "single_blocker",
            "fault_regression_requirements",
            "output_bindings",
            "self_sha256",
        },
        "DOWNSTREAM_GATE",
    )
    _require(
        downstream.get("schema")
        == "czr005.g4irsf14.downstream_fail_closed_gate.v1"
        and downstream.get("status") == "PARTIAL_WITH_EXPLICIT_BLOCKER"
        and downstream.get("generated_by")
        == "scripts/eval/g4irsf14_fail_closed_completion.py"
        and downstream.get("stage_statuses") == STAGE_STATUS
        and downstream.get("formal_pass_claimed") is False
        and downstream.get("promotion_allowed") is False
        and downstream.get("model_artifacts_generated") == []
        and downstream.get("new_experiment_execution_count") == 0
        and downstream.get("causal_label_count") == 0
        and downstream.get("not_run_is_not_pass") is True,
        "DOWNSTREAM_GATE_POLICY_DRIFT",
    )
    pibt_measurement = _mapping(
        downstream.get("pibt_measurement"), "DOWNSTREAM_PIBT"
    )
    _require(
        pibt_measurement
        == {
            "attempt_count": 0,
            "prefilter_candidate_count": 1_337,
            "applicable_ready_slice_boundary_count": 0,
            "canonical_reason_count": 17,
            "taxonomy_runtime_complete": False,
        },
        "DOWNSTREAM_PIBT_PREFILTER_ATTEMPT_CONFLATION",
    )
    single_blocker = _mapping(
        downstream.get("single_blocker"), "DOWNSTREAM_BLOCKER"
    )
    _require(
        single_blocker
        == {
            "code": "NO_FORMAL_STAGE_E_MATCHED_INTERVENTION_CAMPAIGN",
            "child_blockers": [
                "ZERO_COMPLETE_LABELS",
                "MIN_2000_UNMET",
                "H_SYSTEM_ZERO",
                "I2_LIVE_SUPPORT_ONLY_1",
                "I5_APPLICABLE_SUPPORT_ZERO",
            ],
            "detail": (
                "MAKE_THE_PREREGISTERED_EXACT_BINARY_NATIVE_CAMPAIGN_"
                "EXECUTABLE_FOR_SUPPORTED_I1_I3_I4_AND_OBTAIN_COMPLETE_"
                "H_BAG_H_SYSTEM_WHILE_RESTORING_OR_REDESIGNING_I2_PRIMARY_"
                "MERGE_AND_I5_APPLICABLE_SUPPORT;NO_TRAINING_BEFORE_THE_"
                "COMPLETE_STAGE_E_GATE_PASSES"
            ),
        },
        "DOWNSTREAM_SINGLE_BLOCKER_DRIFT",
    )
    _require(
        downstream.get("fault_regression_requirements")
        == [
            {
                "requirement": requirement,
                "evaluation_status": "NOT_EVALUATED",
            }
            for requirement in (
                "G0_G1_G2_G3_G5_G6_G7_CASE_MATRIX_COMPLETE",
                "GRANT_ISSUE_TO_FAULT",
                "PREPARE_COMMIT_TO_FAULT",
                "SAME_TIMESTAMP_BATCH_AND_FAULT_EVENT",
                "STALE_GRANT_REPAIR_ONCE_AND_CLEANUP",
                "P2_PREPARE_VALIDATE_COMMIT_ROLLBACK_ATOMIC",
            )
        ],
        "DOWNSTREAM_FAULT_REQUIREMENT_INVENTORY_DRIFT",
    )
    _validate_binding_map(
        root,
        downstream.get("output_bindings"),
        tuple(path for path in OUTPUT_PATHS if path != DOWNSTREAM_GATE),
        "DOWNSTREAM_GATE",
    )

    identity = _mapping(downstream.get("input_identity"), "INPUT_IDENTITY")
    identity_sha256 = _validate_input_identity(
        root,
        identity,
        stage_e_document,
        stage_e_manifest,
        merge_executed=merge_executed,
        merge_improved=merge_improved,
    )
    expected_generation_id = canonical_sha256(
        {
            "schema": "czr005.g4irsf14.fail_closed_generation.v1",
            "input_identity_sha256": identity_sha256,
            "stage_status": STAGE_STATUS,
            "output_paths": [path.as_posix() for path in OUTPUT_PATHS],
        }
    )
    _require(
        downstream.get("generation_id") == expected_generation_id,
        "GENERATION_ID_DRIFT",
    )

    rows_by_path = {
        path: _read_csv(root, path, columns)
        for path, columns in CSV_SCHEMAS.items()
    }
    _validate_common_rows(
        rows_by_path,
        generation_id=expected_generation_id,
        identity_sha256=identity_sha256,
    )
    _validate_rule_rows(rows_by_path[RULE_TABLE])
    _validate_pibt_rows(
        rows_by_path[PIBT_REASONS_TABLE],
        rows_by_path[PIBT_COMMIT_TABLE],
    )
    _validate_offline_rows(
        rows_by_path[ROUTE_OFFLINE_TABLE],
        rows_by_path[MERGE_OFFLINE_TABLE],
        rows_by_path[ADMISSION_OFFLINE_TABLE],
    )
    _validate_closed_rows(rows_by_path[CLOSED_LOOP_TABLE])
    _validate_fault_rows(rows_by_path[FAULT_TABLE])
    _validate_runtime_rows(rows_by_path[RUNTIME_TABLE])
    _validate_final_rows(rows_by_path[FINAL_TABLE], identity)
    _validate_reports(root, expected_generation_id)
    final = _validate_json_gates(
        root,
        downstream=downstream,
        identity=identity,
        generation_id=expected_generation_id,
        identity_sha256=identity_sha256,
    )
    _validate_no_models(root)

    return {
        "schema": "czr005.g4irsf14.fail_closed_validation.v1",
        "status": "PARTIAL_WITH_EXPLICIT_BLOCKER_VALID",
        "output_count": len(OUTPUT_PATHS),
        "generation_id": expected_generation_id,
        "input_identity_sha256": identity_sha256,
        "stage_statuses": dict(STAGE_STATUS),
        "causal_label_count": 0,
        "pibt_prefilter_candidate_count": 1_337,
        "pibt_attempt_count": 0,
        "selected_candidate_id": final["selected_candidate_id"],
        "deployment_action": final["deployment_action"],
        "scale_execution_count": final["phase_decisions"][
            "scale_execution_count"
        ],
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Independently validate the committed G4IRSF14 F-M "
            "fail-closed completion bundle."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Repository or copied bundle root.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = validate_fail_closed_completion(args.root)
    except (
        CompletionValidationError,
        OpportunityCensusError,
        OSError,
        UnicodeError,
        ValueError,
    ) as exc:
        print(f"G4IRSF14 fail-closed completion validation: FAIL: {exc}")
        return 1
    print(
        "G4IRSF14 fail-closed completion validation: "
        "PARTIAL_WITH_EXPLICIT_BLOCKER_VALID\n"
        + json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
