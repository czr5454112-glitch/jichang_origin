"""Reproducible G4IRSF12 B/C/E/F/G/H/J planning and execution harness.

The harness is deliberately fail closed:

* the only graph and input are the protected ``map2.json`` and
  ``inputdata.jsonl`` artifacts;
* every diagnostic workload is the first N non-empty input rows in file order;
* plan-only rows are ``NOT_RUN`` / ``PENDING`` and can never become PASS;
* 8,192 and 43,603 segment runs require explicit authorization and accepted
  prior-tier evidence;
* executor capabilities are inspected before invocation, so future
  pressure/credit/PIBT controls are never silently dropped by an older wrapper;
* raw-bag timing is recomputed from the protected input rather than accepted
  from a runtime summary.

This module does not execute anything at import time.  The companion CLI is
``run_g4irsf12_reproducible_harness.py``.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from functools import lru_cache
import hashlib
import inspect
import io
import json
import math
import os
from pathlib import Path
import statistics
import tempfile
from typing import Any, Callable, Iterable, Mapping, MutableMapping, Sequence

from scripts.eval.g4irsf11_experiment_protocol import fault_windows
from scripts.eval.g4irsf12_size_ladder import (
    CANONICAL_MAP_PATH,
    CANONICAL_MAP_RAW_SHA256,
    CANONICAL_MAP_SEMANTIC_SHA256,
    CANONICAL_SOURCE_PATH,
    CANONICAL_SOURCE_RAW_SHA256,
    CANONICAL_SOURCE_SEMANTIC_SHA256,
    EARLY_ABORT_STATUS,
    FULL_SIZE_BAGS,
    FULL_SIZE_SEGMENTS,
    INPUT_ORDER_ID,
    PREFIX_SELECTION_ID,
    SIZE_LADDER,
    assert_protected_inputs,
)


ROOT = Path(__file__).resolve().parents[2]

HARNESS_SCHEMA = "czr005.g4irsf12.reproducible_harness.v2"
CASE_SCHEMA = "czr005.g4irsf12.experiment_case.v2"
RESULT_SCHEMA = "czr005.g4irsf12.experiment_result.v2"
CANDIDATE_BUNDLE_SCHEMA = "czr005.g4irsf12.original_scale_candidate_bundle.v2"
G4J_STATUS = "CLOSED"
HISTORICAL_HCA_PROCESSED_ATTEMPT_MINUTES = 3.967122711
FROZEN_V2_SAFE_ORIGINAL_ENTRY_MINUTES = 4.124305453
CORRECTED_HCA_ORIGINAL_ENTRY_MINUTES = 5.764936746
PROCESSED_ATTEMPT_WARNING = (
    "3.967122711 is processed-segment-attempt evidence and is not comparable "
    "to original_entry_time_tth"
)
PREFIX_HASH_SEMANTICS = (
    "sha256_of_selected_nonempty_original_utf8_jsonl_lines_normalized_to_lf"
)
RESULT_HASH_SEMANTICS = (
    "canonical_json_sha256_excluding_wall_clock_memory_and_throughput_measurements"
)

RESOURCE_LABELS = ("R0", "R1", "R2", "R3", "R4")
SCORER_LABELS = ("S0", "S1", "S2", "S3", "S4")
PIBT_LABELS = ("P0", "P1", "P2", "P3", "P4")
CONTROL_LABELS = ("C0", "C1", "C2", "C3", "C4", "C5", "C6")
FRAMEWORK_LABELS = ("B0", "B1", "B2", "B3", "B4", "B5", "B6")

RESOURCE_MODES = {
    "R0": "R0_current_undirected_full_travel_exclusive",
    "R1": "R1_directed_full_travel_exclusive",
    "R2": "R2_directed_entry_headway",
    "R3": "R3_java_node_window_compatible",
    "R4": "R4_directed_headway_plus_merge_service_calendar",
}
SCORER_MODES = {
    "S0": "S0_current_handwritten",
    "S1": "S1_frozen_g4e_legal_local_adapter",
    "S2": "S2_frozen_g4e_without_absolute_node_ids",
    "S3": "S3_shortest_potential_only",
    "S4": "S4_queue_aware_rule_only",
}
PRESSURE_ADMISSION_MODES = {
    "C0": ("off", "off"),
    "C1": ("absolute_downstream_queue_penalty", "off"),
    "C2": ("goal_conditioned_differential", "off"),
    "C3": ("distance_biased_differential", "off"),
    "C4": ("off", "expiring_first_edge_credit"),
    "C5": (
        "goal_conditioned_differential",
        "expiring_first_edge_credit",
    ),
    "C6": (
        "goal_conditioned_differential",
        "expiring_first_edge_credit",
    ),
}
PLANNING_RESOURCE_ANCHOR = "R3"
PLANNING_SCORER_ANCHOR = "S0"
F_RUNTIME_LOCAL_QUEUE_CAPACITY = 32
FORMAL_MAX_EVENTS = 20_000_000
FROZEN_NUMERIC_RUNTIME_CONTROLS: Mapping[str, int | float] = {
    "entry_headway_seconds": 0.001,
    "pressure_weight": 2.0,
    "pressure_age_weight": 0.05,
    "pressure_distance_bias": 0.25,
    "credit_validity_seconds": 1.0,
    "credit_snapshot_max_age_seconds": 1.0,
    "credit_capacity_per_edge": 1,
    "credit_lifecycle_limit": 512,
    "pibt_max_ready_bags": 8,
    "pibt_max_local_resources": 32,
    "pibt_max_candidates_per_bag": 8,
}

OUTPUT_PATHS = {
    "protocol_manifest": "artifacts/configs/g4irsf12_reproducible_harness_manifest.json",
    "framework_csv": "outputs/tables/g4irsf12_framework_delta_ladder.csv",
    "framework_report": "outputs/reports/g4irsf12_framework_delta_ladder.md",
    "resource_runtime_csv": "outputs/tables/g4irsf12_resource_semantics_runtime_plan.csv",
    "resource_runtime_report": "outputs/reports/g4irsf12_resource_semantics_runtime_plan.md",
    "scorer_closed_loop_csv": "outputs/tables/g4irsf12_scorer_closed_loop_plan.csv",
    "scorer_closed_loop_report": "outputs/reports/g4irsf12_scorer_closed_loop_plan.md",
    "pibt_depth_csv": "outputs/tables/g4irsf12_pibt_depth_ablation.csv",
    "pibt_wait_for_csv": "outputs/tables/g4irsf12_wait_for_cycle_audit.csv",
    "pibt_wait_for_motifs_csv": "outputs/tables/g4irsf12_wait_for_cycle_motifs.csv",
    "pibt_atomic_csv": "outputs/tables/g4irsf12_atomic_coordination_audit.csv",
    "pibt_atomic_commit_rollback_csv": "outputs/tables/g4irsf12_atomic_commit_rollback.csv",
    "pibt_runtime_report": "outputs/reports/g4irsf12_bounded_local_pibt_runtime_plan.md",
    "pressure_csv": "outputs/tables/g4irsf12_pressure_mode_ablation.csv",
    "credit_csv": "outputs/tables/g4irsf12_credit_lifecycle.csv",
    "queue_csv": "outputs/tables/g4irsf12_goal_conditioned_queue_state.csv",
    "oscillation_csv": "outputs/tables/g4irsf12_route_oscillation_audit.csv",
    "pressure_report": "outputs/reports/g4irsf12_pressure_credit_design.md",
    "fault_csv": "outputs/tables/g4irsf12_fault_recovery_stable_load.csv",
    "fault_credit_csv": "outputs/tables/g4irsf12_fault_credit_invalidation.csv",
    "fault_pibt_csv": "outputs/tables/g4irsf12_fault_pibt_handoff.csv",
    "fault_report": "outputs/reports/g4irsf12_stable_load_fault_recovery.md",
    "full_csv": "outputs/tables/g4irsf12_original_scale_full_ab.csv",
    "full_report": "outputs/reports/g4irsf12_original_scale_full_ab.md",
    "denominator_report": "outputs/reports/g4irsf12_original_entry_denominator_report.md",
    "promotion_report": "outputs/reports/g4irsf12_promotion_gate.md",
    "candidate_bundle": "artifacts/policies/g4irsf12_original_scale_candidate_bundle.json",
}

CONTROL_EVIDENCE_PATHS = {
    "denominators": "outputs/tables/g4irsf8_tth_denominator_comparison.csv",
    "g4irsf11_ledger": "outputs/tables/g4irsf11_event_runtime_case_ledger.csv",
}

NONDETERMINISTIC_RESULT_KEYS = {
    "wall_seconds",
    "runtime_seconds",
    "event_throughput_per_second",
    "peak_working_set_bytes",
    "working_set_bytes",
    "peak_rss_bytes",
    "rss_bytes",
    "decision_latency_us_p50",
    "decision_latency_us_p95",
    "decision_latency_us_p99",
    "timestamp",
    "started_at",
    "finished_at",
}
TRACE_KEYS = {
    "trace",
    "decisions",
    "decision_trace",
    "events",
    "event_trace",
    "fault_events",
    "credit_events",
    "pibt_events",
}


class HarnessValidationError(ValueError):
    """Raised when an artifact cannot be admitted as experiment evidence."""


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    phase: str
    candidate_id: str
    framework_label: str = ""
    resource_label: str = "R0"
    scorer_label: str = "S0"
    pibt_label: str = "P0"
    control_label: str = "C0"
    fault_profile: str = "no_fault"
    sizes: tuple[int, ...] = SIZE_LADDER
    runtime_controls: Mapping[str, Any] = field(default_factory=dict)
    required_capabilities: tuple[str, ...] = ()
    notes: str = ""
    finalist_role: str = ""
    execution_blocker: str = ""

    def __post_init__(self) -> None:
        if self.phase not in {"B", "C", "E", "F", "G", "H", "J"}:
            raise HarnessValidationError(f"unknown phase: {self.phase}")
        if not self.case_id or not self.candidate_id:
            raise HarnessValidationError("case_id and candidate_id must be non-empty")
        if self.framework_label and self.framework_label not in FRAMEWORK_LABELS:
            raise HarnessValidationError(
                f"unknown framework label: {self.framework_label}"
            )
        if self.resource_label not in RESOURCE_LABELS:
            raise HarnessValidationError(
                f"unknown resource label: {self.resource_label}"
            )
        if self.scorer_label not in SCORER_LABELS:
            raise HarnessValidationError(
                f"unknown scorer label: {self.scorer_label}"
            )
        if self.pibt_label not in PIBT_LABELS:
            raise HarnessValidationError(f"unknown PIBT label: {self.pibt_label}")
        if self.control_label not in CONTROL_LABELS:
            raise HarnessValidationError(
                f"unknown pressure/admission label: {self.control_label}"
            )
        if not self.sizes or any(size not in SIZE_LADDER for size in self.sizes):
            raise HarnessValidationError(
                f"sizes must be a non-empty subset of {SIZE_LADDER}"
            )
        if tuple(sorted(set(self.sizes), key=SIZE_LADDER.index)) != self.sizes:
            raise HarnessValidationError(
                "sizes must be unique and follow the frozen ladder order"
            )
        controls = dict(self.runtime_controls)
        if "max_events" in controls and int(controls["max_events"]) != FORMAL_MAX_EVENTS:
            raise HarnessValidationError(
                f"max_events must use the frozen ceiling {FORMAL_MAX_EVENTS}"
            )
        controls["max_events"] = FORMAL_MAX_EVENTS
        for name, expected in FROZEN_NUMERIC_RUNTIME_CONTROLS.items():
            if name in controls and controls[name] != expected:
                raise HarnessValidationError(
                    f"{name} must use the frozen value {expected}"
                )
            controls[name] = expected
        object.__setattr__(self, "runtime_controls", controls)

    def as_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["schema"] = CASE_SCHEMA
        row["sizes"] = list(self.sizes)
        row["runtime_controls"] = dict(self.runtime_controls)
        row["required_capabilities"] = list(self.required_capabilities)
        return row


@dataclass(frozen=True)
class InputPrefix:
    size_segments: int
    rows: tuple[dict[str, Any], ...]
    prefix_sha256: str
    raw_bag_count: int
    first_segment_id: str
    last_segment_id: str


@dataclass(frozen=True)
class ExecutorCapabilities:
    accepts_request_envelope: bool
    accepts_var_kwargs: bool
    parameters: tuple[str, ...]
    source_path: str
    source_sha256: str

    def supports(self, name: str) -> bool:
        return (
            self.accepts_request_envelope
            or self.accepts_var_kwargs
            or name in self.parameters
        )


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    if not path.is_file():
        raise HarnessValidationError(f"missing hash input: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_bundle_sha256(paths: Sequence[Path], *, root: Path = ROOT) -> str:
    if not paths:
        raise HarnessValidationError("source bundle must contain at least one file")
    rows: list[dict[str, str]] = []
    for raw_path in paths:
        path = raw_path if raw_path.is_absolute() else root / raw_path
        try:
            display = path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            display = path.resolve().as_posix()
        rows.append({"path": display, "sha256": file_sha256(path)})
    rows.sort(key=lambda row: row["path"])
    return canonical_sha256(rows)


def assert_fixed_identity(root: Path = ROOT) -> dict[str, Any]:
    identity = assert_protected_inputs(root)
    expected = {
        "map_path": CANONICAL_MAP_PATH,
        "map_raw_sha256": CANONICAL_MAP_RAW_SHA256,
        "map_semantic_sha256": CANONICAL_MAP_SEMANTIC_SHA256,
        "source_path": CANONICAL_SOURCE_PATH,
        "source_raw_sha256": CANONICAL_SOURCE_RAW_SHA256,
        "source_semantic_sha256": CANONICAL_SOURCE_SEMANTIC_SHA256,
        "source_row_count": FULL_SIZE_SEGMENTS,
        "source_bag_count": FULL_SIZE_BAGS,
    }
    for key, value in expected.items():
        if identity.get(key) != value:
            raise HarnessValidationError(
                f"protected identity {key} mismatch: {identity.get(key)!r} != {value!r}"
            )
    return identity


def load_input_prefix(
    size_segments: int,
    *,
    root: Path = ROOT,
) -> InputPrefix:
    """Load the exact first-N non-empty input rows without sorting."""

    if size_segments not in SIZE_LADDER:
        raise HarnessValidationError(
            f"prefix size must be exactly one of {SIZE_LADDER}"
        )
    assert_fixed_identity(root)
    path = root / CANONICAL_SOURCE_PATH
    selected_lines: list[bytes] = []
    rows: list[dict[str, Any]] = []
    with path.open("rb") as handle:
        for physical_line, payload in enumerate(handle, start=1):
            normalized = payload.rstrip(b"\r\n")
            if not normalized.strip():
                continue
            if len(rows) >= size_segments:
                break
            try:
                decoded = normalized.decode("utf-8")
                row = json.loads(decoded)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise HarnessValidationError(
                    f"invalid canonical input row {physical_line}: {exc}"
                ) from exc
            if not isinstance(row, dict):
                raise HarnessValidationError(
                    f"canonical input row {physical_line} is not an object"
                )
            for key in (
                "segment_id",
                "task_id",
                "original_entry_time",
                "pass_time",
                "start",
                "goal",
                "std",
            ):
                if key not in row:
                    raise HarnessValidationError(
                        f"canonical input row {physical_line} lacks {key}"
                    )
            item = dict(row)
            item["input_row_index"] = len(rows)
            item["input_physical_line"] = physical_line
            rows.append(item)
            selected_lines.append(normalized + b"\n")
    if len(rows) != size_segments:
        raise HarnessValidationError(
            f"canonical input yielded {len(rows)} rows, expected {size_segments}"
        )
    segment_ids = [str(row["segment_id"]) for row in rows]
    if len(segment_ids) != len(set(segment_ids)):
        raise HarnessValidationError("selected prefix segment IDs are not unique")
    task_ids = {int(row["task_id"]) for row in rows}
    return InputPrefix(
        size_segments=size_segments,
        rows=tuple(rows),
        prefix_sha256=hashlib.sha256(b"".join(selected_lines)).hexdigest(),
        raw_bag_count=len(task_ids),
        first_segment_id=segment_ids[0],
        last_segment_id=segment_ids[-1],
    )


def binding_bag_records(prefix: InputPrefix) -> list[tuple[Any, ...]]:
    """Create wrapper records while retaining the protected file order."""

    records: list[tuple[Any, ...]] = []
    for row in prefix.rows:
        records.append(
            (
                str(row["segment_id"]),
                int(row["task_id"]),
                float(row["pass_time"]),
                float(row["std"]),
                int(row["start"]),
                int(row["goal"]),
                str(row.get("source", f"node_{int(row['start'])}")),
            )
        )
    return records


def _resource_controls(resource_label: str) -> dict[str, Any]:
    return {"resource_semantics": RESOURCE_MODES[resource_label]}


def _scorer_controls(scorer_label: str) -> dict[str, Any]:
    return {"scorer_mode": SCORER_MODES[scorer_label]}


def _pibt_controls(pibt_label: str) -> dict[str, Any]:
    depth = int(pibt_label[1:])
    controls = {
        "pibt_mode": pibt_label,
        "pibt_max_depth": depth,
        "enable_pibt_lite": False,
    }
    if pibt_label != "P0":
        controls["local_queue_capacity"] = F_RUNTIME_LOCAL_QUEUE_CAPACITY
    return controls


def _control_controls(control_label: str) -> dict[str, Any]:
    pressure_mode, admission_mode = PRESSURE_ADMISSION_MODES[control_label]
    return {
        "pressure_mode": pressure_mode,
        "admission_mode": admission_mode,
        "enable_backpressure": pressure_mode != "off",
        "enable_source_admission": admission_mode != "off",
    }


def framework_delta_cases() -> tuple[CaseSpec, ...]:
    """Return executable B2--B6 cases; B0/B1 are parsed controls."""

    common_sizes = (144, 512, 2_048, 8_192)
    return (
        CaseSpec(
            case_id="B2_old_order_one_step",
            phase="B",
            candidate_id="B2",
            framework_label="B2",
            resource_label="R3",
            scorer_label="S1",
            pibt_label="P0",
            control_label="C0",
            sizes=common_sizes,
            runtime_controls={
                **_resource_controls("R3"),
                **_scorer_controls("S1"),
                **_pibt_controls("P0"),
                **_control_controls("C0"),
                "framework_mode": "old_scheduling_order_reservation_horizon_one",
                "local_queue_capacity": F_RUNTIME_LOCAL_QUEUE_CAPACITY,
                "reservation_depth": 1,
            },
            required_capabilities=("framework_mode", "scorer_mode", "pibt_mode"),
            notes="old ordering with one-step reservation; no full future route",
        ),
        CaseSpec(
            case_id="B3_event_java_window_frozen",
            phase="B",
            candidate_id="B3",
            framework_label="B3",
            resource_label="R3",
            scorer_label="S1",
            pibt_label="P0",
            control_label="C0",
            sizes=common_sizes,
            runtime_controls={
                **_resource_controls("R3"),
                **_scorer_controls("S1"),
                **_pibt_controls("P0"),
                **_control_controls("C0"),
                "framework_mode": "event_loop_one_step",
                "local_queue_capacity": F_RUNTIME_LOCAL_QUEUE_CAPACITY,
                "reservation_depth": 1,
            },
            required_capabilities=("scorer_mode", "pibt_mode"),
            notes="event loop plus Java/node-window-compatible resource semantics",
        ),
        CaseSpec(
            case_id="B4_event_current_corridor_frozen",
            phase="B",
            candidate_id="B4",
            framework_label="B4",
            resource_label="R0",
            scorer_label="S1",
            pibt_label="P0",
            control_label="C0",
            sizes=common_sizes,
            runtime_controls={
                **_resource_controls("R0"),
                **_scorer_controls("S1"),
                **_pibt_controls("P0"),
                **_control_controls("C0"),
                "framework_mode": "event_loop_one_step",
                "local_queue_capacity": F_RUNTIME_LOCAL_QUEUE_CAPACITY,
                "reservation_depth": 1,
            },
            required_capabilities=("scorer_mode", "pibt_mode"),
            notes="B3 control changing only resource semantics to current corridor mode",
        ),
        CaseSpec(
            case_id="B5_event_corrected_handwritten",
            phase="B",
            candidate_id="B5",
            framework_label="B5",
            resource_label="R3",
            scorer_label="S0",
            pibt_label="P0",
            control_label="C0",
            sizes=common_sizes,
            runtime_controls={
                **_resource_controls("R3"),
                **_scorer_controls("S0"),
                **_pibt_controls("P0"),
                **_control_controls("C0"),
                "framework_mode": "event_loop_one_step",
                "local_queue_capacity": F_RUNTIME_LOCAL_QUEUE_CAPACITY,
                "reservation_depth": 1,
            },
            required_capabilities=("scorer_mode", "pibt_mode"),
            notes="B3 control changing only scorer to the handwritten local rule",
        ),
        CaseSpec(
            case_id="B6_event_corrected_frozen_bounded_pibt",
            phase="B",
            candidate_id="B6",
            framework_label="B6",
            resource_label="R3",
            scorer_label="S1",
            pibt_label="P2",
            control_label="C0",
            sizes=common_sizes,
            runtime_controls={
                **_resource_controls("R3"),
                **_scorer_controls("S1"),
                **_pibt_controls("P2"),
                **_control_controls("C0"),
                "framework_mode": "event_loop_one_step",
                "local_queue_capacity": F_RUNTIME_LOCAL_QUEUE_CAPACITY,
                "reservation_depth": 1,
            },
            required_capabilities=("scorer_mode", "pibt_mode"),
            notes="corrected resource plus frozen scorer and bounded local PIBT",
        ),
    )


def resource_semantics_cases() -> tuple[CaseSpec, ...]:
    """Plan the required R0--R4 controlled runtime matrix.

    The committed ``g4irsf12_resource_semantics_ab.csv`` remains the static
    semantics audit.  These cases are written to a separate runtime-plan
    ledger so plan-only publication cannot overwrite static evidence.
    """

    return tuple(
        CaseSpec(
            case_id=f"C_{label.lower()}",
            phase="C",
            candidate_id=f"C_{label}",
            resource_label=label,
            scorer_label=PLANNING_SCORER_ANCHOR,
            pibt_label="P0",
            control_label="C0",
            sizes=(144, 512, 2_048, 8_192),
            runtime_controls={
                **_resource_controls(label),
                **_scorer_controls(PLANNING_SCORER_ANCHOR),
                **_pibt_controls("P0"),
                **_control_controls("C0"),
                "reservation_depth": 1,
            },
            required_capabilities=(
                "resource_semantics",
                "scorer_mode",
                "pibt_mode",
            ),
            notes=(
                f"R0-R4 runtime isolation for {label}; 8192 remains subject "
                "to reviewed best-two selection and explicit authorization"
            ),
        )
        for label in RESOURCE_LABELS
    )


def scorer_closed_loop_cases() -> tuple[CaseSpec, ...]:
    """Plan S0--S4 closed-loop runs without replacing offline E evidence."""

    return tuple(
        CaseSpec(
            case_id=f"E_{label.lower()}",
            phase="E",
            candidate_id=f"E_{label}",
            resource_label=PLANNING_RESOURCE_ANCHOR,
            scorer_label=label,
            pibt_label="P0",
            control_label="C0",
            sizes=(2_048, 8_192),
            runtime_controls={
                **_resource_controls(PLANNING_RESOURCE_ANCHOR),
                **_scorer_controls(label),
                **_pibt_controls("P0"),
                **_control_controls("C0"),
                "reservation_depth": 1,
            },
            required_capabilities=(
                "resource_semantics",
                "scorer_mode",
                "pibt_mode",
            ),
            notes=(
                f"S0-S4 closed-loop isolation for {label}; R3 is only the "
                "planning anchor and execution requires accepted C_R3 8192 evidence"
            ),
        )
        for label in SCORER_LABELS
    )


def pibt_depth_cases() -> tuple[CaseSpec, ...]:
    """Plan P0--P4 runtime depth ablation after C/E promotion evidence."""

    return tuple(
        CaseSpec(
            case_id=f"F_{label.lower()}",
            phase="F",
            candidate_id=f"F_{label}",
            resource_label=PLANNING_RESOURCE_ANCHOR,
            scorer_label=PLANNING_SCORER_ANCHOR,
            pibt_label=label,
            control_label="C0",
            sizes=(2_048, 8_192),
            runtime_controls={
                **_resource_controls(PLANNING_RESOURCE_ANCHOR),
                **_scorer_controls(PLANNING_SCORER_ANCHOR),
                **_pibt_controls(label),
                **_control_controls("C0"),
                "local_queue_capacity": F_RUNTIME_LOCAL_QUEUE_CAPACITY,
                "reservation_depth": 1,
            },
            required_capabilities=(
                "resource_semantics",
                "scorer_mode",
                "pibt_mode",
                "pibt_max_depth",
                "local_queue_capacity",
            ),
            notes=(
                f"P0-P4 runtime depth ablation for {label}; R3/S0 are planning "
                "anchors, local_queue_capacity=32 is sensitivity-only, and "
                "execution requires accepted E_S0 8192 evidence"
            ),
        )
        for label in PIBT_LABELS
    )


def pressure_credit_cases() -> tuple[CaseSpec, ...]:
    cases: list[CaseSpec] = []
    for label in CONTROL_LABELS:
        pibt_label = "P2" if label == "C6" else "P0"
        required: list[str] = ["scorer_mode", "pibt_mode"]
        pressure_mode, admission_mode = PRESSURE_ADMISSION_MODES[label]
        if pressure_mode in {
            "goal_conditioned_differential",
            "distance_biased_differential",
        }:
            required.append("pressure_mode")
        if admission_mode == "expiring_first_edge_credit":
            required.append("admission_mode")
        if pibt_label != "P0":
            required.append("pibt_mode")
        cases.append(
            CaseSpec(
                case_id=f"G_{label.lower()}",
                phase="G",
                candidate_id=f"G_{label}",
                resource_label="R3",
                scorer_label="S0",
                pibt_label=pibt_label,
                control_label=label,
                sizes=(2_048, 8_192),
                runtime_controls={
                    **_resource_controls("R3"),
                    **_scorer_controls("S0"),
                    **_pibt_controls(pibt_label),
                    **_control_controls(label),
                    "local_queue_capacity": F_RUNTIME_LOCAL_QUEUE_CAPACITY,
                    "reservation_depth": 1,
                },
                required_capabilities=tuple(required),
                notes=f"predeclared pressure/admission ablation {label}",
            )
        )
    return tuple(cases)


def fault_recovery_cases() -> tuple[CaseSpec, ...]:
    profiles = (
        ("stable_no_fault", "no_fault"),
        ("immediate", "single_immediate"),
        ("delayed_30s", "single_delayed_30s"),
        ("notification_drop", "sensor_loss"),
        ("fault_policy_off", "fault_policy_off"),
    )
    cases: list[CaseSpec] = []
    for name, profile in profiles:
        cases.append(
            CaseSpec(
                case_id=f"H_{name}",
                phase="H",
                candidate_id=f"H_{name}",
                resource_label="R3",
                scorer_label="S0",
                pibt_label="P2",
                control_label="C6",
                fault_profile=profile,
                sizes=(2_048, 8_192, FULL_SIZE_SEGMENTS),
                runtime_controls={
                    **_resource_controls("R3"),
                    **_scorer_controls("S0"),
                    **_pibt_controls("P2"),
                    **_control_controls("C6"),
                    "enable_fault_policy": profile != "fault_policy_off",
                    "reservation_depth": 1,
                },
                required_capabilities=(
                    "admission_mode",
                    "pibt_mode",
                    "scorer_mode",
                ),
                notes=(
                    "fault recovery on a stable real-input window before original 1x; "
                    "physical interlock is never configurable off"
                ),
            )
        )
    return tuple(cases)


def original_scale_cases() -> tuple[CaseSpec, ...]:
    finalists = (
        (
            "J_F1_best_rule_bounded_pibt",
            "J_F1",
            "S0",
            "C6",
            "F1 best rule + bounded PIBT",
            "",
        ),
        (
            "J_F2_frozen_scorer_bounded_pibt",
            "J_F2",
            "S1",
            "C0",
            "F2 frozen scorer diagnostic + bounded PIBT",
            "",
        ),
        (
            "J_F3_reserved_no_v3",
            "J_F3_RESERVED_NO_V3",
            "S4",
            "C6",
            "F3 reserved slot; no trained G4IRSF12 v3 candidate configured",
            (
                "J_F3 is reserved until a trained and gated G4IRSF12 v3 "
                "artifact replaces the S4 queue-aware rule placeholder"
            ),
        ),
    )
    cases: list[CaseSpec] = []
    for (
        case_id,
        candidate_id,
        scorer,
        control_label,
        role,
        execution_blocker,
    ) in finalists:
        required = ["pibt_mode", "admission_mode", "scorer_mode"]
        cases.append(
            CaseSpec(
                case_id=case_id,
                phase="J",
                candidate_id=candidate_id,
                resource_label="R3",
                scorer_label=scorer,
                pibt_label="P2",
                control_label=control_label,
                sizes=(FULL_SIZE_SEGMENTS,),
                runtime_controls={
                    **_resource_controls("R3"),
                    **_scorer_controls(scorer),
                    **_pibt_controls("P2"),
                    **_control_controls(control_label),
                    "reservation_depth": 1,
                },
                required_capabilities=tuple(required),
                notes=(
                    "original 1x finalist slot; S4 is a queue-aware rule and "
                    "is not a learned v3 model"
                    if execution_blocker
                    else "original 1x finalist; execution remains closed until selection"
                ),
                finalist_role=role,
                execution_blocker=execution_blocker,
            )
        )
    cases.extend(
        (
            CaseSpec(
                case_id="J_control_pibt_off",
                phase="J",
                candidate_id="J_CTRL_PIBT_OFF",
                resource_label="R3",
                scorer_label="S0",
                pibt_label="P0",
                control_label="C5",
                sizes=(FULL_SIZE_SEGMENTS,),
                runtime_controls={
                    **_resource_controls("R3"),
                    **_scorer_controls("S0"),
                    **_pibt_controls("P0"),
                    **_control_controls("C5"),
                    "local_queue_capacity": F_RUNTIME_LOCAL_QUEUE_CAPACITY,
                    "reservation_depth": 1,
                },
                required_capabilities=(
                    "admission_mode",
                    "pibt_mode",
                    "scorer_mode",
                ),
                notes="required original-1x PIBT-off negative control",
            ),
            CaseSpec(
                case_id="J_control_resource_r0",
                phase="J",
                candidate_id="J_CTRL_RESOURCE_R0",
                resource_label="R0",
                scorer_label="S0",
                pibt_label="P2",
                control_label="C6",
                sizes=(FULL_SIZE_SEGMENTS,),
                runtime_controls={
                    **_resource_controls("R0"),
                    **_scorer_controls("S0"),
                    **_pibt_controls("P2"),
                    **_control_controls("C6"),
                    "reservation_depth": 1,
                },
                required_capabilities=(
                    "admission_mode",
                    "pibt_mode",
                    "scorer_mode",
                ),
                notes="required original-1x current-resource negative control",
                execution_blocker=(
                    "J R0 control lacks a fully matched 8192 preflight case"
                ),
            ),
        )
    )
    return tuple(cases)


def all_cases() -> tuple[CaseSpec, ...]:
    cases = (
        *framework_delta_cases(),
        *resource_semantics_cases(),
        *scorer_closed_loop_cases(),
        *pibt_depth_cases(),
        *pressure_credit_cases(),
        *fault_recovery_cases(),
        *original_scale_cases(),
    )
    identities = [(case.phase, case.case_id) for case in cases]
    if len(identities) != len(set(identities)):
        raise AssertionError("G4IRSF12 harness case IDs must be unique within phase")
    return tuple(cases)


def protocol_manifest() -> dict[str, Any]:
    cases = all_cases()
    return {
        "schema": HARNESS_SCHEMA,
        "map": {
            "path": CANONICAL_MAP_PATH,
            "raw_sha256": CANONICAL_MAP_RAW_SHA256,
            "semantic_sha256": CANONICAL_MAP_SEMANTIC_SHA256,
        },
        "source": {
            "path": CANONICAL_SOURCE_PATH,
            "raw_sha256": CANONICAL_SOURCE_RAW_SHA256,
            "semantic_sha256": CANONICAL_SOURCE_SEMANTIC_SHA256,
            "segments": FULL_SIZE_SEGMENTS,
            "raw_bags": FULL_SIZE_BAGS,
        },
        "size_ladder": list(SIZE_LADDER),
        "input_order": INPUT_ORDER_ID,
        "prefix_selection": PREFIX_SELECTION_ID,
        "prefix_hash_semantics": PREFIX_HASH_SEMANTICS,
        "result_hash_semantics": RESULT_HASH_SEMANTICS,
        "summary_only_default": True,
        "g4j_status": G4J_STATUS,
        "large_run_default_maximum": 2_048,
        "frozen_numeric_runtime_controls": dict(
            FROZEN_NUMERIC_RUNTIME_CONTROLS
        ),
        "original_entry_performance_targets_minutes": {
            "frozen_v2_safe": FROZEN_V2_SAFE_ORIGINAL_ENTRY_MINUTES,
            "corrected_historical_hca": CORRECTED_HCA_ORIGINAL_ENTRY_MINUTES,
        },
        "non_comparable_processed_attempt_reference_minutes": (
            HISTORICAL_HCA_PROCESSED_ATTEMPT_MINUTES
        ),
        "cases": [case.as_dict() for case in cases],
        "claim_boundaries": {
            "historical_hca": (
                "parsed historical evidence, not a fresh Java/HCA* rerun; "
                + PROCESSED_ATTEMPT_WARNING
            ),
            "incomplete": "survivor metrics never participate in promotion",
            "full": (
                "43,603 requires reviewed 8,192 evidence, explicit finalist "
                "selection, and explicit full-run authorization; Phase J is "
                "independent of G4J, which remains CLOSED"
            ),
            "pressure": "engineering local differential pressure, not throughput-optimal",
            "pibt": "bounded local PIBT-inspired coordination, no classic completeness claim",
            "event_ceiling": (
                "max_events=20,000,000 is a declared comparable safety ceiling; "
                "event/time-limit or partial outcomes still fail"
            ),
        },
        "outputs": dict(OUTPUT_PATHS),
    }


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise HarnessValidationError(f"{label} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise HarnessValidationError(f"{label} must be numeric") from exc
    if not math.isfinite(result):
        raise HarnessValidationError(f"{label} must be finite")
    return result


def evaluate_original_entry_performance(
    mean_minutes: Any,
) -> dict[str, Any]:
    """Evaluate matched original-entry targets without relabelling 3.967."""

    result: dict[str, Any] = {
        "v2_safe_original_entry_target_minutes": (
            FROZEN_V2_SAFE_ORIGINAL_ENTRY_MINUTES
        ),
        "v2_safe_original_entry_gate": "NOT_EVALUATED",
        "corrected_hca_original_entry_target_minutes": (
            CORRECTED_HCA_ORIGINAL_ENTRY_MINUTES
        ),
        "corrected_hca_original_entry_gate": "NOT_EVALUATED",
        "matched_original_entry_performance_gate": "NOT_EVALUATED",
        "processed_attempt_reference_minutes": (
            HISTORICAL_HCA_PROCESSED_ATTEMPT_MINUTES
        ),
        "processed_attempt_reference_comparable": False,
        "processed_attempt_warning": PROCESSED_ATTEMPT_WARNING,
    }
    if mean_minutes in (None, ""):
        return result
    mean = _finite_number(mean_minutes, "original-entry mean")
    v2_pass = mean <= FROZEN_V2_SAFE_ORIGINAL_ENTRY_MINUTES
    hca_pass = mean <= CORRECTED_HCA_ORIGINAL_ENTRY_MINUTES
    result.update(
        {
            "v2_safe_original_entry_gate": "PASS" if v2_pass else "FAIL",
            "corrected_hca_original_entry_gate": (
                "PASS" if hca_pass else "FAIL"
            ),
            "matched_original_entry_performance_gate": (
                "PASS" if v2_pass and hca_pass else "FAIL"
            ),
        }
    )
    return result


def _completed(row: Mapping[str, Any]) -> bool:
    return bool(row.get("completed", row.get("complete", False)))


def aggregate_raw_bag_timings(
    input_rows: Sequence[Mapping[str, Any]],
    segment_results: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate protected segments by raw ``task_id``.

    Denominators are intentionally explicit:

    ``original_entry_time_tth_seconds``
        Sum over all segments of ``finish_time - original_entry_time``.
        ``original_entry_time`` is the protected raw-task pass time and is
        common to storage-in/storage-out rows for the same raw task.

    ``java_release_time_tth_seconds``
        Sum over all segments of ``finish_time - pass_time``.

    ``source_wait_seconds``
        Sum of ``admitted_time - pass_time``.

    ``network_time_seconds``
        Sum of ``finish_time - admitted_time``.

    ``total_system_time_seconds``
        Scheduled pre-release dwell plus source wait plus network time.  It is
        required to equal the original-entry total.

    A raw bag is complete only when every selected segment for that task was
    returned and completed.  Primary timing fields stay ``None`` otherwise.
    """

    input_by_segment: dict[str, Mapping[str, Any]] = {}
    groups: dict[int, list[Mapping[str, Any]]] = {}
    for row in input_rows:
        segment_id = str(row["segment_id"])
        if segment_id in input_by_segment:
            raise HarnessValidationError(
                f"duplicate protected segment_id: {segment_id}"
            )
        input_by_segment[segment_id] = row
        groups.setdefault(int(row["task_id"]), []).append(row)

    results_by_segment: dict[str, Mapping[str, Any]] = {}
    for row in segment_results:
        segment_id = str(row.get("segment_id", ""))
        if not segment_id:
            raise HarnessValidationError("runtime segment result lacks segment_id")
        if segment_id in results_by_segment:
            raise HarnessValidationError(
                f"duplicate runtime segment_id: {segment_id}"
            )
        if segment_id not in input_by_segment:
            raise HarnessValidationError(
                f"runtime returned segment outside selected prefix: {segment_id}"
            )
        results_by_segment[segment_id] = row

    aggregated: list[dict[str, Any]] = []
    for task_id, task_rows in groups.items():
        original_entry_observed = 0.0
        java_release_observed = 0.0
        scheduled_pre_release_observed = 0.0
        source_wait_observed = 0.0
        network_observed = 0.0
        returned = 0
        completed = 0
        for input_row in task_rows:
            segment_id = str(input_row["segment_id"])
            result = results_by_segment.get(segment_id)
            if result is None:
                continue
            returned += 1
            if not _completed(result):
                continue
            completed += 1
            finish = _finite_number(
                result.get("finish_time"), f"{segment_id}.finish_time"
            )
            admitted = _finite_number(
                result.get("admitted_time"), f"{segment_id}.admitted_time"
            )
            raw_pass = _finite_number(
                input_row.get("original_entry_time"),
                f"{segment_id}.original_entry_time",
            )
            java_release = _finite_number(
                input_row.get("pass_time"), f"{segment_id}.pass_time"
            )
            runtime_release = result.get("release_time")
            if runtime_release not in (None, "") and not math.isclose(
                _finite_number(runtime_release, f"{segment_id}.release_time"),
                java_release,
                rel_tol=0.0,
                abs_tol=1.0e-9,
            ):
                raise HarnessValidationError(
                    f"{segment_id}: runtime release differs from protected pass_time"
                )
            if java_release + 1.0e-9 < raw_pass:
                raise HarnessValidationError(
                    f"{segment_id}: Java release precedes raw original entry"
                )
            if admitted + 1.0e-9 < java_release:
                raise HarnessValidationError(
                    f"{segment_id}: admission precedes Java release"
                )
            if finish + 1.0e-9 < admitted:
                raise HarnessValidationError(
                    f"{segment_id}: finish precedes admission"
                )

            original_entry_observed += finish - raw_pass
            java_release_observed += finish - java_release
            scheduled_pre_release_observed += java_release - raw_pass
            source_wait_observed += admitted - java_release
            network_observed += finish - admitted

        expected = len(task_rows)
        complete = returned == expected and completed == expected
        reconstructed_total = (
            scheduled_pre_release_observed
            + source_wait_observed
            + network_observed
        )
        if completed and not math.isclose(
            original_entry_observed,
            reconstructed_total,
            rel_tol=0.0,
            abs_tol=1.0e-7,
        ):
            raise HarnessValidationError(
                f"task {task_id}: timing decomposition does not reconstruct original-entry"
            )
        primary = {
            "original_entry_time_tth_seconds": (
                original_entry_observed if complete else None
            ),
            "java_release_time_tth_seconds": (
                java_release_observed if complete else None
            ),
            "scheduled_pre_release_wait_seconds": (
                scheduled_pre_release_observed if complete else None
            ),
            "source_wait_seconds": source_wait_observed if complete else None,
            "network_time_seconds": network_observed if complete else None,
            "total_system_time_seconds": reconstructed_total if complete else None,
        }
        aggregated.append(
            {
                "task_id": task_id,
                "expected_segment_count": expected,
                "returned_segment_count": returned,
                "completed_segment_count": completed,
                "complete": complete,
                **primary,
                "observed_original_entry_seconds": original_entry_observed,
                "observed_java_release_seconds": java_release_observed,
                "observed_source_wait_seconds": source_wait_observed,
                "observed_network_time_seconds": network_observed,
            }
        )
    return aggregated


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise HarnessValidationError("cannot calculate a quantile of no values")
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def summarize_raw_bag_timings(
    raw_bags: Sequence[Mapping[str, Any]],
    *,
    selected_segment_count: int,
) -> dict[str, Any]:
    if not raw_bags:
        raise HarnessValidationError("raw-bag population cannot be empty")
    completed_rows = [row for row in raw_bags if bool(row["complete"])]
    completed_segments = sum(
        int(row["completed_segment_count"]) for row in raw_bags
    )
    full_completion = (
        len(completed_rows) == len(raw_bags)
        and completed_segments == selected_segment_count
    )

    def values(field: str) -> list[float]:
        return [float(row[field]) for row in completed_rows if row[field] is not None]

    original = values("original_entry_time_tth_seconds")
    java = values("java_release_time_tth_seconds")
    source_wait = values("source_wait_seconds")
    network = values("network_time_seconds")
    total = values("total_system_time_seconds")

    def primary_mean(rows: Sequence[float]) -> float | None:
        return statistics.fmean(rows) / 60.0 if full_completion else None

    return {
        "selected_segment_count": selected_segment_count,
        "selected_raw_bag_count": len(raw_bags),
        "completed_segment_count": completed_segments,
        "complete_raw_bag_count": len(completed_rows),
        "completion_rate": len(completed_rows) / len(raw_bags),
        "comparison_eligible": full_completion,
        "primary_denominator": "original_entry_time_tth",
        "denominator_scope": (
            "selected raw task_id population; every selected protected segment; "
            "primary metrics require complete selected-prefix drainage"
        ),
        "original_entry_mean_minutes": primary_mean(original),
        "original_entry_p95_seconds": (
            _quantile(original, 0.95) if full_completion else None
        ),
        "original_entry_p99_seconds": (
            _quantile(original, 0.99) if full_completion else None
        ),
        "java_release_mean_minutes": primary_mean(java),
        "source_wait_mean_minutes": primary_mean(source_wait),
        "network_time_mean_minutes": primary_mean(network),
        "total_system_time_mean_minutes": primary_mean(total),
        "survivor_original_entry_mean_minutes": (
            statistics.fmean(original) / 60.0 if original else None
        ),
        "survivor_metric_comparison_allowed": False,
    }


