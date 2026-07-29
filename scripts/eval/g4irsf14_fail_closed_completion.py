#!/usr/bin/env python3
"""Publish the G4IRSF14 F--M fail-closed completion bundle.

This generator is intentionally non-experimental.  It consumes the committed
Stage-E blocker census, the Stage-D merge-rule table, and the frozen G4IRSF13
controls.  When the causal gate is closed it records every downstream stage as
NOT_RUN (or its stage-specific fail-closed equivalent).  It never trains a
model, runs a candidate, invents a metric, or turns a zero denominator into a
rate.

All payloads are staged and fsynced before publication.  The unified
``g4irsf14_downstream_fail_closed_gate.json`` is replaced last and therefore
acts as the commit marker for the multi-file bundle.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

MAP_RAW_SHA256 = (
    "9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4"
)
MAP_SEMANTIC_SHA256 = (
    "67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63"
)
TASK_RAW_SHA256 = (
    "968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f"
)
FULL_SEGMENT_COUNT = 43_603
FULL_RAW_BAG_COUNT = 28_506
MIN_FORMAL_INTERVENTIONS = 2_000
MIN_B5_READY_SET_ROWS = 20_000

UPSTREAM_CENSUS = Path("outputs/tables/g4irsf14_opportunity_census.json")
UPSTREAM_CLONE_MANIFEST = Path(
    "artifacts/datasets/g4irsf14_clone_manifest.json"
)
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
    UPSTREAM_CLONE_MANIFEST: (
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


class FailClosedCompletionError(RuntimeError):
    """Raised when an upstream binding or a fail-closed invariant drifts."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FailClosedCompletionError(message)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    _require(path.is_file(), f"MISSING_BOUND_FILE:{path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _self_bound(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result.pop("self_sha256", None)
    result["self_sha256"] = _canonical_sha256(result)
    return result


def _load_json(root: Path, relative: Path) -> dict[str, Any]:
    path = root / relative
    _require(path.is_file(), f"MISSING_JSON:{relative.as_posix()}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FailClosedCompletionError(
            f"INVALID_JSON:{relative.as_posix()}:{type(exc).__name__}"
        ) from exc
    _require(isinstance(value, dict), f"JSON_NOT_OBJECT:{relative.as_posix()}")
    return value


def _validate_self_hash(
    value: Mapping[str, Any],
    field: str,
    label: str,
) -> None:
    declared = value.get(field)
    _require(
        isinstance(declared, str) and len(declared) == 64,
        f"MISSING_SELF_HASH:{label}:{field}",
    )
    projection = dict(value)
    projection.pop(field, None)
    _require(
        declared == _canonical_sha256(projection),
        f"SELF_HASH_DRIFT:{label}:{field}",
    )


def _strict_int(value: Any, label: str) -> int:
    _require(
        isinstance(value, int) and not isinstance(value, bool),
        f"NOT_INTEGER:{label}",
    )
    return int(value)


def _strict_float(value: Any, label: str) -> float:
    _require(
        isinstance(value, (int, float)) and not isinstance(value, bool),
        f"NOT_NUMERIC:{label}",
    )
    result = float(value)
    _require(math.isfinite(result), f"NONFINITE:{label}")
    return result


def _csv_rows(root: Path, relative: Path) -> list[dict[str, str]]:
    path = root / relative
    _require(path.is_file(), f"MISSING_CSV:{relative.as_posix()}")
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except UnicodeError as exc:
        raise FailClosedCompletionError(
            f"INVALID_UTF8_CSV:{relative.as_posix()}"
        ) from exc


def _row_hashes(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for source in rows:
        row = {str(key): str(value) for key, value in source.items()}
        _require("row_sha256" not in row, "ROW_ALREADY_HAS_HASH")
        row["row_sha256"] = _canonical_sha256(row)
        result.append(row)
    return result


def _csv_bytes(
    fields: Sequence[str],
    rows: Sequence[Mapping[str, str]],
) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=list(fields),
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        _require(set(row) == set(fields), "CSV_FIELD_INVENTORY_DRIFT")
        writer.writerow(row)
    return stream.getvalue().encode("utf-8")


def _markdown(lines: Sequence[str]) -> bytes:
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def _bound_file(root: Path, relative: Path) -> dict[str, Any]:
    path = root / relative
    return {
        "path": relative.as_posix(),
        "sha256": _file_sha256(path),
        "byte_count": path.stat().st_size,
    }


def _validate_registry_files(
    root: Path,
    registry: Mapping[str, Any],
) -> None:
    inherited = registry.get("inherited_artifacts")
    _require(isinstance(inherited, dict), "BASELINE_INHERITED_BINDINGS_MISSING")
    for key, binding in inherited.items():
        _require(isinstance(binding, dict), f"BAD_REGISTRY_BINDING:{key}")
        relative = Path(str(binding.get("path", key)))
        declared = str(binding.get("file_sha256", ""))
        _require(
            declared == _file_sha256(root / relative),
            f"FROZEN_ARTIFACT_DRIFT:{relative.as_posix()}",
        )
    for key in ("f2_frozen_control", "fault_frozen_control"):
        binding = registry.get(key)
        _require(isinstance(binding, dict), f"MISSING_REGISTRY_CONTROL:{key}")
        relative = Path(str(binding.get("path", "")))
        _require(
            str(binding.get("file_sha256", ""))
            == _file_sha256(root / relative),
            f"FROZEN_CONTROL_DRIFT:{key}",
        )


def _validate_inputs(root: Path) -> dict[str, Any]:
    root = root.resolve()
    for relative, expected_sha256 in PINNED_UPSTREAM_SHA256.items():
        _require(
            _file_sha256(root / relative) == expected_sha256,
            f"PINNED_UPSTREAM_HASH_DRIFT:{relative.as_posix()}",
        )
    _require(
        _file_sha256(root / MAP_PATH) == MAP_RAW_SHA256,
        "PROTECTED_MAP_RAW_HASH_DRIFT",
    )
    _require(
        _file_sha256(root / TASK_PATH) == TASK_RAW_SHA256,
        "PROTECTED_TASK_RAW_HASH_DRIFT",
    )

    census = _load_json(root, UPSTREAM_CENSUS)
    _require(
        census.get("schema") == "czr005.g4irsf14.opportunity_census.v1",
        "UPSTREAM_CENSUS_SCHEMA_DRIFT",
    )
    _require(
        census.get("status") == "PARTIAL_WITH_EXPLICIT_BLOCKER",
        "UPSTREAM_CENSUS_NOT_PARTIAL",
    )
    _require(census.get("formal_pass_claimed") is False, "CAUSAL_PASS_CLAIMED")
    _require(census.get("causal_label_count") == 0, "CAUSAL_LABEL_COUNT_NOT_ZERO")
    _validate_self_hash(census, "self_sha256", "opportunity_census")
    protected = census.get("protected_inputs")
    _require(isinstance(protected, dict), "CENSUS_PROTECTED_INPUTS_MISSING")
    _require(
        protected.get("map")
        == {
            "path": MAP_PATH.as_posix(),
            "raw_sha256": MAP_RAW_SHA256,
            "semantic_sha256": MAP_SEMANTIC_SHA256,
        },
        "CENSUS_MAP_IDENTITY_DRIFT",
    )
    _require(
        protected.get("task")
        == {
            "path": TASK_PATH.as_posix(),
            "raw_sha256": TASK_RAW_SHA256,
            "semantic_sha256": TASK_RAW_SHA256,
            "segment_count": FULL_SEGMENT_COUNT,
            "raw_bag_count": FULL_RAW_BAG_COUNT,
        },
        "CENSUS_TASK_IDENTITY_DRIFT",
    )
    support = census.get("support")
    _require(isinstance(support, dict), "CENSUS_SUPPORT_MISSING")
    i2 = support.get("I2_merge_request_order_swap")
    i5 = support.get("I5_pibt_trigger")
    _require(isinstance(i2, dict), "I2_SUPPORT_MISSING")
    _require(isinstance(i5, dict), "I5_SUPPORT_MISSING")
    _require(
        _strict_int(
            i2.get("eligible_live_multi_request_boundary_count"),
            "i2 eligible boundary count",
        )
        == 1,
        "I2_EXPECTED_SCREENING_COUNT_DRIFT",
    )
    pibt_prefilter = _strict_int(
        i5.get("prefilter_candidate_count"), "i5 prefilter count"
    )
    pibt_applicable = _strict_int(
        i5.get("applicable_ready_slice_boundary_count"),
        "i5 applicable count",
    )
    _require(pibt_prefilter == 1_337, "I5_PREFILTER_COUNT_DRIFT")
    _require(pibt_applicable == 0, "I5_APPLICABLE_SUPPORT_IS_NOT_ZERO")
    _require(i5.get("exact_zero_proven") is True, "I5_ZERO_NOT_EXACT")
    for component, component_support in support.items():
        _require(
            isinstance(component_support, dict),
            f"BAD_SUPPORT_OBJECT:{component}",
        )
        _require(
            component_support.get("causal_label_count") == 0,
            f"NONZERO_CAUSAL_LABELS:{component}",
        )
        _require(
            component_support.get("formal_horizon_completion_count") == 0,
            f"NONZERO_FORMAL_HORIZON:{component}",
        )

    clone_manifest = _load_json(root, UPSTREAM_CLONE_MANIFEST)
    _require(
        clone_manifest.get("schema")
        == "czr005.g4irsf14.blocker_bundle_manifest.v1",
        "CLONE_MANIFEST_SCHEMA_DRIFT",
    )
    _require(
        clone_manifest.get("status") == "PARTIAL_WITH_EXPLICIT_BLOCKER",
        "CLONE_MANIFEST_NOT_PARTIAL",
    )
    _require(
        clone_manifest.get("formal_pass_claimed") is False,
        "CLONE_MANIFEST_FORMAL_PASS_CLAIMED",
    )
    _require(
        clone_manifest.get("causal_label_count") == 0,
        "CLONE_MANIFEST_CAUSAL_LABEL_COUNT_NOT_ZERO",
    )
    _require(
        clone_manifest.get("census_self_sha256") == census["self_sha256"],
        "CLONE_CENSUS_SELF_BINDING_DRIFT",
    )
    _validate_self_hash(clone_manifest, "self_sha256", "clone_manifest")
    bundle_files = clone_manifest.get("bundle_files")
    _require(isinstance(bundle_files, dict), "CLONE_BUNDLE_FILES_MISSING")
    for name, binding in bundle_files.items():
        _require(isinstance(binding, dict), f"BAD_CLONE_BINDING:{name}")
        relative = Path(str(binding.get("path", "")))
        _require(
            str(binding.get("sha256", "")) == _file_sha256(root / relative),
            f"CLONE_BUNDLE_FILE_DRIFT:{relative.as_posix()}",
        )

    merge_config = _load_json(root, UPSTREAM_MERGE_CONFIG)
    merge_bindings = merge_config.get("output_sha256")
    _require(isinstance(merge_bindings, dict), "MERGE_OUTPUT_BINDINGS_MISSING")
    _require(
        merge_bindings.get(UPSTREAM_MERGE_TABLE.as_posix())
        == _file_sha256(root / UPSTREAM_MERGE_TABLE),
        "MERGE_RULE_TABLE_BINDING_DRIFT",
    )
    merge_rows = _csv_rows(root, UPSTREAM_MERGE_TABLE)
    _require(len(merge_rows) == 10, "MERGE_RULE_ROW_COUNT_DRIFT")
    by_rule = {row.get("rule", ""): row for row in merge_rows}
    _require(set(by_rule) == {f"M{i}" for i in range(10)}, "MERGE_RULE_SET_DRIFT")
    for index in range(7):
        row = by_rule[f"M{index}"]
        _require(
            row.get("execution_status") == "EXECUTED_PRODUCTION_E4",
            f"MERGE_RULE_NOT_EXECUTED:M{index}",
        )
        _require(row.get("hard_gate_pass") == "true", f"MERGE_HARD_GATE:M{index}")
        _require(
            row.get("performance_gain_claimed") == "false",
            f"MERGE_GAIN_CLAIM_DRIFT:M{index}",
        )
        _require(
            _strict_float(
                float(row.get("mean_completion_delta_vs_m0_seconds", "nan")),
                f"M{index} mean delta",
            )
            == 0.0,
            f"MERGE_NONZERO_MEAN_DELTA:M{index}",
        )
        _require(
            _strict_float(
                float(row.get("p95_completion_delta_vs_m0_seconds", "nan")),
                f"M{index} p95 delta",
            )
            == 0.0,
            f"MERGE_NONZERO_P95_DELTA:M{index}",
        )
    for index in range(7, 10):
        row = by_rule[f"M{index}"]
        _require(
            row.get("execution_status") == "REJECTED_FAIL_CLOSED",
            f"MERGE_NEGATIVE_RULE_NOT_REJECTED:M{index}",
        )
        _require(
            row.get("online_allowed") == "false",
            f"MERGE_NEGATIVE_RULE_ALLOWED:M{index}",
        )

    registry = _load_json(root, BASELINE_REGISTRY)
    _require(
        registry.get("schema") == "czr005.g4irsf14.baseline_registry.v1",
        "BASELINE_REGISTRY_SCHEMA_DRIFT",
    )
    _require(
        registry.get("status") == "PASS_BASELINE_FROZEN",
        "BASELINE_REGISTRY_NOT_FROZEN",
    )
    _validate_self_hash(registry, "registry_sha256", "baseline_registry")
    _validate_registry_files(root, registry)
    registry_protected = registry.get("protected_inputs")
    _require(
        isinstance(registry_protected, dict)
        and registry_protected.get("map", {}).get("raw_sha256")
        == MAP_RAW_SHA256
        and registry_protected.get("task", {}).get("raw_sha256")
        == TASK_RAW_SHA256,
        "BASELINE_PROTECTED_INPUT_DRIFT",
    )

    f2 = _load_json(root, F2_FROZEN_CONTROL)
    _require(f2.get("status") == "PASS_FROZEN_CONTROL", "F2_CONTROL_NOT_FROZEN")
    _validate_self_hash(f2, "control_sha256", "f2_frozen_control")
    metrics = f2.get("metrics")
    _require(isinstance(metrics, dict), "F2_METRICS_MISSING")
    comparators = f2.get("comparators")
    _require(isinstance(comparators, dict), "F2_COMPARATORS_MISSING")
    f2_mean = _strict_float(
        metrics.get("original_entry_mean_minutes"), "F2 mean"
    )
    v2_mean = _strict_float(
        comparators.get("frozen_v2_safe_original_entry_mean_minutes"),
        "v2 mean",
    )
    gap_seconds = _strict_float(
        comparators.get("delta_vs_v2_safe_seconds_per_bag"),
        "F2 v2 delta",
    )
    _require(
        abs((f2_mean - v2_mean) * 60.0 - gap_seconds) < 1e-10,
        "F2_DENOMINATOR_ARITHMETIC_DRIFT",
    )
    _require(
        f2_mean == PINNED_F2_MEAN_MINUTES
        and v2_mean == PINNED_V2_SAFE_MEAN_MINUTES
        and gap_seconds == PINNED_F2_GAP_SECONDS_PER_BAG,
        "FROZEN_COMPARATOR_METRIC_DRIFT",
    )
    _require(gap_seconds > 0.0, "F2_ALREADY_BEATS_V2_UNEXPECTEDLY")

    fault_control = _load_json(root, FAULT_FROZEN_CONTROL)
    _require(
        fault_control.get("status") == "FAULT_DISCRIMINATING_PASS_FROZEN",
        "FAULT_CONTROL_NOT_FROZEN",
    )
    _validate_self_hash(
        fault_control, "control_sha256", "fault_frozen_control"
    )
    g13_final = _load_json(root, G13_FINAL_BUNDLE)
    _require(g13_final.get("status") == "COMPLETE", "G13_FINAL_NOT_COMPLETE")
    _require(
        g13_final.get("decision_status") == "HISTORICAL_ONLY_PASS",
        "G13_FINAL_DECISION_DRIFT",
    )
    _require(g13_final.get("strict_win_vs_v2_safe") is False, "G13_V2_WIN_DRIFT")
    _require(
        g13_final.get("v3_contribution_proven") is False,
        "G13_LEARNING_CONTRIBUTION_DRIFT",
    )
    _validate_self_hash(g13_final, "bundle_sha256", "g13_final_bundle")
    g13_fault = _load_json(root, G13_FAULT_BUNDLE)
    _require(
        g13_fault.get("status") == "FAULT_DISCRIMINATING_PASS",
        "G13_FAULT_STATUS_DRIFT",
    )
    _validate_self_hash(g13_fault, "self_sha256", "g13_fault_bundle")

    important_inputs = (
        UPSTREAM_CENSUS,
        UPSTREAM_CLONE_MANIFEST,
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
    bindings = {
        relative.as_posix(): _bound_file(root, relative)
        for relative in important_inputs
    }
    identity = {
        "schema": "czr005.g4irsf14.fail_closed_input_identity.v1",
        "bindings": bindings,
        "census_self_sha256": census["self_sha256"],
        "clone_manifest_self_sha256": clone_manifest["self_sha256"],
        "causal_label_count": 0,
        "formal_horizon_completion_count": 0,
        "pibt_prefilter_candidate_count": pibt_prefilter,
        "pibt_applicable_ready_slice_boundary_count": pibt_applicable,
        "merge_rule_executed_count": 7,
        "merge_rule_improved_count": 0,
        "f2_raw_entry_mean_minutes": f2_mean,
        "v2_safe_raw_entry_mean_minutes": v2_mean,
        "remaining_gap_seconds_per_bag": gap_seconds,
    }
    identity["identity_sha256"] = _canonical_sha256(identity)
    return {
        "identity": identity,
        "census": census,
        "clone_manifest": clone_manifest,
        "merge_rows": merge_rows,
        "registry": registry,
        "f2": f2,
        "fault_control": fault_control,
        "g13_final": g13_final,
    }


def _gate_base(
    *,
    schema: str,
    stage: str,
    status: str,
    generation_id: str,
    identity: Mapping[str, Any],
    blockers: Sequence[str],
) -> dict[str, Any]:
    return {
        "schema": schema,
        "stage": stage,
        "status": status,
        "generated_by": "scripts/eval/g4irsf14_fail_closed_completion.py",
        "generation_id": generation_id,
        "input_identity_sha256": identity["identity_sha256"],
        "upstream_census_self_sha256": identity["census_self_sha256"],
        "formal_pass_claimed": False,
        "causal_label_count": 0,
        "blockers": list(blockers),
    }


def _payload_binding(path: Path, payload: bytes) -> dict[str, Any]:
    return {
        "path": path.as_posix(),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "byte_count": len(payload),
    }


def _build_payloads(root: Path, context: Mapping[str, Any]) -> dict[Path, bytes]:
    identity = context["identity"]
    generation_id = _canonical_sha256(
        {
            "schema": "czr005.g4irsf14.fail_closed_generation.v1",
            "input_identity_sha256": identity["identity_sha256"],
            "stage_status": STAGE_STATUS,
            "output_paths": [path.as_posix() for path in OUTPUT_PATHS],
        }
    )
    common_csv = {
        "generation_id": generation_id,
        "input_identity_sha256": identity["identity_sha256"],
    }
    payloads: dict[Path, bytes] = {}

    rule_rows_unhashed: list[dict[str, str]] = []
    for rule_id in (
        *(f"R-M{index}" for index in range(8)),
        *(f"R-S{index}" for index in range(6)),
    ):
        equivalent = {
            "R-M0": "M0",
            "R-M1": "M1",
            "R-M2": "M2",
        }.get(rule_id, "")
        diagnostic_only = rule_id in {"R-M7", "R-S5"}
        rule_rows_unhashed.append(
            {
                **common_csv,
                "stage": "F",
                "rule_id": rule_id,
                "rule_family": (
                    "MERGE_ORDER" if rule_id.startswith("R-M") else "SOURCE_ORDER"
                ),
                "status": STAGE_STATUS["F"],
                "execution_status": "NOT_RUN",
                "planned_rule_count": "14",
                "eligible_rule_count": "0",
                "stage_d_mechanism_rule_count": "7",
                "causal_label_count": "0",
                "formal_causal_eligible": "false",
                "diagnostic_only": str(diagnostic_only).lower(),
                "runtime_deployable_by_design": str(
                    not diagnostic_only
                ).lower(),
                "stage_d_reference_scope": (
                    "SEPARATE_144_SEGMENT_MECHANISM_EVIDENCE_ONLY"
                ),
                "stage_d_equivalent_rule_id": equivalent,
                "observed_mean_delta_vs_m0_seconds": (
                    "0" if equivalent else ""
                ),
                "observed_p95_delta_vs_m0_seconds": (
                    "0" if equivalent else ""
                ),
                "causal_upper_bound_seconds_per_bag": "",
                "metric_status": "NOT_MEASURED",
                "reason": "NO_FORMAL_STAGE_E_MATCHED_INTERVENTION_CAMPAIGN",
            }
        )
    rule_rows = _row_hashes(rule_rows_unhashed)
    rule_fields = tuple(rule_rows[0])
    payloads[RULE_TABLE] = _csv_bytes(rule_fields, rule_rows)
    payloads[RULE_REPORT] = _markdown(
        [
            "# G4IRSF14 规则上界门（Stage F）",
            "",
            f"- 状态：`{STAGE_STATUS['F']}`。",
            "- Stage D 在 144 段机制样本上执行了 M0–M6；安全门通过，但"
            " mean/p95 相对 M0 的变化均为 0。",
            "- Stage F 预注册的 14 个规则（R-M0..R-M7、R-S0..R-S5）"
            "均未运行，formal eligible count = 0。Stage D 与 Stage F"
            "不是完整一一同义；仅 R-M0/R-M1/R-M2 有明确参考映射。",
            "- Stage E 的正式 matched H_bag/H_system 标签数为 0，因此不能"
            "把 144 段规则同值外推成原始 1x 上界，也不能声称规则有收益。",
            "- Stage D 的 M7–M9 已按设计拒绝在线执行；这不能替代 Stage F"
            " 的 R-M7 评估，本阶段没有运行新的候选。",
            "",
            f"生成绑定：`{generation_id}`。",
        ]
    )
    rule_gate = _gate_base(
        schema="czr005.g4irsf14.rule_upper_bound_gate.v1",
        stage="F",
        status=STAGE_STATUS["F"],
        generation_id=generation_id,
        identity=identity,
        blockers=(
            "ZERO_COMPLETE_H_BAG_H_SYSTEM_CAUSAL_LABELS",
            "ORIGINAL_TASK_MINIMUM_2000_MATCHED_INTERVENTIONS_NOT_ESTABLISHED",
        ),
    )
    rule_gate.update(
        {
            "upper_bound_measured": False,
            "causal_upper_bound_seconds_per_bag": None,
            "planned_rule_count": 14,
            "eligible_rule_count": 0,
            "result_label_inventory": [
                "RULE_NO_GAIN",
                "RULE_LOCAL_GAIN_ONLY",
                "RULE_FULL_GAIN_NOT_V2",
                "RULE_STRICT_V2_WIN",
            ],
            "selected_result_label": None,
            "diagnostic_only_rule_ids": ["R-M7", "R-S5"],
            "successive_halving_tiers": [
                "REAL_MAP_MOTIF",
                "144",
                "512",
                "2048",
                "8192",
                "FULL_TOP_LE_3",
            ],
            "elimination_criteria": [
                "NON_DRAIN",
                "HARD_SAFETY_FAIL",
                "MEAN_LOSS_GT_0_5_SECONDS_PER_BAG_AT_MATCHED_TIER",
                "P95_LOSS_GT_2_SECONDS",
                "P99_LOSS_GT_4_SECONDS",
                "SOURCE_WAIT_GAIN_OFFSET_BY_LARGER_NETWORK_LOSS",
                "FAIRNESS_OR_STARVATION",
                "HIDDEN_FUTURE_READ",
                "NO_EFFECTIVE_ACTION",
            ],
            "stage_d_mechanism_rule_count": 7,
            "stage_d_observation": {
                "executed_online_rule_count": 7,
                "observed_improved_rule_count": 0,
                "scope": "144_SEGMENT_MECHANISM_ONLY",
            },
            "output_bindings": {
                RULE_REPORT.as_posix(): _payload_binding(
                    RULE_REPORT, payloads[RULE_REPORT]
                ),
                RULE_TABLE.as_posix(): _payload_binding(
                    RULE_TABLE, payloads[RULE_TABLE]
                ),
            },
        }
    )
    payloads[RULE_GATE] = _json_bytes(_self_bound(rule_gate))

    reason_rows = _row_hashes(
        [
            {
                **common_csv,
                "stage": "G",
                "status": STAGE_STATUS["G"],
                "reason_ordinal": str(index),
                "primary_reason": reason,
                "failure_count": "0",
                "denominator_count": "0",
                "rate": "",
                "measurement_status": "NOT_RUN",
                "taxonomy_static_inventory_complete": "true",
                "taxonomy_runtime_complete": "false",
            }
            for index, reason in enumerate(PIBT_CANONICAL_REASONS, start=1)
        ]
    )
    payloads[PIBT_REASONS_TABLE] = _csv_bytes(
        tuple(reason_rows[0]), reason_rows
    )
    pibt_rows = _row_hashes(
        [
            {
                **common_csv,
                "stage": "G",
                "candidate_id": "P2_READY_SLICE_REDESIGN",
                "status": STAGE_STATUS["G"],
                "execution_status": "NOT_RUN",
                "attempt_count": "0",
                "prefilter_candidate_count": "1337",
                "applicable_ready_slice_boundary_count": "0",
                "prepare_count": "0",
                "validate_count": "0",
                "commit_count": "0",
                "rollback_count": "0",
                "raw_commit_numerator": "0",
                "raw_attempt_denominator": "0",
                "raw_commit_per_attempt_rate": "",
                "raw_commit_per_attempt_status": "NOT_MEASURED",
                "feasible_commit_numerator": "0",
                "feasible_attempt_denominator": "0",
                "feasible_commit_per_feasible_attempt_rate": "",
                "feasible_commit_per_feasible_attempt_status": "NOT_MEASURED",
                "resolved_contention_numerator": "0",
                "applicable_contention_denominator": "0",
                "resolved_per_applicable_rate": "",
                "resolved_per_applicable_status": "NOT_MEASURED",
                "system_benefit_numerator_seconds": "",
                "committed_transaction_denominator": "0",
                "system_benefit_per_committed_transaction": "",
                "system_benefit_per_committed_transaction_status": (
                    "NOT_MEASURED"
                ),
                "metric_status": "NOT_MEASURED",
            }
        ]
    )
    payloads[PIBT_COMMIT_TABLE] = _csv_bytes(tuple(pibt_rows[0]), pibt_rows)
    payloads[PIBT_REPORT] = _markdown(
        [
            "# G4IRSF14 PIBT blocker taxonomy（Stage G）",
            "",
            f"- 状态：`{STAGE_STATUS['G']}`。",
            "- 原始 1x 被动计数：prefilter candidate = 1,337；真正"
            " applicable ready-slice boundary = 0；G4IRSF14 attempt = 0。",
            "- 17 个 canonical primary reasons 已固化为完整枚举，但本轮"
            "没有可适用边界，所以每项 count=0、denominator=0，rate 留空。",
            "- 这不是“17 类故障均未发生”的证据，也不是 runtime taxonomy"
            " complete；只是零支持下的 fail-closed 量测结果。",
            "- raw commit/attempt、feasible commit/feasible attempt、"
            "resolved/applicable、system benefit/committed 四套计划口径"
            "均已保留；因 attempt=0、applicable=0 且未执行，rate 留空并标记"
            " `NOT_MEASURED`，绝不把零分母写成 0% 或 100%。",
            "",
            "PIBT 仅负责 blocker 可局部移动且需要多袋一步原子动作的异常"
            "协调；普通跨上游 merge request 仍由 destination merge arbiter"
            "处理。",
            "",
            f"生成绑定：`{generation_id}`。",
        ]
    )

    offline_fields = (
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

    def offline_rows(
        task: str,
        models: Sequence[tuple[str, str]],
    ) -> list[dict[str, str]]:
        rows = []
        for candidate_id, family in models:
            reason = "ZERO_MATCHED_CAUSAL_LABELS"
            if candidate_id == "B5":
                reason = (
                    "CAUSAL_READY_SET_ROWS_0_BELOW_REQUIRED_20000"
                )
            rows.append(
                {
                    **common_csv,
                    "stage": "H",
                    "task": task,
                    "candidate_id": candidate_id,
                    "candidate_family": family,
                    "status": STAGE_STATUS["H"],
                    "execution_status": "NOT_RUN",
                    "causal_training_row_count": "0",
                    "causal_validation_row_count": "0",
                    "causal_audit_row_count": "0",
                    "metric_name": "",
                    "metric_value": "",
                    "metric_status": "NOT_MEASURED",
                    "model_artifact": "",
                    "reason": reason,
                }
            )
        return _row_hashes(rows)

    route_rows = offline_rows("ROUTE_RESIDUAL", ROUTE_MODELS)
    merge_rows = offline_rows("MERGE_ORDER_RANKER", MERGE_MODELS)
    admission_rows = offline_rows(
        "ADMISSION_HOLD_RELEASE", ADMISSION_MODELS
    )
    payloads[ROUTE_OFFLINE_TABLE] = _csv_bytes(offline_fields, route_rows)
    payloads[MERGE_OFFLINE_TABLE] = _csv_bytes(offline_fields, merge_rows)
    payloads[ADMISSION_OFFLINE_TABLE] = _csv_bytes(
        offline_fields, admission_rows
    )
    payloads[LEARNING_DATA_REPORT] = _markdown(
        [
            "# G4IRSF14 学习数据报告（Stage H）",
            "",
            f"- 状态：`{STAGE_STATUS['H']}`。",
            "- exact clone/no-op fidelity 已验证，但 completed matched causal"
            " labels = 0；screening opportunity 不能代替训练标签。",
            "- Route / Merge / Admission 的 train、validation、audit 都为 0"
            " 行。没有执行 split，没有产生任何模型文件。",
            "- B5 需要至少 20,000 个 causal ready-set rows；当前为 0，"
            "明确 `INSUFFICIENT_DATA_NOT_RUN`。",
            "- 未计算 accuracy、precision、ECE、harmful rate 或 recovered"
            " mean；表中相关字段留空，而不是伪造 0。",
            "",
            f"生成绑定：`{generation_id}`。",
        ]
    )
    payloads[OFFLINE_REPORT] = _markdown(
        [
            "# G4IRSF14 离线训练报告（Stage H/I）",
            "",
            "- 训练执行：`NOT_RUN`。",
            f"- 数据状态：`{STAGE_STATUS['H']}`。",
            f"- 离线门：`{STAGE_STATUS['I']}`。",
            "- 原因：没有 matched clone causal target，故所有模型族均禁止"
            "拟合、校准、选择和导出。",
            "- fallback 仍为 exact F2 / best-rule；这不是新学习策略。",
            "",
            f"生成绑定：`{generation_id}`。",
        ]
    )
    learning_gate = _gate_base(
        schema="czr005.g4irsf14.learning_preclosed_loop_gate.v1",
        stage="I",
        status=STAGE_STATUS["I"],
        generation_id=generation_id,
        identity=identity,
        blockers=(
            "ZERO_MATCHED_CAUSAL_TARGET_SUPPORT",
            "MINIMUM_2000_COMPLETE_INTERVENTIONS_NOT_MET",
            "NO_TRAIN_VALIDATION_AUDIT_SPLIT",
            "NO_ELIGIBLE_MODEL_ARTIFACT",
        ),
    )
    learning_gate.update(
        {
            "training_status": STAGE_STATUS["H"],
            "runtime_eligible": False,
            "selected_candidate": None,
            "model_artifacts_generated": [],
            "planned_negative_cohorts": [
                {
                    "name": name,
                    "evaluation_status": "NOT_EVALUATED",
                }
                for name in PLANNED_NEGATIVE_COHORTS
            ],
            "planned_split_dimensions": [
                {
                    "name": name,
                    "evaluation_status": "NOT_EVALUATED",
                }
                for name in PLANNED_SPLIT_DIMENSIONS
            ],
            "clone_state_interventions_cross_split_allowed": False,
            "allowed_generalization_controls": [
                "SHARED_MODEL",
                "MERGE_SPECIFIC_BIAS",
                "LOCAL_CONTROLLER_CALIBRATION",
            ],
            "required_generalization_ablations": [
                {
                    "name": name,
                    "evaluation_status": "NOT_EVALUATED",
                }
                for name in REQUIRED_GENERALIZATION_ABLATIONS
            ],
            "data_gate": {
                "clone_fidelity_exact": True,
                "counterfactual_target_support_positive": False,
                "complete_intervention_count": 0,
                "minimum_complete_intervention_count": MIN_FORMAL_INTERVENTIONS,
                "train_validation_audit_overlap_zero": None,
                "candidate_request_completeness": None,
                "selected_action_grant_coverage": None,
                "no_future_runtime_leakage": None,
            },
            "offline_metrics": {
                "route": None,
                "merge": None,
                "admission": None,
            },
            "threshold_inventory": {
                "data": [
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
                    {
                        "requirement": "train_validation_audit_overlap",
                        "threshold": "0",
                        "observed": None,
                        "evaluation_status": "NOT_EVALUATED",
                    },
                    {
                        "requirement": "candidate_request_completeness",
                        "threshold": "100%",
                        "observed": None,
                        "evaluation_status": "NOT_EVALUATED",
                    },
                    {
                        "requirement": "selected_action_grant_coverage",
                        "threshold": "100%",
                        "observed": None,
                        "evaluation_status": "NOT_EVALUATED",
                    },
                    {
                        "requirement": "no_future_runtime_leakage",
                        "threshold": "true",
                        "observed": None,
                        "evaluation_status": "NOT_EVALUATED",
                    },
                ],
                "route": [
                    {
                        "requirement": requirement,
                        "threshold": threshold,
                        "observed": None,
                        "evaluation_status": "NOT_EVALUATED",
                    }
                    for requirement, threshold in (
                        ("pairwise_accuracy", ">=0.70"),
                        ("top1_accuracy", ">=0.75"),
                        ("high_confidence_harmful", "<=0.01"),
                        ("ece", "<=0.10"),
                        ("f2_preserved_outside_target", ">=0.98"),
                        ("positive_causal_precision", ">=0.80"),
                    )
                ],
                "merge": [
                    {
                        "requirement": requirement,
                        "threshold": threshold,
                        "observed": None,
                        "evaluation_status": "NOT_EVALUATED",
                    }
                    for requirement, threshold in (
                        ("pairwise_grant_order_accuracy", ">=0.75"),
                        ("top1_winner_accuracy", ">=0.75"),
                        ("high_confidence_harmful_order", "<=0.01"),
                        ("starvation_fairness_violation", "=0"),
                        ("causal_positive_precision", ">=0.80"),
                        ("estimated_recovered_mean_seconds_per_bag", ">=1.50"),
                    )
                ],
                "admission": [
                    {
                        "requirement": requirement,
                        "threshold": threshold,
                        "observed": None,
                        "evaluation_status": "NOT_EVALUATED",
                    }
                    for requirement, threshold in (
                        ("beneficial_hold_precision", ">=0.80"),
                        ("harmful_hold_rate", "<=0.01"),
                        ("outside_target_activation", "<=0.02"),
                        (
                            "source_wait_offset_by_larger_network_decrease",
                            "true",
                        ),
                    )
                ],
                "risk_abstention": [
                    {
                        "requirement": "causal_support_positive",
                        "threshold": "true",
                        "observed": False,
                        "evaluation_status": "FAIL_CLOSED",
                    },
                    *[
                        {
                            "requirement": requirement,
                            "threshold": "true",
                            "observed": None,
                            "evaluation_status": "NOT_EVALUATED",
                        }
                        for requirement in (
                            "confidence_gate",
                            "state_in_distribution",
                            "grant_request_completeness",
                            "fault_generation_current",
                            "exact_f2_or_best_rule_fallback",
                        )
                    ],
                ],
            },
            "output_bindings": {
                path.as_posix(): _payload_binding(path, payloads[path])
                for path in (
                    LEARNING_DATA_REPORT,
                    OFFLINE_REPORT,
                    ROUTE_OFFLINE_TABLE,
                    MERGE_OFFLINE_TABLE,
                    ADMISSION_OFFLINE_TABLE,
                )
            },
        }
    )
    payloads[LEARNING_GATE] = _json_bytes(_self_bound(learning_gate))

    closed_candidates = (
        ("J0", "F2 immediate frozen reference"),
        ("J1", "best batched no-learning"),
        ("J2", "best merge-grant rule"),
        ("J3", "learned merge ranker"),
        ("J4", "learned merge plus route residual"),
        ("J5", "learned merge plus selective admission"),
        ("J6", "complete learned stack plus P2 plus shield"),
    )
    closed_scales = ("motifs", "144", "512", "2048", "8192", "43603")
    closed_rows = _row_hashes(
        [
            {
                **common_csv,
                "stage": "J",
                "candidate_id": candidate_id,
                "candidate_description": description,
                "status": (
                    "REFERENCE_ONLY_NOT_RERUN"
                    if candidate_id == "J0"
                    else STAGE_STATUS["J"]
                ),
                "execution_status": "NOT_RUN",
                "scale": scale,
                "evaluation_status": "NOT_EVALUATED",
                "repeat_count": "0",
                "original_entry_mean_minutes": "",
                "delta_vs_f2_seconds_per_bag": "",
                "delta_vs_v2_safe_seconds_per_bag": "",
                "hard_gate_status": "",
                "performance_gate_status": "",
                "mechanism_gate_status": "",
                "learning_contribution_status": "",
                "tail_gate_status": "",
                "reason": (
                    "FROZEN_REFERENCE_NOT_RERUN"
                    if candidate_id == "J0"
                    else (
                    "F_RULE_UPPER_BOUND_GATE_NOT_RUN"
                    if candidate_id in {"J1", "J2"}
                    else "I_LEARNING_PRECLOSED_LOOP_GATE_FAIL_CLOSED"
                    )
                ),
            }
            for candidate_id, description in closed_candidates
            for scale in closed_scales
        ]
    )
    payloads[CLOSED_LOOP_TABLE] = _csv_bytes(
        tuple(closed_rows[0]), closed_rows
    )
    payloads[CLOSED_LOOP_REPORT] = _markdown(
        [
            "# G4IRSF14 闭环逐级验证（Stage J）",
            "",
            f"- 状态：`{STAGE_STATUS['J']}`。",
            "- J0–J6 × motifs/144/512/2048/8192/43,603 共 42 个"
            "计划单元均未运行；J0 只是未重跑的 reference。",
            "- 离线门 FAIL_CLOSED，因此 motifs → 144 → 512 → 2048 →"
            " 8192 → full 的任何一级都不得启动。",
            "- 没有候选、没有 repeat、没有性能或学习贡献指标。",
            "",
            f"生成绑定：`{generation_id}`。",
        ]
    )
    closed_gate = _gate_base(
        schema="czr005.g4irsf14.closed_loop_gate.v1",
        stage="J",
        status=STAGE_STATUS["J"],
        generation_id=generation_id,
        identity=identity,
        blockers=(
            "RULE_UPPER_BOUND_GATE_NOT_RUN",
            "LEARNING_PRECLOSED_LOOP_GATE_FAIL_CLOSED",
        ),
    )
    closed_gate.update(
        {
            "candidate_execution_count": 0,
            "full_scale_execution_count": 0,
            "promotion_allowed": False,
            "evaluation_inventory": {
                "hard": [
                    {
                        "requirement": requirement,
                        "threshold": threshold,
                        "observed": None,
                        "evaluation_status": "NOT_EVALUATED",
                    }
                    for requirement, threshold in (
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
                ],
                "performance": [
                    {
                        "requirement": requirement,
                        "threshold": threshold,
                        "observed": None,
                        "evaluation_status": "NOT_EVALUATED",
                    }
                    for requirement, threshold in (
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
                ],
                "mechanism": [
                    {
                        "requirement": requirement,
                        "threshold": "measured",
                        "observed": None,
                        "evaluation_status": "NOT_EVALUATED",
                    }
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
                ],
                "learning": [
                    {
                        "requirement": "same_framework_learned_vs_best_rule",
                        "threshold": "learned_strictly_better",
                        "observed": None,
                        "evaluation_status": "NOT_EVALUATED",
                    }
                ],
                "tail": [
                    {
                        "requirement": metric,
                        "threshold": "non_regression",
                        "observed": None,
                        "evaluation_status": "NOT_EVALUATED",
                    }
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
                ],
            },
            "output_bindings": {
                CLOSED_LOOP_REPORT.as_posix(): _payload_binding(
                    CLOSED_LOOP_REPORT, payloads[CLOSED_LOOP_REPORT]
                ),
                CLOSED_LOOP_TABLE.as_posix(): _payload_binding(
                    CLOSED_LOOP_TABLE, payloads[CLOSED_LOOP_TABLE]
                ),
                LEARNING_GATE.as_posix(): _payload_binding(
                    LEARNING_GATE, payloads[LEARNING_GATE]
                ),
            },
        }
    )
    payloads[CLOSED_LOOP_GATE] = _json_bytes(_self_bound(closed_gate))

    fault_rows = _row_hashes(
        [
            {
                **common_csv,
                "stage": "K",
                "case_group": group,
                "status": STAGE_STATUS["K"],
                "execution_status": "NOT_RUN",
                "candidate_id": "",
                "repeat_count": "0",
                "unsafe_entry_count": "",
                "hard_failure_count": "",
                "fault_policy_benefit": "",
                "unsafe_entry_zero_status": "NOT_EVALUATED",
                "fault_generation_monotone_status": "NOT_EVALUATED",
                "stale_grant_rejected_status": "NOT_EVALUATED",
                "repair_reentry_once_status": "NOT_EVALUATED",
                "credit_grant_cleanup_status": "NOT_EVALUATED",
                "p2_transaction_atomic_status": "NOT_EVALUATED",
                "metric_status": "NOT_MEASURED",
                "reference_scope": "G4IRSF13_FROZEN_ONLY",
                "reason": "NO_STAGE14_CLOSED_LOOP_CANDIDATE",
            }
            for group in (
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
        ]
    )
    payloads[FAULT_TABLE] = _csv_bytes(tuple(fault_rows[0]), fault_rows)
    payloads[FAULT_REPORT] = _markdown(
        [
            "# G4IRSF14 故障回归（Stage K）",
            "",
            f"- 状态：`{STAGE_STATUS['K']}`。",
            "- G4IRSF13 的 DDI/BTI local control 仅作为冻结参考；本轮没有"
            "把其历史结果重命名为 G4IRSF14 新候选回归。",
            "- 因 J 阶段没有合格闭环候选，计划中的 G0/G1/G2/G3、G5"
            " delayed、G6 dropped、G7 repair、informative multi-fault、"
            "grant issue→fault、prepare/commit→fault 与 same-timestamp"
            " fault 均未运行。",
            "- unsafe entry=0、fault generation monotone、stale grant"
            " reject、repair re-entry once、credit/grant cleanup 与 P2"
            " transaction atomic 六项保持门均为 `NOT_EVALUATED`。",
            "- 下一步必须在同一候选、同一暴露窗口和 generation 上比较"
            " shield on/off，验证 unsafe=0、complete、安全回退和主动收益。",
            "",
            f"生成绑定：`{generation_id}`。",
        ]
    )

    runtime_rows = _row_hashes(
        [
            {
                **common_csv,
                "stage": "L",
                "scope": "CPP_RUNTIME_PROFILE",
                "status": STAGE_STATUS["L"],
                "execution_status": "NOT_RUN",
                "profile_run_count": "0",
                "wall_seconds": "",
                "events_per_second": "",
                "peak_memory_bytes": "",
                "metric_status": "NOT_MEASURED",
                "optimization_change_count": "0",
                "reason": "ALGORITHM_AND_CAUSAL_GATES_NOT_CLOSED",
            }
        ]
    )
    payloads[RUNTIME_TABLE] = _csv_bytes(tuple(runtime_rows[0]), runtime_rows)
    payloads[RUNTIME_REPORT] = _markdown(
        [
            "# G4IRSF14 runtime profile（Stage L）",
            "",
            f"- 状态：`{STAGE_STATUS['L']}`。",
            "- 未运行 profiler，未修改 C++ 性能路径，也没有 wall-time、"
            "吞吐或内存指标。",
            "- 当前阻塞是 causal label / offline / closed-loop gate，代码"
            "运行更快不能证明 TTH 改善；过早优化还会改变待验证 binary。",
            "",
            f"生成绑定：`{generation_id}`。",
        ]
    )

    f2_mean = identity["f2_raw_entry_mean_minutes"]
    v2_mean = identity["v2_safe_raw_entry_mean_minutes"]
    gap = identity["remaining_gap_seconds_per_bag"]
    final_rows = _row_hashes(
        [
            {
                **common_csv,
                "stage": "M",
                "candidate_id": "V2_COMPARATOR",
                "candidate_role": "frozen v2-safe comparator",
                "evidence_scope": "INHERITED_FROZEN_REFERENCE",
                "status": "REFERENCE_ONLY",
                "execution_status": "NOT_RERUN_G4IRSF14",
                "original_entry_mean_minutes": str(v2_mean),
                "delta_vs_v2_safe_seconds_per_bag": "0.0",
                "strict_win_vs_v2_safe": "false",
                "learning_contribution_proven": "false",
                "fault_regression_pass": "",
                "promotion_status": "REFERENCE_NOT_CANDIDATE",
            },
            {
                **common_csv,
                "stage": "M",
                "candidate_id": "M0_F2",
                "candidate_role": "frozen G4IRSF13 F2 deployment control",
                "evidence_scope": "INHERITED_FROZEN_REFERENCE",
                "status": "HISTORICAL_ONLY_PASS_REFERENCE",
                "execution_status": "NOT_RERUN_G4IRSF14",
                "original_entry_mean_minutes": str(f2_mean),
                "delta_vs_v2_safe_seconds_per_bag": str(gap),
                "strict_win_vs_v2_safe": "false",
                "learning_contribution_proven": "false",
                "fault_regression_pass": "",
                "promotion_status": "KEEP_FROZEN_CONTROL",
            },
            {
                **common_csv,
                "stage": "M",
                "candidate_id": "M1_RULE",
                "candidate_role": "best eligible Stage F rule",
                "evidence_scope": "NO_EXECUTION",
                "status": "NOT_RUN",
                "execution_status": "NOT_RUN",
                "original_entry_mean_minutes": "",
                "delta_vs_v2_safe_seconds_per_bag": "",
                "strict_win_vs_v2_safe": "",
                "learning_contribution_proven": "",
                "fault_regression_pass": "",
                "promotion_status": "PARTIAL_WITH_EXPLICIT_BLOCKER",
            },
            {
                **common_csv,
                "stage": "M",
                "candidate_id": "M2_LEARNED_MERGE",
                "candidate_role": "learned merge ranker",
                "evidence_scope": "NO_EXECUTION",
                "status": "NOT_RUN",
                "execution_status": "NOT_RUN",
                "original_entry_mean_minutes": "",
                "delta_vs_v2_safe_seconds_per_bag": "",
                "strict_win_vs_v2_safe": "",
                "learning_contribution_proven": "",
                "fault_regression_pass": "",
                "promotion_status": "PARTIAL_WITH_EXPLICIT_BLOCKER",
            },
            {
                **common_csv,
                "stage": "M",
                "candidate_id": "M3_LEARNED_STACK",
                "candidate_role": "learned merge route admission plus P2 shield",
                "evidence_scope": "NO_EXECUTION",
                "status": "NOT_RUN",
                "execution_status": "NOT_RUN",
                "original_entry_mean_minutes": "",
                "delta_vs_v2_safe_seconds_per_bag": "",
                "strict_win_vs_v2_safe": "",
                "learning_contribution_proven": "",
                "fault_regression_pass": "",
                "promotion_status": "PARTIAL_WITH_EXPLICIT_BLOCKER",
            },
        ]
    )
    payloads[FINAL_TABLE] = _csv_bytes(tuple(final_rows[0]), final_rows)
    payloads[FINAL_REPORT] = _markdown(
        [
            "# G4IRSF14 原始规模联合结论（Stage M）",
            "",
            f"- Stage 状态：`{STAGE_STATUS['M']}`。",
            "- 总结论：`PARTIAL_WITH_EXPLICIT_BLOCKER`。",
            "- 架构：同一时刻微阶段、destination-owned merge request/grant、"
            "exact clone/no-op 与被动机会计数已有机制测试和绑定证据；这只"
            "证明实现/审计能力，不证明原始 1x 性能改善。",
            "- 规则：Stage D 的 M0–M6 在 144 段机制运行中 mean/p95 均同值，"
            "没有规则改善证据。",
            "- 学习：0 个 matched causal labels，训练与闭环均未运行，"
            "所以没有学习改善。",
            f"- 冻结 F2 仍比 v2-safe 慢 `{gap:.12f}` 秒/袋。",
            "- 因果证据到达 exact clone/no-op fidelity、I1–I5 screening"
            " census；尚未到达 action-changing matched H_bag/H_system outcome。",
            "- 根阻塞是尚无正式 Stage E matched-intervention campaign。应先"
            "让预注册 exact-binary native campaign 可执行，并对已有 screening"
            "支持的 I1/I3/I4 取得完整 H_bag/H_system；同时恢复或重设计 I2"
            "主合流支持和 I5 applicable opportunity。只有完整 Stage E 门"
            "（至少 2,000 个 complete labels、H_system > 0）通过后才允许训练。",
            "",
            "## 第 25 节的 18 个问题",
            "",
            "1. **为什么只慢 1.1 秒仍不能胜？** promotion 要求严格快于"
            " v2-safe；1.134704 秒/袋仍是正差，而且学习、故障与证据门未闭合。",
            "2. **为什么差距大多不是走错路？** 冻结报告的分解把差异主要"
            "记录在局部等待/服务顺序，而不是路径长度；这是继承的描述性"
            "分解，不是 G4IRSF14 已证明的因果解释。",
            "3. **为什么 H1 优先级完全没变化？** 旧证据只显示 H0/Q0 与"
            " H1/Q1 的完整行为投影、路径、合流状态和结果同值；在没有"
            " action-changing matched states 时，不能进一步断言是哪一项"
            "特征或并列机制导致同值。",
            "4. **event seq 是否偷偷决定先后？** 设计与机制测试要求先收集"
            "同刻事件、再由本地仲裁，seq 只作确定性身份/兜底；但尚无新的"
            "原始 1x 闭环候选结果可把它声明为完整性能因果结论。",
            "5. **两阶段同刻处理是什么？** 第一阶段应用同一时间戳的"
            " release/arrival/fault/repair；第二阶段按受影响目的节点各做一次"
            "本地仲裁，不人工推进时间。",
            "6. **merge request/grant 像什么？** 像多个上游向目的合流口领"
            "同一服务槽的本地票据：request、grant、consume/revoke 都有生命周期。",
            "7. **为什么仍去中心化？** 目的节点只读自己的 pending set、"
            "service slot 和一跳状态，不读全机场任务或全局预约。",
            "8. **为什么每袋仍只决定下一边？** grant 只覆盖一个目的槽和"
            "一条有向边，reservation depth 固定为 1。",
            "9. **PIBT 负责什么？** 只处理 blocker 可局部移动、存在替代边"
            "且需要多袋一步原子协调的异常；不接管普通 merge queue 或多步规划。",
            "10. **为什么旧 V3 标签不够？** 它含 proxy/未配对结果，不能证明"
            "改变当前动作导致收益，也可能学到 task ID 或事后信息。",
            "11. **matched clone 如何给更可靠标签？** 从完全相同 checkpoint"
            "克隆，只改一个合法动作，分别运行到同一 H_bag/H_system horizon，"
            "用完整安全结果的差作为 causal label。",
            "12. **为什么 top 1% 是重点？** 冻结分解显示 top 1% 的 286 袋"
            "对全体均值贡献 +1.235566 秒/袋，剩余 99% 则贡献 -0.100862"
            " 秒/袋；这说明均值损失高度集中，不等于 top 1% 直接决定"
            " p95/p99。是否由合流、source wait 或 fault 造成必须靠 matched"
            " evidence 判定，仍须保留全体与负例。",
            "13. **为什么不能盲目模仿 v2-safe？** v2-safe 是性能比较器，"
            "不是逐状态因果 oracle；模仿动作可能复制偶然次序或未来信息。",
            "14. **为什么节点 19/22 不是坏节点？** 节点编号只是高流量上下文"
            "的一部分；好坏取决于 ready set、时间、来源/去向和干预结果，"
            "不能给节点永久负标签。",
            "15. **故障还需要什么？** 对最终候选做新鲜 matched DDI/BTI、"
            "grant issue→fault、prepare/commit→fault、same-timestamp fault"
            "和 informative multi-fault；同时验证 stale grant、repair 仅一次、"
            "cleanup 完整、P2 prepare/validate/commit/rollback 原子，以及"
            "unsafe=0 和 shield 的主动收益。",
            "16. **为什么现在不优化 C++？** 当前缺的是有效动作与因果证据；"
            "wall-time 加速不等于 TTH 改善，还会引入新 binary 身份。",
            "17. **什么时候可开始 1.1x？** 严格 v2-safe 胜利、独立学习贡献、"
            "fault regression、numeric demand calibration 和原任务生成审计"
            "全部通过后；当前 scale gate 锁定。",
            "18. **为什么仍只用原始真实 map？** 本阶段要隔离控制策略的因果"
            "作用；固定唯一 map2 与原始 28,506 袋可防止用合成拓扑或任务漂移"
            "制造假收益。",
            "",
            f"生成绑定：`{generation_id}`。",
        ]
    )

    final_bound_paths = (
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
    final_bundle = {
        "schema": "czr005.g4irsf14.final_candidate_bundle.v1",
        "stage": "M",
        "status": STAGE_STATUS["M"],
        "decision_status": "PARTIAL_WITH_EXPLICIT_BLOCKER",
        "deployment_action": "KEEP_G4IRSF13_F2_FROZEN_CONTROL",
        "generated_by": "scripts/eval/g4irsf14_fail_closed_completion.py",
        "generation_id": generation_id,
        "input_identity": identity,
        "stage_statuses": STAGE_STATUS,
        "selected_candidate_id": None,
        "candidate_selection_status": "NO_ELIGIBLE_G4IRSF14_CANDIDATE",
        "new_candidate_execution_count": 0,
        "formal_pass_claimed": False,
        "strict_win_vs_v2_safe": None,
        "strict_win_vs_v2_safe_evaluation_status": "NOT_EVALUATED",
        "strict_win_vs_v2_safe_gate_satisfied": False,
        "strict_win_vs_v2_safe_proven": False,
        "learning_contribution_proven": False,
        "learning_contribution_evaluation_status": "NOT_EVALUATED",
        "learning_contribution_gate_satisfied": False,
        "fault_regression_pass": None,
        "tail_gate_pass": None,
        "fault_regression_evaluation_status": "NOT_EVALUATED",
        "tail_gate_evaluation_status": "NOT_EVALUATED",
        "fault_regression_gate_satisfied": False,
        "fault_regression_proven": False,
        "tail_gate_satisfied": False,
        "tail_gate_proven": False,
        "scale_unlocked": False,
        "model_artifacts_generated": [],
        "performance": {
            "new_candidate_metrics": None,
            "f2_frozen_reference_mean_minutes": f2_mean,
            "v2_safe_frozen_reference_mean_minutes": v2_mean,
            "remaining_gap_seconds_per_bag": gap,
        },
        "inheritance_boundary": {
            "g4irsf13_f2_status": "HISTORICAL_ONLY_PASS",
            "g4irsf13_f2_is_deployment_control": True,
            "g4irsf14_may_inherit_historical_pass": False,
            "g4irsf14_inherited_promotion_status": "FORBIDDEN",
        },
        "phase_decisions": {
            "G4J": "CLOSED",
            "K": "UNKNOWN/CLOSED",
            "L": "NOT_RUN",
            "scale_execution_count": 0,
        },
        "improvement_statuses": {
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
        "causal_evidence": {
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
        "blocker": {
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
        "fault_regression_requirements": [
            {
                "requirement": requirement,
                "observed": None,
                "evaluation_status": "NOT_EVALUATED",
                "satisfied": False,
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
        "formal_hard_gate_inventory": [
            {
                "requirement": requirement,
                "threshold": threshold,
                "observed": None,
                "evaluation_status": "NOT_EVALUATED",
                "satisfied": False,
            }
            for requirement, threshold in (
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
            )
        ],
        "performance_gate_inventory": [
            {
                "requirement": requirement,
                "threshold": threshold,
                "observed": None,
                "evaluation_status": "NOT_EVALUATED",
                "satisfied": False,
            }
            for requirement, threshold in (
                ("strict_win_vs_v2_safe_mean_minutes", "<41.495306987809"),
                ("strong_pass_margin_seconds_per_bag", ">=0.25"),
                ("small_margin_pass", "strict_win_and_margin<0.25"),
                ("tail_gate", "pass"),
            )
        ],
        "mechanism_gate_inventory": [
            {
                "requirement": requirement,
                "threshold": "complete",
                "observed": None,
                "evaluation_status": "NOT_EVALUATED",
                "satisfied": False,
            }
            for requirement in (
                "source_network_grant_decomposition",
                "learning_ablation",
            )
        ],
        "repeat_requirement": {
            "required": 5,
            "actual": 0,
            "evaluation_status": "NOT_EVALUATED",
            "satisfied": False,
            "deterministic_repeats_are_independent_samples": False,
        },
        "hash_slice_inventory": {
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
        "output_bindings": {
            path.as_posix(): _payload_binding(path, payloads[path])
            for path in final_bound_paths
        },
    }
    payloads[FINAL_BUNDLE] = _json_bytes(_self_bound(final_bundle))

    scale_gate = _gate_base(
        schema="czr005.g4irsf14.scale_unlock_gate.v1",
        stage="M",
        status="LOCKED",
        generation_id=generation_id,
        identity=identity,
        blockers=(
            "STRICT_V2_SAFE_WIN_NOT_PROVEN",
            "LEARNING_CONTRIBUTION_NOT_PROVEN",
            "FAULT_REGRESSION_NOT_RUN",
            "NUMERIC_DEMAND_CALIBRATION_NOT_COMPLETE",
            "ORIGINAL_TASK_GENERATION_AUDIT_NOT_PROMOTED_FOR_SCALE",
        ),
    )
    scale_gate.update(
        {
            "all_five_gates_pass": False,
            "scale_execution_count": 0,
            "allowed_scales": [],
            "forbidden_current_scales": [
                "1.1x",
                "1.2x",
                "1.3x",
                "2x",
                "4x",
                "8x",
                "16x",
                "32x",
                "2x+",
            ],
            "conditions": {
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
            "output_bindings": {
                FINAL_REPORT.as_posix(): _payload_binding(
                    FINAL_REPORT, payloads[FINAL_REPORT]
                ),
                FINAL_TABLE.as_posix(): _payload_binding(
                    FINAL_TABLE, payloads[FINAL_TABLE]
                ),
                FINAL_BUNDLE.as_posix(): _payload_binding(
                    FINAL_BUNDLE, payloads[FINAL_BUNDLE]
                ),
            },
        }
    )
    payloads[SCALE_GATE] = _json_bytes(_self_bound(scale_gate))

    _require(
        set(payloads) == set(OUTPUT_PATHS) - {DOWNSTREAM_GATE},
        "PRECOMMIT_OUTPUT_INVENTORY_DRIFT",
    )
    downstream = {
        "schema": "czr005.g4irsf14.downstream_fail_closed_gate.v1",
        "status": "PARTIAL_WITH_EXPLICIT_BLOCKER",
        "generated_by": "scripts/eval/g4irsf14_fail_closed_completion.py",
        "generation_id": generation_id,
        "input_identity": identity,
        "stage_statuses": STAGE_STATUS,
        "formal_pass_claimed": False,
        "promotion_allowed": False,
        "model_artifacts_generated": [],
        "new_experiment_execution_count": 0,
        "causal_label_count": 0,
        "pibt_measurement": {
            "attempt_count": 0,
            "prefilter_candidate_count": 1_337,
            "applicable_ready_slice_boundary_count": 0,
            "canonical_reason_count": len(PIBT_CANONICAL_REASONS),
            "taxonomy_runtime_complete": False,
        },
        "not_run_is_not_pass": True,
        "single_blocker": {
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
        "fault_regression_requirements": [
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
        "output_bindings": {
            path.as_posix(): _payload_binding(path, payloads[path])
            for path in OUTPUT_PATHS
            if path != DOWNSTREAM_GATE
        },
    }
    payloads[DOWNSTREAM_GATE] = _json_bytes(_self_bound(downstream))
    _require(set(payloads) == set(OUTPUT_PATHS), "OUTPUT_INVENTORY_DRIFT")
    return payloads


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_publish(
    root: Path,
    payloads: Mapping[Path, bytes],
) -> None:
    resolved = {
        (root / relative).resolve(): bytes(payload)
        for relative, payload in payloads.items()
    }
    commit_path = (root / DOWNSTREAM_GATE).resolve()
    _require(commit_path in resolved, "COMMIT_MARKER_PAYLOAD_MISSING")
    _require(len(resolved) == len(payloads), "DUPLICATE_OUTPUT_TARGET")
    for target in resolved:
        _require(
            target == root or root in target.parents,
            f"OUTPUT_ESCAPES_ROOT:{target}",
        )

    staged: dict[Path, Path] = {}
    prior: dict[Path, bytes | None] = {}
    replaced: list[Path] = []
    try:
        for target, payload in resolved.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            prior[target] = target.read_bytes() if target.is_file() else None
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{target.name}.",
                suffix=".bundle.tmp",
                dir=str(target.parent),
            )
            temporary = Path(temporary_name)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            staged[target] = temporary
        order = sorted(
            (target for target in resolved if target != commit_path),
            key=str,
        )
        order.append(commit_path)
        for target in order:
            os.replace(staged[target], target)
            replaced.append(target)
    except BaseException as exc:
        rollback_failures: list[str] = []
        for target in reversed(replaced):
            try:
                previous = prior[target]
                if previous is None:
                    target.unlink(missing_ok=True)
                else:
                    _atomic_write_bytes(target, previous)
            except BaseException as rollback_exc:
                rollback_failures.append(
                    f"{target}:{type(rollback_exc).__name__}"
                )
        detail = (
            ""
            if not rollback_failures
            else ":ROLLBACK_FAILED:" + ",".join(rollback_failures)
        )
        raise FailClosedCompletionError(
            f"BUNDLE_PUBLICATION_FAILED:{type(exc).__name__}{detail}"
        ) from exc
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)


def _validate_published_bundle(
    root: Path,
    *,
    expected_identity: Mapping[str, Any],
) -> dict[str, Any]:
    gate = _load_json(root, DOWNSTREAM_GATE)
    _require(
        gate.get("schema")
        == "czr005.g4irsf14.downstream_fail_closed_gate.v1",
        "DOWNSTREAM_GATE_SCHEMA_DRIFT",
    )
    _require(
        gate.get("status") == "PARTIAL_WITH_EXPLICIT_BLOCKER",
        "DOWNSTREAM_GATE_STATUS_DRIFT",
    )
    _require(
        gate.get("input_identity") == expected_identity,
        "DOWNSTREAM_INPUT_IDENTITY_DRIFT",
    )
    expected_generation_id = _canonical_sha256(
        {
            "schema": "czr005.g4irsf14.fail_closed_generation.v1",
            "input_identity_sha256": expected_identity["identity_sha256"],
            "stage_status": STAGE_STATUS,
            "output_paths": [path.as_posix() for path in OUTPUT_PATHS],
        }
    )
    _require(
        gate.get("generation_id") == expected_generation_id,
        "DOWNSTREAM_GENERATION_ID_DRIFT",
    )
    _require(gate.get("stage_statuses") == STAGE_STATUS, "STAGE_STATUS_DRIFT")
    _validate_self_hash(gate, "self_sha256", "downstream_gate")
    bindings = gate.get("output_bindings")
    _require(isinstance(bindings, dict), "DOWNSTREAM_OUTPUT_BINDINGS_MISSING")
    expected_paths = {
        path.as_posix() for path in OUTPUT_PATHS if path != DOWNSTREAM_GATE
    }
    _require(set(bindings) == expected_paths, "DOWNSTREAM_OUTPUT_SET_DRIFT")
    for relative_text, binding in bindings.items():
        _require(isinstance(binding, dict), f"BAD_OUTPUT_BINDING:{relative_text}")
        relative = Path(relative_text)
        path = root / relative
        _require(
            binding.get("sha256") == _file_sha256(path),
            f"PUBLISHED_OUTPUT_HASH_DRIFT:{relative_text}",
        )
        _require(
            binding.get("byte_count") == path.stat().st_size,
            f"PUBLISHED_OUTPUT_SIZE_DRIFT:{relative_text}",
        )

    reasons = _csv_rows(root, PIBT_REASONS_TABLE)
    _require(len(reasons) == 17, "PIBT_REASON_ROW_COUNT_DRIFT")
    _require(
        tuple(row.get("primary_reason") for row in reasons)
        == PIBT_CANONICAL_REASONS,
        "PIBT_REASON_INVENTORY_DRIFT",
    )
    for row in reasons:
        _require(
            row.get("failure_count") == "0"
            and row.get("denominator_count") == "0"
            and row.get("rate") == ""
            and row.get("taxonomy_runtime_complete") == "false",
            f"PIBT_ZERO_DENOMINATOR_SEMANTICS_DRIFT:{row.get('primary_reason')}",
        )
        projection = dict(row)
        declared = projection.pop("row_sha256", "")
        _require(
            declared == _canonical_sha256(projection),
            f"PIBT_REASON_ROW_HASH_DRIFT:{row.get('primary_reason')}",
        )
    pibt = _csv_rows(root, PIBT_COMMIT_TABLE)
    _require(len(pibt) == 1, "PIBT_COMMIT_ROW_COUNT_DRIFT")
    _require(
        pibt[0].get("attempt_count") == "0"
        and pibt[0].get("prefilter_candidate_count") == "1337"
        and pibt[0].get("applicable_ready_slice_boundary_count") == "0",
        "PIBT_COUNT_SEMANTICS_DRIFT",
    )
    return gate


def _validate_deterministic_payloads(
    root: Path,
    expected_payloads: Mapping[Path, bytes],
) -> None:
    _require(
        set(expected_payloads) == set(OUTPUT_PATHS),
        "EXPECTED_OUTPUT_INVENTORY_DRIFT",
    )
    for relative in OUTPUT_PATHS:
        path = root / relative
        _require(path.is_file(), f"PUBLISHED_OUTPUT_MISSING:{relative.as_posix()}")
        _require(
            path.read_bytes() == expected_payloads[relative],
            f"PUBLISHED_OUTPUT_CONTENT_DRIFT:{relative.as_posix()}",
        )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate deterministic G4IRSF14 F-M fail-closed artifacts "
            "without running downstream experiments."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Repository/bundle root (default: generator repository root).",
    )
    parser.add_argument(
        "--check-inputs-only",
        action="store_true",
        help="Validate all upstream bindings without writing outputs.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate upstream evidence and an already published bundle.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    root = args.root.resolve()
    try:
        _require(root.is_dir(), f"ROOT_NOT_DIRECTORY:{root}")
        context = _validate_inputs(root)
        if args.check_inputs_only:
            print(
                json.dumps(
                    {
                        "status": "PASS_INPUTS_FAIL_CLOSED_READY",
                        "input_identity_sha256": context["identity"][
                            "identity_sha256"
                        ],
                        "causal_label_count": 0,
                        "pibt_prefilter_candidate_count": 1_337,
                        "pibt_applicable_ready_slice_boundary_count": 0,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0
        if args.validate_only:
            expected_payloads = _build_payloads(root, context)
            _validate_deterministic_payloads(root, expected_payloads)
            gate = _validate_published_bundle(
                root,
                expected_identity=context["identity"],
            )
            print(
                json.dumps(
                    {
                        "status": "PASS_FAIL_CLOSED_BUNDLE_VALIDATED",
                        "generation_id": gate["generation_id"],
                        "output_count": len(OUTPUT_PATHS),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0
        payloads = _build_payloads(root, context)
        _atomic_publish(root, payloads)
        gate = _validate_published_bundle(
            root,
            expected_identity=context["identity"],
        )
        print(
            json.dumps(
                {
                    "status": "PARTIAL_WITH_EXPLICIT_BLOCKER",
                    "generation_id": gate["generation_id"],
                    "output_count": len(payloads),
                    "commit_marker": DOWNSTREAM_GATE.as_posix(),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except (FailClosedCompletionError, OSError, ValueError) as exc:
        print(f"FAIL_CLOSED:{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
