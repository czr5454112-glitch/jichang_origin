#!/usr/bin/env python3
"""Independent fail-closed validator for G4IRSF15 Stage 15C/15D.

This module intentionally does not import the generator.  It independently
recomputes protected-input hashes, source/binary bindings, self hashes,
descriptor sampling probabilities, contiguous shard identities, pair/label
counts, split isolation, and the pilot/formal gates.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import math
import ntpath
import os
import posixpath
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

MAP_PATH = Path("data/processed/maps/map2.json")
TASK_PATH = Path("data/processed/tasks/inputdata.jsonl")
MODEL_PATH = Path("artifacts/models/g4e_risk_calibrated_policy.json")
OFFLINE_TAIL_PATH = Path("outputs/tables/g4irsf13_per_bag_delta.csv")
DESCRIPTOR_DATASET_PATH = Path(
    "artifacts/datasets/g4irsf15_causal_target_address_frame.jsonl.zst"
)
SKELETON_DATASET_ROOT = Path(
    "artifacts/datasets/g4irsf15_causal_skeleton_population"
)
DESCRIPTOR_MANIFEST_PATH = Path(
    "artifacts/datasets/g4irsf15_causal_descriptor_manifest.json"
)
CHECKPOINT_MANIFEST_PATH = Path(
    "artifacts/datasets/g4irsf15_checkpoint_bank_manifest.json"
)
PILOT_PLAN_PATH = Path(
    "artifacts/datasets/g4irsf15_pilot_intervention_manifest.json"
)
PILOT_RESULT_PATH = Path(
    "artifacts/datasets/g4irsf15_pilot_causal_result.json"
)
PILOT_ROUND2_PLAN_PATH = Path(
    "artifacts/datasets/g4irsf15_pilot_intervention_manifest_round2.json"
)
PILOT_SCREENING_REVISION_PATH = Path(
    "artifacts/datasets/g4irsf15_pilot_screening_revision.json"
)
PILOT_ROUND2_RESULT_PATH = Path(
    "artifacts/datasets/g4irsf15_pilot_causal_result_round2.json"
)
FORMAL_PLAN_PATH = Path(
    "artifacts/datasets/g4irsf15_causal_campaign_plan.json"
)
LABEL_DATASET_PATH = Path(
    "artifacts/datasets/g4irsf15_causal_labels.jsonl.zst"
)
LABEL_MANIFEST_PATH = Path(
    "artifacts/datasets/g4irsf15_causal_label_manifest.json"
)
WEIGHTED_EFFECT_DATASET_PATH = Path(
    "artifacts/datasets/g4irsf15_weighted_effect_estimates.json"
)
SPLIT_GROUP_PATH = Path(
    "artifacts/datasets/g4irsf15_intervention_split_groups.json"
)
WEIGHTED_EFFECT_TABLE_PATH = Path(
    "outputs/tables/g4irsf15_weighted_effect_estimates.csv"
)
RUN_STATE_SHARD_ROOT = Path(
    "outputs/runstate/g4irsf15_causal_shards"
)
COMPACT_EVIDENCE_ROOT = Path(
    "artifacts/datasets/g4irsf15_compact_pair_evidence"
)
H_SYSTEM_BASELINE_REFERENCE_PATH = Path(
    "artifacts/datasets/"
    "g4irsf15_h_system_baseline_reference.json.zst"
)
GENERATOR_PATH = Path("scripts/eval/g4irsf15_causal_campaign.py")
ORCHESTRATOR_PATH = Path(
    "scripts/run_g4irsf15_campaign_shards.py"
)
ORCHESTRATOR_PROFILE_ROOT = Path(
    "artifacts/datasets/g4irsf15_campaign_execution_profiles"
)

MAP_RAW_SHA256 = (
    "9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4"
)
TASK_RAW_SHA256 = (
    "968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f"
)
MODEL_SHA256 = (
    "4a058dee0bdd17e15f67d1943a551822847d0c066ac3cf03a5da71a07731bbca"
)
FULL_SEGMENT_COUNT = 43_603
FULL_RAW_BAG_COUNT = 28_506
KINDS = ("I1", "I3", "I4")
HEX = frozenset("0123456789abcdef")

DESCRIPTOR_SCHEMA = "czr005.g4irsf15.causal_target_descriptor.v1"
SKELETON_SCAN_SCHEMA = (
    "czr005.g4irsf15.causal_skeleton_population.v1"
)
SKELETON_SCHEMA = "czr005.g4irsf15.causal_skeleton.v1"
MATERIALIZATION_SCHEMA = (
    "czr005.g4irsf15.causal_descriptor_materialization.v1"
)
TARGET_ADDRESS_SCHEMA = "czr005.g4irsf15.causal_target_address.v1"
TARGET_ADDRESS_HORIZON_SCHEMA = (
    "czr005.g4irsf15.causal_target_address_horizon.v1"
)
PREPOP_EVENT_GROUP_SCHEMA = (
    "czr005.g4irsf15.prepop_event_group.v1"
)
G4IRSF14_STATE_CLONE_SCHEMA = (
    "czr005.g4irsf14.matched_runtime_state_clone.v2"
)
RESOLVED_STATE_COMPONENT_FIELDS = (
    ("event_queue_sha256", "event_queue"),
    ("current_time_sha256", "current_time"),
    ("bags_sha256", "bags"),
    ("source_queues_sha256", "source_queues"),
    ("junction_queues_sha256", "junction_queues"),
    ("local_service_calendars_sha256", "local_service_calendars"),
    ("corridor_state_sha256", "corridor_state"),
    ("scheduled_incoming_sha256", "scheduled_incoming"),
    ("credits_sha256", "credits"),
    ("merge_grants_sha256", "merge_grants"),
    ("fault_state_sha256", "fault_state"),
    ("pibt_owner_state_sha256", "pibt_owner_state"),
    ("deterministic_counters_sha256", "deterministic_counters"),
    ("scorer_state_sha256", "scorer_state"),
    ("result_accumulator_sha256", "result_accumulator"),
    ("current_runtime_hashes_sha256", "current_runtime_hashes"),
    ("congestion_beacons_sha256", "congestion_beacons"),
    ("microphase_state_sha256", "microphase_state"),
)
RESOLVED_INTERVENTION_KIND = {
    "I1": "I1_source_order_swap",
    "I3": "I3_next_edge",
    "I4": "I4_hold_release",
}
RESOLVED_BOUNDARY_KIND = {
    "I1": "source_arbitration",
    "I3": "junction_route_arbitration",
    "I4": "hold_release_opportunity",
}
BUILD_MANIFEST_SCHEMA = (
    "czr005.g4irsf15.exact_binary_build_manifest.v1"
)
DESCRIPTOR_MANIFEST_SCHEMA = (
    "czr005.g4irsf15.causal_descriptor_manifest.v3"
)
CHECKPOINT_MANIFEST_SCHEMA = (
    "czr005.g4irsf15.checkpoint_bank_manifest.v1"
)
PLAN_SCHEMA = "czr005.g4irsf15.causal_campaign_plan.v1"
SHARD_SCHEMA = "czr005.g4irsf15.causal_pair_shard.v1"
PAIR_RUN_SCHEMA = "czr005.g4irsf15.causal_target_pairs.v1"
LABEL_SCHEMA = "czr005.g4irsf15.causal_label.v1"
LABEL_MANIFEST_SCHEMA = "czr005.g4irsf15.causal_label_manifest.v2"
ORCHESTRATOR_PROFILE_SCHEMA = (
    "czr005.g4irsf15.campaign_shard_orchestrator_profile.v1"
)
ORCHESTRATOR_HEARTBEAT_SCHEMA = (
    "czr005.g4irsf15.campaign_shard_orchestrator_heartbeat.v1"
)
ORCHESTRATOR_PROFILE_SET_SCHEMA = (
    "czr005.g4irsf15.campaign_shard_execution_profile_set.v1"
)
MAX_PUBLICATION_PROCESS_RSS_MIB = 65_536.0
MAX_ORCHESTRATOR_HEARTBEAT_INTERVAL_SECONDS = 60.0
PRODUCTION_RSS_METHODS = frozenset(
    {
        "WINDOWS_TOOLHELP32_PROCESS_TREE_GETPROCESSMEMORYINFO",
        "LINUX_PROC_PROCESS_TREE_STATUS",
    }
)
COMPACT_EVIDENCE_SCHEMA = (
    "czr005.g4irsf15.compact_pair_evidence_shard.v1"
)
COMPACT_NATIVE_ATTESTATION_SCHEMA = (
    "czr005.g4irsf15.compact_native_payload_attestation.v1"
)
H_SYSTEM_BASELINE_REFERENCE_SCHEMA = (
    "czr005.g4irsf15.h_system_baseline_reference.v1"
)
RAW_BAG_SPARSE_OVERLAY_SCHEMA = (
    "czr005.g4irsf15."
    "raw_bag_sufficient_statistics_sparse_overlay.v1"
)
COHORT_DIFFERENCE_SPARSE_OVERLAY_SCHEMA = (
    "czr005.g4irsf15."
    "full_cohort_outcome_difference_sparse_overlay.v1"
)
SPLIT_SCHEMA = "czr005.g4irsf15.intervention_split_groups.v1"
WEIGHTED_EFFECT_SCHEMA = (
    "czr005.g4irsf15.weighted_effect_estimates.v1"
)
PILOT_SCREENING_REVISION_SCHEMA = (
    "czr005.g4irsf15.pilot_screening_revision.v1"
)
OUTCOME_FREE_SCREENING_PREDICATE_SCHEMA = (
    "czr005.g4irsf15.outcome_free_screening_predicate.v1"
)

PILOT_ATTEMPTS_PER_KIND = 64
PILOT_MIN_COMPLETE_PER_KIND = 30
FORMAL_ATTEMPTS_BY_KIND = {"I1": 1536, "I3": 1280, "I4": 1280}
FORMAL_LABEL_TARGETS = {"I1": 768, "I3": 640, "I4": 640}
FORMAL_MIN_LABELS = 2_048
FORMAL_MIN_H_SYSTEM = 128
FORMAL_MIN_KIND = 512
DEFAULT_H_SYSTEM_TARGETS_PER_SHARD = 4
GITHUB_SAFE_ARTIFACT_MAX_BYTES = 95 * 1024 * 1024
SKELETON_ROWS_PER_SHARD = 200_000
OUTCOME_FREE_SCREENING_FIELDS = (
    "baseline_release",
    "candidate_action_count",
    "coverage_tags",
    "event_hour_floor",
    "kind",
    "legal_next_edges",
    "node",
    "sampling_stratum_id",
    "selected_boolean",
    "source_ready_order",
    "total_legal_action_count",
)
ANALYSIS_DELTA_METRICS = (
    "delta_completion_mean_seconds",
    "delta_completion_p95_seconds",
    "delta_completion_p99_seconds",
    "delta_source_wait_mean_seconds",
    "delta_total_local_wait_mean_seconds",
    "delta_junction_wait_mean_seconds",
    "delta_merge_wait_mean_seconds",
    "delta_edge_travel_mean_seconds",
    "delta_node_service_mean_seconds",
    "delta_loop_extra_mean_seconds",
    "delta_path_length_hops_total",
    "delta_path_length_hops_mean",
    "delta_deadline_miss_count",
)
ANALYSIS_RAW_METRICS = (
    "delta_original_entry_mean_minutes",
    "delta_original_entry_median_seconds",
    "delta_original_entry_p95_seconds",
    "delta_original_entry_p99_seconds",
    "delta_original_entry_max_seconds",
    "delta_java_release_mean_minutes",
    "delta_scheduled_pre_release_wait_mean_minutes",
    "delta_source_wait_mean_minutes",
    "delta_network_time_mean_minutes",
    "delta_total_system_time_mean_minutes",
    "delta_deadline_miss_raw_bag_count",
)
BOOTSTRAP_SEED = "g4irsf15-clone-group-bootstrap-v1"
BOOTSTRAP_REPLICATES = 1_000
FROZEN_CONTROLS: Mapping[str, Any] = {
    "resource_semantics": "R3_java_node_window_compatible",
    "scorer_mode": "S1_frozen_g4e_legal_local_adapter",
    "pibt_mode": "P2",
    "pressure_mode": "C0_off",
    "priority_mode": "Q0",
    "event_semantics": "E4_batch_plus_destination_merge_request",
    "merge_grant_rule": "M0",
    "admission_mode": "off",
    "reservation_depth": 1,
    "max_events": 20_000_000,
    "max_simulation_time": -1.0,
}


class ValidationError(RuntimeError):
    """Raised on any missing, malformed, or contradictory evidence."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def canonical_sequence_sha256(values: Iterable[Any]) -> str:
    digest = hashlib.sha256()
    digest.update(b"[")
    for index, value in enumerate(values):
        if index:
            digest.update(b",")
        digest.update(canonical_bytes(value))
    digest.update(b"]")
    return digest.hexdigest()


def canonical_fields_payload(
    fields: Sequence[tuple[str, str, Any]],
) -> bytes:
    payload = bytearray(b"CZR005-CANONICAL-FIELDS\x02")
    for name, field_type, value in fields:
        encoded_name = name.encode()
        payload.extend(len(encoded_name).to_bytes(4, "big"))
        payload.extend(encoded_name)
        payload.extend(field_type.encode())
        if field_type == "s":
            encoded = value if isinstance(value, bytes) else str(value).encode()
            payload.extend(len(encoded).to_bytes(8, "big"))
            payload.extend(encoded)
        elif field_type in {"i", "u"}:
            payload.extend(
                (int(value) & ((1 << 64) - 1)).to_bytes(8, "big")
            )
        elif field_type == "d":
            import struct

            payload.extend(struct.pack(">d", float(value)))
        elif field_type == "b":
            payload.extend(b"\x01" if value else b"\x00")
        elif field_type == "I":
            values = list(value)
            payload.extend(len(values).to_bytes(8, "big"))
            for item in values:
                payload.extend(
                    (int(item) & ((1 << 64) - 1)).to_bytes(8, "big")
                )
        else:
            raise ValidationError(
                f"UNSUPPORTED_CANONICAL_FIELD_TYPE:{field_type}"
            )
    return bytes(payload)


def canonical_fields_sha256(
    fields: Sequence[tuple[str, str, Any]],
) -> str:
    return hashlib.sha256(canonical_fields_payload(fields)).hexdigest()


def file_sha256(path: Path) -> str:
    require(path.is_file(), f"MISSING_FILE:{path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def publishable_byte_count(path: Path, label: str) -> int:
    size = path.stat().st_size
    require(
        size < GITHUB_SAFE_ARTIFACT_MAX_BYTES,
        f"ARTIFACT_APPROACHES_GITHUB_100_MIB_LIMIT:{label}:{size}",
    )
    return size


def is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in HEX for character in value)
    )


def producer_path_is_absolute(value: str) -> bool:
    return ntpath.isabs(value.replace("/", "\\")) or posixpath.isabs(
        value.replace("\\", "/")
    )


def producer_path_basename(value: str) -> str:
    if "\\" in value or ntpath.splitdrive(value)[0]:
        return ntpath.basename(value.replace("/", "\\"))
    return posixpath.basename(value.replace("\\", "/"))


def portable_binary_location(
    root: Path, declared: str
) -> tuple[Path | None, str | None]:
    """Classify a producer path without applying host path semantics."""

    require(bool(declared), "BUILD_BINARY_PATH_MISSING")
    if producer_path_is_absolute(declared):
        native = Path(declared)
        return (
            native.resolve()
            if native.is_absolute()
            else None,
            None,
        )
    candidate = (root / Path(declared)).resolve()
    try:
        relative = candidate.relative_to(root.resolve()).as_posix()
    except ValueError:
        return candidate, None
    return candidate, relative


def strict_int(value: Any, label: str, minimum: int = 0) -> int:
    require(
        isinstance(value, int) and not isinstance(value, bool),
        f"NOT_INTEGER:{label}",
    )
    result = int(value)
    require(result >= minimum, f"INTEGER_BELOW_MINIMUM:{label}")
    return result


def strict_float(value: Any, label: str) -> float:
    require(
        isinstance(value, (int, float)) and not isinstance(value, bool),
        f"NOT_NUMERIC:{label}",
    )
    result = float(value)
    require(math.isfinite(result), f"NONFINITE:{label}")
    return result


def wilson_lower_bound(successes: int, attempts: int, z: float = 1.96) -> float:
    proportion = successes / attempts
    z2 = z * z
    return max(
        0.0,
        (
            proportion
            + z2 / (2.0 * attempts)
            - z
            * math.sqrt(
                proportion * (1.0 - proportion) / attempts
                + z2 / (4.0 * attempts * attempts)
            )
        )
        / (1.0 + z2 / attempts),
    )


def load_json(path: Path) -> dict[str, Any]:
    require(path.is_file(), f"MISSING_JSON:{path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(
            f"INVALID_JSON:{path}:{type(exc).__name__}"
        ) from exc
    require(isinstance(value, dict), f"JSON_NOT_OBJECT:{path}")
    return value


def validate_self_hash(value: Mapping[str, Any], label: str) -> None:
    declared = value.get("self_sha256")
    require(is_sha256(declared), f"MISSING_SELF_SHA256:{label}")
    projection = dict(value)
    projection.pop("self_sha256", None)
    require(
        declared == canonical_sha256(projection),
        f"SELF_SHA256_DRIFT:{label}",
    )


def zstd_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        import zstandard
    except ImportError as exc:
        raise ValidationError(
            "ZSTANDARD_DEPENDENCY_REQUIRED: install zstandard>=0.23"
        ) from exc
    try:
        payload = zstandard.ZstdDecompressor().decompress(path.read_bytes())
    except zstandard.ZstdError as exc:
        raise ValidationError(f"ZSTD_DECOMPRESS_FAILED:{path}:{exc}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(payload.splitlines(), start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                f"INVALID_JSONL:{path}:{line_number}"
            ) from exc
        require(
            isinstance(row, dict),
            f"JSONL_ROW_NOT_OBJECT:{path}:{line_number}",
        )
        rows.append(row)
    return rows


def zstd_json(path: Path) -> dict[str, Any]:
    try:
        import zstandard
    except ImportError as exc:
        raise ValidationError(
            "ZSTANDARD_DEPENDENCY_REQUIRED: install zstandard>=0.23"
        ) from exc
    try:
        value = json.loads(
            zstandard.ZstdDecompressor().decompress(path.read_bytes())
        )
    except (zstandard.ZstdError, json.JSONDecodeError) as exc:
        raise ValidationError(f"INVALID_ZSTD_JSON:{path}") from exc
    require(isinstance(value, dict), f"ZSTD_JSON_NOT_OBJECT:{path}")
    return value


def protected_inputs(root: Path) -> dict[str, Any]:
    require(file_sha256(root / MAP_PATH) == MAP_RAW_SHA256, "MAP_HASH_DRIFT")
    require(file_sha256(root / TASK_PATH) == TASK_RAW_SHA256, "TASK_HASH_DRIFT")
    require(file_sha256(root / MODEL_PATH) == MODEL_SHA256, "MODEL_HASH_DRIFT")
    segment_count = 0
    task_ids: set[int] = set()
    segment_ids: set[str] = set()
    runtime_mapping: list[dict[str, Any]] = []
    raw_mapping: dict[int, list[tuple[int, str]]] = defaultdict(list)
    original_entry_by_task: dict[int, float] = {}
    workload_fields: list[tuple[str, str, Any]] = [
        (
            "schema",
            "s",
            "czr005.g4irsf15.input_runtime_cohort_order.v1",
        ),
        ("request_count", "u", FULL_SEGMENT_COUNT),
    ]
    with (root / TASK_PATH).open("rb") as handle:
        for physical_line, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise ValidationError(
                    f"TASK_JSON_INVALID:{physical_line}"
                ) from exc
            require(isinstance(row, dict), "TASK_ROW_NOT_OBJECT")
            segment_id = str(row.get("segment_id", ""))
            require(segment_id and segment_id not in segment_ids, "TASK_SEGMENT_ID")
            segment_ids.add(segment_id)
            task_id = int(row["task_id"])
            task_ids.add(task_id)
            original_entry = float(row["original_entry_time"])
            release = float(row["pass_time"])
            require("std" in row, f"TASK_STD_MISSING:{physical_line}")
            deadline = float(row["std"])
            require(
                math.isfinite(original_entry)
                and math.isfinite(release)
                and math.isfinite(deadline)
                and original_entry <= release,
                f"INVALID_PROTECTED_REQUEST_TIMES:{task_id}",
            )
            previous = original_entry_by_task.setdefault(
                task_id, original_entry
            )
            require(
                previous == original_entry,
                f"ORIGINAL_ENTRY_NOT_CONSTANT_PER_TASK:{task_id}",
            )
            runtime_mapping.append(
                {
                    "runtime_bag_id": segment_count,
                    "segment_id": segment_id,
                    "task_id": task_id,
                }
            )
            raw_mapping[task_id].append((segment_count, segment_id))
            workload_fields.append(
                (
                    "request",
                    "s",
                    canonical_fields_payload(
                        [
                            ("runtime_bag_id", "u", segment_count),
                            ("task_id", "i", task_id),
                            ("segment_id", "s", segment_id),
                            ("start", "i", int(row["start"])),
                            ("goal", "i", int(row["goal"])),
                            ("release_time", "d", release),
                            ("deadline", "d", deadline),
                            (
                                "source",
                                "s",
                                str(
                                    row.get(
                                        "source",
                                        f"node_{int(row['start'])}",
                                    )
                                ),
                            ),
                        ]
                    ),
                )
            )
            segment_count += 1
    require(segment_count == FULL_SEGMENT_COUNT, "TASK_SEGMENT_COUNT_DRIFT")
    require(len(task_ids) == FULL_RAW_BAG_COUNT, "TASK_RAW_BAG_COUNT_DRIFT")
    raw_rows = [
        {
            "task_id": task_id,
            "segment_ids_in_protected_input_order": [
                segment for _, segment in entries
            ],
        }
        for task_id, entries in sorted(raw_mapping.items())
    ]
    original_fields: list[tuple[str, str, Any]] = [
        (
            "schema",
            "s",
            "czr005.g4irsf15.raw_bag_original_entry_mapping.v1",
        ),
        ("raw_bag_count", "u", len(raw_mapping)),
    ]
    for task_id, entries in sorted(raw_mapping.items()):
        original_fields.append(
            (
                "raw_bag",
                "s",
                canonical_fields_payload(
                    [
                        ("task_id", "i", task_id),
                        (
                            "runtime_bag_ids",
                            "I",
                            [runtime_id for runtime_id, _ in entries],
                        ),
                        (
                            "original_entry_time",
                            "d",
                            original_entry_by_task[task_id],
                        ),
                    ]
                ),
            )
        )
    return {
        "segment_count": segment_count,
        "raw_bag_count": len(task_ids),
        "input_runtime_cohort_sha256": canonical_fields_sha256(
            workload_fields
        ),
        "runtime_segment_mapping_sha256": canonical_sha256(
            runtime_mapping
        ),
        "raw_bag_mapping_sha256": canonical_sha256(raw_rows),
        "raw_bag_original_entry_mapping_sha256": (
            canonical_fields_sha256(original_fields)
        ),
    }


def validate_source_identity(
    root: Path, identity: Mapping[str, Any]
) -> None:
    files = identity.get("files")
    require(isinstance(files, list) and files, "SOURCE_FILES_MISSING")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for binding in files:
        require(isinstance(binding, dict), "SOURCE_BINDING_NOT_OBJECT")
        relative = str(binding.get("path", ""))
        require(relative and relative not in seen, "SOURCE_PATH_DUPLICATE")
        seen.add(relative)
        path = root / Path(relative)
        require(file_sha256(path) == binding.get("sha256"), f"SOURCE_DRIFT:{relative}")
        require(path.stat().st_size == binding.get("byte_count"), f"SOURCE_SIZE:{relative}")
        normalized.append(dict(binding))
    normalized.sort(key=lambda row: row["path"])
    require(
        canonical_sha256(normalized) == identity.get("source_bundle_sha256"),
        "SOURCE_BUNDLE_SHA256_DRIFT",
    )


def validate_build_manifest(
    root: Path,
    binding: Mapping[str, Any],
    *,
    binary: Path | None = None,
    strict_host_provenance: bool = False,
) -> dict[str, Any]:
    require(isinstance(binding, dict), "BUILD_MANIFEST_BINDING_MISSING")
    declared_manifest_path = Path(str(binding.get("path", "")))
    require(
        str(declared_manifest_path)
        and not declared_manifest_path.is_absolute()
        and declared_manifest_path.as_posix()
        == str(binding.get("path")),
        "BUILD_MANIFEST_PATH_NOT_REPOSITORY_RELATIVE",
    )
    manifest_path = (root / declared_manifest_path).resolve()
    try:
        canonical_manifest_relative = manifest_path.relative_to(
            root.resolve()
        ).as_posix()
    except ValueError as exc:
        raise ValidationError(
            "BUILD_MANIFEST_PATH_ESCAPES_REPOSITORY"
        ) from exc
    require(
        canonical_manifest_relative == str(binding.get("path")),
        "BUILD_MANIFEST_PATH_NOT_CANONICAL_REPOSITORY_RELATIVE",
    )
    manifest = load_json(manifest_path)
    validate_self_hash(manifest, "exact_binary_build_manifest")
    require(
        manifest.get("schema") == BUILD_MANIFEST_SCHEMA
        and manifest.get("status") == "COMPLETE",
        "BUILD_MANIFEST_SCHEMA_OR_STATUS",
    )
    require(
        file_sha256(manifest_path) == binding.get("file_sha256")
        and manifest.get("self_sha256") == binding.get("self_sha256"),
        "BUILD_MANIFEST_FILE_BINDING_DRIFT",
    )
    binary_row = manifest.get("binary")
    require(isinstance(binary_row, dict), "BUILD_BINARY_ROW_MISSING")
    declared_binary_text = str(binary_row.get("path", ""))
    binary_path, publication_binary_path = portable_binary_location(
        root, declared_binary_text
    )
    require(
        is_sha256(binary_row.get("sha256"))
        and binary_row.get("sha256") == binding.get("binary_sha256")
        and binding.get("binary_path") == publication_binary_path
        and binding.get("binary_path_scope")
        == (
            "REPOSITORY_RELATIVE_GENERATION_ARTIFACT"
            if publication_binary_path is not None
            else "CONTENT_HASH_ONLY_EXTERNAL_GENERATION_ARTIFACT"
        )
        and strict_int(
            binary_row.get("byte_count"), "build.binary.byte_count", 1
        )
        > 0,
        "BUILD_BINARY_BINDING_DRIFT",
    )
    if binary is not None or strict_host_provenance:
        host_binary = binary.resolve() if binary is not None else binary_path
        require(
            host_binary is not None
            and (
                publication_binary_path is None
                or host_binary
                == (root / publication_binary_path).resolve()
            )
            and file_sha256(host_binary) == binary_row["sha256"]
            and host_binary.stat().st_size == binary_row["byte_count"],
            "VALIDATOR_BINARY_DIFFERS_FROM_BUILD_MANIFEST",
        )
    git_row = manifest.get("git")
    require(isinstance(git_row, dict), "BUILD_GIT_ROW_MISSING")
    build_head = str(git_row.get("head", ""))
    current_head = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    ancestor = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "merge-base",
            "--is-ancestor",
            build_head,
            current_head,
        ],
        check=False,
    )
    require(
        is_sha256(build_head) and ancestor.returncode == 0,
        "BUILD_HEAD_NOT_PUBLICATION_ANCESTOR",
    )
    inventory = manifest.get("transitive_source_inventory")
    require(
        isinstance(inventory, dict)
        and inventory.get("method")
        == "CMAKE_DEPENDENCY_SCAN_PLUS_EXPLICIT_HEADERS",
        "BUILD_INVENTORY_MISSING_OR_METHOD_DRIFT",
    )
    files = inventory.get("files")
    require(isinstance(files, list) and files, "BUILD_INVENTORY_FILES")
    normalized: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    for source in files:
        require(isinstance(source, dict), "BUILD_SOURCE_ROW_NOT_OBJECT")
        relative = str(source.get("path", ""))
        require(
            relative and relative not in seen_sources,
            "BUILD_SOURCE_PATH_DUPLICATE",
        )
        seen_sources.add(relative)
        current = root / relative
        if strict_host_provenance:
            require(
                file_sha256(current) == source.get("sha256")
                and current.stat().st_size == source.get("byte_count"),
                f"BUILD_SOURCE_CURRENT_DRIFT:{relative}",
            )
        tree = subprocess.run(
            ["git", "-C", str(root), "show", f"{build_head}:{relative}"],
            check=False,
            capture_output=True,
        )
        require(
            tree.returncode == 0
            and hashlib.sha256(tree.stdout).hexdigest()
            == source.get("sha256"),
            f"BUILD_SOURCE_TREE_DRIFT:{relative}",
        )
        normalized.append(dict(source))
    require(
        {
            "CMakeLists.txt",
            "cpp/ics_core/bindings/czr005_cpp.cpp",
            "cpp/ics_core/bindings/g4irsf15_causal_campaign_binding.hpp",
            "cpp/ics_core/runtime/event_driven_junction.hpp",
            "cpp/ics_core/runtime/g4irsf15_causal_campaign.hpp",
        }.issubset(seen_sources),
        "BUILD_INVENTORY_MISSES_REQUIRED_NATIVE_SOURCE",
    )
    normalized.sort(key=lambda row: row["path"])
    require(
        canonical_sha256(normalized) == inventory.get("bundle_sha256")
        == binding.get("transitive_source_bundle_sha256"),
        "BUILD_SOURCE_BUNDLE_DRIFT",
    )
    dirty = manifest.get("dirty_source_state")
    require(isinstance(dirty, dict), "BUILD_DIRTY_STATE_MISSING")
    dirty_projection = dict(dirty)
    declared_dirty = dirty_projection.pop("state_sha256", None)
    require(
        declared_dirty == canonical_sha256(dirty_projection)
        == binding.get("dirty_source_state_sha256")
        and dirty.get("head") == build_head,
        "BUILD_DIRTY_STATE_HASH_DRIFT",
    )
    toolchain = manifest.get("toolchain")
    require(
        isinstance(toolchain, dict)
        and toolchain.get("configuration") == "Release"
        and toolchain.get("generator") not in {None, ""},
        "BUILD_TOOLCHAIN_NOT_RELEASE",
    )
    for field in ("cmake", "compiler", "cmake_cache"):
        row = toolchain.get(field)
        require(isinstance(row, dict), f"BUILD_TOOLCHAIN_FIELD:{field}")
        path = Path(str(row.get("path", "")))
        if not path.is_absolute():
            path = root / path
        require(
            is_sha256(row.get("sha256"))
            and strict_int(
                row.get("byte_count"), f"build.{field}.byte_count", 1
            )
            > 0,
            f"BUILD_TOOLCHAIN_RECORD_DRIFT:{field}",
        )
        if strict_host_provenance:
            require(
                file_sha256(path) == row.get("sha256")
                and path.stat().st_size == row.get("byte_count"),
                f"BUILD_TOOLCHAIN_FILE_DRIFT:{field}",
            )
    python_row = toolchain.get("python")
    pybind_row = toolchain.get("pybind11")
    require(
        isinstance(python_row, dict) and isinstance(pybind_row, dict),
        "BUILD_PYTHON_PYBIND_ROW_MISSING",
    )
    python_path = Path(str(python_row.get("path", ""))).resolve()
    reported = Path(
        str(python_row.get("reported_executable", ""))
    ).resolve()
    try:
        same_python = os.path.samefile(python_path, reported)
    except OSError:
        same_python = os.path.normcase(str(python_path)) == os.path.normcase(
            str(reported)
        )
    require(
        is_sha256(python_row.get("sha256"))
        and python_row.get("version")
        and python_row.get("implementation")
        and pybind_row.get("version")
        and pybind_row.get("cmake_dir"),
        "BUILD_PYTHON_RECORD_DRIFT",
    )
    if strict_host_provenance:
        require(
            same_python
            and file_sha256(python_path) == python_row.get("sha256"),
            "BUILD_PYTHON_BINDING_DRIFT",
        )
    execution = manifest.get("build_execution")
    configure_argv = toolchain.get("configure_argv")
    build_argv = toolchain.get("build_argv")
    def following(argv: Any, token: str) -> Any:
        if not isinstance(argv, list) or token not in argv:
            return None
        index = argv.index(token)
        return argv[index + 1] if index + 1 < len(argv) else None

    require(
        isinstance(execution, dict)
        and isinstance(configure_argv, list)
        and isinstance(build_argv, list)
        and len(configure_argv) >= 8
        and len(build_argv) >= 8
        and producer_path_basename(str(configure_argv[0])).lower()
        in {"cmake", "cmake.exe"}
        and producer_path_basename(str(build_argv[0])).lower()
        in {"cmake", "cmake.exe"}
        and "-S" in configure_argv
        and "-B" in configure_argv
        and "-DCMAKE_BUILD_TYPE=Release" in configure_argv
        and any(
            str(token).startswith("-DPython3_EXECUTABLE=")
            for token in configure_argv
        )
        and any(
            str(token).startswith("-Dpybind11_DIR=")
            for token in configure_argv
        )
        and "--build" in build_argv
        and following(build_argv, "--config") == "Release"
        and following(build_argv, "--target") == "czr005_cpp"
        and "--clean-first" in build_argv
        and execution.get("clean_first") is True
        and execution.get("source_inventory_unchanged_during_build") is True
        and execution.get("configure", {}).get("argv") == configure_argv
        and execution.get("build", {}).get("argv") == build_argv
        and execution.get("configure", {}).get("return_code") == 0
        and execution.get("build", {}).get("return_code") == 0
        and is_sha256(
            execution.get("configure", {}).get("stdout_sha256")
        )
        and is_sha256(
            execution.get("configure", {}).get("stderr_sha256")
        )
        and is_sha256(execution.get("build", {}).get("stdout_sha256"))
        and is_sha256(execution.get("build", {}).get("stderr_sha256")),
        "BUILD_EXECUTION_ATTESTATION_DRIFT",
    )
    producer = manifest.get("producer")
    require(isinstance(producer, dict), "BUILD_PRODUCER_RECORD_MISSING")
    producer_relative = str(producer.get("path", ""))
    producer_tree = subprocess.run(
        ["git", "-C", str(root), "show", f"{build_head}:{producer_relative}"],
        check=False,
        capture_output=True,
    )
    require(
        producer_relative
        == "scripts/create_g4irsf15_exact_binary_build_manifest.py"
        and is_sha256(producer.get("sha256"))
        and strict_int(
            producer.get("byte_count"), "build.producer.byte_count", 1
        )
        > 0
        and producer_tree.returncode == 0
        and hashlib.sha256(producer_tree.stdout).hexdigest()
        == producer.get("sha256")
        and len(producer_tree.stdout) == producer.get("byte_count"),
        "BUILD_PRODUCER_RECORD_DRIFT",
    )
    if strict_host_provenance:
        producer_path = root / producer_relative
        require(
            file_sha256(producer_path) == producer.get("sha256")
            and producer_path.stat().st_size == producer.get("byte_count"),
            "BUILD_PRODUCER_FILE_DRIFT",
        )
    manifest = dict(manifest)
    manifest["_validation_scope"] = {
        "publication_static_provenance": True,
        "binary_reverified": binary is not None or strict_host_provenance,
        "host_toolchain_reverified": strict_host_provenance,
    }
    return manifest


def validate_descriptor(row: Mapping[str, Any]) -> None:
    require(row.get("schema") == DESCRIPTOR_SCHEMA, "DESCRIPTOR_SCHEMA")
    require(row.get("kind") in KINDS, "DESCRIPTOR_KIND")
    descriptor = row.get("descriptor_id")
    require(is_sha256(descriptor), "DESCRIPTOR_ID")
    require(is_sha256(row.get("clone_group_id")), "DESCRIPTOR_CLONE_GROUP")
    hashes = row.get("intervention_sha256_by_horizon")
    require(isinstance(hashes, dict), "DESCRIPTOR_HORIZON_HASHES")
    require(
        hashes.get("H_bag") == descriptor
        and is_sha256(hashes.get("H_system")),
        "DESCRIPTOR_HORIZON_BINDING",
    )
    require(row.get("baseline_action") != row.get("intervention_action"), "ACTION_SAME")
    require(
        row.get("queue_top_not_popped") is True
        and row.get("staged_event_sink_empty") is True,
        "DESCRIPTOR_NOT_PREPOP",
    )
    for counter in (
        "runtime_global_scan_count",
        "runtime_future_route_read_count",
        "runtime_future_schedule_read_count",
    ):
        require(row.get(counter) == 0, f"DESCRIPTOR_LEAKAGE:{counter}")
    require(row.get("reservation_depth") == 1, "RESERVATION_DEPTH_DRIFT")
    sampling = row.get("sampling")
    require(isinstance(sampling, dict), "SAMPLING_METADATA_MISSING")
    N_h = strict_int(sampling.get("N_h"), "N_h", 1)
    n_h = strict_int(sampling.get("n_h"), "n_h", 1)
    pi_h = strict_float(sampling.get("pi_h"), "pi_h")
    weight = strict_float(sampling.get("analysis_weight"), "analysis_weight")
    require(n_h <= N_h, "N_H_EXCEEDS_CAPACITY")
    require(0.0 < pi_h <= 1.0, "PI_H_OUT_OF_RANGE")
    require(math.isclose(pi_h, n_h / N_h, rel_tol=0.0, abs_tol=1e-15), "PI_H_DRIFT")
    require(math.isclose(weight, 1.0 / pi_h, rel_tol=1e-12), "WEIGHT_DRIFT")
    require(
        sampling.get("cluster_id") == row.get("clone_group_id")
        and sampling.get("cluster_bootstrap_unit") == "clone_group_id",
        "CLUSTER_BOOTSTRAP_FIELDS_DRIFT",
    )
    offline = row.get("offline_sampling_metadata")
    require(
        isinstance(offline, dict)
        and offline.get("must_not_enter_policy_features") is True
        and offline.get("runtime_only") is False,
        "OFFLINE_FEATURE_SCOPE_DRIFT",
    )


