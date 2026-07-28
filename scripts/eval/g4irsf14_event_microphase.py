"""Fail-closed G4IRSF14-B/C opportunity audit and event-microphase runner.

The runner is deliberately narrow:

* only the protected ``map2.json`` and ``inputdata.jsonl`` are admitted;
* the control is always F2 ``R3/S1/P2/C0/Q0`` with no fault and scale 1.0;
* the only experimental variable is ``E0``/``E1``/``E2``/``E3`` event
  semantics;
* execution follows motif -> 144 -> 512 -> 2048 -> 8192, while original 1x
  requires ``--allow-full`` and admits only E0 plus the best measured batched
  mode;
* complete raw telemetry is kept in a hash-bound local gzip archive.  Committed
  CSVs contain aggregates and deterministic min-hash samples only;
* missing capabilities, truncated telemetry, incomplete drainage, and safety
  violations are retained as negative evidence and never converted to PASS.

This module does not expose a runtime A*, a future route, a global reservation
table, a non-zero batching window, a fault workload, or a scale multiplier.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import functools
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import statistics
import struct
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT, ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from scripts.eval import g4irsf12_reproducible_harness as g12  # noqa: E402
from scripts.eval import g4irsf13_cde_experiments as g13  # noqa: E402
from scripts.eval import g4irsf14_phase_a as phase_a  # noqa: E402
from scripts.eval.g4irsf11_fixed_map import (  # noqa: E402
    assert_canonical_map,
    canonical_graph_records,
)
from scripts.eval.g4irsf12_size_ladder import (  # noqa: E402
    CANONICAL_MAP_PATH,
    CANONICAL_MAP_RAW_SHA256,
    CANONICAL_MAP_SEMANTIC_SHA256,
    CANONICAL_SOURCE_PATH,
    CANONICAL_SOURCE_RAW_SHA256,
    FULL_SIZE_BAGS,
    FULL_SIZE_SEGMENTS,
)


PROTOCOL_SCHEMA = "czr005.g4irsf14.event_microphase_protocol.v1"
RESULT_SCHEMA = "czr005.g4irsf14.event_microphase_result.v1"
ATTEMPT_SCHEMA = "czr005.g4irsf14.event_microphase_attempt.v1"
COMPLETE_SCHEMA = "czr005.g4irsf14.event_microphase_complete_pointer.v1"
TABLE_SCHEMA = "czr005.g4irsf14.event_microphase_table.v1"

MAP_PATH = Path(CANONICAL_MAP_PATH)
TASK_PATH = Path(CANONICAL_SOURCE_PATH)
LOCAL_ARCHIVE = Path(".local_archives/g4irsf14_event_microphase")
F2_CONTROL_PATH = Path("artifacts/policies/g4irsf14_f2_frozen_control.json")
BASELINE_REGISTRY_PATH = Path(
    "artifacts/gates/g4irsf14_baseline_registry.json"
)
PRIORITY_ABLATION_PATH = Path(
    "outputs/tables/g4irsf13_priority_ablation.csv"
)
PER_BAG_PATH = Path("outputs/tables/g4irsf13_per_bag_delta.csv")
DIVERGENCE_PATH = Path("outputs/tables/g4irsf13_decision_divergence.csv")

OUTPUT_PATHS: Mapping[str, Path] = {
    "source": Path(
        "outputs/tables/g4irsf14_source_admission_opportunities.csv"
    ),
    "junction": Path(
        "outputs/tables/g4irsf14_junction_arbitration_opportunities.csv"
    ),
    "merge": Path("outputs/tables/g4irsf14_merge_request_visibility.csv"),
    "seq": Path("outputs/tables/g4irsf14_event_seq_ordering_audit.csv"),
    "batch": Path(
        "outputs/tables/g4irsf14_arbitration_batch_cardinality.csv"
    ),
    "ab": Path("outputs/tables/g4irsf14_event_microphase_ab.csv"),
    "audit_report": Path(
        "outputs/reports/g4irsf14_effective_decision_opportunity_audit.md"
    ),
    "ab_report": Path("outputs/reports/g4irsf14_event_microphase_ab.md"),
}

MODE_ORDER = (
    "E0_immediate_dispatch_f2",
    "E1_batch_source_same_timestamp",
    "E2_batch_junction_same_timestamp",
    "E3_batch_source_and_junction_same_timestamp",
)
MODE_ALIASES = {
    "E0": MODE_ORDER[0],
    "E1": MODE_ORDER[1],
    "E2": MODE_ORDER[2],
    "E3": MODE_ORDER[3],
    **{mode: mode for mode in MODE_ORDER},
}
BATCHED_MODES = MODE_ORDER[1:]
TIER_ORDER = ("motif", "144", "512", "2048", "8192", "full")
SMALL_TIER_ORDER = TIER_ORDER[:-1]
DEFAULT_OPPORTUNITY_TRACE_LIMIT = 1_000_000
DETERMINISTIC_SAMPLE_COUNT = 24
PRIORITY_COMPARISON_SEMANTICS = (
    "actual_choose_bag_comparator_invocations_escape_bypass_zero"
)
E0_ORACLE_SCHEMA = "czr005.g4irsf14.e0_frozen_oracle.v1"
E0_ORACLE_CERTIFICATE_SCHEMA = (
    "czr005.g4irsf14.e0_frozen_oracle_certificate.v1"
)
E0_ORACLE_TIERS = ("motif", "144")
E0_ORACLE_TRACE_ARRAYS = (
    "events",
    "decisions",
    "decision_trace",
    "hold_attempts",
    "pibt_events",
    "credit_events",
    "fault_events",
)
# These are the only summary observations excluded from the exact algorithm
# projection.  The first two identify the independently loaded binary; the
# remainder are host-dependent performance observations (time/RSS) already
# excluded by the frozen G4IRSF13 algorithm-equivalence protocol.  Runtime
# state-memory accounting fields remain algorithm fields and must compare
# exactly.
E0_ORACLE_EXCLUDED_SUMMARY_FIELDS = frozenset(
    {
        "loaded_cpp_binary_path",
        "loaded_cpp_binary_sha256",
        "wall_seconds",
        "runtime_seconds",
        "event_throughput_per_second",
        "decision_latency_us_p50",
        "decision_latency_us_p95",
        "decision_latency_us_p99",
        "peak_working_set_bytes",
        "working_set_bytes",
        "peak_rss_bytes",
        "rss_bytes",
    }
)
E0_ORACLE_EXTENSION_SUMMARY_FIELDS = frozenset(
    {
        "event_semantics",
        "event_semantics_echo",
        "opportunity_telemetry_enabled",
        "source_arbitration_event_count",
        "junction_arbitration_event_count",
        "stale_arbitration_event_count",
        "superseded_arbitration_event_rejected_count",
        "duplicate_same_time_arbitration_prevented_count",
        "source_same_timestamp_batch_count",
        "junction_same_timestamp_batch_count",
        "max_source_arbitration_batch_size",
        "max_junction_arbitration_batch_size",
        "opportunity_event_queue_inspection_count",
        "source_opportunity_total_count",
        "source_opportunity_stored_count",
        "source_opportunity_dropped_count",
        "junction_opportunity_total_count",
        "junction_opportunity_stored_count",
        "junction_opportunity_dropped_count",
        "merge_visibility_total_count",
        "merge_visibility_stored_count",
        "merge_visibility_dropped_count",
        "event_seq_audit_total_count",
        "event_seq_audit_stored_count",
        "event_seq_audit_dropped_count",
        "arbitration_batch_total_count",
        "arbitration_batch_stored_count",
        "arbitration_batch_dropped_count",
        "fault_generation_commit_recheck_count",
        "microphase_runtime_global_scan_count",
        "artificial_batch_delay_seconds",
    }
)
E0_ORACLE_EXTENSION_TRACE_CONTEXT_FIELDS = frozenset(
    {
        "event_semantics",
        "event_semantics_echo",
        "opportunity_telemetry_enabled",
        "event_timestamp_grouping",
        "local_arbitration_key",
        "priority_comparison_semantics",
        "stale_arbitration_event_semantics",
        "superseded_arbitration_event_rejected_semantics",
        "arbitration_worklist_scope",
        "event_queue_inspection_scope",
        "destination_competitor_visibility_semantics",
        "opportunity_trace_limit",
        "artificial_batch_delay_seconds",
        "destination_merge_grant_enabled",
    }
)
E0_ORACLE_PROJECTION_HASH_FIELDS = (
    "bags_sha256",
    "junction_state_sha256",
    "algorithm_summary_sha256",
    "trace_context_sha256",
    "trace_payload_sha256",
    "algorithm_projection_sha256",
)

FROZEN_CONTROL = {
    "resource_semantics": "R3_java_node_window_compatible",
    "scorer_mode": "S1_frozen_g4e_legal_local_adapter",
    "pibt_mode": "P2",
    "pibt_max_depth": 2,
    "priority_mode": "Q0",
    "framework_mode": "event_loop_one_step",
    "pibt_preference_mode": "current",
    "pibt_regret_prior_records": [],
    "selective_credit_contention_threshold": 1,
    "pressure_mode": "off",
    "admission_mode": "off",
    "enable_backpressure": False,
    "enable_source_admission": False,
    "enable_pibt_lite": False,
    "local_queue_capacity": 32,
    "max_events": 20_000_000,
    "reservation_depth": 1,
    "entry_headway_seconds": 0.001,
    "credit_validity_seconds": 1.0,
    "credit_snapshot_max_age_seconds": 1.0,
    "credit_capacity_per_edge": 1,
    "credit_lifecycle_limit": 512,
    "pibt_max_ready_bags": 8,
    "pibt_max_local_resources": 32,
    "pibt_max_candidates_per_bag": 8,
}

SOURCE_BUNDLE_PATHS = (
    Path("scripts/eval/g4irsf14_event_microphase.py"),
    Path("scripts/eval/g4irsf14_phase_a.py"),
    Path("scripts/eval/g4irsf13_cde_experiments.py"),
    Path("scripts/eval/g4irsf12_reproducible_harness.py"),
    Path("src/czr005/cpp_backend.py"),
    Path("cpp/ics_core/runtime/event_driven_junction.hpp"),
    Path("cpp/ics_core/runtime/bounded_local_pibt.hpp"),
    Path("cpp/ics_core/bindings/czr005_cpp.cpp"),
    Path("artifacts/models/g4e_risk_calibrated_policy.json"),
    BASELINE_REGISTRY_PATH,
    F2_CONTROL_PATH,
    PRIORITY_ABLATION_PATH,
    PER_BAG_PATH,
    DIVERGENCE_PATH,
)

TELEMETRY_ARRAYS: Mapping[str, tuple[str, ...]] = {
    "source_admission_opportunities": (
        "event_time",
        "timestamp_bits",
        "source_node",
        "queue_length_before_enqueue",
        "queue_length_after_enqueue",
        "queue_length_before_arbitration",
        "queue_length_after_arbitration",
        "same_timestamp_release_batch_size",
        "same_time_pending_source_releases",
        "same_time_pending_shared_merge_releases",
        "ready_set_size",
        "priority_comparison_count",
        "chosen_task_id",
        "chosen_runtime_bag_id",
        "chosen_segment_id",
        "queue_discipline",
        "event_seq",
        "arbitration_generation",
        "batched_arbitration",
    ),
    "junction_arbitration_opportunities": (
        "event_time",
        "timestamp_bits",
        "junction_node",
        "queue_length_before_enqueue",
        "queue_length_after_enqueue",
        "queue_length_before_arbitration",
        "queue_length_after_arbitration",
        "same_timestamp_arrival_batch_size",
        "same_time_pending_arrivals",
        "same_time_pending_shared_merge_requests",
        "ready_set_size",
        "priority_comparison_count",
        "pibt_slice_bag_count",
        "pibt_owner_count",
        "chosen_task_id",
        "chosen_runtime_bag_id",
        "chosen_segment_id",
        "event_seq",
        "arbitration_generation",
        "batched_arbitration",
    ),
    "merge_request_visibility": (
        "event_time",
        "timestamp_bits",
        "destination_node",
        "upstream_node",
        "incoming_edge_start",
        "incoming_edge_end",
        "requesting_task_id",
        "requesting_runtime_bag_id",
        "requesting_segment_id",
        "earliest_arrival",
        "slot_start",
        "slot_end",
        "known_competing_request_count",
        "later_same_time_competitor_count",
        "later_same_time_competitor_exists",
        "seq_determined_order",
        "event_seq",
    ),
    "event_seq_ordering_audit": (
        "event_time",
        "timestamp_bits",
        "boundary",
        "node",
        "destination_node",
        "ready_set_size",
        "priority_comparison_count",
        "later_same_time_competitor_count",
        "chosen_runtime_bag_id",
        "chosen_enqueue_sequence",
        "event_seq",
        "seq_determined_order",
        "reason",
    ),
    "arbitration_batch_cardinality": (
        "event_time",
        "timestamp_bits",
        "boundary",
        "node",
        "enqueue_count",
        "ready_set_size",
        "pending_same_time_event_count",
        "chosen_runtime_bag_id",
        "event_seq",
        "arbitration_generation",
    ),
}

# The runtime publishes these counters only when a G4IRSF14 extension is on.
# Keeping exact names here makes telemetry truncation a fail-closed condition.
TELEMETRY_COUNTERS: Mapping[str, tuple[str, str, str]] = {
    "source_admission_opportunities": (
        "source_opportunity_total_count",
        "source_opportunity_stored_count",
        "source_opportunity_dropped_count",
    ),
    "junction_arbitration_opportunities": (
        "junction_opportunity_total_count",
        "junction_opportunity_stored_count",
        "junction_opportunity_dropped_count",
    ),
    "merge_request_visibility": (
        "merge_visibility_total_count",
        "merge_visibility_stored_count",
        "merge_visibility_dropped_count",
    ),
    "event_seq_ordering_audit": (
        "event_seq_audit_total_count",
        "event_seq_audit_stored_count",
        "event_seq_audit_dropped_count",
    ),
    "arbitration_batch_cardinality": (
        "arbitration_batch_total_count",
        "arbitration_batch_stored_count",
        "arbitration_batch_dropped_count",
    ),
}


class MicrophaseError(ValueError):
    """Raised when evidence cannot be admitted."""


@dataclass(frozen=True)
class RuntimeCase:
    mode: str
    tier: str
    selection: g13.WorkloadSelection

    def __post_init__(self) -> None:
        if self.mode not in MODE_ORDER:
            raise MicrophaseError(f"unknown event mode: {self.mode}")
        if self.tier not in TIER_ORDER:
            raise MicrophaseError(f"unknown tier: {self.tier}")
        if self.selection.tier != self.tier:
            raise MicrophaseError("selection tier does not match runtime case")

    @property
    def case_id(self) -> str:
        return f"{self.mode}__{self.tier}"


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
    if not path.is_file():
        raise MicrophaseError(f"missing hash-bound file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_json(path: Path, value: Any) -> None:
    _atomic_write(path, canonical_json_bytes(value) + b"\n")


def atomic_write_csv(
    path: Path,
    columns: Sequence[str],
    rows: Iterable[Mapping[str, Any]],
) -> None:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=list(columns),
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    _atomic_write(path, buffer.getvalue().encode("utf-8"))


class _HashingGzipWriter:
    def __init__(self, handle: gzip.GzipFile) -> None:
        self.handle = handle
        self.digest = hashlib.sha256()

    def write(self, text: str) -> int:
        payload = text.encode("utf-8")
        self.digest.update(payload)
        self.handle.write(payload)
        return len(text)


def atomic_write_gzip_json(path: Path, value: Any) -> tuple[str, str]:
    """Stream canonical JSON to gzip and return raw/compressed SHA-256."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    os.close(descriptor)
    temporary = Path(name)
    raw_digest = ""
    try:
        with temporary.open("wb") as raw_handle:
            with gzip.GzipFile(
                filename="",
                mode="wb",
                fileobj=raw_handle,
                mtime=0,
                compresslevel=6,
            ) as compressed:
                writer = _HashingGzipWriter(compressed)
                json.dump(
                    value,
                    writer,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                raw_digest = writer.digest.hexdigest()
            raw_handle.flush()
            os.fsync(raw_handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return raw_digest, file_sha256(path)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise MicrophaseError(f"missing JSON artifact: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MicrophaseError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise MicrophaseError(f"{path} root must be an object")
    return value


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise MicrophaseError(f"missing CSV artifact: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _strict_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MicrophaseError(f"{label} must be an exact integer")
    return value


def _strict_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise MicrophaseError(f"{label} must be a boolean")
    return value


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MicrophaseError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise MicrophaseError(f"{label} must be finite")
    return result


def _bool_text(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no", ""}:
        return False
    raise MicrophaseError(f"invalid boolean text: {value!r}")


def assert_phase_a_and_inputs(
    root: Path = ROOT,
    *,
    frozen_binary_override: Path | None = None,
    require_frozen_binary: bool = True,
) -> dict[str, Any]:
    """Validate the immutable Stage-14A registry and protected inputs."""

    g13.assert_fixed_inputs(root)
    # A clean verification clone does not contain the intentionally-untracked
    # frozen pyd.  It may point to a physical copy elsewhere, but that copy is
    # admitted only after its bytes match the hash sealed in the Stage-14A
    # artifact below.
    evidence = phase_a.collect_inherited_evidence(
        root,
        require_binary=(
            require_frozen_binary and frozen_binary_override is None
        ),
    )
    failures = [
        *phase_a.validate_inherited_evidence(evidence),
        *phase_a.validate_committed_outputs(root, evidence),
    ]
    if failures:
        raise MicrophaseError(
            "STAGE_14A_FAIL_CLOSED:" + " | ".join(sorted(set(failures)))
        )
    registry = _read_json(root / BASELINE_REGISTRY_PATH)
    f2_control = _read_json(root / F2_CONTROL_PATH)
    if registry.get("status") != "PASS_BASELINE_FROZEN":
        raise MicrophaseError("Stage-14A baseline registry is not frozen PASS")
    if f2_control.get("status") != "PASS_FROZEN_CONTROL":
        raise MicrophaseError("Stage-14A F2 control is not frozen PASS")
    return {
        "map_raw_sha256": CANONICAL_MAP_RAW_SHA256,
        "map_semantic_sha256": CANONICAL_MAP_SEMANTIC_SHA256,
        "task_raw_sha256": CANONICAL_SOURCE_RAW_SHA256,
        "baseline_registry_sha256": file_sha256(
            root / BASELINE_REGISTRY_PATH
        ),
        "f2_control_sha256": file_sha256(root / F2_CONTROL_PATH),
        "frozen_binary": dict(
            f2_control.get("final_runtime_identity", {}).get("binary", {})
        ),
    }


def source_bundle_identity(root: Path = ROOT) -> dict[str, Any]:
    rows = [
        {"path": relative.as_posix(), "sha256": file_sha256(root / relative)}
        for relative in SOURCE_BUNDLE_PATHS
    ]
    return {
        "files": rows,
        "path_manifest_sha256": canonical_sha256(
            [row["path"] for row in rows]
        ),
        "bundle_sha256": canonical_sha256(rows),
    }


def assert_execution_files_unchanged(
    *,
    binary: Path,
    expected_binary: Mapping[str, Any],
    expected_source_bundle: Mapping[str, Any],
    root: Path = ROOT,
) -> None:
    """Fail closed if an instrumented run is edited or relinked in flight."""

    if _binary_identity(binary) != dict(expected_binary):
        raise MicrophaseError("INSTRUMENTED_BINARY_DRIFT_DURING_EXECUTION")
    if source_bundle_identity(root) != dict(expected_source_bundle):
        raise MicrophaseError("SOURCE_BUNDLE_DRIFT_DURING_EXECUTION")


@functools.lru_cache(maxsize=32)
def load_selection(tier: str, root: Path = ROOT) -> g13.WorkloadSelection:
    if tier == "motif":
        return g13.load_real_map_motif(root)
    return g13.load_prefix_selection(tier, root)


def runtime_controls(
    mode: str,
    *,
    opportunity_trace_limit: int,
) -> dict[str, Any]:
    canonical = MODE_ALIASES.get(mode)
    if canonical is None:
        raise MicrophaseError(f"unknown event semantics: {mode}")
    if (
        isinstance(opportunity_trace_limit, bool)
        or not isinstance(opportunity_trace_limit, int)
        or opportunity_trace_limit <= 0
    ):
        raise MicrophaseError("opportunity_trace_limit must be a positive int")
    return {
        **FROZEN_CONTROL,
        "event_semantics": canonical,
        "enable_opportunity_telemetry": True,
        "opportunity_trace_limit": opportunity_trace_limit,
    }


def _binary_identity(binary: Path) -> dict[str, str]:
    resolved = binary.resolve(strict=True)
    return {"path": resolved.as_posix(), "sha256": file_sha256(resolved)}


def _git_command(
    root: Path,
    arguments: Sequence[str],
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *arguments],
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise MicrophaseError(
            f"GIT_COMMAND_LAUNCH_FAILED:{' '.join(arguments)}"
        ) from exc


def _git_stdout(
    root: Path,
    arguments: Sequence[str],
    *,
    label: str,
) -> bytes:
    completed = _git_command(root, arguments)
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", "replace").strip()
        raise MicrophaseError(
            f"{label}:exit={completed.returncode}:stderr={stderr[:1000]}"
        )
    return completed.stdout


def _is_lower_hex_digest(value: Any, lengths: tuple[int, ...]) -> bool:
    return (
        isinstance(value, str)
        and len(value) in lengths
        and all(character in "0123456789abcdef" for character in value)
    )


@functools.lru_cache(maxsize=32)
def _git_source_bundle_at_commit(
    root: Path,
    commit: str,
) -> dict[str, Any]:
    """Rebuild the exact SOURCE_BUNDLE_PATHS blobs from the Git object DB."""

    if not _is_lower_hex_digest(commit, (40, 64)):
        raise MicrophaseError("RECORDED_EXECUTION_GIT_COMMIT_INVALID")
    resolved_commit = _git_stdout(
        root,
        ["rev-parse", "--verify", f"{commit}^{{commit}}"],
        label="RECORDED_EXECUTION_GIT_COMMIT_MISSING",
    ).decode("ascii", "strict").strip().lower()
    if resolved_commit != commit:
        raise MicrophaseError("RECORDED_EXECUTION_GIT_COMMIT_NOT_CANONICAL")
    rows: list[dict[str, str]] = []
    for relative in SOURCE_BUNDLE_PATHS:
        path = relative.as_posix()
        object_spec = f"{commit}:{path}"
        blob_oid = _git_stdout(
            root,
            ["rev-parse", "--verify", object_spec],
            label=f"RECORDED_SOURCE_BLOB_MISSING:{path}",
        ).decode("ascii", "strict").strip().lower()
        if not _is_lower_hex_digest(blob_oid, (40, 64)):
            raise MicrophaseError(
                f"RECORDED_SOURCE_BLOB_OID_INVALID:{path}"
            )
        blob = _git_stdout(
            root,
            ["cat-file", "blob", object_spec],
            label=f"RECORDED_SOURCE_BLOB_READ_FAILED:{path}",
        )
        rows.append(
            {
                "path": path,
                "blob_oid": blob_oid,
                "blob_sha256": hashlib.sha256(blob).hexdigest(),
            }
        )
    return {
        "files": rows,
        "path_manifest_sha256": canonical_sha256(
            [row["path"] for row in rows]
        ),
        "bundle_sha256": canonical_sha256(rows),
    }


def execution_source_history_identity(root: Path = ROOT) -> dict[str, Any]:
    """Bind clean normalized Git state and the actual working source bytes."""

    paths = [path.as_posix() for path in SOURCE_BUNDLE_PATHS]
    for path in paths:
        _git_stdout(
            root,
            ["ls-files", "--error-unmatch", "--", path],
            label=f"EXECUTION_SOURCE_PATH_NOT_TRACKED:{path}",
        )
    for arguments, label in (
        (
            ["diff", "--quiet", "HEAD", "--"],
            "EXECUTION_TRACKED_TREE_WORKTREE_DIRTY",
        ),
        (
            ["diff", "--cached", "--quiet", "HEAD", "--"],
            "EXECUTION_TRACKED_TREE_INDEX_DIRTY",
        ),
    ):
        completed = _git_command(root, arguments)
        if completed.returncode != 0:
            stderr = completed.stderr.decode("utf-8", "replace").strip()
            raise MicrophaseError(
                f"{label}:exit={completed.returncode}:stderr={stderr[:1000]}"
            )
    commit = _git_stdout(
        root,
        ["rev-parse", "--verify", "HEAD^{commit}"],
        label="EXECUTION_GIT_HEAD_INVALID",
    ).decode("ascii", "strict").strip().lower()
    git_source_bundle = _git_source_bundle_at_commit(root, commit)
    working_source_bundle = source_bundle_identity(root)
    return {
        "git_commit_sha": commit,
        "working_source_bundle": working_source_bundle,
        "git_source_bundle": git_source_bundle,
        "clean_gate": {
            "source_paths_tracked": True,
            "tracked_tree_worktree_diff_quiet": True,
            "tracked_tree_index_diff_quiet": True,
            "normalization": (
                "git_diff_normalization_aware;working_raw_sha_may_differ_"
                "from_git_blob_sha_under_core_autocrlf"
            ),
        },
    }


def _resolve_frozen_binary(
    phase_a_identity: Mapping[str, Any],
    *,
    root: Path,
    override: Path | None,
) -> dict[str, str]:
    """Resolve the untracked Stage-A pyd and bind it to its sealed hash."""

    descriptor = phase_a_identity.get("frozen_binary")
    if not isinstance(descriptor, Mapping):
        raise MicrophaseError("Stage-14A frozen binary descriptor is missing")
    artifact_path = descriptor.get("path")
    declared_hash = descriptor.get("file_sha256")
    expected_hash = descriptor.get("expected_file_sha256")
    if not isinstance(artifact_path, str) or not artifact_path:
        raise MicrophaseError("Stage-14A frozen binary path is invalid")
    if (
        not isinstance(declared_hash, str)
        or not isinstance(expected_hash, str)
        or declared_hash != expected_hash
        or len(declared_hash) != 64
        or any(character not in "0123456789abcdef" for character in declared_hash)
    ):
        raise MicrophaseError("Stage-14A frozen binary hash binding is invalid")
    physical_path = (
        override.resolve(strict=True)
        if override is not None
        else (root / artifact_path).resolve(strict=True)
    )
    physical_identity = _binary_identity(physical_path)
    if physical_identity["sha256"] != declared_hash:
        raise MicrophaseError(
            "STAGE_14A_FROZEN_BINARY_SHA256_MISMATCH:"
            f"expected={declared_hash}:observed={physical_identity['sha256']}"
        )
    return {
        "artifact_path": artifact_path,
        "artifact_sha256": declared_hash,
        "physical_path": physical_identity["path"],
        "physical_sha256": physical_identity["sha256"],
    }


def _e0_oracle_controls() -> dict[str, Any]:
    """Return F2 with only non-behavioural, complete-trace observation knobs."""

    return {
        **FROZEN_CONTROL,
        "event_semantics": MODE_ORDER[0],
        "enable_opportunity_telemetry": False,
        "opportunity_trace_limit": 0,
    }


def _e0_oracle_projection(
    payload: Mapping[str, Any],
    *,
    role: str,
    tier: str,
    selection: g13.WorkloadSelection,
    expected_binary: Mapping[str, str],
) -> dict[str, Any]:
    """Project every deterministic algorithm field for an exact old/new gate."""

    if role not in {"frozen", "new"}:
        raise MicrophaseError(f"invalid E0 oracle role: {role}")
    expected_top_level = {
        "summary",
        "bags",
        "junction_state",
        "trace_context",
        "loaded_cpp_binary_path",
        "loaded_cpp_binary_sha256",
        *E0_ORACLE_TRACE_ARRAYS,
    }
    observed_top_level = {str(key) for key in payload}
    if observed_top_level != expected_top_level:
        missing = sorted(expected_top_level - observed_top_level)
        unexpected = sorted(observed_top_level - expected_top_level)
        raise MicrophaseError(
            "E0_ORACLE_PAYLOAD_SHAPE_MISMATCH:"
            f"role={role}:tier={tier}:missing={missing}:unexpected={unexpected}"
        )
    try:
        payload_binary_path = os.path.normcase(
            str(Path(str(payload.get("loaded_cpp_binary_path", ""))).resolve(
                strict=True
            ))
        )
        expected_binary_path = os.path.normcase(
            str(Path(str(expected_binary.get("path", ""))).resolve(strict=True))
        )
    except (OSError, ValueError, RuntimeError) as exc:
        raise MicrophaseError(
            f"E0_ORACLE_BINARY_PATH_INVALID:role={role}:tier={tier}"
        ) from exc
    if payload_binary_path != expected_binary_path:
        raise MicrophaseError(
            f"E0_ORACLE_BINARY_PATH_MISMATCH:role={role}:tier={tier}"
        )
    if payload.get("loaded_cpp_binary_sha256") != expected_binary.get("sha256"):
        raise MicrophaseError(
            f"E0_ORACLE_BINARY_SHA256_MISMATCH:role={role}:tier={tier}"
        )

    summary = payload.get("summary")
    bags = payload.get("bags")
    junction_state = payload.get("junction_state")
    trace_context = payload.get("trace_context")
    if not isinstance(summary, Mapping):
        raise MicrophaseError("E0 oracle payload.summary must be an object")
    if not isinstance(bags, list):
        raise MicrophaseError("E0 oracle payload.bags must be an array")
    if not isinstance(junction_state, list):
        raise MicrophaseError(
            "E0 oracle payload.junction_state must be an array"
        )
    if not isinstance(trace_context, Mapping):
        raise MicrophaseError(
            "E0 oracle payload.trace_context must be an object"
        )
    try:
        summary_binary_path = os.path.normcase(
            str(
                Path(
                    str(summary.get("loaded_cpp_binary_path", ""))
                ).resolve(strict=True)
            )
        )
    except (OSError, ValueError, RuntimeError) as exc:
        raise MicrophaseError(
            f"E0_ORACLE_SUMMARY_BINARY_PATH_INVALID:role={role}:tier={tier}"
        ) from exc
    if summary_binary_path != expected_binary_path:
        raise MicrophaseError(
            f"E0_ORACLE_SUMMARY_BINARY_PATH_MISMATCH:role={role}:tier={tier}"
        )
    if summary.get("loaded_cpp_binary_sha256") != expected_binary.get("sha256"):
        raise MicrophaseError(
            f"E0_ORACLE_SUMMARY_BINARY_SHA256_MISMATCH:role={role}:tier={tier}"
        )

    leaked_summary = sorted(
        E0_ORACLE_EXTENSION_SUMMARY_FIELDS.intersection(
            str(key) for key in summary
        )
    )
    leaked_context = sorted(
        E0_ORACLE_EXTENSION_TRACE_CONTEXT_FIELDS.intersection(
            str(key) for key in trace_context
        )
    )
    if leaked_summary or leaked_context:
        raise MicrophaseError(
            "E0_ORACLE_DISABLED_EXTENSION_FIELD_PRESENT:"
            f"role={role}:tier={tier}:summary={leaked_summary}:"
            f"trace_context={leaked_context}"
        )
    if summary.get("decision_trace_truncated") is not False:
        raise MicrophaseError(
            f"E0_ORACLE_DECISION_TRACE_TRUNCATED:role={role}:tier={tier}"
        )
    if summary.get("event_trace_truncated") is not False:
        raise MicrophaseError(
            f"E0_ORACLE_EVENT_TRACE_TRUNCATED:role={role}:tier={tier}"
        )
    if summary.get("trace_limit") != -1:
        raise MicrophaseError(
            f"E0_ORACLE_DECISION_TRACE_NOT_UNLIMITED:role={role}:tier={tier}"
        )
    if summary.get("event_trace_limit") != -1:
        raise MicrophaseError(
            f"E0_ORACLE_EVENT_TRACE_NOT_UNLIMITED:role={role}:tier={tier}"
        )
    if summary.get("trace_shard_count") != 1 or summary.get(
        "trace_shard_index"
    ) != 0:
        raise MicrophaseError(
            f"E0_ORACLE_TRACE_SHARDED:role={role}:tier={tier}"
        )

    traces: dict[str, list[Any]] = {}
    for name in E0_ORACLE_TRACE_ARRAYS:
        value = payload.get(name)
        if not isinstance(value, list):
            raise MicrophaseError(
                f"E0 oracle payload.{name} must be an array"
            )
        traces[name] = value
    if traces["decision_trace"] != traces["decisions"]:
        raise MicrophaseError(
            f"E0_ORACLE_DECISION_TRACE_ALIAS_DRIFT:role={role}:tier={tier}"
        )
    if summary.get("decision_trace_stored_count") != len(
        traces["decisions"]
    ):
        raise MicrophaseError(
            f"E0_ORACLE_DECISION_TRACE_COUNT_MISMATCH:role={role}:tier={tier}"
        )
    if summary.get("hold_trace_stored_count") != len(
        traces["hold_attempts"]
    ):
        raise MicrophaseError(
            f"E0_ORACLE_HOLD_TRACE_COUNT_MISMATCH:role={role}:tier={tier}"
        )

    algorithm_summary = {
        str(key): value
        for key, value in sorted(summary.items(), key=lambda pair: str(pair[0]))
        if str(key) not in E0_ORACLE_EXCLUDED_SUMMARY_FIELDS
    }
    projection = {
        "bags": bags,
        "junction_state": junction_state,
        "summary": algorithm_summary,
        "trace_context": dict(trace_context),
        "traces": traces,
    }
    return {
        "schema": E0_ORACLE_SCHEMA,
        "role": role,
        "tier": tier,
        "selection": {
            "selection_id": selection.selection_id,
            "segment_count": selection.segment_count,
            "raw_bag_count": selection.raw_bag_count,
            "selected_rows_sha256": selection.selected_rows_sha256,
            "selected_segment_ids_sha256": (
                selection.selected_segment_ids_sha256
            ),
        },
        "binary": dict(expected_binary),
        "controls_sha256": canonical_sha256(_e0_oracle_controls()),
        "excluded_summary_fields": sorted(E0_ORACLE_EXCLUDED_SUMMARY_FIELDS),
        "extension_fields_absent": True,
        "bags_count": len(bags),
        "junction_state_count": len(junction_state),
        "trace_lengths": {
            name: len(value) for name, value in traces.items()
        },
        "bags_sha256": canonical_sha256(bags),
        "junction_state_sha256": canonical_sha256(junction_state),
        "algorithm_summary_sha256": canonical_sha256(algorithm_summary),
        "trace_context_sha256": canonical_sha256(trace_context),
        "trace_payload_sha256": canonical_sha256(traces),
        "algorithm_projection_sha256": canonical_sha256(projection),
    }


def _call_frozen_e0_append_only_adapter(
    legacy_call: Callable[..., Any],
    arguments: Sequence[Any],
) -> Any:
    """Call the Stage-A ABI after checking and removing exactly three tails."""

    args = tuple(arguments)
    if (
        len(args) < 3
        or args[-3] != MODE_ORDER[0]
        or args[-2] is not False
        or isinstance(args[-1], bool)
        or not isinstance(args[-1], int)
        or args[-1] != 0
    ):
        raise MicrophaseError(
            "E0_ORACLE_LEGACY_APPEND_ONLY_ARGUMENT_CONTRACT_DRIFT"
        )
    return legacy_call(*args[:-3])


def _execute_e0_oracle_child(
    *,
    role: str,
    tier: str,
    binary: Path,
    root: Path,
) -> dict[str, Any]:
    """Load exactly one pyd in this process and return its exact projection."""

    if tier not in E0_ORACLE_TIERS:
        raise MicrophaseError(f"invalid E0 oracle tier: {tier}")
    g13.assert_fixed_inputs(root)
    selection = load_selection(tier, root)
    case = RuntimeCase(MODE_ORDER[0], tier, selection)
    binary_identity = _binary_identity(binary)
    controls = _e0_oracle_controls()

    from czr005 import cpp_backend

    native = cpp_backend.load_cpp_module(binary.parent)
    native_path = getattr(native, "__file__", None)
    if native_path is None or os.path.normcase(
        str(Path(native_path).resolve(strict=True))
    ) != os.path.normcase(str(binary.resolve(strict=True))):
        raise MicrophaseError(
            f"E0_ORACLE_WRONG_BINARY_LOADED:role={role}:tier={tier}"
        )
    if role == "frozen":
        legacy_call = native.g4irsf11_event_runtime_from_records

        class _FrozenNativeAdapter:
            __file__ = str(binary.resolve(strict=True))

            @staticmethod
            def g4irsf11_event_runtime_from_records(*args: Any) -> Any:
                return _call_frozen_e0_append_only_adapter(
                    legacy_call, args
                )

        adapter = _FrozenNativeAdapter()
        cpp_backend.load_cpp_module = lambda _search_path=None: adapter
    elif role != "new":
        raise MicrophaseError(f"invalid E0 oracle role: {role}")

    executor = cpp_backend.g4irsf11_event_runtime_from_records
    capabilities = g13.inspect_runtime(executor)
    base = _runtime_base_kwargs(
        case,
        binary=binary,
        search_path=binary.parent,
        root=root,
        config_sha256=canonical_sha256(controls),
    )
    request, blockers = g13.bind_runtime_request(
        capabilities,
        base,
        controls,
        summary_only=False,
    )
    if blockers:
        raise MicrophaseError(
            "E0_ORACLE_RUNTIME_BIND_FAIL:" + " | ".join(blockers)
        )
    # The shared binder historically uses zero event rows for non-summary
    # diagnostics.  The oracle instead captures both event and decision traces
    # without a cap so their complete content participates in the exact hash.
    request["summary_only"] = False
    request["trace_limit"] = -1
    request["event_trace_limit"] = -1
    request["trace_shard_count"] = 1
    request["trace_shard_index"] = 0
    payload = executor(**request)
    if not isinstance(payload, Mapping):
        raise MicrophaseError("E0 oracle runtime returned a non-object payload")
    return _e0_oracle_projection(
        payload,
        role=role,
        tier=tier,
        selection=selection,
        expected_binary=binary_identity,
    )


def _decode_e0_oracle_child(
    completed: subprocess.CompletedProcess[str],
    *,
    role: str,
    tier: str,
) -> dict[str, Any]:
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip().replace("\n", " ")
        raise MicrophaseError(
            "E0_ORACLE_CHILD_FAILED:"
            f"role={role}:tier={tier}:exit={completed.returncode}:"
            f"stderr={stderr[:1000]}"
        )
    try:
        value = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise MicrophaseError(
            f"E0_ORACLE_CHILD_INVALID_JSON:role={role}:tier={tier}"
        ) from exc
    if not isinstance(value, dict):
        raise MicrophaseError(
            f"E0_ORACLE_CHILD_NONOBJECT:role={role}:tier={tier}"
        )
    if (
        value.get("schema") != E0_ORACLE_SCHEMA
        or value.get("role") != role
        or value.get("tier") != tier
    ):
        raise MicrophaseError(
            f"E0_ORACLE_CHILD_IDENTITY_MISMATCH:role={role}:tier={tier}"
        )
    return value


def _compare_e0_oracle_pair(
    frozen: Mapping[str, Any],
    new: Mapping[str, Any],
    *,
    tier: str,
) -> dict[str, Any]:
    for label, value, role in (
        ("frozen", frozen, "frozen"),
        ("new", new, "new"),
    ):
        if (
            value.get("schema") != E0_ORACLE_SCHEMA
            or value.get("role") != role
            or value.get("tier") != tier
            or value.get("extension_fields_absent") is not True
        ):
            raise MicrophaseError(
                f"E0_ORACLE_{label.upper()}_IDENTITY_INVALID:tier={tier}"
            )
    if frozen.get("selection") != new.get("selection"):
        raise MicrophaseError(
            f"E0_ORACLE_COHORT_MISMATCH:tier={tier}"
        )
    if frozen.get("controls_sha256") != new.get("controls_sha256"):
        raise MicrophaseError(
            f"E0_ORACLE_CONTROL_MISMATCH:tier={tier}"
        )
    if frozen.get("excluded_summary_fields") != new.get(
        "excluded_summary_fields"
    ):
        raise MicrophaseError(
            f"E0_ORACLE_EXCLUSION_MISMATCH:tier={tier}"
        )
    for field in (
        "bags_count",
        "junction_state_count",
        "trace_lengths",
        *E0_ORACLE_PROJECTION_HASH_FIELDS,
    ):
        if frozen.get(field) != new.get(field):
            raise MicrophaseError(
                "E0_FROZEN_ORACLE_MISMATCH:"
                f"tier={tier}:field={field}:"
                f"frozen={frozen.get(field)}:new={new.get(field)}"
            )
    return {
        "tier": tier,
        "selection": dict(frozen["selection"]),
        "frozen_projection_sha256": frozen[
            "algorithm_projection_sha256"
        ],
        "new_projection_sha256": new["algorithm_projection_sha256"],
        "projection_hashes": {
            field: frozen[field]
            for field in E0_ORACLE_PROJECTION_HASH_FIELDS
        },
        "bags_count": frozen["bags_count"],
        "junction_state_count": frozen["junction_state_count"],
        "trace_lengths": dict(frozen["trace_lengths"]),
    }


def _execute_e0_oracle_projection_matrix(
    *,
    new_binary: Path,
    frozen_binary: Path,
    root: Path,
    tiers: Sequence[str] = E0_ORACLE_TIERS,
    timeout_seconds: float = 300.0,
    run_child: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    after_child: Callable[[str, str], None] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, str]]:
    """Execute exactly old/new x motif/144 in isolated child processes."""

    if tuple(tiers) != E0_ORACLE_TIERS:
        raise MicrophaseError(
            f"E0 oracle tiers must be exactly {E0_ORACLE_TIERS}"
        )
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0.0:
        raise MicrophaseError("E0 oracle timeout must be positive and finite")
    new_identity = _binary_identity(new_binary)
    frozen_path = frozen_binary.resolve(strict=True)
    frozen_identity = _binary_identity(frozen_path)
    if os.path.normcase(new_identity["path"]) == os.path.normcase(
        frozen_identity["path"]
    ):
        raise MicrophaseError(
            "E0 oracle new and frozen binaries must be different files"
        )

    comparisons: list[dict[str, Any]] = []
    for tier in tiers:
        projections: dict[str, dict[str, Any]] = {}
        for role, binary in (
            ("frozen", frozen_path),
            ("new", new_binary.resolve(strict=True)),
        ):
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--e0-oracle-child",
                "--e0-oracle-role",
                role,
                "--e0-oracle-tier",
                tier,
                "--binary",
                str(binary),
                "--output-root",
                str(root),
            ]
            try:
                completed = run_child(
                    command,
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise MicrophaseError(
                    f"E0_ORACLE_CHILD_LAUNCH_FAILED:role={role}:tier={tier}"
                ) from exc
            projection = _decode_e0_oracle_child(
                completed, role=role, tier=tier
            )
            expected_identity = (
                frozen_identity if role == "frozen" else new_identity
            )
            if projection.get("binary") != expected_identity:
                raise MicrophaseError(
                    f"E0_ORACLE_CHILD_BINARY_DRIFT:role={role}:tier={tier}"
                )
            projections[role] = projection
            if after_child is not None:
                after_child(role, tier)
        comparisons.append(
            _compare_e0_oracle_pair(
                projections["frozen"], projections["new"], tier=tier
            )
        )
        if _binary_identity(frozen_path) != frozen_identity:
            raise MicrophaseError("E0_ORACLE_FROZEN_BINARY_DRIFT_DURING_RUN")
        if _binary_identity(new_binary) != new_identity:
            raise MicrophaseError("E0_ORACLE_NEW_BINARY_DRIFT_DURING_RUN")
    return comparisons, frozen_identity, new_identity


def run_e0_frozen_oracle(
    *,
    new_binary: Path,
    frozen_binary: Mapping[str, str],
    source_history: Mapping[str, Any],
    root: Path,
    tiers: Sequence[str] = E0_ORACLE_TIERS,
    timeout_seconds: float = 300.0,
    run_child: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Run independent old/new processes and fail on any algorithm drift."""

    observed_source_history = execution_source_history_identity(root)
    if observed_source_history != dict(source_history):
        raise MicrophaseError("E0_ORACLE_EXECUTION_SOURCE_HISTORY_DRIFT")
    frozen_path = Path(frozen_binary["physical_path"]).resolve(strict=True)
    if file_sha256(frozen_path) != frozen_binary.get("artifact_sha256"):
        raise MicrophaseError("E0_ORACLE_FROZEN_BINARY_DRIFT_BEFORE_RUN")

    def assert_source_history(role: str, tier: str) -> None:
        if execution_source_history_identity(root) != dict(source_history):
            raise MicrophaseError(
                "E0_ORACLE_EXECUTION_SOURCE_HISTORY_DRIFT_DURING_RUN:"
                f"role={role}:tier={tier}"
            )

    comparisons, frozen_identity, new_identity = (
        _execute_e0_oracle_projection_matrix(
            new_binary=new_binary,
            frozen_binary=frozen_path,
            root=root,
            tiers=tiers,
            timeout_seconds=timeout_seconds,
            run_child=run_child,
            after_child=assert_source_history,
        )
    )
    if frozen_identity["sha256"] != frozen_binary.get("artifact_sha256"):
        raise MicrophaseError("E0_ORACLE_FROZEN_BINARY_DRIFT_DURING_RUN")

    certificate: dict[str, Any] = {
        "schema": E0_ORACLE_CERTIFICATE_SCHEMA,
        "status": "PASS_EXACT_EXTERNAL_ORACLE",
        "process_isolation": "one_named_pyd_per_child_process",
        "tiers": list(tiers),
        "controls": _e0_oracle_controls(),
        "controls_sha256": canonical_sha256(_e0_oracle_controls()),
        "frozen_binary": dict(frozen_binary),
        "new_binary": new_identity,
        "execution_git_commit_sha": source_history["git_commit_sha"],
        "working_source_bundle": dict(
            source_history["working_source_bundle"]
        ),
        "git_source_bundle": dict(source_history["git_source_bundle"]),
        "source_history_clean_gate": dict(source_history["clean_gate"]),
        "excluded_summary_fields": sorted(
            E0_ORACLE_EXCLUDED_SUMMARY_FIELDS
        ),
        "extension_fields_required_absent": True,
        "comparisons": comparisons,
    }
    certificate["certificate_sha256"] = canonical_sha256(certificate)
    return certificate


def rerun_committed_e0_frozen_oracle(
    certificate: Mapping[str, Any],
    *,
    root: Path,
    new_binary_override: Path | None = None,
    frozen_binary_override: Path | None = None,
    timeout_seconds: float = 300.0,
    run_child: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Re-execute the committed oracle; signatures alone do not pass."""

    recorded_new = certificate.get("new_binary")
    recorded_frozen = certificate.get("frozen_binary")
    if not isinstance(recorded_new, Mapping) or not isinstance(
        recorded_frozen, Mapping
    ):
        raise MicrophaseError("COMMITTED_E0_ORACLE_BINARY_BINDING_MISSING")

    def resolve_binary(
        override: Path | None,
        recorded_path: Any,
        *,
        label: str,
    ) -> Path:
        if override is None and (
            not isinstance(recorded_path, str)
            or not recorded_path
            or not Path(recorded_path).is_absolute()
        ):
            raise MicrophaseError(
                f"COMMITTED_E0_ORACLE_{label}_BINARY_PATH_MISSING"
            )
        candidate = override if override is not None else Path(recorded_path)
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise MicrophaseError(
                f"COMMITTED_E0_ORACLE_{label}_BINARY_MISSING"
            ) from exc
        if not resolved.is_file():
            raise MicrophaseError(
                f"COMMITTED_E0_ORACLE_{label}_BINARY_MISSING"
            )
        return resolved

    new_binary = resolve_binary(
        new_binary_override,
        recorded_new.get("path"),
        label="NEW",
    )
    frozen_binary = resolve_binary(
        frozen_binary_override,
        recorded_frozen.get("physical_path"),
        label="FROZEN",
    )
    if file_sha256(new_binary) != recorded_new.get("sha256"):
        raise MicrophaseError("COMMITTED_E0_ORACLE_NEW_BINARY_SHA256_DRIFT")
    if file_sha256(frozen_binary) != recorded_frozen.get(
        "physical_sha256"
    ):
        raise MicrophaseError("COMMITTED_E0_ORACLE_FROZEN_BINARY_SHA256_DRIFT")
    comparisons, frozen_identity, new_identity = (
        _execute_e0_oracle_projection_matrix(
            new_binary=new_binary,
            frozen_binary=frozen_binary,
            root=root,
            timeout_seconds=timeout_seconds,
            run_child=run_child,
        )
    )
    if (
        frozen_identity["sha256"] != recorded_frozen.get("physical_sha256")
        or new_identity["sha256"] != recorded_new.get("sha256")
        or comparisons != certificate.get("comparisons")
    ):
        raise MicrophaseError(
            "COMMITTED_E0_ORACLE_EXTERNAL_REPLAY_MISMATCH"
        )
    return {
        "status": "PASS_EXACT_EXTERNAL_ORACLE_REPLAY",
        "child_process_count": 4,
        "comparisons": comparisons,
        "frozen_binary_sha256": frozen_identity["sha256"],
        "new_binary_sha256": new_identity["sha256"],
    }


def experiment_identity(
    case: RuntimeCase,
    controls: Mapping[str, Any],
    *,
    binary: Path,
    executor: Callable[..., Mapping[str, Any]],
    phase_a_identity: Mapping[str, Any],
    root: Path = ROOT,
) -> dict[str, Any]:
    capabilities = g13.inspect_runtime(executor)
    return {
        "schema": PROTOCOL_SCHEMA,
        "case": {
            "mode": case.mode,
            "tier": case.tier,
            "case_id": case.case_id,
        },
        "selection": {
            "selection_id": case.selection.selection_id,
            "tier": case.selection.tier,
            "segment_count": case.selection.segment_count,
            "raw_bag_count": case.selection.raw_bag_count,
            "selected_rows_sha256": case.selection.selected_rows_sha256,
            "selected_segment_ids_sha256": (
                case.selection.selected_segment_ids_sha256
            ),
            "provenance": dict(case.selection.provenance),
        },
        "controls": dict(controls),
        "controls_sha256": canonical_sha256(controls),
        "protected_inputs": {
            "map_path": MAP_PATH.as_posix(),
            "map_raw_sha256": CANONICAL_MAP_RAW_SHA256,
            "map_semantic_sha256": CANONICAL_MAP_SEMANTIC_SHA256,
            "task_path": TASK_PATH.as_posix(),
            "task_raw_sha256": CANONICAL_SOURCE_RAW_SHA256,
            "map_topology_mutated": False,
            "task_rows_mutated": False,
            "scale": 1.0,
            "fault_windows": [],
        },
        "phase_a": dict(phase_a_identity),
        "binary": _binary_identity(binary),
        "source_bundle": source_bundle_identity(root),
        "executor": {
            "source_path": capabilities.source_path,
            "source_sha256": capabilities.source_sha256,
            "parameters_sha256": canonical_sha256(
                capabilities.parameters
            ),
        },
        "architecture_contract": {
            "one_edge_only": True,
            "reservation_depth": 1,
            "runtime_astar_allowed": False,
            "future_route_allowed": False,
            "global_reservation_scan_allowed": False,
            "same_timestamp_only": True,
            "nonzero_batch_window_allowed": False,
            "all_node_scan_allowed": False,
            "destination_merge_grant_enabled": False,
        },
    }


def _runtime_base_kwargs(
    case: RuntimeCase,
    *,
    binary: Path,
    search_path: Path,
    root: Path,
    config_sha256: str,
) -> dict[str, Any]:
    nodes, edges, heuristic = canonical_graph_records(
        assert_canonical_map(root / MAP_PATH)
    )
    return {
        "node_records": nodes,
        "edge_records": edges,
        "heuristic_time": heuristic,
        "bag_records": [
            (
                str(row["segment_id"]),
                int(row["task_id"]),
                float(row["pass_time"]),
                float(row["std"]),
                int(row["start"]),
                int(row["goal"]),
                str(row.get("source", f"node_{int(row['start'])}")),
            )
            for row in case.selection.rows
        ],
        "input_rows": [dict(row) for row in case.selection.rows],
        "fault_windows": [],
        "scenario": f"g4irsf14_event_microphase_{case.case_id}",
        "scale": 1.0,
        "expected_binary_path": str(binary.resolve(strict=True)),
        "search_path": search_path.resolve(strict=True),
        "input_selection_sha256": case.selection.selected_rows_sha256,
        "case_config_sha256": config_sha256,
    }


def bind_runtime_request(
    executor: Callable[..., Mapping[str, Any]],
    case: RuntimeCase,
    controls: Mapping[str, Any],
    *,
    binary: Path,
    search_path: Path,
    root: Path,
) -> dict[str, Any]:
    capabilities = g13.inspect_runtime(executor)
    required = {
        "event_semantics",
        "enable_opportunity_telemetry",
        "opportunity_trace_limit",
    }
    missing = [
        name
        for name in sorted(required)
        if capabilities.parameter(name) is None
    ]
    if missing:
        raise MicrophaseError(
            "MISSING_RUNTIME_CAPABILITY:" + ",".join(missing)
        )
    base = _runtime_base_kwargs(
        case,
        binary=binary,
        search_path=search_path,
        root=root,
        config_sha256=canonical_sha256(controls),
    )
    request, blockers = g13.bind_runtime_request(
        capabilities,
        base,
        controls,
        summary_only=True,
    )
    if blockers:
        raise MicrophaseError(" | ".join(blockers))
    return request


def _timestamp_bits(value: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", value))[0]


def _validate_telemetry_rows(
    payload: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any], list[str]]:
    decoded: dict[str, list[dict[str, Any]]] = {}
    counts: dict[str, Any] = {}
    blockers: list[str] = []
    for array_name, required_fields in TELEMETRY_ARRAYS.items():
        value = payload.get(array_name)
        if not isinstance(value, list) or not all(
            isinstance(row, Mapping) for row in value
        ):
            raise MicrophaseError(
                f"payload.{array_name} must be an object array"
            )
        rows = [dict(row) for row in value]
        for index, row in enumerate(rows):
            missing = [
                field for field in required_fields if field not in row
            ]
            if missing:
                raise MicrophaseError(
                    f"{array_name}[{index}] missing fields: {missing}"
                )
            event_time = _finite(
                row["event_time"], f"{array_name}[{index}].event_time"
            )
            bits = _strict_int(
                row["timestamp_bits"],
                f"{array_name}[{index}].timestamp_bits",
            )
            if bits != _timestamp_bits(event_time):
                raise MicrophaseError(
                    f"{array_name}[{index}] timestamp bits mismatch"
                )
            _strict_int(
                row["event_seq"], f"{array_name}[{index}].event_seq"
            )
        decoded[array_name] = rows
        total_name, stored_name, dropped_name = TELEMETRY_COUNTERS[
            array_name
        ]
        missing_counters = [
            name
            for name in (total_name, stored_name, dropped_name)
            if name not in summary
        ]
        if missing_counters:
            blockers.append(
                "MISSING_TELEMETRY_COUNTERS:"
                + array_name
                + ":"
                + ",".join(missing_counters)
            )
            counts[array_name] = {
                "total": None,
                "stored": len(rows),
                "dropped": None,
            }
            continue
        total = _strict_int(summary[total_name], total_name)
        stored = _strict_int(summary[stored_name], stored_name)
        dropped = _strict_int(summary[dropped_name], dropped_name)
        if min(total, stored, dropped) < 0:
            blockers.append(f"NEGATIVE_TELEMETRY_COUNTER:{array_name}")
        if stored != len(rows):
            blockers.append(
                f"TELEMETRY_STORED_LENGTH_MISMATCH:{array_name}"
            )
        if total != stored + dropped:
            blockers.append(
                f"TELEMETRY_ACCOUNTING_MISMATCH:{array_name}"
            )
        if dropped:
            blockers.append(
                f"TELEMETRY_TRUNCATED:{array_name}:dropped={dropped}"
            )
        counts[array_name] = {
            "total": total,
            "stored": stored,
            "dropped": dropped,
        }
    return decoded, counts, blockers


def _loaded_binary_blockers(
    payload: Mapping[str, Any],
    summary: Mapping[str, Any],
    expected: Mapping[str, str],
) -> list[str]:
    actual_hash = str(
        summary.get(
            "loaded_cpp_binary_sha256",
            payload.get("loaded_cpp_binary_sha256", ""),
        )
    ).lower()
    actual_path = str(
        summary.get(
            "loaded_cpp_binary_path",
            payload.get("loaded_cpp_binary_path", ""),
        )
    )
    blockers: list[str] = []
    if actual_hash != expected["sha256"].lower():
        blockers.append("LOADED_BINARY_SHA256_MISMATCH")
    try:
        left = os.path.normcase(str(Path(expected["path"]).resolve(strict=True)))
        right = os.path.normcase(str(Path(actual_path).resolve(strict=True)))
        if left != right:
            blockers.append("LOADED_BINARY_PATH_MISMATCH")
    except (OSError, ValueError, RuntimeError):
        blockers.append("LOADED_BINARY_PATH_INVALID")
    return blockers


def _event_mode_blockers(
    payload: Mapping[str, Any],
    summary: Mapping[str, Any],
    mode: str,
    controls: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    expected = {
        "event_semantics": mode,
        "event_semantics_echo": mode,
        "opportunity_telemetry_enabled": True,
        "resource_semantics_echo": FROZEN_CONTROL["resource_semantics"],
        "scorer_mode_echo": FROZEN_CONTROL["scorer_mode"],
        "pibt_mode_echo": FROZEN_CONTROL["pibt_mode"],
        "priority_mode_echo": FROZEN_CONTROL["priority_mode"],
        "framework_mode_echo": FROZEN_CONTROL["framework_mode"],
        "admission_mode_echo": FROZEN_CONTROL["admission_mode"],
        "pressure_mode_echo": FROZEN_CONTROL["pressure_mode"],
        "pibt_preference_mode_echo": FROZEN_CONTROL[
            "pibt_preference_mode"
        ],
    }
    for name, wanted in expected.items():
        if name not in summary:
            blockers.append(f"MISSING_RUNTIME_ECHO:{name}")
            continue
        actual = summary[name]
        if type(actual) is not type(wanted) or actual != wanted:
            blockers.append(
                f"RUNTIME_ECHO_MISMATCH:{name}={actual!r},expected={wanted!r}"
            )
    trace_context = payload.get("trace_context")
    if not isinstance(trace_context, Mapping):
        blockers.append("MISSING_TRACE_CONTEXT")
    else:
        trace_expected = {
            "event_semantics": mode,
            "event_semantics_echo": mode,
            "opportunity_telemetry_enabled": True,
            "event_timestamp_grouping": (
                "exact_double_bits_or_numeric_epsilon_1e-9"
            ),
            "local_arbitration_key": (
                "node,timestamp_bits,wakeup_generation"
            ),
            "stale_arbitration_event_semantics": (
                "valid_generation_arbitration_executed_against_stale_"
                "runtime_state"
            ),
            "superseded_arbitration_event_rejected_semantics": (
                "generation_or_pending_mismatch_rejected_before_"
                "arbitration_execution"
            ),
            "arbitration_worklist_scope": (
                "event_triggered_active_nodes_only_no_all_node_scan"
            ),
            "event_queue_inspection_scope": (
                "passive_opportunity_audit_only_not_runtime_feature_or_"
                "reservation_scan"
            ),
            "destination_competitor_visibility_semantics": (
                "outgoing_edge_potential_competitor_upper_bound_not_"
                "selected_route_or_grant"
            ),
            "priority_comparison_semantics": PRIORITY_COMPARISON_SEMANTICS,
            "opportunity_trace_limit": controls[
                "opportunity_trace_limit"
            ],
            "artificial_batch_delay_seconds": 0.0,
            "destination_merge_grant_enabled": False,
        }
        for name, wanted in trace_expected.items():
            if trace_context.get(name) != wanted:
                blockers.append(f"TRACE_CONTEXT_MISMATCH:{name}")
    return blockers


def _telemetry_invariant_blockers(
    summary: Mapping[str, Any],
    counts: Mapping[str, Mapping[str, Any]],
    case: RuntimeCase,
) -> list[str]:
    """Check exact accounting identities for telemetry-on executions."""

    blockers: list[str] = []
    total_by_array = {
        name: values.get("total")
        for name, values in counts.items()
        if isinstance(values, Mapping)
    }
    if any(
        not isinstance(value, int) or isinstance(value, bool)
        for value in total_by_array.values()
    ):
        # Per-array validation already emits the precise missing-counter errors.
        return blockers
    source_total = int(
        total_by_array["source_admission_opportunities"]
    )
    junction_total = int(
        total_by_array["junction_arbitration_opportunities"]
    )
    merge_total = int(total_by_array["merge_request_visibility"])
    seq_total = int(total_by_array["event_seq_ordering_audit"])
    batch_total = int(
        total_by_array["arbitration_batch_cardinality"]
    )
    if "decision_count" not in summary:
        blockers.append("MISSING_REQUIRED_COUNTER:decision_count")
    else:
        decision_count = _strict_int(
            summary["decision_count"], "decision_count"
        )
        if merge_total != decision_count:
            blockers.append(
                "TELEMETRY_CONSERVATION_MERGE_DECISION:"
                f"merge={merge_total},decision={decision_count}"
            )
    if batch_total != source_total + junction_total:
        blockers.append(
            "TELEMETRY_CONSERVATION_BATCH:"
            f"batch={batch_total},source={source_total},"
            f"junction={junction_total}"
        )
    expected_seq = source_total + junction_total + merge_total
    if seq_total != expected_seq:
        blockers.append(
            "TELEMETRY_CONSERVATION_EVENT_SEQ:"
            f"seq={seq_total},expected={expected_seq}"
        )
    inspection_name = "opportunity_event_queue_inspection_count"
    if inspection_name not in summary:
        blockers.append(f"MISSING_REQUIRED_COUNTER:{inspection_name}")
    else:
        inspection = _strict_int(summary[inspection_name], inspection_name)
        if inspection != seq_total:
            blockers.append(
                "TELEMETRY_CONSERVATION_QUEUE_INSPECTION:"
                f"inspection={inspection},seq={seq_total}"
            )
    if case.selection.segment_count > 0 and all(
        value == 0 for value in total_by_array.values()
    ):
        blockers.append("NONEMPTY_WORKLOAD_HAS_ALL_ZERO_TELEMETRY")
    return blockers


def _safety_blockers(
    payload: Mapping[str, Any],
    summary: Mapping[str, Any],
    timing: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    counters = g13._counter_projection(payload, summary)
    blockers: list[str] = []
    if timing.get("comparison_eligible") is not True:
        blockers.append("INCOMPLETE_DRAIN")
    required_zero = (
        "failed_segment_count",
        "conflict_count",
        "unsafe_entry_count",
        "runtime_full_astar_calls",
        "global_reservation_scan_count",
        "future_routes_stored",
        "unresolved_deadlock_count",
        "priority_teacher_input_count",
        "priority_future_route_input_count",
        "priority_global_scan_count",
    )
    for name in required_zero:
        value = counters.get(name)
        if value is None:
            blockers.append(f"MISSING_REQUIRED_COUNTER:{name}")
        elif int(value) != 0:
            blockers.append(f"{name.upper()}={value}")
    for name in ("event_limit_reached", "time_limit_reached"):
        value = counters.get(name)
        if value is None:
            blockers.append(f"MISSING_REQUIRED_COUNTER:{name}")
        elif value is not False:
            blockers.append(f"{name.upper()}=true")
    if counters.get("reservation_depth") != 1:
        blockers.append(f"RESERVATION_DEPTH={counters.get('reservation_depth')}")
    max_edges = counters.get("max_edges_selected_per_arrive")
    if max_edges is None:
        blockers.append(
            "MISSING_REQUIRED_COUNTER:max_edges_selected_per_arrive"
        )
    elif int(max_edges) > 1:
        blockers.append(f"MAX_EDGES_PER_ARRIVE={max_edges}")
    extension_zero = (
        "stale_arbitration_event_count",
        "microphase_runtime_global_scan_count",
    )
    for name in extension_zero:
        if name not in summary:
            blockers.append(f"MISSING_REQUIRED_COUNTER:{name}")
        elif _strict_int(summary[name], name) != 0:
            blockers.append(f"{name.upper()}={summary[name]}")
    rejected_name = "superseded_arbitration_event_rejected_count"
    if rejected_name not in summary:
        blockers.append(f"MISSING_REQUIRED_COUNTER:{rejected_name}")
    elif _strict_int(summary[rejected_name], rejected_name) < 0:
        blockers.append(f"NEGATIVE_REQUIRED_COUNTER:{rejected_name}")
    delay = summary.get("artificial_batch_delay_seconds")
    if delay is None:
        blockers.append("MISSING_REQUIRED_COUNTER:artificial_batch_delay_seconds")
    elif _finite(delay, "artificial_batch_delay_seconds") != 0.0:
        blockers.append(f"ARTIFICIAL_BATCH_DELAY_SECONDS={delay}")
    for name in (
        "events",
        "decisions",
        "decision_trace",
        "hold_attempts",
        "pibt_events",
        "credit_events",
        "fault_events",
    ):
        value = payload.get(name, [])
        if isinstance(value, list) and value:
            blockers.append(f"UNEXPECTED_SUMMARY_ONLY_TRACE:{name}={len(value)}")
    return counters, blockers


def _runtime_bag_maps(
    bags: Sequence[Mapping[str, Any]],
) -> tuple[dict[int, int], dict[int, str]]:
    task_by_runtime: dict[int, int] = {}
    segment_by_runtime: dict[int, str] = {}
    for row in bags:
        runtime = row.get("runtime_bag_id")
        task = row.get("task_id")
        if isinstance(runtime, int) and not isinstance(runtime, bool):
            if isinstance(task, int) and not isinstance(task, bool):
                task_by_runtime[runtime] = task
            segment_by_runtime[runtime] = str(row.get("segment_id", ""))
    return task_by_runtime, segment_by_runtime


def _telemetry_metrics(
    arrays: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    source = arrays["source_admission_opportunities"]
    junction = arrays["junction_arbitration_opportunities"]
    merge = arrays["merge_request_visibility"]
    seq = arrays["event_seq_ordering_audit"]
    batch = arrays["arbitration_batch_cardinality"]
    source_priority = sum(
        int(row["priority_comparison_count"]) > 0 for row in source
    )
    junction_priority = sum(
        int(row["priority_comparison_count"]) > 0 for row in junction
    )
    return {
        "source_opportunity_count": len(source),
        "junction_opportunity_count": len(junction),
        "merge_visibility_count": len(merge),
        "event_seq_audit_count": len(seq),
        "arbitration_batch_count": len(batch),
        "ready_set_singleton_count": sum(
            int(row["ready_set_size"]) == 1 for row in [*source, *junction]
        ),
        "ready_set_multi_count": sum(
            int(row["ready_set_size"]) > 1 for row in [*source, *junction]
        ),
        "q0_actual_priority_comparator_opportunity_count": (
            source_priority + junction_priority
        ),
        "source_q0_actual_priority_comparator_opportunity_count": (
            source_priority
        ),
        "junction_q0_actual_priority_comparator_opportunity_count": (
            junction_priority
        ),
        "same_time_unseen_competitor_count": sum(
            int(row["same_time_pending_source_releases"]) > 0
            for row in source
        )
        + sum(
            int(row["same_time_pending_arrivals"]) > 0
            for row in junction
        ),
        "shared_merge_pending_count": sum(
            int(row["same_time_pending_shared_merge_releases"]) > 0
            for row in source
        )
        + sum(
            int(row["same_time_pending_shared_merge_requests"]) > 0
            for row in junction
        ),
        "merge_request_collision_count": sum(
            int(row["known_competing_request_count"]) > 0
            or int(row["later_same_time_competitor_count"]) > 0
            for row in merge
        ),
        "merge_known_competitor_count": sum(
            int(row["known_competing_request_count"]) > 0 for row in merge
        ),
        "merge_later_unseen_count": sum(
            bool(row["later_same_time_competitor_exists"]) for row in merge
        ),
        "event_seq_determined_local_reservation_order_proxy_count": sum(
            bool(row["seq_determined_order"]) for row in merge
        ),
        "event_seq_determined_order_count": sum(
            bool(row["seq_determined_order"]) for row in seq
        ),
        "pibt_applicable_opportunity_count": sum(
            int(row["pibt_slice_bag_count"]) > 0 for row in junction
        ),
        "pibt_multi_bag_slice_count": sum(
            int(row["pibt_slice_bag_count"]) > 1 for row in junction
        ),
        "pibt_owner_visible_count": sum(
            int(row["pibt_owner_count"]) > 0 for row in junction
        ),
        "pibt_feasible_slice_proxy_count": sum(
            int(row["pibt_slice_bag_count"]) > 1
            and int(row["pibt_owner_count"]) > 0
            for row in junction
        ),
        "batched_multi_enqueue_count": sum(
            int(row["enqueue_count"]) > 1 for row in batch
        ),
        "max_batch_enqueue_count": max(
            [int(row["enqueue_count"]) for row in batch], default=0
        ),
    }


def validate_runtime_payload(
    payload: Mapping[str, Any],
    case: RuntimeCase,
    controls: Mapping[str, Any],
    *,
    expected_binary: Mapping[str, str],
) -> dict[str, Any]:
    summary = payload.get("summary")
    if not isinstance(summary, Mapping):
        raise MicrophaseError("runtime payload.summary must be an object")
    bags = payload.get("bags")
    if not isinstance(bags, list) or not all(
        isinstance(row, Mapping) for row in bags
    ):
        raise MicrophaseError("runtime payload.bags must be an object array")
    raw_bags = g12.aggregate_raw_bag_timings(case.selection.rows, bags)
    timing = g12.summarize_raw_bag_timings(
        raw_bags, selected_segment_count=case.selection.segment_count
    )
    arrays, telemetry_counts, telemetry_blockers = (
        _validate_telemetry_rows(payload, summary)
    )
    telemetry_invariant_blockers = _telemetry_invariant_blockers(
        summary, telemetry_counts, case
    )
    counters, safety_blockers = _safety_blockers(payload, summary, timing)
    blockers = [
        *_loaded_binary_blockers(payload, summary, expected_binary),
        *_event_mode_blockers(payload, summary, case.mode, controls),
        *telemetry_blockers,
        *telemetry_invariant_blockers,
        *safety_blockers,
    ]
    metrics = _telemetry_metrics(arrays)
    return {
        "timing": timing,
        "counters": counters,
        "summary": dict(summary),
        "trace_context": (
            dict(payload["trace_context"])
            if isinstance(payload.get("trace_context"), Mapping)
            else {}
        ),
        "telemetry_counts": telemetry_counts,
        "telemetry_metrics": metrics,
        "arrays": arrays,
        "bags": [dict(row) for row in bags],
        "blockers": sorted(set(blockers)),
        "gate_status": "PASS" if not blockers else "FAIL",
        "controls_sha256": canonical_sha256(controls),
    }


def _minhash_samples(
    rows: Sequence[Mapping[str, Any]],
    *,
    limit: int = DETERMINISTIC_SAMPLE_COUNT,
) -> list[dict[str, Any]]:
    ranked = sorted(
        (
            canonical_sha256(row),
            index,
            dict(row),
        )
        for index, row in enumerate(rows)
    )
    return [
        {"sample_rank": rank + 1, "sample_sha256": digest, **row}
        for rank, (digest, _index, row) in enumerate(ranked[:limit])
    ]


def _per_bag_context(root: Path) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for row in _read_csv(root / PER_BAG_PATH):
        task_id = int(row["task_id"])
        result[task_id] = {
            "source": row.get("source", ""),
            "goal": row.get("goal", ""),
            "hour": row.get("hour", ""),
            "bag_class": row.get("bag_class", ""),
            "entry_time_band": row.get("entry_time_band", ""),
            "deadline_slack_bucket": row.get("deadline_slack_bucket", ""),
            "top_1pct_delta": _bool_text(row.get("top_1pct_delta", "")),
            "action_divergence_count": int(
                row.get("action_divergence_count", "0") or 0
            ),
            "pibt_involvement": _bool_text(
                row.get("pibt_involvement", "")
            ),
            "first_divergence_node": row.get(
                "first_divergence_node", ""
            ),
        }
    if len(result) != FULL_SIZE_BAGS:
        raise MicrophaseError(
            f"per-bag context count {len(result)} != {FULL_SIZE_BAGS}"
        )
    return result


def _task_id_for_row(
    row: Mapping[str, Any],
    *,
    task_by_runtime: Mapping[int, int],
) -> int | None:
    for name in ("chosen_task_id", "requesting_task_id"):
        value = row.get(name)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    value = row.get("chosen_runtime_bag_id")
    if isinstance(value, int) and not isinstance(value, bool):
        return task_by_runtime.get(value)
    return None


def _cohort_slices(
    row: Mapping[str, Any],
    *,
    kind: str,
    context: Mapping[int, Mapping[str, Any]],
    task_by_runtime: Mapping[int, int],
    merge_nodes: set[int],
    split_nodes: set[int],
    first_divergence_nodes: set[int],
) -> list[tuple[str, str]]:
    slices: list[tuple[str, str]] = [("all", "all")]
    node_names = {
        "source": ("source_node", "source"),
        "junction": ("junction_node", "junction"),
        "merge": ("destination_node", "destination"),
        "seq": ("node", "node"),
        "batch": ("node", "node"),
    }
    node_field, node_label = node_names[kind]
    node = row.get(node_field)
    if isinstance(node, int) and not isinstance(node, bool) and node >= 0:
        slices.append((f"every_{node_label}", str(node)))
        if node in merge_nodes:
            slices.append(("merge_node", str(node)))
        if node in split_nodes:
            slices.append(("split_node", str(node)))
        if node == 52:
            slices.append(("node_52", "52"))
        if node == 50:
            slices.append(("goal_50_node", "50"))
        if node in first_divergence_nodes:
            slices.append(("first_divergence_node", str(node)))
    task_id = _task_id_for_row(row, task_by_runtime=task_by_runtime)
    bag = context.get(task_id) if task_id is not None else None
    if bag:
        if str(bag["hour"]) == "6":
            slices.append(("hour", "6"))
        if bag["entry_time_band"] == "early":
            slices.append(("entry_time_band", "early"))
        if bag["deadline_slack_bucket"] == "tight":
            slices.append(("deadline_slack", "tight"))
        if bag["bag_class"] == "storage_in_out":
            slices.append(("bag_class", "storage_in_out"))
        if str(bag["goal"]) == "50":
            slices.append(("goal", "50"))
        if bool(bag["top_1pct_delta"]):
            slices.append(("top_1pct_delta", "true"))
        if int(bag["action_divergence_count"]) == 0:
            slices.append(("divergence_cohort", "NO_DIVERGENCE"))
        if bool(bag["pibt_involvement"]):
            slices.append(("pibt_cohort", "P2_INVOLVED"))
    return sorted(set(slices))


def _aggregate_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    kind: str,
    context: Mapping[int, Mapping[str, Any]],
    task_by_runtime: Mapping[int, int],
    merge_nodes: set[int],
    split_nodes: set[int],
    first_divergence_nodes: set[int],
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in rows:
        for key in _cohort_slices(
            row,
            kind=kind,
            context=context,
            task_by_runtime=task_by_runtime,
            merge_nodes=merge_nodes,
            split_nodes=split_nodes,
            first_divergence_nodes=first_divergence_nodes,
        ):
            groups.setdefault(key, []).append(row)
    output: list[dict[str, Any]] = []
    for (slice_type, slice_value), members in sorted(groups.items()):
        ready = [int(row.get("ready_set_size", 0)) for row in members]
        priority = [
            int(row.get("priority_comparison_count", 0)) for row in members
        ]
        result: dict[str, Any] = {
            "row_kind": "AGGREGATE",
            "slice_type": slice_type,
            "slice_value": slice_value,
            "opportunity_count": len(members),
            "ready_set_singleton_count": sum(value == 1 for value in ready),
            "ready_set_multi_count": sum(value > 1 for value in ready),
            "mean_ready_set_size": (
                statistics.fmean(ready) if ready else 0.0
            ),
            "max_ready_set_size": max(ready, default=0),
            "q0_actual_priority_comparator_opportunity_count": sum(
                value > 0 for value in priority
            ),
            "priority_comparison_count": sum(priority),
            "seq_determined_count": sum(
                bool(row.get("seq_determined_order", False))
                for row in members
            ),
        }
        if kind == "source":
            result.update(
                {
                    "same_time_pending_count": sum(
                        int(row["same_time_pending_source_releases"]) > 0
                        for row in members
                    ),
                    "shared_merge_pending_count": sum(
                        int(
                            row[
                                "same_time_pending_shared_merge_releases"
                            ]
                        )
                        > 0
                        for row in members
                    ),
                    "batched_count": sum(
                        bool(row["batched_arbitration"])
                        for row in members
                    ),
                }
            )
        elif kind == "junction":
            result.update(
                {
                    "same_time_pending_count": sum(
                        int(row["same_time_pending_arrivals"]) > 0
                        for row in members
                    ),
                    "shared_merge_pending_count": sum(
                        int(
                            row[
                                "same_time_pending_shared_merge_requests"
                            ]
                        )
                        > 0
                        for row in members
                    ),
                    "pibt_applicable_count": sum(
                        int(row["pibt_slice_bag_count"]) > 0
                        for row in members
                    ),
                    "pibt_multi_bag_slice_count": sum(
                        int(row["pibt_slice_bag_count"]) > 1
                        for row in members
                    ),
                    "pibt_owner_visible_count": sum(
                        int(row["pibt_owner_count"]) > 0
                        for row in members
                    ),
                    "pibt_feasible_slice_proxy_count": sum(
                        int(row["pibt_slice_bag_count"]) > 1
                        and int(row["pibt_owner_count"]) > 0
                        for row in members
                    ),
                    "batched_count": sum(
                        bool(row["batched_arbitration"])
                        for row in members
                    ),
                }
            )
        elif kind == "merge":
            result.update(
                {
                    "known_competitor_count": sum(
                        int(row["known_competing_request_count"]) > 0
                        for row in members
                    ),
                    "later_unseen_competitor_count": sum(
                        bool(row["later_same_time_competitor_exists"])
                        for row in members
                    ),
                    "merge_collision_count": sum(
                        int(row["known_competing_request_count"]) > 0
                        or int(row["later_same_time_competitor_count"]) > 0
                        for row in members
                    ),
                }
            )
        elif kind == "seq":
            result.update(
                {
                    "later_unseen_competitor_count": sum(
                        int(row["later_same_time_competitor_count"]) > 0
                        for row in members
                    ),
                }
            )
        elif kind == "batch":
            enqueue = [int(row["enqueue_count"]) for row in members]
            result.update(
                {
                    "multi_enqueue_count": sum(value > 1 for value in enqueue),
                    "mean_enqueue_count": (
                        statistics.fmean(enqueue) if enqueue else 0.0
                    ),
                    "max_enqueue_count": max(enqueue, default=0),
                    "same_time_pending_count": sum(
                        int(row["pending_same_time_event_count"]) > 0
                        for row in members
                    ),
                }
            )
        output.append(result)
    return output


def compact_telemetry(
    validation: Mapping[str, Any],
    *,
    root: Path,
) -> dict[str, Any]:
    arrays = validation["arrays"]
    bags = validation["bags"]
    task_by_runtime, _segment_by_runtime = _runtime_bag_maps(bags)
    context = _per_bag_context(root)
    topology = g13._graph_topology(root)
    merge_nodes = set(topology["merge_nodes"])
    split_nodes = set(topology["split_nodes"])
    first_divergence_nodes = {
        int(value["first_divergence_node"])
        for value in context.values()
        if str(value["first_divergence_node"]).strip()
    }
    mapping = {
        "source": "source_admission_opportunities",
        "junction": "junction_arbitration_opportunities",
        "merge": "merge_request_visibility",
        "seq": "event_seq_ordering_audit",
        "batch": "arbitration_batch_cardinality",
    }
    result: dict[str, Any] = {}
    for kind, array_name in mapping.items():
        rows = arrays[array_name]
        result[kind] = {
            "aggregates": _aggregate_rows(
                rows,
                kind=kind,
                context=context,
                task_by_runtime=task_by_runtime,
                merge_nodes=merge_nodes,
                split_nodes=split_nodes,
                first_divergence_nodes=first_divergence_nodes,
            ),
            "samples": _minhash_samples(rows),
            "stored_row_sha256": canonical_sha256(rows),
        }
    return result


def _completed_pointer(
    cache_dir: Path, *, expected_cache_key: str
) -> dict[str, Any] | None:
    pointer_path = cache_dir / "complete.json"
    if not pointer_path.is_file():
        return None
    pointer = _read_json(pointer_path)
    if pointer.get("schema") != COMPLETE_SCHEMA:
        raise MicrophaseError("complete pointer schema drift")
    if pointer.get("cache_key") != expected_cache_key:
        raise MicrophaseError("complete pointer cache key drift")
    relative = pointer.get("result_relative_path")
    if not isinstance(relative, str) or not relative:
        raise MicrophaseError("complete pointer lacks result path")
    result_path = cache_dir / relative
    if file_sha256(result_path) != pointer.get("result_file_sha256"):
        raise MicrophaseError("cached compact result hash mismatch")
    raw_relative = pointer.get("raw_archive_relative_path")
    if not isinstance(raw_relative, str) or not raw_relative:
        raise MicrophaseError("complete pointer lacks raw telemetry path")
    raw_path = cache_dir / raw_relative
    if file_sha256(raw_path) != pointer.get("raw_archive_file_sha256"):
        raise MicrophaseError("cached raw telemetry hash mismatch")
    result = _read_json(result_path)
    if result.get("cache_key") != expected_cache_key:
        raise MicrophaseError("cached result cache key drift")
    result["result_file_sha256"] = pointer["result_file_sha256"]
    result["execution_status"] = "CACHED"
    return result


def _not_run_result(
    mode: str,
    tier: str,
    blocker: str,
    *,
    selection: g13.WorkloadSelection | None = None,
) -> dict[str, Any]:
    return {
        "schema": RESULT_SCHEMA,
        "mode": mode,
        "tier": tier,
        "selection_id": selection.selection_id if selection else "",
        "selected_segment_count": selection.segment_count if selection else "",
        "selected_raw_bag_count": selection.raw_bag_count if selection else "",
        "selection_sha256": (
            selection.selected_rows_sha256 if selection else ""
        ),
        "execution_status": "NOT_RUN",
        "gate_status": "NOT_EVALUATED",
        "mechanism_gate": "NOT_EVALUATED",
        "promotion_status": "NOT_AUTHORIZED",
        "blocker": blocker,
        "cache_key": "",
        "result_file_sha256": "",
        "raw_archive_file_sha256": "",
        "raw_payload_canonical_sha256": "",
    }


def execute_case(
    case: RuntimeCase,
    *,
    executor: Callable[..., Mapping[str, Any]],
    binary: Path,
    search_path: Path,
    opportunity_trace_limit: int,
    phase_a_identity: Mapping[str, Any],
    e0_frozen_oracle: Mapping[str, Any] | None = None,
    root: Path = ROOT,
    archive_root: Path | None = None,
    stale_lock_seconds: float = 3_600.0,
) -> dict[str, Any]:
    controls = runtime_controls(
        case.mode, opportunity_trace_limit=opportunity_trace_limit
    )
    try:
        request = bind_runtime_request(
            executor,
            case,
            controls,
            binary=binary,
            search_path=search_path,
            root=root,
        )
    except MicrophaseError as exc:
        return _not_run_result(
            case.mode, case.tier, str(exc), selection=case.selection
        )
    identity = experiment_identity(
        case,
        controls,
        binary=binary,
        executor=executor,
        phase_a_identity=phase_a_identity,
        root=root,
    )
    if e0_frozen_oracle is not None:
        identity["e0_frozen_oracle"] = dict(e0_frozen_oracle)
    key = canonical_sha256(identity)
    local_root = archive_root or (root / LOCAL_ARCHIVE)
    cache_dir = local_root / case.mode / case.tier / key
    cached = _completed_pointer(cache_dir, expected_cache_key=key)
    if cached is not None:
        return cached

    attempt_id = f"{time.time_ns()}-{os.getpid()}"
    attempt_dir = cache_dir / "attempts" / attempt_id
    descriptor_path = attempt_dir / "descriptor.json"
    raw_path = attempt_dir / "raw_payload.json.gz"
    result_path = attempt_dir / "compact_result.json"
    descriptor: dict[str, Any] = {
        "schema": ATTEMPT_SCHEMA,
        "attempt_id": attempt_id,
        "cache_key": key,
        "identity": identity,
        "status": "RUNNING",
        "started_unix_time": time.time(),
        "completed_unix_time": None,
        "blocker": "",
    }
    with g13.AttemptLock(
        cache_dir / "attempt.lock",
        cache_key_value=key,
        stale_seconds=stale_lock_seconds,
    ):
        cached = _completed_pointer(cache_dir, expected_cache_key=key)
        if cached is not None:
            return cached
        atomic_write_json(descriptor_path, descriptor)
        try:
            started = time.perf_counter()
            raw_payload = executor(**request)
            wall_seconds = time.perf_counter() - started
            if not isinstance(raw_payload, Mapping):
                raise MicrophaseError("runtime returned a non-object payload")
            payload = dict(raw_payload)
            raw_canonical_sha, raw_file_sha = atomic_write_gzip_json(
                raw_path, payload
            )
            assert_execution_files_unchanged(
                binary=binary,
                expected_binary=identity["binary"],
                expected_source_bundle=identity["source_bundle"],
                root=root,
            )
            validation = validate_runtime_payload(
                payload,
                case,
                controls,
                expected_binary=identity["binary"],
            )
            compact = compact_telemetry(validation, root=root)
            result = {
                "schema": RESULT_SCHEMA,
                "mode": case.mode,
                "tier": case.tier,
                "selection_id": case.selection.selection_id,
                "selected_segment_count": case.selection.segment_count,
                "selected_raw_bag_count": case.selection.raw_bag_count,
                "selection_sha256": case.selection.selected_rows_sha256,
                "cohort_sha256": (
                    case.selection.selected_segment_ids_sha256
                ),
                "fixed_real_map_only": True,
                "map_topology_mutated": False,
                "task_rows_mutated": False,
                "fault_windows": [],
                "scale": 1.0,
                "controls": controls,
                "controls_sha256": validation["controls_sha256"],
                "cache_key": key,
                "identity_sha256": canonical_sha256(identity),
                "instrumented_binary_path": identity["binary"]["path"],
                "instrumented_binary_sha256": identity["binary"]["sha256"],
                "source_bundle_sha256": identity["source_bundle"][
                    "bundle_sha256"
                ],
                "e0_frozen_oracle": (
                    dict(e0_frozen_oracle)
                    if e0_frozen_oracle is not None
                    else {}
                ),
                "execution_git_commit_sha": (
                    e0_frozen_oracle.get("execution_git_commit_sha", "")
                    if e0_frozen_oracle is not None
                    else ""
                ),
                "execution_working_source_bundle": (
                    dict(e0_frozen_oracle.get("working_source_bundle", {}))
                    if e0_frozen_oracle is not None
                    and isinstance(
                        e0_frozen_oracle.get("working_source_bundle"),
                        Mapping,
                    )
                    else {}
                ),
                "execution_git_source_bundle": (
                    dict(e0_frozen_oracle.get("git_source_bundle", {}))
                    if e0_frozen_oracle is not None
                    and isinstance(
                        e0_frozen_oracle.get("git_source_bundle"), Mapping
                    )
                    else {}
                ),
                "attempt_id": attempt_id,
                "execution_status": "EXECUTED",
                "gate_status": validation["gate_status"],
                "mechanism_gate": "PENDING_BASELINE_COMPARISON",
                "promotion_status": "DIAGNOSTIC_ONLY",
                "blocker": " | ".join(validation["blockers"]),
                "wall_seconds": wall_seconds,
                "timing": validation["timing"],
                "counters": validation["counters"],
                "runtime_summary": validation["summary"],
                "trace_context": validation["trace_context"],
                "telemetry_counts": validation["telemetry_counts"],
                "telemetry_metrics": validation["telemetry_metrics"],
                "compact_telemetry": compact,
                "raw_archive_relative_path": raw_path.relative_to(
                    cache_dir
                ).as_posix(),
                "raw_archive_file_sha256": raw_file_sha,
                "raw_payload_canonical_sha256": raw_canonical_sha,
            }
            atomic_write_json(result_path, result)
            result_file_sha = file_sha256(result_path)
            descriptor.update(
                {
                    "status": "COMPLETE",
                    "completed_unix_time": time.time(),
                    "result_relative_path": result_path.relative_to(
                        cache_dir
                    ).as_posix(),
                    "result_file_sha256": result_file_sha,
                    "raw_archive_relative_path": raw_path.relative_to(
                        cache_dir
                    ).as_posix(),
                    "raw_archive_file_sha256": raw_file_sha,
                    "raw_payload_canonical_sha256": raw_canonical_sha,
                    "blocker": result["blocker"],
                }
            )
            atomic_write_json(descriptor_path, descriptor)
            atomic_write_json(
                cache_dir / "complete.json",
                {
                    "schema": COMPLETE_SCHEMA,
                    "cache_key": key,
                    "attempt_id": attempt_id,
                    "descriptor_relative_path": descriptor_path.relative_to(
                        cache_dir
                    ).as_posix(),
                    "descriptor_file_sha256": file_sha256(descriptor_path),
                    "result_relative_path": result_path.relative_to(
                        cache_dir
                    ).as_posix(),
                    "result_file_sha256": result_file_sha,
                    "raw_archive_relative_path": raw_path.relative_to(
                        cache_dir
                    ).as_posix(),
                    "raw_archive_file_sha256": raw_file_sha,
                    "raw_payload_canonical_sha256": raw_canonical_sha,
                },
            )
            result["result_file_sha256"] = result_file_sha
            return result
        except Exception as exc:  # noqa: BLE001 - preserve negative attempt
            descriptor.update(
                {
                    "status": "FAILED",
                    "completed_unix_time": time.time(),
                    "blocker": f"{type(exc).__name__}: {exc}",
                }
            )
            atomic_write_json(descriptor_path, descriptor)
            return {
                **_not_run_result(
                    case.mode,
                    case.tier,
                    descriptor["blocker"],
                    selection=case.selection,
                ),
                "execution_status": "FAILED",
                "gate_status": "FAIL",
                "promotion_status": "REJECT",
                "cache_key": key,
                "attempt_id": attempt_id,
                "raw_archive_file_sha256": (
                    file_sha256(raw_path) if raw_path.is_file() else ""
                ),
            }


def _timing(result: Mapping[str, Any], name: str) -> float | None:
    timing = result.get("timing")
    if not isinstance(timing, Mapping):
        return None
    value = timing.get(name)
    if value is None or value == "":
        return None
    return _finite(value, f"timing.{name}")


def _metric(result: Mapping[str, Any], name: str) -> int:
    value = result.get("telemetry_metrics")
    if not isinstance(value, Mapping):
        return 0
    raw = value.get(name, 0)
    return _strict_int(raw, f"telemetry_metrics.{name}")


def apply_baseline_comparisons(
    results: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    baselines = {
        str(row.get("tier")): row
        for row in results
        if row.get("mode") == MODE_ORDER[0]
        and row.get("gate_status") == "PASS"
    }
    output: list[dict[str, Any]] = []
    for original in results:
        row = dict(original)
        if row.get("mode") == MODE_ORDER[0]:
            row["mechanism_gate"] = (
                "CONTROL" if row.get("gate_status") == "PASS" else "FAIL"
            )
            output.append(row)
            continue
        # Ladder execution calls this function after each tier and publication
        # calls it once more.  Already classified evidence must remain byte-for-
        # byte stable instead of accumulating duplicate blocker text.
        if row.get("mechanism_gate") in {
            "PASS",
            "FAIL",
            "NOT_EVALUATED",
        } and row.get("mechanism_gate") != "PENDING_BASELINE_COMPARISON":
            output.append(row)
            continue
        baseline = baselines.get(str(row.get("tier")))
        if row.get("gate_status") != "PASS":
            row["mechanism_gate"] = "FAIL"
            row["promotion_status"] = "REJECT"
            output.append(row)
            continue
        if baseline is None:
            row["mechanism_gate"] = "NOT_EVALUATED"
            row["promotion_status"] = "NOT_AUTHORIZED"
            row["blocker"] = " | ".join(
                filter(
                    None,
                    [
                        str(row.get("blocker", "")),
                        "MATCHED_E0_BASELINE_UNAVAILABLE",
                    ],
                )
            )
            output.append(row)
            continue
        mean = _timing(row, "original_entry_mean_minutes")
        base_mean = _timing(baseline, "original_entry_mean_minutes")
        p95 = _timing(row, "original_entry_p95_seconds")
        base_p95 = _timing(baseline, "original_entry_p95_seconds")
        p99 = _timing(row, "original_entry_p99_seconds")
        base_p99 = _timing(baseline, "original_entry_p99_seconds")
        mean_delta = (
            (mean - base_mean) * 60.0
            if mean is not None and base_mean is not None
            else None
        )
        p95_delta = (
            p95 - base_p95
            if p95 is not None and base_p95 is not None
            else None
        )
        p99_delta = (
            p99 - base_p99
            if p99 is not None and base_p99 is not None
            else None
        )
        mechanisms = {
            "q0_actual_priority_comparator_opportunity_increased": _metric(
                row, "q0_actual_priority_comparator_opportunity_count"
            )
            > _metric(
                baseline, "q0_actual_priority_comparator_opportunity_count"
            ),
            "merge_visibility_increased": _metric(
                row, "merge_known_competitor_count"
            )
            > _metric(baseline, "merge_known_competitor_count"),
            "local_reservation_seq_order_proxy_reduced": _metric(
                row,
                "event_seq_determined_local_reservation_order_proxy_count",
            )
            < _metric(
                baseline,
                "event_seq_determined_local_reservation_order_proxy_count",
            ),
            "pibt_feasible_slice_increased": _metric(
                row, "pibt_feasible_slice_proxy_count"
            )
            > _metric(baseline, "pibt_feasible_slice_proxy_count"),
            "mean_or_tail_improved": any(
                value is not None and value < -1.0e-9
                for value in (mean_delta, p95_delta, p99_delta)
            ),
        }
        early_rejects: list[str] = []
        if mean_delta is not None and mean_delta > 1.0:
            early_rejects.append("MEAN_LOSS_GT_1S_PER_BAG")
        if p95_delta is not None and p95_delta > 2.0:
            early_rejects.append("P95_LOSS_GT_2S")
        if p99_delta is not None and p99_delta > 4.0:
            early_rejects.append("P99_LOSS_GT_4S")
        row["delta_vs_e0_mean_seconds_per_bag"] = mean_delta
        row["delta_vs_e0_p95_seconds"] = p95_delta
        row["delta_vs_e0_p99_seconds"] = p99_delta
        row["mechanism_evidence"] = mechanisms
        row["mechanism_gate"] = (
            "PASS" if any(mechanisms.values()) else "FAIL"
        )
        row["early_reject_reasons"] = early_rejects
        if row["mechanism_gate"] == "PASS" and not early_rejects:
            row["promotion_status"] = "ELIGIBLE_FOR_NEXT_TIER"
        else:
            row["promotion_status"] = "REJECT"
            additions = [
                "NO_REQUIRED_MECHANISM_CHANGE"
                if row["mechanism_gate"] != "PASS"
                else "",
                *early_rejects,
            ]
            row["blocker"] = " | ".join(
                filter(None, [str(row.get("blocker", "")), *additions])
            )
        output.append(row)
    return output


def select_best_batched(
    results: Sequence[Mapping[str, Any]], *, tier: str = "8192"
) -> str | None:
    candidates = [
        row
        for row in results
        if row.get("tier") == tier
        and row.get("mode") in BATCHED_MODES
        and row.get("gate_status") == "PASS"
        and row.get("mechanism_gate") == "PASS"
        and row.get("promotion_status") == "ELIGIBLE_FOR_NEXT_TIER"
    ]
    if not candidates:
        return None

    def value(row: Mapping[str, Any], name: str) -> float:
        raw = row.get(name)
        return float(raw) if raw is not None else math.inf

    candidates.sort(
        key=lambda row: (
            value(row, "delta_vs_e0_mean_seconds_per_bag"),
            value(row, "delta_vs_e0_p99_seconds"),
            value(row, "delta_vs_e0_p95_seconds"),
            MODE_ORDER.index(str(row["mode"])),
        )
    )
    return str(candidates[0]["mode"])


def execute_ladder(
    *,
    executor: Callable[..., Mapping[str, Any]],
    binary: Path,
    search_path: Path,
    max_tier: str,
    allow_full: bool,
    opportunity_trace_limit: int,
    root: Path = ROOT,
    archive_root: Path | None = None,
    frozen_binary_override: Path | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    if max_tier not in TIER_ORDER:
        raise MicrophaseError(f"unknown max tier: {max_tier}")
    if max_tier == "full" and not allow_full:
        raise MicrophaseError("full tier requires --allow-full")
    expected_runner_path = (
        root / Path("scripts/eval/g4irsf14_event_microphase.py")
    ).resolve(strict=True)
    if os.path.normcase(str(Path(__file__).resolve(strict=True))) != (
        os.path.normcase(str(expected_runner_path))
    ):
        raise MicrophaseError(
            "EXECUTION_RUNNER_PATH_DOES_NOT_MATCH_OUTPUT_ROOT"
        )
    phase_a_identity = assert_phase_a_and_inputs(
        root, frozen_binary_override=frozen_binary_override
    )
    ladder_binary_identity = _binary_identity(binary)
    source_history = execution_source_history_identity(root)
    ladder_source_bundle = dict(source_history["working_source_bundle"])

    def assert_ladder_identity() -> None:
        assert_execution_files_unchanged(
            binary=binary,
            expected_binary=ladder_binary_identity,
            expected_source_bundle=ladder_source_bundle,
            root=root,
        )

    assert_ladder_identity()
    frozen_binary = _resolve_frozen_binary(
        phase_a_identity,
        root=root,
        override=frozen_binary_override,
    )
    if os.path.normcase(frozen_binary["physical_path"]) == os.path.normcase(
        str(binary.resolve(strict=True))
    ):
        raise MicrophaseError(
            "instrumented runtime must not overwrite/use the frozen "
            "Stage-14A binary path"
        )
    e0_frozen_oracle = run_e0_frozen_oracle(
        new_binary=binary,
        frozen_binary=frozen_binary,
        source_history=source_history,
        root=root,
    )
    assert_ladder_identity()
    maximum_small_index = (
        len(SMALL_TIER_ORDER) - 1
        if max_tier == "full"
        else SMALL_TIER_ORDER.index(max_tier)
    )
    results: list[dict[str, Any]] = []
    for tier in SMALL_TIER_ORDER[: maximum_small_index + 1]:
        assert_ladder_identity()
        selection = load_selection(tier, root)
        tier_results: list[dict[str, Any]] = []
        for mode in MODE_ORDER:
            assert_ladder_identity()
            tier_results.append(
                execute_case(
                    RuntimeCase(mode, tier, selection),
                    executor=executor,
                    binary=binary,
                    search_path=search_path,
                    opportunity_trace_limit=opportunity_trace_limit,
                    phase_a_identity=phase_a_identity,
                    e0_frozen_oracle=e0_frozen_oracle,
                    root=root,
                    archive_root=archive_root,
                )
            )
            assert_ladder_identity()
        results = apply_baseline_comparisons([*results, *tier_results])
    best = select_best_batched(results)
    if max_tier == "full" and best is not None:
        full_selection = load_selection("full", root)
        full_modes = [MODE_ORDER[0], best]
        full_results: list[dict[str, Any]] = []
        for mode in full_modes:
            assert_ladder_identity()
            full_results.append(
                execute_case(
                    RuntimeCase(mode, "full", full_selection),
                    executor=executor,
                    binary=binary,
                    search_path=search_path,
                    opportunity_trace_limit=opportunity_trace_limit,
                    phase_a_identity=phase_a_identity,
                    e0_frozen_oracle=e0_frozen_oracle,
                    root=root,
                    archive_root=archive_root,
                )
            )
            assert_ladder_identity()
        results = apply_baseline_comparisons([*results, *full_results])
    assert_ladder_identity()
    return results, best


COMMON_TABLE_COLUMNS = (
    "schema",
    "row_kind",
    "mode",
    "tier",
    "selection_id",
    "selected_segment_count",
    "selected_raw_bag_count",
    "selection_sha256",
    "execution_status",
    "gate_status",
    "slice_type",
    "slice_value",
    "opportunity_count",
    "ready_set_singleton_count",
    "ready_set_multi_count",
    "mean_ready_set_size",
    "max_ready_set_size",
    "q0_actual_priority_comparator_opportunity_count",
    "priority_comparison_count",
    "same_time_pending_count",
    "shared_merge_pending_count",
    "known_competitor_count",
    "later_unseen_competitor_count",
    "merge_collision_count",
    "seq_determined_count",
    "pibt_applicable_count",
    "pibt_multi_bag_slice_count",
    "pibt_owner_visible_count",
    "pibt_feasible_slice_proxy_count",
    "batched_count",
    "multi_enqueue_count",
    "mean_enqueue_count",
    "max_enqueue_count",
    "sample_rank",
    "sample_sha256",
    "event_time",
    "timestamp_bits",
    "source_node",
    "junction_node",
    "destination_node",
    "upstream_node",
    "incoming_edge_start",
    "incoming_edge_end",
    "boundary",
    "node",
    "queue_length_before_enqueue",
    "queue_length_after_enqueue",
    "queue_length_before_arbitration",
    "queue_length_after_arbitration",
    "same_timestamp_release_batch_size",
    "same_timestamp_arrival_batch_size",
    "same_time_pending_source_releases",
    "same_time_pending_shared_merge_releases",
    "same_time_pending_arrivals",
    "same_time_pending_shared_merge_requests",
    "ready_set_size",
    "pibt_slice_bag_count",
    "pibt_owner_count",
    "chosen_task_id",
    "requesting_task_id",
    "chosen_runtime_bag_id",
    "requesting_runtime_bag_id",
    "chosen_segment_id",
    "requesting_segment_id",
    "queue_discipline",
    "earliest_arrival",
    "slot_start",
    "slot_end",
    "known_competing_request_count",
    "later_same_time_competitor_count",
    "later_same_time_competitor_exists",
    "seq_determined_order",
    "chosen_enqueue_sequence",
    "reason",
    "enqueue_count",
    "pending_same_time_event_count",
    "event_seq",
    "arbitration_generation",
    "batched_arbitration",
    "stored_row_sha256",
    "raw_archive_file_sha256",
    "raw_payload_canonical_sha256",
    "result_file_sha256",
    "cache_key",
    "identity_sha256",
    "instrumented_binary_path",
    "instrumented_binary_sha256",
    "source_bundle_sha256",
    "priority_comparison_semantics",
)

AB_COLUMNS = (
    "schema",
    "mode",
    "tier",
    "selection_id",
    "selected_segment_count",
    "selected_raw_bag_count",
    "selection_sha256",
    "execution_status",
    "gate_status",
    "mechanism_gate",
    "promotion_status",
    "blocker",
    "early_reject_reasons",
    "original_entry_mean_minutes",
    "original_entry_p95_seconds",
    "original_entry_p99_seconds",
    "source_wait_mean_minutes",
    "network_time_mean_minutes",
    "delta_vs_e0_mean_seconds_per_bag",
    "delta_vs_e0_p95_seconds",
    "delta_vs_e0_p99_seconds",
    "completed_segment_count",
    "complete_raw_bag_count",
    "completion_rate",
    "conflict_count",
    "unsafe_entry_count",
    "runtime_full_astar_calls",
    "global_reservation_scan_count",
    "future_routes_stored",
    "unresolved_deadlock_count",
    "event_limit_reached",
    "time_limit_reached",
    "reservation_depth",
    "max_edges_selected_per_arrive",
    "stale_arbitration_event_count",
    "superseded_arbitration_event_rejected_count",
    "microphase_runtime_global_scan_count",
    "artificial_batch_delay_seconds",
    "source_same_timestamp_batch_count",
    "junction_same_timestamp_batch_count",
    "max_source_arbitration_batch_size",
    "max_junction_arbitration_batch_size",
    "decision_count",
    "opportunity_event_queue_inspection_count",
    "q0_actual_priority_comparator_opportunity_count",
    "merge_known_competitor_count",
    "merge_later_unseen_count",
    "event_seq_determined_local_reservation_order_proxy_count",
    "pibt_feasible_slice_proxy_count",
    "batched_multi_enqueue_count",
    "source_opportunity_total_count",
    "source_opportunity_stored_count",
    "source_opportunity_dropped_count",
    "junction_opportunity_total_count",
    "junction_opportunity_stored_count",
    "junction_opportunity_dropped_count",
    "merge_visibility_total_count",
    "merge_visibility_stored_count",
    "merge_visibility_dropped_count",
    "event_seq_audit_total_count",
    "event_seq_audit_stored_count",
    "event_seq_audit_dropped_count",
    "arbitration_batch_total_count",
    "arbitration_batch_stored_count",
    "arbitration_batch_dropped_count",
    "raw_archive_file_sha256",
    "raw_payload_canonical_sha256",
    "result_file_sha256",
    "cache_key",
    "identity_sha256",
    "instrumented_binary_path",
    "instrumented_binary_sha256",
    "source_bundle_sha256",
    "priority_comparison_semantics",
    "e0_frozen_oracle_status",
    "e0_frozen_oracle_certificate_sha256",
    "e0_frozen_oracle_tiers",
    "e0_frozen_binary_sha256",
    "e0_new_binary_sha256",
    "e0_frozen_oracle_projection_audit_json",
    "e0_frozen_oracle_full_certificate_json",
    "execution_git_commit_sha",
    "execution_working_source_bundle_manifest_json",
    "execution_git_source_bundle_manifest_json",
)


def _base_table_fields(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": TABLE_SCHEMA,
        "mode": result.get("mode", ""),
        "tier": result.get("tier", ""),
        "selection_id": result.get("selection_id", ""),
        "selected_segment_count": result.get(
            "selected_segment_count", ""
        ),
        "selected_raw_bag_count": result.get(
            "selected_raw_bag_count", ""
        ),
        "selection_sha256": result.get("selection_sha256", ""),
        "execution_status": result.get("execution_status", "NOT_RUN"),
        "gate_status": result.get("gate_status", "NOT_EVALUATED"),
        "raw_archive_file_sha256": result.get(
            "raw_archive_file_sha256", ""
        ),
        "raw_payload_canonical_sha256": result.get(
            "raw_payload_canonical_sha256", ""
        ),
        "result_file_sha256": result.get("result_file_sha256", ""),
        "cache_key": result.get("cache_key", ""),
        "identity_sha256": result.get("identity_sha256", ""),
        "instrumented_binary_path": result.get(
            "instrumented_binary_path", ""
        ),
        "instrumented_binary_sha256": result.get(
            "instrumented_binary_sha256", ""
        ),
        "source_bundle_sha256": result.get("source_bundle_sha256", ""),
        "priority_comparison_semantics": (
            result.get("trace_context", {}).get(
                "priority_comparison_semantics", ""
            )
            if isinstance(result.get("trace_context"), Mapping)
            else ""
        ),
    }


def _telemetry_table_rows(
    result: Mapping[str, Any], kind: str
) -> list[dict[str, Any]]:
    compact = result.get("compact_telemetry")
    if not isinstance(compact, Mapping):
        return []
    section = compact.get(kind)
    if not isinstance(section, Mapping):
        return []
    base = _base_table_fields(result)
    stored_hash = section.get("stored_row_sha256", "")
    rows = [
        {**base, **dict(row), "stored_row_sha256": stored_hash}
        for row in section.get("aggregates", [])
        if isinstance(row, Mapping)
    ]
    rows.extend(
        {
            **base,
            "row_kind": "DETERMINISTIC_SAMPLE",
            "slice_type": "minhash_sample",
            "slice_value": "",
            "opportunity_count": 1,
            **dict(row),
            "stored_row_sha256": stored_hash,
        }
        for row in section.get("samples", [])
        if isinstance(row, Mapping)
    )
    return rows


def _ab_row(result: Mapping[str, Any]) -> dict[str, Any]:
    base = _base_table_fields(result)
    timing = (
        result.get("timing") if isinstance(result.get("timing"), Mapping) else {}
    )
    counters = (
        result.get("counters")
        if isinstance(result.get("counters"), Mapping)
        else {}
    )
    summary = (
        result.get("runtime_summary")
        if isinstance(result.get("runtime_summary"), Mapping)
        else {}
    )
    metrics = (
        result.get("telemetry_metrics")
        if isinstance(result.get("telemetry_metrics"), Mapping)
        else {}
    )
    telemetry_counts = (
        result.get("telemetry_counts")
        if isinstance(result.get("telemetry_counts"), Mapping)
        else {}
    )
    oracle = (
        result.get("e0_frozen_oracle")
        if isinstance(result.get("e0_frozen_oracle"), Mapping)
        else {}
    )
    frozen_oracle_binary = (
        oracle.get("frozen_binary")
        if isinstance(oracle.get("frozen_binary"), Mapping)
        else {}
    )
    new_oracle_binary = (
        oracle.get("new_binary")
        if isinstance(oracle.get("new_binary"), Mapping)
        else {}
    )
    row = {
        **base,
        "mechanism_gate": result.get("mechanism_gate", "NOT_EVALUATED"),
        "promotion_status": result.get(
            "promotion_status", "NOT_AUTHORIZED"
        ),
        "blocker": result.get("blocker", ""),
        "early_reject_reasons": "|".join(
            str(value) for value in result.get("early_reject_reasons", [])
        ),
        **{
            name: timing.get(name, "")
            for name in (
                "original_entry_mean_minutes",
                "original_entry_p95_seconds",
                "original_entry_p99_seconds",
                "source_wait_mean_minutes",
                "network_time_mean_minutes",
                "completed_segment_count",
                "complete_raw_bag_count",
                "completion_rate",
            )
        },
        **{
            name: result.get(name, "")
            for name in (
                "delta_vs_e0_mean_seconds_per_bag",
                "delta_vs_e0_p95_seconds",
                "delta_vs_e0_p99_seconds",
            )
        },
        **{
            name: counters.get(name, "")
            for name in (
                "conflict_count",
                "unsafe_entry_count",
                "runtime_full_astar_calls",
                "global_reservation_scan_count",
                "future_routes_stored",
                "unresolved_deadlock_count",
                "event_limit_reached",
                "time_limit_reached",
                "reservation_depth",
                "max_edges_selected_per_arrive",
            )
        },
        **{
            name: summary.get(name, "")
            for name in (
                "stale_arbitration_event_count",
                "superseded_arbitration_event_rejected_count",
                "microphase_runtime_global_scan_count",
                "artificial_batch_delay_seconds",
                "source_same_timestamp_batch_count",
                "junction_same_timestamp_batch_count",
                "max_source_arbitration_batch_size",
                "max_junction_arbitration_batch_size",
                "decision_count",
                "opportunity_event_queue_inspection_count",
            )
        },
        **{
            name: metrics.get(name, "")
            for name in (
                "q0_actual_priority_comparator_opportunity_count",
                "merge_known_competitor_count",
                "merge_later_unseen_count",
                "event_seq_determined_local_reservation_order_proxy_count",
                "pibt_feasible_slice_proxy_count",
                "batched_multi_enqueue_count",
            )
        },
        "e0_frozen_oracle_status": oracle.get("status", ""),
        "e0_frozen_oracle_certificate_sha256": oracle.get(
            "certificate_sha256", ""
        ),
        "e0_frozen_oracle_tiers": "|".join(
            str(value) for value in oracle.get("tiers", [])
        ),
        "e0_frozen_binary_sha256": frozen_oracle_binary.get(
            "physical_sha256", ""
        ),
        "e0_new_binary_sha256": new_oracle_binary.get("sha256", ""),
        "e0_frozen_oracle_projection_audit_json": (
            canonical_json_bytes(oracle.get("comparisons", [])).decode(
                "utf-8"
            )
            if isinstance(oracle.get("comparisons"), list)
            else ""
        ),
        "e0_frozen_oracle_full_certificate_json": (
            canonical_json_bytes(oracle).decode("utf-8") if oracle else ""
        ),
        "execution_git_commit_sha": oracle.get(
            "execution_git_commit_sha", ""
        ),
        "execution_working_source_bundle_manifest_json": (
            canonical_json_bytes(
                oracle.get("working_source_bundle", {})
            ).decode("utf-8")
            if isinstance(oracle.get("working_source_bundle"), Mapping)
            else ""
        ),
        "execution_git_source_bundle_manifest_json": (
            canonical_json_bytes(
                oracle.get("git_source_bundle", {})
            ).decode("utf-8")
            if isinstance(oracle.get("git_source_bundle"), Mapping)
            else ""
        ),
    }
    for array_name, counter_names in TELEMETRY_COUNTERS.items():
        values = telemetry_counts.get(array_name, {})
        if not isinstance(values, Mapping):
            values = {}
        for label, column in zip(("total", "stored", "dropped"), counter_names):
            row[column] = values.get(label, "")
    return row


def _complete_plan(
    results: Sequence[Mapping[str, Any]],
    *,
    best_batched: str | None,
    root: Path,
) -> list[dict[str, Any]]:
    by_key = {
        (str(row.get("mode")), str(row.get("tier"))): dict(row)
        for row in results
    }
    rows: list[dict[str, Any]] = []
    for tier in TIER_ORDER:
        selection = load_selection(tier, root)
        for mode in MODE_ORDER:
            key = (mode, tier)
            if key in by_key:
                rows.append(by_key[key])
                continue
            blocker = "TIER_NOT_RUN"
            if tier == "full":
                if best_batched is None:
                    blocker = (
                        "NO_BATCHED_MODE_PASSED_8192_MECHANISM_GATE;"
                        "FULL_ROUTE_STOPPED"
                    )
                elif mode not in {MODE_ORDER[0], best_batched}:
                    blocker = "FULL_RESTRICTED_TO_E0_AND_BEST_BATCHED_MODE"
            rows.append(
                _not_run_result(
                    mode, tier, blocker, selection=selection
                )
            )
    return rows


def _prior_q0_q1_equivalence(root: Path) -> dict[str, Any]:
    rows = _read_csv(root / PRIORITY_ABLATION_PATH)
    metrics = (
        "original_entry_mean_minutes",
        "original_entry_p95_seconds",
        "original_entry_p99_seconds",
        "source_wait_mean_minutes",
        "network_time_mean_minutes",
    )
    evidence: list[dict[str, Any]] = []
    for tier in SMALL_TIER_ORDER:
        q0 = next(
            (
                row
                for row in rows
                if row.get("candidate_id") == "C_Q0"
                and row.get("tier") == tier
            ),
            None,
        )
        q1 = next(
            (
                row
                for row in rows
                if row.get("candidate_id") == "C_Q1"
                and row.get("tier") == tier
            ),
            None,
        )
        if q0 is None or q1 is None:
            evidence.append({"tier": tier, "equivalent": False})
            continue
        equivalent = (
            q0.get("gate_status") == q1.get("gate_status") == "PASS"
            and all(q0.get(name) == q1.get(name) for name in metrics)
        )
        evidence.append(
            {
                "tier": tier,
                "equivalent": equivalent,
                "q0_result_file_sha256": q0.get("result_file_sha256", ""),
                "q1_result_file_sha256": q1.get("result_file_sha256", ""),
            }
        )
    return {
        "all_small_tiers_equivalent": all(
            row["equivalent"] for row in evidence
        ),
        "evidence": evidence,
        "source_file_sha256": file_sha256(root / PRIORITY_ABLATION_PATH),
        "claim_boundary": (
            "aggregate timing equivalence only; changed-order count requires "
            "a matched per-opportunity Q1 counterfactual that is not a runtime "
            "feature in this fixed-Q0 audit"
        ),
    }


def _e0_oracle_comparison_report_lines(
    oracle: Mapping[str, Any],
) -> list[str]:
    comparisons = oracle.get("comparisons")
    if not isinstance(comparisons, list) or not comparisons:
        return ["- Projection audit: `NOT_RUN`."]
    lines: list[str] = []
    for item in comparisons:
        if not isinstance(item, Mapping):
            return ["- Projection audit: `INVALID`."]
        hashes = (
            item.get("projection_hashes")
            if isinstance(item.get("projection_hashes"), Mapping)
            else {}
        )
        trace_lengths = (
            item.get("trace_lengths")
            if isinstance(item.get("trace_lengths"), Mapping)
            else {}
        )
        tier = item.get("tier", "UNKNOWN")
        lines.extend(
            [
                f"- `{tier}` common old=new algorithm projection: "
                f"`{hashes.get('algorithm_projection_sha256', 'MISSING')}`.",
                "  - bags: "
                f"`{hashes.get('bags_sha256', 'MISSING')}`; count "
                f"`{item.get('bags_count', 'MISSING')}`.",
                "  - junction state: "
                f"`{hashes.get('junction_state_sha256', 'MISSING')}`; count "
                f"`{item.get('junction_state_count', 'MISSING')}`.",
                "  - algorithm summary: "
                f"`{hashes.get('algorithm_summary_sha256', 'MISSING')}`.",
                "  - trace context: "
                f"`{hashes.get('trace_context_sha256', 'MISSING')}`.",
                "  - complete trace payload: "
                f"`{hashes.get('trace_payload_sha256', 'MISSING')}`; lengths "
                f"`{canonical_json_bytes(trace_lengths).decode('utf-8')}`.",
            ]
        )
    return lines


def _audit_report(
    plan: Sequence[Mapping[str, Any]],
    *,
    prior: Mapping[str, Any],
) -> str:
    e0 = [
        row
        for row in plan
        if row.get("mode") == MODE_ORDER[0]
        and row.get("execution_status") in {"EXECUTED", "CACHED"}
    ]
    largest = max(
        e0,
        key=lambda row: TIER_ORDER.index(str(row["tier"])),
        default=None,
    )
    metrics = (
        largest.get("telemetry_metrics", {})
        if isinstance(largest, Mapping)
        and isinstance(largest.get("telemetry_metrics"), Mapping)
        else {}
    )
    summary = (
        largest.get("runtime_summary", {})
        if isinstance(largest, Mapping)
        and isinstance(largest.get("runtime_summary"), Mapping)
        else {}
    )
    oracle = (
        largest.get("e0_frozen_oracle", {})
        if isinstance(largest, Mapping)
        and isinstance(largest.get("e0_frozen_oracle"), Mapping)
        else {}
    )
    oracle_frozen_binary = (
        oracle.get("frozen_binary", {})
        if isinstance(oracle.get("frozen_binary"), Mapping)
        else {}
    )
    oracle_new_binary = (
        oracle.get("new_binary", {})
        if isinstance(oracle.get("new_binary"), Mapping)
        else {}
    )
    blockers = [
        str(row.get("blocker", ""))
        for row in e0
        if row.get("gate_status") != "PASS"
    ]
    exact_q1_order_blocker = (
        "Q1_CHANGED_ORDER_COUNT_NOT_IDENTIFIED_BY_FIXED_Q0_TELEMETRY"
    )
    oracle_projection_lines = _e0_oracle_comparison_report_lines(oracle)
    # Fixed-Q0 telemetry cannot identify a per-opportunity Q1 counterfactual,
    # so Stage 14B remains explicitly partial even when every runtime hard gate
    # passes.  The missing causal contrast is not papered over by aggregate
    # equality inherited from G4IRSF13.
    status = "PARTIAL_WITH_EXPLICIT_BLOCKER"
    return "\n".join(
        [
            "# G4IRSF14-B Effective Decision Opportunity Audit",
            "",
            f"Status: `{status}`.",
            "",
            "This audit uses the frozen F2 R3/S1/P2/C0/Q0 control, the complete "
            "protected map, unchanged protected task rows, no fault, scale 1.0, "
            "and reservation depth 1. It is diagnostic only and cannot promote "
            "a performance candidate.",
            "",
            "## Four required questions",
            "",
            "1. **Why Q1 was equivalent to Q0.** Prior G4IRSF13 matched tiers "
            f"have aggregate timing equivalence: `{prior.get('all_small_tiers_equivalent')}`. "
            "The measured Q0 actual choose-bag comparator-opportunity count at "
            "the largest available "
            f"E0 tier is `{metrics.get('q0_actual_priority_comparator_opportunity_count', 'NOT_RUN')}`, "
            "so equivalence must not be described as 'no opportunity' when this "
            "count is non-zero. This counter is hard-bound to actual comparator "
            "invocations (escape-token bypass contributes zero); it is not a "
            "ready-set-size proxy and is not a Q1 counterfactual. The exact Q1 "
            "changed-order count is not identified by a fixed-Q0 trace: "
            f"`{exact_q1_order_blocker}`.",
            "2. **Why P2 did not commit more often.** The opportunity trace "
            f"records `{metrics.get('pibt_applicable_opportunity_count', 'NOT_RUN')}` "
            "P2-applicable junction opportunities, "
            f"`{metrics.get('pibt_multi_bag_slice_count', 'NOT_RUN')}` multi-bag "
            "slices, and "
            f"`{metrics.get('pibt_owner_visible_count', 'NOT_RUN')}` owner-visible "
            "slices. Runtime rejection totals remain in the raw summary; the "
            "junction opportunity schema does not conflate owner visibility with "
            "a causal blocker outcome.",
            "3. **Whether v2-safe advantage is concentrated in cross-source "
            "same-time requests.** The frozen-control trace records "
            f"`{metrics.get('shared_merge_pending_count', 'NOT_RUN')}` shared-merge "
            "pending opportunities. This is a locally observable candidate / "
            "upper-bound signal only, not proof that all cross-upstream requests "
            "were atomically visible. It is association only: no matched v2-safe "
            "state clone is run in Stage 14B.",
            "4. **How much merge order is event-seq determined.** The largest "
            "available E0 tier records "
            f"`{metrics.get('event_seq_determined_local_reservation_order_proxy_count', 'NOT_RUN')}` "
            "local destination-reservation/order observations marked "
            "seq-determined and "
            f"`{metrics.get('merge_later_unseen_count', 'NOT_RUN')}` reservations "
            "with a later same-time competitor. This is a local ordering proxy, "
            "not a destination-owned grant count.",
            "",
            "## Runtime integrity",
            "",
            f"- Largest audited E0 tier: `{largest.get('tier') if largest else 'NOT_RUN'}`.",
            f"- Stale arbitration events: `{summary.get('stale_arbitration_event_count', 'NOT_RUN')}`.",
            "- Superseded arbitration wakeups safely rejected before execution: "
            f"`{summary.get('superseded_arbitration_event_rejected_count', 'NOT_RUN')}`.",
            f"- Microphase global scans: `{summary.get('microphase_runtime_global_scan_count', 'NOT_RUN')}`.",
            f"- Artificial batch delay: `{summary.get('artificial_batch_delay_seconds', 'NOT_RUN')}` seconds.",
            f"- E0 blockers: `{' | '.join(filter(None, blockers)) or 'none'}`.",
            "",
            "## Frozen-E0 external exact oracle",
            "",
            f"- Status: `{oracle.get('status', 'NOT_RUN')}`.",
            "- Isolation: one independently spawned process loads exactly one "
            "named `czr005_cpp` pyd; old and new binaries are never imported "
            "into the same process.",
            f"- Real protected cohorts: `{' | '.join(str(value) for value in oracle.get('tiers', [])) or 'NOT_RUN'}`.",
            f"- Certificate SHA-256: `{oracle.get('certificate_sha256', 'NOT_RUN')}`.",
            "- Frozen Stage-14A binary SHA-256: "
            f"`{oracle_frozen_binary.get('physical_sha256', 'NOT_RUN')}`.",
            "- Instrumented new binary SHA-256: "
            f"`{oracle_new_binary.get('sha256', 'NOT_RUN')}`.",
            "- Clean execution Git commit: "
            f"`{oracle.get('execution_git_commit_sha', 'NOT_RUN')}`.",
            "- Working raw source-bundle SHA-256: "
            f"`{oracle.get('working_source_bundle', {}).get('bundle_sha256', 'NOT_RUN') if isinstance(oracle.get('working_source_bundle'), Mapping) else 'NOT_RUN'}`.",
            "- Recorded Git-blob source-bundle SHA-256: "
            f"`{oracle.get('git_source_bundle', {}).get('bundle_sha256', 'NOT_RUN') if isinstance(oracle.get('git_source_bundle'), Mapping) else 'NOT_RUN'}`.",
            "- Exact projection: complete bags, junction state, algorithm "
            "summary, trace context, and all event/decision/hold/PIBT/credit/"
            "fault traces. Only loaded-binary identity and host-dependent "
            "performance observations (time/RSS) are excluded. E0 telemetry "
            "is off and every "
            "Stage-14B extension field is required absent.",
            *oracle_projection_lines,
            "",
            "## Claim boundary",
            "",
            "Raw telemetry is stored only under `.local_archives`; committed "
            "tables contain grouped counts and deterministic min-hash samples "
            "bound to both compressed-file and canonical-payload SHA-256 values. "
            "No NOT_RUN row contains invented performance metrics. `Merge "
            "visibility` in this stage is local candidate/upper-bound evidence; "
            "the runtime explicitly reports destination merge grant disabled and "
            "does not claim an atomic cross-upstream grant. Priority opportunity "
            "counts are accepted only under the runtime's exact actual-comparator "
            "semantics echo; ready-set cardinality is never substituted.",
            "",
        ]
    )


def _ab_report(
    plan: Sequence[Mapping[str, Any]], *, best_batched: str | None
) -> str:
    executed = [
        row
        for row in plan
        if row.get("execution_status") in {"EXECUTED", "CACHED"}
    ]
    passed = [row for row in executed if row.get("gate_status") == "PASS"]
    mechanism = [
        row
        for row in executed
        if row.get("mechanism_gate") == "PASS"
    ]
    full_modes = [
        str(row["mode"])
        for row in executed
        if row.get("tier") == "full"
    ]
    blockers = sorted(
        {
            str(row.get("blocker", ""))
            for row in executed
            if row.get("blocker")
        }
    )
    oracle = (
        executed[0].get("e0_frozen_oracle", {})
        if executed
        and isinstance(executed[0].get("e0_frozen_oracle"), Mapping)
        else {}
    )
    oracle_projection_lines = _e0_oracle_comparison_report_lines(oracle)
    status = (
        "PASS_DIAGNOSTIC_ROUTE_HAS_MECHANISM_EVIDENCE"
        if best_batched is not None and mechanism
        else "PARTIAL_WITH_EXPLICIT_BLOCKER"
    )
    lines = [
        "# G4IRSF14-C Same-Timestamp Event Microphase A/B",
        "",
        f"Status: `{status}`.",
        "",
        "Only event semantics vary. Every case freezes R3/S1/P2/C0/Q0, "
        "uses no fault, preserves scale 1.0 and reservation depth 1, and "
        "processes only nodes activated at the exact simulation timestamp.",
        "",
        "## Ladder",
        "",
        f"- Executed or cached cases: `{len(executed)}`.",
        f"- Hard-gate PASS cases: `{len(passed)}`.",
        f"- Batched cases with a required mechanism change: `{len(mechanism)}`.",
        f"- Best 8192 batched mode: `{best_batched or 'NONE'}`.",
        f"- Full modes actually launched: `{', '.join(full_modes) or 'none'}`.",
        "- Frozen-E0 external exact oracle: "
        f"`{oracle.get('status', 'NOT_RUN')}`; certificate "
        f"`{oracle.get('certificate_sha256', 'NOT_RUN')}`; real cohorts "
        f"`{' | '.join(str(value) for value in oracle.get('tiers', [])) or 'NOT_RUN'}`.",
        "- Original 1x is never launched without `--allow-full`; when launched, "
        "only E0 and the single best 8192 batched mode are admitted.",
        "",
        "## Frozen-E0 projection audit",
        "",
        *oracle_projection_lines,
        "",
        "## Gates",
        "",
        "A PASS requires complete drainage, zero conflict/unsafe/A*/global-scan/"
        "future-route/deadlock/stale-arbitration counts, reservation depth 1, "
        "no event/time limit, zero artificial delay, exact runtime echoes, exact "
        "binary identity, and complete telemetry accounting with zero dropped "
        "rows. The priority counter must explicitly identify actual choose-bag "
        "comparator invocations with escape-token bypass equal to zero.",
        "",
        "A batched mode advances only when at least one of actual Q0 comparator "
        "opportunity, "
        "local merge-visibility candidate evidence, event-seq independence, "
        "P2 feasible-slice proxy, or "
        "TTH/tail improves against denominator-matched E0. Mean loss >1 s/bag, "
        "p95 loss >2 s, or p99 loss >4 s is an early reject.",
        "",
        "## Negative evidence",
        "",
    ]
    lines.extend(
        f"- `{blocker}`" for blocker in blockers
    )
    if not blockers:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Claim boundary",
            "",
            "Stage 14C establishes event-semantics mechanism evidence only. "
            "It does not establish a destination-owned merge grant, causal "
            "matched intervention, learned policy promotion, or scale unlock.",
            "The merge-visibility counters are local observable candidates / "
            "upper bounds and are not an atomic cross-upstream request set.",
            "",
        ]
    )
    return "\n".join(lines)


def _validate_working_source_bundle_manifest(
    value: Any,
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "files",
        "path_manifest_sha256",
        "bundle_sha256",
    }:
        raise MicrophaseError(
            "frozen E0 oracle working source bundle shape drift"
        )
    files = value.get("files")
    if not isinstance(files, list):
        raise MicrophaseError(
            "frozen E0 oracle working source files are missing"
        )
    expected_paths = [path.as_posix() for path in SOURCE_BUNDLE_PATHS]
    observed_paths: list[str] = []
    for row in files:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise MicrophaseError(
                "frozen E0 oracle working source row shape drift"
            )
        observed_paths.append(str(row.get("path", "")))
        if not _is_lower_hex_digest(row.get("sha256"), (64,)):
            raise MicrophaseError(
                "frozen E0 oracle working source SHA-256 is invalid"
            )
    if observed_paths != expected_paths:
        raise MicrophaseError(
            "frozen E0 oracle working source path manifest drift"
        )
    if value["path_manifest_sha256"] != canonical_sha256(expected_paths):
        raise MicrophaseError(
            "frozen E0 oracle working source path-manifest hash drift"
        )
    if value["bundle_sha256"] != canonical_sha256(files):
        raise MicrophaseError(
            "frozen E0 oracle working source bundle hash drift"
        )
    return value


def _recorded_absolute_path_key(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise MicrophaseError(f"{label} is not an absolute path")
    return os.path.normcase(os.path.normpath(value))


def _validate_e0_oracle_certificate(
    certificate: Any,
    *,
    phase_a_identity: Mapping[str, Any],
    root: Path,
    expected_new_binary_path: str,
    expected_new_binary_sha256: str,
    expected_working_source_bundle_sha256: str,
    expected_projection_audit: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not isinstance(certificate, dict):
        raise MicrophaseError("frozen E0 oracle certificate is not an object")
    expected_fields = {
        "schema",
        "status",
        "process_isolation",
        "tiers",
        "controls",
        "controls_sha256",
        "frozen_binary",
        "new_binary",
        "execution_git_commit_sha",
        "working_source_bundle",
        "git_source_bundle",
        "source_history_clean_gate",
        "excluded_summary_fields",
        "extension_fields_required_absent",
        "comparisons",
        "certificate_sha256",
    }
    if set(certificate) != expected_fields:
        raise MicrophaseError("frozen E0 oracle certificate shape drift")
    if (
        certificate["schema"] != E0_ORACLE_CERTIFICATE_SCHEMA
        or certificate["status"] != "PASS_EXACT_EXTERNAL_ORACLE"
        or certificate["process_isolation"]
        != "one_named_pyd_per_child_process"
        or certificate["tiers"] != list(E0_ORACLE_TIERS)
        or certificate["controls"] != _e0_oracle_controls()
        or certificate["controls_sha256"]
        != canonical_sha256(_e0_oracle_controls())
        or certificate["excluded_summary_fields"]
        != sorted(E0_ORACLE_EXCLUDED_SUMMARY_FIELDS)
        or certificate["extension_fields_required_absent"] is not True
    ):
        raise MicrophaseError("frozen E0 oracle certificate contract drift")
    declared_self_hash = certificate["certificate_sha256"]
    unsigned = dict(certificate)
    unsigned.pop("certificate_sha256")
    if (
        not _is_lower_hex_digest(declared_self_hash, (64,))
        or canonical_sha256(unsigned) != declared_self_hash
    ):
        raise MicrophaseError(
            "frozen E0 oracle certificate self-hash drift"
        )

    descriptor = phase_a_identity.get("frozen_binary")
    frozen_binary = certificate.get("frozen_binary")
    if not isinstance(descriptor, Mapping) or not isinstance(
        frozen_binary, dict
    ):
        raise MicrophaseError(
            "frozen E0 oracle Stage-14A binary binding is missing"
        )
    sealed_path = descriptor.get("path")
    sealed_hash = descriptor.get("file_sha256")
    if (
        set(frozen_binary)
        != {
            "artifact_path",
            "artifact_sha256",
            "physical_path",
            "physical_sha256",
        }
        or frozen_binary.get("artifact_path") != sealed_path
        or frozen_binary.get("artifact_sha256") != sealed_hash
        or frozen_binary.get("physical_sha256") != sealed_hash
        or not _is_lower_hex_digest(sealed_hash, (64,))
    ):
        raise MicrophaseError(
            "frozen E0 oracle is not bound to Stage-14A binary"
        )
    _recorded_absolute_path_key(
        frozen_binary.get("physical_path"),
        label="frozen E0 oracle physical binary path",
    )

    new_binary = certificate.get("new_binary")
    if (
        not isinstance(new_binary, dict)
        or set(new_binary) != {"path", "sha256"}
        or new_binary.get("sha256") != expected_new_binary_sha256
        or not _is_lower_hex_digest(expected_new_binary_sha256, (64,))
        or _recorded_absolute_path_key(
            new_binary.get("path"),
            label="frozen E0 oracle new binary path",
        )
        != _recorded_absolute_path_key(
            expected_new_binary_path,
            label="executed result binary path",
        )
    ):
        raise MicrophaseError(
            "frozen E0 oracle new-binary identity drift"
        )

    working_source_bundle = _validate_working_source_bundle_manifest(
        certificate.get("working_source_bundle")
    )
    if (
        working_source_bundle["bundle_sha256"]
        != expected_working_source_bundle_sha256
    ):
        raise MicrophaseError(
            "frozen E0 oracle/result working source bundle mismatch"
        )
    commit = certificate.get("execution_git_commit_sha")
    if not _is_lower_hex_digest(commit, (40, 64)):
        raise MicrophaseError("frozen E0 oracle execution commit is invalid")
    reconstructed_git_bundle = _git_source_bundle_at_commit(
        root, str(commit)
    )
    if certificate.get("git_source_bundle") != reconstructed_git_bundle:
        raise MicrophaseError(
            "frozen E0 oracle recorded Git source bundle drift"
        )
    expected_clean_gate = {
        "source_paths_tracked": True,
        "tracked_tree_worktree_diff_quiet": True,
        "tracked_tree_index_diff_quiet": True,
        "normalization": (
            "git_diff_normalization_aware;working_raw_sha_may_differ_"
            "from_git_blob_sha_under_core_autocrlf"
        ),
    }
    if certificate.get("source_history_clean_gate") != expected_clean_gate:
        raise MicrophaseError(
            "frozen E0 oracle source-history clean gate drift"
        )

    comparisons = certificate.get("comparisons")
    if not isinstance(comparisons, list):
        raise MicrophaseError(
            "frozen E0 oracle projection audit is missing"
        )
    validated_comparisons = _validate_e0_oracle_projection_audit(
        canonical_json_bytes(comparisons).decode("utf-8"),
        root=root,
    )
    if (
        expected_projection_audit is not None
        and validated_comparisons != expected_projection_audit
    ):
        raise MicrophaseError(
            "frozen E0 oracle certificate/projection audit mismatch"
        )
    return certificate


def _assert_executed_results_have_exact_e0_oracle(
    results: Sequence[Mapping[str, Any]],
    *,
    phase_a_identity: Mapping[str, Any],
    root: Path,
) -> None:
    executed = [
        row
        for row in results
        if row.get("execution_status") in {"EXECUTED", "CACHED"}
    ]
    if not executed:
        return
    canonical_certificates: set[bytes] = set()
    for row in executed:
        oracle = row.get("e0_frozen_oracle")
        if not isinstance(oracle, dict):
            raise MicrophaseError(
                "executed result lacks frozen E0 oracle certificate"
            )
        validated = _validate_e0_oracle_certificate(
            oracle,
            phase_a_identity=phase_a_identity,
            root=root,
            expected_new_binary_path=str(
                row.get("instrumented_binary_path", "")
            ),
            expected_new_binary_sha256=str(
                row.get("instrumented_binary_sha256", "")
            ),
            expected_working_source_bundle_sha256=str(
                row.get("source_bundle_sha256", "")
            ),
        )
        if (
            row.get("execution_git_commit_sha")
            != validated["execution_git_commit_sha"]
            or row.get("execution_working_source_bundle")
            != validated["working_source_bundle"]
            or row.get("execution_git_source_bundle")
            != validated["git_source_bundle"]
        ):
            raise MicrophaseError(
                "executed result source-history fields/certificate drift"
            )
        canonical_certificates.add(canonical_json_bytes(validated))
    if len(canonical_certificates) != 1:
        raise MicrophaseError("executed results mix frozen E0 oracle certificates")


def write_outputs(
    results: Sequence[Mapping[str, Any]],
    *,
    best_batched: str | None,
    root: Path = ROOT,
) -> dict[str, Any]:
    # Publication consumes the hash-bound oracle certificate carried by each
    # result.  It must not require the intentionally-untracked frozen pyd to
    # exist at its historical build-tree path (notably in a clean clone).
    phase_a_identity = assert_phase_a_and_inputs(
        root, require_frozen_binary=False
    )
    compared = apply_baseline_comparisons(results)
    _assert_executed_results_have_exact_e0_oracle(
        compared, phase_a_identity=phase_a_identity, root=root
    )
    plan = _complete_plan(compared, best_batched=best_batched, root=root)
    table_rows: dict[str, list[dict[str, Any]]] = {
        "source": [],
        "junction": [],
        "merge": [],
        "seq": [],
        "batch": [],
    }
    for result in plan:
        # Stage 14B is the unmodified E0 audit. Stage 14C batch evidence covers
        # all modes; the four opportunity tables deliberately remain E0-only.
        if result.get("mode") == MODE_ORDER[0]:
            for kind in ("source", "junction", "merge", "seq"):
                table_rows[kind].extend(_telemetry_table_rows(result, kind))
        table_rows["batch"].extend(_telemetry_table_rows(result, "batch"))
    for name, rows in table_rows.items():
        atomic_write_csv(
            root / OUTPUT_PATHS[name],
            COMMON_TABLE_COLUMNS,
            rows,
        )
    ab_rows = [_ab_row(row) for row in plan]
    atomic_write_csv(root / OUTPUT_PATHS["ab"], AB_COLUMNS, ab_rows)
    prior = _prior_q0_q1_equivalence(root)
    _atomic_write(
        root / OUTPUT_PATHS["audit_report"],
        _audit_report(plan, prior=prior).encode("utf-8"),
    )
    _atomic_write(
        root / OUTPUT_PATHS["ab_report"],
        _ab_report(plan, best_batched=best_batched).encode("utf-8"),
    )
    return {
        "status": (
            "REAL_EVIDENCE_RECORDED"
            if any(
                row.get("execution_status") in {"EXECUTED", "CACHED"}
                for row in plan
            )
            else "PROTOCOL_READY_NO_RUNTIME_ATTEMPTS"
        ),
        "best_batched": best_batched,
        "executed_count": sum(
            row.get("execution_status") in {"EXECUTED", "CACHED"}
            for row in plan
        ),
        "gate_pass_count": sum(
            row.get("gate_status") == "PASS" for row in plan
        ),
        "output_sha256": {
            name: file_sha256(root / path)
            for name, path in OUTPUT_PATHS.items()
        },
    }


def _validate_e0_oracle_projection_audit(
    text: str,
    *,
    root: Path = ROOT,
) -> list[dict[str, Any]]:
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise MicrophaseError(
            "A/B frozen E0 oracle projection audit is invalid JSON"
        ) from exc
    if not isinstance(value, list) or len(value) != len(E0_ORACLE_TIERS):
        raise MicrophaseError(
            "A/B frozen E0 oracle projection audit has wrong tier count"
        )
    observed_tiers: list[str] = []
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise MicrophaseError(
                "A/B frozen E0 oracle projection audit row is not an object"
            )
        if set(item) != {
            "tier",
            "selection",
            "frozen_projection_sha256",
            "new_projection_sha256",
            "projection_hashes",
            "bags_count",
            "junction_state_count",
            "trace_lengths",
        }:
            raise MicrophaseError(
                "A/B frozen E0 oracle projection audit row shape drift"
            )
        tier = item.get("tier")
        if not isinstance(tier, str):
            raise MicrophaseError(
                "A/B frozen E0 oracle projection audit tier is invalid"
            )
        observed_tiers.append(tier)
        selection = item.get("selection")
        if not isinstance(selection, dict):
            raise MicrophaseError(
                "A/B frozen E0 oracle projection selection is missing"
            )
        expected_selection = load_selection(tier, root)
        expected_selection_identity = {
            "selection_id": expected_selection.selection_id,
            "segment_count": expected_selection.segment_count,
            "raw_bag_count": expected_selection.raw_bag_count,
            "selected_rows_sha256": expected_selection.selected_rows_sha256,
            "selected_segment_ids_sha256": (
                expected_selection.selected_segment_ids_sha256
            ),
        }
        if selection != expected_selection_identity:
            raise MicrophaseError(
                f"A/B frozen E0 oracle selection drift: tier={tier}"
            )
        for name in ("segment_count", "raw_bag_count"):
            count = selection.get(name)
            if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
                raise MicrophaseError(
                    f"A/B frozen E0 oracle selection {name} is invalid"
                )
        for name in (
            "selected_rows_sha256",
            "selected_segment_ids_sha256",
        ):
            digest = selection.get(name)
            if (
                not isinstance(digest, str)
                or len(digest) != 64
                or any(
                    character not in "0123456789abcdef"
                    for character in digest
                )
            ):
                raise MicrophaseError(
                    f"A/B frozen E0 oracle selection {name} is invalid"
                )
        projection_hashes = item.get("projection_hashes")
        if (
            not isinstance(projection_hashes, dict)
            or set(projection_hashes)
            != set(E0_ORACLE_PROJECTION_HASH_FIELDS)
        ):
            raise MicrophaseError(
                "A/B frozen E0 oracle projection hash shape drift"
            )
        for name in E0_ORACLE_PROJECTION_HASH_FIELDS:
            digest = projection_hashes.get(name)
            if (
                not isinstance(digest, str)
                or len(digest) != 64
                or any(
                    character not in "0123456789abcdef"
                    for character in digest
                )
            ):
                raise MicrophaseError(
                    f"A/B frozen E0 oracle invalid projection hash {name}"
                )
        frozen_projection = item.get("frozen_projection_sha256")
        new_projection = item.get("new_projection_sha256")
        if (
            frozen_projection
            != projection_hashes["algorithm_projection_sha256"]
            or new_projection != frozen_projection
        ):
            raise MicrophaseError(
                "A/B frozen/new E0 algorithm projections are not exact"
            )
        for name in ("bags_count", "junction_state_count"):
            count = item.get(name)
            if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
                raise MicrophaseError(
                    f"A/B frozen E0 oracle {name} is invalid"
                )
        if item["bags_count"] != selection["segment_count"]:
            raise MicrophaseError(
                "A/B frozen E0 oracle bag/selection count mismatch"
            )
        trace_lengths = item.get("trace_lengths")
        if (
            not isinstance(trace_lengths, dict)
            or set(trace_lengths) != set(E0_ORACLE_TRACE_ARRAYS)
        ):
            raise MicrophaseError(
                "A/B frozen E0 oracle trace length manifest is incomplete"
            )
        if any(
            isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
            for count in trace_lengths.values()
        ):
            raise MicrophaseError(
                "A/B frozen E0 oracle trace length is invalid"
            )
        if trace_lengths["decision_trace"] != trace_lengths["decisions"]:
            raise MicrophaseError(
                "A/B frozen E0 oracle decision trace length drift"
            )
        normalized.append(item)
    if tuple(observed_tiers) != E0_ORACLE_TIERS:
        raise MicrophaseError(
            "A/B frozen E0 oracle projection tier order drift"
        )
    return normalized


def validate_committed_outputs(
    root: Path = ROOT,
    *,
    new_binary_override: Path | None = None,
    frozen_binary_override: Path | None = None,
    run_child: Callable[
        ..., subprocess.CompletedProcess[str]
    ] = subprocess.run,
) -> dict[str, Any]:
    # The compact artifacts bind the Stage-A sealed hash.  Executed evidence
    # additionally requires the physical old/new pyd bytes (recorded paths or
    # CLI overrides) for a fresh external four-child replay below.
    phase_a_identity = assert_phase_a_and_inputs(
        root, require_frozen_binary=False
    )
    frozen_binary_descriptor = phase_a_identity.get("frozen_binary")
    if not isinstance(frozen_binary_descriptor, Mapping):
        raise MicrophaseError("Stage-14A frozen binary descriptor is missing")
    frozen_binary_sha256 = str(
        frozen_binary_descriptor.get("file_sha256", "")
    )
    missing = [
        path.as_posix()
        for path in OUTPUT_PATHS.values()
        if not (root / path).is_file()
    ]
    if missing:
        raise MicrophaseError(f"missing Stage-14B/C outputs: {missing}")
    decoded: dict[str, list[dict[str, str]]] = {}
    for name in ("source", "junction", "merge", "seq", "batch"):
        path = root / OUTPUT_PATHS[name]
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != COMMON_TABLE_COLUMNS:
                raise MicrophaseError(f"{name} table header drift")
            rows = [dict(row) for row in reader]
        for row in rows:
            if row["schema"] != TABLE_SCHEMA:
                raise MicrophaseError(f"{name} table schema drift")
            if row["row_kind"] not in {
                "AGGREGATE",
                "DETERMINISTIC_SAMPLE",
            }:
                raise MicrophaseError(f"{name} invalid row kind")
            for digest_name in (
                "stored_row_sha256",
                "raw_archive_file_sha256",
                "raw_payload_canonical_sha256",
                "result_file_sha256",
                "cache_key",
                "identity_sha256",
                "instrumented_binary_sha256",
                "source_bundle_sha256",
            ):
                digest = row[digest_name]
                if len(digest) != 64 or any(
                    character not in "0123456789abcdef"
                    for character in digest
                ):
                    raise MicrophaseError(
                        f"{name} invalid executed-row {digest_name}"
                    )
            if not Path(row["instrumented_binary_path"]).is_absolute():
                raise MicrophaseError(
                    f"{name} executed row lacks absolute binary identity"
                )
            if (
                row["priority_comparison_semantics"]
                != PRIORITY_COMPARISON_SEMANTICS
            ):
                raise MicrophaseError(
                    f"{name} priority comparison semantics drift"
                )
        decoded[name] = rows
    ab_path = root / OUTPUT_PATHS["ab"]
    with ab_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != AB_COLUMNS:
            raise MicrophaseError("A/B table header drift")
        ab_rows = [dict(row) for row in reader]
    expected_count = len(MODE_ORDER) * len(TIER_ORDER)
    if len(ab_rows) != expected_count:
        raise MicrophaseError(
            f"A/B row count {len(ab_rows)} != {expected_count}"
        )
    seen = {(row["mode"], row["tier"]) for row in ab_rows}
    expected = {(mode, tier) for mode in MODE_ORDER for tier in TIER_ORDER}
    if seen != expected:
        raise MicrophaseError("A/B plan matrix is incomplete")
    metric_fields = (
        "original_entry_mean_minutes",
        "original_entry_p95_seconds",
        "original_entry_p99_seconds",
        "source_wait_mean_minutes",
        "network_time_mean_minutes",
    )
    committed_certificate: dict[str, Any] | None = None
    for row in ab_rows:
        if row["schema"] != TABLE_SCHEMA:
            raise MicrophaseError("A/B table schema drift")
        if row["execution_status"] == "NOT_RUN" and any(
            row[name] for name in metric_fields
        ):
            raise MicrophaseError("NOT_RUN row fabricates timing metrics")
        if row["execution_status"] in {"EXECUTED", "CACHED"}:
            for digest_name in (
                "raw_archive_file_sha256",
                "raw_payload_canonical_sha256",
                "result_file_sha256",
                "cache_key",
                "identity_sha256",
                "instrumented_binary_sha256",
                "source_bundle_sha256",
            ):
                digest = row[digest_name]
                if len(digest) != 64 or any(
                    character not in "0123456789abcdef"
                    for character in digest
                ):
                    raise MicrophaseError(
                        f"A/B executed row invalid {digest_name}"
                    )
            if not Path(row["instrumented_binary_path"]).is_absolute():
                raise MicrophaseError(
                    "A/B executed row lacks absolute binary identity"
                )
            if (
                row["priority_comparison_semantics"]
                != PRIORITY_COMPARISON_SEMANTICS
            ):
                raise MicrophaseError(
                    "A/B priority comparison semantics drift"
                )
            if (
                row["e0_frozen_oracle_status"]
                != "PASS_EXACT_EXTERNAL_ORACLE"
            ):
                raise MicrophaseError(
                    "A/B executed row lacks PASS exact frozen E0 oracle"
                )
            if row["e0_frozen_oracle_tiers"] != "|".join(E0_ORACLE_TIERS):
                raise MicrophaseError("A/B frozen E0 oracle tier drift")
            for digest_name in (
                "e0_frozen_oracle_certificate_sha256",
                "e0_frozen_binary_sha256",
                "e0_new_binary_sha256",
            ):
                digest = row[digest_name]
                if len(digest) != 64 or any(
                    character not in "0123456789abcdef"
                    for character in digest
                ):
                    raise MicrophaseError(
                        f"A/B executed row invalid {digest_name}"
                    )
            if row["e0_frozen_binary_sha256"] != frozen_binary_sha256:
                raise MicrophaseError(
                    "A/B frozen E0 oracle binary hash is not Stage-14A"
                )
            if (
                row["e0_new_binary_sha256"]
                != row["instrumented_binary_sha256"]
            ):
                raise MicrophaseError(
                    "A/B frozen E0 oracle new-binary identity drift"
                )
            projection_audit = _validate_e0_oracle_projection_audit(
                row["e0_frozen_oracle_projection_audit_json"],
                root=root,
            )
            if (
                canonical_json_bytes(projection_audit).decode("utf-8")
                != row["e0_frozen_oracle_projection_audit_json"]
            ):
                raise MicrophaseError(
                    "A/B frozen E0 projection audit is not canonical JSON"
                )
            try:
                certificate = json.loads(
                    row["e0_frozen_oracle_full_certificate_json"]
                )
                working_manifest = json.loads(
                    row[
                        "execution_working_source_bundle_manifest_json"
                    ]
                )
                git_manifest = json.loads(
                    row["execution_git_source_bundle_manifest_json"]
                )
            except json.JSONDecodeError as exc:
                raise MicrophaseError(
                    "A/B frozen E0 certificate/source manifest invalid JSON"
                ) from exc
            validated_certificate = _validate_e0_oracle_certificate(
                certificate,
                phase_a_identity=phase_a_identity,
                root=root,
                expected_new_binary_path=row[
                    "instrumented_binary_path"
                ],
                expected_new_binary_sha256=row[
                    "instrumented_binary_sha256"
                ],
                expected_working_source_bundle_sha256=row[
                    "source_bundle_sha256"
                ],
                expected_projection_audit=projection_audit,
            )
            if (
                canonical_json_bytes(validated_certificate).decode("utf-8")
                != row["e0_frozen_oracle_full_certificate_json"]
            ):
                raise MicrophaseError(
                    "A/B frozen E0 certificate is not canonical JSON"
                )
            if committed_certificate is None:
                committed_certificate = validated_certificate
            elif (
                canonical_json_bytes(committed_certificate)
                != canonical_json_bytes(validated_certificate)
            ):
                raise MicrophaseError(
                    "A/B mixed frozen E0 oracle certificates"
                )
            if (
                row["e0_frozen_oracle_certificate_sha256"]
                != validated_certificate["certificate_sha256"]
                or row["e0_frozen_binary_sha256"]
                != validated_certificate["frozen_binary"][
                    "physical_sha256"
                ]
                or row["e0_new_binary_sha256"]
                != validated_certificate["new_binary"]["sha256"]
                or row["execution_git_commit_sha"]
                != validated_certificate["execution_git_commit_sha"]
                or working_manifest
                != validated_certificate["working_source_bundle"]
                or git_manifest
                != validated_certificate["git_source_bundle"]
                or canonical_json_bytes(working_manifest).decode("utf-8")
                != row[
                    "execution_working_source_bundle_manifest_json"
                ]
                or canonical_json_bytes(git_manifest).decode("utf-8")
                != row["execution_git_source_bundle_manifest_json"]
            ):
                raise MicrophaseError(
                    "A/B frozen E0 flattened certificate fields drift"
                )
            if row["gate_status"] == "PASS":
                required = {
                    "conflict_count": "0",
                    "unsafe_entry_count": "0",
                    "runtime_full_astar_calls": "0",
                    "global_reservation_scan_count": "0",
                    "future_routes_stored": "0",
                    "unresolved_deadlock_count": "0",
                    "event_limit_reached": "False",
                    "time_limit_reached": "False",
                    "reservation_depth": "1",
                    "stale_arbitration_event_count": "0",
                    "microphase_runtime_global_scan_count": "0",
                    "artificial_batch_delay_seconds": "0.0",
                }
                for name, wanted in required.items():
                    if row[name] != wanted:
                        raise MicrophaseError(
                            f"PASS row hard-gate drift: {name}={row[name]}"
                        )
                for _array, counter_names in TELEMETRY_COUNTERS.items():
                    if row[counter_names[2]] != "0":
                        raise MicrophaseError(
                            "PASS row has dropped opportunity telemetry"
                        )
                source_total = int(row["source_opportunity_total_count"])
                junction_total = int(
                    row["junction_opportunity_total_count"]
                )
                merge_total = int(row["merge_visibility_total_count"])
                seq_total = int(row["event_seq_audit_total_count"])
                batch_total = int(row["arbitration_batch_total_count"])
                if merge_total != int(row["decision_count"]):
                    raise MicrophaseError(
                        "PASS row merge/decision conservation drift"
                    )
                if batch_total != source_total + junction_total:
                    raise MicrophaseError(
                        "PASS row arbitration-batch conservation drift"
                    )
                if seq_total != source_total + junction_total + merge_total:
                    raise MicrophaseError(
                        "PASS row event-seq conservation drift"
                    )
                if int(
                    row["opportunity_event_queue_inspection_count"]
                ) != seq_total:
                    raise MicrophaseError(
                        "PASS row queue-inspection conservation drift"
                    )
                if (
                    int(row["selected_segment_count"]) > 0
                    and source_total
                    == junction_total
                    == merge_total
                    == seq_total
                    == batch_total
                    == 0
                ):
                    raise MicrophaseError(
                        "PASS nonempty row has all-zero telemetry"
                    )
    executed_identity_rows = [
        row
        for row in ab_rows
        if row["execution_status"] in {"EXECUTED", "CACHED"}
    ]
    for identity_field in (
        "instrumented_binary_path",
        "instrumented_binary_sha256",
        "source_bundle_sha256",
        "e0_frozen_oracle_certificate_sha256",
        "e0_frozen_binary_sha256",
        "e0_new_binary_sha256",
        "e0_frozen_oracle_projection_audit_json",
        "e0_frozen_oracle_full_certificate_json",
        "execution_git_commit_sha",
        "execution_working_source_bundle_manifest_json",
        "execution_git_source_bundle_manifest_json",
    ):
        distinct = {row[identity_field] for row in executed_identity_rows}
        if len(distinct) > 1:
            raise MicrophaseError(
                f"A/B mixed execution identity: {identity_field}"
            )
    if executed_identity_rows:
        if committed_certificate is None:
            raise MicrophaseError(
                "A/B executed evidence lacks frozen E0 oracle certificate"
            )
        external_oracle_replay = rerun_committed_e0_frozen_oracle(
            committed_certificate,
            root=root,
            new_binary_override=new_binary_override,
            frozen_binary_override=frozen_binary_override,
            run_child=run_child,
        )
    else:
        external_oracle_replay = {
            "status": "NOT_APPLICABLE_NO_EXECUTED_ROWS",
            "child_process_count": 0,
        }
    ab_identity_by_case = {
        (row["mode"], row["tier"]): (
            row["cache_key"],
            row["identity_sha256"],
            row["instrumented_binary_sha256"],
            row["source_bundle_sha256"],
        )
        for row in executed_identity_rows
    }
    for table_name, rows in decoded.items():
        for row in rows:
            case_key = (row["mode"], row["tier"])
            if case_key not in ab_identity_by_case:
                raise MicrophaseError(
                    f"{table_name} telemetry lacks executed A/B case"
                )
            observed = (
                row["cache_key"],
                row["identity_sha256"],
                row["instrumented_binary_sha256"],
                row["source_bundle_sha256"],
            )
            if observed != ab_identity_by_case[case_key]:
                raise MicrophaseError(
                    f"{table_name} telemetry/A-B identity mismatch"
                )
    full_executed = [
        row
        for row in ab_rows
        if row["tier"] == "full"
        and row["execution_status"] in {"EXECUTED", "CACHED"}
    ]
    if len(full_executed) > 2:
        raise MicrophaseError("more than E0 + one batched mode ran full")
    if any(row["mode"] in BATCHED_MODES for row in full_executed) and not any(
        row["mode"] == MODE_ORDER[0] for row in full_executed
    ):
        raise MicrophaseError("batched full run lacks matched E0 control")
    if len(full_executed) == 2:
        batched_count = sum(
            row["mode"] in BATCHED_MODES for row in full_executed
        )
        if batched_count != 1:
            raise MicrophaseError("full comparison lacks exactly one batched mode")
    for name in ("audit_report", "ab_report"):
        report = (root / OUTPUT_PATHS[name]).read_text(encoding="utf-8")
        if "Status: `" not in report or "Claim boundary" not in report:
            raise MicrophaseError(f"{name} lacks status/claim boundary")
    return {
        "status": "PASS",
        "ab_row_count": len(ab_rows),
        "executed_count": sum(
            row["execution_status"] in {"EXECUTED", "CACHED"}
            for row in ab_rows
        ),
        "full_executed_count": len(full_executed),
        "external_oracle_replay": external_oracle_replay,
        "telemetry_table_row_counts": {
            name: len(rows) for name, rows in decoded.items()
        },
        "output_sha256": {
            name: file_sha256(root / path)
            for name, path in OUTPUT_PATHS.items()
        },
    }


def protocol_manifest() -> dict[str, Any]:
    return {
        "schema": PROTOCOL_SCHEMA,
        "fixed_real_map_only": True,
        "protected_inputs": {
            "map_path": MAP_PATH.as_posix(),
            "map_raw_sha256": CANONICAL_MAP_RAW_SHA256,
            "map_semantic_sha256": CANONICAL_MAP_SEMANTIC_SHA256,
            "task_path": TASK_PATH.as_posix(),
            "task_raw_sha256": CANONICAL_SOURCE_RAW_SHA256,
            "segment_count": FULL_SIZE_SEGMENTS,
            "raw_bag_count": FULL_SIZE_BAGS,
        },
        "frozen_control": dict(FROZEN_CONTROL),
        "modes": list(MODE_ORDER),
        "tier_order": list(TIER_ORDER),
        "full_default_authorized": False,
        "full_admitted_modes": "E0_plus_single_best_8192_batched_mode",
        "opportunity_trace_limit_default": DEFAULT_OPPORTUNITY_TRACE_LIMIT,
        "priority_comparison_semantics": PRIORITY_COMPARISON_SEMANTICS,
        "frozen_e0_external_exact_oracle": {
            "required_before_ladder": True,
            "process_isolation": "one_named_pyd_per_child_process",
            "tiers": list(E0_ORACLE_TIERS),
            "event_semantics": MODE_ORDER[0],
            "opportunity_telemetry_enabled": False,
            "extension_fields_required_absent": True,
            "source_history_binding": {
                "execution_head_commit_required": True,
                "entire_tracked_tree_git_diff_quiet_required": True,
                "working_raw_source_bundle_recorded": True,
                "recorded_commit_git_blobs_rebuilt_from_object_database": True,
                "autocrlf_policy": (
                    "git_normalization_aware_clean_gate;do_not_compare_"
                    "working_raw_bytes_to_git_blob_bytes"
                ),
            },
            "projection_hash_fields": list(
                E0_ORACLE_PROJECTION_HASH_FIELDS
            ),
            "excluded_summary_fields": sorted(
                E0_ORACLE_EXCLUDED_SUMMARY_FIELDS
            ),
        },
        "raw_archive": LOCAL_ARCHIVE.as_posix(),
        "raw_archive_tracked": False,
        "outputs": {
            name: path.as_posix() for name, path in OUTPUT_PATHS.items()
        },
        "forbidden": {
            "scale_above_one": True,
            "fault_workload": True,
            "runtime_astar": True,
            "future_route": True,
            "global_reservation_scan": True,
            "all_node_microphase_scan": True,
            "nonzero_batch_window": True,
            "reservation_depth_above_one": True,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-ladder",
        action="store_true",
        help="Run E0-E3 through --max-tier and publish compact evidence.",
    )
    parser.add_argument(
        "--max-tier",
        choices=TIER_ORDER,
        default="8192",
        help="Largest tier; full also requires --allow-full.",
    )
    parser.add_argument(
        "--allow-full",
        action="store_true",
        help="Authorize E0 plus the single best measured batched mode at 1x.",
    )
    parser.add_argument(
        "--binary", type=Path, help="Exact instrumented czr005_cpp binary."
    )
    parser.add_argument(
        "--frozen-binary",
        type=Path,
        help=(
            "Physical Stage-14A frozen pyd. Its bytes must match the sealed "
            "artifact hash; useful when verifying from a clean clone."
        ),
    )
    parser.add_argument(
        "--search-path",
        type=Path,
        help="Directory containing --binary; defaults to binary parent.",
    )
    parser.add_argument(
        "--opportunity-trace-limit",
        type=int,
        default=DEFAULT_OPPORTUNITY_TRACE_LIMIT,
        help="Per-array telemetry cap; any dropped row fails the gate.",
    )
    parser.add_argument(
        "--archive-root",
        type=Path,
        help="Override append-only local raw-attempt archive.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT,
        help="Repository root receiving compact outputs.",
    )
    parser.add_argument(
        "--validate-committed",
        action="store_true",
        help=(
            "Validate existing Stage-14B/C artifacts and externally replay "
            "the committed old/new E0 oracle."
        ),
    )
    parser.add_argument(
        "--print-protocol",
        action="store_true",
        help="Print deterministic protocol JSON and exit.",
    )
    parser.add_argument(
        "--publish-protocol",
        action="store_true",
        help=(
            "Explicitly publish a NOT_RUN matrix without executing. This flag "
            "prevents an accidental no-argument invocation from replacing real "
            "evidence."
        ),
    )
    parser.add_argument(
        "--e0-oracle-child",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--e0-oracle-role",
        choices=("frozen", "new"),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--e0-oracle-tier",
        choices=E0_ORACLE_TIERS,
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.output_root.resolve()
    if args.e0_oracle_child:
        if (
            args.binary is None
            or args.e0_oracle_role is None
            or args.e0_oracle_tier is None
        ):
            raise SystemExit(
                "oracle child requires --binary, --e0-oracle-role, and "
                "--e0-oracle-tier"
            )
        projection = _execute_e0_oracle_child(
            role=args.e0_oracle_role,
            tier=args.e0_oracle_tier,
            binary=args.binary.resolve(strict=True),
            root=root,
        )
        print(
            json.dumps(
                projection,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        )
        return 0
    if args.print_protocol:
        print(
            json.dumps(
                protocol_manifest(),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.validate_committed:
        new_binary_override = (
            args.binary.resolve(strict=True)
            if args.binary is not None
            else None
        )
        frozen_binary_override = (
            args.frozen_binary.resolve(strict=True)
            if args.frozen_binary is not None
            else None
        )
        print(
            json.dumps(
                validate_committed_outputs(
                    root,
                    new_binary_override=new_binary_override,
                    frozen_binary_override=frozen_binary_override,
                ),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    if not args.run_ladder and not args.publish_protocol:
        raise SystemExit(
            "choose --run-ladder, --publish-protocol, "
            "--validate-committed, or --print-protocol"
        )
    results: list[dict[str, Any]] = []
    best: str | None = None
    executed_binary: Path | None = None
    executed_frozen_binary: Path | None = None
    if args.run_ladder:
        if args.binary is None:
            raise SystemExit("--binary is required with --run-ladder")
        binary = args.binary.resolve(strict=True)
        executed_binary = binary
        executed_frozen_binary = (
            args.frozen_binary.resolve(strict=True)
            if args.frozen_binary is not None
            else None
        )
        search_path = (
            args.search_path.resolve(strict=True)
            if args.search_path
            else binary.parent
        )
        from czr005 import cpp_backend

        results, best = execute_ladder(
            executor=cpp_backend.g4irsf11_event_runtime_from_records,
            binary=binary,
            search_path=search_path,
            max_tier=args.max_tier,
            allow_full=args.allow_full,
            opportunity_trace_limit=args.opportunity_trace_limit,
            root=root,
            archive_root=args.archive_root,
            frozen_binary_override=executed_frozen_binary,
        )
    publication = write_outputs(results, best_batched=best, root=root)
    validation = validate_committed_outputs(
        root,
        new_binary_override=executed_binary,
        frozen_binary_override=executed_frozen_binary,
    )
    print(
        json.dumps(
            {
                **publication,
                "validation": validation,
                "full_run_launched": bool(
                    args.run_ladder and args.max_tier == "full"
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
