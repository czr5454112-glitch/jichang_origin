#!/usr/bin/env python3
"""Execute the G4IRSF15 two-pass exact-binary causal campaign.

The program deliberately separates discovery from intervention:

* ``scan`` performs one outcome-free native pass over the protected original
  map/task and publishes a deterministic, tail-enriched min-hash frame;
* ``plan-pilot`` and ``plan-formal`` preregister immutable target/shard plans;
* ``run-shard`` is a fresh-process worker that replays a contiguous event
  ordinal range and atomically publishes one native matched-pair shard; and
* ``finalize`` derives signed labels without dropping neutral or harmful
  outcomes and evaluates the preregistered gates.

There is no serialized runtime checkpoint format in G4IRSF15.  A worker
therefore performs deterministic prefix replay and the native batch runner
holds one opaque in-memory checkpoint at each targeted event ordinal.  The
checkpoint manifest records that limitation rather than inventing disk
checkpoints.

This module never trains a model, launches a closed-loop candidate, changes
the protected input, or scales demand.
"""

from __future__ import annotations

import argparse
import copy
import csv
import ctypes
import hashlib
import importlib.util
import io
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    _text = str(_bootstrap)
    if _text not in sys.path:
        sys.path.insert(0, _text)

from scripts.eval import g4irsf12_reproducible_harness as g12
from scripts.eval.g4irsf11_fixed_map import (
    assert_canonical_map,
    canonical_graph_records,
)


MAP_PATH = Path("data/processed/maps/map2.json")
TASK_PATH = Path("data/processed/tasks/inputdata.jsonl")
MODEL_PATH = Path("artifacts/models/g4e_risk_calibrated_policy.json")
OFFLINE_TAIL_PATH = Path("outputs/tables/g4irsf13_per_bag_delta.csv")
GENERATOR_PATH = Path("scripts/eval/g4irsf15_causal_campaign.py")
VALIDATOR_PATH = Path("scripts/validate_g4irsf15_causal_campaign.py")
ORCHESTRATOR_PATH = Path(
    "scripts/run_g4irsf15_campaign_shards.py"
)
ORCHESTRATOR_PROFILE_ROOT = Path(
    "artifacts/datasets/g4irsf15_campaign_execution_profiles"
)
DEFAULT_BUILD_MANIFEST_PATH = Path(
    "outputs/manifests/g4irsf15_exact_binary_build_manifest.json"
)
BUILD_MANIFEST_SCHEMA = (
    "czr005.g4irsf15.exact_binary_build_manifest.v1"
)

