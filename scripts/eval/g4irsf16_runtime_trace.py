"""Capture deployable G4IRSF16 local features from the frozen E4 F2 runtime.

The native runtime remains in exact F2/off mode.  Every trace shard replays the
same protected input; sharding changes only which decision rows are returned.
When matched-feature capture is requested, the formal G4IRSF15 action-changing
target frame is reduced to identity fields before any runtime row is read.
Outcome labels, offline sampling strata, and whole-system fields are never
copied into the deployable ``features`` object.

The public shadow-scoring seam is :func:`score_shadow_features`.  It consumes
the captured feature rows and cannot change native runtime actions.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT, ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from scripts.eval import g4irsf12_reproducible_harness as g12  # noqa: E402
from scripts.eval.g4irsf11_fixed_map import (  # noqa: E402
    assert_canonical_map,
    canonical_graph_records,
)
from scripts.eval.g4irsf14_opportunity_census import (  # noqa: E402
    DETERMINISTIC_CORE_SUMMARY_FIELDS,
    FROZEN_RUNTIME_CONTROLS,
    MODEL_PATH,
    MODEL_SHA256,
    RAW_HARD_GATE_FIELDS,
)


SCHEMA = "czr005.g4irsf16.runtime_trace_capture.v1"
FEATURE_SCHEMA = "czr005.g4irsf16.matched_local_features.v1"
TARGET_SCHEMA = "czr005.g4irsf16.formal_runtime_target.v1"
FULL_SEGMENTS = 43_603
FORMAL_TARGET_COUNT = 2_172
FORMAL_KIND_COUNTS = {"I3": 1_086, "I4": 1_086}
ALLOWED_SEGMENTS = (144, 512, 2_048, 8_192, FULL_SEGMENTS)
DEFAULT_LABEL_FRAME = (
    ROOT / "artifacts/datasets/g4irsf15_causal_labels.jsonl.zst"
)
DEFAULT_ADDRESS_FRAME = (
    ROOT
    / "artifacts/datasets/g4irsf15_causal_target_address_frame.jsonl.zst"
)
DEFAULT_OUTPUT_DIR = ROOT / "outputs/runtime/g4irsf16"


class RuntimeTraceError(RuntimeError):
    """Raised before publishing an incomplete or non-local trace capture."""


def _portable_path(path: Path, *, root: Path = ROOT) -> str:
    """Return a stable evidence path without publishing a host-local prefix."""

    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return f"EXTERNAL_NATIVE_BINARY/{resolved.name}"


@dataclass(frozen=True)
class FormalTarget:
    """Outcome-free identity needed to join one formal target to live trace."""

    target_index: int
    target_key: str
    descriptor_id: str
    kind: str
    horizon: str
    event_ordinal: int
    event_seq: int
    runtime_bag_id: int

    @property
    def formal_key(self) -> tuple[int, int]:
        return (self.event_ordinal, self.runtime_bag_id)

    @property
    def live_key(self) -> tuple[int, int]:
        # EventDecisionTraceRow exposes the sealed native event sequence, not
        # the all-events processed ordinal used by the causal campaign.
        return (self.event_seq, self.runtime_bag_id)


@dataclass(frozen=True)
class TargetFrame:
    targets: tuple[FormalTarget, ...]
    label_path: Path
    label_sha256: str
    address_path: Path
    address_sha256: str


class ShadowScorer(Protocol):
    """Read-only scoring interface; implementations return a proposal only."""

    def __call__(
        self, feature_row: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...


class TraceShardConsumer(Protocol):
    """Read-only sink for one fully validated native trace shard."""

    def __call__(
        self,
        shard_index: int,
        rows: Sequence[Mapping[str, Any]],
    ) -> None: ...


EventExecutor = Callable[..., Mapping[str, Any]]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeTraceError(message)


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{name} must be an object")
    return value


def _array(value: Any, name: str) -> Sequence[Any]:
    _require(
        isinstance(value, Sequence) and not isinstance(value, (str, bytes)),
        f"{name} must be an array",
    )
    return value


def _integer(value: Any, name: str, minimum: int = 0) -> int:
    _require(
        isinstance(value, int) and not isinstance(value, bool),
        f"{name} must be an integer",
    )
    _require(value >= minimum, f"{name} must be >= {minimum}")
    return value


def _number(value: Any, name: str) -> float | int:
    _require(
        isinstance(value, (int, float)) and not isinstance(value, bool),
        f"{name} must be numeric",
    )
    _require(math.isfinite(float(value)), f"{name} must be finite")
    return value


def _boolean(value: Any, name: str) -> bool:
    _require(isinstance(value, bool), f"{name} must be boolean")
    return value


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
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _rows_sha256(
    rows: Sequence[Mapping[str, Any]],
    *,
    key: Callable[[Mapping[str, Any]], Any],
) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=key):
        digest.update(_canonical_bytes(row))
        digest.update(b"\n")
    return digest.hexdigest()


def _zstandard_module() -> Any:
    try:
        import zstandard
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeTraceError(
            "ZSTANDARD_DEPENDENCY_REQUIRED: install zstandard>=0.23"
        ) from exc
    return zstandard


def _read_jsonl_zst(path: Path, name: str) -> list[Mapping[str, Any]]:
    resolved = path.resolve(strict=True)
    zstandard = _zstandard_module()
    try:
        raw = zstandard.ZstdDecompressor().decompress(resolved.read_bytes())
        text = raw.decode("utf-8")
    except (zstandard.ZstdError, UnicodeError) as exc:
        raise RuntimeTraceError(f"INVALID_ZSTD_JSONL:{name}:{resolved}") from exc
    rows: list[Mapping[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeTraceError(
                f"INVALID_JSONL:{name}:{resolved}:{line_number}"
            ) from exc
        rows.append(_mapping(value, f"{name}[{line_number}]"))
    return rows


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as stream:
            temporary_name = stream.name
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def _write_jsonl_zst(
    path: Path, rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    raw = b"".join(_canonical_bytes(row) + b"\n" for row in rows)
    zstandard = _zstandard_module()
    compressed = zstandard.ZstdCompressor(level=9).compress(raw)
    _atomic_write(path, compressed)
    return {
        "path": _portable_path(path),
        "row_count": len(rows),
        "encoding": "CANONICAL_JSONL_ZSTD",
        "content_sha256": hashlib.sha256(raw).hexdigest(),
        "sha256": hashlib.sha256(compressed).hexdigest(),
        "byte_count": len(compressed),
    }


def load_formal_target_frame(
    *,
    label_path: Path = DEFAULT_LABEL_FRAME,
    address_path: Path = DEFAULT_ADDRESS_FRAME,
    require_formal_counts: bool = True,
) -> TargetFrame:
    """Load only target identities; discard all causal outcome columns."""

    label_path = label_path.resolve(strict=True)
    address_path = address_path.resolve(strict=True)
    labels = _read_jsonl_zst(label_path, "formal_label_frame")
    addresses = _read_jsonl_zst(address_path, "target_address_frame")

    address_by_descriptor: dict[str, Mapping[str, Any]] = {}
    for index, address in enumerate(addresses):
        descriptor_id = address.get("descriptor_id")
        _require(
            isinstance(descriptor_id, str) and bool(descriptor_id),
            f"address[{index}].descriptor_id must be non-empty",
        )
        _require(
            descriptor_id not in address_by_descriptor,
            f"duplicate address descriptor_id: {descriptor_id}",
        )
        address_by_descriptor[descriptor_id] = address

    targets: list[FormalTarget] = []
    seen_target_keys: set[str] = set()
    for index, label in enumerate(labels):
        _require(
            label.get("eligible_causal_label") is True
            and label.get("action_changed") is True,
            f"formal label row {index} is not eligible/action-changing",
        )
        kind = label.get("kind")
        _require(kind in {"I3", "I4"}, f"formal label row {index} kind drift")
        target_key = label.get("target_key")
        descriptor_id = label.get("descriptor_id")
        horizon = label.get("horizon")
        _require(
            isinstance(target_key, str) and bool(target_key),
            f"formal label row {index} missing target_key",
        )
        _require(
            isinstance(descriptor_id, str) and bool(descriptor_id),
            f"formal label row {index} missing descriptor_id",
        )
        _require(
            horizon in {"H_bag", "H_system"},
            f"formal label row {index} horizon drift",
        )
        _require(
            target_key not in seen_target_keys,
            f"duplicate formal target_key: {target_key}",
        )
        seen_target_keys.add(target_key)
        address = address_by_descriptor.get(descriptor_id)
        _require(
            address is not None,
            f"formal target missing address descriptor: {descriptor_id}",
        )
        direct_ids = _array(
            label.get("direct_affected_runtime_bag_ids"),
            f"formal_label[{index}].direct_affected_runtime_bag_ids",
        )
        _require(
            len(direct_ids) == 1,
            f"formal label row {index} must have one direct runtime bag",
        )
        runtime_bag_id = _integer(
            direct_ids[0], f"formal_label[{index}].runtime_bag_id"
        )
        event_ordinal = _integer(
            label.get("event_ordinal"),
            f"formal_label[{index}].event_ordinal",
        )
        address_ordinal = _integer(
            address.get("event_ordinal"),
            f"address[{descriptor_id}].event_ordinal",
        )
        address_runtime_id = _integer(
            address.get("runtime_bag_id"),
            f"address[{descriptor_id}].runtime_bag_id",
        )
        event_seq = _integer(
            address.get("event_seq"), f"address[{descriptor_id}].event_seq"
        )
        _require(
            event_ordinal == address_ordinal,
            f"event ordinal disagreement for {target_key}",
        )
        _require(
            runtime_bag_id == address_runtime_id,
            f"runtime bag disagreement for {target_key}",
        )
        _require(
            address.get("kind") == kind,
            f"intervention kind disagreement for {target_key}",
        )
        targets.append(
            FormalTarget(
                target_index=index,
                target_key=target_key,
                descriptor_id=descriptor_id,
                kind=str(kind),
                horizon=str(horizon),
                event_ordinal=event_ordinal,
                event_seq=event_seq,
                runtime_bag_id=runtime_bag_id,
            )
        )

    if require_formal_counts:
        _require(
            len(targets) == FORMAL_TARGET_COUNT,
            f"formal target count must be {FORMAL_TARGET_COUNT}",
        )
        counts = Counter(target.kind for target in targets)
        _require(
            dict(counts) == FORMAL_KIND_COUNTS,
            f"formal target kind counts drift: {dict(counts)}",
        )
    return TargetFrame(
        targets=tuple(targets),
        label_path=label_path,
        label_sha256=_file_sha256(label_path),
        address_path=address_path,
        address_sha256=_file_sha256(address_path),
    )


def build_runtime_request(
    *,
    node_records: Sequence[Any],
    edge_records: Sequence[Any],
    heuristic_time: Sequence[Any],
    bag_records: Sequence[Any],
    binary: Path,
    search_path: Path,
    model_path: Path,
    segments: int,
    trace_shards: int,
    shard_index: int,
) -> dict[str, Any]:
    """Build the exact frozen E4/M0 F2 request for one trace shard."""

    _require(segments in ALLOWED_SEGMENTS, "unsupported segment count")
    _require(trace_shards > 0, "trace_shards must be positive")
    _require(0 <= shard_index < trace_shards, "invalid trace shard index")
    request = dict(FROZEN_RUNTIME_CONTROLS)
    request.update(
        node_records=node_records,
        edge_records=edge_records,
        heuristic_time=heuristic_time,
        bag_records=bag_records,
        fault_windows=(),
        scenario=(
            f"g4irsf16_f2_off_e4_m0_{segments}_"
            f"trace_shard_{shard_index:03d}_of_{trace_shards:03d}"
        ),
        summary_only=False,
        trace_limit=-1,
        trace_shard_count=trace_shards,
        trace_shard_index=shard_index,
        event_trace_limit=0,
        enable_opportunity_telemetry=False,
        opportunity_trace_limit=0,
        scorer_model_path=model_path,
        expected_binary_path=binary,
        search_path=search_path,
    )
    return request


def _validate_binary_echo(
    payload: Mapping[str, Any], summary: Mapping[str, Any], binary: Path
) -> str:
    expected_path = str(binary.resolve(strict=True))
    expected_sha = _file_sha256(binary)
    for owner, value in (("payload", payload), ("summary", summary)):
        observed_path = value.get("loaded_cpp_binary_path")
        observed_sha = value.get("loaded_cpp_binary_sha256")
        _require(isinstance(observed_path, str), f"{owner} missing binary path")
        _require(
            os.path.normcase(str(Path(observed_path).resolve()))
            == os.path.normcase(expected_path),
            f"{owner} binary path echo mismatch",
        )
        _require(observed_sha == expected_sha, f"{owner} binary SHA mismatch")
    return expected_sha


def _validate_frozen_echo(
    summary: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    trace_shards: int,
    shard_index: int,
) -> None:
    summary_expected = {
        "resource_semantics_echo": "R3_java_node_window_compatible",
        "scorer_mode_echo": "S1_frozen_g4e_legal_local_adapter",
        "scorer_model_sha256": MODEL_SHA256,
        "pibt_mode_echo": "P2",
        "pibt_max_depth": 2,
        "framework_mode_echo": "event_loop_one_step",
        "pressure_mode_echo": "off",
        "admission_mode_echo": "off",
        "source_admission_enabled": False,
        "fault_policy_enabled": True,
        "legacy_pibt_lite_enabled": False,
        "priority_mode_echo": "Q0",
        "event_semantics_echo": "E4_batch_plus_destination_merge_request",
        "merge_grant_rule_echo": "M0",
        "merge_grant_max_pending_requests": 256,
        "merge_grant_lifecycle_limit": 8192,
        "local_queue_capacity": 32,
        "trace_limit": -1,
        "trace_shard_count": trace_shards,
        "trace_shard_index": shard_index,
        "event_trace_limit": 0,
        "opportunity_telemetry_enabled": False,
    }
    context_expected = {
        "resource_semantics_echo": "R3_java_node_window_compatible",
        "scorer_mode_echo": "S1_frozen_g4e_legal_local_adapter",
        "scorer_model_sha256": MODEL_SHA256,
        "pibt_mode_echo": "P2",
        "framework_mode_echo": "event_loop_one_step",
        "pressure_mode_echo": "off",
        "admission_mode_echo": "off",
        "enable_source_admission": False,
        "enable_fault_policy": True,
        "priority_mode_echo": "Q0",
        "event_semantics_echo": "E4_batch_plus_destination_merge_request",
        "merge_grant_rule_echo": "M0",
        "merge_grant_max_pending_requests": 256,
        "merge_grant_lifecycle_limit": 8192,
        "trace_limit": -1,
        "trace_shard_count": trace_shards,
        "trace_shard_index": shard_index,
        "event_trace_limit": 0,
        "opportunity_telemetry_enabled": False,
    }
    for field, expected in summary_expected.items():
        _require(
            summary.get(field) == expected,
            f"frozen summary echo drift: {field}",
        )
    for field, expected in context_expected.items():
        _require(
            context.get(field) == expected,
            f"frozen trace-context echo drift: {field}",
        )


def _hard_gate_projection(
    summary: Mapping[str, Any], *, expected_segments: int
) -> dict[str, Any]:
    missing = [field for field in RAW_HARD_GATE_FIELDS if field not in summary]
    _require(not missing, f"runtime summary missing hard gates: {missing}")
    raw = {field: summary[field] for field in RAW_HARD_GATE_FIELDS}
    runtime_global_scan_count = sum(
        _integer(summary.get(field), field)
        for field in (
            "global_reservation_scan_count",
            "priority_global_scan_count",
            "scorer_runtime_global_scan_count",
            "microphase_runtime_global_scan_count",
            "first_edge_credit_global_scan_count",
        )
    )
    runtime_future_route_read_count = sum(
        _integer(summary.get(field), field)
        for field in (
            "priority_future_route_input_count",
            "scorer_future_route_input_count",
            "first_edge_credit_future_route_count",
        )
    )
    runtime_future_schedule_read_count = _integer(
        summary.get("scorer_future_schedule_input_count"),
        "scorer_future_schedule_input_count",
    )
    teacher_input_count = sum(
        _integer(summary.get(field), field)
        for field in (
            "priority_teacher_input_count",
            "scorer_teacher_input_count",
        )
    )
    live_merge_state_integrity = (
        raw["merge_grant_conservation_holds"] is True
        and raw["merge_grant_active_bijection_holds"] is True
        and raw["merge_grant_runtime_owned_capability"] is True
        and raw["merge_grant_exact_slot_no_future_shift"] is True
        and raw["merge_grant_final_active_unconsumed"] == 0
        and raw["merge_grant_outstanding_request_count"] == 0
    )
    passed = (
        raw["requested_count"] == expected_segments
        and raw["completed_count"] == expected_segments
        and raw["failed_count"] == 0
        and raw["physical_fault_edge_entry_violation_count"] == 0
        and raw["reservation_conflicts"] == 0
        and raw["runtime_full_astar_calls"] == 0
        and runtime_global_scan_count == 0
        and runtime_future_route_read_count == 0
        and runtime_future_schedule_read_count == 0
        and teacher_input_count == 0
        and raw["full_future_routes_stored"] == 0
        and raw["bag_future_path_field_present"] is False
        and raw["max_edges_selected_per_bag_per_decision"] <= 1
        and raw["two_step_reservation_count"] == 0
        and raw["unresolved_deadlock_count"] == 0
        and raw["event_limit_reached"] is False
        and raw["time_limit_reached"] is False
        and raw["merge_grant_stale_arbitration_count"] == 0
        and raw["stale_arbitration_event_count"] == 0
        and raw["artificial_batch_delay_seconds"] == 0.0
        and live_merge_state_integrity
    )
    projection = {
        **raw,
        "runtime_global_scan_count": runtime_global_scan_count,
        "runtime_future_route_read_count": runtime_future_route_read_count,
        "runtime_future_schedule_read_count": runtime_future_schedule_read_count,
        "teacher_input_count": teacher_input_count,
        "live_merge_state_integrity_pass": live_merge_state_integrity,
        "all_live_hard_gates_pass": passed,
    }
    _require(passed, "frozen E4 F2 hard gate failure")
    return projection


def _validate_bag_coverage(
    payload: Mapping[str, Any], expected_segment_ids: Sequence[str]
) -> tuple[str, str]:
    bags_raw = _array(payload.get("bags"), "payload.bags")
    bags = [_mapping(row, f"bags[{index}]") for index, row in enumerate(bags_raw)]
    _require(
        len(bags) == len(expected_segment_ids),
        "runtime bag result count mismatch",
    )
    observed_ids = [str(row.get("segment_id", "")) for row in bags]
    _require(len(set(observed_ids)) == len(bags), "duplicate runtime bag result")
    _require(
        set(observed_ids) == set(expected_segment_ids),
        "runtime bag segment coverage drift",
    )
    _require(
        all(
            row.get("completed") is True
            and row.get("failure_reason") in {"", None}
            for row in bags
        ),
        "runtime contains incomplete/failed bag results",
    )
    junction_raw = _array(payload.get("junction_state"), "payload.junction_state")
    junction = [
        _mapping(row, f"junction_state[{index}]")
        for index, row in enumerate(junction_raw)
    ]
    _require(bool(junction), "junction_state cannot be empty")
    return (
        _rows_sha256(bags, key=lambda row: str(row["segment_id"])),
        _rows_sha256(junction, key=lambda row: int(row["node"])),
    )


def _trace_rows(
    payload: Mapping[str, Any],
    summary: Mapping[str, Any],
    *,
    trace_shards: int,
    shard_index: int,
) -> tuple[list[Mapping[str, Any]], set[int]]:
    decisions_raw = _array(payload.get("decisions"), "payload.decisions")
    holds_raw = _array(payload.get("hold_attempts"), "payload.hold_attempts")
    decisions = [
        _mapping(row, f"decisions[{index}]")
        for index, row in enumerate(decisions_raw)
    ]
    holds = [
        _mapping(row, f"hold_attempts[{index}]")
        for index, row in enumerate(holds_raw)
    ]
    _require(
        summary.get("decision_trace_truncated") is False,
        "decision trace was truncated",
    )
    _require(
        len(decisions) == summary.get("decision_trace_stored_count"),
        "committed decision trace count mismatch",
    )
    _require(
        len(holds) == summary.get("hold_trace_stored_count"),
        "hold trace count mismatch",
    )
    _require(
        len(decisions) + len(holds)
        == summary.get("decision_trace_shard_seen_count"),
        "stored trace is not the complete shard trace",
    )
    _require(
        not _array(payload.get("events"), "payload.events"),
        "generic event trace must remain disabled",
    )
    rows = [*decisions, *holds]
    ordinals: set[int] = set()
    for index, row in enumerate(rows):
        metadata = _mapping(row.get("metadata"), f"trace[{index}].metadata")
        _integer(
            metadata.get("runtime_bag_id"),
            f"trace[{index}].runtime_bag_id",
        )
        # Native append_decision_trace partitions on the original task_id,
        # not the input-ordinal runtime_bag_id.  Storage-in/out segments can
        # share one task_id, so those identities are intentionally different.
        shard_task_id = _integer(
            row.get("task_id"), f"trace[{index}].task_id"
        )
        _require(
            shard_task_id % trace_shards == shard_index,
            f"trace row {index} violates task-id shard partition",
        )
        ordinal = _integer(
            metadata.get("decision_ordinal"),
            f"trace[{index}].decision_ordinal",
        )
        _require(ordinal not in ordinals, "duplicate decision ordinal in shard")
        ordinals.add(ordinal)
        _require(
            row.get("full_astar_used") is False,
            "trace row reports full A* usage",
        )
    return rows, ordinals


def _optional_number(value: Any, name: str) -> float | int | None:
    return None if value is None else _number(value, name)


def extract_deployable_feature_row(
    trace_row: Mapping[str, Any], target: FormalTarget
) -> dict[str, Any]:
    """Project one native row through a strict local-feature allowlist."""

    metadata = _mapping(trace_row.get("metadata"), "trace.metadata")
    observed_event_seq = _integer(
        metadata.get("arrive_event_seq"), "trace.metadata.arrive_event_seq"
    )
    observed_runtime_id = _integer(
        metadata.get("runtime_bag_id"), "trace.metadata.runtime_bag_id"
    )
    _require(
        (observed_event_seq, observed_runtime_id) == target.live_key,
        "trace row does not match formal target live key",
    )
    event_time = _number(trace_row.get("event_time"), "trace.event_time")
    snapshot = _mapping(trace_row.get("local_snapshot"), "trace.local_snapshot")
    current_next_available = _number(
        snapshot.get("next_available_time"),
        "trace.local_snapshot.next_available_time",
    )
    short_history = [
        _integer(value, f"trace.short_history[{index}]")
        for index, value in enumerate(
            _array(trace_row.get("short_history"), "trace.short_history")
        )
    ]
    candidates: list[dict[str, Any]] = []
    for index, raw_candidate in enumerate(
        _array(trace_row.get("candidate_records"), "trace.candidate_records")
    ):
        candidate = _mapping(raw_candidate, f"candidate[{index}]")
        source_features = _mapping(
            candidate.get("features"), f"candidate[{index}].features"
        )
        travel_time = _number(
            source_features.get("travel_time"),
            f"candidate[{index}].travel_time",
        )
        corridor_available = _number(
            source_features.get("corridor_next_available"),
            f"candidate[{index}].corridor_next_available",
        )
        target_available = _number(
            source_features.get("target_next_available"),
            f"candidate[{index}].target_next_available",
        )
        candidates.append(
            {
                "action_next_node": _integer(
                    candidate.get("next_node"), f"candidate[{index}].next_node"
                ),
                "features": {
                    "target_queue_length": _integer(
                        source_features.get("target_queue_length"),
                        f"candidate[{index}].target_queue_length",
                    ),
                    "target_scheduled_incoming": _integer(
                        source_features.get("target_scheduled_incoming"),
                        f"candidate[{index}].target_scheduled_incoming",
                    ),
                    "corridor_next_available": corridor_available,
                    "target_next_available": target_available,
                    "corridor_wait_seconds": max(
                        0.0, float(corridor_available) - float(event_time)
                    ),
                    "target_calendar_delay_seconds": max(
                        0.0,
                        float(target_available)
                        - float(event_time)
                        - float(travel_time),
                    ),
                    "travel_time": travel_time,
                    "static_potential": _number(
                        source_features.get("static_potential"),
                        f"candidate[{index}].static_potential",
                    ),
                    "model_score": _number(
                        candidate.get("model_score"),
                        f"candidate[{index}].model_score",
                    ),
                    "scorer_raw_score": _number(
                        candidate.get("scorer_raw_score"),
                        f"candidate[{index}].scorer_raw_score",
                    ),
                    "scorer_raw_bottleneck": _number(
                        candidate.get("scorer_raw_bottleneck"),
                        f"candidate[{index}].scorer_raw_bottleneck",
                    ),
                    "advertised_fault": _boolean(
                        source_features.get("advertised_fault"),
                        f"candidate[{index}].advertised_fault",
                    ),
                    "shield_allowed": _boolean(
                        candidate.get("shield_allowed"),
                        f"candidate[{index}].shield_allowed",
                    ),
                    "shield_reason": str(candidate.get("shield_reason", "")),
                },
            }
        )
    _require(bool(candidates), "matched target trace has no candidates")
    return {
        "schema": FEATURE_SCHEMA,
        "target": {
            "schema": TARGET_SCHEMA,
            "target_index": target.target_index,
            "target_key": target.target_key,
            "descriptor_id": target.descriptor_id,
            "kind": target.kind,
            "horizon": target.horizon,
            "event_ordinal": target.event_ordinal,
            "event_seq": target.event_seq,
            "runtime_bag_id": target.runtime_bag_id,
        },
        "runtime_match": {
            "match_semantics": (
                "FORMAL_EVENT_ORDINAL_RESOLVED_TO_SEALED_EVENT_SEQ_"
                "PLUS_RUNTIME_BAG_ID"
            ),
            "decision_ordinal": _integer(
                metadata.get("decision_ordinal"),
                "trace.metadata.decision_ordinal",
            ),
            "trace_kind": str(metadata.get("trace_kind", "")),
        },
        "action_context": {
            "current_node": _integer(
                trace_row.get("current_node"), "trace.current_node"
            ),
            "goal_node": _integer(trace_row.get("goal_node"), "trace.goal_node"),
            "candidate_next_nodes": [
                candidate["action_next_node"] for candidate in candidates
            ],
            "f2_model_prediction": trace_row.get("model_prediction"),
            "f2_selected_next": trace_row.get("selected_next"),
        },
        "features": {
            "current_local_queue_length": _integer(
                snapshot.get("junction_queue_length"),
                "trace.local_snapshot.junction_queue_length",
            ),
            "current_next_available_time": current_next_available,
            "current_calendar_wait_seconds": max(
                0.0, float(current_next_available) - float(event_time)
            ),
            "short_history": short_history,
            "f2": {
                "model_margin": _number(
                    trace_row.get("model_margin"), "trace.model_margin"
                ),
                "scorer_raw_margin": _optional_number(
                    metadata.get("scorer_raw_margin"),
                    "trace.metadata.scorer_raw_margin",
                ),
                "risk_gate_triggered": _boolean(
                    trace_row.get("risk_gate_triggered"),
                    "trace.risk_gate_triggered",
                ),
                "scorer_risk_abstain": _boolean(
                    metadata.get("scorer_risk_abstain"),
                    "trace.metadata.scorer_risk_abstain",
                ),
            },
            "candidates": candidates,
        },
    }


def score_shadow_features(
    rows: Iterable[Mapping[str, Any]], scorer: ShadowScorer
) -> list[dict[str, Any]]:
    """Score captured rows without any path back into the native runtime."""

    proposals: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        target = _mapping(row.get("target"), f"rows[{index}].target")
        # Target IDs, event ordinals, horizons, and runtime match metadata are
        # deliberately withheld from the scoring callback.  The callback sees
        # only live local action context and the strict feature allowlist.
        scorer_input = {
            "action_context": dict(
                _mapping(row.get("action_context"), f"rows[{index}].action_context")
            ),
            "features": dict(
                _mapping(row.get("features"), f"rows[{index}].features")
            ),
        }
        proposal = scorer(scorer_input)
        _require(
            isinstance(proposal, Mapping),
            f"shadow scorer proposal {index} must be an object",
        )
        proposals.append(
            {
                "target_key": target.get("target_key"),
                "proposal": dict(proposal),
            }
        )
    return proposals


def _resolve_binary(
    binary: Path, search_path: Path | None
) -> tuple[Path, Path]:
    binary = binary.resolve(strict=True)
    _require(
        binary.suffix.lower() in {".pyd", ".so", ".dylib"},
        "--binary must name a native Python extension",
    )
    resolved_search = (
        search_path.resolve(strict=True) if search_path is not None else binary.parent
    )
    _require(
        resolved_search == binary.parent,
        "--search-path must be the exact binary parent",
    )
    return binary, resolved_search


def run_runtime_trace(
    *,
    binary: Path,
    segments: int,
    trace_shards: int,
    allow_full: bool,
    capture_matched_features: bool,
    search_path: Path | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    root: Path = ROOT,
    label_frame: Path = DEFAULT_LABEL_FRAME,
    address_frame: Path = DEFAULT_ADDRESS_FRAME,
    executor: EventExecutor | None = None,
    trace_shard_consumer: TraceShardConsumer | None = None,
) -> dict[str, Any]:
    """Replay exact F2 for every shard, validate, and publish compact capture."""

    _require(segments in ALLOWED_SEGMENTS, "--segments is not in the fixed ladder")
    _require(trace_shards > 0, "--trace-shards must be positive")
    _require(trace_shards <= 64, "--trace-shards must be <= 64")
    if segments == FULL_SEGMENTS:
        _require(allow_full, "full original-1x requires --allow-full")
    if capture_matched_features:
        _require(
            segments == FULL_SEGMENTS and allow_full,
            "formal 2172-row capture requires full original-1x and --allow-full",
        )

    binary, search_path = _resolve_binary(binary, search_path)
    model_path = (root / MODEL_PATH).resolve(strict=True)
    _require(_file_sha256(model_path) == MODEL_SHA256, "frozen scorer model drift")
    prefix = g12.load_input_prefix(segments, root=root)
    expected_segment_ids = [str(row["segment_id"]) for row in prefix.rows]
    nodes, edges, heuristic = canonical_graph_records(assert_canonical_map())
    bag_records = g12.binding_bag_records(prefix)
    if executor is None:
        from czr005.cpp_backend import g4irsf11_event_runtime_from_records

        executor = g4irsf11_event_runtime_from_records

    target_frame: TargetFrame | None = None
    targets_by_live_key: dict[tuple[int, int], list[FormalTarget]] = defaultdict(list)
    if capture_matched_features:
        target_frame = load_formal_target_frame(
            label_path=label_frame,
            address_path=address_frame,
            require_formal_counts=True,
        )
        for target in target_frame.targets:
            targets_by_live_key[target.live_key].append(target)

    reference_digests: dict[str, str] | None = None
    reference_summary: Mapping[str, Any] | None = None
    binary_sha256: str | None = None
    shard_evidence: list[dict[str, Any]] = []
    union_decision_ordinals: set[int] = set()
    matched_live_keys: set[tuple[int, int]] = set()
    captured_by_target_index: dict[int, dict[str, Any]] = {}
    trace_seen_count: int | None = None
    shard_seen_total = 0

    for shard_index in range(trace_shards):
        request = build_runtime_request(
            node_records=nodes,
            edge_records=edges,
            heuristic_time=heuristic,
            bag_records=bag_records,
            binary=binary,
            search_path=search_path,
            model_path=model_path,
            segments=segments,
            trace_shards=trace_shards,
            shard_index=shard_index,
        )
        payload = _mapping(executor(**request), f"shard[{shard_index}] payload")
        summary = _mapping(payload.get("summary"), f"shard[{shard_index}].summary")
        context = _mapping(
            payload.get("trace_context"), f"shard[{shard_index}].trace_context"
        )
        observed_binary_sha = _validate_binary_echo(payload, summary, binary)
        if binary_sha256 is None:
            binary_sha256 = observed_binary_sha
        _require(
            binary_sha256 == observed_binary_sha,
            "runtime binary changed between trace shards",
        )
        _validate_frozen_echo(
            summary,
            context,
            trace_shards=trace_shards,
            shard_index=shard_index,
        )
        hard_gates = _hard_gate_projection(summary, expected_segments=segments)
        bag_sha, junction_sha = _validate_bag_coverage(
            payload, expected_segment_ids
        )
        rows, ordinals = _trace_rows(
            payload,
            summary,
            trace_shards=trace_shards,
            shard_index=shard_index,
        )
        _require(
            union_decision_ordinals.isdisjoint(ordinals),
            "trace shards overlap in decision ordinals",
        )
        union_decision_ordinals.update(ordinals)
        current_seen = _integer(
            summary.get("decision_trace_seen_count"),
            "summary.decision_trace_seen_count",
        )
        if trace_seen_count is None:
            trace_seen_count = current_seen
        _require(
            trace_seen_count == current_seen,
            "decision_trace_seen_count changed between shards",
        )
        shard_seen = _integer(
            summary.get("decision_trace_shard_seen_count"),
            "summary.decision_trace_shard_seen_count",
        )
        shard_seen_total += shard_seen

        missing_core = [
            field
            for field in DETERMINISTIC_CORE_SUMMARY_FIELDS
            if field not in summary
        ]
        _require(
            not missing_core,
            f"summary missing deterministic fields: {missing_core}",
        )
        deterministic_core = {
            field: summary[field]
            for field in dict.fromkeys(DETERMINISTIC_CORE_SUMMARY_FIELDS)
        }
        digests = {
            "deterministic_core_summary_sha256": _canonical_sha256(
                deterministic_core
            ),
            "bag_projection_sha256": bag_sha,
            "junction_state_sha256": junction_sha,
        }
        if reference_digests is None:
            reference_digests = digests
            reference_summary = dict(summary)
        _require(
            digests == reference_digests,
            f"F2 replay digest disagreement at trace shard {shard_index}",
        )

        if target_frame is not None:
            for trace_row in rows:
                metadata = _mapping(trace_row.get("metadata"), "trace.metadata")
                live_key = (
                    _integer(
                        metadata.get("arrive_event_seq"),
                        "trace.metadata.arrive_event_seq",
                    ),
                    _integer(
                        metadata.get("runtime_bag_id"),
                        "trace.metadata.runtime_bag_id",
                    ),
                )
                targets = targets_by_live_key.get(live_key)
                if not targets:
                    continue
                _require(
                    live_key not in matched_live_keys,
                    f"multiple runtime rows match formal live key {live_key}",
                )
                matched_live_keys.add(live_key)
                for target in targets:
                    _require(
                        target.target_index not in captured_by_target_index,
                        f"duplicate captured formal target {target.target_key}",
                    )
                    captured_by_target_index[target.target_index] = (
                        extract_deployable_feature_row(trace_row, target)
                    )

        # This seam is downstream of every per-shard native F2 integrity
        # check.  The consumer receives read-only trace content and has no
        # reference to the executor or request, so it cannot feed an action
        # back into the native run.
        if trace_shard_consumer is not None:
            trace_shard_consumer(shard_index, tuple(rows))

        shard_evidence.append(
            {
                "shard_index": shard_index,
                "trace_shard_count": trace_shards,
                "decision_trace_seen_count": current_seen,
                "decision_trace_shard_seen_count": shard_seen,
                "decision_trace_stored_count": summary.get(
                    "decision_trace_stored_count"
                ),
                "hold_trace_stored_count": summary.get("hold_trace_stored_count"),
                "decision_trace_truncated": False,
                "hard_gates": hard_gates,
                **digests,
            }
        )

    _require(trace_seen_count is not None, "no runtime trace shards executed")
    _require(
        shard_seen_total == trace_seen_count,
        "trace shard union count does not equal complete decision trace count",
    )
    _require(
        len(union_decision_ordinals) == trace_seen_count,
        "decision ordinal union is incomplete",
    )
    _require(reference_digests is not None, "missing reference F2 digests")
    _require(reference_summary is not None, "missing reference F2 summary")
    _require(binary_sha256 is not None, "missing runtime binary SHA")

    stem = f"g4irsf16_f2_off_e4_m0_{segments}_shards{trace_shards}"
    output_dir = output_dir.resolve()
    feature_artifact: dict[str, Any] | None = None
    if target_frame is not None:
        _require(
            len(captured_by_target_index) == len(target_frame.targets),
            "formal target capture incomplete: "
            f"{len(captured_by_target_index)}/{len(target_frame.targets)}",
        )
        feature_rows = [
            captured_by_target_index[index]
            for index in range(len(target_frame.targets))
        ]
        feature_artifact = _write_jsonl_zst(
            output_dir / f"{stem}.matched_features.jsonl.zst",
            feature_rows,
        )

    portable_binary_path = _portable_path(binary)
    portable_runtime_summary = dict(reference_summary)
    if "loaded_cpp_binary_path" in portable_runtime_summary:
        portable_runtime_summary["loaded_cpp_binary_path"] = portable_binary_path

    metadata: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "PASS_FROZEN_F2_OFF_TRACE_CAPTURE",
        "execution_mode": "F2_OFF_EXACT_NO_SUPERVISOR_ACTION",
        "segments": segments,
        "trace_shards": trace_shards,
        "runtime_tuple": {
            "resource": "R3_java_node_window_compatible",
            "scorer": "S1_frozen_g4e_legal_local_adapter",
            "pibt": "P2",
            "admission": "off",
            "priority": "Q0",
            "event_semantics": "E4_batch_plus_destination_merge_request",
            "merge_grant_rule": "M0",
        },
        "binary": {
            "path": portable_binary_path,
            "sha256": binary_sha256,
        },
        "input": {
            "segment_count": segments,
            "raw_bag_count": prefix.raw_bag_count,
            "prefix_sha256": prefix.prefix_sha256,
        },
        "trace_integrity": {
            "decision_trace_seen_count": trace_seen_count,
            "shard_seen_total": shard_seen_total,
            "unique_decision_ordinal_count": len(union_decision_ordinals),
            "all_shards_untruncated": True,
            "all_shard_replay_digests_equal": True,
            **reference_digests,
        },
        "shards": shard_evidence,
        "runtime_summary": portable_runtime_summary,
        "capture": {
            "requested": capture_matched_features,
            "feature_schema": FEATURE_SCHEMA,
            "feature_allowlist": {
                "current": [
                    "current_local_queue_length",
                    "current_next_available_time",
                    "current_calendar_wait_seconds",
                    "short_history",
                ],
                "f2": [
                    "model_margin",
                    "scorer_raw_margin",
                    "risk_gate_triggered",
                    "scorer_risk_abstain",
                ],
                "candidate": [
                    "target_queue_length",
                    "target_scheduled_incoming",
                    "corridor_next_available",
                    "target_next_available",
                    "corridor_wait_seconds",
                    "target_calendar_delay_seconds",
                    "travel_time",
                    "static_potential",
                    "model_score",
                    "scorer_raw_score",
                    "scorer_raw_bottleneck",
                    "advertised_fault",
                    "shield_allowed",
                    "shield_reason",
                ],
            },
            "forbidden_feature_sources": [
                "causal_outcome_labels",
                "signed_label",
                "delta_metrics",
                "offline_sampling_metadata",
                "coverage_tags",
                "global_queue_or_task_scan",
                "active_merge_capability_count",
                "pending_merge_request_count",
                "whole_system_outcomes",
            ],
            "target_match_semantics": (
                "READ_FORMAL_EVENT_ORDINAL_AND_RUNTIME_BAG_ID;_"
                "RESOLVE_ORDINAL_TO_SEALED_EVENT_SEQ_FOR_NATIVE_TRACE_JOIN"
            ),
            "formal_target_count": (
                len(target_frame.targets) if target_frame is not None else 0
            ),
            "matched_target_count": len(captured_by_target_index),
            "feature_artifact": feature_artifact,
        },
    }
    if target_frame is not None:
        metadata["capture"]["target_frames"] = {
            "formal_label_frame": {
                "path": _portable_path(target_frame.label_path),
                "sha256": target_frame.label_sha256,
                "row_count": len(target_frame.targets),
                "outcome_columns_copied_to_features": False,
            },
            "address_frame": {
                "path": _portable_path(target_frame.address_path),
                "sha256": target_frame.address_sha256,
            },
        }
    metadata_path = output_dir / f"{stem}.metadata.json"
    metadata["metadata_path"] = _portable_path(metadata_path)
    _atomic_write(
        metadata_path,
        json.dumps(
            metadata,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n",
    )
    return metadata


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--search-path", type=Path)
    parser.add_argument(
        "--segments", type=int, choices=ALLOWED_SEGMENTS, required=True
    )
    parser.add_argument("--trace-shards", type=int, default=1)
    parser.add_argument("--allow-full", action="store_true")
    parser.add_argument("--capture-matched-features", action="store_true")
    parser.add_argument("--label-frame", type=Path, default=DEFAULT_LABEL_FRAME)
    parser.add_argument(
        "--address-frame", type=Path, default=DEFAULT_ADDRESS_FRAME
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    metadata = run_runtime_trace(
        binary=args.binary,
        search_path=args.search_path,
        segments=args.segments,
        trace_shards=args.trace_shards,
        allow_full=args.allow_full,
        capture_matched_features=args.capture_matched_features,
        label_frame=args.label_frame,
        address_frame=args.address_frame,
        output_dir=args.output_dir,
    )
    print(
        json.dumps(
            {
                "status": metadata["status"],
                "segments": metadata["segments"],
                "trace_shards": metadata["trace_shards"],
                "decision_trace_seen_count": metadata["trace_integrity"][
                    "decision_trace_seen_count"
                ],
                "matched_target_count": metadata["capture"][
                    "matched_target_count"
                ],
                "metadata_path": metadata["metadata_path"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through CLI
    raise SystemExit(main())