def prepop_event_group_sha256(
    row: Mapping[str, Any], *, input_runtime_cohort_sha256: str
) -> str:
    require(
        is_sha256(input_runtime_cohort_sha256),
        "TARGET_ADDRESS_COHORT_SHA256_MISSING",
    )
    return canonical_sha256(
        {
            "schema": PREPOP_EVENT_GROUP_SCHEMA,
            "input_runtime_cohort_sha256": input_runtime_cohort_sha256,
            "event_ordinal": strict_int(
                row.get("event_ordinal"), "target.event_ordinal"
            ),
            "event_seq": strict_int(row.get("event_seq"), "target.event_seq", 1),
            "event_time_bits": strict_int(
                row.get("event_time_bits"), "target.event_time_bits"
            ),
            "node": strict_int(row.get("node"), "target.node"),
        }
    )


def target_address_horizon_sha256(
    target_address_id: str, horizon: str
) -> str:
    require(is_sha256(target_address_id), "TARGET_ADDRESS_ID_INVALID")
    require(horizon in {"H_bag", "H_system"}, "TARGET_ADDRESS_HORIZON")
    return canonical_sha256(
        {
            "schema": TARGET_ADDRESS_HORIZON_SCHEMA,
            "target_address_id": target_address_id,
            "horizon": horizon,
        }
    )


def validate_target_address(
    row: Mapping[str, Any], *, input_runtime_cohort_sha256: str
) -> None:
    require(row.get("schema") == TARGET_ADDRESS_SCHEMA, "TARGET_ADDRESS_SCHEMA")
    address = row.get("target_address_id")
    require(
        is_sha256(address)
        and row.get("descriptor_id") == address
        and row.get("skeleton_id") == address
        and row.get("population_selection_sha256") == address
        and row.get("skeleton_selection_sha256") == address
        and row.get("sample_sha256") == address
        and row.get("input_runtime_cohort_sha256")
        == input_runtime_cohort_sha256
        and row.get("target_address_id_semantics")
        == "ALIAS_OF_NATIVE_SKELETON_SELECTION_SHA256",
        "TARGET_ADDRESS_IDENTITY_DRIFT",
    )
    require(row.get("kind") in KINDS, "TARGET_ADDRESS_KIND")
    event_group = prepop_event_group_sha256(
        row, input_runtime_cohort_sha256=input_runtime_cohort_sha256
    )
    require(
        row.get("prepop_event_group_sha256") == event_group
        and row.get("clone_group_id") == event_group,
        "TARGET_ADDRESS_EVENT_GROUP_DRIFT",
    )
    hashes = row.get("target_address_sha256_by_horizon")
    require(
        isinstance(hashes, dict)
        and set(hashes) == {"H_bag", "H_system"}
        and all(
            hashes[horizon]
            == target_address_horizon_sha256(str(address), horizon)
            for horizon in ("H_bag", "H_system")
        )
        and row.get("horizon") == "H_bag"
        and row.get("target_address_sha256") == hashes["H_bag"],
        "TARGET_ADDRESS_HORIZON_BINDING_DRIFT",
    )
    require(
        row.get("seal_level") == "LOCAL_PREPOP_ADDRESS"
        and row.get("full_state_seal") == "DEFERRED_TO_EXECUTED_PAIR"
        and row.get("runtime_state_sha256") is None
        and row.get("boundary_sha256") is None
        and row.get("intervention_sha256") is None
        and row.get("outcome_free") is True,
        "TARGET_ADDRESS_EAGER_FULL_SEAL_FORBIDDEN",
    )
    for eager_field in (
        "intervention_sha256_by_horizon",
        "state_components",
        "kind_name",
        "boundary_kind",
        "queue_top_not_popped",
        "staged_event_sink_empty",
        "runtime_global_scan_count",
        "runtime_future_route_read_count",
        "runtime_future_schedule_read_count",
        "reservation_depth",
        "max_selected_edges_per_bag",
    ):
        require(
            row.get(eager_field) is None,
            f"TARGET_ADDRESS_EAGER_FULL_SEAL_FORBIDDEN:{eager_field}",
        )
    require(
        row.get("baseline_action") != row.get("intervention_action"),
        "TARGET_ADDRESS_ACTION_SAME",
    )
    sampling = row.get("sampling")
    require(isinstance(sampling, dict), "TARGET_ADDRESS_SAMPLING_MISSING")
    N_h = strict_int(sampling.get("N_h"), "target.N_h", 1)
    n_h = strict_int(sampling.get("n_h"), "target.n_h", 1)
    pi_h = strict_float(sampling.get("pi_h"), "target.pi_h")
    weight = strict_float(
        sampling.get("analysis_weight"), "target.analysis_weight"
    )
    require(
        n_h <= N_h
        and math.isclose(pi_h, n_h / N_h, rel_tol=0.0, abs_tol=1e-15)
        and math.isclose(weight, 1.0 / pi_h, rel_tol=1e-12)
        and sampling.get("cluster_id") == event_group
        and sampling.get("cluster_bootstrap_unit")
        == "prepop_event_group_sha256",
        "TARGET_ADDRESS_SAMPLING_DRIFT",
    )
    offline = row.get("offline_sampling_metadata")
    require(
        isinstance(offline, dict)
        and offline.get("must_not_enter_policy_features") is True
        and offline.get("runtime_only") is False,
        "TARGET_ADDRESS_OFFLINE_FEATURE_SCOPE_DRIFT",
    )


def expected_target_address_from_skeleton(
    selected: Mapping[str, Any], *, input_runtime_cohort_sha256: str
) -> dict[str, Any]:
    """Independently reconstruct the exact outcome-free address row."""

    expected = dict(selected)
    address = str(selected.get("skeleton_id", ""))
    require(is_sha256(address), "EXPECTED_TARGET_ADDRESS_SKELETON_ID")
    event_group = prepop_event_group_sha256(
        selected,
        input_runtime_cohort_sha256=input_runtime_cohort_sha256,
    )
    hashes = {
        horizon: target_address_horizon_sha256(address, horizon)
        for horizon in ("H_bag", "H_system")
    }
    sampling = selected.get("sampling")
    require(
        isinstance(sampling, dict),
        "EXPECTED_TARGET_ADDRESS_SAMPLING_MISSING",
    )
    expected_sampling = dict(sampling)
    expected_sampling["cluster_id"] = event_group
    expected_sampling["cluster_bootstrap_unit"] = (
        "prepop_event_group_sha256"
    )
    expected.update(
        {
            "schema": TARGET_ADDRESS_SCHEMA,
            "descriptor_id": address,
            "target_address_id": address,
            "target_address_id_semantics": (
                "ALIAS_OF_NATIVE_SKELETON_SELECTION_SHA256"
            ),
            "population_selection_sha256": address,
            "input_runtime_cohort_sha256": (
                input_runtime_cohort_sha256
            ),
            "prepop_event_group_sha256": event_group,
            "clone_group_id": event_group,
            "seal_level": "LOCAL_PREPOP_ADDRESS",
            "full_state_seal": "DEFERRED_TO_EXECUTED_PAIR",
            "runtime_state_sha256": None,
            "boundary_sha256": None,
            "horizon": "H_bag",
            "target_address_sha256_by_horizon": hashes,
            "target_address_sha256": hashes["H_bag"],
            "sample_sha256": address,
            "sampling": expected_sampling,
        }
    )
    return expected


def validate_terminal_invariants(
    invariants: Any, replay_hashes: Any, *, label: str
) -> None:
    require(isinstance(invariants, dict), f"{label}_INVARIANTS")
    expected = {
        "requested_count": FULL_SEGMENT_COUNT,
        "completed_count": FULL_SEGMENT_COUNT,
        "failed_segment_count": 0,
        "unsafe_entry_count": 0,
        "reservation_conflict_count": 0,
        "runtime_full_astar_call_count": 0,
        "runtime_global_scan_count": 0,
        "runtime_future_route_read_count": 0,
        "runtime_future_schedule_read_count": 0,
        "teacher_input_count": 0,
        "two_step_reservation_count": 0,
        "unresolved_deadlock_count": 0,
        "merge_grant_stale_arbitration_count": 0,
        "stale_arbitration_event_count": 0,
        "merge_grant_outstanding_request_count": 0,
        "merge_grant_final_active_unconsumed": 0,
    }
    for name, value in expected.items():
        require(
            invariants.get(name) == value,
            f"{label}_INVARIANT:{name}",
        )
    require(
        strict_int(invariants.get("event_count"), f"{label}.event_count", 1)
        > 0,
        f"{label}_EVENT_COUNT",
    )
    require(
        invariants.get("max_selected_edges_per_bag") in {0, 1},
        f"{label}_MAX_EDGE",
    )
    for name in ("event_limit_reached", "time_limit_reached"):
        require(invariants.get(name) is False, f"{label}_{name}")
    for name in (
        "merge_grant_conservation_holds",
        "merge_grant_active_bijection_holds",
        "merge_grant_runtime_owned_capability",
        "merge_grant_exact_slot_no_future_shift",
        "live_safety_pass",
        "formal_hard_gate_evaluated",
        "formal_hard_gate_pass",
    ):
        require(invariants.get(name) is True, f"{label}_{name}")
    require(
        strict_float(
            invariants.get("artificial_batch_delay_seconds"),
            f"{label}.artificial_batch_delay_seconds",
        )
        == 0.0
        and invariants.get("hard_gate_fail_reasons") == [],
        f"{label}_TERMINAL_GATE",
    )
    require(
        isinstance(replay_hashes, dict)
        and set(replay_hashes)
        == {
            "complete_bags_sha256",
            "segment_result_sha256",
            "junction_state_sha256",
            "algorithm_summary_sha256",
            "deterministic_result_sha256",
        }
        and all(is_sha256(value) for value in replay_hashes.values()),
        f"{label}_REPLAY_HASHES",
    )


def validate_skeleton(row: Mapping[str, Any]) -> None:
    require(
        row.get("schema") == SKELETON_SCHEMA
        and row.get("kind") in KINDS,
        "SKELETON_SCHEMA_OR_KIND",
    )
    require(
        is_sha256(row.get("skeleton_id"))
        and row.get("skeleton_id")
        == row.get("skeleton_selection_sha256")
        and is_sha256(row.get("population_group_sha256")),
        "SKELETON_IDENTITY",
    )
    require(
        row.get("outcome_free") is True
        and row.get("runtime_state_sha256") is None
        and row.get("boundary_sha256") is None,
        "SKELETON_OUTCOME_LEAKAGE",
    )
    alternatives = strict_int(
        row.get("alternative_action_count"),
        "skeleton.alternative_action_count",
        1,
    )
    require(
        row.get("candidate_action_count") == alternatives
        and row.get("total_legal_action_count") == alternatives + 1
        and row.get("baseline_action") != row.get("intervention_action"),
        "SKELETON_ACTION_COUNT_OR_CHANGE",
    )
    sampling = row.get("sampling")
    require(
        not isinstance(sampling, dict),
        "FULL_SKELETON_POPULATION_MUST_NOT_HAVE_SELECTION_SAMPLING",
    )


def validate_skeleton_population_dataset(
    root: Path,
    binding: Mapping[str, Any],
    *,
    expected_row_count: int,
) -> tuple[list[dict[str, Any]], set[str], Counter[str]]:
    """Validate the complete ordered census across deterministic shards."""

    require(
        binding.get("encoding") == "SHARDED_CANONICAL_JSONL_ZSTD",
        "SKELETON_DATASET_ENCODING",
    )
    rows_per_shard = strict_int(
        binding.get("rows_per_shard"),
        "skeleton_population.rows_per_shard",
        1,
    )
    require(
        rows_per_shard <= SKELETON_ROWS_PER_SHARD,
        "SKELETON_ROWS_PER_SHARD_EXCEEDS_MAXIMUM",
    )
    require(
        isinstance(expected_row_count, int)
        and not isinstance(expected_row_count, bool)
        and expected_row_count > 0,
        "SKELETON_EXPECTED_ROW_COUNT",
    )
    shards = binding.get("shards")
    expected_shard_count = math.ceil(expected_row_count / rows_per_shard)
    require(
        isinstance(shards, list)
        and len(shards) == expected_shard_count
        and binding.get("shard_count") == expected_shard_count
        and binding.get("row_count") == expected_row_count,
        "SKELETON_SHARD_INVENTORY_COUNT",
    )
    expected_paths = [
        (
            SKELETON_DATASET_ROOT
            / f"part-{shard_index:05d}.jsonl.zst"
        ).as_posix()
        for shard_index in range(expected_shard_count)
    ]
    actual_paths = sorted(
        path.relative_to(root).as_posix()
        for path in (root / SKELETON_DATASET_ROOT).glob(
            "part-*.jsonl.zst"
        )
        if path.is_file()
    )
    require(
        actual_paths == expected_paths,
        "SKELETON_SHARD_DIRECTORY_INVENTORY_DRIFT",
    )

    digest = hashlib.sha256()
    digest.update(b"[")
    total_rows = 0
    skeletons: list[dict[str, Any]] = []
    skeleton_ids: set[str] = set()
    skeleton_groups: set[tuple[str, str]] = set()
    population_by_kind: Counter[str] = Counter()
    for shard_index, shard in enumerate(shards):
        require(
            isinstance(shard, dict),
            f"SKELETON_SHARD_NOT_OBJECT:{shard_index}",
        )
        expected_relative = (
            SKELETON_DATASET_ROOT
            / f"part-{shard_index:05d}.jsonl.zst"
        ).as_posix()
        require(
            shard.get("path") == expected_relative,
            f"SKELETON_SHARD_PATH_DRIFT:{shard_index}",
        )
        path = root / Path(expected_relative)
        byte_count = publishable_byte_count(
            path, f"skeleton_population_part_{shard_index:05d}"
        )
        require(
            file_sha256(path) == shard.get("sha256")
            and byte_count == shard.get("byte_count")
            and shard.get("row_start") == total_rows,
            f"SKELETON_SHARD_BINDING_DRIFT:{shard_index}",
        )
        rows = zstd_jsonl(path)
        require(
            len(rows) == shard.get("row_count")
            and len(rows) > 0
            and len(rows) <= rows_per_shard
            and shard.get("row_end_exclusive")
            == total_rows + len(rows),
            f"SKELETON_SHARD_CONTENT_DRIFT:{shard_index}",
        )
        if shard_index + 1 < expected_shard_count:
            require(
                len(rows) == rows_per_shard,
                f"SKELETON_NONFINAL_SHARD_NOT_FULL:{shard_index}",
            )
        shard_digest = hashlib.sha256()
        shard_digest.update(b"[")
        for local_index, skeleton in enumerate(rows):
            encoded = canonical_bytes(skeleton)
            if local_index:
                shard_digest.update(b",")
            shard_digest.update(encoded)
            if total_rows:
                digest.update(b",")
            digest.update(encoded)
            validate_skeleton(skeleton)
            skeleton_id = str(skeleton["skeleton_id"])
            group = (
                str(skeleton["kind"]),
                str(skeleton["population_group_sha256"]),
            )
            require(
                skeleton_id not in skeleton_ids
                and group not in skeleton_groups,
                "DUPLICATE_SKELETON_POPULATION",
            )
            skeleton_ids.add(skeleton_id)
            skeleton_groups.add(group)
            population_by_kind[str(skeleton["kind"])] += 1
            skeletons.append(skeleton)
            total_rows += 1
        shard_digest.update(b"]")
        require(
            shard_digest.hexdigest() == shard.get("content_sha256"),
            f"SKELETON_SHARD_CONTENT_DRIFT:{shard_index}",
        )
    digest.update(b"]")
    require(
        total_rows == expected_row_count
        and digest.hexdigest() == binding.get("content_sha256"),
        "SKELETON_POPULATION_COUNT_OR_HASH_DRIFT",
    )
    return skeletons, skeleton_ids, population_by_kind


def hash_rank(namespace: str, identifier: str) -> str:
    return hashlib.sha256(f"{namespace}:{identifier}".encode()).hexdigest()


def allocate(
    capacities: Mapping[str, int],
    total: int,
    weights: Mapping[str, float],
    *,
    minimum_each: int = 0,
) -> dict[str, int]:
    require(total <= sum(capacities.values()), "ALLOCATION_EXCEEDS_CAPACITY")
    allocation = {
        key: min(capacity, minimum_each)
        for key, capacity in capacities.items()
    }
    remaining = total - sum(allocation.values())
    if remaining < 0:
        for key in sorted(allocation, reverse=True):
            take = min(allocation[key], -remaining)
            allocation[key] -= take
            remaining += take
            if remaining == 0:
                break
    while remaining:
        available = [
            key
            for key in capacities
            if allocation[key] < capacities[key]
        ]
        denominator = sum(max(0.0, weights[key]) for key in available)
        scores = (
            {key: max(0.0, weights[key]) for key in available}
            if denominator > 0.0
            else {key: 1.0 for key in available}
        )
        denominator = sum(scores.values())
        quotas = {
            key: remaining * scores[key] / denominator
            for key in available
        }
        additions = {
            key: min(
                capacities[key] - allocation[key],
                int(math.floor(quotas[key])),
            )
            for key in available
        }
        added = sum(additions.values())
        if added:
            for key, count in additions.items():
                allocation[key] += count
            remaining -= added
            continue
        for key in sorted(
            available,
            key=lambda item: (
                -(quotas[item] - math.floor(quotas[item])),
                item,
            ),
        ):
            if not remaining:
                break
            allocation[key] += 1
            remaining -= 1
    return allocation


