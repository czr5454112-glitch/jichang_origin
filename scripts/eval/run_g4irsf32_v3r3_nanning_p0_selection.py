#!/usr/bin/env python3
"""Freeze the outcome-blind V3R7 Nanning P0 control-selected shadow slice.

This module has no G32 implementation dependency on its control path.  It
regenerates the committed G31 workloads, finds the minimum canonical external
prefix whose predicted final commit intersects one adjacent local-service
overlap before the first external arrival, and can
execute only the frozen G31 binary in omitted/default-off mode.  A separate
callable prepares and audits the later G32 shadow gate; the CLI never invokes
that callable.  The terminal V3R3 32-pair artifacts remain immutable history.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from scripts.eval import g4irsf31_map_adapter as map_adapter  # noqa: E402
from scripts.eval import run_g4irsf31_nanning_native as native31  # noqa: E402
from scripts.eval import run_g4irsf31_nanning_workload as workload31  # noqa: E402


SCHEMA = "czr005.g4irsf32.nanning_p0_control_selection.v3r7"
SHADOW_GATE_SCHEMA = "czr005.g4irsf32.nanning_p0_shadow_gate.v3r11"
PROTOCOL_ID = "G4IRSF32_EXTERNAL_COMMIT_LOCAL_VIRTUAL_SLOT_SHADOW_P0_V3R3"
CONTROL_REVISION_ID = (
    "G4IRSF32_V3R7_MINIMAL_PREARRIVAL_OVERLAP_NANNING_P0_ADDENDUM_20260828"
)
SYNTHETIC_REVISION_ID = "G4IRSF32_V3R11_DEEP_REPLAY_COMPATIBILITY_P0_20260829"
CAMPAIGN_REVISION_ID = "G4IRSF32_V3R11_P0_CAMPAIGN_20260829"
EXECUTION_REGISTRATION_ID = CONTROL_REVISION_ID
SELECTOR_ALGORITHM_ID = (
    "MINIMUM_EXTERNAL_PREFIX_ADJACENT_LOCAL_SERVICE_OVERLAP_V1"
)
G31_BASE_COMMIT = "46cc46ab6bc121628fd6357e9f3c7636745fd732"
FINAL_GO = (
    "GO_V3R11_EXTERNAL_COMMIT_LOCAL_VIRTUAL_RELATION_AND_"
    "MINIMAL_PREARRIVAL_OVERLAP_NANNING_P1_REVIEW_ALLOWED"
)
PASS = "PASS_V3R7_NANNING_P0_CONTROL_SELECTION"
NO_EVENT = "NO_GO_V3R7_NANNING_P0_CONTROL_SELECTION_NO_EVENT"
NO_GO = "NO_GO_V3R7_NANNING_P0_CONTROL_SELECTION_AUDIT_FAILED"
SHADOW_PASS = "PASS_V3R11_NANNING_P0_G32_SHADOW"
SHADOW_NO_EVENT = "NO_GO_V3R11_NANNING_P0_REAL_MIXED_ORIGIN_NOT_OBSERVED"
SHADOW_NO_GO = "NO_GO_V3R11_NANNING_P0_G32_SHADOW_GATE"
FORMAL_EXECUTION_BLOCKED_REASON = ""
CONTROL_EXECUTION_BLOCKED_REASON = "V3R7_CONTROL_FROZEN_USE_REGISTERED_ARTIFACT"
SHADOW_CHECK_NAMES = {
    "loaded_g32_binary",
    "ordinary_request_exact",
    "ordinary_state_exact",
    "rows_joined",
    "shadow_census",
    "permanent_starvation_and_service",
    "resource_ratio",
    "legacy_wait_exact",
    "node49_upstream53_admitted",
}
IMPLEMENTATION_GATE_NAMES = {
    "implementation_head_resolved",
    "implementation_parent_is_ancestor",
    "implementation_implementation_not_parent",
    "implementation_diff_paths_allowed",
    "implementation_source_bundle_clean",
}
NATIVE_PROOF_GATE_NAMES = {
    "native_proof_exit_zero",
    "native_proof_fixed_executable",
    "native_proof_executable_unchanged",
    "native_proof_exact_schema",
    "native_proof_schema_id",
    "native_proof_test_id",
    "native_proof_all_native_assertions",
    "native_proof_same_build_head",
    "native_proof_nested_exit_zero",
    "native_proof_fixed_nested_executable",
    "native_proof_nested_executable_unchanged",
    "native_proof_nested_exact_schema",
    "native_proof_nested_schema_id",
    "native_proof_nested_test_id",
    "native_proof_nested_assertion",
    "native_proof_nested_same_build_head",
    "native_proof_g32_binary_unchanged",
}
CROSS_BINARY_GATE_NAMES = {
    "cross_binary_exact_ordinary_request",
    "cross_binary_exact_off_payload",
    "cross_binary_exact_off_accounting",
    "cross_binary_exact_off_extension_absent",
    "g31_release_binary_exact",
    "g32_omitted_explicit_repeated",
}
MAP2_GATE_NAMES = {
    "map2_frozen_hashes",
    "map2_completion_safety",
    "map2_legacy_wait_exact",
    "map2_service_sequence_exact",
    "map2_exact_no_mutation",
    "map2_join_census",
    "map2_resource",
    "map2_g32_binary",
}
STAGE0_OWN_GATE_NAMES = {
    "stage0_execution",
    "native_proof",
    "native_artifacts_implementation_head",
    "cross_binary_exact_off",
    "shadow_repeat_exact",
    "direct_unique_publish",
    "j2_unique_publish",
    "no_direct_j2_double_publish",
    "motif_controls_safety_census",
    "motif_g32_binary",
    "future_probe_completion_safety_join_census",
    "future_release_prefix_exact",
    "distant_probe_completion_safety_join_census",
    "distant_L_prefix_exact",
    "map2_sentinel",
    "source_bundle_unchanged_through_stage0",
    "g32_binary_unchanged_through_stage0",
}
STAGE0_GATE_NAMES = (
    IMPLEMENTATION_GATE_NAMES
    | NATIVE_PROOF_GATE_NAMES
    | CROSS_BINARY_GATE_NAMES
    | MAP2_GATE_NAMES
    | STAGE0_OWN_GATE_NAMES
)
STAGE1_GATE_NAMES = {
    "stage1_manifest_bound_before_execution",
    "stage1_identification_design_non_degenerate",
    "stage1_exact_120_attempted",
    "stage1_exact_24_identification_attempted",
    "stage1_no_execution_errors",
    "stage1_loaded_binary_identity",
    "stage1_completion_overlap_duplicate_origin_pending_safety",
    "stage1_safety_regression",
    "stage1_primary_relationship",
    "stage1_resources",
    "source_bundle_unchanged_through_stage1",
    "g32_binary_unchanged_through_stage1",
}
IDENTIFICATION_PRIMARY_GATE_NAMES = {
    "exact_frozen_24_case_population",
    "primary_pair_case_population",
    "directional_case_strata",
    "unique_primary_bags",
    "mixed_flow_coverage",
    "service_coverage",
    "population_coverage",
    "join_and_census_complete",
    "case_equal_rho_positive",
    "case_block_rho_lcb_positive",
    "positive_rho_share",
    "positive_rho_wilson_lower",
}
SAFETY_REGRESSION_GATE_NAMES = {
    "exact_frozen_120_case_population",
    "negative_controls_zero",
    "join_and_census_complete",
    "all_hard_safety_gates",
}
RESOURCE_GATE_NAMES = {
    "resource_events_per_completed",
    "resource_junction_local_accounted_bytes",
    "resource_runtime_internal_accounted_bytes",
    "resource_total_accounted_bytes",
}
SERVICE_AUDIT_CHECK_NAMES = {
    "complete_once",
    "exact_request_population_identity",
    "origin_coverage",
    "legacy_wait_native_consistent",
    "permanent_starvation_zero",
    "service_sequence_conservation",
    "global_service_calendar",
    "no_overlap_or_duplicate",
    "pending_bounded",
    "safety",
    "junction_state_present",
}
PERMANENT_CHECK_NAMES = {
    "requested_population_exact",
    "completed_once",
    "deadline_complete",
    "L_service_once_where_applicable",
    "failed_zero",
    "final_active_zero",
    "unresolved_deadlock_zero",
    "limits_not_reached",
    "active_node_identity_valid",
    "active_junction_state_exact",
    "final_queues_empty",
    "final_scheduled_incoming_zero",
    "lifecycle_ordered",
    "lifecycle_chains_valid",
    "lifecycle_counts_exact",
    "lifecycle_final_state_complete",
    "lifecycle_consumed_committed_exact",
    "lifecycle_terminal_exact",
    "lifecycle_outstanding_exact",
    "lifecycle_active_exact",
    "merge_request_conservation",
    "final_merge_pending_zero",
    "merge_active_unconsumed_zero",
    "mixed_origin_request_completion",
    "recomputable_vectors_bounded",
}
GLOBAL_SERVICE_CHECK_NAMES = {
    "unique_bag_node",
    "completion_event_identity_unique",
    "no_node_overlap",
    "reservation_count_match",
    "goal_arrival_has_no_service",
    "evidence_vector_bounded",
}
LEGACY_PAIR_CHECK_NAMES = {
    "off_native_consistent",
    "shadow_native_consistent",
    "count_exact",
    "ordered_identities_exact",
    "ordered_waits_exact",
    "ordered_flags_exact",
    "per_origin_exact",
    "ordered_vector_hash_exact",
}
CENSUS_CHECK_NAMES = {
    "partition",
    "seam_partition",
    "ordinary_commit_seam_binding",
    "stored_matches",
    "zero_drop",
    "inert_local",
    "mode",
}
CENSUS_PART_NAMES = {
    "no_local_count",
    "local_guard_fail_count",
    "non_overlap_count",
    "staged_rollback_count",
    "observation_stored_count",
    "observation_dropped_count",
}
CENSUS_ZERO_NAMES = {
    "action_change_count",
    "calendar_mutation_count",
    "future_release_read_count",
    "global_scan_count",
}
ORDINARY_PAYLOAD_HASH_NAMES = {
    "actions",
    "timing",
    "calendar_state",
    "events",
    "merge_lifecycle",
    "result_contract",
    "deterministic_payload",
    "physical_state",
    "ordinary_payload",
}
RESOURCE_VALUE_NAMES = {
    "events_per_completed",
    "junction_local_accounted_bytes",
    "runtime_internal_accounted_bytes",
    "trace_sidecar_accounted_bytes",
    "total_accounted_bytes",
}
CROSS_BINARY_RUN_NAMES = (
    "g31_parent",
    "g32_explicit",
    "g32_omitted",
    "g32_repeated",
)
CROSS_BINARY_RUN_KEYS = {
    "schema",
    "binary_path",
    "binary_sha256",
    "request_sha256",
    "ordinary_request_sha256",
    "ordinary",
    "accounting",
    "extension_absent",
}
CROSS_BINARY_WORKER_SCHEMA = "czr005.g4irsf32.v3r2_off_worker.v1"
STAGE0_CASE_FIXTURE_KEYS = {
    "rows",
    "pairs",
    "off_ordinary_hashes",
    "shadow_ordinary_hashes",
}
STAGE0_PROBE_AUDIT_KEYS = {
    "pass",
    "row_count",
    "join_status",
    "census",
    "service",
    "rows",
    "pairs",
    "off_ordinary_hashes",
    "shadow_ordinary_hashes",
}
STAGE0_CASE_ROLES = (
    ("direct", "simultaneous_local_first", False),
    ("j2", "simultaneous_local_first", False),
    ("external_only", "external_only", True),
    ("local_only", "local_only", True),
)
SYNTHETIC_EXACT_SERVICE_NODE = 1
STAGE0_FIXTURE_NAMES = {
    "direct",
    "j2",
    "external_only",
    "local_only",
    "repeated_shadow",
    "future_a",
    "future_b",
    "distant",
    "map2",
}
STAGE0_MAP2_KEYS = {
    "pass",
    "gates",
    "hashes",
    "row_count",
    "join_status",
    "census",
    "rows_sha256",
    "pairs_sha256",
    "resources",
    "legacy_wait_over_120",
    "service_sequence_parity",
    "off_audit",
    "shadow_audit",
    "rows",
    "pairs",
    "off_ordinary_hashes",
    "shadow_ordinary_hashes",
}
STAGE0_J2_IDENTITY_FIELDS = (
    "external_request_id",
    "external_request_lineage",
    "external_request_generation",
    "external_junction_queue_generation",
)
JOIN_PAIR_KEYS = {
    "case_id",
    "observation_ordinal",
    "opportunity_id",
    "primary",
    "status",
    "reason",
    "local",
    "external",
    "Y_realized",
    "A_gap",
    "X_insert",
    "H_gap",
    "case_status",
}
JOIN_EPISODE_OUTPUT_KEYS = {
    "actual_L_service_start",
    "actual_L_service_complete",
    "actual_subsequent_source_wait",
    "actual_subsequent_junction_wait",
    "actual_transit_seconds",
    "actual_subsequent_calendar_wait",
    "actual_subsequent_wait",
}
LIFECYCLE_FINAL_STATES = {
    "REQUESTED",
    "COMMITTED",
    "CONSUMED",
    "EXPIRED",
    "REVOKED_FAULT",
    "REVOKED_STALE_STATE",
    "REVOKED_REPLAN_CURRENT_EDGE",
    "ROLLED_BACK",
}
SYNTHETIC_CASE_KEYS = {
    "cohort",
    "replica",
    "case_id",
    "service_seconds",
    "bag_count",
    "flow_pattern",
    "negative_control",
    "admitted_row_count",
    "join_status",
    "census_partition_pass",
    "hard_gate_pass",
    "off_audit",
    "shadow_audit",
    "legacy_wait_over_120",
    "service_sequence_parity",
    "census",
    "ordinary_parity",
    "request_parity",
    "binary_parity",
    "loaded_cpp_binary_path",
    "loaded_cpp_binary_sha256",
    "off_hashes",
    "shadow_hashes",
    "rows_sha256",
    "pairs_sha256",
    "profile_sha256",
    "potential_sha256",
    "off_request_sha256",
    "shadow_request_sha256",
    "off_ordinary_request_sha256",
    "shadow_ordinary_request_sha256",
    "resources",
}

MAP_ID = native31.MAP_ID
SPEED_MPS = 2.5
EXTERNAL_START = 53
LOCAL_START = 49
EXTERNAL_FIRST_ENTRY_OFFSET_SECONDS = 0.001
NODE49_SERVICE_SECONDS = 1.0
SOURCE_RETRY_INTERVAL_SECONDS = 0.25
EXTERNAL_53_TO_49_TRAVEL_SECONDS = 60.1
TRACE_LIMIT = 200_000
G32_TRACE_LIMIT = 200_000
AUDIT_EPSILON = 1.0e-9
RESOURCE_RATIO_LIMIT = 1.10
SELECTOR_RULE = (
    "canonically order external bursts and adjacent local node-49 rows by "
    "(pass_time,segment_id,task_id); retain adjacent local pairs with "
    "EPSILON<release_gap<1.0-EPSILON and local_clear=max(second_release+"
    "0.25,first_release+1.0)+1.0<=external_release+0.001+60.1-EPSILON; "
    "for each pair/release set commit_rank=max(0,ceil((second_release-"
    "external_release-0.001)/1.0)), require that rank to exist and "
    "second_release+EPSILON<predicted_commit<first_release+1.0-EPSILON "
    "and predicted_commit<first_external_arrival-EPSILON; choose the minimum "
    "(external_prefix_count,external_release,first_release,second_release,"
    "canonical local identities), then select that canonical external prefix "
    "and exactly that adjacent local pair"
)

PROTOCOL_PATH = ROOT / "docs/G4IRSF32_v3r3_measurement_semantics_protocol.md"
EXECUTION_REGISTRATION_PATH = (
    ROOT / "docs/G4IRSF32_v3r7_minimal_prearrival_overlap_nanning_p0_addendum.md"
)
V3R5_ADDENDUM_PATH = (
    ROOT / "docs/G4IRSF32_v3r5_commit_aligned_nanning_p0_addendum.md"
)
V3R6_ADDENDUM_PATH = (
    ROOT / "docs/G4IRSF32_v3r6_bounded_commit_aligned_nanning_p0_addendum.md"
)
PROFILE_PATH = ROOT / "data/processed/maps/nanning_airport_profile.json"
SOURCE_WORKLOAD_PATH = ROOT / "data/processed/tasks/inputdata.jsonl"
SOURCE_TIMETABLE_PATH = ROOT / "legacy/jichang_origin_readonly/inputdata.txt"
MANIFEST_DIR = ROOT / "artifacts/tasks/g4irsf31_nanning"
G31_AGGREGATE_PATH = ROOT / "outputs/tables/g4irsf31_nanning_native.json"
G31_BINARY = Path(
    "C:/tmp/g4irsf32_v3r2_g31_build/python/Release/"
    "czr005_cpp.cp311-win_amd64.pyd"
)
OUTPUT_PATH = (
    ROOT / "outputs/tables/g4irsf32_v3r7_nanning_p0_control_selection.json"
)
RUNNER_PATH = Path(__file__).resolve()

EXPECTED_SCALE_COUNTS = {1: (28_506, 43_603), 2: (57_012, 87_206)}
EXPECTED_POOL_COUNTS = {1: (15_097, 2_807), 2: (30_194, 5_614)}
EXPECTED_SELECTION_COUNTS = {
    1: {
        "external_release": 58_200.0,
        "external_release_multiplicity": 117,
        "external_commit_rank": 3,
        "predicted_external_commit_time": 58_203.001,
        "first_local_release": 58_202.30181,
        "second_local_release": 58_202.90035,
        "candidate_count": 9,
        "external": 4,
        "local": 2,
        "total": 6,
    },
    2: {
        "external_release": 45_000.0,
        "external_release_multiplicity": 127,
        "external_commit_rank": 0,
        "predicted_external_commit_time": 45_000.001,
        "first_local_release": 44_999.16006,
        "second_local_release": 44_999.31313,
        "candidate_count": 82,
        "external": 1,
        "local": 2,
        "total": 3,
    },
}
EXPECTED_POOL_HASHES = {
    1: (
        "1e4a19ba8214635367e7f4a3f6aded487624f6508991632f7d0ddc32743d2fce",
        "f5588b26ce6230b078e1f7eeab464c010be2c979d71ebd54a813c71e5de603c2",
    ),
    2: (
        "24dc5dc2351484f8ab7756e18f761ab849209893805f72350a9dca07547f2986",
        "3671b54a91a5910c96abc013ab934a2902b6f0f337bea32de1c2e262d98ccde4",
    ),
}
EXPECTED_REGENERATION_HASHES = {
    1: {
        "manifest_semantics": (
            "2001fa39b8ca42a866c53bef44b583745acaf41724b3578e04eb40aa9d9a1e62"
        ),
        "raw": "5fc1a834f1cf03d28417d3e5a6c16114967a7f9f352af9b795f25a00df983ae6",
        "canonical_jsonl": (
            "f167648ca524770b48465c66eaa7a548390f31e35815fb9c73accff68520c3a1"
        ),
        "ordered_rows": (
            "99641a195191744b541039accd3474f40a35990345c0c4e60c8b39e7e2f96f76"
        ),
    },
    2: {
        "manifest_semantics": (
            "c564b43a026c96e0d0e647e910724d017d0ee1c2bd2584f89085b40dfa7ac25f"
        ),
        "raw": "f7528ca4207d77ea96aca3bea0c6761d6a7a7656944f6a7e31256248f44fbc20",
        "canonical_jsonl": (
            "55538837011a1ed31eb272cc170fdc9fefb3b40ec14e2ae0574877a8c465a115"
        ),
        "ordered_rows": (
            "823a7f3d7022daa063ba167889658e30dd4a84a7b6ea0724cb401ec66049893c"
        ),
    },
}
EXPECTED_SELECTION_HASHES = {
    1: {
        "external_release_histogram": (
            "29b791b11683997127cab95c7ea9762c2b93150b38328bb30df08527630381dd"
        ),
        "candidate_set": (
            "0a62a1c72182b832f04ae0835bc6b71ef32ec1ae81e40d76afde80835cbf1684"
        ),
        "original_rows": (
            "79d321de396cbbaffa786c11d8a032d57ad0be448b021f680e0f890dc7a94478"
        ),
        "projected_rows": (
            "48727b540fe2853b392e3cc10ee5a0995c735e4154dd5e9a5d6c224028a3dbd3"
        ),
        "projection_identity": (
            "691d6015af2eae895351afeca33732cd4c4a01fc5293cab90d367707ccfa0874"
        ),
        "selected_segment_ids": (
            "fe20379a1c66ed627654c51e66ce4e3e11974b845196e207e2d3d18dc328dda6"
        ),
    },
    2: {
        "external_release_histogram": (
            "ba35a35236263aa430ea8290af271934546e99d9f06605fe7b99784596d7a534"
        ),
        "candidate_set": (
            "f4e8b6232bd9ed8bfed92d3f279232a57643b3f8e7d7dc5901b35522c357d54e"
        ),
        "original_rows": (
            "5b2c8d6b80159f29abdf38e42c8cf7a3f514836c927479a6e16f6890b7924f8f"
        ),
        "projected_rows": (
            "7b86b3fc69bd6a9d9984f1f48a9e64f5e513c08bd416b9a93c00f6d27c89b1bd"
        ),
        "projection_identity": (
            "eddb032a9b584dfb9b5b249272f586efd6f15aa82a7a1baad8deb49a532657b0"
        ),
        "selected_segment_ids": (
            "bdf084982830882a1b36ac6e67d2f198a0fb13ba33ab0f1a0691ca9f1484219d"
        ),
    },
}
FROZEN_SOURCE_HASHES: Mapping[Path, str] = {
    PROTOCOL_PATH: "ac4c92b3e3090254799b1c12c723786d3a4116bbc9c1c1aaf6bf454afc5e5c1e",
    EXECUTION_REGISTRATION_PATH: (
        "1733b7311d996eef27ac70097c11984d90d9e929b5e49c9fb6645bd471537531"
    ),
    V3R5_ADDENDUM_PATH: (
        "10291eb088000a70838de9ded86ea3f1cfe7975ebf3fb6a3453fdb615ab080ce"
    ),
    V3R6_ADDENDUM_PATH: (
        "4a2a6a66337989cc18eb7b5f3e2b99f4dfce57db0efcf618b5c8c11545ace4d8"
    ),
    PROFILE_PATH: "70aeeafe2c774d415fe9f922eedec36e8e35132bcba04596c2b1c486ffb3d1df",
    SOURCE_WORKLOAD_PATH: "968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f",
    SOURCE_TIMETABLE_PATH: "0f39d359b47a3f243ab077e4a294cbab56ec306a0f89bcc0ccc1d946caceef87",
    MANIFEST_DIR / "nanning_1x_manifest.json": (
        "6d097ca9ddf6975dd79fdaa04d5e68276864bbdc790ac67a947ffc24f5d13de1"
    ),
    MANIFEST_DIR / "nanning_2x_manifest.json": (
        "4b86c684f15f02f967e2477860150145ebb34df6a10174fcde1077a3500eae2e"
    ),
    G31_AGGREGATE_PATH: (
        "2bd68c9007fda73d93efd25200ff7fadd9d516e08adbcb b33dd777f8168a72da"
    ).replace(" ", ""),
    G31_BINARY: "35a43037b0881aca3b92732541126ee71c2d431d537a13e07918777c8b7cce59",
}

Executor = Callable[..., Mapping[str, Any]]


class SelectionError(RuntimeError):
    """Raised when a frozen source, selection, or runtime gate is invalid."""


def _portable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            portable_key = str(key)
            if portable_key in result:
                raise SelectionError(
                    f"JSON object key collision after string conversion: {portable_key!r}"
                )
            result[portable_key] = _portable(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_portable(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Out of range float values are not JSON compliant")
    return value


def _json_bytes(value: Any, *, pretty: bool = False) -> bytes:
    portable = _portable(value)
    options: dict[str, Any] = {
        "sort_keys": True,
        "ensure_ascii": False,
        "allow_nan": False,
    }
    if pretty:
        options["indent"] = 2
    else:
        options["separators"] = (",", ":")
    return (json.dumps(portable, **options) + ("\n" if pretty else "")).encode(
        "utf-8"
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SelectionError(f"duplicate JSON object key is forbidden: {key!r}")
        result[key] = value
    return result


def _parse_strict_json_bytes(data: bytes) -> Any:
    try:
        text_value = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SelectionError("strict JSON artifact is not UTF-8") from error
    return json.loads(
        text_value,
        parse_constant=_reject_json_constant,
        object_pairs_hook=_strict_json_object,
    )


def read_strict_json(path: Path) -> Any:
    return _parse_strict_json_bytes(path.read_bytes())


def atomic_write_strict_json(path: Path, value: Mapping[str, Any]) -> None:
    """Publish one strict JSON object atomically and never overwrite evidence."""

    if path.exists():
        raise FileExistsError(f"append-only evidence already exists: {path}")
    data = _json_bytes(value, pretty=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        handle = tempfile.NamedTemporaryFile(
            mode="wb",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary = Path(handle.name)
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            raise FileExistsError(f"append-only evidence already exists: {path}")
        os.link(temporary, path)
        temporary.unlink()
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def with_content_hash(value: Mapping[str, Any]) -> dict[str, Any]:
    if "artifact_content_sha256" in value:
        raise SelectionError("artifact content hash must not already be present")
    result = _portable(deepcopy(dict(value)))
    if not isinstance(result, dict):
        raise SelectionError("artifact must normalize to a JSON object")
    result["artifact_content_sha256"] = canonical_sha256(result)
    return result


def verify_content_hash(value: Mapping[str, Any]) -> str:
    expected = value.get("artifact_content_sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        raise SelectionError("control artifact lacks a canonical content hash")
    unhashed = {key: item for key, item in value.items() if key != "artifact_content_sha256"}
    actual = canonical_sha256(unhashed)
    if actual != expected:
        raise SelectionError("control artifact canonical content hash mismatch")
    return actual


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SelectionError(f"{label} must be an object")
    return value


def _rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(row, Mapping) for row in value):
        raise SelectionError(f"{label} must be an array of objects")
    return list(value)


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SelectionError(f"{label} must be an integer")
    return value


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SelectionError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise SelectionError(f"{label} must be finite")
    return result


def verify_frozen_sources() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path, expected in FROZEN_SOURCE_HASHES.items():
        try:
            actual = file_sha256(path)
            error = None
        except OSError as caught:
            actual = None
            error = f"{type(caught).__name__}: {caught}"
        rows.append(
            {
                "path": path.relative_to(ROOT).as_posix()
                if path.is_relative_to(ROOT)
                else str(path),
                "expected_sha256": expected,
                "actual_sha256": actual,
                "pass": actual == expected,
                "error": error,
            }
        )
    return {
        "pass": all(row["pass"] for row in rows),
        "g31_base_commit": G31_BASE_COMMIT,
        "protocol_path": PROTOCOL_PATH.relative_to(ROOT).as_posix(),
        "protocol_sha256": file_sha256(PROTOCOL_PATH),
        "execution_registration_id": EXECUTION_REGISTRATION_ID,
        "execution_registration_path": EXECUTION_REGISTRATION_PATH.relative_to(
            ROOT
        ).as_posix(),
        "execution_registration_sha256": file_sha256(
            EXECUTION_REGISTRATION_PATH
        ),
        "files": rows,
        "bundle_sha256": canonical_sha256(rows),
    }


def execution_dependency_identity(auditor: Any | None = None) -> dict[str, Any]:
    selected_auditor = auditor or _v3_auditor()
    from czr005 import cpp_backend

    paths = (
        RUNNER_PATH,
        Path(workload31.__file__).resolve(),
        Path(map_adapter.__file__).resolve(),
        Path(native31.__file__).resolve(),
        Path(selected_auditor.__file__).resolve(),
        Path(cpp_backend.__file__).resolve(),
        ROOT / "src/czr005/g4irsf32_v3r2_outcome_join.py",
        ROOT / "scripts/eval/run_g4irsf32_v3r3_p0_campaign.py",
        ROOT / "tests/test_g4irsf32_v3r3_p0_campaign.py",
    )
    rows = [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": file_sha256(path),
        }
        for path in paths
    ]
    return {"files": rows, "bundle_sha256": canonical_sha256(rows)}


def _manifest_semantics(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in manifest.items()
        if key not in {"raw_output", "canonical_output"}
    }


def validate_regenerated_workload(
    scale: int,
    manifest: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    frozen_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Pure fail-closed validation of one regenerated canonical workload."""

    if scale not in EXPECTED_SCALE_COUNTS:
        raise SelectionError("scale must be 1 or 2")
    expected_raw, expected_segments = EXPECTED_SCALE_COUNTS[scale]
    lifecycle = _mapping(manifest.get("lifecycle"), "manifest.lifecycle")
    checks = {
        "schema": manifest.get("schema") == workload31.SCHEMA,
        "status": manifest.get("status") == workload31.STATUS,
        "scale": manifest.get("scale") == scale,
        "map_id": manifest.get("map_id") == MAP_ID,
        "raw_count": manifest.get("raw_task_count") == expected_raw,
        "segment_count": manifest.get("expanded_segment_count")
        == expected_segments,
        "storage_pair": lifecycle.get("storage_in_goal") == EXTERNAL_START
        and lifecycle.get("storage_out_start") == EXTERNAL_START,
        "frozen_manifest_semantics": _manifest_semantics(manifest)
        == _manifest_semantics(frozen_manifest),
        "manifest_invariants": isinstance(manifest.get("invariants"), Mapping)
        and all(manifest["invariants"].values()),
    }
    if not all(checks.values()):
        raise SelectionError(f"regenerated {scale}x manifest mismatch: {checks}")
    if len(rows) != expected_segments:
        raise SelectionError(f"regenerated {scale}x row count mismatch")

    segment_ids: list[str] = []
    task_ids: set[int] = set()
    external_count = 0
    local_count = 0
    for index, row in enumerate(rows):
        segment_id = row.get("segment_id")
        leg = row.get("leg")
        if not isinstance(segment_id, str) or not segment_id:
            raise SelectionError(f"rows[{index}].segment_id is invalid")
        task_id = _integer(row.get("task_id"), f"rows[{index}].task_id")
        start = _integer(row.get("start"), f"rows[{index}].start")
        _integer(row.get("goal"), f"rows[{index}].goal")
        release = _finite(row.get("pass_time"), f"rows[{index}].pass_time")
        deadline = _finite(row.get("std"), f"rows[{index}].std")
        if release > deadline or segment_id != f"{task_id}:{leg}":
            raise SelectionError(f"rows[{index}] has invalid lifecycle identity/timing")
        segment_ids.append(segment_id)
        task_ids.add(task_id)
        external_count += start == EXTERNAL_START and leg == "storage_out"
        local_count += start == LOCAL_START
    if len(set(segment_ids)) != len(segment_ids):
        raise SelectionError("regenerated segment IDs are not unique")
    if len(task_ids) != expected_raw:
        raise SelectionError("regenerated raw task identity count mismatch")
    expected_external, expected_local = EXPECTED_POOL_COUNTS[scale]
    if (external_count, local_count) != (expected_external, expected_local):
        raise SelectionError("regenerated E/L pool cardinalities changed")
    external_pool = sorted(
        (
            dict(row)
            for row in rows
            if row.get("start") == EXTERNAL_START
            and row.get("leg") == "storage_out"
        ),
        key=lambda row: (row["pass_time"], row["segment_id"], row["task_id"]),
    )
    local_pool = sorted(
        (dict(row) for row in rows if row.get("start") == LOCAL_START),
        key=lambda row: (row["pass_time"], row["segment_id"], row["task_id"]),
    )
    external_pool_sha = canonical_sha256(external_pool)
    local_pool_sha = canonical_sha256(local_pool)
    if (external_pool_sha, local_pool_sha) != EXPECTED_POOL_HASHES[scale]:
        raise SelectionError("regenerated E/L canonical pool hashes changed")
    return {
        "pass": True,
        "checks": checks,
        "raw_task_count": len(task_ids),
        "segment_count": len(rows),
        "external_pool_count": external_count,
        "local_pool_count": local_count,
        "external_pool_sha256": external_pool_sha,
        "local_pool_sha256": local_pool_sha,
        "ordered_rows_sha256": canonical_sha256(list(rows)),
    }