DESCRIPTOR_DATASET_PATH = Path(
    "artifacts/datasets/g4irsf15_causal_descriptor_pool.jsonl.zst"
)
SKELETON_DATASET_PATH = Path(
    "artifacts/datasets/g4irsf15_causal_skeleton_population.jsonl.zst"
)
DESCRIPTOR_MANIFEST_PATH = Path(
    "artifacts/datasets/g4irsf15_causal_descriptor_manifest.json"
)
CHECKPOINT_MANIFEST_PATH = Path(
    "artifacts/datasets/g4irsf15_checkpoint_bank_manifest.json"
)
PILOT_MANIFEST_PATH = Path(
    "artifacts/datasets/g4irsf15_pilot_intervention_manifest.json"
)
PILOT_ROUND2_MANIFEST_PATH = Path(
    "artifacts/datasets/g4irsf15_pilot_intervention_manifest_round2.json"
)
PILOT_SCREENING_REVISION_PATH = Path(
    "artifacts/datasets/g4irsf15_pilot_screening_revision.json"
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
PILOT_TABLE_PATH = Path(
    "outputs/tables/g4irsf15_pilot_causal_pairs.csv"
)
CAUSAL_TABLE_PATH = Path("outputs/tables/g4irsf15_causal_pairs.csv")
H_SYSTEM_TABLE_PATH = Path(
    "outputs/tables/g4irsf15_h_system_pairs.csv"
)
COVERAGE_TABLE_PATH = Path(
    "outputs/tables/g4irsf15_campaign_coverage.csv"
)
WEIGHTED_EFFECT_TABLE_PATH = Path(
    "outputs/tables/g4irsf15_weighted_effect_estimates.csv"
)
RUNNER_REPORT_PATH = Path(
    "outputs/reports/g4irsf15_intervention_runner_validation.md"
)
CAMPAIGN_REPORT_PATH = Path(
    "outputs/reports/g4irsf15_causal_campaign_results.md"
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

MAP_RAW_SHA256 = (
    "9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4"
)
MAP_SEMANTIC_SHA256 = (
    "67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63"
)
TASK_RAW_SHA256 = (
    "968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f"
)
MODEL_SHA256 = (
    "4a058dee0bdd17e15f67d1943a551822847d0c066ac3cf03a5da71a07731bbca"
)
FULL_SEGMENT_COUNT = 43_603
FULL_RAW_BAG_COUNT = 28_506

SKELETON_SCAN_SCHEMA = (
    "czr005.g4irsf15.causal_skeleton_population.v1"
)
SKELETON_SCHEMA = "czr005.g4irsf15.causal_skeleton.v1"
MATERIALIZATION_SCHEMA = (
    "czr005.g4irsf15.causal_descriptor_materialization.v1"
)
DESCRIPTOR_SCHEMA = "czr005.g4irsf15.causal_target_descriptor.v1"
PAIR_RUN_SCHEMA = "czr005.g4irsf15.causal_target_pairs.v1"
DESCRIPTOR_MANIFEST_SCHEMA = (
    "czr005.g4irsf15.causal_descriptor_manifest.v1"
)
CHECKPOINT_MANIFEST_SCHEMA = (
    "czr005.g4irsf15.checkpoint_bank_manifest.v1"
)
CAMPAIGN_PLAN_SCHEMA = "czr005.g4irsf15.causal_campaign_plan.v1"
SHARD_SCHEMA = "czr005.g4irsf15.causal_pair_shard.v1"
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

KINDS = ("I1", "I3", "I4")
PILOT_ATTEMPTS_PER_KIND = 64
PILOT_MIN_COMPLETE_PER_KIND = 30
FORMAL_LABEL_TARGETS: Mapping[str, int] = {
    "I1": 768,
    "I3": 640,
    "I4": 640,
}
FORMAL_ATTEMPT_TARGETS: Mapping[str, int] = {
    kind: target * 2 for kind, target in FORMAL_LABEL_TARGETS.items()
}
FORMAL_MIN_LABELS_PER_KIND = 512
FORMAL_MIN_LABELS = 2_048
FORMAL_MIN_H_SYSTEM = 128
FORMAL_TARGET_H_SYSTEM = 256
MIN_DESCRIPTOR_POOL = 4_096
DEFAULT_DESCRIPTOR_POOL = 6_144
DEFAULT_FORMAL_SHARD_SIZE = 256
DEFAULT_PILOT_SHARD_SIZE = 64
DEFAULT_H_SYSTEM_TARGETS_PER_SHARD = 4
GITHUB_SAFE_ARTIFACT_MAX_BYTES = 95 * 1024 * 1024

OUTCOME_FREE_SCREENING_FIELDS = (
    "baseline_release",
    "candidate_action_count",
    "coverage_tags",
    "kind",
    "node",
    "queue_top_not_popped",
    "reservation_depth",
    "runtime_future_route_read_count",
    "runtime_future_schedule_read_count",
    "runtime_global_scan_count",
    "sampling_stratum_id",
    "selected_boolean",
    "staged_event_sink_empty",
    "total_legal_action_count",
)

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

SOURCE_PATHS = (
    Path("pyproject.toml"),
    GENERATOR_PATH,
    VALIDATOR_PATH,
    ORCHESTRATOR_PATH,
    Path("scripts/smoke_g4irsf15_real_pyd.py"),
    Path("scripts/eval/g4irsf12_reproducible_harness.py"),
    Path("scripts/eval/g4irsf11_fixed_map.py"),
    Path("cpp/ics_core/bindings/czr005_cpp.cpp"),
    Path("cpp/ics_core/bindings/g4irsf15_causal_campaign_binding.hpp"),
    Path("cpp/ics_core/runtime/event_driven_junction.hpp"),
    Path("cpp/ics_core/runtime/g4irsf15_causal_campaign.hpp"),
    Path("cpp/ics_core/runtime/g4irsf14_causal_intervention.hpp"),
    Path("cpp/ics_core/runtime/g4irsf14_state_clone.hpp"),
    MODEL_PATH,
)

HEX = frozenset("0123456789abcdef")


class CampaignError(RuntimeError):
    """Raised when evidence cannot be admitted fail-closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CampaignError(message)


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


def _canonical_fields_payload(
    fields: Sequence[tuple[str, str, Any]],
) -> bytes:
    """Encode the small cross-language CanonicalFields v2 wire format."""

    payload = bytearray(b"CZR005-CANONICAL-FIELDS\x02")
    for name, field_type, value in fields:
        encoded_name = name.encode("utf-8")
        payload.extend(len(encoded_name).to_bytes(4, "big"))
        payload.extend(encoded_name)
        payload.extend(field_type.encode("ascii"))
        if field_type == "s":
            encoded = (
                value
                if isinstance(value, bytes)
                else str(value).encode("utf-8")
            )
            payload.extend(len(encoded).to_bytes(8, "big"))
            payload.extend(encoded)
        elif field_type in {"i", "u"}:
            payload.extend(
                (int(value) & ((1 << 64) - 1)).to_bytes(8, "big")
            )
        elif field_type == "b":
            payload.extend(b"\x01" if value else b"\x00")
        elif field_type == "d":
            import struct

            payload.extend(struct.pack(">d", float(value)))
        elif field_type == "I":
            values = [int(item) for item in value]
            payload.extend(len(values).to_bytes(8, "big"))
            for item in values:
                payload.extend(
                    (item & ((1 << 64) - 1)).to_bytes(8, "big")
                )
        else:  # pragma: no cover - all campaign encodings are explicit
            raise CampaignError(f"UNSUPPORTED_CANONICAL_FIELD_TYPE:{field_type}")
    return bytes(payload)


def _canonical_fields_sha256(
    fields: Sequence[tuple[str, str, Any]],
) -> str:
    return hashlib.sha256(_canonical_fields_payload(fields)).hexdigest()


def _file_sha256(path: Path) -> str:
    _require(path.is_file(), f"MISSING_FILE:{path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _publishable_byte_count(path: Path, label: str) -> int:
    size = path.stat().st_size
    _require(
        size < GITHUB_SAFE_ARTIFACT_MAX_BYTES,
        f"ARTIFACT_APPROACHES_GITHUB_100_MIB_LIMIT:{label}:{size}",
    )
    return size


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in HEX for character in value)
    )


def _strict_int(value: Any, label: str, *, minimum: int | None = None) -> int:
    _require(
        isinstance(value, int) and not isinstance(value, bool),
        f"NOT_INTEGER:{label}",
    )
    result = int(value)
    if minimum is not None:
        _require(result >= minimum, f"INTEGER_BELOW_MINIMUM:{label}")
    return result


def _strict_float(value: Any, label: str) -> float:
    _require(
        isinstance(value, (int, float)) and not isinstance(value, bool),
        f"NOT_NUMERIC:{label}",
    )
    result = float(value)
    _require(math.isfinite(result), f"NONFINITE:{label}")
    return result


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


def _validate_self_bound(value: Mapping[str, Any], label: str) -> None:
    declared = value.get("self_sha256")
    _require(_is_sha256(declared), f"MISSING_SELF_SHA256:{label}")
    projection = dict(value)
    projection.pop("self_sha256", None)
    _require(
        declared == _canonical_sha256(projection),
        f"SELF_SHA256_DRIFT:{label}",
    )


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        raise


def _atomic_json(path: Path, value: Mapping[str, Any]) -> dict[str, Any]:
    bound = _self_bound(value)
    _atomic_write(path, _json_bytes(bound))
    return bound


def _csv_bytes(
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


def _zstd_compress(payload: bytes, level: int = 9) -> bytes:
    try:
        import zstandard
    except ImportError as exc:
        raise CampaignError(
            "ZSTANDARD_DEPENDENCY_REQUIRED: install the project dependency "
            "`zstandard>=0.23` before scan/final publication"
        ) from exc
    return zstandard.ZstdCompressor(level=level).compress(payload)


def _atomic_zstd_json(
    path: Path, value: Mapping[str, Any]
) -> dict[str, Any]:
    bound = _self_bound(value)
    _atomic_write(path, _zstd_compress(_canonical_bytes(bound)))
    return bound


def _jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(_canonical_bytes(row) + b"\n" for row in rows)


def _load_json(path: Path) -> dict[str, Any]:
    _require(path.is_file(), f"MISSING_JSON:{path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CampaignError(f"INVALID_JSON:{path}:{type(exc).__name__}") from exc
    _require(isinstance(value, dict), f"JSON_NOT_OBJECT:{path}")
    return value


def _load_zstd_json(path: Path) -> dict[str, Any]:
    _require(path.is_file(), f"MISSING_ZSTD_JSON:{path}")
    try:
        import zstandard
    except ImportError as exc:
        raise CampaignError(
            "ZSTANDARD_DEPENDENCY_REQUIRED: install `zstandard>=0.23`"
        ) from exc
    try:
        decoded = zstandard.ZstdDecompressor().decompress(path.read_bytes())
        value = json.loads(decoded)
    except (zstandard.ZstdError, json.JSONDecodeError) as exc:
        raise CampaignError(f"INVALID_ZSTD_JSON:{path}") from exc
    _require(isinstance(value, dict), f"ZSTD_JSON_NOT_OBJECT:{path}")
    return value


def _git_output(root: Path, *arguments: str) -> str:
    process = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    _require(
        process.returncode == 0,
        f"GIT_COMMAND_FAILED:{' '.join(arguments)}:{process.stderr.strip()}",
    )
    return process.stdout.strip()


def _git_bytes(root: Path, *arguments: str) -> bytes:
    process = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        capture_output=True,
    )
    _require(
        process.returncode == 0,
        f"GIT_COMMAND_FAILED:{' '.join(arguments)}:"
        f"{process.stderr.decode('utf-8', 'replace').strip()}",
    )
    return process.stdout


def _dirty_source_state(
    root: Path, transitive_paths: Sequence[str]
) -> dict[str, Any]:
    normalized = sorted(set(str(Path(path).as_posix()) for path in transitive_paths))
    tracked = _git_bytes(
        root,
        "diff",
        "--binary",
        "--no-ext-diff",
        "--full-index",
        "HEAD",
        "--",
        *normalized,
    )
    staged = _git_bytes(
        root,
        "diff",
        "--cached",
        "--binary",
        "--no-ext-diff",
        "--full-index",
        "HEAD",
        "--",
        *normalized,
    )
    untracked_raw = _git_bytes(
        root,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
        "--",
        *normalized,
    )
    untracked: list[dict[str, Any]] = []
    for relative in sorted(
        value.decode("utf-8", "surrogateescape")
        for value in untracked_raw.split(b"\0")
        if value
    ):
        path = root / Path(relative)
        untracked.append(
            {
                "path": Path(relative).as_posix(),
                "sha256": _file_sha256(path),
                "byte_count": path.stat().st_size,
            }
        )
    state = {
        "algorithm": "GIT_BINARY_DIFF_FULL_INDEX_V1",
        "head": _git_output(root, "rev-parse", "HEAD"),
        "tracked_worktree_diff_sha256": hashlib.sha256(tracked).hexdigest(),
        "staged_diff_sha256": hashlib.sha256(staged).hexdigest(),
        "untracked_source_files": untracked,
    }
    state["state_sha256"] = _canonical_sha256(state)
    return state


def _validate_build_manifest(
    *,
    root: Path,
    binary: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    path = (
        manifest_path
        if manifest_path.is_absolute()
        else root / manifest_path
    ).resolve(strict=True)
    manifest = _load_json(path)
    _validate_self_bound(manifest, "exact_binary_build_manifest")
    _require(
        manifest.get("schema") == BUILD_MANIFEST_SCHEMA
        and manifest.get("status") == "COMPLETE",
        "BUILD_MANIFEST_SCHEMA_OR_STATUS",
    )
    binary_binding = manifest.get("binary")
    _require(isinstance(binary_binding, dict), "BUILD_BINARY_BINDING_MISSING")
    binary = binary.resolve(strict=True)
    bound_binary_path = Path(str(binary_binding.get("path", "")))
    if not bound_binary_path.is_absolute():
        bound_binary_path = root / bound_binary_path
    _require(
        bound_binary_path.resolve() == binary
        and binary_binding.get("sha256") == _file_sha256(binary)
        and binary_binding.get("byte_count") == binary.stat().st_size,
        "BUILD_BINARY_BINDING_DRIFT",
    )
    git_binding = manifest.get("git")
    _require(
        isinstance(git_binding, dict)
        and git_binding.get("head") == _git_output(root, "rev-parse", "HEAD")
        and git_binding.get("branch")
        == _git_output(root, "branch", "--show-current"),
        "BUILD_GIT_BINDING_DRIFT",
    )
    inventory = manifest.get("transitive_source_inventory")
    _require(isinstance(inventory, dict), "BUILD_SOURCE_INVENTORY_MISSING")
    _require(
        inventory.get("method")
        == "CMAKE_DEPENDENCY_SCAN_PLUS_EXPLICIT_HEADERS",
        "BUILD_SOURCE_INVENTORY_METHOD",
    )
    files = inventory.get("files")
    _require(isinstance(files, list) and files, "BUILD_SOURCE_FILES_MISSING")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for binding in files:
        _require(isinstance(binding, dict), "BUILD_SOURCE_BINDING_NOT_OBJECT")
        relative = str(binding.get("path", ""))
        _require(relative and relative not in seen, "BUILD_SOURCE_PATH_DUPLICATE")
        seen.add(relative)
        source_path = root / Path(relative)
        _require(
            _file_sha256(source_path) == binding.get("sha256")
            and source_path.stat().st_size == binding.get("byte_count"),
            f"BUILD_TRANSITIVE_SOURCE_DRIFT:{relative}",
        )
        normalized.append(dict(binding))
    normalized.sort(key=lambda row: row["path"])
    _require(
        _canonical_sha256(normalized) == inventory.get("bundle_sha256"),
        "BUILD_TRANSITIVE_SOURCE_BUNDLE_DRIFT",
    )
    required_native = {
        "CMakeLists.txt",
        "cpp/ics_core/bindings/czr005_cpp.cpp",
        "cpp/ics_core/bindings/g4irsf15_causal_campaign_binding.hpp",
        "cpp/ics_core/runtime/event_driven_junction.hpp",
        "cpp/ics_core/runtime/g4irsf15_causal_campaign.hpp",
    }
    _require(
        required_native.issubset(seen),
        "BUILD_TRANSITIVE_INVENTORY_MISSES_REQUIRED_NATIVE_SOURCE",
    )
    expected_dirty = _dirty_source_state(root, sorted(seen))
    _require(
        manifest.get("dirty_source_state") == expected_dirty,
        "BUILD_DIRTY_SOURCE_STATE_DRIFT",
    )
    toolchain = manifest.get("toolchain")
    _require(isinstance(toolchain, dict), "BUILD_TOOLCHAIN_MISSING")
    _require(toolchain.get("configuration") == "Release", "BUILD_NOT_RELEASE")
    _require(toolchain.get("generator") not in (None, ""), "BUILD_GENERATOR")
    for name in ("cmake", "compiler", "python", "pybind11", "cmake_cache"):
        _require(
            isinstance(toolchain.get(name), dict),
            f"BUILD_TOOLCHAIN_FIELD:{name}",
        )
    def validate_bound_file(
        binding: Mapping[str, Any],
        *,
        field: str,
        base: Path | None = None,
    ) -> Path:
        candidate = Path(str(binding.get("path", "")))
        if not candidate.is_absolute():
            candidate = (base or root) / candidate
        candidate = candidate.resolve(strict=True)
        _require(
            binding.get("sha256") == _file_sha256(candidate)
            and binding.get("byte_count") == candidate.stat().st_size,
            f"BUILD_TOOLCHAIN_FILE_DRIFT:{field}",
        )
        return candidate

    cmake_path = validate_bound_file(toolchain["cmake"], field="cmake")
    compiler_path = validate_bound_file(
        toolchain["compiler"], field="compiler"
    )
    _require(
        toolchain["compiler"].get("id")
        and toolchain["compiler"].get("version")
        and toolchain["compiler"].get("architecture") is not None
        and toolchain["cmake"].get("version")
        and isinstance(toolchain.get("configure_argv"), list)
        and isinstance(toolchain.get("build_argv"), list)
        and Path(str(toolchain["configure_argv"][0])).name.lower()
        in {"cmake", "cmake.exe"}
        and Path(str(toolchain["build_argv"][0])).name.lower()
        in {"cmake", "cmake.exe"},
        "BUILD_TOOLCHAIN_DETAIL_MISSING",
    )
    python_binding = toolchain["python"]
    python_path = Path(str(python_binding.get("path", ""))).resolve(
        strict=True
    )
    reported_python = Path(
        str(python_binding.get("reported_executable", ""))
    ).resolve(strict=True)
    try:
        same_python = os.path.samefile(python_path, reported_python)
    except OSError:
        same_python = os.path.normcase(str(python_path)) == os.path.normcase(
            str(reported_python)
        )
    _require(
        same_python
        and python_binding.get("sha256") == _file_sha256(python_path),
        "BUILD_PYTHON_EXECUTABLE_DRIFT",
    )
    metadata_process = subprocess.run(
        [
            str(python_path),
            "-c",
            (
                "import json,platform,sys,pybind11;"
                "print(json.dumps({'executable':sys.executable,"
                "'version':sys.version,"
                "'implementation':sys.implementation.name,"
                "'pybind11_version':pybind11.__version__,"
                "'pybind11_cmake_dir':pybind11.get_cmake_dir()}))"
            ),
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    _require(
        metadata_process.returncode == 0,
        "BUILD_TARGET_PYTHON_METADATA_FAILED",
    )
    try:
        current_python = json.loads(metadata_process.stdout)
    except json.JSONDecodeError as exc:
        raise CampaignError("BUILD_TARGET_PYTHON_METADATA_INVALID") from exc
    pybind_binding = toolchain["pybind11"]
    _require(
        current_python.get("version") == python_binding.get("version")
        and current_python.get("implementation")
        == python_binding.get("implementation")
        and current_python.get("pybind11_version")
        == pybind_binding.get("version")
        and Path(current_python["pybind11_cmake_dir"]).resolve()
        == Path(str(pybind_binding.get("cmake_dir", ""))).resolve(
            strict=True
        ),
        "BUILD_PYTHON_OR_PYBIND11_ENVIRONMENT_DRIFT",
    )
    _require(
        Path(current_python["executable"]).resolve() == reported_python,
        "BUILD_REPORTED_PYTHON_DRIFT",
    )
    cache_path = Path(str(toolchain["cmake_cache"]["path"]))
    if not cache_path.is_absolute():
        cache_path = root / cache_path
    _require(
        _file_sha256(cache_path) == toolchain["cmake_cache"]["sha256"]
        and cache_path.stat().st_size
        == toolchain["cmake_cache"]["byte_count"],
        "BUILD_CMAKE_CACHE_DRIFT",
    )
    execution = manifest.get("build_execution")
    _require(
        isinstance(execution, dict)
        and execution.get("clean_first") is True
        and execution.get("source_inventory_unchanged_during_build") is True
        and isinstance(execution.get("configure"), dict)
        and execution["configure"].get("return_code") == 0
        and execution["configure"].get("argv")
        == toolchain["configure_argv"]
        and isinstance(execution.get("build"), dict)
        and execution["build"].get("return_code") == 0
        and execution["build"].get("argv") == toolchain["build_argv"]
        and "--clean-first" in toolchain["build_argv"],
        "BUILD_EXECUTION_ATTESTATION_DRIFT",
    )
    producer = manifest.get("producer")
    _require(isinstance(producer, dict), "BUILD_PRODUCER_MISSING")
    validate_bound_file(producer, field="producer")
    try:
        publication_manifest_path = path.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise CampaignError(
            "BUILD_MANIFEST_MUST_BE_INSIDE_REPOSITORY_FOR_PUBLICATION"
        ) from exc
    bound_binary_path = Path(str(binary_binding.get("path", "")))
    resolved_bound_binary = (
        bound_binary_path
        if bound_binary_path.is_absolute()
        else root / bound_binary_path
    ).resolve()
    try:
        publication_binary_path: str | None = (
            resolved_bound_binary.relative_to(root.resolve()).as_posix()
        )
    except ValueError:
        publication_binary_path = None
    return {
        "path": publication_manifest_path,
        "file_sha256": _file_sha256(path),
        "self_sha256": manifest["self_sha256"],
        "binary_sha256": binary_binding["sha256"],
        "binary_path": publication_binary_path,
        "binary_path_scope": (
            "REPOSITORY_RELATIVE_GENERATION_ARTIFACT"
            if publication_binary_path is not None
            else "CONTENT_HASH_ONLY_EXTERNAL_GENERATION_ARTIFACT"
        ),
        "transitive_source_bundle_sha256": inventory["bundle_sha256"],
        "dirty_source_state_sha256": expected_dirty["state_sha256"],
    }


def _assert_repository_safety(root: Path) -> dict[str, Any]:
    root = root.resolve()
    top = Path(_git_output(root, "rev-parse", "--show-toplevel")).resolve()
    _require(top == root, f"WRONG_REPOSITORY_ROOT:{top}")
    _require("czr004" not in str(root).lower(), "WRONG_REPOSITORY_CZR004")
    branch = _git_output(root, "branch", "--show-current")
    _require(
        branch == "codex/czr005-rewrite"
        or branch.startswith("codex/g4irsf15"),
        f"WRONG_BRANCH:{branch}",
    )
    protected_diff = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "diff",
            "--quiet",
            "--",
            "cpp/ics_core/runtime/bounded_local_pibt.hpp",
        ],
        check=False,
    )
    _require(
        protected_diff.returncode == 0,
        "PROTECTED_BOUNDED_LOCAL_PIBT_HAS_WORKTREE_DIFF",
    )
    return {
        "repository_root": str(root),
        "branch": branch,
        "head": _git_output(root, "rev-parse", "HEAD"),
        "origin": _git_output(root, "remote", "get-url", "origin"),
    }


def _protected_inputs(root: Path) -> dict[str, Any]:
    map_path = root / MAP_PATH
    task_path = root / TASK_PATH
    _require(_file_sha256(map_path) == MAP_RAW_SHA256, "MAP_RAW_SHA256_DRIFT")
    _require(_file_sha256(task_path) == TASK_RAW_SHA256, "TASK_SHA256_DRIFT")
    canonical_map = assert_canonical_map(map_path)
    semantic = getattr(canonical_map, "semantic_sha256", MAP_SEMANTIC_SHA256)
    _require(semantic == MAP_SEMANTIC_SHA256, "MAP_SEMANTIC_SHA256_DRIFT")
    prefix = g12.load_input_prefix(FULL_SEGMENT_COUNT, root=root)
    _require(
        prefix.size_segments == FULL_SEGMENT_COUNT
        and prefix.raw_bag_count == FULL_RAW_BAG_COUNT
        and prefix.prefix_sha256 == TASK_RAW_SHA256,
        "ORIGINAL_TASK_IDENTITY_DRIFT",
    )
    runtime_mapping = [
        {
            "runtime_bag_id": index,
            "segment_id": str(row["segment_id"]),
            "task_id": int(row["task_id"]),
        }
        for index, row in enumerate(prefix.rows)
    ]
    raw_bag_mapping: dict[int, list[tuple[int, str]]] = defaultdict(list)
    original_entry_by_task: dict[int, float] = {}
    workload_fields: list[tuple[str, str, Any]] = [
        (
            "schema",
            "s",
            "czr005.g4irsf15.input_runtime_cohort_order.v1",
        ),
        ("request_count", "u", len(prefix.rows)),
    ]
    for runtime_bag_id, row in enumerate(prefix.rows):
        task_id = int(row["task_id"])
        original_entry = float(row["original_entry_time"])
        release = float(row["pass_time"])
        deadline = float(row["std"])
        source = str(
            row.get("source", f"node_{int(row['start'])}")
        )
        _require(
            math.isfinite(original_entry)
            and math.isfinite(release)
            and math.isfinite(deadline)
            and original_entry <= release,
            f"INVALID_PROTECTED_REQUEST_TIMES:{task_id}",
        )
        previous = original_entry_by_task.setdefault(task_id, original_entry)
        _require(
            previous == original_entry,
            f"ORIGINAL_ENTRY_NOT_CONSTANT_PER_TASK:{task_id}",
        )
        raw_bag_mapping[task_id].append(
            (runtime_bag_id, str(row["segment_id"]))
        )
        workload_fields.append(
            (
                "request",
                "s",
                _canonical_fields_payload(
                    [
                        ("runtime_bag_id", "u", runtime_bag_id),
                        ("task_id", "i", task_id),
                        ("segment_id", "s", str(row["segment_id"])),
                        ("start", "i", int(row["start"])),
                        ("goal", "i", int(row["goal"])),
                        ("release_time", "d", release),
                        ("deadline", "d", deadline),
                        ("source", "s", source),
                    ]
                ),
            )
        )
    raw_mapping_rows = [
        {
            "task_id": task_id,
            "segment_ids_in_protected_input_order": [
                segment_id for _, segment_id in entries
            ],
        }
        for task_id, entries in sorted(raw_bag_mapping.items())
    ]
    original_entry_fields: list[tuple[str, str, Any]] = [
        (
            "schema",
            "s",
            "czr005.g4irsf15.raw_bag_original_entry_mapping.v1",
        ),
        ("raw_bag_count", "u", len(raw_bag_mapping)),
    ]
    for task_id, entries in sorted(raw_bag_mapping.items()):
        original_entry_fields.append(
            (
                "raw_bag",
                "s",
                _canonical_fields_payload(
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
        "map": {
            "path": MAP_PATH.as_posix(),
            "raw_sha256": MAP_RAW_SHA256,
            "semantic_sha256": MAP_SEMANTIC_SHA256,
        },
        "task": {
            "path": TASK_PATH.as_posix(),
            "raw_sha256": TASK_RAW_SHA256,
            "segment_count": FULL_SEGMENT_COUNT,
            "raw_bag_count": FULL_RAW_BAG_COUNT,
            "input_runtime_cohort_sha256": _canonical_fields_sha256(
                workload_fields
            ),
            "runtime_segment_mapping_sha256": _canonical_sha256(
                runtime_mapping
            ),
            "raw_bag_mapping_sha256": _canonical_sha256(
                raw_mapping_rows
            ),
            "raw_bag_original_entry_mapping_sha256": (
                _canonical_fields_sha256(original_entry_fields)
            ),
        },
        "model": {
            "path": MODEL_PATH.as_posix(),
            "raw_sha256": _file_sha256(root / MODEL_PATH),
        },
    }


def _source_identity(root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for relative in SOURCE_PATHS:
        path = root / relative
        rows.append(
            {
                "path": relative.as_posix(),
                "sha256": _file_sha256(path),
                "byte_count": path.stat().st_size,
            }
        )
    rows.sort(key=lambda row: row["path"])
    return {
        "files": rows,
        "source_bundle_sha256": _canonical_sha256(rows),
    }


def _load_model(root: Path) -> dict[str, Any]:
    path = root / MODEL_PATH
    model_sha256 = _file_sha256(path)
    _require(model_sha256 == MODEL_SHA256, "FROZEN_MODEL_SHA256_DRIFT")
    try:
        model = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CampaignError("INVALID_FROZEN_MODEL") from exc
    _require(isinstance(model, dict), "FROZEN_MODEL_NOT_OBJECT")
    w1, b1, w2 = model.get("w1"), model.get("b1"), model.get("w2")
    _require(
        isinstance(w1, list)
        and len(w1) == 22
        and all(isinstance(row, list) and len(row) == 22 for row in w1),
        "FROZEN_MODEL_W1_DIMENSION_DRIFT",
    )
    _require(isinstance(b1, list) and len(b1) == 22, "MODEL_B1_DIMENSION")
    _require(isinstance(w2, list) and len(w2) == 22, "MODEL_W2_DIMENSION")
    normalized = {
        "w1": [[float(value) for value in row] for row in w1],
        "b1": [float(value) for value in b1],
        "w2": [float(value) for value in w2],
        "b2": float(model["b2"]),
        "risk_margin": float(model["risk_margin_threshold"]),
        "risk_bottleneck": float(model["risk_bottleneck_threshold"]),
        "sha256": model_sha256,
    }
    _require(
        all(
            math.isfinite(value)
            for row in normalized["w1"]
            for value in row
        )
        and all(math.isfinite(value) for value in normalized["b1"])
        and all(math.isfinite(value) for value in normalized["w2"])
        and math.isfinite(normalized["b2"])
        and normalized["risk_margin"] == 1.0
        and normalized["risk_bottleneck"] == 5.0,
        "FROZEN_MODEL_NUMERIC_DRIFT",
    )
    return normalized


def _load_exact_module(binary: Path) -> ModuleType:
    binary = binary.resolve(strict=True)
    existing = sys.modules.get("czr005_cpp")
    if existing is not None:
        loaded = Path(str(getattr(existing, "__file__", ""))).resolve()
        _require(loaded == binary, f"CPP_MODULE_ALREADY_LOADED_FROM:{loaded}")
        return existing
    specification = importlib.util.spec_from_file_location("czr005_cpp", binary)
    _require(
        specification is not None and specification.loader is not None,
        f"CPP_BINARY_NOT_LOADABLE:{binary}",
    )
    module = importlib.util.module_from_spec(specification)
    sys.modules["czr005_cpp"] = module
    specification.loader.exec_module(module)
    loaded = Path(str(getattr(module, "__file__", ""))).resolve()
    _require(loaded == binary, f"CPP_BINARY_PATH_MISMATCH:{loaded}:{binary}")
    return module


def _process_memory_snapshot() -> dict[str, Any]:
    """Return current/peak resident memory without an optional dependency."""

    if os.name == "nt":
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        get_current_process = kernel32.GetCurrentProcess
        get_current_process.argtypes = []
        get_current_process.restype = wintypes.HANDLE
        get_memory = psapi.GetProcessMemoryInfo
        get_memory.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        get_memory.restype = wintypes.BOOL
        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        process = get_current_process()
        succeeded = get_memory(
            process, ctypes.byref(counters), counters.cb
        )
        _require(bool(succeeded), "WINDOWS_PROCESS_MEMORY_SAMPLE_FAILED")
        return {
            "sampler": "WINDOWS_PSAPI_GET_PROCESS_MEMORY_INFO",
            "resident_bytes": int(counters.WorkingSetSize),
            "peak_resident_bytes": int(counters.PeakWorkingSetSize),
        }
    try:
        import resource
    except ImportError as exc:  # pragma: no cover - non-Windows exotic host
        raise CampaignError("PROCESS_MEMORY_SAMPLER_UNAVAILABLE") from exc
    usage = resource.getrusage(resource.RUSAGE_SELF)
    # Linux reports KiB; macOS reports bytes.
    multiplier = 1 if sys.platform == "darwin" else 1024
    return {
        "sampler": "GETRUSAGE_RUSAGE_SELF",
        "resident_bytes": None,
        "peak_resident_bytes": int(usage.ru_maxrss) * multiplier,
    }


def _runtime_records(
    root: Path,
) -> tuple[list[Any], list[Any], list[list[float]], list[Any], Any]:
    prefix = g12.load_input_prefix(FULL_SEGMENT_COUNT, root=root)
    graph = assert_canonical_map(root / MAP_PATH)
    nodes, edges, heuristic = canonical_graph_records(graph)
    bags = g12.binding_bag_records(prefix)
    _require(len(bags) == FULL_SEGMENT_COUNT, "BAG_RECORD_COUNT_DRIFT")
    return nodes, edges, heuristic, bags, prefix


def _native_arguments(root: Path) -> tuple[list[Any], dict[str, Any], Any]:
    nodes, edges, heuristic, bags, prefix = _runtime_records(root)
    model = _load_model(root)
    arguments = [
        nodes,
        edges,
        heuristic,
        bags,
        model["w1"],
        model["b1"],
        model["w2"],
        model["b2"],
        model["risk_margin"],
        model["risk_bottleneck"],
        model["sha256"],
        [float(row["original_entry_time"]) for row in prefix.rows],
    ]
    return arguments, {"model": model, "bag_records": bags}, prefix


def _call_exact_binary(
    *,
    root: Path,
    binary: Path,
    function_name: str,
    arguments: Sequence[Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    binary = binary.resolve(strict=True)
    before = _file_sha256(binary)
    module = _load_exact_module(binary)
    function = getattr(module, function_name, None)
    _require(callable(function), f"NATIVE_FUNCTION_MISSING:{function_name}")
    memory_before = _process_memory_snapshot()
    started = time.time()
    payload = function(*arguments)
    elapsed = time.time() - started
    memory_after = _process_memory_snapshot()
    after = _file_sha256(binary)
    _require(before == after, "CPP_BINARY_CHANGED_DURING_EXECUTION")
    _require(isinstance(payload, dict), "NATIVE_PAYLOAD_NOT_OBJECT")
    try:
        publication_binary_path = binary.relative_to(
            root.resolve()
        ).as_posix()
    except ValueError:
        publication_binary_path = None
    return dict(payload), {
        "path": publication_binary_path,
        "path_scope": (
            "REPOSITORY_RELATIVE_GENERATION_ARTIFACT"
            if publication_binary_path is not None
            else "CONTENT_HASH_ONLY_EXTERNAL_GENERATION_ARTIFACT"
        ),
        "sha256_before": before,
        "sha256_after": after,
        "unchanged": before == after,
        "elapsed_wall_seconds": elapsed,
        "process_memory_before": memory_before,
        "process_memory_after": memory_after,
        "peak_resident_bytes": memory_after["peak_resident_bytes"],
    }


def _validate_terminal_invariants(
    invariants: Any,
    replay_hashes: Any,
    *,
    label: str,
) -> None:
    _require(isinstance(invariants, dict), f"{label}_INVARIANTS_MISSING")
    exact_counts = {
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
    for name, expected in exact_counts.items():
        _require(
            invariants.get(name) == expected,
            f"{label}_TERMINAL_INVARIANT:{name}",
        )
    _require(
        _strict_int(
            invariants.get("event_count"),
            f"{label}.event_count",
            minimum=1,
        )
        > 0,
        f"{label}_NO_EVENTS",
    )
    _require(
        invariants.get("max_selected_edges_per_bag") in (0, 1),
        f"{label}_RESERVATION_DEPTH",
    )
    for name in (
        "event_limit_reached",
        "time_limit_reached",
    ):
        _require(invariants.get(name) is False, f"{label}_{name}")
    for name in (
        "merge_grant_conservation_holds",
        "merge_grant_active_bijection_holds",
        "merge_grant_runtime_owned_capability",
        "merge_grant_exact_slot_no_future_shift",
        "live_safety_pass",
        "formal_hard_gate_evaluated",
        "formal_hard_gate_pass",
    ):
        _require(invariants.get(name) is True, f"{label}_{name}")
    _require(
        _strict_float(
            invariants.get("artificial_batch_delay_seconds"),
            f"{label}.artificial_batch_delay_seconds",
        )
        == 0.0,
        f"{label}_ARTIFICIAL_DELAY",
    )
    _require(
        invariants.get("hard_gate_fail_reasons") == [],
        f"{label}_HARD_GATE_REASONS",
    )
    _require(isinstance(replay_hashes, dict), f"{label}_REPLAY_HASHES")
    _require(
        set(replay_hashes)
        == {
            "complete_bags_sha256",
            "segment_result_sha256",
            "junction_state_sha256",
            "algorithm_summary_sha256",
            "deterministic_result_sha256",
        }
        and all(_is_sha256(value) for value in replay_hashes.values()),
        f"{label}_REPLAY_HASH_DRIFT",
    )


def _validate_native_input_binding(
    payload: Mapping[str, Any],
    *,
    protected: Mapping[str, Any],
    label: str,
) -> None:
    task = protected["task"]
    _require(
        payload.get("input_request_count") == FULL_SEGMENT_COUNT
        and payload.get("raw_bag_count") == FULL_RAW_BAG_COUNT,
        f"{label}_PROTECTED_COHORT_SIZE",
    )
    for field in (
        "input_runtime_cohort_sha256",
        "h_system_cohort_mapping_sha256",
        "raw_bag_mapping_sha256",
        "raw_bag_original_entry_mapping_sha256",
    ):
        protected_field = (
            "runtime_segment_mapping_sha256"
            if field == "h_system_cohort_mapping_sha256"
            else field
        )
        _require(
            payload.get(field) == task.get(protected_field),
            f"{label}_INPUT_BINDING:{field}",
        )


def _validate_skeleton_scan_payload(
    payload: Mapping[str, Any],
    *,
    protected: Mapping[str, Any],
) -> list[dict[str, Any]]:
    _require(
        payload.get("schema") == SKELETON_SCAN_SCHEMA,
        "SKELETON_SCAN_SCHEMA_DRIFT",
    )
    _require(
        payload.get("formal_pass_claimed") is False
        and payload.get("outcome_free") is True
        and payload.get("sealed_descriptor_materialization_required") is True,
        "SKELETON_SCAN_CLAIM_DRIFT",
    )
    _require(
        payload.get("evidence_scope")
        == "OUTCOME_FREE_NATIVE_PREPOP_SKELETON_CENSUS",
        "SKELETON_SCAN_EVIDENCE_SCOPE",
    )
    _require(
        payload.get("census_complete") is True
        and payload.get("terminal_finalized") is True
        and payload.get("protected_full_1x_shape") is True,
        "SKELETON_CENSUS_NOT_TERMINAL_COMPLETE",
    )
    _validate_terminal_invariants(
        payload.get("terminal_invariants"),
        payload.get("terminal_replay_hashes"),
        label="SKELETON_CENSUS",
    )
    _validate_native_input_binding(
        payload, protected=protected, label="SKELETON_SCAN"
    )
    controls = payload.get("frozen_controls")
    _require(isinstance(controls, dict), "SCAN_CONTROLS_MISSING")
    for name, expected in FROZEN_CONTROLS.items():
        _require(controls.get(name) == expected, f"CONTROL_DRIFT:{name}")
    counts = payload.get("population_counts")
    skeletons = payload.get("skeletons")
    _require(
        isinstance(counts, dict) and set(counts) == set(KINDS),
        "SKELETON_KIND_INVENTORY",
    )
    _require(isinstance(skeletons, list), "SKELETON_ROWS_MISSING")
    seen_ids: set[str] = set()
    seen_groups: set[tuple[str, str]] = set()
    rows_by_kind: Counter[str] = Counter()
    action_count_by_kind: Counter[str] = Counter()
    normalized: list[dict[str, Any]] = []
    for raw in skeletons:
        _require(isinstance(raw, dict), "SKELETON_NOT_OBJECT")
        row = dict(raw)
        kind = str(row.get("kind"))
        skeleton_id = row.get("skeleton_id")
        population_group = row.get("population_group_sha256")
        _require(
            row.get("schema") == SKELETON_SCHEMA and kind in KINDS,
            "SKELETON_IDENTITY_SCHEMA",
        )
        _require(
            _is_sha256(skeleton_id)
            and skeleton_id == row.get("skeleton_selection_sha256")
            and _is_sha256(population_group),
            "SKELETON_CONTENT_ID",
        )
        _require(
            skeleton_id not in seen_ids
            and (kind, str(population_group)) not in seen_groups,
            "DUPLICATE_SKELETON_POPULATION_GROUP",
        )
        seen_ids.add(str(skeleton_id))
        seen_groups.add((kind, str(population_group)))
        _require(
            row.get("outcome_free") is True
            and row.get("runtime_state_sha256") is None
            and row.get("boundary_sha256") is None,
            "SKELETON_PRE_SEAL_LEAKAGE",
        )
        _require(
            row.get("baseline_action") != row.get("intervention_action"),
            "SKELETON_ACTION_NOT_DIFFERENT",
        )
        alternative_count = _strict_int(
            row.get("alternative_action_count"),
            "skeleton.alternative_action_count",
            minimum=1,
        )
        _require(
            row.get("candidate_action_count") == alternative_count
            and row.get("total_legal_action_count")
            == alternative_count + 1
            and row.get("candidate_action_count_semantics")
            == "ALTERNATIVES_EXCLUDING_BASELINE",
            "SKELETON_ACTION_COUNT_SEMANTICS",
        )
        _strict_int(row.get("event_ordinal"), "event_ordinal", minimum=0)
        runtime_id = _strict_int(
            row.get("runtime_bag_id"), "runtime_bag_id", minimum=0
        )
        _require(runtime_id < FULL_SEGMENT_COUNT, "SKELETON_RUNTIME_ID")
        for name in (
            "active_merge_capability_count",
            "pending_merge_request_count",
            "active_physical_fault_edge_count",
            "queued_bag_count",
        ):
            _strict_int(row.get(name), f"skeleton.{name}", minimum=0)
        _require(
            isinstance(row.get("pibt_prefilter_candidate_event"), bool),
            "SKELETON_PIBT_FLAG",
        )
        rows_by_kind[kind] += 1
        action_count_by_kind[kind] += alternative_count
        normalized.append(row)
    total = 0
    for kind in KINDS:
        count = counts[kind]
        _require(isinstance(count, dict), f"BAD_KIND_COUNT:{kind}")
        primary = _strict_int(
            count.get("primary_population_count"),
            f"{kind}.primary_population_count",
            minimum=0,
        )
        unique = _strict_int(
            count.get("unique_population_group_count"),
            f"{kind}.unique_population_group_count",
            minimum=0,
        )
        observed = _strict_int(
            count.get("observed_skeleton_count"),
            f"{kind}.observed_skeleton_count",
            minimum=0,
        )
        duplicates = _strict_int(
            count.get("duplicate_population_group_count"),
            f"{kind}.duplicate_population_group_count",
            minimum=0,
        )
        _require(
            primary == unique == rows_by_kind[kind]
            and observed >= primary + duplicates
            and count.get("eligible_action_count")
            == action_count_by_kind[kind],
            f"SKELETON_POPULATION_COUNT_DRIFT:{kind}",
        )
        total += primary
    _require(
        total == len(normalized) == payload.get("primary_population_count"),
        "SKELETON_POPULATION_TOTAL_DRIFT",
    )
    return normalized


def _validate_materialization_payload(
    payload: Mapping[str, Any],
    *,
    selected_skeletons: Sequence[Mapping[str, Any]],
    protected: Mapping[str, Any],
) -> list[dict[str, Any]]:
    _require(
        payload.get("schema") == MATERIALIZATION_SCHEMA
        and payload.get("formal_pass_claimed") is False
        and payload.get("evidence_scope")
        == "SELECTED_NATIVE_PREPOP_BOUNDARY_MATERIALIZATION",
        "MATERIALIZATION_SCHEMA_OR_SCOPE",
    )
    _validate_native_input_binding(
        payload, protected=protected, label="MATERIALIZATION"
    )
    controls = payload.get("frozen_controls")
    _require(isinstance(controls, dict), "MATERIALIZATION_CONTROLS")
    for name, expected in FROZEN_CONTROLS.items():
        _require(
            controls.get(name) == expected,
            f"MATERIALIZATION_CONTROL_DRIFT:{name}",
        )
    descriptors = payload.get("descriptors")
    expected_count = len(selected_skeletons)
    _require(
        isinstance(descriptors, list)
        and payload.get("selected_skeleton_count") == expected_count
        and payload.get("materialized_descriptor_count") == expected_count
        and len(descriptors) == expected_count,
        "MATERIALIZATION_COUNT_DRIFT",
    )
    selected_by_id = {
        str(row["skeleton_id"]): row for row in selected_skeletons
    }
    _require(
        len(selected_by_id) == expected_count,
        "SELECTED_SKELETON_DUPLICATE",
    )
    seen_descriptor_ids: set[str] = set()
    seen_skeleton_ids: set[str] = set()
    seen_groups: set[tuple[str, str]] = set()
    normalized: list[dict[str, Any]] = []
    for raw in descriptors:
        _require(isinstance(raw, dict), "DESCRIPTOR_NOT_OBJECT")
        row = dict(raw)
        descriptor_id = row.get("descriptor_id")
        skeleton_id = row.get("skeleton_id")
        kind = str(row.get("kind"))
        clone_group = row.get("clone_group_id")
        _require(
            row.get("schema") == DESCRIPTOR_SCHEMA
            and _is_sha256(descriptor_id)
            and _is_sha256(skeleton_id)
            and _is_sha256(clone_group)
            and kind in KINDS,
            "SEALED_DESCRIPTOR_IDENTITY",
        )
        selected = selected_by_id.get(str(skeleton_id))
        _require(selected is not None, "MATERIALIZED_UNSELECTED_SKELETON")
        for field in (
            "kind",
            "event_ordinal",
            "population_group_sha256",
            "runtime_bag_id",
        ):
            _require(
                row.get(field) == selected.get(field),
                f"MATERIALIZED_SKELETON_DRIFT:{field}",
            )
        _require(
            row.get("population_selection_sha256")
            == selected.get("skeleton_selection_sha256")
            == skeleton_id,
            "MATERIALIZED_SKELETON_DRIFT:population_selection_sha256",
        )
        _require(
            descriptor_id not in seen_descriptor_ids
            and str(skeleton_id) not in seen_skeleton_ids
            and (kind, str(clone_group)) not in seen_groups,
            "DUPLICATE_SEALED_DESCRIPTOR",
        )
        seen_descriptor_ids.add(str(descriptor_id))
        seen_skeleton_ids.add(str(skeleton_id))
        seen_groups.add((kind, str(clone_group)))
        hashes = row.get("intervention_sha256_by_horizon")
        _require(
            isinstance(hashes, dict)
            and row.get("intervention_sha256") == descriptor_id
            and hashes.get("H_bag") == descriptor_id
            and _is_sha256(hashes.get("H_system"))
            and row.get("horizon") == "H_bag",
            "DESCRIPTOR_INTERVENTION_HASH_DRIFT",
        )
        _require(
            row.get("baseline_action") != row.get("intervention_action")
            and row.get("queue_top_not_popped") is True
            and row.get("staged_event_sink_empty") is True,
            "DESCRIPTOR_NOT_PREPOP_ACTION_CHANGE",
        )
        for counter in (
            "runtime_global_scan_count",
            "runtime_future_route_read_count",
            "runtime_future_schedule_read_count",
        ):
            _require(row.get(counter) == 0, f"DESCRIPTOR_LEAKAGE:{counter}")
        _require(
            row.get("reservation_depth") == 1
            and row.get("max_selected_edges_per_bag") in (0, 1),
            "DESCRIPTOR_RESERVATION_DEPTH_DRIFT",
        )
        merged = dict(row)
        for field in (
            "offline_sampling_metadata",
            "coverage_tags",
            "sampling_stratum_id",
            "sampling",
        ):
            merged[field] = selected[field]
        merged["sample_sha256"] = descriptor_id
        sampling = dict(merged["sampling"])
        sampling["cluster_id"] = str(clone_group)
        sampling["cluster_bootstrap_unit"] = "clone_group_id"
        merged["sampling"] = sampling
        normalized.append(merged)
    _require(
        seen_skeleton_ids == set(selected_by_id),
        "MATERIALIZATION_NOT_ONE_TO_ONE",
    )
    return normalized


def _load_offline_rows(root: Path) -> tuple[dict[int, dict[str, str]], str]:
    path = root / OFFLINE_TAIL_PATH
    digest = _file_sha256(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_task: dict[int, dict[str, str]] = {}
    for row in rows:
        task_id = int(row["task_id"])
        _require(task_id not in by_task, f"DUPLICATE_OFFLINE_TASK:{task_id}")
        by_task[task_id] = row
    _require(len(by_task) == FULL_RAW_BAG_COUNT, "OFFLINE_TASK_COUNT_DRIFT")
    return by_task, digest


def _truth(text: Any) -> bool:
    return str(text).strip().lower() in {"1", "true", "yes"}


def _contention_bucket(row: Mapping[str, Any]) -> str:
    for name in (
        "destination_pending_count",
        "local_destination_pending_count",
        "pending_merge_request_count",
        "active_merge_capability_count",
        "source_ready_count",
        "local_ready_count",
        "queue_occupancy_count",
    ):
        value = row.get(name)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 2:
            return "HIGH"
    return "HIGH" if int(row.get("candidate_action_count", 0)) >= 3 else "LOW"


def _coverage_tags(
    row: Mapping[str, Any],
    offline: Mapping[str, str],
    bag_record: Sequence[Any],
) -> list[str]:
    segment_id, _, release, deadline, start, goal, source = bag_record
    top_tail = _truth(offline.get("top_1pct_f2_slow")) or _truth(
        offline.get("top_1pct_delta")
    )
    divergence = int(offline.get("action_divergence_count", "0") or 0) > 0
    entry_band = offline.get("entry_time_band", "").lower()
    slack = offline.get("deadline_slack_bucket", "").lower()
    bag_class = offline.get("bag_class", "").lower()
    hour = int(float(offline.get("hour", "0") or 0))
    start_node = int(start)
    goal_node = int(goal)
    node = int(row["node"])
    contention = _contention_bucket(row)
    tags = {
        "top_tail" if top_tail else "non_tail",
        "route_divergence" if divergence else "no_divergence",
        f"entry_{entry_band}" if entry_band in {"early", "normal", "late"} else "",
        f"slack_{slack}" if slack in {"tight", "ample"} else "",
        "storage" if "storage" in bag_class or "storage_" in str(segment_id) else "direct",
        f"goal_{goal_node}" if goal_node in {48, 49, 50} else "goal_other",
        "hour_6" if hour == 6 else "hour_other",
        (
            "source_0_1_2_53"
            if start_node in {0, 1, 2, 53}
            else "source_3_4_5"
            if start_node in {3, 4, 5}
            else "source_other"
        ),
        "node_52" if node == 52 else "node_19_22" if node in {19, 22} else "node_other",
        "high_contention" if contention == "HIGH" else "low_contention",
    }
    p2_value = row.get(
        "pibt_prefilter_candidate_event",
        row.get("p2_prefilter_candidate"),
    )
    if p2_value is True:
        tags.add("p2_prefilter_candidate")
    tags.discard("")
    return sorted(tags)


def annotate_population(
    descriptors: Sequence[Mapping[str, Any]],
    *,
    bag_records: Sequence[Sequence[Any]],
    offline_by_task: Mapping[int, Mapping[str, str]],
) -> list[dict[str, Any]]:
    """Add offline-only sampling metadata without changing native identity."""

    rows: list[dict[str, Any]] = []
    for source in descriptors:
        row = dict(source)
        runtime_id = int(row["runtime_bag_id"])
        _require(
            0 <= runtime_id < len(bag_records),
            f"RUNTIME_BAG_ID_OUT_OF_RANGE:{runtime_id}",
        )
        bag = bag_records[runtime_id]
        task_id = int(bag[1])
        offline = offline_by_task.get(task_id)
        _require(offline is not None, f"OFFLINE_TASK_MISSING:{task_id}")
        tags = _coverage_tags(row, offline, bag)
        top_tail = "top_tail" in tags
        divergence = "route_divergence" in tags
        contention = _contention_bucket(row)
        row["offline_sampling_metadata"] = {
            "runtime_only": False,
            "must_not_enter_policy_features": True,
            "task_id": task_id,
            "segment_id": str(bag[0]),
            "source_node": int(bag[4]),
            "goal": int(bag[5]),
            "source_label": str(bag[6]),
            "release_time": float(bag[2]),
            "deadline": float(bag[3]),
            "top_tail": top_tail,
            "route_divergence": divergence,
            "entry_time_band": offline.get("entry_time_band", ""),
            "deadline_slack_bucket": offline.get(
                "deadline_slack_bucket", ""
            ),
            "bag_class": offline.get("bag_class", ""),
            "hour": int(float(offline.get("hour", "0") or 0)),
        }
        row["coverage_tags"] = tags
        row["sampling_stratum_id"] = "|".join(
            (
                str(row["kind"]),
                "TAIL" if top_tail else "BODY",
                "DIVERGENCE" if divergence else "NO_DIVERGENCE",
                contention,
            )
        )
        rows.append(row)
    return rows


def _allocate(
    capacities: Mapping[str, int],
    total: int,
    weights: Mapping[str, float],
    *,
    minimum_each: int = 0,
) -> dict[str, int]:
    _require(total >= 0, "NEGATIVE_ALLOCATION_TOTAL")
    _require(total <= sum(capacities.values()), "ALLOCATION_EXCEEDS_CAPACITY")
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
    while remaining > 0:
        available = [
            key
            for key, capacity in capacities.items()
            if allocation[key] < capacity
        ]
        _require(available, "ALLOCATION_NO_AVAILABLE_STRATUM")
        scores = {
            key: max(0.0, float(weights.get(key, 1.0)))
            for key in available
        }
        denominator = sum(scores.values())
        if denominator <= 0.0:
            scores = {key: 1.0 for key in available}
            denominator = float(len(available))
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
            if remaining == 0:
                break
            allocation[key] += 1
            remaining -= 1
    return allocation


def _hash_rank(namespace: str, descriptor_id: str) -> str:
    return hashlib.sha256(f"{namespace}:{descriptor_id}".encode()).hexdigest()


def _row_selection_id(row: Mapping[str, Any]) -> str:
    value = row.get("descriptor_id", row.get("skeleton_id"))
    _require(_is_sha256(value), "ROW_SELECTION_ID_MISSING")
    return str(value)


def select_descriptor_pool(
    population: Sequence[Mapping[str, Any]],
    *,
    pool_size: int = MIN_DESCRIPTOR_POOL,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Return a deterministic weighted-stratum min-hash sample.

    Half of each kind allocation is proportional population min-hash.  The
    second half is allocated with a 4x tail multiplier.  Every selected row
    carries the final union probability ``pi_h=n_h/N_h`` and inverse analysis
    weight.  This keeps the population estimator separate from descriptive
    tail enrichment.
    """

    _require(pool_size >= MIN_DESCRIPTOR_POOL, "POOL_BELOW_4096")
    by_kind: dict[str, list[Mapping[str, Any]]] = {
        kind: [row for row in population if row.get("kind") == kind]
        for kind in KINDS
    }
    desired = dict(FORMAL_ATTEMPT_TARGETS)
    extra = pool_size - sum(desired.values())
    if extra > 0:
        capacity = {
            kind: max(0, len(by_kind[kind]) - desired[kind])
            for kind in KINDS
        }
        extra_allocation = _allocate(
            capacity,
            min(extra, sum(capacity.values())),
            {kind: float(len(by_kind[kind])) for kind in KINDS},
        )
        for kind, count in extra_allocation.items():
            desired[kind] += count
    _require(
        sum(desired.values()) == pool_size,
        "DESCRIPTOR_POOL_POPULATION_TOO_SMALL",
    )
    selected: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    stratum_design: dict[str, Any] = {}
    for kind in KINDS:
        _require(
            len(by_kind[kind]) >= desired[kind],
            f"INSUFFICIENT_DESCRIPTOR_POPULATION:{kind}",
        )
        groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in by_kind[kind]:
            groups[str(row["sampling_stratum_id"])].append(row)
        capacities = {key: len(rows) for key, rows in groups.items()}
        base_total = desired[kind] // 2
        base = _allocate(
            capacities,
            base_total,
            {key: float(capacity) for key, capacity in capacities.items()},
            minimum_each=1,
        )
        remaining_capacities = {
            key: capacities[key] - base[key] for key in capacities
        }
        enriched = _allocate(
            remaining_capacities,
            desired[kind] - base_total,
            {
                key: (
                    float(remaining_capacities[key])
                    * (4.0 if "|TAIL|" in key else 1.0)
                )
                for key in capacities
            },
        )
        final = {key: base[key] + enriched[key] for key in capacities}
        for stratum, rows in groups.items():
            ranked = sorted(
                rows,
                key=lambda row: (
                    _hash_rank(
                        "g4irsf15-population", _row_selection_id(row)
                    ),
                    int(row["event_ordinal"]),
                ),
            )
            n_h = final[stratum]
            n_base = base[stratum]
            N_h = len(ranked)
            pi_h = n_h / N_h
            stratum_design[stratum] = {
                "kind": kind,
                "N_h": N_h,
                "population_min_hash_n": n_base,
                "enriched_n": enriched[stratum],
                "n_h": n_h,
                "pi_h": pi_h,
                "analysis_weight": 1.0 / pi_h,
                "tail_enrichment_multiplier": (
                    4.0 if "|TAIL|" in stratum else 1.0
                ),
            }
            for rank, source in enumerate(ranked[:n_h], start=1):
                row = dict(source)
                row["sampling"] = {
                    **stratum_design[stratum],
                    "sampling_stratum_id": stratum,
                    "rank_within_stratum": rank,
                    "selection_panel": (
                        "POPULATION_MIN_HASH"
                        if rank <= n_base
                        else "ENRICHED_TAIL_MIN_HASH"
                        if "|TAIL|" in stratum
                        else "STRATIFIED_MIN_HASH_FILL"
                    ),
                    "rank_sha256": _hash_rank(
                        "g4irsf15-population", _row_selection_id(row)
                    ),
                    "cluster_id": str(
                        row.get("clone_group_id", row.get("skeleton_id"))
                    ),
                    "cluster_bootstrap_unit": (
                        "clone_group_id"
                        if row.get("clone_group_id") is not None
                        else "skeleton_id_pending_descriptor_materialization"
                    ),
                }
                selected.append(row)
    selected.sort(
        key=lambda row: (
            str(row["kind"]),
            _hash_rank("g4irsf15-pool-order", _row_selection_id(row)),
        )
    )
    selected_ids = {_row_selection_id(row) for row in selected}
    _require(len(selected_ids) == pool_size, "POOL_DUPLICATE_DESCRIPTOR")
    all_tags: Counter[str] = Counter()
    selected_tags: Counter[str] = Counter()
    for row in population:
        all_tags.update(row.get("coverage_tags", []))
    for row in selected:
        selected_tags.update(row.get("coverage_tags", []))
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
    blockers: list[str] = []
    for tag in required_tags:
        N = all_tags[tag]
        n = selected_tags[tag]
        status = (
            "COVERED"
            if n > 0
            else "ZERO_ELIGIBLE_SUPPORT"
            if N == 0
            else "SAMPLE_COVERAGE_MISS"
        )
        if status != "COVERED":
            blockers.append(f"{tag}:{status}")
        coverage_rows.append(
            {
                "row_type": "REQUIRED_CATEGORY",
                "coverage_dimension": tag,
                "sampling_stratum_id": "",
                "N_population": N,
                "n_descriptor_pool": n,
                "N_h": "",
                "n_h": "",
                "pi_h": "",
                "analysis_weight": "",
                "coverage_status": status,
            }
        )
    coverage_rows.append(
        {
            "row_type": "REQUIRED_CATEGORY",
            "coverage_dimension": "random_eligible_control",
            "sampling_stratum_id": "",
            "N_population": len(population),
            "n_descriptor_pool": sum(
                row["sampling"]["selection_panel"] == "POPULATION_MIN_HASH"
                for row in selected
            ),
            "N_h": "",
            "n_h": "",
            "pi_h": "",
            "analysis_weight": "",
            "coverage_status": "COVERED",
        }
    )
    for stratum, design in sorted(stratum_design.items()):
        coverage_rows.append(
            {
                "row_type": "SAMPLING_STRATUM",
                "coverage_dimension": "",
                "sampling_stratum_id": stratum,
                "N_population": design["N_h"],
                "n_descriptor_pool": design["n_h"],
                "N_h": design["N_h"],
                "n_h": design["n_h"],
                "pi_h": design["pi_h"],
                "analysis_weight": design["analysis_weight"],
                "coverage_status": "COVERED",
            }
        )
    return selected, coverage_rows, {
        "strata": stratum_design,
        "coverage_blockers": blockers,
        "pool_sha256": _canonical_sha256(selected),
    }


def _target_native_projection(row: Mapping[str, Any]) -> dict[str, Any]:
    """Keep the content-addressed target plus harmless offline annotations."""

    return dict(row)


def _with_horizon(row: Mapping[str, Any], horizon: str) -> dict[str, Any]:
    _require(horizon in {"H_bag", "H_system"}, "BAD_HORIZON")
    result = dict(row)
    hashes = result.get("intervention_sha256_by_horizon")
    _require(isinstance(hashes, dict), "TARGET_HORIZON_HASHES_MISSING")
    result["horizon"] = horizon
    result["intervention_sha256"] = hashes[horizon]
    result["target_key"] = f"{result['descriptor_id']}:{horizon}"
    return result


def _descriptor_order(namespace: str, row: Mapping[str, Any]) -> tuple[str, int]:
    return (
        _hash_rank(namespace, str(row["descriptor_id"])),
        int(row["event_ordinal"]),
    )


def _select_stratified_panel(
    rows: Sequence[Mapping[str, Any]],
    *,
    total: int,
    namespace: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Preregister fixed per-stratum counts, then min-hash within strata."""

    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        sampling = row.get("sampling")
        _require(isinstance(sampling, dict), "PANEL_POOL_SAMPLING_MISSING")
        groups[str(sampling["sampling_stratum_id"])].append(row)
    capacities = {stratum: len(group) for stratum, group in groups.items()}
    _require(total <= sum(capacities.values()), "PANEL_TOTAL_EXCEEDS_FRAME")
    allocation = _allocate(
        capacities,
        total,
        {stratum: float(capacity) for stratum, capacity in capacities.items()},
        minimum_each=1 if total >= len(capacities) else 0,
    )
    selected: list[dict[str, Any]] = []
    for stratum, group in sorted(groups.items()):
        ordered = sorted(
            group,
            key=lambda row: _descriptor_order(
                f"{namespace}:{stratum}", row
            ),
        )
        selected.extend(dict(row) for row in ordered[: allocation[stratum]])
    _require(len(selected) == total, "STRATIFIED_PANEL_COUNT_DRIFT")
    return selected, dict(sorted(allocation.items()))


def select_pilot_targets(
    pool: Sequence[Mapping[str, Any]],
    *,
    round_index: int = 1,
    excluded_descriptor_ids: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    _require(round_index in {1, 2}, "PILOT_ROUND_MUST_BE_1_OR_2")
    targets: list[dict[str, Any]] = []
    for kind in KINDS:
        rows = [row for row in pool if row.get("kind") == kind]
        excluded = {
            str(value) for value in (excluded_descriptor_ids or ())
        }
        if round_index == 2 and excluded_descriptor_ids is None:
            round1, _ = _select_stratified_panel(
                rows,
                total=PILOT_ATTEMPTS_PER_KIND,
                namespace=f"g4irsf15-pilot-r1:{kind}",
            )
            excluded = {str(row["descriptor_id"]) for row in round1}
        available = [
            row
            for row in rows
            if str(row["descriptor_id"]) not in excluded
        ]
        selected, _ = _select_stratified_panel(
            available,
            total=PILOT_ATTEMPTS_PER_KIND,
            namespace=f"g4irsf15-pilot-r{round_index}:{kind}",
        )
        targets.extend(_with_horizon(row, "H_bag") for row in selected)
    return sorted(
        targets, key=lambda row: (int(row["event_ordinal"]), row["target_key"])
    )


def select_formal_targets(
    pool: Sequence[Mapping[str, Any]],
    *,
    h_system_attempts: int = 0,
) -> list[dict[str, Any]]:
    targets, _ = preregister_formal_targets(
        pool,
        pilot_complete_by_kind={
            kind: PILOT_MIN_COMPLETE_PER_KIND for kind in KINDS
        },
        h_system_attempts=h_system_attempts,
    )
    return targets


def wilson_lower_bound(
    successes: int, attempts: int, *, z: float = 1.96
) -> float:
    _require(0 <= successes <= attempts and attempts > 0, "BAD_WILSON_COUNTS")
    proportion = successes / attempts
    z2 = z * z
    denominator = 1.0 + z2 / attempts
    center = proportion + z2 / (2.0 * attempts)
    radius = z * math.sqrt(
        proportion * (1.0 - proportion) / attempts
        + z2 / (4.0 * attempts * attempts)
    )
    return max(0.0, (center - radius) / denominator)


def preregister_formal_targets(
    pool: Sequence[Mapping[str, Any]],
    *,
    pilot_complete_by_kind: Mapping[str, int],
    h_system_attempts: int = 0,
    active_kinds: Sequence[str] = KINDS,
    excluded_pilot_descriptor_ids: Iterable[str] | None = None,
    pilot_rounds_excluded: Sequence[int] = (1, 2),
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    active = tuple(kind for kind in KINDS if kind in set(active_kinds))
    _require(len(active) >= 2, "FORMAL_REQUIRES_AT_LEAST_TWO_ACTIVE_KINDS")
    _require(
        len(active) == len(set(active_kinds)),
        "FORMAL_ACTIVE_KIND_INVENTORY_DRIFT",
    )
    formal_label_targets = {
        kind: FORMAL_LABEL_TARGETS[kind] for kind in active
    }
    missing_label_target = FORMAL_MIN_LABELS - sum(
        formal_label_targets.values()
    )
    if missing_label_target > 0:
        reallocation = _allocate(
            {kind: missing_label_target for kind in active},
            missing_label_target,
            {
                kind: float(FORMAL_LABEL_TARGETS[kind])
                for kind in active
            },
        )
        for kind, extra in reallocation.items():
            formal_label_targets[kind] += extra
    _require(
        sum(formal_label_targets.values()) == FORMAL_MIN_LABELS
        and all(
            formal_label_targets[kind] >= FORMAL_MIN_LABELS_PER_KIND
            for kind in active
        )
        and all(
            formal_label_targets[kind] < FORMAL_MIN_LABELS
            for kind in active
        ),
        "FORMAL_BLOCKED_KIND_REALLOCATION_INVALID",
    )
    if excluded_pilot_descriptor_ids is None:
        pilot_targets = [
            *select_pilot_targets(pool, round_index=1),
            *select_pilot_targets(pool, round_index=2),
        ]
        excluded_pilot_ids = {
            str(row["descriptor_id"]) for row in pilot_targets
        }
    else:
        excluded_pilot_ids = {
            str(value) for value in excluded_pilot_descriptor_ids
        }
    selected: list[dict[str, Any]] = []
    by_kind: dict[str, list[dict[str, Any]]] = {}
    preregistration: dict[str, Any] = {}
    for kind in active:
        successes = _strict_int(
            pilot_complete_by_kind.get(kind),
            f"pilot_complete_by_kind.{kind}",
            minimum=PILOT_MIN_COMPLETE_PER_KIND,
        )
        _require(
            successes <= PILOT_ATTEMPTS_PER_KIND,
            f"PILOT_SUCCESS_COUNT_TOO_LARGE:{kind}",
        )
        lower_bound = wilson_lower_bound(
            successes, PILOT_ATTEMPTS_PER_KIND
        )
        _require(lower_bound > 0.0, f"PILOT_WILSON_ZERO:{kind}")
        requested = int(
            math.ceil(formal_label_targets[kind] / lower_bound)
        )
        available = [
            dict(row)
            for row in pool
            if row.get("kind") == kind
            and str(row.get("descriptor_id")) not in excluded_pilot_ids
        ]
        count = min(requested, len(available))
        _require(count > 0, f"FORMAL_EMPTY_ACTIVE_KIND:{kind}")
        by_kind[kind], stratum_allocation = _select_stratified_panel(
            available,
            total=count,
            namespace=f"g4irsf15-formal:{kind}",
        )
        preregistration[kind] = {
            "pilot_attempt_count": PILOT_ATTEMPTS_PER_KIND,
            "pilot_complete_action_changing_count": successes,
            "wilson_z": 1.96,
            "wilson_lower_bound": lower_bound,
            "original_formal_label_target": FORMAL_LABEL_TARGETS[kind],
            "formal_label_target": formal_label_targets[kind],
            "reallocated_label_target": (
                formal_label_targets[kind] - FORMAL_LABEL_TARGETS[kind]
            ),
            "static_two_x_reference_not_used": FORMAL_ATTEMPT_TARGETS[kind],
            "rate_based_requested_attempts": requested,
            "available_after_pilot_exclusion": len(available),
            "preregistered_attempts": count,
            "descriptor_cap_applied": count < requested,
            "attempts_by_sampling_stratum": stratum_allocation,
        }
    pilot_success_total = sum(
        int(pilot_complete_by_kind[kind]) for kind in active
    )
    pilot_attempt_total = PILOT_ATTEMPTS_PER_KIND * len(active)
    h_system_lower_bound = wilson_lower_bound(
        pilot_success_total, pilot_attempt_total
    )
    auto_h_system_attempts = FORMAL_TARGET_H_SYSTEM
    if h_system_attempts == 0:
        h_system_attempts = auto_h_system_attempts
    else:
        _require(
            h_system_attempts >= auto_h_system_attempts,
            "H_SYSTEM_ATTEMPTS_BELOW_FIXED_AUDIT_PREREGISTRATION",
        )
    _require(
        h_system_attempts >= FORMAL_MIN_H_SYSTEM
        and h_system_attempts <= sum(len(rows) for rows in by_kind.values()),
        "H_SYSTEM_ATTEMPT_ALLOCATION_OUT_OF_RANGE",
    )
    h_alloc = _allocate(
        {kind: len(by_kind[kind]) for kind in active},
        h_system_attempts,
        {
            kind: float(formal_label_targets[kind])
            for kind in active
        },
    )
    used_clone_groups: set[str] = set()
    used_h_system_event_ordinals: set[int] = set()
    for kind in active:
        h_candidates = sorted(
            by_kind[kind],
            key=lambda row: _descriptor_order("g4irsf15-h-system", row),
        )
        h_ids: set[str] = set()
        if h_alloc[kind] == 0:
            for row in by_kind[kind]:
                selected.append(_with_horizon(row, "H_bag"))
            continue
        for row in h_candidates:
            clone_group = str(row["clone_group_id"])
            event_ordinal = int(row["event_ordinal"])
            if (
                clone_group in used_clone_groups
                or event_ordinal in used_h_system_event_ordinals
            ):
                continue
            used_clone_groups.add(clone_group)
            used_h_system_event_ordinals.add(event_ordinal)
            h_ids.add(str(row["descriptor_id"]))
            if len(h_ids) == h_alloc[kind]:
                break
        _require(
            len(h_ids) == h_alloc[kind],
            f"INSUFFICIENT_UNIQUE_H_SYSTEM_CLONES:{kind}",
        )
        for row in by_kind[kind]:
            selected.append(
                _with_horizon(
                    row,
                    "H_system"
                    if str(row["descriptor_id"]) in h_ids
                    else "H_bag",
                )
            )
    _require(
        len({row["target_key"] for row in selected}) == len(selected),
        "FORMAL_DUPLICATE_TARGET",
    )
    _require(
        len(
            {
                row["clone_group_id"]
                for row in selected
                if row["horizon"] == "H_system"
            }
        )
        == h_system_attempts,
        "H_SYSTEM_CLONE_GROUP_NOT_UNIQUE",
    )
    targets = sorted(
        selected, key=lambda row: (int(row["event_ordinal"]), row["target_key"])
    )
    _require(
        not (
            {str(row["descriptor_id"]) for row in targets}
            & excluded_pilot_ids
        ),
        "FORMAL_PILOT_DESCRIPTOR_CONTAMINATION",
    )
    return targets, {
        "method": (
            "TARGET_DIVIDED_BY_TWO_SIDED_95_PERCENT_WILSON_LOWER_"
            "ENDPOINT_CAPPED_AT_SEALED_POST_PILOT_POOL"
        ),
        "wilson_interval_convention": (
            "TWO_SIDED_95_PERCENT_LOWER_ENDPOINT_"
            "EQUIVALENT_ONE_SIDED_97_5_PERCENT"
        ),
        "active_kinds": list(active),
        "blocked_kinds": [kind for kind in KINDS if kind not in active],
        "formal_label_targets": dict(sorted(formal_label_targets.items())),
        "blocked_kind_target_reallocation": (
            "NONE_ALL_KINDS_ACTIVE"
            if len(active) == len(KINDS)
            else "PREREGISTERED_PROPORTIONAL_TO_ORIGINAL_KIND_TARGETS"
        ),
        "pilot_rounds_excluded": list(pilot_rounds_excluded),
        "excluded_pilot_descriptor_count": len(excluded_pilot_ids),
        "excluded_pilot_descriptor_ids": sorted(excluded_pilot_ids),
        "excluded_pilot_descriptor_ids_sha256": _canonical_sha256(
            sorted(excluded_pilot_ids)
        ),
        "per_kind": preregistration,
        "descriptor_cap_blocked": any(
            row["descriptor_cap_applied"]
            for row in preregistration.values()
        ),
        "h_system_preregistration": {
            "method": (
                "FIXED_256_FULL_SYSTEM_HARD_GATE_AND_EXTERNALITY_"
                "AUDIT_ATTEMPTS_NOT_INFERRED_FROM_H_BAG_RESPONSE"
            ),
            "pilot_attempt_count": pilot_attempt_total,
            "pilot_complete_action_changing_count": pilot_success_total,
            "wilson_z": 1.96,
            "pilot_h_bag_wilson_lower_bound_diagnostic_not_used": (
                h_system_lower_bound
            ),
            "complete_pair_target": FORMAL_TARGET_H_SYSTEM,
            "hard_minimum_complete_pairs": FORMAL_MIN_H_SYSTEM,
            "fixed_requested_attempts": auto_h_system_attempts,
            "preregistered_attempts": h_system_attempts,
            "h_system_population_effect_inference": (
                "DESCRIPTIVE_ONLY_HORIZON_ASSIGNMENT_PI_NOT_MODELED"
            ),
        },
    }


def build_contiguous_shards(
    targets: Sequence[Mapping[str, Any]],
    *,
    shard_size: int,
    h_system_targets_per_shard: int = DEFAULT_H_SYSTEM_TARGETS_PER_SHARD,
) -> list[dict[str, Any]]:
    _require(shard_size > 0, "SHARD_SIZE_NOT_POSITIVE")
    _require(
        h_system_targets_per_shard > 0,
        "H_SYSTEM_SHARD_SIZE_NOT_POSITIVE",
    )
    ordered = sorted(
        (dict(row) for row in targets),
        key=lambda row: (int(row["event_ordinal"]), str(row["target_key"])),
    )
    groups: list[list[dict[str, Any]]] = []
    for row in ordered:
        if not groups or int(groups[-1][0]["event_ordinal"]) != int(
            row["event_ordinal"]
        ):
            groups.append([row])
        else:
            groups[-1].append(row)
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_h_system = 0
    for group in groups:
        group_h_system = sum(
            row.get("horizon") == "H_system" for row in group
        )
        _require(
            group_h_system <= h_system_targets_per_shard,
            "ONE_EVENT_EXCEEDS_H_SYSTEM_SHARD_MEMORY_CAP",
        )
        if current and (
            len(current) + len(group) > shard_size
            or current_h_system + group_h_system
            > h_system_targets_per_shard
        ):
            chunks.append(current)
            current = []
            current_h_system = 0
        current.extend(group)
        current_h_system += group_h_system
    if current:
        chunks.append(current)
    shards: list[dict[str, Any]] = []
    previous_end = -1
    for index, rows in enumerate(chunks):
        start = int(rows[0]["event_ordinal"])
        end = int(rows[-1]["event_ordinal"])
        _require(start > previous_end, "SHARD_ORDINAL_RANGES_OVERLAP")
        previous_end = end
        projection = {
            "shard_index": index,
            "event_ordinal_start": start,
            "event_ordinal_end": end,
            "target_count": len(rows),
            "h_system_target_count": sum(
                row.get("horizon") == "H_system" for row in rows
            ),
            "target_keys": [row["target_key"] for row in rows],
            "targets": rows,
        }
        projection["shard_sha256"] = _canonical_sha256(projection)
        shards.append(projection)
    return shards


def attach_attempt_sampling(
    targets: Sequence[Mapping[str, Any]],
    *,
    pool: Sequence[Mapping[str, Any]],
    excluded_descriptor_ids: Iterable[str],
    panel: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Attach the preregistered two-stage panel inclusion probabilities."""

    excluded = {str(value) for value in excluded_descriptor_ids}
    counts = Counter(
        str(row.get("sampling", {}).get("sampling_stratum_id"))
        for row in targets
    )
    frame_counts: Counter[str] = Counter()
    excluded_counts: Counter[str] = Counter()
    frame_ids: set[str] = set()
    for source in pool:
        sampling = source.get("sampling")
        _require(isinstance(sampling, dict), "POOL_SAMPLING_MISSING")
        stratum = str(sampling["sampling_stratum_id"])
        descriptor_id = str(source["descriptor_id"])
        if descriptor_id in excluded:
            excluded_counts[stratum] += 1
        else:
            frame_counts[stratum] += 1
            frame_ids.add(descriptor_id)
    _require(
        all(str(row["descriptor_id"]) in frame_ids for row in targets),
        "ATTEMPT_TARGET_OUTSIDE_POST_EXCLUSION_FRAME",
    )
    result: list[dict[str, Any]] = []
    design: dict[str, Any] = {}
    for source in targets:
        row = dict(source)
        pool_sampling = row.get("sampling")
        _require(
            isinstance(pool_sampling, dict),
            "TARGET_POOL_SAMPLING_MISSING",
        )
        stratum = str(pool_sampling["sampling_stratum_id"])
        N_h = _strict_int(
            pool_sampling.get("N_h"), f"{stratum}.N_h", minimum=1
        )
        sealed_n_h = _strict_int(
            pool_sampling.get("n_h"),
            f"{stratum}.sealed_n_h",
            minimum=1,
        )
        pool_pi_h = _strict_float(
            pool_sampling.get("pi_h"), f"{stratum}.pool_pi_h"
        )
        _require(
            abs(pool_pi_h - sealed_n_h / N_h) <= 1e-15,
            f"POOL_PI_DRIFT:{stratum}",
        )
        stage2_frame_n_h = frame_counts[stratum]
        attempt_n_h = counts[stratum]
        _require(
            0 < attempt_n_h <= stage2_frame_n_h <= sealed_n_h <= N_h,
            f"ATTEMPT_SAMPLING_COUNT_DRIFT:{stratum}",
        )
        stage2_pi_h = attempt_n_h / stage2_frame_n_h
        post_exclusion_survival_pi_h = (
            stage2_frame_n_h / sealed_n_h
        )
        final_pi_h = (
            pool_pi_h
            * post_exclusion_survival_pi_h
            * stage2_pi_h
        )
        attempt_sampling = {
            "sampling_stratum_id": stratum,
            "N_h": N_h,
            "sealed_pool_n_h": sealed_n_h,
            "pool_pi_h": pool_pi_h,
            "excluded_before_panel_n_h": excluded_counts[stratum],
            "stage2_frame_n_h": stage2_frame_n_h,
            "post_exclusion_survival_pi_h": (
                post_exclusion_survival_pi_h
            ),
            "attempt_n_h": attempt_n_h,
            "n_h": attempt_n_h,
            "stage2_pi_h": stage2_pi_h,
            "pi_h": final_pi_h,
            "analysis_weight": 1.0 / final_pi_h,
            "selection_panel": panel,
            "selection_stages": (
                "SKELETON_POPULATION_TO_SEALED_POOL_TO_FINAL_ATTEMPT_PANEL"
            ),
            "probability_formula": (
                "pool_pi_h*post_exclusion_survival_pi_h*stage2_pi_h"
            ),
            "stage2_selection_rule": (
                "PREREGISTERED_FIXED_M_H_PER_STRATUM_DETERMINISTIC_MIN_HASH"
            ),
            "cluster_id": str(row["clone_group_id"]),
            "cluster_bootstrap_unit": "clone_group_id",
        }
        row["sealed_pool_sampling"] = dict(pool_sampling)
        row["sampling"] = attempt_sampling
        result.append(row)
        design[stratum] = {
            key: attempt_sampling[key]
            for key in (
                "sampling_stratum_id",
                "N_h",
                "sealed_pool_n_h",
                "pool_pi_h",
                "excluded_before_panel_n_h",
                "stage2_frame_n_h",
                "post_exclusion_survival_pi_h",
                "attempt_n_h",
                "stage2_pi_h",
                "pi_h",
                "analysis_weight",
                "selection_panel",
            )
        }
    return result, {
        "panel": panel,
        "excluded_descriptor_count": len(excluded),
        "excluded_descriptor_ids_sha256": _canonical_sha256(
            sorted(excluded)
        ),
        "stratum_count": len(design),
        "strata": dict(sorted(design.items())),
        "population_estimation": (
            "TWO_STAGE_POOL_TIMES_POST_EXCLUSION_STRATUM_PANEL_"
            "HORVITZ_THOMPSON_READY"
        ),
        "variance_estimation": "CLONE_GROUP_CLUSTER_BOOTSTRAP_READY",
    }


def _read_descriptor_pool(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest = _load_json(root / DESCRIPTOR_MANIFEST_PATH)
    _validate_self_bound(manifest, "descriptor_manifest")
    _require(
        manifest.get("schema") == DESCRIPTOR_MANIFEST_SCHEMA
        and manifest.get("status") == "READY_FOR_PILOT",
        "DESCRIPTOR_MANIFEST_NOT_READY_FOR_PILOT",
    )
    coverage_blockers = manifest.get("sampling_design", {}).get(
        "coverage_blockers"
    )
    _require(
        isinstance(coverage_blockers, list)
        and not any(
            str(blocker).endswith(":SAMPLE_COVERAGE_MISS")
            for blocker in coverage_blockers
        ),
        "DESCRIPTOR_ACTIONABLE_SAMPLE_COVERAGE_MISS",
    )
    _protected_inputs(root)
    current_source = _source_identity(root)
    _require(
        current_source["source_bundle_sha256"]
        == manifest.get("source_identity", {}).get("source_bundle_sha256"),
        "DESCRIPTOR_SOURCE_BUNDLE_DRIFT",
    )
    offline = manifest.get("offline_sampling_input")
    _require(
        isinstance(offline, dict)
        and _file_sha256(root / OFFLINE_TAIL_PATH) == offline.get("sha256"),
        "DESCRIPTOR_OFFLINE_SAMPLING_INPUT_DRIFT",
    )
    dataset = root / Path(str(manifest["descriptor_dataset"]["path"]))
    _require(
        _file_sha256(dataset) == manifest["descriptor_dataset"]["sha256"],
        "DESCRIPTOR_DATASET_SHA256_DRIFT",
    )
    # Descriptor pools are small enough to use a one-shot frame.  Decompression
    # lives in the independent validator too; here we use the system libzstd.
    rows = _zstd_decompress_jsonl(dataset.read_bytes())
    _require(
        len(rows) == manifest.get("descriptor_pool_count"),
        "DESCRIPTOR_POOL_COUNT_DRIFT",
    )
    _require(
        _canonical_sha256(rows) == manifest.get("descriptor_pool_sha256"),
        "DESCRIPTOR_POOL_CONTENT_DRIFT",
    )
    return rows, manifest


def _zstd_decompress_jsonl(payload: bytes) -> list[dict[str, Any]]:
    try:
        import zstandard
    except ImportError as exc:
        raise CampaignError(
            "ZSTANDARD_DEPENDENCY_REQUIRED: install the project dependency "
            "`zstandard>=0.23` before reading campaign datasets"
        ) from exc
    try:
        decoded = zstandard.ZstdDecompressor().decompress(payload)
    except zstandard.ZstdError as exc:
        raise CampaignError(f"ZSTD_DECOMPRESS_FAILED:{exc}") from exc
    lines = decoded.splitlines()
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(lines, start=1):
        value = json.loads(line)
        _require(isinstance(value, dict), f"JSONL_ROW_NOT_OBJECT:{index}")
        rows.append(value)
    return rows


def run_scan(
    *,
    root: Path,
    binary: Path,
    pool_size: int,
    build_manifest: Path,
    native_max_per_kind: int = 0,
) -> dict[str, Any]:
    """Execute and publish pass 1.  Publication forbids injected executors."""

    repository = _assert_repository_safety(root)
    protected = _protected_inputs(root)
    source = _source_identity(root)
    build_binding = _validate_build_manifest(
        root=root,
        binary=binary,
        manifest_path=build_manifest,
    )
    _require(
        native_max_per_kind == 0,
        "PUBLICATION_REQUIRES_COMPLETE_POPULATION_SCAN",
    )
    native_args, auxiliary, _ = _native_arguments(root)
    skeleton_payload, skeleton_binary_identity = _call_exact_binary(
        root=root,
        binary=binary,
        function_name="g4irsf15_scan_causal_skeletons_from_records",
        arguments=native_args,
    )
    skeletons = _validate_skeleton_scan_payload(
        skeleton_payload,
        protected=protected,
    )
    offline_by_task, offline_sha = _load_offline_rows(root)
    population = annotate_population(
        skeletons,
        bag_records=auxiliary["bag_records"],
        offline_by_task=offline_by_task,
    )
    selected_skeletons, coverage_rows, design = select_descriptor_pool(
        population, pool_size=pool_size
    )
    skeleton_compressed = _zstd_compress(_jsonl_bytes(population))
    _atomic_write(root / SKELETON_DATASET_PATH, skeleton_compressed)
    skeleton_byte_count = _publishable_byte_count(
        root / SKELETON_DATASET_PATH, "skeleton_population"
    )
    materialization_payload, materialization_binary_identity = (
        _call_exact_binary(
            root=root,
            binary=binary,
            function_name=(
                "g4irsf15_materialize_causal_descriptors_from_records"
            ),
            arguments=[*native_args, selected_skeletons],
        )
    )
    pool = _validate_materialization_payload(
        materialization_payload,
        selected_skeletons=selected_skeletons,
        protected=protected,
    )
    _require(
        skeleton_binary_identity["sha256_before"]
        == materialization_binary_identity["sha256_before"]
        == build_binding["binary_sha256"],
        "SCAN_MATERIALIZATION_BINARY_DRIFT",
    )
    compressed = _zstd_compress(_jsonl_bytes(pool))
    _atomic_write(root / DESCRIPTOR_DATASET_PATH, compressed)
    descriptor_byte_count = _publishable_byte_count(
        root / DESCRIPTOR_DATASET_PATH, "descriptor_pool"
    )
    coverage_bytes = _csv_bytes(
        coverage_rows,
        (
            "row_type",
            "coverage_dimension",
            "sampling_stratum_id",
            "N_population",
            "n_descriptor_pool",
            "N_h",
            "n_h",
            "pi_h",
            "analysis_weight",
            "coverage_status",
        ),
    )
    _atomic_write(root / COVERAGE_TABLE_PATH, coverage_bytes)
    coverage_byte_count = _publishable_byte_count(
        root / COVERAGE_TABLE_PATH, "campaign_coverage"
    )
    manifest_value = {
        "schema": DESCRIPTOR_MANIFEST_SCHEMA,
        "status": (
            "READY_FOR_PILOT"
            if not any(
                blocker.endswith("SAMPLE_COVERAGE_MISS")
                for blocker in design["coverage_blockers"]
            )
            else "BLOCKED_SAMPLE_COVERAGE"
        ),
        "formal_pass_claimed": False,
        "scale_count": 0,
        "repository": repository,
        "protected_inputs": protected,
        "source_identity": source,
        "exact_binary_build_manifest": build_binding,
        "binary": {
            "path": skeleton_binary_identity["path"],
            "sha256_before": skeleton_binary_identity["sha256_before"],
            "sha256_after": materialization_binary_identity["sha256_after"],
            "unchanged": (
                skeleton_binary_identity["unchanged"]
                and materialization_binary_identity["unchanged"]
            ),
            "elapsed_wall_seconds": (
                skeleton_binary_identity["elapsed_wall_seconds"]
                + materialization_binary_identity["elapsed_wall_seconds"]
            ),
            "peak_resident_bytes": max(
                skeleton_binary_identity["peak_resident_bytes"],
                materialization_binary_identity["peak_resident_bytes"],
            ),
            "skeleton_scan_call": skeleton_binary_identity,
            "descriptor_materialization_call": (
                materialization_binary_identity
            ),
        },
        "frozen_controls": dict(skeleton_payload["frozen_controls"]),
        "native_scan_summary": {
            key: skeleton_payload[key]
            for key in (
                "schema",
                "evidence_scope",
                "census_complete",
                "terminal_finalized",
                "protected_full_1x_shape",
                "terminal_invariants",
                "terminal_replay_hashes",
                "input_request_count",
                "input_runtime_cohort_sha256",
                "h_system_cohort_mapping_sha256",
                "raw_bag_mapping_sha256",
                "raw_bag_original_entry_mapping_sha256",
                "raw_bag_count",
                "processed_event_count",
                "candidate_mask_event_count",
                "false_positive_mask_event_count",
                "primary_population_count",
                "sample_rule",
                "population_counts",
            )
        },
        "native_materialization_summary": {
            key: materialization_payload[key]
            for key in (
                "schema",
                "evidence_scope",
                "input_request_count",
                "input_runtime_cohort_sha256",
                "h_system_cohort_mapping_sha256",
                "raw_bag_mapping_sha256",
                "raw_bag_original_entry_mapping_sha256",
                "raw_bag_count",
                "selected_skeleton_count",
                "materialized_descriptor_count",
                "source_events_replayed",
            )
        },
        "offline_sampling_input": {
            "path": OFFLINE_TAIL_PATH.as_posix(),
            "sha256": offline_sha,
            "runtime_feature_allowed": False,
        },
        "sampling_design": {
            "name": "TAIL_ENRICHED_STRATIFIED_DETERMINISTIC_MIN_HASH",
            "randomization_surrogate": "SHA256_PSEUDORANDOM_ORDER",
            "population_estimation": (
                "REFERENCE_DESIGN_WEIGHTS_ONLY_NOT_ORIGINAL_POPULATION_ATE"
            ),
            "variance_estimation": (
                "ACTUAL_DETERMINISTIC_CLONE_GROUP_BOOTSTRAP_AT_FORMAL_FINALIZE"
            ),
            "strata": design["strata"],
            "coverage_blockers": design["coverage_blockers"],
        },
        "skeleton_population_count": len(population),
        "selected_skeleton_count": len(selected_skeletons),
        "sealed_descriptor_count": len(pool),
        "selected_skeleton_inventory_sha256": _canonical_sha256(
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
                for row in selected_skeletons
            ]
        ),
        "descriptor_population_count": len(population),
        "descriptor_pool_count": len(pool),
        "descriptor_pool_sha256": _canonical_sha256(pool),
        "skeleton_population_dataset": {
            "path": SKELETON_DATASET_PATH.as_posix(),
            "sha256": _file_sha256(root / SKELETON_DATASET_PATH),
            "byte_count": skeleton_byte_count,
            "encoding": "CANONICAL_JSONL_ZSTD",
            "row_count": len(population),
            "content_sha256": _canonical_sha256(population),
        },
        "descriptor_dataset": {
            "path": DESCRIPTOR_DATASET_PATH.as_posix(),
            "sha256": _file_sha256(root / DESCRIPTOR_DATASET_PATH),
            "byte_count": descriptor_byte_count,
            "encoding": "CANONICAL_JSONL_ZSTD",
        },
        "coverage_table": {
            "path": COVERAGE_TABLE_PATH.as_posix(),
            "sha256": _file_sha256(root / COVERAGE_TABLE_PATH),
            "byte_count": coverage_byte_count,
        },
    }
    manifest = _atomic_json(root / DESCRIPTOR_MANIFEST_PATH, manifest_value)
    checkpoint_value = {
        "schema": CHECKPOINT_MANIFEST_SCHEMA,
        "status": "IMPLEMENTED_AS_NATIVE_OPAQUE_IN_MEMORY_CHECKPOINTS",
        "formal_pass_claimed": False,
        "descriptor_manifest_self_sha256": manifest["self_sha256"],
        "checkpoint_storage": "NOT_SERIALIZED",
        "checkpoint_policy": (
            "FRESH_PROCESS_DETERMINISTIC_PREFIX_REPLAY_THEN_ONE_OPAQUE_"
            "IN_MEMORY_CHECKPOINT_PER_TARGET_EVENT_ORDINAL"
        ),
        "runtime_scope": "OFFLINE_CAMPAIGN_ONLY_NOT_RUNTIME_POLICY",
        "crash_recovery": (
            "ATOMIC_SHARD_RESUME_REPLAYS_PREFIX_IN_A_FRESH_PROCESS"
        ),
        "no_op_fidelity_requirement": (
            "EVERY_PAIR_REQUIRES_IDENTICAL_SOURCE_BASELINE_TREATMENT_"
            "START_STATE_SHA256"
        ),
        "exact_binary_build_manifest": build_binding,
        "binary": {
            "path": skeleton_binary_identity["path"],
            "sha256_before": skeleton_binary_identity["sha256_before"],
            "sha256_after": materialization_binary_identity["sha256_after"],
            "unchanged": True,
        },
        "source_bundle_sha256": source["source_bundle_sha256"],
    }
    _atomic_json(root / CHECKPOINT_MANIFEST_PATH, checkpoint_value)
    return manifest


def _plan_path(campaign: str, *, pilot_round: int = 1) -> Path:
    if campaign == "pilot":
        _require(pilot_round in {1, 2}, "BAD_PILOT_ROUND")
        return (
            PILOT_MANIFEST_PATH
            if pilot_round == 1
            else PILOT_ROUND2_MANIFEST_PATH
        )
    if campaign == "formal":
        return FORMAL_PLAN_PATH
    raise CampaignError(f"UNKNOWN_CAMPAIGN:{campaign}")


def _screening_clause_matches(
    descriptor: Mapping[str, Any],
    clause: Mapping[str, Any],
) -> bool:
    _require(
        set(clause) == {"field", "operator", "value"},
        "SCREENING_REVISION_CLAUSE_FIELDS",
    )
    field = str(clause.get("field", ""))
    operator = str(clause.get("operator", ""))
    _require(
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
        _require(
            isinstance(expected, list) and expected,
            "SCREENING_REVISION_IN_VALUE_NOT_LIST",
        )
        matched = actual in expected
        return matched if operator == "IN" else not matched
    if operator in {"CONTAINS", "NOT_CONTAINS"}:
        _require(
            isinstance(actual, list),
            f"SCREENING_REVISION_CONTAINS_NON_LIST:{field}",
        )
        matched = expected in actual
        return matched if operator == "CONTAINS" else not matched
    if operator in {"LT", "LTE", "GT", "GTE"}:
        _require(
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
    raise CampaignError(f"SCREENING_REVISION_OPERATOR_FORBIDDEN:{operator}")


def _apply_screening_revision_predicate(
    pool: Sequence[Mapping[str, Any]],
    predicate: Mapping[str, Any],
) -> list[dict[str, Any]]:
    clauses = predicate.get("exclude_if_any")
    _require(
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
            _screening_clause_matches(row, clause)
            for clause in clauses
        )
    ]


def _load_screening_revision(
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
    revision = _load_json(path)
    _validate_self_bound(revision, "pilot_screening_revision")
    _require(
        revision.get("schema") == PILOT_SCREENING_REVISION_SCHEMA
        and revision.get("status")
        == "READY_FOR_ONE_REPLACEMENT_ROUND"
        and revision.get("formal_pass_claimed") is False,
        "SCREENING_REVISION_SCHEMA_OR_STATUS",
    )
    _require(
        revision.get("prior_pilot_result") == round1_binding
        and revision.get("r1_false_positive_evidence")
        == round1_result.get("round_false_positive_evidence"),
        "SCREENING_REVISION_R1_EVIDENCE_BINDING_DRIFT",
    )
    frozen = revision.get("frozen_campaign")
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
        "native_scan_summary_sha256": _canonical_sha256(
            descriptor_manifest["native_scan_summary"]
        ),
        "skeleton_population_content_sha256": descriptor_manifest[
            "skeleton_population_dataset"
        ]["content_sha256"],
        "descriptor_pool_sha256": descriptor_manifest[
            "descriptor_pool_sha256"
        ],
    }
    _require(
        frozen == expected_frozen,
        "SCREENING_REVISION_FROZEN_CAMPAIGN_DRIFT",
    )
    _require(
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
    _require(
        isinstance(predicate, dict),
        "SCREENING_REVISION_PREDICATE_MISSING",
    )
    revised_pool = _apply_screening_revision_predicate(pool, predicate)
    rationales = revision.get("clause_rationales")
    observed_reason_codes = set(
        round1_result["round_false_positive_evidence"][
            "reason_counts"
        ]
    )
    _require(
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
    _require(
        revision.get("revised_eligible_descriptor_ids") == revised_ids
        and revision.get("revised_eligible_descriptor_ids_sha256")
        == _canonical_sha256(revised_ids)
        and revision.get("outcome_free_predicate_sha256")
        == _canonical_sha256(predicate)
        and len(revised_pool) < len(pool),
        "SCREENING_REVISION_ELIGIBLE_INVENTORY_DRIFT",
    )
    failed_r1_ids = set(
        round1_result["round_false_positive_evidence"][
            "noneligible_descriptor_ids"
        ]
    )
    _require(
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
    available_replacement = Counter(
        str(row["kind"])
        for row in revised_pool
        if str(row["descriptor_id"]) not in round1_descriptor_ids
    )
    _require(
        all(
            available_replacement[kind] >= PILOT_ATTEMPTS_PER_KIND
            for kind in failed_kinds
        ),
        "SCREENING_REVISION_INSUFFICIENT_REPLACEMENT_CAPACITY",
    )
    binding = {
        "path": PILOT_SCREENING_REVISION_PATH.as_posix(),
        "sha256": _file_sha256(path),
        "byte_count": _publishable_byte_count(
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


def create_plan(
    *,
    root: Path,
    campaign: str,
    shard_size: int,
    pilot_round: int = 1,
    h_system_attempts: int = 0,
    h_system_targets_per_shard: int = DEFAULT_H_SYSTEM_TARGETS_PER_SHARD,
) -> dict[str, Any]:
    pool, descriptor_manifest = _read_descriptor_pool(root)
    formal_preregistration: dict[str, Any] | None = None
    pilot_result_binding: dict[str, Any] | None = None
    pilot_result_bindings: list[dict[str, Any]] = []
    prior_pilot_result_binding: dict[str, Any] | None = None
    excluded_before_panel: set[str] = set()
    sampling_excluded_before_panel: set[str] = set()
    active_kinds = list(KINDS)
    screening_revision_binding: dict[str, Any] | None = None
    attempt_frame_pool = pool

    def load_pilot_result(round_index: int) -> tuple[dict[str, Any], dict[str, Any]]:
        relative = (
            Path("artifacts/datasets/g4irsf15_pilot_causal_result.json")
            if round_index == 1
            else Path(
                "artifacts/datasets/g4irsf15_pilot_causal_result_round2.json"
            )
        )
        result_path = root / relative
        result = _load_json(result_path)
        _validate_self_bound(result, f"pilot_r{round_index}_result")
        _require(
            result.get("schema") == "czr005.g4irsf15.pilot_result.v1"
            and result.get("pilot_round") == round_index,
            f"PILOT_R{round_index}_RESULT_SCHEMA",
        )
        return result, {
            "path": relative.as_posix(),
            "sha256": _file_sha256(result_path),
            "self_sha256": result["self_sha256"],
            "status": result["status"],
            "pilot_round": round_index,
        }

    def plan_descriptor_ids(round_index: int) -> set[str]:
        plan = _load_json(
            root / _plan_path("pilot", pilot_round=round_index)
        )
        _validate_plan(plan, "pilot")
        _require(
            plan.get("pilot_round") == round_index,
            f"PILOT_R{round_index}_PLAN_ROUND_DRIFT",
        )
        return {
            str(target["descriptor_id"])
            for shard in plan["shards"]
            for target in shard["targets"]
        }

    if campaign == "pilot":
        targets = select_pilot_targets(pool, round_index=pilot_round)
        if pilot_round == 2:
            round1_result, prior_pilot_result_binding = load_pilot_result(1)
            _require(
                round1_result.get("status") == "RESAMPLE_REQUIRED",
                "PILOT_R2_REQUIRES_R1_RESAMPLE_REQUIRED",
            )
            round1_complete = round1_result.get("complete_by_kind")
            _require(
                isinstance(round1_complete, dict),
                "PILOT_R1_COMPLETE_BY_KIND_MISSING",
            )
            failed_kinds = {
                kind
                for kind in KINDS
                if _strict_int(
                    round1_complete.get(kind, 0),
                    f"pilot_r1.complete_by_kind.{kind}",
                    minimum=0,
                )
                < PILOT_MIN_COMPLETE_PER_KIND
            }
            _require(failed_kinds, "PILOT_R2_HAS_NO_FAILED_KIND")
            excluded_before_panel = plan_descriptor_ids(1)
            attempt_frame_pool, screening_revision_binding = (
                _load_screening_revision(
                    root=root,
                    pool=pool,
                    descriptor_manifest=descriptor_manifest,
                    round1_result=round1_result,
                    round1_binding=prior_pilot_result_binding,
                    round1_descriptor_ids=excluded_before_panel,
                    failed_kinds=failed_kinds,
                )
            )
            targets = [
                row
                for row in select_pilot_targets(
                    attempt_frame_pool,
                    round_index=2,
                    excluded_descriptor_ids=excluded_before_panel,
                )
                if row["kind"] in failed_kinds
            ]
            _require(
                not (
                    {str(row["descriptor_id"]) for row in targets}
                    & excluded_before_panel
                ),
                "PILOT_R1_R2_DESCRIPTOR_OVERLAP",
            )
            active_kinds = sorted(failed_kinds)
    elif campaign == "formal":
        round1_result, round1_binding = load_pilot_result(1)
        pilot_result_bindings.append(round1_binding)
        excluded_before_panel.update(plan_descriptor_ids(1))
        if round1_result.get("status") == "PASS_PILOT":
            pilot_result = round1_result
            pilot_result_binding = round1_binding
        else:
            _require(
                round1_result.get("status") == "RESAMPLE_REQUIRED",
                "FORMAL_PLAN_REQUIRES_PASS_OR_RESAMPLE_R1",
            )
            round2_result, round2_binding = load_pilot_result(2)
            _require(
                round2_result.get("status")
                in {"PASS_PILOT", "PASS_PILOT_WITH_BLOCKED_KINDS"},
                "FORMAL_PLAN_REQUIRES_USABLE_R2",
            )
            prior = round2_result.get("prior_pilot_result")
            _require(
                isinstance(prior, dict)
                and prior.get("self_sha256") == round1_result["self_sha256"]
                and prior.get("sha256") == round1_binding["sha256"],
                "PILOT_R2_NOT_BOUND_TO_R1",
            )
            round1_complete = round1_result.get("complete_by_kind")
            _require(
                isinstance(round1_complete, dict),
                "PILOT_R1_COMPLETE_BY_KIND_MISSING",
            )
            failed_r1_kinds = {
                kind
                for kind in KINDS
                if _strict_int(
                    round1_complete.get(kind, 0),
                    f"pilot_r1.complete_by_kind.{kind}",
                    minimum=0,
                )
                < PILOT_MIN_COMPLETE_PER_KIND
            }
            attempt_frame_pool, screening_revision_binding = (
                _load_screening_revision(
                    root=root,
                    pool=pool,
                    descriptor_manifest=descriptor_manifest,
                    round1_result=round1_result,
                    round1_binding=round1_binding,
                    round1_descriptor_ids=plan_descriptor_ids(1),
                    failed_kinds=failed_r1_kinds,
                )
            )
            _require(
                round2_result.get("screening_revision")
                == screening_revision_binding,
                "PILOT_R2_RESULT_SCREENING_REVISION_BINDING_DRIFT",
            )
            excluded_before_panel.update(plan_descriptor_ids(2))
            pilot_result_bindings.append(round2_binding)
            pilot_result = round2_result
            pilot_result_binding = round2_binding
        pilot_complete = pilot_result.get("complete_by_kind")
        _require(
            isinstance(pilot_complete, dict),
            "PILOT_COMPLETE_BY_KIND_MISSING",
        )
        active_kinds = [
            kind
            for kind in KINDS
            if _strict_int(
                pilot_complete.get(kind, 0),
                f"pilot_result.complete_by_kind.{kind}",
                minimum=0,
            )
            >= PILOT_MIN_COMPLETE_PER_KIND
        ]
        _require(
            len(active_kinds) >= 2,
            "FORMAL_REQUIRES_TWO_PILOT_SUPPORTED_KINDS",
        )
        targets, formal_preregistration = preregister_formal_targets(
            attempt_frame_pool,
            pilot_complete_by_kind={
                kind: _strict_int(
                    pilot_complete.get(kind),
                    f"pilot_result.complete_by_kind.{kind}",
                    minimum=PILOT_MIN_COMPLETE_PER_KIND,
                )
                for kind in active_kinds
            },
            h_system_attempts=h_system_attempts,
            active_kinds=active_kinds,
            excluded_pilot_descriptor_ids=excluded_before_panel,
            pilot_rounds_excluded=[
                int(binding["pilot_round"])
                for binding in pilot_result_bindings
            ],
        )
    else:
        raise CampaignError(f"UNKNOWN_CAMPAIGN:{campaign}")
    provenance_targets: list[dict[str, Any]] = []
    for source_target in targets:
        target = dict(source_target)
        target["intervention_id"] = target["target_key"]
        target["target_decision_id"] = (
            f"{target['boundary_sha256']}:{target['event_seq']}"
        )
        target["source_screening_manifest_sha256"] = (
            descriptor_manifest["self_sha256"]
        )
        target["source_bundle_sha256"] = descriptor_manifest[
            "source_identity"
        ]["source_bundle_sha256"]
        target["binary_sha256"] = descriptor_manifest["binary"][
            "sha256_before"
        ]
        target["map_raw_sha256"] = MAP_RAW_SHA256
        target["task_raw_sha256"] = TASK_RAW_SHA256
        target["h_system_cohort_mapping_sha256"] = (
            descriptor_manifest["protected_inputs"]["task"][
                "runtime_segment_mapping_sha256"
            ]
        )
        target["raw_bag_mapping_sha256"] = descriptor_manifest[
            "protected_inputs"
        ]["task"]["raw_bag_mapping_sha256"]
        target["raw_bag_original_entry_mapping_sha256"] = (
            descriptor_manifest["protected_inputs"]["task"][
                "raw_bag_original_entry_mapping_sha256"
            ]
        )
        provenance_targets.append(target)
    sampling_excluded_before_panel.update(excluded_before_panel)
    if screening_revision_binding is not None:
        revised_ids = {
            str(row["descriptor_id"]) for row in attempt_frame_pool
        }
        sampling_excluded_before_panel.update(
            str(row["descriptor_id"])
            for row in pool
            if str(row["descriptor_id"]) not in revised_ids
        )
    targets, attempt_sampling_design = attach_attempt_sampling(
        provenance_targets,
        pool=pool,
        excluded_descriptor_ids=sampling_excluded_before_panel,
        panel=(
            f"PILOT_ROUND_{pilot_round}"
            if campaign == "pilot"
            else "FORMAL_PREREGISTERED_ATTEMPTS"
        ),
    )
    shards = build_contiguous_shards(
        targets,
        shard_size=shard_size,
        h_system_targets_per_shard=h_system_targets_per_shard,
    )
    per_kind = Counter(str(row["kind"]) for row in targets)
    per_horizon = Counter(str(row["horizon"]) for row in targets)
    value = {
        "schema": CAMPAIGN_PLAN_SCHEMA,
        "campaign": campaign,
        "status": (
            "PREREGISTERED_WITH_DESCRIPTOR_CAP_BLOCKER_NOT_RUN"
            if formal_preregistration
            and formal_preregistration["descriptor_cap_blocked"]
            else "PREREGISTERED_NOT_RUN"
        ),
        "formal_pass_claimed": False,
        "scale_count": 0,
        "descriptor_manifest": {
            "path": DESCRIPTOR_MANIFEST_PATH.as_posix(),
            "self_sha256": descriptor_manifest["self_sha256"],
            "file_sha256": _file_sha256(root / DESCRIPTOR_MANIFEST_PATH),
        },
        "exact_binary_build_manifest": descriptor_manifest[
            "exact_binary_build_manifest"
        ],
        "binary": descriptor_manifest["binary"],
        "source_bundle_sha256": descriptor_manifest["source_identity"][
            "source_bundle_sha256"
        ],
        "protected_inputs": descriptor_manifest["protected_inputs"],
        "pilot_round": pilot_round if campaign == "pilot" else None,
        "pilot_result": pilot_result_binding,
        "pilot_results": pilot_result_bindings,
        "prior_pilot_result": prior_pilot_result_binding,
        "screening_revision": screening_revision_binding,
        "active_kinds": active_kinds,
        "blocked_kinds": [
            kind for kind in KINDS if kind not in active_kinds
        ],
        "formal_attempt_preregistration": formal_preregistration,
        "attempt_budget": len(targets),
        "attempts_by_kind": dict(sorted(per_kind.items())),
        "attempts_by_horizon": dict(sorted(per_horizon.items())),
        "attempt_sampling_design": attempt_sampling_design,
        "panel_execution_policy": {
            "publication_requires_complete_preregistered_panel": True,
            "outcome_dependent_early_stop_allowed": False,
            "required_shard_indices": list(range(len(shards))),
            "required_target_count": len(targets),
        },
        "pilot_gate": (
            {
                "attempts_per_kind": PILOT_ATTEMPTS_PER_KIND,
                "attempted_kinds": active_kinds,
                "minimum_complete_action_changing_h_bag_per_kind": (
                    PILOT_MIN_COMPLETE_PER_KIND
                ),
                "resample_once_if_blocked": True,
            }
            if campaign == "pilot"
            else None
        ),
        "formal_gate": (
            {
                "active_kinds": active_kinds,
                "blocked_kinds": [
                    kind for kind in KINDS if kind not in active_kinds
                ],
                "causal_label_count_min": FORMAL_MIN_LABELS,
                "h_bag_or_stronger_complete_min": FORMAL_MIN_LABELS,
                "h_system_complete_min": FORMAL_MIN_H_SYSTEM,
                "per_kind_label_min": FORMAL_MIN_LABELS_PER_KIND,
                "initial_label_targets": dict(
                    formal_preregistration["formal_label_targets"]
                ),
                "original_label_targets": dict(FORMAL_LABEL_TARGETS),
                "reallocation_allowed": len(active_kinds) < len(KINDS),
                "minimum_active_kind_count": 2,
                "hard_gate_fail_max": 0,
                "action_changed_rate": 1.0,
                "clone_fidelity": 1.0,
                "future_leakage": 0,
                "split_contamination": 0,
            }
            if campaign == "formal"
            else None
        ),
        "worker_contract": {
            "process_model": "INDEPENDENT_FRESH_PROCESS_PER_SHARD",
            "target_order": "CONTIGUOUS_EVENT_ORDINAL",
            "output_publication": "FSYNC_TEMP_THEN_ATOMIC_REPLACE",
            "resume": "VALID_EXISTING_SHARD_IS_IDEMPOTENT",
            "duplicate_target_allowed": False,
            "binary_hash_checked_before_after": True,
        },
        "shard_size_target": shard_size,
        "h_system_targets_per_shard": h_system_targets_per_shard,
        "shard_count": len(shards),
        "shards": shards,
    }
    return _atomic_json(
        root / _plan_path(campaign, pilot_round=pilot_round), value
    )


def _campaign_namespace(campaign: str, pilot_round: int) -> str:
    return f"pilot_r{pilot_round}" if campaign == "pilot" else campaign


def _shard_output_path(
    campaign: str, shard_index: int, *, pilot_round: int = 1
) -> Path:
    namespace = _campaign_namespace(campaign, pilot_round)
    return (
        RUN_STATE_SHARD_ROOT
        / namespace
        / f"g4irsf15_{namespace}_shard_{shard_index:04d}.json.zst"
    )


def _heartbeat_path(
    campaign: str, shard_index: int, *, pilot_round: int = 1
) -> Path:
    namespace = _campaign_namespace(campaign, pilot_round)
    return (
        RUN_STATE_SHARD_ROOT
        / namespace
        / f"g4irsf15_{namespace}_shard_{shard_index:04d}.heartbeat.json"
    )


def _compact_evidence_path(
    campaign: str, evidence_index: int, *, pilot_round: int = 1
) -> Path:
    namespace = _campaign_namespace(campaign, pilot_round)
    return (
        COMPACT_EVIDENCE_ROOT
        / namespace
        / (
            f"g4irsf15_{namespace}_compact_evidence_"
            f"{evidence_index:04d}.json.zst"
        )
    )


def _orchestrator_publication_path(path: Path, root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _orchestrator_file_binding(
    path: Path, root: Path
) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    return {
        "path": _orchestrator_publication_path(resolved, root),
        "file_sha256": _file_sha256(resolved),
        "byte_count": resolved.stat().st_size,
    }


def _repository_publication_file(
    root: Path, path: Path, label: str
) -> tuple[Path, str]:
    candidate = (
        path if path.is_absolute() else root / path
    ).resolve()
    try:
        relative = candidate.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise CampaignError(
            f"{label}_MUST_BE_INSIDE_REPOSITORY"
        ) from exc
    _require(
        relative
        and Path(relative).as_posix() == relative
        and not Path(relative).is_absolute(),
        f"{label}_PATH_NOT_CANONICAL",
    )
    try:
        Path(relative).relative_to(ORCHESTRATOR_PROFILE_ROOT)
    except ValueError as exc:
        raise CampaignError(
            f"{label}_OUTSIDE_PUBLICATION_PROFILE_ROOT"
        ) from exc
    _require(candidate.is_file(), f"{label}_FILE_MISSING")
    return candidate, relative


def _orchestrator_timestamp(value: Any, label: str) -> datetime:
    _require(isinstance(value, str), f"{label}_NOT_STRING")
    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise CampaignError(f"{label}_INVALID") from exc
    _require(
        parsed.tzinfo is not None,
        f"{label}_MISSING_TIMEZONE",
    )
    return parsed


def _orchestrator_index_list(
    value: Any, label: str, *, nonempty: bool = False
) -> list[int]:
    _require(isinstance(value, list), f"{label}_NOT_LIST")
    indices = [
        _strict_int(item, f"{label}.item", minimum=0)
        for item in value
    ]
    _require(
        indices == sorted(set(indices)),
        f"{label}_NOT_STRICT_SORTED_UNIQUE",
    )
    if nonempty:
        _require(bool(indices), f"{label}_EMPTY")
    return indices


def _validate_orchestrator_stream_binding(
    value: Any, label: str
) -> None:
    _require(isinstance(value, dict), f"{label}_NOT_OBJECT")
    _require(
        _is_sha256(value.get("sha256"))
        and _strict_int(
            value.get("byte_count"),
            f"{label}.byte_count",
            minimum=0,
        )
        >= 0,
        f"{label}_INVALID",
    )


def _validate_orchestrator_profile(
    *,
    root: Path,
    profile_path: Path,
    campaign: str,
    pilot_round: int,
    plan: Mapping[str, Any],
    plan_path: Path,
    binary: Path,
    build_manifest: Path,
    build_binding: Mapping[str, Any],
) -> tuple[dict[str, Any], list[int]]:
    resolved_profile, relative_profile = _repository_publication_file(
        root, profile_path, "ORCHESTRATOR_PROFILE"
    )
    profile = _load_json(resolved_profile)
    _validate_self_bound(profile, "orchestrator_profile")
    _require(
        profile.get("schema") == ORCHESTRATOR_PROFILE_SCHEMA
        and profile.get("status") == "COMPLETE"
        and profile.get("formal_pass_claimed") is False
        and profile.get("campaign") == campaign
        and profile.get("pilot_round") == pilot_round
        and profile.get("execution_mode")
        == "PRODUCTION_NATIVE_PROCESS_TREE_RSS",
        "ORCHESTRATOR_PROFILE_SCHEMA_STATUS_SCOPE",
    )
    available_indices = list(range(len(plan["shards"])))
    shard_inventory = [
        {
            "shard_index": index,
            "shard_sha256": plan["shards"][index][
                "shard_sha256"
            ],
        }
        for index in available_indices
    ]
    expected_plan_binding = {
        **_orchestrator_file_binding(plan_path, root),
        "self_sha256": plan["self_sha256"],
        "shard_count": len(available_indices),
        "available_shard_indices": available_indices,
        "shard_inventory": shard_inventory,
        "shard_inventory_sha256": _canonical_sha256(
            shard_inventory
        ),
    }
    expected_input_bindings = {
        "plan": _orchestrator_file_binding(plan_path, root),
        "binary": _orchestrator_file_binding(binary, root),
        "build_manifest": _orchestrator_file_binding(
            build_manifest, root
        ),
        "worker_script": _orchestrator_file_binding(
            root / GENERATOR_PATH, root
        ),
        "orchestrator_script": _orchestrator_file_binding(
            root / ORCHESTRATOR_PATH, root
        ),
    }
    _require(
        profile.get("plan") == expected_plan_binding
        and profile.get("input_artifact_bindings")
        == expected_input_bindings
        and profile.get("ending_input_artifact_bindings")
        == expected_input_bindings
        and profile.get("input_artifact_drift") == []
        and profile.get("binary_sha256")
        == build_binding.get("binary_sha256")
        == expected_input_bindings["binary"]["file_sha256"]
        and profile.get("build_manifest_sha256")
        == expected_input_bindings["build_manifest"]["file_sha256"],
        "ORCHESTRATOR_PROFILE_INPUT_BINDING_DRIFT",
    )
    requested = _orchestrator_index_list(
        profile.get("requested_shard_indices"),
        "orchestrator.requested_shard_indices",
        nonempty=True,
    )
    _require(
        set(requested).issubset(available_indices)
        and _orchestrator_index_list(
            profile.get("launch_attempted_shard_indices"),
            "orchestrator.launch_attempted_shard_indices",
        )
        == requested
        and _orchestrator_index_list(
            profile.get("scheduled_shard_indices"),
            "orchestrator.scheduled_shard_indices",
        )
        == requested
        and _orchestrator_index_list(
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
    workers_requested = _strict_int(
        profile.get("worker_count_requested"),
        "orchestrator.worker_count_requested",
        minimum=1,
    )
    workers_effective = _strict_int(
        profile.get("worker_count_effective"),
        "orchestrator.worker_count_effective",
        minimum=1,
    )
    _require(
        workers_effective == min(workers_requested, len(requested)),
        "ORCHESTRATOR_WORKER_COUNT_DRIFT",
    )
    cap = profile.get("process_rss_cap")
    _require(isinstance(cap, dict), "ORCHESTRATOR_RSS_CAP_MISSING")
    cap_mib = _strict_float(
        cap.get("max_process_rss_mib"),
        "orchestrator.max_process_rss_mib",
    )
    cap_bytes = _strict_int(
        cap.get("max_process_rss_bytes"),
        "orchestrator.max_process_rss_bytes",
        minimum=1,
    )
    _require(
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
    publication_contract = profile.get(
        "publication_execution_contract"
    )
    _require(
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
        and isinstance(publication_contract, dict)
        and publication_contract.get(
            "max_allowed_process_rss_mib"
        )
        == MAX_PUBLICATION_PROCESS_RSS_MIB
        and publication_contract.get(
            "max_allowed_heartbeat_interval_seconds"
        )
        == MAX_ORCHESTRATOR_HEARTBEAT_INTERVAL_SECONDS,
        "ORCHESTRATOR_MEMORY_SAMPLER_CONTRACT_DRIFT",
    )
    rows = profile.get("shards")
    _require(
        isinstance(rows, list)
        and [
            row.get("shard_index")
            for row in rows
            if isinstance(row, dict)
        ]
        == requested,
        "ORCHESTRATOR_RESULT_SHARD_INVENTORY_DRIFT",
    )
    profile_started = _orchestrator_timestamp(
        profile.get("started_utc"),
        "orchestrator.started_utc",
    )
    profile_finished = _orchestrator_timestamp(
        profile.get("finished_utc"),
        "orchestrator.finished_utc",
    )
    _require(
        profile_started <= profile_finished,
        "ORCHESTRATOR_PROFILE_TIME_WINDOW_DRIFT",
    )
    python_executable = profile.get("python_executable")
    _require(
        isinstance(python_executable, str)
        and python_executable,
        "ORCHESTRATOR_PYTHON_EXECUTABLE_MISSING",
    )
    expected_worker = (root / GENERATOR_PATH).resolve()
    _require(
        Path(str(profile.get("worker_script"))).resolve()
        == expected_worker,
        "ORCHESTRATOR_WORKER_SCRIPT_PATH_DRIFT",
    )
    for row, shard_index in zip(rows, requested, strict=True):
        row_started = _orchestrator_timestamp(
            row.get("started_utc"),
            f"orchestrator.shard_{shard_index}.started_utc",
        )
        row_finished = _orchestrator_timestamp(
            row.get("finished_utc"),
            f"orchestrator.shard_{shard_index}.finished_utc",
        )
        row_elapsed = _strict_float(
            row.get("elapsed_wall_seconds"),
            f"orchestrator.shard_{shard_index}.elapsed_wall_seconds",
        )
        _require(
            row.get("return_code") == 0
            and row.get("launch_error") is None
            and row.get("orchestration_failure_reason") is None
            and _strict_int(
                row.get("pid"),
                f"orchestrator.shard_{shard_index}.pid",
                minimum=1,
            )
            > 0
            and row.get("memory_sampling_supported") is True
            and row.get("rss_sample_method")
            in PRODUCTION_RSS_METHODS
            and _strict_int(
                row.get("rss_sample_count"),
                f"orchestrator.shard_{shard_index}.rss_sample_count",
                minimum=1,
            )
            >= _strict_int(
                row.get("rss_successful_sample_count"),
                (
                    f"orchestrator.shard_{shard_index}."
                    "rss_successful_sample_count"
                ),
                minimum=1,
            )
            and row.get("termination_requested") is False
            and row.get("forced_kill") is False,
            f"ORCHESTRATOR_SHARD_RESULT_FAILURE:{shard_index}",
        )
        _require(
            profile_started
            <= row_started
            <= row_finished
            <= profile_finished
            and row_elapsed >= 0.0,
            f"ORCHESTRATOR_SHARD_TIME_WINDOW_DRIFT:{shard_index}",
        )
        peak = _strict_int(
            row.get("peak_resident_bytes"),
            f"orchestrator.shard_{shard_index}.peak_resident_bytes",
            minimum=1,
        )
        _require(
            peak <= cap_bytes,
            f"ORCHESTRATOR_SHARD_RSS_CAP_EXCEEDED:{shard_index}",
        )
        expected_argv = [
            python_executable,
            str(expected_worker),
            "--root",
            str(root.resolve()),
            "run-shard",
            "--campaign",
            campaign,
            "--shard-index",
            str(shard_index),
            "--binary",
            str(binary.resolve()),
            "--build-manifest",
            str(build_manifest.resolve()),
            "--round",
            str(pilot_round),
        ]
        _require(
            row.get("argv") == expected_argv,
            f"ORCHESTRATOR_SHARD_ARGV_DRIFT:{shard_index}",
        )
        _validate_orchestrator_stream_binding(
            row.get("stdout"),
            f"orchestrator.shard_{shard_index}.stdout",
        )
        _validate_orchestrator_stream_binding(
            row.get("stderr"),
            f"orchestrator.shard_{shard_index}.stderr",
        )
    process_group_peak = _strict_int(
        profile.get("process_group_peak_resident_bytes"),
        "orchestrator.process_group_peak_resident_bytes",
        minimum=1,
    )
    _require(
        process_group_peak <= cap_bytes * workers_effective
        and profile.get("process_group_rss_scope")
        == (
            "SUM_OF_CONCURRENT_SHARD_WORKER_PROCESS_TREE_RSS_SAMPLES"
        ),
        "ORCHESTRATOR_PROCESS_GROUP_RSS_DRIFT",
    )
    poll_interval = _strict_float(
        profile.get("rss_sampling_interval_seconds"),
        "orchestrator.rss_sampling_interval_seconds",
    )
    liveness = profile.get("liveness")
    _require(isinstance(liveness, dict), "ORCHESTRATOR_LIVENESS_MISSING")
    heartbeat_interval = _strict_float(
        liveness.get("heartbeat_interval_seconds"),
        "orchestrator.heartbeat_interval_seconds",
    )
    _require(
        0.0 < poll_interval <= 1.0
        and 0.0
        < heartbeat_interval
        <= MAX_ORCHESTRATOR_HEARTBEAT_INTERVAL_SECONDS
        and liveness.get("poll_interval_seconds") == poll_interval
        and liveness.get("rss_sampling_interval_seconds")
        == poll_interval,
        "ORCHESTRATOR_INTERVAL_CONTRACT_DRIFT",
    )
    heartbeat_count = _strict_int(
        liveness.get("heartbeat_count"),
        "orchestrator.heartbeat_count",
        minimum=2,
    )
    timestamps_raw = liveness.get("heartbeat_timestamps_utc")
    _require(
        isinstance(timestamps_raw, list)
        and len(timestamps_raw) == heartbeat_count,
        "ORCHESTRATOR_HEARTBEAT_TIMESTAMP_COUNT_DRIFT",
    )
    timestamps = [
        _orchestrator_timestamp(
            value, f"orchestrator.heartbeat_timestamp_{index}"
        )
        for index, value in enumerate(timestamps_raw)
    ]
    _require(
        all(
            left < right
            for left, right in zip(
                timestamps, timestamps[1:], strict=False
            )
        ),
        "ORCHESTRATOR_HEARTBEAT_TIMESTAMPS_NOT_STRICT",
    )
    _require(
        profile_started
        <= timestamps[0]
        <= timestamps[-1]
        <= profile_finished,
        "ORCHESTRATOR_HEARTBEAT_TIME_WINDOW_DRIFT",
    )
    elapsed = _strict_float(
        profile.get("elapsed_wall_seconds"),
        "orchestrator.elapsed_wall_seconds",
    )
    _require(elapsed >= 0.0, "ORCHESTRATOR_NEGATIVE_ELAPSED")
    if elapsed > 2.0 * heartbeat_interval:
        _require(
            heartbeat_count >= 3,
            "ORCHESTRATOR_PERIODIC_HEARTBEAT_MISSING",
        )
    max_gap = heartbeat_interval + max(1.0, 4.0 * poll_interval)
    _require(
        all(
            (right - left).total_seconds() <= max_gap
            for left, right in zip(
                timestamps, timestamps[1:], strict=False
            )
        ),
        "ORCHESTRATOR_HEARTBEAT_GAP_EXCEEDED",
    )
    heartbeat_relative = liveness.get("heartbeat_path")
    _require(
        isinstance(heartbeat_relative, str),
        "ORCHESTRATOR_HEARTBEAT_PATH_MISSING",
    )
    heartbeat_path, canonical_heartbeat_relative = (
        _repository_publication_file(
            root,
            Path(heartbeat_relative),
            "ORCHESTRATOR_HEARTBEAT",
        )
    )
    _require(
        heartbeat_relative == canonical_heartbeat_relative
        and heartbeat_path != resolved_profile,
        "ORCHESTRATOR_HEARTBEAT_PATH_DRIFT",
    )
    heartbeat = _load_json(heartbeat_path)
    _validate_self_bound(heartbeat, "orchestrator_heartbeat")
    _require(
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
        == expected_input_bindings
        and heartbeat.get("ending_input_artifact_bindings")
        == expected_input_bindings
        and heartbeat.get("input_artifact_drift") == []
        and heartbeat.get("available_shard_indices")
        == available_indices
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
        == heartbeat_interval,
        "ORCHESTRATOR_FINAL_HEARTBEAT_CONTENT_DRIFT",
    )
    _require(
        liveness.get("heartbeat_file_sha256")
        == _file_sha256(heartbeat_path)
        and liveness.get("heartbeat_self_sha256")
        == heartbeat["self_sha256"]
        and liveness.get("final_heartbeat_status") == "COMPLETE"
        and liveness.get("final_heartbeat_sequence")
        == heartbeat_count
        == heartbeat.get("heartbeat_sequence")
        and heartbeat.get("heartbeat_utc") == timestamps_raw[-1],
        "ORCHESTRATOR_FINAL_HEARTBEAT_BINDING_DRIFT",
    )
    attestation = profile.get("publication_execution_attestation")
    _require(
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
    binding = {
        "path": relative_profile,
        "sha256": _file_sha256(resolved_profile),
        "byte_count": resolved_profile.stat().st_size,
        "self_sha256": profile["self_sha256"],
        "requested_shard_indices": requested,
        "heartbeat": {
            "path": canonical_heartbeat_relative,
            "sha256": _file_sha256(heartbeat_path),
            "byte_count": heartbeat_path.stat().st_size,
            "self_sha256": heartbeat["self_sha256"],
        },
    }
    return binding, requested


def _validate_orchestrator_profile_set(
    *,
    root: Path,
    profile_paths: Sequence[Path],
    campaign: str,
    pilot_round: int,
    plan: Mapping[str, Any],
    plan_path: Path,
    binary: Path,
    build_manifest: Path,
    build_binding: Mapping[str, Any],
) -> dict[str, Any]:
    _require(
        isinstance(profile_paths, Sequence)
        and not isinstance(profile_paths, (str, bytes))
        and bool(profile_paths),
        "AT_LEAST_ONE_ORCHESTRATOR_PROFILE_REQUIRED",
    )
    bindings: list[dict[str, Any]] = []
    covered: set[int] = set()
    seen_paths: set[str] = set()
    for profile_path in profile_paths:
        _require(
            isinstance(profile_path, Path),
            "ORCHESTRATOR_PROFILE_PATH_NOT_PATH",
        )
        binding, requested = _validate_orchestrator_profile(
            root=root,
            profile_path=profile_path,
            campaign=campaign,
            pilot_round=pilot_round,
            plan=plan,
            plan_path=plan_path,
            binary=binary,
            build_manifest=build_manifest,
            build_binding=build_binding,
        )
        _require(
            binding["path"] not in seen_paths,
            "DUPLICATE_ORCHESTRATOR_PROFILE_PATH",
        )
        seen_paths.add(binding["path"])
        overlap = covered.intersection(requested)
        _require(
            not overlap,
            f"ORCHESTRATOR_PROFILE_SHARD_OVERLAP:{sorted(overlap)}",
        )
        covered.update(requested)
        bindings.append(binding)
    required = list(range(len(plan["shards"])))
    _require(
        sorted(covered) == required,
        "ORCHESTRATOR_PROFILE_SET_DOES_NOT_EXACTLY_COVER_PLAN",
    )
    bindings.sort(
        key=lambda row: (
            tuple(row["requested_shard_indices"]),
            row["path"],
        )
    )
    return _self_bound(
        {
            "schema": ORCHESTRATOR_PROFILE_SET_SCHEMA,
            "canonical_order": (
                "LEXICOGRAPHIC_REQUESTED_SHARD_INDICES_THEN_PATH"
            ),
            "profile_count": len(bindings),
            "covered_shard_indices": required,
            "profiles": bindings,
        }
    )


def _revalidate_orchestrator_profile_files(
    root: Path, profile_set: Mapping[str, Any]
) -> None:
    for binding in profile_set["profiles"]:
        profile_path = root / Path(binding["path"])
        heartbeat = binding["heartbeat"]
        heartbeat_path = root / Path(heartbeat["path"])
        _require(
            profile_path.stat().st_size == binding["byte_count"]
            and _file_sha256(profile_path) == binding["sha256"]
            and heartbeat_path.stat().st_size
            == heartbeat["byte_count"]
            and _file_sha256(heartbeat_path) == heartbeat["sha256"],
            "ORCHESTRATOR_PROFILE_CHANGED_DURING_FINALIZE",
        )


def _validate_plan(plan: Mapping[str, Any], campaign: str) -> None:
    _validate_self_bound(plan, f"{campaign}_plan")
    _require(plan.get("schema") == CAMPAIGN_PLAN_SCHEMA, "PLAN_SCHEMA")
    _require(plan.get("campaign") == campaign, "PLAN_CAMPAIGN_DRIFT")
    if campaign == "pilot":
        _require(
            plan.get("pilot_round") in {1, 2},
            "PLAN_PILOT_ROUND_MISSING",
        )
    _require(
        isinstance(plan.get("exact_binary_build_manifest"), dict),
        "PLAN_BUILD_MANIFEST_BINDING_MISSING",
    )
    shards = plan.get("shards")
    _require(isinstance(shards, list) and shards, "PLAN_SHARDS_MISSING")
    seen: set[str] = set()
    previous_end = -1
    for index, shard in enumerate(shards):
        _require(isinstance(shard, dict), "PLAN_SHARD_NOT_OBJECT")
        _require(shard.get("shard_index") == index, "SHARD_INDEX_DRIFT")
        projection = dict(shard)
        declared = projection.pop("shard_sha256", None)
        _require(
            declared == _canonical_sha256(projection),
            f"SHARD_SHA256_DRIFT:{index}",
        )
        start = _strict_int(
            shard.get("event_ordinal_start"), "shard_start", minimum=0
        )
        end = _strict_int(
            shard.get("event_ordinal_end"), "shard_end", minimum=start
        )
        _require(start > previous_end, "PLAN_SHARD_ORDINAL_OVERLAP")
        previous_end = end
        targets = shard.get("targets")
        keys = shard.get("target_keys")
        _require(
            isinstance(targets, list)
            and isinstance(keys, list)
            and len(targets) == len(keys) == shard.get("target_count"),
            "SHARD_TARGET_INVENTORY_DRIFT",
        )
        _require(
            shard.get("h_system_target_count")
            == sum(
                row.get("horizon") == "H_system"
                for row in targets
                if isinstance(row, dict)
            )
            and shard.get("h_system_target_count")
            <= plan.get(
                "h_system_targets_per_shard",
                DEFAULT_H_SYSTEM_TARGETS_PER_SHARD,
            ),
            "SHARD_H_SYSTEM_MEMORY_CAP_DRIFT",
        )
        for row, key in zip(targets, keys, strict=True):
            _require(isinstance(row, dict), "TARGET_NOT_OBJECT")
            _require(row.get("target_key") == key, "TARGET_KEY_DRIFT")
            _require(key not in seen, f"DUPLICATE_TARGET_KEY:{key}")
            seen.add(str(key))
            hashes = row.get("intervention_sha256_by_horizon")
            _require(
                isinstance(hashes, dict)
                and row.get("intervention_sha256")
                == hashes.get(row.get("horizon")),
                "TARGET_HORIZON_HASH_NOT_UPDATED",
            )
            sampling = row.get("sampling")
            _require(isinstance(sampling, dict), "TARGET_SAMPLING_MISSING")
            N_h = _strict_int(
                sampling.get("N_h"), "target.N_h", minimum=1
            )
            sealed = _strict_int(
                sampling.get("sealed_pool_n_h"),
                "target.sealed_pool_n_h",
                minimum=1,
            )
            frame = _strict_int(
                sampling.get("stage2_frame_n_h"),
                "target.stage2_frame_n_h",
                minimum=1,
            )
            attempted_h = _strict_int(
                sampling.get("attempt_n_h"),
                "target.attempt_n_h",
                minimum=1,
            )
            pool_pi = _strict_float(
                sampling.get("pool_pi_h"), "target.pool_pi_h"
            )
            survival = _strict_float(
                sampling.get("post_exclusion_survival_pi_h"),
                "target.post_exclusion_survival_pi_h",
            )
            stage2 = _strict_float(
                sampling.get("stage2_pi_h"), "target.stage2_pi_h"
            )
            final_pi = _strict_float(
                sampling.get("pi_h"), "target.pi_h"
            )
            _require(
                0 < attempted_h <= frame <= sealed <= N_h
                and abs(pool_pi - sealed / N_h) <= 1e-15
                and abs(survival - frame / sealed) <= 1e-15
                and abs(stage2 - attempted_h / frame) <= 1e-15
                and abs(final_pi - pool_pi * survival * stage2)
                <= 1e-15
                and abs(
                    _strict_float(
                        sampling.get("analysis_weight"),
                        "target.analysis_weight",
                    )
                    - 1.0 / final_pi
                )
                <= 1e-12,
                "TARGET_ATTEMPT_PROBABILITY_DRIFT",
            )
    _require(
        len(seen) == plan.get("attempt_budget"),
        "PLAN_ATTEMPT_BUDGET_DRIFT",
    )


def _validate_pair_run_payload(
    payload: Mapping[str, Any],
    *,
    shard: Mapping[str, Any],
    protected: Mapping[str, Any],
) -> None:
    _require(
        payload.get("schema") == PAIR_RUN_SCHEMA
        and payload.get("evidence_scope")
        == "EXACT_NATIVE_SAME_STATE_ONE_SHOT_MATCHED_PAIRS"
        and payload.get("formal_pass_claimed") is False,
        "PAIR_RUN_SCHEMA_OR_SCOPE",
    )
    _require(
        payload.get("protected_full_1x_shape") is True
        and payload.get("h_system_cohort_policy")
        == "ALL_INPUT_RUNTIME_IDS_IN_INPUT_ORDER",
        "PAIR_RUN_COHORT_POLICY",
    )
    _validate_native_input_binding(
        payload,
        protected=protected,
        label="PAIR_RUN",
    )
    controls = payload.get("frozen_controls")
    _require(isinstance(controls, dict), "PAIR_RUN_CONTROLS_MISSING")
    for name, expected in FROZEN_CONTROLS.items():
        _require(controls.get(name) == expected, f"PAIR_CONTROL_DRIFT:{name}")
    pairs = payload.get("pairs")
    targets = shard.get("targets")
    _require(
        isinstance(pairs, list)
        and isinstance(targets, list)
        and len(pairs) == len(targets) == payload.get("target_count"),
        "PAIR_RUN_TARGET_COUNT_DRIFT",
    )
    action_count = 0
    false_positive_count = 0
    complete_h_bag_count = 0
    applied_h_system_count = 0
    complete_h_system_count = 0
    for pair, target in zip(pairs, targets, strict=True):
        _require(
            isinstance(pair, dict)
            and pair.get("descriptor_id") == target.get("descriptor_id")
            and pair.get("kind") == target.get("kind")
            and pair.get("event_ordinal") == target.get("event_ordinal")
            and pair.get("horizon") == target.get("horizon"),
            "PAIR_RUN_TARGET_IDENTITY_DRIFT",
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
            _label_pair(pair, target)
        else:
            false_positive_count += 1
    _require(
        payload.get("action_changing_pair_count")
        == payload.get("applied_action_changing_pair_count")
        == action_count
        and payload.get("false_positive_pair_count")
        == false_positive_count
        and payload.get("complete_action_changing_h_bag_count")
        == complete_h_bag_count
        and payload.get("applied_action_changing_h_system_count")
        == applied_h_system_count
        and payload.get("complete_h_system_hard_gate_pass_count")
        == payload.get("h_system_pair_count")
        == complete_h_system_count,
        "PAIR_RUN_SUMMARY_COUNT_DRIFT",
    )


def _validate_completed_shard(
    value: Mapping[str, Any],
    *,
    root: Path,
    campaign: str,
    pilot_round: int,
    plan: Mapping[str, Any],
    shard: Mapping[str, Any],
    protected: Mapping[str, Any],
    build_binding: Mapping[str, Any],
    binary_sha256: str,
) -> None:
    """Validate every persisted shard field before reuse or aggregation."""
    index = int(shard["shard_index"])
    plan_path = root / _plan_path(campaign, pilot_round=pilot_round)
    _validate_self_bound(value, f"{campaign}_shard_{index}")
    binary = value.get("binary")
    native_payload = value.get("native_payload")
    _require(
        value.get("schema") == SHARD_SCHEMA
        and value.get("campaign") == campaign
        and value.get("shard_index") == index
        and value.get("status") == "COMPLETE"
        and value.get("formal_pass_claimed") is False
        and value.get("plan_path")
        == _plan_path(campaign, pilot_round=pilot_round).as_posix()
        and value.get("plan_self_sha256") == plan["self_sha256"]
        and value.get("plan_file_sha256") == _file_sha256(plan_path)
        and value.get("shard_sha256") == shard["shard_sha256"]
        and value.get("target_keys") == shard["target_keys"]
        and value.get("exact_binary_build_manifest") == build_binding
        and isinstance(binary, dict)
        and binary.get("sha256_before")
        == binary.get("sha256_after")
        == binary_sha256
        and binary.get("unchanged") is True
        and isinstance(native_payload, dict),
        f"SHARD_FULL_BINDING_DRIFT:{index}",
    )
    _validate_pair_run_payload(
        native_payload,
        shard=shard,
        protected=protected,
    )


def run_shard(
    *,
    root: Path,
    campaign: str,
    shard_index: int,
    binary: Path,
    build_manifest: Path,
    pilot_round: int = 1,
) -> dict[str, Any]:
    _require(
        campaign == "pilot" or pilot_round == 1,
        "FORMAL_CAMPAIGN_HAS_NO_ROUND_NAMESPACE",
    )
    _assert_repository_safety(root)
    protected = _protected_inputs(root)
    plan_path = root / _plan_path(campaign, pilot_round=pilot_round)
    plan = _load_json(plan_path)
    _validate_plan(plan, campaign)
    _require(
        _source_identity(root)["source_bundle_sha256"]
        == plan["source_bundle_sha256"],
        "WORKER_SOURCE_BUNDLE_DRIFT",
    )
    _require(
        _file_sha256(binary.resolve(strict=True))
        == plan["binary"]["sha256_before"],
        "WORKER_BINARY_DIFFERS_FROM_SCAN_BINARY",
    )
    build_binding = _validate_build_manifest(
        root=root,
        binary=binary,
        manifest_path=build_manifest,
    )
    _require(
        build_binding == plan.get("exact_binary_build_manifest"),
        "WORKER_BUILD_MANIFEST_DIFFERS_FROM_SCAN",
    )
    shards = plan["shards"]
    _require(0 <= shard_index < len(shards), "SHARD_INDEX_OUT_OF_RANGE")
    shard = shards[shard_index]
    output_path = root / _shard_output_path(
        campaign, shard_index, pilot_round=pilot_round
    )
    if output_path.is_file():
        _require(
            output_path.stat().st_size > 0,
            f"EMPTY_RUN_STATE_SHARD:{campaign}:{shard_index}",
        )
        existing = _load_zstd_json(output_path)
        _validate_completed_shard(
            existing,
            root=root,
            campaign=campaign,
            pilot_round=pilot_round,
            plan=plan,
            shard=shard,
            protected=protected,
            build_binding=build_binding,
            binary_sha256=plan["binary"]["sha256_before"],
        )
        return existing
    heartbeat_path = root / _heartbeat_path(
        campaign, shard_index, pilot_round=pilot_round
    )
    _atomic_json(
        heartbeat_path,
        {
            "schema": "czr005.g4irsf15.causal_shard_heartbeat.v1",
            "campaign": campaign,
            "shard_index": shard_index,
            "status": "RUNNING",
            "started_unix_seconds": time.time(),
            "plan_self_sha256": plan["self_sha256"],
            "shard_sha256": shard["shard_sha256"],
        },
    )
    native_args, _, _ = _native_arguments(root)
    payload, binary_identity = _call_exact_binary(
        root=root,
        binary=binary,
        function_name="g4irsf15_run_causal_target_pairs_from_records",
        arguments=[*native_args, shard["targets"]],
    )
    _validate_pair_run_payload(
        payload,
        shard=shard,
        protected=protected,
    )
    _require(
        binary_identity["sha256_before"]
        == plan["binary"]["sha256_before"],
        "WORKER_BINARY_DIFFERS_FROM_SCAN_BINARY",
    )
    result = _atomic_zstd_json(
        output_path,
        {
            "schema": SHARD_SCHEMA,
            "campaign": campaign,
            "shard_index": shard_index,
            "status": "COMPLETE",
            "formal_pass_claimed": False,
            "plan_path": _plan_path(
                campaign, pilot_round=pilot_round
            ).as_posix(),
            "plan_self_sha256": plan["self_sha256"],
            "plan_file_sha256": _file_sha256(plan_path),
            "shard_sha256": shard["shard_sha256"],
            "target_keys": shard["target_keys"],
            "exact_binary_build_manifest": build_binding,
            "binary": binary_identity,
            "native_payload": payload,
        },
    )
    output_byte_count = output_path.stat().st_size
    _atomic_json(
        heartbeat_path,
        {
            "schema": "czr005.g4irsf15.causal_shard_heartbeat.v1",
            "campaign": campaign,
            "shard_index": shard_index,
            "status": "COMPLETE",
            "finished_unix_seconds": time.time(),
            "plan_self_sha256": plan["self_sha256"],
            "shard_sha256": shard["shard_sha256"],
            "output_path": _shard_output_path(
                campaign, shard_index, pilot_round=pilot_round
            ).as_posix(),
            "output_sha256": _file_sha256(output_path),
            "output_byte_count": output_byte_count,
        },
    )
    return result


def _branch_gate(
    branch: Mapping[str, Any],
    horizon: str,
    *,
    terminal_evidence_complete: bool = True,
    protected_full_1x_shape: bool = True,
) -> tuple[bool, list[str]]:
    invariants = branch.get("invariants")
    if not isinstance(invariants, dict):
        return False, ["INVARIANTS_MISSING"]
    reasons: list[str] = []
    checks = (
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
    )
    for field, reason in checks:
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
    if _strict_float(
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
    _require(
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


def _outcome_delta(
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
    result: dict[str, float] = {}
    for field in fields:
        result[f"delta_{field}"] = _strict_float(
            treatment.get(field), f"treatment.{field}"
        ) - _strict_float(baseline.get(field), f"baseline.{field}")
    result["delta_deadline_miss_count"] = float(
        int(treatment.get("deadline_miss_count", 0))
        - int(baseline.get("deadline_miss_count", 0))
    )
    return result


def _affected_outcome_deltas(
    baseline_rows: Any, treatment_rows: Any
) -> list[dict[str, Any]]:
    _require(
        isinstance(baseline_rows, list) and isinstance(treatment_rows, list),
        "AFFECTED_BAG_OUTCOMES_MISSING",
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
    _require(set(baseline) == set(treatment), "AFFECTED_OUTCOME_ID_DRIFT")
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
        for field in numeric_fields:
            row[f"delta_{field}"] = _strict_float(
                right.get(field), f"treatment_bag.{field}"
            ) - _strict_float(left.get(field), f"baseline_bag.{field}")
        result.append(row)
    return result


def _causal_outcome_payload(row: Mapping[str, Any]) -> bytes:
    return _canonical_fields_payload(
        [
            (
                "schema",
                "s",
                "czr005.g4irsf15.causal_bag_outcome.v1",
            ),
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


def _validate_realized_outcome_deltas(
    rows: Any,
    *,
    declared_sha256: Any,
) -> tuple[list[dict[str, Any]], list[int]]:
    _require(isinstance(rows, list), "REALIZED_OUTCOME_DELTAS_MISSING")
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
    integer_fields = ("decision_count", "retry_count", "loop_count")
    normalized: list[dict[str, Any]] = []
    ids: list[int] = []
    row_hashes: list[str] = []
    for source in rows:
        _require(isinstance(source, dict), "REALIZED_DELTA_NOT_OBJECT")
        row = dict(source)
        baseline = row.get("baseline")
        treatment = row.get("treatment")
        _require(
            isinstance(baseline, dict) and isinstance(treatment, dict),
            "REALIZED_DELTA_OUTCOME_MISSING",
        )
        runtime_id = _strict_int(
            row.get("runtime_bag_id"),
            "realized_delta.runtime_bag_id",
            minimum=0,
        )
        _require(
            runtime_id == baseline.get("runtime_bag_id")
            == treatment.get("runtime_bag_id")
            and row.get("task_id") == baseline.get("task_id")
            == treatment.get("task_id")
            and row.get("segment_id") == baseline.get("segment_id")
            == treatment.get("segment_id"),
            "REALIZED_DELTA_IDENTITY_DRIFT",
        )
        _require(runtime_id not in ids, "DUPLICATE_REALIZED_DELTA_ID")
        ids.append(runtime_id)
        expected_scalars = {
            "completed_delta": int(bool(treatment["completed"]))
            - int(bool(baseline["completed"])),
            "failed_delta": int(bool(treatment["failed"]))
            - int(bool(baseline["failed"])),
            "status_changed": treatment["status"] != baseline["status"],
            "failure_reason_changed": (
                treatment["failure_reason"] != baseline["failure_reason"]
            ),
        }
        for name, expected in expected_scalars.items():
            _require(
                row.get(name) == expected,
                f"REALIZED_DELTA_ARITHMETIC:{name}",
            )
        for field in numeric_fields:
            expected = _strict_float(
                treatment.get(field), f"realized.treatment.{field}"
            ) - _strict_float(
                baseline.get(field), f"realized.baseline.{field}"
            )
            delta_field = (
                f"{field[:-8]}_delta_seconds"
                if field.endswith("_seconds")
                else f"{field}_delta_seconds"
            )
            _require(
                _strict_float(
                    row.get(delta_field),
                    f"realized.{delta_field}",
                )
                == expected,
                f"REALIZED_DELTA_ARITHMETIC:{field}",
            )
        for field in integer_fields:
            expected = int(treatment[field]) - int(baseline[field])
            _require(
                row.get(f"{field}_delta") == expected,
                f"REALIZED_DELTA_ARITHMETIC:{field}",
            )
        expected_hash = _canonical_fields_sha256(
            [
                (
                    "schema",
                    "s",
                    "czr005.g4irsf15.realized_outcome_delta.v1",
                ),
                ("baseline", "s", _causal_outcome_payload(baseline)),
                ("treatment", "s", _causal_outcome_payload(treatment)),
            ]
        )
        _require(
            row.get("outcome_delta_sha256") == expected_hash,
            "REALIZED_DELTA_SHA256_DRIFT",
        )
        row_hashes.append(expected_hash)
        normalized.append(row)
    sidecar_fields: list[tuple[str, str, Any]] = [
        (
            "schema",
            "s",
            "czr005.g4irsf15.realized_outcome_deltas.v1",
        ),
        ("row_count", "u", len(row_hashes)),
    ]
    sidecar_fields.extend(
        ("row_sha256", "s", value) for value in row_hashes
    )
    _require(
        declared_sha256 == _canonical_fields_sha256(sidecar_fields),
        "REALIZED_OUTCOME_DELTAS_SIDECAR_SHA256_DRIFT",
    )
    return normalized, ids


def _raw_bag_metric_delta(
    baseline: Mapping[str, Any],
    treatment: Mapping[str, Any],
) -> dict[str, float]:
    numeric_fields = (
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
        f"delta_{field}": _strict_float(
            treatment.get(field), f"raw_bag.treatment.{field}"
        )
        - _strict_float(
            baseline.get(field), f"raw_bag.baseline.{field}"
        )
        for field in numeric_fields
    }
    result["delta_deadline_miss_raw_bag_count"] = float(
        int(treatment.get("deadline_miss_raw_bag_count", 0))
        - int(baseline.get("deadline_miss_raw_bag_count", 0))
    )
    return result


def _raw_bag_sequential_mean(values: Sequence[float]) -> float:
    _require(values, "RAW_BAG_MEAN_EMPTY")
    total = 0.0
    for value in values:
        total += value
    return total / len(values)


def _raw_bag_type7_quantile(
    values: Sequence[float], probability: float
) -> float:
    _require(values, "RAW_BAG_QUANTILE_EMPTY")
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


def _validate_raw_bag_sufficient_statistics_sidecar(
    sidecar: Any,
    *,
    raw_metrics: Mapping[str, Any],
    target: Mapping[str, Any],
    branch_name: str,
) -> dict[str, Any]:
    _require(
        isinstance(sidecar, dict),
        f"RAW_BAG_SUFFICIENT_STATISTICS_MISSING:{branch_name}",
    )
    rows = sidecar.get("rows")
    _require(
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
    covered_runtime_ids: list[int] = []
    previous_task_id = -1
    completed_segment_count = 0
    complete_count = 0
    failed_count = 0
    deadline_miss_count = 0
    totals: dict[str, list[float]] = {
        name: []
        for name in (
            "original_entry_total_seconds",
            "java_release_total_seconds",
            "scheduled_pre_release_wait_total_seconds",
            "source_wait_total_seconds",
            "network_time_total_seconds",
            "total_system_time_total_seconds",
        )
    }
    for index, source in enumerate(rows):
        _require(
            isinstance(source, dict),
            f"RAW_BAG_SUFFICIENT_ROW_NOT_OBJECT:{branch_name}:{index}",
        )
        task_id = _strict_int(
            source.get("task_id"),
            f"raw_sidecar.{branch_name}.task_id",
            minimum=0,
        )
        runtime_ids = source.get("runtime_bag_ids")
        _require(
            task_id > previous_task_id
            and isinstance(runtime_ids, list)
            and runtime_ids,
            f"RAW_BAG_SUFFICIENT_ROW_ORDER:{branch_name}:{index}",
        )
        previous_task_id = task_id
        normalized_ids = [
            _strict_int(
                value,
                f"raw_sidecar.{branch_name}.runtime_bag_id",
                minimum=0,
            )
            for value in runtime_ids
        ]
        _require(
            normalized_ids == sorted(set(normalized_ids))
            and source.get("runtime_segment_count")
            == len(normalized_ids),
            f"RAW_BAG_RUNTIME_ID_MAPPING:{branch_name}:{task_id}",
        )
        completed = _strict_int(
            source.get("completed_segment_count"),
            f"raw_sidecar.{branch_name}.completed_segment_count",
            minimum=0,
        )
        complete = source.get("complete")
        failed = source.get("failed")
        deadline_miss = source.get("deadline_miss")
        _require(
            isinstance(complete, bool)
            and isinstance(failed, bool)
            and isinstance(deadline_miss, bool)
            and completed <= len(normalized_ids)
            and complete is True
            and failed is False
            and completed == len(normalized_ids),
            f"RAW_BAG_SUFFICIENT_ROW_COMPLETION:{branch_name}:{task_id}",
        )
        numeric = {
            name: _strict_float(
                source.get(name),
                f"raw_sidecar.{branch_name}.{name}",
            )
            for name in totals
        }
        _require(
            all(value >= 0.0 for value in numeric.values())
            and abs(
                numeric["scheduled_pre_release_wait_total_seconds"]
                + numeric["source_wait_total_seconds"]
                + numeric["network_time_total_seconds"]
                - numeric["original_entry_total_seconds"]
            )
            <= 1.0e-7
            and abs(
                numeric["scheduled_pre_release_wait_total_seconds"]
                + numeric["source_wait_total_seconds"]
                + numeric["network_time_total_seconds"]
                - numeric["total_system_time_total_seconds"]
            )
            <= 1.0e-7,
            f"RAW_BAG_SUFFICIENT_TIMING_DECOMPOSITION:{branch_name}:{task_id}",
        )
        runtime_mapping_sha = _canonical_fields_sha256(
            [
                (
                    "schema",
                    "s",
                    "czr005.g4irsf15.raw_bag_runtime_id_mapping_row.v1",
                ),
                ("task_id", "i", task_id),
                ("runtime_bag_ids", "I", normalized_ids),
            ]
        )
        row_fields: list[tuple[str, str, Any]] = [
            (
                "schema",
                "s",
                "czr005.g4irsf15.raw_bag_sufficient_statistics_row.v1",
            ),
            ("task_id", "i", task_id),
            ("runtime_bag_ids", "I", normalized_ids),
            ("runtime_segment_count", "i", len(normalized_ids)),
            ("completed_segment_count", "i", completed),
            ("complete", "b", complete),
            ("failed", "b", failed),
            ("deadline_miss", "b", deadline_miss),
        ]
        row_fields.extend((name, "d", numeric[name]) for name in totals)
        row_fields.append(
            ("runtime_id_mapping_sha256", "s", runtime_mapping_sha)
        )
        row_sha = _canonical_fields_sha256(row_fields)
        _require(
            source.get("runtime_id_mapping_sha256")
            == runtime_mapping_sha
            and source.get("row_sha256") == row_sha,
            f"RAW_BAG_SUFFICIENT_ROW_HASH:{branch_name}:{task_id}",
        )
        content_fields.append(("row_sha256", "s", row_sha))
        covered_runtime_ids.extend(normalized_ids)
        completed_segment_count += completed
        complete_count += int(complete)
        failed_count += int(failed)
        deadline_miss_count += int(deadline_miss)
        for name, value in numeric.items():
            totals[name].append(value)
    _require(
        sorted(covered_runtime_ids) == list(range(FULL_SEGMENT_COUNT)),
        f"RAW_BAG_SUFFICIENT_RUNTIME_COVERAGE:{branch_name}",
    )
    expected_content_sha = _canonical_fields_sha256(content_fields)
    _require(
        sidecar.get("content_sha256") == expected_content_sha,
        f"RAW_BAG_SUFFICIENT_CONTENT_HASH:{branch_name}",
    )
    original = totals["original_entry_total_seconds"]
    expected_metrics = {
        "selected_segment_count": FULL_SEGMENT_COUNT,
        "selected_raw_bag_count": FULL_RAW_BAG_COUNT,
        "completed_segment_count": completed_segment_count,
        "complete_raw_bag_count": complete_count,
        "failed_raw_bag_count": failed_count,
        "deadline_miss_raw_bag_count": deadline_miss_count,
        "completion_rate": complete_count / FULL_RAW_BAG_COUNT,
        "comparison_eligible": True,
        "primary_denominator": "original_entry_time_tth",
        "denominator_scope": "SUM_PER_RAW_TASK_OVER_ALL_PROTECTED_SEGMENTS",
        "original_entry_mean_minutes": (
            _raw_bag_sequential_mean(original) / 60.0
        ),
        "original_entry_median_seconds": (
            _raw_bag_type7_quantile(original, 0.5)
        ),
        "original_entry_p95_seconds": (
            _raw_bag_type7_quantile(original, 0.95)
        ),
        "original_entry_p99_seconds": (
            _raw_bag_type7_quantile(original, 0.99)
        ),
        "original_entry_max_seconds": max(original),
        "java_release_mean_minutes": (
            _raw_bag_sequential_mean(
                totals["java_release_total_seconds"]
            )
            / 60.0
        ),
        "scheduled_pre_release_wait_mean_minutes": (
            _raw_bag_sequential_mean(
                totals["scheduled_pre_release_wait_total_seconds"]
            )
            / 60.0
        ),
        "source_wait_mean_minutes": (
            _raw_bag_sequential_mean(
                totals["source_wait_total_seconds"]
            )
            / 60.0
        ),
        "network_time_mean_minutes": (
            _raw_bag_sequential_mean(
                totals["network_time_total_seconds"]
            )
            / 60.0
        ),
        "total_system_time_mean_minutes": (
            _raw_bag_sequential_mean(
                totals["total_system_time_total_seconds"]
            )
            / 60.0
        ),
        "survivor_original_entry_mean_minutes": (
            _raw_bag_sequential_mean(original) / 60.0
        ),
        "survivor_metric_comparison_allowed": False,
        "quantile_method": "LINEAR_TYPE7_N_MINUS_ONE",
    }
    _require(
        dict(raw_metrics) == expected_metrics,
        f"RAW_BAG_AGGREGATES_NOT_REDERIVED:{branch_name}",
    )
    return {
        "schema": sidecar["schema"],
        "content_sha256": expected_content_sha,
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
        "rederived_raw_bag_metrics_sha256": _canonical_sha256(
            expected_metrics
        ),
    }


def _validate_cohort_difference_sidecar(
    sidecar: Any,
    *,
    realized_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    _require(isinstance(sidecar, dict), "COHORT_DIFFERENCE_SIDECAR_MISSING")
    rows = sidecar.get("rows")
    _require(
        sidecar.get("schema")
        == "czr005.g4irsf15.full_cohort_outcome_difference.v1"
        and sidecar.get("row_count") == FULL_SEGMENT_COUNT
        and sidecar.get("complete_coverage") is True
        and sidecar.get("runtime_id_order")
        == "CONTIGUOUS_ZERO_BASED_INPUT_ORDER"
        and isinstance(rows, list)
        and len(rows) == FULL_SEGMENT_COUNT,
        "COHORT_DIFFERENCE_SIDECAR_COVERAGE",
    )
    digest_fields: list[tuple[str, str, Any]] = [
        (
            "schema",
            "s",
            "czr005.g4irsf15.full_cohort_outcome_difference.v1",
        ),
        ("row_count", "u", FULL_SEGMENT_COUNT),
    ]
    changed_ids: list[int] = []
    realized_by_id = {
        int(row["runtime_bag_id"]): row for row in realized_rows
    }
    for runtime_id, source in enumerate(rows):
        _require(isinstance(source, dict), "COHORT_DIFFERENCE_ROW_NOT_OBJECT")
        baseline_sha = source.get("baseline_outcome_sha256")
        treatment_sha = source.get("treatment_outcome_sha256")
        changed = source.get("outcome_changed")
        expected_row_sha = _canonical_fields_sha256(
            [
                ("runtime_bag_id", "i", runtime_id),
                ("baseline_outcome_sha256", "s", baseline_sha),
                ("treatment_outcome_sha256", "s", treatment_sha),
                ("outcome_changed", "b", changed),
            ]
        )
        _require(
            source.get("runtime_bag_id") == runtime_id
            and _is_sha256(baseline_sha)
            and _is_sha256(treatment_sha)
            and isinstance(changed, bool)
            and changed == (baseline_sha != treatment_sha)
            and source.get("row_sha256") == expected_row_sha,
            f"COHORT_DIFFERENCE_ROW_DRIFT:{runtime_id}",
        )
        if changed:
            changed_ids.append(runtime_id)
            numeric = realized_by_id.get(runtime_id)
            _require(
                numeric is not None
                and hashlib.sha256(
                    _causal_outcome_payload(numeric["baseline"])
                ).hexdigest()
                == baseline_sha
                and hashlib.sha256(
                    _causal_outcome_payload(numeric["treatment"])
                ).hexdigest()
                == treatment_sha,
                f"COHORT_DIFFERENCE_NUMERIC_BINDING:{runtime_id}",
            )
        digest_fields.append(("row_sha256", "s", expected_row_sha))
    digest_fields.append(("changed_count", "i", len(changed_ids)))
    _require(
        sidecar.get("changed_count") == len(changed_ids)
        and sidecar.get("content_sha256")
        == _canonical_fields_sha256(digest_fields)
        and set(changed_ids) == set(realized_by_id),
        "COHORT_DIFFERENCE_CONTENT_OR_REALIZED_DRIFT",
    )
    return {
        "schema": sidecar["schema"],
        "row_count": sidecar["row_count"],
        "changed_count": sidecar["changed_count"],
        "complete_coverage": sidecar["complete_coverage"],
        "runtime_id_order": sidecar["runtime_id_order"],
        "content_sha256": sidecar["content_sha256"],
    }


def _signed_label(delta_seconds: float) -> str:
    return (
        "BENEFICIAL"
        if delta_seconds < -1e-9
        else "HARMFUL"
        if delta_seconds > 1e-9
        else "NEUTRAL_WITHIN_TOLERANCE"
    )


def _validate_action_change_certificate(
    pair: Mapping[str, Any],
    target: Mapping[str, Any],
) -> bool:
    certificate = pair.get("committed_action_certificate")
    baseline_step = pair.get("baseline_step")
    treatment_step = pair.get("treatment_step")
    if not all(
        isinstance(value, dict)
        for value in (certificate, baseline_step, treatment_step)
    ):
        return False
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
        == target.get("boundary_sha256")
        and treatment_step.get("requested_intervention_sha256")
        == target.get("intervention_sha256")
        and treatment_step.get("application_reason")
        == certificate.get("application_reason")
        and sorted(treatment_step.get("affected_runtime_bag_ids", []))
        == expected_direct
        and treatment_step.get("source_state_sha256")
        == pair.get("source_checkpoint_state_sha256")
        and baseline_step.get("source_state_sha256")
        == pair.get("source_checkpoint_state_sha256")
    )
    snapshot_valid = (
        isinstance(certificate.get("baseline_pre_action_snapshots"), list)
        and isinstance(
            certificate.get("treatment_pre_action_snapshots"), list
        )
        and isinstance(
            certificate.get("baseline_post_action_snapshots"), list
        )
        and isinstance(
            certificate.get("treatment_post_action_snapshots"), list
        )
    )
    if not snapshot_valid:
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
    snapshot_valid = (
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
    baseline_action = str(certificate.get("baseline_action", ""))
    treatment_action = str(certificate.get("treatment_action", ""))
    runtime_id = int(target["runtime_bag_id"])
    semantic_valid = False
    if kind == "I1":
        pre_winner = baseline_pre_by_id.get(runtime_id, {})
        peer_id = int(target["peer_runtime_bag_id"])
        pre_peer = baseline_pre_by_id.get(peer_id, {})
        baseline_winner = baseline_post_by_id.get(runtime_id, {})
        baseline_peer = baseline_post_by_id.get(peer_id, {})
        treatment_winner = treatment_post_by_id.get(runtime_id, {})
        treatment_peer = treatment_post_by_id.get(peer_id, {})
        semantic_valid = (
            certificate.get("committed_action_type") == "SOURCE_ADMIT"
            and certificate.get("application_reason")
            == "APPLIED_I1_SOURCE_ADMIT_COMMITTED_ONE_ACTION"
            and baseline_action == target.get("baseline_action")
            and treatment_action == target.get("intervention_action")
            and _strict_float(
                pre_winner.get("admitted_time"), "i1.pre_winner.admitted"
            )
            < 0.0
            and _strict_float(
                pre_peer.get("admitted_time"), "i1.pre_peer.admitted"
            )
            < 0.0
            and pre_winner.get("source_queued_at_current_node") is True
            and pre_peer.get("source_queued_at_current_node") is True
            and pre_winner.get("current_node")
            == pre_peer.get("current_node")
            and _strict_float(
                baseline_winner.get("admitted_time"),
                "i1.baseline_winner.admitted",
            )
            >= 0.0
            and _strict_float(
                baseline_peer.get("admitted_time"),
                "i1.baseline_peer.admitted",
            )
            < 0.0
            and _strict_float(
                treatment_winner.get("admitted_time"),
                "i1.treatment_winner.admitted",
            )
            < 0.0
            and _strict_float(
                treatment_peer.get("admitted_time"),
                "i1.treatment_peer.admitted",
            )
            >= 0.0
        )
    elif kind == "I3":
        baseline_next = int(target["baseline_next_node"])
        treatment_next = int(target["selected_next_node"])
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
        semantic_valid = (
            commit_type in {"EDGE_COMMIT", "MERGE_REQUEST_ENQUEUED"}
            and baseline_action
            == f"{baseline_commit[0]}:NEXT_NODE={baseline_commit[1]}"
            and treatment_action
            == f"{treatment_commit[0]}:NEXT_NODE={treatment_commit[1]}"
            and baseline_commit[1] == baseline_next
            and treatment_commit == (commit_type, treatment_next)
            and baseline_commit[1] != treatment_commit[1]
            and pre.get("queued_at_current_node") is True
            and pre.get("status") == "JUNCTION_QUEUE"
            and int(pre.get("pending_merge_request_id", -1)) == 0
            and target.get("baseline_action")
            == (
                f"NEXT_EDGE_RUNTIME_BAG_ID={runtime_id};"
                f"NEXT_NODE={baseline_next}"
            )
            and target.get("intervention_action")
            == (
                f"NEXT_EDGE_RUNTIME_BAG_ID={runtime_id};"
                f"NEXT_NODE={treatment_next}"
            )
            and certificate.get("application_reason") == expected_reason
        )
    elif kind == "I4":
        pre = baseline_pre_by_id.get(runtime_id, {})
        baseline_commit = committed_route_action(
            baseline_post_by_id.get(runtime_id, {})
        )
        treatment_snapshot = treatment_post_by_id.get(runtime_id, {})
        semantic_valid = (
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
            == (
                "APPLIED_I4_SAFE_HOLD_UNTIL_NEXT_"
                "JUNCTION_SERVICE_OPPORTUNITY"
            )
            and pre.get("queued_at_current_node") is True
            and pre.get("status") == "JUNCTION_QUEUE"
            and int(pre.get("pending_merge_request_id", -1)) == 0
            and pre.get("junction_wakeup_pending") is True
            and _strict_float(
                pre.get("junction_wakeup_time"),
                "i4.pre.junction_wakeup_time",
            )
            == _strict_float(target.get("event_time"), "i4.event_time")
            and treatment_snapshot.get("queued_at_current_node") is True
            and treatment_snapshot.get("junction_wakeup_pending") is True
            and int(
                treatment_snapshot.get(
                    "junction_wakeup_generation", -1
                )
            )
            > int(pre.get("junction_wakeup_generation", -1))
            and _strict_float(
                treatment_snapshot.get("junction_wakeup_time"),
                "i4.treatment.junction_wakeup_time",
            )
            > _strict_float(target.get("event_time"), "i4.event_time")
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
        and snapshot_valid
        and semantic_valid
    )
    return bool(
        independently_valid
        and certificate.get("valid") is independently_valid
        and certificate.get("post_commit_verified")
        is independently_valid
    )


def _direct_outcome_metrics(
    rows: Any,
    *,
    expected_runtime_ids: Sequence[int],
    branch_name: str,
) -> tuple[dict[int, Mapping[str, Any]], dict[str, Any]]:
    _require(
        isinstance(rows, list)
        and all(isinstance(row, dict) for row in rows),
        f"DIRECT_OUTCOMES_MISSING:{branch_name}",
    )
    by_id = {
        _strict_int(
            row.get("runtime_bag_id"),
            f"direct.{branch_name}.runtime_bag_id",
            minimum=0,
        ): row
        for row in rows
    }
    _require(
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
        _require(
            row.get("known") is True
            and row.get("completed") is True
            and row.get("failed") is False
            and row.get("status") == "COMPLETED"
            and row.get("failure_reason") == "",
            f"DIRECT_OUTCOME_NOT_COMPLETE:{branch_name}:{runtime_id}",
        )
        numeric = {
            name: _strict_float(
                row.get(name), f"direct.{branch_name}.{name}"
            )
            for name in numeric_fields
        }
        completions.append(numeric["completion_seconds"])
        for name in sums:
            sums[name] += numeric[name]
        deadline = _strict_float(
            row.get("deadline"), f"direct.{branch_name}.deadline"
        )
        if deadline >= 0.0 and numeric["finish_time"] > deadline:
            deadline_miss += 1
        decisions += _strict_int(
            row.get("decision_count"),
            f"direct.{branch_name}.decision_count",
            minimum=0,
        )
        retries += _strict_int(
            row.get("retry_count"),
            f"direct.{branch_name}.retry_count",
            minimum=0,
        )
        loops += _strict_int(
            row.get("loop_count"),
            f"direct.{branch_name}.loop_count",
            minimum=0,
        )
    denominator = len(rows)
    ordered_completion = sorted(completions)
    def nearest_rank(probability: float) -> float:
        rank = max(1, int(math.ceil(probability * denominator)))
        return ordered_completion[rank - 1]

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


def _label_pair(
    pair: Mapping[str, Any],
    target: Mapping[str, Any],
) -> dict[str, Any]:
    horizon = str(pair.get("horizon"))
    action_changed = pair.get("action_changed") is True
    same_state = (
        pair.get("same_state_start") is True
        and pair.get("baseline_start_state_sha256")
        == pair.get("treatment_start_state_sha256")
        == pair.get("source_checkpoint_state_sha256")
        == target.get("runtime_state_sha256")
    )
    certificate = pair.get("committed_action_certificate")
    certificate_valid = _validate_action_change_certificate(pair, target)
    baseline = pair.get("baseline")
    treatment = pair.get("treatment")
    if not isinstance(baseline, dict) or not isinstance(treatment, dict):
        missing_label = {
            "schema": LABEL_SCHEMA,
            "target_key": target["target_key"],
            "descriptor_id": target["descriptor_id"],
            "kind": target["kind"],
            "clone_group_id": target["clone_group_id"],
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
        missing_label["label_sha256"] = _canonical_sha256(missing_label)
        return missing_label
    horizon_complete = (
        pair.get("horizon_complete") is True
        and baseline.get("horizon_complete") is True
        and treatment.get("horizon_complete") is True
        and baseline.get("blocked") is False
        and treatment.get("blocked") is False
    )
    horizon_blockers: list[str] = []
    if not horizon_complete:
        horizon_blockers.append("HORIZON_INCOMPLETE_OR_BLOCKED")
    baseline_gate, baseline_blockers = _branch_gate(
        baseline,
        horizon,
        terminal_evidence_complete=horizon_complete,
        protected_full_1x_shape=(
            pair.get("protected_full_1x_shape") is True
        ),
    )
    treatment_gate, treatment_blockers = _branch_gate(
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
    _require(
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
    _require(
        isinstance(baseline_metrics, dict)
        and isinstance(treatment_metrics, dict),
        "PAIR_COHORT_METRICS_MISSING",
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
        _direct_outcome_metrics(
            baseline.get("affected_bag_outcomes"),
            expected_runtime_ids=expected_direct,
            branch_name="baseline",
        )
    )
    treatment_direct, expected_treatment_direct_metrics = (
        _direct_outcome_metrics(
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
    _require(
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
        _require(
            baseline_metrics == expected_baseline_direct_metrics
            and treatment_metrics == expected_treatment_direct_metrics,
            "H_BAG_COHORT_METRICS_NOT_REDERIVED_FROM_DIRECT_OUTCOMES",
        )
    delta = _outcome_delta(baseline_metrics, treatment_metrics)
    affected_deltas = _affected_outcome_deltas(
        baseline.get("affected_bag_outcomes"),
        treatment.get("affected_bag_outcomes"),
    )
    direct = pair.get(
        "direct_affected_runtime_bag_ids",
        pair.get("affected_runtime_bag_ids", []),
    )
    _require(
        isinstance(direct, list)
        and sorted(int(value) for value in direct) == expected_direct,
        "DIRECT_AFFECTED_IDENTITY_DRIFT",
    )
    baseline_affected_ids = sorted(
        int(row["runtime_bag_id"])
        for row in baseline.get("affected_bag_outcomes", [])
    )
    treatment_affected_ids = sorted(
        int(row["runtime_bag_id"])
        for row in treatment.get("affected_bag_outcomes", [])
    )
    delta_affected_ids = sorted(
        int(row["runtime_bag_id"]) for row in affected_deltas
    )
    native_affected_deltas = pair.get("affected_bag_deltas")
    _require(
        isinstance(native_affected_deltas, list)
        and all(isinstance(row, dict) for row in native_affected_deltas),
        "NATIVE_AFFECTED_BAG_DELTAS_MISSING",
    )
    native_delta_ids = sorted(
        int(row["runtime_bag_id"]) for row in native_affected_deltas
    )
    _require(
        baseline_affected_ids
        == treatment_affected_ids
        == delta_affected_ids
        == native_delta_ids
        == expected_direct,
        "DIRECT_AFFECTED_OUTCOME_EVIDENCE_MISMATCH",
    )
    _require(affected_deltas, "DIRECT_AFFECTED_OUTCOMES_EMPTY")
    direct_completion_delta = sum(
        row["delta_completion_seconds"] for row in affected_deltas
    ) / len(affected_deltas)
    direct_signed = _signed_label(direct_completion_delta)
    system_completion_delta = (
        delta["delta_completion_mean_seconds"]
        if horizon == "H_system"
        else None
    )
    system_signed = (
        _signed_label(system_completion_delta)
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
    fixed_h_system_cohort = (
        horizon != "H_system"
        or (
            pair.get("h_system_cohort_is_all_input_runtime_ids") is True
            and pair.get("h_system_cohort_size") == FULL_SEGMENT_COUNT
        )
    )
    evidence_blockers: list[str] = []
    realized_delta_rows: list[dict[str, Any]] | None = None
    realized_direct: list[int] | None = None
    if horizon == "H_system" and not realized_observable:
        evidence_blockers.append("REALIZED_AFFECTED_SET_NOT_REPORTED")
    if not fixed_h_system_cohort:
        evidence_blockers.append(
            "H_SYSTEM_COHORT_NOT_FIXED_FULL_ORIGINAL"
        )
    raw_baseline = baseline.get("raw_bag_cohort_metrics")
    raw_treatment = treatment.get("raw_bag_cohort_metrics")
    raw_delta: dict[str, float] | None = None
    baseline_raw_sidecar_binding: dict[str, Any] | None = None
    treatment_raw_sidecar_binding: dict[str, Any] | None = None
    cohort_difference_binding: dict[str, Any] | None = None
    if horizon == "H_system":
        if realized_observable:
            realized_delta_rows, realized_delta_ids = (
                _validate_realized_outcome_deltas(
                    pair.get("realized_outcome_deltas"),
                    declared_sha256=pair.get(
                        "realized_outcome_deltas_sha256"
                    ),
                )
            )
            realized_ids = sorted(int(value) for value in realized)
            externality_ids = sorted(int(value) for value in externality)
            realized_direct = sorted(
                set(realized_ids) & set(expected_direct)
            )
            _require(
                realized_ids == sorted(realized_delta_ids)
                and externality_ids
                == sorted(set(realized_ids) - set(expected_direct)),
                "REALIZED_EXTERNALITY_PARTITION_DRIFT",
            )
            native_externality = pair.get("realized_externality")
            _require(
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
                "REALIZED_EXTERNALITY_SIDECAR_DRIFT",
            )
        _require(
            pair.get("cohort_difference_sidecar_serialized") is True,
            "COHORT_DIFFERENCE_SIDECAR_NOT_SERIALIZED",
        )
        cohort_difference_binding = _validate_cohort_difference_sidecar(
            pair.get("cohort_difference_sidecar"),
            realized_rows=realized_delta_rows or [],
        )
        if not isinstance(raw_baseline, dict) or not isinstance(
            raw_treatment, dict
        ):
            evidence_blockers.append("RAW_BAG_COHORT_METRICS_MISSING")
        else:
            for branch_name, branch_row, raw in (
                ("baseline", baseline, raw_baseline),
                ("treatment", treatment, raw_treatment),
            ):
                _require(
                    raw.get("selected_segment_count")
                    == raw.get("completed_segment_count")
                    == FULL_SEGMENT_COUNT
                    and raw.get("selected_raw_bag_count")
                    == raw.get("complete_raw_bag_count")
                    == FULL_RAW_BAG_COUNT
                    and raw.get("failed_raw_bag_count") == 0
                    and raw.get("comparison_eligible") is True,
                    f"RAW_BAG_COHORT_NOT_COMPLETE:{branch_name}",
                )
                _require(
                    branch_row.get(
                        "h_system_cohort_mapping_sha256"
                    )
                    == target.get("h_system_cohort_mapping_sha256")
                    and branch_row.get("raw_bag_mapping_sha256")
                    == target.get("raw_bag_mapping_sha256")
                    and branch_row.get(
                        "raw_bag_original_entry_mapping_sha256"
                    )
                    == target.get(
                        "raw_bag_original_entry_mapping_sha256"
                    ),
                    f"RAW_BAG_MAPPING_BINDING_DRIFT:{branch_name}",
                )
                _require(
                    branch_row.get(
                        "raw_bag_sufficient_statistics_serialized"
                    )
                    is True,
                    f"RAW_BAG_SUFFICIENT_STATISTICS_NOT_SERIALIZED:{branch_name}",
                )
                sidecar_binding = (
                    _validate_raw_bag_sufficient_statistics_sidecar(
                        branch_row.get(
                            "raw_bag_sufficient_statistics_sidecar"
                        ),
                        raw_metrics=raw,
                        target=target,
                        branch_name=branch_name,
                    )
                )
                if branch_name == "baseline":
                    baseline_raw_sidecar_binding = sidecar_binding
                else:
                    treatment_raw_sidecar_binding = sidecar_binding
            _require(
                pair.get("h_system_cohort_mapping_sha256")
                == target.get("h_system_cohort_mapping_sha256")
                and pair.get("raw_bag_mapping_sha256")
                == target.get("raw_bag_mapping_sha256")
                and pair.get("raw_bag_original_entry_mapping_sha256")
                == target.get(
                    "raw_bag_original_entry_mapping_sha256"
                ),
                "PAIR_RAW_BAG_MAPPING_BINDING_DRIFT",
            )
            raw_delta = _raw_bag_metric_delta(
                raw_baseline, raw_treatment
            )
    else:
        _require(
            pair.get("realized_affected_set_observable") is False
            and pair.get("externality_observation_status")
            == "NOT_OBSERVED_AT_H_BAG"
            and pair.get("realized_outcome_deltas") == []
            and pair.get("cohort_difference_sidecar") is None
            and pair.get("cohort_difference_sidecar_serialized") is False,
            "H_BAG_SYSTEM_EXTERNALITY_MUST_BE_NOT_OBSERVED",
        )
        for branch_name, branch_row in (
            ("baseline", baseline),
            ("treatment", treatment),
        ):
            _require(
                branch_row.get("raw_bag_cohort_metrics") is None
                and branch_row.get(
                    "raw_bag_sufficient_statistics_sidecar"
                )
                is None
                and branch_row.get(
                    "raw_bag_sufficient_statistics_serialized"
                )
                is False,
                f"H_BAG_RAW_BAG_SIDECAR_MUST_BE_ABSENT:{branch_name}",
            )
        realized = None
        externality = None
        realized_observable = False
    h_system_original_entry_delta_seconds = (
        raw_delta["delta_original_entry_mean_minutes"] * 60.0
        if raw_delta is not None
        else None
    )
    if h_system_original_entry_delta_seconds is not None:
        system_signed = _signed_label(
            h_system_original_entry_delta_seconds
        )
    all_blockers = baseline_blockers + treatment_blockers
    safety_blockers = list(all_blockers)
    branch_live_safety_equivalent = (
        baseline.get("invariants", {}).get("live_safety_pass") is True
        and treatment.get("invariants", {}).get("live_safety_pass") is True
    )
    _require(
        pair.get("live_safety_pass") is branch_live_safety_equivalent
        and pair.get("safety_equivalent")
        is branch_live_safety_equivalent,
        "PAIR_SAFETY_EQUIVALENCE_DRIFT",
    )
    evidence_complete = not (
        horizon == "H_system"
        and evidence_blockers
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
    exclusion = "" if eligible else "|".join(
        sorted(
            set(
                all_blockers
                + horizon_blockers
                + evidence_blockers
                + (
                    []
                    if action_changed
                    else ["ACTION_NOT_CHANGED"]
                )
                + ([] if same_state else ["START_STATE_MISMATCH"])
                + ([] if certificate_valid else ["CERTIFICATE_INVALID"])
            )
        )
    )
    label = {
        "schema": LABEL_SCHEMA,
        "target_key": target["target_key"],
        "descriptor_id": target["descriptor_id"],
        "kind": target["kind"],
        "clone_group_id": target["clone_group_id"],
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
        "safety_equivalent": branch_live_safety_equivalent,
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
        "raw_bag_mapping_sha256": target.get(
            "raw_bag_mapping_sha256"
        ),
        "raw_bag_original_entry_mapping_sha256": target.get(
            "raw_bag_original_entry_mapping_sha256"
        ),
        "signed_label": direct_signed,
        "direct_affected_signed_label": direct_signed,
        "h_bag_delta_completion_mean_seconds": direct_completion_delta,
        "h_system_signed_label": system_signed,
        "h_system_delta_completion_mean_seconds": system_completion_delta,
        "h_system_delta_original_entry_mean_seconds": (
            h_system_original_entry_delta_seconds
        ),
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
        "realized_outcome_deltas": realized_delta_rows,
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
        "affected_bag_deltas": affected_deltas,
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
        "cohort_difference_sidecar_binding": (
            cohort_difference_binding
        ),
        "committed_action_certificate": certificate,
        "sampling": target.get("sampling"),
        "coverage_tags": target.get("coverage_tags", []),
        "offline_sampling_metadata": target.get(
            "offline_sampling_metadata"
        ),
    }
    label["label_sha256"] = _canonical_sha256(label)
    return label


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


def _analysis_metric_values(
    label: Mapping[str, Any],
) -> dict[str, float]:
    if label.get("eligible_causal_label") is not True:
        return {}
    values: dict[str, float] = {}
    delta = label.get("delta_metrics")
    _require(isinstance(delta, dict), "ANALYSIS_DELTA_METRICS_MISSING")
    for metric in ANALYSIS_DELTA_METRICS:
        values[metric] = _strict_float(
            delta.get(metric), f"analysis.{metric}"
        )
    affected = label.get("affected_bag_deltas")
    _require(
        isinstance(affected, list) and affected,
        "ANALYSIS_DIRECT_AFFECTED_DELTAS_MISSING",
    )
    values["direct_affected_delta_completion_mean_seconds"] = (
        math.fsum(
            _strict_float(
                row.get("delta_completion_seconds"),
                "analysis.direct.delta_completion_seconds",
            )
            for row in affected
            if isinstance(row, dict)
        )
        / len(affected)
    )
    _require(
        sum(isinstance(row, dict) for row in affected) == len(affected),
        "ANALYSIS_DIRECT_AFFECTED_DELTA_ROW_NOT_OBJECT",
    )
    raw = label.get("raw_bag_delta_metrics")
    if raw is not None:
        _require(
            label.get("horizon") == "H_system"
            and isinstance(raw, dict),
            "ANALYSIS_RAW_METRICS_SCOPE_DRIFT",
        )
        for metric in ANALYSIS_RAW_METRICS:
            values[f"raw_bag_{metric}"] = _strict_float(
                raw.get(metric), f"analysis.raw_bag.{metric}"
            )
    return values


def _analysis_group_specs() -> list[dict[str, str]]:
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


def _analysis_group_match(
    label: Mapping[str, Any], group: Mapping[str, str]
) -> bool:
    group_type = group["group_type"]
    if group_type == "overall":
        return True
    if group_type == "kind_horizon":
        kind, horizon = group["group_value"].split(":", 1)
        return (
            label.get("kind") == kind
            and label.get("horizon") == horizon
        )
    return str(label.get(group_type)) == group["group_value"]


def _linear_quantile(values: Sequence[float], probability: float) -> float:
    _require(values, "EMPTY_BOOTSTRAP_DISTRIBUTION")
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


def _cluster_bootstrap_interval(
    observations: Sequence[tuple[str, float, float]],
    *,
    group_id: str,
    metric: str,
    replicates: int,
) -> tuple[float, float, int, str]:
    by_cluster: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for cluster, weight, value in observations:
        by_cluster[cluster].append((weight, value))
    cluster_ids = sorted(by_cluster)
    _require(cluster_ids, "BOOTSTRAP_HAS_NO_CLUSTER")
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
    cluster_count = len(cluster_ids)
    for replicate in range(replicates):
        selected: list[str] = []
        for draw in range(cluster_count):
            digest = hashlib.sha256(
                (
                    f"{seed_sha256}|replicate={replicate}|draw={draw}"
                ).encode("utf-8")
            ).digest()
            selected.append(
                cluster_ids[
                    int.from_bytes(digest[:8], "big") % cluster_count
                ]
            )
        denominator = math.fsum(
            denominators[cluster] for cluster in selected
        )
        _require(denominator > 0.0, "BOOTSTRAP_ZERO_WEIGHT")
        estimates.append(
            math.fsum(numerators[cluster] for cluster in selected)
            / denominator
        )
    return (
        _linear_quantile(estimates, 0.025),
        _linear_quantile(estimates, 0.975),
        cluster_count,
        seed_sha256,
    )


def _weighted_effect_analysis(
    labels: Sequence[Mapping[str, Any]],
    *,
    plan: Mapping[str, Any],
    label_dataset_binding: Mapping[str, Any],
    formal_gate_passed: bool,
) -> dict[str, Any]:
    _require(
        len(labels) == plan.get("attempt_budget"),
        "ANALYSIS_REQUIRES_COMPLETE_PREREGISTERED_PANEL",
    )
    records = [
        (row, _analysis_metric_values(row))
        for row in labels
    ]
    responses: list[dict[str, Any]] = []
    estimates: list[dict[str, Any]] = []
    for group in _analysis_group_specs():
        group_id = (
            f"{group['group_type']}:{group['group_value']}"
        )
        attempted = [
            row
            for row, _ in records
            if _analysis_group_match(row, group)
        ]
        eligible = [
            (row, metrics)
            for row, metrics in records
            if _analysis_group_match(row, group)
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
        metrics = sorted(
            {
                metric
                for _, row_metrics in eligible
                for metric in row_metrics
            }
        )
        for metric in metrics:
            observations = [
                (
                    str(row["clone_group_id"]),
                    1.0,
                    row_metrics[metric],
                )
                for row, row_metrics in eligible
                if metric in row_metrics
            ]
            if not observations:
                continue
            weights = [weight for _, weight, _ in observations]
            values = [value for _, _, value in observations]
            weighted_denominator = math.fsum(weights)
            weighted_total = math.fsum(
                weight * value
                for _, weight, value in observations
            )
            lower, upper, cluster_count, seed_sha256 = (
                _cluster_bootstrap_interval(
                    observations,
                    group_id=group_id,
                    metric=metric,
                    replicates=BOOTSTRAP_REPLICATES,
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
            "unit": "sealed_causal_descriptor_attempt",
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
    return _self_bound(projection)


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


def _split_groups(labels: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    # Connect clone groups to every *directly affected* raw task.  I1 can
    # directly affect both target and peer bags, so target-only grouping leaks
    # the peer task across splits.  H_system externalities are deliberately not
    # joined: doing so would collapse most of the protected cohort into one
    # component.
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
        target_key = str(row["target_key"])
        baseline = row.get("baseline_affected_bag_outcomes")
        treatment = row.get("treatment_affected_bag_outcomes")
        _require(
            isinstance(baseline, list)
            and baseline
            and isinstance(treatment, list)
            and treatment,
            f"SPLIT_DIRECT_OUTCOME_EVIDENCE_MISSING:{target_key}",
        )
        baseline_tasks = {
            _strict_int(
                outcome.get("task_id"),
                f"split.baseline.task_id:{target_key}",
                minimum=0,
            )
            for outcome in baseline
            if isinstance(outcome, dict)
        }
        treatment_tasks = {
            _strict_int(
                outcome.get("task_id"),
                f"split.treatment.task_id:{target_key}",
                minimum=0,
            )
            for outcome in treatment
            if isinstance(outcome, dict)
        }
        _require(
            all(isinstance(outcome, dict) for outcome in baseline)
            and all(isinstance(outcome, dict) for outcome in treatment)
            and baseline_tasks == treatment_tasks
            and baseline_tasks,
            f"SPLIT_DIRECT_TASK_ID_DRIFT:{target_key}",
        )
        metadata = row.get("offline_sampling_metadata")
        if isinstance(metadata, dict):
            target_task = _strict_int(
                metadata.get("task_id"),
                f"split.target.task_id:{target_key}",
                minimum=0,
            )
            _require(
                target_task in baseline_tasks,
                f"SPLIT_TARGET_TASK_NOT_DIRECTLY_AFFECTED:{target_key}",
            )
        raw_tasks_by_target[target_key] = baseline_tasks
        find(clone)
        for task_id in sorted(baseline_tasks):
            union(clone, f"task:{task_id}")
    components: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in labels:
        components[find(f"clone:{row['clone_group_id']}")].append(row)
    groups: list[dict[str, Any]] = []
    descriptor_split: dict[str, str] = {}
    for root_key, rows in sorted(components.items()):
        component_id = _canonical_sha256(
            sorted(str(row["target_key"]) for row in rows)
        )
        bucket = int(component_id[:8], 16) % 100
        split = "train" if bucket < 70 else "validation" if bucket < 85 else "test"
        keys = sorted(str(row["target_key"]) for row in rows)
        for key in keys:
            descriptor_split[key] = split
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
    contamination = 0
    by_clone: dict[str, set[str]] = defaultdict(set)
    by_raw_task: dict[int, set[str]] = defaultdict(set)
    for row in labels:
        target_key = str(row["target_key"])
        split = descriptor_split[target_key]
        by_clone[str(row["clone_group_id"])].add(split)
        for task_id in raw_tasks_by_target[target_key]:
            by_raw_task[task_id].add(split)
    contamination += sum(len(values) > 1 for values in by_clone.values())
    contamination += sum(
        len(values) > 1 for values in by_raw_task.values()
    )
    return _self_bound(
        {
            "schema": SPLIT_SCHEMA,
            "split_policy": (
                "CONNECTED_COMPONENTS_OF_CLONE_GROUP_AND_RAW_TASK_THEN_"
                "DETERMINISTIC_70_15_15"
            ),
            "split_contamination_count": contamination,
            "group_count": len(groups),
            "groups": groups,
        }
    )


def _pair_rows(labels: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for label in labels:
        delta = label.get("delta_metrics")
        rows.append(
            {
                "target_key": label.get("target_key"),
                "descriptor_id": label.get("descriptor_id"),
                "kind": label.get("kind"),
                "clone_group_id": label.get("clone_group_id"),
                "event_ordinal": label.get("event_ordinal"),
                "horizon": label.get("horizon"),
                "pair_status": label.get("pair_status"),
                "eligible_causal_label": str(
                    label.get("eligible_causal_label", False)
                ).lower(),
                "exclusion_reason": label.get("exclusion_reason", ""),
                "action_changed": str(
                    label.get("action_changed", False)
                ).lower(),
                "same_state_start": str(
                    label.get("same_state_start", False)
                ).lower(),
                "certificate_valid": str(
                    label.get("certificate_valid", False)
                ).lower(),
                "signed_label": label.get("signed_label", ""),
                "delta_completion_mean_seconds": (
                    delta.get("delta_completion_mean_seconds", "")
                    if isinstance(delta, dict)
                    else ""
                ),
                "direct_affected_runtime_bag_ids": label.get(
                    "direct_affected_runtime_bag_ids"
                ),
                "realized_affected_runtime_bag_ids": label.get(
                    "realized_affected_runtime_bag_ids"
                ),
                "externality_runtime_bag_ids": label.get(
                    "externality_runtime_bag_ids"
                ),
                "sampling_stratum_id": (
                    label.get("sampling", {}).get("sampling_stratum_id", "")
                    if isinstance(label.get("sampling"), dict)
                    else ""
                ),
                "N_h": (
                    label.get("sampling", {}).get("N_h", "")
                    if isinstance(label.get("sampling"), dict)
                    else ""
                ),
                "n_h": (
                    label.get("sampling", {}).get("n_h", "")
                    if isinstance(label.get("sampling"), dict)
                    else ""
                ),
                "pi_h": (
                    label.get("sampling", {}).get("pi_h", "")
                    if isinstance(label.get("sampling"), dict)
                    else ""
                ),
                "analysis_weight": (
                    label.get("sampling", {}).get("analysis_weight", "")
                    if isinstance(label.get("sampling"), dict)
                    else ""
                ),
            }
        )
    return rows


PAIR_CSV_FIELDS = (
    "target_key",
    "descriptor_id",
    "kind",
    "clone_group_id",
    "event_ordinal",
    "horizon",
    "pair_status",
    "eligible_causal_label",
    "exclusion_reason",
    "action_changed",
    "same_state_start",
    "certificate_valid",
    "signed_label",
    "delta_completion_mean_seconds",
    "direct_affected_runtime_bag_ids",
    "realized_affected_runtime_bag_ids",
    "externality_runtime_bag_ids",
    "sampling_stratum_id",
    "N_h",
    "n_h",
    "pi_h",
    "analysis_weight",
)


def _dense_h_system_pair(pair: Mapping[str, Any]) -> bool:
    if pair.get("horizon") != "H_system":
        return False
    baseline = pair.get("baseline")
    treatment = pair.get("treatment")
    return bool(
        isinstance(baseline, dict)
        and isinstance(treatment, dict)
        and isinstance(
            baseline.get("raw_bag_sufficient_statistics_sidecar"),
            dict,
        )
        and isinstance(
            treatment.get("raw_bag_sufficient_statistics_sidecar"),
            dict,
        )
        and isinstance(pair.get("cohort_difference_sidecar"), dict)
    )


def _baseline_outcome_hash_rows(
    cohort_sidecar: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows = cohort_sidecar.get("rows")
    _require(
        isinstance(rows, list)
        and cohort_sidecar.get("row_count") == len(rows),
        "COMPACT_BASELINE_COHORT_ROWS_MISSING",
    )
    result: list[dict[str, Any]] = []
    for runtime_id, source in enumerate(rows):
        _require(
            isinstance(source, dict)
            and source.get("runtime_bag_id") == runtime_id
            and _is_sha256(source.get("baseline_outcome_sha256")),
            f"COMPACT_BASELINE_COHORT_ROW_DRIFT:{runtime_id}",
        )
        result.append(
            {
                "runtime_bag_id": runtime_id,
                "baseline_outcome_sha256": source[
                    "baseline_outcome_sha256"
                ],
            }
        )
    return result


def _new_h_system_baseline_reference(
    pair: Mapping[str, Any],
    target: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    binary_sha256: str,
) -> dict[str, Any]:
    _require(
        _dense_h_system_pair(pair),
        "BASELINE_REFERENCE_REQUIRES_DENSE_H_SYSTEM_PAIR",
    )
    baseline = pair["baseline"]
    cohort_sidecar = pair["cohort_difference_sidecar"]
    outcome_hash_rows = _baseline_outcome_hash_rows(cohort_sidecar)
    outcome_hash_inventory = _self_bound(
        {
            "schema": (
                "czr005.g4irsf15."
                "baseline_cohort_outcome_hash_inventory.v1"
            ),
            "row_count": len(outcome_hash_rows),
            "complete_coverage": True,
            "runtime_id_order": "CONTIGUOUS_ZERO_BASED_INPUT_ORDER",
            "rows": outcome_hash_rows,
        }
    )
    return _self_bound(
        {
            "schema": H_SYSTEM_BASELINE_REFERENCE_SCHEMA,
            "source_target_key": target["target_key"],
            "plan_self_sha256": plan["self_sha256"],
            "source_bundle_sha256": plan["source_bundle_sha256"],
            "binary_sha256": binary_sha256,
            "input_runtime_cohort_sha256": plan["protected_inputs"][
                "task"
            ]["input_runtime_cohort_sha256"],
            "h_system_cohort_mapping_sha256": pair[
                "h_system_cohort_mapping_sha256"
            ],
            "raw_bag_mapping_sha256": pair[
                "raw_bag_mapping_sha256"
            ],
            "raw_bag_original_entry_mapping_sha256": pair[
                "raw_bag_original_entry_mapping_sha256"
            ],
            "baseline_terminal_state_sha256": baseline[
                "terminal_state_sha256"
            ],
            "baseline_cohort_outcome_sha256": baseline[
                "cohort_outcome_sha256"
            ],
            "baseline_cohort_metrics": copy.deepcopy(
                baseline["cohort_metrics"]
            ),
            "baseline_raw_bag_cohort_metrics": copy.deepcopy(
                baseline["raw_bag_cohort_metrics"]
            ),
            "baseline_raw_bag_sufficient_statistics_sidecar": (
                copy.deepcopy(
                    baseline[
                        "raw_bag_sufficient_statistics_sidecar"
                    ]
                )
            ),
            "baseline_outcome_hash_inventory": outcome_hash_inventory,
        }
    )


def _require_same_h_system_baseline(
    pair: Mapping[str, Any],
    reference: Mapping[str, Any],
) -> None:
    baseline = pair["baseline"]
    sidecar = baseline["raw_bag_sufficient_statistics_sidecar"]
    hashes = _baseline_outcome_hash_rows(
        pair["cohort_difference_sidecar"]
    )
    inventory = reference["baseline_outcome_hash_inventory"]
    _require(
        _is_sha256(pair.get("h_system_cohort_mapping_sha256"))
        and _is_sha256(pair.get("raw_bag_mapping_sha256"))
        and _is_sha256(
            pair.get("raw_bag_original_entry_mapping_sha256")
        )
        and _is_sha256(baseline.get("terminal_state_sha256"))
        and _is_sha256(baseline.get("cohort_outcome_sha256"))
        and _is_sha256(sidecar.get("content_sha256"))
        and pair.get("h_system_cohort_mapping_sha256")
        == reference.get("h_system_cohort_mapping_sha256")
        and pair.get("raw_bag_mapping_sha256")
        == reference.get("raw_bag_mapping_sha256")
        and pair.get("raw_bag_original_entry_mapping_sha256")
        == reference.get("raw_bag_original_entry_mapping_sha256")
        and baseline.get("terminal_state_sha256")
        == reference.get("baseline_terminal_state_sha256")
        and baseline.get("cohort_outcome_sha256")
        == reference.get("baseline_cohort_outcome_sha256")
        and baseline.get("cohort_metrics")
        == reference.get("baseline_cohort_metrics")
        and baseline.get("raw_bag_cohort_metrics")
        == reference.get("baseline_raw_bag_cohort_metrics")
        and sidecar.get("content_sha256")
        == reference[
            "baseline_raw_bag_sufficient_statistics_sidecar"
        ].get("content_sha256")
        and hashes == inventory.get("rows"),
        "H_SYSTEM_BASELINE_REFERENCE_DRIFT",
    )


def _raw_bag_sidecar_logical_content_sha256(
    sidecar: Mapping[str, Any],
) -> str:
    rows = sidecar.get("rows")
    _require(
        isinstance(rows, list)
        and sidecar.get("row_count") == len(rows),
        "RAW_BAG_LOGICAL_CONTENT_ROWS_MISSING",
    )
    fields: list[tuple[str, str, Any]] = [
        ("schema", "s", sidecar.get("schema")),
        ("row_count", "i", sidecar.get("row_count")),
        (
            "expected_raw_bag_count",
            "i",
            sidecar.get("expected_raw_bag_count"),
        ),
        (
            "selected_segment_count",
            "i",
            sidecar.get("selected_segment_count"),
        ),
        ("complete_coverage", "b", sidecar.get("complete_coverage")),
        ("task_id_order", "s", sidecar.get("task_id_order")),
        (
            "runtime_segment_mapping_sha256",
            "s",
            sidecar.get("runtime_segment_mapping_sha256"),
        ),
        (
            "raw_bag_mapping_sha256",
            "s",
            sidecar.get("raw_bag_mapping_sha256"),
        ),
        (
            "raw_bag_original_entry_mapping_sha256",
            "s",
            sidecar.get(
                "raw_bag_original_entry_mapping_sha256"
            ),
        ),
    ]
    previous_task_id = -1
    for index, row in enumerate(rows):
        _require(
            isinstance(row, dict)
            and isinstance(row.get("task_id"), int)
            and not isinstance(row.get("task_id"), bool)
            and row["task_id"] > previous_task_id
            and _is_sha256(row.get("row_sha256")),
            f"RAW_BAG_LOGICAL_CONTENT_ROW_DRIFT:{index}",
        )
        previous_task_id = row["task_id"]
        fields.append(("row_sha256", "s", row["row_sha256"]))
    return _canonical_fields_sha256(fields)


def _compact_h_system_pair(
    pair: Mapping[str, Any],
    target: Mapping[str, Any],
    reference: Mapping[str, Any],
) -> dict[str, Any]:
    _require_same_h_system_baseline(pair, reference)
    compact = copy.deepcopy(dict(pair))
    compact["target_key"] = target["target_key"]
    baseline = compact["baseline"]
    treatment = compact["treatment"]
    baseline_sidecar = pair["baseline"][
        "raw_bag_sufficient_statistics_sidecar"
    ]
    treatment_sidecar = pair["treatment"][
        "raw_bag_sufficient_statistics_sidecar"
    ]
    baseline_rows = baseline_sidecar["rows"]
    treatment_rows = treatment_sidecar["rows"]
    _require(
        len(baseline_rows) == len(treatment_rows),
        "RAW_BAG_SPARSE_OVERLAY_CARDINALITY_DRIFT",
    )
    changed_rows: list[dict[str, Any]] = []
    changed_task_ids: list[int] = []
    for left, right in zip(
        baseline_rows, treatment_rows, strict=True
    ):
        _require(
            left.get("task_id") == right.get("task_id")
            and left.get("runtime_bag_ids")
            == right.get("runtime_bag_ids")
            and left.get("runtime_id_mapping_sha256")
            == right.get("runtime_id_mapping_sha256"),
            "RAW_BAG_SPARSE_OVERLAY_MAPPING_DRIFT",
        )
        if left.get("row_sha256") != right.get("row_sha256"):
            changed_task_ids.append(int(right["task_id"]))
            changed_rows.append(copy.deepcopy(right))
    raw_overlay = _self_bound(
        {
            "schema": RAW_BAG_SPARSE_OVERLAY_SCHEMA,
            "storage": "SPARSE_OVER_GLOBAL_BASELINE",
            "baseline_reference_self_sha256": reference["self_sha256"],
            "baseline_content_sha256": baseline_sidecar[
                "content_sha256"
            ],
            "logical_content_sha256": treatment_sidecar[
                "content_sha256"
            ],
            "row_count": treatment_sidecar["row_count"],
            "expected_raw_bag_count": treatment_sidecar[
                "expected_raw_bag_count"
            ],
            "selected_segment_count": treatment_sidecar[
                "selected_segment_count"
            ],
            "complete_coverage": treatment_sidecar[
                "complete_coverage"
            ],
            "task_id_order": treatment_sidecar["task_id_order"],
            "runtime_segment_mapping_sha256": treatment_sidecar[
                "runtime_segment_mapping_sha256"
            ],
            "raw_bag_mapping_sha256": treatment_sidecar[
                "raw_bag_mapping_sha256"
            ],
            "raw_bag_original_entry_mapping_sha256": (
                treatment_sidecar[
                    "raw_bag_original_entry_mapping_sha256"
                ]
            ),
            "changed_row_count": len(changed_rows),
            "changed_task_ids": changed_task_ids,
            "rows": changed_rows,
        }
    )
    cohort_sidecar = pair["cohort_difference_sidecar"]
    changed_runtime_ids = [
        int(row["runtime_bag_id"])
        for row in cohort_sidecar["rows"]
        if row["outcome_changed"]
    ]
    cohort_overlay = _self_bound(
        {
            "schema": COHORT_DIFFERENCE_SPARSE_OVERLAY_SCHEMA,
            "storage": "SPARSE_OVER_GLOBAL_BASELINE",
            "baseline_reference_self_sha256": reference["self_sha256"],
            "logical_schema": cohort_sidecar["schema"],
            "logical_content_sha256": cohort_sidecar[
                "content_sha256"
            ],
            "row_count": cohort_sidecar["row_count"],
            "changed_count": cohort_sidecar["changed_count"],
            "complete_coverage": cohort_sidecar[
                "complete_coverage"
            ],
            "runtime_id_order": cohort_sidecar[
                "runtime_id_order"
            ],
            "changed_runtime_bag_ids": changed_runtime_ids,
            "realized_outcome_deltas_sha256": pair[
                "realized_outcome_deltas_sha256"
            ],
        }
    )
    baseline["raw_bag_sufficient_statistics_sidecar"] = {
        "storage": "GLOBAL_BASELINE_REFERENCE",
        "baseline_reference_self_sha256": reference["self_sha256"],
        "logical_content_sha256": baseline_sidecar[
            "content_sha256"
        ],
    }
    treatment["raw_bag_sufficient_statistics_sidecar"] = raw_overlay
    compact["cohort_difference_sidecar"] = cohort_overlay
    compact["compact_storage"] = (
        "GLOBAL_BASELINE_PLUS_SPARSE_TREATMENT_OVERLAYS"
    )
    return compact


def _compact_pair_for_publication(
    pair: Mapping[str, Any],
    target: Mapping[str, Any],
    reference: Mapping[str, Any] | None,
    *,
    plan: Mapping[str, Any],
    binary_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if not _dense_h_system_pair(pair):
        compact = copy.deepcopy(dict(pair))
        compact["target_key"] = target["target_key"]
        compact["compact_storage"] = "INLINE_NATIVE_SMALL_EVIDENCE"
        return compact, reference
    if reference is None:
        reference = _new_h_system_baseline_reference(
            pair,
            target,
            plan=plan,
            binary_sha256=binary_sha256,
        )
    return (
        _compact_h_system_pair(pair, target, reference),
        dict(reference),
    )


def _compact_native_payload_attestation(
    native: Mapping[str, Any],
) -> dict[str, Any]:
    return _self_bound(
        {
            "schema": COMPACT_NATIVE_ATTESTATION_SCHEMA,
            "native_payload_schema": native["schema"],
            "evidence_scope": native["evidence_scope"],
            "formal_pass_claimed": native["formal_pass_claimed"],
            "protected_full_1x_shape": native[
                "protected_full_1x_shape"
            ],
            "h_system_cohort_policy": native[
                "h_system_cohort_policy"
            ],
            "input_request_count": native["input_request_count"],
            "raw_bag_count": native["raw_bag_count"],
            "input_runtime_cohort_sha256": native[
                "input_runtime_cohort_sha256"
            ],
            "h_system_cohort_mapping_sha256": native[
                "h_system_cohort_mapping_sha256"
            ],
            "raw_bag_mapping_sha256": native[
                "raw_bag_mapping_sha256"
            ],
            "raw_bag_original_entry_mapping_sha256": native[
                "raw_bag_original_entry_mapping_sha256"
            ],
            "frozen_controls": copy.deepcopy(
                native["frozen_controls"]
            ),
            "target_count": native["target_count"],
            "action_changing_pair_count": native[
                "action_changing_pair_count"
            ],
            "applied_action_changing_pair_count": native[
                "applied_action_changing_pair_count"
            ],
            "false_positive_pair_count": native[
                "false_positive_pair_count"
            ],
            "complete_action_changing_h_bag_count": native[
                "complete_action_changing_h_bag_count"
            ],
            "applied_action_changing_h_system_count": native[
                "applied_action_changing_h_system_count"
            ],
            "complete_h_system_hard_gate_pass_count": native[
                "complete_h_system_hard_gate_pass_count"
            ],
            "h_system_pair_count": native[
                "h_system_pair_count"
            ],
        }
    )


def _hydrate_compact_pair(
    compact_pair: Mapping[str, Any],
    reference: Mapping[str, Any] | None,
    *,
    expected_target_key: str,
) -> dict[str, Any]:
    pair = copy.deepcopy(dict(compact_pair))
    storage = pair.pop("compact_storage", None)
    _require(
        pair.pop("target_key", None) == expected_target_key,
        "COMPACT_PAIR_TARGET_KEY_DRIFT",
    )
    if storage == "INLINE_NATIVE_SMALL_EVIDENCE":
        return pair
    _require(
        storage
        == "GLOBAL_BASELINE_PLUS_SPARSE_TREATMENT_OVERLAYS"
        and isinstance(reference, Mapping),
        "COMPACT_H_SYSTEM_BASELINE_REFERENCE_MISSING",
    )
    _validate_self_bound(reference, "h_system_baseline_reference")
    baseline = pair.get("baseline")
    treatment = pair.get("treatment")
    _require(
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
    _require(
        isinstance(baseline_binding, dict)
        and baseline_binding.get("storage")
        == "GLOBAL_BASELINE_REFERENCE"
        and isinstance(raw_overlay, dict)
        and isinstance(cohort_overlay, dict),
        "COMPACT_H_SYSTEM_OVERLAY_MISSING",
    )
    _validate_self_bound(raw_overlay, "raw_bag_sparse_overlay")
    _validate_self_bound(
        cohort_overlay, "cohort_difference_sparse_overlay"
    )
    reference_sha = reference["self_sha256"]
    _require(
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
    _require(
        _is_sha256(pair.get("h_system_cohort_mapping_sha256"))
        and _is_sha256(pair.get("raw_bag_mapping_sha256"))
        and _is_sha256(
            pair.get("raw_bag_original_entry_mapping_sha256")
        )
        and _is_sha256(baseline.get("terminal_state_sha256"))
        and _is_sha256(baseline.get("cohort_outcome_sha256"))
        and isinstance(reference_sidecar, dict)
        and _is_sha256(reference_sidecar.get("content_sha256"))
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
    _require(
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
    _require(
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
        _require(
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
        _require(
            treatment_sidecar.get(field) == raw_overlay.get(field),
            f"COMPACT_RAW_OVERLAY_TOP_LEVEL_DRIFT:{field}",
        )
    _require(
        _raw_bag_sidecar_logical_content_sha256(
            treatment_sidecar
        )
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
    _require(
        isinstance(inventory, dict),
        "COMPACT_BASELINE_HASH_INVENTORY_MISSING",
    )
    _validate_self_bound(inventory, "baseline_hash_inventory")
    baseline_hash_rows = inventory.get("rows")
    realized_rows = pair.get("realized_outcome_deltas")
    _require(
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
    _require(
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
        _require(
            isinstance(baseline_hash_row, dict)
            and baseline_hash_row.get("runtime_bag_id")
            == runtime_id
            and _is_sha256(
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
            _require(
                hashlib.sha256(
                    _causal_outcome_payload(realized["baseline"])
                ).hexdigest()
                == baseline_sha,
                f"COMPACT_REALIZED_BASELINE_HASH_DRIFT:{runtime_id}",
            )
            treatment_sha = hashlib.sha256(
                _causal_outcome_payload(realized["treatment"])
            ).hexdigest()
            _require(
                treatment_sha != baseline_sha,
                f"COMPACT_REALIZED_ROW_NOT_CHANGED:{runtime_id}",
            )
        changed = treatment_sha != baseline_sha
        row_sha = _canonical_fields_sha256(
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
    logical_content_sha = _canonical_fields_sha256(digest_fields)
    _require(
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


def _compact_label_projection(
    full_label: Mapping[str, Any],
    pair_evidence_sha256: str,
) -> dict[str, Any]:
    _require(
        _is_sha256(pair_evidence_sha256),
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
        _canonical_sha256(certificate)
        if isinstance(certificate, dict)
        else None
    )
    label["label_sha256"] = _canonical_sha256(label)
    return label


def _partition_compact_evidence_rows(
    rows: Sequence[Mapping[str, Any]],
) -> list[list[dict[str, Any]]]:
    """Keep every dense H_system pair in its own publishable blob."""
    chunks: list[list[dict[str, Any]]] = []
    small: list[dict[str, Any]] = []
    for source in rows:
        row = copy.deepcopy(dict(source))
        pair = row.get("pair")
        dense = (
            isinstance(pair, dict)
            and pair.get("compact_storage")
            == "GLOBAL_BASELINE_PLUS_SPARSE_TREATMENT_OVERLAYS"
        )
        if dense:
            if small:
                chunks.append(small)
                small = []
            chunks.append([row])
        else:
            small.append(row)
    if small:
        chunks.append(small)
    _require(
        all(
            sum(
                isinstance(row.get("pair"), dict)
                and row["pair"].get("compact_storage")
                == (
                    "GLOBAL_BASELINE_PLUS_"
                    "SPARSE_TREATMENT_OVERLAYS"
                )
                for row in chunk
            )
            <= 1
            for chunk in chunks
        ),
        "COMPACT_EVIDENCE_DENSE_PAIR_PARTITION_DRIFT",
    )
    return chunks


def _collect_shards(
    root: Path,
    campaign: str,
    plan: Mapping[str, Any],
    *,
    pilot_round: int = 1,
    protected: Mapping[str, Any],
    build_binding: Mapping[str, Any],
    binary_sha256: str,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any] | None,
]:
    target_by_key = {
        str(row["target_key"]): row
        for shard in plan["shards"]
        for row in shard["targets"]
    }
    labels: list[dict[str, Any]] = []
    evidence_bindings: list[dict[str, Any]] = []
    run_state_attestations: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    baseline_reference: dict[str, Any] | None = None
    evidence_index = 0
    for shard in plan["shards"]:
        index = int(shard["shard_index"])
        path = root / _shard_output_path(
            campaign, index, pilot_round=pilot_round
        )
        _require(
            path.is_file(),
            f"PREREGISTERED_SHARD_NOT_COMPLETE:{index}",
        )
        value = _load_zstd_json(path)
        shard_byte_count = path.stat().st_size
        _validate_completed_shard(
            value,
            root=root,
            campaign=campaign,
            pilot_round=pilot_round,
            plan=plan,
            shard=shard,
            protected=protected,
            build_binding=build_binding,
            binary_sha256=binary_sha256,
        )
        native = value.get("native_payload")
        native_pairs = native.get("pairs")
        native_attestation = _compact_native_payload_attestation(
            native
        )
        expected_keys = list(shard["target_keys"])
        evidence_rows: list[dict[str, Any]] = []
        for pair, key in zip(native_pairs, expected_keys, strict=True):
            target = target_by_key[str(key)]
            _require(key not in seen_keys, f"DUPLICATE_EXECUTED_TARGET:{key}")
            seen_keys.add(str(key))
            _require(
                pair.get("descriptor_id")
                == target.get("descriptor_id")
                and pair.get("kind") == target.get("kind")
                and pair.get("event_ordinal")
                == target.get("event_ordinal")
                and pair.get("horizon") == target.get("horizon")
                and pair.get("protected_full_1x_shape") is True,
                f"COMPACT_PAIR_TARGET_IDENTITY_DRIFT:{key}",
            )
            full_label = _label_pair(pair, target)
            compact_pair, baseline_reference = (
                _compact_pair_for_publication(
                    pair,
                    target,
                    baseline_reference,
                    plan=plan,
                    binary_sha256=binary_sha256,
                )
            )
            hydrated_pair = _hydrate_compact_pair(
                compact_pair,
                baseline_reference,
                expected_target_key=str(key),
            )
            _require(
                hydrated_pair == dict(pair),
                f"COMPACT_PAIR_NOT_LOSSLESS:{key}",
            )
            _require(
                _label_pair(hydrated_pair, target) == full_label,
                f"COMPACT_PAIR_LABEL_DERIVATION_DRIFT:{key}",
            )
            pair_evidence_sha256 = _canonical_sha256(compact_pair)
            evidence_rows.append(
                {
                    "target_key": key,
                    "pair_evidence_sha256": pair_evidence_sha256,
                    "pair": compact_pair,
                }
            )
            labels.append(
                _compact_label_projection(
                    full_label, pair_evidence_sha256
                )
            )
        for chunk in _partition_compact_evidence_rows(
            evidence_rows
        ):
            chunk_keys = [row["target_key"] for row in chunk]
            relative = _compact_evidence_path(
                campaign,
                evidence_index,
                pilot_round=pilot_round,
            )
            evidence_value = _atomic_zstd_json(
                root / relative,
                {
                    "schema": COMPACT_EVIDENCE_SCHEMA,
                    "campaign": campaign,
                    "pilot_round": (
                        pilot_round if campaign == "pilot" else None
                    ),
                    "evidence_index": evidence_index,
                    "source_shard_index": index,
                    "plan_self_sha256": plan["self_sha256"],
                    "source_shard_sha256": shard["shard_sha256"],
                    "binary_sha256": binary_sha256,
                    "source_run_state_sha256": _file_sha256(path),
                    "source_run_state_self_sha256": value[
                        "self_sha256"
                    ],
                    "source_native_payload_attestation": (
                        native_attestation
                    ),
                    "target_keys": chunk_keys,
                    "pair_count": len(chunk),
                    "dense_h_system_pair_count": sum(
                        row["pair"].get("compact_storage")
                        == (
                            "GLOBAL_BASELINE_PLUS_"
                            "SPARSE_TREATMENT_OVERLAYS"
                        )
                        for row in chunk
                    ),
                    "pairs": chunk,
                },
            )
            evidence_path = root / relative
            evidence_byte_count = _publishable_byte_count(
                evidence_path,
                f"{campaign}_compact_evidence_{evidence_index}",
            )
            evidence_bindings.append(
                {
                    "path": relative.as_posix(),
                    "sha256": _file_sha256(evidence_path),
                    "byte_count": evidence_byte_count,
                    "self_sha256": evidence_value["self_sha256"],
                    "evidence_index": evidence_index,
                    "source_shard_index": index,
                    "source_native_payload_attestation_self_sha256": (
                        native_attestation["self_sha256"]
                    ),
                    "target_count": len(chunk),
                    "target_keys": chunk_keys,
                    "dense_h_system_pair_count": evidence_value[
                        "dense_h_system_pair_count"
                    ],
                    "binary_sha256": binary_sha256,
                }
            )
            evidence_index += 1
        run_state_attestations.append(
            {
                "shard_index": index,
                "sha256": _file_sha256(path),
                "byte_count": shard_byte_count,
                "self_sha256": value["self_sha256"],
                "target_count": len(native_pairs),
                "binary_sha256": value["binary"]["sha256_before"],
            }
        )
    _require(
        len(run_state_attestations) == len(plan["shards"])
        and [
            binding["evidence_index"]
            for binding in evidence_bindings
        ]
        == list(range(len(evidence_bindings)))
        and [
            binding["shard_index"]
            for binding in run_state_attestations
        ]
        == list(range(len(plan["shards"])))
        and seen_keys == set(target_by_key),
        "PREREGISTERED_PANEL_NOT_EXECUTED_IN_FULL",
    )
    return (
        labels,
        evidence_bindings,
        run_state_attestations,
        baseline_reference,
    )


def _pilot_false_positive_evidence(
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
    projection["evidence_sha256"] = _canonical_sha256(projection)
    return projection


def _write_report(
    path: Path,
    *,
    campaign: str,
    summary: Mapping[str, Any],
) -> None:
    lines = [
        f"# G4IRSF15 {campaign} causal campaign",
        "",
        f"- Status: `{summary['status']}`",
        f"- Attempted pairs: `{summary['attempted_pair_count']}`",
        f"- Eligible complete action-changing labels: `{summary['causal_label_count']}`",
        f"- Complete H_system pairs: `{summary['h_system_complete_count']}`",
        f"- Hard-gate failures: `{summary['hard_gate_fail_count']}`",
        f"- Exact same-state rate: `{summary['clone_fidelity']}`",
        f"- Action-changed rate among admitted labels: `{summary['action_changed_rate']}`",
        f"- Future/global leakage count: `{summary['future_leakage_count']}`",
        f"- Remaining preregistered attempts: `{summary['remaining_attempt_count']}`",
        "",
        "Signed outcomes are retained in full; neutral and harmful rows were not filtered.",
        "",
        "H_system uses the fixed full protected cohort of 43,603 runtime segment IDs. "
        "H_bag uses only the directly affected live bag set and does not claim that "
        "system-wide externalities are observable.",
    ]
    if campaign == "formal":
        lines.extend(
            [
                "",
                "Weighted effect artifact: "
                f"`{WEIGHTED_EFFECT_DATASET_PATH.as_posix()}`.",
                "",
                "Population effect identified: `false`. Every horizon and "
                "mixed-horizon summary is descriptive because the horizon-"
                "assignment probability is not modeled; recorded panel "
                "fractions are diagnostic only. Deterministic clone-group "
                "bootstrap intervals quantify realized-panel sensitivity.",
            ]
        )
    _atomic_write(path, ("\n".join(lines) + "\n").encode("utf-8"))


def finalize_campaign(
    *,
    root: Path,
    campaign: str,
    binary: Path,
    build_manifest: Path,
    orchestrator_profiles: Sequence[Path],
    pilot_round: int = 1,
) -> dict[str, Any]:
    _require(
        campaign == "pilot" or pilot_round == 1,
        "FORMAL_CAMPAIGN_HAS_NO_ROUND_NAMESPACE",
    )
    _assert_repository_safety(root)
    protected = _protected_inputs(root)
    resolved_binary = binary.resolve(strict=True)
    resolved_build_manifest = (
        build_manifest
        if build_manifest.is_absolute()
        else root / build_manifest
    ).resolve(strict=True)
    plan_path = root / _plan_path(campaign, pilot_round=pilot_round)
    plan = _load_json(plan_path)
    _validate_plan(plan, campaign)
    _require(
        _source_identity(root)["source_bundle_sha256"]
        == plan["source_bundle_sha256"],
        "FINALIZE_SOURCE_BUNDLE_DRIFT",
    )
    current_binary_sha = _file_sha256(resolved_binary)
    _require(
        current_binary_sha == plan["binary"]["sha256_before"],
        "FINALIZE_BINARY_SHA256_DRIFT",
    )
    build_binding = _validate_build_manifest(
        root=root,
        binary=resolved_binary,
        manifest_path=resolved_build_manifest,
    )
    _require(
        build_binding == plan.get("exact_binary_build_manifest"),
        "FINALIZE_BUILD_MANIFEST_DIFFERS_FROM_PLAN",
    )
    orchestrator_profile_set = _validate_orchestrator_profile_set(
        root=root,
        profile_paths=orchestrator_profiles,
        campaign=campaign,
        pilot_round=pilot_round,
        plan=plan,
        plan_path=plan_path,
        binary=resolved_binary,
        build_manifest=resolved_build_manifest,
        build_binding=build_binding,
    )
    (
        labels,
        evidence_bindings,
        run_state_shard_attestations,
        baseline_reference,
    ) = _collect_shards(
        root,
        campaign,
        plan,
        pilot_round=pilot_round,
        protected=protected,
        build_binding=build_binding,
        binary_sha256=current_binary_sha,
    )
    _require(
        campaign == "formal" or baseline_reference is None,
        "PILOT_MUST_NOT_PUBLISH_H_SYSTEM_BASELINE",
    )
    dense_h_system_evidence_count = sum(
        row.get("horizon") == "H_system"
        and row.get("action_changed") is True
        for row in labels
    )
    _require(
        (baseline_reference is not None)
        is (dense_h_system_evidence_count > 0),
        "H_SYSTEM_BASELINE_OPTIONALITY_DRIFT",
    )
    baseline_reference_binding: dict[str, Any] | None = None
    if baseline_reference is not None:
        published_reference = _atomic_zstd_json(
            root / H_SYSTEM_BASELINE_REFERENCE_PATH,
            baseline_reference,
        )
        baseline_reference_byte_count = _publishable_byte_count(
            root / H_SYSTEM_BASELINE_REFERENCE_PATH,
            "h_system_baseline_reference",
        )
        baseline_reference_binding = {
            "path": H_SYSTEM_BASELINE_REFERENCE_PATH.as_posix(),
            "sha256": _file_sha256(
                root / H_SYSTEM_BASELINE_REFERENCE_PATH
            ),
            "byte_count": baseline_reference_byte_count,
            "self_sha256": published_reference["self_sha256"],
            "source_target_key": published_reference[
                "source_target_key"
            ],
        }
    run_state_attestation = _self_bound(
        {
            "schema": (
                "czr005.g4irsf15."
                "ephemeral_run_state_attestation.v1"
            ),
            "retention": "EPHEMERAL_NOT_REQUIRED_FOR_VALIDATION",
            "committed_to_git": False,
            "shard_count": len(run_state_shard_attestations),
            "shards": run_state_shard_attestations,
        }
    )
    eligible = [row for row in labels if row["eligible_causal_label"]]
    by_kind = Counter(str(row["kind"]) for row in eligible)
    signed_counts = Counter(str(row.get("signed_label")) for row in eligible)
    labels_per_clone = Counter(
        str(row["clone_group_id"]) for row in eligible
    )
    h_system = [
        row
        for row in eligible
        if row["horizon"] == "H_system"
    ]
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
    horizon_blocked_count = sum(
        row.get("action_changed") is True
        and row.get("horizon_complete") is not True
        for row in labels
    )
    evidence_incomplete_count = sum(
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
    clone_comparable = [
        row for row in labels if row.get("action_changed") is True
    ]
    same_state_count = sum(
        row.get("same_state_start") is True for row in clone_comparable
    )
    action_changed_count = sum(
        row.get("action_changed") is True for row in eligible
    )
    attempted = len(labels)
    remaining = int(plan["attempt_budget"]) - attempted
    clone_fidelity = (
        same_state_count / len(clone_comparable)
        if clone_comparable
        else 0.0
    )
    action_rate = (
        action_changed_count / len(eligible) if eligible else 0.0
    )
    if campaign == "pilot":
        round_false_positive_evidence = _pilot_false_positive_evidence(
            labels
        )
        round_by_kind = Counter(by_kind)
        cumulative_by_kind = Counter(by_kind)
        cumulative_signed_counts = Counter(signed_counts)
        cumulative_attempted = attempted
        cumulative_hard_gate_fail = hard_gate_fail
        prior_result: dict[str, Any] | None = None
        if pilot_round == 2:
            prior_binding = plan.get("prior_pilot_result")
            _require(
                isinstance(prior_binding, dict),
                "PILOT_R2_PRIOR_RESULT_BINDING_MISSING",
            )
            prior_path = root / Path(str(prior_binding["path"]))
            prior_result = _load_json(prior_path)
            _validate_self_bound(prior_result, "pilot_r2_prior_result")
            _require(
                _file_sha256(prior_path) == prior_binding.get("sha256")
                and prior_result.get("self_sha256")
                == prior_binding.get("self_sha256")
                and prior_result.get("status") == "RESAMPLE_REQUIRED",
                "PILOT_R2_PRIOR_RESULT_BINDING_DRIFT",
            )
            prior_complete = prior_result.get("complete_by_kind")
            _require(
                isinstance(prior_complete, dict),
                "PILOT_R1_COMPLETE_BY_KIND_MISSING",
            )
            attempted_kinds = set(plan.get("active_kinds", []))
            cumulative_by_kind = Counter(
                {
                    kind: (
                        round_by_kind[kind]
                        if kind in attempted_kinds
                        else int(prior_complete.get(kind, 0))
                    )
                    for kind in KINDS
                }
            )
            cumulative_signed_counts.update(
                prior_result.get("signed_label_counts", {})
            )
            cumulative_attempted += int(
                prior_result.get("attempted_pair_count", 0)
            )
            cumulative_hard_gate_fail += int(
                prior_result.get("hard_gate_fail_count", 0)
            )
        per_kind_pass = {
            kind: cumulative_by_kind[kind] >= PILOT_MIN_COMPLETE_PER_KIND
            for kind in KINDS
        }
        active_supported_kinds = [
            kind for kind in KINDS if per_kind_pass[kind]
        ]
        expected_round_attempts = int(plan["attempt_budget"])
        passed_all = (
            attempted == expected_round_attempts
            and all(per_kind_pass.values())
            and cumulative_hard_gate_fail == 0
            and clone_fidelity == 1.0
        )
        passed_with_blocker = (
            pilot_round == 2
            and attempted == expected_round_attempts
            and len(active_supported_kinds) >= 2
            and cumulative_hard_gate_fail == 0
            and clone_fidelity == 1.0
        )
        passed = passed_all or passed_with_blocker
        exhausted = attempted == int(plan["attempt_budget"])
        status = (
            "SAFETY_HARD_GATE_BLOCKED"
            if exhausted and cumulative_hard_gate_fail > 0
            else "CLONE_FIDELITY_BLOCKED"
            if exhausted and clone_fidelity < 1.0
            else "PASS_PILOT"
            if passed_all
            else "PASS_PILOT_WITH_BLOCKED_KINDS"
            if passed_with_blocker
            else "INTERVENTION_KIND_BLOCKED"
            if exhausted and pilot_round == 2
            else "RESAMPLE_REQUIRED"
            if exhausted
            else "INCOMPLETE_PILOT_SHARDS"
        )
        by_kind = cumulative_by_kind
        signed_counts = cumulative_signed_counts
        hard_gate_fail = cumulative_hard_gate_fail
    else:
        split = _split_groups(eligible)
        formal_gate = plan.get("formal_gate")
        _require(isinstance(formal_gate, dict), "FORMAL_GATE_MISSING")
        active_kinds = list(formal_gate.get("active_kinds", []))
        causal_min = _strict_int(
            formal_gate.get("causal_label_count_min"),
            "formal_gate.causal_label_count_min",
            minimum=1,
        )
        passed = (
            len(active_kinds) >= 2
            and len(eligible) >= causal_min
            and len(h_system)
            >= int(formal_gate["h_system_complete_min"])
            and all(
                by_kind[kind] >= FORMAL_MIN_LABELS_PER_KIND
                for kind in active_kinds
            )
            and all(
                by_kind[kind] == 0
                for kind in KINDS
                if kind not in active_kinds
            )
            and hard_gate_fail == 0
            and clone_fidelity == 1.0
            and action_rate == 1.0
            and future_leakage == 0
            and split["split_contamination_count"] == 0
        )
        exhausted = attempted == int(plan["attempt_budget"])
        status = (
            "PASS_CAUSAL_GATE"
            if passed
            else "BLOCKED_DESCRIPTOR_BUDGET_EXHAUSTED"
            if exhausted
            else "INCOMPLETE_MORE_SHARDS_REQUIRED"
        )
    summary = {
        "status": status,
        "formal_pass_claimed": campaign == "formal" and passed,
        "attempted_pair_count": attempted,
        "remaining_attempt_count": remaining,
        "preregistered_panel_complete": (
            attempted == int(plan["attempt_budget"])
            and len(run_state_shard_attestations)
            == len(plan["shards"])
        ),
        "executed_shard_indices": [
            binding["shard_index"]
            for binding in run_state_shard_attestations
        ],
        "outcome_dependent_early_stop": False,
        "causal_label_count": len(eligible),
        "complete_by_kind": {
            kind: int(by_kind[kind]) for kind in KINDS
        },
        "signed_label_counts": dict(sorted(signed_counts.items())),
        "unique_clone_group_count": len(labels_per_clone),
        "labels_per_clone_group_max": max(
            labels_per_clone.values(), default=0
        ),
        "h_bag_or_stronger_complete_count": len(eligible),
        "h_system_complete_count": len(h_system),
        "h_system_dense_evidence_count": (
            dense_h_system_evidence_count
        ),
        "h_system_unique_clone_group_count": len(
            {str(row["clone_group_id"]) for row in h_system}
        ),
        "action_changed_count": action_changed_count,
        "action_changed_rate": action_rate,
        "hard_gate_fail_count": hard_gate_fail,
        "action_changed_hard_gate_fail_count": hard_gate_fail,
        "safety_hard_gate_fail_count": safety_hard_gate_fail,
        "horizon_blocked_count": horizon_blocked_count,
        "evidence_incomplete_count": evidence_incomplete_count,
        "clone_fidelity": clone_fidelity,
        "future_leakage_count": future_leakage,
        "active_kinds": (
            active_supported_kinds
            if campaign == "pilot"
            else list(plan["formal_gate"]["active_kinds"])
        ),
        "blocked_kinds": (
            [
                kind
                for kind in KINDS
                if kind not in active_supported_kinds
            ]
            if campaign == "pilot"
            else list(plan["formal_gate"]["blocked_kinds"])
        ),
    }
    if campaign == "pilot":
        summary["round_attempted_pair_count"] = attempted
        summary["cumulative_attempted_pair_count"] = cumulative_attempted
        summary["round_complete_by_kind"] = dict(
            sorted(round_by_kind.items())
        )
        summary["kind_status"] = {
            kind: (
                "SAFETY_BLOCKED"
                if hard_gate_fail_by_kind[kind] > 0
                else "PASS"
                if kind in active_supported_kinds
                else "INTERVENTION_KIND_BLOCKED"
                if pilot_round == 2
                else "RESAMPLE_REQUIRED"
            )
            for kind in KINDS
        }
        summary["round_false_positive_evidence"] = (
            round_false_positive_evidence
        )
    rows = _pair_rows(labels)
    if campaign == "pilot":
        pilot_table_path = (
            PILOT_TABLE_PATH
            if pilot_round == 1
            else Path(
                "outputs/tables/g4irsf15_pilot_causal_pairs_round2.csv"
            )
        )
        runner_report_path = (
            RUNNER_REPORT_PATH
            if pilot_round == 1
            else Path(
                "outputs/reports/"
                "g4irsf15_intervention_runner_validation_round2.md"
            )
        )
        pilot_result_path = (
            Path("artifacts/datasets/g4irsf15_pilot_causal_result.json")
            if pilot_round == 1
            else Path(
                "artifacts/datasets/"
                "g4irsf15_pilot_causal_result_round2.json"
            )
        )
        _atomic_write(
            root / pilot_table_path, _csv_bytes(rows, PAIR_CSV_FIELDS)
        )
        pilot_table_byte_count = _publishable_byte_count(
            root / pilot_table_path, f"pilot_r{pilot_round}_table"
        )
        _write_report(
            root / runner_report_path,
            campaign=campaign,
            summary=summary,
        )
        pilot_report_byte_count = _publishable_byte_count(
            root / runner_report_path, f"pilot_r{pilot_round}_report"
        )
        result = {
            "schema": "czr005.g4irsf15.pilot_result.v1",
            **summary,
            "plan": {
                "path": _plan_path(
                    campaign, pilot_round=pilot_round
                ).as_posix(),
                "self_sha256": plan["self_sha256"],
            },
            "pilot_round": pilot_round,
            "prior_pilot_result": plan.get("prior_pilot_result"),
            "screening_revision": plan.get("screening_revision"),
            "binary_sha256": current_binary_sha,
            "exact_binary_build_manifest": build_binding,
            "campaign_shard_execution": orchestrator_profile_set,
            "pair_evidence_shards": evidence_bindings,
            "run_state_attestation": run_state_attestation,
            "h_system_baseline_reference": None,
            "pilot_table": {
                "path": pilot_table_path.as_posix(),
                "sha256": _file_sha256(root / pilot_table_path),
                "byte_count": pilot_table_byte_count,
            },
            "report": {
                "path": runner_report_path.as_posix(),
                "sha256": _file_sha256(root / runner_report_path),
                "byte_count": pilot_report_byte_count,
            },
        }
        _require(
            _validate_orchestrator_profile_set(
                root=root,
                profile_paths=orchestrator_profiles,
                campaign=campaign,
                pilot_round=pilot_round,
                plan=plan,
                plan_path=plan_path,
                binary=resolved_binary,
                build_manifest=resolved_build_manifest,
                build_binding=build_binding,
            )
            == orchestrator_profile_set,
            "ORCHESTRATOR_PROFILE_SET_CHANGED_DURING_FINALIZE",
        )
        _revalidate_orchestrator_profile_files(
            root, orchestrator_profile_set
        )
        return _atomic_json(root / pilot_result_path, result)

    split = _split_groups(eligible)
    _atomic_write(root / SPLIT_GROUP_PATH, _json_bytes(split))
    split_byte_count = _publishable_byte_count(
        root / SPLIT_GROUP_PATH, "formal_split_groups"
    )
    label_payload = _zstd_compress(_jsonl_bytes(labels))
    _atomic_write(root / LABEL_DATASET_PATH, label_payload)
    label_byte_count = _publishable_byte_count(
        root / LABEL_DATASET_PATH, "formal_label_dataset"
    )
    label_dataset_binding = {
        "path": LABEL_DATASET_PATH.as_posix(),
        "sha256": _file_sha256(root / LABEL_DATASET_PATH),
        "byte_count": label_byte_count,
        "encoding": "CANONICAL_JSONL_ZSTD",
        "row_count": len(labels),
        "eligible_row_count": len(eligible),
        "content_sha256": _canonical_sha256(labels),
    }
    weighted_effects = _weighted_effect_analysis(
        labels,
        plan=plan,
        label_dataset_binding=label_dataset_binding,
        formal_gate_passed=passed,
    )
    _atomic_write(
        root / WEIGHTED_EFFECT_DATASET_PATH,
        _json_bytes(weighted_effects),
    )
    weighted_effect_dataset_byte_count = _publishable_byte_count(
        root / WEIGHTED_EFFECT_DATASET_PATH,
        "weighted_effect_dataset",
    )
    _atomic_write(
        root / WEIGHTED_EFFECT_TABLE_PATH,
        _csv_bytes(
            weighted_effects["estimates"],
            WEIGHTED_EFFECT_CSV_FIELDS,
        ),
    )
    weighted_effect_table_byte_count = _publishable_byte_count(
        root / WEIGHTED_EFFECT_TABLE_PATH,
        "weighted_effect_table",
    )
    _atomic_write(root / CAUSAL_TABLE_PATH, _csv_bytes(rows, PAIR_CSV_FIELDS))
    causal_table_byte_count = _publishable_byte_count(
        root / CAUSAL_TABLE_PATH, "formal_causal_table"
    )
    h_rows = _pair_rows(
        [row for row in labels if row.get("horizon") == "H_system"]
    )
    _atomic_write(
        root / H_SYSTEM_TABLE_PATH, _csv_bytes(h_rows, PAIR_CSV_FIELDS)
    )
    h_system_table_byte_count = _publishable_byte_count(
        root / H_SYSTEM_TABLE_PATH, "formal_h_system_table"
    )
    _write_report(
        root / CAMPAIGN_REPORT_PATH,
        campaign=campaign,
        summary=summary,
    )
    campaign_report_byte_count = _publishable_byte_count(
        root / CAMPAIGN_REPORT_PATH, "formal_campaign_report"
    )
    manifest_value = {
        "schema": LABEL_MANIFEST_SCHEMA,
        **summary,
        "scale_count": 0,
        "learning_authorized": passed,
        "plan": {
            "path": FORMAL_PLAN_PATH.as_posix(),
            "self_sha256": plan["self_sha256"],
            "file_sha256": _file_sha256(plan_path),
        },
        "binary": {
            "path": build_binding.get("binary_path"),
            "path_scope": build_binding.get("binary_path_scope"),
            "sha256": current_binary_sha,
            "all_shards_same_binary": all(
                binding["binary_sha256"] == current_binary_sha
                for binding in evidence_bindings
            ),
        },
        "exact_binary_build_manifest": build_binding,
        "campaign_shard_execution": orchestrator_profile_set,
        "pair_evidence_shards": evidence_bindings,
        "run_state_attestation": run_state_attestation,
        "h_system_baseline_reference": (
            baseline_reference_binding
        ),
        "label_dataset": label_dataset_binding,
        "weighted_effect_estimates": {
            "path": WEIGHTED_EFFECT_DATASET_PATH.as_posix(),
            "sha256": _file_sha256(
                root / WEIGHTED_EFFECT_DATASET_PATH
            ),
            "self_sha256": weighted_effects["self_sha256"],
            "byte_count": weighted_effect_dataset_byte_count,
            "estimate_count": len(weighted_effects["estimates"]),
            "response_summary_count": len(
                weighted_effects["response_summaries"]
            ),
        },
        "split_groups": {
            "path": SPLIT_GROUP_PATH.as_posix(),
            "sha256": _file_sha256(root / SPLIT_GROUP_PATH),
            "self_sha256": split["self_sha256"],
            "byte_count": split_byte_count,
        },
        "tables": {
            "causal_pairs": {
                "path": CAUSAL_TABLE_PATH.as_posix(),
                "sha256": _file_sha256(root / CAUSAL_TABLE_PATH),
                "byte_count": causal_table_byte_count,
            },
            "h_system_pairs": {
                "path": H_SYSTEM_TABLE_PATH.as_posix(),
                "sha256": _file_sha256(root / H_SYSTEM_TABLE_PATH),
                "byte_count": h_system_table_byte_count,
            },
            "campaign_coverage": {
                "path": COVERAGE_TABLE_PATH.as_posix(),
                "sha256": _file_sha256(root / COVERAGE_TABLE_PATH),
                "byte_count": _publishable_byte_count(
                    root / COVERAGE_TABLE_PATH, "campaign_coverage"
                ),
            },
            "weighted_effect_estimates": {
                "path": WEIGHTED_EFFECT_TABLE_PATH.as_posix(),
                "sha256": _file_sha256(
                    root / WEIGHTED_EFFECT_TABLE_PATH
                ),
                "byte_count": weighted_effect_table_byte_count,
            },
        },
        "report": {
            "path": CAMPAIGN_REPORT_PATH.as_posix(),
            "sha256": _file_sha256(root / CAMPAIGN_REPORT_PATH),
            "byte_count": campaign_report_byte_count,
        },
    }
    _require(
        _validate_orchestrator_profile_set(
            root=root,
            profile_paths=orchestrator_profiles,
            campaign=campaign,
            pilot_round=pilot_round,
            plan=plan,
            plan_path=plan_path,
            binary=resolved_binary,
            build_manifest=resolved_build_manifest,
            build_binding=build_binding,
        )
        == orchestrator_profile_set,
        "ORCHESTRATOR_PROFILE_SET_CHANGED_DURING_FINALIZE",
    )
    _revalidate_orchestrator_profile_files(
        root, orchestrator_profile_set
    )
    return _atomic_json(root / LABEL_MANIFEST_PATH, manifest_value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan")
    scan.add_argument("--binary", type=Path, required=True)
    scan.add_argument(
        "--build-manifest",
        type=Path,
        required=True,
        help="Build-emitted exact-binary attestation to revalidate.",
    )
    scan.add_argument(
        "--pool-size", type=int, default=DEFAULT_DESCRIPTOR_POOL
    )
    scan.add_argument(
        "--native-max-per-kind",
        type=int,
        default=0,
        help="Publication requires 0 (complete population).",
    )

    pilot = subparsers.add_parser("plan-pilot")
    pilot.add_argument("--round", type=int, choices=(1, 2), default=1)
    pilot.add_argument(
        "--shard-size", type=int, default=DEFAULT_PILOT_SHARD_SIZE
    )

    formal = subparsers.add_parser("plan-formal")
    formal.add_argument(
        "--shard-size", type=int, default=DEFAULT_FORMAL_SHARD_SIZE
    )
    formal.add_argument(
        "--h-system-attempts",
        type=int,
        default=0,
        help=(
            "0 preregisters the fixed 256-pair full-system hard-gate/"
            "externality audit; a manual value may only increase it."
        ),
    )
    formal.add_argument(
        "--h-system-targets-per-shard",
        type=int,
        default=DEFAULT_H_SYSTEM_TARGETS_PER_SHARD,
        help=(
            "Memory cap for full 43,603-row H_system evidence sidecars."
        ),
    )

    worker = subparsers.add_parser("run-shard")
    worker.add_argument("--campaign", choices=("pilot", "formal"), required=True)
    worker.add_argument("--shard-index", type=int, required=True)
    worker.add_argument("--binary", type=Path, required=True)
    worker.add_argument("--build-manifest", type=Path, required=True)
    worker.add_argument(
        "--round",
        type=int,
        choices=(1, 2),
        default=1,
        help="Required namespace selector for pilot r1/r2.",
    )

    finalize = subparsers.add_parser("finalize")
    finalize.add_argument(
        "--campaign", choices=("pilot", "formal"), required=True
    )
    finalize.add_argument("--binary", type=Path, required=True)
    finalize.add_argument("--build-manifest", type=Path, required=True)
    finalize.add_argument(
        "--orchestrator-profile",
        dest="orchestrator_profiles",
        action="append",
        type=Path,
        required=True,
        help=(
            "Repeat once per COMPLETE production orchestrator profile; "
            "their requested shard sets must be disjoint and exactly "
            "cover the preregistered plan."
        ),
    )
    finalize.add_argument(
        "--round",
        type=int,
        choices=(1, 2),
        default=1,
        help="Required namespace selector for pilot r1/r2.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    root = arguments.root.resolve()
    if arguments.command == "scan":
        result = run_scan(
            root=root,
            binary=arguments.binary,
            pool_size=arguments.pool_size,
            build_manifest=arguments.build_manifest,
            native_max_per_kind=arguments.native_max_per_kind,
        )
    elif arguments.command == "plan-pilot":
        result = create_plan(
            root=root,
            campaign="pilot",
            shard_size=arguments.shard_size,
            pilot_round=arguments.round,
        )
    elif arguments.command == "plan-formal":
        result = create_plan(
            root=root,
            campaign="formal",
            shard_size=arguments.shard_size,
            h_system_attempts=arguments.h_system_attempts,
            h_system_targets_per_shard=(
                arguments.h_system_targets_per_shard
            ),
        )
    elif arguments.command == "run-shard":
        result = run_shard(
            root=root,
            campaign=arguments.campaign,
            shard_index=arguments.shard_index,
            binary=arguments.binary,
            build_manifest=arguments.build_manifest,
            pilot_round=arguments.round,
        )
    elif arguments.command == "finalize":
        result = finalize_campaign(
            root=root,
            campaign=arguments.campaign,
            binary=arguments.binary,
            build_manifest=arguments.build_manifest,
            orchestrator_profiles=arguments.orchestrator_profiles,
            pilot_round=arguments.round,
        )
    else:  # pragma: no cover
        raise AssertionError(arguments.command)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CampaignError as exc:
        print(f"G4IRSF15_CAUSAL_CAMPAIGN_ERROR:{exc}", file=sys.stderr)
        raise SystemExit(2) from exc