def validate_descriptor_bundle(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    current_protected = protected_inputs(root)
    manifest = load_json(root / DESCRIPTOR_MANIFEST_PATH)
    validate_self_hash(manifest, "descriptor_manifest")
    require(
        manifest.get("schema") == DESCRIPTOR_MANIFEST_SCHEMA
        and manifest.get("status") == "READY_FOR_PILOT",
        "DESCRIPTOR_MANIFEST_NOT_READY_FOR_PILOT",
    )
    require(manifest.get("formal_pass_claimed") is False, "SCAN_FORMAL_CLAIM")
    require(manifest.get("scale_count") == 0, "SCALE_COUNT_NONZERO")
    bound_protected = manifest.get("protected_inputs")
    require(isinstance(bound_protected, dict), "PROTECTED_INPUT_BINDING_MISSING")
    bound_task = bound_protected.get("task")
    require(
        isinstance(bound_task, dict)
        and bound_task.get("raw_sha256") == TASK_RAW_SHA256
        and bound_task.get("segment_count") == FULL_SEGMENT_COUNT
        and bound_task.get("raw_bag_count") == FULL_RAW_BAG_COUNT
        and bound_task.get("runtime_segment_mapping_sha256")
        == current_protected["runtime_segment_mapping_sha256"]
        and bound_task.get("raw_bag_mapping_sha256")
        == current_protected["raw_bag_mapping_sha256"]
        and bound_task.get("input_runtime_cohort_sha256")
        == current_protected["input_runtime_cohort_sha256"]
        and bound_task.get("raw_bag_original_entry_mapping_sha256")
        == current_protected[
            "raw_bag_original_entry_mapping_sha256"
        ],
        "PROTECTED_TASK_MAPPING_BINDING_DRIFT",
    )
    require(
        bound_protected.get("map", {}).get("raw_sha256") == MAP_RAW_SHA256
        and bound_protected.get("model", {}).get("raw_sha256") == MODEL_SHA256,
        "PROTECTED_MAP_MODEL_BINDING_DRIFT",
    )
    validate_source_identity(root, manifest.get("source_identity", {}))
    validate_build_manifest(
        root, manifest.get("exact_binary_build_manifest", {})
    )
    binary = manifest.get("binary")
    require(isinstance(binary, dict), "SCAN_BINARY_MISSING")
    require(
        binary.get("sha256_before") == binary.get("sha256_after")
        and binary.get("unchanged") is True
        and is_sha256(binary.get("sha256_before")),
        "SCAN_BINARY_NOT_EXACT",
    )
    require(
        isinstance(binary.get("peak_resident_bytes"), int)
        and binary["peak_resident_bytes"] > 0
        and isinstance(binary.get("skeleton_scan_call"), dict)
        and binary.get("descriptor_materialization_call") is None
        and binary.get(
            "full_state_digest_count_during_target_frame_publication"
        )
        == 0,
        "SCAN_RSS_PROFILE_MISSING",
    )
    controls = manifest.get("frozen_controls")
    require(isinstance(controls, dict), "SCAN_FROZEN_CONTROLS_MISSING")
    for name, expected in FROZEN_CONTROLS.items():
        require(
            controls.get(name) == expected,
            f"SCAN_FROZEN_CONTROL_DRIFT:{name}",
        )
    scan = manifest.get("native_scan_summary")
    require(
        isinstance(scan, dict)
        and scan.get("schema") == SKELETON_SCAN_SCHEMA
        and scan.get("evidence_scope")
        == "OUTCOME_FREE_NATIVE_PREPOP_SKELETON_CENSUS"
        and scan.get("census_complete") is True
        and scan.get("terminal_finalized") is True
        and scan.get("protected_full_1x_shape") is True
        and scan.get("sealed_descriptor_materialization_required")
        is False
        and scan.get("target_address_frame_required") is True
        and scan.get("full_state_seal_policy")
        == "DEFERRED_TO_EXECUTED_PAIR",
        "NATIVE_SKELETON_CENSUS_NOT_COMPLETE",
    )
    validate_terminal_invariants(
        scan.get("terminal_invariants"),
        scan.get("terminal_replay_hashes"),
        label="SKELETON_CENSUS",
    )
    require(
        scan.get("input_request_count") == FULL_SEGMENT_COUNT
        and scan.get("raw_bag_count") == FULL_RAW_BAG_COUNT
        and scan.get("input_runtime_cohort_sha256")
        == current_protected["input_runtime_cohort_sha256"]
        and scan.get("h_system_cohort_mapping_sha256")
        == current_protected["runtime_segment_mapping_sha256"]
        and scan.get("raw_bag_mapping_sha256")
        == current_protected["raw_bag_mapping_sha256"]
        and scan.get("raw_bag_original_entry_mapping_sha256")
        == current_protected[
            "raw_bag_original_entry_mapping_sha256"
        ],
        "NATIVE_SKELETON_INPUT_BINDING_DRIFT",
    )
    skeleton_binding = manifest.get("skeleton_population_dataset")
    require(
        isinstance(skeleton_binding, dict),
        "SKELETON_DATASET_BINDING_MISSING",
    )
    expected_population_count = strict_int(
        scan.get("primary_population_count"),
        "native_scan_summary.primary_population_count",
        1,
    )
    require(
        manifest.get("skeleton_population_count")
        == manifest.get("target_address_population_count")
        == expected_population_count,
        "SKELETON_POPULATION_MANIFEST_COUNT_DRIFT",
    )
    skeletons, skeleton_ids, population_by_kind = (
        validate_skeleton_population_dataset(
            root,
            skeleton_binding,
            expected_row_count=expected_population_count,
        )
    )
    native_counts = scan.get("population_counts")
    require(
        isinstance(native_counts, dict)
        and set(native_counts) == set(KINDS),
        "NATIVE_SKELETON_KIND_COUNTS",
    )
    for kind in KINDS:
        require(
            native_counts[kind].get("primary_population_count")
            == native_counts[kind].get(
                "unique_population_group_count"
            )
            == population_by_kind[kind],
            f"NATIVE_SKELETON_KIND_COUNT_DRIFT:{kind}",
        )
    materialization = manifest.get("target_address_frame_summary")
    require(
        isinstance(materialization, dict)
        and materialization.get("schema") == TARGET_ADDRESS_SCHEMA
        and materialization.get("evidence_scope")
        == "OUTCOME_FREE_LOCAL_PREPOP_TARGET_FRAME"
        and materialization.get("selected_skeleton_count")
        == materialization.get("target_address_count")
        == manifest.get("selected_skeleton_count")
        == manifest.get("target_address_count")
        and materialization.get("full_state_digest_count") == 0
        and materialization.get("full_state_seal_policy")
        == "DEFERRED_TO_EXECUTED_PAIR"
        and materialization.get("false_positive_policy")
        == "RETAIN_ATTEMPT_IF_ADDRESS_DOES_NOT_RESOLVE_UNIQUELY"
        and manifest.get("full_state_sealed_descriptor_count") == 0,
        "TARGET_ADDRESS_FRAME_COUNT_OR_SCOPE_DRIFT",
    )
    require(
        materialization.get("input_request_count") == FULL_SEGMENT_COUNT
        and materialization.get("raw_bag_count") == FULL_RAW_BAG_COUNT
        and materialization.get("input_runtime_cohort_sha256")
        == current_protected["input_runtime_cohort_sha256"]
        and materialization.get("h_system_cohort_mapping_sha256")
        == current_protected["runtime_segment_mapping_sha256"]
        and materialization.get("raw_bag_mapping_sha256")
        == current_protected["raw_bag_mapping_sha256"]
        and materialization.get(
            "raw_bag_original_entry_mapping_sha256"
        )
        == current_protected[
            "raw_bag_original_entry_mapping_sha256"
        ],
        "TARGET_ADDRESS_INPUT_BINDING_DRIFT",
    )
    offline = manifest.get("offline_sampling_input")
    require(isinstance(offline, dict), "OFFLINE_BINDING_MISSING")
    require(
        offline.get("path") == OFFLINE_TAIL_PATH.as_posix()
        and file_sha256(root / OFFLINE_TAIL_PATH) == offline.get("sha256")
        and offline.get("runtime_feature_allowed") is False,
        "OFFLINE_SAMPLING_BINDING_DRIFT",
    )
    dataset = manifest.get("target_address_dataset")
    require(isinstance(dataset, dict), "TARGET_ADDRESS_DATASET_BINDING_MISSING")
    dataset_path = root / Path(str(dataset.get("path", "")))
    require(dataset_path == root / DESCRIPTOR_DATASET_PATH, "TARGET_ADDRESS_DATASET_PATH")
    require(
        file_sha256(dataset_path) == dataset.get("sha256")
        and dataset.get("encoding") == "CANONICAL_JSONL_ZSTD"
        and dataset.get("byte_count") == dataset_path.stat().st_size
        and 0 < dataset_path.stat().st_size < GITHUB_SAFE_ARTIFACT_MAX_BYTES,
        "TARGET_ADDRESS_DATASET_HASH_OR_STORAGE_DRIFT",
    )
    rows = zstd_jsonl(dataset_path)
    require(len(rows) >= 4_096, "TARGET_ADDRESS_FRAME_BELOW_4096")
    require(len(rows) == manifest.get("target_address_frame_count"), "TARGET_ADDRESS_FRAME_COUNT_DRIFT")
    require(canonical_sha256(rows) == manifest.get("target_address_frame_sha256"), "TARGET_ADDRESS_FRAME_CONTENT_DRIFT")
    seen: set[str] = set()
    seen_selected_skeletons: set[str] = set()
    by_stratum: Counter[str] = Counter()
    for row in rows:
        validate_target_address(
            row,
            input_runtime_cohort_sha256=current_protected[
                "input_runtime_cohort_sha256"
            ],
        )
        descriptor = str(row["descriptor_id"])
        selected_skeleton_id = str(row.get("skeleton_id", ""))
        require(
            selected_skeleton_id in skeleton_ids
            and selected_skeleton_id not in seen_selected_skeletons,
            "DESCRIPTOR_SKELETON_ONE_TO_ONE_DRIFT",
        )
        seen_selected_skeletons.add(selected_skeleton_id)
        require(descriptor not in seen, f"DUPLICATE_DESCRIPTOR:{descriptor}")
        seen.add(descriptor)
        by_stratum[str(row["sampling"]["sampling_stratum_id"])] += 1
    sampling_design = manifest.get("sampling_design")
    require(
        isinstance(sampling_design, dict)
        and sampling_design.get("name")
        == "TAIL_ENRICHED_STRATIFIED_DETERMINISTIC_MIN_HASH"
        and sampling_design.get("randomization_surrogate")
        == "SHA256_PSEUDORANDOM_ORDER"
        and sampling_design.get("population_estimation")
        == "REFERENCE_DESIGN_WEIGHTS_ONLY_NOT_ORIGINAL_POPULATION_ATE"
        and sampling_design.get("variance_estimation")
        == (
            "ACTUAL_DETERMINISTIC_PREPOP_EVENT_GROUP_BOOTSTRAP_"
            "AT_FORMAL_FINALIZE"
        ),
        "TARGET_ADDRESS_SAMPLING_DESIGN_POLICY_DRIFT",
    )
    strata = sampling_design.get("strata")
    require(isinstance(strata, dict), "SAMPLING_STRATA_MISSING")
    expected_selected: list[dict[str, Any]] = []
    population_strata: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for skeleton in skeletons:
        population_strata[str(skeleton["sampling_stratum_id"])].append(
            skeleton
        )
    require(set(population_strata) == set(strata), "POPULATION_STRATA_DRIFT")
    for stratum, population_rows in sorted(population_strata.items()):
        design = strata[stratum]
        require(isinstance(design, dict), f"BAD_STRATUM_DESIGN:{stratum}")
        N_h = len(population_rows)
        n_h = strict_int(design.get("n_h"), f"{stratum}.n_h", 1)
        base_n = strict_int(
            design.get("population_min_hash_n"),
            f"{stratum}.population_min_hash_n",
        )
        require(
            design.get("N_h") == N_h
            and n_h <= N_h
            and base_n <= n_h
            and math.isclose(
                float(design.get("pi_h")),
                n_h / N_h,
                abs_tol=1e-15,
            ),
            f"POPULATION_STRATUM_DESIGN_DRIFT:{stratum}",
        )
        ranked = sorted(
            population_rows,
            key=lambda row: (
                hash_rank("g4irsf15-population", row["skeleton_id"]),
                int(row["event_ordinal"]),
            ),
        )
        for rank, skeleton in enumerate(ranked[:n_h], start=1):
            sampling = {
                **design,
                "sampling_stratum_id": stratum,
                "rank_within_stratum": rank,
                "selection_panel": (
                    "POPULATION_MIN_HASH"
                    if rank <= base_n
                    else "ENRICHED_TAIL_MIN_HASH"
                    if "|TAIL|" in stratum
                    else "STRATIFIED_MIN_HASH_FILL"
                ),
                "rank_sha256": hash_rank(
                    "g4irsf15-population", skeleton["skeleton_id"]
                ),
                "cluster_id": skeleton["skeleton_id"],
                "cluster_bootstrap_unit": (
                    "skeleton_id_pending_target_address_frame"
                ),
            }
            expected_selected.append({**skeleton, "sampling": sampling})
    expected_selected.sort(
        key=lambda row: (
            str(row["kind"]),
            hash_rank("g4irsf15-pool-order", row["skeleton_id"]),
        )
    )
    require(
        len(expected_selected)
        == manifest.get("selected_skeleton_count")
        == len(rows)
        and {str(row["skeleton_id"]) for row in expected_selected}
        == seen_selected_skeletons,
        "SELECTED_SKELETON_INVENTORY_DRIFT",
    )
    require(
        canonical_sha256(
            [
                {
                    "skeleton_id": row["skeleton_id"],
                    "population_group_sha256": row[
                        "population_group_sha256"
                    ],
                    "kind": row["kind"],
                    "event_ordinal": row["event_ordinal"],
                    "sampling": row["sampling"],
                }
                for row in expected_selected
            ]
        )
        == manifest.get("selected_skeleton_inventory_sha256"),
        "SELECTED_SKELETON_INVENTORY_SHA_DRIFT",
    )
    expected_by_skeleton = {
        str(row["skeleton_id"]): row for row in expected_selected
    }
    for descriptor in rows:
        selected = expected_by_skeleton[str(descriptor["skeleton_id"])]
        require(
            descriptor
            == expected_target_address_from_skeleton(
                selected,
                input_runtime_cohort_sha256=current_protected[
                    "input_runtime_cohort_sha256"
                ],
            ),
            "TARGET_ADDRESS_SKELETON_MATERIALIZATION_DRIFT",
        )
    for stratum, count in by_stratum.items():
        design = strata.get(stratum)
        require(isinstance(design, dict), f"STRATUM_DESIGN_MISSING:{stratum}")
        require(count == design.get("n_h"), f"STRATUM_N_H_DRIFT:{stratum}")
    coverage_binding = manifest.get("coverage_table")
    require(isinstance(coverage_binding, dict), "COVERAGE_TABLE_BINDING_MISSING")
    coverage_path = root / Path(str(coverage_binding.get("path", "")))
    require(
        file_sha256(coverage_path) == coverage_binding.get("sha256"),
        "COVERAGE_TABLE_HASH_DRIFT",
    )
    with coverage_path.open("r", encoding="utf-8", newline="") as handle:
        coverage_rows = list(csv.DictReader(handle))
    required_tags = (
        "top_tail",
        "non_tail",
        "no_divergence",
        "route_divergence",
        "entry_early",
        "entry_normal",
        "entry_late",
        "slack_tight",
        "slack_ample",
        "direct",
        "storage",
        "goal_48",
        "goal_49",
        "goal_50",
        "hour_6",
        "hour_other",
        "source_0_1_2_53",
        "source_3_4_5",
        "node_52",
        "node_19_22",
        "low_contention",
        "high_contention",
        "p2_prefilter_candidate",
    )
    population_tags: Counter[str] = Counter()
    selected_tags: Counter[str] = Counter()
    for row in skeletons:
        population_tags.update(row.get("coverage_tags", []))
    for row in expected_selected:
        selected_tags.update(row.get("coverage_tags", []))
    expected_category_rows: list[dict[str, str]] = []
    expected_coverage_blockers: list[str] = []
    for tag in required_tags:
        population_count = population_tags[tag]
        selected_count = selected_tags[tag]
        status = (
            "COVERED"
            if selected_count > 0
            else "ZERO_ELIGIBLE_SUPPORT"
            if population_count == 0
            else "SAMPLE_COVERAGE_MISS"
        )
        if status != "COVERED":
            expected_coverage_blockers.append(f"{tag}:{status}")
        expected_category_rows.append(
            {
                "row_type": "REQUIRED_CATEGORY",
                "coverage_dimension": tag,
                "sampling_stratum_id": "",
                "N_population": str(population_count),
                "n_descriptor_pool": str(selected_count),
                "N_h": "",
                "n_h": "",
                "pi_h": "",
                "analysis_weight": "",
                "coverage_status": status,
            }
        )
    expected_category_rows.append(
        {
            "row_type": "REQUIRED_CATEGORY",
            "coverage_dimension": "random_eligible_control",
            "sampling_stratum_id": "",
            "N_population": str(len(skeletons)),
            "n_descriptor_pool": str(
                sum(
                    row["sampling"]["selection_panel"]
                    == "POPULATION_MIN_HASH"
                    for row in expected_selected
                )
            ),
            "N_h": "",
            "n_h": "",
            "pi_h": "",
            "analysis_weight": "",
            "coverage_status": "COVERED",
        }
    )
    actual_category_rows = [
        row
        for row in coverage_rows
        if row.get("row_type") == "REQUIRED_CATEGORY"
    ]
    bound_coverage_blockers = manifest.get(
        "sampling_design", {}
    ).get("coverage_blockers")
    require(
        actual_category_rows == expected_category_rows
        and bound_coverage_blockers == expected_coverage_blockers
        and not any(
            blocker.endswith(":SAMPLE_COVERAGE_MISS")
            for blocker in expected_coverage_blockers
        ),
        "REQUIRED_CATEGORY_COVERAGE_OR_BLOCKER_DRIFT",
    )
    stratum_rows = {
        row["sampling_stratum_id"]: row
        for row in coverage_rows
        if row.get("row_type") == "SAMPLING_STRATUM"
    }
    require(set(stratum_rows) == set(strata), "COVERAGE_STRATUM_INVENTORY_DRIFT")
    for stratum, design in strata.items():
        row = stratum_rows[stratum]
        require(int(row["N_h"]) == design["N_h"], f"COVERAGE_N_H:{stratum}")
        require(int(row["n_h"]) == design["n_h"], f"COVERAGE_n_h:{stratum}")
        require(
            math.isclose(float(row["pi_h"]), design["pi_h"], abs_tol=1e-15),
            f"COVERAGE_PI_H:{stratum}",
        )
    checkpoint = load_json(root / CHECKPOINT_MANIFEST_PATH)
    validate_self_hash(checkpoint, "checkpoint_manifest")
    require(
        checkpoint.get("schema") == CHECKPOINT_MANIFEST_SCHEMA,
        "CHECKPOINT_SCHEMA",
    )
    require(
        checkpoint.get("status")
        == "IMPLEMENTED_AS_NATIVE_OPAQUE_IN_MEMORY_CHECKPOINTS"
        and checkpoint.get("formal_pass_claimed") is False
        and checkpoint.get("checkpoint_storage") == "NOT_SERIALIZED"
        and checkpoint.get("checkpoint_policy")
        == (
            "FRESH_PROCESS_DETERMINISTIC_PREFIX_REPLAY_THEN_ONE_OPAQUE_"
            "IN_MEMORY_CHECKPOINT_PER_TARGET_EVENT_ORDINAL"
        )
        and checkpoint.get("runtime_scope")
        == "OFFLINE_CAMPAIGN_ONLY_NOT_RUNTIME_POLICY"
        and checkpoint.get("crash_recovery")
        == "ATOMIC_SHARD_RESUME_REPLAYS_PREFIX_IN_A_FRESH_PROCESS"
        and checkpoint.get("no_op_fidelity_requirement")
        == (
            "EVERY_PAIR_REQUIRES_IDENTICAL_SOURCE_BASELINE_TREATMENT_"
            "START_STATE_SHA256"
        )
        and checkpoint.get("descriptor_manifest_self_sha256")
        == manifest["self_sha256"]
        and checkpoint.get("exact_binary_build_manifest")
        == manifest.get("exact_binary_build_manifest")
        and checkpoint.get("source_bundle_sha256")
        == manifest.get("source_identity", {}).get("source_bundle_sha256"),
        "CHECKPOINT_POLICY_OR_PROVENANCE_BINDING_DRIFT",
    )
    checkpoint_binary = checkpoint.get("binary")
    require(
        isinstance(checkpoint_binary, dict)
        and checkpoint_binary.get("path") == binary.get("path")
        and checkpoint_binary.get("sha256_before")
        == checkpoint_binary.get("sha256_after")
        == binary.get("sha256_before")
        and checkpoint_binary.get("unchanged") is True,
        "CHECKPOINT_BINARY_BINDING_DRIFT",
    )
    return rows, manifest


def screening_clause_matches(
    descriptor: Mapping[str, Any],
    clause: Mapping[str, Any],
) -> bool:
    require(
        set(clause) == {"field", "operator", "value"},
        "SCREENING_REVISION_CLAUSE_FIELDS",
    )
    field = str(clause.get("field", ""))
    operator = str(clause.get("operator", ""))
    require(
        field in OUTCOME_FREE_SCREENING_FIELDS,
        f"SCREENING_REVISION_OUTCOME_OR_ID_FIELD_FORBIDDEN:{field}",
    )
    actual = descriptor.get(field)
    expected = clause.get("value")
    if operator == "EQ":
        return actual == expected
    if operator == "NE":
        return actual != expected
    if operator in {"IN", "NOT_IN"}:
        require(
            isinstance(expected, list) and expected,
            "SCREENING_REVISION_IN_VALUE_NOT_LIST",
        )
        matched = actual in expected
        return matched if operator == "IN" else not matched
    if operator in {"CONTAINS", "NOT_CONTAINS"}:
        require(
            isinstance(actual, list),
            f"SCREENING_REVISION_CONTAINS_NON_LIST:{field}",
        )
        matched = expected in actual
        return matched if operator == "CONTAINS" else not matched
    if operator in {"LT", "LTE", "GT", "GTE"}:
        require(
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and isinstance(expected, (int, float))
            and not isinstance(expected, bool),
            f"SCREENING_REVISION_ORDER_NON_NUMERIC:{field}",
        )
        return {
            "LT": actual < expected,
            "LTE": actual <= expected,
            "GT": actual > expected,
            "GTE": actual >= expected,
        }[operator]
    raise ValidationError(
        f"SCREENING_REVISION_OPERATOR_FORBIDDEN:{operator}"
    )


def apply_screening_revision_predicate(
    pool: Sequence[Mapping[str, Any]],
    predicate: Mapping[str, Any],
) -> list[dict[str, Any]]:
    clauses = predicate.get("exclude_if_any")
    require(
        predicate.get("schema")
        == OUTCOME_FREE_SCREENING_PREDICATE_SCHEMA
        and predicate.get("decision")
        == "ELIGIBLE_UNLESS_ANY_EXCLUSION_CLAUSE_MATCHES"
        and predicate.get("allowed_input_fields")
        == list(OUTCOME_FREE_SCREENING_FIELDS)
        and predicate.get("outcome_fields_used") == []
        and isinstance(clauses, list)
        and clauses,
        "SCREENING_REVISION_PREDICATE_CONTRACT",
    )
    return [
        dict(row)
        for row in pool
        if not any(
            screening_clause_matches(row, clause)
            for clause in clauses
        )
    ]


def validate_screening_revision(
    *,
    root: Path,
    pool: Sequence[Mapping[str, Any]],
    descriptor_manifest: Mapping[str, Any],
    round1_result: Mapping[str, Any],
    round1_binding: Mapping[str, Any],
    round1_descriptor_ids: set[str],
    failed_kinds: set[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = root / PILOT_SCREENING_REVISION_PATH
    revision = load_json(path)
    validate_self_hash(revision, "pilot_screening_revision")
    require(
        revision.get("schema") == PILOT_SCREENING_REVISION_SCHEMA
        and revision.get("status")
        == "READY_FOR_ONE_REPLACEMENT_ROUND"
        and revision.get("formal_pass_claimed") is False,
        "SCREENING_REVISION_SCHEMA_OR_STATUS",
    )
    require(
        revision.get("prior_pilot_result") == round1_binding
        and revision.get("r1_false_positive_evidence")
        == round1_result.get("round_false_positive_evidence"),
        "SCREENING_REVISION_R1_EVIDENCE_BINDING_DRIFT",
    )
    expected_frozen = {
        "descriptor_manifest_self_sha256": descriptor_manifest[
            "self_sha256"
        ],
        "source_bundle_sha256": descriptor_manifest["source_identity"][
            "source_bundle_sha256"
        ],
        "binary_sha256": descriptor_manifest["binary"]["sha256_before"],
        "build_manifest_self_sha256": descriptor_manifest[
            "exact_binary_build_manifest"
        ]["self_sha256"],
        "native_scan_summary_sha256": canonical_sha256(
            descriptor_manifest["native_scan_summary"]
        ),
        "skeleton_population_content_sha256": descriptor_manifest[
            "skeleton_population_dataset"
        ]["content_sha256"],
        "target_address_frame_sha256": descriptor_manifest[
            "target_address_frame_sha256"
        ],
    }
    require(
        revision.get("frozen_campaign") == expected_frozen,
        "SCREENING_REVISION_FROZEN_CAMPAIGN_DRIFT",
    )
    require(
        revision.get("revision_scope")
        == {
            "same_frozen_source_binary_census": True,
            "changes_binary_or_descriptor_definition": False,
            "screening_only_repair": True,
            "predicate_inputs_are_outcome_free": True,
            "revision_selected_using_r1_diagnostic_evidence": True,
            "per_target_r1_outcomes_directly_used_by_predicate": False,
            "replacement_round_limit": 1,
        },
        "SCREENING_REVISION_SCOPE_DRIFT",
    )
    predicate = revision.get("outcome_free_predicate")
    require(
        isinstance(predicate, dict),
        "SCREENING_REVISION_PREDICATE_MISSING",
    )
    revised_pool = apply_screening_revision_predicate(pool, predicate)
    rationales = revision.get("clause_rationales")
    observed_reason_codes = set(
        round1_result["round_false_positive_evidence"][
            "reason_counts"
        ]
    )
    require(
        isinstance(rationales, list)
        and len(rationales) == len(predicate["exclude_if_any"])
        and all(
            isinstance(row, dict)
            and row.get("clause_index") == index
            and isinstance(row.get("r1_reason_codes"), list)
            and bool(row["r1_reason_codes"])
            and set(row["r1_reason_codes"]).issubset(
                observed_reason_codes
            )
            and isinstance(row.get("diagnostic_rationale"), str)
            and bool(row["diagnostic_rationale"].strip())
            for index, row in enumerate(rationales)
        ),
        "SCREENING_REVISION_CLAUSE_RATIONALE_DRIFT",
    )
    revised_ids = sorted(str(row["descriptor_id"]) for row in revised_pool)
    require(
        revision.get("revised_eligible_descriptor_ids") == revised_ids
        and revision.get("revised_eligible_descriptor_ids_sha256")
        == canonical_sha256(revised_ids)
        and revision.get("outcome_free_predicate_sha256")
        == canonical_sha256(predicate)
        and len(revised_pool) < len(pool),
        "SCREENING_REVISION_ELIGIBLE_INVENTORY_DRIFT",
    )
    r1_false_positive = round1_result.get(
        "round_false_positive_evidence"
    )
    require(
        isinstance(r1_false_positive, dict),
        "SCREENING_REVISION_R1_FALSE_POSITIVE_EVIDENCE_MISSING",
    )
    failed_r1_ids = set(
        r1_false_positive.get("noneligible_descriptor_ids", [])
    )
    require(
        all(
            any(
                str(row["descriptor_id"]) in failed_r1_ids
                and str(row["descriptor_id"]) not in set(revised_ids)
                and row.get("kind") == kind
                for row in pool
            )
            for kind in failed_kinds
        ),
        "SCREENING_REVISION_DOES_NOT_REMOVE_FALSE_POSITIVE_PER_FAILED_KIND",
    )
    available = Counter(
        str(row["kind"])
        for row in revised_pool
        if str(row["descriptor_id"]) not in round1_descriptor_ids
    )
    require(
        all(
            available[kind] >= PILOT_ATTEMPTS_PER_KIND
            for kind in failed_kinds
        ),
        "SCREENING_REVISION_INSUFFICIENT_REPLACEMENT_CAPACITY",
    )
    binding = {
        "path": PILOT_SCREENING_REVISION_PATH.as_posix(),
        "sha256": file_sha256(path),
        "byte_count": publishable_byte_count(
            path, "pilot_screening_revision"
        ),
        "self_sha256": revision["self_sha256"],
        "outcome_free_predicate_sha256": revision[
            "outcome_free_predicate_sha256"
        ],
        "revised_eligible_descriptor_ids_sha256": revision[
            "revised_eligible_descriptor_ids_sha256"
        ],
    }
    return revised_pool, binding


def validate_plan(
    root: Path, campaign: str, *, pilot_round: int = 1
) -> dict[str, Any]:
    descriptor_rows, descriptor_manifest = validate_descriptor_bundle(root)
    path = root / (
        PILOT_PLAN_PATH
        if campaign == "pilot" and pilot_round == 1
        else PILOT_ROUND2_PLAN_PATH
        if campaign == "pilot"
        else FORMAL_PLAN_PATH
    )
    plan = load_json(path)
    validate_self_hash(plan, f"{campaign}_plan")
    require(plan.get("schema") == PLAN_SCHEMA, "PLAN_SCHEMA")
    require(plan.get("campaign") == campaign, "PLAN_CAMPAIGN")
    require(plan.get("formal_pass_claimed") is False, "PLAN_FORMAL_CLAIM")
    require(plan.get("scale_count") == 0, "PLAN_SCALE_NONZERO")
    if campaign == "pilot":
        require(
            plan.get("pilot_round") == pilot_round,
            "PLAN_PILOT_ROUND_DRIFT",
        )
    binding = plan.get("descriptor_manifest")
    require(isinstance(binding, dict), "PLAN_DESCRIPTOR_BINDING_MISSING")
    require(
        binding.get("self_sha256") == descriptor_manifest["self_sha256"]
        and binding.get("file_sha256")
        == file_sha256(root / DESCRIPTOR_MANIFEST_PATH),
        "PLAN_DESCRIPTOR_BINDING_DRIFT",
    )
    require(
        plan.get("exact_binary_build_manifest")
        == descriptor_manifest.get("exact_binary_build_manifest"),
        "PLAN_BUILD_MANIFEST_BINDING_DRIFT",
    )
    validate_build_manifest(
        root, plan.get("exact_binary_build_manifest", {})
    )
    descriptor_by_id = {row["descriptor_id"]: row for row in descriptor_rows}
    shards = plan.get("shards")
    require(isinstance(shards, list) and shards, "PLAN_SHARDS_MISSING")
    seen: set[str] = set()
    target_rows: list[dict[str, Any]] = []
    prior_end = -1
    for expected_index, shard in enumerate(shards):
        require(isinstance(shard, dict), "PLAN_SHARD_NOT_OBJECT")
        require(shard.get("shard_index") == expected_index, "SHARD_INDEX_DRIFT")
        projection = dict(shard)
        declared = projection.pop("shard_sha256", None)
        require(declared == canonical_sha256(projection), "SHARD_SHA_DRIFT")
        start = strict_int(shard.get("event_ordinal_start"), "shard_start")
        end = strict_int(shard.get("event_ordinal_end"), "shard_end", start)
        require(start > prior_end, "SHARD_ORDINAL_OVERLAP")
        prior_end = end
        targets = shard.get("targets")
        keys = shard.get("target_keys")
        require(
            isinstance(targets, list)
            and isinstance(keys, list)
            and len(targets) == len(keys) == shard.get("target_count"),
            "SHARD_TARGET_COUNT_DRIFT",
        )
        require(
            shard.get("h_system_target_count")
            == sum(
                row.get("horizon") == "H_system" for row in targets
            )
            and shard.get("h_system_target_count")
            <= plan.get(
                "h_system_targets_per_shard",
                DEFAULT_H_SYSTEM_TARGETS_PER_SHARD,
            ),
            "SHARD_H_SYSTEM_MEMORY_CAP",
        )
        ordinals = [strict_int(row.get("event_ordinal"), "target_ordinal") for row in targets]
        require(min(ordinals) == start and max(ordinals) == end, "SHARD_RANGE_DRIFT")
        for target, key in zip(targets, keys, strict=True):
            require(isinstance(target, dict), "TARGET_NOT_OBJECT")
            require(target.get("target_key") == key, "TARGET_KEY_DRIFT")
            require(key not in seen, f"DUPLICATE_TARGET:{key}")
            seen.add(str(key))
            source = descriptor_by_id.get(target.get("descriptor_id"))
            require(source is not None, "TARGET_NOT_IN_DESCRIPTOR_POOL")
            for field, expected in source.items():
                if field in {
                    "horizon",
                    "target_address_sha256",
                    "sampling",
                }:
                    continue
                require(
                    target.get(field) == expected,
                    f"TARGET_MUTATES_SEALED_DESCRIPTOR:{field}",
                )
            horizon = target.get("horizon")
            require(horizon in {"H_bag", "H_system"}, "TARGET_HORIZON")
            require(
                target.get("intervention_sha256") is None
                and target.get("target_address_sha256")
                == target.get(
                    "target_address_sha256_by_horizon", {}
                ).get(horizon),
                "TARGET_ADDRESS_HORIZON_SHA_NOT_UPDATED",
            )
            require(
                target.get("clone_group_id") == source.get("clone_group_id"),
                "TARGET_CLONE_DRIFT",
            )
            require(
                target.get("source_screening_manifest_sha256")
                == descriptor_manifest["self_sha256"]
                and target.get("source_bundle_sha256")
                == descriptor_manifest["source_identity"][
                    "source_bundle_sha256"
                ]
                and target.get("binary_sha256")
                == descriptor_manifest["binary"]["sha256_before"]
                and target.get("map_raw_sha256") == MAP_RAW_SHA256
                and target.get("task_raw_sha256") == TASK_RAW_SHA256,
                "TARGET_PROVENANCE_BINDING_DRIFT",
            )
            require(
                target.get("h_system_cohort_mapping_sha256")
                == descriptor_manifest["protected_inputs"]["task"][
                    "runtime_segment_mapping_sha256"
                ]
                and target.get("raw_bag_mapping_sha256")
                == descriptor_manifest["protected_inputs"]["task"][
                    "raw_bag_mapping_sha256"
                ]
                and target.get(
                    "raw_bag_original_entry_mapping_sha256"
                )
                == descriptor_manifest["protected_inputs"]["task"][
                    "raw_bag_original_entry_mapping_sha256"
                ],
                "TARGET_COHORT_MAPPING_BINDING_DRIFT",
            )
            require(
                target.get("intervention_id") == key
                and target.get("target_decision_id")
                == (
                    f"{target['target_address_sha256']}:"
                    f"{target['event_seq']}"
                ),
                "TARGET_DECISION_ID_DRIFT",
            )
            target_rows.append(target)
    require(len(seen) == plan.get("attempt_budget"), "PLAN_ATTEMPT_BUDGET")
    execution_policy = plan.get("panel_execution_policy")
    require(
        isinstance(execution_policy, dict)
        and execution_policy.get(
            "publication_requires_complete_preregistered_panel"
        )
        is True
        and execution_policy.get("outcome_dependent_early_stop_allowed")
        is False
        and execution_policy.get("required_shard_indices")
        == list(range(len(shards)))
        and execution_policy.get("required_target_count")
        == len(target_rows),
        "PLAN_PANEL_EXECUTION_POLICY_DRIFT",
    )
    by_kind = Counter(str(row["kind"]) for row in target_rows)
    attempt_strata = Counter(
        str(row.get("sampling", {}).get("sampling_stratum_id"))
        for row in target_rows
    )
    bound_attempt_design = plan.get("attempt_sampling_design")
    require(
        isinstance(bound_attempt_design, dict)
        and isinstance(bound_attempt_design.get("strata"), dict),
        "ATTEMPT_SAMPLING_DESIGN_MISSING",
    )
    require(
        set(attempt_strata) == set(bound_attempt_design["strata"]),
        "ATTEMPT_SAMPLING_STRATUM_INVENTORY",
    )
    for target in target_rows:
        sampling = target.get("sampling")
        address_frame = target.get("target_address_frame_sampling")
        require(
            isinstance(sampling, dict)
            and isinstance(address_frame, dict),
            "TARGET_ATTEMPT_SAMPLING_MISSING",
        )
        stratum = str(sampling.get("sampling_stratum_id"))
        N_h = strict_int(sampling.get("N_h"), f"{stratum}.N_h", 1)
        attempt_n = strict_int(
            sampling.get("attempt_n_h"), f"{stratum}.attempt_n_h", 1
        )
        address_frame_n = strict_int(
            sampling.get("target_address_frame_n_h"),
            f"{stratum}.target_address_frame_n_h",
            1,
        )
        frame_n = strict_int(
            sampling.get("stage2_frame_n_h"),
            f"{stratum}.stage2_frame_n_h",
            1,
        )
        excluded_n = strict_int(
            sampling.get("excluded_before_panel_n_h"),
            f"{stratum}.excluded_before_panel_n_h",
        )
        frame_pi = strict_float(
            sampling.get("frame_pi_h"), f"{stratum}.frame_pi_h"
        )
        survival_pi = strict_float(
            sampling.get("post_exclusion_survival_pi_h"),
            f"{stratum}.survival_pi_h",
        )
        stage2_pi = strict_float(
            sampling.get("stage2_pi_h"), f"{stratum}.stage2_pi_h"
        )
        final_pi = strict_float(
            sampling.get("pi_h"), f"{stratum}.pi_h"
        )
        require(attempt_n == attempt_strata[stratum], "ATTEMPT_n_h_DRIFT")
        require(
            sampling.get("n_h") == attempt_n
            and excluded_n + frame_n == address_frame_n
            and math.isclose(
                frame_pi, address_frame_n / N_h, abs_tol=1e-15
            )
            and math.isclose(
                survival_pi,
                frame_n / address_frame_n,
                abs_tol=1e-15,
            )
            and math.isclose(
                stage2_pi, attempt_n / frame_n, abs_tol=1e-15
            )
            and math.isclose(
                final_pi,
                frame_pi * survival_pi * stage2_pi,
                abs_tol=1e-15,
            )
            and math.isclose(
                float(sampling.get("analysis_weight")),
                1.0 / final_pi,
                abs_tol=1e-12,
            )
            and sampling.get("cluster_id") == target.get("clone_group_id"),
            "ATTEMPT_INCLUSION_PROBABILITY_DRIFT",
        )
        require(
            address_frame.get("N_h") == N_h
            and address_frame.get("n_h")
            == sampling.get("target_address_frame_n_h"),
            "TARGET_ADDRESS_FRAME_TO_ATTEMPT_SAMPLING_BINDING",
        )
        require(
            bound_attempt_design["strata"][stratum]
            == {
                key: sampling[key]
                for key in (
                    "sampling_stratum_id",
                    "N_h",
                    "target_address_frame_n_h",
                    "frame_pi_h",
                    "excluded_before_panel_n_h",
                    "stage2_frame_n_h",
                    "post_exclusion_survival_pi_h",
                    "attempt_n_h",
                    "stage2_pi_h",
                    "pi_h",
                    "analysis_weight",
                    "selection_panel",
                )
            },
            "ATTEMPT_DESIGN_ROW_DRIFT",
        )
    if campaign == "pilot":
        attempted_kinds = list(
            plan.get("pilot_gate", {}).get("attempted_kinds", [])
        )
        require(
            set(attempted_kinds).issubset(KINDS)
            and by_kind
            == Counter(
                {
                    kind: PILOT_ATTEMPTS_PER_KIND
                    for kind in attempted_kinds
                }
            ),
            "PILOT_ATTEMPTS_BY_KIND",
        )
        if pilot_round == 1:
            require(
                attempted_kinds == list(KINDS),
                "PILOT_R1_MUST_ATTEMPT_ALL_KINDS",
            )
            require(
                plan.get("screening_revision") is None,
                "PILOT_R1_MUST_NOT_HAVE_SCREENING_REVISION",
            )
        require(all(row["horizon"] == "H_bag" for row in target_rows), "PILOT_NOT_H_BAG")
        excluded_ids: set[str] = set()
        if pilot_round == 2:
            prior_binding = plan.get("prior_pilot_result")
            require(
                isinstance(prior_binding, dict),
                "PILOT_R2_PRIOR_BINDING_MISSING",
            )
            prior_path = root / Path(str(prior_binding.get("path", "")))
            prior_result = load_json(prior_path)
            validate_self_hash(prior_result, "pilot_r2_bound_r1")
            require(
                file_sha256(prior_path) == prior_binding.get("sha256")
                and prior_result.get("self_sha256")
                == prior_binding.get("self_sha256")
                and prior_result.get("status") == "RESAMPLE_REQUIRED",
                "PILOT_R2_PRIOR_BINDING_DRIFT",
            )
            prior_complete = prior_result.get("complete_by_kind")
            require(
                isinstance(prior_complete, dict)
                and attempted_kinds
                == [
                    kind
                    for kind in KINDS
                    if strict_int(
                        prior_complete.get(kind),
                        f"pilot_r1.complete_by_kind.{kind}",
                    )
                    < PILOT_MIN_COMPLETE_PER_KIND
                ],
                "PILOT_R2_KIND_INVENTORY_NOT_EXACT_FAILED_R1_SET",
            )
            round1_plan = validate_plan(root, "pilot", pilot_round=1)
            excluded_ids = {
                str(row["descriptor_id"])
                for shard in round1_plan["shards"]
                for row in shard["targets"]
            }
            require(
                not (
                    excluded_ids
                    & {
                        str(row["descriptor_id"])
                        for row in target_rows
                    }
                ),
                "PILOT_R1_R2_OVERLAP",
            )
            failed_kinds = set(attempted_kinds)
            revised_pool, revision_binding = (
                validate_screening_revision(
                    root=root,
                    pool=descriptor_rows,
                    descriptor_manifest=descriptor_manifest,
                    round1_result=prior_result,
                    round1_binding=prior_binding,
                    round1_descriptor_ids=excluded_ids,
                    failed_kinds=failed_kinds,
                )
            )
            require(
                plan.get("screening_revision") == revision_binding,
                "PILOT_R2_SCREENING_REVISION_BINDING_DRIFT",
            )
            revised_ids = {
                str(row["descriptor_id"]) for row in revised_pool
            }
            excluded_ids.update(
                str(row["descriptor_id"])
                for row in descriptor_rows
                if str(row["descriptor_id"]) not in revised_ids
            )
        panel_namespace = f"g4irsf15-pilot-r{pilot_round}"
    else:
        preregistration = plan.get("formal_attempt_preregistration")
        require(isinstance(preregistration, dict), "FORMAL_PREREGISTRATION_MISSING")
        require(
            preregistration.get("method")
            == (
                "TARGET_DIVIDED_BY_TWO_SIDED_95_PERCENT_WILSON_LOWER_"
                "ENDPOINT_CAPPED_AT_LOCAL_TARGET_ADDRESS_FRAME"
            )
            and preregistration.get("wilson_interval_convention")
            == (
                "TWO_SIDED_95_PERCENT_LOWER_ENDPOINT_"
                "EQUIVALENT_ONE_SIDED_97_5_PERCENT"
            ),
            "FORMAL_WILSON_CONVENTION_DRIFT",
        )
        per_kind = preregistration.get("per_kind")
        require(isinstance(per_kind, dict), "FORMAL_PREREGISTRATION_PER_KIND")
        active_kinds = list(preregistration.get("active_kinds", []))
        require(
            len(active_kinds) >= 2
            and set(active_kinds).issubset(KINDS)
            and plan.get("active_kinds") == active_kinds,
            "FORMAL_ACTIVE_KIND_INVENTORY",
        )
        expected_attempts = {
            kind: strict_int(
                per_kind.get(kind, {}).get("preregistered_attempts"),
                f"formal_preregistered_attempts.{kind}",
                1,
            )
            for kind in active_kinds
        }
        require(by_kind == Counter(expected_attempts), "FORMAL_ATTEMPT_ALLOCATION")
        excluded = preregistration.get("excluded_pilot_descriptor_ids")
        require(
            isinstance(excluded, list)
            and len(excluded)
            == preregistration.get("excluded_pilot_descriptor_count"),
            "FORMAL_PILOT_EXCLUSION_INVENTORY",
        )
        require(
            canonical_sha256(excluded)
            == preregistration.get("excluded_pilot_descriptor_ids_sha256"),
            "FORMAL_PILOT_EXCLUSION_HASH",
        )
        pilot_result_bindings = plan.get("pilot_results")
        excluded_rounds = preregistration.get("pilot_rounds_excluded")
        require(
            isinstance(pilot_result_bindings, list)
            and isinstance(excluded_rounds, list)
            and [binding.get("pilot_round") for binding in pilot_result_bindings]
            == excluded_rounds,
            "FORMAL_PILOT_ROUND_BINDING_DRIFT",
        )
        exact_pilot_ids: set[str] = set()
        pilot_ids_by_round: dict[int, set[str]] = {}
        pilot_results_by_round: dict[int, dict[str, Any]] = {}
        pilot_bindings_by_round: dict[int, Mapping[str, Any]] = {}
        for result_binding, round_index in zip(
            pilot_result_bindings, excluded_rounds, strict=True
        ):
            require(
                isinstance(result_binding, dict)
                and round_index in {1, 2},
                "FORMAL_PILOT_RESULT_BINDING_ROW",
            )
            result_path = root / Path(str(result_binding.get("path", "")))
            bound_result = load_json(result_path)
            validate_self_hash(
                bound_result, f"formal_excluded_pilot_r{round_index}"
            )
            require(
                file_sha256(result_path) == result_binding.get("sha256")
                and bound_result.get("self_sha256")
                == result_binding.get("self_sha256")
                and bound_result.get("pilot_round") == round_index
                and bound_result.get("status") == result_binding.get("status"),
                "FORMAL_PILOT_RESULT_LIST_BINDING_DRIFT",
            )
            pilot_results_by_round[int(round_index)] = bound_result
            pilot_bindings_by_round[int(round_index)] = result_binding
            pilot_plan = validate_plan(
                root, "pilot", pilot_round=int(round_index)
            )
            round_ids = {
                str(row["descriptor_id"])
                for pilot_shard in pilot_plan["shards"]
                for row in pilot_shard["targets"]
            }
            pilot_ids_by_round[int(round_index)] = round_ids
            exact_pilot_ids.update(round_ids)
        require(
            sorted(exact_pilot_ids) == excluded,
            "FORMAL_PILOT_EXCLUSION_NOT_EXACT_PLAN_UNION",
        )
        require(
            not (
                {str(row["descriptor_id"]) for row in target_rows}
                & {str(value) for value in excluded}
            ),
            "FORMAL_REUSES_PILOT_DESCRIPTOR",
        )
        pilot_binding = plan.get("pilot_result")
        require(isinstance(pilot_binding, dict), "FORMAL_PILOT_RESULT_BINDING")
        pilot_path = root / Path(str(pilot_binding.get("path", "")))
        pilot_result = load_json(pilot_path)
        validate_self_hash(pilot_result, "formal_bound_pilot_result")
        require(
            file_sha256(pilot_path) == pilot_binding.get("sha256")
            and pilot_result.get("self_sha256")
            == pilot_binding.get("self_sha256")
            and pilot_result.get("status")
            in {"PASS_PILOT", "PASS_PILOT_WITH_BLOCKED_KINDS"},
            "FORMAL_PILOT_RESULT_DRIFT",
        )
        pilot_complete = pilot_result.get("complete_by_kind")
        require(isinstance(pilot_complete, dict), "BOUND_PILOT_KIND_COUNTS")
        revision_excluded_ids: set[str] = set()
        if excluded_rounds == [1, 2]:
            round1_result = pilot_results_by_round[1]
            round1_complete = round1_result.get("complete_by_kind")
            require(
                isinstance(round1_complete, dict),
                "FORMAL_R1_COMPLETE_BY_KIND_MISSING",
            )
            failed_r1_kinds = {
                kind
                for kind in KINDS
                if strict_int(
                    round1_complete.get(kind),
                    f"formal_r1.complete_by_kind.{kind}",
                )
                < PILOT_MIN_COMPLETE_PER_KIND
            }
            revised_pool, revision_binding = (
                validate_screening_revision(
                    root=root,
                    pool=descriptor_rows,
                    descriptor_manifest=descriptor_manifest,
                    round1_result=round1_result,
                    round1_binding=pilot_bindings_by_round[1],
                    round1_descriptor_ids=pilot_ids_by_round[1],
                    failed_kinds=failed_r1_kinds,
                )
            )
            require(
                plan.get("screening_revision") == revision_binding
                and pilot_results_by_round[2].get(
                    "screening_revision"
                )
                == revision_binding,
                "FORMAL_R2_SCREENING_REVISION_BINDING_DRIFT",
            )
            revised_ids = {
                str(row["descriptor_id"]) for row in revised_pool
            }
            revision_excluded_ids = {
                str(row["descriptor_id"])
                for row in descriptor_rows
                if str(row["descriptor_id"]) not in revised_ids
            }
        else:
            require(
                excluded_rounds == [1]
                and plan.get("screening_revision") is None,
                "FORMAL_R1_PASS_SCREENING_REVISION_OR_ROUND_DRIFT",
            )
        exact_active_kinds = [
            kind
            for kind in KINDS
            if strict_int(
                pilot_complete.get(kind),
                f"bound_pilot_complete.{kind}",
            )
            >= PILOT_MIN_COMPLETE_PER_KIND
        ]
        exact_blocked_kinds = [
            kind for kind in KINDS if kind not in exact_active_kinds
        ]
        formal_gate = plan.get("formal_gate")
        expected_label_targets = {
            kind: FORMAL_LABEL_TARGETS[kind]
            for kind in exact_active_kinds
        }
        missing_label_target = FORMAL_MIN_LABELS - sum(
            expected_label_targets.values()
        )
        if missing_label_target > 0:
            expected_reallocation = allocate(
                {
                    kind: missing_label_target
                    for kind in exact_active_kinds
                },
                missing_label_target,
                {
                    kind: float(FORMAL_LABEL_TARGETS[kind])
                    for kind in exact_active_kinds
                },
            )
            for kind, extra in expected_reallocation.items():
                expected_label_targets[kind] += extra
        require(
            active_kinds == exact_active_kinds
            and preregistration.get("blocked_kinds")
            == exact_blocked_kinds
            and plan.get("active_kinds") == exact_active_kinds
            and plan.get("blocked_kinds") == exact_blocked_kinds
            and isinstance(formal_gate, dict)
            and formal_gate.get("active_kinds") == exact_active_kinds
            and formal_gate.get("blocked_kinds") == exact_blocked_kinds,
            "FORMAL_ACTIVE_KINDS_NOT_EXACT_PILOT_SUPPORTED_SET",
        )
        require(
            set(per_kind) == set(exact_active_kinds)
            and preregistration.get("blocked_kind_target_reallocation")
            == (
                "NONE_ALL_KINDS_ACTIVE"
                if not exact_blocked_kinds
                else "PREREGISTERED_PROPORTIONAL_TO_ORIGINAL_KIND_TARGETS"
            ),
            "FORMAL_PREREGISTRATION_KIND_INVENTORY_DRIFT",
        )
        expected_formal_gate = {
            "active_kinds": exact_active_kinds,
            "blocked_kinds": exact_blocked_kinds,
            "causal_label_count_min": FORMAL_MIN_LABELS,
            "h_bag_or_stronger_complete_min": FORMAL_MIN_LABELS,
            "h_system_complete_min": FORMAL_MIN_H_SYSTEM,
            "per_kind_label_min": FORMAL_MIN_KIND,
            "initial_label_targets": expected_label_targets,
            "original_label_targets": FORMAL_LABEL_TARGETS,
            "reallocation_allowed": bool(exact_blocked_kinds),
            "minimum_active_kind_count": 2,
            "hard_gate_fail_max": 0,
            "action_changed_rate": 1.0,
            "clone_fidelity": 1.0,
            "future_leakage": 0,
            "split_contamination": 0,
        }
        require(
            formal_gate == expected_formal_gate,
            "FORMAL_GATE_CONTRACT_DRIFT",
        )
        label_targets = preregistration.get("formal_label_targets")
        require(
            label_targets == expected_label_targets,
            "FORMAL_LABEL_TARGET_REALLOCATION_DRIFT",
        )
        for kind in active_kinds:
            registration = per_kind[kind]
            successes = strict_int(
                pilot_complete.get(kind),
                f"bound_pilot_complete.{kind}",
                PILOT_MIN_COMPLETE_PER_KIND,
            )
            lower = wilson_lower_bound(successes, PILOT_ATTEMPTS_PER_KIND)
            requested = int(math.ceil(label_targets[kind] / lower))
            available_after_exclusion = sum(
                row.get("kind") == kind
                and str(row["descriptor_id"]) not in exact_pilot_ids
                and str(row["descriptor_id"])
                not in revision_excluded_ids
                for row in descriptor_rows
            )
            exact_preregistered_attempts = min(
                requested, available_after_exclusion
            )
            require(
                math.isclose(
                    float(registration.get("wilson_lower_bound")),
                    lower,
                    abs_tol=1e-15,
                )
                and registration.get("rate_based_requested_attempts")
                == requested
                and registration.get("pilot_complete_action_changing_count")
                == successes,
                f"FORMAL_WILSON_PREREGISTRATION_DRIFT:{kind}",
            )
            require(
                registration.get("original_formal_label_target")
                == FORMAL_LABEL_TARGETS[kind]
                and registration.get("formal_label_target")
                == expected_label_targets[kind]
                and registration.get("reallocated_label_target")
                == (
                    expected_label_targets[kind]
                    - FORMAL_LABEL_TARGETS[kind]
                )
                and registration.get("static_two_x_reference_not_used")
                == FORMAL_ATTEMPTS_BY_KIND[kind]
                and registration.get("available_after_pilot_exclusion")
                == available_after_exclusion
                and registration.get("preregistered_attempts")
                == exact_preregistered_attempts
                and registration.get("descriptor_cap_applied")
                is (exact_preregistered_attempts < requested),
                f"FORMAL_KIND_LABEL_TARGET_DRIFT:{kind}",
            )
        exact_descriptor_cap_blocked = any(
            per_kind[kind].get("descriptor_cap_applied") is True
            for kind in active_kinds
        )
        require(
            preregistration.get("descriptor_cap_blocked")
            is exact_descriptor_cap_blocked
            and plan.get("status")
            == (
                "PREREGISTERED_WITH_DESCRIPTOR_CAP_BLOCKER_NOT_RUN"
                if exact_descriptor_cap_blocked
                else "PREREGISTERED_NOT_RUN"
            ),
            "FORMAL_DESCRIPTOR_CAP_STATUS_DRIFT",
        )
        h_system = [row for row in target_rows if row["horizon"] == "H_system"]
        h_registration = preregistration.get("h_system_preregistration")
        require(isinstance(h_registration, dict), "H_SYSTEM_PREREGISTRATION_MISSING")
        aggregate_success = sum(
            int(pilot_complete[kind]) for kind in active_kinds
        )
        aggregate_attempts = PILOT_ATTEMPTS_PER_KIND * len(active_kinds)
        aggregate_lower = wilson_lower_bound(
            aggregate_success, aggregate_attempts
        )
        auto_h_attempts = 256
        require(
            h_registration.get("method")
            == (
                "FIXED_256_FULL_SYSTEM_HARD_GATE_AND_EXTERNALITY_"
                "AUDIT_ATTEMPTS_NOT_INFERRED_FROM_H_BAG_RESPONSE"
            )
            and math.isclose(
                float(
                    h_registration.get(
                        "pilot_h_bag_wilson_lower_bound_diagnostic_not_used"
                    )
                ),
                aggregate_lower,
                abs_tol=1e-15,
            )
            and h_registration.get("fixed_requested_attempts")
            == auto_h_attempts
            and h_registration.get("pilot_attempt_count")
            == aggregate_attempts
            and h_registration.get(
                "pilot_complete_action_changing_count"
            )
            == aggregate_success
            and h_registration.get("wilson_z") == 1.96
            and h_registration.get("complete_pair_target") == 256
            and h_registration.get("hard_minimum_complete_pairs")
            == FORMAL_MIN_H_SYSTEM
            and h_registration.get("preregistered_attempts")
            == len(h_system)
            and len(h_system) >= auto_h_attempts,
            "H_SYSTEM_WILSON_PREREGISTRATION_DRIFT",
        )
        require(
            h_registration.get("h_system_population_effect_inference")
            == "DESCRIPTIVE_ONLY_HORIZON_ASSIGNMENT_PI_NOT_MODELED",
            "H_SYSTEM_INFERENCE_SCOPE_DRIFT",
        )
        require(len(h_system) >= FORMAL_MIN_H_SYSTEM, "H_SYSTEM_ATTEMPTS_BELOW_128")
        require(
            len({row["clone_group_id"] for row in h_system}) == len(h_system),
            "H_SYSTEM_CLONE_GROUP_DUPLICATE",
        )
        require(
            len({int(row["event_ordinal"]) for row in h_system})
            == len(h_system),
            "H_SYSTEM_EVENT_ORDINAL_DUPLICATE",
        )
        excluded_ids = {
            str(value) for value in excluded
        } | revision_excluded_ids
        panel_namespace = "g4irsf15-formal"
    require(
        bound_attempt_design.get("excluded_descriptor_count")
        == len(excluded_ids)
        and bound_attempt_design.get("excluded_descriptor_ids_sha256")
        == canonical_sha256(sorted(excluded_ids)),
        "ATTEMPT_PANEL_EXCLUSION_BINDING_DRIFT",
    )
    excluded_by_stratum: Counter[str] = Counter()
    frame_by_stratum: Counter[str] = Counter()
    for row in descriptor_rows:
        stratum = str(row["sampling"]["sampling_stratum_id"])
        if str(row["descriptor_id"]) in excluded_ids:
            excluded_by_stratum[stratum] += 1
        else:
            frame_by_stratum[stratum] += 1
    for target in target_rows:
        sampling = target["sampling"]
        stratum = str(sampling["sampling_stratum_id"])
        require(
            sampling.get("excluded_before_panel_n_h")
            == excluded_by_stratum[stratum]
            and sampling.get("stage2_frame_n_h")
            == frame_by_stratum[stratum],
            "ATTEMPT_PANEL_FRAME_COUNT_DRIFT",
        )
    # Independently replay the fixed per-stratum stage-2 allocation/min-hash.
    for kind in (
        attempted_kinds if campaign == "pilot" else active_kinds
    ):
        available = [
            row
            for row in descriptor_rows
            if row.get("kind") == kind
            and str(row["descriptor_id"]) not in excluded_ids
        ]
        selected_kind = [
            row for row in target_rows if row.get("kind") == kind
        ]
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in available:
            groups[str(row["sampling"]["sampling_stratum_id"])].append(
                row
            )
        capacities = {
            stratum: len(values) for stratum, values in groups.items()
        }
        allocation = allocate(
            capacities,
            len(selected_kind),
            {
                stratum: float(capacity)
                for stratum, capacity in capacities.items()
            },
            minimum_each=1
            if len(selected_kind) >= len(capacities)
            else 0,
        )
        expected_ids: set[str] = set()
        for stratum, values in groups.items():
            ordered = sorted(
                values,
                key=lambda row: (
                    hash_rank(
                        f"{panel_namespace}:{kind}:{stratum}",
                        str(row["descriptor_id"]),
                    ),
                    int(row["event_ordinal"]),
                ),
            )
            expected_ids.update(
                str(row["descriptor_id"])
                for row in ordered[: allocation[stratum]]
            )
        require(
            expected_ids
            == {
                str(row["descriptor_id"]) for row in selected_kind
            },
            f"PANEL_STRATIFIED_MIN_HASH_DRIFT:{kind}",
        )
    if campaign == "formal":
        # Independently replay the deterministic horizon assignment.  H_system
        # is a fixed descriptive audit cohort, selected by global clone/event
        # uniqueness after the exact per-kind attempt panels are frozen.
        h_registration = preregistration["h_system_preregistration"]
        h_system_total = strict_int(
            h_registration.get("preregistered_attempts"),
            "h_system_preregistered_attempts",
            FORMAL_MIN_H_SYSTEM,
        )
        label_targets = preregistration["formal_label_targets"]
        selected_by_kind = {
            kind: [
                row for row in target_rows if row.get("kind") == kind
            ]
            for kind in active_kinds
        }
        h_allocation = allocate(
            {
                kind: len(selected_by_kind[kind])
                for kind in active_kinds
            },
            h_system_total,
            {
                kind: float(label_targets[kind])
                for kind in active_kinds
            },
        )
        used_clone_groups: set[str] = set()
        used_event_ordinals: set[int] = set()
        expected_h_system_ids: set[str] = set()
        for kind in active_kinds:
            chosen_for_kind = 0
            ordered = sorted(
                selected_by_kind[kind],
                key=lambda row: (
                    hash_rank(
                        "g4irsf15-h-system",
                        str(row["descriptor_id"]),
                    ),
                    int(row["event_ordinal"]),
                ),
            )
            for row in ordered:
                clone_group = str(row["clone_group_id"])
                event_ordinal = int(row["event_ordinal"])
                if (
                    clone_group in used_clone_groups
                    or event_ordinal in used_event_ordinals
                ):
                    continue
                used_clone_groups.add(clone_group)
                used_event_ordinals.add(event_ordinal)
                expected_h_system_ids.add(str(row["descriptor_id"]))
                chosen_for_kind += 1
                if chosen_for_kind == h_allocation[kind]:
                    break
            require(
                chosen_for_kind == h_allocation[kind],
                f"H_SYSTEM_EXPECTED_UNIQUE_ALLOCATION_SHORTFALL:{kind}",
            )
        actual_h_system_ids = {
            str(row["descriptor_id"])
            for row in target_rows
            if row.get("horizon") == "H_system"
        }
        require(
            actual_h_system_ids == expected_h_system_ids,
            "H_SYSTEM_DETERMINISTIC_ASSIGNMENT_DRIFT",
        )
    return plan


def validate_shard(
    root: Path,
    campaign: str,
    plan: Mapping[str, Any],
    shard: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    index = int(shard["shard_index"])
    namespace = (
        f"pilot_r{plan.get('pilot_round', 1)}"
        if campaign == "pilot"
        else "formal"
    )
    relative = (
        RUN_STATE_SHARD_ROOT
        / namespace
        / f"g4irsf15_{namespace}_shard_{index:04d}.json.zst"
    )
    shard_byte_count = (root / relative).stat().st_size
    value = zstd_json(root / relative)
    validate_self_hash(value, f"{campaign}_shard_{index}")
    plan_relative = (
        PILOT_PLAN_PATH
        if campaign == "pilot" and plan.get("pilot_round") == 1
        else PILOT_ROUND2_PLAN_PATH
        if campaign == "pilot"
        else FORMAL_PLAN_PATH
    )
    require(
        value.get("schema") == SHARD_SCHEMA
        and value.get("campaign") == campaign
        and value.get("shard_index") == index
        and value.get("status") == "COMPLETE"
        and value.get("formal_pass_claimed") is False,
        "SHARD_SCHEMA_IDENTITY_OR_STATUS",
    )
    require(
        value.get("plan_path") == plan_relative.as_posix()
        and value.get("plan_self_sha256") == plan["self_sha256"]
        and value.get("plan_file_sha256")
        == file_sha256(root / plan_relative)
        and value.get("shard_sha256") == shard["shard_sha256"],
        "SHARD_PLAN_BINDING",
    )
    require(
        value.get("target_keys") == shard.get("target_keys")
        and value.get("exact_binary_build_manifest")
        == plan.get("exact_binary_build_manifest"),
        "SHARD_TARGET_OR_BUILD_BINDING_DRIFT",
    )
    binary = value.get("binary")
    require(isinstance(binary, dict), "SHARD_BINARY_MISSING")
    require(
        binary.get("sha256_before") == binary.get("sha256_after")
        == plan["binary"]["sha256_before"]
        and binary.get("unchanged") is True,
        "SHARD_BINARY_DRIFT",
    )
    require(
        isinstance(binary.get("peak_resident_bytes"), int)
        and binary["peak_resident_bytes"] > 0,
        "SHARD_RSS_PROFILE_MISSING",
    )
    native = value.get("native_payload")
    require(
        isinstance(native, dict)
        and native.get("schema") == PAIR_RUN_SCHEMA
        and native.get("formal_pass_claimed") is False
        and native.get("evidence_scope")
        == "EXACT_NATIVE_SAME_STATE_ONE_SHOT_MATCHED_PAIRS"
        and native.get("h_system_cohort_policy")
        == "ALL_INPUT_RUNTIME_IDS_IN_INPUT_ORDER",
        "SHARD_NATIVE_SCHEMA",
    )
    controls = native.get("frozen_controls")
    require(isinstance(controls, dict), "SHARD_NATIVE_CONTROLS_MISSING")
    for name, expected in FROZEN_CONTROLS.items():
        require(
            controls.get(name) == expected,
            f"SHARD_NATIVE_CONTROL_DRIFT:{name}",
        )
    current = protected_inputs(root)
    require(
        native.get("evidence_scope")
        == "EXACT_NATIVE_SAME_STATE_ONE_SHOT_MATCHED_PAIRS"
        and native.get("input_request_count") == FULL_SEGMENT_COUNT
        and native.get("raw_bag_count") == FULL_RAW_BAG_COUNT
        and native.get("protected_full_1x_shape") is True
        and native.get("input_runtime_cohort_sha256")
        == current["input_runtime_cohort_sha256"]
        and native.get("h_system_cohort_mapping_sha256")
        == current["runtime_segment_mapping_sha256"]
        and native.get("raw_bag_mapping_sha256")
        == current["raw_bag_mapping_sha256"]
        and native.get("raw_bag_original_entry_mapping_sha256")
        == current["raw_bag_original_entry_mapping_sha256"],
        "SHARD_NATIVE_PROTECTED_INPUT_DRIFT",
    )
    pairs = native.get("pairs")
    require(
        isinstance(pairs, list)
        and len(pairs) == shard.get("target_count")
        == native.get("target_count"),
        "SHARD_NATIVE_PAIR_COUNT",
    )
    targets = shard["targets"]
    action_count = 0
    false_positive_count = 0
    complete_h_bag_count = 0
    applied_h_system_count = 0
    complete_h_system_count = 0
    for pair, target in zip(pairs, targets, strict=True):
        require(isinstance(pair, dict), "PAIR_NOT_OBJECT")
        require(
            pair.get("descriptor_id") == target.get("descriptor_id")
            and pair.get("target_address_id")
            == target.get(
                "target_address_id", target.get("descriptor_id")
            )
            and pair.get("kind") == target.get("kind")
            and pair.get("event_ordinal") == target.get("event_ordinal")
            and pair.get("horizon") == target.get("horizon")
            and pair.get("protected_full_1x_shape") is True,
            "PAIR_TARGET_IDENTITY",
        )
        if pair.get("action_changed") is True:
            action_count += 1
            if pair.get("horizon") == "H_system":
                applied_h_system_count += 1
                if (
                    pair.get("pair_complete") is True
                    and pair.get("formal_hard_gate_pass") is True
                ):
                    complete_h_system_count += 1
            elif pair.get("pair_complete") is True:
                complete_h_bag_count += 1
        else:
            false_positive_count += 1
    require(
        native.get("action_changing_pair_count")
        == native.get("applied_action_changing_pair_count")
        == action_count
        and native.get("false_positive_pair_count")
        == false_positive_count
        and native.get("complete_action_changing_h_bag_count")
        == complete_h_bag_count
        and native.get("applied_action_changing_h_system_count")
        == applied_h_system_count
        and native.get("complete_h_system_hard_gate_pass_count")
        == native.get("h_system_pair_count")
        == complete_h_system_count,
        "SHARD_NATIVE_SUMMARY_COUNT_DRIFT",
    )
    return pairs, value


def derive_branch_gate(
    branch: Mapping[str, Any],
    horizon: str,
    *,
    terminal_evidence_complete: bool,
    protected_full_1x_shape: bool = True,
) -> tuple[bool, list[str]]:
    invariants = branch.get("invariants")
    if not isinstance(invariants, dict):
        return False, ["INVARIANTS_MISSING"]
    reasons: list[str] = []
    for field, reason in (
        ("unsafe_entry_count", "UNSAFE_PHYSICAL_FAULT_EDGE_ENTRY"),
        ("reservation_conflict_count", "RESERVATION_CONFLICT"),
        ("runtime_full_astar_call_count", "RUNTIME_FULL_ASTAR_CALL"),
        ("runtime_global_scan_count", "RUNTIME_GLOBAL_SCAN"),
        ("runtime_future_route_read_count", "RUNTIME_FUTURE_ROUTE_READ"),
        (
            "runtime_future_schedule_read_count",
            "RUNTIME_FUTURE_SCHEDULE_READ",
        ),
        ("teacher_input_count", "TEACHER_INPUT_USED"),
    ):
        if invariants.get(field) != 0:
            reasons.append(reason)
    if invariants.get("max_selected_edges_per_bag") not in (0, 1):
        reasons.append("MORE_THAN_ONE_EDGE_SELECTED_PER_DECISION")
    for field, reason in (
        ("two_step_reservation_count", "TWO_STEP_RESERVATION"),
        ("unresolved_deadlock_count", "UNRESOLVED_DEADLOCK"),
    ):
        if invariants.get(field) != 0:
            reasons.append(reason)
    if invariants.get("event_limit_reached") is not False:
        reasons.append("EVENT_LIMIT_REACHED")
    if invariants.get("time_limit_reached") is not False:
        reasons.append("TIME_LIMIT_REACHED")
    if invariants.get("merge_grant_stale_arbitration_count") != 0:
        reasons.append("MERGE_GRANT_STALE_ARBITRATION")
    if invariants.get("stale_arbitration_event_count") != 0:
        reasons.append("STALE_ARBITRATION_EVENT")
    if strict_float(
        invariants.get("artificial_batch_delay_seconds"),
        "invariants.artificial_batch_delay_seconds",
    ) != 0.0:
        reasons.append("ARTIFICIAL_BATCH_DELAY")
    for field, reason in (
        (
            "merge_grant_conservation_holds",
            "MERGE_GRANT_CONSERVATION_FAILED",
        ),
        (
            "merge_grant_active_bijection_holds",
            "MERGE_GRANT_ACTIVE_BIJECTION_FAILED",
        ),
        (
            "merge_grant_runtime_owned_capability",
            "MERGE_GRANT_CAPABILITY_NOT_RUNTIME_OWNED",
        ),
        (
            "merge_grant_exact_slot_no_future_shift",
            "MERGE_GRANT_FUTURE_SHIFT",
        ),
    ):
        if invariants.get(field) is not True:
            reasons.append(reason)
    live_reasons = list(reasons)
    formal_evaluated = horizon == "H_system"
    if formal_evaluated:
        if not protected_full_1x_shape:
            reasons.append("PROTECTED_FULL_1X_SHAPE_MISMATCH")
        if invariants.get("completed_count") != invariants.get(
            "requested_count"
        ):
            reasons.append("SYSTEM_COHORT_NOT_ALL_COMPLETED")
        if invariants.get("failed_segment_count") != 0:
            reasons.append("SYSTEM_COHORT_FAILED_SEGMENT")
        if invariants.get("merge_grant_final_active_unconsumed") != 0:
            reasons.append("FINAL_ACTIVE_MERGE_GRANT_UNCONSUMED")
        if invariants.get("merge_grant_outstanding_request_count") != 0:
            reasons.append("FINAL_OUTSTANDING_MERGE_REQUEST")
    require(
        invariants.get("hard_gate_fail_reasons") == reasons
        and invariants.get("live_safety_pass") is (not live_reasons)
        and invariants.get("formal_hard_gate_evaluated")
        is formal_evaluated
        and invariants.get("formal_hard_gate_pass")
        is (formal_evaluated and not reasons),
        "BRANCH_INVARIANT_GATE_DERIVATION_DRIFT",
    )
    blockers = list(reasons)
    if horizon == "H_system" and terminal_evidence_complete:
        if branch.get("finalized") is not True:
            blockers.append("H_SYSTEM_NOT_FINALIZED")
        if invariants.get("completed_count") != FULL_SEGMENT_COUNT:
            blockers.append("H_SYSTEM_NOT_ALL_SEGMENTS_COMPLETE")
        if invariants.get("failed_segment_count") != 0:
            blockers.append("H_SYSTEM_FAILED_SEGMENT")
    return not blockers, blockers


def derive_metric_delta(
    baseline: Mapping[str, Any], treatment: Mapping[str, Any]
) -> dict[str, float]:
    fields = (
        "completion_mean_seconds",
        "completion_p95_seconds",
        "completion_p99_seconds",
        "source_wait_mean_seconds",
        "total_local_wait_mean_seconds",
        "junction_wait_mean_seconds",
        "merge_wait_mean_seconds",
        "edge_travel_mean_seconds",
        "node_service_mean_seconds",
        "loop_extra_mean_seconds",
        "path_length_hops_total",
        "path_length_hops_mean",
    )
    result = {
        f"delta_{field}": strict_float(
            treatment.get(field), f"treatment.{field}"
        )
        - strict_float(baseline.get(field), f"baseline.{field}")
        for field in fields
    }
    result["delta_deadline_miss_count"] = float(
        int(treatment.get("deadline_miss_count", 0))
        - int(baseline.get("deadline_miss_count", 0))
    )
    return result


def derive_affected_deltas(
    baseline_rows: Any, treatment_rows: Any
) -> list[dict[str, Any]]:
    require(
        isinstance(baseline_rows, list)
        and isinstance(treatment_rows, list),
        "AFFECTED_OUTCOMES_MISSING",
    )
    baseline = {
        int(row["runtime_bag_id"]): row
        for row in baseline_rows
        if isinstance(row, dict)
    }
    treatment = {
        int(row["runtime_bag_id"]): row
        for row in treatment_rows
        if isinstance(row, dict)
    }
    require(set(baseline) == set(treatment), "AFFECTED_ID_DRIFT")
    fields = (
        "finish_time",
        "completion_seconds",
        "source_wait_seconds",
        "total_local_wait_seconds",
        "junction_wait_seconds",
        "merge_wait_seconds",
        "edge_travel_seconds",
        "node_service_seconds",
        "loop_extra_seconds",
        "decision_count",
        "retry_count",
        "loop_count",
    )
    result: list[dict[str, Any]] = []
    for runtime_id in sorted(baseline):
        left, right = baseline[runtime_id], treatment[runtime_id]
        row: dict[str, Any] = {
            "runtime_bag_id": runtime_id,
            "segment_id": left.get("segment_id"),
            "baseline_completed": left.get("completed"),
            "treatment_completed": right.get("completed"),
            "baseline_failed": left.get("failed"),
            "treatment_failed": right.get("failed"),
        }
        for field in fields:
            row[f"delta_{field}"] = strict_float(
                right.get(field), f"treatment_bag.{field}"
            ) - strict_float(left.get(field), f"baseline_bag.{field}")
        result.append(row)
    return result


def causal_outcome_payload(row: Mapping[str, Any]) -> bytes:
    return canonical_fields_payload(
        [
            ("schema", "s", "czr005.g4irsf15.causal_bag_outcome.v1"),
            ("runtime_bag_id", "i", row["runtime_bag_id"]),
            ("task_id", "i", row["task_id"]),
            ("segment_id", "s", row["segment_id"]),
            ("start", "i", row["start"]),
            ("goal", "i", row["goal"]),
            ("current_node", "i", row["current_node"]),
            ("known", "b", row["known"]),
            ("completed", "b", row["completed"]),
            ("failed", "b", row["failed"]),
            ("status", "s", row["status"]),
            ("failure_reason", "s", row["failure_reason"]),
            ("release_time", "d", row["release_time"]),
            ("deadline", "d", row["deadline"]),
            ("admitted_time", "d", row["admitted_time"]),
            ("finish_time", "d", row["finish_time"]),
            ("source_wait_seconds", "d", row["source_wait_seconds"]),
            (
                "total_local_wait_seconds",
                "d",
                row["total_local_wait_seconds"],
            ),
            ("junction_wait_seconds", "d", row["junction_wait_seconds"]),
            ("merge_wait_seconds", "d", row["merge_wait_seconds"]),
            ("edge_travel_seconds", "d", row["edge_travel_seconds"]),
            ("node_service_seconds", "d", row["node_service_seconds"]),
            ("loop_extra_seconds", "d", row["loop_extra_seconds"]),
            ("completion_seconds", "d", row["completion_seconds"]),
            ("decision_count", "i", row["decision_count"]),
            ("retry_count", "i", row["retry_count"]),
            ("loop_count", "i", row["loop_count"]),
        ]
    )


def validate_realized_deltas(
    rows: Any, declared_sha256: Any
) -> tuple[list[dict[str, Any]], list[int]]:
    require(isinstance(rows, list), "REALIZED_DELTAS_MISSING")
    normalized: list[dict[str, Any]] = []
    ids: list[int] = []
    hashes: list[str] = []
    numeric = (
        "finish_time",
        "completion_seconds",
        "source_wait_seconds",
        "total_local_wait_seconds",
        "junction_wait_seconds",
        "merge_wait_seconds",
        "edge_travel_seconds",
        "node_service_seconds",
        "loop_extra_seconds",
    )
    for source in rows:
        require(isinstance(source, dict), "REALIZED_DELTA_NOT_OBJECT")
        row = dict(source)
        left, right = row.get("baseline"), row.get("treatment")
        require(
            isinstance(left, dict) and isinstance(right, dict),
            "REALIZED_OUTCOME_PAIR_MISSING",
        )
        runtime_id = strict_int(
            row.get("runtime_bag_id"), "realized.runtime_id"
        )
        require(
            runtime_id == left.get("runtime_bag_id")
            == right.get("runtime_bag_id")
            and runtime_id not in ids,
            "REALIZED_IDENTITY_DRIFT",
        )
        ids.append(runtime_id)
        require(
            row.get("completed_delta")
            == int(bool(right["completed"])) - int(bool(left["completed"]))
            and row.get("failed_delta")
            == int(bool(right["failed"])) - int(bool(left["failed"]))
            and row.get("status_changed")
            == (right["status"] != left["status"])
            and row.get("failure_reason_changed")
            == (right["failure_reason"] != left["failure_reason"]),
            "REALIZED_STATUS_DELTA_DRIFT",
        )
        for field in numeric:
            delta_field = (
                f"{field[:-8]}_delta_seconds"
                if field.endswith("_seconds")
                else f"{field}_delta_seconds"
            )
            require(
                strict_float(row.get(delta_field), delta_field)
                == strict_float(right.get(field), f"right.{field}")
                - strict_float(left.get(field), f"left.{field}"),
                f"REALIZED_NUMERIC_DELTA:{field}",
            )
        for field in ("decision_count", "retry_count", "loop_count"):
            require(
                row.get(f"{field}_delta")
                == int(right[field]) - int(left[field]),
                f"REALIZED_INTEGER_DELTA:{field}",
            )
        row_hash = canonical_fields_sha256(
            [
                (
                    "schema",
                    "s",
                    "czr005.g4irsf15.realized_outcome_delta.v1",
                ),
                ("baseline", "s", causal_outcome_payload(left)),
                ("treatment", "s", causal_outcome_payload(right)),
            ]
        )
        require(
            row.get("outcome_delta_sha256") == row_hash,
            "REALIZED_DELTA_HASH_DRIFT",
        )
        hashes.append(row_hash)
        normalized.append(row)
    fields: list[tuple[str, str, Any]] = [
        (
            "schema",
            "s",
            "czr005.g4irsf15.realized_outcome_deltas.v1",
        ),
        ("row_count", "u", len(hashes)),
    ]
    fields.extend(("row_sha256", "s", value) for value in hashes)
    require(
        declared_sha256 == canonical_fields_sha256(fields),
        "REALIZED_SIDECAR_HASH_DRIFT",
    )
    return normalized, ids


def derive_raw_delta(
    baseline: Mapping[str, Any], treatment: Mapping[str, Any]
) -> dict[str, float]:
    fields = (
        "original_entry_mean_minutes",
        "original_entry_median_seconds",
        "original_entry_p95_seconds",
        "original_entry_p99_seconds",
        "original_entry_max_seconds",
        "java_release_mean_minutes",
        "scheduled_pre_release_wait_mean_minutes",
        "source_wait_mean_minutes",
        "network_time_mean_minutes",
        "total_system_time_mean_minutes",
    )
    result = {
        f"delta_{field}": strict_float(
            treatment.get(field), f"raw.right.{field}"
        )
        - strict_float(baseline.get(field), f"raw.left.{field}")
        for field in fields
    }
    result["delta_deadline_miss_raw_bag_count"] = float(
        int(treatment.get("deadline_miss_raw_bag_count", 0))
        - int(baseline.get("deadline_miss_raw_bag_count", 0))
    )
    return result


def raw_sequential_mean(values: Sequence[float]) -> float:
    require(bool(values), "RAW_BAG_MEAN_EMPTY")
    total = 0.0
    for value in values:
        total += value
    return total / len(values)


def raw_type7_quantile(
    values: Sequence[float], probability: float
) -> float:
    require(bool(values), "RAW_BAG_QUANTILE_EMPTY")
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return (
        ordered[lower] * (1.0 - fraction)
        + ordered[upper] * fraction
    )


def validate_raw_bag_sufficient_sidecar(
    sidecar: Any,
    *,
    raw_metrics: Mapping[str, Any],
    target: Mapping[str, Any],
    branch_name: str,
) -> dict[str, Any]:
    require(
        isinstance(sidecar, dict),
        f"RAW_BAG_SUFFICIENT_STATISTICS_MISSING:{branch_name}",
    )
    rows = sidecar.get("rows")
    require(
        sidecar.get("schema")
        == "czr005.g4irsf15.raw_bag_sufficient_statistics.v1"
        and sidecar.get("row_count") == FULL_RAW_BAG_COUNT
        and sidecar.get("expected_raw_bag_count") == FULL_RAW_BAG_COUNT
        and sidecar.get("selected_segment_count") == FULL_SEGMENT_COUNT
        and sidecar.get("complete_coverage") is True
        and sidecar.get("task_id_order") == "STRICT_ASCENDING_NUMERIC"
        and sidecar.get("runtime_segment_mapping_sha256")
        == target.get("h_system_cohort_mapping_sha256")
        and sidecar.get("raw_bag_mapping_sha256")
        == target.get("raw_bag_mapping_sha256")
        and sidecar.get("raw_bag_original_entry_mapping_sha256")
        == target.get("raw_bag_original_entry_mapping_sha256")
        and isinstance(rows, list)
        and len(rows) == FULL_RAW_BAG_COUNT,
        f"RAW_BAG_SUFFICIENT_STATISTICS_COVERAGE:{branch_name}",
    )
    content_fields: list[tuple[str, str, Any]] = [
        (
            "schema",
            "s",
            "czr005.g4irsf15.raw_bag_sufficient_statistics.v1",
        ),
        ("row_count", "i", FULL_RAW_BAG_COUNT),
        ("expected_raw_bag_count", "i", FULL_RAW_BAG_COUNT),
        ("selected_segment_count", "i", FULL_SEGMENT_COUNT),
        ("complete_coverage", "b", True),
        ("task_id_order", "s", "STRICT_ASCENDING_NUMERIC"),
        (
            "runtime_segment_mapping_sha256",
            "s",
            target["h_system_cohort_mapping_sha256"],
        ),
        (
            "raw_bag_mapping_sha256",
            "s",
            target["raw_bag_mapping_sha256"],
        ),
        (
            "raw_bag_original_entry_mapping_sha256",
            "s",
            target["raw_bag_original_entry_mapping_sha256"],
        ),
    ]
    total_fields = (
        "original_entry_total_seconds",
        "java_release_total_seconds",
        "scheduled_pre_release_wait_total_seconds",
        "source_wait_total_seconds",
        "network_time_total_seconds",
        "total_system_time_total_seconds",
    )
    totals: dict[str, list[float]] = {
        name: [] for name in total_fields
    }
    covered: list[int] = []
    previous_task = -1
    completed_segments = 0
    complete_count = 0
    failed_count = 0
    deadline_count = 0
    for index, source in enumerate(rows):
        require(
            isinstance(source, dict),
            f"RAW_BAG_SUFFICIENT_ROW_NOT_OBJECT:{branch_name}:{index}",
        )
        task_id = strict_int(
            source.get("task_id"),
            f"raw_sidecar.{branch_name}.task_id",
        )
        runtime_ids_source = source.get("runtime_bag_ids")
        require(
            task_id > previous_task
            and isinstance(runtime_ids_source, list)
            and bool(runtime_ids_source),
            f"RAW_BAG_SUFFICIENT_ROW_ORDER:{branch_name}:{index}",
        )
        previous_task = task_id
        runtime_ids = [
            strict_int(
                value,
                f"raw_sidecar.{branch_name}.runtime_bag_id",
            )
            for value in runtime_ids_source
        ]
        require(
            runtime_ids == sorted(set(runtime_ids))
            and source.get("runtime_segment_count") == len(runtime_ids),
            f"RAW_BAG_RUNTIME_ID_MAPPING:{branch_name}:{task_id}",
        )
        completed = strict_int(
            source.get("completed_segment_count"),
            f"raw_sidecar.{branch_name}.completed_segment_count",
        )
        complete = source.get("complete")
        failed = source.get("failed")
        deadline = source.get("deadline_miss")
        require(
            isinstance(complete, bool)
            and isinstance(failed, bool)
            and isinstance(deadline, bool)
            and completed <= len(runtime_ids)
            and complete is True
            and failed is False
            and completed == len(runtime_ids),
            f"RAW_BAG_SUFFICIENT_ROW_COMPLETION:{branch_name}:{task_id}",
        )
        numeric = {
            name: strict_float(
                source.get(name),
                f"raw_sidecar.{branch_name}.{name}",
            )
            for name in total_fields
        }
        decomposed = (
            numeric["scheduled_pre_release_wait_total_seconds"]
            + numeric["source_wait_total_seconds"]
            + numeric["network_time_total_seconds"]
        )
        require(
            all(value >= 0.0 for value in numeric.values())
            and abs(
                decomposed - numeric["original_entry_total_seconds"]
            )
            <= 1.0e-7
            and abs(
                decomposed - numeric["total_system_time_total_seconds"]
            )
            <= 1.0e-7,
            f"RAW_BAG_SUFFICIENT_TIMING_DECOMPOSITION:{branch_name}:{task_id}",
        )
        runtime_mapping_sha = canonical_fields_sha256(
            [
                (
                    "schema",
                    "s",
                    "czr005.g4irsf15.raw_bag_runtime_id_mapping_row.v1",
                ),
                ("task_id", "i", task_id),
                ("runtime_bag_ids", "I", runtime_ids),
            ]
        )
        row_fields: list[tuple[str, str, Any]] = [
            (
                "schema",
                "s",
                "czr005.g4irsf15.raw_bag_sufficient_statistics_row.v1",
            ),
            ("task_id", "i", task_id),
            ("runtime_bag_ids", "I", runtime_ids),
            ("runtime_segment_count", "i", len(runtime_ids)),
            ("completed_segment_count", "i", completed),
            ("complete", "b", complete),
            ("failed", "b", failed),
            ("deadline_miss", "b", deadline),
        ]
        row_fields.extend(
            (name, "d", numeric[name]) for name in total_fields
        )
        row_fields.append(
            ("runtime_id_mapping_sha256", "s", runtime_mapping_sha)
        )
        row_sha = canonical_fields_sha256(row_fields)
        require(
            source.get("runtime_id_mapping_sha256")
            == runtime_mapping_sha
            and source.get("row_sha256") == row_sha,
            f"RAW_BAG_SUFFICIENT_ROW_HASH:{branch_name}:{task_id}",
        )
        content_fields.append(("row_sha256", "s", row_sha))
        covered.extend(runtime_ids)
        completed_segments += completed
        complete_count += int(complete)
        failed_count += int(failed)
        deadline_count += int(deadline)
        for name, value in numeric.items():
            totals[name].append(value)
    require(
        sorted(covered) == list(range(FULL_SEGMENT_COUNT)),
        f"RAW_BAG_SUFFICIENT_RUNTIME_COVERAGE:{branch_name}",
    )
    content_sha = canonical_fields_sha256(content_fields)
    require(
        sidecar.get("content_sha256") == content_sha,
        f"RAW_BAG_SUFFICIENT_CONTENT_HASH:{branch_name}",
    )
    original = totals["original_entry_total_seconds"]
    expected_metrics = {
        "selected_segment_count": FULL_SEGMENT_COUNT,
        "selected_raw_bag_count": FULL_RAW_BAG_COUNT,
        "completed_segment_count": completed_segments,
        "complete_raw_bag_count": complete_count,
        "failed_raw_bag_count": failed_count,
        "deadline_miss_raw_bag_count": deadline_count,
        "completion_rate": complete_count / FULL_RAW_BAG_COUNT,
        "comparison_eligible": True,
        "primary_denominator": "original_entry_time_tth",
        "denominator_scope": "SUM_PER_RAW_TASK_OVER_ALL_PROTECTED_SEGMENTS",
        "original_entry_mean_minutes": raw_sequential_mean(original) / 60.0,
        "original_entry_median_seconds": raw_type7_quantile(original, 0.5),
        "original_entry_p95_seconds": raw_type7_quantile(original, 0.95),
        "original_entry_p99_seconds": raw_type7_quantile(original, 0.99),
        "original_entry_max_seconds": max(original),
        "java_release_mean_minutes": (
            raw_sequential_mean(totals["java_release_total_seconds"])
            / 60.0
        ),
        "scheduled_pre_release_wait_mean_minutes": (
            raw_sequential_mean(
                totals["scheduled_pre_release_wait_total_seconds"]
            )
            / 60.0
        ),
        "source_wait_mean_minutes": (
            raw_sequential_mean(totals["source_wait_total_seconds"])
            / 60.0
        ),
        "network_time_mean_minutes": (
            raw_sequential_mean(totals["network_time_total_seconds"])
            / 60.0
        ),
        "total_system_time_mean_minutes": (
            raw_sequential_mean(
                totals["total_system_time_total_seconds"]
            )
            / 60.0
        ),
        "survivor_original_entry_mean_minutes": (
            raw_sequential_mean(original) / 60.0
        ),
        "survivor_metric_comparison_allowed": False,
        "quantile_method": "LINEAR_TYPE7_N_MINUS_ONE",
    }
    require(
        dict(raw_metrics) == expected_metrics,
        f"RAW_BAG_AGGREGATES_NOT_REDERIVED:{branch_name}",
    )
    return {
        "schema": sidecar["schema"],
        "content_sha256": content_sha,
        "row_count": FULL_RAW_BAG_COUNT,
        "expected_raw_bag_count": FULL_RAW_BAG_COUNT,
        "selected_segment_count": FULL_SEGMENT_COUNT,
        "complete_coverage": True,
        "runtime_segment_mapping_sha256": sidecar[
            "runtime_segment_mapping_sha256"
        ],
        "raw_bag_mapping_sha256": sidecar["raw_bag_mapping_sha256"],
        "raw_bag_original_entry_mapping_sha256": sidecar[
            "raw_bag_original_entry_mapping_sha256"
        ],
        "rederived_raw_bag_metrics_sha256": canonical_sha256(
            expected_metrics
        ),
    }


def validate_cohort_sidecar(
    sidecar: Any, realized_rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    require(
        isinstance(sidecar, dict)
        and sidecar.get("schema")
        == "czr005.g4irsf15.full_cohort_outcome_difference.v1"
        and sidecar.get("row_count") == FULL_SEGMENT_COUNT
        and sidecar.get("complete_coverage") is True
        and sidecar.get("runtime_id_order")
        == "CONTIGUOUS_ZERO_BASED_INPUT_ORDER",
        "FULL_COHORT_SIDECAR_COVERAGE",
    )
    rows = sidecar.get("rows")
    require(
        isinstance(rows, list) and len(rows) == FULL_SEGMENT_COUNT,
        "FULL_COHORT_SIDECAR_ROWS",
    )
    realized = {
        int(row["runtime_bag_id"]): row for row in realized_rows
    }
    changed_ids: list[int] = []
    fields: list[tuple[str, str, Any]] = [
        (
            "schema",
            "s",
            "czr005.g4irsf15.full_cohort_outcome_difference.v1",
        ),
        ("row_count", "u", FULL_SEGMENT_COUNT),
    ]
    for runtime_id, row in enumerate(rows):
        require(isinstance(row, dict), "FULL_COHORT_ROW_NOT_OBJECT")
        baseline_sha = row.get("baseline_outcome_sha256")
        treatment_sha = row.get("treatment_outcome_sha256")
        changed = row.get("outcome_changed")
        row_sha = canonical_fields_sha256(
            [
                ("runtime_bag_id", "i", runtime_id),
                ("baseline_outcome_sha256", "s", baseline_sha),
                ("treatment_outcome_sha256", "s", treatment_sha),
                ("outcome_changed", "b", changed),
            ]
        )
        require(
            row.get("runtime_bag_id") == runtime_id
            and is_sha256(baseline_sha)
            and is_sha256(treatment_sha)
            and isinstance(changed, bool)
            and changed == (baseline_sha != treatment_sha)
            and row.get("row_sha256") == row_sha,
            f"FULL_COHORT_ROW_DRIFT:{runtime_id}",
        )
        if changed:
            changed_ids.append(runtime_id)
            numeric = realized.get(runtime_id)
            require(
                numeric is not None
                and hashlib.sha256(
                    causal_outcome_payload(numeric["baseline"])
                ).hexdigest()
                == baseline_sha
                and hashlib.sha256(
                    causal_outcome_payload(numeric["treatment"])
                ).hexdigest()
                == treatment_sha,
                f"FULL_COHORT_NUMERIC_BINDING:{runtime_id}",
            )
        fields.append(("row_sha256", "s", row_sha))
    fields.append(("changed_count", "i", len(changed_ids)))
    require(
        sidecar.get("changed_count") == len(changed_ids)
        and set(changed_ids) == set(realized)
        and sidecar.get("content_sha256")
        == canonical_fields_sha256(fields),
        "FULL_COHORT_CONTENT_DRIFT",
    )
    return {
        key: sidecar[key]
        for key in (
            "schema",
            "row_count",
            "changed_count",
            "complete_coverage",
            "runtime_id_order",
            "content_sha256",
        )
    }


def signed_label(value: float) -> str:
    return (
        "BENEFICIAL"
        if value < -1e-9
        else "HARMFUL"
        if value > 1e-9
        else "NEUTRAL_WITHIN_TOLERANCE"
    )


def runtime_state_sha256_from_components(
    components: Mapping[str, Any],
) -> str:
    require(
        set(components)
        == {field for field, _ in RESOLVED_STATE_COMPONENT_FIELDS}
        and all(is_sha256(value) for value in components.values()),
        "RESOLVED_STATE_COMPONENTS_INVALID",
    )
    return canonical_fields_sha256(
        [
            ("schema", "s", G4IRSF14_STATE_CLONE_SCHEMA),
            *[
                (canonical_name, "s", components[field])
                for field, canonical_name in RESOLVED_STATE_COMPONENT_FIELDS
            ],
        ]
    )


def clone_group_sha256_from_runtime_state(runtime_state_sha256: str) -> str:
    require(
        is_sha256(runtime_state_sha256),
        "RESOLVED_RUNTIME_STATE_SHA256_INVALID",
    )
    return canonical_fields_sha256(
        [
            ("schema", "s", G4IRSF14_STATE_CLONE_SCHEMA),
            ("runtime_state_sha256", "s", runtime_state_sha256),
        ]
    )


def resolved_intervention_sha256(
    resolved: Mapping[str, Any], horizon: str
) -> str:
    kind = str(resolved.get("kind"))
    require(
        kind in RESOLVED_INTERVENTION_KIND
        and horizon in {"H_bag", "H_system"}
        and is_sha256(resolved.get("boundary_sha256")),
        "RESOLVED_INTERVENTION_FIELDS_INVALID",
    )
    for field in (
        "runtime_bag_id",
        "peer_runtime_bag_id",
        "selected_next_node",
    ):
        require(
            isinstance(resolved.get(field), int)
            and not isinstance(resolved.get(field), bool),
            f"RESOLVED_INTERVENTION_INTEGER_INVALID:{field}",
        )
    require(
        isinstance(resolved.get("selected_boolean"), bool),
        "RESOLVED_INTERVENTION_BOOLEAN_INVALID",
    )
    return canonical_fields_sha256(
        [
            ("schema", "s", G4IRSF14_STATE_CLONE_SCHEMA),
            ("boundary_sha256", "s", resolved["boundary_sha256"]),
            ("kind", "s", RESOLVED_INTERVENTION_KIND[kind]),
            ("horizon", "s", horizon),
            ("runtime_bag_id", "i", resolved["runtime_bag_id"]),
            ("peer_runtime_bag_id", "i", resolved["peer_runtime_bag_id"]),
            ("merge_request_id", "u", 0),
            ("peer_merge_request_id", "u", 0),
            ("selected_next_node", "i", resolved["selected_next_node"]),
            ("selected_boolean", "b", resolved["selected_boolean"]),
        ]
    )


def validate_resolved_execution_descriptor(
    pair: Mapping[str, Any], target: Mapping[str, Any]
) -> dict[str, Any]:
    resolved = pair.get("resolved_execution_descriptor")
    require(isinstance(resolved, dict), "RESOLVED_DESCRIPTOR_MISSING")
    require(
        resolved.get("schema") == DESCRIPTOR_SCHEMA
        and is_sha256(resolved.get("descriptor_id"))
        and is_sha256(resolved.get("runtime_state_sha256"))
        and is_sha256(resolved.get("boundary_sha256"))
        and is_sha256(resolved.get("clone_group_id")),
        "RESOLVED_DESCRIPTOR_FULL_SEAL_MISSING",
    )
    for field in (
        "skeleton_id",
        "population_group_sha256",
        "population_selection_sha256",
        "kind",
        "event_ordinal",
        "event_seq",
        "event_time",
        "event_time_bits",
        "node",
        "runtime_bag_id",
        "peer_runtime_bag_id",
        "baseline_next_node",
        "selected_next_node",
        "baseline_release",
        "selected_boolean",
        "source_ready_order",
        "legal_next_edges",
        "baseline_action",
        "intervention_action",
        "expected_action_change_type",
        "candidate_action_count",
        "candidate_action_count_semantics",
        "alternative_action_count",
        "total_legal_action_count",
        "active_merge_capability_count",
        "pending_merge_request_count",
        "active_physical_fault_edge_count",
        "queued_bag_count",
        "pibt_prefilter_candidate_event",
        "primary_action_selection",
    ):
        require(
            resolved.get(field) == target.get(field),
            f"RESOLVED_DESCRIPTOR_LOCAL_ADDRESS_DRIFT:{field}",
        )
    hashes = resolved.get("intervention_sha256_by_horizon")
    state_components = resolved.get("state_components")
    expected_state_component_keys = {
        field for field, _ in RESOLVED_STATE_COMPONENT_FIELDS
    }
    expected_runtime_state_sha256 = (
        runtime_state_sha256_from_components(state_components)
        if isinstance(state_components, dict)
        else None
    )
    horizon = str(target.get("horizon"))
    require(
        isinstance(hashes, dict)
        and set(hashes) == {"H_bag", "H_system"}
        and resolved.get("descriptor_id") == hashes.get("H_bag")
        == resolved.get("intervention_sha256")
        and is_sha256(hashes.get("H_system"))
        and resolved.get("horizon") == "H_bag"
        and resolved.get("kind_name")
        == RESOLVED_INTERVENTION_KIND.get(resolved.get("kind"))
        and resolved.get("boundary_kind")
        == RESOLVED_BOUNDARY_KIND.get(resolved.get("kind"))
        and isinstance(state_components, dict)
        and set(state_components) == expected_state_component_keys
        and all(is_sha256(value) for value in state_components.values())
        and resolved.get("reservation_depth") == 1
        and resolved.get("max_selected_edges_per_bag") in {0, 1}
        and resolved.get("runtime_state_sha256")
        == expected_runtime_state_sha256
        and resolved.get("clone_group_id")
        == clone_group_sha256_from_runtime_state(
            str(expected_runtime_state_sha256)
        )
        and hashes.get("H_bag")
        == resolved_intervention_sha256(resolved, "H_bag")
        and hashes.get("H_system")
        == resolved_intervention_sha256(resolved, "H_system")
        and pair.get("resolved_execution_runtime_state_sha256")
        == resolved.get("runtime_state_sha256")
        == pair.get("source_checkpoint_state_sha256")
        and pair.get("resolved_execution_boundary_sha256")
        == resolved.get("boundary_sha256")
        and pair.get("resolved_execution_intervention_sha256")
        == hashes.get(horizon)
        and resolved.get("queue_top_not_popped") is True
        and resolved.get("staged_event_sink_empty") is True,
        "RESOLVED_DESCRIPTOR_EXECUTION_BINDING_DRIFT",
    )
    require(
        resolved.get("candidate_action_count")
        == resolved.get("alternative_action_count")
        and resolved.get("total_legal_action_count")
        == resolved.get("candidate_action_count") + 1,
        "RESOLVED_DESCRIPTOR_ACTION_COUNT_DRIFT",
    )
    for counter in (
        "runtime_global_scan_count",
        "runtime_future_route_read_count",
        "runtime_future_schedule_read_count",
    ):
        require(
            resolved.get(counter) == 0,
            f"RESOLVED_DESCRIPTOR_LEAKAGE:{counter}",
        )
    return dict(resolved)


def action_certificate_valid(
    pair: Mapping[str, Any], target: Mapping[str, Any]
) -> bool:
    certificate = pair.get("committed_action_certificate")
    baseline_step = pair.get("baseline_step")
    treatment_step = pair.get("treatment_step")
    if not all(
        isinstance(value, dict)
        for value in (certificate, baseline_step, treatment_step)
    ):
        return False
    resolved = validate_resolved_execution_descriptor(pair, target)
    resolved_hashes = resolved["intervention_sha256_by_horizon"]
    expected_direct = sorted(
        {
            int(target["runtime_bag_id"]),
            *(
                [int(target["peer_runtime_bag_id"])]
                if target.get("kind") == "I1"
                else []
            ),
        }
    )
    step_valid = (
        baseline_step.get("event_processed") is True
        and baseline_step.get("treatment_requested") is False
        and baseline_step.get("intervention_applied") is False
        and baseline_step.get("changed_action_count") == 0
        and treatment_step.get("event_processed") is True
        and treatment_step.get("treatment_requested") is True
        and treatment_step.get("target_opportunity_observed") is True
        and treatment_step.get("intervention_applied") is True
        and treatment_step.get("changed_action_count") == 1
        and treatment_step.get("requested_boundary_sha256")
        == resolved.get("boundary_sha256")
        and treatment_step.get("requested_intervention_sha256")
        == resolved_hashes.get(target.get("horizon"))
        and treatment_step.get("application_reason")
        == certificate.get("application_reason")
        and sorted(treatment_step.get("affected_runtime_bag_ids", []))
        == expected_direct
        and treatment_step.get("source_state_sha256")
        == baseline_step.get("source_state_sha256")
        == pair.get("source_checkpoint_state_sha256")
        == resolved.get("runtime_state_sha256")
    )
    snapshots_valid = all(
        isinstance(certificate.get(field), list)
        for field in (
            "baseline_pre_action_snapshots",
            "treatment_pre_action_snapshots",
            "baseline_post_action_snapshots",
            "treatment_post_action_snapshots",
        )
    )
    if not snapshots_valid:
        return False
    baseline_pre = certificate["baseline_pre_action_snapshots"]
    treatment_pre = certificate["treatment_pre_action_snapshots"]
    baseline_post = certificate["baseline_post_action_snapshots"]
    treatment_post = certificate["treatment_post_action_snapshots"]

    def snapshot_map(rows: Sequence[Any]) -> dict[int, Mapping[str, Any]]:
        return {
            int(row["runtime_bag_id"]): row
            for row in rows
            if isinstance(row, dict) and "runtime_bag_id" in row
        }

    baseline_pre_by_id = snapshot_map(baseline_pre)
    treatment_pre_by_id = snapshot_map(treatment_pre)
    baseline_post_by_id = snapshot_map(baseline_post)
    treatment_post_by_id = snapshot_map(treatment_post)
    expected_id_set = set(expected_direct)
    snapshots_valid = (
        len(baseline_pre_by_id) == len(baseline_pre)
        == len(expected_direct)
        and len(treatment_pre_by_id) == len(treatment_pre)
        == len(expected_direct)
        and len(baseline_post_by_id) == len(baseline_post)
        == len(expected_direct)
        and len(treatment_post_by_id) == len(treatment_post)
        == len(expected_direct)
        and set(baseline_pre_by_id)
        == set(treatment_pre_by_id)
        == set(baseline_post_by_id)
        == set(treatment_post_by_id)
        == expected_id_set
        and baseline_pre == treatment_pre
        and all(
            snapshot.get("known") is True
            for snapshot in (
                *baseline_pre,
                *treatment_pre,
                *baseline_post,
                *treatment_post,
            )
        )
        and certificate.get("pre_action_snapshots_match") is True
    )

    def committed_route_action(
        snapshot: Mapping[str, Any],
    ) -> tuple[str, int]:
        if (
            int(snapshot.get("pending_merge_request_id", 0)) != 0
            and int(snapshot.get("pending_merge_destination", -1)) >= 0
        ):
            return (
                "MERGE_REQUEST_ENQUEUED",
                int(snapshot["pending_merge_destination"]),
            )
        if int(snapshot.get("transit_to", -1)) >= 0:
            return "EDGE_COMMIT", int(snapshot["transit_to"])
        return "NO_ROUTE_COMMIT", -1

    kind = target.get("kind")
    runtime_id = int(target["runtime_bag_id"])
    baseline_action = str(certificate.get("baseline_action", ""))
    treatment_action = str(certificate.get("treatment_action", ""))
    semantic = False
    if kind == "I1":
        pre_winner = baseline_pre_by_id.get(runtime_id, {})
        peer_id = int(target["peer_runtime_bag_id"])
        pre_peer = baseline_pre_by_id.get(peer_id, {})
        baseline_winner = baseline_post_by_id.get(runtime_id, {})
        baseline_peer = baseline_post_by_id.get(peer_id, {})
        treatment_winner = treatment_post_by_id.get(runtime_id, {})
        treatment_peer = treatment_post_by_id.get(peer_id, {})
        semantic = (
            certificate.get("committed_action_type") == "SOURCE_ADMIT"
            and certificate.get("application_reason")
            == "APPLIED_I1_SOURCE_ADMIT_COMMITTED_ONE_ACTION"
            and baseline_action == target.get("baseline_action")
            and treatment_action == target.get("intervention_action")
            and strict_float(
                pre_winner.get("admitted_time"), "i1.pre_winner.admitted"
            )
            < 0.0
            and strict_float(
                pre_peer.get("admitted_time"), "i1.pre_peer.admitted"
            )
            < 0.0
            and pre_winner.get("source_queued_at_current_node") is True
            and pre_peer.get("source_queued_at_current_node") is True
            and pre_winner.get("current_node")
            == pre_peer.get("current_node")
            and strict_float(
                baseline_winner.get("admitted_time"),
                "i1.baseline_winner.admitted",
            )
            >= 0.0
            and strict_float(
                baseline_peer.get("admitted_time"),
                "i1.baseline_peer.admitted",
            )
            < 0.0
            and strict_float(
                treatment_winner.get("admitted_time"),
                "i1.treatment_winner.admitted",
            )
            < 0.0
            and strict_float(
                treatment_peer.get("admitted_time"),
                "i1.treatment_peer.admitted",
            )
            >= 0.0
        )
    elif kind == "I3":
        baseline_next = int(target["baseline_next_node"])
        selected_next = int(target["selected_next_node"])
        commit_type = certificate.get("committed_action_type")
        pre = baseline_pre_by_id.get(runtime_id, {})
        baseline_commit = committed_route_action(
            baseline_post_by_id.get(runtime_id, {})
        )
        treatment_commit = committed_route_action(
            treatment_post_by_id.get(runtime_id, {})
        )
        expected_reason = {
            "EDGE_COMMIT": "APPLIED_I3_ONE_EDGE_COMMIT_ONE_ACTION",
            "MERGE_REQUEST_ENQUEUED": (
                "APPLIED_I3_MERGE_REQUEST_ENQUEUED_ONE_ACTION"
            ),
        }.get(str(commit_type))
        semantic = (
            commit_type in {"EDGE_COMMIT", "MERGE_REQUEST_ENQUEUED"}
            and baseline_action
            == f"{baseline_commit[0]}:NEXT_NODE={baseline_commit[1]}"
            and treatment_action
            == f"{treatment_commit[0]}:NEXT_NODE={treatment_commit[1]}"
            and baseline_commit[1] == baseline_next
            and treatment_commit == (commit_type, selected_next)
            and baseline_commit[1] != treatment_commit[1]
            and pre.get("queued_at_current_node") is True
            and pre.get("status") == "JUNCTION_QUEUE"
            and int(pre.get("pending_merge_request_id", -1)) == 0
            and target.get("baseline_action")
            == f"NEXT_EDGE_RUNTIME_BAG_ID={runtime_id};NEXT_NODE={baseline_next}"
            and target.get("intervention_action")
            == f"NEXT_EDGE_RUNTIME_BAG_ID={runtime_id};NEXT_NODE={selected_next}"
            and certificate.get("application_reason") == expected_reason
        )
    elif kind == "I4":
        pre = baseline_pre_by_id.get(runtime_id, {})
        baseline_commit = committed_route_action(
            baseline_post_by_id.get(runtime_id, {})
        )
        treatment_snapshot = treatment_post_by_id.get(runtime_id, {})
        semantic = (
            certificate.get("committed_action_type") == "SAFE_HOLD"
            and treatment_action == "SAFE_HOLD"
            and baseline_action
            == f"{baseline_commit[0]}:NEXT_NODE={baseline_commit[1]}"
            and baseline_commit[0] != "NO_ROUTE_COMMIT"
            and target.get("baseline_action")
            == f"RELEASE_RUNTIME_BAG_ID={runtime_id}"
            and target.get("intervention_action")
            == f"SAFE_HOLD_RUNTIME_BAG_ID={runtime_id}"
            and certificate.get("application_reason")
            == "APPLIED_I4_SAFE_HOLD_UNTIL_NEXT_JUNCTION_SERVICE_OPPORTUNITY"
            and pre.get("queued_at_current_node") is True
            and pre.get("status") == "JUNCTION_QUEUE"
            and int(pre.get("pending_merge_request_id", -1)) == 0
            and pre.get("junction_wakeup_pending") is True
            and strict_float(
                pre.get("junction_wakeup_time"),
                "i4.pre.junction_wakeup_time",
            )
            == strict_float(target.get("event_time"), "i4.event_time")
            and treatment_snapshot.get("queued_at_current_node") is True
            and treatment_snapshot.get("junction_wakeup_pending") is True
            and int(
                treatment_snapshot.get(
                    "junction_wakeup_generation", -1
                )
            )
            > int(pre.get("junction_wakeup_generation", -1))
            and strict_float(
                treatment_snapshot.get("junction_wakeup_time"),
                "i4.treatment.junction_wakeup_time",
            )
            > strict_float(target.get("event_time"), "i4.event_time")
            and treatment_snapshot.get("status") == "JUNCTION_QUEUE"
            and int(
                treatment_snapshot.get("pending_merge_request_id", -1)
            )
            == 0
        )
    expected_change_type = {
        "I1": "SOURCE_ADMIT_COMMIT",
        "I3": "EDGE_COMMIT_OR_MERGE_REQUEST_ENQUEUED",
        "I4": "SAFE_HOLD_UNTIL_NEXT_JUNCTION_SERVICE_OPPORTUNITY",
    }.get(str(kind))
    independently_valid = bool(
        certificate.get("changed_action_count") == 1
        and baseline_action != treatment_action
        and target.get("expected_action_change_type")
        == expected_change_type
        and step_valid
        and snapshots_valid
        and semantic
    )
    return bool(
        independently_valid
        and certificate.get("valid") is independently_valid
        and certificate.get("post_commit_verified")
        is independently_valid
    )


def direct_outcome_metrics(
    rows: Any,
    *,
    expected_runtime_ids: Sequence[int],
    branch_name: str,
) -> tuple[dict[int, Mapping[str, Any]], dict[str, Any]]:
    require(
        isinstance(rows, list)
        and all(isinstance(row, dict) for row in rows),
        f"DIRECT_OUTCOMES_MISSING:{branch_name}",
    )
    by_id = {
        strict_int(
            row.get("runtime_bag_id"),
            f"direct.{branch_name}.runtime_bag_id",
        ): row
        for row in rows
    }
    require(
        len(by_id) == len(rows)
        and sorted(by_id) == list(expected_runtime_ids),
        f"DIRECT_OUTCOME_IDENTITY:{branch_name}",
    )
    numeric_fields = (
        "finish_time",
        "completion_seconds",
        "source_wait_seconds",
        "total_local_wait_seconds",
        "junction_wait_seconds",
        "merge_wait_seconds",
        "edge_travel_seconds",
        "node_service_seconds",
        "loop_extra_seconds",
    )
    sums = {name: 0.0 for name in numeric_fields[2:]}
    completions: list[float] = []
    deadline_miss = 0
    decisions = 0
    retries = 0
    loops = 0
    for runtime_id in expected_runtime_ids:
        row = by_id[runtime_id]
        require(
            row.get("known") is True
            and row.get("completed") is True
            and row.get("failed") is False
            and row.get("status") == "COMPLETED"
            and row.get("failure_reason") == "",
            f"DIRECT_OUTCOME_NOT_COMPLETE:{branch_name}:{runtime_id}",
        )
        numeric = {
            name: strict_float(
                row.get(name), f"direct.{branch_name}.{name}"
            )
            for name in numeric_fields
        }
        completions.append(numeric["completion_seconds"])
        for name in sums:
            sums[name] += numeric[name]
        deadline = strict_float(
            row.get("deadline"), f"direct.{branch_name}.deadline"
        )
        if deadline >= 0.0 and numeric["finish_time"] > deadline:
            deadline_miss += 1
        decisions += strict_int(
            row.get("decision_count"),
            f"direct.{branch_name}.decision_count",
        )
        retries += strict_int(
            row.get("retry_count"),
            f"direct.{branch_name}.retry_count",
        )
        loops += strict_int(
            row.get("loop_count"),
            f"direct.{branch_name}.loop_count",
        )
    denominator = len(rows)
    ordered = sorted(completions)
    def nearest_rank(probability: float) -> float:
        rank = max(1, int(math.ceil(probability * denominator)))
        return ordered[rank - 1]

    completion_total = 0.0
    for value in completions:
        completion_total += value
    metrics = {
        "cohort_size": denominator,
        "known_count": denominator,
        "completed_count": denominator,
        "failed_count": 0,
        "deadline_miss_count": deadline_miss,
        "completion_mean_seconds": completion_total / denominator,
        "completion_p95_seconds": nearest_rank(0.95),
        "completion_p99_seconds": nearest_rank(0.99),
        "quantile_method": "NEAREST_RANK_CEILING",
        **{
            f"{name[:-8]}_mean_seconds": total / denominator
            for name, total in sums.items()
        },
        "decision_count": decisions,
        "retry_count": retries,
        "loop_count": loops,
        "path_length_hops_total": decisions,
        "path_length_hops_mean": decisions / denominator,
        "path_length_definition": "COMMITTED_ONE_EDGE_ACTION_COUNT",
    }
    return by_id, metrics


def derive_label(
    pair: Mapping[str, Any], target: Mapping[str, Any]
) -> dict[str, Any]:
    horizon = str(pair.get("horizon"))
    action_changed = pair.get("action_changed") is True
    resolved_descriptor = pair.get("resolved_execution_descriptor")
    resolved_state_sha256 = (
        resolved_descriptor.get("runtime_state_sha256")
        if isinstance(resolved_descriptor, dict)
        else None
    )
    same_state = (
        pair.get("same_state_start") is True
        and pair.get("baseline_start_state_sha256")
        == pair.get("treatment_start_state_sha256")
        == pair.get("source_checkpoint_state_sha256")
        == resolved_state_sha256
    )
    certificate = pair.get("committed_action_certificate")
    certificate_valid = action_certificate_valid(pair, target)
    baseline, treatment = pair.get("baseline"), pair.get("treatment")
    if not isinstance(baseline, dict) or not isinstance(treatment, dict):
        label = {
            "schema": LABEL_SCHEMA,
            "target_key": target["target_key"],
            "descriptor_id": target["descriptor_id"],
            "kind": target["kind"],
            "clone_group_id": target["clone_group_id"],
            "resolved_execution_descriptor_id": (
                resolved_descriptor.get("descriptor_id")
                if isinstance(resolved_descriptor, dict)
                else None
            ),
            "resolved_execution_clone_group_id": (
                resolved_descriptor.get("clone_group_id")
                if isinstance(resolved_descriptor, dict)
                else None
            ),
            "resolved_execution_runtime_state_sha256": (
                resolved_state_sha256
            ),
            "resolved_execution_boundary_sha256": (
                resolved_descriptor.get("boundary_sha256")
                if isinstance(resolved_descriptor, dict)
                else None
            ),
            "event_ordinal": target["event_ordinal"],
            "horizon": horizon,
            "eligible_causal_label": False,
            "exclusion_reason": pair.get(
                "false_positive_reason", "MISSING_BRANCH_EVIDENCE"
            ),
            "pair_status": pair.get("pair_status"),
            "action_changed": action_changed,
            "same_state_start": same_state,
            "certificate_valid": certificate_valid,
            "baseline_hard_gate_pass": False,
            "treatment_hard_gate_pass": False,
            "hard_gate_pass": False,
            "safety_hard_gate_pass": False,
            "safety_equivalent": False,
            "safety_hard_gate_blockers": ["BRANCH_EVIDENCE_MISSING"],
            "horizon_complete": False,
            "evidence_complete": False,
            "h_system_cohort_size": pair.get("h_system_cohort_size", 0),
            "h_system_cohort_is_all_input_runtime_ids": pair.get(
                "h_system_cohort_is_all_input_runtime_ids", False
            ),
            "h_system_cohort_mapping_sha256": target.get(
                "h_system_cohort_mapping_sha256"
            ),
            "raw_bag_mapping_sha256": target.get(
                "raw_bag_mapping_sha256"
            ),
            "raw_bag_original_entry_mapping_sha256": target.get(
                "raw_bag_original_entry_mapping_sha256"
            ),
            "system_externality_observation_status": (
                "NOT_OBSERVED_AT_H_BAG"
                if horizon == "H_bag"
                else "MISSING_REQUIRED_H_SYSTEM_EVIDENCE"
            ),
            "sampling": target.get("sampling"),
            "coverage_tags": target.get("coverage_tags", []),
            "offline_sampling_metadata": target.get(
                "offline_sampling_metadata"
            ),
        }
        label["label_sha256"] = canonical_sha256(label)
        return label
    require(
        isinstance(resolved_descriptor, dict),
        "PAIR_BRANCH_EVIDENCE_WITHOUT_RESOLVED_DESCRIPTOR",
    )
    validate_resolved_execution_descriptor(pair, target)
    horizon_complete = (
        pair.get("horizon_complete") is True
        and baseline.get("horizon_complete") is True
        and treatment.get("horizon_complete") is True
        and baseline.get("blocked") is False
        and treatment.get("blocked") is False
    )
    horizon_blockers = (
        [] if horizon_complete else ["HORIZON_INCOMPLETE_OR_BLOCKED"]
    )
    baseline_gate, baseline_blockers = derive_branch_gate(
        baseline,
        horizon,
        terminal_evidence_complete=horizon_complete,
        protected_full_1x_shape=(
            pair.get("protected_full_1x_shape") is True
        ),
    )
    treatment_gate, treatment_blockers = derive_branch_gate(
        treatment,
        horizon,
        terminal_evidence_complete=horizon_complete,
        protected_full_1x_shape=(
            pair.get("protected_full_1x_shape") is True
        ),
    )
    baseline_invariants = baseline["invariants"]
    treatment_invariants = treatment["invariants"]
    expected_live_safety = (
        baseline_invariants["live_safety_pass"] is True
        and treatment_invariants["live_safety_pass"] is True
    )
    expected_formal_evaluated = horizon == "H_system"
    expected_formal_pass = (
        expected_formal_evaluated
        and baseline_invariants["formal_hard_gate_pass"] is True
        and treatment_invariants["formal_hard_gate_pass"] is True
    )
    expected_hard_gate_pass = expected_live_safety and (
        not expected_formal_evaluated or expected_formal_pass
    )
    expected_pair_complete = (
        horizon_complete and expected_hard_gate_pass
    )
    expected_pair_status = (
        "ACTION_CHANGED_HORIZON_BLOCKED"
        if not horizon_complete
        else "ACTION_CHANGED_HARD_GATE_FAILED"
        if not expected_hard_gate_pass
        else "ACTION_CHANGED_HORIZON_COMPLETE"
    )
    expected_pair_reasons = [
        *[
            f"BASELINE:{reason}"
            for reason in baseline_invariants["hard_gate_fail_reasons"]
        ],
        *[
            f"TREATMENT:{reason}"
            for reason in treatment_invariants["hard_gate_fail_reasons"]
        ],
    ]
    require(
        pair.get("horizon_complete") is horizon_complete
        and pair.get("pair_complete") is expected_pair_complete
        and pair.get("live_safety_pass") is expected_live_safety
        and pair.get("safety_equivalent") is expected_live_safety
        and pair.get("formal_hard_gate_evaluated")
        is expected_formal_evaluated
        and pair.get("formal_hard_gate_pass") is expected_formal_pass
        and pair.get("hard_gate_pass") is expected_hard_gate_pass
        and pair.get("hard_gate_fail_reasons")
        == expected_pair_reasons
        and pair.get("pair_status") == expected_pair_status,
        "PAIR_HARD_GATE_DERIVATION_DRIFT",
    )
    baseline_metrics = baseline.get("cohort_metrics")
    treatment_metrics = treatment.get("cohort_metrics")
    require(
        isinstance(baseline_metrics, dict)
        and isinstance(treatment_metrics, dict),
        "PAIR_METRICS_MISSING",
    )
    expected_direct = sorted(
        {
            int(target["runtime_bag_id"]),
            *(
                [int(target["peer_runtime_bag_id"])]
                if target.get("kind") == "I1"
                else []
            ),
        }
    )
    baseline_direct, expected_baseline_direct_metrics = (
        direct_outcome_metrics(
            baseline.get("affected_bag_outcomes"),
            expected_runtime_ids=expected_direct,
            branch_name="baseline",
        )
    )
    treatment_direct, expected_treatment_direct_metrics = (
        direct_outcome_metrics(
            treatment.get("affected_bag_outcomes"),
            expected_runtime_ids=expected_direct,
            branch_name="treatment",
        )
    )
    identity_fields = (
        "task_id",
        "segment_id",
        "start",
        "goal",
        "release_time",
        "deadline",
    )
    require(
        all(
            all(
                baseline_direct[runtime_id].get(field)
                == treatment_direct[runtime_id].get(field)
                for field in identity_fields
            )
            for runtime_id in expected_direct
        ),
        "DIRECT_OUTCOME_BASELINE_TREATMENT_IDENTITY_DRIFT",
    )
    if horizon == "H_bag":
        require(
            baseline_metrics == expected_baseline_direct_metrics
            and treatment_metrics == expected_treatment_direct_metrics,
            "H_BAG_COHORT_METRICS_NOT_REDERIVED_FROM_DIRECT_OUTCOMES",
        )
    delta = derive_metric_delta(baseline_metrics, treatment_metrics)
    affected = derive_affected_deltas(
        baseline.get("affected_bag_outcomes"),
        treatment.get("affected_bag_outcomes"),
    )
    direct = pair.get(
        "direct_affected_runtime_bag_ids",
        pair.get("affected_runtime_bag_ids", []),
    )
    baseline_ids = sorted(
        int(row["runtime_bag_id"])
        for row in baseline.get("affected_bag_outcomes", [])
    )
    treatment_ids = sorted(
        int(row["runtime_bag_id"])
        for row in treatment.get("affected_bag_outcomes", [])
    )
    delta_ids = sorted(int(row["runtime_bag_id"]) for row in affected)
    native_deltas = pair.get("affected_bag_deltas")
    require(
        isinstance(native_deltas, list)
        and all(isinstance(row, dict) for row in native_deltas)
        and sorted(int(row["runtime_bag_id"]) for row in native_deltas)
        == expected_direct
        and sorted(int(value) for value in direct) == expected_direct
        and baseline_ids
        == treatment_ids
        == delta_ids
        == expected_direct,
        "DIRECT_AFFECTED_EVIDENCE_DRIFT",
    )
    direct_delta = sum(
        row["delta_completion_seconds"] for row in affected
    ) / len(affected)
    direct_signed = signed_label(direct_delta)
    system_completion_delta = (
        delta["delta_completion_mean_seconds"]
        if horizon == "H_system"
        else None
    )
    system_signed = (
        signed_label(system_completion_delta)
        if system_completion_delta is not None
        else None
    )
    realized = pair.get("realized_affected_runtime_bag_ids")
    externality = pair.get("externality_runtime_bag_ids")
    realized_observable = (
        horizon == "H_system"
        and pair.get("realized_affected_set_observable") is True
        and pair.get("externality_observation_status")
        == "OBSERVED_AT_H_SYSTEM"
        and isinstance(realized, list)
        and isinstance(externality, list)
    )
    fixed_cohort = (
        horizon != "H_system"
        or (
            pair.get("h_system_cohort_is_all_input_runtime_ids") is True
            and pair.get("h_system_cohort_size") == FULL_SEGMENT_COUNT
        )
    )
    evidence_blockers: list[str] = []
    realized_rows: list[dict[str, Any]] | None = None
    realized_direct: list[int] | None = None
    raw_baseline = baseline.get("raw_bag_cohort_metrics")
    raw_treatment = treatment.get("raw_bag_cohort_metrics")
    raw_delta: dict[str, float] | None = None
    baseline_raw_sidecar_binding: dict[str, Any] | None = None
    treatment_raw_sidecar_binding: dict[str, Any] | None = None
    cohort_binding: dict[str, Any] | None = None
    if horizon == "H_system":
        if not realized_observable:
            evidence_blockers.append("REALIZED_AFFECTED_SET_NOT_REPORTED")
        if not fixed_cohort:
            evidence_blockers.append(
                "H_SYSTEM_COHORT_NOT_FIXED_FULL_ORIGINAL"
            )
        if realized_observable:
            realized_rows, realized_ids = validate_realized_deltas(
                pair.get("realized_outcome_deltas"),
                pair.get("realized_outcome_deltas_sha256"),
            )
            realized_values = sorted(int(value) for value in realized)
            external_values = sorted(int(value) for value in externality)
            realized_direct = sorted(
                set(realized_values) & set(expected_direct)
            )
            require(
                realized_values == sorted(realized_ids)
                and external_values
                == sorted(set(realized_values) - set(expected_direct)),
                "REALIZED_PARTITION_DRIFT",
            )
            native_externality = pair.get("realized_externality")
            require(
                isinstance(native_externality, dict)
                and sorted(
                    int(value)
                    for value in native_externality.get(
                        "realized_direct_runtime_bag_ids", []
                    )
                )
                == realized_direct
                and native_externality.get(
                    "realized_outcome_deltas_sha256"
                )
                == pair.get("realized_outcome_deltas_sha256"),
                "REALIZED_EXTERNALITY_BINDING_DRIFT",
            )
        require(
            pair.get("cohort_difference_sidecar_serialized") is True,
            "FULL_COHORT_SIDECAR_NOT_SERIALIZED",
        )
        cohort_binding = validate_cohort_sidecar(
            pair.get("cohort_difference_sidecar"), realized_rows or []
        )
        if not isinstance(raw_baseline, dict) or not isinstance(
            raw_treatment, dict
        ):
            evidence_blockers.append("RAW_BAG_COHORT_METRICS_MISSING")
        else:
            for branch_name, branch, raw in (
                ("baseline", baseline, raw_baseline),
                ("treatment", treatment, raw_treatment),
            ):
                require(
                    raw.get("selected_segment_count")
                    == raw.get("completed_segment_count")
                    == FULL_SEGMENT_COUNT
                    and raw.get("selected_raw_bag_count")
                    == raw.get("complete_raw_bag_count")
                    == FULL_RAW_BAG_COUNT
                    and raw.get("failed_raw_bag_count") == 0
                    and raw.get("comparison_eligible") is True
                    and branch.get("h_system_cohort_mapping_sha256")
                    == target.get("h_system_cohort_mapping_sha256")
                    and branch.get("raw_bag_mapping_sha256")
                    == target.get("raw_bag_mapping_sha256")
                    and branch.get(
                        "raw_bag_original_entry_mapping_sha256"
                    )
                    == target.get(
                        "raw_bag_original_entry_mapping_sha256"
                    ),
                    f"RAW_BAG_BRANCH_DRIFT:{branch_name}",
                )
                require(
                    branch.get(
                        "raw_bag_sufficient_statistics_serialized"
                    )
                    is True,
                    f"RAW_BAG_SUFFICIENT_STATISTICS_NOT_SERIALIZED:{branch_name}",
                )
                sidecar_binding = validate_raw_bag_sufficient_sidecar(
                    branch.get(
                        "raw_bag_sufficient_statistics_sidecar"
                    ),
                    raw_metrics=raw,
                    target=target,
                    branch_name=branch_name,
                )
                if branch_name == "baseline":
                    baseline_raw_sidecar_binding = sidecar_binding
                else:
                    treatment_raw_sidecar_binding = sidecar_binding
            require(
                pair.get("h_system_cohort_mapping_sha256")
                == target.get("h_system_cohort_mapping_sha256")
                and pair.get("raw_bag_mapping_sha256")
                == target.get("raw_bag_mapping_sha256")
                and pair.get("raw_bag_original_entry_mapping_sha256")
                == target.get(
                    "raw_bag_original_entry_mapping_sha256"
                ),
                "PAIR_RAW_MAPPING_DRIFT",
            )
            raw_delta = derive_raw_delta(raw_baseline, raw_treatment)
    else:
        require(
            pair.get("realized_affected_set_observable") is False
            and pair.get("externality_observation_status")
            == "NOT_OBSERVED_AT_H_BAG"
            and pair.get("realized_outcome_deltas") == []
            and pair.get("cohort_difference_sidecar") is None
            and pair.get("cohort_difference_sidecar_serialized") is False,
            "H_BAG_EXTERNALITY_CLAIM_DRIFT",
        )
        for branch_name, branch in (
            ("baseline", baseline),
            ("treatment", treatment),
        ):
            require(
                branch.get("raw_bag_cohort_metrics") is None
                and branch.get(
                    "raw_bag_sufficient_statistics_sidecar"
                )
                is None
                and branch.get(
                    "raw_bag_sufficient_statistics_serialized"
                )
                is False,
                f"H_BAG_RAW_BAG_SIDECAR_MUST_BE_ABSENT:{branch_name}",
            )
        realized = None
        externality = None
        realized_observable = False
    original_entry_delta = (
        raw_delta["delta_original_entry_mean_minutes"] * 60.0
        if raw_delta is not None
        else None
    )
    if original_entry_delta is not None:
        system_signed = signed_label(original_entry_delta)
    all_blockers = baseline_blockers + treatment_blockers
    safety_blockers = list(all_blockers)
    branch_safety = (
        baseline.get("invariants", {}).get("live_safety_pass") is True
        and treatment.get("invariants", {}).get("live_safety_pass") is True
    )
    require(
        pair.get("live_safety_pass") is branch_safety
        and pair.get("safety_equivalent") is branch_safety,
        "PAIR_SAFETY_EQUIVALENCE_DRIFT",
    )
    evidence_complete = not (
        horizon == "H_system" and evidence_blockers
    )
    eligible = (
        pair.get("pair_status") == "ACTION_CHANGED_HORIZON_COMPLETE"
        and horizon_complete
        and action_changed
        and same_state
        and certificate_valid
        and baseline_gate
        and treatment_gate
        and evidence_complete
    )
    exclusion = (
        ""
        if eligible
        else "|".join(
            sorted(
                set(
                    all_blockers
                    + horizon_blockers
                    + evidence_blockers
                    + ([] if action_changed else ["ACTION_NOT_CHANGED"])
                    + ([] if same_state else ["START_STATE_MISMATCH"])
                    + (
                        []
                        if certificate_valid
                        else ["CERTIFICATE_INVALID"]
                    )
                )
            )
        )
    )
    label = {
        "schema": LABEL_SCHEMA,
        "target_key": target["target_key"],
        "descriptor_id": target["descriptor_id"],
        "kind": target["kind"],
        "clone_group_id": target["clone_group_id"],
        "resolved_execution_descriptor_id": resolved_descriptor[
            "descriptor_id"
        ],
        "resolved_execution_clone_group_id": resolved_descriptor[
            "clone_group_id"
        ],
        "resolved_execution_runtime_state_sha256": resolved_descriptor[
            "runtime_state_sha256"
        ],
        "resolved_execution_boundary_sha256": resolved_descriptor[
            "boundary_sha256"
        ],
        "event_ordinal": target["event_ordinal"],
        "horizon": horizon,
        "eligible_causal_label": eligible,
        "exclusion_reason": exclusion,
        "pair_status": pair.get("pair_status"),
        "action_changed": action_changed,
        "same_state_start": same_state,
        "certificate_valid": certificate_valid,
        "baseline_hard_gate_pass": baseline_gate,
        "treatment_hard_gate_pass": treatment_gate,
        "hard_gate_pass": baseline_gate and treatment_gate,
        "safety_hard_gate_pass": not safety_blockers,
        "safety_equivalent": branch_safety,
        "safety_hard_gate_blockers": sorted(set(safety_blockers)),
        "hard_gate_evaluated": action_changed,
        "horizon_complete": horizon_complete,
        "horizon_blockers": horizon_blockers,
        "evidence_complete": evidence_complete,
        "evidence_blockers": sorted(set(evidence_blockers)),
        "h_system_cohort_size": pair.get("h_system_cohort_size", 0),
        "h_system_cohort_is_all_input_runtime_ids": pair.get(
            "h_system_cohort_is_all_input_runtime_ids", False
        ),
        "h_system_cohort_mapping_sha256": target.get(
            "h_system_cohort_mapping_sha256"
        ),
        "raw_bag_mapping_sha256": target.get("raw_bag_mapping_sha256"),
        "raw_bag_original_entry_mapping_sha256": target.get(
            "raw_bag_original_entry_mapping_sha256"
        ),
        "signed_label": direct_signed,
        "direct_affected_signed_label": direct_signed,
        "h_bag_delta_completion_mean_seconds": direct_delta,
        "h_system_signed_label": system_signed,
        "h_system_delta_completion_mean_seconds": system_completion_delta,
        "h_system_delta_original_entry_mean_seconds": original_entry_delta,
        "externality_sign_discordance": (
            horizon == "H_system"
            and direct_signed != system_signed
            and "NEUTRAL_WITHIN_TOLERANCE"
            not in {direct_signed, system_signed}
        ),
        "direct_affected_runtime_bag_ids": direct,
        "realized_affected_runtime_bag_ids": (
            realized if realized_observable else None
        ),
        "realized_direct_runtime_bag_ids": (
            realized_direct if realized_observable else None
        ),
        "externality_runtime_bag_ids": (
            externality if realized_observable else None
        ),
        "realized_affected_set_observable": realized_observable,
        "system_externality_observation_status": (
            "OBSERVED_AT_H_SYSTEM"
            if realized_observable
            else "NOT_OBSERVED_AT_H_BAG"
            if horizon == "H_bag"
            else "MISSING_REQUIRED_H_SYSTEM_EVIDENCE"
        ),
        "realized_outcome_deltas": realized_rows,
        "realized_outcome_deltas_sha256": (
            pair.get("realized_outcome_deltas_sha256")
            if realized_observable
            else None
        ),
        "baseline_metrics": baseline_metrics,
        "treatment_metrics": treatment_metrics,
        "delta_metrics": delta,
        "baseline_affected_bag_outcomes": baseline.get(
            "affected_bag_outcomes"
        ),
        "treatment_affected_bag_outcomes": treatment.get(
            "affected_bag_outcomes"
        ),
        "affected_bag_deltas": affected,
        "baseline_raw_bag_cohort_metrics": (
            raw_baseline if horizon == "H_system" else None
        ),
        "treatment_raw_bag_cohort_metrics": (
            raw_treatment if horizon == "H_system" else None
        ),
        "raw_bag_delta_metrics": raw_delta,
        "baseline_raw_bag_sufficient_statistics_binding": (
            baseline_raw_sidecar_binding
        ),
        "treatment_raw_bag_sufficient_statistics_binding": (
            treatment_raw_sidecar_binding
        ),
        "cohort_difference_sidecar_binding": cohort_binding,
        "committed_action_certificate": certificate,
        "sampling": target.get("sampling"),
        "coverage_tags": target.get("coverage_tags", []),
        "offline_sampling_metadata": target.get(
            "offline_sampling_metadata"
        ),
    }
    label["label_sha256"] = canonical_sha256(label)
    return label


def compact_evidence_path(
    campaign: str, evidence_index: int, *, pilot_round: int = 1
) -> Path:
    namespace = (
        f"pilot_r{pilot_round}" if campaign == "pilot" else campaign
    )
    return (
        COMPACT_EVIDENCE_ROOT
        / namespace
        / (
            f"g4irsf15_{namespace}_compact_evidence_"
            f"{evidence_index:04d}.json.zst"
        )
    )


def validate_h_system_baseline_reference(
    root: Path,
    binding: Any,
    *,
    plan: Mapping[str, Any],
    campaign: str,
) -> dict[str, Any] | None:
    if binding is None:
        return None
    require(campaign == "formal", "PILOT_BASELINE_REFERENCE_FORBIDDEN")
    require(
        isinstance(binding, dict)
        and binding.get("path")
        == H_SYSTEM_BASELINE_REFERENCE_PATH.as_posix(),
        "BASELINE_REFERENCE_BINDING_MISSING",
    )
    path = root / H_SYSTEM_BASELINE_REFERENCE_PATH
    reference = zstd_json(path)
    validate_self_hash(reference, "h_system_baseline_reference")
    require(
        file_sha256(path) == binding.get("sha256")
        and publishable_byte_count(
            path, "h_system_baseline_reference"
        )
        == binding.get("byte_count")
        and reference.get("self_sha256")
        == binding.get("self_sha256")
        and reference.get("source_target_key")
        == binding.get("source_target_key")
        and reference.get("schema")
        == H_SYSTEM_BASELINE_REFERENCE_SCHEMA
        and reference.get("plan_self_sha256")
        == plan.get("self_sha256")
        and reference.get("source_bundle_sha256")
        == plan.get("source_bundle_sha256")
        and reference.get("binary_sha256")
        == plan.get("binary", {}).get("sha256_before"),
        "BASELINE_REFERENCE_FILE_BINDING_DRIFT",
    )
    task_binding = plan["protected_inputs"]["task"]
    require(
        reference.get("input_runtime_cohort_sha256")
        == task_binding.get("input_runtime_cohort_sha256")
        and reference.get("h_system_cohort_mapping_sha256")
        == task_binding.get("runtime_segment_mapping_sha256")
        and reference.get("raw_bag_mapping_sha256")
        == task_binding.get("raw_bag_mapping_sha256")
        and reference.get("raw_bag_original_entry_mapping_sha256")
        == task_binding.get(
            "raw_bag_original_entry_mapping_sha256"
        ),
        "BASELINE_REFERENCE_PROTECTED_INPUT_DRIFT",
    )
    h_system_target_keys = {
        str(target["target_key"])
        for shard in plan["shards"]
        for target in shard["targets"]
        if target.get("horizon") == "H_system"
    }
    require(
        str(reference.get("source_target_key"))
        in h_system_target_keys,
        "BASELINE_REFERENCE_SOURCE_TARGET_NOT_PREREGISTERED_H_SYSTEM",
    )
    require(
        is_sha256(reference.get("baseline_terminal_state_sha256"))
        and is_sha256(
            reference.get("baseline_cohort_outcome_sha256")
        )
        and isinstance(
            reference.get("baseline_cohort_metrics"), dict
        )
        and isinstance(
            reference.get("baseline_raw_bag_cohort_metrics"),
            dict,
        ),
        "BASELINE_REFERENCE_BRANCH_SUMMARY_INVALID",
    )
    inventory = reference.get("baseline_outcome_hash_inventory")
    require(
        isinstance(inventory, dict),
        "BASELINE_HASH_INVENTORY_MISSING",
    )
    validate_self_hash(inventory, "baseline_hash_inventory")
    rows = inventory.get("rows")
    require(
        inventory.get("schema")
        == (
            "czr005.g4irsf15."
            "baseline_cohort_outcome_hash_inventory.v1"
        )
        and inventory.get("row_count") == FULL_SEGMENT_COUNT
        and inventory.get("complete_coverage") is True
        and inventory.get("runtime_id_order")
        == "CONTIGUOUS_ZERO_BASED_INPUT_ORDER"
        and isinstance(rows, list)
        and len(rows) == FULL_SEGMENT_COUNT,
        "BASELINE_HASH_INVENTORY_COVERAGE",
    )
    for runtime_id, row in enumerate(rows):
        require(
            isinstance(row, dict)
            and row.get("runtime_bag_id") == runtime_id
            and is_sha256(row.get("baseline_outcome_sha256")),
            f"BASELINE_HASH_INVENTORY_ROW:{runtime_id}",
        )
    validate_raw_bag_sufficient_sidecar(
        reference.get(
            "baseline_raw_bag_sufficient_statistics_sidecar"
        ),
        raw_metrics=reference["baseline_raw_bag_cohort_metrics"],
        target={
            "h_system_cohort_mapping_sha256": reference[
                "h_system_cohort_mapping_sha256"
            ],
            "raw_bag_mapping_sha256": reference[
                "raw_bag_mapping_sha256"
            ],
            "raw_bag_original_entry_mapping_sha256": reference[
                "raw_bag_original_entry_mapping_sha256"
            ],
        },
        branch_name="baseline_reference",
    )
    return reference


def hydrate_compact_pair(
    compact_pair: Mapping[str, Any],
    reference: Mapping[str, Any] | None,
    *,
    expected_target_key: str,
) -> dict[str, Any]:
    pair = copy.deepcopy(dict(compact_pair))
    storage = pair.pop("compact_storage", None)
    require(
        pair.pop("target_key", None) == expected_target_key,
        "COMPACT_PAIR_TARGET_KEY_DRIFT",
    )
    if storage == "INLINE_NATIVE_SMALL_EVIDENCE":
        return pair
    require(
        storage
        == "GLOBAL_BASELINE_PLUS_SPARSE_TREATMENT_OVERLAYS"
        and isinstance(reference, Mapping),
        "COMPACT_H_SYSTEM_BASELINE_REFERENCE_MISSING",
    )
    validate_self_hash(reference, "h_system_baseline_reference")
    baseline = pair.get("baseline")
    treatment = pair.get("treatment")
    require(
        isinstance(baseline, dict) and isinstance(treatment, dict),
        "COMPACT_H_SYSTEM_BRANCHES_MISSING",
    )
    baseline_binding = baseline.get(
        "raw_bag_sufficient_statistics_sidecar"
    )
    raw_overlay = treatment.get(
        "raw_bag_sufficient_statistics_sidecar"
    )
    cohort_overlay = pair.get("cohort_difference_sidecar")
    require(
        isinstance(baseline_binding, dict)
        and baseline_binding.get("storage")
        == "GLOBAL_BASELINE_REFERENCE"
        and isinstance(raw_overlay, dict)
        and isinstance(cohort_overlay, dict),
        "COMPACT_H_SYSTEM_OVERLAY_MISSING",
    )
    validate_self_hash(raw_overlay, "raw_bag_sparse_overlay")
    validate_self_hash(
        cohort_overlay, "cohort_difference_sparse_overlay"
    )
    require(
        raw_overlay.get("schema") == RAW_BAG_SPARSE_OVERLAY_SCHEMA
        and cohort_overlay.get("schema")
        == COHORT_DIFFERENCE_SPARSE_OVERLAY_SCHEMA,
        "COMPACT_OVERLAY_SCHEMA_DRIFT",
    )
    reference_sha = reference["self_sha256"]
    require(
        baseline_binding.get("baseline_reference_self_sha256")
        == reference_sha
        and raw_overlay.get("baseline_reference_self_sha256")
        == reference_sha
        and cohort_overlay.get("baseline_reference_self_sha256")
        == reference_sha,
        "COMPACT_BASELINE_REFERENCE_BINDING_DRIFT",
    )
    reference_sidecar = reference.get(
        "baseline_raw_bag_sufficient_statistics_sidecar"
    )
    require(
        is_sha256(pair.get("h_system_cohort_mapping_sha256"))
        and is_sha256(pair.get("raw_bag_mapping_sha256"))
        and is_sha256(
            pair.get("raw_bag_original_entry_mapping_sha256")
        )
        and is_sha256(baseline.get("terminal_state_sha256"))
        and is_sha256(baseline.get("cohort_outcome_sha256"))
        and isinstance(reference_sidecar, dict)
        and is_sha256(reference_sidecar.get("content_sha256"))
        and pair.get("h_system_cohort_mapping_sha256")
        == reference.get("h_system_cohort_mapping_sha256")
        and pair.get("raw_bag_mapping_sha256")
        == reference.get("raw_bag_mapping_sha256")
        and pair.get("raw_bag_original_entry_mapping_sha256")
        == reference.get(
            "raw_bag_original_entry_mapping_sha256"
        )
        and baseline.get("terminal_state_sha256")
        == reference.get("baseline_terminal_state_sha256")
        and baseline.get("cohort_outcome_sha256")
        == reference.get("baseline_cohort_outcome_sha256")
        and baseline.get("cohort_metrics")
        == reference.get("baseline_cohort_metrics")
        and baseline.get("raw_bag_cohort_metrics")
        == reference.get("baseline_raw_bag_cohort_metrics"),
        "COMPACT_INLINE_BASELINE_REFERENCE_DRIFT",
    )
    baseline_sidecar = copy.deepcopy(
        reference_sidecar
    )
    require(
        baseline_binding.get("logical_content_sha256")
        == baseline_sidecar.get("content_sha256")
        and raw_overlay.get("baseline_content_sha256")
        == baseline_sidecar.get("content_sha256"),
        "COMPACT_BASELINE_RAW_CONTENT_DRIFT",
    )
    treatment_sidecar = copy.deepcopy(baseline_sidecar)
    by_task = {
        int(row["task_id"]): index
        for index, row in enumerate(treatment_sidecar["rows"])
    }
    changed_ids = raw_overlay.get("changed_task_ids")
    changed_rows = raw_overlay.get("rows")
    require(
        isinstance(changed_ids, list)
        and isinstance(changed_rows, list)
        and len(changed_ids)
        == len(changed_rows)
        == raw_overlay.get("changed_row_count")
        and changed_ids == sorted(set(changed_ids)),
        "COMPACT_RAW_OVERLAY_INVENTORY_DRIFT",
    )
    for task_id, row in zip(
        changed_ids, changed_rows, strict=True
    ):
        require(
            isinstance(row, dict)
            and row.get("task_id") == task_id
            and task_id in by_task
            and row.get("runtime_bag_ids")
            == treatment_sidecar["rows"][by_task[task_id]].get(
                "runtime_bag_ids"
            )
            and row.get("row_sha256")
            != treatment_sidecar["rows"][by_task[task_id]].get(
                "row_sha256"
            ),
            f"COMPACT_RAW_OVERLAY_ROW_DRIFT:{task_id}",
        )
        treatment_sidecar["rows"][by_task[task_id]] = copy.deepcopy(
            row
        )
    treatment_sidecar["content_sha256"] = raw_overlay[
        "logical_content_sha256"
    ]
    for field in (
        "row_count",
        "expected_raw_bag_count",
        "selected_segment_count",
        "complete_coverage",
        "task_id_order",
        "runtime_segment_mapping_sha256",
        "raw_bag_mapping_sha256",
        "raw_bag_original_entry_mapping_sha256",
    ):
        require(
            treatment_sidecar.get(field) == raw_overlay.get(field),
            f"COMPACT_RAW_OVERLAY_TOP_LEVEL_DRIFT:{field}",
        )
    raw_content_fields: list[tuple[str, str, Any]] = [
        ("schema", "s", treatment_sidecar.get("schema")),
        ("row_count", "i", treatment_sidecar.get("row_count")),
        (
            "expected_raw_bag_count",
            "i",
            treatment_sidecar.get("expected_raw_bag_count"),
        ),
        (
            "selected_segment_count",
            "i",
            treatment_sidecar.get("selected_segment_count"),
        ),
        (
            "complete_coverage",
            "b",
            treatment_sidecar.get("complete_coverage"),
        ),
        (
            "task_id_order",
            "s",
            treatment_sidecar.get("task_id_order"),
        ),
        (
            "runtime_segment_mapping_sha256",
            "s",
            treatment_sidecar.get(
                "runtime_segment_mapping_sha256"
            ),
        ),
        (
            "raw_bag_mapping_sha256",
            "s",
            treatment_sidecar.get("raw_bag_mapping_sha256"),
        ),
        (
            "raw_bag_original_entry_mapping_sha256",
            "s",
            treatment_sidecar.get(
                "raw_bag_original_entry_mapping_sha256"
            ),
        ),
    ]
    previous_task_id = -1
    for index, row in enumerate(treatment_sidecar["rows"]):
        require(
            isinstance(row, dict)
            and isinstance(row.get("task_id"), int)
            and not isinstance(row.get("task_id"), bool)
            and row["task_id"] > previous_task_id
            and is_sha256(row.get("row_sha256")),
            f"COMPACT_RAW_LOGICAL_ROW_DRIFT:{index}",
        )
        previous_task_id = row["task_id"]
        raw_content_fields.append(
            ("row_sha256", "s", row["row_sha256"])
        )
    require(
        canonical_fields_sha256(raw_content_fields)
        == treatment_sidecar["content_sha256"],
        "COMPACT_RAW_OVERLAY_LOGICAL_CONTENT_DRIFT",
    )
    baseline["raw_bag_sufficient_statistics_sidecar"] = (
        baseline_sidecar
    )
    treatment["raw_bag_sufficient_statistics_sidecar"] = (
        treatment_sidecar
    )

    inventory = reference.get("baseline_outcome_hash_inventory")
    require(
        isinstance(inventory, dict),
        "COMPACT_BASELINE_HASH_INVENTORY_MISSING",
    )
    validate_self_hash(inventory, "baseline_hash_inventory")
    baseline_hash_rows = inventory.get("rows")
    realized_rows = pair.get("realized_outcome_deltas")
    require(
        isinstance(baseline_hash_rows, list)
        and isinstance(realized_rows, list),
        "COMPACT_COHORT_INPUT_ROWS_MISSING",
    )
    realized_by_id = {
        int(row["runtime_bag_id"]): row for row in realized_rows
    }
    changed_runtime_ids = cohort_overlay.get(
        "changed_runtime_bag_ids"
    )
    require(
        isinstance(changed_runtime_ids, list)
        and changed_runtime_ids
        == sorted(set(changed_runtime_ids))
        and set(changed_runtime_ids) == set(realized_by_id)
        and cohort_overlay.get("changed_count")
        == len(changed_runtime_ids),
        "COMPACT_COHORT_CHANGED_INVENTORY_DRIFT",
    )
    cohort_rows: list[dict[str, Any]] = []
    digest_fields: list[tuple[str, str, Any]] = [
        (
            "schema",
            "s",
            "czr005.g4irsf15.full_cohort_outcome_difference.v1",
        ),
        ("row_count", "u", len(baseline_hash_rows)),
    ]
    for runtime_id, baseline_hash_row in enumerate(
        baseline_hash_rows
    ):
        require(
            isinstance(baseline_hash_row, dict)
            and baseline_hash_row.get("runtime_bag_id")
            == runtime_id
            and is_sha256(
                baseline_hash_row.get(
                    "baseline_outcome_sha256"
                )
            ),
            f"COMPACT_BASELINE_HASH_ROW_DRIFT:{runtime_id}",
        )
        baseline_sha = baseline_hash_row[
            "baseline_outcome_sha256"
        ]
        realized = realized_by_id.get(runtime_id)
        if realized is None:
            treatment_sha = baseline_sha
        else:
            require(
                hashlib.sha256(
                    causal_outcome_payload(realized["baseline"])
                ).hexdigest()
                == baseline_sha,
                f"COMPACT_REALIZED_BASELINE_HASH_DRIFT:{runtime_id}",
            )
            treatment_sha = hashlib.sha256(
                causal_outcome_payload(realized["treatment"])
            ).hexdigest()
            require(
                treatment_sha != baseline_sha,
                f"COMPACT_REALIZED_ROW_NOT_CHANGED:{runtime_id}",
            )
        changed = treatment_sha != baseline_sha
        row_sha = canonical_fields_sha256(
            [
                ("runtime_bag_id", "i", runtime_id),
                ("baseline_outcome_sha256", "s", baseline_sha),
                ("treatment_outcome_sha256", "s", treatment_sha),
                ("outcome_changed", "b", changed),
            ]
        )
        cohort_rows.append(
            {
                "runtime_bag_id": runtime_id,
                "baseline_outcome_sha256": baseline_sha,
                "treatment_outcome_sha256": treatment_sha,
                "outcome_changed": changed,
                "row_sha256": row_sha,
            }
        )
        digest_fields.append(("row_sha256", "s", row_sha))
    digest_fields.append(
        ("changed_count", "i", len(changed_runtime_ids))
    )
    logical_content_sha = canonical_fields_sha256(digest_fields)
    require(
        logical_content_sha
        == cohort_overlay.get("logical_content_sha256")
        and cohort_overlay.get("row_count")
        == len(cohort_rows)
        and cohort_overlay.get("realized_outcome_deltas_sha256")
        == pair.get("realized_outcome_deltas_sha256"),
        "COMPACT_COHORT_LOGICAL_CONTENT_DRIFT",
    )
    pair["cohort_difference_sidecar"] = {
        "schema": cohort_overlay["logical_schema"],
        "row_count": len(cohort_rows),
        "changed_count": len(changed_runtime_ids),
        "complete_coverage": cohort_overlay[
            "complete_coverage"
        ],
        "runtime_id_order": cohort_overlay[
            "runtime_id_order"
        ],
        "rows": cohort_rows,
        "content_sha256": logical_content_sha,
    }
    return pair


def compact_label_projection(
    full_label: Mapping[str, Any],
    pair_evidence_sha256: str,
) -> dict[str, Any]:
    require(
        is_sha256(pair_evidence_sha256),
        "PAIR_EVIDENCE_SHA256_INVALID",
    )
    label = copy.deepcopy(dict(full_label))
    label.pop("label_sha256", None)
    realized_rows = label.pop("realized_outcome_deltas", None)
    certificate = label.pop("committed_action_certificate", None)
    label["pair_evidence_sha256"] = pair_evidence_sha256
    label["realized_outcome_deltas_binding"] = (
        None
        if realized_rows is None
        else {
            "row_count": len(realized_rows),
            "content_sha256": label.get(
                "realized_outcome_deltas_sha256"
            ),
        }
    )
    label["committed_action_certificate_sha256"] = (
        canonical_sha256(certificate)
        if isinstance(certificate, dict)
        else None
    )
    label["label_sha256"] = canonical_sha256(label)
    return label


def validate_compact_native_payload_attestation(
    value: Any,
    *,
    plan: Mapping[str, Any],
    shard: Mapping[str, Any],
) -> dict[str, Any]:
    require(
        isinstance(value, dict),
        "COMPACT_NATIVE_ATTESTATION_MISSING",
    )
    validate_self_hash(value, "compact_native_attestation")
    task = plan["protected_inputs"]["task"]
    require(
        value.get("schema") == COMPACT_NATIVE_ATTESTATION_SCHEMA
        and value.get("native_payload_schema") == PAIR_RUN_SCHEMA
        and value.get("evidence_scope")
        == "EXACT_NATIVE_SAME_STATE_ONE_SHOT_MATCHED_PAIRS"
        and value.get("formal_pass_claimed") is False
        and value.get("protected_full_1x_shape") is True
        and value.get("h_system_cohort_policy")
        == "ALL_INPUT_RUNTIME_IDS_IN_INPUT_ORDER"
        and value.get("input_request_count") == FULL_SEGMENT_COUNT
        and value.get("raw_bag_count") == FULL_RAW_BAG_COUNT
        and value.get("input_runtime_cohort_sha256")
        == task.get("input_runtime_cohort_sha256")
        and value.get("h_system_cohort_mapping_sha256")
        == task.get("runtime_segment_mapping_sha256")
        and value.get("raw_bag_mapping_sha256")
        == task.get("raw_bag_mapping_sha256")
        and value.get("raw_bag_original_entry_mapping_sha256")
        == task.get("raw_bag_original_entry_mapping_sha256")
        and value.get("target_count") == shard.get("target_count"),
        "COMPACT_NATIVE_ATTESTATION_SCOPE_OR_INPUT_DRIFT",
    )
    controls = value.get("frozen_controls")
    require(
        isinstance(controls, dict),
        "COMPACT_NATIVE_ATTESTATION_CONTROLS_MISSING",
    )
    for name, expected in FROZEN_CONTROLS.items():
        require(
            controls.get(name) == expected,
            f"COMPACT_NATIVE_ATTESTATION_CONTROL_DRIFT:{name}",
        )
    for field in (
        "action_changing_pair_count",
        "applied_action_changing_pair_count",
        "false_positive_pair_count",
        "complete_action_changing_h_bag_count",
        "applied_action_changing_h_system_count",
        "complete_h_system_hard_gate_pass_count",
        "h_system_pair_count",
    ):
        strict_int(
            value.get(field),
            f"compact_native_attestation.{field}",
            0,
        )
    return dict(value)


def validate_compact_native_summary_counts(
    attestation: Mapping[str, Any],
    pairs: Sequence[Mapping[str, Any]],
) -> None:
    action_count = 0
    false_positive_count = 0
    complete_h_bag_count = 0
    applied_h_system_count = 0
    complete_h_system_count = 0
    for pair in pairs:
        if pair.get("action_changed") is True:
            action_count += 1
            if pair.get("horizon") == "H_system":
                applied_h_system_count += 1
                if (
                    pair.get("pair_complete") is True
                    and pair.get("formal_hard_gate_pass") is True
                ):
                    complete_h_system_count += 1
            elif pair.get("pair_complete") is True:
                complete_h_bag_count += 1
        else:
            false_positive_count += 1
    require(
        len(pairs) == attestation.get("target_count")
        and attestation.get("action_changing_pair_count")
        == attestation.get("applied_action_changing_pair_count")
        == action_count
        and attestation.get("false_positive_pair_count")
        == false_positive_count
        and attestation.get(
            "complete_action_changing_h_bag_count"
        )
        == complete_h_bag_count
        and attestation.get(
            "applied_action_changing_h_system_count"
        )
        == applied_h_system_count
        and attestation.get(
            "complete_h_system_hard_gate_pass_count"
        )
        == attestation.get("h_system_pair_count")
        == complete_h_system_count,
        "COMPACT_NATIVE_ATTESTATION_SUMMARY_COUNT_DRIFT",
    )


def validate_compact_pair_target_identity(
    pair: Mapping[str, Any],
    target: Mapping[str, Any],
) -> None:
    require(
        pair.get("descriptor_id") == target.get("descriptor_id")
        and pair.get("target_address_id")
        == target.get("target_address_id", target.get("descriptor_id"))
        and pair.get("kind") == target.get("kind")
        and pair.get("event_ordinal") == target.get("event_ordinal")
        and pair.get("horizon") == target.get("horizon")
        and pair.get("protected_full_1x_shape") is True,
        "COMPACT_PAIR_PREREGISTERED_TARGET_IDENTITY_DRIFT",
    )


def validate_compact_storage_semantics(
    compact_pair: Mapping[str, Any],
    hydrated_pair: Mapping[str, Any],
) -> None:
    baseline = hydrated_pair.get("baseline")
    treatment = hydrated_pair.get("treatment")
    native_dense_h_system = bool(
        hydrated_pair.get("horizon") == "H_system"
        and isinstance(baseline, dict)
        and isinstance(treatment, dict)
        and isinstance(
            baseline.get("raw_bag_sufficient_statistics_sidecar"),
            dict,
        )
        and isinstance(
            treatment.get("raw_bag_sufficient_statistics_sidecar"),
            dict,
        )
        and isinstance(
            hydrated_pair.get("cohort_difference_sidecar"),
            dict,
        )
    )
    compact_sparse_h_system = (
        compact_pair.get("compact_storage")
        == "GLOBAL_BASELINE_PLUS_SPARSE_TREATMENT_OVERLAYS"
    )
    require(
        native_dense_h_system is compact_sparse_h_system,
        "COMPACT_STORAGE_MODE_SEMANTIC_DRIFT",
    )


def validate_compact_source_run_state_binding(
    evidence: Mapping[str, Any],
    run_state: Mapping[str, Any],
) -> None:
    require(
        evidence.get("source_run_state_sha256")
        == run_state.get("sha256")
        and evidence.get("source_run_state_self_sha256")
        == run_state.get("self_sha256"),
        "COMPACT_SOURCE_RUN_STATE_ATTESTATION_DRIFT",
    )


def validate_compact_global_target_order(
    observed_target_keys: Sequence[str],
    plan: Mapping[str, Any],
) -> None:
    require(
        list(observed_target_keys)
        == [
            str(key)
            for shard in plan["shards"]
            for key in shard["target_keys"]
        ],
        "COMPACT_EVIDENCE_GLOBAL_TARGET_ORDER_DRIFT",
    )


def validate_compact_baseline_reference_order(
    reference: Mapping[str, Any] | None,
    dense_target_keys: Sequence[str],
) -> None:
    if reference is None:
        require(
            not dense_target_keys,
            "COMPACT_DENSE_PAIR_WITHOUT_BASELINE_REFERENCE",
        )
        return
    require(
        bool(dense_target_keys)
        and reference.get("source_target_key")
        == dense_target_keys[0],
        "COMPACT_BASELINE_REFERENCE_NOT_FIRST_DENSE_PAIR",
    )


def collect_compact_evidence_labels(
    root: Path,
    campaign: str,
    plan: Mapping[str, Any],
    *,
    evidence_bindings: Any,
    baseline_binding: Any,
    run_state_attestation: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    require(
        isinstance(evidence_bindings, list)
        and evidence_bindings,
        "COMPACT_EVIDENCE_BINDINGS_MISSING",
    )
    validate_run_state_attestation(
        run_state_attestation,
        plan=plan,
    )
    run_state_by_shard = {
        int(row["shard_index"]): row
        for row in run_state_attestation["shards"]
    }
    reference = validate_h_system_baseline_reference(
        root,
        baseline_binding,
        plan=plan,
        campaign=campaign,
    )
    target_by_key = {
        str(row["target_key"]): row
        for shard in plan["shards"]
        for row in shard["targets"]
    }
    source_shard_by_key = {
        str(key): int(shard["shard_index"])
        for shard in plan["shards"]
        for key in shard["target_keys"]
    }
    labels: list[dict[str, Any]] = []
    normalized_bindings: list[dict[str, Any]] = []
    seen: set[str] = set()
    observed_target_keys: list[str] = []
    dense_count = 0
    dense_target_keys: list[str] = []
    native_attestation_by_shard: dict[int, dict[str, Any]] = {}
    hydrated_pairs_by_shard: dict[
        int, dict[str, dict[str, Any]]
    ] = defaultdict(dict)
    binary_sha = plan["binary"]["sha256_before"]
    pilot_round = int(plan.get("pilot_round", 1))
    for evidence_index, binding in enumerate(evidence_bindings):
        require(
            isinstance(binding, dict)
            and binding.get("evidence_index") == evidence_index,
            "COMPACT_EVIDENCE_INDEX_DRIFT",
        )
        relative = compact_evidence_path(
            campaign,
            evidence_index,
            pilot_round=pilot_round,
        )
        require(
            binding.get("path") == relative.as_posix(),
            "COMPACT_EVIDENCE_PATH_DRIFT",
        )
        path = root / relative
        value = zstd_json(path)
        validate_self_hash(
            value, f"compact_evidence_{evidence_index}"
        )
        require(
            file_sha256(path) == binding.get("sha256")
            and publishable_byte_count(
                path, f"compact_evidence_{evidence_index}"
            )
            == binding.get("byte_count")
            and value.get("self_sha256")
            == binding.get("self_sha256")
            and value.get("schema") == COMPACT_EVIDENCE_SCHEMA
            and value.get("campaign") == campaign
            and value.get("pilot_round")
            == (pilot_round if campaign == "pilot" else None)
            and value.get("evidence_index") == evidence_index
            and value.get("plan_self_sha256")
            == plan["self_sha256"]
            and value.get("binary_sha256") == binary_sha,
            "COMPACT_EVIDENCE_FILE_BINDING_DRIFT",
        )
        source_shard_index = strict_int(
            value.get("source_shard_index"),
            "compact.source_shard_index",
            0,
        )
        require(
            source_shard_index < len(plan["shards"])
            and value.get("source_shard_sha256")
            == plan["shards"][source_shard_index]["shard_sha256"]
            and binding.get("source_shard_index")
            == source_shard_index,
            "COMPACT_SOURCE_SHARD_BINDING_DRIFT",
        )
        run_state = run_state_by_shard[source_shard_index]
        validate_compact_source_run_state_binding(
            value,
            run_state,
        )
        native_attestation = (
            validate_compact_native_payload_attestation(
                value.get("source_native_payload_attestation"),
                plan=plan,
                shard=plan["shards"][source_shard_index],
            )
        )
        require(
            binding.get(
                "source_native_payload_attestation_self_sha256"
            )
            == native_attestation["self_sha256"],
            "COMPACT_NATIVE_ATTESTATION_BINDING_DRIFT",
        )
        prior_native_attestation = native_attestation_by_shard.get(
            source_shard_index
        )
        require(
            prior_native_attestation is None
            or prior_native_attestation == native_attestation,
            "COMPACT_NATIVE_ATTESTATION_INCONSISTENT_WITHIN_SHARD",
        )
        native_attestation_by_shard[source_shard_index] = (
            native_attestation
        )
        pairs = value.get("pairs")
        keys = value.get("target_keys")
        require(
            isinstance(pairs, list)
            and isinstance(keys, list)
            and len(pairs)
            == len(keys)
            == value.get("pair_count")
            == binding.get("target_count")
            and keys == binding.get("target_keys"),
            "COMPACT_EVIDENCE_PAIR_INVENTORY_DRIFT",
        )
        chunk_dense = 0
        for evidence_row, key in zip(pairs, keys, strict=True):
            require(
                isinstance(evidence_row, dict)
                and evidence_row.get("target_key") == key
                and str(key) not in seen
                and str(key) in target_by_key
                and source_shard_by_key[str(key)]
                == source_shard_index,
                "COMPACT_EVIDENCE_TARGET_DRIFT",
            )
            compact_pair = evidence_row.get("pair")
            pair_sha = evidence_row.get("pair_evidence_sha256")
            require(
                isinstance(compact_pair, dict)
                and is_sha256(pair_sha)
                and canonical_sha256(compact_pair) == pair_sha,
                "COMPACT_PAIR_EVIDENCE_HASH_DRIFT",
            )
            is_dense = (
                compact_pair.get("compact_storage")
                == (
                    "GLOBAL_BASELINE_PLUS_"
                    "SPARSE_TREATMENT_OVERLAYS"
                )
            )
            chunk_dense += int(is_dense)
            dense_count += int(is_dense)
            if is_dense:
                dense_target_keys.append(str(key))
            hydrated = hydrate_compact_pair(
                compact_pair,
                reference,
                expected_target_key=str(key),
            )
            validate_compact_storage_semantics(
                compact_pair,
                hydrated,
            )
            target = target_by_key[str(key)]
            validate_compact_pair_target_identity(
                hydrated,
                target,
            )
            full_label = derive_label(
                hydrated, target
            )
            labels.append(
                compact_label_projection(full_label, pair_sha)
            )
            hydrated_pairs_by_shard[source_shard_index][
                str(key)
            ] = hydrated
            seen.add(str(key))
            observed_target_keys.append(str(key))
        require(
            chunk_dense
            == value.get("dense_h_system_pair_count")
            == binding.get("dense_h_system_pair_count")
            and chunk_dense <= 1,
            "COMPACT_EVIDENCE_DENSE_PAIR_CAP_DRIFT",
        )
        normalized_bindings.append(dict(binding))
    require(
        seen == set(target_by_key)
        and len(labels) == plan.get("attempt_budget"),
        "COMPACT_PREREGISTERED_PANEL_NOT_COMPLETE",
    )
    validate_compact_global_target_order(
        observed_target_keys,
        plan,
    )
    require(
        (reference is not None) is (dense_count > 0),
        "COMPACT_BASELINE_OPTIONALITY_DRIFT",
    )
    validate_compact_baseline_reference_order(
        reference,
        dense_target_keys,
    )
    require(
        set(native_attestation_by_shard)
        == set(range(len(plan["shards"]))),
        "COMPACT_NATIVE_ATTESTATION_SHARD_COVERAGE_DRIFT",
    )
    for shard_index, shard in enumerate(plan["shards"]):
        pair_by_key = hydrated_pairs_by_shard[shard_index]
        require(
            list(pair_by_key) == list(shard["target_keys"]),
            f"COMPACT_SOURCE_SHARD_TARGET_ORDER_DRIFT:{shard_index}",
        )
        validate_compact_native_summary_counts(
            native_attestation_by_shard[shard_index],
            [
                pair_by_key[str(key)]
                for key in shard["target_keys"]
            ],
        )
    return labels, normalized_bindings


def validate_run_state_attestation(
    value: Any,
    *,
    plan: Mapping[str, Any],
) -> None:
    require(
        isinstance(value, dict),
        "RUN_STATE_ATTESTATION_MISSING",
    )
    validate_self_hash(value, "run_state_attestation")
    shards = value.get("shards")
    require(
        value.get("schema")
        == "czr005.g4irsf15.ephemeral_run_state_attestation.v1"
        and value.get("retention")
        == "EPHEMERAL_NOT_REQUIRED_FOR_VALIDATION"
        and value.get("committed_to_git") is False
        and isinstance(shards, list)
        and len(shards)
        == value.get("shard_count")
        == len(plan["shards"]),
        "RUN_STATE_ATTESTATION_CONTRACT_DRIFT",
    )
    for index, row in enumerate(shards):
        require(
            isinstance(row, dict)
            and row.get("shard_index") == index
            and is_sha256(row.get("sha256"))
            and is_sha256(row.get("self_sha256"))
            and strict_int(
                row.get("byte_count"),
                "run_state.byte_count",
                1,
            )
            >= 1
            and row.get("target_count")
            == plan["shards"][index]["target_count"]
            and row.get("binary_sha256")
            == plan["binary"]["sha256_before"],
            f"RUN_STATE_ATTESTATION_SHARD_DRIFT:{index}",
        )


def collect_shard_labels(
    root: Path,
    campaign: str,
    plan: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Re-derive every label from the complete preregistered shard panel."""
    labels: list[dict[str, Any]] = []
    bindings: list[dict[str, Any]] = []
    seen: set[str] = set()
    namespace = (
        f"pilot_r{plan.get('pilot_round', 1)}"
        if campaign == "pilot"
        else "formal"
    )
    for expected_index, shard in enumerate(plan["shards"]):
        require(
            shard.get("shard_index") == expected_index,
            "EXECUTED_SHARD_INDEX_NOT_CONTIGUOUS",
        )
        pairs, value = validate_shard(root, campaign, plan, shard)
        for pair, target, key in zip(
            pairs,
            shard["targets"],
            shard["target_keys"],
            strict=True,
        ):
            require(str(key) not in seen, "EXECUTED_TARGET_DUPLICATE")
            seen.add(str(key))
            labels.append(derive_label(pair, target))
        relative = (
            RUN_STATE_SHARD_ROOT
            / namespace
            / f"g4irsf15_{namespace}_shard_{expected_index:04d}.json.zst"
        )
        bindings.append(
            {
                "path": relative.as_posix(),
                "sha256": file_sha256(root / relative),
                "byte_count": (root / relative).stat().st_size,
                "self_sha256": value["self_sha256"],
                "shard_index": expected_index,
                "target_count": len(pairs),
                "binary_sha256": value["binary"]["sha256_before"],
            }
        )
    expected_keys = {
        str(key)
        for shard in plan["shards"]
        for key in shard["target_keys"]
    }
    require(
        seen == expected_keys
        and len(labels) == plan.get("attempt_budget")
        and len(bindings) == len(plan["shards"]),
        "PREREGISTERED_PANEL_NOT_EXECUTED_IN_FULL",
    )
    return labels, bindings


def pilot_false_positive_evidence(
    labels: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    failed = [
        row
        for row in labels
        if row.get("eligible_causal_label") is not True
    ]
    reason_counts: Counter[str] = Counter()
    reasons_by_kind: dict[str, Counter[str]] = {
        kind: Counter() for kind in KINDS
    }
    for row in failed:
        reasons = [
            token
            for token in str(row.get("exclusion_reason", "")).split("|")
            if token
        ] or ["UNCLASSIFIED_NON_ELIGIBLE"]
        for reason in sorted(set(reasons)):
            reason_counts[reason] += 1
            reasons_by_kind[str(row["kind"])][reason] += 1
    projection = {
        "noneligible_attempt_count": len(failed),
        "noneligible_descriptor_ids": sorted(
            str(row["descriptor_id"]) for row in failed
        ),
        "reason_counts": dict(sorted(reason_counts.items())),
        "reason_counts_by_kind": {
            kind: dict(sorted(reasons_by_kind[kind].items()))
            for kind in KINDS
        },
    }
    projection["evidence_sha256"] = canonical_sha256(projection)
    return projection


def orchestrator_publication_path(path: Path, root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def orchestrator_file_binding(
    path: Path, root: Path
) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    return {
        "path": orchestrator_publication_path(resolved, root),
        "file_sha256": file_sha256(resolved),
        "byte_count": resolved.stat().st_size,
    }


def repository_publication_file(
    root: Path, value: Any, label: str
) -> tuple[Path, str]:
    require(isinstance(value, str) and value, f"{label}_PATH_MISSING")
    declared = Path(value)
    require(not declared.is_absolute(), f"{label}_PATH_ABSOLUTE")
    path = (root / declared).resolve()
    try:
        relative = path.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValidationError(f"{label}_PATH_ESCAPES_REPOSITORY") from exc
    require(
        relative == value and Path(relative).as_posix() == value,
        f"{label}_PATH_NOT_CANONICAL",
    )
    try:
        Path(relative).relative_to(ORCHESTRATOR_PROFILE_ROOT)
    except ValueError as exc:
        raise ValidationError(
            f"{label}_OUTSIDE_PUBLICATION_PROFILE_ROOT"
        ) from exc
    require(path.is_file(), f"{label}_FILE_MISSING")
    return path, relative


def orchestrator_timestamp(value: Any, label: str) -> datetime:
    require(isinstance(value, str), f"{label}_NOT_STRING")
    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValidationError(f"{label}_INVALID") from exc
    require(parsed.tzinfo is not None, f"{label}_MISSING_TIMEZONE")
    return parsed


def orchestrator_index_list(
    value: Any, label: str, *, nonempty: bool = False
) -> list[int]:
    require(isinstance(value, list), f"{label}_NOT_LIST")
    indices = [
        strict_int(item, f"{label}.item") for item in value
    ]
    require(
        indices == sorted(set(indices)),
        f"{label}_NOT_STRICT_SORTED_UNIQUE",
    )
    if nonempty:
        require(bool(indices), f"{label}_EMPTY")
    return indices


def validate_orchestrator_stream_binding(
    value: Any, label: str
) -> None:
    require(isinstance(value, dict), f"{label}_NOT_OBJECT")
    require(
        is_sha256(value.get("sha256"))
        and strict_int(
            value.get("byte_count"), f"{label}.byte_count"
        )
        >= 0,
        f"{label}_INVALID",
    )


def producer_join(root_text: str, relative: str) -> str:
    separator = "\\" if "\\" in root_text else "/"
    return (
        root_text.rstrip("/\\")
        + separator
        + relative.replace("/", separator)
    )


def producer_resolve_path(root_text: str, declared: str) -> str:
    if "\\" in root_text:
        normalized = declared.replace("/", "\\")
        return ntpath.normpath(
            normalized
            if ntpath.isabs(normalized)
            else ntpath.join(root_text, normalized)
        )
    normalized = declared.replace("\\", "/")
    return posixpath.normpath(
        normalized
        if posixpath.isabs(normalized)
        else posixpath.join(root_text, normalized)
    )


def producer_binary_argv_path(
    root_text: str,
    bound_path: str,
    *,
    repository_relative: bool,
) -> str:
    return (
        producer_join(root_text, bound_path)
        if repository_relative
        else bound_path
    )


def expected_orchestrator_input_bindings(
    root: Path,
    *,
    plan_path: Path,
    build_binding: Mapping[str, Any],
    declared_inputs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    manifest_path = root / Path(str(build_binding["path"]))
    build_manifest = load_json(manifest_path)
    binary = build_manifest.get("binary")
    require(isinstance(binary, dict), "ORCHESTRATOR_BUILD_BINARY_MISSING")
    binary_relative = build_binding.get("binary_path")
    if binary_relative is not None:
        binary_path = root / Path(str(binary_relative))
        binary_binding = orchestrator_file_binding(binary_path, root)
    else:
        declared_binary = str(binary.get("path", ""))
        declared_profile_binary = (
            declared_inputs.get("binary")
            if isinstance(declared_inputs, Mapping)
            else None
        )
        require(
            declared_binary
            and isinstance(declared_profile_binary, dict)
            and isinstance(
                declared_profile_binary.get("path"), str
            )
            and declared_profile_binary.get("path")
            and declared_profile_binary.get("file_sha256")
            == binary.get("sha256")
            and declared_profile_binary.get("byte_count")
            == strict_int(
                binary.get("byte_count"),
                "orchestrator.build.binary.byte_count",
                1,
            ),
            "ORCHESTRATOR_EXTERNAL_BINARY_CONTENT_BINDING_DRIFT",
        )
        binary_binding = dict(declared_profile_binary)
    require(
        binary_binding["file_sha256"]
        == build_binding.get("binary_sha256"),
        "ORCHESTRATOR_BINARY_BUILD_BINDING_DRIFT",
    )
    return {
        "plan": orchestrator_file_binding(plan_path, root),
        "binary": binary_binding,
        "build_manifest": orchestrator_file_binding(
            manifest_path, root
        ),
        "worker_script": orchestrator_file_binding(
            root / GENERATOR_PATH, root
        ),
        "orchestrator_script": orchestrator_file_binding(
            root / ORCHESTRATOR_PATH, root
        ),
    }


def validate_orchestrator_profile(
    root: Path,
    *,
    stored_binding: Mapping[str, Any],
    campaign: str,
    pilot_round: int,
    plan: Mapping[str, Any],
    plan_path: Path,
    build_binding: Mapping[str, Any],
) -> tuple[dict[str, Any], list[int]]:
    require(
        isinstance(stored_binding, dict),
        "ORCHESTRATOR_PROFILE_BINDING_NOT_OBJECT",
    )
    profile_path, profile_relative = repository_publication_file(
        root,
        stored_binding.get("path"),
        "ORCHESTRATOR_PROFILE",
    )
    profile = load_json(profile_path)
    validate_self_hash(profile, "orchestrator_profile")
    require(
        file_sha256(profile_path) == stored_binding.get("sha256")
        and profile_path.stat().st_size
        == stored_binding.get("byte_count")
        and profile.get("self_sha256")
        == stored_binding.get("self_sha256"),
        "ORCHESTRATOR_PROFILE_FILE_BINDING_DRIFT",
    )
    require(
        profile.get("schema") == ORCHESTRATOR_PROFILE_SCHEMA
        and profile.get("status") == "COMPLETE"
        and profile.get("formal_pass_claimed") is False
        and profile.get("campaign") == campaign
        and profile.get("pilot_round") == pilot_round
        and profile.get("execution_mode")
        == "PRODUCTION_NATIVE_PROCESS_TREE_RSS",
        "ORCHESTRATOR_PROFILE_SCHEMA_STATUS_SCOPE",
    )
    available = list(range(len(plan["shards"])))
    inventory = [
        {
            "shard_index": index,
            "shard_sha256": plan["shards"][index][
                "shard_sha256"
            ],
        }
        for index in available
    ]
    expected_plan_binding = {
        **orchestrator_file_binding(plan_path, root),
        "self_sha256": plan["self_sha256"],
        "shard_count": len(available),
        "available_shard_indices": available,
        "shard_inventory": inventory,
        "shard_inventory_sha256": canonical_sha256(inventory),
    }
    declared_inputs = profile.get("input_artifact_bindings")
    require(
        isinstance(declared_inputs, dict),
        "ORCHESTRATOR_INPUT_BINDINGS_MISSING",
    )
    expected_inputs = expected_orchestrator_input_bindings(
        root,
        plan_path=plan_path,
        build_binding=build_binding,
        declared_inputs=declared_inputs,
    )
    require(
        profile.get("plan") == expected_plan_binding
        and profile.get("input_artifact_bindings") == expected_inputs
        and profile.get("ending_input_artifact_bindings")
        == expected_inputs
        and profile.get("input_artifact_drift") == []
        and profile.get("binary_sha256")
        == build_binding.get("binary_sha256")
        == expected_inputs["binary"]["file_sha256"]
        and profile.get("build_manifest_sha256")
        == expected_inputs["build_manifest"]["file_sha256"],
        "ORCHESTRATOR_PROFILE_INPUT_BINDING_DRIFT",
    )
    requested = orchestrator_index_list(
        profile.get("requested_shard_indices"),
        "orchestrator.requested_shard_indices",
        nonempty=True,
    )
    require(
        set(requested).issubset(available)
        and orchestrator_index_list(
            profile.get("launch_attempted_shard_indices"),
            "orchestrator.launch_attempted_shard_indices",
        )
        == requested
        and orchestrator_index_list(
            profile.get("scheduled_shard_indices"),
            "orchestrator.scheduled_shard_indices",
        )
        == requested
        and orchestrator_index_list(
            profile.get("unscheduled_shard_indices"),
            "orchestrator.unscheduled_shard_indices",
        )
        == []
        and profile.get("completed_result_count") == len(requested)
        and profile.get("successful_shard_count") == len(requested)
        and profile.get("failed_shard_count") == 0
        and profile.get("first_failure_shard_index") is None
        and profile.get("launch_error") is None,
        "ORCHESTRATOR_PROFILE_SHARD_COMPLETION_DRIFT",
    )
    require(
        stored_binding.get("requested_shard_indices") == requested,
        "ORCHESTRATOR_PROFILE_REQUEST_BINDING_DRIFT",
    )
    workers_requested = strict_int(
        profile.get("worker_count_requested"),
        "orchestrator.worker_count_requested",
        1,
    )
    workers_effective = strict_int(
        profile.get("worker_count_effective"),
        "orchestrator.worker_count_effective",
        1,
    )
    require(
        workers_effective == min(workers_requested, len(requested)),
        "ORCHESTRATOR_WORKER_COUNT_DRIFT",
    )
    cap = profile.get("process_rss_cap")
    require(isinstance(cap, dict), "ORCHESTRATOR_RSS_CAP_MISSING")
    cap_mib = strict_float(
        cap.get("max_process_rss_mib"),
        "orchestrator.max_process_rss_mib",
    )
    cap_bytes = strict_int(
        cap.get("max_process_rss_bytes"),
        "orchestrator.max_process_rss_bytes",
        1,
    )
    require(
        cap.get("configured") is True
        and cap.get("required_for_publication_execution") is True
        and 0.0 < cap_mib <= MAX_PUBLICATION_PROCESS_RSS_MIB
        and cap_bytes == int(cap_mib * 1024 * 1024)
        and cap.get("policy")
        == (
            "FAIL_CLOSED_STOP_SCHEDULING_TERMINATE_ONLY_"
            "OFFENDING_WORKER;UNAVAILABLE_SAMPLE_IS_FAILURE"
        )
        and cap.get("cap_scope")
        == "PER_SHARD_WORKER_PROCESS_TREE_RESIDENT_BYTES"
        and cap.get("exceeded_shard_indices") == []
        and cap.get("unattestable_shard_indices") == [],
        "ORCHESTRATOR_RSS_CAP_CONTRACT_DRIFT",
    )
    sampling = profile.get("memory_sampling")
    contract = profile.get("publication_execution_contract")
    require(
        isinstance(sampling, dict)
        and sampling.get("execution_mode")
        == "PRODUCTION_NATIVE_PROCESS_TREE_RSS"
        and sampling.get("production_native_sampler") is True
        and sampling.get("injected_sampler") is False
        and sampling.get("required_complete_profile_methods")
        == sorted(PRODUCTION_RSS_METHODS)
        and sampling.get(
            "fail_closed_on_unavailable_process_or_child"
        )
        is True
        and isinstance(contract, dict)
        and contract.get("max_allowed_process_rss_mib")
        == MAX_PUBLICATION_PROCESS_RSS_MIB
        and contract.get("max_allowed_heartbeat_interval_seconds")
        == MAX_ORCHESTRATOR_HEARTBEAT_INTERVAL_SECONDS,
        "ORCHESTRATOR_MEMORY_SAMPLER_CONTRACT_DRIFT",
    )
    rows = profile.get("shards")
    require(
        isinstance(rows, list)
        and all(isinstance(row, dict) for row in rows)
        and [row["shard_index"] for row in rows] == requested,
        "ORCHESTRATOR_RESULT_SHARD_INVENTORY_DRIFT",
    )
    profile_started = orchestrator_timestamp(
        profile.get("started_utc"),
        "orchestrator.started_utc",
    )
    profile_finished = orchestrator_timestamp(
        profile.get("finished_utc"),
        "orchestrator.finished_utc",
    )
    require(
        profile_started <= profile_finished,
        "ORCHESTRATOR_PROFILE_TIME_WINDOW_DRIFT",
    )
    python_executable = profile.get("python_executable")
    require(
        isinstance(python_executable, str) and python_executable,
        "ORCHESTRATOR_PYTHON_EXECUTABLE_MISSING",
    )
    producer_root: str | None = None
    for row, index in zip(rows, requested, strict=True):
        row_started = orchestrator_timestamp(
            row.get("started_utc"),
            f"orchestrator.shard_{index}.started_utc",
        )
        row_finished = orchestrator_timestamp(
            row.get("finished_utc"),
            f"orchestrator.shard_{index}.finished_utc",
        )
        row_elapsed = strict_float(
            row.get("elapsed_wall_seconds"),
            f"orchestrator.shard_{index}.elapsed_wall_seconds",
        )
        argv = row.get("argv")
        require(
            isinstance(argv, list)
            and len(argv) == 15
            and all(isinstance(token, str) for token in argv),
            f"ORCHESTRATOR_SHARD_ARGV_SHAPE:{index}",
        )
        row_root = argv[3]
        if producer_root is None:
            producer_root = row_root
        require(
            row_root == producer_root
            and argv
            == [
                python_executable,
                producer_join(producer_root, GENERATOR_PATH.as_posix()),
                "--root",
                producer_root,
                "run-shard",
                "--campaign",
                campaign,
                "--shard-index",
                str(index),
                "--binary",
                producer_binary_argv_path(
                    producer_root,
                    expected_inputs["binary"]["path"],
                    repository_relative=(
                        build_binding.get("binary_path") is not None
                    ),
                ),
                "--build-manifest",
                producer_join(
                    producer_root,
                    expected_inputs["build_manifest"]["path"],
                ),
                "--round",
                str(pilot_round),
            ],
            f"ORCHESTRATOR_SHARD_ARGV_DRIFT:{index}",
        )
        require(
            row.get("return_code") == 0
            and row.get("launch_error") is None
            and row.get("orchestration_failure_reason") is None
            and strict_int(
                row.get("pid"),
                f"orchestrator.shard_{index}.pid",
                1,
            )
            > 0
            and row.get("memory_sampling_supported") is True
            and row.get("rss_sample_method") in PRODUCTION_RSS_METHODS
            and strict_int(
                row.get("rss_successful_sample_count"),
                f"orchestrator.shard_{index}.successful_samples",
                1,
            )
            <= strict_int(
                row.get("rss_sample_count"),
                f"orchestrator.shard_{index}.samples",
                1,
            )
            and row.get("termination_requested") is False
            and row.get("forced_kill") is False,
            f"ORCHESTRATOR_SHARD_RESULT_FAILURE:{index}",
        )
        require(
            profile_started
            <= row_started
            <= row_finished
            <= profile_finished
            and row_elapsed >= 0.0,
            f"ORCHESTRATOR_SHARD_TIME_WINDOW_DRIFT:{index}",
        )
        require(
            strict_int(
                row.get("peak_resident_bytes"),
                f"orchestrator.shard_{index}.peak_rss",
                1,
            )
            <= cap_bytes,
            f"ORCHESTRATOR_SHARD_RSS_CAP_EXCEEDED:{index}",
        )
        validate_orchestrator_stream_binding(
            row.get("stdout"),
            f"orchestrator.shard_{index}.stdout",
        )
        validate_orchestrator_stream_binding(
            row.get("stderr"),
            f"orchestrator.shard_{index}.stderr",
        )
    require(
        profile.get("worker_script")
        == producer_join(
            str(producer_root), GENERATOR_PATH.as_posix()
        ),
        "ORCHESTRATOR_WORKER_SCRIPT_PATH_DRIFT",
    )
    build_manifest_value = load_json(
        root / Path(str(build_binding["path"]))
    )
    declared_binary_path = str(
        build_manifest_value.get("binary", {}).get("path", "")
    )
    require(
        producer_root is not None
        and producer_resolve_path(
            producer_root, declared_binary_path
        )
        == (
            producer_join(
                producer_root,
                expected_inputs["binary"]["path"],
            )
            if build_binding.get("binary_path") is not None
            else expected_inputs["binary"]["path"]
        ),
        "ORCHESTRATOR_EXTERNAL_BINARY_PRODUCER_PATH_DRIFT",
    )
    process_group_peak = strict_int(
        profile.get("process_group_peak_resident_bytes"),
        "orchestrator.process_group_peak_resident_bytes",
        1,
    )
    require(
        process_group_peak <= cap_bytes * workers_effective
        and profile.get("process_group_rss_scope")
        == (
            "SUM_OF_CONCURRENT_SHARD_WORKER_PROCESS_TREE_RSS_SAMPLES"
        ),
        "ORCHESTRATOR_PROCESS_GROUP_RSS_DRIFT",
    )
    poll_interval = strict_float(
        profile.get("rss_sampling_interval_seconds"),
        "orchestrator.rss_sampling_interval_seconds",
    )
    liveness = profile.get("liveness")
    require(isinstance(liveness, dict), "ORCHESTRATOR_LIVENESS_MISSING")
    heartbeat_interval = strict_float(
        liveness.get("heartbeat_interval_seconds"),
        "orchestrator.heartbeat_interval_seconds",
    )
    require(
        0.0 < poll_interval <= 1.0
        and 0.0
        < heartbeat_interval
        <= MAX_ORCHESTRATOR_HEARTBEAT_INTERVAL_SECONDS
        and liveness.get("poll_interval_seconds") == poll_interval
        and liveness.get("rss_sampling_interval_seconds")
        == poll_interval,
        "ORCHESTRATOR_INTERVAL_CONTRACT_DRIFT",
    )
    heartbeat_count = strict_int(
        liveness.get("heartbeat_count"),
        "orchestrator.heartbeat_count",
        2,
    )
    raw_timestamps = liveness.get("heartbeat_timestamps_utc")
    require(
        isinstance(raw_timestamps, list)
        and len(raw_timestamps) == heartbeat_count,
        "ORCHESTRATOR_HEARTBEAT_TIMESTAMP_COUNT_DRIFT",
    )
    timestamps = [
        orchestrator_timestamp(
            value, f"orchestrator.heartbeat_timestamp_{index}"
        )
        for index, value in enumerate(raw_timestamps)
    ]
    require(
        all(
            left < right
            for left, right in zip(timestamps, timestamps[1:])
        ),
        "ORCHESTRATOR_HEARTBEAT_TIMESTAMPS_NOT_STRICT",
    )
    require(
        profile_started
        <= timestamps[0]
        <= timestamps[-1]
        <= profile_finished,
        "ORCHESTRATOR_HEARTBEAT_TIME_WINDOW_DRIFT",
    )
    elapsed = strict_float(
        profile.get("elapsed_wall_seconds"),
        "orchestrator.elapsed_wall_seconds",
    )
    require(elapsed >= 0.0, "ORCHESTRATOR_NEGATIVE_ELAPSED")
    if elapsed > 2.0 * heartbeat_interval:
        require(
            heartbeat_count >= 3,
            "ORCHESTRATOR_PERIODIC_HEARTBEAT_MISSING",
        )
    max_gap = heartbeat_interval + max(1.0, 4.0 * poll_interval)
    require(
        all(
            (right - left).total_seconds() <= max_gap
            for left, right in zip(timestamps, timestamps[1:])
        ),
        "ORCHESTRATOR_HEARTBEAT_GAP_EXCEEDED",
    )
    heartbeat_binding = stored_binding.get("heartbeat")
    require(
        isinstance(heartbeat_binding, dict),
        "ORCHESTRATOR_HEARTBEAT_BINDING_MISSING",
    )
    heartbeat_path, heartbeat_relative = repository_publication_file(
        root,
        heartbeat_binding.get("path"),
        "ORCHESTRATOR_HEARTBEAT",
    )
    require(
        heartbeat_relative == liveness.get("heartbeat_path")
        and heartbeat_path != profile_path,
        "ORCHESTRATOR_HEARTBEAT_PATH_DRIFT",
    )
    heartbeat = load_json(heartbeat_path)
    validate_self_hash(heartbeat, "orchestrator_heartbeat")
    require(
        file_sha256(heartbeat_path) == heartbeat_binding.get("sha256")
        and heartbeat_path.stat().st_size
        == heartbeat_binding.get("byte_count")
        and heartbeat.get("self_sha256")
        == heartbeat_binding.get("self_sha256")
        == liveness.get("heartbeat_self_sha256")
        and file_sha256(heartbeat_path)
        == liveness.get("heartbeat_file_sha256"),
        "ORCHESTRATOR_HEARTBEAT_FILE_BINDING_DRIFT",
    )
    require(
        heartbeat.get("schema") == ORCHESTRATOR_HEARTBEAT_SCHEMA
        and heartbeat.get("status") == "COMPLETE"
        and heartbeat.get("formal_pass_claimed") is False
        and heartbeat.get("campaign") == campaign
        and heartbeat.get("pilot_round") == pilot_round
        and heartbeat.get("execution_mode")
        == "PRODUCTION_NATIVE_PROCESS_TREE_RSS"
        and heartbeat.get("started_utc")
        == profile.get("started_utc")
        and heartbeat.get("input_artifact_bindings")
        == expected_inputs
        and heartbeat.get("ending_input_artifact_bindings")
        == expected_inputs
        and heartbeat.get("input_artifact_drift") == []
        and heartbeat.get("available_shard_indices") == available
        and heartbeat.get("requested_shard_indices") == requested
        and heartbeat.get("scheduled_shard_indices") == requested
        and heartbeat.get("pending_shard_indices") == []
        and heartbeat.get("active_shard_indices") == []
        and heartbeat.get("completed_shard_indices") == requested
        and heartbeat.get("failure_observed") is False
        and heartbeat.get("max_process_rss_bytes") == cap_bytes
        and heartbeat.get("rss_cap_exceeded_shard_indices") == []
        and heartbeat.get("rss_cap_unattestable_shard_indices") == []
        and heartbeat.get("process_group_peak_resident_bytes")
        == process_group_peak
        and heartbeat.get("active_memory_samples") == []
        and heartbeat.get("rss_sampling_interval_seconds")
        == poll_interval
        and heartbeat.get("heartbeat_interval_seconds")
        == heartbeat_interval
        and heartbeat.get("heartbeat_sequence") == heartbeat_count
        and heartbeat.get("heartbeat_utc") == raw_timestamps[-1]
        and liveness.get("final_heartbeat_status") == "COMPLETE"
        and liveness.get("final_heartbeat_sequence")
        == heartbeat_count,
        "ORCHESTRATOR_FINAL_HEARTBEAT_CONTENT_DRIFT",
    )
    attestation = profile.get("publication_execution_attestation")
    require(
        isinstance(attestation, dict)
        and all(
            attestation.get(field) is True
            for field in (
                "profile_status_complete",
                "input_artifacts_stable",
                "rss_cap_configured",
                "production_native_memory_sampling",
                "all_successful_shards_have_peak_rss",
                "final_heartbeat_complete",
                "final_heartbeat_self_hash_bound",
            )
        ),
        "ORCHESTRATOR_PUBLICATION_ATTESTATION_DRIFT",
    )
    expected_stored_binding = {
        "path": profile_relative,
        "sha256": file_sha256(profile_path),
        "byte_count": profile_path.stat().st_size,
        "self_sha256": profile["self_sha256"],
        "requested_shard_indices": requested,
        "heartbeat": {
            "path": heartbeat_relative,
            "sha256": file_sha256(heartbeat_path),
            "byte_count": heartbeat_path.stat().st_size,
            "self_sha256": heartbeat["self_sha256"],
        },
    }
    require(
        dict(stored_binding) == expected_stored_binding,
        "ORCHESTRATOR_PROFILE_CANONICAL_BINDING_DRIFT",
    )
    return expected_stored_binding, requested


def validate_orchestrator_profile_set(
    root: Path,
    *,
    binding: Any,
    campaign: str,
    pilot_round: int,
    plan: Mapping[str, Any],
    plan_path: Path,
    build_binding: Mapping[str, Any],
) -> dict[str, Any]:
    require(
        isinstance(binding, dict),
        "ORCHESTRATOR_PROFILE_SET_MISSING",
    )
    validate_self_hash(binding, "orchestrator_profile_set")
    profiles = binding.get("profiles")
    require(
        binding.get("schema") == ORCHESTRATOR_PROFILE_SET_SCHEMA
        and binding.get("canonical_order")
        == "LEXICOGRAPHIC_REQUESTED_SHARD_INDICES_THEN_PATH"
        and isinstance(profiles, list)
        and bool(profiles)
        and binding.get("profile_count") == len(profiles),
        "ORCHESTRATOR_PROFILE_SET_SCHEMA",
    )
    canonical_profiles: list[dict[str, Any]] = []
    covered: set[int] = set()
    seen_paths: set[str] = set()
    for stored_profile in profiles:
        canonical, requested = validate_orchestrator_profile(
            root,
            stored_binding=stored_profile,
            campaign=campaign,
            pilot_round=pilot_round,
            plan=plan,
            plan_path=plan_path,
            build_binding=build_binding,
        )
        require(
            canonical["path"] not in seen_paths,
            "DUPLICATE_ORCHESTRATOR_PROFILE_PATH",
        )
        seen_paths.add(canonical["path"])
        overlap = covered.intersection(requested)
        require(
            not overlap,
            f"ORCHESTRATOR_PROFILE_SHARD_OVERLAP:{sorted(overlap)}",
        )
        covered.update(requested)
        canonical_profiles.append(canonical)
    canonical_profiles.sort(
        key=lambda row: (
            tuple(row["requested_shard_indices"]),
            row["path"],
        )
    )
    required = list(range(len(plan["shards"])))
    require(
        profiles == canonical_profiles
        and sorted(covered) == required
        and binding.get("covered_shard_indices") == required,
        "ORCHESTRATOR_PROFILE_SET_COVERAGE_OR_ORDER_DRIFT",
    )
    projection = dict(binding)
    projection.pop("self_sha256", None)
    require(
        binding["self_sha256"] == canonical_sha256(projection),
        "ORCHESTRATOR_PROFILE_SET_SELF_HASH_DRIFT",
    )
    return dict(binding)


def validate_pilot(
    root: Path,
    binary: Path | None,
    *,
    pilot_round: int = 1,
    strict_host_provenance: bool = False,
) -> dict[str, Any]:
    plan = validate_plan(root, "pilot", pilot_round=pilot_round)
    result_path = root / (
        PILOT_RESULT_PATH
        if pilot_round == 1
        else PILOT_ROUND2_RESULT_PATH
    )
    result = load_json(result_path)
    validate_self_hash(result, f"pilot_r{pilot_round}_result")
    require(
        result.get("schema") == "czr005.g4irsf15.pilot_result.v1"
        and result.get("pilot_round") == pilot_round
        and result.get("formal_pass_claimed") is False,
        "PILOT_RESULT_SCHEMA_OR_ROUND",
    )
    plan_binding = result.get("plan")
    expected_plan_path = (
        PILOT_PLAN_PATH
        if pilot_round == 1
        else PILOT_ROUND2_PLAN_PATH
    )
    require(
        isinstance(plan_binding, dict)
        and plan_binding.get("path") == expected_plan_path.as_posix()
        and plan_binding.get("self_sha256") == plan["self_sha256"],
        "PILOT_PLAN_BINDING",
    )
    require(
        result.get("exact_binary_build_manifest")
        == plan.get("exact_binary_build_manifest"),
        "PILOT_BUILD_MANIFEST_BINDING_DRIFT",
    )
    validate_build_manifest(
        root,
        plan.get("exact_binary_build_manifest", {}),
        binary=binary,
        strict_host_provenance=strict_host_provenance,
    )
    validate_orchestrator_profile_set(
        root,
        binding=result.get("campaign_shard_execution"),
        campaign="pilot",
        pilot_round=pilot_round,
        plan=plan,
        plan_path=root / expected_plan_path,
        build_binding=plan.get(
            "exact_binary_build_manifest", {}
        ),
    )
    labels, evidence_bindings = collect_compact_evidence_labels(
        root,
        "pilot",
        plan,
        evidence_bindings=result.get("pair_evidence_shards"),
        baseline_binding=result.get(
            "h_system_baseline_reference"
        ),
        run_state_attestation=result.get(
            "run_state_attestation"
        ),
    )
    require(
        result.get("pair_evidence_shards") == evidence_bindings
        and result.get("h_system_baseline_reference") is None,
        "PILOT_COMPACT_EVIDENCE_BINDING_LIST_DRIFT",
    )
    validate_run_state_attestation(
        result.get("run_state_attestation"),
        plan=plan,
    )
    eligible = [
        row for row in labels if row.get("eligible_causal_label") is True
    ]
    round_by_kind = Counter(str(row["kind"]) for row in eligible)
    round_signed = Counter(str(row.get("signed_label")) for row in eligible)
    hard_gate_fail = sum(
        row.get("action_changed") is True
        and row.get("hard_gate_evaluated") is True
        and row.get("hard_gate_pass") is not True
        for row in labels
    )
    hard_gate_fail_by_kind = Counter(
        str(row["kind"])
        for row in labels
        if row.get("action_changed") is True
        and row.get("hard_gate_evaluated") is True
        and row.get("hard_gate_pass") is not True
    )
    safety_hard_gate_fail = sum(
        row.get("action_changed") is True
        and row.get("safety_hard_gate_pass") is not True
        for row in labels
    )
    horizon_blocked = sum(
        row.get("action_changed") is True
        and row.get("horizon_complete") is not True
        for row in labels
    )
    evidence_incomplete = sum(
        row.get("action_changed") is True
        and row.get("evidence_complete") is not True
        for row in labels
    )
    future_leakage = sum(
        any(
            token in str(row.get("exclusion_reason", "")).upper()
            for token in ("GLOBAL_SCAN", "FUTURE_ROUTE", "FUTURE_SCHEDULE")
        )
        for row in labels
    )
    comparable = [
        row for row in labels if row.get("action_changed") is True
    ]
    clone_fidelity = (
        sum(row.get("same_state_start") is True for row in comparable)
        / len(comparable)
        if comparable
        else 0.0
    )
    action_changed_count = sum(
        row.get("action_changed") is True for row in eligible
    )
    action_rate = (
        action_changed_count / len(eligible) if eligible else 0.0
    )
    complete = Counter(round_by_kind)
    signed = Counter(round_signed)
    cumulative_attempted = len(labels)
    cumulative_hard_gate_fail = hard_gate_fail
    if pilot_round == 2:
        validate_pilot(root, None, pilot_round=1)
        prior_binding = plan.get("prior_pilot_result")
        prior_path = root / Path(str(prior_binding.get("path", "")))
        prior = load_json(prior_path)
        validate_self_hash(prior, "pilot_r2_prior_result")
        require(
            file_sha256(prior_path) == prior_binding.get("sha256")
            and prior.get("self_sha256")
            == prior_binding.get("self_sha256")
            and prior.get("status") == "RESAMPLE_REQUIRED",
            "PILOT_R2_PRIOR_RESULT_BINDING_DRIFT",
        )
        attempted_kinds = set(plan.get("active_kinds", []))
        prior_complete = prior.get("complete_by_kind")
        require(
            isinstance(prior_complete, dict),
            "PILOT_R1_COMPLETE_BY_KIND_MISSING",
        )
        complete = Counter(
            {
                kind: (
                    round_by_kind[kind]
                    if kind in attempted_kinds
                    else int(prior_complete.get(kind, 0))
                )
                for kind in KINDS
            }
        )
        signed.update(prior.get("signed_label_counts", {}))
        cumulative_attempted += int(prior.get("attempted_pair_count", 0))
        cumulative_hard_gate_fail += int(
            prior.get("hard_gate_fail_count", 0)
        )
    per_kind_pass = {
        kind: complete[kind] >= PILOT_MIN_COMPLETE_PER_KIND
        for kind in KINDS
    }
    supported = [kind for kind in KINDS if per_kind_pass[kind]]
    passed_all = (
        len(labels) == int(plan["attempt_budget"])
        and all(per_kind_pass.values())
        and cumulative_hard_gate_fail == 0
        and clone_fidelity == 1.0
    )
    passed_with_blocker = (
        pilot_round == 2
        and len(labels) == int(plan["attempt_budget"])
        and len(supported) >= 2
        and cumulative_hard_gate_fail == 0
        and clone_fidelity == 1.0
    )
    passed = passed_all or passed_with_blocker
    status = (
        "SAFETY_HARD_GATE_BLOCKED"
        if cumulative_hard_gate_fail > 0
        else "CLONE_FIDELITY_BLOCKED"
        if clone_fidelity < 1.0
        else "PASS_PILOT"
        if passed_all
        else "PASS_PILOT_WITH_BLOCKED_KINDS"
        if passed_with_blocker
        else "INTERVENTION_KIND_BLOCKED"
        if pilot_round == 2
        else "RESAMPLE_REQUIRED"
    )
    labels_per_clone = Counter(
        str(row["clone_group_id"]) for row in eligible
    )
    expected_summary = {
        "status": status,
        "attempted_pair_count": len(labels),
        "remaining_attempt_count": 0,
        "preregistered_panel_complete": True,
        "executed_shard_indices": list(range(len(plan["shards"]))),
        "outcome_dependent_early_stop": False,
        "causal_label_count": len(eligible),
        "complete_by_kind": {
            kind: int(complete[kind]) for kind in KINDS
        },
        "signed_label_counts": dict(sorted(signed.items())),
        "unique_clone_group_count": len(labels_per_clone),
        "labels_per_clone_group_max": max(
            labels_per_clone.values(), default=0
        ),
        "h_bag_or_stronger_complete_count": len(eligible),
        "h_system_complete_count": 0,
        "h_system_dense_evidence_count": 0,
        "h_system_unique_clone_group_count": 0,
        "action_changed_count": action_changed_count,
        "action_changed_rate": action_rate,
        "hard_gate_fail_count": cumulative_hard_gate_fail,
        "action_changed_hard_gate_fail_count": cumulative_hard_gate_fail,
        "safety_hard_gate_fail_count": safety_hard_gate_fail,
        "horizon_blocked_count": horizon_blocked,
        "evidence_incomplete_count": evidence_incomplete,
        "clone_fidelity": clone_fidelity,
        "future_leakage_count": future_leakage,
        "active_kinds": supported,
        "blocked_kinds": [
            kind for kind in KINDS if kind not in supported
        ],
        "round_attempted_pair_count": len(labels),
        "cumulative_attempted_pair_count": cumulative_attempted,
        "round_complete_by_kind": dict(sorted(round_by_kind.items())),
        "kind_status": {
            kind: (
                "SAFETY_BLOCKED"
                if hard_gate_fail_by_kind[kind] > 0
                else "PASS"
                if kind in supported
                else "INTERVENTION_KIND_BLOCKED"
                if pilot_round == 2
                else "RESAMPLE_REQUIRED"
            )
            for kind in KINDS
        },
        "round_false_positive_evidence": (
            pilot_false_positive_evidence(labels)
        ),
    }
    for field, expected in expected_summary.items():
        require(
            result.get(field) == expected,
            f"PILOT_RESULT_SUMMARY_DRIFT:{field}",
        )
    require(
        result.get("binary_sha256") == plan["binary"]["sha256_before"],
        "PILOT_BINARY_SHA_DRIFT",
    )
    require(
        result.get("screening_revision")
        == plan.get("screening_revision"),
        "PILOT_SCREENING_REVISION_BINDING_DRIFT",
    )
    if binary is not None:
        require(
            file_sha256(binary.resolve()) == result.get("binary_sha256"),
            "PILOT_BINARY_SHA_DRIFT",
        )
    for field in ("pilot_table", "report"):
        binding = result.get(field)
        require(isinstance(binding, dict), f"PILOT_OUTPUT_BINDING:{field}")
        bound_path = root / Path(str(binding.get("path", "")))
        require(
            file_sha256(bound_path) == binding.get("sha256")
            and publishable_byte_count(
                bound_path, f"pilot_r{pilot_round}_{field}"
            )
            == binding.get("byte_count"),
            f"PILOT_OUTPUT_BINDING_DRIFT:{field}",
        )
    return {
        "validation_status": (
            "PASS_PILOT_VALID"
            if passed
            else "VALID_EXPLICIT_PILOT_BLOCKER"
        ),
        "pilot_round": pilot_round,
        "attempted_pair_count": len(labels),
        "complete_by_kind": dict(complete),
    }


def validate_label(row: Mapping[str, Any]) -> None:
    require(row.get("schema") == LABEL_SCHEMA, "LABEL_SCHEMA")
    require(is_sha256(row.get("descriptor_id")), "LABEL_DESCRIPTOR_ID")
    require(is_sha256(row.get("clone_group_id")), "LABEL_CLONE_GROUP")
    strict_int(row.get("event_ordinal"), "label.event_ordinal", 0)
    require(
        isinstance(row.get("offline_sampling_metadata"), dict)
        and row["offline_sampling_metadata"].get(
            "must_not_enter_policy_features"
        )
        is True,
        "LABEL_OFFLINE_SAMPLING_METADATA",
    )
    require(
        is_sha256(row.get("pair_evidence_sha256")),
        "LABEL_PAIR_EVIDENCE_SHA256",
    )
    realized_sha = row.get("realized_outcome_deltas_sha256")
    realized_binding = row.get(
        "realized_outcome_deltas_binding"
    )
    if realized_sha is None:
        require(
            realized_binding is None,
            "LABEL_REALIZED_OUTCOME_BINDING_WITHOUT_CONTENT",
        )
    else:
        require(
            is_sha256(realized_sha)
            and isinstance(realized_binding, dict)
            and strict_int(
                realized_binding.get("row_count"),
                "label.realized_outcome_deltas_binding.row_count",
                1,
            )
            >= 1
            and realized_binding.get("content_sha256")
            == realized_sha,
            "LABEL_REALIZED_OUTCOME_BINDING_DRIFT",
        )
    certificate_sha = row.get(
        "committed_action_certificate_sha256"
    )
    require(
        certificate_sha is None or is_sha256(certificate_sha),
        "LABEL_COMMITTED_ACTION_CERTIFICATE_SHA256",
    )
    if row.get("certificate_valid") is True:
        require(
            is_sha256(certificate_sha),
            "LABEL_VALID_CERTIFICATE_BINDING_MISSING",
        )
    require(row.get("kind") in KINDS, "LABEL_KIND")
    require(row.get("horizon") in {"H_bag", "H_system"}, "LABEL_HORIZON")
    declared = row.get("label_sha256")
    if declared is not None:
        require(is_sha256(declared), "LABEL_SHA_FORMAT")
        projection = dict(row)
        projection.pop("label_sha256", None)
        require(declared == canonical_sha256(projection), "LABEL_SHA_DRIFT")
    sampling = row.get("sampling")
    require(isinstance(sampling, dict), "LABEL_SAMPLING_MISSING")
    N_h = strict_int(sampling.get("N_h"), "label.N_h", 1)
    address_frame_n = strict_int(
        sampling.get("target_address_frame_n_h"),
        "label.target_address_frame_n_h",
        1,
    )
    frame_n = strict_int(
        sampling.get("stage2_frame_n_h"), "label.stage2_frame_n_h", 1
    )
    n_h = strict_int(sampling.get("attempt_n_h"), "label.attempt_n_h", 1)
    require(sampling.get("n_h") == n_h, "LABEL_n_h_DRIFT")
    frame_pi = strict_float(
        sampling.get("frame_pi_h"), "label.frame_pi_h"
    )
    survival_pi = strict_float(
        sampling.get("post_exclusion_survival_pi_h"),
        "label.post_exclusion_survival_pi_h",
    )
    stage2_pi = strict_float(
        sampling.get("stage2_pi_h"), "label.stage2_pi_h"
    )
    pi_h = strict_float(sampling.get("pi_h"), "label.pi_h")
    require(
        0 < n_h <= frame_n <= address_frame_n <= N_h
        and math.isclose(
            frame_pi, address_frame_n / N_h, abs_tol=1e-15
        )
        and math.isclose(
            survival_pi, frame_n / address_frame_n, abs_tol=1e-15
        )
        and math.isclose(stage2_pi, n_h / frame_n, abs_tol=1e-15)
        and math.isclose(
            pi_h,
            frame_pi * survival_pi * stage2_pi,
            abs_tol=1e-15,
        )
        and math.isclose(
            float(sampling.get("analysis_weight")),
            1.0 / pi_h,
            abs_tol=1e-12,
        ),
        "LABEL_PI_H_DRIFT",
    )
    if row.get("eligible_causal_label") is True:
        require(row.get("action_changed") is True, "ELIGIBLE_ACTION_NOT_CHANGED")
        require(row.get("same_state_start") is True, "ELIGIBLE_STATE_MISMATCH")
        require(row.get("certificate_valid") is True, "ELIGIBLE_CERTIFICATE_INVALID")
        require(row.get("hard_gate_pass") is True, "ELIGIBLE_HARD_GATE_FAIL")
        require(not row.get("exclusion_reason"), "ELIGIBLE_HAS_EXCLUSION")
        require(
            row.get("signed_label")
            in {"BENEFICIAL", "NEUTRAL_WITHIN_TOLERANCE", "HARMFUL"},
            "SIGNED_LABEL_MISSING",
        )
        baseline_outcomes = row.get("baseline_affected_bag_outcomes")
        treatment_outcomes = row.get("treatment_affected_bag_outcomes")
        affected_deltas = row.get("affected_bag_deltas")
        require(
            isinstance(baseline_outcomes, list)
            and baseline_outcomes
            and isinstance(treatment_outcomes, list)
            and isinstance(affected_deltas, list)
            and len(baseline_outcomes)
            == len(treatment_outcomes)
            == len(affected_deltas),
            "AFFECTED_BAG_OUTCOME_EVIDENCE_MISSING",
        )
        baseline_ids = {
            int(outcome["runtime_bag_id"]) for outcome in baseline_outcomes
        }
        treatment_ids = {
            int(outcome["runtime_bag_id"]) for outcome in treatment_outcomes
        }
        delta_ids = {
            int(outcome["runtime_bag_id"]) for outcome in affected_deltas
        }
        require(
            baseline_ids == treatment_ids == delta_ids,
            "AFFECTED_BAG_OUTCOME_ID_DRIFT",
        )
        if row.get("horizon") == "H_system":
            require(
                row.get("h_system_cohort_size") == FULL_SEGMENT_COUNT
                and row.get("h_system_cohort_is_all_input_runtime_ids") is True,
                "H_SYSTEM_COHORT_NOT_FIXED_FULL_ORIGINAL",
            )
            require(
                is_sha256(row.get("h_system_cohort_mapping_sha256"))
                and is_sha256(row.get("raw_bag_mapping_sha256")),
                "H_SYSTEM_COHORT_MAPPING_SHA_MISSING",
            )
            direct = row.get("direct_affected_runtime_bag_ids")
            realized = row.get("realized_affected_runtime_bag_ids")
            external = row.get("externality_runtime_bag_ids")
            require(
                isinstance(direct, list)
                and isinstance(realized, list)
                and isinstance(external, list)
                and row.get("realized_affected_set_observable") is True,
                "H_SYSTEM_REALIZED_AFFECTED_SET_MISSING",
            )
            require(
                set(external) == set(realized) - set(direct),
                "H_SYSTEM_EXTERNALITY_SET_DRIFT",
            )


def analysis_metric_values(
    label: Mapping[str, Any],
) -> dict[str, float]:
    if label.get("eligible_causal_label") is not True:
        return {}
    delta = label.get("delta_metrics")
    require(isinstance(delta, dict), "ANALYSIS_DELTA_METRICS_MISSING")
    values = {
        metric: strict_float(delta.get(metric), f"analysis.{metric}")
        for metric in ANALYSIS_DELTA_METRICS
    }
    affected = label.get("affected_bag_deltas")
    require(
        isinstance(affected, list)
        and affected
        and all(isinstance(row, dict) for row in affected),
        "ANALYSIS_DIRECT_AFFECTED_DELTAS_MISSING",
    )
    values["direct_affected_delta_completion_mean_seconds"] = (
        math.fsum(
            strict_float(
                row.get("delta_completion_seconds"),
                "analysis.direct.delta_completion_seconds",
            )
            for row in affected
        )
        / len(affected)
    )
    raw = label.get("raw_bag_delta_metrics")
    if raw is not None:
        require(
            label.get("horizon") == "H_system"
            and isinstance(raw, dict),
            "ANALYSIS_RAW_METRICS_SCOPE_DRIFT",
        )
        for metric in ANALYSIS_RAW_METRICS:
            values[f"raw_bag_{metric}"] = strict_float(
                raw.get(metric), f"analysis.raw_bag.{metric}"
            )
    return values


def analysis_group_specs() -> list[dict[str, str]]:
    return [
        {"group_type": "overall", "group_value": "ALL"},
        *[
            {"group_type": "kind", "group_value": kind}
            for kind in KINDS
        ],
        {"group_type": "horizon", "group_value": "H_bag"},
        {"group_type": "horizon", "group_value": "H_system"},
        *[
            {
                "group_type": "kind_horizon",
                "group_value": f"{kind}:H_bag",
            }
            for kind in KINDS
        ],
    ]


def analysis_group_match(
    label: Mapping[str, Any], group: Mapping[str, str]
) -> bool:
    if group["group_type"] == "overall":
        return True
    if group["group_type"] == "kind_horizon":
        kind, horizon = group["group_value"].split(":", 1)
        return (
            label.get("kind") == kind
            and label.get("horizon") == horizon
        )
    return (
        str(label.get(group["group_type"])) == group["group_value"]
    )


def linear_quantile(
    values: Sequence[float], probability: float
) -> float:
    require(values, "EMPTY_BOOTSTRAP_DISTRIBUTION")
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * probability
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (
        ordered[upper] - ordered[lower]
    ) * fraction


def cluster_bootstrap_interval(
    observations: Sequence[tuple[str, float, float]],
    *,
    group_id: str,
    metric: str,
) -> tuple[float, float, int, str]:
    by_cluster: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for cluster, weight, value in observations:
        by_cluster[cluster].append((weight, value))
    cluster_ids = sorted(by_cluster)
    require(cluster_ids, "BOOTSTRAP_HAS_NO_CLUSTER")
    numerators = {
        cluster: math.fsum(
            weight * value for weight, value in by_cluster[cluster]
        )
        for cluster in cluster_ids
    }
    denominators = {
        cluster: math.fsum(
            weight for weight, _ in by_cluster[cluster]
        )
        for cluster in cluster_ids
    }
    seed_sha256 = hashlib.sha256(
        f"{BOOTSTRAP_SEED}|{group_id}|{metric}".encode("utf-8")
    ).hexdigest()
    estimates: list[float] = []
    for replicate in range(BOOTSTRAP_REPLICATES):
        selected: list[str] = []
        for draw in range(len(cluster_ids)):
            digest = hashlib.sha256(
                (
                    f"{seed_sha256}|replicate={replicate}|draw={draw}"
                ).encode("utf-8")
            ).digest()
            selected.append(
                cluster_ids[
                    int.from_bytes(digest[:8], "big")
                    % len(cluster_ids)
                ]
            )
        denominator = math.fsum(
            denominators[cluster] for cluster in selected
        )
        require(denominator > 0.0, "BOOTSTRAP_ZERO_WEIGHT")
        estimates.append(
            math.fsum(numerators[cluster] for cluster in selected)
            / denominator
        )
    return (
        linear_quantile(estimates, 0.025),
        linear_quantile(estimates, 0.975),
        len(cluster_ids),
        seed_sha256,
    )


def expected_weighted_effect_analysis(
    labels: Sequence[Mapping[str, Any]],
    *,
    plan: Mapping[str, Any],
    label_dataset_binding: Mapping[str, Any],
    formal_gate_passed: bool,
) -> dict[str, Any]:
    require(
        len(labels) == plan.get("attempt_budget"),
        "ANALYSIS_REQUIRES_COMPLETE_PREREGISTERED_PANEL",
    )
    records = [
        (row, analysis_metric_values(row))
        for row in labels
    ]
    responses: list[dict[str, Any]] = []
    estimates: list[dict[str, Any]] = []
    for group in analysis_group_specs():
        group_id = f"{group['group_type']}:{group['group_value']}"
        attempted = [
            row
            for row, _ in records
            if analysis_group_match(row, group)
        ]
        eligible = [
            (row, metrics)
            for row, metrics in records
            if analysis_group_match(row, group)
            and row.get("eligible_causal_label") is True
        ]
        responses.append(
            {
                **group,
                "group_id": group_id,
                "attempted_count": len(attempted),
                "eligible_response_count": len(eligible),
                "unweighted_response_rate": (
                    len(eligible) / len(attempted) if attempted else None
                ),
                "reference_design_weighted_attempt_total": None,
                "reference_design_weighted_response_total": None,
                "reference_design_weighted_response_rate": None,
                "reference_design_scope": (
                    "NOT_IDENTIFIED_NO_HORIZON_ASSIGNMENT_PROBABILITY"
                ),
            }
        )
        metric_names = sorted(
            {
                metric
                for _, metrics in eligible
                for metric in metrics
            }
        )
        for metric in metric_names:
            observations = [
                (
                    str(row["clone_group_id"]),
                    1.0,
                    metrics[metric],
                )
                for row, metrics in eligible
                if metric in metrics
            ]
            weights = [weight for _, weight, _ in observations]
            values = [value for _, _, value in observations]
            denominator = math.fsum(weights)
            weighted_total = math.fsum(
                weight * value
                for _, weight, value in observations
            )
            lower, upper, cluster_count, seed_sha256 = (
                cluster_bootstrap_interval(
                    observations,
                    group_id=group_id,
                    metric=metric,
                )
            )
            estimates.append(
                {
                    **group,
                    "group_id": group_id,
                    "metric": metric,
                    "observation_count": len(observations),
                    "clone_group_count": cluster_count,
                    "unweighted_realized_panel_mean": (
                        math.fsum(values) / len(values)
                    ),
                    "reference_design_horvitz_thompson_total": None,
                    "reference_design_estimated_denominator": None,
                    "reference_design_hajek_mean": None,
                    "cluster_bootstrap_ci95_lower": lower,
                    "cluster_bootstrap_ci95_upper": upper,
                    "bootstrap_seed_sha256": seed_sha256,
                    "bootstrap_replicates": BOOTSTRAP_REPLICATES,
                    "population_inference_status": (
                        "DESCRIPTIVE_ONLY_NO_HORIZON_ASSIGNMENT_WEIGHT"
                    ),
                    "estimate_scope": (
                        "DESCRIPTIVE_CONDITIONAL_ON_COMPLETE_"
                        "PREREGISTERED_REALIZED_PANEL"
                    ),
                }
            )
    projection = {
        "schema": WEIGHTED_EFFECT_SCHEMA,
        "status": (
            "COMPLETE_DESCRIPTIVE_ESTIMATES_GATE_PASSED"
            if formal_gate_passed
            else "COMPLETE_DESCRIPTIVE_ESTIMATES_GATE_BLOCKED"
        ),
        "formal_gate_passed": formal_gate_passed,
        "formal_pass_claimed": False,
        "estimand": {
            "unit": "preregistered_local_target_address_attempt",
            "outcome": (
                "matched-pair treatment-minus-baseline delta at the "
                "preregistered assigned horizon"
            ),
            "sampling_weight": (
                "recorded three-stage deterministic-minhash panel fraction "
                "is diagnostic only and is not used for population inference"
            ),
            "response_conditioning": (
                "eligible exact action-changing horizon-complete pairs only"
            ),
            "population_effect_identified": False,
            "non_identification_reasons": [
                "ACTION_CHANGE_AND_COMPLETE_EVIDENCE_RESPONSE_NOT_RANDOMIZED",
                "HORIZON_ASSIGNMENT_INCLUSION_PROBABILITY_NOT_MODELED",
            ],
            "h_system_specific_effects": (
                "DESCRIPTIVE_ONLY_HT_AND_HAJEK_FORBIDDEN"
            ),
            "primary_reference_design_scope": (
                "NONE; ALL HORIZONS AND MIXED-HORIZON SUMMARIES ARE "
                "DESCRIPTIVE ONLY"
            ),
            "h_system_role": "HARD_GATE_AND_EXTERNALITY_AUDIT_COHORT",
        },
        "panel_execution": {
            "complete_preregistered_panel": True,
            "attempted_pair_count": len(labels),
            "outcome_dependent_early_stop": False,
        },
        "bootstrap": {
            "method": (
                "DETERMINISTIC_NONPARAMETRIC_CLUSTER_RESAMPLE_WITH_"
                "REPLACEMENT_AND_HAJEK_REESTIMATION"
            ),
            "cluster_unit": "clone_group_id",
            "seed": BOOTSTRAP_SEED,
            "replicates": BOOTSTRAP_REPLICATES,
            "quantile_method": "LINEAR_TYPE_7",
        },
        "plan": {
            "self_sha256": plan["self_sha256"],
            "attempt_budget": plan["attempt_budget"],
        },
        "label_dataset": dict(label_dataset_binding),
        "response_summaries": responses,
        "estimates": estimates,
    }
    return {**projection, "self_sha256": canonical_sha256(projection)}


WEIGHTED_EFFECT_CSV_FIELDS = (
    "group_type",
    "group_value",
    "group_id",
    "metric",
    "observation_count",
    "clone_group_count",
    "unweighted_realized_panel_mean",
    "reference_design_horvitz_thompson_total",
    "reference_design_estimated_denominator",
    "reference_design_hajek_mean",
    "cluster_bootstrap_ci95_lower",
    "cluster_bootstrap_ci95_upper",
    "bootstrap_seed_sha256",
    "bootstrap_replicates",
    "population_inference_status",
    "estimate_scope",
)


def csv_bytes(
    rows: Sequence[Mapping[str, Any]], fields: Sequence[str]
) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=list(fields),
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    for source in rows:
        writer.writerow(
            {
                field: (
                    json.dumps(
                        source.get(field),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    if isinstance(source.get(field), (list, dict))
                    else source.get(field, "")
                )
                for field in fields
            }
        )
    return stream.getvalue().encode("utf-8")


def validate_weighted_effect_analysis(
    root: Path,
    manifest: Mapping[str, Any],
    labels: Sequence[Mapping[str, Any]],
    plan: Mapping[str, Any],
    *,
    formal_gate_passed: bool,
) -> None:
    binding = manifest.get("weighted_effect_estimates")
    require(isinstance(binding, dict), "WEIGHTED_EFFECT_BINDING_MISSING")
    require(
        binding.get("path") == WEIGHTED_EFFECT_DATASET_PATH.as_posix(),
        "WEIGHTED_EFFECT_PATH_DRIFT",
    )
    path = root / WEIGHTED_EFFECT_DATASET_PATH
    artifact = load_json(path)
    validate_self_hash(artifact, "weighted_effect_estimates")
    require(
        file_sha256(path) == binding.get("sha256")
        and artifact.get("self_sha256") == binding.get("self_sha256")
        and len(artifact.get("estimates", []))
        == binding.get("estimate_count")
        and len(artifact.get("response_summaries", []))
        == binding.get("response_summary_count"),
        "WEIGHTED_EFFECT_FILE_BINDING_DRIFT",
    )
    expected = expected_weighted_effect_analysis(
        labels,
        plan=plan,
        label_dataset_binding=manifest["label_dataset"],
        formal_gate_passed=formal_gate_passed,
    )
    require(
        artifact == expected,
        "WEIGHTED_EFFECT_NOT_INDEPENDENTLY_REPRODUCIBLE",
    )
    table_binding = manifest.get("tables", {}).get(
        "weighted_effect_estimates"
    )
    require(
        isinstance(table_binding, dict)
        and table_binding.get("path")
        == WEIGHTED_EFFECT_TABLE_PATH.as_posix()
        and (root / WEIGHTED_EFFECT_TABLE_PATH).read_bytes()
        == csv_bytes(artifact["estimates"], WEIGHTED_EFFECT_CSV_FIELDS)
        and file_sha256(root / WEIGHTED_EFFECT_TABLE_PATH)
        == table_binding.get("sha256"),
        "WEIGHTED_EFFECT_TABLE_NOT_REPRODUCIBLE",
    )


def expected_split_groups(
    labels: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    parent: dict[str, str] = {}
    raw_tasks_by_target: dict[str, set[int]] = {}

    def find(value: str) -> str:
        parent.setdefault(value, value)
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: str, right: str) -> None:
        a, b = find(left), find(right)
        if a != b:
            parent[max(a, b)] = min(a, b)

    for row in labels:
        clone = f"clone:{row['clone_group_id']}"
        key = str(row["target_key"])
        baseline = row.get("baseline_affected_bag_outcomes")
        treatment = row.get("treatment_affected_bag_outcomes")
        require(
            isinstance(baseline, list)
            and baseline
            and isinstance(treatment, list)
            and treatment,
            f"SPLIT_DIRECT_OUTCOME_EVIDENCE_MISSING:{key}",
        )
        baseline_tasks = {
            strict_int(
                outcome.get("task_id"),
                f"split.baseline.task_id:{key}",
                0,
            )
            for outcome in baseline
            if isinstance(outcome, dict)
        }
        treatment_tasks = {
            strict_int(
                outcome.get("task_id"),
                f"split.treatment.task_id:{key}",
                0,
            )
            for outcome in treatment
            if isinstance(outcome, dict)
        }
        require(
            all(isinstance(outcome, dict) for outcome in baseline)
            and all(isinstance(outcome, dict) for outcome in treatment)
            and baseline_tasks == treatment_tasks
            and baseline_tasks,
            f"SPLIT_DIRECT_TASK_ID_DRIFT:{key}",
        )
        metadata = row.get("offline_sampling_metadata")
        require(isinstance(metadata, dict), f"SPLIT_METADATA_MISSING:{key}")
        require(
            strict_int(metadata.get("task_id"), f"split.task_id:{key}", 0)
            in baseline_tasks,
            f"SPLIT_TARGET_TASK_NOT_DIRECTLY_AFFECTED:{key}",
        )
        raw_tasks_by_target[key] = baseline_tasks
        find(clone)
        for task_id in sorted(baseline_tasks):
            union(clone, f"task:{task_id}")

    components: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in labels:
        components[find(f"clone:{row['clone_group_id']}")].append(row)
    groups: list[dict[str, Any]] = []
    target_split: dict[str, str] = {}
    for root_key, rows in sorted(components.items()):
        component_id = canonical_sha256(
            sorted(str(row["target_key"]) for row in rows)
        )
        bucket = int(component_id[:8], 16) % 100
        split = (
            "train"
            if bucket < 70
            else "validation"
            if bucket < 85
            else "test"
        )
        keys = sorted(str(row["target_key"]) for row in rows)
        for key in keys:
            target_split[key] = split
        groups.append(
            {
                "component_id": component_id,
                "root_group": root_key,
                "split": split,
                "target_keys": keys,
                "clone_group_ids": sorted(
                    {str(row["clone_group_id"]) for row in rows}
                ),
                "raw_task_ids": sorted(
                    {
                        task_id
                        for row in rows
                        for task_id in raw_tasks_by_target[
                            str(row["target_key"])
                        ]
                    }
                ),
            }
        )
    by_clone: dict[str, set[str]] = defaultdict(set)
    by_task: dict[int, set[str]] = defaultdict(set)
    for row in labels:
        key = str(row["target_key"])
        split = target_split[key]
        by_clone[str(row["clone_group_id"])].add(split)
        for task_id in raw_tasks_by_target[key]:
            by_task[task_id].add(split)
    contamination = sum(
        len(values) > 1 for values in by_clone.values()
    ) + sum(len(values) > 1 for values in by_task.values())
    projection = {
        "schema": SPLIT_SCHEMA,
        "split_policy": (
            "CONNECTED_COMPONENTS_OF_CLONE_GROUP_AND_RAW_TASK_THEN_"
            "DETERMINISTIC_70_15_15"
        ),
        "split_contamination_count": contamination,
        "group_count": len(groups),
        "groups": groups,
    }
    return {**projection, "self_sha256": canonical_sha256(projection)}


def validate_split(root: Path, manifest: Mapping[str, Any], labels: Sequence[Mapping[str, Any]]) -> None:
    binding = manifest.get("split_groups")
    require(isinstance(binding, dict), "SPLIT_BINDING_MISSING")
    path = root / Path(str(binding.get("path", "")))
    require(path == root / SPLIT_GROUP_PATH, "SPLIT_PATH_DRIFT")
    require(file_sha256(path) == binding.get("sha256"), "SPLIT_FILE_HASH_DRIFT")
    split = load_json(path)
    validate_self_hash(split, "split_groups")
    require(split.get("schema") == SPLIT_SCHEMA, "SPLIT_SCHEMA")
    require(split.get("split_contamination_count") == 0, "SPLIT_CONTAMINATION")
    eligible = [
        row for row in labels if row.get("eligible_causal_label") is True
    ]
    require(
        split == expected_split_groups(eligible),
        "SPLIT_GROUPS_NOT_INDEPENDENTLY_REPRODUCIBLE",
    )
    target_split: dict[str, str] = {}
    clone_splits: dict[str, set[str]] = defaultdict(set)
    for group in split.get("groups", []):
        require(isinstance(group, dict), "SPLIT_GROUP_NOT_OBJECT")
        split_name = str(group.get("split"))
        require(split_name in {"train", "validation", "test"}, "SPLIT_NAME")
        for key in group.get("target_keys", []):
            require(key not in target_split, "TARGET_IN_TWO_SPLITS")
            target_split[str(key)] = split_name
        for clone in group.get("clone_group_ids", []):
            clone_splits[str(clone)].add(split_name)
    require(
        set(target_split) == {str(row["target_key"]) for row in eligible},
        "SPLIT_ELIGIBLE_TARGET_INVENTORY",
    )
    require(all(len(values) == 1 for values in clone_splits.values()), "CLONE_SPLIT_CONTAMINATION")


def validate_formal(
    root: Path,
    binary: Path | None,
    *,
    strict_host_provenance: bool = False,
) -> dict[str, Any]:
    plan = validate_plan(root, "formal")
    validate_build_manifest(
        root,
        plan.get("exact_binary_build_manifest", {}),
        binary=binary,
        strict_host_provenance=strict_host_provenance,
    )
    manifest = load_json(root / LABEL_MANIFEST_PATH)
    validate_self_hash(manifest, "label_manifest")
    require(manifest.get("schema") == LABEL_MANIFEST_SCHEMA, "LABEL_MANIFEST_SCHEMA")
    require(manifest.get("scale_count") == 0, "LABEL_SCALE_NONZERO")
    require(
        manifest.get("plan", {}).get("path") == FORMAL_PLAN_PATH.as_posix()
        and manifest.get("plan", {}).get("self_sha256")
        == plan["self_sha256"]
        and manifest.get("plan", {}).get("file_sha256")
        == file_sha256(root / FORMAL_PLAN_PATH),
        "LABEL_PLAN_BINDING",
    )
    require(
        manifest.get("exact_binary_build_manifest")
        == plan.get("exact_binary_build_manifest"),
        "LABEL_BUILD_MANIFEST_BINDING_DRIFT",
    )
    validate_orchestrator_profile_set(
        root,
        binding=manifest.get("campaign_shard_execution"),
        campaign="formal",
        pilot_round=1,
        plan=plan,
        plan_path=root / FORMAL_PLAN_PATH,
        build_binding=plan.get(
            "exact_binary_build_manifest", {}
        ),
    )
    expected_labels, expected_evidence_bindings = (
        collect_compact_evidence_labels(
            root,
            "formal",
            plan,
            evidence_bindings=manifest.get(
                "pair_evidence_shards"
            ),
            baseline_binding=manifest.get(
                "h_system_baseline_reference"
            ),
            run_state_attestation=manifest.get(
                "run_state_attestation"
            ),
        )
    )
    require(
        manifest.get("pair_evidence_shards")
        == expected_evidence_bindings,
        "LABEL_COMPACT_EVIDENCE_BINDING_LIST_DRIFT",
    )
    validate_run_state_attestation(
        manifest.get("run_state_attestation"),
        plan=plan,
    )
    dataset = manifest.get("label_dataset")
    require(isinstance(dataset, dict), "LABEL_DATASET_BINDING")
    path = root / Path(str(dataset.get("path", "")))
    require(path == root / LABEL_DATASET_PATH, "LABEL_DATASET_PATH")
    require(file_sha256(path) == dataset.get("sha256"), "LABEL_DATASET_HASH")
    require(
        publishable_byte_count(path, "formal_label_dataset")
        == dataset.get("byte_count"),
        "LABEL_DATASET_SIZE_DRIFT",
    )
    labels = zstd_jsonl(path)
    require(len(labels) == dataset.get("row_count"), "LABEL_ROW_COUNT")
    require(canonical_sha256(labels) == dataset.get("content_sha256"), "LABEL_CONTENT_HASH")
    require(
        labels == expected_labels,
        "PUBLISHED_LABELS_NOT_EXACT_INDEPENDENT_NATIVE_DERIVATION",
    )
    require(
        len(labels) == plan.get("attempt_budget")
        and manifest.get("attempted_pair_count") == len(labels)
        and manifest.get("remaining_attempt_count") == 0,
        "FORMAL_PREREGISTERED_PANEL_NOT_COMPLETE",
    )
    require(
        manifest.get("preregistered_panel_complete") is True
        and manifest.get("executed_shard_indices")
        == list(range(len(plan["shards"])))
        and manifest.get("outcome_dependent_early_stop") is False,
        "FORMAL_PANEL_EXECUTION_ATTESTATION_DRIFT",
    )
    target_keys: set[str] = set()
    for row in labels:
        validate_label(row)
        if row.get("horizon") == "H_system":
            require(
                row.get("h_system_cohort_mapping_sha256")
                == plan["protected_inputs"]["task"][
                    "runtime_segment_mapping_sha256"
                ]
                and row.get("raw_bag_mapping_sha256")
                == plan["protected_inputs"]["task"][
                    "raw_bag_mapping_sha256"
                ],
                "LABEL_H_SYSTEM_MAPPING_DRIFT",
            )
        key = str(row.get("target_key"))
        require(key not in target_keys, f"DUPLICATE_LABEL_TARGET:{key}")
        target_keys.add(key)
    eligible = [row for row in labels if row.get("eligible_causal_label") is True]
    require(
        dataset.get("eligible_row_count") == len(eligible),
        "LABEL_ELIGIBLE_ROW_COUNT_DRIFT",
    )
    by_kind = Counter(str(row["kind"]) for row in eligible)
    signed_counts = Counter(str(row.get("signed_label")) for row in eligible)
    labels_per_clone = Counter(
        str(row["clone_group_id"]) for row in eligible
    )
    h_system = [row for row in eligible if row["horizon"] == "H_system"]
    action_changed_rows = [
        row for row in labels if row.get("action_changed") is True
    ]
    hard_gate_fail = sum(
        row.get("hard_gate_evaluated") is True
        and row.get("hard_gate_pass") is not True
        for row in action_changed_rows
    )
    safety_hard_gate_fail = sum(
        row.get("safety_hard_gate_pass") is not True
        for row in action_changed_rows
    )
    horizon_blocked = sum(
        row.get("horizon_complete") is not True
        for row in action_changed_rows
    )
    evidence_incomplete = sum(
        row.get("evidence_complete") is not True
        for row in action_changed_rows
    )
    clone_fidelity = (
        sum(row.get("same_state_start") is True for row in action_changed_rows)
        / len(action_changed_rows)
        if action_changed_rows
        else 0.0
    )
    require(len(eligible) == manifest.get("causal_label_count"), "CAUSAL_LABEL_COUNT_DRIFT")
    require(len(h_system) == manifest.get("h_system_complete_count"), "H_SYSTEM_COUNT_DRIFT")
    dense_h_system_count = sum(
        row.get("horizon") == "H_system"
        and row.get("action_changed") is True
        for row in labels
    )
    require(
        dense_h_system_count
        == manifest.get("h_system_dense_evidence_count"),
        "H_SYSTEM_DENSE_EVIDENCE_COUNT_DRIFT",
    )
    require(
        len({row["clone_group_id"] for row in h_system})
        == manifest.get("h_system_unique_clone_group_count"),
        "H_SYSTEM_UNIQUE_CLONE_COUNT_DRIFT",
    )
    require(
        {kind: int(by_kind[kind]) for kind in KINDS}
        == manifest.get("complete_by_kind"),
        "LABEL_KIND_COUNT_DRIFT",
    )
    require(
        manifest.get("h_bag_or_stronger_complete_count") == len(eligible),
        "H_BAG_OR_STRONGER_COUNT_DRIFT",
    )
    require(
        dict(sorted(signed_counts.items()))
        == manifest.get("signed_label_counts"),
        "SIGNED_LABEL_COUNT_DRIFT",
    )
    require(
        len(labels_per_clone) == manifest.get("unique_clone_group_count")
        and max(labels_per_clone.values(), default=0)
        == manifest.get("labels_per_clone_group_max"),
        "CLONE_GROUP_LABEL_COUNT_DRIFT",
    )
    require(
        hard_gate_fail == manifest.get("hard_gate_fail_count"),
        "HARD_GATE_FAIL_COUNT_DRIFT",
    )
    require(
        hard_gate_fail
        == manifest.get("action_changed_hard_gate_fail_count"),
        "ACTION_CHANGED_HARD_GATE_FAIL_COUNT_DRIFT",
    )
    require(
        safety_hard_gate_fail
        == manifest.get("safety_hard_gate_fail_count"),
        "SAFETY_HARD_GATE_FAIL_COUNT_DRIFT",
    )
    require(
        horizon_blocked == manifest.get("horizon_blocked_count"),
        "HORIZON_BLOCKED_COUNT_DRIFT",
    )
    require(
        evidence_incomplete == manifest.get("evidence_incomplete_count"),
        "EVIDENCE_INCOMPLETE_COUNT_DRIFT",
    )
    require(
        clone_fidelity == manifest.get("clone_fidelity"),
        "CLONE_FIDELITY_DRIFT",
    )
    action_changed_count = sum(
        row.get("action_changed") is True for row in eligible
    )
    action_rate = (
        action_changed_count / len(eligible) if eligible else 0.0
    )
    require(
        action_changed_count == manifest.get("action_changed_count")
        and action_rate == manifest.get("action_changed_rate"),
        "ACTION_CHANGED_RATE_DRIFT",
    )
    future_leakage = sum(
        any(
            token in str(row.get("exclusion_reason", "")).upper()
            for token in ("GLOBAL_SCAN", "FUTURE_ROUTE", "FUTURE_SCHEDULE")
        )
        for row in labels
    )
    require(
        future_leakage == manifest.get("future_leakage_count"),
        "FUTURE_LEAKAGE_COUNT_DRIFT",
    )
    validate_split(root, manifest, labels)
    table_bindings = manifest.get("tables")
    require(isinstance(table_bindings, dict), "TABLE_BINDINGS_MISSING")
    for name, binding in table_bindings.items():
        require(isinstance(binding, dict), f"TABLE_BINDING:{name}")
        table_path = root / Path(str(binding.get("path", "")))
        require(
            file_sha256(table_path) == binding.get("sha256")
            and publishable_byte_count(table_path, f"table_{name}")
            == binding.get("byte_count"),
            f"TABLE_HASH_DRIFT:{name}",
        )
    report_binding = manifest.get("report")
    require(
        isinstance(report_binding, dict)
        and report_binding.get("path")
        == Path(
            "outputs/reports/g4irsf15_causal_campaign_results.md"
        ).as_posix(),
        "FORMAL_REPORT_BINDING_MISSING",
    )
    report_path = root / Path(str(report_binding["path"]))
    require(
        file_sha256(report_path) == report_binding.get("sha256")
        and publishable_byte_count(report_path, "formal_campaign_report")
        == report_binding.get("byte_count")
        and "Population effect identified: `false`"
        in report_path.read_text(encoding="utf-8"),
        "FORMAL_REPORT_BINDING_DRIFT",
    )
    formal_gate = plan.get("formal_gate")
    require(isinstance(formal_gate, dict), "FORMAL_GATE_MISSING")
    active_kinds = list(formal_gate.get("active_kinds", []))
    blocked_kinds = [kind for kind in KINDS if kind not in active_kinds]
    require(
        len(active_kinds) >= 2
        and set(active_kinds).issubset(KINDS)
        and manifest.get("active_kinds") == active_kinds
        and manifest.get("blocked_kinds") == blocked_kinds,
        "FORMAL_ACTIVE_KIND_GATE_DRIFT",
    )
    passed = (
        len(eligible)
        >= strict_int(
            formal_gate.get("causal_label_count_min"),
            "formal.causal_label_count_min",
            1,
        )
        and len(h_system)
        >= strict_int(
            formal_gate.get("h_system_complete_min"),
            "formal.h_system_complete_min",
            1,
        )
        and all(
            by_kind[kind]
            >= strict_int(
                formal_gate.get("per_kind_label_min"),
                "formal.per_kind_label_min",
                1,
            )
            for kind in active_kinds
        )
        and all(by_kind[kind] == 0 for kind in blocked_kinds)
        and hard_gate_fail == 0
        and action_rate == 1.0
        and clone_fidelity == 1.0
        and future_leakage == 0
    )
    require(manifest.get("formal_pass_claimed") is passed, "FORMAL_PASS_CLAIM_DRIFT")
    require(manifest.get("learning_authorized") is passed, "LEARNING_AUTHORIZATION_DRIFT")
    if not passed:
        require(
            manifest.get("status") == "BLOCKED_DESCRIPTOR_BUDGET_EXHAUSTED",
            "FORMAL_BLOCKER_STATUS_MISSING",
        )
    else:
        require(manifest.get("status") == "PASS_CAUSAL_GATE", "PASS_STATUS_DRIFT")
    binary_binding = manifest.get("binary")
    require(
        isinstance(binary_binding, dict)
        and binary_binding.get("all_shards_same_binary") is True
        and binary_binding.get("sha256")
        == plan["binary"]["sha256_before"]
        and all(
            binding["binary_sha256"] == binary_binding["sha256"]
            for binding in expected_evidence_bindings
        ),
        "FORMAL_BINARY_CONSISTENCY",
    )
    if binary is not None:
        require(
            file_sha256(binary.resolve()) == binary_binding.get("sha256"),
            "FORMAL_BINARY_SHA_DRIFT",
        )
    validate_weighted_effect_analysis(
        root,
        manifest,
        labels,
        plan,
        formal_gate_passed=passed,
    )
    return {
        "validation_status": (
            "PASS_CAUSAL_GATE_VALID"
            if passed
            else "VALID_EXPLICIT_CAUSAL_GATE_BLOCKER"
        ),
        "causal_label_count": len(eligible),
        "h_system_complete_count": len(h_system),
        "complete_by_kind": dict(by_kind),
        "learning_authorized": passed,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--root", type=Path, default=ROOT)
    result.add_argument(
        "--scope",
        choices=("scan", "pilot", "formal"),
        default="formal",
    )
    result.add_argument("--binary", type=Path)
    result.add_argument(
        "--round",
        type=int,
        choices=(1, 2),
        default=1,
        dest="pilot_round",
    )
    result.add_argument(
        "--strict-host-provenance",
        action="store_true",
        help=(
            "also re-open the generation host's binary and toolchain paths; "
            "default validation is publication-portable static provenance"
        ),
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    root = arguments.root.resolve()
    if arguments.scope == "scan":
        rows, manifest = validate_descriptor_bundle(root)
        validate_build_manifest(
            root,
            manifest.get("exact_binary_build_manifest", {}),
            binary=arguments.binary,
            strict_host_provenance=arguments.strict_host_provenance,
        )
        result = {
            "validation_status": "PASS_DESCRIPTOR_SCAN_VALID",
            "target_address_frame_count": len(rows),
            "full_state_sealed_descriptor_count": manifest[
                "full_state_sealed_descriptor_count"
            ],
            "population_count": manifest[
                "target_address_population_count"
            ],
            "binary_reverified": arguments.binary is not None,
            "host_toolchain_reverified": (
                arguments.strict_host_provenance
            ),
        }
    elif arguments.scope == "pilot":
        result = validate_pilot(
            root,
            arguments.binary,
            pilot_round=arguments.pilot_round,
            strict_host_provenance=arguments.strict_host_provenance,
        )
    else:
        result = validate_formal(
            root,
            arguments.binary,
            strict_host_provenance=arguments.strict_host_provenance,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        print(f"G4IRSF15_CAUSAL_VALIDATION_ERROR:{exc}", file=sys.stderr)
        raise SystemExit(2) from exc