CAPABILITY_ALIASES: Mapping[str, tuple[str, ...]] = {
    "resource_semantics": ("resource_semantics", "resource_semantics_id"),
    "scorer_mode": ("scorer_mode", "scorer_id"),
    "pibt_mode": ("pibt_mode", "bounded_local_pibt_mode"),
    "pibt_max_depth": ("pibt_max_depth", "bounded_local_pibt_depth"),
    "pressure_mode": ("pressure_mode",),
    "admission_mode": ("admission_mode",),
    "framework_mode": ("framework_mode",),
    "reservation_depth": ("reservation_depth",),
    "local_queue_capacity": ("local_queue_capacity",),
    "max_events": ("max_events",),
    "entry_headway_seconds": ("entry_headway_seconds",),
    "pressure_weight": ("pressure_weight",),
    "pressure_age_weight": ("pressure_age_weight",),
    "pressure_distance_bias": ("pressure_distance_bias",),
    "credit_validity_seconds": ("credit_validity_seconds",),
    "credit_snapshot_max_age_seconds": (
        "credit_snapshot_max_age_seconds",
    ),
    "credit_capacity_per_edge": ("credit_capacity_per_edge",),
    "credit_lifecycle_limit": ("credit_lifecycle_limit",),
    "pibt_max_ready_bags": ("pibt_max_ready_bags",),
    "pibt_max_local_resources": ("pibt_max_local_resources",),
    "pibt_max_candidates_per_bag": ("pibt_max_candidates_per_bag",),
    "enable_expiring_credit": (
        "enable_expiring_credit",
        "enable_first_edge_credit",
    ),
}


