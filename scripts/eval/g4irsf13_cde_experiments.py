"""Fail-closed G4IRSF13 C/D/E experiment and evidence runner.

This runner is intentionally narrower than a generic tuning framework:

* it accepts only the protected ``map2.json`` and ``inputdata.jsonl``;
* every runtime request contains the full, unmodified real graph and real task
  rows selected by a deterministic, hash-bound rule;
* controls are passed through an introspected append-only adapter and a missing
  control is recorded as ``NOT_RUN`` instead of being silently ignored;
* the ladder is motif -> 144 -> 512 -> 2048 -> 8192 -> original 1x, with
  explicit prior-tier authorization and at most four full finalists;
* failures, partial drainage, safety violations, and early rejects are retained
  in an append-only local attempt archive;
* committed tables contain compact evidence only.  They never manufacture a
  number for a case or tier that was not executed.

The runtime remains one-edge-at-arrival.  This module does not expose an A*
argument, a future route, or a global reservation table.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass, field
import hashlib
import inspect
import io
import json
import math
import os
from pathlib import Path
import socket
import statistics
import sys
import tempfile
import time
from typing import Any, Callable, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT, ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from scripts.eval import g4irsf12_reproducible_harness as g12  # noqa: E402
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


PROTOCOL_SCHEMA = "czr005.g4irsf13.cde_experiment_protocol.v1"
ADAPTER_SCHEMA = "czr005.g4irsf13.cde_runtime_adapter.v1"
RESULT_SCHEMA = "czr005.g4irsf13.cde_compact_result.v1"
ATTEMPT_SCHEMA = "czr005.g4irsf13.cde_attempt_descriptor.v1"
MANIFEST_SCHEMA = "czr005.g4irsf13.pibt_contention_manifest.v1"

MAP_PATH = Path(CANONICAL_MAP_PATH)
TASK_PATH = Path(CANONICAL_SOURCE_PATH)
LOCAL_ARCHIVE = Path(".local_archives/g4irsf13_cde_experiments")
F2_PER_BAG_PATH = Path("outputs/tables/g4irsf13_per_bag_delta.csv")
F2_DIVERGENCE_PATH = Path("outputs/tables/g4irsf13_decision_divergence.csv")
F2_POINTER_PATH = Path(
    ".local_archives/g4irsf13_delay_attribution/f2/current.json"
)

F2_ORIGINAL_ENTRY_MEAN_MINUTES = 41.514218717973414
FROZEN_V2_SAFE_MEAN_MINUTES = 41.49530698780892

TIER_ORDER = ("motif", "144", "512", "2048", "8192", "full")
TIER_SEGMENTS = {
    "motif": None,
    "144": 144,
    "512": 512,
    "2048": 2_048,
    "8192": 8_192,
    "full": FULL_SIZE_SEGMENTS,
}
NEXT_TIER = {
    tier: TIER_ORDER[index + 1] if index + 1 < len(TIER_ORDER) else None
    for index, tier in enumerate(TIER_ORDER)
}
MAX_FULL_FINALISTS = 4
MOTIF_TARGET_SEGMENTS = 96
MOTIF_RELEASE_WINDOW_SECONDS = 180.0
CONTENTION_MAX_SEGMENTS = 8_192

OUTPUT_PATHS = {
    "priority": Path("outputs/tables/g4irsf13_priority_ablation.csv"),
    "matrix": Path(
        "outputs/tables/g4irsf13_scorer_priority_pibt_control_matrix.csv"
    ),
    "tradeoff": Path(
        "outputs/tables/g4irsf13_source_vs_network_tradeoff.csv"
    ),
    "matched": Path(
        "outputs/tables/g4irsf13_pibt_matched_contention_ab.csv"
    ),
    "depth": Path(
        "outputs/tables/g4irsf13_pibt_depth_priority_ablation.csv"
    ),
    "preference": Path(
        "outputs/tables/g4irsf13_pibt_dodge_regret_ablation.csv"
    ),
    "interaction_report": Path(
        "outputs/reports/g4irsf13_interaction_isolation.md"
    ),
    "pibt_report": Path(
        "outputs/reports/g4irsf13_pibt_contention_analysis.md"
    ),
    "manifest": Path(
        "artifacts/datasets/g4irsf13_pibt_contention_manifest.json"
    ),
}

SOURCE_BUNDLE_PATHS = (
    Path("scripts/eval/g4irsf13_cde_experiments.py"),
    Path("scripts/eval/g4irsf12_reproducible_harness.py"),
    Path("src/czr005/cpp_backend.py"),
    Path("cpp/ics_core/runtime/event_driven_junction.hpp"),
    Path("cpp/ics_core/runtime/bounded_local_pibt.hpp"),
    Path("cpp/ics_core/runtime/expiring_first_edge_credit.hpp"),
    Path("cpp/ics_core/bindings/czr005_cpp.cpp"),
    Path("artifacts/models/g4e_risk_calibrated_policy.json"),
)

CONTROL_ALIASES: Mapping[str, tuple[str, ...]] = {
    "priority_mode": ("priority_mode", "queue_priority_mode"),
    "framework_mode": ("framework_mode",),
    "resource_semantics": ("resource_semantics",),
    "scorer_mode": ("scorer_mode",),
    "pressure_mode": ("pressure_mode",),
    "admission_mode": ("admission_mode",),
    "pibt_mode": ("pibt_mode",),
    "pibt_max_depth": ("pibt_max_depth",),
    "pibt_preference_mode": ("pibt_preference_mode",),
    "pibt_regret_prior_records": ("pibt_regret_prior_records",),
    "selective_credit_contention_threshold": (
        "selective_credit_contention_threshold",
    ),
    "summary_only": ("summary_only",),
    "event_trace_limit": ("event_trace_limit",),
    "expected_binary_path": ("expected_binary_path",),
}

ECHO_ALIASES: Mapping[str, tuple[str, ...]] = {
    "priority_mode": ("priority_mode_echo", "priority_mode"),
    "framework_mode": ("framework_mode_echo", "framework_mode"),
    "resource_semantics": (
        "resource_semantics_echo",
        "resource_semantics",
    ),
    "scorer_mode": ("scorer_mode_echo", "scorer_mode"),
    "pressure_mode": ("pressure_mode_echo", "pressure_mode"),
    "admission_mode": ("admission_mode_echo", "admission_mode"),
    "pibt_mode": ("pibt_mode_echo", "pibt_mode"),
    "pibt_max_depth": ("pibt_max_depth_echo", "pibt_max_depth"),
    "pibt_preference_mode": (
        "pibt_preference_mode_echo",
        "pibt_preference_mode",
    ),
    "selective_credit_contention_threshold": (
        "selective_credit_contention_threshold_echo",
        "selective_credit_contention_threshold",
    ),
}

METRIC_ALIASES: Mapping[str, tuple[str, ...]] = {
    "failed_segment_count": ("failed_count", "failed_segment_count"),
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
    "event_limit_reached": ("event_limit_reached",),
    "time_limit_reached": ("time_limit_reached",),
    "reservation_depth": ("reservation_depth",),
    "max_edges_selected_per_arrive": ("max_edges_selected_per_arrive",),
    "max_actions_committed_per_pibt_batch": (
        "max_actions_committed_per_pibt_batch",
    ),
    "event_count": ("event_count",),
    "credit_issued_count": (
        "credit_issued_count",
        "first_edge_credit_issued_count",
    ),
    "credit_consumed_count": (
        "credit_consumed_count",
        "first_edge_credit_consumed_count",
    ),
    "credit_expired_count": (
        "credit_expired_count",
        "first_edge_credit_expired_count",
    ),
    "credit_local_hold_count": (
        "credit_local_hold_count",
        "first_edge_credit_local_hold_count",
    ),
    "selective_credit_trigger_count": ("selective_credit_trigger_count",),
    "selective_credit_low_load_bypass_count": (
        "selective_credit_low_load_bypass_count",
    ),
    "selective_credit_merge_trigger_count": (
        "selective_credit_merge_trigger_count",
    ),
    "selective_credit_contention_trigger_count": (
        "selective_credit_contention_trigger_count",
    ),
    "priority_teacher_input_count": ("priority_teacher_input_count",),
    "priority_future_route_input_count": (
        "priority_future_route_input_count",
    ),
    "priority_global_scan_count": ("priority_global_scan_count",),
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
    "pibt_max_observed_depth": (
        "pibt_max_observed_depth",
        "bounded_local_pibt_max_observed_depth",
        "bounded_local_pibt_max_inheritance_depth",
    ),
    "pibt_state_read_count": (
        "pibt_state_read_count",
        "bounded_local_pibt_state_read_count",
    ),
    "pibt_message_count": (
        "pibt_message_count",
        "bounded_local_pibt_message_count",
    ),
    "pibt_decision_latency_seconds": (
        "pibt_decision_latency_seconds",
        "bounded_local_pibt_decision_latency_seconds",
    ),
    "pibt_preference_candidate_count": (
        "pibt_preference_candidate_count",
    ),
    "pibt_preference_unique_exit_penalty_count": (
        "pibt_preference_unique_exit_penalty_count",
    ),
    "pibt_preference_wait_cycle_penalty_count": (
        "pibt_preference_wait_cycle_penalty_count",
    ),
    "pibt_preference_backtrack_penalty_count": (
        "pibt_preference_backtrack_penalty_count",
    ),
    "pibt_preference_regret_prior_hit_count": (
        "pibt_preference_regret_prior_hit_count",
    ),
    "decision_latency_us_p50": ("decision_latency_us_p50",),
    "decision_latency_us_p95": ("decision_latency_us_p95",),
    "decision_latency_us_p99": ("decision_latency_us_p99",),
}


class ExperimentError(ValueError):
    """Raised when an experiment artifact cannot be admitted."""


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    family: str
    scorer: str = "S1_frozen_g4e_legal_local_adapter"
    pibt: str = "P2"
    control: str = "C0"
    priority: str = "Q0"
    framework: str = "event_loop_one_step"
    preference: str = "current"
    diagnostic_only: bool = False
    cohort_only: bool = False
    notes: str = ""
    dependency: str = ""

    def __post_init__(self) -> None:
        if not self.candidate_id:
            raise ExperimentError("candidate_id cannot be empty")
        if self.family not in {
            "priority",
            "interaction",
            "pibt_depth",
            "pibt_priority",
            "pibt_preference",
        }:
            raise ExperimentError(f"unknown family: {self.family}")
        if self.pibt not in {"P0", "P1", "P2", "P3", "P4"}:
            raise ExperimentError(f"unknown PIBT mode: {self.pibt}")
        if self.priority not in {"Q0", "Q1", "Q2", "Q3", "$QBEST"}:
            raise ExperimentError(f"unknown priority mode: {self.priority}")
        if self.control not in {
            "C0",
            "C4",
            "C5",
            "C6",
            "C7",
            "C8",
        }:
            raise ExperimentError(f"unknown control mode: {self.control}")
        if self.preference not in {
            "current",
            "dodge",
            "local_regret",
            "dodge_regret",
        }:
            raise ExperimentError(
                f"unknown PIBT preference mode: {self.preference}"
            )

    def resolved(self, qbest: str | None) -> "Candidate":
        if self.priority != "$QBEST":
            return self
        if qbest not in {"Q0", "Q1", "Q2", "Q3"}:
            raise ExperimentError(
                f"{self.candidate_id} requires a measured Qbest"
            )
        values = asdict(self)
        values["priority"] = qbest
        return Candidate(**values)


@dataclass(frozen=True)
class WorkloadSelection:
    selection_id: str
    tier: str
    rows: tuple[dict[str, Any], ...]
    selected_rows_sha256: str
    selected_segment_ids_sha256: str
    raw_bag_count: int
    provenance: Mapping[str, Any] = field(default_factory=dict)

    @property
    def segment_count(self) -> int:
        return len(self.rows)


@dataclass(frozen=True)
class RuntimeCapabilities:
    parameters: tuple[str, ...]
    accepts_var_kwargs: bool
    source_path: str
    source_sha256: str

    def parameter(self, canonical: str) -> str | None:
        aliases = CONTROL_ALIASES.get(canonical, (canonical,))
        if self.accepts_var_kwargs:
            return aliases[0]
        for alias in aliases:
            if alias in self.parameters:
                return alias
        return None


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
        raise ExperimentError(f"missing hash-bound file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ExperimentError(f"missing JSON artifact: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ExperimentError(
            f"cannot decode JSON artifact {path}: {type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise ExperimentError(f"{path} root must be an object")
    return value


def assert_fixed_inputs(root: Path = ROOT) -> dict[str, Any]:
    identity = g12.assert_fixed_identity(root)
    if identity["map_raw_sha256"] != CANONICAL_MAP_RAW_SHA256:
        raise ExperimentError("protected map identity drift")
    if identity["map_semantic_sha256"] != CANONICAL_MAP_SEMANTIC_SHA256:
        raise ExperimentError("protected map semantic identity drift")
    if identity["source_raw_sha256"] != CANONICAL_SOURCE_RAW_SHA256:
        raise ExperimentError("protected task identity drift")
    return identity


def _all_task_rows(root: Path = ROOT) -> list[dict[str, Any]]:
    assert_fixed_inputs(root)
    rows: list[dict[str, Any]] = []
    with (root / TASK_PATH).open("rb") as handle:
        for physical_line, payload in enumerate(handle, start=1):
            normalized = payload.rstrip(b"\r\n")
            if not normalized.strip():
                continue
            value = json.loads(normalized.decode("utf-8"))
            if not isinstance(value, dict):
                raise ExperimentError(
                    f"protected task row {physical_line} is not an object"
                )
            value = dict(value)
            value["input_row_index"] = len(rows)
            value["input_physical_line"] = physical_line
            value["_canonical_line_sha256"] = hashlib.sha256(
                normalized + b"\n"
            ).hexdigest()
            rows.append(value)
    if len(rows) != FULL_SIZE_SEGMENTS:
        raise ExperimentError(
            f"protected task row count {len(rows)} != {FULL_SIZE_SEGMENTS}"
        )
    return rows


def _selection(
    selection_id: str,
    tier: str,
    rows: Sequence[Mapping[str, Any]],
    *,
    provenance: Mapping[str, Any],
) -> WorkloadSelection:
    if not rows:
        raise ExperimentError(f"{selection_id} selected no real task rows")
    ordered = sorted(rows, key=lambda row: int(row["input_row_index"]))
    if len({str(row["segment_id"]) for row in ordered}) != len(ordered):
        raise ExperimentError(f"{selection_id} contains duplicate segment IDs")
    canonical_lines = [
        str(row["_canonical_line_sha256"]) for row in ordered
    ]
    segment_ids = [str(row["segment_id"]) for row in ordered]
    clean_rows = tuple(
        {
            key: value
            for key, value in row.items()
            if key != "_canonical_line_sha256"
        }
        for row in ordered
    )
    return WorkloadSelection(
        selection_id=selection_id,
        tier=tier,
        rows=clean_rows,
        selected_rows_sha256=canonical_sha256(canonical_lines),
        selected_segment_ids_sha256=canonical_sha256(segment_ids),
        raw_bag_count=len({int(row["task_id"]) for row in ordered}),
        provenance=dict(provenance),
    )


def load_prefix_selection(tier: str, root: Path = ROOT) -> WorkloadSelection:
    size = TIER_SEGMENTS.get(tier)
    if not isinstance(size, int):
        raise ExperimentError(f"{tier} is not a prefix tier")
    prefix = g12.load_input_prefix(size, root=root)
    rows = _all_task_rows(root)[:size]
    if [str(row["segment_id"]) for row in rows] != [
        str(row["segment_id"]) for row in prefix.rows
    ]:
        raise ExperimentError("canonical prefix selection identity drift")
    return _selection(
        f"canonical_first_{size}_segments",
        tier,
        rows,
        provenance={
            "fixed_real_map_only": True,
            "task_selection": "first_n_nonempty_rows_without_reordering",
            "prefix_sha256": prefix.prefix_sha256,
            "map_topology_mutated": False,
            "task_rows_mutated": False,
        },
    )


def _graph_topology(root: Path = ROOT) -> dict[str, Any]:
    assert_fixed_inputs(root)
    payload = _read_json(root / MAP_PATH)
    edges = payload.get("edges")
    nodes = payload.get("nodes")
    if not isinstance(edges, list) or not isinstance(nodes, list):
        raise ExperimentError("protected map lacks nodes/edges")
    incoming: dict[int, set[int]] = {}
    outgoing: dict[int, set[int]] = {}
    for edge in edges:
        start = int(edge["start"])
        end = int(edge["end"])
        outgoing.setdefault(start, set()).add(end)
        incoming.setdefault(end, set()).add(start)
    merge_nodes = sorted(
        node for node, parents in incoming.items() if len(parents) >= 2
    )
    split_nodes = sorted(
        node for node, children in outgoing.items() if len(children) >= 2
    )
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "incoming": incoming,
        "outgoing": outgoing,
        "merge_nodes": merge_nodes,
        "split_nodes": split_nodes,
    }


def _reachable_merges(
    source: int,
    topology: Mapping[str, Any],
    *,
    max_hops: int = 4,
) -> set[int]:
    outgoing = topology["outgoing"]
    merge_nodes = set(topology["merge_nodes"])
    frontier = {source}
    visited = {source}
    reached: set[int] = set()
    for _ in range(max_hops):
        next_frontier: set[int] = set()
        for node in frontier:
            for child in outgoing.get(node, ()):
                if child in merge_nodes:
                    reached.add(child)
                if child not in visited:
                    visited.add(child)
                    next_frontier.add(child)
        frontier = next_frontier
    return reached


def load_real_map_motif(root: Path = ROOT) -> WorkloadSelection:
    """Select an unchanged, dense real-task window around real merge routes."""

    topology = _graph_topology(root)
    all_rows = _all_task_rows(root)
    source_nodes = sorted({int(row["start"]) for row in all_rows})
    source_merges = {
        source: _reachable_merges(source, topology) for source in source_nodes
    }
    eligible_sources = {
        source
        for source in source_nodes
        if any(
            source != other
            and source_merges[source] & source_merges[other]
            for other in source_nodes
        )
    }
    candidates = [
        row for row in all_rows if int(row["start"]) in eligible_sources
    ]
    candidates.sort(
        key=lambda row: (
            float(row["pass_time"]),
            int(row["input_row_index"]),
        )
    )
    if len(candidates) < MOTIF_TARGET_SEGMENTS:
        raise ExperimentError(
            "real-map motif rule found too few protected task rows"
        )

    left = 0
    best: tuple[int, int, int] | None = None
    for right, row in enumerate(candidates):
        release = float(row["pass_time"])
        while (
            release - float(candidates[left]["pass_time"])
            > MOTIF_RELEASE_WINDOW_SECONDS
        ):
            left += 1
        window = candidates[left : right + 1]
        distinct_sources = len({int(item["start"]) for item in window})
        shared_merge_coverage = len(
            set().union(
                *(source_merges[int(item["start"])] for item in window)
            )
        )
        score = (
            min(len(window), MOTIF_TARGET_SEGMENTS)
            * max(1, distinct_sources)
            * max(1, shared_merge_coverage)
        )
        candidate_key = (score, -left, right)
        if best is None or candidate_key > best:
            best = candidate_key
    if best is None:
        raise ExperimentError("real-map motif window selection failed")
    _, negative_left, right = best
    left = -negative_left
    window = candidates[left : right + 1]
    selected = window[:MOTIF_TARGET_SEGMENTS]
    if len({int(row["start"]) for row in selected}) < 2:
        raise ExperimentError("real-map motif lacks multiple real sources")
    selected_merges = sorted(
        set().union(
            *(source_merges[int(row["start"])] for row in selected)
        )
    )
    if not selected_merges:
        raise ExperimentError("real-map motif lacks a real merge")
    return _selection(
        "real_map2_dense_merge_window_v1",
        "motif",
        selected,
        provenance={
            "fixed_real_map_only": True,
            "map_path": MAP_PATH.as_posix(),
            "map_raw_sha256": CANONICAL_MAP_RAW_SHA256,
            "map_topology_mutated": False,
            "task_path": TASK_PATH.as_posix(),
            "task_raw_sha256": CANONICAL_SOURCE_RAW_SHA256,
            "task_rows_mutated": False,
            "selection_uses_runtime_future_route": False,
            "selection_rule": (
                "unchanged real rows in densest 180-second release window "
                "whose real start nodes share a real merge within four map hops"
            ),
            "merge_nodes": selected_merges,
            "all_real_merge_node_count": len(topology["merge_nodes"]),
            "all_real_split_node_count": len(topology["split_nodes"]),
            "release_window_seconds": MOTIF_RELEASE_WINDOW_SECONDS,
        },
    )


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise ExperimentError(f"missing evidence table: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _f2_archive_binding(root: Path = ROOT) -> dict[str, Any]:
    pointer_path = root / F2_POINTER_PATH
    pointer = _read_json(pointer_path)
    relative = pointer.get("descriptor_relative_path")
    if not isinstance(relative, str) or not relative:
        raise ExperimentError("F2 archive pointer lacks descriptor path")
    descriptor_path = pointer_path.parent.parent / relative
    descriptor = _read_json(descriptor_path)
    expected = pointer.get("descriptor_file_sha256")
    actual = file_sha256(descriptor_path)
    if actual != expected:
        raise ExperimentError("F2 descriptor file hash differs from pointer")
    if descriptor.get("status") != "COMPLETE":
        raise ExperimentError("F2 full archive is not COMPLETE")
    validation = descriptor.get("validation")
    if not isinstance(validation, Mapping):
        raise ExperimentError("F2 descriptor lacks validation")
    if int(validation.get("segment_count", -1)) != FULL_SIZE_SEGMENTS:
        raise ExperimentError("F2 archive does not cover all protected segments")
    if int(validation.get("raw_bag_count", -1)) != FULL_SIZE_BAGS:
        raise ExperimentError("F2 archive does not cover all protected bags")
    if validation.get("decision_trace_truncated") is not False:
        raise ExperimentError("F2 decision trace is censored")
    return {
        "pointer_path": F2_POINTER_PATH.as_posix(),
        "pointer_sha256": file_sha256(pointer_path),
        "descriptor_relative_path": relative,
        "descriptor_sha256": actual,
        "cache_key": descriptor.get("cache_key"),
        "canonical_payload_sha256": descriptor.get("archive", {}).get(
            "canonical_json_sha256"
        ),
        "decision_trace_count": validation.get("decision_trace_count"),
        "segment_count": validation.get("segment_count"),
        "raw_bag_count": validation.get("raw_bag_count"),
    }


def load_matched_contention_cohort(
    root: Path = ROOT,
) -> tuple[WorkloadSelection, dict[str, Any], list[tuple[int, int, int, float]]]:
    """Build a real-task cohort from actual P2 states in the F2 full run.

    ``g4irsf13_per_bag_delta.csv`` identifies every raw bag touched by a
    recorded P2 transaction.  ``g4irsf13_decision_divergence.csv`` contributes
    the available transaction action context.  A sparse extraction does not
    preserve the queue history that created those transactions, so the cohort
    is the smallest declared canonical prefix tier containing the first actual
    transaction context and four following source rows.  Release times,
    endpoints, deadlines, task order, and topology are never modified.
    """

    assert_fixed_inputs(root)
    archive = _f2_archive_binding(root)
    per_bag_path = root / F2_PER_BAG_PATH
    divergence_path = root / F2_DIVERGENCE_PATH
    per_bag = _read_csv_rows(per_bag_path)
    divergence = _read_csv_rows(divergence_path)
    pibt_task_ids = {
        int(row["task_id"])
        for row in per_bag
        if row.get("pibt_involvement") == "True"
    }
    if not pibt_task_ids:
        raise ExperimentError("F2 full evidence contains no PIBT-involved bag")

    state_rows: list[dict[str, Any]] = []
    regret_observations: list[
        tuple[int, tuple[int, int, int], float]
    ] = []
    activation_ids: set[int] = set()
    for row in divergence:
        if row.get("pibt_involvement") != "True":
            continue
        raw_context = row.get("pibt_owner_chain_json", "")
        try:
            context = json.loads(raw_context)
        except json.JSONDecodeError as exc:
            raise ExperimentError(
                "PIBT owner-chain context is not valid JSON"
            ) from exc
        if not isinstance(context, Mapping) or not context:
            raise ExperimentError("PIBT-involved divergence lacks owner chain")
        actions = context.get("actions")
        if not isinstance(actions, list) or not actions:
            raise ExperimentError("PIBT owner chain lacks actions")
        activation_ids.add(int(context["activation_id"]))
        trigger_id = int(context["trigger_runtime_bag_id"])
        goal = int(row["goal"])
        incoming = max(
            0.0, float(row.get("selected_target_scheduled_incoming") or 0.0)
        )
        wait_age = max(0.0, float(row.get("wait_age_seconds") or 0.0))
        rollback = max(0, int(context.get("rollback_count", 0)))
        backtrack = max(0, int(context.get("backtrack_count", 0)))
        # This is a bounded contention-risk proxy, not a causal delay label.
        # It uses only observed local transaction/queue fields and is clipped.
        proxy_penalty = min(
            60.0,
            rollback * 4.0
            + backtrack * 2.0
            + math.log1p(incoming)
            + min(wait_age / 30.0, 2.0),
        )
        for action in actions:
            if not isinstance(action, Mapping):
                raise ExperimentError("PIBT action context is not an object")
            if int(action.get("runtime_bag_id", -1)) != trigger_id:
                continue
            key = (
                int(action["from_node"]),
                int(action["next_node"]),
                goal,
            )
            regret_observations.append(
                (int(row["task_id"]), key, proxy_penalty)
            )
        state_rows.append(
            {
                "task_id": int(row["task_id"]),
                "segment_id": row["segment_id"],
                "activation_id": int(context["activation_id"]),
                "trigger_runtime_bag_id": trigger_id,
                "trigger_node": int(context["trigger_node"]),
                "outcome": str(context["outcome"]),
                "max_inheritance_depth": int(
                    context.get("max_inheritance_depth", 0)
                ),
                "backtrack_count": backtrack,
                "rollback_count": rollback,
                "action_count": len(actions),
            }
        )
    if not state_rows:
        raise ExperimentError(
            "F2 attribution contains no uncensored PIBT state context"
        )

    all_rows = _all_task_rows(root)
    state_task_ids = {int(row["task_id"]) for row in state_rows}
    state_indices = [
        int(row["input_row_index"])
        for row in all_rows
        if int(row["task_id"]) in state_task_ids
    ]
    if not state_indices:
        raise ExperimentError("F2 state contexts do not map to protected tasks")
    required_prefix_segments = min(state_indices) + 5
    declared_prefix_sizes = [
        int(TIER_SEGMENTS[tier])
        for tier in ("144", "512", "2048", "8192", "full")
    ]
    prefix_size = next(
        (
            size
            for size in declared_prefix_sizes
            if size >= required_prefix_segments
        ),
        None,
    )
    if prefix_size is None or prefix_size > CONTENTION_MAX_SEGMENTS:
        raise ExperimentError(
            "first actual F2 contention context requires "
            f"{required_prefix_segments} history-closed segments, above "
            f"the frozen cap {CONTENTION_MAX_SEGMENTS}"
        )
    selected = all_rows[:prefix_size]
    selected_task_ids_actual = {int(row["task_id"]) for row in selected}
    selected_state_rows = [
        row for row in state_rows if int(row["task_id"]) in selected_task_ids_actual
    ]
    if not selected_state_rows:
        raise ExperimentError(
            "history-closed contention cohort omitted its source F2 state"
        )
    selected_activation_ids = {
        int(row["activation_id"]) for row in selected_state_rows
    }
    selected_pibt_task_ids = pibt_task_ids & selected_task_ids_actual
    if not selected_pibt_task_ids:
        raise ExperimentError(
            "history-closed contention cohort omitted every involved F2 bag"
        )

    regret_accumulator: dict[tuple[int, int, int], list[float]] = {}
    for task_id, key, penalty in regret_observations:
        if task_id in selected_task_ids_actual:
            regret_accumulator.setdefault(key, []).append(penalty)

    prior_records = [
        (
            from_node,
            to_node,
            goal,
            statistics.fmean(penalties),
        )
        for (from_node, to_node, goal), penalties in sorted(
            regret_accumulator.items()
        )
    ]
    selection = _selection(
        "f2_full_first_actual_pibt_state_history_closed_8192_v2",
        "contention_cohort",
        selected,
        provenance={
            "fixed_real_map_only": True,
            "task_rows_mutated": False,
            "map_topology_mutated": False,
            "cohort_source": "actual_uncensored_F2_full_P2_transactions",
            "f2_archive": archive,
            "per_bag_table_path": F2_PER_BAG_PATH.as_posix(),
            "per_bag_table_sha256": file_sha256(per_bag_path),
            "divergence_table_path": F2_DIVERGENCE_PATH.as_posix(),
            "divergence_table_sha256": file_sha256(divergence_path),
            "f2_full_pibt_involved_raw_bag_count": len(pibt_task_ids),
            "selected_f2_pibt_involved_raw_bag_count": len(
                selected_pibt_task_ids
            ),
            "f2_full_state_context_row_count": len(state_rows),
            "f2_full_activation_count": len(activation_ids),
            "selected_state_context_row_count": len(selected_state_rows),
            "selected_activation_count": len(selected_activation_ids),
            "required_prefix_segments": required_prefix_segments,
            "declared_prefix_segments": prefix_size,
            "context_rule": (
                "smallest declared canonical prefix tier containing the "
                "first actual uncensored F2 PIBT state plus four following "
                "canonical rows; all preceding workload history retained"
            ),
        },
    )
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "status": "COHORT_READY_NOT_YET_MATCHED",
        "fixed_real_map_only": True,
        "canonical_map": {
            "path": MAP_PATH.as_posix(),
            "raw_sha256": CANONICAL_MAP_RAW_SHA256,
            "semantic_sha256": CANONICAL_MAP_SEMANTIC_SHA256,
            "topology_mutated": False,
        },
        "canonical_tasks": {
            "path": TASK_PATH.as_posix(),
            "raw_sha256": CANONICAL_SOURCE_RAW_SHA256,
            "rows_mutated": False,
        },
        "f2_full_source": archive,
        "cohort": {
            "selection_id": selection.selection_id,
            "selected_segment_count": selection.segment_count,
            "selected_raw_bag_count": selection.raw_bag_count,
            "selected_rows_sha256": selection.selected_rows_sha256,
            "selected_segment_ids_sha256": (
                selection.selected_segment_ids_sha256
            ),
            "f2_full_pibt_involved_raw_bag_count": len(pibt_task_ids),
            "selected_f2_pibt_involved_raw_bag_count": len(
                selected_pibt_task_ids
            ),
            "f2_full_state_context_row_count": len(state_rows),
            "f2_full_activation_count": len(activation_ids),
            "selected_state_context_row_count": len(selected_state_rows),
            "selected_activation_count": len(selected_activation_ids),
            "required_prefix_segments": required_prefix_segments,
            "declared_prefix_segments": prefix_size,
            "history_closed": True,
        },
        "state_context_sha256": canonical_sha256(selected_state_rows),
        "state_context_sample": selected_state_rows[:16],
        "regret_prior": {
            "status": (
                "OBSERVED_LOCAL_CONTENTION_RISK_PROXY_NOT_CAUSAL_REGRET"
                if prior_records
                else "NOT_AVAILABLE"
            ),
            "runtime_future_route_fields": 0,
            "record_schema": ["from_node", "to_node", "goal", "penalty"],
            "record_count": len(prior_records),
            "records_sha256": canonical_sha256(prior_records),
            "derivation": (
                "clipped deterministic function of observed local incoming, "
                "wait age, backtrack, and rollback fields; no future route"
            ),
            "promotion_claim_allowed": False,
        },
        "matched_gate": {
            "required_modes": ["P0", "P1", "P2", "P3", "P4"],
            "same_cohort_hash_required": True,
            "both_or_all_complete_required": True,
            "survivor_tth_comparison_allowed": False,
            "status": "NOT_RUN",
        },
    }
    return selection, manifest, prior_records


def priority_candidates() -> tuple[Candidate, ...]:
    return (
        Candidate("C_Q0", "priority", priority="Q0", notes="current local queue"),
        Candidate(
            "C_Q1",
            "priority",
            priority="Q1",
            notes="thesis-exact local projection",
        ),
        Candidate(
            "C_Q2",
            "priority",
            priority="Q2",
            notes="thesis type plus slack and aging",
        ),
        Candidate(
            "C_Q3",
            "priority",
            priority="Q3",
            notes="fault/slack/age/stable-id",
        ),
        Candidate(
            "C_B2",
            "priority",
            pibt="P0",
            priority="Q0",
            framework="legacy_order_one_step_diagnostic",
            diagnostic_only=True,
            notes="legacy ordering, one edge only; never a finalist",
        ),
    )


def interaction_candidates() -> tuple[Candidate, ...]:
    return (
        Candidate("D0", "interaction", control="C0", priority="Q0"),
        Candidate("D1", "interaction", control="C4", priority="Q0"),
        Candidate("D2", "interaction", control="C5", priority="Q0"),
        Candidate(
            "D3",
            "interaction",
            control="C6",
            priority="Q0",
            notes=(
                "C6 and C5 share pressure/credit controls when both use P2; "
                "retained as a declared alias, not independent causal evidence"
            ),
        ),
        Candidate("D4", "interaction", control="C7", priority="Q0"),
        Candidate("D5", "interaction", control="C8", priority="Q0"),
        Candidate("D6", "interaction", control="C0", priority="Q1"),
        Candidate("D7", "interaction", control="C0", priority="Q2"),
        Candidate(
            "D8",
            "interaction",
            pibt="P1",
            control="C0",
            priority="$QBEST",
            dependency="measured_priority_Qbest",
        ),
        Candidate(
            "D9",
            "interaction",
            pibt="P3",
            control="C0",
            priority="$QBEST",
            dependency="measured_priority_Qbest",
        ),
    )


def pibt_depth_candidates() -> tuple[Candidate, ...]:
    return tuple(
        Candidate(
            f"E_{mode}",
            "pibt_depth",
            pibt=mode,
            priority="$QBEST",
            diagnostic_only=mode == "P4",
            cohort_only=True,
            dependency="measured_priority_Qbest+matched_contention_cohort",
        )
        for mode in ("P0", "P1", "P2", "P3", "P4")
    )


def pibt_priority_candidates() -> tuple[Candidate, ...]:
    return (
        Candidate(
            "E_PRIO0_CURRENT",
            "pibt_priority",
            priority="Q0",
            cohort_only=True,
        ),
        Candidate(
            "E_PRIO1_THESIS",
            "pibt_priority",
            priority="Q1",
            cohort_only=True,
        ),
        Candidate(
            "E_PRIO2_FAULT_SLACK_AGE_ID",
            "pibt_priority",
            priority="Q3",
            cohort_only=True,
        ),
        Candidate(
            "E_PRIO3_DELAY_REGRET_AWARE",
            "pibt_priority",
            priority="$QBEST",
            preference="local_regret",
            cohort_only=True,
            dependency="measured_priority_Qbest+frozen_regret_prior",
        ),
    )


def pibt_preference_candidates() -> tuple[Candidate, ...]:
    return tuple(
        Candidate(
            f"E_PREF_{preference.upper()}",
            "pibt_preference",
            priority="$QBEST",
            preference=preference,
            cohort_only=True,
            dependency=(
                "measured_priority_Qbest+matched_contention_cohort"
                + (
                    "+frozen_regret_prior"
                    if preference in {"local_regret", "dodge_regret"}
                    else ""
                )
            ),
        )
        for preference in (
            "current",
            "dodge",
            "local_regret",
            "dodge_regret",
        )
    )


def all_candidates() -> tuple[Candidate, ...]:
    rows = (
        *priority_candidates(),
        *interaction_candidates(),
        *pibt_depth_candidates(),
        *pibt_priority_candidates(),
        *pibt_preference_candidates(),
    )
    ids = [row.candidate_id for row in rows]
    if len(ids) != len(set(ids)):
        raise AssertionError("C/D/E candidate IDs must be unique")
    return tuple(rows)


CONTROL_CONFIGS: Mapping[str, Mapping[str, Any]] = {
    "C0": {
        "pressure_mode": "off",
        "admission_mode": "off",
        "enable_backpressure": False,
        "enable_source_admission": False,
    },
    "C4": {
        "pressure_mode": "off",
        "admission_mode": "expiring_first_edge_credit",
        "enable_backpressure": False,
        "enable_source_admission": True,
    },
    "C5": {
        "pressure_mode": "goal_conditioned_differential",
        "admission_mode": "expiring_first_edge_credit",
        "enable_backpressure": True,
        "enable_source_admission": True,
    },
    "C6": {
        "pressure_mode": "goal_conditioned_differential",
        "admission_mode": "expiring_first_edge_credit",
        "enable_backpressure": True,
        "enable_source_admission": True,
    },
    "C7": {
        "pressure_mode": "off",
        "admission_mode": "merge_only_first_edge_credit",
        "enable_backpressure": False,
        "enable_source_admission": True,
    },
    "C8": {
        "pressure_mode": "off",
        "admission_mode": "contention_triggered_first_edge_credit",
        "enable_backpressure": False,
        "enable_source_admission": True,
    },
}


def candidate_runtime_controls(
    candidate: Candidate,
    *,
    qbest: str | None,
    regret_prior_records: Sequence[Sequence[Any]] = (),
) -> dict[str, Any]:
    resolved = candidate.resolved(qbest)
    controls = {
        "resource_semantics": "R3_java_node_window_compatible",
        "scorer_mode": resolved.scorer,
        "pibt_mode": resolved.pibt,
        "pibt_max_depth": int(resolved.pibt[1:]),
        "priority_mode": resolved.priority,
        "framework_mode": resolved.framework,
        "pibt_preference_mode": resolved.preference,
        "pibt_regret_prior_records": [
            [int(row[0]), int(row[1]), int(row[2]), float(row[3])]
            for row in regret_prior_records
        ],
        "selective_credit_contention_threshold": 1,
        "enable_pibt_lite": False,
        "local_queue_capacity": 32 if resolved.pibt != "P0" else 0,
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
        **dict(CONTROL_CONFIGS[resolved.control]),
    }
    if resolved.preference in {"local_regret", "dodge_regret"} and not controls[
        "pibt_regret_prior_records"
    ]:
        raise ExperimentError(
            f"{resolved.candidate_id} requires a non-empty frozen regret prior"
        )
    return controls


def inspect_runtime(
    executor: Callable[..., Mapping[str, Any]],
) -> RuntimeCapabilities:
    try:
        signature = inspect.signature(executor)
    except (TypeError, ValueError) as exc:
        raise ExperimentError(
            f"runtime signature is not introspectable: {exc}"
        ) from exc
    parameters = tuple(signature.parameters)
    accepts_var_kwargs = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    source_path = ""
    source_digest = ""
    try:
        raw_path = inspect.getsourcefile(executor) or inspect.getfile(executor)
    except (TypeError, OSError):
        raw_path = None
    if raw_path:
        path = Path(raw_path)
        if path.is_file():
            source_path = path.resolve().as_posix()
            source_digest = file_sha256(path)
    return RuntimeCapabilities(
        parameters=parameters,
        accepts_var_kwargs=accepts_var_kwargs,
        source_path=source_path,
        source_sha256=source_digest,
    )


def capability_blockers(
    capabilities: RuntimeCapabilities,
    controls: Mapping[str, Any],
) -> list[str]:
    required = {
        "priority_mode",
        "framework_mode",
        "resource_semantics",
        "scorer_mode",
        "admission_mode",
        "pibt_mode",
        "pibt_max_depth",
        "pibt_preference_mode",
        "pibt_regret_prior_records",
        "selective_credit_contention_threshold",
        "summary_only",
        "event_trace_limit",
        "expected_binary_path",
    }
    blockers = [
        f"MISSING_EXECUTOR_CAPABILITY:{name}"
        for name in sorted(required)
        if capabilities.parameter(name) is None
    ]
    for name in controls:
        if capabilities.parameter(name) is None and name not in {
            "reservation_depth",
        }:
            blockers.append(f"MISSING_EXECUTOR_CAPABILITY:{name}")
    return sorted(set(blockers))


def bind_runtime_request(
    capabilities: RuntimeCapabilities,
    base: Mapping[str, Any],
    controls: Mapping[str, Any],
    *,
    summary_only: bool,
) -> tuple[dict[str, Any], list[str]]:
    blockers = capability_blockers(capabilities, controls)
    if blockers:
        return {}, blockers
    request: dict[str, Any] = {}
    for canonical, value in {**dict(base), **dict(controls)}.items():
        target = capabilities.parameter(canonical)
        if target is not None:
            request[target] = value
        elif capabilities.accepts_var_kwargs:
            request[canonical] = value
        elif canonical not in {
            "input_rows",
            "input_selection_sha256",
            "case_config_sha256",
            "reservation_depth",
        }:
            blockers.append(f"MISSING_EXECUTOR_CAPABILITY:{canonical}")
    request[capabilities.parameter("summary_only") or "summary_only"] = (
        summary_only
    )
    request[capabilities.parameter("event_trace_limit") or "event_trace_limit"] = 0
    if "trace_limit" in capabilities.parameters or capabilities.accepts_var_kwargs:
        request["trace_limit"] = 0 if summary_only else -1
    if (
        "trace_shard_count" in capabilities.parameters
        or capabilities.accepts_var_kwargs
    ):
        request["trace_shard_count"] = 1
        request["trace_shard_index"] = 0
    return request, sorted(set(blockers))


def source_bundle_identity(root: Path = ROOT) -> dict[str, Any]:
    rows: list[dict[str, str]] = []
    for relative in SOURCE_BUNDLE_PATHS:
        path = root / relative
        rows.append(
            {"path": relative.as_posix(), "sha256": file_sha256(path)}
        )
    return {
        "paths": rows,
        "path_manifest_sha256": canonical_sha256(
            [row["path"] for row in rows]
        ),
        "bundle_sha256": canonical_sha256(rows),
    }


def _binary_identity(binary: Path) -> dict[str, str]:
    resolved = binary.resolve(strict=True)
    return {
        "path": resolved.as_posix(),
        "sha256": file_sha256(resolved),
    }


def experiment_identity(
    candidate: Candidate,
    selection: WorkloadSelection,
    controls: Mapping[str, Any],
    *,
    binary: Path,
    capabilities: RuntimeCapabilities,
    root: Path = ROOT,
) -> dict[str, Any]:
    return {
        "schema": PROTOCOL_SCHEMA,
        "adapter_schema": ADAPTER_SCHEMA,
        "candidate": asdict(candidate),
        "candidate_config_sha256": canonical_sha256(asdict(candidate)),
        "runtime_controls": dict(controls),
        "runtime_controls_sha256": canonical_sha256(controls),
        "selection": {
            "selection_id": selection.selection_id,
            "tier": selection.tier,
            "segment_count": selection.segment_count,
            "raw_bag_count": selection.raw_bag_count,
            "selected_rows_sha256": selection.selected_rows_sha256,
            "selected_segment_ids_sha256": (
                selection.selected_segment_ids_sha256
            ),
            "provenance": dict(selection.provenance),
        },
        "protected_inputs": {
            "map_path": MAP_PATH.as_posix(),
            "map_raw_sha256": CANONICAL_MAP_RAW_SHA256,
            "map_semantic_sha256": CANONICAL_MAP_SEMANTIC_SHA256,
            "task_path": TASK_PATH.as_posix(),
            "task_raw_sha256": CANONICAL_SOURCE_RAW_SHA256,
            "map_topology_mutated": False,
            "task_rows_mutated": False,
        },
        "binary": _binary_identity(binary),
        "source_bundle": source_bundle_identity(root),
        "executor": {
            "source_path": capabilities.source_path,
            "source_sha256": capabilities.source_sha256,
            "parameters_sha256": canonical_sha256(capabilities.parameters),
        },
        "runtime_contract": {
            "one_next_edge_only": True,
            "reservation_depth": 1,
            "runtime_full_astar_allowed": False,
            "global_reservation_scan_allowed": False,
            "future_route_allowed": False,
            "physical_fault_interlock_always_on": True,
        },
    }


def cache_key(identity: Mapping[str, Any]) -> str:
    return canonical_sha256(identity)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            process = ctypes.windll.kernel32.OpenProcess(  # type: ignore[attr-defined]
                0x1000, False, pid
            )
            if not process:
                return False
            ctypes.windll.kernel32.CloseHandle(process)  # type: ignore[attr-defined]
            return True
        except (AttributeError, OSError):
            return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class AttemptLock:
    def __init__(
        self,
        path: Path,
        *,
        cache_key_value: str,
        stale_seconds: float,
    ) -> None:
        self.path = path
        self.cache_key = cache_key_value
        self.stale_seconds = stale_seconds
        self.acquired = False

    def _archive_stale(self) -> bool:
        if not self.path.is_file():
            return False
        try:
            value = _read_json(self.path)
            started = float(value.get("started_unix_time", 0.0))
            hostname = str(value.get("hostname", ""))
            pid = int(value.get("pid", 0))
        except (OSError, ValueError, TypeError, ExperimentError):
            started = 0.0
            hostname = ""
            pid = 0
        age = max(0.0, time.time() - started)
        local_live = hostname == socket.gethostname() and _pid_alive(pid)
        if age <= self.stale_seconds or local_live:
            return False
        stale = self.path.with_name(
            f"{self.path.name}.stale.{int(time.time())}.{pid}"
        )
        os.replace(self.path, stale)
        return True

    def __enter__(self) -> "AttemptLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                descriptor = os.open(
                    self.path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
            except FileExistsError:
                if self._archive_stale():
                    continue
                raise ExperimentError(
                    f"ACTIVE_ATTEMPT_LOCK:{self.path.as_posix()}"
                )
            payload = canonical_json_bytes(
                {
                    "schema": "czr005.g4irsf13.cde_attempt_lock.v1",
                    "cache_key": self.cache_key,
                    "hostname": socket.gethostname(),
                    "pid": os.getpid(),
                    "started_unix_time": time.time(),
                }
            )
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
            self.acquired = True
            return self
        raise ExperimentError(f"could not acquire lock: {self.path}")

    def __exit__(self, *_args: Any) -> None:
        if self.acquired:
            self.path.unlink(missing_ok=True)
            self.acquired = False


def _completed_pointer(
    cache_dir: Path,
    *,
    expected_cache_key: str,
) -> dict[str, Any] | None:
    path = cache_dir / "complete.json"
    if not path.is_file():
        return None
    pointer = _read_json(path)
    if pointer.get("cache_key") != expected_cache_key:
        raise ExperimentError("complete pointer cache key drift")
    result_relative = pointer.get("result_relative_path")
    if not isinstance(result_relative, str) or not result_relative:
        raise ExperimentError("complete pointer lacks result path")
    result_path = cache_dir / result_relative
    if file_sha256(result_path) != pointer.get("result_file_sha256"):
        raise ExperimentError("cached result hash mismatch")
    result = _read_json(result_path)
    if result.get("cache_key") != expected_cache_key:
        raise ExperimentError("cached result cache key drift")
    result["result_file_sha256"] = pointer["result_file_sha256"]
    return result


def _attempt_paths(cache_dir: Path) -> tuple[str, Path, Path]:
    attempt_id = (
        f"{time.time_ns()}-{socket.gethostname()}-{os.getpid()}"
    )
    attempt_dir = cache_dir / "attempts" / attempt_id
    return (
        attempt_id,
        attempt_dir / "descriptor.json",
        attempt_dir / "result.json",
    )


def _summary_metric(
    payload: Mapping[str, Any],
    summary: Mapping[str, Any],
    aliases: Sequence[str],
    *,
    default: Any = None,
) -> Any:
    for name in aliases:
        if name in summary:
            return summary[name]
        if name in payload:
            return payload[name]
    return default


def _strict_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ExperimentError(f"{label} must be an exact integer")
    return value


def _strict_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ExperimentError(f"{label} must be a boolean")
    return value


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExperimentError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ExperimentError(f"{label} must be finite")
    return result


def _counter_projection(
    payload: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    boolean_names = {"event_limit_reached", "time_limit_reached"}
    float_names = {
        "pibt_decision_latency_seconds",
        "decision_latency_us_p50",
        "decision_latency_us_p95",
        "decision_latency_us_p99",
    }
    for canonical, aliases in METRIC_ALIASES.items():
        value = _summary_metric(payload, summary, aliases, default=None)
        if value is None:
            result[canonical] = None
        elif canonical in boolean_names:
            result[canonical] = _strict_bool(value, canonical)
        elif canonical in float_names:
            result[canonical] = _finite(value, canonical)
        else:
            result[canonical] = _strict_int(value, canonical)
    return result


def _control_echo_blockers(
    summary: Mapping[str, Any],
    controls: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    for canonical, aliases in ECHO_ALIASES.items():
        expected = controls[canonical]
        actual: Any = None
        present = False
        for alias in aliases:
            if alias in summary:
                actual = summary[alias]
                present = True
                break
        if not present:
            blockers.append(f"MISSING_RUNTIME_CONTROL_ECHO:{canonical}")
            continue
        if type(actual) is not type(expected) or actual != expected:
            # Python may expose exact integral doubles for numeric controls.
            numeric_match = (
                isinstance(actual, (int, float))
                and not isinstance(actual, bool)
                and isinstance(expected, (int, float))
                and not isinstance(expected, bool)
                and float(actual) == float(expected)
            )
            if not numeric_match:
                blockers.append(
                    f"RUNTIME_CONTROL_ECHO_MISMATCH:{canonical}="
                    f"{actual!r},expected={expected!r}"
                )
    return blockers


def _deterministic_payload_projection(value: Any) -> Any:
    excluded = {
        "wall_seconds",
        "runtime_seconds",
        "peak_working_set_bytes",
        "loaded_cpp_binary_path",
        "loaded_cpp_binary_sha256",
        "events",
        "decision_trace",
        "decisions",
        "hold_attempts",
        "pibt_events",
        "credit_events",
        "junction_state",
    }
    if isinstance(value, Mapping):
        return {
            str(key): _deterministic_payload_projection(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in excluded
        }
    if isinstance(value, list):
        return [_deterministic_payload_projection(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ExperimentError("runtime payload contains non-finite float")
    return value


def validate_runtime_payload(
    payload: Mapping[str, Any],
    selection: WorkloadSelection,
    controls: Mapping[str, Any],
    *,
    expected_binary: Mapping[str, str],
) -> dict[str, Any]:
    summary = payload.get("summary")
    if not isinstance(summary, Mapping):
        raise ExperimentError("runtime payload.summary must be an object")
    bags = payload.get("bags")
    if not isinstance(bags, list) or not all(
        isinstance(row, Mapping) for row in bags
    ):
        raise ExperimentError("runtime payload.bags must be an object array")
    raw_bags = g12.aggregate_raw_bag_timings(selection.rows, bags)
    timing = g12.summarize_raw_bag_timings(
        raw_bags,
        selected_segment_count=selection.segment_count,
    )
    counters = _counter_projection(payload, summary)
    control_blockers = _control_echo_blockers(summary, controls)

    loaded_path = _summary_metric(
        payload,
        summary,
        ("loaded_cpp_binary_path",),
        default="",
    )
    loaded_hash = _summary_metric(
        payload,
        summary,
        ("loaded_cpp_binary_sha256",),
        default="",
    )
    provenance_blockers: list[str] = []
    if str(loaded_hash).lower() != expected_binary["sha256"].lower():
        provenance_blockers.append("LOADED_BINARY_SHA256_MISMATCH")
    try:
        expected_path = Path(expected_binary["path"]).resolve(strict=True)
        actual_path = Path(str(loaded_path)).resolve(strict=True)
        if os.path.normcase(str(expected_path)) != os.path.normcase(
            str(actual_path)
        ):
            provenance_blockers.append("LOADED_BINARY_PATH_MISMATCH")
    except (OSError, ValueError, RuntimeError):
        provenance_blockers.append("LOADED_BINARY_PATH_INVALID")

    hard_blockers: list[str] = []
    if not timing["comparison_eligible"]:
        hard_blockers.append("INCOMPLETE_DRAIN")
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
            hard_blockers.append(f"MISSING_REQUIRED_COUNTER:{name}")
        elif int(value) != 0:
            hard_blockers.append(f"{name.upper()}={value}")
    for name in ("event_limit_reached", "time_limit_reached"):
        value = counters.get(name)
        if value is None:
            hard_blockers.append(f"MISSING_REQUIRED_COUNTER:{name}")
        elif value is not False:
            hard_blockers.append(f"{name.upper()}=true")
    if counters.get("reservation_depth") != 1:
        hard_blockers.append(
            f"RESERVATION_DEPTH={counters.get('reservation_depth')}"
        )
    max_edges = counters.get("max_edges_selected_per_arrive")
    if max_edges is None:
        hard_blockers.append(
            "MISSING_REQUIRED_COUNTER:max_edges_selected_per_arrive"
        )
    elif int(max_edges) > 1:
        hard_blockers.append(f"MAX_EDGES_PER_ARRIVE={max_edges}")
    for name in (
        "events",
        "decisions",
        "decision_trace",
        "hold_attempts",
        "pibt_events",
        "credit_events",
    ):
        trace = payload.get(name, [])
        if isinstance(trace, list) and trace:
            hard_blockers.append(
                f"SUMMARY_ONLY_TRACE_STORED:{name}={len(trace)}"
            )
    for name in (
        "decision_trace_stored_count",
        "hold_trace_stored_count",
    ):
        stored = _summary_metric(payload, summary, (name,), default=0)
        if _strict_int(stored, name) != 0:
            hard_blockers.append(f"SUMMARY_ONLY_TRACE_STORED:{name}={stored}")

    mechanism_blockers: list[str] = []
    pibt_mode = str(controls["pibt_mode"])
    applicability = counters.get("pibt_applicability_count")
    if (
        selection.tier == "contention_cohort"
        and pibt_mode != "P0"
        and (applicability is None or int(applicability) <= 0)
    ):
        mechanism_blockers.append(
            "UNINFORMATIVE_CONTENTION_COHORT:NO_PIBT_APPLICABILITY"
        )
    admission_mode = str(controls["admission_mode"])
    if admission_mode in {
        "merge_only_first_edge_credit",
        "contention_triggered_first_edge_credit",
    }:
        trigger_count = counters.get("selective_credit_trigger_count")
        if trigger_count is None or int(trigger_count) <= 0:
            mechanism_blockers.append("SELECTIVE_CREDIT_NOT_TRIGGERED")
    preference = str(controls["pibt_preference_mode"])
    if preference in {"dodge", "dodge_regret"}:
        dodge_evidence = sum(
            int(counters.get(name) or 0)
            for name in (
                "pibt_preference_unique_exit_penalty_count",
                "pibt_preference_wait_cycle_penalty_count",
                "pibt_preference_backtrack_penalty_count",
            )
        )
        if dodge_evidence <= 0:
            mechanism_blockers.append("DODGE_PREFERENCE_NOT_EXERCISED")
    if preference in {"local_regret", "dodge_regret"}:
        regret_hits = counters.get(
            "pibt_preference_regret_prior_hit_count"
        )
        if regret_hits is None or int(regret_hits) <= 0:
            mechanism_blockers.append("REGRET_PRIOR_NOT_EXERCISED")

    segment_projection = [
        {
            "segment_id": str(row.get("segment_id", "")),
            "completed": bool(row.get("completed", False)),
            "finish_time": row.get("finish_time"),
            "admitted_time": row.get("admitted_time"),
            "final_node": row.get("final_node"),
            "failure_reason": row.get("failure_reason", ""),
        }
        for row in bags
    ]
    return {
        "timing": timing,
        "counters": counters,
        "control_echo_blockers": control_blockers,
        "provenance_blockers": provenance_blockers,
        "hard_blockers": hard_blockers,
        "mechanism_blockers": mechanism_blockers,
        "gate_status": (
            "PASS"
            if not control_blockers
            and not provenance_blockers
            and not hard_blockers
            and not mechanism_blockers
            else (
                "NOT_APPLICABLE"
                if not control_blockers
                and not provenance_blockers
                and not hard_blockers
                and mechanism_blockers
                else "FAIL"
            )
        ),
        "segment_result_sha256": canonical_sha256(segment_projection),
        "runtime_deterministic_sha256": canonical_sha256(
            _deterministic_payload_projection(payload)
        ),
        "runtime_summary": dict(summary),
        "pibt_event_count_stored": len(payload.get("pibt_events", []))
        if isinstance(payload.get("pibt_events", []), list)
        else 0,
        "credit_event_count_stored": len(payload.get("credit_events", []))
        if isinstance(payload.get("credit_events", []), list)
        else 0,
    }


def _runtime_base_kwargs(
    selection: WorkloadSelection,
    *,
    binary: Path,
    search_path: Path,
    root: Path,
    candidate: Candidate,
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
            for row in selection.rows
        ],
        "input_rows": [dict(row) for row in selection.rows],
        "fault_windows": [],
        "scenario": (
            f"g4irsf13_cde_{candidate.candidate_id}_{selection.tier}"
        ),
        "scale": 1.0,
        "expected_binary_path": str(binary.resolve(strict=True)),
        "search_path": search_path.resolve(strict=True),
        "input_selection_sha256": selection.selected_rows_sha256,
        "case_config_sha256": config_sha256,
    }


def _not_run_result(
    candidate: Candidate,
    selection: WorkloadSelection | None,
    blocker: str,
    *,
    qbest: str | None = None,
) -> dict[str, Any]:
    return {
        "schema": RESULT_SCHEMA,
        "candidate_id": candidate.candidate_id,
        "family": candidate.family,
        "tier": selection.tier if selection else "",
        "selection_id": selection.selection_id if selection else "",
        "selected_segment_count": selection.segment_count if selection else "",
        "selected_raw_bag_count": selection.raw_bag_count if selection else "",
        "selection_sha256": (
            selection.selected_rows_sha256 if selection else ""
        ),
        "cohort_sha256": (
            selection.selected_segment_ids_sha256 if selection else ""
        ),
        "resolved_priority": (
            qbest if candidate.priority == "$QBEST" and qbest else candidate.priority
        ),
        "execution_status": "NOT_RUN",
        "gate_status": "NOT_EVALUATED",
        "promotion_status": "NOT_AUTHORIZED",
        "blocker": blocker,
        "cache_key": "",
        "result_file_sha256": "",
        "attempt_id": "",
    }


def execute_candidate(
    candidate: Candidate,
    selection: WorkloadSelection,
    *,
    executor: Callable[..., Mapping[str, Any]],
    binary: Path,
    search_path: Path,
    qbest: str | None,
    regret_prior_records: Sequence[Sequence[Any]],
    root: Path = ROOT,
    archive_root: Path | None = None,
    stale_lock_seconds: float = 3_600.0,
    summary_only: bool = True,
) -> dict[str, Any]:
    """Execute one admitted case, retaining a hash-bound local attempt."""

    assert_fixed_inputs(root)
    try:
        resolved = candidate.resolved(qbest)
        controls = candidate_runtime_controls(
            resolved,
            qbest=qbest,
            regret_prior_records=regret_prior_records,
        )
    except ExperimentError as exc:
        return _not_run_result(
            candidate, selection, str(exc), qbest=qbest
        )
    capabilities = inspect_runtime(executor)
    blockers = capability_blockers(capabilities, controls)
    if blockers:
        return _not_run_result(
            resolved,
            selection,
            " | ".join(blockers),
            qbest=qbest,
        )
    identity = experiment_identity(
        resolved,
        selection,
        controls,
        binary=binary,
        capabilities=capabilities,
        root=root,
    )
    key = cache_key(identity)
    local_root = archive_root or (root / LOCAL_ARCHIVE)
    cache_dir = (
        local_root
        / resolved.candidate_id
        / selection.tier
        / key
    )
    cached = _completed_pointer(cache_dir, expected_cache_key=key)
    if cached is not None:
        result = dict(cached)
        result["execution_status"] = "CACHED"
        return result

    attempt_id, descriptor_path, result_path = _attempt_paths(cache_dir)
    started = time.time()
    descriptor = {
        "schema": ATTEMPT_SCHEMA,
        "attempt_id": attempt_id,
        "cache_key": key,
        "candidate_id": resolved.candidate_id,
        "tier": selection.tier,
        "status": "RUNNING",
        "identity": identity,
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "started_unix_time": started,
        "completed_unix_time": None,
        "result_relative_path": "",
        "result_file_sha256": "",
        "blocker": "",
    }
    with AttemptLock(
        cache_dir / "attempt.lock",
        cache_key_value=key,
        stale_seconds=stale_lock_seconds,
    ):
        # A process may have completed between the pre-lock check and lock.
        cached = _completed_pointer(cache_dir, expected_cache_key=key)
        if cached is not None:
            result = dict(cached)
            result["execution_status"] = "CACHED"
            return result
        atomic_write_json(descriptor_path, descriptor)
        try:
            base = _runtime_base_kwargs(
                selection,
                binary=binary,
                search_path=search_path,
                root=root,
                candidate=resolved,
                config_sha256=identity["candidate_config_sha256"],
            )
            request, request_blockers = bind_runtime_request(
                capabilities,
                base,
                controls,
                summary_only=summary_only,
            )
            if request_blockers:
                raise ExperimentError(" | ".join(request_blockers))
            wall_started = time.perf_counter()
            raw_payload = executor(**request)
            wall_seconds = time.perf_counter() - wall_started
            if not isinstance(raw_payload, Mapping):
                raise ExperimentError("runtime returned a non-object payload")
            payload = dict(raw_payload)
            validation = validate_runtime_payload(
                payload,
                selection,
                controls,
                expected_binary=identity["binary"],
            )
            result = {
                "schema": RESULT_SCHEMA,
                "candidate_id": resolved.candidate_id,
                "family": resolved.family,
                "tier": selection.tier,
                "selection_id": selection.selection_id,
                "selected_segment_count": selection.segment_count,
                "selected_raw_bag_count": selection.raw_bag_count,
                "selection_sha256": selection.selected_rows_sha256,
                "cohort_sha256": selection.selected_segment_ids_sha256,
                "fixed_real_map_only": True,
                "map_topology_mutated": False,
                "task_rows_mutated": False,
                "resolved_priority": resolved.priority,
                "scorer": resolved.scorer,
                "pibt": resolved.pibt,
                "control": resolved.control,
                "framework": resolved.framework,
                "preference": resolved.preference,
                "diagnostic_only": resolved.diagnostic_only,
                "runtime_future_route_fields": 0,
                "cache_key": key,
                "identity_sha256": canonical_sha256(identity),
                "attempt_id": attempt_id,
                "execution_status": "EXECUTED",
                "gate_status": validation["gate_status"],
                "promotion_status": "PENDING_EARLY_REJECT_REVIEW",
                "blocker": " | ".join(
                    [
                        *validation["control_echo_blockers"],
                        *validation["provenance_blockers"],
                        *validation["hard_blockers"],
                        *validation["mechanism_blockers"],
                    ]
                ),
                "wall_seconds": wall_seconds,
                "timing": validation["timing"],
                "counters": validation["counters"],
                "runtime_deterministic_sha256": validation[
                    "runtime_deterministic_sha256"
                ],
                "segment_result_sha256": validation[
                    "segment_result_sha256"
                ],
                "pibt_event_count_stored": validation[
                    "pibt_event_count_stored"
                ],
                "credit_event_count_stored": validation[
                    "credit_event_count_stored"
                ],
            }
            atomic_write_json(result_path, result)
            result_digest = file_sha256(result_path)
            descriptor.update(
                {
                    "status": "COMPLETE",
                    "completed_unix_time": time.time(),
                    "result_relative_path": result_path.relative_to(
                        cache_dir
                    ).as_posix(),
                    "result_file_sha256": result_digest,
                    "blocker": result["blocker"],
                }
            )
            atomic_write_json(descriptor_path, descriptor)
            atomic_write_json(
                cache_dir / "complete.json",
                {
                    "schema": (
                        "czr005.g4irsf13.cde_complete_pointer.v1"
                    ),
                    "cache_key": key,
                    "attempt_id": attempt_id,
                    "descriptor_relative_path": descriptor_path.relative_to(
                        cache_dir
                    ).as_posix(),
                    "descriptor_file_sha256": file_sha256(descriptor_path),
                    "result_relative_path": result_path.relative_to(
                        cache_dir
                    ).as_posix(),
                    "result_file_sha256": result_digest,
                },
            )
            result["result_file_sha256"] = result_digest
            return result
        except Exception as exc:  # noqa: BLE001 - retain all negative attempts
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
                    resolved,
                    selection,
                    descriptor["blocker"],
                    qbest=qbest,
                ),
                "execution_status": "FAILED",
                "gate_status": "FAIL",
                "promotion_status": "REJECT",
                "cache_key": key,
                "attempt_id": attempt_id,
            }


def _timing_value(result: Mapping[str, Any], name: str) -> float | None:
    timing = result.get("timing")
    if not isinstance(timing, Mapping):
        return None
    value = timing.get(name)
    if value is None or value == "":
        return None
    return _finite(value, f"timing.{name}")


def _counter_value(result: Mapping[str, Any], name: str) -> int | float | None:
    counters = result.get("counters")
    if not isinstance(counters, Mapping):
        return None
    value = counters.get(name)
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExperimentError(f"counter {name} is not numeric")
    return value


def early_reject_reasons(
    result: Mapping[str, Any],
    baseline: Mapping[str, Any] | None,
) -> list[str]:
    """Apply predeclared, matched-denominator early-reject rules."""

    if result.get("execution_status") not in {"EXECUTED", "CACHED"}:
        return ["NOT_EXECUTED"]
    if result.get("gate_status") == "NOT_APPLICABLE":
        return ["MECHANISM_NOT_APPLICABLE"]
    if result.get("gate_status") != "PASS":
        return ["HARD_GATE_FAILURE"]
    if baseline is None:
        return []
    if baseline.get("gate_status") != "PASS":
        return ["MATCHED_F2_TIER_BASELINE_UNAVAILABLE"]
    if result.get("selection_sha256") != baseline.get("selection_sha256"):
        return ["MATCHED_DENOMINATOR_MISMATCH"]

    reasons: list[str] = []
    mean = _timing_value(result, "original_entry_mean_minutes")
    base_mean = _timing_value(baseline, "original_entry_mean_minutes")
    p95 = _timing_value(result, "original_entry_p95_seconds")
    base_p95 = _timing_value(baseline, "original_entry_p95_seconds")
    p99 = _timing_value(result, "original_entry_p99_seconds")
    base_p99 = _timing_value(baseline, "original_entry_p99_seconds")
    if mean is None or base_mean is None:
        reasons.append("PRIMARY_MEAN_UNAVAILABLE")
    elif (mean - base_mean) * 60.0 > 1.0:
        reasons.append("MEAN_WORSE_BY_MORE_THAN_1_SECOND_PER_BAG")
    if p95 is None or base_p95 is None:
        reasons.append("P95_UNAVAILABLE")
    elif p95 - base_p95 > 2.0:
        reasons.append("P95_WORSE_BY_MORE_THAN_2_SECONDS")
    if p99 is None or base_p99 is None:
        reasons.append("P99_UNAVAILABLE")
    elif p99 - base_p99 > 4.0:
        reasons.append("P99_WORSE_BY_MORE_THAN_4_SECONDS")

    source = _timing_value(result, "source_wait_mean_minutes")
    base_source = _timing_value(baseline, "source_wait_mean_minutes")
    network = _timing_value(result, "network_time_mean_minutes")
    base_network = _timing_value(baseline, "network_time_mean_minutes")
    if None not in (source, base_source, network, base_network):
        source_gain = (float(base_source) - float(source)) * 60.0
        network_loss = (float(network) - float(base_network)) * 60.0
        if source_gain > 0.0 and network_loss > source_gain + 0.25:
            reasons.append(
                "SOURCE_WAIT_GAIN_MORE_THAN_OFFSET_BY_NETWORK_LOSS"
            )
    rollback = _counter_value(result, "pibt_rollback_count")
    base_rollback = _counter_value(baseline, "pibt_rollback_count")
    if rollback is not None and base_rollback is not None:
        if float(rollback) > max(float(base_rollback) * 2.0, float(base_rollback) + 10):
            reasons.append("PIBT_ROLLBACK_SURGE")
    return reasons


def apply_early_rejects(
    results: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    updated = [dict(row) for row in results]
    baselines: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in updated:
        if row.get("candidate_id") in {"D0", "C_Q0"}:
            key = (str(row.get("family")), str(row.get("tier")))
            baselines.setdefault(key, row)
        if row.get("candidate_id") == "D0":
            baselines[("interaction", str(row.get("tier")))] = row
    # D0 is the declared interaction-family alias of C_Q0 (same S1/P2/C0/Q0
    # controls).  At the deliberately de-duplicated 8192 tier D0 is NOT_RUN,
    # so use the denominator-matched C_Q0 execution instead of rejecting P1/P3
    # merely because their duplicate baseline was not launched.
    for row in updated:
        if row.get("candidate_id") != "C_Q0":
            continue
        key = ("interaction", str(row.get("tier")))
        existing = baselines.get(key)
        if (
            row.get("gate_status") == "PASS"
            and (
                existing is None
                or existing.get("gate_status") != "PASS"
            )
        ):
            baselines[key] = row
    for row in updated:
        family = str(row.get("family", ""))
        tier = str(row.get("tier", ""))
        baseline = baselines.get((family, tier))
        if family in {"pibt_depth", "pibt_priority", "pibt_preference"}:
            baseline = next(
                (
                    item
                    for item in updated
                    if item.get("candidate_id") == "E_P2"
                    and item.get("cohort_sha256") == row.get("cohort_sha256")
                ),
                None,
            )
        reasons = early_reject_reasons(row, baseline)
        if reasons:
            row["promotion_status"] = "REJECT"
            row["early_reject_reasons"] = ";".join(reasons)
        elif row.get("execution_status") in {"EXECUTED", "CACHED"}:
            if bool(row.get("diagnostic_only")):
                row["promotion_status"] = "DIAGNOSTIC_ONLY_NO_PROMOTION"
            else:
                row["promotion_status"] = "ELIGIBLE_FOR_NEXT_TIER"
            row["early_reject_reasons"] = ""
        else:
            row["early_reject_reasons"] = ";".join(reasons)
    return updated


def select_qbest(
    results: Sequence[Mapping[str, Any]],
    *,
    preferred_tier: str | None = None,
) -> str | None:
    """Select a measured priority using complete matched real-map evidence."""

    all_measured = [
        row
        for row in results
        if row.get("candidate_id") in {"C_Q0", "C_Q1", "C_Q2", "C_Q3"}
        and row.get("gate_status") == "PASS"
        and row.get("promotion_status") != "REJECT"
    ]
    candidates = list(all_measured)
    if preferred_tier is not None:
        candidates = [
            row for row in candidates if row.get("tier") == preferred_tier
        ]
    if not candidates:
        available_tiers = [
            tier
            for tier in TIER_ORDER
            if any(row.get("tier") == tier for row in all_measured)
        ]
        if not available_tiers:
            return None
        latest = max(available_tiers, key=TIER_ORDER.index)
        candidates = [
            row for row in all_measured if row.get("tier") == latest
        ]
    cohort_hashes = {row.get("selection_sha256") for row in candidates}
    if len(cohort_hashes) != 1:
        raise ExperimentError("priority Qbest evidence is not denominator-matched")

    def key(row: Mapping[str, Any]) -> tuple[float, float, float, str]:
        mean = _timing_value(row, "original_entry_mean_minutes")
        p95 = _timing_value(row, "original_entry_p95_seconds")
        p99 = _timing_value(row, "original_entry_p99_seconds")
        if None in (mean, p95, p99):
            raise ExperimentError("Qbest evidence lacks primary timing")
        return float(mean), float(p95), float(p99), str(row["candidate_id"])

    best = min(candidates, key=key)
    return str(best.get("resolved_priority"))


def rank_survivors(
    rows: Sequence[Mapping[str, Any]],
    *,
    limit: int,
    retain_ids: Sequence[str] = (),
) -> set[str]:
    eligible = [
        row
        for row in rows
        if row.get("promotion_status") == "ELIGIBLE_FOR_NEXT_TIER"
    ]

    def key(row: Mapping[str, Any]) -> tuple[float, float, float, str]:
        mean = _timing_value(row, "original_entry_mean_minutes")
        p95 = _timing_value(row, "original_entry_p95_seconds")
        p99 = _timing_value(row, "original_entry_p99_seconds")
        return (
            float("inf") if mean is None else mean,
            float("inf") if p95 is None else p95,
            float("inf") if p99 is None else p99,
            str(row.get("candidate_id", "")),
        )

    ranked = sorted(eligible, key=key)
    eligible_ids = {str(row["candidate_id"]) for row in eligible}
    selected: list[str] = []
    for candidate_id in retain_ids:
        if candidate_id in eligible_ids and candidate_id not in selected:
            selected.append(candidate_id)
            if len(selected) == limit:
                return set(selected)
    for row in ranked:
        candidate_id = str(row["candidate_id"])
        if candidate_id not in selected:
            selected.append(candidate_id)
            if len(selected) == limit:
                break
    return set(selected)


def enforce_full_limit(candidate_ids: Sequence[str]) -> None:
    unique = set(candidate_ids)
    if len(unique) > MAX_FULL_FINALISTS:
        raise ExperimentError(
            f"full tier admits at most {MAX_FULL_FINALISTS} candidates, "
            f"got {len(unique)}"
        )


def matched_contention_gate(
    results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    required = {f"E_P{depth}" for depth in range(5)}
    rows = {
        str(row.get("candidate_id")): row
        for row in results
        if row.get("candidate_id") in required
    }
    missing = sorted(required - set(rows))
    blockers: list[str] = []
    if missing:
        blockers.append("MISSING_MODES:" + ",".join(missing))
    hashes = {
        str(row.get("cohort_sha256", ""))
        for row in rows.values()
        if row.get("cohort_sha256")
    }
    if len(hashes) != 1:
        blockers.append("COHORT_HASH_MISMATCH_OR_MISSING")
    for candidate_id in sorted(required & set(rows)):
        row = rows[candidate_id]
        if row.get("execution_status") not in {"EXECUTED", "CACHED"}:
            blockers.append(f"{candidate_id}:NOT_EXECUTED")
        elif row.get("gate_status") != "PASS":
            blockers.append(f"{candidate_id}:INCOMPLETE_OR_HARD_GATE_FAIL")
        timing = row.get("timing")
        if not isinstance(timing, Mapping) or timing.get(
            "comparison_eligible"
        ) is not True:
            blockers.append(f"{candidate_id}:TTH_INELIGIBLE")
    eligible = not blockers
    return {
        "status": "PASS" if eligible else "PARTIAL_WITH_EXPLICIT_BLOCKER",
        "matched_comparison_eligible": eligible,
        "cohort_sha256": next(iter(hashes)) if len(hashes) == 1 else "",
        "required_modes": sorted(required),
        "complete_modes": sorted(
            candidate_id
            for candidate_id, row in rows.items()
            if row.get("gate_status") == "PASS"
        ),
        "blockers": blockers,
    }


TIER_PROMOTION_LIMITS: Mapping[str, Mapping[str, int]] = {
    "motif": {"priority": 5, "interaction": 10},
    "144": {"priority": 4, "interaction": 6},
    "512": {"priority": 3, "interaction": 4},
    # The 2048 -> 8192 boundary is the first one that can reach the measured
    # F2/P2 contention events.  Preserve the three non-static priority rules
    # plus the two alternate PIBT-depth controls.  D0 is configuration-identical
    # to C_Q0, and D7/Q2 is the static priority control already rejected from
    # the priority family, so neither consumes another 8192 run.
    "2048": {"priority": 3, "interaction": 2},
    "8192": {"priority": 2, "interaction": 4},
    "full": {"priority": 0, "interaction": 0},
}


def execute_ladder(
    *,
    executor: Callable[..., Mapping[str, Any]],
    binary: Path,
    search_path: Path,
    max_tier: str,
    allow_full: bool,
    root: Path = ROOT,
    archive_root: Path | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    if max_tier not in TIER_ORDER:
        raise ExperimentError(f"unknown max tier: {max_tier}")
    if max_tier == "full" and not allow_full:
        raise ExperimentError("full tier requires --allow-full")
    results: list[dict[str, Any]] = []
    family_candidates = {
        "priority": list(priority_candidates()),
        "interaction": list(interaction_candidates()),
    }
    active = {
        family: {candidate.candidate_id for candidate in candidates}
        for family, candidates in family_candidates.items()
    }
    qbest: str | None = None
    max_index = TIER_ORDER.index(max_tier)
    for tier in TIER_ORDER[: max_index + 1]:
        selection = (
            load_real_map_motif(root)
            if tier == "motif"
            else load_prefix_selection(tier, root)
        )
        if tier == "full":
            finalists = sorted(
                active["priority"] | active["interaction"]
            )
            enforce_full_limit(finalists)
        tier_rows: list[dict[str, Any]] = []
        for family, candidates in family_candidates.items():
            for candidate in candidates:
                if candidate.candidate_id not in active[family]:
                    tier_rows.append(
                        _not_run_result(
                            candidate,
                            selection,
                            "SUCCESSIVE_HALVING_NOT_SELECTED",
                            qbest=qbest,
                        )
                    )
                    continue
                if candidate.priority == "$QBEST" and qbest is None:
                    tier_rows.append(
                        _not_run_result(
                            candidate,
                            selection,
                            "MEASURED_QBEST_NOT_AVAILABLE",
                        )
                    )
                    continue
                tier_rows.append(
                    execute_candidate(
                        candidate,
                        selection,
                        executor=executor,
                        binary=binary,
                        search_path=search_path,
                        qbest=qbest,
                        regret_prior_records=(),
                        root=root,
                        archive_root=archive_root,
                    )
                )
        combined = apply_early_rejects([*results, *tier_rows])
        # Replace prior and current rows with their evaluated projections.
        results = combined
        qbest_at_tier = select_qbest(results, preferred_tier=tier)
        if qbest_at_tier is not None:
            qbest = qbest_at_tier
        if tier == max_tier:
            break
        current = [row for row in results if row.get("tier") == tier]
        for family in family_candidates:
            family_rows = [
                row for row in current if row.get("family") == family
            ]
            limit = TIER_PROMOTION_LIMITS[tier][family]
            if family == "priority":
                retain = (
                    ("C_Q0", "C_Q1", "C_Q3")
                    if tier in {"512", "2048"}
                    else (
                        ("C_Q0",)
                    )
                )
            else:
                retain = (
                    ("D8", "D9")
                    if tier == "2048"
                    else (
                        ("D0", "D7", "D8", "D9")
                        if tier == "512"
                        else ("D0",)
                    )
                )
            active[family] = rank_survivors(
                family_rows, limit=limit, retain_ids=retain
            )
        if qbest is not None and tier == "motif":
            # D8/D9 are dependency-blocked at motif and enter at 144 only
            # after Qbest has been measured on the common motif denominator.
            active["interaction"].update({"D8", "D9"})
            if len(active["interaction"]) > TIER_PROMOTION_LIMITS[tier][
                "interaction"
            ]:
                raise ExperimentError(
                    "dependency activation exceeds interaction tier budget"
                )
        if tier == "motif":
            # B2 is deliberately non-promotable as a final candidate, but a
            # second real tier is needed to make the ordering diagnostic useful.
            if any(
                row.get("candidate_id") == "C_B2"
                and row.get("gate_status") == "PASS"
                for row in current
            ):
                active["priority"].add("C_B2")
    return results, qbest


def execute_contention_study(
    *,
    executor: Callable[..., Mapping[str, Any]],
    binary: Path,
    search_path: Path,
    qbest: str | None,
    root: Path = ROOT,
    archive_root: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        selection, manifest, prior = load_matched_contention_cohort(root)
    except ExperimentError as exc:
        rows = [
            _not_run_result(candidate, None, str(exc), qbest=qbest)
            for candidate in (
                *pibt_depth_candidates(),
                *pibt_priority_candidates(),
                *pibt_preference_candidates(),
            )
        ]
        return rows, {
            "schema": MANIFEST_SCHEMA,
            "status": "PARTIAL_WITH_EXPLICIT_BLOCKER",
            "blocker": str(exc),
            "matched_gate": {
                "status": "NOT_RUN",
                "matched_comparison_eligible": False,
            },
        }
    rows: list[dict[str, Any]] = []
    for candidate in (
        *pibt_depth_candidates(),
        *pibt_priority_candidates(),
        *pibt_preference_candidates(),
    ):
        rows.append(
            execute_candidate(
                candidate,
                selection,
                executor=executor,
                binary=binary,
                search_path=search_path,
                qbest=qbest,
                regret_prior_records=prior,
                root=root,
                archive_root=archive_root,
            )
        )
    rows = apply_early_rejects(rows)
    gate = matched_contention_gate(rows)
    manifest = dict(manifest)
    manifest["matched_gate"] = gate
    manifest["status"] = (
        "MATCHED_CONTENTION_EVIDENCE_READY"
        if gate["matched_comparison_eligible"]
        else "PARTIAL_WITH_EXPLICIT_BLOCKER"
    )
    manifest["result_bindings"] = [
        {
            "candidate_id": row.get("candidate_id"),
            "execution_status": row.get("execution_status"),
            "gate_status": row.get("gate_status"),
            "cache_key": row.get("cache_key"),
            "result_file_sha256": row.get("result_file_sha256"),
            "runtime_deterministic_sha256": row.get(
                "runtime_deterministic_sha256"
            ),
        }
        for row in rows
    ]
    return rows, manifest


COMMON_COLUMNS = (
    "candidate_id",
    "family",
    "tier",
    "selection_id",
    "selected_segment_count",
    "selected_raw_bag_count",
    "selection_sha256",
    "cohort_sha256",
    "scorer",
    "pibt",
    "control",
    "resolved_priority",
    "framework",
    "preference",
    "diagnostic_only",
    "execution_status",
    "gate_status",
    "promotion_status",
    "early_reject_reasons",
    "blocker",
    "original_entry_mean_minutes",
    "original_entry_p95_seconds",
    "original_entry_p99_seconds",
    "source_wait_mean_minutes",
    "network_time_mean_minutes",
    "complete_raw_bag_count",
    "completed_segment_count",
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
    "credit_issued_count",
    "credit_consumed_count",
    "credit_expired_count",
    "credit_local_hold_count",
    "selective_credit_trigger_count",
    "selective_credit_low_load_bypass_count",
    "selective_credit_merge_trigger_count",
    "selective_credit_contention_trigger_count",
    "priority_teacher_input_count",
    "priority_future_route_input_count",
    "priority_global_scan_count",
    "pibt_applicability_count",
    "pibt_attempt_count",
    "pibt_prepare_count",
    "pibt_validate_count",
    "pibt_commit_count",
    "pibt_rollback_count",
    "pibt_backtrack_count",
    "pibt_wait_for_cycle_count",
    "pibt_handoff_count",
    "pibt_max_observed_depth",
    "pibt_state_read_count",
    "pibt_message_count",
    "pibt_decision_latency_seconds",
    "pibt_preference_candidate_count",
    "pibt_preference_unique_exit_penalty_count",
    "pibt_preference_wait_cycle_penalty_count",
    "pibt_preference_backtrack_penalty_count",
    "pibt_preference_regret_prior_hit_count",
    "decision_latency_us_p50",
    "decision_latency_us_p95",
    "decision_latency_us_p99",
    "runtime_deterministic_sha256",
    "result_file_sha256",
    "cache_key",
    "attempt_id",
)

TRADEOFF_COLUMNS = (
    "candidate_id",
    "tier",
    "selection_sha256",
    "execution_status",
    "comparison_eligible",
    "source_wait_mean_seconds",
    "network_time_mean_seconds",
    "total_algorithm_sensitive_mean_seconds",
    "delta_source_wait_vs_d0_seconds",
    "delta_network_vs_d0_seconds",
    "net_delta_vs_d0_seconds",
    "source_gain_offset_by_network_loss",
    "promotion_status",
    "blocker",
)

MATCHED_COLUMNS = (
    "candidate_id",
    "pibt",
    "cohort_sha256",
    "selected_segment_count",
    "selected_raw_bag_count",
    "execution_status",
    "gate_status",
    "matched_comparison_eligible",
    "matched_gate_status",
    "original_entry_mean_minutes",
    "original_entry_p95_seconds",
    "original_entry_p99_seconds",
    "pibt_applicability_count",
    "pibt_commit_count",
    "pibt_rollback_count",
    "pibt_backtrack_count",
    "pibt_wait_for_cycle_count",
    "pibt_max_observed_depth",
    "blocker",
    "runtime_deterministic_sha256",
    "result_file_sha256",
)


def _flatten_result(row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    timing = row.get("timing")
    counters = row.get("counters")
    if isinstance(timing, Mapping):
        for name in (
            "original_entry_mean_minutes",
            "original_entry_p95_seconds",
            "original_entry_p99_seconds",
            "source_wait_mean_minutes",
            "network_time_mean_minutes",
            "complete_raw_bag_count",
            "completed_segment_count",
            "completion_rate",
        ):
            result[name] = timing.get(name, "")
    if isinstance(counters, Mapping):
        for name in METRIC_ALIASES:
            result[name] = counters.get(name, "")
    return result


def _selection_for_tier(
    tier: str,
    *,
    root: Path,
    memo: dict[str, WorkloadSelection],
) -> WorkloadSelection:
    if tier not in memo:
        memo[tier] = (
            load_real_map_motif(root)
            if tier == "motif"
            else load_prefix_selection(tier, root)
        )
    return memo[tier]


def complete_ladder_plan(
    results: Sequence[Mapping[str, Any]],
    *,
    qbest: str | None,
    root: Path = ROOT,
) -> list[dict[str, Any]]:
    existing = {
        (str(row.get("candidate_id")), str(row.get("tier"))): dict(row)
        for row in results
    }
    memo: dict[str, WorkloadSelection] = {}
    completed: list[dict[str, Any]] = []
    for candidate in (*priority_candidates(), *interaction_candidates()):
        for tier in TIER_ORDER:
            key = (candidate.candidate_id, tier)
            if key in existing:
                completed.append(existing[key])
                continue
            selection = _selection_for_tier(tier, root=root, memo=memo)
            completed.append(
                _not_run_result(
                    candidate,
                    selection,
                    "TIER_NOT_RUN",
                    qbest=qbest,
                )
            )
    return completed


def complete_contention_plan(
    results: Sequence[Mapping[str, Any]],
    *,
    qbest: str | None,
    selection: WorkloadSelection | None,
) -> list[dict[str, Any]]:
    candidates = (
        *pibt_depth_candidates(),
        *pibt_priority_candidates(),
        *pibt_preference_candidates(),
    )
    existing = {
        str(row.get("candidate_id")): dict(row) for row in results
    }
    return [
        existing.get(candidate.candidate_id)
        or _not_run_result(
            candidate,
            selection,
            "CONTENTION_STUDY_NOT_RUN",
            qbest=qbest,
        )
        for candidate in candidates
    ]


def _tradeoff_rows(
    interaction_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    flattened = [_flatten_result(row) for row in interaction_rows]
    baselines = {
        str(row["tier"]): row
        for row in flattened
        if row.get("candidate_id") == "D0"
        and row.get("gate_status") == "PASS"
    }
    rows: list[dict[str, Any]] = []
    for row in flattened:
        source_minutes = row.get("source_wait_mean_minutes")
        network_minutes = row.get("network_time_mean_minutes")
        eligible = (
            row.get("gate_status") == "PASS"
            and source_minutes not in (None, "")
            and network_minutes not in (None, "")
        )
        baseline = baselines.get(str(row.get("tier")))
        matched = (
            eligible
            and baseline is not None
            and baseline.get("selection_sha256")
            == row.get("selection_sha256")
        )
        if matched:
            source_seconds = float(source_minutes) * 60.0
            network_seconds = float(network_minutes) * 60.0
            base_source = (
                float(baseline["source_wait_mean_minutes"]) * 60.0
            )
            base_network = (
                float(baseline["network_time_mean_minutes"]) * 60.0
            )
            delta_source = source_seconds - base_source
            delta_network = network_seconds - base_network
            net_delta = delta_source + delta_network
            offset = delta_source < 0.0 and delta_network > -delta_source
        else:
            source_seconds = ""
            network_seconds = ""
            delta_source = ""
            delta_network = ""
            net_delta = ""
            offset = ""
        rows.append(
            {
                "candidate_id": row.get("candidate_id"),
                "tier": row.get("tier"),
                "selection_sha256": row.get("selection_sha256"),
                "execution_status": row.get("execution_status"),
                "comparison_eligible": matched,
                "source_wait_mean_seconds": source_seconds,
                "network_time_mean_seconds": network_seconds,
                "total_algorithm_sensitive_mean_seconds": (
                    float(source_seconds) + float(network_seconds)
                    if matched
                    else ""
                ),
                "delta_source_wait_vs_d0_seconds": delta_source,
                "delta_network_vs_d0_seconds": delta_network,
                "net_delta_vs_d0_seconds": net_delta,
                "source_gain_offset_by_network_loss": offset,
                "promotion_status": row.get("promotion_status"),
                "blocker": row.get("blocker"),
            }
        )
    return rows


def _matched_rows(
    contention_rows: Sequence[Mapping[str, Any]],
    gate: Mapping[str, Any],
) -> list[dict[str, Any]]:
    eligible = gate.get("matched_comparison_eligible") is True
    rows: list[dict[str, Any]] = []
    for raw in contention_rows:
        if raw.get("family") != "pibt_depth":
            continue
        row = _flatten_result(raw)
        rows.append(
            {
                "candidate_id": row.get("candidate_id"),
                "pibt": row.get("pibt"),
                "cohort_sha256": row.get("cohort_sha256"),
                "selected_segment_count": row.get(
                    "selected_segment_count"
                ),
                "selected_raw_bag_count": row.get(
                    "selected_raw_bag_count"
                ),
                "execution_status": row.get("execution_status"),
                "gate_status": row.get("gate_status"),
                "matched_comparison_eligible": eligible,
                "matched_gate_status": gate.get("status"),
                # Do not publish survivor TTH when any paired mode failed.
                "original_entry_mean_minutes": (
                    row.get("original_entry_mean_minutes", "")
                    if eligible
                    else ""
                ),
                "original_entry_p95_seconds": (
                    row.get("original_entry_p95_seconds", "")
                    if eligible
                    else ""
                ),
                "original_entry_p99_seconds": (
                    row.get("original_entry_p99_seconds", "")
                    if eligible
                    else ""
                ),
                "pibt_applicability_count": row.get(
                    "pibt_applicability_count", ""
                ),
                "pibt_commit_count": row.get("pibt_commit_count", ""),
                "pibt_rollback_count": row.get(
                    "pibt_rollback_count", ""
                ),
                "pibt_backtrack_count": row.get(
                    "pibt_backtrack_count", ""
                ),
                "pibt_wait_for_cycle_count": row.get(
                    "pibt_wait_for_cycle_count", ""
                ),
                "pibt_max_observed_depth": row.get(
                    "pibt_max_observed_depth", ""
                ),
                "blocker": row.get("blocker", ""),
                "runtime_deterministic_sha256": row.get(
                    "runtime_deterministic_sha256", ""
                ),
                "result_file_sha256": row.get(
                    "result_file_sha256", ""
                ),
            }
        )
    return rows


def _status_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("execution_status", "UNKNOWN"))
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _interaction_report(
    ladder_rows: Sequence[Mapping[str, Any]],
    *,
    qbest: str | None,
) -> str:
    executed = [
        row
        for row in ladder_rows
        if row.get("execution_status") in {"EXECUTED", "CACHED"}
    ]
    full = [row for row in executed if row.get("tier") == "full"]
    status = (
        "ORIGINAL_1X_INTERACTION_EVIDENCE_READY"
        if full
        else "PARTIAL_WITH_EXPLICIT_BLOCKER"
    )
    rejected = [
        row for row in executed if row.get("promotion_status") == "REJECT"
    ]
    lines = [
        "# G4IRSF13-D Interaction Isolation",
        "",
        f"Status: `{status}`.",
        "",
        "The matrix is executed only on the protected real map and unchanged "
        "real task rows. Blank metrics mean `NOT_RUN`; they are not zero.",
        "",
        "## Current evidence",
        "",
        f"- Executed/cached rows: `{len(executed)}`.",
        f"- Explicitly rejected rows: `{len(rejected)}`.",
        f"- Measured priority selection: `{qbest or 'NOT_AVAILABLE'}`.",
        f"- Execution status counts: `{json.dumps(_status_counts(ladder_rows), sort_keys=True)}`.",
        "- C7 publishes only a real merge slot; C8 activates only on local "
        "contention evidence and must degrade to C0 under low load.",
        "- C5 and C6 have the same pressure/credit vector when both use P2. "
        "Their duplicate configuration is retained and not misreported as an "
        "independent causal contrast.",
        "",
        "## Early rejection",
        "",
        "A candidate is rejected before 8192 for incomplete drainage, any hard "
        "safety/architecture violation, >1 s/bag matched mean loss, >2 s p95 "
        "loss, >4 s p99 loss, a source-wait gain more than offset by network "
        "loss, or a material PIBT rollback surge.",
        "",
        "## Claim boundary",
        "",
        "Motif, 144, 512, 2048, and 8192 are successive-halving diagnostics. "
        "Only up to four explicitly authorized finalists may run full. B2 is "
        "a legacy-order one-step diagnostic and can never be a finalist. No "
        "runtime A*, future route, or global reservation scan is admitted.",
        "",
    ]
    return "\n".join(lines)


def _pibt_report(
    contention_rows: Sequence[Mapping[str, Any]],
    manifest: Mapping[str, Any],
) -> str:
    gate = (
        manifest.get("matched_gate")
        if isinstance(manifest.get("matched_gate"), Mapping)
        else {}
    )
    eligible = gate.get("matched_comparison_eligible") is True
    lines = [
        "# G4IRSF13-E PIBT Contention Analysis",
        "",
        f"Status: `{manifest.get('status', 'PARTIAL_WITH_EXPLICIT_BLOCKER')}`.",
        "",
        "The cohort is derived from actual, uncensored P2 transactions in the "
        "F2 full run and reuses unchanged rows from the protected task file on "
        "the complete protected map.",
        "",
        "## Matched gate",
        "",
        f"- TTH comparison eligible: `{eligible}`.",
        f"- Cohort SHA-256: `{gate.get('cohort_sha256', '')}`.",
        f"- Complete modes: `{', '.join(gate.get('complete_modes', [])) or 'none'}`.",
        f"- Blockers: `{' | '.join(gate.get('blockers', [])) or 'none'}`.",
        "",
        "P0-P4 TTH values are published in the matched table only when every "
        "mode drains the identical cohort and clears all hard gates. Survivor "
        "timing is never substituted.",
        "",
        "## Preference evidence",
        "",
        "The dodge variants use one-step local tie-breaking and unique-exit / "
        "wait-for-cycle protection. The frozen local regret input is currently "
        "an observed contention-risk proxy, not a causal regret estimate; it "
        "therefore cannot by itself support promotion.",
        "",
        "## Theory boundary",
        "",
        "The protected directed graph has merges, splits, bridges, multiple "
        "SCCs and sinks. The implementation is accurately described as "
        "`PIBT-inspired bounded local priority inheritance and backtracking`; "
        "classic PIBT finite-arrival guarantees are not claimed.",
        "",
        f"Recorded contention result rows: `{len(contention_rows)}`.",
        "",
    ]
    return "\n".join(lines)


def write_outputs(
    ladder_results: Sequence[Mapping[str, Any]],
    contention_results: Sequence[Mapping[str, Any]],
    manifest: Mapping[str, Any],
    *,
    qbest: str | None,
    root: Path = ROOT,
) -> dict[str, Any]:
    ladder = complete_ladder_plan(
        ladder_results, qbest=qbest, root=root
    )
    try:
        cohort_selection, cohort_manifest, _prior = (
            load_matched_contention_cohort(root)
        )
    except ExperimentError:
        cohort_selection = None
        cohort_manifest = {}
    contention = complete_contention_plan(
        contention_results,
        qbest=qbest,
        selection=cohort_selection,
    )
    effective_manifest = dict(cohort_manifest)
    effective_manifest.update(dict(manifest))
    effective_manifest["matched_gate"] = matched_contention_gate(contention)
    effective_manifest["protocol"] = {
        "schema": PROTOCOL_SCHEMA,
        "adapter_schema": ADAPTER_SCHEMA,
        "tier_order": list(TIER_ORDER),
        "maximum_full_finalists": MAX_FULL_FINALISTS,
        "full_default_authorized": False,
        "candidate_matrix_sha256": canonical_sha256(
            [asdict(candidate) for candidate in all_candidates()]
        ),
        "runtime_contract": {
            "one_next_edge_only": True,
            "reservation_depth": 1,
            "runtime_full_astar_allowed": False,
            "future_route_allowed": False,
            "global_reservation_scan_allowed": False,
        },
    }
    effective_manifest["qbest"] = {
        "value": qbest,
        "status": "MEASURED" if qbest else "NOT_RUN",
    }
    effective_manifest["result_bindings"] = [
        {
            "candidate_id": row.get("candidate_id"),
            "tier": row.get("tier"),
            "execution_status": row.get("execution_status"),
            "gate_status": row.get("gate_status"),
            "cache_key": row.get("cache_key"),
            "result_file_sha256": row.get("result_file_sha256"),
            "runtime_deterministic_sha256": row.get(
                "runtime_deterministic_sha256"
            ),
        }
        for row in contention
        if row.get("execution_status") in {"EXECUTED", "CACHED"}
    ]

    flattened_ladder = [_flatten_result(row) for row in ladder]
    flattened_contention = [_flatten_result(row) for row in contention]
    priority = [
        row for row in flattened_ladder if row.get("family") == "priority"
    ]
    interaction = [
        row
        for row in flattened_ladder
        if row.get("family") == "interaction"
    ]
    depth = [
        row
        for row in flattened_contention
        if row.get("family") in {"pibt_depth", "pibt_priority"}
    ]
    preference = [
        row
        for row in flattened_contention
        if row.get("family") == "pibt_preference"
    ]
    matched_gate_value = effective_manifest["matched_gate"]
    matched = _matched_rows(contention, matched_gate_value)

    atomic_write_csv(root / OUTPUT_PATHS["priority"], COMMON_COLUMNS, priority)
    atomic_write_csv(root / OUTPUT_PATHS["matrix"], COMMON_COLUMNS, interaction)
    atomic_write_csv(
        root / OUTPUT_PATHS["tradeoff"],
        TRADEOFF_COLUMNS,
        _tradeoff_rows(interaction),
    )
    atomic_write_csv(root / OUTPUT_PATHS["matched"], MATCHED_COLUMNS, matched)
    atomic_write_csv(root / OUTPUT_PATHS["depth"], COMMON_COLUMNS, depth)
    atomic_write_csv(
        root / OUTPUT_PATHS["preference"],
        COMMON_COLUMNS,
        preference,
    )
    _atomic_write(
        root / OUTPUT_PATHS["interaction_report"],
        _interaction_report(ladder, qbest=qbest).encode("utf-8"),
    )
    _atomic_write(
        root / OUTPUT_PATHS["pibt_report"],
        _pibt_report(contention, effective_manifest).encode("utf-8"),
    )
    atomic_write_json(root / OUTPUT_PATHS["manifest"], effective_manifest)
    return {
        "status": (
            "SMALL_TIER_EVIDENCE_RECORDED"
            if any(
                row.get("execution_status") in {"EXECUTED", "CACHED"}
                for row in [*ladder, *contention]
            )
            else "PROTOCOL_READY_NO_RUNTIME_ATTEMPTS"
        ),
        "qbest": qbest,
        "ladder_execution_counts": _status_counts(ladder),
        "contention_execution_counts": _status_counts(contention),
        "matched_gate": matched_gate_value,
        "outputs": {
            name: path.as_posix() for name, path in OUTPUT_PATHS.items()
        },
    }


def validate_committed_outputs(root: Path = ROOT) -> dict[str, Any]:
    assert_fixed_inputs(root)
    required = [root / path for path in OUTPUT_PATHS.values()]
    missing = [path for path in required if not path.is_file()]
    if missing:
        raise ExperimentError(f"missing committed C/D/E outputs: {missing}")

    expected_tables: Mapping[str, tuple[Sequence[str], int]] = {
        "priority": (COMMON_COLUMNS, len(priority_candidates()) * len(TIER_ORDER)),
        "matrix": (
            COMMON_COLUMNS,
            len(interaction_candidates()) * len(TIER_ORDER),
        ),
        "tradeoff": (
            TRADEOFF_COLUMNS,
            len(interaction_candidates()) * len(TIER_ORDER),
        ),
        "matched": (MATCHED_COLUMNS, len(pibt_depth_candidates())),
        "depth": (
            COMMON_COLUMNS,
            len(pibt_depth_candidates()) + len(pibt_priority_candidates()),
        ),
        "preference": (COMMON_COLUMNS, len(pibt_preference_candidates())),
    }
    decoded: dict[str, list[dict[str, str]]] = {}
    for name, (columns, expected_count) in expected_tables.items():
        path = root / OUTPUT_PATHS[name]
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != tuple(columns):
                raise ExperimentError(f"{name} table header drift")
            rows = [dict(row) for row in reader]
        if len(rows) != expected_count:
            raise ExperimentError(
                f"{name} table row count {len(rows)} != {expected_count}"
            )
        decoded[name] = rows

    metric_names = (
        "original_entry_mean_minutes",
        "original_entry_p95_seconds",
        "original_entry_p99_seconds",
        "source_wait_mean_minutes",
        "network_time_mean_minutes",
    )
    for table_name in ("priority", "matrix", "depth", "preference"):
        for row in decoded[table_name]:
            if row["execution_status"] == "NOT_RUN" and any(
                row.get(name, "") != "" for name in metric_names
            ):
                raise ExperimentError(
                    f"{table_name}:{row['candidate_id']} fabricates NOT_RUN metrics"
                )
            if row["runtime_full_astar_calls"] not in {"", "0"}:
                raise ExperimentError(
                    f"{table_name}:{row['candidate_id']} used runtime A*"
                )
            if row["global_reservation_scan_count"] not in {"", "0"}:
                raise ExperimentError(
                    f"{table_name}:{row['candidate_id']} used global scan"
                )
            if row["future_routes_stored"] not in {"", "0"}:
                raise ExperimentError(
                    f"{table_name}:{row['candidate_id']} stored a future route"
                )
            if (
                row["execution_status"] in {"EXECUTED", "CACHED"}
                and row["gate_status"] == "PASS"
                and row["reservation_depth"] != "1"
            ):
                raise ExperimentError(
                    f"{table_name}:{row['candidate_id']} reservation depth drift"
                )

    full_executed = {
        row["candidate_id"]
        for row in [*decoded["priority"], *decoded["matrix"]]
        if row["tier"] == "full"
        and row["execution_status"] in {"EXECUTED", "CACHED"}
    }
    enforce_full_limit(sorted(full_executed))

    matched_eligible_values = {
        row["matched_comparison_eligible"] for row in decoded["matched"]
    }
    if len(matched_eligible_values) != 1:
        raise ExperimentError("matched contention rows disagree on gate")
    if matched_eligible_values == {"False"}:
        for row in decoded["matched"]:
            if any(
                row.get(name, "")
                for name in (
                    "original_entry_mean_minutes",
                    "original_entry_p95_seconds",
                    "original_entry_p99_seconds",
                )
            ):
                raise ExperimentError(
                    "unmatched PIBT cohort publishes survivor TTH"
                )

    manifest = _read_json(root / OUTPUT_PATHS["manifest"])
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ExperimentError("contention manifest schema drift")
    canonical_map = manifest.get("canonical_map")
    if not isinstance(canonical_map, Mapping):
        raise ExperimentError("contention manifest lacks canonical map")
    if canonical_map.get("raw_sha256") != CANONICAL_MAP_RAW_SHA256:
        raise ExperimentError("contention manifest map hash drift")
    if canonical_map.get("topology_mutated") is not False:
        raise ExperimentError("contention manifest permits topology mutation")
    protocol = manifest.get("protocol")
    if not isinstance(protocol, Mapping):
        raise ExperimentError("contention manifest lacks protocol")
    expected_matrix_hash = canonical_sha256(
        [asdict(candidate) for candidate in all_candidates()]
    )
    if protocol.get("candidate_matrix_sha256") != expected_matrix_hash:
        raise ExperimentError("contention candidate matrix hash drift")
    if int(protocol.get("maximum_full_finalists", -1)) != MAX_FULL_FINALISTS:
        raise ExperimentError("full finalist limit drift")
    runtime_contract = protocol.get("runtime_contract")
    if not isinstance(runtime_contract, Mapping):
        raise ExperimentError("runtime contract missing")
    expected_contract = {
        "one_next_edge_only": True,
        "reservation_depth": 1,
        "runtime_full_astar_allowed": False,
        "future_route_allowed": False,
        "global_reservation_scan_allowed": False,
    }
    if dict(runtime_contract) != expected_contract:
        raise ExperimentError("runtime contract drift")

    for binding in manifest.get("result_bindings", []):
        if not isinstance(binding, Mapping):
            raise ExperimentError("result binding is not an object")
        for name in (
            "cache_key",
            "result_file_sha256",
            "runtime_deterministic_sha256",
        ):
            digest = str(binding.get(name, ""))
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise ExperimentError(
                    f"executed result binding has invalid {name}"
                )

    return {
        "status": "PASS",
        "table_row_counts": {
            name: len(rows) for name, rows in decoded.items()
        },
        "full_executed_candidate_count": len(full_executed),
        "matched_comparison_eligible": (
            matched_eligible_values == {"True"}
        ),
        "manifest_sha256": file_sha256(root / OUTPUT_PATHS["manifest"]),
    }


def protocol_manifest() -> dict[str, Any]:
    return {
        "schema": PROTOCOL_SCHEMA,
        "adapter_schema": ADAPTER_SCHEMA,
        "fixed_real_map_only": True,
        "canonical_map": {
            "path": MAP_PATH.as_posix(),
            "raw_sha256": CANONICAL_MAP_RAW_SHA256,
            "semantic_sha256": CANONICAL_MAP_SEMANTIC_SHA256,
        },
        "canonical_tasks": {
            "path": TASK_PATH.as_posix(),
            "raw_sha256": CANONICAL_SOURCE_RAW_SHA256,
            "segment_count": FULL_SIZE_SEGMENTS,
            "raw_bag_count": FULL_SIZE_BAGS,
        },
        "tier_order": list(TIER_ORDER),
        "maximum_full_finalists": MAX_FULL_FINALISTS,
        "full_default_authorized": False,
        "candidates": [asdict(candidate) for candidate in all_candidates()],
        "candidate_matrix_sha256": canonical_sha256(
            [asdict(candidate) for candidate in all_candidates()]
        ),
        "control_configs": {
            key: dict(value) for key, value in CONTROL_CONFIGS.items()
        },
        "early_reject": {
            "mean_loss_seconds_per_bag": 1.0,
            "p95_loss_seconds": 2.0,
            "p99_loss_seconds": 4.0,
            "source_network_offset_tolerance_seconds": 0.25,
            "rollback_surge": "greater_of_2x_or_plus_10",
        },
        "outputs": {
            name: path.as_posix() for name, path in OUTPUT_PATHS.items()
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-ladder",
        action="store_true",
        help="Execute admitted C/D tiers through --max-tier.",
    )
    parser.add_argument(
        "--run-contention",
        action="store_true",
        help="Execute the matched real F2 contention cohort.",
    )
    parser.add_argument(
        "--max-tier",
        choices=TIER_ORDER,
        default="512",
        help="Largest requested ladder tier; full also requires --allow-full.",
    )
    parser.add_argument(
        "--allow-full",
        action="store_true",
        help="Explicitly authorize at most four original-1x finalists.",
    )
    parser.add_argument(
        "--binary",
        type=Path,
        help="Exact czr005_cpp binary to bind and execute.",
    )
    parser.add_argument(
        "--search-path",
        type=Path,
        help="Directory containing --binary; defaults to binary parent.",
    )
    parser.add_argument(
        "--archive-root",
        type=Path,
        help="Local append-only attempt archive override.",
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
        help="Validate existing compact outputs without running the runtime.",
    )
    parser.add_argument(
        "--print-protocol",
        action="store_true",
        help="Print the deterministic protocol JSON and exit.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.output_root.resolve()
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
        print(
            json.dumps(
                validate_committed_outputs(root),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0

    ladder_results: list[dict[str, Any]] = []
    contention_results: list[dict[str, Any]] = []
    qbest: str | None = None
    manifest: dict[str, Any]
    try:
        _selection_value, manifest, _prior = (
            load_matched_contention_cohort(root)
        )
    except ExperimentError as exc:
        manifest = {
            "schema": MANIFEST_SCHEMA,
            "status": "PARTIAL_WITH_EXPLICIT_BLOCKER",
            "blocker": str(exc),
            "canonical_map": {
                "path": MAP_PATH.as_posix(),
                "raw_sha256": CANONICAL_MAP_RAW_SHA256,
                "semantic_sha256": CANONICAL_MAP_SEMANTIC_SHA256,
                "topology_mutated": False,
            },
            "matched_gate": {
                "status": "NOT_RUN",
                "matched_comparison_eligible": False,
            },
        }

    if args.run_ladder or args.run_contention:
        if args.binary is None:
            raise SystemExit("--binary is required for runtime execution")
        binary = args.binary.resolve(strict=True)
        search_path = (
            args.search_path.resolve(strict=True)
            if args.search_path
            else binary.parent
        )
        from czr005 import cpp_backend

        executor = cpp_backend.g4irsf11_event_runtime_from_records
        if args.run_ladder:
            ladder_results, qbest = execute_ladder(
                executor=executor,
                binary=binary,
                search_path=search_path,
                max_tier=args.max_tier,
                allow_full=args.allow_full,
                root=root,
                archive_root=args.archive_root,
            )
        if args.run_contention:
            if qbest is None:
                qbest = select_qbest(ladder_results)
            contention_results, manifest = execute_contention_study(
                executor=executor,
                binary=binary,
                search_path=search_path,
                qbest=qbest,
                root=root,
                archive_root=args.archive_root,
            )
    publication = write_outputs(
        ladder_results,
        contention_results,
        manifest,
        qbest=qbest,
        root=root,
    )
    validation = validate_committed_outputs(root)
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
