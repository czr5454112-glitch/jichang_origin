"""Fail-closed G4IRSF12-D size-ladder and early-abort protocol.

This module does not execute the event runtime.  It defines the only admitted
original-scale diagnostic ladder, validates result descriptors produced by a
runner, evaluates online-collapse symptoms, and writes compact evidence while
retaining every partial or negative attempt.

The diagnostic is deliberately not a final performance gate.  Clearing a
layer only authorizes the next layer in ``SIZE_LADDER``; clearing 43,603
segments records completion of the original-1x diagnostic ladder and does not
authorize any scaled workload.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import statistics
import tempfile
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]

PROTOCOL_SCHEMA = "czr005.g4irsf12.size_ladder_protocol.v1"
RESULT_DESCRIPTOR_SCHEMA = "czr005.g4irsf12.size_ladder_result_descriptor.v1"
EARLY_ABORT_STATUS = "EARLY_ABORT_DIAGNOSTIC_COLLAPSE"

SIZE_LADDER = (144, 512, 2_048, 8_192, 43_603)
FULL_SIZE_SEGMENTS = 43_603
FULL_SIZE_BAGS = 28_506
SIZE_LABELS = {
    144: "diagnostic_144",
    512: "diagnostic_512",
    2_048: "diagnostic_2048",
    8_192: "gate_8192",
    FULL_SIZE_SEGMENTS: "original_1x_full",
}

CANONICAL_MAP_PATH = "data/processed/maps/map2.json"
CANONICAL_MAP_RAW_SHA256 = (
    "9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4"
)
CANONICAL_MAP_SEMANTIC_SHA256 = (
    "67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63"
)
CANONICAL_SOURCE_PATH = "data/processed/tasks/inputdata.jsonl"
CANONICAL_SOURCE_RAW_SHA256 = (
    "968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f"
)
CANONICAL_SOURCE_SEMANTIC_SHA256 = CANONICAL_SOURCE_RAW_SHA256
TEXT_HASH_SEMANTICS = "sha256_of_utf8_text_after_crlf_cr_normalization_to_lf"

INPUT_ORDER_ID = "canonical_inputdata_jsonl_row_order"
PREFIX_SELECTION_ID = "first_n_segments_without_reordering"
WORKLOAD_GENERATION_LEVEL = "original_input_prefix_1x"
PRIMARY_THT_DENOMINATOR = "original_entry_time_tth"

OUTPUT_PATHS = {
    "size_ladder": "outputs/tables/g4irsf12_size_ladder.csv",
    "report": "outputs/reports/g4irsf12_early_abort_diagnostics.md",
    "backlog": "outputs/tables/g4irsf12_backlog_drain_curves.csv",
    "utilization": "outputs/tables/g4irsf12_utilization_with_backlog.csv",
}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EXECUTION_STATUSES = {"EXECUTED", "PARTIAL", "FAILED"}
_TERMINATION_REASONS = {
    "DRAINED",
    "SIMULATION_TIME_LIMIT",
    "EVENT_LIMIT",
    EARLY_ABORT_STATUS,
    "WORKER_FAILURE",
    "USER_STOP",
}

_IDENTITY_KEYS = {
    "map_path",
    "map_raw_sha256",
    "map_semantic_sha256",
    "source_path",
    "source_raw_sha256",
    "source_semantic_sha256",
    "source_row_count",
    "source_bag_count",
    "implementation_sha256",
    "implementation_source_bundle_sha256",
    "candidate_config_sha256",
    "resource_semantics_id",
    "scorer_id",
    "pibt_mode",
    "pressure_mode",
    "admission_mode",
    "tht_denominator",
    "workload_generation_level",
}
_REPRODUCIBILITY_KEYS = {
    "mode",
    "seed",
    "input_order",
    "prefix_selection",
    "deterministic_tie_break",
}
_SUMMARY_KEYS = {
    "arrivals",
    "admissions",
    "departures",
    "end_backlog",
    "peak_backlog",
    "deadlock_episode_count",
    "unresolved_deadlock_count",
    "starvation_count",
    "source_hold_count",
    "event_count",
    "simulation_horizon_seconds",
    "wall_seconds",
    "last_arrival_time_seconds",
    "projected_p99_seconds",
    "control_p99_seconds",
    "critical_junction_utilization",
}
_SNAPSHOT_KEYS = {
    "time_seconds",
    "wall_seconds",
    "arrivals",
    "admissions",
    "departures",
    "backlog",
    "source_holds",
    "event_count",
    "starvation_count",
    "deadlock_episode_count",
    "critical_junction_utilization",
    "wait_for_cycle_id",
}
_DESCRIPTOR_KEYS = {
    "schema",
    "attempt_id",
    "attempt_index",
    "candidate_id",
    "size_segments",
    "execution_status",
    "termination_reason",
    "identity",
    "reproducibility",
    "summary",
    "snapshots",
}


SIZE_LADDER_COLUMNS = (
    "attempt_id",
    "attempt_index",
    "candidate_id",
    "size_segments",
    "size_label",
    "descriptor_status",
    "execution_status",
    "termination_reason",
    "diagnostic_status",
    "promotion_decision",
    "arrivals",
    "admissions",
    "departures",
    "end_backlog",
    "peak_backlog",
    "critical_max_utilization",
    "deadlock_episode_count",
    "unresolved_deadlock_count",
    "starvation_count",
    "source_hold_count",
    "event_count",
    "simulation_horizon_seconds",
    "wall_seconds",
    "projected_p99_seconds",
    "control_p99_seconds",
    "triggered_criteria",
    "warning_criteria",
    "blockers",
    "descriptor_sha256",
)
BACKLOG_COLUMNS = (
    "attempt_id",
    "candidate_id",
    "size_segments",
    "snapshot_index",
    "time_seconds",
    "wall_seconds",
    "arrivals",
    "admissions",
    "departures",
    "backlog",
    "source_holds",
    "event_count",
    "starvation_count",
    "deadlock_episode_count",
    "after_last_arrival",
)
UTILIZATION_COLUMNS = (
    "attempt_id",
    "candidate_id",
    "size_segments",
    "snapshot_index",
    "time_seconds",
    "junction_id",
    "utilization",
    "backlog",
)


@dataclass(frozen=True)
class DiagnosticThresholds:
    """Frozen diagnostic thresholds, not claims of physical capacity."""

    recent_window_snapshots: int = 4
    minimum_observed_arrival_fraction: float = 0.25
    large_backlog_fraction: float = 0.10
    departure_to_arrival_ratio_max: float = 0.80
    low_critical_utilization_max: float = 0.20
    repeated_cycle_snapshots: int = 3
    source_hold_delta_fraction: float = 0.05
    minimum_source_hold_delta: int = 16
    nonlinear_interval_rate_factor: float = 3.0
    minimum_last_interval_events: int = 100
    p99_control_ratio_abort: float = 4.0
    starvation_total_fraction: float = 0.02
    starvation_window_fraction: float = 0.005
    minimum_starvation_total: int = 8
    minimum_starvation_window: int = 4
    composite_soft_trigger_count: int = 2
    cross_tier_normalized_growth_factor: float = 4.0


DEFAULT_THRESHOLDS = DiagnosticThresholds()

_HARD_CRITERIA = {
    "repeated_wait_for_cycle",
    "nonlinear_event_rate_without_progress",
    "p99_projection_far_above_control",
    "rapid_starvation_accumulation",
    "cross_tier_nonlinear_event_growth",
    "cross_tier_nonlinear_horizon_growth",
    "deterministic_repeat_mismatch",
    "candidate_reproducibility_tainted",
}


class DescriptorValidationError(ValueError):
    """Raised when a result descriptor cannot be admitted as evidence."""


def _normalised_text_bytes(path: Path) -> bytes:
    payload = path.read_bytes()
    payload.decode("utf-8")
    return payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _raw_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _semantic_sha256(path: Path) -> str:
    return hashlib.sha256(_normalised_text_bytes(path)).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _descriptor_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json_bytes(dict(value))).hexdigest()


def assert_protected_inputs(root: Path = ROOT) -> dict[str, Any]:
    """Recompute the protected map/task identities and fail closed on drift."""

    map_path = root / CANONICAL_MAP_PATH
    source_path = root / CANONICAL_SOURCE_PATH
    failures: list[str] = []
    if not map_path.is_file():
        failures.append(f"missing protected map: {CANONICAL_MAP_PATH}")
    if not source_path.is_file():
        failures.append(f"missing protected task source: {CANONICAL_SOURCE_PATH}")
    if failures:
        raise DescriptorValidationError("; ".join(failures))

    actual_map_raw = _raw_sha256(map_path)
    actual_map_semantic = _semantic_sha256(map_path)
    actual_source_raw = _raw_sha256(source_path)
    actual_source_semantic = _semantic_sha256(source_path)
    if actual_map_raw != CANONICAL_MAP_RAW_SHA256:
        failures.append("protected map raw SHA-256 mismatch")
    if actual_map_semantic != CANONICAL_MAP_SEMANTIC_SHA256:
        failures.append("protected map semantic SHA-256 mismatch")
    if actual_source_raw != CANONICAL_SOURCE_RAW_SHA256:
        failures.append("protected source raw SHA-256 mismatch")
    if actual_source_semantic != CANONICAL_SOURCE_SEMANTIC_SHA256:
        failures.append("protected source semantic SHA-256 mismatch")

    row_count = 0
    bag_ids: set[int] = set()
    try:
        with source_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                row_count += 1
                row = json.loads(line)
                bag_ids.add(int(row["pallet_id"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        failures.append(f"protected source cannot be audited: {type(exc).__name__}: {exc}")
    if row_count != FULL_SIZE_SEGMENTS:
        failures.append(
            f"protected source row count mismatch: {row_count} != {FULL_SIZE_SEGMENTS}"
        )
    if len(bag_ids) != FULL_SIZE_BAGS:
        failures.append(
            f"protected source bag count mismatch: {len(bag_ids)} != {FULL_SIZE_BAGS}"
        )
    if failures:
        raise DescriptorValidationError("; ".join(failures))
    return {
        "map_path": CANONICAL_MAP_PATH,
        "map_raw_sha256": actual_map_raw,
        "map_semantic_sha256": actual_map_semantic,
        "source_path": CANONICAL_SOURCE_PATH,
        "source_raw_sha256": actual_source_raw,
        "source_semantic_sha256": actual_source_semantic,
        "source_row_count": row_count,
        "source_bag_count": len(bag_ids),
        "hash_semantics": TEXT_HASH_SEMANTICS,
    }


def protocol_manifest(
    thresholds: DiagnosticThresholds = DEFAULT_THRESHOLDS,
) -> dict[str, Any]:
    """Return the deterministic, checkout-independent G4IRSF12-D protocol."""

    return {
        "schema": PROTOCOL_SCHEMA,
        "diagnostic_only": True,
        "final_performance_gate": False,
        "scale_authorization": "none_beyond_original_1x",
        "size_ladder_segments": list(SIZE_LADDER),
        "full_original_bag_count": FULL_SIZE_BAGS,
        "input_order": INPUT_ORDER_ID,
        "prefix_selection": PREFIX_SELECTION_ID,
        "canonical_map": {
            "path": CANONICAL_MAP_PATH,
            "raw_sha256": CANONICAL_MAP_RAW_SHA256,
            "semantic_sha256": CANONICAL_MAP_SEMANTIC_SHA256,
        },
        "canonical_source": {
            "path": CANONICAL_SOURCE_PATH,
            "raw_sha256": CANONICAL_SOURCE_RAW_SHA256,
            "semantic_sha256": CANONICAL_SOURCE_SEMANTIC_SHA256,
            "row_count": FULL_SIZE_SEGMENTS,
            "bag_count": FULL_SIZE_BAGS,
        },
        "descriptor_schema": RESULT_DESCRIPTOR_SCHEMA,
        "thresholds": asdict(thresholds),
        "abort_status": EARLY_ABORT_STATUS,
        "soft_trigger_rule": (
            "hold on one soft symptom; abort on at least "
            f"{thresholds.composite_soft_trigger_count} simultaneous soft symptoms"
        ),
        "hard_trigger_rule": "any hard symptom aborts immediately",
        "forbidden_repairs": [
            "increase_max_simulation_time_only",
            "increase_max_events_only",
            "disable_starvation_metric",
            "disable_deadlock_metric",
            "survivor_only_tth",
            "leave_backlog_at_run_end_and_claim_success",
            "advance_directly_to_scaled_workload",
        ],
        "outputs": dict(OUTPUT_PATHS),
    }


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _exact_keys(value: Any, expected: set[str], label: str, errors: list[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        errors.append(f"{label} must be an object")
        return {}
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        errors.append(f"{label} missing keys: {missing}")
    if extra:
        errors.append(f"{label} unknown keys require a schema bump: {extra}")
    return value


def _nonnegative_int(value: Any, label: str, errors: list[str]) -> int:
    if not _is_int(value) or value < 0:
        errors.append(f"{label} must be a non-negative integer")
        return 0
    return int(value)


def _nonnegative_float(value: Any, label: str, errors: list[str]) -> float:
    if not _finite(value) or float(value) < 0.0:
        errors.append(f"{label} must be a finite non-negative number")
        return 0.0
    return float(value)


def _validate_utilization(value: Any, label: str, errors: list[str]) -> dict[str, float]:
    if not isinstance(value, Mapping) or not value:
        errors.append(f"{label} must be a non-empty junction-to-utilization object")
        return {}
    result: dict[str, float] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key)
        if not key:
            errors.append(f"{label} contains an empty junction id")
            continue
        if not _finite(raw_value) or not 0.0 <= float(raw_value) <= 1.0:
            errors.append(f"{label}.{key} must be finite and within [0, 1]")
            continue
        result[key] = float(raw_value)
    return result


def descriptor_validation_errors(value: Any) -> list[str]:
    """Return every reason a descriptor must be rejected."""

    errors: list[str] = []
    if isinstance(value, Mapping) and "descriptor_load_error" in value:
        errors.append(f"descriptor load error: {value['descriptor_load_error']}")
    descriptor = _exact_keys(value, _DESCRIPTOR_KEYS, "descriptor", errors)
    if descriptor.get("schema") != RESULT_DESCRIPTOR_SCHEMA:
        errors.append("descriptor schema mismatch")

    for field in ("attempt_id", "candidate_id"):
        raw = descriptor.get(field)
        if not isinstance(raw, str) or not raw.strip():
            errors.append(f"{field} must be a non-empty string")
    attempt_index = descriptor.get("attempt_index")
    if not _is_int(attempt_index) or int(attempt_index) <= 0:
        errors.append("attempt_index must be a positive integer")
    size_segments = descriptor.get("size_segments")
    if not _is_int(size_segments) or int(size_segments) not in SIZE_LADDER:
        errors.append(f"size_segments must be exactly one of {SIZE_LADDER}")
        size = 0
    else:
        size = int(size_segments)

    execution_status = descriptor.get("execution_status")
    termination_reason = descriptor.get("termination_reason")
    if execution_status not in _EXECUTION_STATUSES:
        errors.append(f"execution_status must be one of {sorted(_EXECUTION_STATUSES)}")
    if termination_reason not in _TERMINATION_REASONS:
        errors.append(f"termination_reason must be one of {sorted(_TERMINATION_REASONS)}")

    identity = _exact_keys(descriptor.get("identity"), _IDENTITY_KEYS, "identity", errors)
    expected_identity = {
        "map_path": CANONICAL_MAP_PATH,
        "map_raw_sha256": CANONICAL_MAP_RAW_SHA256,
        "map_semantic_sha256": CANONICAL_MAP_SEMANTIC_SHA256,
        "source_path": CANONICAL_SOURCE_PATH,
        "source_raw_sha256": CANONICAL_SOURCE_RAW_SHA256,
        "source_semantic_sha256": CANONICAL_SOURCE_SEMANTIC_SHA256,
        "source_row_count": FULL_SIZE_SEGMENTS,
        "source_bag_count": FULL_SIZE_BAGS,
        "tht_denominator": PRIMARY_THT_DENOMINATOR,
        "workload_generation_level": WORKLOAD_GENERATION_LEVEL,
    }
    for field, expected in expected_identity.items():
        if identity.get(field) != expected:
            errors.append(f"identity.{field} must equal {expected!r}")
    for field in (
        "implementation_sha256",
        "implementation_source_bundle_sha256",
        "candidate_config_sha256",
    ):
        if not isinstance(identity.get(field), str) or not _SHA256_RE.fullmatch(str(identity.get(field))):
            errors.append(f"identity.{field} must be a lowercase SHA-256 digest")
    for field in (
        "resource_semantics_id",
        "scorer_id",
        "pibt_mode",
        "pressure_mode",
        "admission_mode",
    ):
        if not isinstance(identity.get(field), str) or not str(identity.get(field)).strip():
            errors.append(f"identity.{field} must be a non-empty string")

    reproducibility = _exact_keys(
        descriptor.get("reproducibility"),
        _REPRODUCIBILITY_KEYS,
        "reproducibility",
        errors,
    )
    mode = reproducibility.get("mode")
    seed = reproducibility.get("seed")
    if mode not in {"deterministic", "seeded"}:
        errors.append("reproducibility.mode must be deterministic or seeded")
    elif mode == "deterministic" and seed is not None:
        errors.append("fully deterministic mode must use seed=null")
    elif mode == "seeded" and (not _is_int(seed) or int(seed) < 0):
        errors.append("seeded mode must use a non-negative integer seed")
    if reproducibility.get("input_order") != INPUT_ORDER_ID:
        errors.append("reproducibility.input_order is not canonical")
    if reproducibility.get("prefix_selection") != PREFIX_SELECTION_ID:
        errors.append("reproducibility.prefix_selection is not the frozen prefix rule")
    if not isinstance(reproducibility.get("deterministic_tie_break"), str) or not str(
        reproducibility.get("deterministic_tie_break")
    ).strip():
        errors.append("reproducibility.deterministic_tie_break must be explicit")

    summary = _exact_keys(descriptor.get("summary"), _SUMMARY_KEYS, "summary", errors)
    integer_fields = (
        "arrivals",
        "admissions",
        "departures",
        "end_backlog",
        "peak_backlog",
        "deadlock_episode_count",
        "unresolved_deadlock_count",
        "starvation_count",
        "source_hold_count",
        "event_count",
    )
    counts = {
        field: _nonnegative_int(summary.get(field), f"summary.{field}", errors)
        for field in integer_fields
    }
    horizon = _nonnegative_float(
        summary.get("simulation_horizon_seconds"),
        "summary.simulation_horizon_seconds",
        errors,
    )
    wall_seconds = _nonnegative_float(summary.get("wall_seconds"), "summary.wall_seconds", errors)
    last_arrival = summary.get("last_arrival_time_seconds")
    if last_arrival is not None:
        last_arrival_value = _nonnegative_float(
            last_arrival, "summary.last_arrival_time_seconds", errors
        )
        if last_arrival_value > horizon:
            errors.append("summary.last_arrival_time_seconds cannot exceed the horizon")
    projected_p99 = summary.get("projected_p99_seconds")
    control_p99 = summary.get("control_p99_seconds")
    if projected_p99 is not None and (
        not _finite(projected_p99) or float(projected_p99) <= 0.0
    ):
        errors.append("summary.projected_p99_seconds must be null or finite and positive")
    if not _finite(control_p99) or float(control_p99) <= 0.0:
        errors.append("summary.control_p99_seconds must be finite and positive")
    _validate_utilization(
        summary.get("critical_junction_utilization"),
        "summary.critical_junction_utilization",
        errors,
    )

    if counts["admissions"] > counts["arrivals"]:
        errors.append("summary admissions cannot exceed arrivals")
    if counts["departures"] > counts["admissions"]:
        errors.append("summary departures cannot exceed admissions")
    if size and counts["arrivals"] > size:
        errors.append("summary arrivals cannot exceed size_segments")
    if counts["end_backlog"] != counts["arrivals"] - counts["departures"]:
        errors.append("summary end_backlog must equal arrivals minus departures")
    if counts["peak_backlog"] < counts["end_backlog"]:
        errors.append("summary peak_backlog cannot be below end_backlog")
    if counts["unresolved_deadlock_count"] > counts["deadlock_episode_count"]:
        errors.append("unresolved deadlocks cannot exceed deadlock episodes")
    if counts["departures"] > 0 and projected_p99 is None:
        errors.append("projected p99 is required when any segment departed")
    if wall_seconds == 0.0 and counts["event_count"] > 0:
        errors.append("wall_seconds must be positive when events were processed")

    snapshots_raw = descriptor.get("snapshots")
    if not isinstance(snapshots_raw, list):
        errors.append("snapshots must be an array")
        snapshots: list[Mapping[str, Any]] = []
    else:
        snapshots = []
        previous_time = -1.0
        previous_wall = -1.0
        previous_cumulative = {
            "arrivals": -1,
            "admissions": -1,
            "departures": -1,
            "source_holds": -1,
            "event_count": -1,
            "starvation_count": -1,
            "deadlock_episode_count": -1,
        }
        for index, raw_snapshot in enumerate(snapshots_raw):
            label = f"snapshots[{index}]"
            snapshot = _exact_keys(raw_snapshot, _SNAPSHOT_KEYS, label, errors)
            snapshots.append(snapshot)
            time_value = _nonnegative_float(snapshot.get("time_seconds"), f"{label}.time_seconds", errors)
            wall_value = _nonnegative_float(snapshot.get("wall_seconds"), f"{label}.wall_seconds", errors)
            if time_value <= previous_time:
                errors.append(f"{label}.time_seconds must be strictly increasing")
            if wall_value < previous_wall:
                errors.append(f"{label}.wall_seconds must be non-decreasing")
            previous_time = time_value
            previous_wall = wall_value
            snapshot_counts = {
                field: _nonnegative_int(snapshot.get(field), f"{label}.{field}", errors)
                for field in (
                    "arrivals",
                    "admissions",
                    "departures",
                    "backlog",
                    "source_holds",
                    "event_count",
                    "starvation_count",
                    "deadlock_episode_count",
                )
            }
            if snapshot_counts["admissions"] > snapshot_counts["arrivals"]:
                errors.append(f"{label} admissions cannot exceed arrivals")
            if snapshot_counts["departures"] > snapshot_counts["admissions"]:
                errors.append(f"{label} departures cannot exceed admissions")
            if snapshot_counts["backlog"] != snapshot_counts["arrivals"] - snapshot_counts["departures"]:
                errors.append(f"{label} backlog must equal arrivals minus departures")
            if size and snapshot_counts["arrivals"] > size:
                errors.append(f"{label} arrivals cannot exceed size_segments")
            for field, previous in previous_cumulative.items():
                if snapshot_counts[field] < previous:
                    errors.append(f"{label}.{field} must be cumulative and non-decreasing")
                previous_cumulative[field] = snapshot_counts[field]
            _validate_utilization(
                snapshot.get("critical_junction_utilization"),
                f"{label}.critical_junction_utilization",
                errors,
            )
            cycle_id = snapshot.get("wait_for_cycle_id")
            if cycle_id is not None and (not isinstance(cycle_id, str) or not cycle_id.strip()):
                errors.append(f"{label}.wait_for_cycle_id must be null or a non-empty string")

    if execution_status != "FAILED" and not snapshots:
        errors.append("non-failed executions must retain at least one diagnostic snapshot")
    if snapshots:
        final = snapshots[-1]
        final_pairs = {
            "arrivals": "arrivals",
            "admissions": "admissions",
            "departures": "departures",
            "backlog": "end_backlog",
            "source_holds": "source_hold_count",
            "event_count": "event_count",
            "starvation_count": "starvation_count",
            "deadlock_episode_count": "deadlock_episode_count",
        }
        for snapshot_field, summary_field in final_pairs.items():
            if final.get(snapshot_field) != summary.get(summary_field):
                errors.append(
                    f"final snapshot {snapshot_field} differs from summary.{summary_field}"
                )
        if _finite(final.get("time_seconds")) and _finite(summary.get("simulation_horizon_seconds")):
            if not math.isclose(
                float(final["time_seconds"]),
                float(summary["simulation_horizon_seconds"]),
                rel_tol=0.0,
                abs_tol=1.0e-9,
            ):
                errors.append("final snapshot time differs from simulation horizon")
        if _finite(final.get("wall_seconds")) and _finite(summary.get("wall_seconds")):
            if not math.isclose(
                float(final["wall_seconds"]),
                float(summary["wall_seconds"]),
                rel_tol=0.0,
                abs_tol=1.0e-9,
            ):
                errors.append("final snapshot wall time differs from summary wall time")

    if termination_reason == "DRAINED":
        if execution_status != "EXECUTED":
            errors.append("DRAINED requires execution_status=EXECUTED")
        if size and not (
            counts["arrivals"]
            == counts["admissions"]
            == counts["departures"]
            == size
        ):
            errors.append("DRAINED requires every tier segment to arrive, admit, and depart")
        if counts["end_backlog"] != 0:
            errors.append("DRAINED requires zero end backlog")
        if counts["unresolved_deadlock_count"] != 0:
            errors.append("DRAINED requires zero unresolved deadlock")
    elif termination_reason == EARLY_ABORT_STATUS:
        if execution_status != "PARTIAL":
            errors.append(f"{EARLY_ABORT_STATUS} requires execution_status=PARTIAL")
    elif termination_reason in {"SIMULATION_TIME_LIMIT", "EVENT_LIMIT", "USER_STOP"}:
        if execution_status != "PARTIAL":
            errors.append(f"{termination_reason} requires execution_status=PARTIAL")
    elif termination_reason == "WORKER_FAILURE" and execution_status != "FAILED":
        errors.append("WORKER_FAILURE requires execution_status=FAILED")

    return errors


def validate_result_descriptor(value: Any) -> dict[str, Any]:
    errors = descriptor_validation_errors(value)
    if errors:
        raise DescriptorValidationError("; ".join(errors))
    return dict(value)


def _criterion(
    criterion_id: str,
    triggered: bool,
    evidence: str,
    *,
    hard: bool | None = None,
) -> dict[str, Any]:
    return {
        "criterion_id": criterion_id,
        "triggered": bool(triggered),
        "hard": criterion_id in _HARD_CRITERIA if hard is None else bool(hard),
        "evidence": evidence,
    }


def diagnose_result_descriptor(
    descriptor: Mapping[str, Any],
    thresholds: DiagnosticThresholds = DEFAULT_THRESHOLDS,
) -> list[dict[str, Any]]:
    """Evaluate the current (or final) online diagnostic window.

    Callers may invoke this function after every newly persisted snapshot.  It
    intentionally looks only at the current recent window, so a transient
    symptom that later drained does not rewrite a completed run into an abort.
    """

    validate_result_descriptor(descriptor)
    size = int(descriptor["size_segments"])
    summary = descriptor["summary"]
    snapshots = list(descriptor["snapshots"])
    if not snapshots:
        return [
            _criterion(
                "insufficient_runtime_observation",
                True,
                "no snapshots were retained",
                hard=False,
            )
        ]

    window = snapshots[-thresholds.recent_window_snapshots :]
    first = window[0]
    last = window[-1]
    arrivals_delta = int(last["arrivals"]) - int(first["arrivals"])
    departures_delta = int(last["departures"]) - int(first["departures"])
    backlog = int(last["backlog"])
    large_backlog = max(8, math.ceil(size * thresholds.large_backlog_fraction))
    minimum_observed = max(
        8, math.ceil(size * thresholds.minimum_observed_arrival_fraction)
    )

    imbalance = (
        len(window) >= thresholds.recent_window_snapshots
        and int(last["arrivals"]) >= minimum_observed
        and backlog >= large_backlog
        and arrivals_delta > 0
        and departures_delta
        <= arrivals_delta * thresholds.departure_to_arrival_ratio_max
    )
    results = [
        _criterion(
            "sustained_arrival_departure_imbalance",
            imbalance,
            (
                f"window={len(window)} arrivals_delta={arrivals_delta} "
                f"departures_delta={departures_delta} backlog={backlog} "
                f"large_backlog={large_backlog}"
            ),
            hard=False,
        )
    ]

    last_arrival_time = summary.get("last_arrival_time_seconds")
    all_arrivals_seen = int(last["arrivals"]) == size and last_arrival_time is not None
    window_after_last_arrival = (
        all_arrivals_seen and float(first["time_seconds"]) >= float(last_arrival_time)
    )
    no_drain = (
        len(window) >= thresholds.recent_window_snapshots
        and window_after_last_arrival
        and int(first["backlog"]) > 0
        and int(last["backlog"]) >= int(first["backlog"])
    )
    results.append(
        _criterion(
            "post_arrival_backlog_not_draining",
            no_drain,
            (
                f"all_arrivals_seen={all_arrivals_seen} "
                f"window_after_last_arrival={window_after_last_arrival} "
                f"backlog_start={first['backlog']} backlog_end={last['backlog']}"
            ),
            hard=False,
        )
    )

    utilization = {
        str(key): float(value)
        for key, value in last["critical_junction_utilization"].items()
    }
    max_utilization = max(utilization.values())
    low_utilization = (
        backlog >= large_backlog
        and max_utilization <= thresholds.low_critical_utilization_max
    )
    results.append(
        _criterion(
            "large_backlog_with_low_critical_utilization",
            low_utilization,
            (
                f"backlog={backlog} large_backlog={large_backlog} "
                f"max_critical_utilization={max_utilization:.6f} "
                f"ceiling={thresholds.low_critical_utilization_max:.6f}"
            ),
            hard=False,
        )
    )

    cycle_window = snapshots[-thresholds.repeated_cycle_snapshots :]
    cycle_ids = [row.get("wait_for_cycle_id") for row in cycle_window]
    repeated_cycle = (
        len(cycle_window) == thresholds.repeated_cycle_snapshots
        and all(isinstance(value, str) and value for value in cycle_ids)
        and len(set(cycle_ids)) == 1
    )
    results.append(
        _criterion(
            "repeated_wait_for_cycle",
            repeated_cycle,
            f"recent_cycle_ids={cycle_ids}",
        )
    )

    source_hold_delta = int(last["source_holds"]) - int(first["source_holds"])
    hold_threshold = max(
        thresholds.minimum_source_hold_delta,
        math.ceil(size * thresholds.source_hold_delta_fraction),
    )
    source_hold_no_throughput = (
        len(window) >= thresholds.recent_window_snapshots
        and source_hold_delta >= hold_threshold
        and departures_delta == 0
    )
    results.append(
        _criterion(
            "source_holds_without_network_throughput",
            source_hold_no_throughput,
            (
                f"source_hold_delta={source_hold_delta} threshold={hold_threshold} "
                f"departures_delta={departures_delta}"
            ),
            hard=False,
        )
    )

    interval_rates: list[float] = []
    interval_departures: list[int] = []
    interval_events: list[int] = []
    for left, right in zip(window, window[1:]):
        time_delta = float(right["time_seconds"]) - float(left["time_seconds"])
        event_delta = int(right["event_count"]) - int(left["event_count"])
        departure_delta = int(right["departures"]) - int(left["departures"])
        interval_events.append(event_delta)
        interval_departures.append(departure_delta)
        interval_rates.append(event_delta / max(time_delta, 1.0e-9))
    if len(interval_rates) >= 2:
        baseline_rate = statistics.median(interval_rates[:-1])
        last_rate = interval_rates[-1]
        nonlinear_events = (
            interval_events[-1] >= thresholds.minimum_last_interval_events
            and last_rate
            >= max(1.0e-9, baseline_rate)
            * thresholds.nonlinear_interval_rate_factor
            and interval_departures[-1] == 0
            and backlog >= large_backlog
        )
    else:
        baseline_rate = 0.0
        last_rate = 0.0
        nonlinear_events = False
    results.append(
        _criterion(
            "nonlinear_event_rate_without_progress",
            nonlinear_events,
            (
                f"interval_rates={interval_rates} baseline_rate={baseline_rate:.6f} "
                f"last_rate={last_rate:.6f} interval_events={interval_events} "
                f"interval_departures={interval_departures}"
            ),
        )
    )

    projected_p99 = summary.get("projected_p99_seconds")
    control_p99 = float(summary["control_p99_seconds"])
    p99_ratio = (
        float(projected_p99) / control_p99 if projected_p99 is not None else None
    )
    p99_abort = (
        p99_ratio is not None and p99_ratio >= thresholds.p99_control_ratio_abort
    )
    results.append(
        _criterion(
            "p99_projection_far_above_control",
            p99_abort,
            (
                f"projected_p99={projected_p99} control_p99={control_p99} "
                f"ratio={p99_ratio} threshold={thresholds.p99_control_ratio_abort}"
            ),
        )
    )

    starvation_delta = int(last["starvation_count"]) - int(first["starvation_count"])
    starvation_total_threshold = max(
        thresholds.minimum_starvation_total,
        math.ceil(size * thresholds.starvation_total_fraction),
    )
    starvation_window_threshold = max(
        thresholds.minimum_starvation_window,
        math.ceil(size * thresholds.starvation_window_fraction),
    )
    rapid_starvation = (
        int(last["starvation_count"]) >= starvation_total_threshold
        and starvation_delta >= starvation_window_threshold
    )
    results.append(
        _criterion(
            "rapid_starvation_accumulation",
            rapid_starvation,
            (
                f"total={last['starvation_count']} total_threshold={starvation_total_threshold} "
                f"window_delta={starvation_delta} "
                f"window_threshold={starvation_window_threshold}"
            ),
        )
    )
    return results


def _candidate_signature(descriptor: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_json_bytes(
            {
                "identity": descriptor["identity"],
                "reproducibility": descriptor["reproducibility"],
            }
        )
    ).hexdigest()


def _deterministic_outcome_signature(descriptor: Mapping[str, Any]) -> str:
    """Hash simulation outcomes while excluding host wall-clock timing."""

    summary = {
        key: value
        for key, value in descriptor["summary"].items()
        if key != "wall_seconds"
    }
    snapshots = [
        {key: value for key, value in snapshot.items() if key != "wall_seconds"}
        for snapshot in descriptor["snapshots"]
    ]
    return hashlib.sha256(
        _canonical_json_bytes(
            {
                "execution_status": descriptor["execution_status"],
                "termination_reason": descriptor["termination_reason"],
                "summary": summary,
                "snapshots": snapshots,
            }
        )
    ).hexdigest()


def _cross_tier_criteria(
    previous: Mapping[str, Any],
    current: Mapping[str, Any],
    thresholds: DiagnosticThresholds,
) -> list[dict[str, Any]]:
    previous_size = int(previous["size_segments"])
    current_size = int(current["size_segments"])
    previous_summary = previous["summary"]
    current_summary = current["summary"]
    previous_events_per_segment = float(previous_summary["event_count"]) / previous_size
    current_events_per_segment = float(current_summary["event_count"]) / current_size
    event_ratio = current_events_per_segment / max(previous_events_per_segment, 1.0e-12)

    previous_snapshots = previous["snapshots"]
    current_snapshots = current["snapshots"]
    previous_span = (
        float(previous_snapshots[-1]["time_seconds"])
        - float(previous_snapshots[0]["time_seconds"])
        if len(previous_snapshots) >= 2
        else float(previous_summary["simulation_horizon_seconds"])
    )
    current_span = (
        float(current_snapshots[-1]["time_seconds"])
        - float(current_snapshots[0]["time_seconds"])
        if len(current_snapshots) >= 2
        else float(current_summary["simulation_horizon_seconds"])
    )
    previous_horizon_per_segment = previous_span / previous_size
    current_horizon_per_segment = current_span / current_size
    horizon_ratio = current_horizon_per_segment / max(previous_horizon_per_segment, 1.0e-12)
    threshold = thresholds.cross_tier_normalized_growth_factor
    return [
        _criterion(
            "cross_tier_nonlinear_event_growth",
            event_ratio >= threshold,
            (
                f"previous_size={previous_size} current_size={current_size} "
                f"events_per_segment={previous_events_per_segment:.9f}->"
                f"{current_events_per_segment:.9f} ratio={event_ratio:.6f} "
                f"threshold={threshold}"
            ),
        ),
        _criterion(
            "cross_tier_nonlinear_horizon_growth",
            horizon_ratio >= threshold,
            (
                f"previous_size={previous_size} current_size={current_size} "
                f"horizon_per_segment={previous_horizon_per_segment:.9f}->"
                f"{current_horizon_per_segment:.9f} ratio={horizon_ratio:.6f} "
                f"threshold={threshold}"
            ),
        ),
    ]


def _blank_row(raw: Any, errors: Sequence[str]) -> dict[str, Any]:
    descriptor = raw if isinstance(raw, Mapping) else {}
    summary = descriptor.get("summary") if isinstance(descriptor.get("summary"), Mapping) else {}
    try:
        raw_digest = _descriptor_sha256(descriptor) if descriptor else ""
    except (TypeError, ValueError):
        raw_digest = ""
    return {
        "attempt_id": str(descriptor.get("attempt_id", "")),
        "attempt_index": descriptor.get("attempt_index", ""),
        "candidate_id": str(descriptor.get("candidate_id", "")),
        "size_segments": descriptor.get("size_segments", ""),
        "size_label": SIZE_LABELS.get(descriptor.get("size_segments"), ""),
        "descriptor_status": "INVALID_RESULT_DESCRIPTOR",
        "execution_status": str(descriptor.get("execution_status", "")),
        "termination_reason": str(descriptor.get("termination_reason", "")),
        "diagnostic_status": "INVALID_RESULT_DESCRIPTOR",
        "promotion_decision": "HOLD_INVALID_DESCRIPTOR",
        "arrivals": summary.get("arrivals", ""),
        "admissions": summary.get("admissions", ""),
        "departures": summary.get("departures", ""),
        "end_backlog": summary.get("end_backlog", ""),
        "peak_backlog": summary.get("peak_backlog", ""),
        "critical_max_utilization": "",
        "deadlock_episode_count": summary.get("deadlock_episode_count", ""),
        "unresolved_deadlock_count": summary.get("unresolved_deadlock_count", ""),
        "starvation_count": summary.get("starvation_count", ""),
        "source_hold_count": summary.get("source_hold_count", ""),
        "event_count": summary.get("event_count", ""),
        "simulation_horizon_seconds": summary.get("simulation_horizon_seconds", ""),
        "wall_seconds": summary.get("wall_seconds", ""),
        "projected_p99_seconds": summary.get("projected_p99_seconds", ""),
        "control_p99_seconds": summary.get("control_p99_seconds", ""),
        "triggered_criteria": "",
        "warning_criteria": "",
        "blockers": " | ".join(errors),
        "descriptor_sha256": raw_digest,
        "criteria": [],
        "descriptor": None,
    }


def evaluate_ladder_attempts(
    descriptors: Sequence[Any],
    thresholds: DiagnosticThresholds = DEFAULT_THRESHOLDS,
) -> list[dict[str, Any]]:
    """Validate, diagnose, sequence, and retain all supplied attempts."""

    prepared: list[tuple[str, int, int, Any, list[str]]] = []
    seen_attempt_ids: set[str] = set()
    seen_indices: set[tuple[str, int]] = set()
    for ordinal, raw in enumerate(descriptors):
        errors = descriptor_validation_errors(raw)
        descriptor = raw if isinstance(raw, Mapping) else {}
        candidate = str(descriptor.get("candidate_id", ""))
        attempt_index_raw = descriptor.get("attempt_index")
        attempt_index = int(attempt_index_raw) if _is_int(attempt_index_raw) else 10**12 + ordinal
        attempt_id = str(descriptor.get("attempt_id", ""))
        if attempt_id and attempt_id in seen_attempt_ids:
            errors.append(f"duplicate attempt_id: {attempt_id}")
        elif attempt_id:
            seen_attempt_ids.add(attempt_id)
        index_key = (candidate, attempt_index)
        if candidate and attempt_index < 10**12 and index_key in seen_indices:
            errors.append(
                f"duplicate attempt_index for candidate {candidate}: {attempt_index}"
            )
        elif candidate and attempt_index < 10**12:
            seen_indices.add(index_key)
        prepared.append((candidate, attempt_index, ordinal, raw, errors))

    prepared.sort(key=lambda item: (item[0], item[1], item[2]))
    rows: list[dict[str, Any]] = []
    candidate_signatures: dict[str, str] = {}
    cleared_sizes: dict[str, set[int]] = {}
    cleared_descriptors: dict[tuple[str, int], Mapping[str, Any]] = {}
    deterministic_outcomes: dict[tuple[str, int], str] = {}
    tainted_from_tier: dict[str, int] = {}

    for candidate, _attempt_index, _ordinal, raw, errors in prepared:
        if errors:
            rows.append(_blank_row(raw, errors))
            continue
        descriptor = dict(raw)
        signature = _candidate_signature(descriptor)
        expected_signature = candidate_signatures.setdefault(candidate, signature)
        if signature != expected_signature:
            rows.append(
                _blank_row(
                    descriptor,
                    [
                        "candidate identity/reproducibility changed across attempts; "
                        "use a new candidate_id"
                    ],
                )
            )
            continue

        size = int(descriptor["size_segments"])
        criteria = diagnose_result_descriptor(descriptor, thresholds)
        tier_index = SIZE_LADDER.index(size)
        prior_size = SIZE_LADDER[tier_index - 1] if tier_index > 0 else None
        if prior_size is not None and (candidate, prior_size) in cleared_descriptors:
            criteria.extend(
                _cross_tier_criteria(
                    cleared_descriptors[(candidate, prior_size)], descriptor, thresholds
                )
            )

        tier_key = (candidate, size)
        tier_taint = tainted_from_tier.get(candidate)
        if tier_taint is not None and tier_index >= tier_taint:
            criteria.append(
                _criterion(
                    "candidate_reproducibility_tainted",
                    True,
                    (
                        f"candidate was already tainted at ladder index {tier_taint}; "
                        "use a new candidate_id after correcting reproducibility"
                    ),
                    hard=True,
                )
            )
        if descriptor["execution_status"] != "FAILED" and descriptor[
            "termination_reason"
        ] != "USER_STOP":
            outcome_signature = _deterministic_outcome_signature(descriptor)
            prior_outcome = deterministic_outcomes.setdefault(tier_key, outcome_signature)
            if prior_outcome != outcome_signature:
                criteria.append(
                    _criterion(
                        "deterministic_repeat_mismatch",
                        True,
                        (
                            f"same candidate/tier produced {prior_outcome} then "
                            f"{outcome_signature} under the frozen reproducibility identity"
                        ),
                        hard=True,
                    )
                )
                tainted_from_tier[candidate] = min(
                    tier_index, tainted_from_tier.get(candidate, tier_index)
                )
                for tainted_size in SIZE_LADDER[tier_index:]:
                    cleared_sizes.get(candidate, set()).discard(tainted_size)
                    cleared_descriptors.pop((candidate, tainted_size), None)

        triggered = [row for row in criteria if row["triggered"]]
        hard_triggered = [row for row in triggered if row["hard"]]
        soft_triggered = [row for row in triggered if not row["hard"]]
        collapse = bool(hard_triggered) or len(soft_triggered) >= thresholds.composite_soft_trigger_count
        warning = bool(soft_triggered) and not collapse
        termination_reason = str(descriptor["termination_reason"])
        if termination_reason == EARLY_ABORT_STATUS and not collapse:
            collapse = True
            criteria.append(
                _criterion(
                    "runner_declared_diagnostic_collapse",
                    True,
                    "runner terminated with the frozen early-abort status",
                    hard=True,
                )
            )
            triggered = [row for row in criteria if row["triggered"]]

        missing_prior = prior_size is not None and prior_size not in cleared_sizes.get(candidate, set())
        execution_clear = (
            descriptor["execution_status"] == "EXECUTED"
            and termination_reason == "DRAINED"
        )
        blockers: list[str] = []
        if missing_prior:
            blockers.append(f"missing accepted prior tier {prior_size}")
        if collapse:
            diagnostic_status = EARLY_ABORT_STATUS
            blockers.append("diagnostic collapse criteria triggered")
        elif not execution_clear:
            diagnostic_status = "INCOMPLETE_OR_NEGATIVE_RESULT"
            blockers.append(
                f"execution={descriptor['execution_status']} termination={termination_reason}"
            )
        elif warning:
            diagnostic_status = "DIAGNOSTIC_WARNING_HOLD"
            blockers.append("one soft collapse symptom requires review")
        else:
            diagnostic_status = "CLEAR"

        already_cleared = size in cleared_sizes.get(candidate, set())
        if missing_prior:
            promotion = "HOLD_MISSING_PRIOR_TIER"
        elif collapse:
            promotion = "HOLD_DIAGNOSTIC_COLLAPSE"
        elif not execution_clear:
            promotion = "HOLD_INCOMPLETE_OR_NEGATIVE_RESULT"
        elif warning:
            promotion = "HOLD_DIAGNOSTIC_WARNING"
        elif already_cleared:
            promotion = "REPEAT_EVIDENCE_RETAINED"
        elif size == FULL_SIZE_SEGMENTS:
            promotion = "ORIGINAL_1X_DIAGNOSTIC_COMPLETE_NOT_FINAL_GATE"
            cleared_sizes.setdefault(candidate, set()).add(size)
            cleared_descriptors[(candidate, size)] = descriptor
        else:
            promotion = "ELIGIBLE_FOR_NEXT_SIZE"
            cleared_sizes.setdefault(candidate, set()).add(size)
            cleared_descriptors[(candidate, size)] = descriptor

        summary = descriptor["summary"]
        utilization = {
            str(key): float(value)
            for key, value in summary["critical_junction_utilization"].items()
        }
        rows.append(
            {
                "attempt_id": descriptor["attempt_id"],
                "attempt_index": descriptor["attempt_index"],
                "candidate_id": candidate,
                "size_segments": size,
                "size_label": SIZE_LABELS[size],
                "descriptor_status": "VALID",
                "execution_status": descriptor["execution_status"],
                "termination_reason": termination_reason,
                "diagnostic_status": diagnostic_status,
                "promotion_decision": promotion,
                "arrivals": summary["arrivals"],
                "admissions": summary["admissions"],
                "departures": summary["departures"],
                "end_backlog": summary["end_backlog"],
                "peak_backlog": summary["peak_backlog"],
                "critical_max_utilization": max(utilization.values()),
                "deadlock_episode_count": summary["deadlock_episode_count"],
                "unresolved_deadlock_count": summary["unresolved_deadlock_count"],
                "starvation_count": summary["starvation_count"],
                "source_hold_count": summary["source_hold_count"],
                "event_count": summary["event_count"],
                "simulation_horizon_seconds": summary["simulation_horizon_seconds"],
                "wall_seconds": summary["wall_seconds"],
                "projected_p99_seconds": summary["projected_p99_seconds"],
                "control_p99_seconds": summary["control_p99_seconds"],
                "triggered_criteria": ";".join(
                    row["criterion_id"] for row in triggered if row["hard"]
                ),
                "warning_criteria": ";".join(
                    row["criterion_id"] for row in triggered if not row["hard"]
                ),
                "blockers": " | ".join(blockers),
                "descriptor_sha256": _descriptor_sha256(descriptor),
                "criteria": criteria,
                "descriptor": descriptor,
            }
        )
    return rows


def authorize_requested_size(
    evaluations: Sequence[Mapping[str, Any]],
    *,
    candidate_id: str,
    requested_size: int,
) -> None:
    """Raise unless ``requested_size`` is authorized by the preceding tier."""

    if requested_size not in SIZE_LADDER:
        raise PermissionError(
            f"requested size {requested_size} is outside the original-1x ladder; "
            "scaled workloads are forbidden"
        )
    if requested_size == SIZE_LADDER[0]:
        return
    prior_size = SIZE_LADDER[SIZE_LADDER.index(requested_size) - 1]
    prior_rows = [
        row
        for row in evaluations
        if (
            row.get("candidate_id") == candidate_id
            and row.get("size_segments") == prior_size
        )
    ]
    latest = prior_rows[-1] if prior_rows else {}
    accepted = latest.get("promotion_decision") in {
        "ELIGIBLE_FOR_NEXT_SIZE",
        "ORIGINAL_1X_DIAGNOSTIC_COMPLETE_NOT_FINAL_GATE",
        "REPEAT_EVIDENCE_RETAINED",
    }
    if not accepted:
        raise PermissionError(
            f"candidate {candidate_id!r} has not cleared prior tier {prior_size}; "
            f"refusing requested tier {requested_size}"
        )


def _atomic_write(path: Path, payload: bytes) -> None:
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


def _csv_bytes(columns: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(columns), extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    return buffer.getvalue().encode("utf-8")


def _evidence_rows(
    evaluations: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    backlog_rows: list[dict[str, Any]] = []
    utilization_rows: list[dict[str, Any]] = []
    for evaluation in evaluations:
        descriptor = evaluation.get("descriptor")
        if not isinstance(descriptor, Mapping):
            continue
        summary = descriptor["summary"]
        last_arrival = summary.get("last_arrival_time_seconds")
        for index, snapshot in enumerate(descriptor["snapshots"]):
            base = {
                "attempt_id": descriptor["attempt_id"],
                "candidate_id": descriptor["candidate_id"],
                "size_segments": descriptor["size_segments"],
                "snapshot_index": index,
                "time_seconds": snapshot["time_seconds"],
                "wall_seconds": snapshot["wall_seconds"],
                "arrivals": snapshot["arrivals"],
                "admissions": snapshot["admissions"],
                "departures": snapshot["departures"],
                "backlog": snapshot["backlog"],
                "source_holds": snapshot["source_holds"],
                "event_count": snapshot["event_count"],
                "starvation_count": snapshot["starvation_count"],
                "deadlock_episode_count": snapshot["deadlock_episode_count"],
                "after_last_arrival": (
                    last_arrival is not None
                    and float(snapshot["time_seconds"]) >= float(last_arrival)
                ),
            }
            backlog_rows.append(base)
            for junction_id, utilization in sorted(
                snapshot["critical_junction_utilization"].items(),
                key=lambda item: str(item[0]),
            ):
                utilization_rows.append(
                    {
                        "attempt_id": descriptor["attempt_id"],
                        "candidate_id": descriptor["candidate_id"],
                        "size_segments": descriptor["size_segments"],
                        "snapshot_index": index,
                        "time_seconds": snapshot["time_seconds"],
                        "junction_id": junction_id,
                        "utilization": utilization,
                        "backlog": snapshot["backlog"],
                    }
                )
    return backlog_rows, utilization_rows


def _report_text(
    evaluations: Sequence[Mapping[str, Any]],
    thresholds: DiagnosticThresholds,
) -> str:
    if not evaluations:
        status = "PROTOCOL_READY_NO_ATTEMPTS"
    elif any(row.get("descriptor_status") != "VALID" for row in evaluations):
        status = "PARTIAL_WITH_EXPLICIT_BLOCKER"
    elif evaluations and all(
        row.get("promotion_decision")
        == "ORIGINAL_1X_DIAGNOSTIC_COMPLETE_NOT_FINAL_GATE"
        for row in evaluations
        if row.get("size_segments") == FULL_SIZE_SEGMENTS
    ) and any(row.get("size_segments") == FULL_SIZE_SEGMENTS for row in evaluations):
        status = "DIAGNOSTIC_LADDER_COMPLETE_NOT_FINAL_GATE"
    else:
        status = "PARTIAL_WITH_EXPLICIT_BLOCKER"

    lines = [
        "# G4IRSF12-D Early-Abort Diagnostics",
        "",
        f"Status: `{status}`.",
        "",
        "This report is size-ladder diagnostic evidence, not a final performance gate.",
        "It never authorizes 1.1x or larger workloads. Empty tables mean no runtime",
        "attempt was executed; they are not PASS evidence.",
        "",
        "## Frozen protocol",
        "",
        f"- Segment ladder: `{' -> '.join(str(value) for value in SIZE_LADDER)}`.",
        f"- Full original workload: `{FULL_SIZE_SEGMENTS}` segments / `{FULL_SIZE_BAGS}` bags.",
        f"- Input order: `{INPUT_ORDER_ID}`.",
        f"- Prefix selection: `{PREFIX_SELECTION_ID}`.",
        f"- Early-abort status: `{EARLY_ABORT_STATUS}`.",
        "- One soft symptom holds promotion for review; two simultaneous soft symptoms abort.",
        "- Any repeated cycle, nonlinear event growth, gross p99 projection, or rapid starvation aborts.",
        "",
        "## Attempts (negative and partial attempts retained)",
        "",
        "| Candidate | Attempt | Size | Descriptor | Diagnostic | Promotion | Blockers |",
        "| --- | --- | ---: | --- | --- | --- | --- |",
    ]
    if not evaluations:
        lines.append(
            "| — | — | — | NO_ATTEMPTS | NOT_EVALUATED | NOT_AUTHORIZED | No descriptor supplied |"
        )
    else:
        for row in evaluations:
            blockers = str(row.get("blockers") or "").replace("|", "/")
            lines.append(
                "| {candidate} | {attempt} | {size} | {descriptor} | {diagnostic} | "
                "{promotion} | {blockers} |".format(
                    candidate=row.get("candidate_id", ""),
                    attempt=row.get("attempt_id", ""),
                    size=row.get("size_segments", ""),
                    descriptor=row.get("descriptor_status", ""),
                    diagnostic=row.get("diagnostic_status", ""),
                    promotion=row.get("promotion_decision", ""),
                    blockers=blockers or "—",
                )
            )

    lines.extend(
        [
            "",
            "## Diagnostic thresholds",
            "",
            "```json",
            json.dumps(asdict(thresholds), ensure_ascii=False, indent=2, sort_keys=True),
            "```",
            "",
            "## Claim boundary",
            "",
            "`ELIGIBLE_FOR_NEXT_SIZE` authorizes only the immediately following original-1x "
            "tier. `ORIGINAL_1X_DIAGNOSTIC_COMPLETE_NOT_FINAL_GATE` is not an algorithm PASS, "
            "does not establish superiority over historical HCA*, and does not authorize scaling.",
            "",
        ]
    )
    return "\n".join(lines)


def write_diagnostic_outputs(
    descriptors: Sequence[Any],
    *,
    root: Path = ROOT,
    thresholds: DiagnosticThresholds = DEFAULT_THRESHOLDS,
) -> tuple[list[dict[str, Any]], tuple[Path, Path, Path, Path]]:
    """Validate protected inputs and atomically write all four D outputs."""

    assert_protected_inputs(root)
    evaluations = evaluate_ladder_attempts(descriptors, thresholds)
    backlog_rows, utilization_rows = _evidence_rows(evaluations)
    size_path = root / OUTPUT_PATHS["size_ladder"]
    report_path = root / OUTPUT_PATHS["report"]
    backlog_path = root / OUTPUT_PATHS["backlog"]
    utilization_path = root / OUTPUT_PATHS["utilization"]
    _atomic_write(size_path, _csv_bytes(SIZE_LADDER_COLUMNS, evaluations))
    _atomic_write(backlog_path, _csv_bytes(BACKLOG_COLUMNS, backlog_rows))
    _atomic_write(
        utilization_path,
        _csv_bytes(UTILIZATION_COLUMNS, utilization_rows),
    )
    _atomic_write(report_path, _report_text(evaluations, thresholds).encode("utf-8"))
    return evaluations, (size_path, report_path, backlog_path, utilization_path)