def inspect_executor(executor: Callable[..., Mapping[str, Any]]) -> ExecutorCapabilities:
    try:
        signature = inspect.signature(executor)
    except (TypeError, ValueError) as exc:
        raise HarnessValidationError(
            f"executor signature is not introspectable: {exc}"
        ) from exc
    parameters = signature.parameters
    accepts_var_kwargs = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )
    accepts_request = (
        "request" in parameters
        and len(
            [
                parameter
                for parameter in parameters.values()
                if parameter.kind
                not in {
                    inspect.Parameter.VAR_KEYWORD,
                    inspect.Parameter.VAR_POSITIONAL,
                }
            ]
        )
        == 1
    )
    source_path = ""
    source_digest = ""
    try:
        source = inspect.getsourcefile(executor) or inspect.getfile(executor)
    except (TypeError, OSError):
        source = None
    if source:
        path = Path(source)
        if path.is_file():
            source_path = path.resolve().as_posix()
            source_digest = file_sha256(path)
    return ExecutorCapabilities(
        accepts_request_envelope=accepts_request,
        accepts_var_kwargs=accepts_var_kwargs,
        parameters=tuple(parameters),
        source_path=source_path,
        source_sha256=source_digest,
    )


def _executor_parameter(
    canonical_name: str,
    capabilities: ExecutorCapabilities,
) -> str | None:
    aliases = CAPABILITY_ALIASES.get(canonical_name, (canonical_name,))
    if capabilities.accepts_request_envelope or capabilities.accepts_var_kwargs:
        return aliases[0]
    for alias in aliases:
        if alias in capabilities.parameters:
            return alias
    return None


def bind_executor_request(
    case: CaseSpec,
    *,
    base_kwargs: Mapping[str, Any],
    capabilities: ExecutorCapabilities,
    summary_only: bool,
) -> tuple[dict[str, Any], list[str]]:
    """Bind controls without silently dropping a required capability."""

    request: dict[str, Any] = {}
    blockers: list[str] = []
    required_capabilities = set(case.required_capabilities)
    required_capabilities.add("max_events")
    required_capabilities.update(FROZEN_NUMERIC_RUNTIME_CONTROLS)
    if "local_queue_capacity" in case.runtime_controls:
        required_capabilities.add("local_queue_capacity")
    if capabilities.accepts_request_envelope:
        request.update(base_kwargs)
        request.update(case.runtime_controls)
        request["summary_only"] = summary_only
        request["trace_limit"] = 0 if summary_only else request.get("trace_limit", 20_000)
        return request, blockers

    for key, value in base_kwargs.items():
        if capabilities.accepts_var_kwargs or key in capabilities.parameters:
            request[key] = value
    for canonical_name, value in case.runtime_controls.items():
        target = _executor_parameter(canonical_name, capabilities)
        if target is not None:
            request[target] = value
        elif canonical_name in required_capabilities:
            blockers.append(f"MISSING_EXECUTOR_CAPABILITY:{canonical_name}")
    for required in sorted(required_capabilities):
        if _executor_parameter(required, capabilities) is None:
            blocker = f"MISSING_EXECUTOR_CAPABILITY:{required}"
            if blocker not in blockers:
                blockers.append(blocker)
    if capabilities.accepts_var_kwargs or "summary_only" in capabilities.parameters:
        request["summary_only"] = summary_only
    if capabilities.accepts_var_kwargs or "trace_limit" in capabilities.parameters:
        request["trace_limit"] = 0 if summary_only else request.get("trace_limit", 20_000)
    return request, blockers


