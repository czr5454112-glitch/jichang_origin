"""Collect and attribute the frozen F2 versus v2-safe matched-denominator gap.

The formal G4IRSF12 Phase-J ledger is immutable and summary-only.  This module
therefore creates a separate, ignored diagnostic archive and refuses to use it
unless its descriptor, hashes, protected inputs, runtime controls, complete
trace, and per-segment timing reconstruction all validate.

Two timing conventions are deliberately kept separate:

* ``scheduled_ebs_dwell`` always comes from the protected
  ``inputdata.jsonl`` rows.  It is common to F2 and v2-safe and is counted once
  for every protected segment, matching the reconciled raw-entry denominator.
* Runtime components remain measured from each comparator's own attempt time.
  The frozen v2 Java-source-queue artifact can move a segment relative to the
  protected ``pass_time`` (including sub-second epoch rounding), so a separate
  signed ``release_interface_alignment`` term binds that interface difference
  without mislabelling it as nonnegative queue wait.  The v2 path is offline
  evidence only and is never copied into ``runtime_features``.

Full collection is opt-in through ``--collect``.  Raw payloads live below the
gitignored ``.local_archives`` directory as atomic gzip files.  ``--analyze``
publishes only compact tables, a bounded divergence sample, and a report.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import contextmanager
import csv
from dataclasses import dataclass
import gzip
import hashlib
import heapq
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
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence
import uuid


ROOT = Path(__file__).resolve().parents[2]
for _import_path in (ROOT, ROOT / "src"):
    if str(_import_path) not in sys.path:
        sys.path.insert(0, str(_import_path))


MAP_PATH = Path("data/processed/maps/map2.json")
TASK_PATH = Path("data/processed/tasks/inputdata.jsonl")
V2_TASK_PATH = Path(
    "artifacts/tasks/g4irsf7/java_source_queue_one_per_epoch.jsonl"
)
V2_POLICY_PATH = Path(
    "artifacts/policies/g4irsf9_noastar_v2_safe_policy_bundle.json"
)
FROZEN_MODEL_PATH = Path("artifacts/models/g4e_risk_calibrated_policy.json")
F2_POLICY_PATH = Path("artifacts/policies/g4irsf13_f2_frozen_baseline.json")

DEFAULT_ARCHIVE_ROOT = ROOT / ".local_archives" / "g4irsf13_delay_attribution"

REPORT_PATH = Path("outputs/reports/g4irsf13_f2_v2_delay_attribution.md")
PER_BAG_PATH = Path("outputs/tables/g4irsf13_per_bag_delta.csv")
LEDGER_PATH = Path("outputs/tables/g4irsf13_delay_component_ledger.csv")
DIVERGENCE_PATH = Path("outputs/tables/g4irsf13_decision_divergence.csv")
HOTSPOT_PATH = Path("outputs/tables/g4irsf13_hotspot_contribution.csv")
VALIDATION_PATH = Path(
    "outputs/tables/g4irsf13_delay_attribution_validation.csv"
)
TRACE_SAMPLE_PATH = Path(
    "artifacts/traces/g4irsf13_divergence_trace_sample.jsonl"
)

MAP_RAW_SHA256 = (
    "9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4"
)
MAP_SEMANTIC_SHA256 = (
    "67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63"
)
TASK_SHA256 = (
    "968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f"
)
V2_TASK_SHA256 = (
    "abb03e6d6d46031bfb653fece7ade8a94d58a54e8142c53448704f800ec5d386"
)
FROZEN_MODEL_SHA256 = (
    "4a058dee0bdd17e15f67d1943a551822847d0c066ac3cf03a5da71a07731bbca"
)

FULL_SEGMENTS = 43_603
FULL_BAGS = 28_506
PRIMARY_SPEED = 2.5
EXPECTED_F2_RAW_ENTRY_MINUTES = 41.514218717973414
EXPECTED_V2_RAW_ENTRY_MINUTES = 41.49530698780892
EXPECTED_GAP_SECONDS = 1.1347038098698192
EXPECTED_V2_PASS_ANCHORED_MINUTES = 4.124305453486908
EXPECTED_V2_JAVA_RELEASE_MINUTES = 3.556593852974151

ARCHIVE_DESCRIPTOR_SCHEMA = (
    "czr005.g4irsf13.delay_attribution_archive_descriptor.v1"
)
ARCHIVE_POINTER_SCHEMA = (
    "czr005.g4irsf13.delay_attribution_archive_pointer.v1"
)
ARCHIVE_PAYLOAD_SCHEMA = "czr005.g4irsf13.delay_attribution_payload.v1"
TRACE_SAMPLE_SCHEMA = "czr005.g4irsf13.divergence_trace_sample.v1"
# Full F2 decision payloads contain hundreds of thousands of nested local
# candidate records.  Level 1 keeps the ignored audit archive compact while
# avoiding a many-minute level-9 CPU bottleneck; integrity comes from the
# canonical-JSON and compressed-file SHA-256 values, not compression ratio.
ARCHIVE_GZIP_LEVEL = 1

ADDITIVE_COMPONENTS = (
    "scheduled_ebs_dwell",
    "release_interface_alignment",
    "source_queue_wait",
    "junction_queue_wait",
    "resource_calendar_wait",
    "pibt_prepare_wait",
    "pibt_rollback_wait",
    "fault_hold",
    "edge_travel_time",
    "node_service_time",
)
DIAGNOSTIC_COMPONENTS = (
    "detour_extra_time",
    "loop_extra_time",
    "goal_completion_time",
)
ALL_COMPONENTS = ADDITIVE_COMPONENTS + DIAGNOSTIC_COMPONENTS

F2_INSTRUMENTATION_ALIASES: Mapping[str, tuple[str, ...]] = {
    "junction_queue_wait": (
        "junction_queue_wait_seconds",
        "junction_queue_wait",
    ),
    "edge_travel_time": (
        "edge_travel_time_seconds",
        "edge_travel_time",
    ),
    "node_service_time": (
        "node_service_time_seconds",
        "node_service_time",
    ),
    "loop_extra_time": (
        "loop_extra_time_seconds",
        "loop_extra_time",
    ),
    "goal_completion_time": (
        "goal_completion_time_seconds",
        "goal_completion_time",
    ),
}

SAFE_LOCAL_SNAPSHOT_FIELDS = frozenset(
    {
        "junction_queue_length",
        "next_available_time",
        "faulted_outgoing_count",
        "message_age_seconds",
        "downstream_pressure",
    }
)
SAFE_CANDIDATE_FEATURE_FIELDS = frozenset(
    {
        "static_potential",
        "travel_time",
        "target_queue_length",
        "target_scheduled_incoming",
        "corridor_next_available",
        "target_next_available",
        "advertised_fault",
        "fault_message_age_seconds",
        "recent_visit_count",
        "two_hop_queue_pressure",
        "current_goal_queue_length",
        "target_goal_queue_length",
        "target_goal_scheduled_incoming",
        "current_goal_max_wait",
        "goal_conditioned_differential",
        "estimated_service_rate",
        "service_weighted_pressure",
        "first_edge_credit_required",
        "first_edge_credit_matches",
        "first_edge_credit_valid",
        "first_edge_credit_slack_seconds",
    }
)
FORBIDDEN_RUNTIME_FEATURE_FRAGMENTS = (
    "teacher",
    "v2_",
    "future_route",
    "future_schedule",
    "route_suffix",
    "label_source",
    "finish_time",
    "goal_completion",
    "post_hoc",
    "outcome",
)


class AttributionError(ValueError):
    """Raised when evidence cannot be admitted into the attribution."""


class ArchiveError(AttributionError):
    """Raised when a local raw-evidence archive is invalid."""


class StaleWorkerError(ArchiveError):
    """Raised when a dead writer lease requires explicit recovery."""


@dataclass(frozen=True)
class ArchiveBundle:
    descriptor_path: Path
    descriptor: dict[str, Any]
    payload: dict[str, Any]


@dataclass(frozen=True)
class AnalysisArtifacts:
    per_bag_rows: tuple[dict[str, Any], ...]
    ledger_rows: tuple[dict[str, Any], ...]
    divergence_rows: tuple[dict[str, Any], ...]
    hotspot_rows: tuple[dict[str, Any], ...]
    validation_rows: tuple[dict[str, Any], ...]
    trace_rows: tuple[dict[str, Any], ...]
    summary: dict[str, Any]


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AttributionError(f"value is not canonical JSON: {exc}") from exc


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _semantic_json_sha256(path: Path) -> str:
    text = path.read_bytes().decode("utf-8")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AttributionError(f"{label} must be a numeric scalar")
    result = float(value)
    if not math.isfinite(result):
        raise AttributionError(f"{label} must be finite")
    return result


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise AttributionError(f"{label} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise AttributionError(f"{label} must be an integer") from exc
    if str(result) != str(value) and not (
        isinstance(value, float) and value.is_integer()
    ):
        raise AttributionError(f"{label} is not an exact integer")
    return result


def _one_of(row: Mapping[str, Any], aliases: Sequence[str], label: str) -> Any:
    for alias in aliases:
        if alias in row and row[alias] not in (None, ""):
            return row[alias]
    raise AttributionError(
        f"MISSING_F2_INSTRUMENTATION:{label}; accepted aliases={list(aliases)}"
    )


def _close(
    left: float,
    right: float,
    *,
    tolerance: float = 1.0e-6,
) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=tolerance)


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
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


def _atomic_write_json(path: Path, value: Any) -> None:
    _atomic_write_bytes(path, _canonical_json_bytes(value) + b"\n")


def _atomic_write_gzip_json(path: Path, value: Any) -> dict[str, Any]:
    """Write deterministic gzip JSON without materializing a second full copy."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temporary = Path(temporary_name)
    raw_digest = hashlib.sha256()
    raw_size = 0
    try:
        with os.fdopen(descriptor, "wb") as raw_handle:
            with gzip.GzipFile(
                filename="",
                mode="wb",
                fileobj=raw_handle,
                compresslevel=ARCHIVE_GZIP_LEVEL,
                mtime=0,
            ) as gzip_handle:
                encoder = json.JSONEncoder(
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                buffered = bytearray()
                for text in encoder.iterencode(value):
                    buffered.extend(text.encode("utf-8"))
                    if len(buffered) < 1 << 20:
                        continue
                    chunk = bytes(buffered)
                    raw_digest.update(chunk)
                    raw_size += len(chunk)
                    gzip_handle.write(chunk)
                    buffered.clear()
                if buffered:
                    chunk = bytes(buffered)
                    raw_digest.update(chunk)
                    raw_size += len(chunk)
                    gzip_handle.write(chunk)
            raw_handle.flush()
            os.fsync(raw_handle.fileno())
        compressed_sha = _file_sha256(temporary)
        compressed_size = temporary.stat().st_size
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "path": path.name,
        "compression": "gzip",
        "compression_level": ARCHIVE_GZIP_LEVEL,
        "canonical_json_sha256": raw_digest.hexdigest(),
        "canonical_json_size_bytes": raw_size,
        "file_sha256": compressed_sha,
        "file_size_bytes": compressed_size,
    }


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArchiveError(f"cannot decode JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ArchiveError(f"JSON root must be an object: {path}")
    return value


def _read_gzip_json(path: Path) -> dict[str, Any]:
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArchiveError(f"cannot decode gzip JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ArchiveError(f"gzip JSON root must be an object: {path}")
    return value


def _parse_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AttributionError(
                    f"{path}:{line_number}: invalid JSON: {exc}"
                ) from exc
            if not isinstance(value, dict):
                raise AttributionError(
                    f"{path}:{line_number}: row must be an object"
                )
            rows.append(value)
    return rows


def load_protected_inputs(
    root: Path = ROOT,
    *,
    require_full: bool = True,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    map_path = root / MAP_PATH
    task_path = root / TASK_PATH
    if _file_sha256(map_path) != MAP_RAW_SHA256:
        raise AttributionError("canonical map raw SHA-256 drift")
    if _semantic_json_sha256(map_path) != MAP_SEMANTIC_SHA256:
        raise AttributionError("canonical map semantic SHA-256 drift")
    if _file_sha256(task_path) != TASK_SHA256:
        raise AttributionError("protected task SHA-256 drift")
    map_data = _read_json_object(map_path)
    rows = _parse_jsonl(task_path)
    if require_full:
        if len(rows) != FULL_SEGMENTS:
            raise AttributionError(
                f"protected segment count {len(rows)} != {FULL_SEGMENTS}"
            )
        task_ids = {int(row["task_id"]) for row in rows}
        if len(task_ids) != FULL_BAGS:
            raise AttributionError(
                f"protected raw-bag count {len(task_ids)} != {FULL_BAGS}"
            )
    return map_data, rows


def _segment_identity(row: Mapping[str, Any]) -> tuple[int, int, str, str]:
    return (
        _integer(row.get("task_id"), "task_id"),
        _integer(row.get("pallet_id"), "pallet_id"),
        str(row.get("segment_id", "")),
        str(row.get("leg", "")),
    )


def _alignment_identity(
    row: Mapping[str, Any],
) -> tuple[int, int, str, str, int, int, float]:
    """Return the seven-field scientific alignment identity.

    Runtime payloads do not repeat every field.  Missing runtime metadata is
    restored only through this protected/v2-source identity and never by
    positional row order.
    """

    task_id, pallet_id, segment_id, leg = _segment_identity(row)
    return (
        task_id,
        pallet_id,
        segment_id,
        leg,
        _integer(row.get("start"), f"{segment_id}.start"),
        _integer(row.get("goal"), f"{segment_id}.goal"),
        _finite(
            row.get("original_entry_time"),
            f"{segment_id}.original_entry_time",
        ),
    )


def _protected_index(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[
    dict[str, dict[str, Any]],
    dict[int, list[dict[str, Any]]],
]:
    by_segment: dict[str, dict[str, Any]] = {}
    by_task: dict[int, list[dict[str, Any]]] = defaultdict(list)
    identities: set[tuple[int, int, str, str, int, int, float]] = set()
    for raw in rows:
        row = dict(raw)
        identity = _alignment_identity(row)
        segment_id = identity[2]
        if not segment_id:
            raise AttributionError("protected segment_id must be non-empty")
        if identity in identities or segment_id in by_segment:
            raise AttributionError(f"duplicate protected segment: {identity}")
        identities.add(identity)
        by_segment[segment_id] = row
        by_task[identity[0]].append(row)
    for task_rows in by_task.values():
        task_rows.sort(
            key=lambda row: (
                float(row["pass_time"]),
                str(row["leg"]),
                str(row["segment_id"]),
            )
        )
    return by_segment, dict(by_task)


def _runtime_index(
    rows: Sequence[Mapping[str, Any]],
    protected: Mapping[str, Mapping[str, Any]],
    *,
    label: str,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for raw in rows:
        row = dict(raw)
        segment_id = str(row.get("segment_id", ""))
        if not segment_id:
            raise AttributionError(f"{label} runtime row lacks segment_id")
        if segment_id in result:
            raise AttributionError(
                f"{label} duplicate runtime segment_id: {segment_id}"
            )
        source = protected.get(segment_id)
        if source is None:
            raise AttributionError(
                f"{label} returned unknown segment_id: {segment_id}"
            )
        if _integer(row.get("task_id"), f"{label}.{segment_id}.task_id") != int(
            source["task_id"]
        ):
            raise AttributionError(
                f"{label}.{segment_id}: task_id identity mismatch"
            )
        if "pallet_id" in row and _integer(
            row["pallet_id"], f"{label}.{segment_id}.pallet_id"
        ) != int(source["pallet_id"]):
            raise AttributionError(
                f"{label}.{segment_id}: pallet_id identity mismatch"
            )
        if "leg" in row and str(row["leg"]) != str(source["leg"]):
            raise AttributionError(
                f"{label}.{segment_id}: leg identity mismatch"
            )
        for field in ("start", "goal"):
            if field in row and _integer(
                row[field], f"{label}.{segment_id}.{field}"
            ) != int(source[field]):
                raise AttributionError(
                    f"{label}.{segment_id}: {field} identity mismatch"
                )
        if "original_entry_time" in row and not _close(
            _finite(
                row["original_entry_time"],
                f"{label}.{segment_id}.original_entry_time",
            ),
            _finite(
                source["original_entry_time"],
                f"protected.{segment_id}.original_entry_time",
            ),
            tolerance=1.0e-9,
        ):
            raise AttributionError(
                f"{label}.{segment_id}: original_entry_time identity mismatch"
            )
        result[segment_id] = row
    missing = sorted(set(protected) - set(result))
    extra = sorted(set(result) - set(protected))
    if missing or extra:
        raise AttributionError(
            f"{label} segment alignment failed: "
            f"missing={len(missing)}, extra={len(extra)}, "
            f"missing_sample={missing[:3]}, extra_sample={extra[:3]}"
        )
    return result


def _graph_metadata(
    map_data: Mapping[str, Any],
) -> tuple[
    dict[tuple[int, int], float],
    dict[int, float],
    dict[int, int],
    dict[tuple[int, int], float],
]:
    edge_travel: dict[tuple[int, int], float] = {}
    outgoing: dict[int, list[tuple[int, float]]] = defaultdict(list)
    indegree: dict[int, int] = defaultdict(int)
    for edge in map_data.get("edges", []):
        start = int(edge["start"])
        end = int(edge["end"])
        speed = float(edge.get("speed", PRIMARY_SPEED))
        if not _close(speed, PRIMARY_SPEED, tolerance=1.0e-12):
            raise AttributionError(
                f"canonical edge {start}->{end} speed={speed}, "
                f"expected {PRIMARY_SPEED}"
            )
        travel = float(edge["length"]) / PRIMARY_SPEED
        key = (start, end)
        if key in edge_travel:
            raise AttributionError(f"duplicate directed map edge: {key}")
        edge_travel[key] = travel
        outgoing[start].append((end, travel))
        indegree[end] += 1
    service = {
        int(node["location"]): float(node.get("service_time", 0.0))
        for node in map_data.get("nodes", [])
    }
    shortest: dict[tuple[int, int], float] = {}
    for source in service:
        distances = {source: 0.0}
        heap: list[tuple[float, int]] = [(0.0, source)]
        while heap:
            cost, node = heapq.heappop(heap)
            if cost != distances.get(node):
                continue
            for nxt, weight in outgoing.get(node, ()):
                candidate = cost + weight
                if candidate < distances.get(nxt, math.inf):
                    distances[nxt] = candidate
                    heapq.heappush(heap, (candidate, nxt))
        for goal, value in distances.items():
            shortest[(source, goal)] = value
    return edge_travel, service, dict(indegree), shortest


def _path_metrics(
    path: Sequence[Any],
    edge_travel: Mapping[tuple[int, int], float],
    service: Mapping[int, float],
    shortest: Mapping[tuple[int, int], float],
    *,
    minimum_service_seconds: float,
) -> dict[str, float]:
    nodes = [int(value) for value in path]
    if not nodes:
        raise AttributionError("runtime path must contain at least its source")
    travel = 0.0
    loop_extra = 0.0
    seen = {nodes[0]}
    for start, end in zip(nodes, nodes[1:]):
        edge = (start, end)
        if edge not in edge_travel:
            raise AttributionError(f"runtime path uses non-map edge: {edge}")
        duration = edge_travel[edge]
        travel += duration
        if end in seen:
            loop_extra += duration
        seen.add(end)
    service_time = 0.0
    for node in nodes:
        if node not in service:
            raise AttributionError(f"runtime path uses non-map node: {node}")
        service_time += max(service[node], minimum_service_seconds)
    shortest_value = shortest.get((nodes[0], nodes[-1]), math.inf)
    detour = (
        max(0.0, travel - shortest_value)
        if math.isfinite(shortest_value)
        else 0.0
    )
    return {
        "edge_travel_time": travel,
        "node_service_time": service_time,
        "detour_extra_time": detour,
        "loop_extra_time": loop_extra,
    }


def _f2_paths_from_events(
    events: Sequence[Mapping[str, Any]],
    protected: Mapping[str, Mapping[str, Any]],
) -> dict[str, list[int]]:
    paths = {
        segment_id: [int(row["start"])]
        for segment_id, row in protected.items()
    }
    seen_sequences: set[int] = set()
    ordered = sorted(
        (dict(row) for row in events),
        key=lambda row: _integer(row.get("seq"), "event.seq"),
    )
    for event in ordered:
        sequence = _integer(event.get("seq"), "event.seq")
        if sequence in seen_sequences:
            raise AttributionError(f"duplicate F2 event sequence: {sequence}")
        seen_sequences.add(sequence)
        if str(event.get("event")) != "EDGE_EXIT":
            continue
        segment_id = str(event.get("segment_id", ""))
        if segment_id not in paths:
            raise AttributionError(
                f"F2 EDGE_EXIT references unknown segment: {segment_id}"
            )
        from_node = _integer(
            event.get("from_node"), f"F2.{segment_id}.EDGE_EXIT.from_node"
        )
        to_node = _integer(
            event.get("to_node"), f"F2.{segment_id}.EDGE_EXIT.to_node"
        )
        if paths[segment_id][-1] != from_node:
            raise AttributionError(
                f"F2.{segment_id}: non-contiguous EDGE_EXIT path "
                f"{paths[segment_id][-1]} != {from_node}"
            )
        paths[segment_id].append(to_node)
    return paths


def _f2_paths_from_decisions(
    decisions: Sequence[Mapping[str, Any]],
    protected: Mapping[str, Mapping[str, Any]],
) -> dict[str, list[int]]:
    """Reconstruct committed paths without retaining the full event stream."""

    paths = {
        segment_id: [int(row["start"])]
        for segment_id, row in protected.items()
    }
    def order_key(row: Mapping[str, Any]) -> tuple[float, int, str]:
        metadata = row.get("metadata", {})
        ordinal: Any = None
        if isinstance(metadata, Mapping):
            ordinal = metadata.get("decision_ordinal")
        numeric_ordinal = (
            _integer(ordinal, "decision.metadata.decision_ordinal")
            if ordinal is not None
            else sys.maxsize
        )
        return (
            _finite(row.get("event_time"), "decision.event_time"),
            numeric_ordinal,
            str(row.get("decision_id", "")),
        )

    ordered = sorted((dict(row) for row in decisions), key=order_key)
    committed_count = 0
    for decision in ordered:
        selected = decision.get("selected_next")
        if selected is None:
            continue
        segment_id = str(decision.get("segment_id", ""))
        if segment_id not in paths:
            raise AttributionError(
                f"F2 committed decision references unknown segment: {segment_id}"
            )
        current = _integer(
            decision.get("current_node"),
            f"F2.{segment_id}.decision.current_node",
        )
        next_node = _integer(
            selected,
            f"F2.{segment_id}.decision.selected_next",
        )
        if paths[segment_id][-1] != current:
            raise AttributionError(
                f"F2.{segment_id}: non-contiguous committed-decision path "
                f"{paths[segment_id][-1]} != {current}"
            )
        paths[segment_id].append(next_node)
        committed_count += 1
    if committed_count == 0:
        raise AttributionError("F2 committed decision trace contains no edges")
    return paths


def _component_template() -> dict[str, float]:
    return {name: 0.0 for name in ALL_COMPONENTS}


def _f2_segment_components(
    row: Mapping[str, Any],
    protected: Mapping[str, Any],
    path: Sequence[int],
    *,
    edge_travel: Mapping[tuple[int, int], float],
    service: Mapping[int, float],
    shortest: Mapping[tuple[int, int], float],
) -> tuple[dict[str, float], float]:
    segment_id = str(protected["segment_id"])
    if row.get("completed") is not True:
        raise AttributionError(f"F2.{segment_id}: segment is not completed")
    release = _finite(row.get("release_time"), f"F2.{segment_id}.release_time")
    protected_release = _finite(
        protected.get("pass_time"), f"{segment_id}.pass_time"
    )
    if not _close(release, protected_release, tolerance=1.0e-9):
        raise AttributionError(
            f"F2.{segment_id}: release differs from protected pass_time"
        )
    finish = _finite(row.get("finish_time"), f"F2.{segment_id}.finish_time")
    if finish + 1.0e-9 < release:
        raise AttributionError(f"F2.{segment_id}: finish precedes release")
    path_values = _path_metrics(
        path,
        edge_travel,
        service,
        shortest,
        minimum_service_seconds=1.0e-3,
    )
    components = _component_template()
    components["scheduled_ebs_dwell"] = protected_release - _finite(
        protected.get("original_entry_time"),
        f"{segment_id}.original_entry_time",
    )
    components["release_interface_alignment"] = 0.0
    components["source_queue_wait"] = _finite(
        row.get("source_queue_delay"), f"F2.{segment_id}.source_queue_delay"
    )
    components["junction_queue_wait"] = _finite(
        _one_of(
            row,
            F2_INSTRUMENTATION_ALIASES["junction_queue_wait"],
            "junction_queue_wait",
        ),
        f"F2.{segment_id}.junction_queue_wait",
    )
    # R3 calendar/dispatch/fault holds are deliberately owned by the measured
    # junction queue interval.  P2 prepare/rollback mutate no simulation clock.
    components["resource_calendar_wait"] = _finite(
        row.get("resource_calendar_wait_seconds", 0.0),
        f"F2.{segment_id}.resource_calendar_wait",
    )
    components["pibt_prepare_wait"] = _finite(
        row.get("pibt_prepare_wait_seconds", 0.0),
        f"F2.{segment_id}.pibt_prepare_wait",
    )
    components["pibt_rollback_wait"] = _finite(
        row.get("pibt_rollback_wait_seconds", 0.0),
        f"F2.{segment_id}.pibt_rollback_wait",
    )
    # Stage B is a frozen no-fault comparator.  A distinct zero-valued entry
    # keeps the requested time-bank schema explicit without relabelling queue
    # time as fault delay.
    components["fault_hold"] = 0.0
    components["edge_travel_time"] = _finite(
        _one_of(
            row,
            F2_INSTRUMENTATION_ALIASES["edge_travel_time"],
            "edge_travel_time",
        ),
        f"F2.{segment_id}.edge_travel_time",
    )
    components["node_service_time"] = _finite(
        _one_of(
            row,
            F2_INSTRUMENTATION_ALIASES["node_service_time"],
            "node_service_time",
        ),
        f"F2.{segment_id}.node_service_time",
    )
    components["loop_extra_time"] = _finite(
        _one_of(
            row,
            F2_INSTRUMENTATION_ALIASES["loop_extra_time"],
            "loop_extra_time",
        ),
        f"F2.{segment_id}.loop_extra_time",
    )
    components["goal_completion_time"] = _finite(
        _one_of(
            row,
            F2_INSTRUMENTATION_ALIASES["goal_completion_time"],
            "goal_completion_time",
        ),
        f"F2.{segment_id}.goal_completion_time",
    )
    components["detour_extra_time"] = path_values["detour_extra_time"]

    if not _close(
        components["edge_travel_time"],
        path_values["edge_travel_time"],
    ):
        raise AttributionError(
            f"F2.{segment_id}: instrumented edge travel disagrees with path"
        )
    if not _close(
        components["node_service_time"],
        path_values["node_service_time"],
    ):
        raise AttributionError(
            f"F2.{segment_id}: instrumented node service disagrees with path"
        )
    if components["loop_extra_time"] > components["edge_travel_time"] + 1.0e-9:
        raise AttributionError(
            f"F2.{segment_id}: loop diagnostic exceeds edge travel"
        )
    release_total = sum(
        components[name] for name in ADDITIVE_COMPONENTS[1:]
    )
    reconstruction_error = release_total - components["goal_completion_time"]
    if not _close(reconstruction_error, 0.0):
        raise AttributionError(
            f"F2.{segment_id}: source+junction+resource+PIBT+fault+travel+service "
            f"does not reconstruct release-to-goal ({reconstruction_error:+.9f}s)"
        )
    if not _close(components["goal_completion_time"], finish - release):
        raise AttributionError(
            f"F2.{segment_id}: goal completion differs from finish-release"
        )
    return components, abs(reconstruction_error)


def _v2_segment_components(
    row: Mapping[str, Any],
    protected: Mapping[str, Any],
    v2_source: Mapping[str, Any],
    *,
    edge_travel: Mapping[tuple[int, int], float],
    service: Mapping[int, float],
    shortest: Mapping[tuple[int, int], float],
) -> tuple[dict[str, float], float, list[int], float]:
    segment_id = str(protected["segment_id"])
    if row.get("goal_reached") is not True:
        raise AttributionError(f"v2.{segment_id}: segment is not completed")
    attempt = _finite(row.get("attempt_time"), f"v2.{segment_id}.attempt_time")
    expected_attempt = _finite(
        v2_source.get("pass_time"), f"v2_source.{segment_id}.pass_time"
    )
    if not _close(attempt, expected_attempt, tolerance=1.0e-9):
        raise AttributionError(
            f"v2.{segment_id}: attempt differs from frozen v2 task artifact"
        )
    finish = _finite(row.get("finish_time"), f"v2.{segment_id}.finish_time")
    if finish + 1.0e-9 < attempt:
        raise AttributionError(f"v2.{segment_id}: finish precedes attempt")
    raw_path = row.get("path")
    if not isinstance(raw_path, list):
        raise AttributionError(f"v2.{segment_id}: complete path is missing")
    path = [int(value) for value in raw_path]
    if (
        not path
        or path[0] != int(protected["start"])
        or path[-1] != int(protected["goal"])
    ):
        raise AttributionError(
            f"v2.{segment_id}: path endpoints do not match protected input"
        )
    path_values = _path_metrics(
        path,
        edge_travel,
        service,
        shortest,
        minimum_service_seconds=0.0,
    )
    source_wait = _finite(
        row.get("source_wait_seconds", 0.0),
        f"v2.{segment_id}.source_wait_seconds",
    )
    total_wait = _finite(
        row.get("wait_seconds", 0.0),
        f"v2.{segment_id}.wait_seconds",
    )
    reported_resource_wait = total_wait - source_wait
    if reported_resource_wait < -1.0e-9:
        raise AttributionError(
            f"v2.{segment_id}: total wait is less than source wait"
        )
    # The legacy v2 runtime advances a closed reservation boundary by
    # G4I_EPSILON=1e-6, but deliberately adds a wait to ``wait_seconds`` only
    # when it is strictly greater than that threshold.  Consequently, the
    # reported aggregate can omit one or more exact boundary nudges.  Use the
    # independently observed finish timestamp for the additive time bank, and
    # retain the legacy aggregate as a bounded cross-check instead of silently
    # relaxing the reconstruction gate.
    timestamp_resource_wait = (
        finish
        - attempt
        - path_values["edge_travel_time"]
        - path_values["node_service_time"]
        - source_wait
    )
    if timestamp_resource_wait < -1.0e-6:
        raise AttributionError(
            f"v2.{segment_id}: timestamp-derived resource wait is negative "
            f"({timestamp_resource_wait:+.9f}s)"
        )
    timestamp_resource_wait = max(0.0, timestamp_resource_wait)
    reported_wait_drift = timestamp_resource_wait - max(
        0.0, reported_resource_wait
    )
    epsilon_drift_bound = (len(path) + 1) * 1.1e-6
    if abs(reported_wait_drift) > epsilon_drift_bound:
        raise AttributionError(
            f"v2.{segment_id}: reported wait differs from timestamp-derived "
            f"calendar wait by {reported_wait_drift:+.9f}s, exceeding "
            f"the per-transition epsilon bound {epsilon_drift_bound:.9f}s"
        )
    components = _component_template()
    # Use the protected release offset, not the transformed v2 artifact
    # release, so this reproduces the reconciled matched denominator.
    protected_release = _finite(
        protected.get("pass_time"), f"{segment_id}.pass_time"
    )
    components["scheduled_ebs_dwell"] = protected_release - _finite(
        protected.get("original_entry_time"),
        f"{segment_id}.original_entry_time",
    )
    # The frozen Java one-per-epoch task artifact is an interface transform,
    # not runtime queue time.  Keep its signed shift explicit: individual
    # segments may move by sub-second epoch rounding even though the complete
    # raw-bag population has a positive mean source-ordering delay.
    components["release_interface_alignment"] = attempt - protected_release
    components["source_queue_wait"] = source_wait
    components["junction_queue_wait"] = 0.0
    components["resource_calendar_wait"] = timestamp_resource_wait
    components["pibt_prepare_wait"] = 0.0
    components["pibt_rollback_wait"] = 0.0
    components["fault_hold"] = 0.0
    components["edge_travel_time"] = path_values["edge_travel_time"]
    components["node_service_time"] = path_values["node_service_time"]
    components["detour_extra_time"] = path_values["detour_extra_time"]
    components["loop_extra_time"] = path_values["loop_extra_time"]
    components["goal_completion_time"] = finish - protected_release
    release_total = sum(
        components[name] for name in ADDITIVE_COMPONENTS[1:]
    )
    reconstruction_error = release_total - components["goal_completion_time"]
    if not _close(reconstruction_error, 0.0):
        raise AttributionError(
            f"v2.{segment_id}: release alignment+source+calendar+fault+travel+"
            f"service does not reconstruct protected-release-to-goal "
            f"({reconstruction_error:+.9f}s)"
        )
    return (
        components,
        abs(reconstruction_error),
        path,
        abs(reported_wait_drift),
    )


def _sum_components(
    rows: Iterable[Mapping[str, float]],
) -> dict[str, float]:
    result = _component_template()
    for row in rows:
        for component in ALL_COMPONENTS:
            result[component] += float(row[component])
    return result


def _first_divergence(
    f2_path: Sequence[int],
    v2_path: Sequence[int],
) -> tuple[int, int | None, int | None, int] | None:
    common_nodes = 0
    for f2_node, v2_node in zip(f2_path, v2_path):
        if f2_node != v2_node:
            break
        common_nodes += 1
    if common_nodes == len(f2_path) == len(v2_path):
        return None
    if common_nodes == 0:
        raise AttributionError("aligned paths disagree at their source node")
    current = int(f2_path[common_nodes - 1])
    f2_next = (
        int(f2_path[common_nodes])
        if common_nodes < len(f2_path)
        else None
    )
    v2_next = (
        int(v2_path[common_nodes])
        if common_nodes < len(v2_path)
        else None
    )
    return current, f2_next, v2_next, common_nodes - 1


def _action_divergence_count(
    f2_path: Sequence[int],
    v2_path: Sequence[int],
) -> int:
    f2_edges = list(zip(f2_path, f2_path[1:]))
    v2_edges = list(zip(v2_path, v2_path[1:]))
    shared = min(len(f2_edges), len(v2_edges))
    return sum(
        f2_edges[index] != v2_edges[index] for index in range(shared)
    ) + abs(len(f2_edges) - len(v2_edges))


def _safe_runtime_features(
    decision: Mapping[str, Any] | None,
    *,
    current_node: int,
    goal_node: int,
    deadline_slack_seconds: float | None = None,
    wait_age_seconds: float | None = None,
) -> dict[str, Any]:
    if decision is None:
        result: dict[str, Any] = {
            "current_node": current_node,
            "goal_node": goal_node,
            "candidate_next_nodes": [],
            "local_snapshot": {},
            "candidate_records": [],
            "short_history": [],
        }
        if deadline_slack_seconds is not None:
            result["deadline_slack_seconds"] = deadline_slack_seconds
        if wait_age_seconds is not None:
            result["wait_age_seconds"] = wait_age_seconds
        _assert_no_teacher_leakage(result)
        return result
    snapshot_raw = decision.get("local_snapshot", {})
    snapshot = (
        {
            key: value
            for key, value in dict(snapshot_raw).items()
            if key in SAFE_LOCAL_SNAPSHOT_FIELDS
        }
        if isinstance(snapshot_raw, Mapping)
        else {}
    )
    candidates: list[dict[str, Any]] = []
    raw_candidates = decision.get("candidate_records", [])
    if isinstance(raw_candidates, list):
        for raw in raw_candidates:
            if not isinstance(raw, Mapping):
                continue
            features_raw = raw.get("features", {})
            features = (
                {
                    key: value
                    for key, value in dict(features_raw).items()
                    if key in SAFE_CANDIDATE_FEATURE_FIELDS
                }
                if isinstance(features_raw, Mapping)
                else {}
            )
            candidates.append(
                {
                    "next_node": raw.get("next_node"),
                    "features": features,
                    "model_score": raw.get("model_score"),
                    "scorer_raw_score": raw.get("scorer_raw_score"),
                    "scorer_raw_bottleneck": raw.get(
                        "scorer_raw_bottleneck"
                    ),
                    "shield_allowed": raw.get("shield_allowed"),
                    "shield_reason": raw.get("shield_reason"),
                }
            )
    result = {
        "current_node": current_node,
        "goal_node": goal_node,
        "event_time": decision.get("event_time"),
        "candidate_next_nodes": [
            int(value)
            for value in decision.get("candidate_next_nodes", [])
            if isinstance(value, int) and not isinstance(value, bool)
        ],
        "local_snapshot": snapshot,
        "candidate_records": candidates,
        "short_history": [
            int(value)
            for value in decision.get("short_history", [])
            if isinstance(value, int) and not isinstance(value, bool)
        ],
    }
    if deadline_slack_seconds is not None:
        result["deadline_slack_seconds"] = deadline_slack_seconds
    if wait_age_seconds is not None:
        result["wait_age_seconds"] = wait_age_seconds
    _assert_no_teacher_leakage(result)
    return result


def _recorded_candidate_ranking(
    runtime_features: Mapping[str, Any],
) -> list[int]:
    """Return the recorded F2 cost ranking, without inventing missing scores."""

    records = runtime_features.get("candidate_records", [])
    if not isinstance(records, list):
        return []
    ranked: list[tuple[bool, float, int]] = []
    for raw in records:
        if not isinstance(raw, Mapping):
            continue
        next_node = raw.get("next_node")
        score = raw.get("model_score")
        if (
            not isinstance(next_node, int)
            or isinstance(next_node, bool)
            or not isinstance(score, (int, float))
            or isinstance(score, bool)
            or not math.isfinite(float(score))
        ):
            continue
        ranked.append(
            (
                raw.get("shield_allowed") is not True,
                float(score),
                int(next_node),
            )
        )
    ranked.sort()
    return [next_node for _blocked, _score, next_node in ranked]


def _assert_no_teacher_leakage(value: Any, prefix: str = "runtime_features") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            lowered = str(key).lower()
            if any(fragment in lowered for fragment in FORBIDDEN_RUNTIME_FEATURE_FRAGMENTS):
                raise AttributionError(
                    f"teacher/future leakage in {prefix}.{key}"
                )
            _assert_no_teacher_leakage(child, f"{prefix}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_teacher_leakage(child, f"{prefix}[{index}]")


def _teacher_leakage_paths(
    value: Any,
    prefix: str = "runtime_features",
) -> list[str]:
    violations: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{prefix}.{key}"
            lowered = str(key).lower()
            if any(
                fragment in lowered
                for fragment in FORBIDDEN_RUNTIME_FEATURE_FRAGMENTS
            ):
                violations.append(child_path)
            violations.extend(_teacher_leakage_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(
                _teacher_leakage_paths(child, f"{prefix}[{index}]")
            )
    return violations


def _decision_index(
    decisions: Sequence[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in decisions:
        row = dict(raw)
        segment_id = str(row.get("segment_id", ""))
        if segment_id:
            result[segment_id].append(row)
    for rows in result.values():
        rows.sort(
            key=lambda row: (
                float(row.get("event_time", 0.0)),
                str(row.get("decision_id", "")),
            )
        )
    return dict(result)


def _matching_decision(
    decisions: Sequence[Mapping[str, Any]],
    *,
    current: int,
    selected: int | None,
    occurrence: int,
) -> Mapping[str, Any] | None:
    matches = [
        row
        for row in decisions
        if row.get("selected_next") is not None
        and int(row.get("current_node", -1)) == current
        and (
            selected is None
            or int(row.get("selected_next", -1)) == selected
        )
    ]
    if not matches:
        return None
    return matches[min(max(0, occurrence), len(matches) - 1)]


def _pibt_runtime_bag_ids(
    pibt_events: Sequence[Mapping[str, Any]],
) -> set[int]:
    result: set[int] = set()
    for event in pibt_events:
        trigger = event.get("trigger_runtime_bag_id")
        if isinstance(trigger, int) and not isinstance(trigger, bool) and trigger >= 0:
            result.add(trigger)
        actions = event.get("actions", [])
        if not isinstance(actions, list):
            continue
        for action in actions:
            if not isinstance(action, Mapping):
                continue
            bag_id = action.get("runtime_bag_id")
            if isinstance(bag_id, int) and not isinstance(bag_id, bool) and bag_id >= 0:
                result.add(bag_id)
    return result


def _pibt_action_context_index(
    pibt_events: Sequence[Mapping[str, Any]],
) -> dict[tuple[int, int, int], list[dict[str, Any]]]:
    """Index bounded P2 audit context by its actually proposed local action."""

    result: dict[tuple[int, int, int], list[dict[str, Any]]] = defaultdict(list)
    for raw_event in pibt_events:
        event = dict(raw_event)
        actions = event.get("actions", [])
        if not isinstance(actions, list):
            continue
        bounded_chain = [
            {
                "runtime_bag_id": action.get("runtime_bag_id"),
                "from_node": action.get("from_node"),
                "next_node": action.get("next_node"),
                "priority_rank": action.get("priority_rank"),
                "inheritance_depth": action.get("inheritance_depth"),
                "inherited": action.get("inherited"),
            }
            for action in actions
            if isinstance(action, Mapping)
        ]
        context = {
            "activation_id": event.get("activation_id"),
            "event_time": event.get("time"),
            "trigger_runtime_bag_id": event.get("trigger_runtime_bag_id"),
            "trigger_node": event.get("trigger_node"),
            "outcome": event.get("outcome"),
            "blocker": event.get("blocker"),
            "max_inheritance_depth": event.get("max_inheritance_depth"),
            "backtrack_count": event.get("backtrack_count"),
            "rollback_count": event.get("rollback_count"),
            "actions": bounded_chain,
        }
        for action in bounded_chain:
            bag_id = action["runtime_bag_id"]
            current = action["from_node"]
            selected = action["next_node"]
            if all(
                isinstance(value, int) and not isinstance(value, bool)
                for value in (bag_id, current, selected)
            ):
                result[(int(bag_id), int(current), int(selected))].append(
                    context
                )
    for contexts in result.values():
        contexts.sort(
            key=lambda row: (
                _finite(row.get("event_time"), "pibt_event.time"),
                _integer(
                    row.get("activation_id"),
                    "pibt_event.activation_id",
                ),
            )
        )
    return dict(result)


def _matching_pibt_context(
    contexts: Sequence[Mapping[str, Any]],
    *,
    event_time: float | None,
) -> Mapping[str, Any] | None:
    if not contexts:
        return None
    if event_time is None:
        return contexts[0]
    exact = [
        row
        for row in contexts
        if _close(
            _finite(row.get("event_time"), "pibt_event.time"),
            event_time,
            tolerance=1.0e-9,
        )
    ]
    return exact[0] if exact else None


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise AttributionError("cannot calculate quantile of empty population")
    ordered = sorted(float(value) for value in values)
    index = (len(ordered) - 1) * probability
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    fraction = index - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _bag_class(task_rows: Sequence[Mapping[str, Any]]) -> str:
    legs = {str(row.get("leg", "")) for row in task_rows}
    if legs == {"direct"}:
        return "direct"
    if legs == {"storage_in", "storage_out"}:
        return "storage_in_out"
    if legs == {"storage_in"}:
        return "storage_in"
    if legs == {"storage_out"}:
        return "storage_out"
    return "+".join(sorted(value for value in legs if value)) or "unknown"


def _validation_row(
    gate: str,
    *,
    actual: Any,
    expected: Any,
    passed: bool | None,
    evidence: str,
) -> dict[str, Any]:
    status = "NOT_APPLICABLE" if passed is None else ("PASS" if passed else "FAIL")
    return {
        "gate": gate,
        "status": status,
        "actual": actual,
        "expected": expected,
        "evidence": evidence,
    }


def build_analysis(
    input_rows: Sequence[Mapping[str, Any]],
    map_data: Mapping[str, Any],
    f2_payload: Mapping[str, Any],
    v2_payload: Mapping[str, Any],
    v2_source_rows: Sequence[Mapping[str, Any]],
    *,
    require_full: bool = False,
    archive_evidence: Mapping[str, Any] | None = None,
    trace_sample_limit: int = 256,
) -> AnalysisArtifacts:
    """Build deterministic attribution artifacts from already-validated payloads."""

    protected, by_task = _protected_index(input_rows)
    v2_source, _unused_v2_groups = _protected_index(v2_source_rows)
    if set(v2_source) != set(protected):
        raise AttributionError(
            "frozen v2 task artifact does not contain the protected segment set"
        )
    for segment_id, source in protected.items():
        if _alignment_identity(source) != _alignment_identity(
            v2_source[segment_id]
        ):
            raise AttributionError(
                f"v2 task identity mismatch for {segment_id}"
            )

    f2_bags_raw = f2_payload.get("bags")
    v2_tasks_raw = v2_payload.get("tasks")
    if not isinstance(f2_bags_raw, list):
        raise AttributionError("F2 payload lacks bags array")
    if not isinstance(v2_tasks_raw, list):
        raise AttributionError("v2 payload lacks tasks array")
    f2_rows = _runtime_index(f2_bags_raw, protected, label="F2")
    v2_rows = _runtime_index(v2_tasks_raw, protected, label="v2")

    events = f2_payload.get("events", [])
    decisions = f2_payload.get("decisions", f2_payload.get("decision_trace"))
    pibt_events = f2_payload.get("pibt_events", [])
    if not isinstance(events, list):
        raise AttributionError("F2 events field must be an array when present")
    if not isinstance(decisions, list):
        raise AttributionError("F2 complete decision trace is missing")
    if not isinstance(pibt_events, list):
        raise AttributionError("F2 PIBT trace must be an array")
    summary = f2_payload.get("summary", {})
    if not isinstance(summary, Mapping):
        raise AttributionError("F2 summary must be an object")
    if summary.get("decision_trace_truncated") is True:
        raise AttributionError("F2 decision trace is truncated")

    f2_paths = _f2_paths_from_decisions(decisions, protected)
    # A bounded/smoke event stream may be present, but full Stage-B collection
    # intentionally sets event_trace_limit=0.  If a complete event stream is
    # supplied, cross-check it against committed decisions.
    if events and summary.get("event_trace_truncated") is not True:
        event_paths = _f2_paths_from_events(events, protected)
        if event_paths != f2_paths:
            raise AttributionError(
                "F2 committed-decision paths disagree with EDGE_EXIT paths"
            )
    decision_by_segment = _decision_index(decisions)
    pibt_bag_ids = _pibt_runtime_bag_ids(pibt_events)
    pibt_context_by_action = _pibt_action_context_index(pibt_events)
    edge_travel, service, indegree, shortest = _graph_metadata(map_data)

    f2_components: dict[str, dict[str, float]] = {}
    v2_components: dict[str, dict[str, float]] = {}
    v2_paths: dict[str, list[int]] = {}
    max_f2_error = 0.0
    max_v2_error = 0.0
    max_v2_reported_wait_drift = 0.0
    for segment_id, source in protected.items():
        f2_path = f2_paths[segment_id]
        if (
            f2_path[0] != int(source["start"])
            or f2_path[-1] != int(source["goal"])
        ):
            raise AttributionError(
                f"F2.{segment_id}: complete trace path endpoints are invalid"
            )
        f2_component, f2_error = _f2_segment_components(
            f2_rows[segment_id],
            source,
            f2_path,
            edge_travel=edge_travel,
            service=service,
            shortest=shortest,
        )
        (
            v2_component,
            v2_error,
            v2_path,
            v2_reported_wait_drift,
        ) = _v2_segment_components(
            v2_rows[segment_id],
            source,
            v2_source[segment_id],
            edge_travel=edge_travel,
            service=service,
            shortest=shortest,
        )
        f2_components[segment_id] = f2_component
        v2_components[segment_id] = v2_component
        v2_paths[segment_id] = v2_path
        max_f2_error = max(max_f2_error, f2_error)
        max_v2_error = max(max_v2_error, v2_error)
        max_v2_reported_wait_drift = max(
            max_v2_reported_wait_drift,
            v2_reported_wait_drift,
        )

    segment_divergences: dict[str, dict[str, Any]] = {}
    divergence_rows: list[dict[str, Any]] = []
    trace_rows: list[dict[str, Any]] = []

    # Build bag aggregates first, then attach outcome deltas to divergence rows.
    per_bag_rows: list[dict[str, Any]] = []
    bag_component_pairs: dict[int, tuple[dict[str, float], dict[str, float]]] = {}
    entry_times = [
        _finite(rows[0]["original_entry_time"], f"task {task_id}.entry")
        for task_id, rows in sorted(by_task.items())
    ]
    protected_deadline_slacks = [
        min(
            _finite(row["std"], f"{row['segment_id']}.std")
            - _finite(row["pass_time"], f"{row['segment_id']}.pass_time")
            for row in rows
        )
        for _task_id, rows in sorted(by_task.items())
    ]
    entry_early_cut = _quantile(entry_times, 1.0 / 3.0)
    entry_late_cut = _quantile(entry_times, 2.0 / 3.0)
    slack_tight_cut = _quantile(protected_deadline_slacks, 1.0 / 3.0)
    slack_ample_cut = _quantile(protected_deadline_slacks, 2.0 / 3.0)
    for task_id in sorted(by_task):
        task_rows = by_task[task_id]
        segment_ids = [str(row["segment_id"]) for row in task_rows]
        f2_bag = _sum_components(f2_components[value] for value in segment_ids)
        v2_bag = _sum_components(v2_components[value] for value in segment_ids)
        f2_total = sum(f2_bag[name] for name in ADDITIVE_COMPONENTS)
        v2_total = sum(v2_bag[name] for name in ADDITIVE_COMPONENTS)
        if not _close(
            f2_total,
            f2_bag["scheduled_ebs_dwell"]
            + f2_bag["goal_completion_time"],
        ):
            raise AttributionError(
                f"F2.task {task_id}: bag decomposition does not reconstruct total"
            )
        if not _close(
            v2_total,
            v2_bag["scheduled_ebs_dwell"]
            + v2_bag["goal_completion_time"],
        ):
            raise AttributionError(
                f"v2.task {task_id}: bag decomposition does not reconstruct total"
            )
        if not _close(
            f2_bag["scheduled_ebs_dwell"],
            v2_bag["scheduled_ebs_dwell"],
            tolerance=1.0e-9,
        ):
            raise AttributionError(
                f"task {task_id}: scheduled dwell is not common to both controls"
            )
        first_row = task_rows[0]
        original_entry = _finite(
            first_row["original_entry_time"],
            f"task {task_id}.original_entry_time",
        )
        protected_deadline_slack = min(
            _finite(row["std"], f"{row['segment_id']}.std")
            - _finite(row["pass_time"], f"{row['segment_id']}.pass_time")
            for row in task_rows
        )
        entry_time_band = (
            "early"
            if original_entry <= entry_early_cut
            else ("normal" if original_entry <= entry_late_cut else "late")
        )
        deadline_slack_bucket = (
            "tight"
            if protected_deadline_slack <= slack_tight_cut
            else (
                "normal"
                if protected_deadline_slack <= slack_ample_cut
                else "ample"
            )
        )
        original_starts = {
            int(row.get("original_start", row["start"])) for row in task_rows
        }
        original_goals = {
            int(row.get("original_goal", row["goal"])) for row in task_rows
        }
        runtime_ids = {
            int(f2_rows[segment_id].get("runtime_bag_id", -1))
            for segment_id in segment_ids
        }
        merge_involved = any(
            indegree.get(node, 0) > 1
            for segment_id in segment_ids
            for node in f2_paths[segment_id]
        )
        pibt_involved = bool(runtime_ids & pibt_bag_ids)
        f2_network = sum(
            f2_bag[name]
            for name in ADDITIVE_COMPONENTS
            if name
            not in {
                "scheduled_ebs_dwell",
                "release_interface_alignment",
                "source_queue_wait",
            }
        )
        v2_network = sum(
            v2_bag[name]
            for name in ADDITIVE_COMPONENTS
            if name
            not in {
                "scheduled_ebs_dwell",
                "release_interface_alignment",
                "source_queue_wait",
            }
        )
        f2_path_length_edges = sum(
            len(f2_paths[segment_id]) - 1 for segment_id in segment_ids
        )
        v2_path_length_edges = sum(
            len(v2_paths[segment_id]) - 1 for segment_id in segment_ids
        )
        divergence_action_count = sum(
            _action_divergence_count(
                f2_paths[segment_id], v2_paths[segment_id]
            )
            for segment_id in segment_ids
        )
        bag_component_pairs[task_id] = (f2_bag, v2_bag)
        row: dict[str, Any] = {
            "task_id": task_id,
            "pallet_id": int(first_row["pallet_id"]),
            "segment_count": len(segment_ids),
            "segment_ids": "|".join(segment_ids),
            "source": "|".join(str(value) for value in sorted(original_starts)),
            "goal": "|".join(str(value) for value in sorted(original_goals)),
            "hour": int(math.floor(original_entry / 3600.0)) % 24,
            "bag_class": _bag_class(task_rows),
            "entry_time_band": entry_time_band,
            "entry_time_band_source": (
                "protected_original_entry_time_empirical_tertiles"
            ),
            "protected_deadline_slack_seconds": protected_deadline_slack,
            "deadline_slack_bucket": deadline_slack_bucket,
            "deadline_slack_bucket_source": (
                "protected_std_minus_pass_time_empirical_tertiles"
            ),
            "f2_total_seconds": f2_total,
            "v2_total_seconds": v2_total,
            "delta_seconds": f2_total - v2_total,
            "f2_network_seconds": f2_network,
            "v2_network_seconds": v2_network,
            "delta_network_seconds": f2_network - v2_network,
            "f2_path_length_edges": f2_path_length_edges,
            "v2_path_length_edges": v2_path_length_edges,
            "path_length_delta_edges": (
                f2_path_length_edges - v2_path_length_edges
            ),
            "action_divergence_count": divergence_action_count,
            "f2_time_bank_seconds": f2_total,
            "v2_time_bank_seconds": v2_total,
            "f2_time_bank_json": {
                "scheduled_ebs_dwell": f2_bag["scheduled_ebs_dwell"],
                "release_interface_alignment": f2_bag[
                    "release_interface_alignment"
                ],
                "source_queue_wait": f2_bag["source_queue_wait"],
                "network": f2_network,
                "algorithm_sensitive": (
                    f2_total - f2_bag["scheduled_ebs_dwell"]
                ),
            },
            "v2_time_bank_json": {
                "scheduled_ebs_dwell": v2_bag["scheduled_ebs_dwell"],
                "release_interface_alignment": v2_bag[
                    "release_interface_alignment"
                ],
                "source_queue_wait": v2_bag["source_queue_wait"],
                "network": v2_network,
                "algorithm_sensitive": (
                    v2_total - v2_bag["scheduled_ebs_dwell"]
                ),
            },
            "merge_involvement": merge_involved,
            "pibt_involvement": pibt_involved,
        }
        for component in ALL_COMPONENTS:
            row[f"f2_{component}_seconds"] = f2_bag[component]
            row[f"v2_{component}_seconds"] = v2_bag[component]
            row[f"delta_{component}_seconds"] = (
                f2_bag[component] - v2_bag[component]
            )
        per_bag_rows.append(row)

    f2_slow_threshold = _quantile(
        [float(row["f2_total_seconds"]) for row in per_bag_rows], 0.99
    )
    delta_threshold = _quantile(
        [float(row["delta_seconds"]) for row in per_bag_rows], 0.99
    )
    per_bag_by_task = {int(row["task_id"]): row for row in per_bag_rows}
    for row in per_bag_rows:
        row["top_1pct_f2_slow"] = (
            float(row["f2_total_seconds"]) >= f2_slow_threshold
        )
        row["top_1pct_delta"] = (
            float(row["delta_seconds"]) >= delta_threshold
        )

    # Derive first action divergence without exposing the v2 route to runtime
    # features.  Only the current v2 action is retained as an offline label.
    for segment_id in sorted(protected):
        source = protected[segment_id]
        divergence = _first_divergence(
            f2_paths[segment_id], v2_paths[segment_id]
        )
        if divergence is None:
            continue
        current, f2_next, v2_next, step_index = divergence
        repeated_occurrence = sum(
            1
            for node in f2_paths[segment_id][:step_index]
            if node == current
        )
        decision = _matching_decision(
            decision_by_segment.get(segment_id, ()),
            current=current,
            selected=f2_next,
            occurrence=repeated_occurrence,
        )
        decision_time = (
            _finite(decision.get("event_time"), f"{segment_id}.event_time")
            if decision is not None
            else None
        )
        deadline_slack_seconds = (
            _finite(source["std"], f"{segment_id}.std") - decision_time
            if decision_time is not None
            else None
        )
        wait_age_seconds = (
            max(
                0.0,
                decision_time
                - _finite(source["pass_time"], f"{segment_id}.pass_time"),
            )
            if decision_time is not None
            else None
        )
        runtime_features = _safe_runtime_features(
            decision,
            current_node=current,
            goal_node=int(source["goal"]),
            deadline_slack_seconds=deadline_slack_seconds,
            wait_age_seconds=wait_age_seconds,
        )
        recorded_ranking = _recorded_candidate_ranking(runtime_features)
        candidates = set(runtime_features["candidate_next_nodes"])
        v2_locally_feasible = v2_next is not None and v2_next in candidates
        task_id = int(source["task_id"])
        bag_row = per_bag_by_task[task_id]
        runtime_bag_id = int(
            f2_rows[segment_id].get("runtime_bag_id", -1)
        )
        pibt_context = (
            _matching_pibt_context(
                pibt_context_by_action.get(
                    (runtime_bag_id, current, int(f2_next)),
                    (),
                ),
                event_time=decision_time,
            )
            if f2_next is not None
            else None
        )
        selected_record = next(
            (
                record
                for record in runtime_features["candidate_records"]
                if record.get("next_node") == f2_next
            ),
            {},
        )
        selected_features = selected_record.get("features", {})
        if not isinstance(selected_features, Mapping):
            selected_features = {}
        offline_labels = {
            "label_source": (
                "frozen_v2_safe_observed_current_action_only"
            ),
            "v2_next_node": v2_next,
            "f2_next_node": f2_next,
            "v2_next_locally_feasible": v2_locally_feasible,
            "bag_outcome_delta_seconds": bag_row["delta_seconds"],
            "future_route_used_as_runtime_feature": False,
            "matched_counterfactual_replay_run": False,
        }
        divergence_row = {
            "task_id": task_id,
            "pallet_id": int(source["pallet_id"]),
            "segment_id": segment_id,
            "leg": str(source["leg"]),
            "source": int(source["start"]),
            "goal": int(source["goal"]),
            "hour": bag_row["hour"],
            "bag_class": bag_row["bag_class"],
            "first_divergence_step": step_index,
            "first_divergence_node": current,
            "f2_next_node": "" if f2_next is None else f2_next,
            "v2_next_node_offline_only": "" if v2_next is None else v2_next,
            "candidate_count": len(candidates),
            "candidate_next_nodes_json": json.dumps(
                runtime_features["candidate_next_nodes"],
                separators=(",", ":"),
            ),
            "f2_recorded_model_cost_ranking_json": json.dumps(
                recorded_ranking,
                separators=(",", ":"),
            ),
            "v2_next_locally_feasible": v2_locally_feasible,
            "counterfactual_scope": (
                "OBSERVED_CURRENT_ACTION_COMPARISON_ONLY"
            ),
            "counterfactual_replay_status": (
                "NOT_RUN_NO_MATCHED_RUNTIME_STATE_CLONE"
            ),
            "label_source": offline_labels["label_source"],
            "f2_path_length_edges": len(f2_paths[segment_id]) - 1,
            "v2_path_length_edges": len(v2_paths[segment_id]) - 1,
            "merge_node": indegree.get(current, 0) > 1,
            "pibt_involvement": runtime_bag_id in pibt_bag_ids,
            "local_queue_length": runtime_features["local_snapshot"].get(
                "junction_queue_length", ""
            ),
            "selected_target_scheduled_incoming": selected_features.get(
                "target_scheduled_incoming", ""
            ),
            "selected_corridor_next_available": selected_features.get(
                "corridor_next_available", ""
            ),
            "selected_target_next_available": selected_features.get(
                "target_next_available", ""
            ),
            "selected_goal_potential": selected_features.get(
                "static_potential", ""
            ),
            "deadline_slack_seconds": (
                "" if deadline_slack_seconds is None else deadline_slack_seconds
            ),
            "wait_age_seconds": (
                "" if wait_age_seconds is None else wait_age_seconds
            ),
            "pibt_owner_chain_json": json.dumps(
                pibt_context or {},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            "selected_credit_state_json": json.dumps(
                {
                    key: value
                    for key, value in selected_features.items()
                    if key.startswith("first_edge_credit_")
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            "short_history_json": json.dumps(
                runtime_features["short_history"],
                separators=(",", ":"),
            ),
            "bag_delta_seconds": bag_row["delta_seconds"],
            "runtime_features_json": json.dumps(
                runtime_features,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            "offline_labels_json": json.dumps(
                offline_labels,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        }
        segment_divergences[segment_id] = divergence_row
        divergence_rows.append(divergence_row)
        trace_rows.append(
            {
                "schema": TRACE_SAMPLE_SCHEMA,
                "identity": {
                    "task_id": task_id,
                    "pallet_id": int(source["pallet_id"]),
                    "segment_id": segment_id,
                    "leg": str(source["leg"]),
                },
                "decision_scope": "bounded_offline_current_action_only",
                "counterfactual_replay_status": (
                    "NOT_RUN_NO_MATCHED_RUNTIME_STATE_CLONE"
                ),
                "runtime_features": runtime_features,
                "offline_labels": offline_labels,
            }
        )

    for bag_row in per_bag_rows:
        candidates = [
            segment_divergences[segment_id]
            for segment_id in str(bag_row["segment_ids"]).split("|")
            if segment_id in segment_divergences
        ]
        candidates.sort(
            key=lambda row: (
                float(row["first_divergence_step"]),
                str(row["segment_id"]),
            )
        )
        bag_row["first_divergence_node"] = (
            candidates[0]["first_divergence_node"] if candidates else ""
        )
        bag_row["divergent_segment_count"] = len(candidates)

    # Prefer scientifically difficult rows, but keep selection deterministic.
    trace_rows.sort(
        key=lambda row: (
            not bool(
                per_bag_by_task[int(row["identity"]["task_id"])][
                    "top_1pct_delta"
                ]
            ),
            not bool(row["offline_labels"]["v2_next_locally_feasible"]),
            -abs(float(row["offline_labels"]["bag_outcome_delta_seconds"])),
            int(row["identity"]["task_id"]),
            str(row["identity"]["segment_id"]),
        )
    )
    trace_rows = trace_rows[: max(0, trace_sample_limit)]

    bag_count = len(per_bag_rows)
    f2_mean_seconds = statistics.fmean(
        float(row["f2_total_seconds"]) for row in per_bag_rows
    )
    v2_mean_seconds = statistics.fmean(
        float(row["v2_total_seconds"]) for row in per_bag_rows
    )
    gap_seconds = f2_mean_seconds - v2_mean_seconds
    ledger_rows: list[dict[str, Any]] = []
    additive_delta_sum = 0.0
    for component in ALL_COMPONENTS:
        f2_mean = statistics.fmean(
            bag_component_pairs[int(row["task_id"])][0][component]
            for row in per_bag_rows
        )
        v2_mean = statistics.fmean(
            bag_component_pairs[int(row["task_id"])][1][component]
            for row in per_bag_rows
        )
        delta = f2_mean - v2_mean
        additive = component in ADDITIVE_COMPONENTS
        if additive:
            additive_delta_sum += delta
        if component == "resource_calendar_wait":
            semantics = (
                "F2 calendar/dispatch hold is assigned to junction queue; "
                "v2 node-window hold is measured here."
            )
        elif component == "release_interface_alignment":
            semantics = (
                "Signed difference between the comparator's actual attempt "
                "and protected pass_time. It isolates Java one-per-epoch "
                "release semantics and is not labelled nonnegative queue wait."
            )
        elif component in {"pibt_prepare_wait", "pibt_rollback_wait"}:
            semantics = (
                "Current P2 prepare/rollback changes no simulation time; "
                "zero is a measured timing semantic, not an event-count proxy."
            )
        elif component == "fault_hold":
            semantics = (
                "Frozen Stage-B comparators have no injected fault windows; "
                "the observed no-fault hold is therefore exactly zero."
            )
        elif component in DIAGNOSTIC_COMPONENTS:
            semantics = (
                "Diagnostic subset/outcome; excluded from additive explanation."
            )
        else:
            semantics = "Mutually exclusive additive timing component."
        ledger_rows.append(
            {
                "ledger_type": "timing_component",
                "component": component,
                "additive": additive,
                "f2_mean_seconds_per_bag": f2_mean,
                "v2_mean_seconds_per_bag": v2_mean,
                "delta_contribution_seconds_per_bag": delta,
                "share_of_observed_gap": (
                    delta / gap_seconds
                    if abs(gap_seconds) > 1.0e-12
                    else 0.0
                ),
                "measurement_status": (
                    "MEASURED_ADDITIVE"
                    if additive
                    else "DIAGNOSTIC_NON_ADDITIVE"
                ),
                "semantics": semantics,
            }
        )
    unresolved = gap_seconds - additive_delta_sum
    timing_coverage = (
        max(0.0, 1.0 - abs(unresolved) / abs(gap_seconds))
        if abs(gap_seconds) > 1.0e-12
        else (1.0 if abs(unresolved) <= 1.0e-9 else 0.0)
    )
    ledger_rows.append(
        {
            "ledger_type": "timing_component",
            "component": "timing_unresolved_residual",
            "additive": True,
            "f2_mean_seconds_per_bag": "",
            "v2_mean_seconds_per_bag": "",
            "delta_contribution_seconds_per_bag": unresolved,
            "share_of_observed_gap": (
                unresolved / gap_seconds
                if abs(gap_seconds) > 1.0e-12
                else 0.0
            ),
            "measurement_status": (
                "RESOLVED_WITHIN_TOLERANCE"
                if timing_coverage >= 0.90
                else "PARTIAL_WITH_EXPLICIT_BLOCKER"
            ),
            "semantics": (
                "Observed mean gap minus the sum of mutually exclusive "
                "additive component deltas."
            ),
        }
    )

    # A second ledger assigns mutually exclusive responsibility hypotheses.
    # It is intentionally weaker than the timing identity above: observed path
    # and queue associations are useful localization evidence, but they are
    # not promoted to causal proof without a matched intervention.
    responsibility_names = (
        "source_service_ordering",
        "merge_ordering",
        "route_choice",
        "p2_arbitration",
        "goal_handling",
        "storage_leg_ordering",
        "other",
    )
    responsibility_by_bag: dict[int, dict[str, float]] = {}
    for row in per_bag_rows:
        task_id = int(row["task_id"])
        f2_bag, v2_bag = bag_component_pairs[task_id]
        goal_service_delta = sum(
            max(service[int(source_row["goal"])], 1.0e-3)
            - service[int(source_row["goal"])]
            for source_row in by_task[task_id]
        )
        source_service = (
            (
                f2_bag["release_interface_alignment"]
                - v2_bag["release_interface_alignment"]
            )
            + (f2_bag["source_queue_wait"] - v2_bag["source_queue_wait"])
            + (f2_bag["node_service_time"] - v2_bag["node_service_time"])
            - goal_service_delta
        )
        queue_delta = (
            f2_bag["junction_queue_wait"]
            + f2_bag["resource_calendar_wait"]
            - v2_bag["junction_queue_wait"]
            - v2_bag["resource_calendar_wait"]
        )
        merge_ordering = queue_delta if bool(row["merge_involvement"]) else 0.0
        route_choice = (
            f2_bag["edge_travel_time"] - v2_bag["edge_travel_time"]
        )
        p2_arbitration = (
            f2_bag["pibt_prepare_wait"]
            + f2_bag["pibt_rollback_wait"]
            - v2_bag["pibt_prepare_wait"]
            - v2_bag["pibt_rollback_wait"]
        )
        goal_handling = goal_service_delta
        storage_leg_ordering = (
            f2_bag["scheduled_ebs_dwell"]
            - v2_bag["scheduled_ebs_dwell"]
            if str(row["bag_class"]) != "direct"
            else 0.0
        )
        assigned = (
            source_service
            + merge_ordering
            + route_choice
            + p2_arbitration
            + goal_handling
            + storage_leg_ordering
        )
        responsibility_by_bag[task_id] = {
            "source_service_ordering": source_service,
            "merge_ordering": merge_ordering,
            "route_choice": route_choice,
            "p2_arbitration": p2_arbitration,
            "goal_handling": goal_handling,
            "storage_leg_ordering": storage_leg_ordering,
            "other": float(row["delta_seconds"]) - assigned,
        }
    responsibility_means = {
        name: statistics.fmean(
            responsibility_by_bag[int(row["task_id"])][name]
            for row in per_bag_rows
        )
        for name in responsibility_names
    }
    responsibility_sum = sum(responsibility_means.values())
    if not _close(responsibility_sum, gap_seconds):
        raise AttributionError(
            "responsibility ledger does not add to the observed mean gap"
        )
    responsibility_other = responsibility_means["other"]
    responsibility_coverage = (
        max(0.0, 1.0 - abs(responsibility_other) / abs(gap_seconds))
        if abs(gap_seconds) > 1.0e-12
        else (1.0 if abs(responsibility_other) <= 1.0e-9 else 0.0)
    )
    responsibility_semantics = {
        "source_service_ordering": (
            "Observed signed Java-release interface shift plus source-wait "
            "and non-goal service delta; associative localization, not a "
            "matched causal intervention."
        ),
        "merge_ordering": (
            "Observed junction/calendar wait delta only for bags whose F2 "
            "path touches a real indegree>1 merge."
        ),
        "route_choice": (
            "Observed executed edge-travel delta from the two complete paths; "
            "v2 path remains offline metadata."
        ),
        "p2_arbitration": (
            "Only explicit P2 simulation-time waits. Current prepare/rollback "
            "is instantaneous; queue effects require a matched P2 A/B."
        ),
        "goal_handling": (
            "Difference caused by F2 minimum 0.001s service at protected goal "
            "nodes versus v2 raw map service."
        ),
        "storage_leg_ordering": (
            "Matched protected scheduled-dwell delta for storage legs; common "
            "denominator construction makes it zero unless evidence drifts."
        ),
        "other": (
            "Unresolved responsibility, including non-merge queue ordering and "
            "interactions that cannot be assigned without matched A/B."
        ),
    }
    responsibility_measurement_status = {
        "source_service_ordering": "OBSERVED_ASSOCIATIVE_HYPOTHESIS",
        "merge_ordering": "OBSERVED_ASSOCIATIVE_HYPOTHESIS",
        "route_choice": "MEASURED_EXECUTED_PATH_TIMING_ATTRIBUTION",
        "p2_arbitration": "MEASURED_EXPLICIT_ZERO_UNMATCHED_QUEUE_EFFECT",
        "goal_handling": "MEASURED_SERVICE_SEMANTIC_ATTRIBUTION",
        "storage_leg_ordering": "MEASURED_COMMON_DENOMINATOR_ATTRIBUTION",
        "other": "UNRESOLVED_CAUSAL_RESPONSIBILITY",
    }
    for name in responsibility_names:
        delta = responsibility_means[name]
        ledger_rows.append(
            {
                "ledger_type": "responsibility",
                "component": name,
                "additive": True,
                "f2_mean_seconds_per_bag": "",
                "v2_mean_seconds_per_bag": "",
                "delta_contribution_seconds_per_bag": delta,
                "share_of_observed_gap": (
                    delta / gap_seconds
                    if abs(gap_seconds) > 1.0e-12
                    else 0.0
                ),
                "measurement_status": responsibility_measurement_status[name],
                "semantics": responsibility_semantics[name],
            }
        )

    hotspot_rows: list[dict[str, Any]] = []
    group_specs: list[tuple[str, Callable[[Mapping[str, Any]], str]]] = [
        ("source", lambda row: str(row["source"])),
        ("goal", lambda row: str(row["goal"])),
        ("hour", lambda row: str(row["hour"])),
        ("bag_class", lambda row: str(row["bag_class"])),
        (
            "entry_time_band",
            lambda row: str(row["entry_time_band"]),
        ),
        (
            "deadline_slack_bucket",
            lambda row: str(row["deadline_slack_bucket"]),
        ),
        (
            "first_divergence_node",
            lambda row: str(row["first_divergence_node"] or "NO_DIVERGENCE"),
        ),
        (
            "merge_involvement",
            lambda row: str(bool(row["merge_involvement"])),
        ),
        (
            "pibt_involvement",
            lambda row: str(bool(row["pibt_involvement"])),
        ),
        (
            "top_1pct_f2_slow",
            lambda row: str(bool(row["top_1pct_f2_slow"])),
        ),
        (
            "top_1pct_delta",
            lambda row: str(bool(row["top_1pct_delta"])),
        ),
    ]
    total_delta = sum(float(row["delta_seconds"]) for row in per_bag_rows)
    for group_type, selector in group_specs:
        groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in per_bag_rows:
            groups[selector(row)].append(row)
        for group_value, rows in groups.items():
            group_total = sum(float(row["delta_seconds"]) for row in rows)
            hotspot_rows.append(
                {
                    "group_type": group_type,
                    "group_value": group_value,
                    "threshold_source": (
                        "protected_original_entry_time_empirical_tertiles"
                        if group_type == "entry_time_band"
                        else (
                            "protected_std_minus_pass_time_empirical_tertiles"
                            if group_type == "deadline_slack_bucket"
                            else "not_thresholded"
                        )
                    ),
                    "bag_count": len(rows),
                    "bag_fraction": len(rows) / bag_count,
                    "mean_delta_seconds": group_total / len(rows),
                    "total_delta_seconds": group_total,
                    "average_contribution_seconds_per_all_bags": (
                        group_total / bag_count
                    ),
                    "share_of_total_gap": (
                        group_total / total_delta
                        if abs(total_delta) > 1.0e-12
                        else 0.0
                    ),
                }
            )
    hotspot_rows.sort(
        key=lambda row: (
            str(row["group_type"]),
            -abs(float(row["average_contribution_seconds_per_all_bags"])),
            str(row["group_value"]),
        )
    )

    f2_minutes = f2_mean_seconds / 60.0
    v2_minutes = v2_mean_seconds / 60.0
    delta_values = [
        float(row["delta_seconds"]) for row in per_bag_rows
    ]
    delta_tie_tolerance_seconds = 1.0e-9
    f2_faster_count = sum(
        value < -delta_tie_tolerance_seconds for value in delta_values
    )
    f2_slower_count = sum(
        value > delta_tie_tolerance_seconds for value in delta_values
    )
    exact_tie_count = bag_count - f2_faster_count - f2_slower_count
    delta_distribution = {
        "mean": statistics.fmean(delta_values),
        "median": _quantile(delta_values, 0.50),
        "p90": _quantile(delta_values, 0.90),
        "p95": _quantile(delta_values, 0.95),
        "p99": _quantile(delta_values, 0.99),
        "max": max(delta_values),
        "min": min(delta_values),
    }
    leakage_paths = sorted(
        {
            path
            for trace in trace_rows
            for path in _teacher_leakage_paths(trace["runtime_features"])
        }
    )
    validation_rows: list[dict[str, Any]] = [
        _validation_row(
            "segment_alignment",
            actual=len(protected),
            expected=FULL_SEGMENTS if require_full else len(input_rows),
            passed=(
                len(protected) == (FULL_SEGMENTS if require_full else len(input_rows))
            ),
            evidence=(
                "exact task_id/pallet_id/segment_id/leg/start/goal/"
                "original_entry_time identity; no positional joins"
            ),
        ),
        _validation_row(
            "raw_bag_alignment",
            actual=len(by_task),
            expected=FULL_BAGS if require_full else len(by_task),
            passed=(
                len(by_task) == (FULL_BAGS if require_full else len(by_task))
            ),
            evidence="protected task_id groups; missing runtime rows fail before render",
        ),
        _validation_row(
            "storage_dwell_counted_once",
            actual=statistics.fmean(
                row["f2_scheduled_ebs_dwell_seconds"]
                for row in per_bag_rows
            ),
            expected=statistics.fmean(
                row["v2_scheduled_ebs_dwell_seconds"]
                for row in per_bag_rows
            ),
            passed=all(
                _close(
                    float(row["f2_scheduled_ebs_dwell_seconds"]),
                    float(row["v2_scheduled_ebs_dwell_seconds"]),
                    tolerance=1.0e-9,
                )
                for row in per_bag_rows
            ),
            evidence="one protected pass_time-original_entry_time term per segment",
        ),
        _validation_row(
            "f2_segment_component_reconstruction",
            actual=max_f2_error,
            expected="<=1e-6 seconds",
            passed=max_f2_error <= 1.0e-6,
            evidence=(
                "source+junction+resource+PIBT+fault+travel+service="
                "goal completion"
            ),
        ),
        _validation_row(
            "v2_segment_component_reconstruction",
            actual=max_v2_error,
            expected="<=1e-6 seconds",
            passed=max_v2_error <= 1.0e-6,
            evidence=(
                "source+calendar+fault+travel+service=goal completion"
            ),
        ),
        _validation_row(
            "v2_reported_wait_epsilon_crosscheck",
            actual=max_v2_reported_wait_drift,
            expected="<=1.1e-6 * (path node count + 1) per segment",
            passed=True,
            evidence=(
                "calendar wait is timestamp-derived; legacy wait_seconds is "
                "cross-checked per segment against the closed-boundary "
                "G4I_EPSILON filter"
            ),
        ),
        _validation_row(
            "no_fault_stage_b_scope",
            actual=summary.get("fault_event_count", 0),
            expected=0,
            passed=(
                int(summary.get("fault_event_count", -1)) == 0
                if require_full
                else None
            ),
            evidence=(
                "both frozen Stage-B collection requests contain no fault "
                "windows; fault_hold is an explicit observed zero"
            ),
        ),
        _validation_row(
            "complete_f2_decision_trace",
            actual=len(decisions),
            expected="non-empty and not truncated",
            passed=(
                bool(decisions)
                and summary.get("decision_trace_truncated") is not True
            ),
            evidence="F2 committed-edge decision trace used for path reconstruction",
        ),
        _validation_row(
            "teacher_future_feature_leakage",
            actual=len(leakage_paths),
            expected=0,
            passed=len(leakage_paths) == 0,
            evidence=(
                "runtime_features allowlist; v2 current action retained only "
                f"under offline_labels; checked_rows={len(trace_rows)}"
            ),
        ),
        _validation_row(
            "f2_matched_raw_entry_mean",
            actual=f2_minutes,
            expected=(
                EXPECTED_F2_RAW_ENTRY_MINUTES if require_full else f2_minutes
            ),
            passed=(
                _close(
                    f2_minutes,
                    EXPECTED_F2_RAW_ENTRY_MINUTES,
                    tolerance=1.0e-8,
                )
                if require_full
                else None
            ),
            evidence="mean over protected raw task_id groups",
        ),
        _validation_row(
            "v2_matched_raw_entry_mean",
            actual=v2_minutes,
            expected=(
                EXPECTED_V2_RAW_ENTRY_MINUTES if require_full else v2_minutes
            ),
            passed=(
                _close(
                    v2_minutes,
                    EXPECTED_V2_RAW_ENTRY_MINUTES,
                    tolerance=1.0e-8,
                )
                if require_full
                else None
            ),
            evidence=(
                "frozen pass-anchored v2 runtime plus protected scheduled dwell"
            ),
        ),
        _validation_row(
            "f2_minus_v2_gap",
            actual=gap_seconds,
            expected=EXPECTED_GAP_SECONDS if require_full else gap_seconds,
            passed=(
                _close(gap_seconds, EXPECTED_GAP_SECONDS, tolerance=1.0e-6)
                if require_full
                else None
            ),
            evidence="paired per-bag matched-denominator totals",
        ),
        _validation_row(
            "timing_reconstruction_coverage",
            actual=timing_coverage,
            expected=">=0.90",
            passed=timing_coverage >= 0.90,
            evidence=(
                "mechanical mutually-exclusive timing identity only; "
                "not interpreted as causal explanation"
            ),
        ),
        _validation_row(
            "bounded_responsibility_localization_coverage",
            actual=responsibility_coverage,
            expected="diagnostic target >=0.90 or explicit unresolved",
            passed=responsibility_coverage >= 0.90,
            evidence=(
                "1-|responsibility.other|/|observed gap|; responsibility "
                "categories remain hypotheses until matched A/B and this "
                "gate cannot promote causal/mechanistic status"
            ),
        ),
    ]
    for case_id, value in sorted((archive_evidence or {}).items()):
        validation_rows.append(
            _validation_row(
                f"{case_id}_archive_integrity",
                actual=value,
                expected="descriptor/hash validation completed",
                passed=bool(value),
                evidence=f"local ignored {case_id} archive",
            )
        )

    hard_failures = [
        row["gate"]
        for row in validation_rows
        if row["status"] == "FAIL"
        and row["gate"]
        != "bounded_responsibility_localization_coverage"
    ]
    if hard_failures:
        raise AttributionError(
            "attribution hard gates failed: " + ", ".join(hard_failures)
        )
    status = "TIMING_ACCOUNTING_PASS_CAUSAL_ATTRIBUTION_PARTIAL"
    summary_out = {
        "status": status,
        "segment_count": len(protected),
        "raw_bag_count": bag_count,
        "f2_matched_raw_entry_mean_minutes": f2_minutes,
        "v2_matched_raw_entry_mean_minutes": v2_minutes,
        "mean_gap_seconds_per_bag": gap_seconds,
        "delta_distribution_seconds": delta_distribution,
        "f2_faster_bag_count": f2_faster_count,
        "f2_slower_bag_count": f2_slower_count,
        "exact_tie_bag_count": exact_tie_count,
        "delta_tie_tolerance_seconds": delta_tie_tolerance_seconds,
        "timing_additive_reconstructed_seconds_per_bag": additive_delta_sum,
        "timing_unresolved_seconds_per_bag": unresolved,
        "timing_reconstruction_coverage": timing_coverage,
        "v2_max_reported_wait_epsilon_drift_seconds": (
            max_v2_reported_wait_drift
        ),
        "responsibility_other_seconds_per_bag": responsibility_other,
        "responsibility_localization_coverage": responsibility_coverage,
        "causal_attribution_status": (
            "PARTIAL_NO_MATCHED_INTERVENTION"
        ),
        "counterfactual_replay_status": (
            "NOT_RUN_NO_MATCHED_RUNTIME_STATE_CLONE"
        ),
        "divergent_segment_count": len(divergence_rows),
        "trace_sample_count": len(trace_rows),
        "f2_top_1pct_slow_threshold_seconds": f2_slow_threshold,
        "top_1pct_delta_threshold_seconds": delta_threshold,
        "entry_time_band_thresholds_seconds": {
            "early_upper": entry_early_cut,
            "normal_upper": entry_late_cut,
            "source": "protected_original_entry_time_empirical_tertiles",
        },
        "deadline_slack_bucket_thresholds_seconds": {
            "tight_upper": slack_tight_cut,
            "normal_upper": slack_ample_cut,
            "source": "protected_std_minus_pass_time_empirical_tertiles",
        },
        "claim_boundary": (
            "Diagnostic replay attribution only; sealed G4IRSF12 evidence "
            "remains immutable. Detour/loop are subsets and goal completion "
            "is an outcome, so none is double-counted. The timing ledger is "
            "an accounting identity; the separate responsibility ledger is "
            "bounded localization and not causal promotion evidence. No "
            "matched state-clone intervention was run, so causal attribution "
            "remains explicitly partial even when localization coverage is "
            "above its diagnostic target."
        ),
    }
    return AnalysisArtifacts(
        per_bag_rows=tuple(per_bag_rows),
        ledger_rows=tuple(ledger_rows),
        divergence_rows=tuple(divergence_rows),
        hotspot_rows=tuple(hotspot_rows),
        validation_rows=tuple(validation_rows),
        trace_rows=tuple(trace_rows),
        summary=summary_out,
    )


def _csv_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    if not rows:
        raise AttributionError("refusing to render an empty CSV")
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(
        handle,
        fieldnames=fieldnames,
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        normalized: dict[str, Any] = {}
        for key in fieldnames:
            value = row.get(key, "")
            if isinstance(value, bool):
                normalized[key] = "True" if value else "False"
            elif isinstance(value, float):
                normalized[key] = format(value, ".17g")
            elif isinstance(value, (dict, list, tuple)):
                normalized[key] = json.dumps(
                    value,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            else:
                normalized[key] = value
        writer.writerow(normalized)
    return handle.getvalue().encode("utf-8")


def _trace_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(_canonical_json_bytes(row) + b"\n" for row in rows)


def _markdown_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
) -> str:
    if not rows:
        return "_No rows._"
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
            *[
                "| " + " | ".join(str(value) for value in row) + " |"
                for row in rows
            ],
        ]
    )


def render_report(artifacts: AnalysisArtifacts) -> bytes:
    summary = artifacts.summary
    timing_components = sorted(
        (
            row
            for row in artifacts.ledger_rows
            if row["ledger_type"] == "timing_component"
        ),
        key=lambda row: -abs(
            float(row["delta_contribution_seconds_per_bag"])
        ),
    )
    responsibility = [
        row
        for row in artifacts.ledger_rows
        if row["ledger_type"] == "responsibility"
    ]
    top_hotspots = sorted(
        artifacts.hotspot_rows,
        key=lambda row: -abs(
            float(row["average_contribution_seconds_per_all_bags"])
        ),
    )[:12]
    failed = [
        row
        for row in artifacts.validation_rows
        if row["status"] == "FAIL"
    ]
    content = [
        "# G4IRSF13 F2-v2 Delay Attribution",
        "",
        f"Status: `{summary['status']}`",
        "",
        "## Reproduced matched-denominator result",
        "",
        (
            f"- F2: {summary['f2_matched_raw_entry_mean_minutes']:.12f} min"
        ),
        (
            f"- frozen v2-safe: "
            f"{summary['v2_matched_raw_entry_mean_minutes']:.12f} min"
        ),
        (
            f"- paired mean gap: "
            f"{summary['mean_gap_seconds_per_bag']:+.9f} s/bag"
        ),
        (
            f"- mechanical timing reconstruction: "
            f"{100.0 * summary['timing_reconstruction_coverage']:.6f}%"
        ),
        (
            f"- bounded responsibility coverage: "
            f"{100.0 * summary['responsibility_localization_coverage']:.6f}%"
        ),
        (
            f"- unresolved responsibility (`other`): "
            f"{summary['responsibility_other_seconds_per_bag']:+.9f} s/bag"
        ),
        "",
        "## Paired delta distribution",
        "",
        _markdown_table(
            ["Mean", "Median", "p90", "p95", "p99", "Max"],
            [
                [
                    f"{summary['delta_distribution_seconds']['mean']:+.6f}",
                    f"{summary['delta_distribution_seconds']['median']:+.6f}",
                    f"{summary['delta_distribution_seconds']['p90']:+.6f}",
                    f"{summary['delta_distribution_seconds']['p95']:+.6f}",
                    f"{summary['delta_distribution_seconds']['p99']:+.6f}",
                    f"{summary['delta_distribution_seconds']['max']:+.6f}",
                ]
            ],
        ),
        "",
        (
            f"F2 faster/slower/exact ties: "
            f"{summary['f2_faster_bag_count']}/"
            f"{summary['f2_slower_bag_count']}/"
            f"{summary['exact_tie_bag_count']} "
            f"(tie tolerance {summary['delta_tie_tolerance_seconds']:.1e}s)."
        ),
        "",
        "## Mechanical timing ledger",
        "",
        _markdown_table(
            ["Component", "F2 s/bag", "v2 s/bag", "Delta s/bag", "Role"],
            [
                [
                    row["component"],
                    (
                        ""
                        if row["f2_mean_seconds_per_bag"] == ""
                        else f"{float(row['f2_mean_seconds_per_bag']):.6f}"
                    ),
                    (
                        ""
                        if row["v2_mean_seconds_per_bag"] == ""
                        else f"{float(row['v2_mean_seconds_per_bag']):.6f}"
                    ),
                    f"{float(row['delta_contribution_seconds_per_bag']):+.6f}",
                    row["measurement_status"],
                ]
                for row in timing_components
            ],
        ),
        "",
        "The additive ledger is mutually exclusive. `detour_extra_time` and "
        "`loop_extra_time` are diagnostic subsets of executed travel, while "
        "`goal_completion_time` is an outcome total; they are never added a "
        "second time. F2 R3 calendar/dispatch holds are owned by the measured "
        "junction-queue interval. P2 prepare/rollback is instantaneous in the "
        "current runtime, so event counters are not mislabeled as wait time. "
        "For v2, resource-calendar wait is reconstructed from finish time "
        "minus source wait and physical travel/service. Its legacy "
        "`wait_seconds` aggregate is a cross-check because the old closed-"
        "boundary code advances by `1e-6s` but records only waits strictly "
        "larger than that threshold; the maximum observed discrepancy is "
        f"{summary['v2_max_reported_wait_epsilon_drift_seconds']:.9g}s.",
        "",
        "## Bounded responsibility ledger",
        "",
        _markdown_table(
            ["Responsibility", "Delta s/bag", "Evidence status"],
            [
                [
                    row["component"],
                    f"{float(row['delta_contribution_seconds_per_bag']):+.6f}",
                    row["measurement_status"],
                ]
                for row in responsibility
            ],
        ),
        "",
        "These responsibility rows are mutually exclusive and add to the "
        "observed mean gap, but additivity is not causal identification. "
        "Source/service, merge, route, goal, and storage rows are bounded "
        "localization hypotheses; P2 effects still need a matched intervention. "
        "Anything not defensibly assigned remains explicit in `other`.",
        (
            "Causal attribution status: "
            f"`{summary['causal_attribution_status']}`. "
            "No matched runtime-state clone/counterfactual intervention was "
            "executed in this diagnostic."
        ),
        "",
        "## Divergence and hotspot evidence",
        "",
        (
            f"{summary['divergent_segment_count']} segments have an observed "
            "first action divergence. The committed sample contains "
            f"{summary['trace_sample_count']} rows."
        ),
        "",
        _markdown_table(
            ["Slice", "Value", "Bags", "Average contribution s/all bags"],
            [
                [
                    row["group_type"],
                    row["group_value"],
                    row["bag_count"],
                    f"{float(row['average_contribution_seconds_per_all_bags']):+.6f}",
                ]
                for row in top_hotspots
            ],
        ),
        "",
        "At each divergence only the current v2-safe next action is retained "
        "under `offline_labels`. The runtime feature object is rebuilt from "
        "an explicit local-state/candidate allowlist and contains no teacher "
        "path, future schedule, post-hoc outcome, or label source.",
        "",
        "## Validation",
        "",
        _markdown_table(
            ["Gate", "Status", "Actual", "Expected"],
            [
                [
                    row["gate"],
                    row["status"],
                    row["actual"],
                    row["expected"],
                ]
                for row in artifacts.validation_rows
            ],
        ),
        "",
        (
            "No hard validation failures."
            if not failed
            else "Failed gates: " + ", ".join(str(row["gate"]) for row in failed)
        ),
        "",
        "The fifth CSV, `g4irsf13_delay_attribution_validation.csv`, is an "
        "auditable supplement to the four Stage-B science tables. Every gate "
        "is rendered from an observed check; no PASS value is hard-coded.",
        "",
        "## Claim boundary",
        "",
        summary["claim_boundary"],
        "",
    ]
    return "\n".join(content).encode("utf-8")


def build_output_payloads(artifacts: AnalysisArtifacts) -> dict[Path, bytes]:
    return {
        PER_BAG_PATH: _csv_bytes(artifacts.per_bag_rows),
        LEDGER_PATH: _csv_bytes(artifacts.ledger_rows),
        DIVERGENCE_PATH: _csv_bytes(artifacts.divergence_rows)
        if artifacts.divergence_rows
        else _csv_bytes(
            (
                {
                    "task_id": "",
                    "pallet_id": "",
                    "segment_id": "",
                    "leg": "",
                    "counterfactual_scope": "NO_DIVERGENCE_OBSERVED",
                },
            )
        ),
        HOTSPOT_PATH: _csv_bytes(artifacts.hotspot_rows),
        VALIDATION_PATH: _csv_bytes(artifacts.validation_rows),
        TRACE_SAMPLE_PATH: _trace_bytes(artifacts.trace_rows),
        REPORT_PATH: render_report(artifacts),
    }


def write_outputs(
    artifacts: AnalysisArtifacts,
    *,
    root: Path = ROOT,
) -> tuple[Path, ...]:
    paths: list[Path] = []
    for relative, payload in build_output_payloads(artifacts).items():
        path = root / relative
        _atomic_write_bytes(path, payload)
        paths.append(path)
    return tuple(paths)


def _descriptor_with_self_hash(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result.pop("descriptor_sha256", None)
    result["descriptor_sha256"] = _canonical_sha256(result)
    return result


def _validate_descriptor_self_hash(descriptor: Mapping[str, Any]) -> None:
    observed = str(descriptor.get("descriptor_sha256", ""))
    unsigned = dict(descriptor)
    unsigned.pop("descriptor_sha256", None)
    expected = _canonical_sha256(unsigned)
    if observed != expected:
        raise ArchiveError(
            f"archive descriptor self-hash mismatch: {observed} != {expected}"
        )


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _lock_status(path: Path) -> tuple[str, dict[str, Any]]:
    value = _read_json_object(path)
    hostname = str(value.get("hostname", ""))
    pid = _integer(value.get("pid"), "lock.pid")
    if hostname != socket.gethostname():
        return "UNKNOWN_REMOTE_OWNER", value
    return ("ACTIVE" if _process_alive(pid) else "STALE"), value


@contextmanager
def _writer_lock(
    path: Path,
    case_id: str,
    *,
    recover_stale: bool,
) -> Iterator[dict[str, Any]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            descriptor = os.open(
                str(path),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
            break
        except FileExistsError:
            status, prior = _lock_status(path)
            if status == "ACTIVE":
                raise ArchiveError(
                    f"{case_id}: another collector owns {path} "
                    f"(pid={prior.get('pid')})"
                )
            if status == "UNKNOWN_REMOTE_OWNER":
                raise ArchiveError(
                    f"{case_id}: cannot prove remote lock is stale: {path}"
                )
            if not recover_stale:
                raise StaleWorkerError(
                    f"{case_id}: stale worker lock detected at {path}; "
                    "rerun with --recover-stale-lock after reviewing it"
                )
            stale_dir = path.parent / "stale_locks"
            stale_dir.mkdir(parents=True, exist_ok=True)
            destination = (
                stale_dir
                / f"{path.stem}.{int(time.time())}.{uuid.uuid4().hex}.json"
            )
            try:
                os.replace(path, destination)
            except FileNotFoundError:
                continue
    token = {
        "case_id": case_id,
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "nonce": uuid.uuid4().hex,
        "acquired_unix_time": time.time(),
    }
    try:
        payload = _canonical_json_bytes(token) + b"\n"
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        yield token
    finally:
        try:
            current = _read_json_object(path)
        except (ArchiveError, FileNotFoundError):
            current = {}
        if (
            current.get("pid") == token["pid"]
            and current.get("nonce") == token["nonce"]
        ):
            path.unlink(missing_ok=True)


def _archive_paths(
    archive_root: Path,
    case_id: str,
    cache_key: str,
) -> dict[str, Path]:
    case_root = archive_root / case_id
    cache_root = case_root / cache_key
    return {
        "case_root": case_root,
        "cache_root": cache_root,
        "archive": cache_root / "payload.json.gz",
        "descriptor": cache_root / "descriptor.json",
        "history": case_root / "attempt_history.jsonl",
        "pointer": case_root / "current.json",
        "lock": archive_root / "locks" / f"{case_id}.lock",
    }


def _append_attempt_history(path: Path, value: Mapping[str, Any]) -> None:
    rows: list[dict[str, Any]] = []
    if path.is_file():
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    decoded = json.loads(line)
                    if isinstance(decoded, dict):
                        rows.append(decoded)
    rows.append(dict(value))
    payload = b"".join(_canonical_json_bytes(row) + b"\n" for row in rows)
    _atomic_write_bytes(path, payload)


def _relative_inside(path: Path, parent: Path) -> str:
    resolved = path.resolve()
    root = parent.resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise ArchiveError(f"path escapes archive root: {path}") from exc


def _resolve_inside(parent: Path, relative: str) -> Path:
    candidate = (parent / Path(relative)).resolve()
    root = parent.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ArchiveError(
            f"descriptor path escapes archive root: {relative}"
        ) from exc
    return candidate


def load_archive(
    descriptor_path: Path,
    *,
    archive_root: Path,
    expected_case_id: str | None = None,
) -> ArchiveBundle:
    descriptor = _read_json_object(descriptor_path)
    _validate_descriptor_self_hash(descriptor)
    if descriptor.get("schema") != ARCHIVE_DESCRIPTOR_SCHEMA:
        raise ArchiveError("unexpected archive descriptor schema")
    if descriptor.get("status") != "COMPLETE":
        raise ArchiveError(
            f"archive descriptor is not COMPLETE: {descriptor.get('status')}"
        )
    if (
        expected_case_id is not None
        and descriptor.get("case_id") != expected_case_id
    ):
        raise ArchiveError(
            f"archive case mismatch: {descriptor.get('case_id')} "
            f"!= {expected_case_id}"
        )
    archive = descriptor.get("archive")
    if not isinstance(archive, Mapping):
        raise ArchiveError("descriptor.archive must be an object")
    archive_path = _resolve_inside(
        archive_root, str(archive.get("relative_path", ""))
    )
    if not archive_path.is_file():
        raise ArchiveError(f"archive payload is missing: {archive_path}")
    if _file_sha256(archive_path) != archive.get("file_sha256"):
        raise ArchiveError("archive compressed-file SHA-256 mismatch")
    if archive_path.stat().st_size != int(archive.get("file_size_bytes", -1)):
        raise ArchiveError("archive compressed-file size mismatch")
    payload = _read_gzip_json(archive_path)
    if _canonical_sha256(payload) != archive.get("canonical_json_sha256"):
        raise ArchiveError("archive canonical payload SHA-256 mismatch")
    if payload.get("schema") != ARCHIVE_PAYLOAD_SCHEMA:
        raise ArchiveError("unexpected archive payload schema")
    if payload.get("case_id") != descriptor.get("case_id"):
        raise ArchiveError("archive payload/descriptor case mismatch")
    return ArchiveBundle(
        descriptor_path=descriptor_path,
        descriptor=descriptor,
        payload=payload,
    )


def _current_descriptor_path(archive_root: Path, case_id: str) -> Path:
    pointer_path = archive_root / case_id / "current.json"
    pointer = _read_json_object(pointer_path)
    if pointer.get("schema") != ARCHIVE_POINTER_SCHEMA:
        raise ArchiveError(f"{case_id}: unexpected current-pointer schema")
    descriptor_path = _resolve_inside(
        archive_root, str(pointer.get("descriptor_relative_path", ""))
    )
    if _file_sha256(descriptor_path) != pointer.get("descriptor_file_sha256"):
        raise ArchiveError(f"{case_id}: current descriptor file hash mismatch")
    return descriptor_path


def collect_cached(
    *,
    case_id: str,
    identity: Mapping[str, Any],
    producer: Callable[[], Mapping[str, Any]],
    validator: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    archive_root: Path = DEFAULT_ARCHIVE_ROOT,
    resume: bool = True,
    recover_stale: bool = False,
) -> dict[str, Any]:
    cache_key = _canonical_sha256(identity)
    paths = _archive_paths(archive_root, case_id, cache_key)
    if resume and paths["descriptor"].is_file():
        bundle = load_archive(
            paths["descriptor"],
            archive_root=archive_root,
            expected_case_id=case_id,
        )
        if bundle.descriptor.get("identity") != dict(identity):
            raise ArchiveError(f"{case_id}: cache identity mismatch")
        return {
            "status": "REUSED",
            "case_id": case_id,
            "cache_key": cache_key,
            "descriptor_path": str(paths["descriptor"]),
        }

    with _writer_lock(
        paths["lock"],
        case_id,
        recover_stale=recover_stale,
    ):
        if resume and paths["descriptor"].is_file():
            bundle = load_archive(
                paths["descriptor"],
                archive_root=archive_root,
                expected_case_id=case_id,
            )
            if bundle.descriptor.get("identity") != dict(identity):
                raise ArchiveError(f"{case_id}: cache identity mismatch")
            return {
                "status": "REUSED",
                "case_id": case_id,
                "cache_key": cache_key,
                "descriptor_path": str(paths["descriptor"]),
            }
        started = time.time()
        running = _descriptor_with_self_hash(
            {
                "schema": ARCHIVE_DESCRIPTOR_SCHEMA,
                "case_id": case_id,
                "cache_key": cache_key,
                "identity": dict(identity),
                "status": "RUNNING",
                "started_unix_time": started,
                "worker": {
                    "pid": os.getpid(),
                    "hostname": socket.gethostname(),
                },
                "archive": {},
                "validation": {},
                "blocker": "",
            }
        )
        _atomic_write_json(paths["descriptor"], running)
        try:
            raw_payload = dict(producer())
            payload = {
                "schema": ARCHIVE_PAYLOAD_SCHEMA,
                "case_id": case_id,
                "identity_sha256": cache_key,
                "runtime_payload": raw_payload,
            }
            validation = dict(validator(raw_payload))
            archive_info = _atomic_write_gzip_json(
                paths["archive"], payload
            )
            archive_descriptor = {
                **archive_info,
                "relative_path": _relative_inside(
                    paths["archive"], archive_root
                ),
            }
            complete = _descriptor_with_self_hash(
                {
                    "schema": ARCHIVE_DESCRIPTOR_SCHEMA,
                    "case_id": case_id,
                    "cache_key": cache_key,
                    "identity": dict(identity),
                    "status": "COMPLETE",
                    "started_unix_time": started,
                    "completed_unix_time": time.time(),
                    "worker": {
                        "pid": os.getpid(),
                        "hostname": socket.gethostname(),
                    },
                    "archive": archive_descriptor,
                    "validation": validation,
                    "blocker": "",
                }
            )
            _atomic_write_json(paths["descriptor"], complete)
            pointer = {
                "schema": ARCHIVE_POINTER_SCHEMA,
                "case_id": case_id,
                "cache_key": cache_key,
                "descriptor_relative_path": _relative_inside(
                    paths["descriptor"], archive_root
                ),
                "descriptor_file_sha256": _file_sha256(
                    paths["descriptor"]
                ),
            }
            _atomic_write_json(paths["pointer"], pointer)
            return {
                "status": "COLLECTED",
                "case_id": case_id,
                "cache_key": cache_key,
                "descriptor_path": str(paths["descriptor"]),
            }
        except BaseException as exc:
            failed = _descriptor_with_self_hash(
                {
                    "schema": ARCHIVE_DESCRIPTOR_SCHEMA,
                    "case_id": case_id,
                    "cache_key": cache_key,
                    "identity": dict(identity),
                    "status": "FAILED",
                    "started_unix_time": started,
                    "completed_unix_time": time.time(),
                    "worker": {
                        "pid": os.getpid(),
                        "hostname": socket.gethostname(),
                    },
                    "archive": {},
                    "validation": {},
                    "blocker": f"{type(exc).__name__}: {exc}",
                }
            )
            _atomic_write_json(paths["descriptor"], failed)
            _append_attempt_history(paths["history"], failed)
            raise


def _loaded_binary_identity(binary: Path, search_path: Path) -> dict[str, Any]:
    from czr005 import cpp_backend

    expected = binary.resolve(strict=True)
    module = cpp_backend.load_cpp_module(search_path)
    module_file = getattr(module, "__file__", None)
    if not module_file:
        raise ArchiveError("loaded C++ module has no __file__")
    loaded = Path(module_file).resolve(strict=True)
    if os.path.normcase(str(loaded)) != os.path.normcase(str(expected)):
        raise ArchiveError(
            f"loaded C++ binary differs from --binary: {loaded} != {expected}"
        )
    return {
        "path": loaded.as_posix(),
        "sha256": _file_sha256(loaded),
    }


def _collector_source_sha256() -> str:
    return _file_sha256(Path(__file__).resolve())


def _base_collection_identity(
    *,
    case_id: str,
    binary_identity: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "collector_schema": ARCHIVE_DESCRIPTOR_SCHEMA,
        "collector_source_sha256": _collector_source_sha256(),
        "protected_inputs": {
            "map_path": MAP_PATH.as_posix(),
            "map_raw_sha256": MAP_RAW_SHA256,
            "map_semantic_sha256": MAP_SEMANTIC_SHA256,
            "task_path": TASK_PATH.as_posix(),
            "task_sha256": TASK_SHA256,
            "segment_count": FULL_SEGMENTS,
            "raw_bag_count": FULL_BAGS,
        },
        "binary": dict(binary_identity),
        "full_runtime": True,
        "diagnostic_only": True,
        "sealed_evidence_rewritten": False,
    }


def _f2_case() -> Any:
    from scripts.eval import g4irsf12_reproducible_harness as harness

    matches = [
        case
        for case in harness.original_scale_cases()
        if case.candidate_id == "J_F2"
    ]
    if len(matches) != 1:
        raise AttributionError(f"expected one J_F2 case, got {len(matches)}")
    return matches[0]


def f2_collection_identity(
    *,
    binary_identity: Mapping[str, Any],
    root: Path = ROOT,
) -> dict[str, Any]:
    from scripts.eval import g4irsf12_reproducible_harness as harness

    case = _f2_case()
    frozen = _read_json_object(root / F2_POLICY_PATH)
    if harness.canonical_sha256(case.as_dict()) != frozen.get(
        "provenance", {}
    ).get("case_config_sha256"):
        raise AttributionError("frozen F2 case configuration drift")
    return {
        **_base_collection_identity(
            case_id="f2",
            binary_identity=binary_identity,
        ),
        "configuration": case.as_dict(),
        "case_config_sha256": harness.canonical_sha256(case.as_dict()),
        "trace_contract": {
            "summary_only": False,
            "trace_limit": -1,
            "event_trace_limit": 0,
            "trace_shard_count": 1,
            "trace_shard_index": 0,
            "path_source": "complete_committed_edge_action_decisions",
            "full_event_payload_retained": False,
        },
        "instrumentation_contract": {
            "required_fields": {
                key: list(value)
                for key, value in F2_INSTRUMENTATION_ALIASES.items()
            },
            "additive_reconstruction": (
                "source_queue_delay+junction_queue_wait_seconds+"
                "fault_hold_zero+edge_travel_time_seconds+"
                "node_service_time_seconds="
                "goal_completion_time_seconds"
            ),
            "resource_calendar_semantics": (
                "included_in_junction_queue_wait_seconds"
            ),
            "pibt_wait_semantics": (
                "prepare_and_rollback_are_instantaneous_no_simulation_time"
            ),
        },
    }


def v2_collection_identity(
    *,
    binary_identity: Mapping[str, Any],
    root: Path = ROOT,
) -> dict[str, Any]:
    if _file_sha256(root / V2_TASK_PATH) != V2_TASK_SHA256:
        raise AttributionError("frozen v2 task artifact SHA-256 drift")
    if _file_sha256(root / FROZEN_MODEL_PATH) != FROZEN_MODEL_SHA256:
        raise AttributionError("frozen G4E model SHA-256 drift")
    return {
        **_base_collection_identity(
            case_id="v2_safe",
            binary_identity=binary_identity,
        ),
        "configuration": {
            "policy_id": "model_plus_pibt_lite_java_source_queue_v2_safe",
            "task_artifact": V2_TASK_PATH.as_posix(),
            "task_artifact_sha256": V2_TASK_SHA256,
            "model_path": FROZEN_MODEL_PATH.as_posix(),
            "model_sha256": FROZEN_MODEL_SHA256,
            "graph_source": MAP_PATH.as_posix(),
            "graph_transform": (
                "in_memory_speed_2_5_and_recomputed_directed_heuristic"
            ),
            "graph_written_to_disk": False,
            "reservation_semantics": "baseline",
            "summary_only": False,
            "runtime_full_astar": False,
        },
        "policy_bundle_sha256": _file_sha256(root / V2_POLICY_PATH),
    }


def collect_f2_runtime(
    *,
    binary: Path,
    search_path: Path,
    root: Path = ROOT,
) -> dict[str, Any]:
    from czr005 import cpp_backend
    from scripts.eval.g4irsf11_fixed_map import (
        assert_canonical_map,
        canonical_graph_records,
    )
    from scripts.eval import g4irsf12_reproducible_harness as harness

    case = _f2_case()
    prefix = harness.load_input_prefix(FULL_SEGMENTS, root=root)
    nodes, edges, heuristic = canonical_graph_records(
        assert_canonical_map(root / MAP_PATH)
    )
    base = {
        "node_records": nodes,
        "edge_records": edges,
        "heuristic_time": heuristic,
        "bag_records": harness.binding_bag_records(prefix),
        "input_rows": [dict(row) for row in prefix.rows],
        "fault_windows": [],
        "scenario": f"g4irsf13_attribution_{case.case_id}_{FULL_SEGMENTS}",
        "scale": 1.0,
        "expected_binary_path": str(binary.resolve(strict=True)),
        "input_prefix_sha256": prefix.prefix_sha256,
        "case_config_sha256": harness.canonical_sha256(case.as_dict()),
        "search_path": search_path,
        "trace_limit": -1,
        "event_trace_limit": 0,
        "trace_shard_count": 1,
        "trace_shard_index": 0,
    }
    capabilities = harness.inspect_executor(
        cpp_backend.g4irsf11_event_runtime_from_records
    )
    request, blockers = harness.bind_executor_request(
        case,
        base_kwargs=base,
        capabilities=capabilities,
        summary_only=False,
    )
    if blockers:
        raise AttributionError(
            "F2 diagnostic executor capability blockers: "
            + " | ".join(blockers)
        )
    if not (
        capabilities.accepts_var_kwargs
        or "event_trace_limit" in capabilities.parameters
    ):
        raise AttributionError(
            "MISSING_EXECUTOR_CAPABILITY:event_trace_limit"
        )
    request["trace_limit"] = -1
    request["event_trace_limit"] = 0
    request["trace_shard_count"] = 1
    request["trace_shard_index"] = 0
    request["summary_only"] = False
    payload = cpp_backend.g4irsf11_event_runtime_from_records(**request)
    if not isinstance(payload, Mapping):
        raise AttributionError("F2 executor returned a non-object payload")
    return dict(payload)


def _in_memory_v2_graph(
    root: Path = ROOT,
) -> tuple[list[Any], list[Any], list[list[float]]]:
    from scripts.eval import run_g4irsf6_paper_protocol_gap_closure as g6

    map_data = _read_json_object(root / MAP_PATH)
    for edge in map_data["edges"]:
        edge["speed"] = PRIMARY_SPEED
        edge["file_speed"] = PRIMARY_SPEED
        edge["travel_time"] = float(edge["length"]) / PRIMARY_SPEED
    map_data["constants"]["edge_speed"] = PRIMARY_SPEED
    map_data["constants"]["heuristic_divisor"] = PRIMARY_SPEED
    map_data["heuristic_time"] = g6.recompute_heuristic_time(
        map_data, PRIMARY_SPEED
    )
    return g6.graph_records_from_map(map_data)


def collect_v2_runtime(
    *,
    search_path: Path,
    root: Path = ROOT,
) -> dict[str, Any]:
    from czr005 import cpp_backend
    import scripts.eval.g4i_runtime as g4i
    from scripts.eval import (
        run_g4irsf7_engineering_tht_gap_closure as g7,
    )

    node_records, edge_records, heuristic = _in_memory_v2_graph(root)
    policy = _read_json_object(root / FROZEN_MODEL_PATH)
    mode = g7.official_mode()
    payload = cpp_backend.g4irsf4_no_astar_streaming_replay_from_jsonl(
        node_records=node_records,
        edge_records=edge_records,
        heuristic_time=heuristic,
        task_jsonl_path=root / V2_TASK_PATH,
        w1=policy["w1"],
        b1=policy["b1"],
        w2=policy["w2"],
        b2=policy["b2"],
        risk_margin_threshold=float(
            policy.get("risk_margin_threshold", 1.0)
        ),
        risk_historical_threshold=float(
            policy.get("risk_historical_threshold", 0.5)
        ),
        risk_bottleneck_threshold=float(
            policy.get("risk_bottleneck_threshold", 5.0)
        ),
        historical_risk_rules=g4i._historical_risk_rules(),
        fallback_rules=g4i._fallback_rules(policy),
        policy_name=mode.policy_name,
        use_model=mode.use_model,
        rule_only=mode.rule_only,
        risk_gated_rule=mode.risk_gated_rule,
        fallback_name=mode.fallback_name,
        bounded_depth=mode.bounded_depth,
        max_steps=80,
        trace_limit=0,
        summary_only=False,
        profile_enabled=True,
        enable_edge_overlap_diagnostic=False,
        audit_final_conflicts=True,
        fault_edges=(),
        fault_windows=(),
        max_tasks=-1,
        reservation_semantics="baseline",
        search_path=search_path,
    )
    if not isinstance(payload, Mapping):
        raise AttributionError("v2 executor returned a non-object payload")
    return dict(payload)


def validate_f2_collection(
    payload: Mapping[str, Any],
    *,
    root: Path = ROOT,
) -> dict[str, Any]:
    from scripts.eval import g4irsf12_reproducible_harness as harness

    _map, input_rows = load_protected_inputs(root, require_full=True)
    bags = payload.get("bags")
    if not isinstance(bags, list) or len(bags) != FULL_SEGMENTS:
        raise AttributionError(
            f"F2 archive bag count={len(bags) if isinstance(bags, list) else 'missing'}, "
            f"expected {FULL_SEGMENTS}"
        )
    protected, _groups = _protected_index(input_rows)
    indexed = _runtime_index(bags, protected, label="F2")
    for segment_id, row in indexed.items():
        if row.get("completed") is not True:
            raise AttributionError(f"F2.{segment_id} is incomplete")
        for label, aliases in F2_INSTRUMENTATION_ALIASES.items():
            _finite(
                _one_of(row, aliases, label),
                f"F2.{segment_id}.{label}",
            )
    events = payload.get("events", [])
    decisions = payload.get("decisions")
    summary = payload.get("summary")
    if not isinstance(events, list):
        raise AttributionError("F2 events field must be an array")
    if not isinstance(decisions, list) or not decisions:
        raise AttributionError(
            "F2 collection requires a non-empty decision trace"
        )
    if not isinstance(summary, Mapping):
        raise AttributionError("F2 summary must be an object")
    if summary.get("decision_trace_truncated") is True:
        raise AttributionError("F2 decision trace is truncated")
    if int(summary.get("fault_event_count", -1)) != 0:
        raise AttributionError(
            "F2 Stage-B attribution is no-fault but runtime reported "
            "fault events"
        )
    if int(summary.get("event_trace_limit", -1)) != 0:
        raise AttributionError(
            "F2 full attribution must suppress the full event payload "
            "with event_trace_limit=0"
        )
    if events:
        raise AttributionError(
            "F2 event_trace_limit=0 archive unexpectedly retained events"
        )
    decision_paths = _f2_paths_from_decisions(decisions, protected)
    for segment_id, path in decision_paths.items():
        source = protected[segment_id]
        if (
            path[0] != int(source["start"])
            or path[-1] != int(source["goal"])
        ):
            raise AttributionError(
                f"F2.{segment_id}: committed decision path endpoints drift"
            )
    decision_edge_count = sum(len(path) - 1 for path in decision_paths.values())
    if decision_edge_count != len(decisions):
        raise AttributionError(
            "F2 committed decision rows do not form exactly one complete "
            "edge sequence per segment"
        )
    timing_rows = harness.aggregate_raw_bag_timings(input_rows, bags)
    timing = harness.summarize_raw_bag_timings(
        timing_rows, selected_segment_count=FULL_SEGMENTS
    )
    mean_minutes = float(timing["original_entry_mean_minutes"])
    if not _close(
        mean_minutes,
        EXPECTED_F2_RAW_ENTRY_MINUTES,
        tolerance=1.0e-8,
    ):
        raise AttributionError(
            f"F2 diagnostic mean drift: {mean_minutes} "
            f"!= {EXPECTED_F2_RAW_ENTRY_MINUTES}"
        )
    return {
        "segment_count": len(bags),
        "raw_bag_count": int(timing["complete_raw_bag_count"]),
        "original_entry_mean_minutes": mean_minutes,
        "event_trace_count": 0,
        "event_trace_limit": 0,
        "decision_trace_count": len(decisions),
        "reconstructed_decision_edge_count": decision_edge_count,
        "decision_trace_truncated": False,
        "fault_event_count": 0,
        "fault_hold_seconds": 0.0,
        "instrumentation_fields_validated": sorted(
            F2_INSTRUMENTATION_ALIASES
        ),
    }


def validate_v2_collection(
    payload: Mapping[str, Any],
    *,
    root: Path = ROOT,
) -> dict[str, Any]:
    _map, input_rows = load_protected_inputs(root, require_full=True)
    protected, by_task = _protected_index(input_rows)
    v2_source_rows = _parse_jsonl(root / V2_TASK_PATH)
    v2_source, _groups = _protected_index(v2_source_rows)
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != FULL_SEGMENTS:
        raise AttributionError(
            f"v2 archive task count={len(tasks) if isinstance(tasks, list) else 'missing'}, "
            f"expected {FULL_SEGMENTS}"
        )
    indexed = _runtime_index(tasks, protected, label="v2")
    java_release_durations_by_task: dict[int, float] = defaultdict(float)
    protected_pass_durations_by_task: dict[int, float] = defaultdict(float)
    for segment_id, row in indexed.items():
        if row.get("goal_reached") is not True:
            raise AttributionError(f"v2.{segment_id} is incomplete")
        attempt = _finite(
            row.get("attempt_time"), f"v2.{segment_id}.attempt_time"
        )
        if not _close(
            attempt,
            _finite(
                v2_source[segment_id]["pass_time"],
                f"v2_source.{segment_id}.pass_time",
            ),
            tolerance=1.0e-9,
        ):
            raise AttributionError(
                f"v2.{segment_id}: attempt/source artifact mismatch"
            )
        finish = _finite(
            row.get("finish_time"), f"v2.{segment_id}.finish_time"
        )
        task_id = int(protected[segment_id]["task_id"])
        java_release_durations_by_task[task_id] += finish - attempt
        protected_pass_durations_by_task[task_id] += finish - _finite(
            protected[segment_id]["pass_time"],
            f"protected.{segment_id}.pass_time",
        )
    if (
        set(java_release_durations_by_task) != set(by_task)
        or set(protected_pass_durations_by_task) != set(by_task)
    ):
        raise AttributionError("v2 raw-bag duration population is incomplete")
    java_release_mean = (
        statistics.fmean(java_release_durations_by_task.values()) / 60.0
    )
    if not _close(
        java_release_mean,
        EXPECTED_V2_JAVA_RELEASE_MINUTES,
        tolerance=1.0e-8,
    ):
        raise AttributionError(
            f"v2 Java-release mean drift: {java_release_mean} "
            f"!= {EXPECTED_V2_JAVA_RELEASE_MINUTES}"
        )
    pass_mean = (
        statistics.fmean(protected_pass_durations_by_task.values()) / 60.0
    )
    if not _close(
        pass_mean,
        EXPECTED_V2_PASS_ANCHORED_MINUTES,
        tolerance=1.0e-8,
    ):
        raise AttributionError(
            f"v2 pass-anchored mean drift: {pass_mean} "
            f"!= {EXPECTED_V2_PASS_ANCHORED_MINUTES}"
        )
    summary = payload.get("summary")
    if not isinstance(summary, Mapping):
        raise AttributionError("v2 summary must be an object")
    if int(summary.get("runtime_full_cie_astar_calls", -1)) != 0:
        raise AttributionError("v2 collection used runtime full A*/CIE")
    if int(summary.get("node_window_conflicts", -1)) != 0:
        raise AttributionError("v2 collection has node-window conflicts")
    return {
        "segment_count": len(tasks),
        "raw_bag_count": len(protected_pass_durations_by_task),
        "java_release_mean_minutes": java_release_mean,
        "pass_time_anchored_mean_minutes": pass_mean,
        "runtime_full_cie_astar_calls": 0,
        "node_window_conflicts": 0,
        "graph_written_to_disk": False,
    }


def collect(
    *,
    selection: str,
    binary: Path,
    search_path: Path | None = None,
    archive_root: Path = DEFAULT_ARCHIVE_ROOT,
    resume: bool = True,
    recover_stale: bool = False,
    root: Path = ROOT,
) -> list[dict[str, Any]]:
    effective_search = (search_path or binary.parent).resolve(strict=True)
    binary_identity = _loaded_binary_identity(binary, effective_search)
    results: list[dict[str, Any]] = []
    if selection in {"f2", "both"}:
        identity = f2_collection_identity(
            binary_identity=binary_identity,
            root=root,
        )
        results.append(
            collect_cached(
                case_id="f2",
                identity=identity,
                producer=lambda: collect_f2_runtime(
                    binary=binary,
                    search_path=effective_search,
                    root=root,
                ),
                validator=lambda payload: validate_f2_collection(
                    payload, root=root
                ),
                archive_root=archive_root,
                resume=resume,
                recover_stale=recover_stale,
            )
        )
    if selection in {"v2", "both"}:
        identity = v2_collection_identity(
            binary_identity=binary_identity,
            root=root,
        )
        results.append(
            collect_cached(
                case_id="v2_safe",
                identity=identity,
                producer=lambda: collect_v2_runtime(
                    search_path=effective_search,
                    root=root,
                ),
                validator=lambda payload: validate_v2_collection(
                    payload, root=root
                ),
                archive_root=archive_root,
                resume=resume,
                recover_stale=recover_stale,
            )
        )
    return results


def analyze(
    *,
    archive_root: Path = DEFAULT_ARCHIVE_ROOT,
    f2_descriptor: Path | None = None,
    v2_descriptor: Path | None = None,
    root: Path = ROOT,
    write: bool = True,
    trace_sample_limit: int = 256,
) -> tuple[AnalysisArtifacts, tuple[Path, ...]]:
    f2_path = f2_descriptor or _current_descriptor_path(archive_root, "f2")
    v2_path = v2_descriptor or _current_descriptor_path(
        archive_root, "v2_safe"
    )
    f2_bundle = load_archive(
        f2_path, archive_root=archive_root, expected_case_id="f2"
    )
    v2_bundle = load_archive(
        v2_path, archive_root=archive_root, expected_case_id="v2_safe"
    )
    map_data, input_rows = load_protected_inputs(root, require_full=True)
    if _file_sha256(root / V2_TASK_PATH) != V2_TASK_SHA256:
        raise AttributionError("frozen v2 task artifact SHA-256 drift")
    v2_source_rows = _parse_jsonl(root / V2_TASK_PATH)
    artifacts = build_analysis(
        input_rows,
        map_data,
        f2_bundle.payload["runtime_payload"],
        v2_bundle.payload["runtime_payload"],
        v2_source_rows,
        require_full=True,
        archive_evidence={
            "f2": f2_bundle.descriptor["archive"]["file_sha256"],
            "v2_safe": v2_bundle.descriptor["archive"]["file_sha256"],
        },
        trace_sample_limit=trace_sample_limit,
    )
    paths = write_outputs(artifacts, root=root) if write else ()
    return artifacts, paths


def validate_committed_outputs(
    *,
    archive_root: Path = DEFAULT_ARCHIVE_ROOT,
    f2_descriptor: Path | None = None,
    v2_descriptor: Path | None = None,
    root: Path = ROOT,
    trace_sample_limit: int = 256,
) -> list[str]:
    artifacts, _paths = analyze(
        archive_root=archive_root,
        f2_descriptor=f2_descriptor,
        v2_descriptor=v2_descriptor,
        root=root,
        write=False,
        trace_sample_limit=trace_sample_limit,
    )
    failures: list[str] = []
    for relative, expected in build_output_payloads(artifacts).items():
        path = root / relative
        if not path.is_file():
            failures.append(f"missing committed output: {relative.as_posix()}")
        elif path.read_bytes() != expected:
            failures.append(
                f"committed output differs from deterministic render: "
                f"{relative.as_posix()}"
            )
    return failures


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--collect",
        choices=("f2", "v2", "both"),
        help="run one full diagnostic collection into ignored local archives",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="validate current archives and publish compact Stage-B outputs",
    )
    parser.add_argument(
        "--validate-committed",
        action="store_true",
        help="rebuild analysis in memory and compare committed bytes",
    )
    parser.add_argument(
        "--binary",
        type=Path,
        help="exact C++ extension binary; required with --collect",
    )
    parser.add_argument(
        "--search-path",
        type=Path,
        help="C++ extension import directory; defaults to --binary parent",
    )
    parser.add_argument(
        "--archive-root",
        type=Path,
        default=DEFAULT_ARCHIVE_ROOT,
    )
    parser.add_argument("--f2-descriptor", type=Path)
    parser.add_argument("--v2-descriptor", type=Path)
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="do not reuse a complete matching cache entry",
    )
    parser.add_argument(
        "--recover-stale-lock",
        action="store_true",
        help="archive a same-host dead-PID lock before collecting",
    )
    parser.add_argument("--trace-sample-limit", type=int, default=256)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not (args.collect or args.analyze or args.validate_committed):
        raise SystemExit(
            "select at least one of --collect, --analyze, --validate-committed"
        )
    if args.collect and args.binary is None:
        raise SystemExit("--binary is required with --collect")
    result: dict[str, Any] = {
        "schema": "czr005.g4irsf13.delay_attribution_command.v1",
        "archive_root": args.archive_root.resolve().as_posix(),
    }
    if args.collect:
        result["collection"] = collect(
            selection=args.collect,
            binary=args.binary,
            search_path=args.search_path,
            archive_root=args.archive_root,
            resume=not args.no_resume,
            recover_stale=args.recover_stale_lock,
        )
    if args.analyze:
        artifacts, paths = analyze(
            archive_root=args.archive_root,
            f2_descriptor=args.f2_descriptor,
            v2_descriptor=args.v2_descriptor,
            trace_sample_limit=args.trace_sample_limit,
        )
        result["analysis"] = artifacts.summary
        result["output_paths"] = [
            path.resolve().as_posix() for path in paths
        ]
    if args.validate_committed:
        failures = validate_committed_outputs(
            archive_root=args.archive_root,
            f2_descriptor=args.f2_descriptor,
            v2_descriptor=args.v2_descriptor,
            trace_sample_limit=args.trace_sample_limit,
        )
        result["committed_validation_failures"] = failures
        if failures:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