def select_commit_aligned_cohort(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Select the smallest pre-arrival local-overlap external prefix.

    Only committed workload identity, role, and release fields plus the frozen
    53->49 timing constants participate.  No completion, event, queue, wait,
    safety, or G32 field is accepted as an input to the selection rule.
    """

    external = sorted(
        (
            row
            for row in rows
            if row.get("start") == EXTERNAL_START
            and row.get("leg") == "storage_out"
            and str(row.get("segment_id", "")).endswith(":storage_out")
        ),
        key=lambda row: (
            _finite(row.get("pass_time"), "external.pass_time"),
            str(row["segment_id"]),
            _integer(row.get("task_id"), "external.task_id"),
        ),
    )
    local = sorted(
        (row for row in rows if row.get("start") == LOCAL_START),
        key=lambda row: (
            _finite(row.get("pass_time"), "local.pass_time"),
            str(row["segment_id"]),
            _integer(row.get("task_id"), "local.task_id"),
        ),
    )
    if not external or len(local) < 2:
        raise SelectionError("E pool and at least two local rows are required")
    if len({str(row["segment_id"]) for row in external}) != len(external):
        raise SelectionError("external pool segment identities are not unique")
    if len({str(row["segment_id"]) for row in local}) != len(local):
        raise SelectionError("local pool segment identities are not unique")

    external_by_release: dict[float, list[Mapping[str, Any]]] = defaultdict(list)
    for row in external:
        external_by_release[
            _finite(row.get("pass_time"), "external.pass_time")
        ].append(row)
    histogram = sorted(
        (release, len(burst))
        for release, burst in external_by_release.items()
    )

    candidates: list[dict[str, Any]] = []
    for first, second in zip(local, local[1:]):
        first_release = _finite(first.get("pass_time"), "first local pass_time")
        second_release = _finite(
            second.get("pass_time"), "second local pass_time"
        )
        local_gap = second_release - first_release
        if not (
            AUDIT_EPSILON
            < local_gap
            < NODE49_SERVICE_SECONDS - AUDIT_EPSILON
        ):
            continue
        for external_release, burst in external_by_release.items():
            first_external_arrival = (
                external_release
                + EXTERNAL_FIRST_ENTRY_OFFSET_SECONDS
                + EXTERNAL_53_TO_49_TRAVEL_SECONDS
            )
            second_local_service_start = max(
                second_release + SOURCE_RETRY_INTERVAL_SECONDS,
                first_release + NODE49_SERVICE_SECONDS,
            )
            second_local_service_complete = (
                second_local_service_start + NODE49_SERVICE_SECONDS
            )
            if (
                second_local_service_complete
                > first_external_arrival - AUDIT_EPSILON
            ):
                continue
            commit_rank = max(
                0,
                math.ceil(
                    (
                        second_release
                        - external_release
                        - EXTERNAL_FIRST_ENTRY_OFFSET_SECONDS
                    )
                    / NODE49_SERVICE_SECONDS
                ),
            )
            predicted_commit = (
                external_release
                + EXTERNAL_FIRST_ENTRY_OFFSET_SECONDS
                + commit_rank * NODE49_SERVICE_SECONDS
            )
            if (
                commit_rank >= len(burst)
                or predicted_commit <= second_release + AUDIT_EPSILON
                or predicted_commit
                >= first_release + NODE49_SERVICE_SECONDS - AUDIT_EPSILON
                or predicted_commit
                >= first_external_arrival - AUDIT_EPSILON
            ):
                continue
            candidates.append(
                {
                    "external_release": external_release,
                    "external_release_multiplicity": len(burst),
                    "external_prefix_count": commit_rank + 1,
                    "external_commit_rank": commit_rank,
                    "predicted_external_commit_time": predicted_commit,
                    "first_local_release": first_release,
                    "first_local_segment_id": str(first["segment_id"]),
                    "first_local_task_id": _integer(
                        first.get("task_id"), "first local task_id"
                    ),
                    "second_local_release": second_release,
                    "second_local_segment_id": str(second["segment_id"]),
                    "second_local_task_id": _integer(
                        second.get("task_id"), "second local task_id"
                    ),
                    "local_release_gap_seconds": local_gap,
                }
            )

    candidates.sort(
        key=lambda candidate: (
            candidate["external_prefix_count"],
            candidate["external_release"],
            candidate["first_local_release"],
            candidate["second_local_release"],
            candidate["first_local_segment_id"],
            candidate["first_local_task_id"],
            candidate["second_local_segment_id"],
            candidate["second_local_task_id"],
        )
    )
    if not candidates:
        raise SelectionError("no frozen pre-arrival local-overlap candidate exists")
    selected_candidate = candidates[0]
    selected_external = external_by_release[
        selected_candidate["external_release"]
    ][: selected_candidate["external_prefix_count"]]
    local_by_segment_id = {str(row["segment_id"]): row for row in local}
    selected_local = [
        local_by_segment_id[selected_candidate["first_local_segment_id"]],
        local_by_segment_id[selected_candidate["second_local_segment_id"]],
    ]
    selected_rows = sorted(
        (dict(row) for row in [*selected_external, *selected_local]),
        key=lambda row: (
            _finite(row.get("pass_time"), "selected.pass_time"),
            str(row["segment_id"]),
            _integer(row.get("task_id"), "selected.task_id"),
        ),
    )
    selected_ids = [str(row["segment_id"]) for row in selected_rows]
    if len(selected_ids) != len(set(selected_ids)):
        raise SelectionError("selected segment identities are not unique")
    return (
        {
            "external_first_entry_offset_seconds": (
                EXTERNAL_FIRST_ENTRY_OFFSET_SECONDS
            ),
            "node49_service_seconds": NODE49_SERVICE_SECONDS,
            "source_retry_interval_seconds": SOURCE_RETRY_INTERVAL_SECONDS,
            "external_53_to_49_travel_seconds": (
                EXTERNAL_53_TO_49_TRAVEL_SECONDS
            ),
            "candidate_count": len(candidates),
            "candidate_set_sha256": canonical_sha256(candidates),
            **selected_candidate,
            "external_selected_count": len(selected_external),
            "local_selected_count": len(selected_local),
            "selected_segment_count": len(selected_rows),
            "external_release_histogram_sha256": canonical_sha256(histogram),
            "selected_segment_ids_sha256": canonical_sha256(selected_ids),
        },
        selected_rows,
    )


def project_selected_rows(
    original_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Bind registered external/local labels and preserve every other field."""

    projected: list[dict[str, Any]] = []
    identity: list[dict[str, Any]] = []
    for ordinal, original in enumerate(original_rows):
        row = dict(original)
        start = _integer(row.get("start"), "selected.start")
        if start == EXTERNAL_START and row.get("leg") == "storage_out":
            source = "external"
        elif start == LOCAL_START:
            source = "local"
        else:
            raise SelectionError("selected row is outside the frozen E/L pools")
        if "source" in row:
            raise SelectionError("canonical G31 row unexpectedly already has source")
        row["source"] = source
        projected.append(row)
        identity.append(
            {
                "ordered_row_ordinal": ordinal,
                "segment_id": row["segment_id"],
                "task_id": row["task_id"],
                "start": start,
                "projected_source": source,
                "original_row_sha256": canonical_sha256(original),
                "projected_row_sha256": canonical_sha256(row),
            }
        )
    origin_counts = Counter(row["source"] for row in projected)
    if set(origin_counts) != {"external", "local"} or min(origin_counts.values()) <= 0:
        raise SelectionError("projected selection must retain both exact origins")
    return projected, identity


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line, parse_constant=_reject_json_constant)
            if not isinstance(value, dict):
                raise SelectionError(f"{path}:{line_number} is not an object")
            rows.append(value)
    return rows


def regenerate_and_select(
    temporary_root: Path,
    *,
    source_raw_path: Path = SOURCE_TIMETABLE_PATH,
    map_profile_path: Path = PROFILE_PATH,
    manifest_dir: Path = MANIFEST_DIR,
) -> dict[int, dict[str, Any]]:
    """Regenerate both frozen workloads and retain only outcome-blind evidence."""

    result: dict[int, dict[str, Any]] = {}
    for scale in (1, 2):
        output_dir = temporary_root / f"{scale}x"
        generated = workload31.build_workload(
            scale=scale,
            source_raw_path=source_raw_path,
            map_profile_path=map_profile_path,
            output_dir=output_dir,
        )
        generated_manifest_path = output_dir / f"nanning_{scale}x_manifest.json"
        generated_manifest = _mapping(
            read_strict_json(generated_manifest_path), "generated manifest"
        )
        if generated_manifest != generated:
            raise SelectionError("returned and written regenerated manifests differ")
        frozen_manifest_path = manifest_dir / f"nanning_{scale}x_manifest.json"
        frozen_manifest = _mapping(
            read_strict_json(frozen_manifest_path), "frozen manifest"
        )
        canonical_path = output_dir / f"nanning_{scale}x_canonical.jsonl"
        raw_path = output_dir / f"nanning_{scale}x_raw.txt"
        rows = _read_jsonl(canonical_path)
        validation = validate_regenerated_workload(
            scale, generated_manifest, rows, frozen_manifest
        )
        cohort, original_selected_rows = select_commit_aligned_cohort(rows)
        selected_rows, projection_identity = project_selected_rows(
            original_selected_rows
        )
        result[scale] = {
            "scale": scale,
            "workload": {
                "validation": validation,
                "frozen_manifest_sha256": file_sha256(frozen_manifest_path),
                "regenerated_manifest_sha256": file_sha256(
                    generated_manifest_path
                ),
                "regenerated_manifest_semantics_sha256": canonical_sha256(
                    _manifest_semantics(generated_manifest)
                ),
                "regenerated_raw_sha256": file_sha256(raw_path),
                "regenerated_canonical_jsonl_sha256": file_sha256(canonical_path),
                "regenerated_ordered_rows_sha256": canonical_sha256(rows),
            },
            "selection": {
                "selector_algorithm_id": SELECTOR_ALGORITHM_ID,
                "rule": SELECTOR_RULE,
                "outcome_fields_read": False,
                **cohort,
                "original_selected_rows_sha256": canonical_sha256(
                    original_selected_rows
                ),
                "selected_rows_sha256": canonical_sha256(selected_rows),
                "projection_identity_sha256": canonical_sha256(
                    projection_identity
                ),
                "original_selected_rows": original_selected_rows,
                "selected_rows": selected_rows,
                "projection_identity": projection_identity,
            },
        }
    return result