def _deterministic_projection(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _deterministic_projection(child)
            for key, child in value.items()
            if str(key) not in NONDETERMINISTIC_RESULT_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_deterministic_projection(child) for child in value]
    if isinstance(value, float) and not math.isfinite(value):
        return "INF" if value > 0 else ("-INF" if value < 0 else "NAN")
    return value


def deterministic_result_sha256(payload: Mapping[str, Any]) -> str:
    return canonical_sha256(_deterministic_projection(payload))


def _summary_only_errors(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in TRACE_KEYS:
        if key in payload and payload[key] not in (None, [], {}, ""):
            errors.append(f"SUMMARY_ONLY_PAYLOAD_CONTAINS:{key}")
    summary = payload.get("summary")
    if isinstance(summary, Mapping):
        trace_count = summary.get(
            "decision_trace_stored_count",
            summary.get("trace_stored_count", 0),
        )
        if trace_count not in (None, "", 0, 0.0):
            errors.append("SUMMARY_ONLY_REPORTED_NONZERO_TRACE_COUNT")
    return errors


RESULT_COLUMNS = (
    "schema",
    "phase",
    "case_id",
    "candidate_id",
    "framework_label",
    "resource_label",
    "scorer_label",
    "pibt_label",
    "control_label",
    "resource_semantics_echo",
    "scorer_mode_echo",
    "pibt_mode_echo",
    "pressure_mode_echo",
    "admission_mode_echo",
    "framework_mode_echo",
    "pibt_max_depth_echo",
    "max_events_echo",
    "entry_headway_seconds_echo",
    "pressure_weight_echo",
    "pressure_age_weight_echo",
    "pressure_distance_bias_echo",
    "credit_validity_seconds_echo",
    "credit_snapshot_max_age_seconds_echo",
    "credit_capacity_per_edge_echo",
    "credit_lifecycle_limit_echo",
    "pibt_max_ready_bags_echo",
    "pibt_max_local_resources_echo",
    "pibt_max_candidates_per_bag_echo",
    "fault_profile",
    "size_segments",
    "repeat_index",
    "execution_status",
    "gate_status",
    "evidence_status",
    "termination_reason",
    "early_abort_status",
    "blocker",
    "summary_only",
    "input_order",
    "prefix_selection",
    "map_raw_sha256",
    "map_semantic_sha256",
    "source_raw_sha256",
    "source_semantic_sha256",
    "input_prefix_sha256",
    "case_config_sha256",
    "source_bundle_sha256",
    "binary_sha256",
    "executor_source_sha256",
    "deterministic_result_sha256",
    "repeat_consistency",
    "primary_denominator",
    "reported_mean_minutes",
    "denominator_scope",
    "selected_segment_count",
    "selected_raw_bag_count",
    "completed_segment_count",
    "complete_raw_bag_count",
    "failed_segment_count",
    "completion_rate",
    "comparison_eligible",
    "original_entry_mean_minutes",
    "original_entry_p95_seconds",
    "original_entry_p99_seconds",
    "java_release_mean_minutes",
    "source_wait_mean_minutes",
    "network_time_mean_minutes",
    "total_system_time_mean_minutes",
    "survivor_original_entry_mean_minutes",
    "v2_safe_original_entry_target_minutes",
    "v2_safe_original_entry_gate",
    "corrected_hca_original_entry_target_minutes",
    "corrected_hca_original_entry_gate",
    "matched_original_entry_performance_gate",
    "processed_attempt_reference_minutes",
    "processed_attempt_reference_comparable",
    "processed_attempt_warning",
    "conflict_count",
    "unsafe_entry_count",
    "runtime_full_astar_calls",
    "global_reservation_scan_count",
    "future_routes_stored",
    "unresolved_deadlock_count",
    "event_limit_reached",
    "time_limit_reached",
    "reservation_depth",
    "local_queue_capacity",
    "declared_max_events",
    "max_edges_selected_per_arrive",
    "event_count",
    "wall_seconds",
    "peak_working_set_bytes",
    "fault_affected_bag_count",
    "fault_affected_completed_count",
    "fault_local_hold_count",
    "fault_reroute_count",
    "fault_recovery_seconds_available",
    "fault_recovery_seconds",
    "repair_backlog_slope_available",
    "repair_backlog_slope",
    "unrecovered_window_seconds",
    "fault_p95_delta_seconds",
    "fault_p99_delta_seconds",
    "credit_issued_count",
    "credit_consumed_count",
    "credit_expired_count",
    "credit_fault_revocation_count",
    "credit_generation_revocation_count",
    "credit_local_hold_count",
    "pibt_applicability_count",
    "pibt_attempt_count",
    "pibt_prepare_count",
    "pibt_validate_count",
    "pibt_commit_count",
    "pibt_rollback_count",
    "pibt_backtrack_count",
    "pibt_wait_for_cycle_count",
    "pibt_handoff_count",
    "route_change_count",
    "route_oscillation_count",
    "notes",
)


def _metric(
    payload: Mapping[str, Any],
    summary: Mapping[str, Any],
    *names: str,
    default: Any = "",
) -> Any:
    for name in names:
        if name in summary:
            return summary[name]
        if name in payload:
            return payload[name]
    for nested_name in ("fault_metrics", "capacity_metrics", "metrics"):
        nested = payload.get(nested_name)
        if isinstance(nested, Mapping):
            for name in names:
                if name in nested:
                    return nested[name]
    return default


def _has_metric(
    payload: Mapping[str, Any],
    summary: Mapping[str, Any],
    *names: str,
) -> bool:
    if any(
        (
            name in summary
            and summary[name] not in (None, "")
        )
        or (
            name in payload
            and payload[name] not in (None, "")
        )
        for name in names
    ):
        return True
    return any(
        isinstance(payload.get(nested_name), Mapping)
        and any(
            name in payload[nested_name]
            and payload[nested_name][name] not in (None, "")
            for name in names
        )
        for nested_name in ("fault_metrics", "capacity_metrics", "metrics")
    )


def _int_metric(
    payload: Mapping[str, Any],
    summary: Mapping[str, Any],
    *names: str,
    default: int = 0,
) -> int:
    value = _metric(payload, summary, *names, default=default)
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise HarnessValidationError(
            f"metric {names[0]} must be an integer, got {value!r}"
        ) from exc


def _bool_metric(
    payload: Mapping[str, Any],
    summary: Mapping[str, Any],
    *names: str,
    default: bool = False,
) -> bool:
    value = _metric(payload, summary, *names, default=default)
    if isinstance(value, bool):
        return value
    if value in (0, 0.0, "0", "false", "False", "", None):
        return False
    if value in (1, 1.0, "1", "true", "True"):
        return True
    raise HarnessValidationError(
        f"metric {names[0]} must be boolean, got {value!r}"
    )


def _float_or_blank(value: Any) -> float | str:
    if value in (None, ""):
        return ""
    return _finite_number(value, "result metric")


def _finite_float_or_blank(value: Any) -> float | str:
    """Serialize invalid optional metrics as blank after their gate has failed."""

    try:
        return _float_or_blank(value)
    except HarnessValidationError:
        return ""


def _planned_blocker(case: CaseSpec, size: int) -> str:
    if case.execution_blocker:
        return case.execution_blocker
    if size == FULL_SIZE_SEGMENTS:
        if case.phase == "J":
            return (
                "requires reviewed 8192 evidence, explicit finalist selection, "
                "and explicit full-run authorization; G4J remains independently CLOSED"
            )
        return "requires accepted 8192 evidence and explicit full-run authorization"
    if size == 8_192:
        return "requires accepted prior tier and explicit 8192 authorization"
    if case.phase == "H" and size == 2_048:
        return "requires a stable no-fault real-input candidate before fault injection"
    return "awaiting execution in frozen prefix order"


def planned_result(case: CaseSpec, size: int) -> dict[str, Any]:
    config = case.as_dict()
    row = {
        **{column: "" for column in RESULT_COLUMNS},
        "schema": RESULT_SCHEMA,
        "phase": case.phase,
        "case_id": case.case_id,
        "candidate_id": case.candidate_id,
        "framework_label": case.framework_label,
        "resource_label": case.resource_label,
        "scorer_label": case.scorer_label,
        "pibt_label": case.pibt_label,
        "control_label": case.control_label,
        "fault_profile": case.fault_profile,
        "size_segments": size,
        "execution_status": "NOT_RUN",
        "gate_status": "PENDING",
        "evidence_status": "PLANNED_NOT_EXECUTED",
        "termination_reason": "NOT_RUN",
        "early_abort_status": "",
        "blocker": _planned_blocker(case, size),
        "summary_only": True,
        "input_order": INPUT_ORDER_ID,
        "prefix_selection": PREFIX_SELECTION_ID,
        "map_raw_sha256": CANONICAL_MAP_RAW_SHA256,
        "map_semantic_sha256": CANONICAL_MAP_SEMANTIC_SHA256,
        "source_raw_sha256": CANONICAL_SOURCE_RAW_SHA256,
        "source_semantic_sha256": CANONICAL_SOURCE_SEMANTIC_SHA256,
        "case_config_sha256": canonical_sha256(config),
        "primary_denominator": "original_entry_time_tth",
        "selected_segment_count": size,
        "comparison_eligible": False,
        "local_queue_capacity": case.runtime_controls.get(
            "local_queue_capacity",
            0,
        ),
        "declared_max_events": case.runtime_controls["max_events"],
        "repeat_consistency": "NOT_EVALUATED",
        "notes": case.notes,
    }
    if case.phase == "J":
        row.update(evaluate_original_entry_performance(None))
        row["v2_safe_original_entry_gate"] = "PENDING"
        row["corrected_hca_original_entry_gate"] = "PENDING"
        row["matched_original_entry_performance_gate"] = "PENDING"
    return row


def planned_results(cases: Sequence[CaseSpec] | None = None) -> list[dict[str, Any]]:
    return [
        planned_result(case, size)
        for case in (tuple(cases) if cases is not None else all_cases())
        for size in case.sizes
    ]


def _fault_records(case: CaseSpec, prefix: InputPrefix) -> list[tuple[Any, ...]]:
    releases = [float(row["pass_time"]) for row in prefix.rows]
    rows = fault_windows(
        case.fault_profile,
        minimum_release=min(releases),
        maximum_release=max(releases),
    )
    return [
        (
            int(row["start"]),
            int(row["end"]),
            float(row["fault_time"]),
            float(row["repair_time"]),
            float(row.get("message_delay", 0.0)),
            bool(row.get("drop_notification", False)),
        )
        for row in rows
    ]


def _base_result_identity(
    case: CaseSpec,
    prefix: InputPrefix,
    *,
    binary_sha256: str,
    bundle_sha256: str,
    capabilities: ExecutorCapabilities,
    summary_only: bool,
) -> dict[str, Any]:
    return {
        **planned_result(case, prefix.size_segments),
        "input_prefix_sha256": prefix.prefix_sha256,
        "selected_raw_bag_count": prefix.raw_bag_count,
        "source_bundle_sha256": bundle_sha256,
        "binary_sha256": binary_sha256,
        "executor_source_sha256": capabilities.source_sha256,
        "summary_only": summary_only,
    }


def _safety_blockers(
    *,
    case: CaseSpec,
    size: int,
    payload: Mapping[str, Any],
    summary: Mapping[str, Any],
    timing: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    required_zero_aliases = {
        "conflict_count": (
            "conflict_count",
            "conflicts",
            "reservation_conflicts",
        ),
        "unsafe_entry_count": (
            "unsafe_entry_count",
            "physical_fault_edge_entry_violation_count",
        ),
        "runtime_full_astar_calls": ("runtime_full_astar_calls",),
        "global_reservation_scan_count": (
            "global_reservation_scan_count",
            "first_edge_credit_global_scan_count",
        ),
        "future_routes_stored": (
            "future_routes_stored",
            "full_future_routes_stored",
            "first_edge_credit_future_route_count",
        ),
        "unresolved_deadlock_count": ("unresolved_deadlock_count",),
    }
    for name, aliases in required_zero_aliases.items():
        if not _has_metric(payload, summary, *aliases):
            blockers.append(f"missing required safety metric: {name}")
            continue
        value = _int_metric(payload, summary, *aliases)
        if value != 0:
            blockers.append(f"{name}={value}, expected 0")
    for limit_name in ("event_limit_reached", "time_limit_reached"):
        if not _has_metric(payload, summary, limit_name):
            blockers.append(f"missing required safety metric: {limit_name}")
        elif _bool_metric(payload, summary, limit_name):
            blockers.append(f"{limit_name}=true")
    if not _has_metric(payload, summary, "event_count"):
        blockers.append("missing required safety metric: event_count")
    else:
        event_count = _int_metric(payload, summary, "event_count")
        actual_max_events = _int_metric(
            payload,
            summary,
            "declared_max_events",
            "max_events",
            default=0,
        )
        if event_count < 0:
            blockers.append(f"event_count={event_count}, expected >=0")
        if actual_max_events <= 0:
            blockers.append("missing or invalid runtime max_events echo")
        elif event_count > actual_max_events:
            blockers.append(
                f"event_count={event_count} exceeds max_events={actual_max_events}"
            )
    if not _has_metric(payload, summary, "reservation_depth"):
        blockers.append("missing required safety metric: reservation_depth")
    reservation_depth = _int_metric(
        payload, summary, "reservation_depth", default=1
    )
    if reservation_depth != 1:
        blockers.append(f"reservation_depth={reservation_depth}, expected 1")
    if not _has_metric(payload, summary, "max_edges_selected_per_arrive"):
        blockers.append(
            "missing required safety metric: max_edges_selected_per_arrive"
        )
    max_edges = _int_metric(
        payload, summary, "max_edges_selected_per_arrive", default=1
    )
    if max_edges > 1:
        blockers.append(
            f"max_edges_selected_per_arrive={max_edges}, expected <=1"
        )
    if not bool(timing["comparison_eligible"]):
        blockers.append("selected prefix did not complete; survivor metrics excluded")
    if case.phase == "F" and case.pibt_label != "P0":
        for name, aliases in {
            "pibt_applicability_count": (
                "pibt_applicability_count",
                "bounded_local_pibt_applicability_count",
            ),
            "pibt_attempt_count": (
                "pibt_attempt_count",
                "bounded_local_pibt_attempt_count",
            ),
            "pibt_prepare_count": (
                "pibt_prepare_count",
                "bounded_local_pibt_prepare_count",
            ),
            "pibt_validate_count": (
                "pibt_validate_count",
                "bounded_local_pibt_validate_count",
            ),
            "pibt_commit_count": (
                "pibt_commit_count",
                "bounded_local_pibt_commit_count",
            ),
            "pibt_rollback_count": (
                "pibt_rollback_count",
                "bounded_local_pibt_rollback_count",
            ),
            "pibt_backtrack_count": (
                "pibt_backtrack_count",
                "bounded_local_pibt_backtrack_count",
            ),
            "pibt_wait_for_cycle_count": (
                "pibt_wait_for_cycle_count",
                "bounded_local_pibt_wait_for_cycle_count",
            ),
            "pibt_handoff_count": (
                "pibt_handoff_count",
                "bounded_local_pibt_handoff_count",
            ),
        }.items():
            if not _has_metric(payload, summary, *aliases):
                blockers.append(f"missing required F runtime audit metric: {name}")
            elif _int_metric(payload, summary, *aliases) < 0:
                blockers.append(f"{name} must be >=0")
    if case.phase == "J":
        if size != FULL_SIZE_SEGMENTS:
            blockers.append("J comparison must use exactly 43,603 segments")
        if int(timing["selected_raw_bag_count"]) != FULL_SIZE_BAGS:
            blockers.append(
                f"J raw bag count={timing['selected_raw_bag_count']}, expected {FULL_SIZE_BAGS}"
            )
        if int(timing["complete_raw_bag_count"]) != FULL_SIZE_BAGS:
            blockers.append(
                f"J completed raw bags={timing['complete_raw_bag_count']}, "
                f"expected {FULL_SIZE_BAGS}"
            )
        performance = evaluate_original_entry_performance(
            timing.get("original_entry_mean_minutes")
        )
        if performance["v2_safe_original_entry_gate"] != "PASS":
            blockers.append(
                "original_entry_mean_minutes does not meet matched frozen "
                f"v2-safe target <= {FROZEN_V2_SAFE_ORIGINAL_ENTRY_MINUTES}"
            )
        if performance["corrected_hca_original_entry_gate"] != "PASS":
            blockers.append(
                "original_entry_mean_minutes does not meet corrected historical "
                f"HCA original-entry target <= {CORRECTED_HCA_ORIGINAL_ENTRY_MINUTES}"
            )
    if case.phase == "H" and case.fault_profile != "no_fault":
        affected = _int_metric(payload, summary, "fault_affected_bag_count")
        affected_completed = _int_metric(
            payload, summary, "fault_affected_completed_count"
        )
        if affected <= 0:
            blockers.append("fault exposure not observed")
        elif affected_completed != affected:
            blockers.append(
                f"fault affected completion={affected_completed}/{affected}"
            )
        recovery_available_names = (
            "fault_recovery_seconds_available",
            "fault_recovery_time_seconds_available",
        )
        recovery_available = (
            _has_metric(payload, summary, *recovery_available_names)
            and _bool_metric(payload, summary, *recovery_available_names)
        )
        if not recovery_available:
            blockers.append("fault recovery availability is missing or false")
        recovery = _metric(
            payload,
            summary,
            "fault_recovery_seconds",
            "fault_recovery_time_seconds_max",
            default=None,
        )
        if recovery in (None, ""):
            blockers.append("fault recovery window was not measured")
        else:
            try:
                recovery_value = _finite_number(
                    recovery,
                    "fault recovery seconds",
                )
            except HarnessValidationError:
                blockers.append("fault recovery seconds must be finite")
            else:
                if recovery_value < 0.0:
                    blockers.append("fault recovery seconds must be >=0")
        slope_available_names = ("repair_backlog_slope_available",)
        slope_available = (
            _has_metric(payload, summary, *slope_available_names)
            and _bool_metric(payload, summary, *slope_available_names)
        )
        if not slope_available:
            blockers.append("repair backlog slope availability is missing or false")
        slope = _metric(
            payload, summary, "repair_backlog_slope", default=None
        )
        if slope in (None, ""):
            blockers.append("post-repair backlog slope is missing")
        else:
            try:
                slope_value = _finite_number(
                    slope,
                    "repair backlog slope",
                )
            except HarnessValidationError:
                blockers.append("repair backlog slope must be finite")
            else:
                if slope_value > 0.0:
                    blockers.append("post-repair backlog slope is positive")
    return blockers


def _not_applicable_reasons(
    *,
    case: CaseSpec,
    payload: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> list[str]:
    """Return executed configurations that cannot count as an A/B result."""

    reasons: list[str] = []
    if case.pibt_label != "P0":
        capacity = _int_metric(
            payload,
            summary,
            "local_queue_capacity",
            default=0,
        )
        if capacity <= 0:
            reasons.append(
                f"{case.pibt_label} with unlimited local_queue_capacity is "
                "NOT_APPLICABLE to bounded-local PIBT evidence"
            )
    if case.phase == "F" and case.pibt_label != "P0":
        audit_aliases = {
            "applicability": (
                "pibt_applicability_count",
                "bounded_local_pibt_applicability_count",
            ),
            "attempt": (
                "pibt_attempt_count",
                "bounded_local_pibt_attempt_count",
            ),
            "prepare": (
                "pibt_prepare_count",
                "bounded_local_pibt_prepare_count",
            ),
            "validate": (
                "pibt_validate_count",
                "bounded_local_pibt_validate_count",
            ),
        }
        if all(
            _has_metric(payload, summary, *aliases)
            for aliases in audit_aliases.values()
        ):
            inactive = [
                name
                for name, aliases in audit_aliases.items()
                if _int_metric(payload, summary, *aliases) == 0
            ]
            if inactive:
                reasons.append(
                    f"{case.pibt_label} did not exercise positive "
                    f"{'/'.join(inactive)} audit counts; configuration is "
                    "NOT_APPLICABLE to the bounded-local PIBT depth comparison"
                )
    return reasons


def _control_echo_blockers(
    case: CaseSpec,
    summary: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    echo_aliases = {
        "resource_semantics": (
            "resource_semantics_echo",
            "resource_semantics_id",
            "resource_semantics",
        ),
        "scorer_mode": ("scorer_mode_echo", "scorer_mode", "scorer_id"),
        "pibt_mode": (
            "pibt_mode_echo",
            "pibt_mode",
            "bounded_local_pibt_mode",
        ),
        "pressure_mode": ("pressure_mode_echo", "pressure_mode"),
        "admission_mode": ("admission_mode_echo", "admission_mode"),
        "framework_mode": ("framework_mode_echo", "framework_mode"),
        "pibt_max_depth": (
            "pibt_max_depth_echo",
            "pibt_max_depth",
            "bounded_local_pibt_depth",
        ),
        "reservation_depth": ("reservation_depth",),
        "local_queue_capacity": ("local_queue_capacity",),
        "max_events": (
            "max_events_echo",
            "declared_max_events",
            "max_events",
        ),
        "entry_headway_seconds": (
            "entry_headway_seconds_echo",
            "entry_headway_seconds",
        ),
        "pressure_weight": ("pressure_weight_echo", "pressure_weight"),
        "pressure_age_weight": (
            "pressure_age_weight_echo",
            "pressure_age_weight",
        ),
        "pressure_distance_bias": (
            "pressure_distance_bias_echo",
            "pressure_distance_bias",
        ),
        "credit_validity_seconds": (
            "credit_validity_seconds_echo",
            "credit_validity_seconds",
        ),
        "credit_snapshot_max_age_seconds": (
            "credit_snapshot_max_age_seconds_echo",
            "credit_snapshot_max_age_seconds",
        ),
        "credit_capacity_per_edge": (
            "credit_capacity_per_edge_echo",
            "credit_capacity_per_edge",
        ),
        "credit_lifecycle_limit": (
            "credit_lifecycle_limit_echo",
            "credit_lifecycle_limit",
        ),
        "pibt_max_ready_bags": (
            "pibt_max_ready_bags_echo",
            "pibt_max_ready_bags",
        ),
        "pibt_max_local_resources": (
            "pibt_max_local_resources_echo",
            "pibt_max_local_resources",
        ),
        "pibt_max_candidates_per_bag": (
            "pibt_max_candidates_per_bag_echo",
            "pibt_max_candidates_per_bag",
        ),
    }
    required_echoes = {
        "resource_semantics",
        "scorer_mode",
        "pibt_mode",
        "pressure_mode",
        "admission_mode",
    }
    required_echoes.update(
        name
        for name in case.runtime_controls
        if name in echo_aliases
    )
    required_echoes.update(
        name
        for name in case.required_capabilities
        if name in echo_aliases
    )
    for canonical_name in sorted(required_echoes):
        if canonical_name not in case.runtime_controls:
            continue
        aliases = echo_aliases[canonical_name]
        found_name = next(
            (
                name
                for name in aliases
                if name in summary and summary[name] not in (None, "")
            ),
            None,
        )
        if found_name is None:
            blockers.append(f"MISSING_RUNTIME_CONTROL_ECHO:{canonical_name}")
            continue
        actual = summary[found_name]
        expected = case.runtime_controls[canonical_name]
        if str(actual) != str(expected):
            blockers.append(
                f"RUNTIME_CONTROL_ECHO_MISMATCH:{canonical_name}="
                f"{actual!r}, expected {expected!r}"
            )
    return blockers


def execute_case(
    case: CaseSpec,
    size_segments: int,
    *,
    executor: Callable[..., Mapping[str, Any]],
    executor_binary: Path,
    source_paths: Sequence[Path],
    base_runtime_kwargs: Mapping[str, Any] | None = None,
    root: Path = ROOT,
    summary_only: bool = True,
) -> dict[str, Any]:
    """Execute one already-authorized tier and return one compact result row."""

    if size_segments not in case.sizes:
        raise HarnessValidationError(
            f"{case.case_id} does not declare size {size_segments}"
        )
    prefix = load_input_prefix(size_segments, root=root)
    binary_digest = file_sha256(executor_binary)
    bundle_digest = source_bundle_sha256(source_paths, root=root)
    capabilities = inspect_executor(executor)
    row = _base_result_identity(
        case,
        prefix,
        binary_sha256=binary_digest,
        bundle_sha256=bundle_digest,
        capabilities=capabilities,
        summary_only=summary_only,
    )

    base: dict[str, Any] = dict(base_runtime_kwargs or {})
    base.update(
        {
            "bag_records": binding_bag_records(prefix),
            "input_rows": [dict(item) for item in prefix.rows],
            "fault_windows": _fault_records(case, prefix),
            "scenario": f"g4irsf12_{case.case_id}_{size_segments}",
            "scale": 1.0,
            "input_prefix_sha256": prefix.prefix_sha256,
            "case_config_sha256": row["case_config_sha256"],
        }
    )
    request, capability_blockers = bind_executor_request(
        case,
        base_kwargs=base,
        capabilities=capabilities,
        summary_only=summary_only,
    )
    if capability_blockers:
        row.update(
            {
                "execution_status": "NOT_RUN",
                "gate_status": "PENDING",
                "evidence_status": "EXECUTOR_CAPABILITY_BLOCKED",
                "termination_reason": "NOT_RUN",
                "blocker": " | ".join(capability_blockers),
            }
        )
        return row

    try:
        payload_raw = (
            executor(request=request)
            if capabilities.accepts_request_envelope
            else executor(**request)
        )
    except Exception as exc:  # noqa: BLE001 - failure is retained as evidence
        row.update(
            {
                "execution_status": "FAILED",
                "gate_status": "FAIL",
                "evidence_status": "EXECUTOR_FAILURE_RETAINED",
                "termination_reason": "WORKER_FAILURE",
                "blocker": f"{type(exc).__name__}: {exc}",
            }
        )
        return row
    if not isinstance(payload_raw, Mapping):
        raise HarnessValidationError("executor payload must be an object")
    payload = dict(payload_raw)
    summary = payload.get("summary")
    if not isinstance(summary, Mapping):
        raise HarnessValidationError("executor payload.summary must be an object")
    bags = payload.get("bags", payload.get("segment_results"))
    if not isinstance(bags, list) or not all(
        isinstance(item, Mapping) for item in bags
    ):
        raise HarnessValidationError(
            "executor payload must contain a bags/segment_results array"
        )

    summary_errors = _summary_only_errors(payload) if summary_only else []
    raw_bags = aggregate_raw_bag_timings(prefix.rows, bags)
    timing = summarize_raw_bag_timings(
        raw_bags,
        selected_segment_count=size_segments,
    )
    performance_fields = (
        evaluate_original_entry_performance(
            timing.get("original_entry_mean_minutes")
        )
        if case.phase == "J"
        else {}
    )
    result_digest = deterministic_result_sha256(payload)
    termination_reason = str(
        summary.get(
            "termination_reason",
            (
                "EVENT_LIMIT"
                if _bool_metric(payload, summary, "event_limit_reached")
                else (
                    "SIMULATION_TIME_LIMIT"
                    if _bool_metric(payload, summary, "time_limit_reached")
                    else ("DRAINED" if timing["comparison_eligible"] else "PARTIAL")
                )
            ),
        )
    )
    early_abort = (
        termination_reason == EARLY_ABORT_STATUS
        or str(summary.get("early_abort_status", "")) == EARLY_ABORT_STATUS
    )
    safety_blockers = _safety_blockers(
        case=case,
        size=size_segments,
        payload=payload,
        summary=summary,
        timing=timing,
    )
    not_applicable = _not_applicable_reasons(
        case=case,
        payload=payload,
        summary=summary,
    )
    blockers = [
        *summary_errors,
        *_control_echo_blockers(case, summary),
        *safety_blockers,
        *not_applicable,
    ]
    if early_abort:
        blockers.append(EARLY_ABORT_STATUS)

    execution_status = (
        EARLY_ABORT_STATUS
        if early_abort
        else ("EXECUTED" if timing["comparison_eligible"] else "PARTIAL")
    )
    if execution_status != "EXECUTED":
        gate_status = "FAIL"
    elif not_applicable:
        gate_status = "NOT_APPLICABLE"
    else:
        gate_status = "PASS" if not blockers else "FAIL"
    completed_segments = int(timing["completed_segment_count"])
    row.update(
        {
            "execution_status": execution_status,
            "gate_status": gate_status,
            "evidence_status": (
                "EXECUTED_RESULT_VALIDATED"
                if gate_status == "PASS"
                else (
                    "EXECUTED_CONFIGURATION_NOT_APPLICABLE"
                    if gate_status == "NOT_APPLICABLE"
                    else "NEGATIVE_OR_PARTIAL_RESULT_RETAINED"
                )
            ),
            "termination_reason": termination_reason,
            "early_abort_status": EARLY_ABORT_STATUS if early_abort else "",
            "blocker": " | ".join(blockers),
            "resource_semantics_echo": _metric(
                payload,
                summary,
                "resource_semantics_id",
                "resource_semantics",
            ),
            "scorer_mode_echo": _metric(
                payload,
                summary,
                "scorer_mode",
                "scorer_id",
            ),
            "pibt_mode_echo": _metric(
                payload,
                summary,
                "pibt_mode",
                "bounded_local_pibt_mode",
            ),
            "pressure_mode_echo": _metric(
                payload,
                summary,
                "pressure_mode",
            ),
            "admission_mode_echo": _metric(
                payload,
                summary,
                "admission_mode",
            ),
            "framework_mode_echo": _metric(
                payload,
                summary,
                "framework_mode",
            ),
            "pibt_max_depth_echo": _metric(
                payload,
                summary,
                "pibt_max_depth",
                "bounded_local_pibt_depth",
            ),
            "max_events_echo": _metric(
                payload,
                summary,
                "declared_max_events",
                "max_events",
            ),
            "entry_headway_seconds_echo": _metric(
                payload,
                summary,
                "entry_headway_seconds",
            ),
            "pressure_weight_echo": _metric(
                payload,
                summary,
                "pressure_weight",
            ),
            "pressure_age_weight_echo": _metric(
                payload,
                summary,
                "pressure_age_weight",
            ),
            "pressure_distance_bias_echo": _metric(
                payload,
                summary,
                "pressure_distance_bias",
            ),
            "credit_validity_seconds_echo": _metric(
                payload,
                summary,
                "credit_validity_seconds",
            ),
            "credit_snapshot_max_age_seconds_echo": _metric(
                payload,
                summary,
                "credit_snapshot_max_age_seconds",
            ),
            "credit_capacity_per_edge_echo": _metric(
                payload,
                summary,
                "credit_capacity_per_edge",
            ),
            "credit_lifecycle_limit_echo": _metric(
                payload,
                summary,
                "credit_lifecycle_limit",
            ),
            "pibt_max_ready_bags_echo": _metric(
                payload,
                summary,
                "pibt_max_ready_bags",
            ),
            "pibt_max_local_resources_echo": _metric(
                payload,
                summary,
                "pibt_max_local_resources",
            ),
            "pibt_max_candidates_per_bag_echo": _metric(
                payload,
                summary,
                "pibt_max_candidates_per_bag",
            ),
            "deterministic_result_sha256": result_digest,
            "repeat_consistency": "SINGLE_RESULT",
            **timing,
            **performance_fields,
            "failed_segment_count": size_segments - completed_segments,
            "conflict_count": _int_metric(
                payload,
                summary,
                "conflict_count",
                "conflicts",
                "reservation_conflicts",
            ),
            "unsafe_entry_count": _int_metric(
                payload,
                summary,
                "unsafe_entry_count",
                "physical_fault_edge_entry_violation_count",
            ),
            "runtime_full_astar_calls": _int_metric(
                payload, summary, "runtime_full_astar_calls"
            ),
            "global_reservation_scan_count": _int_metric(
                payload,
                summary,
                "global_reservation_scan_count",
                "first_edge_credit_global_scan_count",
            ),
            "future_routes_stored": _int_metric(
                payload,
                summary,
                "future_routes_stored",
                "full_future_routes_stored",
                "first_edge_credit_future_route_count",
            ),
            "unresolved_deadlock_count": _int_metric(
                payload, summary, "unresolved_deadlock_count"
            ),
            "event_limit_reached": _bool_metric(
                payload, summary, "event_limit_reached"
            ),
            "time_limit_reached": _bool_metric(
                payload, summary, "time_limit_reached"
            ),
            "reservation_depth": _int_metric(
                payload, summary, "reservation_depth", default=1
            ),
            "local_queue_capacity": _int_metric(
                payload,
                summary,
                "local_queue_capacity",
                default=int(case.runtime_controls.get("local_queue_capacity", 0)),
            ),
            "max_edges_selected_per_arrive": _int_metric(
                payload,
                summary,
                "max_edges_selected_per_arrive",
                default=1,
            ),
            "event_count": _int_metric(payload, summary, "event_count"),
            "wall_seconds": _float_or_blank(
                _metric(payload, summary, "wall_seconds", "runtime_seconds")
            ),
            "peak_working_set_bytes": _metric(
                payload, summary, "peak_working_set_bytes", default=""
            ),
            "fault_affected_bag_count": _int_metric(
                payload, summary, "fault_affected_bag_count"
            ),
            "fault_affected_completed_count": _int_metric(
                payload, summary, "fault_affected_completed_count"
            ),
            "fault_local_hold_count": _int_metric(
                payload,
                summary,
                "fault_local_hold_count",
                "local_fault_policy_hold_count",
            ),
            "fault_reroute_count": _int_metric(
                payload,
                summary,
                "fault_reroute_count",
                "local_fault_policy_reroute_count",
            ),
            "fault_recovery_seconds_available": _bool_metric(
                payload,
                summary,
                "fault_recovery_seconds_available",
                "fault_recovery_time_seconds_available",
            ),
            "fault_recovery_seconds": _finite_float_or_blank(
                _metric(
                    payload,
                    summary,
                    "fault_recovery_seconds",
                    "fault_recovery_time_seconds_max",
                )
            ),
            "repair_backlog_slope_available": _bool_metric(
                payload,
                summary,
                "repair_backlog_slope_available",
            ),
            "repair_backlog_slope": _finite_float_or_blank(
                _metric(payload, summary, "repair_backlog_slope")
            ),
            "unrecovered_window_seconds": _float_or_blank(
                _metric(payload, summary, "unrecovered_window_seconds")
            ),
            "fault_p95_delta_seconds": _float_or_blank(
                _metric(payload, summary, "fault_p95_delta_seconds")
            ),
            "fault_p99_delta_seconds": _float_or_blank(
                _metric(payload, summary, "fault_p99_delta_seconds")
            ),
            "credit_issued_count": _int_metric(
                payload,
                summary,
                "credit_issued_count",
                "first_edge_credit_issued_count",
            ),
            "credit_consumed_count": _int_metric(
                payload,
                summary,
                "credit_consumed_count",
                "first_edge_credit_consumed_count",
            ),
            "credit_expired_count": _int_metric(
                payload,
                summary,
                "credit_expired_count",
                "first_edge_credit_expired_count",
            ),
            "credit_fault_revocation_count": _int_metric(
                payload,
                summary,
                "credit_fault_revocation_count",
                "first_edge_credit_fault_revocation_count",
            ),
            "credit_generation_revocation_count": _int_metric(
                payload,
                summary,
                "credit_generation_revocation_count",
                "first_edge_credit_generation_revocation_count",
            ),
            "credit_local_hold_count": _int_metric(
                payload,
                summary,
                "credit_local_hold_count",
                "first_edge_credit_local_hold_count",
            ),
            "pibt_applicability_count": _int_metric(
                payload,
                summary,
                "pibt_applicability_count",
                "bounded_local_pibt_applicability_count",
            ),
            "pibt_attempt_count": _int_metric(
                payload,
                summary,
                "pibt_attempt_count",
                "bounded_local_pibt_attempt_count",
            ),
            "pibt_prepare_count": _int_metric(
                payload,
                summary,
                "pibt_prepare_count",
                "bounded_local_pibt_prepare_count",
            ),
            "pibt_validate_count": _int_metric(
                payload,
                summary,
                "pibt_validate_count",
                "bounded_local_pibt_validate_count",
            ),
            "pibt_commit_count": _int_metric(
                payload,
                summary,
                "pibt_commit_count",
                "bounded_local_pibt_commit_count",
            ),
            "pibt_rollback_count": _int_metric(
                payload,
                summary,
                "pibt_rollback_count",
                "bounded_local_pibt_rollback_count",
            ),
            "pibt_backtrack_count": _int_metric(
                payload,
                summary,
                "pibt_backtrack_count",
                "bounded_local_pibt_backtrack_count",
            ),
            "pibt_wait_for_cycle_count": _int_metric(
                payload,
                summary,
                "pibt_wait_for_cycle_count",
                "bounded_local_pibt_wait_for_cycle_count",
            ),
            "pibt_handoff_count": _int_metric(
                payload,
                summary,
                "pibt_handoff_count",
                "bounded_local_pibt_handoff_count",
            ),
            "route_change_count": _int_metric(
                payload, summary, "route_change_count"
            ),
            "route_oscillation_count": _int_metric(
                payload, summary, "route_oscillation_count"
            ),
        }
    )
    return row


def apply_repeat_consistency(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Fail every executed repeat group whose deterministic hashes disagree."""

    result = [dict(row) for row in rows]
    groups: dict[tuple[str, str, int, str], list[dict[str, Any]]] = {}
    for row in result:
        digest = str(row.get("deterministic_result_sha256", ""))
        if row.get("execution_status") != "EXECUTED" or not digest:
            continue
        key = (
            str(row.get("phase", "")),
            str(row.get("case_id", "")),
            int(row.get("size_segments", 0)),
            str(row.get("case_config_sha256", "")),
        )
        groups.setdefault(key, []).append(row)
    for members in groups.values():
        digests = {str(row["deterministic_result_sha256"]) for row in members}
        status = "MATCH" if len(digests) == 1 and len(members) > 1 else "SINGLE_RESULT"
        if len(digests) > 1:
            status = "MISMATCH"
        for row in members:
            row["repeat_consistency"] = status
            if status == "MISMATCH":
                row["gate_status"] = "FAIL"
                row["evidence_status"] = "DETERMINISTIC_REPEAT_MISMATCH"
                blocker = "DETERMINISTIC_RESULT_HASH_MISMATCH"
                row["blocker"] = " | ".join(
                    part
                    for part in (str(row.get("blocker", "")), blocker)
                    if part
                )
    return result


def _serialized_cell(value: Any) -> str:
    return "" if value is None else str(value)


def _required_row_int(row: Mapping[str, Any], name: str) -> int:
    value = row.get(name)
    if value in (None, "") or isinstance(value, bool):
        raise HarnessValidationError(f"{name} must be a present integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise HarnessValidationError(f"{name} must be an integer") from exc


def _required_row_bool(row: Mapping[str, Any], name: str) -> bool:
    if not _has_metric(row, {}, name):
        raise HarnessValidationError(f"{name} must be a present boolean")
    return _bool_metric(row, {}, name)


def _required_sha256(row: Mapping[str, Any], name: str) -> str:
    value = str(row.get(name, ""))
    if len(value) != 64:
        raise HarnessValidationError(f"{name} must be a non-empty SHA-256")
    try:
        int(value, 16)
    except ValueError as exc:
        raise HarnessValidationError(f"{name} must be hexadecimal") from exc
    return value.lower()


@lru_cache(maxsize=32)
def _cached_prefix_evidence(
    root_text: str,
    size_segments: int,
) -> tuple[str, int]:
    prefix = load_input_prefix(size_segments, root=Path(root_text))
    return prefix.prefix_sha256, prefix.raw_bag_count


def _validate_case_ledger_row(
    row: Mapping[str, Any],
    case: CaseSpec,
    *,
    root: Path = ROOT,
) -> None:
    """Revalidate a serialized executable-case row against current protocol."""

    if row.get("schema") != RESULT_SCHEMA:
        raise HarnessValidationError("result ledger schema mismatch")
    if str(row.get("case_id", "")) != case.case_id:
        raise HarnessValidationError("case_id does not match current CaseSpec")
    if str(row.get("phase", "")) != case.phase:
        raise HarnessValidationError(
            f"{case.case_id}: phase does not match current CaseSpec"
        )
    size = _required_row_int(row, "size_segments")
    if size not in case.sizes:
        raise HarnessValidationError(
            f"{case.case_id}: size {size} is not declared by current CaseSpec"
        )

    expected_scalars = {
        "candidate_id": case.candidate_id,
        "framework_label": case.framework_label,
        "resource_label": case.resource_label,
        "scorer_label": case.scorer_label,
        "pibt_label": case.pibt_label,
        "control_label": case.control_label,
        "fault_profile": case.fault_profile,
        "map_raw_sha256": CANONICAL_MAP_RAW_SHA256,
        "map_semantic_sha256": CANONICAL_MAP_SEMANTIC_SHA256,
        "source_raw_sha256": CANONICAL_SOURCE_RAW_SHA256,
        "source_semantic_sha256": CANONICAL_SOURCE_SEMANTIC_SHA256,
        "case_config_sha256": canonical_sha256(case.as_dict()),
    }
    for name, expected in expected_scalars.items():
        if _serialized_cell(row.get(name, "")) != _serialized_cell(expected):
            raise HarnessValidationError(
                f"{case.case_id}@{size}: {name} does not match current protocol"
            )

    expected_max_events = int(case.runtime_controls["max_events"])
    if _required_row_int(row, "declared_max_events") != expected_max_events:
        raise HarnessValidationError(
            f"{case.case_id}@{size}: declared_max_events drift"
        )
    expected_capacity = int(
        case.runtime_controls.get("local_queue_capacity", 0)
    )
    if _required_row_int(row, "local_queue_capacity") != expected_capacity:
        raise HarnessValidationError(
            f"{case.case_id}@{size}: local_queue_capacity drift"
        )

    execution_status = str(row.get("execution_status", ""))
    if execution_status == "NOT_RUN":
        return
    if execution_status not in {
        "EXECUTED",
        "FAILED",
        "PARTIAL",
        EARLY_ABORT_STATUS,
    }:
        raise HarnessValidationError(
            f"{case.case_id}@{size}: unknown execution_status={execution_status!r}"
        )

    expected_prefix_hash, expected_raw_bags = _cached_prefix_evidence(
        str(root.resolve()),
        size,
    )
    if str(row.get("input_prefix_sha256", "")) != expected_prefix_hash:
        raise HarnessValidationError(
            f"{case.case_id}@{size}: input_prefix_sha256 drift"
        )
    if _required_row_int(row, "selected_segment_count") != size:
        raise HarnessValidationError(
            f"{case.case_id}@{size}: selected_segment_count drift"
        )
    if _required_row_int(row, "selected_raw_bag_count") != expected_raw_bags:
        raise HarnessValidationError(
            f"{case.case_id}@{size}: selected_raw_bag_count drift"
        )

    if execution_status in {"EXECUTED", "PARTIAL", EARLY_ABORT_STATUS}:
        echo_blockers = _control_echo_blockers(case, row)
        if echo_blockers:
            raise HarnessValidationError(
                f"{case.case_id}@{size}: " + " | ".join(echo_blockers)
            )

    gate_status = str(row.get("gate_status", ""))
    if gate_status == "PASS" and execution_status != "EXECUTED":
        raise HarnessValidationError(
            f"{case.case_id}@{size}: PASS requires EXECUTED"
        )
    if gate_status != "PASS":
        return

    for name in (
        "binary_sha256",
        "source_bundle_sha256",
        "executor_source_sha256",
        "deterministic_result_sha256",
    ):
        _required_sha256(row, name)
    if _required_row_int(row, "repeat_index") <= 0:
        raise HarnessValidationError(
            f"{case.case_id}@{size}: repeat_index must be positive"
        )
    if _required_row_int(row, "completed_segment_count") != size:
        raise HarnessValidationError(
            f"{case.case_id}@{size}: completed segment count is incomplete"
        )
    if _required_row_int(row, "complete_raw_bag_count") != expected_raw_bags:
        raise HarnessValidationError(
            f"{case.case_id}@{size}: complete raw bag count is incomplete"
        )
    if _required_row_int(row, "failed_segment_count") != 0:
        raise HarnessValidationError(
            f"{case.case_id}@{size}: failed_segment_count must be zero"
        )
    if not _required_row_bool(row, "comparison_eligible"):
        raise HarnessValidationError(
            f"{case.case_id}@{size}: comparison_eligible must be true"
        )
    completion_rate = _finite_number(
        row.get("completion_rate"),
        "completion_rate",
    )
    if not math.isclose(completion_rate, 1.0, rel_tol=0.0, abs_tol=1.0e-12):
        raise HarnessValidationError(
            f"{case.case_id}@{size}: completion_rate must be 1"
        )

    timing = {
        "comparison_eligible": True,
        "selected_raw_bag_count": expected_raw_bags,
        "complete_raw_bag_count": expected_raw_bags,
        "original_entry_mean_minutes": row.get(
            "original_entry_mean_minutes"
        ),
    }
    safety_blockers = _safety_blockers(
        case=case,
        size=size,
        payload={},
        summary=row,
        timing=timing,
    )
    not_applicable = _not_applicable_reasons(
        case=case,
        payload={},
        summary=row,
    )
    if safety_blockers or not_applicable:
        raise HarnessValidationError(
            f"{case.case_id}@{size}: serialized PASS no longer validates: "
            + " | ".join([*safety_blockers, *not_applicable])
        )


def _accepted_tier_passes(
    case_id: str,
    size_segments: int,
    rows: Sequence[Mapping[str, Any]],
    *,
    root: Path = ROOT,
    required_repeat_count: int = 1,
) -> bool:
    """Require a fully valid, provenance-consistent repeat group."""

    case = next(
        (item for item in all_cases() if item.case_id == case_id),
        None,
    )
    if case is None or required_repeat_count <= 0:
        return False
    members = [
        row
        for row in rows
        if str(row.get("phase", "")) == case.phase
        and str(row.get("case_id", "")) == case_id
        and str(row.get("size_segments", "")) == str(size_segments)
        and str(row.get("execution_status", "")) != "NOT_RUN"
    ]
    if len(members) < required_repeat_count:
        return False
    if any(
        str(row.get("execution_status", "")) != "EXECUTED"
        or str(row.get("gate_status", "")) != "PASS"
        for row in members
    ):
        return False
    try:
        for row in members:
            _validate_case_ledger_row(row, case, root=root)
    except (HarnessValidationError, TypeError, ValueError):
        return False

    repeat_indexes: list[int] = []
    try:
        repeat_indexes = [
            _required_row_int(row, "repeat_index") for row in members
        ]
    except HarnessValidationError:
        return False
    if (
        any(index <= 0 for index in repeat_indexes)
        or len(repeat_indexes) != len(set(repeat_indexes))
    ):
        return False
    provenance_fields = (
        "case_config_sha256",
        "input_prefix_sha256",
        "binary_sha256",
        "source_bundle_sha256",
        "executor_source_sha256",
    )
    if any(
        len({str(row.get(name, "")) for row in members}) != 1
        for name in provenance_fields
    ):
        return False
    result_hashes = {
        str(row.get("deterministic_result_sha256", "")) for row in members
    }
    if len(members) > 1 and len(result_hashes) != 1:
        return False
    return True


def authorization_blockers(
    case: CaseSpec,
    size_segments: int,
    accepted_rows: Sequence[Mapping[str, Any]],
    *,
    allow_8192: bool = False,
    allow_full: bool = False,
    promoted_resource_labels: Sequence[str] = (),
    promoted_finalists: Sequence[str] = (),
    identity_root: Path = ROOT,
    required_repeat_count: int = 1,
) -> list[str]:
    """Return every reason a tier must not be executed."""

    blockers: list[str] = []
    if size_segments not in case.sizes:
        return [f"case does not declare size {size_segments}"]
    if case.execution_blocker:
        blockers.append(case.execution_blocker)
    if size_segments == 8_192 and not allow_8192:
        blockers.append("8192 execution requires --allow-8192")
    if (
        case.phase == "C"
        and size_segments == 8_192
        and case.resource_label not in set(promoted_resource_labels)
    ):
        blockers.append(
            f"C resource {case.resource_label} lacks reviewed best-two selection"
        )
    if size_segments == FULL_SIZE_SEGMENTS:
        if not allow_full:
            blockers.append("full execution requires --allow-full")
        if case.phase == "J" and case.candidate_id not in set(promoted_finalists):
            blockers.append(
                f"J finalist {case.candidate_id} lacks explicit promotion authorization"
            )

    def passed(case_id: str, size: int) -> bool:
        return _accepted_tier_passes(
            case_id,
            size,
            accepted_rows,
            root=identity_root,
            required_repeat_count=required_repeat_count,
        )

    index = case.sizes.index(size_segments)
    if index > 0:
        prior_size = case.sizes[index - 1]
        if not passed(case.case_id, prior_size):
            blockers.append(
                f"missing accepted same-case prior tier {prior_size}"
            )
    if case.phase == "E":
        if not passed(
            f"C_{PLANNING_RESOURCE_ANCHOR.lower()}",
            8_192,
        ):
            blockers.append(
                "E scorer isolation requires accepted C_R3 8192 evidence; "
                "R3 is only the current planning anchor"
            )
    if case.phase == "F":
        if not passed(
            f"E_{PLANNING_SCORER_ANCHOR.lower()}",
            8_192,
        ):
            blockers.append(
                "F depth ablation requires accepted E_S0 8192 evidence; "
                "S0 is only the current planning anchor"
            )
    if case.phase == "H":
        if case.case_id == "H_stable_no_fault":
            anchor_size = (
                size_segments
                if size_segments in {2_048, 8_192}
                else 8_192
            )
            if not passed("G_c6", anchor_size):
                blockers.append(
                    "H stable control requires accepted "
                    f"G_c6 {anchor_size} evidence"
                )
        elif not passed("H_stable_no_fault", size_segments):
            blockers.append(
                "fault injection requires accepted H_stable_no_fault at the same size"
            )
    if case.phase == "J":
        matched_preflight = {
            "J_F1_best_rule_bounded_pibt": ("G_c6", 8_192),
            "J_F2_frozen_scorer_bounded_pibt": (
                "B6_event_corrected_frozen_bounded_pibt",
                8_192,
            ),
            "J_control_pibt_off": ("G_c5", 8_192),
        }.get(case.case_id)
        if matched_preflight is not None and not passed(*matched_preflight):
            blockers.append(
                f"J {case.candidate_id} requires matched preflight "
                f"{matched_preflight[0]} {matched_preflight[1]} PASS"
            )
    return blockers


def load_result_ledger(
    path: Path,
    *,
    root: Path = ROOT,
) -> list[dict[str, Any]]:
    """Admit only rows that still validate against the frozen protocol.

    Historical B0/B1/J controls are compared byte-for-byte at the CSV-cell
    level with freshly parsed frozen controls.  They remain NOT_RUN reference
    evidence and are never reclassified as executable PASS rows.  Stale
    executable-case NOT_RUN rows are intentionally dropped so they cannot
    overwrite the current planning matrix.
    """

    rows = _read_csv(path)
    cases = all_cases()
    case_by_id = {case.case_id: case for case in cases}
    if len(case_by_id) != len(cases):
        raise AssertionError("executable case IDs must be globally unique")
    frozen_controls = load_control_evidence(root)
    control_by_id = {
        str(row["case_id"]): dict(row) for row in frozen_controls
    }
    if len(control_by_id) != len(frozen_controls):
        raise AssertionError("frozen control case IDs must be globally unique")

    admitted: list[dict[str, Any]] = []
    for row_index, row_raw in enumerate(rows, start=2):
        row = dict(row_raw)
        case_id = str(row.get("case_id", ""))
        context = f"{path}:{row_index}"
        if row.get("schema") != RESULT_SCHEMA:
            raise HarnessValidationError(
                f"{context}: result ledger schema mismatch"
            )
        if case_id in control_by_id:
            expected = control_by_id[case_id]
            for column in RESULT_COLUMNS:
                if _serialized_cell(row.get(column, "")) != _serialized_cell(
                    expected.get(column, "")
                ):
                    raise HarnessValidationError(
                        f"{context}: frozen control {case_id} field "
                        f"{column} drift"
                    )
            admitted.append(expected)
            continue
        case = case_by_id.get(case_id)
        if case is None:
            raise HarnessValidationError(
                f"{context}: unknown result-ledger case_id={case_id!r}"
            )
        try:
            _validate_case_ledger_row(row, case, root=root)
        except HarnessValidationError as exc:
            raise HarnessValidationError(f"{context}: {exc}") from exc
        if str(row.get("execution_status", "")) == "NOT_RUN":
            continue
        admitted.append(row)
    return apply_repeat_consistency(admitted)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise HarnessValidationError(f"missing control evidence: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _one_row(
    rows: Sequence[Mapping[str, str]],
    **criteria: str,
) -> Mapping[str, str]:
    matches = [
        row
        for row in rows
        if all(str(row.get(key, "")) == value for key, value in criteria.items())
    ]
    if len(matches) != 1:
        raise HarnessValidationError(
            f"expected one control row for {criteria}, found {len(matches)}"
        )
    return matches[0]


def _control_result(
    *,
    phase: str,
    case_id: str,
    candidate_id: str,
    evidence_status: str,
    denominator: str,
    mean_minutes: float | None,
    complete_bags: int,
    total_bags: int,
    completed_segments: int,
    total_segments: int,
    source_path: str,
    notes: str,
) -> dict[str, Any]:
    row = {
        **{column: "" for column in RESULT_COLUMNS},
        "schema": RESULT_SCHEMA,
        "phase": phase,
        "case_id": case_id,
        "candidate_id": candidate_id,
        "framework_label": (
            "B0" if "historical_hca" in candidate_id else (
                "B1" if "v2_safe" in candidate_id else ""
            )
        ),
        "resource_label": "",
        "scorer_label": "",
        "pibt_label": "",
        "control_label": "",
        "fault_profile": "historical_control",
        "size_segments": total_segments,
        "execution_status": "NOT_RUN",
        "gate_status": "NOT_APPLICABLE",
        "evidence_status": evidence_status,
        "termination_reason": "NOT_RERUN",
        "blocker": "historical/committed control only; no fresh execution",
        "summary_only": True,
        "input_order": INPUT_ORDER_ID,
        "prefix_selection": PREFIX_SELECTION_ID,
        "map_raw_sha256": CANONICAL_MAP_RAW_SHA256,
        "map_semantic_sha256": CANONICAL_MAP_SEMANTIC_SHA256,
        "source_raw_sha256": CANONICAL_SOURCE_RAW_SHA256,
        "source_semantic_sha256": CANONICAL_SOURCE_SEMANTIC_SHA256,
        "primary_denominator": denominator,
        "reported_mean_minutes": mean_minutes if mean_minutes is not None else "",
        "denominator_scope": source_path,
        "selected_segment_count": total_segments,
        "selected_raw_bag_count": total_bags,
        "completed_segment_count": completed_segments,
        "complete_raw_bag_count": complete_bags,
        "failed_segment_count": total_segments - completed_segments,
        "completion_rate": complete_bags / total_bags,
        "comparison_eligible": (
            complete_bags == total_bags and completed_segments == total_segments
        ),
        "repeat_consistency": "HISTORICAL_NOT_RERUN",
        "notes": notes,
    }
    if denominator == "original_entry_time_tth" and mean_minutes is not None:
        row["original_entry_mean_minutes"] = mean_minutes
    if denominator == "java_release_time_tth" and mean_minutes is not None:
        row["java_release_mean_minutes"] = mean_minutes
    return row


def load_control_evidence(root: Path = ROOT) -> list[dict[str, Any]]:
    """Read B0/B1/J controls from existing committed evidence with denominators."""

    assert_fixed_identity(root)
    denominator_path = root / CONTROL_EVIDENCE_PATHS["denominators"]
    ledger_path = root / CONTROL_EVIDENCE_PATHS["g4irsf11_ledger"]
    denominator_rows = _read_csv(denominator_path)
    ledger_rows = _read_csv(ledger_path)

    controls: list[dict[str, Any]] = []
    for phase in ("B", "J"):
        for denominator in (
            "processed_segment_attempt_time_tth",
            "java_release_time_tth",
            "original_entry_time_tth",
        ):
            source = _one_row(
                denominator_rows,
                variant="original_project_text_result",
                tth_denominator=denominator,
            )
            controls.append(
                _control_result(
                    phase=phase,
                    case_id=f"{phase}_control_historical_hca_{denominator}",
                    candidate_id="historical_hca_parsed",
                    evidence_status="PARSED_HISTORICAL_HCA_NOT_FRESH_RERUN",
                    denominator=denominator,
                    mean_minutes=float(source["mean_tht"]),
                    complete_bags=FULL_SIZE_BAGS,
                    total_bags=FULL_SIZE_BAGS,
                    completed_segments=FULL_SIZE_SEGMENTS,
                    total_segments=FULL_SIZE_SEGMENTS,
                    source_path=CONTROL_EVIDENCE_PATHS["denominators"],
                    notes=(
                        "3.967122711 is valid only for processed-segment-attempt; "
                        "the recomputed historical original-entry value is reported separately"
                    ),
                )
            )
        for denominator in (
            "java_release_time_tth",
            "original_entry_time_tth",
        ):
            source = _one_row(
                denominator_rows,
                variant="java_source_queue_one_per_epoch",
                tth_denominator=denominator,
            )
            controls.append(
                _control_result(
                    phase=phase,
                    case_id=f"{phase}_control_v2_safe_{denominator}",
                    candidate_id="frozen_v2_safe",
                    evidence_status="PARSED_FROZEN_V2_SAFE_NOT_RERUN",
                    denominator=denominator,
                    mean_minutes=float(source["mean_tht"]),
                    complete_bags=FULL_SIZE_BAGS,
                    total_bags=FULL_SIZE_BAGS,
                    completed_segments=FULL_SIZE_SEGMENTS,
                    total_segments=FULL_SIZE_SEGMENTS,
                    source_path=CONTROL_EVIDENCE_PATHS["denominators"],
                    notes="frozen central/future-reservation control; never a runtime fallback",
                )
            )

    g11 = _one_row(ledger_rows, case_id="real_map_paper_full")
    g11_row = _control_result(
        phase="J",
        case_id="J_control_g4irsf11_negative",
        candidate_id="g4irsf11_negative_control",
        evidence_status="COMMITTED_G4IRSF11_NEGATIVE_CONTROL_NOT_RERUN",
        denominator="original_entry_time_tth",
        mean_minutes=None,
        complete_bags=FULL_SIZE_BAGS - int(float(g11["end_backlog"])),
        total_bags=int(float(g11["raw_bag_count"])),
        completed_segments=int(float(g11["completed_segment_count"])),
        total_segments=int(float(g11["workload_segment_count"])),
        source_path=CONTROL_EVIDENCE_PATHS["g4irsf11_ledger"],
        notes="incomplete negative control; survivor means excluded from victory claims",
    )
    g11_row.update(
        {
            "original_entry_p95_seconds": g11.get(
                "original_entry_p95_seconds", ""
            ),
            "original_entry_p99_seconds": g11.get(
                "original_entry_p99_seconds", ""
            ),
            "source_wait_mean_minutes": "",
            "network_time_mean_minutes": "",
            "conflict_count": g11.get("conflict_count", ""),
            "runtime_full_astar_calls": g11.get(
                "runtime_full_astar_calls", ""
            ),
            "global_reservation_scan_count": g11.get(
                "global_reservation_scan_count", ""
            ),
            "unresolved_deadlock_count": g11.get(
                "unresolved_deadlock_count", ""
            ),
            "event_count": g11.get("event_count", ""),
            "wall_seconds": g11.get("wall_seconds", ""),
            "peak_working_set_bytes": g11.get("peak_working_set_bytes", ""),
            "comparison_eligible": False,
        }
    )
    controls.append(g11_row)
    return controls


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


def _csv_bytes(
    columns: Sequence[str],
    rows: Iterable[Mapping[str, Any]],
) -> bytes:
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
    return buffer.getvalue().encode("utf-8")


def _phase_status(rows: Sequence[Mapping[str, Any]]) -> str:
    executed = [row for row in rows if row.get("execution_status") == "EXECUTED"]
    if not executed:
        return "PROTOCOL_READY_NO_NEW_EXECUTION"
    if any(row.get("gate_status") == "FAIL" for row in rows):
        return "PARTIAL_WITH_NEGATIVE_RESULTS_RETAINED"
    if any(
        row.get("execution_status") == "NOT_RUN"
        and row.get("gate_status") == "PENDING"
        for row in rows
    ):
        return "PARTIAL_EXECUTION_PENDING_TIERS"
    return "EXECUTED_EVIDENCE_AVAILABLE_NOT_AUTOMATIC_PROMOTION"


def _phase_report(
    title: str,
    rows: Sequence[Mapping[str, Any]],
    *,
    boundary: Sequence[str],
) -> str:
    lines = [
        f"# {title}",
        "",
        f"Status: `{_phase_status(rows)}`.",
        "",
        "Every unexecuted case is retained as `NOT_RUN` / `PENDING`. No planned",
        "row is treated as PASS, and incomplete survivor timing is excluded from",
        "comparison.",
        "",
        "## Evidence ledger",
        "",
        "| Case | Size | R/S/P/C | Fault | Execution | Gate | Complete bags | Segments | Denominator | Blocker |",
        "| --- | ---: | --- | --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    for row in rows:
        labels = "/".join(
            str(row.get(key, ""))
            for key in ("resource_label", "scorer_label", "pibt_label", "control_label")
            if row.get(key, "")
        )
        blocker = str(row.get("blocker", "")).replace("|", "/")
        lines.append(
            "| {case} | {size} | {labels} | {fault} | {execution} | {gate} | "
            "{bags} | {segments} | {denominator} | {blocker} |".format(
                case=row.get("case_id", ""),
                size=row.get("size_segments", ""),
                labels=labels or "historical",
                fault=row.get("fault_profile", ""),
                execution=row.get("execution_status", ""),
                gate=row.get("gate_status", ""),
                bags=row.get("complete_raw_bag_count", ""),
                segments=row.get("completed_segment_count", ""),
                denominator=row.get("primary_denominator", ""),
                blocker=blocker or "",
            )
        )
    lines.extend(["", "## Claim boundary", ""])
    lines.extend(f"- {item}" for item in boundary)
    lines.append("")
    return "\n".join(lines)


CREDIT_COLUMNS = (
    "phase",
    "case_id",
    "size_segments",
    "execution_status",
    "gate_status",
    "credit_issued_count",
    "credit_consumed_count",
    "credit_expired_count",
    "credit_fault_revocation_count",
    "credit_generation_revocation_count",
    "credit_local_hold_count",
    "blocker",
)
QUEUE_COLUMNS = (
    "phase",
    "case_id",
    "size_segments",
    "execution_status",
    "gate_status",
    "control_label",
    "goal_queue_state_artifact_status",
    "blocker",
)
OSCILLATION_COLUMNS = (
    "phase",
    "case_id",
    "size_segments",
    "execution_status",
    "gate_status",
    "route_change_count",
    "route_oscillation_count",
    "blocker",
)
PIBT_WAIT_FOR_COLUMNS = (
    "phase",
    "case_id",
    "size_segments",
    "execution_status",
    "gate_status",
    "pibt_label",
    "local_queue_capacity",
    "pibt_applicability_count",
    "pibt_attempt_count",
    "pibt_wait_for_cycle_count",
    "pibt_backtrack_count",
    "pibt_handoff_count",
    "blocker",
)
PIBT_ATOMIC_COLUMNS = (
    "phase",
    "case_id",
    "size_segments",
    "execution_status",
    "gate_status",
    "pibt_label",
    "local_queue_capacity",
    "pibt_applicability_count",
    "pibt_attempt_count",
    "pibt_prepare_count",
    "pibt_validate_count",
    "pibt_commit_count",
    "pibt_rollback_count",
    "blocker",
)
FAULT_CREDIT_COLUMNS = (
    "case_id",
    "size_segments",
    "fault_profile",
    "execution_status",
    "gate_status",
    "credit_fault_revocation_count",
    "credit_generation_revocation_count",
    "credit_expired_count",
    "blocker",
)
FAULT_PIBT_COLUMNS = (
    "case_id",
    "size_segments",
    "fault_profile",
    "execution_status",
    "gate_status",
    "pibt_label",
    "pibt_handoff_count",
    "fault_local_hold_count",
    "fault_reroute_count",
    "blocker",
)


def candidate_bundle(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    finalists = [case for case in original_scale_cases() if case.finalist_role]
    if len(finalists) > 3:
        raise AssertionError("at most three original-scale finalists are allowed")
    entries: list[dict[str, Any]] = []
    for case in finalists:
        evidence = [
            row
            for row in rows
            if row.get("case_id") == case.case_id
            and int(row.get("size_segments", 0)) == FULL_SIZE_SEGMENTS
        ]
        executed = [
            row
            for row in evidence
            if row.get("execution_status") == "EXECUTED"
        ]
        hashes = {
            str(row.get("deterministic_result_sha256", ""))
            for row in executed
            if row.get("deterministic_result_sha256")
        }
        repeat_gate = (
            len(executed) >= 5
            and len(hashes) == 1
            and all(row.get("deterministic_result_sha256") for row in executed)
        )
        performance = [
            evaluate_original_entry_performance(
                row.get("original_entry_mean_minutes")
            )
            for row in executed
        ]
        v2_gate = len(executed) >= 5 and all(
            item["v2_safe_original_entry_gate"] == "PASS"
            for item in performance
        )
        hca_gate = len(executed) >= 5 and all(
            item["corrected_hca_original_entry_gate"] == "PASS"
            for item in performance
        )
        validated_full_gate = len(executed) >= 5 and all(
            row.get("gate_status") == "PASS" for row in executed
        )
        promoted = bool(
            repeat_gate
            and v2_gate
            and hca_gate
            and validated_full_gate
            and not case.execution_blocker
        )
        blockers: list[str] = []
        if case.execution_blocker:
            blockers.append(case.execution_blocker)
        if len(executed) < 5:
            blockers.append("requires at least five executed full repeats")
        elif not repeat_gate:
            blockers.append("full-repeat deterministic hashes do not match")
        if executed and not v2_gate:
            blockers.append(
                "matched original-entry mean does not meet frozen v2-safe target"
            )
        if executed and not hca_gate:
            blockers.append(
                "matched original-entry mean does not meet corrected HCA target"
            )
        if executed and not validated_full_gate:
            blockers.append(
                "one or more full repeats failed completion, safety, or performance gates"
            )
        means = [
            float(row["original_entry_mean_minutes"])
            for row in executed
            if row.get("original_entry_mean_minutes") not in (None, "")
        ]
        entries.append(
            {
                "case_id": case.case_id,
                "candidate_id": case.candidate_id,
                "role": case.finalist_role,
                "config_sha256": canonical_sha256(case.as_dict()),
                "executed_full_repeat_count": len(executed),
                "deterministic_result_sha256": (
                    next(iter(hashes)) if len(hashes) == 1 else ""
                ),
                "repeat_gate": "PASS" if repeat_gate else "PENDING",
                "v2_safe_original_entry_gate": (
                    "PASS" if v2_gate else ("FAIL" if executed else "PENDING")
                ),
                "corrected_hca_original_entry_gate": (
                    "PASS" if hca_gate else ("FAIL" if executed else "PENDING")
                ),
                "validated_full_gate": (
                    "PASS"
                    if validated_full_gate
                    else ("FAIL" if executed else "PENDING")
                ),
                "maximum_executed_original_entry_mean_minutes": (
                    max(means) if means else ""
                ),
                "promotion_status": "PROMOTED" if promoted else "PENDING",
                "blocker": "" if promoted else " | ".join(blockers),
            }
        )
    bundle = {
        "schema": CANDIDATE_BUNDLE_SCHEMA,
        "g4j_enabled": False,
        "g4j_status": G4J_STATUS,
        "phase_j_promotion_opens_g4j": False,
        "promotion_status": (
            "READY"
            if any(row["promotion_status"] == "PROMOTED" for row in entries)
            else "PENDING"
        ),
        "maximum_finalists": 3,
        "primary_denominator": "original_entry_time_tth",
        "frozen_v2_safe_original_entry_target_minutes": (
            FROZEN_V2_SAFE_ORIGINAL_ENTRY_MINUTES
        ),
        "corrected_hca_original_entry_target_minutes": (
            CORRECTED_HCA_ORIGINAL_ENTRY_MINUTES
        ),
        "non_comparable_processed_attempt_reference_minutes": (
            HISTORICAL_HCA_PROCESSED_ATTEMPT_MINUTES
        ),
        "processed_attempt_reference_warning": PROCESSED_ATTEMPT_WARNING,
        "finalists": entries,
    }
    bundle["bundle_sha256"] = canonical_sha256(bundle)
    return bundle


def _denominator_report() -> str:
    return """# G4IRSF12 Original-Entry Denominator

Status: `FROZEN_FORMULAS_READY`.

For each raw `task_id`, every protected segment participates:

```text
original_entry_time_tth = sum(finish_time - original_entry_time)
java_release_time_tth   = sum(finish_time - pass_time)
scheduled_pre_release   = sum(pass_time - original_entry_time)
source_wait             = sum(admitted_time - pass_time)
network_time            = sum(finish_time - admitted_time)
total_system_time       = scheduled_pre_release + source_wait + network_time
```

`total_system_time` must equal `original_entry_time_tth`. The source file's
`original_entry_time` is the raw-task pass time; split storage rows retain that
same value, while `pass_time` is each Java segment release. A raw bag is
complete only if every selected segment completes. Survivor means are reported
only with an explicit survivor label and never participate in promotion.

Historical HCA* `3.967122711 min` is parsed
`processed_segment_attempt_time_tth`, not original-entry, and never participates
in the Phase-J original-entry gate. Matched original-entry gates use frozen
v2-safe `4.124305453 min` and corrected historical HCA `5.764936746 min`.
The stricter v2-safe target therefore controls promotion, while both comparisons
remain explicit.
"""


def write_harness_outputs(
    rows: Sequence[Mapping[str, Any]],
    *,
    root: Path = ROOT,
    identity_root: Path | None = None,
) -> tuple[Path, ...]:
    """Write every prescribed B/C/E/F/G/H/J output atomically."""

    assert_fixed_identity(identity_root or root)
    normalized = apply_repeat_consistency(rows)
    by_phase = {
        phase: [row for row in normalized if row.get("phase") == phase]
        for phase in ("B", "C", "E", "F", "G", "H", "J")
    }
    paths = {key: root / value for key, value in OUTPUT_PATHS.items()}
    _atomic_write(
        paths["protocol_manifest"],
        (
            json.dumps(
                protocol_manifest(),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8"),
    )

    _atomic_write(
        paths["framework_csv"],
        _csv_bytes(RESULT_COLUMNS, by_phase["B"]),
    )
    _atomic_write(
        paths["framework_report"],
        _phase_report(
            "G4IRSF12 Framework Delta Ladder",
            by_phase["B"],
            boundary=(
                "B0/B1 are parsed controls and are never disguised as fresh reruns.",
                "Each B2--B6 tier changes only its declared framework/resource/scorer/PIBT controls.",
                "B2--B6 share local_queue_capacity=32 as sensitivity-only isolation, not as a physical-capacity claim.",
                "An 8,192 PASS authorizes only finalist review; it does not authorize full automatically.",
            ),
        ).encode("utf-8"),
    )

    _atomic_write(
        paths["resource_runtime_csv"],
        _csv_bytes(RESULT_COLUMNS, by_phase["C"]),
    )
    _atomic_write(
        paths["resource_runtime_report"],
        _phase_report(
            "G4IRSF12 Resource Semantics Runtime Plan",
            by_phase["C"],
            boundary=(
                "This runtime-plan ledger does not overwrite the committed static resource-semantics audit.",
                "R0-R4 first run at 144/512/2048; only two reviewed resources may be selected for 8192.",
                "Unknown physical headway and queue capacity remain sensitivity-only.",
            ),
        ).encode("utf-8"),
    )

    _atomic_write(
        paths["scorer_closed_loop_csv"],
        _csv_bytes(RESULT_COLUMNS, by_phase["E"]),
    )
    _atomic_write(
        paths["scorer_closed_loop_report"],
        _phase_report(
            "G4IRSF12 Scorer Closed-Loop Plan",
            by_phase["E"],
            boundary=(
                "This closed-loop plan does not overwrite the committed offline S0-S4 replay evidence.",
                "R3 is a planning anchor only; execution requires accepted C_R3 8192 evidence.",
                "Frozen G4E remains an out-of-distribution diagnostic and cannot be promoted as a new learned policy.",
            ),
        ).encode("utf-8"),
    )

    _atomic_write(
        paths["pibt_depth_csv"],
        _csv_bytes(RESULT_COLUMNS, by_phase["F"]),
    )
    pibt_wait_for_bytes = _csv_bytes(PIBT_WAIT_FOR_COLUMNS, by_phase["F"])
    for key in ("pibt_wait_for_csv", "pibt_wait_for_motifs_csv"):
        _atomic_write(paths[key], pibt_wait_for_bytes)
    pibt_atomic_bytes = _csv_bytes(PIBT_ATOMIC_COLUMNS, by_phase["F"])
    for key in ("pibt_atomic_csv", "pibt_atomic_commit_rollback_csv"):
        _atomic_write(paths[key], pibt_atomic_bytes)
    _atomic_write(
        paths["pibt_runtime_report"],
        _phase_report(
            "G4IRSF12 Bounded-Local PIBT Runtime Plan",
            by_phase["F"],
            boundary=(
                "P0-P4 share local_queue_capacity=32 as one explicit sensitivity value; this is not a physical-capacity claim.",
                "P1-P4 require positive applicability, attempt, prepare, and validate counts; all published coordination counters must be present and non-negative, while zero handoffs alone remain valid.",
                "An unlimited-capacity P1-P4 execution is NOT_APPLICABLE, never PASS.",
                "The real-map motif suite remains the evidence for actual inheritance, backtracking, cycle guards, and rollback behavior.",
            ),
        ).encode("utf-8"),
    )

    _atomic_write(paths["pressure_csv"], _csv_bytes(RESULT_COLUMNS, by_phase["G"]))
    _atomic_write(paths["credit_csv"], _csv_bytes(CREDIT_COLUMNS, by_phase["G"]))
    queue_rows = [
        {
            **row,
            "goal_queue_state_artifact_status": (
                "SUMMARY_ONLY_NOT_MATERIALIZED"
                if row.get("execution_status") == "EXECUTED"
                else "NOT_RUN"
            ),
        }
        for row in by_phase["G"]
    ]
    _atomic_write(paths["queue_csv"], _csv_bytes(QUEUE_COLUMNS, queue_rows))
    _atomic_write(
        paths["oscillation_csv"], _csv_bytes(OSCILLATION_COLUMNS, by_phase["G"])
    )
    _atomic_write(
        paths["pressure_report"],
        _phase_report(
            "G4IRSF12 Pressure and Credit Design",
            by_phase["G"],
            boundary=(
                "C0--C6 are separate A/B labels; absent executor capabilities remain PENDING.",
                "C0--C6 share local_queue_capacity=32, so pressure/credit/PIBT labels are not confounded by unlimited-versus-finite queues.",
                "Credit binds only the first selected edge and cannot create a future route.",
                "Differential pressure is an engineering local signal, not a throughput-optimality claim.",
            ),
        ).encode("utf-8"),
    )

    _atomic_write(paths["fault_csv"], _csv_bytes(RESULT_COLUMNS, by_phase["H"]))
    _atomic_write(
        paths["fault_credit_csv"],
        _csv_bytes(FAULT_CREDIT_COLUMNS, by_phase["H"]),
    )
    _atomic_write(
        paths["fault_pibt_csv"],
        _csv_bytes(FAULT_PIBT_COLUMNS, by_phase["H"]),
    )
    _atomic_write(
        paths["fault_report"],
        _phase_report(
            "G4IRSF12 Stable-Load Fault Recovery",
            by_phase["H"],
            boundary=(
                "Fault injection starts only after a no-fault candidate is stable on the same real-input window.",
                "Physical interlock and unsafe-entry accounting are never disabled.",
                "A recovery PASS requires affected-bag completion plus true runtime availability for finite non-negative recovery seconds and a finite non-positive post-repair backlog slope.",
            ),
        ).encode("utf-8"),
    )

    _atomic_write(paths["full_csv"], _csv_bytes(RESULT_COLUMNS, by_phase["J"]))
    _atomic_write(
        paths["full_report"],
        _phase_report(
            "G4IRSF12 Original-Scale Full A/B",
            by_phase["J"],
            boundary=(
                "Phase J is evaluated independently while G4J remains CLOSED; a Phase-J PASS does not open G4J.",
                "Only 28,506/28,506 bags and 43,603/43,603 segments can enter the primary comparison.",
                "Every finalist must meet both matched original-entry targets: frozen v2-safe 4.124305453 min and corrected historical HCA 5.764936746 min.",
                "The 3.967122711 min processed-attempt value is shown only as a non-comparable warning.",
                "Historical HCA* remains parsed engineering evidence, not a same-machine rerun.",
            ),
        ).encode("utf-8"),
    )
    _atomic_write(paths["denominator_report"], _denominator_report().encode("utf-8"))
    bundle = candidate_bundle(by_phase["J"])
    _atomic_write(
        paths["candidate_bundle"],
        (
            json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8"),
    )
    promotion_lines = [
        "# G4IRSF12 Promotion Gate",
        "",
        f"Status: `{bundle['promotion_status']}`.",
        "",
        f"G4J status: `{bundle['g4j_status']}` (independent of Phase-J promotion).",
        "",
        "| Finalist | Full repeats | Repeat | v2-safe OE | corrected HCA OE | Promotion | Blocker |",
        "| --- | ---: | --- | --- | --- | --- | --- |",
    ]
    for entry in bundle["finalists"]:
        blocker = str(entry["blocker"]).replace("|", "/")
        promotion_lines.append(
            f"| {entry['candidate_id']} | {entry['executed_full_repeat_count']} | "
            f"{entry['repeat_gate']} | {entry['v2_safe_original_entry_gate']} | "
            f"{entry['corrected_hca_original_entry_gate']} | "
            f"{entry['promotion_status']} | {blocker} |"
        )
    promotion_lines.extend(
        [
            "",
            "A NOT_RUN/PENDING case is never PASS. Incomplete survivor timing is never "
            "eligible for promotion.",
            "",
            "Phase-J promotion never changes G4J status; G4J remains CLOSED.",
            "",
        ]
    )
    _atomic_write(
        paths["promotion_report"],
        "\n".join(promotion_lines).encode("utf-8"),
    )
    return tuple(paths[key] for key in OUTPUT_PATHS)