def build_g31_control_request(
    scale: int,
    selected_rows: Sequence[Mapping[str, Any]],
    *,
    binary: Path = G31_BINARY,
    map_profile_path: Path = PROFILE_PATH,
    auditor: Any | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if scale not in EXPECTED_SELECTION_COUNTS:
        raise SelectionError("control request scale must be 1 or 2")
    expected_count = EXPECTED_SELECTION_COUNTS[scale]["total"]
    if len(selected_rows) != expected_count:
        raise SelectionError(
            f"control request requires the exact {expected_count}-row {scale}x slice"
        )
    selected_auditor = auditor or _v3_auditor()
    profile = map_adapter.load_map_profile(
        map_profile_path, storage_source_nodes=[EXTERNAL_START]
    )
    request, potential = map_adapter.build_s4_request(
        profile,
        selected_rows,
        binary=binary,
        scenario=f"g4irsf32_v3r7_nanning_p0_{scale}x",
        max_events=2_000_000,
        max_simulation_time=-1.0,
        trace_limit=TRACE_LIMIT,
        event_trace_limit=TRACE_LIMIT,
        summary_only=False,
        edge_speed_mps=SPEED_MPS,
        enable_s4_local_potential_descent_guard=True,
        enable_s4_direct_neighbor_merge_calendar_visibility=True,
        complete_on_goal_arrival=True,
    )
    request.update(fault_windows=[])
    ordinary_projection = {
        key: value
        for key, value in selected_auditor.REQUEST_PROJECTION.items()
        if key != "source_aware_destination_service_trace_limit"
    }
    mismatches = {
        key: {"expected": value, "actual": request.get(key)}
        for key, value in ordinary_projection.items()
        if request.get(key) != value
    }
    if mismatches:
        raise SelectionError(f"G31 control request projection drift: {mismatches}")
    if request.get("retry_interval") != SOURCE_RETRY_INTERVAL_SECONDS:
        raise SelectionError(
            "G31 control retry interval differs from frozen selector geometry"
        )
    expected_keys = (
        set(ordinary_projection)
        | (
            set(selected_auditor.REQUEST_DATA_KEYS)
            - {"source_aware_destination_service_mode"}
        )
        | set(selected_auditor.REQUEST_BINARY_LOCATOR_KEYS)
    )
    if set(request) != expected_keys:
        raise SelectionError(
            "G31 control request key set differs from the omitted V3R2 projection"
        )
    if request.get("storage_source_nodes") != [EXTERNAL_START]:
        raise SelectionError("G31 control storage role must be exactly [53]")
    return request, potential


def _v3_auditor() -> Any:
    return importlib.import_module(
        "scripts.eval.run_g4irsf32_v3r2_external_commit_local_virtual_shadow"
    )


def _reject_g32_contamination(
    request: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    expected_binary_sha256: str,
    auditor: Any,
) -> None:
    source_aware_keys = {
        str(key) for key in request if str(key).startswith(auditor.NS)
    }
    if source_aware_keys:
        raise SelectionError("control request is not exact omitted/default-off")
    summary = _mapping(payload.get("summary"), "payload.summary")
    context = _mapping(payload.get("trace_context"), "payload.trace_context")
    if any(
        str(key).startswith(auditor.NS)
        for mapping in (payload, summary, context)
        for key in mapping
    ):
        raise SelectionError("G31 control payload is contaminated by G32 telemetry")
    if context.get("schema_id") != auditor.ORDINARY_TRACE_SCHEMA_ID:
        raise SelectionError("control payload ordinary trace schema mismatch")
    loaded_path, digest = auditor._loaded_binary(payload)
    request_path_value = request.get("expected_binary_path")
    search_path_value = request.get("search_path")
    if not isinstance(request_path_value, (str, Path)) or not isinstance(
        search_path_value, (str, Path)
    ):
        raise SelectionError("control request lacks an explicit binary locator")
    requested_path = Path(request_path_value).resolve(strict=True)
    requested_search = Path(search_path_value).resolve(strict=True)
    resolved_loaded_path = Path(loaded_path).resolve(strict=True)
    if (
        digest != expected_binary_sha256
        or resolved_loaded_path != requested_path
        or requested_search != requested_path.parent
    ):
        raise SelectionError("control payload did not load the frozen G31 binary")


def _qualifying_control_events(
    payload: Mapping[str, Any],
    episodes: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    bags = _rows(payload.get("bags"), "payload.bags")
    events = _rows(payload.get("events"), "payload.events")
    by_bag = {_integer(row.get("runtime_bag_id"), "bag.runtime_bag_id"): row for row in bags}
    if len(by_bag) != len(bags):
        raise SelectionError("runtime bag identities are not unique")
    event_sequences = [_integer(row.get("seq"), "event.seq") for row in events]
    event_times = [_finite(row.get("time"), "event.time") for row in events]
    # seq is the unique identity assigned when an event is scheduled, not its
    # execution ordinal.  A later-created passive/microphase event may execute
    # before an older future event, so global seq monotonicity is not a runtime
    # invariant.  The emitted trace itself must remain chronological and seq
    # identities must remain unique.
    if len(set(event_sequences)) != len(event_sequences):
        raise SelectionError("ordinary event sequence identities are not unique")
    if any(
        right + AUDIT_EPSILON < left
        for left, right in zip(event_times, event_times[1:])
    ):
        raise SelectionError("ordinary event times are not monotonic")
    ordered_events = events

    service_at_49: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for episode in episodes:
        if episode.get("node") == LOCAL_START:
            service_at_49[_integer(episode.get("runtime_bag_id"), "episode bag")].append(
                episode
            )

    seam_enters: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    seam_exits: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for event in ordered_events:
        if event.get("from_node") != EXTERNAL_START or event.get("to_node") != LOCAL_START:
            continue
        runtime_id = _integer(event.get("runtime_bag_id"), "seam event bag")
        if event.get("event") == "EDGE_ENTER":
            seam_enters[runtime_id].append(event)
        elif event.get("event") == "EDGE_EXIT":
            seam_exits[runtime_id].append(event)
    for runtime_id in set(seam_enters) | set(seam_exits):
        enters = seam_enters.get(runtime_id, [])
        exits = seam_exits.get(runtime_id, [])
        if len(enters) != 1 or len(exits) != 1:
            raise SelectionError("53->49 traversal lacks a unique EDGE_ENTER/EDGE_EXIT")
        enter, exit_event = enters[0], exits[0]
        bag = by_bag.get(runtime_id)
        if (
            bag is None
            or enter.get("task_id") != bag.get("task_id")
            or enter.get("segment_id") != bag.get("segment_id")
            or exit_event.get("task_id") != bag.get("task_id")
            or exit_event.get("segment_id") != bag.get("segment_id")
            or exit_event.get("node") != LOCAL_START
            or exit_event.get("reason") != "edge_traversal_complete"
            or _integer(exit_event.get("seq"), "seam exit seq")
            <= _integer(enter.get("seq"), "seam enter seq")
            or _finite(exit_event.get("time"), "seam exit time")
            + AUDIT_EPSILON
            < _finite(enter.get("time"), "seam enter time")
        ):
            raise SelectionError("53->49 EDGE_ENTER/EDGE_EXIT identity is inconsistent")

    queue: list[int] = []
    enqueued_at: dict[int, float] = {}
    qualifying: list[dict[str, Any]] = []
    for event in ordered_events:
        if (
            event.get("event") == "EDGE_ENTER"
            and event.get("from_node") == EXTERNAL_START
            and event.get("to_node") == LOCAL_START
            and event.get("reason")
            in {"one_step_reservation_committed", "one_step_merge_grant_committed"}
        ):
            external_id = _integer(event.get("runtime_bag_id"), "external event bag")
            external = by_bag.get(external_id)
            if external is None:
                raise SelectionError("external EDGE_ENTER references an unknown bag")
            if (
                external.get("start") != EXTERNAL_START
                or not str(external.get("segment_id", "")).endswith(":storage_out")
                or external.get("task_id") != event.get("task_id")
                or external.get("segment_id") != event.get("segment_id")
            ):
                raise SelectionError("53->49 EDGE_ENTER has inconsistent external identity")
            # Ordinary G31 telemetry cannot replay the G32 escape token.  A
            # control seam is therefore attributable only when the live
            # source queue has one and only one possible local winner.
            if len(queue) == 1:
                local_id = queue[0]
                local = by_bag.get(local_id)
                event_time = _finite(event.get("time"), "external event time")
                exit_event = seam_exits[external_id][0]
                exit_time = _finite(exit_event.get("time"), "external edge exit time")
                if (
                    local is not None
                    and local_id != external_id
                    and local.get("start") == LOCAL_START
                    and local.get("source") == "local"
                    and _finite(local.get("release_time"), "local release") <= event_time
                    and _finite(local.get("finish_time"), "local finish")
                    > event_time + AUDIT_EPSILON
                    and local.get("completed") is True
                    and external.get("completed") is True
                    and len(service_at_49[local_id]) == 1
                    and len(service_at_49[external_id]) == 1
                ):
                    local_episode = service_at_49[local_id][0]
                    external_episode = service_at_49[external_id][0]
                    local_interval = (
                        _finite(local_episode.get("actual_L_service_start"), "local service start"),
                        _finite(local_episode.get("actual_L_service_complete"), "local service end"),
                    )
                    external_interval = (
                        _finite(external_episode.get("actual_L_service_start"), "external service start"),
                        _finite(external_episode.get("actual_L_service_complete"), "external service end"),
                    )
                    local_live_at_entry = (
                        local_interval[0] + AUDIT_EPSILON >= event_time
                        and local_interval[1] > event_time + AUDIT_EPSILON
                    )
                    exit_starts_external_service = abs(
                        exit_time - external_interval[0]
                    ) <= AUDIT_EPSILON
                    non_overlap = (
                        local_interval[1] <= external_interval[0] + AUDIT_EPSILON
                        or external_interval[1] <= local_interval[0] + AUDIT_EPSILON
                    )
                    if local_live_at_entry and exit_starts_external_service and non_overlap:
                        qualifying.append(
                            {
                                "edge_enter_event": dict(event),
                                "edge_exit_event": dict(exit_event),
                                "external_runtime_bag_id": external_id,
                                "external_segment_id": external["segment_id"],
                                "local_runtime_bag_id": local_id,
                                "local_segment_id": local["segment_id"],
                                "local_source_enqueued_at": enqueued_at[local_id],
                                "local_unique_choose_index": 0,
                                "local_queue_runtime_bag_ids": list(queue),
                                "winner_reconstruction": (
                                    "UNIQUE_LIVE_SOURCE_QUEUE_CANDIDATE_NO_ESCAPE_TOKEN_NEEDED"
                                ),
                                "local_service_episode": dict(local_episode),
                                "external_service_episode": dict(external_episode),
                                "external_edge_exit_equals_L_service_start": True,
                                "local_live_at_edge_entry": True,
                                "node49_service_non_overlap": True,
                            }
                        )
        if event.get("event") != "LOCAL_QUEUE_UPDATE" or event.get("node") != LOCAL_START:
            continue
        runtime_id = _integer(event.get("runtime_bag_id"), "local queue bag")
        reason = event.get("reason")
        if reason == "source_enqueue":
            if runtime_id in enqueued_at:
                raise SelectionError("repeated source enqueue in ordinary trace")
            bag = by_bag.get(runtime_id)
            if (
                bag is None
                or bag.get("start") != LOCAL_START
                or bag.get("source") != "local"
                or bag.get("task_id") != event.get("task_id")
                or bag.get("segment_id") != event.get("segment_id")
            ):
                raise SelectionError("node49 source enqueue has invalid bag identity")
            queue.append(runtime_id)
            enqueued_at[runtime_id] = _finite(event.get("time"), "source enqueue time")
        elif reason == "source_dequeue":
            if runtime_id not in queue:
                raise SelectionError("source dequeue lacks a preceding enqueue")
            bag = by_bag.get(runtime_id)
            if (
                bag is None
                or bag.get("task_id") != event.get("task_id")
                or bag.get("segment_id") != event.get("segment_id")
            ):
                raise SelectionError("node49 source dequeue has invalid bag identity")
            queue.remove(runtime_id)
        elif reason in {"junction_enqueue", "junction_dequeue"}:
            # LOCAL_QUEUE_UPDATE is the shared telemetry event for both the
            # source queue and the ordinary junction queue.  Only source rows
            # participate in the live-winner reconstruction above.
            continue
        else:
            raise SelectionError("node49 local queue update reason is not replayable")
    return qualifying


SAFETY_ZERO_FIELDS = (
    "reservation_conflicts",
    "physical_fault_edge_entry_violation_count",
    "runtime_full_astar_calls",
    "runtime_full_cie_astar_calls",
    "global_reservation_scan_count",
    "priority_global_scan_count",
    "scorer_runtime_global_scan_count",
    "microphase_runtime_global_scan_count",
    "first_edge_credit_global_scan_count",
    "unresolved_deadlock_count",
    "fault_event_count",
    "repair_event_count",
)


def audit_g31_control_payload(
    *,
    scale: int,
    selected_rows: Sequence[Mapping[str, Any]],
    request: Mapping[str, Any],
    payload: Mapping[str, Any],
    expected_binary_sha256: str = FROZEN_SOURCE_HASHES[G31_BINARY],
    auditor: Any | None = None,
) -> dict[str, Any]:
    """Fail closed on identity, completion, trace, safety, and real 53->49 state."""

    selected_auditor = auditor or _v3_auditor()
    _reject_g32_contamination(
        request,
        payload,
        expected_binary_sha256=expected_binary_sha256,
        auditor=selected_auditor,
    )
    summary, _context = selected_auditor._ordinary_health(payload)
    services = selected_auditor._services(request)
    episodes, ordinary_events, _bags_by_id = selected_auditor._base_episodes(
        f"nanning_p0_control_{scale}x", payload, services
    )
    identity = selected_auditor._bag_population_identity(payload, request)
    junctions = _rows(payload.get("junction_state"), "payload.junction_state")
    global_service = selected_auditor._global_service_calendar_audit(
        episodes, junctions, request
    )
    bags = _rows(payload.get("bags"), "payload.bags")
    lifecycle = _rows(payload.get("merge_grant_lifecycle"), "merge_grant_lifecycle")
    decisions = _rows(payload.get("decisions"), "payload.decisions")
    hold_attempts = _rows(payload.get("hold_attempts"), "payload.hold_attempts")
    qualifying = _qualifying_control_events(payload, episodes)

    expected_count = len(selected_rows)
    service = selected_auditor._service_audit(
        f"nanning_p0_control_{scale}x",
        expected_count,
        {"external", "local"},
        payload,
        request,
        exact_node=LOCAL_START,
    )
    full_safety = selected_auditor._safety(summary)
    legacy_wait = _mapping(
        service.get("legacy_wait_over_120"), "control service legacy wait"
    )
    permanent = _mapping(
        service.get("permanent_starvation"), "control permanent starvation"
    )
    service_sequence = _mapping(
        service.get("service_sequence"), "control service sequence"
    )
    requested_origins = Counter(
        str(record[6]) for record in request.get("bag_records", [])
    )
    completed_origins = Counter(
        str(bag.get("source")) for bag in bags if bag.get("completed") is True
    )
    node49_counts = Counter(
        _integer(row.get("runtime_bag_id"), "node49 service bag")
        for row in episodes
        if row.get("node") == LOCAL_START
    )
    request_nodes = {_integer(row[0], "request node") for row in request["node_records"]}
    junction_by_node = {
        _integer(row.get("node"), "junction node"): row for row in junctions
    }
    junction_nodes = set(junction_by_node)
    request_active_nodes = {
        _integer(record[index], "request active node")
        for record in request.get("bag_records", [])
        for index in (4, 5)
    }
    event_active_nodes = {
        node
        for event in ordinary_events
        for key in ("node", "from_node", "to_node")
        for node in (_integer(event.get(key), f"event.{key}"),)
        if node >= 0
    }
    expected_junction_nodes = request_active_nodes | event_active_nodes
    extra_state_inert = all(
        _integer(
            junction_by_node[node].get("service_reservation_count"),
            "dormant junction service reservation count",
        )
        == 0
        for node in junction_nodes - expected_junction_nodes
    )
    active_node_identity_valid = (
        bool(expected_junction_nodes)
        and expected_junction_nodes <= request_nodes
        and len(junction_nodes) == len(junctions)
        and expected_junction_nodes <= junction_nodes <= request_nodes
        and extra_state_inert
    )
    strict_trace_counts = (
        summary.get("decision_trace_stored_count") == len(decisions)
        and summary.get("hold_trace_stored_count") == len(hold_attempts)
        and summary.get("merge_grant_lifecycle_stored_count") == len(lifecycle)
    )
    completion = (
        summary.get("requested_count") == expected_count
        and summary.get("completed_count") == expected_count
        and summary.get("failed_count") == 0
        and summary.get("final_active_bag_count") == 0
        and len(bags) == expected_count
        and all(bag.get("completed") is True for bag in bags)
        and all(
            math.isfinite(_finite(bag.get("finish_time"), "bag.finish_time"))
            and _finite(bag.get("finish_time"), "bag.finish_time")
            <= _finite(bag.get("deadline"), "bag.deadline")
            for bag in bags
        )
        and completed_origins == requested_origins
    )
    final_pending_zero = (
        active_node_identity_valid
        and all(
            row.get("final_source_queue_length") == 0
            and row.get("final_junction_queue_length") == 0
            and row.get("scheduled_incoming") == 0
            for row in junctions
        )
        and summary.get("merge_grant_final_active_unconsumed") == 0
        and summary.get("merge_grant_outstanding_request_count") == 0
        and summary.get("first_edge_credit_active_count") == 0
    )
    safety = (
        full_safety
        and all(summary.get(field) == 0 for field in SAFETY_ZERO_FIELDS)
        and summary.get("event_limit_reached") is False
        and summary.get("time_limit_reached") is False
        and summary.get("event_trace_truncated") is False
        and summary.get("decision_trace_truncated") is False
        and summary.get("merge_grant_lifecycle_complete") is True
        and summary.get("merge_grant_lifecycle_telemetry_truncated") is False
        and summary.get("merge_grant_lifecycle_dropped_count") == 0
        and summary.get("merge_grant_active_state_integrity_pass") is True
        and summary.get("merge_grant_protocol_integrity_pass") is True
    )
    service_once = (
        len(node49_counts) == expected_count
        and all(value == 1 for value in node49_counts.values())
    )
    checks = {
        "exact_population_identity": identity.get("pass") is True,
        "complete_safe_terminal_population": completion,
        "ordinary_trace_complete": strict_trace_counts,
        "global_service_calendar": global_service.get("pass") is True,
        "every_selected_segment_served_once_at_node49": service_once,
        "final_pending_zero": final_pending_zero,
        "stable_no_fault_no_global_search": safety,
        "full_service_audit": service.get("pass") is True,
        "legacy_wait_native_consistent": legacy_wait.get("pass") is True,
        "permanent_starvation_zero": permanent.get("pass") is True,
        "service_sequence_conservation": service_sequence.get("pass") is True,
        "real_53_to_49_with_released_live_local_winner": bool(qualifying),
    }
    pass_without_event = all(
        value
        for name, value in checks.items()
        if name != "real_53_to_49_with_released_live_local_winner"
    )
    passed = all(checks.values())
    status = PASS if passed else NO_EVENT if pass_without_event else NO_GO
    return {
        "pass": passed,
        "status": status,
        "checks": checks,
        "qualifying_event_count": len(qualifying),
        "qualifying_events": qualifying,
        "population_identity": identity,
        "global_service_calendar": global_service,
        "service_audit": service,
        "legacy_wait_over_120": legacy_wait,
        "permanent_starvation": permanent,
        "service_sequence": service_sequence,
        "full_safety_pass": full_safety,
        "requested_origin_counts": dict(sorted(requested_origins.items())),
        "completed_origin_counts": dict(sorted(completed_origins.items())),
        "service_episodes_sha256": canonical_sha256(episodes),
        "service_episodes": episodes,
    }


def _control_evidence(
    payload: Mapping[str, Any], audit: Mapping[str, Any], auditor: Any
) -> dict[str, Any]:
    events = _rows(payload.get("events"), "payload.events")
    decisions = _rows(payload.get("decisions"), "payload.decisions")
    episodes = _rows(audit.get("service_episodes"), "audit.service_episodes")
    return {
        "payload_sha256": canonical_sha256(payload),
        "ordinary_payload_hashes": auditor.ordinary_payload_hashes(payload),
        "events_sha256": canonical_sha256(events),
        "decisions_sha256": canonical_sha256(decisions),
        "service_episodes_sha256": canonical_sha256(episodes),
        "payload": _portable(payload),
        "audit": dict(audit),
    }


def _validate_frozen_g31_binary_argument(binary: Path) -> Path:
    if not isinstance(binary, Path):
        raise TypeError("G31 binary must be supplied as a Path")
    resolved = binary.resolve(strict=True)
    frozen = G31_BINARY.resolve(strict=True)
    if resolved != frozen:
        raise SelectionError("G31 binary path differs from the frozen Release path")
    if file_sha256(resolved) != FROZEN_SOURCE_HASHES[G31_BINARY]:
        raise SelectionError("frozen G31 binary SHA-256 changed")
    return resolved


def _validate_regenerated_selections_for_execution(
    selections: Mapping[int, Mapping[str, Any]],
) -> None:
    if set(selections) != {1, 2}:
        raise SelectionError("regeneration must return the exact 1x/2x selection set")
    for scale in (1, 2):
        item = _mapping(selections[scale], f"regenerated {scale}x selection")
        _exact_keys(item, {"scale", "workload", "selection"}, f"regenerated {scale}x")
        if item.get("scale") != scale:
            raise SelectionError(f"regenerated {scale}x scale identity changed")
        _validate_workload_evidence(
            scale, _mapping(item.get("workload"), f"regenerated {scale}x workload")
        )
        _validate_selection_evidence(
            scale, _mapping(item.get("selection"), f"regenerated {scale}x selection")
        )


def run_control_selection(
    *,
    executor: Executor | None = None,
    binary: Path = G31_BINARY,
    map_profile_path: Path = PROFILE_PATH,
    source_raw_path: Path = SOURCE_TIMETABLE_PATH,
    manifest_dir: Path = MANIFEST_DIR,
    _test_only: bool = False,
) -> dict[str, Any]:
    """Regenerate/select first, then execute two G31-only omitted/off controls."""

    if CONTROL_EXECUTION_BLOCKED_REASON and not _test_only:
        raise SelectionError(CONTROL_EXECUTION_BLOCKED_REASON)
    binary = _validate_frozen_g31_binary_argument(binary)
    auditor = _v3_auditor()
    dependencies_start = execution_dependency_identity(auditor)
    sources_start = verify_frozen_sources()
    if not sources_start["pass"]:
        raise SelectionError("one or more frozen Nanning/G31 sources changed")
    selected_executor = executor
    if selected_executor is None:
        from czr005.cpp_backend import g4irsf11_event_runtime_from_records

        selected_executor = g4irsf11_event_runtime_from_records
    with tempfile.TemporaryDirectory(prefix="g4irsf32_v3r7_nanning_select_") as name:
        selections = regenerate_and_select(
            Path(name),
            source_raw_path=source_raw_path,
            map_profile_path=map_profile_path,
            manifest_dir=manifest_dir,
        )
        _validate_regenerated_selections_for_execution(selections)
        scales: dict[str, Any] = {}
        for scale in (1, 2):
            item: Mapping[str, Any] | None = None
            request: Mapping[str, Any] | None = None
            potential: Mapping[str, Any] | None = None
            payload: Mapping[str, Any] | None = None
            try:
                item = selections[scale]
                rows = _rows(item["selection"]["selected_rows"], "selected rows")
                request, potential = build_g31_control_request(
                    scale,
                    rows,
                    binary=binary,
                    map_profile_path=map_profile_path,
                    auditor=auditor,
                )
                raw_payload = selected_executor(**request)
                if not isinstance(raw_payload, Mapping):
                    raise SelectionError("G31 executor did not return an object")
                payload = raw_payload
                audit = audit_g31_control_payload(
                    scale=scale,
                    selected_rows=rows,
                    request=request,
                    payload=payload,
                    expected_binary_sha256=FROZEN_SOURCE_HASHES[G31_BINARY],
                    auditor=auditor,
                )
                scales[f"{scale}x"] = {
                    **item,
                    "request": _portable(request),
                    "request_sha256": auditor.request_sha256(request),
                    "ordinary_request_sha256": auditor.ordinary_request_sha256(
                        request
                    ),
                    "profile_sha256": auditor.profile_sha256(request),
                    "potential_sha256": canonical_sha256(
                        request["heuristic_time"]
                    ),
                    "potential_contract": potential,
                    "control": _control_evidence(payload, audit, auditor),
                    "pass": audit["pass"],
                    "status": audit["status"],
                }
            except Exception as error:
                partial: dict[str, Any] = {
                    "scale": scale,
                    "pass": False,
                    "status": NO_GO,
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
                if item is not None:
                    partial.update(_portable(item))
                if request is not None:
                    partial.update(
                        request=_portable(request),
                        request_sha256=auditor.request_sha256(request),
                        ordinary_request_sha256=auditor.ordinary_request_sha256(
                            request
                        ),
                        profile_sha256=auditor.profile_sha256(request),
                        potential_sha256=canonical_sha256(
                            request.get("heuristic_time")
                        ),
                        potential_contract=_portable(potential),
                    )
                if payload is not None:
                    try:
                        payload_sha = canonical_sha256(payload)
                        retained_payload: Any = _portable(payload)
                        serialization_error = None
                    except Exception as payload_error:
                        payload_sha = None
                        retained_payload = None
                        serialization_error = (
                            f"{type(payload_error).__name__}: {payload_error}"
                        )
                    try:
                        ordinary_hashes = auditor.ordinary_payload_hashes(payload)
                        ordinary_hash_error = None
                    except Exception as hash_error:
                        ordinary_hashes = None
                        ordinary_hash_error = f"{type(hash_error).__name__}: {hash_error}"
                    partial["control_partial"] = {
                        "payload_sha256": payload_sha,
                        "ordinary_payload_hashes": ordinary_hashes,
                        "payload": retained_payload,
                        "serialization_error": serialization_error,
                        "ordinary_hash_error": ordinary_hash_error,
                    }
                scales[f"{scale}x"] = partial
                break
    sources_end = verify_frozen_sources()
    dependencies_end = execution_dependency_identity(auditor)
    source_stable = sources_start == sources_end
    dependencies_stable = dependencies_start == dependencies_end
    all_scales_attempted = set(scales) == {"1x", "2x"}
    passed = (
        all_scales_attempted
        and source_stable
        and dependencies_stable
        and all(scales[name]["pass"] for name in ("1x", "2x"))
    )
    zero_event_only = (
        all_scales_attempted
        and any(scales[name]["status"] == NO_EVENT for name in ("1x", "2x"))
        and all(
            scales[name]["status"] in {PASS, NO_EVENT} for name in ("1x", "2x")
        )
    )
    status = (
        PASS
        if passed
        else NO_EVENT
        if source_stable and dependencies_stable and zero_event_only
        else NO_GO
    )
    return with_content_hash(
        {
            "schema": SCHEMA,
            "protocol_id": PROTOCOL_ID,
            "control_revision_id": CONTROL_REVISION_ID,
            "status": status,
            "pass": passed,
            "g32_executed": False,
            "selection_outcome_blind": True,
            "frozen_sources_start": sources_start,
            "frozen_sources_end": sources_end,
            "frozen_sources_unchanged": source_stable,
            "execution_dependencies_start": dependencies_start,
            "execution_dependencies_end": dependencies_end,
            "execution_dependencies_unchanged": dependencies_stable,
            "scales": scales,
        }
    )


def _sha256_text(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise SelectionError(
            f"{label} keys differ: missing={sorted(expected - set(value))}, "
            f"extra={sorted(set(value) - expected)}"
        )


def _load_bound_json(
    path: Path, expected_file_sha256: str, *, label: str
) -> tuple[dict[str, Any], str]:
    if not isinstance(path, Path):
        raise TypeError(f"{label} must be supplied as a Path")
    if not _sha256_text(expected_file_sha256):
        raise SelectionError(f"{label} expected file SHA-256 is invalid")
    resolved = path.resolve(strict=True)
    bound_bytes = resolved.read_bytes()
    actual = hashlib.sha256(bound_bytes).hexdigest()
    if actual != expected_file_sha256:
        raise SelectionError(f"{label} file SHA-256 mismatch")
    loaded = _parse_strict_json_bytes(bound_bytes)
    if not isinstance(loaded, dict):
        raise SelectionError(f"{label} root must be an object")
    return loaded, actual


def _validate_workload_evidence(scale: int, value: Mapping[str, Any]) -> None:
    _exact_keys(
        value,
        {
            "validation",
            "frozen_manifest_sha256",
            "regenerated_manifest_sha256",
            "regenerated_manifest_semantics_sha256",
            "regenerated_raw_sha256",
            "regenerated_canonical_jsonl_sha256",
            "regenerated_ordered_rows_sha256",
        },
        f"{scale}x.workload",
    )
    validation = _mapping(value.get("validation"), f"{scale}x.workload.validation")
    expected_raw, expected_segments = EXPECTED_SCALE_COUNTS[scale]
    expected_external, expected_local = EXPECTED_POOL_COUNTS[scale]
    expected_pools = EXPECTED_POOL_HASHES[scale]
    expected_regeneration = EXPECTED_REGENERATION_HASHES[scale]
    expected_checks = {
        "schema",
        "status",
        "scale",
        "map_id",
        "raw_count",
        "segment_count",
        "storage_pair",
        "frozen_manifest_semantics",
        "manifest_invariants",
    }
    checks = _mapping(validation.get("checks"), f"{scale}x.workload.checks")
    expected_values = {
        "pass": True,
        "raw_task_count": expected_raw,
        "segment_count": expected_segments,
        "external_pool_count": expected_external,
        "local_pool_count": expected_local,
        "external_pool_sha256": expected_pools[0],
        "local_pool_sha256": expected_pools[1],
        "ordered_rows_sha256": expected_regeneration["ordered_rows"],
    }
    if (
        set(checks) != expected_checks
        or not all(checks.get(name) is True for name in expected_checks)
        or any(validation.get(key) != expected for key, expected in expected_values.items())
        or value.get("frozen_manifest_sha256")
        != FROZEN_SOURCE_HASHES[MANIFEST_DIR / f"nanning_{scale}x_manifest.json"]
        or not _sha256_text(value.get("regenerated_manifest_sha256"))
        or value.get("regenerated_manifest_semantics_sha256")
        != expected_regeneration["manifest_semantics"]
        or value.get("regenerated_raw_sha256") != expected_regeneration["raw"]
        or value.get("regenerated_canonical_jsonl_sha256")
        != expected_regeneration["canonical_jsonl"]
        or value.get("regenerated_ordered_rows_sha256")
        != expected_regeneration["ordered_rows"]
    ):
        raise SelectionError(f"{scale}x regenerated workload evidence changed")


def _validate_selection_evidence(
    scale: int, value: Mapping[str, Any]
) -> list[Mapping[str, Any]]:
    _exact_keys(
        value,
        {
            "selector_algorithm_id",
            "rule",
            "outcome_fields_read",
            "external_first_entry_offset_seconds",
            "node49_service_seconds",
            "source_retry_interval_seconds",
            "external_53_to_49_travel_seconds",
            "candidate_count",
            "candidate_set_sha256",
            "external_release",
            "external_release_multiplicity",
            "external_prefix_count",
            "external_commit_rank",
            "predicted_external_commit_time",
            "first_local_release",
            "first_local_segment_id",
            "first_local_task_id",
            "second_local_release",
            "second_local_segment_id",
            "second_local_task_id",
            "local_release_gap_seconds",
            "external_selected_count",
            "local_selected_count",
            "selected_segment_count",
            "external_release_histogram_sha256",
            "selected_segment_ids_sha256",
            "original_selected_rows_sha256",
            "selected_rows_sha256",
            "projection_identity_sha256",
            "original_selected_rows",
            "selected_rows",
            "projection_identity",
        },
        f"{scale}x.selection",
    )
    original = _rows(
        value.get("original_selected_rows"),
        f"{scale}x.selection.original_selected_rows",
    )
    projected = _rows(value.get("selected_rows"), f"{scale}x.selection.selected_rows")
    identity = _rows(
        value.get("projection_identity"), f"{scale}x.selection.projection_identity"
    )
    expected_hashes = EXPECTED_SELECTION_HASHES[scale]
    hashes = {
        "external_release_histogram": value.get(
            "external_release_histogram_sha256"
        ),
        "candidate_set": value.get("candidate_set_sha256"),
        "original_rows": canonical_sha256(original),
        "projected_rows": canonical_sha256(projected),
        "projection_identity": canonical_sha256(identity),
        "selected_segment_ids": canonical_sha256(
            [str(row.get("segment_id")) for row in original]
        ),
    }
    recorded = {
        "external_release_histogram": value.get(
            "external_release_histogram_sha256"
        ),
        "candidate_set": value.get("candidate_set_sha256"),
        "original_rows": value.get("original_selected_rows_sha256"),
        "projected_rows": value.get("selected_rows_sha256"),
        "projection_identity": value.get("projection_identity_sha256"),
        "selected_segment_ids": value.get("selected_segment_ids_sha256"),
    }
    reprojection, reidentity = project_selected_rows(original)
    expected_counts = EXPECTED_SELECTION_COUNTS[scale]
    external_release = expected_counts["external_release"]
    external = [
        row
        for row in original
        if row.get("start") == EXTERNAL_START
        and row.get("leg") == "storage_out"
    ]
    local = sorted(
        (row for row in original if row.get("start") == LOCAL_START),
        key=lambda row: (
            _finite(row.get("pass_time"), "local.pass_time"),
            str(row.get("segment_id")),
            _integer(row.get("task_id"), "local.task_id"),
        ),
    )
    canonical_original = sorted(
        (dict(row) for row in original),
        key=lambda row: (
            _finite(row.get("pass_time"), "selected.pass_time"),
            str(row.get("segment_id")),
            _integer(row.get("task_id"), "selected.task_id"),
        ),
    )
    if len(local) != 2:
        raise SelectionError(f"{scale}x frozen selection must contain two local rows")
    first_local, second_local = local
    first_release = _finite(
        first_local.get("pass_time"), "first local pass_time"
    )
    second_release = _finite(
        second_local.get("pass_time"), "second local pass_time"
    )
    expected_rank = max(
        0,
        math.ceil(
            (
                second_release
                - external_release
                - EXTERNAL_FIRST_ENTRY_OFFSET_SECONDS
            )
            / NODE49_SERVICE_SECONDS
        ),
    )
    expected_commit = (
        external_release
        + EXTERNAL_FIRST_ENTRY_OFFSET_SECONDS
        + expected_rank * NODE49_SERVICE_SECONDS
    )
    second_local_service_complete = (
        max(
            second_release + SOURCE_RETRY_INTERVAL_SECONDS,
            first_release + NODE49_SERVICE_SECONDS,
        )
        + NODE49_SERVICE_SECONDS
    )
    release_semantics = (
        all(
            _finite(row.get("pass_time"), "external.pass_time")
            == external_release
            and str(row.get("segment_id", "")).endswith(":storage_out")
            for row in external
        )
        and AUDIT_EPSILON
        < second_release - first_release
        < NODE49_SERVICE_SECONDS - AUDIT_EPSILON
        and second_local_service_complete
        <= external_release
        + EXTERNAL_FIRST_ENTRY_OFFSET_SECONDS
        + EXTERNAL_53_TO_49_TRAVEL_SECONDS
        - AUDIT_EPSILON
        and second_release + AUDIT_EPSILON < expected_commit
        < first_release + NODE49_SERVICE_SECONDS - AUDIT_EPSILON
        and expected_commit
        < external_release
        + EXTERNAL_FIRST_ENTRY_OFFSET_SECONDS
        + EXTERNAL_53_TO_49_TRAVEL_SECONDS
        - AUDIT_EPSILON
    )
    if (
        value.get("selector_algorithm_id") != SELECTOR_ALGORITHM_ID
        or value.get("rule") != SELECTOR_RULE
        or value.get("outcome_fields_read") is not False
        or value.get("external_first_entry_offset_seconds")
        != EXTERNAL_FIRST_ENTRY_OFFSET_SECONDS
        or value.get("node49_service_seconds") != NODE49_SERVICE_SECONDS
        or value.get("source_retry_interval_seconds")
        != SOURCE_RETRY_INTERVAL_SECONDS
        or value.get("external_53_to_49_travel_seconds")
        != EXTERNAL_53_TO_49_TRAVEL_SECONDS
        or value.get("candidate_count") != expected_counts["candidate_count"]
        or value.get("external_release") != external_release
        or value.get("external_release_multiplicity")
        != expected_counts["external_release_multiplicity"]
        or value.get("external_prefix_count") != expected_counts["external"]
        or value.get("external_commit_rank") != expected_rank
        or value.get("external_commit_rank")
        != expected_counts["external_commit_rank"]
        or value.get("predicted_external_commit_time") != expected_commit
        or value.get("predicted_external_commit_time")
        != expected_counts["predicted_external_commit_time"]
        or value.get("first_local_release") != first_release
        or value.get("first_local_release")
        != expected_counts["first_local_release"]
        or value.get("first_local_segment_id")
        != first_local.get("segment_id")
        or value.get("first_local_task_id") != first_local.get("task_id")
        or value.get("second_local_release") != second_release
        or value.get("second_local_release")
        != expected_counts["second_local_release"]
        or value.get("second_local_segment_id")
        != second_local.get("segment_id")
        or value.get("second_local_task_id") != second_local.get("task_id")
        or value.get("local_release_gap_seconds")
        != second_release - first_release
        or value.get("external_selected_count") != expected_counts["external"]
        or value.get("local_selected_count") != expected_counts["local"]
        or value.get("selected_segment_count") != expected_counts["total"]
        or len(external) != expected_counts["external"]
        or len(local) != expected_counts["local"]
        or len(original) != expected_counts["total"]
        or len(projected) != expected_counts["total"]
        or len(identity) != expected_counts["total"]
        or original != canonical_original
        or not release_semantics
        or hashes != recorded
        or hashes != expected_hashes
        or reprojection != projected
        or reidentity != identity
    ):
        raise SelectionError(f"{scale}x frozen selection/projection changed")
    return projected


def _validate_control_artifact_mapping(
    value: Mapping[str, Any], *, auditor: Any | None = None
) -> dict[str, Any]:
    """Deep validator for tests/internal use; formal shadow loading remains Path-only."""

    loaded = deepcopy(dict(value))
    _exact_keys(
        loaded,
        {
            "schema",
            "protocol_id",
            "control_revision_id",
            "status",
            "pass",
            "g32_executed",
            "selection_outcome_blind",
            "frozen_sources_start",
            "frozen_sources_end",
            "frozen_sources_unchanged",
            "execution_dependencies_start",
            "execution_dependencies_end",
            "execution_dependencies_unchanged",
            "scales",
            "artifact_content_sha256",
        },
        "control artifact",
    )
    verify_content_hash(loaded)
    selected_auditor = auditor or _v3_auditor()
    recorded_sources_start = _mapping(
        loaded.get("frozen_sources_start"), "control.frozen_sources_start"
    )
    recorded_sources_end = _mapping(
        loaded.get("frozen_sources_end"), "control.frozen_sources_end"
    )
    recorded_dependencies_start = _mapping(
        loaded.get("execution_dependencies_start"),
        "control.execution_dependencies_start",
    )
    recorded_dependencies_end = _mapping(
        loaded.get("execution_dependencies_end"),
        "control.execution_dependencies_end",
    )
    if (
        loaded.get("schema") != SCHEMA
        or loaded.get("protocol_id") != PROTOCOL_ID
        or loaded.get("control_revision_id") != CONTROL_REVISION_ID
        or loaded.get("status") != PASS
        or loaded.get("pass") is not True
        or loaded.get("g32_executed") is not False
        or loaded.get("selection_outcome_blind") is not True
        or loaded.get("frozen_sources_unchanged") is not True
        or recorded_sources_start != recorded_sources_end
        or recorded_sources_start.get("pass") is not True
        or loaded.get("execution_dependencies_unchanged") is not True
        or recorded_dependencies_start != recorded_dependencies_end
    ):
        raise SelectionError("control source/dependency checkpoints are not exact")

    scales = _mapping(loaded.get("scales"), "control.scales")
    if set(scales) != {"1x", "2x"}:
        raise SelectionError("control artifact must contain exact 1x/2x scales")
    for scale_number, name in ((1, "1x"), (2, "2x")):
        scale = _mapping(scales[name], f"control.scales.{name}")
        _exact_keys(
            scale,
            {
                "scale",
                "workload",
                "selection",
                "request",
                "request_sha256",
                "ordinary_request_sha256",
                "profile_sha256",
                "potential_sha256",
                "potential_contract",
                "control",
                "pass",
                "status",
            },
            f"control.scales.{name}",
        )
        if scale.get("scale") != scale_number:
            raise SelectionError(f"{name} scale identity changed")
        _validate_workload_evidence(
            scale_number, _mapping(scale.get("workload"), f"{name}.workload")
        )
        rows = _validate_selection_evidence(
            scale_number, _mapping(scale.get("selection"), f"{name}.selection")
        )
        request = _mapping(scale.get("request"), f"{name}.request")
        rebuilt_request, rebuilt_potential = build_g31_control_request(
            scale_number,
            rows,
            binary=G31_BINARY,
            map_profile_path=PROFILE_PATH,
            auditor=selected_auditor,
        )
        request_hashes = {
            "request_sha256": selected_auditor.request_sha256(request),
            "ordinary_request_sha256": selected_auditor.ordinary_request_sha256(
                request
            ),
            "profile_sha256": selected_auditor.profile_sha256(request),
            "potential_sha256": canonical_sha256(request.get("heuristic_time")),
        }
        if (
            _portable(request) != _portable(rebuilt_request)
            or _portable(scale.get("potential_contract"))
            != _portable(rebuilt_potential)
            or any(scale.get(key) != digest for key, digest in request_hashes.items())
        ):
            raise SelectionError(f"{name} request/profile/potential evidence changed")

        control = _mapping(scale.get("control"), f"{name}.control")
        _exact_keys(
            control,
            {
                "payload_sha256",
                "ordinary_payload_hashes",
                "events_sha256",
                "decisions_sha256",
                "service_episodes_sha256",
                "payload",
                "audit",
            },
            f"{name}.control",
        )
        payload = _mapping(control.get("payload"), f"{name}.control.payload")
        recorded_audit = _mapping(control.get("audit"), f"{name}.control.audit")
        recorded_checks = _mapping(
            recorded_audit.get("checks"), f"{name}.control.audit.checks"
        )
        if (
            recorded_audit.get("pass") is not True
            or recorded_audit.get("status") != PASS
            or _integer(
                recorded_audit.get("qualifying_event_count"),
                f"{name}.control.audit.qualifying_event_count",
            )
            < 1
            or not recorded_checks
            or any(check is not True for check in recorded_checks.values())
        ):
            raise SelectionError(f"{name} recorded control audit is not passing")
        _reject_g32_contamination(
            request,
            payload,
            expected_binary_sha256=FROZEN_SOURCE_HASHES[G31_BINARY],
            auditor=selected_auditor,
        )
        recomputed_audit = audit_g31_control_payload(
            scale=scale_number,
            selected_rows=rows,
            request=request,
            payload=payload,
            expected_binary_sha256=FROZEN_SOURCE_HASHES[G31_BINARY],
            auditor=selected_auditor,
        )
        if (
            recomputed_audit.get("pass") is not True
            or recomputed_audit.get("status") != PASS
        ):
            raise SelectionError(f"{name} control payload failed current deep replay")
        recomputed_control = _control_evidence(
            payload, recomputed_audit, selected_auditor
        )
        recorded_non_audit = {
            key: item for key, item in control.items() if key != "audit"
        }
        recomputed_non_audit = {
            key: item for key, item in recomputed_control.items() if key != "audit"
        }
        if (
            _portable(recorded_non_audit) != _portable(recomputed_non_audit)
            or scale.get("pass") is not True
            or scale.get("status") != PASS
        ):
            raise SelectionError(f"{name} control payload/audit failed deep replay")
    return loaded


def load_and_validate_control_artifact(
    value: Path,
    *,
    expected_file_sha256: str,
    auditor: Any | None = None,
) -> tuple[dict[str, Any], str]:
    if not isinstance(value, Path):
        raise TypeError("control artifact must be supplied as a Path")
    if value.resolve() != OUTPUT_PATH.resolve():
        raise SelectionError("control artifact is not at the registered output path")
    loaded, file_hash = _load_bound_json(
        value, expected_file_sha256, label="control artifact"
    )
    return _validate_control_artifact_mapping(loaded, auditor=auditor), file_hash


def _validate_gate_vector(
    value: Any, expected_names: set[str], label: str
) -> dict[str, Mapping[str, Any]]:
    gates = _rows(value, label)
    by_name: dict[str, Mapping[str, Any]] = {}
    for index, gate in enumerate(gates):
        _exact_keys(gate, {"name", "pass", "evidence"}, f"{label}[{index}]")
        name = gate.get("name")
        if not isinstance(name, str) or not name or name in by_name:
            raise SelectionError(f"{label} has an invalid/duplicate gate name")
        if not isinstance(gate.get("pass"), bool):
            raise SelectionError(f"{label}.{name}.pass must be bool")
        by_name[name] = gate
    if set(by_name) != expected_names:
        raise SelectionError(f"{label} has a non-exact gate set")
    return by_name


def _validate_boolean_checks(
    value: Any, expected_names: set[str], label: str
) -> Mapping[str, bool]:
    checks = _mapping(value, label)
    if set(checks) != expected_names or any(
        not isinstance(item, bool) for item in checks.values()
    ):
        raise SelectionError(f"{label} has a non-exact boolean check set")
    return checks  # type: ignore[return-value]


def _validate_legacy_wait_evidence(value: Any, label: str) -> None:
    audit = _mapping(value, label)
    _exact_keys(
        audit,
        {
            "pass",
            "threshold_seconds",
            "bag_count",
            "native_summary_count",
            "recomputed_count",
            "runtime_ids_contiguous",
            "native_flags_match",
            "ordered_identities",
            "ordered_waits",
            "ordered_flags",
            "ordered_recomputed_flags",
            "per_origin",
            "maximum_wait",
            "ordered_vector_sha256",
        },
        label,
    )
    identities = audit.get("ordered_identities")
    waits = audit.get("ordered_waits")
    native_flags = audit.get("ordered_flags")
    recomputed_flags = audit.get("ordered_recomputed_flags")
    if (
        not isinstance(identities, list)
        or not isinstance(waits, list)
        or not isinstance(native_flags, list)
        or not isinstance(recomputed_flags, list)
    ):
        raise SelectionError(f"{label} vectors must be arrays")
    count = _integer(audit.get("bag_count"), f"{label}.bag_count")
    threshold = _finite(audit.get("threshold_seconds"), f"{label}.threshold")
    if count <= 0 or not (
        len(identities) == len(waits) == len(native_flags) == len(recomputed_flags) == count
    ):
        raise SelectionError(f"{label} vector cardinality is invalid")
    records: list[dict[str, Any]] = []
    for index, (identity, wait, native, recomputed) in enumerate(
        zip(identities, waits, native_flags, recomputed_flags)
    ):
        if not isinstance(identity, list) or len(identity) != 4:
            raise SelectionError(f"{label}.ordered_identities[{index}] is invalid")
        runtime_id = _integer(identity[0], f"{label}.runtime_id")
        segment_id, task_id, source = identity[1], identity[2], identity[3]
        if (
            not isinstance(segment_id, str)
            or not segment_id
            or isinstance(task_id, bool)
            or not isinstance(task_id, int)
            or not isinstance(source, str)
            or not source
            or not isinstance(native, bool)
            or not isinstance(recomputed, bool)
        ):
            raise SelectionError(f"{label} identity/flag vector is invalid")
        numeric_wait = _finite(wait, f"{label}.ordered_waits[{index}]")
        if recomputed is not (numeric_wait > threshold):
            raise SelectionError(f"{label} recomputed wait flag changed")
        records.append(
            {
                "runtime_bag_id": runtime_id,
                "segment_id": segment_id,
                "task_id": task_id,
                "source": source,
                "total_local_wait": numeric_wait,
                "native_starved": native,
                "recomputed_wait_over_120": recomputed,
            }
        )
    contiguous = [row["runtime_bag_id"] for row in records] == list(range(count))
    flags_match = all(
        row["native_starved"] is row["recomputed_wait_over_120"] for row in records
    )
    per_origin: dict[str, dict[str, Any]] = {}
    for source in sorted({str(row["source"]) for row in records}):
        selected = [row for row in records if row["source"] == source]
        per_origin[source] = {
            "bag_count": len(selected),
            "wait_over_120_count": sum(
                row["recomputed_wait_over_120"] for row in selected
            ),
            "maximum_wait": max(row["total_local_wait"] for row in selected),
        }
    recomputed_count = sum(row["recomputed_wait_over_120"] for row in records)
    passed = (
        contiguous
        and flags_match
        and _integer(audit.get("native_summary_count"), f"{label}.native_count")
        == recomputed_count
    )
    if (
        audit.get("runtime_ids_contiguous") is not contiguous
        or audit.get("native_flags_match") is not flags_match
        or audit.get("recomputed_count") != recomputed_count
        or audit.get("per_origin") != per_origin
        or audit.get("maximum_wait") != max(row["total_local_wait"] for row in records)
        or audit.get("ordered_vector_sha256") != canonical_sha256(records)
        or audit.get("pass") is not passed
    ):
        raise SelectionError(f"{label} vector/check replay failed")


def _validate_service_sequence_evidence(
    value: Any,
    *,
    bag_count: int,
    exact_l: bool,
    expected_exact_node: int | None,
    service_seconds: float | None,
    label: str,
) -> list[dict[str, Any]]:
    exact_node = _expected_exact_service_node(
        exact_l=exact_l,
        value=expected_exact_node,
        label=label,
    )
    audit = _mapping(value, label)
    _exact_keys(
        audit,
        {
            "pass",
            "exact_L_applicable",
            "sequence_count",
            "evidence_vector_limit",
            "evidence_vector_bounded",
            "bag_conservation",
            "origin_conservation",
            "no_overlap",
            "requested_origin_counts",
            "service_origin_counts",
            "ordered_service_episodes",
            "ordered_runtime_bag_ids",
            "origin_sequence",
            "sequence_sha256",
            "origin_sequence_sha256",
            "maximum_consecutive_origin_run",
        },
        label,
    )
    episodes = _rows(audit.get("ordered_service_episodes"), f"{label}.episodes")
    normalized: list[dict[str, Any]] = []
    for index, episode in enumerate(episodes):
        _exact_keys(
            episode,
            {
                "runtime_bag_id",
                "source",
                "node",
                "start",
                "complete",
                "completion_event_seq",
            },
            f"{label}.episodes[{index}]",
        )
        source = episode.get("source")
        if not isinstance(source, str) or not source:
            raise SelectionError(f"{label} episode source is invalid")
        normalized.append(
            {
                "runtime_bag_id": _integer(
                    episode.get("runtime_bag_id"), f"{label}.runtime_bag_id"
                ),
                "source": source,
                "node": _integer(episode.get("node"), f"{label}.node"),
                "start": _finite(episode.get("start"), f"{label}.start"),
                "complete": _finite(episode.get("complete"), f"{label}.complete"),
                "completion_event_seq": _integer(
                    episode.get("completion_event_seq"), f"{label}.event_seq"
                ),
            }
        )
    ordered = sorted(
        normalized,
        key=lambda row: (
            row["start"],
            row["complete"],
            row["completion_event_seq"],
            row["runtime_bag_id"],
        ),
    )
    if normalized != ordered:
        raise SelectionError(f"{label} service sequence is not canonical")
    if any(
        row["runtime_bag_id"] < 0
        or row["node"] < 0
        or (exact_node is not None and row["node"] != exact_node)
        or row["completion_event_seq"] <= 0
        or row["complete"] < row["start"]
        or (
            service_seconds is not None
            and not math.isclose(
                row["complete"] - row["start"],
                service_seconds,
                rel_tol=0.0,
                abs_tol=AUDIT_EPSILON,
            )
        )
        for row in normalized
    ) or len({row["completion_event_seq"] for row in normalized}) != len(normalized):
        raise SelectionError(f"{label} service duration/event identity changed")
    bag_ids = [row["runtime_bag_id"] for row in normalized]
    origins = [row["source"] for row in normalized]
    requested = _mapping(
        audit.get("requested_origin_counts"), f"{label}.requested origins"
    )
    served = dict(sorted(Counter(origins).items()))
    if any(
        not isinstance(name, str)
        or not name
        or isinstance(count, bool)
        or not isinstance(count, int)
        or count < 0
        for name, count in requested.items()
    ):
        raise SelectionError(f"{label} requested origin counts are invalid")
    requested_sorted = dict(sorted(requested.items()))
    by_node: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in normalized:
        by_node[int(row["node"])].append(row)
    no_overlap = all(
        float(right["start"]) >= float(left["complete"]) - AUDIT_EPSILON
        for rows_at_node in by_node.values()
        for left, right in zip(rows_at_node, rows_at_node[1:])
    )
    bag_conservation = len({(row["runtime_bag_id"], row["node"]) for row in normalized}) == len(normalized)
    if exact_l:
        bag_conservation = (
            bag_conservation
            and len(bag_ids) == len(set(bag_ids)) == bag_count
        )
    origin_conservation = not exact_l or served == requested_sorted
    vector_limit = bag_count * max(1, len(by_node))
    vector_bounded = len(normalized) <= vector_limit
    maximum_run = 0
    prior: str | None = None
    run = 0
    for origin in origins:
        run = run + 1 if origin == prior else 1
        prior = origin
        maximum_run = max(maximum_run, run)
    passed = bool(normalized) and all(
        (bag_conservation, origin_conservation, no_overlap, vector_bounded)
    )
    if (
        audit.get("exact_L_applicable") is not exact_l
        or audit.get("sequence_count") != len(normalized)
        or audit.get("evidence_vector_limit") != vector_limit
        or audit.get("evidence_vector_bounded") is not vector_bounded
        or audit.get("bag_conservation") is not bag_conservation
        or audit.get("origin_conservation") is not origin_conservation
        or audit.get("no_overlap") is not no_overlap
        or requested_sorted != requested
        or sum(requested_sorted.values()) != bag_count
        or audit.get("service_origin_counts") != served
        or audit.get("ordered_runtime_bag_ids") != bag_ids
        or audit.get("origin_sequence") != origins
        or audit.get("sequence_sha256") != canonical_sha256(normalized)
        or audit.get("origin_sequence_sha256") != canonical_sha256(origins)
        or audit.get("maximum_consecutive_origin_run") != maximum_run
        or audit.get("pass") is not passed
    ):
        raise SelectionError(f"{label} sequence/vector replay failed")
    return normalized


def _validate_permanent_evidence(
    value: Any, *, bag_count: int, exact_l: bool, label: str
) -> dict[str, Any]:
    audit = _mapping(value, label)
    _exact_keys(
        audit,
        {
            "pass",
            "checks",
            "requested_origin_counts",
            "completed_origin_counts",
            "late_runtime_bag_ids",
            "bag_completion_vector",
            "bag_completion_vector_sha256",
            "junction_final_vector",
            "junction_final_vector_sha256",
            "lifecycle_final_state_vector",
            "lifecycle_final_state_vector_sha256",
            "lifecycle_count_checks",
            "lifecycle_state_counts",
            "recomputable_vector_count",
            "recomputable_vector_limit",
            "merge_request_accounting",
            "historical_last_lifecycle_state_counts",
            "junction_count",
            "expected_junction_count",
            "configured_junction_count",
        },
        label,
    )
    checks = _validate_boolean_checks(
        audit.get("checks"), PERMANENT_CHECK_NAMES, f"{label}.checks"
    )
    lifecycle_count_checks = _validate_boolean_checks(
        audit.get("lifecycle_count_checks"),
        {
            "transition_count_exact",
            "stored_count_exact",
            "dropped_count_zero",
            "request_transition_count_exact",
            "issued_transition_count_exact",
            "prepared_transition_count_exact",
            "committed_transition_count_exact",
            "historical_commit_transition_conservation",
            "current_committed_count_exact",
            "consumed_transition_count_exact",
            "post_commit_revoked_count_exact",
            "post_commit_expired_count_exact",
            "post_commit_rollback_count_exact",
            "terminal_state_counts_exact",
        },
        f"{label}.lifecycle_count_checks",
    )
    completion = _rows(
        audit.get("bag_completion_vector"), f"{label}.bag_completion_vector"
    )
    junctions = _rows(
        audit.get("junction_final_vector"), f"{label}.junction_final_vector"
    )
    lifecycle = _rows(
        audit.get("lifecycle_final_state_vector"),
        f"{label}.lifecycle_final_state_vector",
    )
    if len(completion) != bag_count:
        raise SelectionError(f"{label} bag completion cardinality changed")
    runtime_ids: list[int] = []
    completed_origins: Counter[str] = Counter()
    late: list[int] = []
    for index, row in enumerate(completion):
        _exact_keys(
            row,
            {
                "runtime_bag_id",
                "source",
                "goal",
                "completed",
                "finish_time",
                "deadline",
                "L_service_count",
            },
            f"{label}.bag_completion_vector[{index}]",
        )
        runtime_id = _integer(row.get("runtime_bag_id"), f"{label}.runtime_id")
        source = row.get("source")
        if not isinstance(source, str) or not source or not isinstance(
            row.get("completed"), bool
        ):
            raise SelectionError(f"{label} completion identity is invalid")
        finish = _finite(row.get("finish_time"), f"{label}.finish_time")
        deadline = _finite(row.get("deadline"), f"{label}.deadline")
        goal = _integer(row.get("goal"), f"{label}.goal")
        service_count = _integer(
            row.get("L_service_count"), f"{label}.L_service_count"
        )
        if goal < 0:
            raise SelectionError(f"{label} completion goal is invalid")
        runtime_ids.append(runtime_id)
        if row["completed"]:
            completed_origins[source] += 1
        if finish > deadline + AUDIT_EPSILON:
            late.append(runtime_id)
        if exact_l and service_count != 1:
            raise SelectionError(f"{label} L-service vector is not exact")
    if runtime_ids != list(range(bag_count)):
        raise SelectionError(f"{label} completion runtime IDs are not contiguous")
    for index, row in enumerate(junctions):
        _exact_keys(
            row,
            {
                "node",
                "service_reservation_count",
                "final_source_queue_length",
                "final_junction_queue_length",
                "scheduled_incoming",
            },
            f"{label}.junction_final_vector[{index}]",
        )
        node = _integer(row.get("node"), f"{label}.junction.node")
        counts = [
            _integer(row.get(key), f"{label}.junction.{key}")
            for key in (
                "service_reservation_count",
                "final_source_queue_length",
                "final_junction_queue_length",
                "scheduled_incoming",
            )
        ]
        if node < 0 or any(count < 0 for count in counts):
            raise SelectionError(f"{label} junction vector is negative")
    junction_nodes = [row["node"] for row in junctions]
    if junction_nodes != sorted(junction_nodes) or len(set(junction_nodes)) != len(
        junction_nodes
    ):
        raise SelectionError(f"{label} junction vector is not ordered")
    lifecycle_states: Counter[str] = Counter()
    lifecycle_identities: list[tuple[int, int, int, int, int]] = []
    for index, row in enumerate(lifecycle):
        _exact_keys(
            row,
            {
                "request_id",
                "lineage",
                "request_generation",
                "junction_queue_generation",
                "destination_node",
                "state",
            },
            f"{label}.lifecycle_final_state_vector[{index}]",
        )
        identity = tuple(
            _integer(row.get(key), f"{label}.lifecycle.{key}")
            for key in (
            "request_id",
            "lineage",
            "request_generation",
            "junction_queue_generation",
            "destination_node",
            )
        )
        lifecycle_identities.append(identity)
        state = row.get("state")
        if state not in LIFECYCLE_FINAL_STATES:
            raise SelectionError(f"{label} lifecycle state is invalid")
        lifecycle_states[state] += 1
    accounting = _mapping(
        audit.get("merge_request_accounting"), f"{label}.merge accounting"
    )
    _exact_keys(
        accounting,
        {
            "request_count",
            "committed_count",
            "terminal_count",
            "outstanding_count",
            "final_active_unconsumed",
            "final_consumed_count",
            "final_committed_active_count",
            "final_terminal_count",
            "final_outstanding_count",
        },
        f"{label}.merge accounting",
    )
    if any(
        _integer(item, f"{label}.merge accounting") < 0
        for item in accounting.values()
    ):
        raise SelectionError(f"{label} merge accounting is negative")
    final_terminal = sum(
        lifecycle_states[name]
        for name in (
            "EXPIRED",
            "REVOKED_FAULT",
            "REVOKED_STALE_STATE",
            "REVOKED_REPLAN_CURRENT_EDGE",
            "ROLLED_BACK",
        )
    )
    expected_accounting = {
        "final_consumed_count": lifecycle_states["CONSUMED"],
        "final_committed_active_count": lifecycle_states["COMMITTED"],
        "final_terminal_count": final_terminal,
        "final_outstanding_count": lifecycle_states["REQUESTED"],
    }
    requested_origins = _mapping(
        audit.get("requested_origin_counts"), f"{label}.requested origins"
    )
    if any(
        not isinstance(count, int) or isinstance(count, bool) or count < 0
        for count in requested_origins.values()
    ):
        raise SelectionError(f"{label} requested origin counts are invalid")
    expected_junction_count = _integer(
        audit.get("expected_junction_count"), f"{label}.expected junctions"
    )
    configured_junction_count = _integer(
        audit.get("configured_junction_count"), f"{label}.configured junctions"
    )
    vector_count = len(completion) + len(junctions) + len(lifecycle)
    vector_limit = (
        bag_count + configured_junction_count + int(accounting["request_count"])
    )
    historical = _mapping(
        audit.get("historical_last_lifecycle_state_counts"),
        f"{label}.historical lifecycle counts",
    )
    lifecycle_transition_counts = _mapping(
        audit.get("lifecycle_state_counts"), f"{label}.lifecycle state counts"
    )
    if any(
        not isinstance(name, str)
        or not name
        or not isinstance(count, int)
        or isinstance(count, bool)
        or count < 0
        for name, count in [
            *historical.items(),
            *lifecycle_transition_counts.items(),
        ]
    ):
        raise SelectionError(f"{label} lifecycle count evidence is invalid")
    all_completed = all(row.get("completed") is True for row in completion)
    l_service_once = not exact_l or all(
        row.get("L_service_count") == 1 for row in completion
    )
    queues_empty = all(
        row.get("final_source_queue_length") == 0
        and row.get("final_junction_queue_length") == 0
        for row in junctions
    )
    incoming_zero = all(row.get("scheduled_incoming") == 0 for row in junctions)
    active_nodes_valid = 0 < expected_junction_count <= configured_junction_count
    junction_state_valid = (
        active_nodes_valid
        and expected_junction_count <= len(junctions) <= configured_junction_count
    )
    final_invalid = lifecycle_states["ISSUED"] + lifecycle_states["PREPARED"]
    recomputed_checks = {
        "completed_once": all_completed,
        "deadline_complete": not late,
        "L_service_once_where_applicable": l_service_once,
        "active_node_identity_valid": active_nodes_valid,
        "active_junction_state_exact": junction_state_valid,
        "final_queues_empty": junction_state_valid and queues_empty,
        "final_scheduled_incoming_zero": junction_state_valid and incoming_zero,
        "lifecycle_final_state_complete": len(lifecycle) == accounting["request_count"]
        and final_invalid == 0,
        "lifecycle_consumed_committed_exact": lifecycle_states["CONSUMED"]
        + lifecycle_states["COMMITTED"]
        == accounting["committed_count"],
        "lifecycle_terminal_exact": final_terminal == accounting["terminal_count"],
        "lifecycle_outstanding_exact": lifecycle_states["REQUESTED"]
        == accounting["outstanding_count"],
        "lifecycle_active_exact": lifecycle_states["COMMITTED"]
        == accounting["final_active_unconsumed"],
        "merge_request_conservation": accounting["request_count"]
        == accounting["committed_count"]
        + accounting["terminal_count"]
        + accounting["outstanding_count"],
        "final_merge_pending_zero": accounting["outstanding_count"] == 0
        and lifecycle_states["REQUESTED"] == 0,
        "merge_active_unconsumed_zero": accounting["final_active_unconsumed"] == 0
        and lifecycle_states["COMMITTED"] == 0,
        "mixed_origin_request_completion": set(requested_origins)
        != {"local", "external"}
        or dict(sorted(completed_origins.items())) == requested_origins,
        "recomputable_vectors_bounded": vector_count <= vector_limit,
    }
    necessary_raw_conditions = (
        all_completed,
        queues_empty,
        incoming_zero,
        junction_state_valid,
    )
    if (
        audit.get("bag_completion_vector_sha256") != canonical_sha256(completion)
        or audit.get("junction_final_vector_sha256") != canonical_sha256(junctions)
        or audit.get("lifecycle_final_state_vector_sha256")
        != canonical_sha256(lifecycle)
        or audit.get("late_runtime_bag_ids") != late
        or audit.get("completed_origin_counts")
        != dict(sorted(completed_origins.items()))
        or sum(requested_origins.values()) != bag_count
        or audit.get("junction_count") != len(junctions)
        or configured_junction_count < expected_junction_count
        or audit.get("recomputable_vector_count") != vector_count
        or audit.get("recomputable_vector_limit") != vector_limit
        or any(accounting.get(key) != item for key, item in expected_accounting.items())
        or accounting.get("request_count") != len(lifecycle)
        or lifecycle_identities != sorted(lifecycle_identities)
        or len(set(lifecycle_identities)) != len(lifecycle_identities)
        or accounting.get("request_count")
        != accounting.get("committed_count")
        + accounting.get("terminal_count")
        + accounting.get("outstanding_count")
        or historical != dict(sorted(lifecycle_states.items()))
        or any(
            checks[name] is not passed
            for name, passed in recomputed_checks.items()
        )
        or not all(recomputed_checks.values())
        or not all(necessary_raw_conditions)
        or not all(lifecycle_count_checks.values())
        or audit.get("pass") is not all(checks.values())
        or not all(checks.values())
    ):
        raise SelectionError(f"{label} permanent-starvation replay failed")
    return {
        "completion": completion,
        "junctions": junctions,
        "lifecycle": lifecycle,
        "requested_origins": dict(requested_origins),
        "completed_origins": dict(sorted(completed_origins.items())),
    }


def _validate_population_identity_evidence(value: Any, label: str) -> None:
    audit = _mapping(value, label)
    _exact_keys(
        audit,
        {
            "pass",
            "exact_ordered_manifest",
            "unique_segment_and_segment_task_identity",
            "event_sequence_identity_valid",
            "shadow_row_bag_links",
            "shadow_row_source_queue_winner",
            "shadow_row_local_telemetry_exact",
            "expected_sha256",
            "actual_sha256",
        },
        label,
    )
    booleans = [
        audit.get(name)
        for name in (
            "exact_ordered_manifest",
            "unique_segment_and_segment_task_identity",
            "event_sequence_identity_valid",
            "shadow_row_bag_links",
            "shadow_row_source_queue_winner",
            "shadow_row_local_telemetry_exact",
        )
    ]
    if (
        any(not isinstance(item, bool) for item in booleans)
        or not _sha256_text(audit.get("expected_sha256"))
        or not _sha256_text(audit.get("actual_sha256"))
        or (audit.get("exact_ordered_manifest") is True)
        != (audit.get("expected_sha256") == audit.get("actual_sha256"))
        or audit.get("pass") is not all(booleans)
        or not all(booleans)
    ):
        raise SelectionError(f"{label} population identity replay failed")


def _goal_map_from_bag_rows(
    value: Any, *, bag_count: int, label: str
) -> dict[int, int]:
    rows = _rows(value, label)
    if len(rows) != bag_count:
        raise SelectionError(f"{label} cardinality differs from the frozen population")
    goals: dict[int, int] = {}
    for runtime_id, row in enumerate(rows):
        goal = _integer(row.get("goal"), f"{label}[{runtime_id}].goal")
        if goal < 0:
            raise SelectionError(f"{label} contains an invalid goal")
        goals[runtime_id] = goal
    return goals


def _goal_map_from_manifest_case(
    value: Mapping[str, Any], *, bag_count: int, label: str
) -> dict[int, int]:
    rows = _rows(value.get("bag_rows"), f"{label}.bag_rows")
    if value.get("bag_rows_sha256") != canonical_sha256(rows):
        raise SelectionError(f"{label} bag-row hash differs from the frozen manifest")
    return _goal_map_from_bag_rows(
        rows, bag_count=bag_count, label=f"{label}.bag_rows"
    )


def _goal_map_from_request(
    value: Mapping[str, Any], *, bag_count: int, label: str
) -> dict[int, int]:
    records = value.get("bag_records")
    if not isinstance(records, (list, tuple)) or len(records) != bag_count:
        raise SelectionError(f"{label}.bag_records differs from the frozen population")
    goals: dict[int, int] = {}
    for runtime_id, record in enumerate(records):
        if not isinstance(record, (list, tuple)) or len(record) != 7:
            raise SelectionError(f"{label}.bag_records[{runtime_id}] is malformed")
        goal = _integer(record[5], f"{label}.bag_records[{runtime_id}].goal")
        if goal < 0:
            raise SelectionError(f"{label}.bag_records contains an invalid goal")
        goals[runtime_id] = goal
    return goals


def _service_profile_from_request(
    value: Mapping[str, Any], *, label: str
) -> dict[int, float]:
    minimum = _finite(value.get("minimum_service_seconds"), f"{label}.minimum")
    records = value.get("node_records")
    if minimum <= 0.0 or not isinstance(records, (list, tuple)):
        raise SelectionError(f"{label} service profile is invalid")
    services: dict[int, float] = {}
    for index, record in enumerate(records):
        if not isinstance(record, (list, tuple)) or len(record) < 3:
            raise SelectionError(f"{label}.node_records[{index}] is malformed")
        node = _integer(record[0], f"{label}.node_records[{index}].node")
        raw = _finite(record[2], f"{label}.node_records[{index}].service")
        if node < 0 or node in services or raw < 0.0:
            raise SelectionError(f"{label} service profile identity is invalid")
        services[node] = max(raw, minimum)
    if not services:
        raise SelectionError(f"{label} service profile is empty")
    return services


def _expected_exact_service_node(
    *, exact_l: bool, value: int | None, label: str
) -> int | None:
    if not isinstance(exact_l, bool) or exact_l is not (value is not None):
        raise SelectionError(f"{label} exact-L node applicability is invalid")
    if value is None:
        return None
    node = _integer(value, f"{label}.expected_exact_node")
    if node < 0:
        raise SelectionError(f"{label} exact-L node identity is invalid")
    return node


def _validate_global_service_evidence(
    value: Any,
    label: str,
    *,
    complete_sequence: Sequence[Mapping[str, Any]],
    goal_by_runtime: Mapping[int, int],
    exact_l: bool,
    expected_exact_node: int | None,
    expected_reservation_counts: Mapping[int, int],
    expected_service_by_node: Mapping[int, float],
) -> None:
    if complete_sequence is None or goal_by_runtime is None:
        raise SelectionError(f"{label} requires externally bound own-goal evidence")
    exact_node = _expected_exact_service_node(
        exact_l=exact_l,
        value=expected_exact_node,
        label=label,
    )
    service_by_node: dict[int, float] = {}
    for raw_node, raw_seconds in expected_service_by_node.items():
        node = _integer(raw_node, f"{label}.expected service node")
        seconds = _finite(raw_seconds, f"{label}.expected service seconds")
        if node < 0 or node in service_by_node or seconds <= 0.0:
            raise SelectionError(f"{label} expected service profile is invalid")
        service_by_node[node] = seconds
    if not service_by_node:
        raise SelectionError(f"{label} expected service profile is empty")
    audit = _mapping(value, label)
    _exact_keys(
        audit,
        {
            "pass",
            "checks",
            "completion_counts",
            "reservation_counts",
            "ordered_service_episodes",
            "service_episodes_sha256",
            "service_episode_count",
            "evidence_vector_limit",
            "evidence_vector_bounded",
            "error",
        },
        label,
    )
    checks = _validate_boolean_checks(
        audit.get("checks"), GLOBAL_SERVICE_CHECK_NAMES, f"{label}.checks"
    )
    completions = _mapping(
        audit.get("completion_counts"), f"{label}.completion_counts"
    )
    reservations = _mapping(
        audit.get("reservation_counts"), f"{label}.reservation_counts"
    )
    if any(
        not isinstance(name, str)
        or not name
        or not name.isdecimal()
        or str(int(name)) != name
        or int(name) not in service_by_node
        for name in [*completions, *reservations]
    ):
        raise SelectionError(f"{label} service-count node identity is invalid")
    if any(
        isinstance(count, bool) or not isinstance(count, int) or count < 0
        for count in [*completions.values(), *reservations.values()]
    ):
        raise SelectionError(f"{label} service counts are invalid")
    frozen_reservations = {
        str(_integer(node, f"{label}.expected reservation node")): _integer(
            count, f"{label}.expected reservation count"
        )
        for node, count in expected_reservation_counts.items()
    }
    if dict(reservations) != frozen_reservations:
        raise SelectionError(f"{label} reservation counts differ from final state")

    raw_episodes = audit.get("ordered_service_episodes")
    if not isinstance(raw_episodes, list):
        raise SelectionError(f"{label} global service episodes must be a list")
    episodes: list[dict[str, int | float]] = []
    for index, raw in enumerate(raw_episodes):
        episode = _mapping(raw, f"{label}.episodes[{index}]")
        _exact_keys(
            episode,
            {"runtime_bag_id", "node", "start", "complete", "completion_event_seq"},
            f"{label}.episodes[{index}]",
        )
        normalized = {
            "runtime_bag_id": _integer(
                episode.get("runtime_bag_id"),
                f"{label}.episodes[{index}].runtime_bag_id",
            ),
            "node": _integer(
                episode.get("node"), f"{label}.episodes[{index}].node"
            ),
            "start": _finite(
                episode.get("start"), f"{label}.episodes[{index}].start"
            ),
            "complete": _finite(
                episode.get("complete"), f"{label}.episodes[{index}].complete"
            ),
            "completion_event_seq": _integer(
                episode.get("completion_event_seq"),
                f"{label}.episodes[{index}].completion_event_seq",
            ),
        }
        if (
            normalized["runtime_bag_id"] not in goal_by_runtime
            or normalized["node"] not in service_by_node
            or str(normalized["node"]) not in reservations
            or normalized["completion_event_seq"] <= 0
            or normalized["complete"] < normalized["start"]
            or not math.isclose(
                normalized["complete"] - normalized["start"],
                service_by_node[int(normalized["node"])],
                rel_tol=0.0,
                abs_tol=AUDIT_EPSILON,
            )
        ):
            raise SelectionError(f"{label} global service episode is invalid")
        episodes.append(normalized)
    ordered = sorted(
        episodes,
        key=lambda row: (
            row["start"],
            row["complete"],
            row["completion_event_seq"],
            row["runtime_bag_id"],
            row["node"],
        ),
    )
    if episodes != ordered:
        raise SelectionError(f"{label} global service episode order changed")
    if audit.get("service_episodes_sha256") != canonical_sha256(episodes):
        raise SelectionError(f"{label} global service episode hash changed")

    expected_limit = len(goal_by_runtime) * max(1, len(reservations))
    vector_bounded = len(episodes) <= expected_limit
    if (
        audit.get("service_episode_count") != len(episodes)
        or audit.get("evidence_vector_limit") != expected_limit
        or audit.get("evidence_vector_bounded") is not vector_bounded
    ):
        raise SelectionError(f"{label} global service evidence bound changed")

    identities = [
        (int(row["runtime_bag_id"]), int(row["node"])) for row in episodes
    ]
    event_identities = [int(row["completion_event_seq"]) for row in episodes]
    by_node: dict[int, list[tuple[float, float]]] = defaultdict(list)
    completion_counts: Counter[str] = Counter()
    for row in episodes:
        node = int(row["node"])
        by_node[node].append((float(row["start"]), float(row["complete"])))
        completion_counts[str(node)] += 1
    projected_counts = dict(sorted(completion_counts.items()))
    if projected_counts != dict(completions):
        raise SelectionError(f"{label} completion-count projection changed")
    reservation_match = set(completions) <= set(reservations) and all(
        count == completions.get(node, 0) for node, count in reservations.items()
    )
    recomputed: dict[str, bool] = {
        "unique_bag_node": len(identities) == len(set(identities)),
        "completion_event_identity_unique": len(event_identities)
        == len(set(event_identities)),
        "no_node_overlap": all(
            right[0] >= left[1] - AUDIT_EPSILON
            for intervals in by_node.values()
            for left, right in zip(sorted(intervals), sorted(intervals)[1:])
        ),
        "reservation_count_match": reservation_match,
        "goal_arrival_has_no_service": all(
            int(row["node"]) != goal_by_runtime[int(row["runtime_bag_id"])]
            for row in episodes
        ),
        "evidence_vector_bounded": vector_bounded,
    }

    sequence_projection = [
        {
            "runtime_bag_id": _integer(
                row.get("runtime_bag_id"), f"{label}.sequence.runtime_bag_id"
            ),
            "node": _integer(row.get("node"), f"{label}.sequence.node"),
            "start": _finite(row.get("start"), f"{label}.sequence.start"),
            "complete": _finite(
                row.get("complete"), f"{label}.sequence.complete"
            ),
            "completion_event_seq": _integer(
                row.get("completion_event_seq"),
                f"{label}.sequence.completion_event_seq",
            ),
        }
        for row in complete_sequence
    ]
    if exact_node is not None:
        sequence_nodes = {row["node"] for row in sequence_projection}
        if sequence_nodes != {exact_node}:
            raise SelectionError(f"{label} exact-L sequence node identity changed")
        global_projection = [
            row for row in episodes if row["node"] == exact_node
        ]
    else:
        global_projection = episodes
    if global_projection != sequence_projection:
        raise SelectionError(f"{label} service-sequence/global projection changed")
    if (
        not reservations
        or checks != recomputed
        or not all(recomputed.values())
        or audit.get("error") is not None
        or audit.get("pass") is not all(checks.values())
        or not all(checks.values())
    ):
        raise SelectionError(f"{label} global service replay failed")


def _validate_service_audit_evidence(
    value: Any,
    *,
    bag_count: int,
    exact_l: bool,
    expected_exact_node: int | None,
    expected_goal_by_runtime: Mapping[int, int],
    expected_service_by_node: Mapping[int, float],
    service_seconds: float | None = None,
    expected_origins: set[str] | None = None,
    label: str,
) -> None:
    exact_node = _expected_exact_service_node(
        exact_l=exact_l,
        value=expected_exact_node,
        label=label,
    )
    audit = _mapping(value, label)
    _exact_keys(
        audit,
        {
            "pass",
            "checks",
            "origins",
            "episode_count",
            "population_identity",
            "legacy_wait_over_120",
            "permanent_starvation",
            "service_sequence",
            "global_service_calendar",
        },
        label,
    )
    checks = _validate_boolean_checks(
        audit.get("checks"), SERVICE_AUDIT_CHECK_NAMES, f"{label}.checks"
    )
    _validate_population_identity_evidence(
        audit.get("population_identity"), f"{label}.population_identity"
    )
    _validate_legacy_wait_evidence(
        audit.get("legacy_wait_over_120"), f"{label}.legacy_wait"
    )
    permanent = _validate_permanent_evidence(
        audit.get("permanent_starvation"),
        bag_count=bag_count,
        exact_l=exact_l,
        label=f"{label}.permanent",
    )
    sequence = _validate_service_sequence_evidence(
        audit.get("service_sequence"),
        bag_count=bag_count,
        exact_l=exact_l,
        expected_exact_node=exact_node,
        service_seconds=service_seconds,
        label=f"{label}.service_sequence",
    )
    expected_goals = dict(expected_goal_by_runtime)
    if (
        set(expected_goals) != set(range(bag_count))
        or any(
            isinstance(runtime_id, bool)
            or not isinstance(runtime_id, int)
            or isinstance(goal, bool)
            or not isinstance(goal, int)
            or goal < 0
            for runtime_id, goal in expected_goals.items()
        )
    ):
        raise SelectionError(f"{label} frozen own-goal mapping is invalid")
    completion_goals = {
        row["runtime_bag_id"]: row["goal"] for row in permanent["completion"]
    }
    if completion_goals != expected_goals:
        raise SelectionError(f"{label} own-goal mapping differs from frozen request")
    _validate_global_service_evidence(
        audit.get("global_service_calendar"),
        f"{label}.global_service",
        complete_sequence=sequence,
        goal_by_runtime=expected_goals,
        exact_l=exact_l,
        expected_exact_node=exact_node,
        expected_reservation_counts={
            _integer(row.get("node"), f"{label}.permanent.junction.node"): _integer(
                row.get("service_reservation_count"),
                f"{label}.permanent.junction.service_reservation_count",
            )
            for row in permanent["junctions"]
        },
        expected_service_by_node=expected_service_by_node,
    )
    nested = {
        "exact_request_population_identity": audit["population_identity"]["pass"],
        "legacy_wait_native_consistent": audit["legacy_wait_over_120"]["pass"],
        "permanent_starvation_zero": audit["permanent_starvation"]["pass"],
        "service_sequence_conservation": audit["service_sequence"]["pass"],
        "global_service_calendar": audit["global_service_calendar"]["pass"],
    }
    origins = audit.get("origins")
    completion_by_bag = {
        row["runtime_bag_id"]: row for row in permanent["completion"]
    }
    sequence_by_bag = {row["runtime_bag_id"]: row for row in sequence}
    completed_origin_names = sorted(permanent["completed_origins"])
    exact_completion_sequence = not exact_l or (
        set(completion_by_bag) == set(sequence_by_bag)
        and all(
            completion_by_bag[bag_id]["source"] == sequence_by_bag[bag_id]["source"]
            for bag_id in completion_by_bag
        )
    )
    complete_once = all(
        row["completed"] is True for row in permanent["completion"]
    ) and (not exact_l or len(sequence) == bag_count)
    origin_coverage = (expected_origins or set()) <= set(completed_origin_names)
    if (
        not isinstance(origins, list)
        or any(not isinstance(origin, str) or not origin for origin in origins)
        or origins != sorted(set(origins))
        or origins != completed_origin_names
        or checks.get("complete_once") is not complete_once
        or checks.get("origin_coverage") is not origin_coverage
        or not exact_completion_sequence
        or audit.get("episode_count") != audit["service_sequence"]["sequence_count"]
        or any(checks.get(name) is not passed for name, passed in nested.items())
        or audit.get("pass") is not all(checks.values())
        or not all(checks.values())
    ):
        raise SelectionError(f"{label} service-audit parent/child replay failed")


def _validate_legacy_pair_evidence(value: Any, label: str) -> None:
    audit = _mapping(value, label)
    _exact_keys(audit, {"pass", "checks", "off", "shadow"}, label)
    checks = _validate_boolean_checks(
        audit.get("checks"), LEGACY_PAIR_CHECK_NAMES, f"{label}.checks"
    )
    _validate_legacy_wait_evidence(audit.get("off"), f"{label}.off")
    _validate_legacy_wait_evidence(audit.get("shadow"), f"{label}.shadow")
    off = _mapping(audit.get("off"), f"{label}.off")
    shadow = _mapping(audit.get("shadow"), f"{label}.shadow")
    recomputed = {
        "off_native_consistent": off.get("pass") is True,
        "shadow_native_consistent": shadow.get("pass") is True,
        "count_exact": off.get("recomputed_count") == shadow.get("recomputed_count"),
        "ordered_identities_exact": off.get("ordered_identities")
        == shadow.get("ordered_identities"),
        "ordered_waits_exact": off.get("ordered_waits")
        == shadow.get("ordered_waits"),
        "ordered_flags_exact": off.get("ordered_flags")
        == shadow.get("ordered_flags"),
        "per_origin_exact": off.get("per_origin") == shadow.get("per_origin"),
        "ordered_vector_hash_exact": off.get("ordered_vector_sha256")
        == shadow.get("ordered_vector_sha256"),
    }
    if checks != recomputed or audit.get("pass") is not all(checks.values()):
        raise SelectionError(f"{label} legacy pair replay failed")


def _validate_census_evidence(value: Any, *, row_count: int, label: str) -> None:
    census = _mapping(value, label)
    _exact_keys(
        census,
        {"pass", *CENSUS_CHECK_NAMES, "values", "ordinary_commit_counts"},
        label,
    )
    checks = {
        name: census.get(name) for name in CENSUS_CHECK_NAMES
    }
    if any(not isinstance(item, bool) for item in checks.values()):
        raise SelectionError(f"{label} census checks must be bool")
    values = _mapping(census.get("values"), f"{label}.values")
    ordinary = _mapping(
        census.get("ordinary_commit_counts"), f"{label}.ordinary counts"
    )
    if set(ordinary) != {"direct", "j2", "unclassified"} or any(
        not isinstance(item, int) or isinstance(item, bool) or item < 0
        for item in [*values.values(), *ordinary.values()]
    ):
        raise SelectionError(f"{label} census count vectors are invalid")
    required = {
        "external_commit_considered_count",
        "direct_external_commit_count",
        "j2_exact_commit_count",
        *CENSUS_PART_NAMES,
        *CENSUS_ZERO_NAMES,
    }
    if set(values) != required:
        raise SelectionError(f"{label} census count vector is incomplete")
    considered = values["external_commit_considered_count"]
    derived = {
        "partition": considered
        == sum(values[name] for name in CENSUS_PART_NAMES),
        "seam_partition": considered
        == values["direct_external_commit_count"]
        + values["j2_exact_commit_count"],
        "ordinary_commit_seam_binding": ordinary["unclassified"] == 0
        and considered == ordinary["direct"] + ordinary["j2"]
        and values["direct_external_commit_count"] == ordinary["direct"]
        and values["j2_exact_commit_count"] == ordinary["j2"],
        "stored_matches": values["observation_stored_count"] == row_count,
        "zero_drop": values["observation_dropped_count"] == 0,
        "inert_local": all(values[name] == 0 for name in CENSUS_ZERO_NAMES),
    }
    if (
        any(checks[name] is not passed for name, passed in derived.items())
        or census.get("pass") is not all(checks.values())
        or not all(checks.values())
    ):
        raise SelectionError(f"{label} census replay failed")


def _validate_resource_values(value: Any, label: str) -> Mapping[str, Any]:
    resources = _mapping(value, label)
    _exact_keys(resources, RESOURCE_VALUE_NAMES, label)
    if any(_finite(item, label) < 0.0 for item in resources.values()):
        raise SelectionError(f"{label} resource value is negative")
    return resources


def _validate_synthetic_case_evidence(
    case: Mapping[str, Any],
    *,
    expected_binary_sha256: str,
    expected_manifest_case: Mapping[str, Any] | None,
    expected_goal_by_runtime: Mapping[int, int],
    expected_service_by_node: Mapping[int, float],
    expected_exact_node: int,
    label: str,
) -> None:
    _exact_keys(case, SYNTHETIC_CASE_KEYS, label)
    bag_count = _integer(case.get("bag_count"), f"{label}.bag_count")
    admitted = _integer(case.get("admitted_row_count"), f"{label}.admitted")
    service_seconds = _finite(case.get("service_seconds"), f"{label}.service_seconds")
    flow_pattern = case.get("flow_pattern")
    if bag_count <= 0 or admitted < 0 or service_seconds <= 0.0:
        raise SelectionError(f"{label} cardinality is invalid")
    expected_origins = (
        {"external"}
        if flow_pattern == "external_only"
        else {"local"}
        if flow_pattern == "local_only"
        else {"external", "local"}
    )
    if expected_manifest_case is not None:
        for key in (
            "cohort",
            "replica",
            "case_id",
            "service_seconds",
            "bag_count",
            "flow_pattern",
            "negative_control",
        ):
            if key in expected_manifest_case and case.get(key) != expected_manifest_case.get(key):
                raise SelectionError(f"{label} differs from the frozen manifest")
    _validate_service_audit_evidence(
        case.get("off_audit"),
        bag_count=bag_count,
        exact_l=True,
        expected_exact_node=expected_exact_node,
        expected_goal_by_runtime=expected_goal_by_runtime,
        expected_service_by_node=expected_service_by_node,
        service_seconds=service_seconds,
        expected_origins=expected_origins,
        label=f"{label}.off",
    )
    _validate_service_audit_evidence(
        case.get("shadow_audit"),
        bag_count=bag_count,
        exact_l=True,
        expected_exact_node=expected_exact_node,
        expected_goal_by_runtime=expected_goal_by_runtime,
        expected_service_by_node=expected_service_by_node,
        service_seconds=service_seconds,
        expected_origins=expected_origins,
        label=f"{label}.shadow",
    )
    _validate_legacy_pair_evidence(
        case.get("legacy_wait_over_120"), f"{label}.legacy_pair"
    )
    sequence = _validate_boolean_checks(
        case.get("service_sequence_parity"),
        {
            "sequence_sha256",
            "origin_sequence_sha256",
            "maximum_consecutive_origin_run",
        },
        f"{label}.service_sequence_parity",
    )
    off_sequence = case["off_audit"]["service_sequence"]
    shadow_sequence = case["shadow_audit"]["service_sequence"]
    sequence_recomputed = {
        key: off_sequence[key] == shadow_sequence[key] for key in sequence
    }
    _validate_census_evidence(
        case.get("census"), row_count=admitted, label=f"{label}.census"
    )
    off_hashes = _mapping(case.get("off_hashes"), f"{label}.off_hashes")
    shadow_hashes = _mapping(case.get("shadow_hashes"), f"{label}.shadow_hashes")
    if (
        set(off_hashes) != ORDINARY_PAYLOAD_HASH_NAMES
        or set(shadow_hashes) != ORDINARY_PAYLOAD_HASH_NAMES
        or any(not _sha256_text(item) for item in [*off_hashes.values(), *shadow_hashes.values()])
    ):
        raise SelectionError(f"{label} ordinary payload hash vector is invalid")
    resources = _mapping(case.get("resources"), f"{label}.resources")
    _exact_keys(resources, {"off", "shadow"}, f"{label}.resources")
    off_resources = _validate_resource_values(
        resources.get("off"), f"{label}.resources.off"
    )
    shadow_resources = _validate_resource_values(
        resources.get("shadow"), f"{label}.resources.shadow"
    )
    resource_decomposition = (
        off_resources["trace_sidecar_accounted_bytes"] == 0.0
        and off_resources["runtime_internal_accounted_bytes"]
        == off_resources["total_accounted_bytes"]
        and shadow_resources["runtime_internal_accounted_bytes"]
        + shadow_resources["trace_sidecar_accounted_bytes"]
        == shadow_resources["total_accounted_bytes"]
    )
    resource_ratios = []
    for resource_name in RESOURCE_VALUE_NAMES - {"trace_sidecar_accounted_bytes"}:
        off_value = off_resources[resource_name]
        shadow_value = shadow_resources[resource_name]
        resource_ratios.append(
            shadow_value / off_value
            if off_value > 0.0
            else 1.0
            if shadow_value == 0.0
            else math.inf
        )
    resource_gate = resource_decomposition and all(
        ratio <= RESOURCE_RATIO_LIMIT for ratio in resource_ratios
    )
    path_value = case.get("loaded_cpp_binary_path")
    hashes = [
        case.get(name)
        for name in (
            "rows_sha256",
            "pairs_sha256",
            "profile_sha256",
            "potential_sha256",
            "off_request_sha256",
            "shadow_request_sha256",
            "off_ordinary_request_sha256",
            "shadow_ordinary_request_sha256",
        )
    ]
    hard = all(
        (
            case["off_audit"]["pass"],
            case["shadow_audit"]["pass"],
            case["legacy_wait_over_120"]["pass"],
            all(sequence.values()),
            case["census"]["pass"],
            case.get("ordinary_parity") is True,
            case.get("request_parity") is True,
            case.get("binary_parity") is True,
            case.get("join_status") == "V3R2_OUTCOME_JOINED",
        )
    )
    if (
        sequence != sequence_recomputed
        or case.get("census_partition_pass") is not case["census"]["pass"]
        or case.get("ordinary_parity") is not (off_hashes == shadow_hashes)
        or case.get("request_parity")
        is not (
            case.get("off_ordinary_request_sha256")
            == case.get("shadow_ordinary_request_sha256")
        )
        or case.get("hard_gate_pass") is not hard
        or not hard
        or case.get("loaded_cpp_binary_sha256") != expected_binary_sha256
        or not isinstance(path_value, str)
        or not path_value
        or any(not _sha256_text(item) for item in hashes)
        or (case.get("negative_control") is True and admitted != 0)
        or not resource_gate
    ):
        raise SelectionError(f"{label} hard gate/nested replay failed")


def _evidence_close(left: Any, right: Any, label: str) -> bool:
    return math.isclose(
        _finite(left, f"{label}.left"),
        _finite(right, f"{label}.right"),
        rel_tol=0.0,
        abs_tol=AUDIT_EPSILON,
    )


def _validate_joined_pair_arithmetic(
    source: Mapping[str, Any], pair: Mapping[str, Any], label: str
) -> None:
    if set(pair) != set(source) | JOIN_PAIR_KEYS:
        raise SelectionError(f"{label} merged pair schema changed")
    status = pair.get("status")
    if status == "V3R2_REPEATED_BAG_DIAGNOSTIC":
        if (
            pair.get("primary") is not False
            or pair.get("reason") != "EARLIER_PRIMARY_USED_BAG"
            or pair.get("case_status") != "V3R2_OUTCOME_JOINED"
            or any(
                pair.get(name) is not None
                for name in (
                    "local",
                    "external",
                    "Y_realized",
                    "A_gap",
                    "X_insert",
                    "H_gap",
                )
            )
        ):
            raise SelectionError(f"{label} repeat diagnostic changed")
        return
    if (
        status != "V3R2_OUTCOME_JOINED"
        or pair.get("primary") is not True
        or pair.get("reason") != "UNIQUE_V3R2_PAIR"
        or pair.get("case_status") != "V3R2_OUTCOME_JOINED"
    ):
        raise SelectionError(f"{label} joined status/identity changed")
    local = _mapping(pair.get("local"), f"{label}.local")
    external = _mapping(pair.get("external"), f"{label}.external")
    _exact_keys(local, JOIN_EPISODE_OUTPUT_KEYS, f"{label}.local")
    _exact_keys(external, JOIN_EPISODE_OUTPUT_KEYS, f"{label}.external")
    for side_name, episode in (("local", local), ("external", external)):
        numbers = {
            name: _finite(value, f"{label}.{side_name}.{name}")
            for name, value in episode.items()
        }
        if numbers["actual_L_service_complete"] < numbers["actual_L_service_start"]:
            raise SelectionError(f"{label} service episode duration is negative")
        waits = (
            numbers["actual_subsequent_source_wait"],
            numbers["actual_subsequent_junction_wait"],
            numbers["actual_transit_seconds"],
            numbers["actual_subsequent_calendar_wait"],
        )
        if min(*waits, numbers["actual_subsequent_wait"]) < 0.0 or not math.isclose(
            math.fsum(waits),
            numbers["actual_subsequent_wait"],
            rel_tol=0.0,
            abs_tol=AUDIT_EPSILON,
        ):
            raise SelectionError(f"{label} subsequent-wait decomposition changed")
    required_equalities = (
        (
            external["actual_L_service_start"],
            source.get("external_slot_start_seconds"),
        ),
        (
            external["actual_L_service_complete"],
            source.get("external_slot_end_seconds"),
        ),
        (
            external["actual_L_service_complete"]
            - external["actual_L_service_start"],
            source.get("external_service_seconds"),
        ),
        (
            local["actual_L_service_complete"] - local["actual_L_service_start"],
            source.get("local_service_seconds"),
        ),
        (
            pair.get("Y_realized"),
            local["actual_L_service_start"] - _finite(source.get("L0"), label),
        ),
        (
            pair.get("A_gap"),
            local["actual_L_service_start"] - external["actual_L_service_start"],
        ),
        (pair.get("X_insert"), source.get("X_insert")),
        (pair.get("H_gap"), source.get("H_gap")),
    )
    if any(
        not _evidence_close(left, right, label)
        for left, right in required_equalities
    ) or _finite(pair.get("Y_realized"), f"{label}.Y_realized") < 0.0:
        raise SelectionError(f"{label} joined arithmetic changed")


def _validate_stage1_case_association(
    cases: Sequence[Mapping[str, Any]],
    observations: Sequence[Mapping[str, Any]],
    pairs: Sequence[Mapping[str, Any]],
    *,
    auditor: Any | None = None,
) -> None:
    ordered_case_ids = [case.get("case_id") for case in cases]
    case_positions = {case_id: index for index, case_id in enumerate(ordered_case_ids)}
    if len(case_positions) != len(cases) or any(
        not isinstance(case_id, str) or not case_id for case_id in ordered_case_ids
    ):
        raise SelectionError("synthetic case identities are invalid")

    def identity(row: Mapping[str, Any], label: str) -> tuple[str, int, int]:
        case_id = row.get("case_id")
        if case_id not in case_positions:
            raise SelectionError(f"{label} references an unknown case")
        ordinal = _integer(row.get("observation_ordinal"), f"{label}.ordinal")
        opportunity = _integer(
            row.get("opportunity_id"), f"{label}.opportunity"
        )
        if ordinal <= 0 or opportunity <= 0:
            raise SelectionError(f"{label} identity must be positive")
        return str(case_id), ordinal, opportunity

    observation_by_identity: dict[tuple[str, int, int], Mapping[str, Any]] = {}
    observation_order: list[int] = []
    by_case_observations: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for index, row in enumerate(observations):
        key = identity(row, f"synthetic observation[{index}]")
        if key in observation_by_identity:
            raise SelectionError("synthetic observation identity is duplicated")
        observation_by_identity[key] = row
        by_case_observations[key[0]].append(row)
        observation_order.append(case_positions[key[0]])
    pair_by_identity: dict[tuple[str, int, int], Mapping[str, Any]] = {}
    pair_order: list[int] = []
    by_case_pairs: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for index, pair in enumerate(pairs):
        key = identity(pair, f"synthetic pair[{index}]")
        if key in pair_by_identity:
            raise SelectionError("synthetic pair identity is duplicated")
        source = observation_by_identity.get(key)
        if (
            source is None
            or not (set(source) - JOIN_PAIR_KEYS) <= set(pair)
            or any(
                pair.get(name) != item
                for name, item in source.items()
                if name not in JOIN_PAIR_KEYS
            )
        ):
            raise SelectionError("synthetic pair is not bound to its source observation")
        if not JOIN_PAIR_KEYS <= set(pair):
            raise SelectionError("synthetic pair lacks the exact join projection")
        _validate_joined_pair_arithmetic(
            source, pair, f"synthetic pair[{index}]"
        )
        pair_by_identity[key] = pair
        by_case_pairs[key[0]].append(pair)
        pair_order.append(case_positions[key[0]])
    if (
        set(pair_by_identity) != set(observation_by_identity)
        or observation_order != sorted(observation_order)
        or pair_order != sorted(pair_order)
    ):
        raise SelectionError("synthetic observation/pair association is incomplete")
    for case in cases:
        case_id = str(case["case_id"])
        case_observations = by_case_observations[case_id]
        case_pairs = by_case_pairs[case_id]
        if auditor is not None and case_observations:
            normalizer = getattr(auditor, "normalize_numeric_rows", None)
            if not callable(normalizer):
                raise SelectionError("synthetic auditor lacks V3R4 row normalization")
            metadata = {
                "cohort": case.get("cohort"),
                "replica": case.get("replica"),
                "service_seconds": case.get("service_seconds"),
                "bag_count": case.get("bag_count"),
                "flow_pattern": case.get("flow_pattern"),
            }
            metadata_keys = {"case_id", *metadata}
            if any(
                row.get("case_id") != case_id
                or any(row.get(name) != value for name, value in metadata.items())
                for row in case_observations
            ):
                raise SelectionError("synthetic observation metadata changed")
            raw_rows = [
                {name: value for name, value in row.items() if name not in metadata_keys}
                for row in case_observations
            ]
            try:
                normalized = normalizer(
                    case_id,
                    raw_rows,
                    {1: _finite(case.get("service_seconds"), "case service")},
                    metadata=metadata,
                )
            except (KeyError, TypeError, ValueError) as error:
                raise SelectionError("synthetic V3R4 observation replay failed") from error
            if normalized != case_observations:
                raise SelectionError("synthetic V3R4 observation projection changed")

            completion = _rows(
                _mapping(
                    _mapping(case.get("shadow_audit"), "case.shadow_audit").get(
                        "permanent_starvation"
                    ),
                    "case.shadow_audit.permanent",
                ).get("bag_completion_vector"),
                "case.shadow completion vector",
            )
            sources = {
                _integer(row.get("runtime_bag_id"), "completion runtime id"): row.get(
                    "source"
                )
                for row in completion
            }
            canonical_origins = {"local", "external"} <= set(sources.values())
            if canonical_origins and any(
                sources.get(row.get("local_runtime_bag_id")) != "local"
                or sources.get(row.get("external_runtime_bag_id")) != "external"
                for row in case_observations
            ):
                raise SelectionError("synthetic observation origin roles changed")
        raw_pairs = [
            {key: pair[key] for key in JOIN_PAIR_KEYS} for pair in case_pairs
        ]
        if (
            case.get("admitted_row_count") != len(case_observations)
            or case.get("rows_sha256") != canonical_sha256(case_observations)
            or case.get("pairs_sha256") != canonical_sha256(raw_pairs)
        ):
            raise SelectionError("synthetic per-case observation/pair hash changed")


def _resolved_evidence_path(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise SelectionError(f"{label} must be a nonempty path")
    try:
        return Path(value).resolve()
    except (OSError, RuntimeError) as error:
        raise SelectionError(f"{label} cannot be resolved") from error


def _validate_native_proof_identity(
    native_proof: Mapping[str, Any],
    *,
    native_gates: Mapping[str, Mapping[str, Any]],
    auditor: Any,
    expected_binary_sha256: str,
    expected_build_head: str,
    expected_executable: Path,
    expected_nested_executable: Path,
    expected_source_bundle: Mapping[str, Any],
    case_binary_paths: Sequence[Any],
) -> None:
    sha_pairs = (
        ("executable_sha256", "executable_sha256_after"),
        ("nested_executable_sha256", "nested_executable_sha256_after"),
        ("g32_binary_sha256", "g32_binary_sha256_after"),
    )
    for before_name, after_name in sha_pairs:
        before = native_proof.get(before_name)
        after = native_proof.get(after_name)
        if not _sha256_text(before) or not _sha256_text(after) or before != after:
            raise SelectionError(
                f"synthetic Stage0 native proof {before_name} identity changed"
            )
    if native_proof.get("g32_binary_sha256") != expected_binary_sha256:
        raise SelectionError("synthetic Stage0 native proof G32 identity changed")

    proof = _mapping(native_proof.get("proof"), "synthetic native proof payload")
    nested_proof = _mapping(
        native_proof.get("nested_proof"), "synthetic nested proof payload"
    )
    proof_assertions = tuple(auditor.NATIVE_PROOF_ASSERTIONS)
    nested_assertion = str(auditor.NESTED_PROOF_ASSERTION)
    _exact_keys(
        proof,
        {"schema_id", "test_id", "build_head", *proof_assertions},
        "synthetic native proof payload",
    )
    _exact_keys(
        nested_proof,
        {"schema_id", "test_id", "build_head", nested_assertion},
        "synthetic nested proof payload",
    )
    build_heads = (
        native_proof.get("build_head"),
        native_proof.get("proof_build_head"),
        native_proof.get("nested_proof_build_head"),
        proof.get("build_head"),
        nested_proof.get("build_head"),
    )
    if any(value != expected_build_head for value in build_heads):
        raise SelectionError("synthetic Stage0 native proof build head changed")

    executable_path = _resolved_evidence_path(
        native_proof.get("executable_path"),
        "synthetic native proof executable_path",
    )
    nested_executable_path = _resolved_evidence_path(
        native_proof.get("nested_executable_path"),
        "synthetic native proof nested_executable_path",
    )
    binary_path = _resolved_evidence_path(
        native_proof.get("g32_binary_path"), "synthetic native proof g32_binary_path"
    )
    if (
        executable_path != expected_executable.resolve()
        or nested_executable_path != expected_nested_executable.resolve()
    ):
        raise SelectionError("synthetic Stage0 native proof executable path changed")
    try:
        executable_current_sha = file_sha256(executable_path)
        nested_executable_current_sha = file_sha256(nested_executable_path)
    except OSError as error:
        raise SelectionError(
            "synthetic Stage0 native proof executable is not currently readable"
        ) from error
    if (
        native_proof.get("executable_sha256") != executable_current_sha
        or native_proof.get("executable_sha256_after") != executable_current_sha
        or native_proof.get("nested_executable_sha256")
        != nested_executable_current_sha
        or native_proof.get("nested_executable_sha256_after")
        != nested_executable_current_sha
    ):
        raise SelectionError(
            "synthetic Stage0 native proof executable current identity changed"
        )
    if not case_binary_paths or any(
        _resolved_evidence_path(path, "synthetic case loaded_cpp_binary_path")
        != binary_path
        for path in case_binary_paths
    ):
        raise SelectionError("synthetic Stage0 native proof G32 path is unbound")
    if native_proof.get("source_bundle") != expected_source_bundle:
        raise SelectionError("synthetic Stage0 native proof source bundle changed")

    exit_zero = (
        type(native_proof.get("exit_code")) is int
        and native_proof.get("exit_code") == 0
    )
    nested_exit_zero = (
        type(native_proof.get("nested_exit_code")) is int
        and native_proof.get("nested_exit_code") == 0
    )
    recomputed_gates = {
        "native_proof_exit_zero": exit_zero,
        "native_proof_fixed_executable": executable_path
        == expected_executable.resolve(),
        "native_proof_executable_unchanged": native_proof.get(
            "executable_sha256"
        )
        == native_proof.get("executable_sha256_after"),
        "native_proof_exact_schema": True,
        "native_proof_schema_id": proof.get("schema_id")
        == auditor.NATIVE_PROOF_SCHEMA,
        "native_proof_test_id": proof.get("test_id")
        == auditor.NATIVE_PROOF_TEST_ID,
        "native_proof_all_native_assertions": all(
            proof.get(name) is True for name in proof_assertions
        ),
        "native_proof_same_build_head": proof.get("build_head")
        == native_proof.get("proof_build_head")
        == native_proof.get("build_head")
        == expected_build_head,
        "native_proof_nested_exit_zero": nested_exit_zero,
        "native_proof_fixed_nested_executable": nested_executable_path
        == expected_nested_executable.resolve(),
        "native_proof_nested_executable_unchanged": native_proof.get(
            "nested_executable_sha256"
        )
        == native_proof.get("nested_executable_sha256_after"),
        "native_proof_nested_exact_schema": True,
        "native_proof_nested_schema_id": nested_proof.get("schema_id")
        == auditor.NESTED_PROOF_SCHEMA,
        "native_proof_nested_test_id": nested_proof.get("test_id")
        == auditor.NESTED_PROOF_TEST_ID,
        "native_proof_nested_assertion": nested_proof.get(nested_assertion) is True,
        "native_proof_nested_same_build_head": nested_proof.get("build_head")
        == native_proof.get("nested_proof_build_head")
        == native_proof.get("build_head")
        == expected_build_head,
        "native_proof_g32_binary_unchanged": native_proof.get(
            "g32_binary_sha256"
        )
        == native_proof.get("g32_binary_sha256_after"),
    }
    if set(recomputed_gates) != NATIVE_PROOF_GATE_NAMES:
        raise SelectionError("synthetic native proof replay gate schema is incomplete")
    if any(
        native_gates[name].get("pass") is not passed
        for name, passed in recomputed_gates.items()
    ):
        raise SelectionError("synthetic native proof gate replay changed")
    if not all(recomputed_gates.values()):
        raise SelectionError("synthetic native proof raw evidence did not pass")


def _validate_cross_binary_evidence(
    cross_binary: Mapping[str, Any],
    *,
    cross_gates: Mapping[str, Mapping[str, Any]],
    stage0_gates: Mapping[str, Mapping[str, Any]],
    auditor: Any,
    expected_g32_binary_sha256: str,
    expected_g32_binary_path: Any,
) -> None:
    runs = _mapping(cross_binary.get("runs"), "synthetic cross-binary runs")
    if tuple(runs) != CROSS_BINARY_RUN_NAMES:
        raise SelectionError("synthetic cross-binary run labels/order changed")

    expected_g32_path = _resolved_evidence_path(
        expected_g32_binary_path, "synthetic cross-binary expected G32 path"
    )
    expected_g31_path = Path(auditor.G31_BINARY).resolve()
    expected_accounting_keys = set(auditor.ORDINARY_RESOURCE_SUMMARY_KEYS)
    validated_runs: dict[str, Mapping[str, Any]] = {}
    for name in CROSS_BINARY_RUN_NAMES:
        run = _mapping(runs.get(name), f"synthetic cross-binary {name}")
        _exact_keys(run, CROSS_BINARY_RUN_KEYS, f"synthetic cross-binary {name}")
        ordinary = _mapping(
            run.get("ordinary"), f"synthetic cross-binary {name}.ordinary"
        )
        accounting = _mapping(
            run.get("accounting"), f"synthetic cross-binary {name}.accounting"
        )
        _exact_keys(
            ordinary,
            ORDINARY_PAYLOAD_HASH_NAMES,
            f"synthetic cross-binary {name}.ordinary",
        )
        _exact_keys(
            accounting,
            expected_accounting_keys,
            f"synthetic cross-binary {name}.accounting",
        )
        if (
            run.get("schema") != CROSS_BINARY_WORKER_SCHEMA
            or not _sha256_text(run.get("binary_sha256"))
            or not _sha256_text(run.get("request_sha256"))
            or not _sha256_text(run.get("ordinary_request_sha256"))
            or any(not _sha256_text(value) for value in ordinary.values())
            or any(
                _finite(value, f"synthetic cross-binary {name}.accounting") < 0.0
                for value in accounting.values()
            )
            or run.get("extension_absent") is not True
        ):
            raise SelectionError("synthetic cross-binary worker evidence is invalid")
        run_path = _resolved_evidence_path(
            run.get("binary_path"), f"synthetic cross-binary {name}.binary_path"
        )
        if name == "g31_parent":
            if (
                run_path != expected_g31_path
                or run.get("binary_sha256") != auditor.G31_BINARY_SHA256
            ):
                raise SelectionError("synthetic cross-binary G31 identity changed")
        elif (
            run_path != expected_g32_path
            or run.get("binary_sha256") != expected_g32_binary_sha256
        ):
            raise SelectionError("synthetic cross-binary G32 identity changed")
        validated_runs[name] = run

    request_hashes = {
        str(run["ordinary_request_sha256"]) for run in validated_runs.values()
    }
    ordinary_hashes = {
        canonical_sha256(run["ordinary"]) for run in validated_runs.values()
    }
    accounting_hashes = {
        canonical_sha256(run["accounting"]) for run in validated_runs.values()
    }
    omitted_request_sha = validated_runs["g31_parent"]["request_sha256"]
    explicit_request_sha = validated_runs["g32_explicit"]["request_sha256"]
    if (
        validated_runs["g32_omitted"]["request_sha256"] != omitted_request_sha
        or validated_runs["g32_repeated"]["request_sha256"]
        != explicit_request_sha
        or omitted_request_sha == explicit_request_sha
    ):
        raise SelectionError("synthetic cross-binary request modes are unbound")

    g32_runs = [
        validated_runs[name]
        for name in ("g32_omitted", "g32_explicit", "g32_repeated")
    ]
    recomputed_gates = {
        "cross_binary_exact_ordinary_request": len(request_hashes) == 1,
        "cross_binary_exact_off_payload": len(ordinary_hashes) == 1,
        "cross_binary_exact_off_accounting": len(accounting_hashes) == 1,
        "cross_binary_exact_off_extension_absent": all(
            run["extension_absent"] is True for run in validated_runs.values()
        ),
        "g31_release_binary_exact": validated_runs["g31_parent"]["binary_sha256"]
        == auditor.G31_BINARY_SHA256,
        "g32_omitted_explicit_repeated": len(
            {canonical_sha256(run["ordinary"]) for run in g32_runs}
        )
        == 1
        and len({canonical_sha256(run["accounting"]) for run in g32_runs}) == 1,
    }
    if set(recomputed_gates) != CROSS_BINARY_GATE_NAMES or any(
        cross_gates[name].get("pass") is not passed
        for name, passed in recomputed_gates.items()
    ):
        raise SelectionError("synthetic cross-binary gate replay changed")
    if not all(recomputed_gates.values()):
        raise SelectionError("synthetic cross-binary raw evidence did not pass")
    stage0_cross_pass = (
        cross_binary.get("pass") is True
        and all(
            run["binary_sha256"] == expected_g32_binary_sha256
            for name, run in validated_runs.items()
            if name.startswith("g32_")
        )
    )
    if stage0_gates["cross_binary_exact_off"].get("pass") is not stage0_cross_pass:
        raise SelectionError("synthetic Stage0 cross-binary gate replay changed")


def _validate_ordinary_hash_vector(value: Any, label: str) -> Mapping[str, Any]:
    hashes = _mapping(value, label)
    _exact_keys(hashes, ORDINARY_PAYLOAD_HASH_NAMES, label)
    if any(not _sha256_text(item) for item in hashes.values()):
        raise SelectionError(f"{label} contains an invalid SHA-256")
    return hashes


def _fixture_row_identity(row: Mapping[str, Any], label: str) -> tuple[str, int, int]:
    case_id = row.get("case_id")
    if not isinstance(case_id, str) or not case_id:
        raise SelectionError(f"{label}.case_id is invalid")
    ordinal = _integer(row.get("observation_ordinal"), f"{label}.observation_ordinal")
    opportunity = _integer(row.get("opportunity_id"), f"{label}.opportunity_id")
    if ordinal <= 0 or opportunity <= 0:
        raise SelectionError(f"{label} identity must be positive")
    return case_id, ordinal, opportunity


def _validate_fixture_rows_and_pairs(
    value: Mapping[str, Any], label: str
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    rows = _rows(value.get("rows"), f"{label}.rows")
    pairs = _rows(value.get("pairs"), f"{label}.pairs")
    row_identities = [
        _fixture_row_identity(row, f"{label}.rows[{index}]")
        for index, row in enumerate(rows)
    ]
    pair_identities: list[tuple[str, int, int]] = []
    for index, pair in enumerate(pairs):
        _exact_keys(pair, JOIN_PAIR_KEYS, f"{label}.pairs[{index}]")
        pair_identities.append(
            _fixture_row_identity(pair, f"{label}.pairs[{index}]")
        )
    if (
        len(set(row_identities)) != len(row_identities)
        or len(set(pair_identities)) != len(pair_identities)
        or set(row_identities) != set(pair_identities)
    ):
        raise SelectionError(f"{label} row/pair association changed")
    return rows, pairs


def _validate_case_fixture(
    value: Any, label: str
) -> tuple[
    Mapping[str, Any],
    list[Mapping[str, Any]],
    list[Mapping[str, Any]],
    Mapping[str, Any],
    Mapping[str, Any],
]:
    fixture = _mapping(value, label)
    _exact_keys(fixture, STAGE0_CASE_FIXTURE_KEYS, label)
    rows, pairs = _validate_fixture_rows_and_pairs(fixture, label)
    off_hashes = _validate_ordinary_hash_vector(
        fixture.get("off_ordinary_hashes"), f"{label}.off_ordinary_hashes"
    )
    shadow_hashes = _validate_ordinary_hash_vector(
        fixture.get("shadow_ordinary_hashes"), f"{label}.shadow_ordinary_hashes"
    )
    return fixture, rows, pairs, off_hashes, shadow_hashes


def _physical_commit_identity(row: Mapping[str, Any], label: str) -> tuple[Any, ...]:
    path = _integer(row.get("external_path_code"), f"{label}.external_path_code")
    common = tuple(
        _integer(row.get(name), f"{label}.{name}")
        for name in (
            "external_runtime_bag_id",
            "external_task_id",
            "external_upstream_node",
            "node",
        )
    )
    if path == 1:
        return (
            "DIRECT",
            _integer(
                row.get("external_direct_episode_event_seq"),
                f"{label}.external_direct_episode_event_seq",
            ),
            *common,
        )
    if path == 2:
        return (
            "J2",
            *(
                _integer(row.get(name), f"{label}.{name}")
                for name in STAGE0_J2_IDENTITY_FIELDS
            ),
            *common,
        )
    raise SelectionError(f"{label}.external_path_code must be 1 or 2")


def _validate_probe_audit(
    value: Any,
    *,
    bag_count: int,
    exact_l: bool,
    expected_exact_node: int | None,
    expected_goal_by_runtime: Mapping[int, int],
    expected_service_by_node: Mapping[int, float],
    expected_origins: set[str],
    expected_case_id: str,
    joined_status: str,
    label: str,
) -> Mapping[str, Any]:
    probe = _mapping(value, label)
    _exact_keys(probe, STAGE0_PROBE_AUDIT_KEYS, label)
    rows, pairs = _validate_fixture_rows_and_pairs(probe, label)
    if any(row.get("case_id") != expected_case_id for row in [*rows, *pairs]):
        raise SelectionError(f"{label} case identity changed")
    _validate_census_evidence(
        probe.get("census"), row_count=len(rows), label=f"{label}.census"
    )
    _validate_service_audit_evidence(
        probe.get("service"),
        bag_count=bag_count,
        exact_l=exact_l,
        expected_exact_node=expected_exact_node,
        expected_goal_by_runtime=expected_goal_by_runtime,
        expected_service_by_node=expected_service_by_node,
        label=f"{label}.service",
    )
    service = _mapping(probe.get("service"), f"{label}.service")
    if not expected_origins <= set(service.get("origins", [])):
        raise SelectionError(f"{label} required origin coverage changed")
    if probe.get("off_ordinary_hashes") is not None:
        raise SelectionError(f"{label} must not fabricate an off payload")
    _validate_ordinary_hash_vector(
        probe.get("shadow_ordinary_hashes"), f"{label}.shadow_ordinary_hashes"
    )
    passed = (
        probe.get("join_status") == joined_status
        and probe["census"]["pass"] is True
        and probe["service"]["pass"] is True
    )
    if probe.get("row_count") != len(rows) or probe.get("pass") is not passed:
        raise SelectionError(f"{label} completion/join/census replay changed")
    return probe


def _validate_resource_gate_summary(value: Any, label: str) -> Mapping[str, Any]:
    resources = _mapping(value, label)
    _exact_keys(resources, {"pass", "gates"}, label)
    gates = _validate_gate_vector(
        resources.get("gates"), RESOURCE_GATE_NAMES, f"{label}.gates"
    )
    for name, gate in gates.items():
        evidence = _mapping(gate.get("evidence"), f"{label}.{name}.evidence")
        _exact_keys(
            evidence, {"limit", "max_ratio", "non_finite"}, f"{label}.{name}.evidence"
        )
        limit = _finite(evidence.get("limit"), f"{label}.{name}.limit")
        maximum = _finite(evidence.get("max_ratio"), f"{label}.{name}.max_ratio")
        non_finite = _integer(
            evidence.get("non_finite"), f"{label}.{name}.non_finite"
        )
        passed = (
            limit == RESOURCE_RATIO_LIMIT
            and maximum >= 0.0
            and maximum <= limit
            and non_finite == 0
        )
        if gate.get("pass") is not passed:
            raise SelectionError(f"{label}.{name} resource summary replay changed")
    if resources.get("pass") is not all(
        gate.get("pass") is True for gate in gates.values()
    ):
        raise SelectionError(f"{label} parent resource pass changed")
    return resources


def _validate_map2_raw_evidence(
    map2: Mapping[str, Any],
    *,
    map2_gates: Mapping[str, Mapping[str, Any]],
    fixture: Any,
    auditor: Any,
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]], Mapping[str, Any]]:
    _exact_keys(map2, STAGE0_MAP2_KEYS, "synthetic.stage0.map2")
    hashes = _mapping(map2.get("hashes"), "synthetic.stage0.map2.hashes")
    expected_hashes = {
        "raw": auditor.MAP2_RAW_SHA256,
        "profile": auditor.MAP2_PROFILE_SHA256,
        "potential": auditor.MAP2_POTENTIAL_SHA256,
        "rows": auditor.MAP2_ROWS_SHA256,
        "segments": list(auditor.MAP2_SEGMENTS),
        "storage_source_nodes": [52],
    }
    _exact_keys(hashes, set(expected_hashes), "map2 hashes")
    if hashes != expected_hashes:
        raise SelectionError("synthetic Stage0 map2 frozen identity changed")
    try:
        map2_request, rebuilt_hashes = auditor.map2_fixture(
            mode="off", binary=None
        )
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise SelectionError("synthetic Stage0 map2 request cannot be rebuilt") from error
    if rebuilt_hashes != expected_hashes:
        raise SelectionError("synthetic Stage0 map2 request identity changed")
    map2_goals = _goal_map_from_request(
        map2_request, bag_count=8, label="synthetic.stage0.map2.request"
    )
    map2_services = _service_profile_from_request(
        map2_request, label="synthetic.stage0.map2.request"
    )

    _validate_service_audit_evidence(
        map2.get("off_audit"),
        bag_count=8,
        exact_l=False,
        expected_exact_node=None,
        expected_goal_by_runtime=map2_goals,
        expected_service_by_node=map2_services,
        label="synthetic.stage0.map2.off_audit",
    )
    _validate_service_audit_evidence(
        map2.get("shadow_audit"),
        bag_count=8,
        exact_l=False,
        expected_exact_node=None,
        expected_goal_by_runtime=map2_goals,
        expected_service_by_node=map2_services,
        label="synthetic.stage0.map2.shadow_audit",
    )
    _validate_legacy_pair_evidence(
        map2.get("legacy_wait_over_120"),
        "synthetic.stage0.map2.legacy_wait",
    )
    sequence = _validate_boolean_checks(
        map2.get("service_sequence_parity"),
        {
            "sequence_sha256",
            "origin_sequence_sha256",
            "maximum_consecutive_origin_run",
        },
        "synthetic.stage0.map2.service_sequence_parity",
    )
    off_sequence = map2["off_audit"]["service_sequence"]
    shadow_sequence = map2["shadow_audit"]["service_sequence"]
    sequence_recomputed = {
        key: off_sequence[key] == shadow_sequence[key] for key in sequence
    }
    if sequence != sequence_recomputed:
        raise SelectionError("synthetic Stage0 map2 sequence parity changed")

    map2_rows, map2_pairs = _validate_fixture_rows_and_pairs(
        map2, "synthetic.stage0.map2"
    )
    _validate_census_evidence(
        map2.get("census"),
        row_count=len(map2_rows),
        label="synthetic.stage0.map2.census",
    )
    off_hashes = _validate_ordinary_hash_vector(
        map2.get("off_ordinary_hashes"),
        "synthetic.stage0.map2.off_ordinary_hashes",
    )
    shadow_hashes = _validate_ordinary_hash_vector(
        map2.get("shadow_ordinary_hashes"),
        "synthetic.stage0.map2.shadow_ordinary_hashes",
    )
    resources = _validate_resource_gate_summary(
        map2.get("resources"), "synthetic.stage0.map2.resources"
    )
    fixture_mapping, fixture_rows, fixture_pairs, fixture_off, fixture_shadow = (
        _validate_case_fixture(fixture, "synthetic.stage0.fixtures.map2")
    )
    if (
        fixture_mapping.get("rows") != map2_rows
        or fixture_mapping.get("pairs") != map2_pairs
        or fixture_rows != map2_rows
        or fixture_pairs != map2_pairs
        or fixture_off != off_hashes
        or fixture_shadow != shadow_hashes
    ):
        raise SelectionError("synthetic Stage0 map2 fixture binding changed")

    recomputed = {
        "map2_frozen_hashes": hashes == expected_hashes,
        "map2_completion_safety": map2["off_audit"]["pass"] is True
        and map2["shadow_audit"]["pass"] is True,
        "map2_legacy_wait_exact": map2["legacy_wait_over_120"]["pass"] is True,
        "map2_service_sequence_exact": all(sequence.values()),
        "map2_exact_no_mutation": off_hashes == shadow_hashes,
        "map2_join_census": map2.get("join_status") == auditor.JOINED
        and map2["census"]["pass"] is True,
        "map2_resource": resources.get("pass") is True,
    }
    if any(
        map2_gates[name].get("pass") is not passed
        for name, passed in recomputed.items()
    ) or not all(recomputed.values()):
        raise SelectionError("synthetic Stage0 map2 raw gate replay changed")
    if (
        map2.get("row_count") != len(map2_rows)
        or map2.get("rows_sha256") != canonical_sha256(map2_rows)
        or map2.get("pairs_sha256") != canonical_sha256(map2_pairs)
        or map2.get("pass")
        is not all(gate.get("pass") is True for gate in map2_gates.values())
    ):
        raise SelectionError("synthetic Stage0 map2 aggregate evidence changed")
    return map2_rows, map2_pairs, resources


def _validate_stage0_fixture_probe_evidence(
    stage0: Mapping[str, Any],
    *,
    stage0_cases: Sequence[Mapping[str, Any]],
    stage0_gates: Mapping[str, Mapping[str, Any]],
    map2: Mapping[str, Any],
    map2_gates: Mapping[str, Mapping[str, Any]],
    auditor: Any,
    expected_binary_sha256: str,
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]], Mapping[str, Any]]:
    fixtures = _mapping(stage0.get("fixtures"), "synthetic.stage0.fixtures")
    if set(fixtures) != STAGE0_FIXTURE_NAMES:
        raise SelectionError("synthetic Stage0 fixture set changed")
    if len(stage0_cases) != len(STAGE0_CASE_ROLES):
        raise SelectionError("synthetic Stage0 must contain the exact four motif roles")

    validated_fixtures: dict[
        str,
        tuple[
            Mapping[str, Any],
            list[Mapping[str, Any]],
            list[Mapping[str, Any]],
            Mapping[str, Any],
            Mapping[str, Any],
        ],
    ] = {}
    for fixture_name, _flow, _negative in STAGE0_CASE_ROLES:
        validated_fixtures[fixture_name] = _validate_case_fixture(
            fixtures.get(fixture_name), f"synthetic.stage0.fixtures.{fixture_name}"
        )

    for index, (fixture_name, flow, negative) in enumerate(STAGE0_CASE_ROLES):
        case = stage0_cases[index]
        _fixture, rows, pairs, off_hashes, shadow_hashes = validated_fixtures[
            fixture_name
        ]
        expected_case_id = f"v3r2_{flow}__n8__service_1p0s"
        if (
            case.get("case_id") != expected_case_id
            or case.get("service_seconds") != 1.0
            or case.get("bag_count") != 8
            or case.get("flow_pattern") != flow
            or case.get("negative_control") is not negative
            or case.get("admitted_row_count") != len(rows)
            or case.get("rows_sha256") != canonical_sha256(rows)
            or case.get("pairs_sha256") != canonical_sha256(pairs)
            or case.get("off_hashes") != off_hashes
            or case.get("shadow_hashes") != shadow_hashes
        ):
            raise SelectionError(f"synthetic Stage0 {fixture_name} role binding changed")

    direct_rows = validated_fixtures["direct"][1]
    j2_rows = validated_fixtures["j2"][1]
    direct_identities = [
        _physical_commit_identity(row, f"synthetic direct row[{index}]")
        for index, row in enumerate(direct_rows)
    ]
    j2_identities = [
        _physical_commit_identity(row, f"synthetic j2 row[{index}]")
        for index, row in enumerate(j2_rows)
    ]
    direct_unique = (
        bool(direct_rows)
        and all(row.get("external_path_code") == 1 for row in direct_rows)
        and len(set(direct_identities)) == len(direct_identities)
    )
    j2_unique = (
        bool(j2_rows)
        and all(row.get("external_path_code") == 2 for row in j2_rows)
        and len(set(j2_identities)) == len(j2_identities)
    )

    repeated, repeated_rows, repeated_pairs, repeated_off, repeated_shadow = (
        _validate_case_fixture(
            fixtures.get("repeated_shadow"),
            "synthetic.stage0.fixtures.repeated_shadow",
        )
    )
    direct_fixture, direct_fixture_rows, direct_fixture_pairs, direct_off, direct_shadow = (
        validated_fixtures["direct"]
    )
    if (
        repeated_rows != direct_fixture_rows
        or repeated_pairs != direct_fixture_pairs
        or repeated_off != direct_off
        or repeated_shadow != direct_shadow
        or repeated.get("rows") != direct_fixture.get("rows")
    ):
        raise SelectionError("synthetic Stage0 repeated shadow fixture changed")
    repeat_evidence = _mapping(
        stage0_gates["shadow_repeat_exact"].get("evidence"),
        "synthetic.stage0.shadow_repeat_exact.evidence",
    )
    _exact_keys(
        repeat_evidence,
        {"hashes", "repeat_census", "repeat_resources", "error"},
        "synthetic.stage0.shadow_repeat_exact.evidence",
    )
    repeat_hashes = _mapping(
        repeat_evidence.get("hashes"), "synthetic Stage0 repeat hashes"
    )
    _exact_keys(
        repeat_hashes,
        {"ordinary", "extension", "rows", "join"},
        "synthetic Stage0 repeat hashes",
    )
    for name, pair in repeat_hashes.items():
        if (
            not isinstance(pair, list)
            or len(pair) != 2
            or any(not _sha256_text(item) for item in pair)
        ):
            raise SelectionError(f"synthetic Stage0 repeat {name} hash pair is invalid")
    if (
        repeat_hashes["ordinary"]
        != [canonical_sha256(direct_shadow), canonical_sha256(repeated_shadow)]
        or repeat_hashes["rows"]
        != [canonical_sha256(direct_rows), canonical_sha256(repeated_rows)]
        or repeat_evidence.get("error") is not None
    ):
        raise SelectionError("synthetic Stage0 repeat raw hashes are unbound")
    _validate_census_evidence(
        repeat_evidence.get("repeat_census"),
        row_count=len(repeated_rows),
        label="synthetic Stage0 repeat census",
    )
    _validate_resource_values(
        repeat_evidence.get("repeat_resources"),
        "synthetic Stage0 repeat resources",
    )
    repeat_pass = all(pair[0] == pair[1] for pair in repeat_hashes.values()) and (
        repeat_evidence["repeat_census"]["pass"] is True
    )

    probes = _mapping(stage0.get("probes"), "synthetic.stage0.probes")
    _exact_keys(probes, {"future", "distant"}, "synthetic.stage0.probes")
    future = _mapping(probes.get("future"), "synthetic.stage0.probes.future")
    _exact_keys(
        future,
        {
            "request_a_sha256",
            "request_b_sha256",
            "profile_a_sha256",
            "profile_b_sha256",
            "potential_a_sha256",
            "potential_b_sha256",
            "prefix_sha256",
            "audit",
        },
        "synthetic.stage0.probes.future",
    )
    if any(
        not _sha256_text(future.get(name))
        for name in (
            "request_a_sha256",
            "request_b_sha256",
            "profile_a_sha256",
            "profile_b_sha256",
            "potential_a_sha256",
            "potential_b_sha256",
        )
    ):
        raise SelectionError("synthetic Stage0 future probe hashes are invalid")
    future_prefix = _mapping(
        future.get("prefix_sha256"), "synthetic.stage0.probes.future.prefix"
    )
    _exact_keys(future_prefix, {"a", "b"}, "synthetic future prefix")
    if any(not _sha256_text(item) for item in future_prefix.values()):
        raise SelectionError("synthetic Stage0 future prefix hashes are invalid")
    future_audits = _rows(future.get("audit"), "synthetic Stage0 future audits")
    if len(future_audits) != 2:
        raise SelectionError("synthetic Stage0 future probe cardinality changed")
    try:
        anchor = auditor.V3R2Case(1.0, 8, "simultaneous_local_first")
        future_requests = (
            auditor._future_request(anchor, (100.0, 120.0), None),
            auditor._future_request(anchor, (500.0, 600.0), None),
        )
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise SelectionError("synthetic Stage0 future requests cannot be rebuilt") from error
    future_goals = tuple(
        _goal_map_from_request(
            request,
            bag_count=10,
            label=f"synthetic.stage0.probes.future.request[{index}]",
        )
        for index, request in enumerate(future_requests)
    )
    future_services = tuple(
        _service_profile_from_request(
            request, label=f"synthetic.stage0.probes.future.request[{index}]"
        )
        for index, request in enumerate(future_requests)
    )
    expected_future_hashes = {
        "request_a_sha256": auditor.request_sha256(future_requests[0]),
        "request_b_sha256": auditor.request_sha256(future_requests[1]),
        "profile_a_sha256": auditor.profile_sha256(future_requests[0]),
        "profile_b_sha256": auditor.profile_sha256(future_requests[1]),
        "potential_a_sha256": canonical_sha256(
            future_requests[0].get("heuristic_time")
        ),
        "potential_b_sha256": canonical_sha256(
            future_requests[1].get("heuristic_time")
        ),
    }
    if any(future.get(name) != digest for name, digest in expected_future_hashes.items()):
        raise SelectionError("synthetic Stage0 future request identity changed")
    future_a = _validate_probe_audit(
        future_audits[0],
        bag_count=10,
        exact_l=True,
        expected_exact_node=SYNTHETIC_EXACT_SERVICE_NODE,
        expected_goal_by_runtime=future_goals[0],
        expected_service_by_node=future_services[0],
        expected_origins={"external", "local"},
        expected_case_id="v3r2_future_a",
        joined_status=auditor.JOINED,
        label="synthetic.stage0.probes.future.audit[0]",
    )
    future_b = _validate_probe_audit(
        future_audits[1],
        bag_count=10,
        exact_l=True,
        expected_exact_node=SYNTHETIC_EXACT_SERVICE_NODE,
        expected_goal_by_runtime=future_goals[1],
        expected_service_by_node=future_services[1],
        expected_origins={"external", "local"},
        expected_case_id="v3r2_future_b",
        joined_status=auditor.JOINED,
        label="synthetic.stage0.probes.future.audit[1]",
    )
    if (
        fixtures.get("future_a") != future_a
        or fixtures.get("future_b") != future_b
    ):
        raise SelectionError("synthetic Stage0 future fixture binding changed")

    distant = _mapping(probes.get("distant"), "synthetic.stage0.probes.distant")
    _exact_keys(
        distant,
        {
            "request_sha256",
            "profile_sha256",
            "potential_sha256",
            "prefix_sha256",
            "audit",
        },
        "synthetic.stage0.probes.distant",
    )
    if any(
        not _sha256_text(distant.get(name))
        for name in ("request_sha256", "profile_sha256", "potential_sha256")
    ):
        raise SelectionError("synthetic Stage0 distant probe hashes are invalid")
    distant_prefix = _mapping(
        distant.get("prefix_sha256"), "synthetic.stage0.probes.distant.prefix"
    )
    _exact_keys(distant_prefix, {"direct", "distant"}, "synthetic distant prefix")
    if any(not _sha256_text(item) for item in distant_prefix.values()):
        raise SelectionError("synthetic Stage0 distant prefix hashes are invalid")
    try:
        distant_request = auditor._distant_request(anchor, None)
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise SelectionError("synthetic Stage0 distant request cannot be rebuilt") from error
    distant_goals = _goal_map_from_request(
        distant_request,
        bag_count=9,
        label="synthetic.stage0.probes.distant.request",
    )
    distant_services = _service_profile_from_request(
        distant_request, label="synthetic.stage0.probes.distant.request"
    )
    expected_distant_hashes = {
        "request_sha256": auditor.request_sha256(distant_request),
        "profile_sha256": auditor.profile_sha256(distant_request),
        "potential_sha256": canonical_sha256(
            distant_request.get("heuristic_time")
        ),
    }
    if any(
        distant.get(name) != digest
        for name, digest in expected_distant_hashes.items()
    ):
        raise SelectionError("synthetic Stage0 distant request identity changed")
    distant_audit = _validate_probe_audit(
        distant.get("audit"),
        bag_count=9,
        exact_l=False,
        expected_exact_node=None,
        expected_goal_by_runtime=distant_goals,
        expected_service_by_node=distant_services,
        expected_origins={"external", "local", "distant"},
        expected_case_id="v3r2_distant",
        joined_status=auditor.JOINED,
        label="synthetic.stage0.probes.distant.audit",
    )
    if fixtures.get("distant") != distant_audit:
        raise SelectionError("synthetic Stage0 distant fixture binding changed")

    map2_rows, map2_pairs, map2_resources = _validate_map2_raw_evidence(
        map2,
        map2_gates=map2_gates,
        fixture=fixtures.get("map2"),
        auditor=auditor,
    )
    own_recomputed = {
        "stage0_execution": stage0.get("error") is None,
        "native_proof": stage0.get("native_proof", {}).get("pass") is True
        and stage0.get("native_proof", {}).get("g32_binary_sha256")
        == expected_binary_sha256,
        "native_artifacts_implementation_head": stage0.get(
            "native_proof", {}
        ).get("build_head")
        == stage0.get("native_proof", {}).get("proof_build_head"),
        "shadow_repeat_exact": repeat_pass,
        "direct_unique_publish": direct_unique,
        "j2_unique_publish": j2_unique,
        "no_direct_j2_double_publish": j2_unique,
        "motif_controls_safety_census": all(
            case.get("hard_gate_pass") is True for case in stage0_cases
        )
        and all(
            case.get("admitted_row_count") == 0
            for case in stage0_cases
            if case.get("negative_control") is True
        ),
        "motif_g32_binary": all(
            case.get("loaded_cpp_binary_sha256") == expected_binary_sha256
            for case in stage0_cases
        ),
        "future_probe_completion_safety_join_census": future_a.get("pass") is True
        and future_b.get("pass") is True,
        "future_release_prefix_exact": future_prefix.get("a")
        == future_prefix.get("b"),
        "distant_probe_completion_safety_join_census": distant_audit.get("pass")
        is True,
        "distant_L_prefix_exact": distant_prefix.get("direct")
        == distant_prefix.get("distant"),
        "map2_sentinel": map2.get("pass") is True,
    }
    if any(
        stage0_gates[name].get("pass") is not passed
        for name, passed in own_recomputed.items()
    ) or not all(own_recomputed.values()):
        raise SelectionError("synthetic Stage0 fixture/probe gate replay changed")
    return map2_rows, map2_pairs, map2_resources


def load_and_validate_synthetic_artifact(
    value: Path,
    *,
    expected_file_sha256: str,
    expected_g32_binary_sha256: str,
    auditor: Any | None = None,
) -> tuple[dict[str, Any], str]:
    selected_auditor = auditor or _v3_auditor()
    if not isinstance(value, Path):
        raise TypeError("synthetic artifact must be supplied as a Path")
    registered_synthetic_path = Path(selected_auditor.OUTPUT_JSON)
    if value.resolve() != registered_synthetic_path.resolve():
        raise SelectionError("synthetic artifact is not at the registered output path")
    loaded, file_hash = _load_bound_json(
        value, expected_file_sha256, label="synthetic artifact"
    )
    _exact_keys(
        loaded,
        {
            "schema",
            "synthetic_revision_id",
            "campaign_revision_id",
            "historical_control_revision_id",
            "status",
            "decision",
            "synthetic_pass",
            "nanning_p0_status",
            "p1_review_authorized",
            "protocol",
            "source_bundle",
            "source_bundle_checkpoints",
            "implementation",
            "implementation_head",
            "g32_binary_sha256",
            "issue_remediation_ledger_file",
            "bootstrap",
            "resource_ratio_limit",
            "stage0",
            "stage1",
            "issue_remediation_ledger",
            "artifact_content_sha256",
        },
        "synthetic artifact",
    )
    verify_content_hash(loaded)
    stage0 = _mapping(loaded.get("stage0"), "synthetic.stage0")
    _exact_keys(
        stage0,
        {
            "pass",
            "status",
            "gates",
            "native_proof",
            "cross_binary",
            "cases",
            "map2",
            "probes",
            "fixtures",
            "error",
        },
        "synthetic.stage0",
    )
    stage1 = _mapping(loaded.get("stage1"), "synthetic.stage1")
    implementation = _mapping(
        loaded.get("implementation"), "synthetic.implementation"
    )
    protocol = _mapping(loaded.get("protocol"), "synthetic.protocol")
    checkpoints = _mapping(
        loaded.get("source_bundle_checkpoints"), "synthetic source checkpoints"
    )
    source_bundle = _mapping(loaded.get("source_bundle"), "synthetic source bundle")
    auditor_resource_ratio_limit = _finite(
        getattr(selected_auditor, "RESOURCE_RATIO_LIMIT", None),
        "synthetic auditor resource ratio limit",
    )
    artifact_resource_ratio_limit = _finite(
        loaded.get("resource_ratio_limit"), "synthetic resource ratio limit"
    )
    if (
        auditor_resource_ratio_limit != RESOURCE_RATIO_LIMIT
        or artifact_resource_ratio_limit != auditor_resource_ratio_limit
    ):
        raise SelectionError("synthetic resource ratio limit differs from fixed 1.10")
    stage0_gates = _validate_gate_vector(
        stage0.get("gates"), STAGE0_GATE_NAMES, "synthetic.stage0.gates"
    )
    stage1_gates = _validate_gate_vector(
        stage1.get("gates"), STAGE1_GATE_NAMES, "synthetic.stage1.gates"
    )
    implementation_gates = _validate_gate_vector(
        implementation.get("gates"),
        IMPLEMENTATION_GATE_NAMES,
        "synthetic.implementation.gates",
    )
    protocol_cohorts = _mapping(protocol.get("cohorts"), "synthetic.protocol.cohorts")
    if set(protocol_cohorts) != {"safety_regression", "identification"}:
        raise SelectionError("synthetic protocol must contain exact dual cohorts")
    safety_protocol = _mapping(
        protocol_cohorts.get("safety_regression"),
        "synthetic.protocol.safety_regression",
    )
    identification_protocol = _mapping(
        protocol_cohorts.get("identification"),
        "synthetic.protocol.identification",
    )
    safety_stage = _mapping(
        stage1.get("safety_regression"), "synthetic.stage1.safety_regression"
    )
    identification_stage = _mapping(
        stage1.get("identification"), "synthetic.stage1.identification"
    )
    safety_cases = _rows(
        safety_stage.get("cases"), "synthetic.stage1.safety.cases"
    )
    identification_cases = _rows(
        identification_stage.get("cases"),
        "synthetic.stage1.identification.cases",
    )
    safety_protocol_cases = _rows(
        safety_protocol.get("cases"), "synthetic.protocol.safety.cases"
    )
    identification_protocol_cases = _rows(
        identification_protocol.get("cases"),
        "synthetic.protocol.identification.cases",
    )
    safety_observations = _rows(
        safety_stage.get("observations"), "synthetic.stage1.safety.observations"
    )
    identification_observations = _rows(
        identification_stage.get("observations"),
        "synthetic.stage1.identification.observations",
    )
    safety_pairs = _rows(
        safety_stage.get("pairs"), "synthetic.stage1.safety.pairs"
    )
    identification_pairs = _rows(
        identification_stage.get("pairs"),
        "synthetic.stage1.identification.pairs",
    )
    safety_case_ids = [row.get("case_id") for row in safety_cases]
    identification_case_ids = [row.get("case_id") for row in identification_cases]
    safety_protocol_case_ids = [
        row.get("case_id") for row in safety_protocol_cases
    ]
    identification_protocol_case_ids = [
        row.get("case_id") for row in identification_protocol_cases
    ]
    head = implementation.get("head")
    native_proof = _mapping(
        stage0.get("native_proof"), "synthetic.stage0.native_proof"
    )
    cross_binary = _mapping(
        stage0.get("cross_binary"), "synthetic.stage0.cross_binary"
    )
    map2 = _mapping(stage0.get("map2"), "synthetic.stage0.map2")
    native_gates = _validate_gate_vector(
        native_proof.get("gates"),
        NATIVE_PROOF_GATE_NAMES,
        "synthetic.stage0.native_proof.gates",
    )
    cross_gates = _validate_gate_vector(
        cross_binary.get("gates"),
        CROSS_BINARY_GATE_NAMES,
        "synthetic.stage0.cross_binary.gates",
    )
    map2_gates = _validate_gate_vector(
        map2.get("gates"), MAP2_GATE_NAMES, "synthetic.stage0.map2.gates"
    )
    for nested in (implementation_gates, native_gates, cross_gates, map2_gates):
        if any(stage0_gates[name] != gate for name, gate in nested.items()):
            raise SelectionError("synthetic Stage0 flattened gate evidence changed")
    current_protocol = selected_auditor.population_manifest()
    current_protocol_cohorts = _mapping(
        current_protocol.get("cohorts"), "current synthetic protocol cohorts"
    )
    current_safety_protocol_cases = _rows(
        _mapping(
            current_protocol_cohorts.get("safety_regression"),
            "current safety protocol",
        ).get("cases"),
        "current safety protocol cases",
    )
    current_identification_protocol_cases = _rows(
        _mapping(
            current_protocol_cohorts.get("identification"),
            "current identification protocol",
        ).get("cases"),
        "current identification protocol cases",
    )
    current_source_bundle = selected_auditor.source_bundle_manifest()
    for index, case in enumerate(safety_cases):
        if index >= len(current_safety_protocol_cases):
            raise SelectionError("synthetic Stage1 exceeds the frozen case manifest")
        expected_manifest_case = current_safety_protocol_cases[index]
        try:
            case_spec = selected_auditor.V3R2Case(
                _finite(case.get("service_seconds"), f"stage1[{index}].service"),
                _integer(case.get("bag_count"), f"stage1[{index}].bag_count"),
                str(case.get("flow_pattern")),
            )
            expected_request = selected_auditor.build_request(
                case_spec, mode="off", binary=None
            )[0]
            expected_goals = _goal_map_from_manifest_case(
                expected_manifest_case,
                bag_count=case_spec.bag_count,
                label=f"current synthetic safety protocol cases[{index}]",
            )
            request_goals = _goal_map_from_request(
                expected_request,
                bag_count=case_spec.bag_count,
                label=f"current synthetic safety request[{index}]",
            )
            expected_services = _service_profile_from_request(
                expected_request, label=f"current synthetic safety request[{index}]"
            )
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise SelectionError(
                f"synthetic.stage1.safety.cases[{index}] request cannot be rebuilt"
            ) from error
        if expected_goals != request_goals:
            raise SelectionError(
                f"synthetic.stage1.safety.cases[{index}] manifest/request goals differ"
            )
        _validate_synthetic_case_evidence(
            case,
            expected_binary_sha256=expected_g32_binary_sha256,
            expected_manifest_case=expected_manifest_case,
            expected_goal_by_runtime=expected_goals,
            expected_service_by_node=expected_services,
            expected_exact_node=SYNTHETIC_EXACT_SERVICE_NODE,
            label=f"synthetic.stage1.safety.cases[{index}]",
        )
    _validate_stage1_case_association(
        safety_cases, safety_observations, safety_pairs, auditor=selected_auditor
    )
    for index, case in enumerate(identification_cases):
        if index >= len(current_identification_protocol_cases):
            raise SelectionError(
                "synthetic identification exceeds the frozen case manifest"
            )
        expected_manifest_case = current_identification_protocol_cases[index]
        try:
            flow_pattern = str(case.get("flow_pattern"))
            permutation = selected_auditor.IDENTIFICATION_FLOW_PATTERNS.index(
                flow_pattern
            )
            case_spec = selected_auditor.IdentificationCase(
                _finite(
                    case.get("service_seconds"),
                    f"identification[{index}].service",
                ),
                _integer(
                    case.get("bag_count"), f"identification[{index}].bag_count"
                ),
                _integer(
                    case.get("replica"), f"identification[{index}].replica"
                ),
                permutation,
            )
            expected_request = selected_auditor.build_identification_request(
                case_spec, mode="off", binary=None
            )[0]
            expected_goals = _goal_map_from_manifest_case(
                expected_manifest_case,
                bag_count=case_spec.bag_count,
                label=f"current identification protocol cases[{index}]",
            )
            request_goals = _goal_map_from_request(
                expected_request,
                bag_count=case_spec.bag_count,
                label=f"current identification request[{index}]",
            )
            expected_services = _service_profile_from_request(
                expected_request,
                label=f"current identification request[{index}]",
            )
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise SelectionError(
                f"synthetic.stage1.identification.cases[{index}] request cannot be rebuilt"
            ) from error
        if expected_goals != request_goals:
            raise SelectionError(
                f"synthetic.stage1.identification.cases[{index}] manifest/request goals differ"
            )
        _validate_synthetic_case_evidence(
            case,
            expected_binary_sha256=expected_g32_binary_sha256,
            expected_manifest_case=expected_manifest_case,
            expected_goal_by_runtime=expected_goals,
            expected_service_by_node=expected_services,
            expected_exact_node=SYNTHETIC_EXACT_SERVICE_NODE,
            label=f"synthetic.stage1.identification.cases[{index}]",
        )
    _validate_stage1_case_association(
        identification_cases,
        identification_observations,
        identification_pairs,
        auditor=selected_auditor,
    )
    stage0_cases = _rows(stage0.get("cases"), "synthetic.stage0.cases")
    if len(stage0_cases) != len(STAGE0_CASE_ROLES):
        raise SelectionError("synthetic Stage0 must contain the four frozen roles")
    for index, case in enumerate(stage0_cases):
        try:
            fixture_name, frozen_flow, frozen_negative = STAGE0_CASE_ROLES[index]
            expected_case_id = f"v3r2_{frozen_flow}__n8__service_1p0s"
            if (
                case.get("cohort") != "safety_regression"
                or case.get("replica") is not None
                or
                case.get("case_id") != expected_case_id
                or case.get("service_seconds") != 1.0
                or case.get("bag_count") != 8
                or case.get("flow_pattern") != frozen_flow
                or case.get("negative_control") is not frozen_negative
            ):
                raise SelectionError(
                    f"synthetic.stage0.cases[{index}] frozen role changed"
                )
            case_spec = selected_auditor.V3R2Case(
                1.0,
                8,
                frozen_flow,
            )
            expected_goals = _goal_map_from_bag_rows(
                selected_auditor.build_bag_rows(case_spec),
                bag_count=case_spec.bag_count,
                label=f"synthetic.stage0.cases[{index}].frozen_bag_rows",
            )
            expected_request = selected_auditor.build_request(
                case_spec,
                mode="off",
                binary=None,
                j2=fixture_name == "j2",
            )[0]
            expected_services = _service_profile_from_request(
                expected_request,
                label=f"synthetic.stage0.cases[{index}].frozen_request",
            )
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise SelectionError(
                f"synthetic.stage0.cases[{index}] request cannot be rebuilt"
            ) from error
        _validate_synthetic_case_evidence(
            case,
            expected_binary_sha256=expected_g32_binary_sha256,
            expected_manifest_case=None,
            expected_goal_by_runtime=expected_goals,
            expected_service_by_node=expected_services,
            expected_exact_node=SYNTHETIC_EXACT_SERVICE_NODE,
            label=f"synthetic.stage0.cases[{index}]",
        )
    _validate_native_proof_identity(
        native_proof,
        native_gates=native_gates,
        auditor=selected_auditor,
        expected_binary_sha256=expected_g32_binary_sha256,
        expected_build_head=str(head),
        expected_executable=Path(selected_auditor.NATIVE_PROOF_EXE),
        expected_nested_executable=Path(selected_auditor.NESTED_PROOF_EXE),
        expected_source_bundle=source_bundle,
        case_binary_paths=[
            case.get("loaded_cpp_binary_path")
            for case in [*stage0_cases, *safety_cases, *identification_cases]
        ],
    )
    _validate_cross_binary_evidence(
        cross_binary,
        cross_gates=cross_gates,
        stage0_gates=stage0_gates,
        auditor=selected_auditor,
        expected_g32_binary_sha256=expected_g32_binary_sha256,
        expected_g32_binary_path=native_proof.get("g32_binary_path"),
    )
    map2_rows, map2_pairs, map2_resources = (
        _validate_stage0_fixture_probe_evidence(
            stage0,
            stage0_cases=stage0_cases,
            stage0_gates=stage0_gates,
            map2=map2,
            map2_gates=map2_gates,
            auditor=selected_auditor,
            expected_binary_sha256=expected_g32_binary_sha256,
        )
    )
    primary = _mapping(
        identification_stage.get("primary"),
        "synthetic.stage1.identification.primary",
    )
    safety_evaluation_gates = _validate_gate_vector(
        safety_stage.get("gates"),
        SAFETY_REGRESSION_GATE_NAMES,
        "synthetic.stage1.safety.gates",
    )
    resources = _mapping(stage1.get("resources"), "synthetic.stage1.resources")
    _validate_gate_vector(
        primary.get("gates"),
        IDENTIFICATION_PRIMARY_GATE_NAMES,
        "synthetic.stage1.identification.primary.gates",
    )
    _validate_gate_vector(
        resources.get("gates"),
        RESOURCE_GATE_NAMES,
        "synthetic.stage1.resources.gates",
    )
    safety_resources = _mapping(
        safety_stage.get("resources"), "synthetic.stage1.safety.resources"
    )
    identification_resources = _mapping(
        identification_stage.get("resources"),
        "synthetic.stage1.identification.resources",
    )
    _validate_gate_vector(
        safety_resources.get("gates"),
        RESOURCE_GATE_NAMES,
        "synthetic.stage1.safety.resources.gates",
    )
    _validate_gate_vector(
        identification_resources.get("gates"),
        RESOURCE_GATE_NAMES,
        "synthetic.stage1.identification.resources.gates",
    )
    recomputed_safety = selected_auditor.evaluate_safety_regression(safety_cases)
    recomputed_primary = selected_auditor.evaluate_identification_primary(
        identification_pairs,
        identification_cases,
        draws=selected_auditor.BOOTSTRAP_DRAWS,
    )
    recomputed_resources = selected_auditor.evaluate_resources(
        [*safety_cases, *identification_cases]
    )
    recomputed_safety_resources = selected_auditor.evaluate_resources(safety_cases)
    recomputed_identification_resources = selected_auditor.evaluate_resources(
        identification_cases
    )
    if (
        loaded.get("schema") != selected_auditor.SCHEMA
        or loaded.get("synthetic_revision_id") != SYNTHETIC_REVISION_ID
        or loaded.get("campaign_revision_id") != CAMPAIGN_REVISION_ID
        or loaded.get("historical_control_revision_id") != CONTROL_REVISION_ID
        or loaded.get("status") != selected_auditor.SYNTHETIC_PASS
        or loaded.get("decision") != selected_auditor.SYNTHETIC_PASS
        or loaded.get("synthetic_pass") is not True
        or loaded.get("p1_review_authorized") is not False
        or loaded.get("nanning_p0_status") != "PENDING_NOT_RUN_BY_SYNTHETIC_RUNNER"
        or stage0.get("pass") is not True
        or stage0.get("status") != selected_auditor.STAGE0_PASS
        or stage0.get("pass") is not all(
            gate.get("pass") is True for gate in stage0_gates.values()
        )
        or not all(gate.get("pass") is True for gate in stage0_gates.values())
        or stage0.get("error") is not None
        or native_proof.get("pass")
        is not all(gate.get("pass") is True for gate in native_gates.values())
        or cross_binary.get("pass")
        is not all(gate.get("pass") is True for gate in cross_gates.values())
        or map2.get("pass")
        is not all(gate.get("pass") is True for gate in map2_gates.values())
        or stage1.get("pass") is not True
        or stage1.get("status") != "V3R11_STAGE1_PASS"
        or stage1.get("pass") is not all(
            gate.get("pass") is True for gate in stage1_gates.values()
        )
        or not all(gate.get("pass") is True for gate in stage1_gates.values())
        or protocol.get("synthetic_revision_id") != SYNTHETIC_REVISION_ID
        or protocol.get("campaign_revision_id") != CAMPAIGN_REVISION_ID
        or protocol.get("historical_control_revision_id") != CONTROL_REVISION_ID
        or protocol.get("case_count") != 144
        or len(safety_cases) != 120
        or len(set(safety_case_ids)) != 120
        or len(identification_cases) != 24
        or len(set(identification_case_ids)) != 24
        or set(safety_case_ids) & set(identification_case_ids)
        or safety_case_ids != safety_protocol_case_ids
        or identification_case_ids != identification_protocol_case_ids
        or safety_protocol.get("case_count") != 120
        or identification_protocol.get("case_count") != 24
        or safety_protocol.get("cases_sha256")
        != canonical_sha256(safety_protocol_cases)
        or identification_protocol.get("cases_sha256")
        != canonical_sha256(identification_protocol_cases)
        or protocol.get("cohorts_sha256") != canonical_sha256(protocol_cohorts)
        or stage1.get("manifest_sha256") != protocol.get("cohorts_sha256")
        or safety_stage.get("manifest_sha256")
        != safety_protocol.get("cases_sha256")
        or identification_stage.get("manifest_sha256")
        != identification_protocol.get("cases_sha256")
        or protocol != current_protocol
        or source_bundle != current_source_bundle
        or safety_stage.get("observation_count") != len(safety_observations)
        or safety_stage.get("observations_sha256")
        != canonical_sha256(safety_observations)
        or safety_stage.get("pair_count") != len(safety_pairs)
        or safety_stage.get("pairs_sha256") != canonical_sha256(safety_pairs)
        or identification_stage.get("observation_count")
        != len(identification_observations)
        or identification_stage.get("observations_sha256")
        != canonical_sha256(identification_observations)
        or identification_stage.get("pair_count") != len(identification_pairs)
        or identification_stage.get("pairs_sha256")
        != canonical_sha256(identification_pairs)
        or safety_stage.get("gates") != recomputed_safety.get("gates")
        or safety_stage.get("pass")
        is not (recomputed_safety.get("pass") is True and recomputed_safety_resources.get("pass") is True)
        or identification_stage.get("primary") != recomputed_primary
        or identification_stage.get("resources")
        != recomputed_identification_resources
        or identification_stage.get("pass")
        is not (
            recomputed_primary.get("pass") is True
            and recomputed_identification_resources.get("pass") is True
        )
        or safety_stage.get("resources") != recomputed_safety_resources
        or stage1.get("resources") != recomputed_resources
        or implementation.get("pass")
        is not all(
            gate.get("pass") is True for gate in implementation_gates.values()
        )
        or not all(
            gate.get("pass") is True for gate in implementation_gates.values()
        )
        or not isinstance(head, str)
        or len(head) != 40
        or any(character not in "0123456789abcdef" for character in head.lower())
        or loaded.get("implementation_head") != head
        or checkpoints.get("start") != source_bundle
        or checkpoints.get("after_stage0") != source_bundle
        or checkpoints.get("after_stage1") != source_bundle
        or not _sha256_text(source_bundle.get("sha256"))
        or canonical_sha256(_rows(source_bundle.get("files"), "source bundle files"))
        != source_bundle.get("sha256")
        or loaded.get("g32_binary_sha256") != expected_g32_binary_sha256
        or native_proof.get("pass") is not True
        or native_proof.get("build_head") != head
        or native_proof.get("g32_binary_sha256") != expected_g32_binary_sha256
        or map2.get("row_count") != len(map2_rows)
        or map2.get("rows_sha256") != canonical_sha256(map2_rows)
        or map2.get("pairs_sha256") != canonical_sha256(map2_pairs)
        or map2_resources.get("pass")
        is not all(
            gate.get("pass") is True
            for gate in _rows(map2_resources.get("gates"), "map2 resource gates")
        )
    ):
        raise SelectionError("synthetic Stage0/Stage1 sequencing evidence is invalid")
    return loaded, file_hash


def _shadow_campaign_status(results: Mapping[str, Mapping[str, Any]]) -> str:
    if set(results) != {"1x", "2x"}:
        return SHADOW_NO_GO
    admission_name = "node49_upstream53_admitted"
    admission_missing = False
    all_pass = True
    for name in ("1x", "2x"):
        result = _mapping(results[name], f"shadow result {name}")
        if "error" not in result or result.get("error") is not None:
            return SHADOW_NO_GO
        checks = _mapping(result.get("checks"), f"shadow result {name}.checks")
        if set(checks) != SHADOW_CHECK_NAMES or any(
            not isinstance(value, bool) for value in checks.values()
        ):
            return SHADOW_NO_GO
        recomputed_pass = all(checks.values())
        if result.get("pass") is not recomputed_pass:
            return SHADOW_NO_GO
        if not all(
            value for check_name, value in checks.items() if check_name != admission_name
        ):
            return SHADOW_NO_GO
        admission_missing = admission_missing or checks[admission_name] is False
        all_pass = all_pass and recomputed_pass
    if all_pass:
        return SHADOW_PASS
    if admission_missing:
        return SHADOW_NO_EVENT
    return SHADOW_NO_GO


def _build_g32_shadow_scale_context(
    *,
    name: str,
    control_scale: Mapping[str, Any],
    g32_binary: Path,
    auditor: Any,
) -> dict[str, Any]:
    """Purely rebuild the registered request tail for one frozen scale."""

    if name not in {"1x", "2x"}:
        raise SelectionError("shadow scale name must be 1x or 2x")
    selection = _mapping(control_scale.get("selection"), f"control.{name}.selection")
    rows = _rows(selection.get("selected_rows"), f"control.{name}.rows")
    off_request = deepcopy(
        dict(_mapping(control_scale.get("request"), f"control.{name}.request"))
    )
    control = _mapping(control_scale.get("control"), f"control.{name}.control")
    off_payload = _mapping(control.get("payload"), f"control.{name}.off payload")
    shadow_request = deepcopy(off_request)
    shadow_request["expected_binary_path"] = g32_binary
    shadow_request["search_path"] = g32_binary.parent
    shadow_request["source_aware_destination_service_mode"] = "shadow"
    shadow_request["source_aware_destination_service_trace_limit"] = G32_TRACE_LIMIT
    ordinary_equal = (
        auditor.ordinary_request_sha256(off_request)
        == auditor.ordinary_request_sha256(shadow_request)
    )
    excluded = {
        "expected_binary_path",
        "search_path",
        "source_aware_destination_service_mode",
        "source_aware_destination_service_trace_limit",
    }
    off_projection = {
        key: _portable(value)
        for key, value in off_request.items()
        if key not in excluded
    }
    shadow_projection = {
        key: _portable(value)
        for key, value in shadow_request.items()
        if key not in excluded
    }
    if not ordinary_equal or off_projection != shadow_projection:
        raise SelectionError("shadow request differs beyond binary locator/mode/trace")
    auditor.assert_request_projection(
        shadow_request,
        "shadow",
        [EXTERNAL_START],
        f"g4irsf32_v3r7_nanning_p0_{name}",
    )
    return {
        "name": name,
        "scale": int(name[0]),
        "rows": rows,
        "off_request": off_request,
        "shadow_request": shadow_request,
        "off_payload": off_payload,
        "ordinary_request_exact": ordinary_equal,
        "control_ordinary_payload_hashes": control.get(
            "ordinary_payload_hashes"
        ),
    }


def _replay_g32_shadow_scale_evidence(
    *,
    context: Mapping[str, Any],
    shadow_payload: Mapping[str, Any],
    g32_binary: Path,
    expected_g32_binary_sha256: str,
    auditor: Any,
) -> dict[str, Any]:
    """Recompute every retained scale field without invoking an executor."""

    name = str(context.get("name"))
    scale = _integer(context.get("scale"), f"{name}.scale")
    rows = _rows(context.get("rows"), f"{name}.rows")
    shadow_request = _mapping(
        context.get("shadow_request"), f"{name}.shadow request"
    )
    off_payload = _mapping(context.get("off_payload"), f"{name}.off payload")
    legacy_wait_pair = getattr(auditor, "legacy_wait_pair", None)
    if not callable(legacy_wait_pair):
        raise SelectionError("G32 auditor lacks the required legacy_wait_pair callable")

    loaded_path, loaded_sha = auditor._loaded_binary(shadow_payload)
    resolved_loaded_path = Path(loaded_path).resolve(strict=True)
    metadata = {
        "scale": scale,
        "flow_pattern": "nanning_control_selected",
        "bag_count": len(rows),
        "service_seconds": 1.0,
    }
    case_id = f"g4irsf32_v3r7_nanning_p0_shadow_{name}"
    observed = auditor.extract_rows(
        shadow_payload,
        case_id=case_id,
        request=shadow_request,
        metadata=metadata,
    )
    episodes = auditor.build_service_episodes(
        case_id, shadow_payload, observed, shadow_request
    )
    joined = auditor.join_v3r2_outcomes(observed, episodes)
    summary = _mapping(shadow_payload.get("summary"), f"{name}.summary")
    census = auditor._shadow_census(summary, observed, shadow_payload)
    service = auditor._service_audit(
        case_id,
        len(rows),
        {"external", "local"},
        shadow_payload,
        shadow_request,
        exact_node=LOCAL_START,
    )
    resources = auditor.evaluate_resources(
        [
            {
                "resources": {
                    "off": auditor._resource_values(off_payload, shadow=False),
                    "shadow": auditor._resource_values(
                        shadow_payload, shadow=True
                    ),
                }
            }
        ]
    )
    legacy_wait = _mapping(
        legacy_wait_pair(off_payload, shadow_payload),
        f"{name}.legacy_wait_pair",
    )
    admitted = [
        row
        for row in observed
        if row.get("node") == LOCAL_START
        and row.get("external_upstream_node") == EXTERNAL_START
    ]
    ordinary_hashes = auditor.ordinary_payload_hashes(shadow_payload)
    checks = {
        "loaded_g32_binary": loaded_sha == expected_g32_binary_sha256
        and resolved_loaded_path == g32_binary,
        "ordinary_request_exact": context.get("ordinary_request_exact") is True,
        "ordinary_state_exact": ordinary_hashes
        == context.get("control_ordinary_payload_hashes"),
        "rows_joined": joined.get("status") == auditor.JOINED,
        "shadow_census": census.get("pass") is True,
        "permanent_starvation_and_service": service.get("pass") is True,
        "resource_ratio": resources.get("pass") is True,
        "legacy_wait_exact": legacy_wait.get("pass") is True,
        "node49_upstream53_admitted": bool(admitted),
    }
    return {
        "scale": scale,
        "selected_row_count": len(rows),
        "selected_rows_sha256": canonical_sha256(rows),
        "pass": all(checks.values()),
        "checks": checks,
        "loaded_cpp_binary_path": loaded_path,
        "loaded_cpp_binary_sha256": loaded_sha,
        "shadow_request_sha256": auditor.request_sha256(shadow_request),
        "ordinary_request_sha256": auditor.ordinary_request_sha256(
            shadow_request
        ),
        "ordinary_payload_hashes": ordinary_hashes,
        "shadow_payload_sha256": canonical_sha256(shadow_payload),
        "shadow_payload": _portable(shadow_payload),
        "observation_count": len(observed),
        "observations_sha256": canonical_sha256(observed),
        "observations": observed,
        "admitted_node49_upstream53_count": len(admitted),
        "admitted_node49_upstream53_sha256": canonical_sha256(admitted),
        "joined_sha256": canonical_sha256(joined),
        "join": joined,
        "census": census,
        "service": service,
        "resources": resources,
        "legacy_wait_over_120": legacy_wait,
        "error": None,
    }


def _deep_validate_g32_shadow_result_mapping(
    value: Mapping[str, Any],
    *,
    control: Mapping[str, Any],
    control_file_sha256: str,
    synthetic: Mapping[str, Any],
    synthetic_file_sha256: str,
    g32_binary: Path,
    expected_g32_binary_sha256: str,
    expected_implementation_head: str | None = None,
    auditor: Any | None = None,
) -> dict[str, Any]:
    """Replay against already deep-validated control/synthetic mappings."""

    result = deepcopy(dict(_mapping(value, "shadow artifact")))
    _exact_keys(
        result,
        {
            "schema",
            "protocol_id",
            "campaign_revision_id",
            "control_revision_id",
            "status",
            "pass",
            "control_artifact_content_sha256",
            "control_artifact_file_sha256",
            "synthetic_artifact_file_sha256",
            "synthetic_decision",
            "synthetic_implementation_head",
            "g32_binary_sha256",
            "scales",
            "artifact_content_sha256",
        },
        "shadow artifact",
    )
    content_sha = verify_content_hash(result)
    if not _sha256_text(control_file_sha256) or not _sha256_text(
        synthetic_file_sha256
    ):
        raise SelectionError("shadow input file SHA-256 is invalid")
    if not isinstance(g32_binary, Path):
        raise TypeError("G32 binary must be supplied as a Path")
    if g32_binary.is_symlink():
        raise SelectionError("G32 binary symlinks are forbidden in deep replay")
    binary = g32_binary.resolve(strict=True)
    binary_sha = file_sha256(binary)
    if (
        not _sha256_text(expected_g32_binary_sha256)
        or binary_sha != expected_g32_binary_sha256
        or binary_sha == FROZEN_SOURCE_HASHES[G31_BINARY]
    ):
        raise SelectionError("deep shadow replay G32 binary identity mismatch")
    implementation_head = (
        expected_implementation_head
        if expected_implementation_head is not None
        else synthetic.get("implementation_head")
    )
    bindings = {
        "schema": result.get("schema") == SHADOW_GATE_SCHEMA,
        "protocol": result.get("protocol_id") == PROTOCOL_ID,
        "campaign_revision": result.get("campaign_revision_id")
        == CAMPAIGN_REVISION_ID,
        "control_revision": result.get("control_revision_id")
        == CONTROL_REVISION_ID
        == control.get("control_revision_id"),
        "control_content": result.get("control_artifact_content_sha256")
        == control.get("artifact_content_sha256"),
        "control_file": result.get("control_artifact_file_sha256")
        == control_file_sha256,
        "synthetic_file": result.get("synthetic_artifact_file_sha256")
        == synthetic_file_sha256,
        "synthetic_decision": result.get("synthetic_decision")
        == synthetic.get("decision"),
        "implementation_head": result.get("synthetic_implementation_head")
        == implementation_head
        == synthetic.get("implementation_head"),
        "g32_binary": result.get("g32_binary_sha256")
        == expected_g32_binary_sha256,
    }
    if not all(bindings.values()):
        failed = sorted(name for name, passed in bindings.items() if not passed)
        raise SelectionError(f"shadow artifact binding mismatch: {failed}")

    selected_auditor = auditor or _v3_auditor()
    scales = _mapping(result.get("scales"), "shadow.scales")
    if set(scales) != {"1x", "2x"}:
        raise SelectionError("shadow artifact must contain exact 1x/2x scales")
    replayed: dict[str, Mapping[str, Any]] = {}
    scale_checks: dict[str, bool] = {}
    control_scales = _mapping(control.get("scales"), "control.scales")
    for scale_number, name in ((1, "1x"), (2, "2x")):
        control_scale = _mapping(control_scales.get(name), f"control.scales.{name}")
        context = _build_g32_shadow_scale_context(
            name=name,
            control_scale=control_scale,
            g32_binary=binary,
            auditor=selected_auditor,
        )
        rows = _rows(context.get("rows"), f"control.{name}.rows")
        expected_count = EXPECTED_SELECTION_COUNTS[scale_number]["total"]
        request = _mapping(context.get("shadow_request"), f"shadow.{name}.request")
        bag_records = request.get("bag_records")
        if (
            len(rows) != expected_count
            or not isinstance(bag_records, (list, tuple))
            or len(bag_records) != expected_count
        ):
            raise SelectionError(
                f"{name} deep replay requires exact {expected_count}-row request"
            )
        recorded = _mapping(scales.get(name), f"shadow.scales.{name}")
        payload = _mapping(
            recorded.get("shadow_payload"), f"shadow.scales.{name}.shadow_payload"
        )
        expected = _replay_g32_shadow_scale_evidence(
            context=context,
            shadow_payload=payload,
            g32_binary=binary,
            expected_g32_binary_sha256=expected_g32_binary_sha256,
            auditor=selected_auditor,
        )
        exact = _portable(recorded) == _portable(expected)
        scale_checks[name] = exact
        if not exact:
            raise SelectionError(f"{name} shadow scale evidence differs on deep replay")
        replayed[name] = expected

    status = _shadow_campaign_status(replayed)
    passed = status == SHADOW_PASS
    if result.get("status") != status or result.get("pass") is not passed:
        raise SelectionError("shadow campaign status/pass differs on deep replay")
    return {
        "pass": passed,
        "checks": {**bindings, **{f"scale_{name}": ok for name, ok in scale_checks.items()}},
        "status": status,
        "content_sha256": content_sha,
        "attempted_scales": ["1x", "2x"],
    }


def load_and_deep_validate_g32_shadow_result(
    value: Mapping[str, Any],
    *,
    control_artifact: Path,
    expected_control_file_sha256: str,
    synthetic_artifact: Path,
    expected_synthetic_file_sha256: str,
    g32_binary: Path,
    expected_g32_binary_sha256: str,
    expected_implementation_head: str | None = None,
    auditor: Any | None = None,
) -> dict[str, Any]:
    """Reload trusted artifacts, then deeply replay a retained shadow mapping."""

    selected_auditor = auditor or _v3_auditor()
    control, control_file_sha = load_and_validate_control_artifact(
        control_artifact,
        expected_file_sha256=expected_control_file_sha256,
        auditor=selected_auditor,
    )
    if not isinstance(g32_binary, Path):
        raise TypeError("G32 binary must be supplied as a Path")
    if g32_binary.is_symlink():
        raise SelectionError("G32 binary symlinks are forbidden in deep replay")
    binary = g32_binary.resolve(strict=True)
    binary_sha = file_sha256(binary)
    if binary_sha != expected_g32_binary_sha256:
        raise SelectionError("G32 binary does not match deep replay expectation")
    synthetic, synthetic_file_sha = load_and_validate_synthetic_artifact(
        synthetic_artifact,
        expected_file_sha256=expected_synthetic_file_sha256,
        expected_g32_binary_sha256=binary_sha,
        auditor=selected_auditor,
    )
    return _deep_validate_g32_shadow_result_mapping(
        value,
        control=control,
        control_file_sha256=control_file_sha,
        synthetic=synthetic,
        synthetic_file_sha256=synthetic_file_sha,
        g32_binary=binary,
        expected_g32_binary_sha256=binary_sha,
        expected_implementation_head=expected_implementation_head,
        auditor=selected_auditor,
    )


def run_g32_shadow_gate(
    control_artifact: Path,
    g32_binary: Path,
    executor: Executor,
    *,
    expected_control_file_sha256: str,
    synthetic_artifact: Path,
    expected_synthetic_file_sha256: str,
    expected_g32_binary_sha256: str,
    auditor: Any | None = None,
    _test_only: bool = False,
) -> dict[str, Any]:
    """Execute the later shadow-only gate after validating the whole control.

    This function is intentionally not called by :func:`main`.  The caller
    must first establish the registered synthetic V3R11 pass, bind the V3R7
    control revision, and explicitly provide a G32 executor/binary.  Invalid
    control evidence fails before any executor call.
    """

    if FORMAL_EXECUTION_BLOCKED_REASON and not _test_only:
        raise SelectionError(FORMAL_EXECUTION_BLOCKED_REASON)
    selected_auditor = auditor or _v3_auditor()
    control, control_file_sha = load_and_validate_control_artifact(
        control_artifact,
        expected_file_sha256=expected_control_file_sha256,
        auditor=selected_auditor,
    )
    binary = g32_binary.resolve(strict=True)
    binary_sha = file_sha256(binary)
    if not _sha256_text(expected_g32_binary_sha256):
        raise SelectionError("expected G32 binary SHA-256 is invalid")
    if binary_sha != expected_g32_binary_sha256:
        raise SelectionError("G32 binary does not match the expected SHA-256")
    if binary_sha == FROZEN_SOURCE_HASHES[G31_BINARY]:
        raise SelectionError("G32 shadow gate was given the frozen G31 binary")
    synthetic, synthetic_file_sha = load_and_validate_synthetic_artifact(
        synthetic_artifact,
        expected_file_sha256=expected_synthetic_file_sha256,
        expected_g32_binary_sha256=binary_sha,
        auditor=selected_auditor,
    )
    legacy_wait_pair = getattr(selected_auditor, "legacy_wait_pair", None)
    if not callable(legacy_wait_pair):
        raise SelectionError("G32 auditor lacks the required legacy_wait_pair callable")

    results: dict[str, Any] = {}
    for name in ("1x", "2x"):
        scale = _mapping(control["scales"][name], f"control.{name}")
        context = _build_g32_shadow_scale_context(
            name=name,
            control_scale=scale,
            g32_binary=binary,
            auditor=selected_auditor,
        )
        shadow_request = _mapping(
            context.get("shadow_request"), f"{name}.shadow request"
        )

        retained_payload: Mapping[str, Any] | None = None
        try:
            payload = executor(**shadow_request)
            if not isinstance(payload, Mapping):
                raise SelectionError("G32 executor did not return an object")
            retained_payload = payload
            results[name] = _replay_g32_shadow_scale_evidence(
                context=context,
                shadow_payload=payload,
                g32_binary=binary,
                expected_g32_binary_sha256=binary_sha,
                auditor=selected_auditor,
            )
        except Exception as error:  # retain a strict fail-closed stage structure
            results[name] = {
                "pass": False,
                "checks": {},
                "admitted_node49_upstream53_count": 0,
                "error_type": type(error).__name__,
                "error": str(error),
                "shadow_payload_sha256": canonical_sha256(retained_payload)
                if retained_payload is not None
                else None,
                "shadow_payload": _portable(retained_payload)
                if retained_payload is not None
                else None,
            }
            break

    status = _shadow_campaign_status(results)
    passed = status == SHADOW_PASS
    return with_content_hash(
        {
            "schema": SHADOW_GATE_SCHEMA,
            "protocol_id": PROTOCOL_ID,
            "campaign_revision_id": CAMPAIGN_REVISION_ID,
            "control_revision_id": CONTROL_REVISION_ID,
            "status": status,
            "pass": passed,
            "control_artifact_content_sha256": control[
                "artifact_content_sha256"
            ],
            "control_artifact_file_sha256": control_file_sha,
            "synthetic_artifact_file_sha256": synthetic_file_sha,
            "synthetic_decision": synthetic["decision"],
            "synthetic_implementation_head": synthetic["implementation_head"],
            "g32_binary_sha256": binary_sha,
            "scales": results,
        }
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--g31-binary", type=Path, default=G31_BINARY)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if CONTROL_EXECUTION_BLOCKED_REASON:
        raise SelectionError(CONTROL_EXECUTION_BLOCKED_REASON)
    try:
        result = run_control_selection(binary=args.g31_binary)
    except Exception as error:
        result = with_content_hash(
            {
                "schema": SCHEMA,
                "protocol_id": PROTOCOL_ID,
                "control_revision_id": CONTROL_REVISION_ID,
                "status": NO_GO,
                "pass": False,
                "g32_executed": False,
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )
    atomic_write_strict_json(args.output, result)
    print(result["status"])
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
