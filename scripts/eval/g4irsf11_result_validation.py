"""Strict v3 result and execution-descriptor validation for G4IRSF11.

The event runtime produces scientific evidence, not a best-effort cache.  This
module therefore keeps serialization, hashing, and semantic validation in one
place so a descriptor can only advertise ``EXECUTED`` after the complete
result bundle has been checked.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable, Mapping, Sequence
import uuid

from scripts.eval.g4irsf11_experiment_protocol import CAPACITY_SLO, FAULT_SLO


RESULT_SCHEMA = "czr005.g4irsf11.event_runtime_result.v3"
EXECUTION_DESCRIPTOR_SCHEMA = "czr005.g4irsf11.event_runtime_execution_descriptor.v3"
JUNCTION_LOCAL_STATE_ACCOUNTING_SEMANTICS = (
    "cpp_object_plus_live_deque_payload_plus_calendar_capacity_lower_bound"
)
JUNCTION_SERVICE_UTILIZATION_SEMANTICS = (
    "cumulative_service_reserved_seconds_over_first_start_to_last_end_reservation_span"
)
JUNCTION_BOTTLENECK_SCORE_SEMANTICS = (
    "peak_source_queue_length_plus_peak_junction_queue_length_plus_"
    "peak_service_calendar_intervals_plus_service_utilization;"
    "rank_by_score_desc_then_peak_local_state_accounted_bytes_desc_then_node_asc"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_NONFINITE_TOKENS = {"NAN", "INF", "+INF", "-INF", "INFINITY", "+INFINITY", "-INFINITY"}

WORKER_RUNTIME_DEFAULTS: dict[str, Any] = {
    "retry_interval": 0.25,
    "minimum_service_seconds": 0.001,
    "dispatch_headway_seconds": 0.001,
    "history_limit": 8,
    "max_decisions_per_bag": 512,
    "max_simulation_time": -1.0,
    "trace_shard_count": 1,
    "trace_shard_index": 0,
    "local_queue_capacity": 0,
    "deadlock_retry_threshold": 8,
}

WORKER_CONFIG_KEYS = (
    "queue_discipline",
    "retry_interval",
    "minimum_service_seconds",
    "dispatch_headway_seconds",
    "history_limit",
    "max_decisions_per_bag",
    "max_events",
    "max_simulation_time",
    "trace_limit",
    "trace_shard_count",
    "trace_shard_index",
    "local_queue_capacity",
    "deadlock_retry_threshold",
    "diagnostic_hops",
    "enable_source_admission",
    "enable_backpressure",
    "enable_pibt_lite",
    "enable_deadlock_escape",
    "enable_fault_policy",
    "max_backlog_slope_fraction",
    "max_drain_seconds",
    "max_p95_service_seconds",
    "max_p99_service_seconds",
    "max_deadline_miss_rate",
    "starvation_seconds",
    "max_fault_recovery_seconds",
)


def runtime_config_from_namespace(args: Any) -> dict[str, Any]:
    """Extract every runtime-affecting CLI value into the result echo."""

    missing = [name for name in WORKER_CONFIG_KEYS if not hasattr(args, name)]
    if missing:
        raise ValueError(f"worker namespace is missing config fields: {missing}")
    return {name: getattr(args, name) for name in WORKER_CONFIG_KEYS}


def canonical_json_bytes(value: Any) -> bytes:
    """Return the only byte representation used for protocol hashing."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def json_document_bytes(value: Any) -> bytes:
    """Return deterministic human-readable JSON document bytes."""

    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def canonical_jsonl_line(row: Mapping[str, Any]) -> bytes:
    return canonical_json_bytes(dict(row)) + b"\n"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_manifest_sha256(manifest: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(dict(manifest)))


def canonical_jsonl_sha256(rows: Iterable[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(canonical_jsonl_line(row))
    return digest.hexdigest()


def _atomic_replace(path: Path, payload: bytes) -> None:
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


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    _atomic_replace(path, payload)


def atomic_write_text(path: Path, value: str) -> None:
    _atomic_replace(path, value.encode("utf-8"))


def atomic_write_json(path: Path, value: Mapping[str, Any] | Sequence[Any]) -> None:
    _atomic_replace(path, json_document_bytes(value))


def atomic_write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    count = 0
    try:
        with os.fdopen(descriptor, "wb") as handle:
            for row in rows:
                handle.write(canonical_jsonl_line(row))
                count += 1
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return count


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def read_json_object(path: Path) -> dict[str, Any]:
    return parse_json_object(path.read_text(encoding="utf-8"), label=str(path))


def _parse_json(value: str) -> Any:
    return json.loads(
        value,
        parse_constant=_reject_constant,
        object_pairs_hook=_unique_object,
    )


def parse_json_object(value: str, *, label: str = "JSON") -> dict[str, Any]:
    parsed = _parse_json(value)
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must contain one JSON object")
    return parsed


def read_json_array(path: Path) -> list[dict[str, Any]]:
    parsed = _parse_json(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, list) or not all(isinstance(row, dict) for row in parsed):
        raise ValueError(f"{path} must contain an array of JSON objects")
    return [dict(row) for row in parsed]


def parse_json_array(value: str, *, label: str = "JSON") -> list[dict[str, Any]]:
    parsed = _parse_json(value)
    if not isinstance(parsed, list) or not all(isinstance(row, dict) for row in parsed):
        raise ValueError(f"{label} must contain an array of JSON objects")
    return [dict(row) for row in parsed]


def count_jsonl_rows(path: Path) -> int:
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(
                line,
                parse_constant=_reject_constant,
                object_pairs_hook=_unique_object,
            )
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: JSONL row must be an object")
            count += 1
    return count


def artifact_binding(
    path: Path,
    *,
    state: str = "present",
    row_count: int | None = None,
) -> dict[str, Any]:
    resolved = str(path.resolve())
    if state != "present":
        if state not in {"empty", "not_requested"}:
            raise ValueError(f"unsupported artifact state: {state}")
        return {
            "path": resolved,
            "state": state,
            "sha256": "",
            "size_bytes": 0,
            "row_count": 0 if row_count is None else int(row_count),
        }
    if not path.is_file():
        raise FileNotFoundError(path)
    binding = {
        "path": resolved,
        "state": "present",
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }
    if row_count is not None:
        binding["row_count"] = int(row_count)
    return binding


def workload_binding(path: Path, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    releases = [_finite_number(row.get("release_time"), "release_time") for row in rows]
    minimum = min(releases) if releases else 0.0
    maximum = max(releases) if releases else 0.0
    return {
        "path": str(path.resolve()),
        "state": "present",
        "sha256": canonical_jsonl_sha256(rows),
        "row_count": len(rows),
        "minimum_release_time": minimum,
        "maximum_release_time": maximum,
        "release_span_seconds": maximum - minimum,
    }


def fault_binding(path: Path, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "state": "empty" if not rows else "present",
        "sha256": sha256_bytes(json_document_bytes([dict(row) for row in rows])),
        "size_bytes": len(json_document_bytes([dict(row) for row in rows])),
        "row_count": len(rows),
    }


@dataclass(frozen=True)
class ResultExpectation:
    run_id: str
    case: Mapping[str, Any]
    protocol_version: str
    protocol_manifest_sha256: str
    input_artifact: Mapping[str, Any]
    fault_artifact: Mapping[str, Any]
    fault_rows: Sequence[Mapping[str, Any]]
    map_sha256: str
    source_sha256: str
    implementation_sha256: str
    config: Mapping[str, Any]
    measurement_cohort: Mapping[str, Any]


def _add(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be numeric, not bool")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _integer(value: Any, label: str) -> int:
    number = _finite_number(value, label)
    if not number.is_integer():
        raise ValueError(f"{label} must be an integer")
    return int(number)


def derive_junction_evidence(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Validate raw C++ junction counters and derive comparable local evidence.

    Utilization uses each junction's actual reservation coverage window, from
    its first reserved service start through its last reserved service end.
    This remains valid when an event/time-limited run has future reservations
    beyond ``summary.end_time``.  The local calendar is non-overlapping, so
    cumulative reserved service may not exceed that window apart from roundoff.
    """
    # A fail-closed event/time limit may fire before the first future release.
    # In that legitimate negative run no junction-local state has been
    # materialized yet, so the exact raw evidence is an empty array.
    if not rows:
        return []

    enriched: list[dict[str, Any]] = []
    seen_nodes: set[int] = set()
    integer_fields = (
        "final_source_queue_length",
        "peak_source_queue_length",
        "final_junction_queue_length",
        "peak_junction_queue_length",
        "final_service_calendar_intervals",
        "peak_service_calendar_intervals",
        "final_local_state_accounted_bytes",
        "peak_local_state_accounted_bytes",
        "service_reservation_count",
        "scheduled_incoming",
    )
    for index, value in enumerate(rows):
        if not isinstance(value, Mapping):
            raise ValueError(f"junction_state[{index}] must be an object")
        node = _integer(value.get("node"), f"junction_state[{index}].node")
        if node < 0:
            raise ValueError(f"junction_state[{index}].node must be non-negative")
        if node in seen_nodes:
            raise ValueError(f"junction_state contains duplicate node {node}")
        seen_nodes.add(node)
        counters = {
            key: _integer(value.get(key), f"junction_state[{index}].{key}")
            for key in integer_fields
        }
        if any(counter < 0 for counter in counters.values()):
            raise ValueError(f"junction_state[{index}] counters must be non-negative")
        for final_key, peak_key in (
            ("final_source_queue_length", "peak_source_queue_length"),
            ("final_junction_queue_length", "peak_junction_queue_length"),
            ("final_service_calendar_intervals", "peak_service_calendar_intervals"),
            ("final_local_state_accounted_bytes", "peak_local_state_accounted_bytes"),
        ):
            if counters[final_key] > counters[peak_key]:
                raise ValueError(
                    f"junction_state[{index}].{peak_key} is below {final_key}"
                )
        if counters["final_local_state_accounted_bytes"] <= 0:
            raise ValueError(
                f"junction_state[{index}].final_local_state_accounted_bytes must be positive"
            )
        if (
            value.get("local_state_accounting_semantics")
            != JUNCTION_LOCAL_STATE_ACCOUNTING_SEMANTICS
        ):
            raise ValueError(
                f"junction_state[{index}].local_state_accounting_semantics mismatch"
            )
        if (
            counters["peak_service_calendar_intervals"]
            > counters["service_reservation_count"]
        ):
            raise ValueError(
                f"junction_state[{index}] calendar peak exceeds reservation count"
            )
        reserved_seconds = _finite_number(
            value.get("cumulative_service_reserved_seconds"),
            f"junction_state[{index}].cumulative_service_reserved_seconds",
        )
        if reserved_seconds < 0.0:
            raise ValueError(
                f"junction_state[{index}].cumulative_service_reserved_seconds must be non-negative"
            )
        first_reservation_start = _finite_number(
            value.get("first_service_reservation_start_time"),
            f"junction_state[{index}].first_service_reservation_start_time",
        )
        last_reservation_end = _finite_number(
            value.get("last_service_reservation_end_time"),
            f"junction_state[{index}].last_service_reservation_end_time",
        )
        if counters["service_reservation_count"] == 0:
            if reserved_seconds != 0.0:
                raise ValueError(
                    f"junction_state[{index}] has service seconds without reservations"
                )
            if first_reservation_start != -1.0 or last_reservation_end != -1.0:
                raise ValueError(
                    f"junction_state[{index}] empty reservation window must use -1 sentinels"
                )
            span = 0.0
            utilization = 0.0
        else:
            if reserved_seconds <= 0.0:
                raise ValueError(
                    f"junction_state[{index}] has reservations without positive service seconds"
                )
            if first_reservation_start < 0.0 or last_reservation_end <= first_reservation_start:
                raise ValueError(
                    f"junction_state[{index}] reservation observation window is invalid"
                )
            span = last_reservation_end - first_reservation_start
            span_tolerance = max(
                1.0e-9,
                abs(span) * 1.0e-9,
                counters["service_reservation_count"] * 1.0e-12,
            )
            if reserved_seconds > span + span_tolerance:
                raise ValueError(
                    f"junction_state[{index}] reserved service exceeds reservation observation span"
                )
            utilization = reserved_seconds / span
            if utilization > 1.0 + 1.0e-9:
                raise ValueError(
                    f"junction_state[{index}].service_utilization exceeds one"
                )
        next_dispatch_time = _finite_number(
            value.get("next_dispatch_time"),
            f"junction_state[{index}].next_dispatch_time",
        )
        if next_dispatch_time < 0.0:
            raise ValueError(
                f"junction_state[{index}].next_dispatch_time must be non-negative"
            )

        score = float(
            counters["peak_source_queue_length"]
            + counters["peak_junction_queue_length"]
            + counters["peak_service_calendar_intervals"]
        ) + utilization
        row = dict(value)
        row.update(
            {
                "service_observation_span_seconds": span,
                "service_utilization": utilization,
                "service_utilization_semantics": JUNCTION_SERVICE_UTILIZATION_SEMANTICS,
                "bottleneck_score": score,
                "bottleneck_score_semantics": JUNCTION_BOTTLENECK_SCORE_SEMANTICS,
            }
        )
        enriched.append(row)

    ranked = sorted(
        enriched,
        key=lambda row: (
            -float(row["bottleneck_score"]),
            -int(row["peak_local_state_accounted_bytes"]),
            int(row["node"]),
        ),
    )
    rank_by_node = {int(row["node"]): rank for rank, row in enumerate(ranked, start=1)}
    for row in enriched:
        row["bottleneck_rank"] = rank_by_node[int(row["node"])]
    return enriched


def _walk_finite(value: Any, label: str, errors: list[str]) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        errors.append(f"{label} is non-finite")
    elif isinstance(value, str) and value.strip().upper() in _NONFINITE_TOKENS:
        errors.append(f"{label} encodes a forbidden non-finite token")
    elif isinstance(value, Mapping):
        for key, child in value.items():
            _walk_finite(child, f"{label}.{key}", errors)
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _walk_finite(child, f"{label}[{index}]", errors)


def _mapping(value: Any, label: str, errors: list[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        errors.append(f"{label} must be an object")
        return {}
    return value


def _validate_sha(value: Any, label: str, errors: list[str]) -> None:
    _add(errors, isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None, f"{label} must be lowercase sha256")


def _validate_capacity_metrics(
    label: str,
    metrics_value: Any,
    *,
    expected_count: int,
    expected_completed: int | None = None,
    expected_failed: int | None = None,
    summary: Mapping[str, Any],
    errors: list[str],
) -> None:
    metrics = _mapping(metrics_value, label, errors)
    try:
        bag_count = _integer(metrics.get("bag_count"), f"{label}.bag_count")
        complete_count = _integer(metrics.get("complete_count"), f"{label}.complete_count")
        failed_count = _integer(metrics.get("failed_count"), f"{label}.failed_count")
        _add(errors, bag_count == expected_count, f"{label}.bag_count != expected count")
        _add(errors, complete_count + failed_count == bag_count, f"{label} completion counters do not partition bag_count")
        _add(errors, all(value >= 0 for value in (bag_count, complete_count, failed_count)), f"{label} counters must be non-negative")
        if expected_completed is not None:
            _add(
                errors,
                complete_count == expected_completed,
                f"{label}.complete_count != runtime completed_count",
            )
        if expected_failed is not None:
            _add(
                errors,
                failed_count == expected_failed,
                f"{label}.failed_count != runtime failed_count",
            )

        projections = {
            "conflict_count": "reservation_conflicts",
            "deadlock_count": "deadlock_count",
            "loop_count": "loop_count",
            "runtime_full_astar_calls": "runtime_full_astar_calls",
            "event_count": "event_count",
            "decision_count": "decision_count",
        }
        for metric_key, summary_key in projections.items():
            _add(
                errors,
                _integer(metrics.get(metric_key), f"{label}.{metric_key}")
                == _integer(summary.get(summary_key), f"summary.{summary_key}"),
                f"{label}.{metric_key} != summary.{summary_key}",
            )
        for metric_key, summary_key in (
            ("runtime_seconds", "runtime_seconds"),
            ("decision_latency_us_p50", "decision_latency_us_p50"),
            ("decision_latency_us_p95", "decision_latency_us_p95"),
            ("decision_latency_us_p99", "decision_latency_us_p99"),
        ):
            _add(
                errors,
                _finite_number(metrics.get(metric_key), f"{label}.{metric_key}")
                == _finite_number(summary.get(summary_key), f"summary.{summary_key}"),
                f"{label}.{metric_key} != summary.{summary_key}",
            )

        _add(
            errors,
            _finite_number(metrics.get("gate_max_backlog_slope_fraction"), f"{label}.gate_max_backlog_slope_fraction")
            == float(CAPACITY_SLO["max_backlog_slope_fraction"]),
            f"{label} backlog slope gate differs from protocol",
        )
        gate_pairs = (
            ("gate_max_drain_seconds", "max_drain_seconds"),
            ("gate_max_p95_total_seconds", "max_p95_service_seconds"),
            ("gate_max_p99_total_seconds", "max_p99_service_seconds"),
            ("gate_max_deadline_miss_rate", "max_deadline_miss_rate"),
            ("gate_starvation_seconds", "starvation_seconds"),
        )
        for metric_key, protocol_key in gate_pairs:
            _add(
                errors,
                _finite_number(metrics.get(metric_key), f"{label}.{metric_key}")
                == float(CAPACITY_SLO[protocol_key]),
                f"{label}.{metric_key} differs from protocol",
            )

        tolerance = _finite_number(
            metrics.get("gate_backlog_slope_numerical_tolerance_per_second"),
            f"{label}.gate_backlog_slope_numerical_tolerance_per_second",
        )
        slope = _finite_number(metrics.get("backlog_slope_per_second"), f"{label}.backlog_slope_per_second")
        expected_slope_pass = slope <= tolerance
        expected_drain_pass = (
            _integer(metrics.get("end_backlog"), f"{label}.end_backlog") == 0
            and _finite_number(metrics.get("drain_time_seconds"), f"{label}.drain_time_seconds")
            <= float(CAPACITY_SLO["max_drain_seconds"])
        )
        expected_safe = (
            _integer(metrics.get("conflict_count"), f"{label}.conflict_count") == 0
            and _integer(metrics.get("runtime_full_astar_calls"), f"{label}.runtime_full_astar_calls") == 0
            and metrics.get("safety_evidence_status") == "PASS"
            and not list(metrics.get("missing_required_summary_fields") or [])
        )
        expected_service = (
            complete_count == bag_count
            and _finite_number(metrics.get("service_time_p95_seconds"), f"{label}.service_time_p95_seconds")
            <= float(CAPACITY_SLO["max_p95_service_seconds"])
            and _finite_number(metrics.get("service_time_p99_seconds"), f"{label}.service_time_p99_seconds")
            <= float(CAPACITY_SLO["max_p99_service_seconds"])
            and _finite_number(metrics.get("deadline_miss_rate"), f"{label}.deadline_miss_rate")
            <= float(CAPACITY_SLO["max_deadline_miss_rate"])
            and _integer(metrics.get("starvation_count"), f"{label}.starvation_count") == 0
        )
        _add(errors, metrics.get("queue_slope_pass") is expected_slope_pass, f"{label}.queue_slope_pass inconsistent")
        _add(errors, metrics.get("queue_drain_pass") is expected_drain_pass, f"{label}.queue_drain_pass inconsistent")
        _add(
            errors,
            metrics.get("queue_stability_pass") is (expected_slope_pass and expected_drain_pass),
            f"{label}.queue_stability_pass inconsistent",
        )
        _add(errors, metrics.get("safe_execution_pass") is expected_safe, f"{label}.safe_execution_pass inconsistent")
        _add(errors, metrics.get("service_level_pass") is expected_service, f"{label}.service_level_pass inconsistent")
        _add(
            errors,
            metrics.get("capacity_pass")
            is (expected_safe and expected_slope_pass and expected_drain_pass and expected_service),
            f"{label}.capacity_pass inconsistent",
        )
    except ValueError as exc:
        errors.append(str(exc))


def _validate_continuity(
    result: Mapping[str, Any],
    expectation: ResultExpectation,
    workload_rows: Sequence[Mapping[str, Any]] | None,
    errors: list[str],
) -> None:
    case = expectation.case
    scale = float(case.get("scale", 0.0))
    required = case.get("workload_mode") == "rolling_multiday_carryover" and scale in {2.0, 7.0}
    continuity = result.get("continuity_metrics")
    if not required:
        _add(errors, continuity in (None, {}), "continuity_metrics is only allowed for rolling scale 2/7")
        return
    metrics = _mapping(continuity, "continuity_metrics", errors)
    expected_copies = int(scale)
    _add(errors, metrics.get("status") == "PASS", "continuity_metrics.status must be PASS")
    _add(errors, list(metrics.get("blockers") or []) == [], "continuity_metrics.blockers must be empty")
    _add(errors, metrics.get("runtime_instance_id") == expectation.run_id, "continuity runtime_instance_id != run_id")
    _add(errors, metrics.get("single_runtime_invocation_pass") is True, "continuity single runtime invocation not proven")
    try:
        boundary_count = _integer(metrics.get("boundary_count"), "continuity_metrics.boundary_count")
        boundaries = metrics.get("boundaries")
        _add(errors, isinstance(boundaries, list), "continuity_metrics.boundaries must be an array")
        boundaries = boundaries if isinstance(boundaries, list) else []
        _add(errors, boundary_count == expected_copies - 1 == len(boundaries), "continuity boundary count mismatch")
        _add(
            errors,
            _integer(metrics.get("cross_boundary_completion_count"), "continuity_metrics.cross_boundary_completion_count")
            == sum(_integer(row.get("cross_boundary_completion_count"), "continuity boundary cross count") for row in boundaries),
            "continuity cross-boundary count inconsistent",
        )
        _add(
            errors,
            metrics.get("carry_over_observed")
            is any(_integer(row.get("pending_before_boundary"), "continuity pending") > 0 for row in boundaries),
            "continuity carry_over_observed inconsistent",
        )
        audit = _mapping(metrics.get("input_audit"), "continuity_metrics.input_audit", errors)
        _add(errors, audit.get("status") == "PASS", "continuity input audit failed")
        _add(errors, _integer(audit.get("expected_copy_count"), "continuity expected_copy_count") == expected_copies, "continuity expected copy count mismatch")
        _add(errors, _integer(audit.get("workload_row_count"), "continuity workload_row_count") == int(expectation.input_artifact["row_count"]), "continuity workload count mismatch")
        if workload_rows is not None:
            from scripts.eval.g4irsf11_continuity_metrics import rolling_input_audit

            _add(
                errors,
                dict(audit) == rolling_input_audit(workload_rows, expected_copies=expected_copies),
                "continuity input audit does not recompute from workload",
            )
    except ValueError as exc:
        errors.append(str(exc))


def validate_event_result(
    result: Mapping[str, Any],
    expectation: ResultExpectation,
    *,
    workload_rows: Sequence[Mapping[str, Any]] | None = None,
) -> list[str]:
    """Return every v3 schema/semantic error; an empty list means reusable."""

    errors: list[str] = []
    _walk_finite(result, "result", errors)
    _add(errors, result.get("schema") == RESULT_SCHEMA, "result schema mismatch")
    _add(errors, result.get("run_id") == expectation.run_id, "result run_id mismatch")
    try:
        parsed_run_id = uuid.UUID(str(result.get("run_id")))
        if parsed_run_id.version != 4 or str(parsed_run_id) != str(result.get("run_id")):
            errors.append("result run_id must be a canonical UUIDv4")
    except (ValueError, AttributeError):
        errors.append("result run_id must be a canonical UUIDv4")
    _add(errors, result.get("case") == dict(expectation.case), "result CaseSpec echo mismatch")
    _add(errors, result.get("protocol_version") == expectation.protocol_version, "result protocol version mismatch")
    _add(
        errors,
        result.get("protocol_manifest_sha256") == expectation.protocol_manifest_sha256,
        "result protocol manifest hash mismatch",
    )
    for key, expected in (
        ("input_artifact", dict(expectation.input_artifact)),
        ("fault_artifact", dict(expectation.fault_artifact)),
        ("map_sha256", expectation.map_sha256),
        ("source_sha256", expectation.source_sha256),
        ("implementation_sha256", expectation.implementation_sha256),
        ("config", dict(expectation.config)),
        ("measurement_cohort", dict(expectation.measurement_cohort)),
    ):
        _add(errors, result.get(key) == expected, f"result {key} echo mismatch")
    for key in (
        "protocol_manifest_sha256",
        "map_sha256",
        "source_sha256",
        "implementation_sha256",
    ):
        _validate_sha(result.get(key), f"result.{key}", errors)
    input_value = result.get("input_artifact")
    if isinstance(input_value, Mapping):
        _validate_sha(input_value.get("sha256"), "result.input_artifact.sha256", errors)
        try:
            input_count = _integer(input_value.get("row_count"), "result.input_artifact.row_count")
            minimum_release = _finite_number(
                input_value.get("minimum_release_time"),
                "result.input_artifact.minimum_release_time",
            )
            maximum_release = _finite_number(
                input_value.get("maximum_release_time"),
                "result.input_artifact.maximum_release_time",
            )
            release_span = _finite_number(
                input_value.get("release_span_seconds"),
                "result.input_artifact.release_span_seconds",
            )
            _add(errors, input_count > 0, "result input artifact must contain rows")
            _add(errors, maximum_release >= minimum_release, "result input release bounds reversed")
            _add(
                errors,
                math.isclose(
                    release_span,
                    maximum_release - minimum_release,
                    rel_tol=0.0,
                    abs_tol=1.0e-9,
                ),
                "result input release span inconsistent",
            )
        except ValueError as exc:
            errors.append(str(exc))
        if workload_rows is not None:
            try:
                _add(
                    errors,
                    workload_binding(Path(str(input_value.get("path") or "")), workload_rows)
                    == dict(expectation.input_artifact),
                    "input artifact does not recompute from workload rows",
                )
            except ValueError as exc:
                errors.append(str(exc))
    fault_value = result.get("fault_artifact")
    if isinstance(fault_value, Mapping):
        _validate_sha(fault_value.get("sha256"), "result.fault_artifact.sha256", errors)
        try:
            fault_count = _integer(fault_value.get("row_count"), "result.fault_artifact.row_count")
            _add(errors, fault_count == len(expectation.fault_rows), "fault artifact row count mismatch")
            _add(
                errors,
                fault_value.get("state") == ("empty" if fault_count == 0 else "present"),
                "fault artifact explicit-empty/present state inconsistent",
            )
        except ValueError as exc:
            errors.append(str(exc))

    case = expectation.case
    config = _mapping(result.get("config"), "config", errors)
    case_config = {
        "queue_discipline": case.get("queue_discipline"),
        "diagnostic_hops": case.get("diagnostic_hops"),
        "enable_source_admission": case.get("enable_source_admission"),
        "enable_backpressure": case.get("enable_backpressure"),
        "enable_pibt_lite": case.get("enable_pibt_lite"),
        "enable_deadlock_escape": case.get("enable_deadlock_escape"),
        "enable_fault_policy": case.get("enable_fault_policy"),
        "trace_limit": -1 if case.get("trace_complete") else 0,
    }
    for key, expected in case_config.items():
        _add(errors, config.get(key) == expected, f"config.{key} != CaseSpec")
    _add(errors, result.get("scenario") == case.get("case_id"), "result scenario != case_id")
    try:
        _add(errors, _finite_number(result.get("scale"), "result.scale") == float(case.get("scale")), "result scale mismatch")
    except ValueError as exc:
        errors.append(str(exc))
    _add(errors, result.get("workload_mode") == case.get("workload_mode"), "result workload mode mismatch")
    _add(errors, result.get("workload_path") == expectation.input_artifact.get("path"), "result workload path mismatch")

    summary = _mapping(result.get("summary"), "summary", errors)
    completed_count: int | None = None
    peak_active_count: int | None = None
    bag_release_event_count: int | None = None
    event_limited_flag: bool | None = None
    time_limited_flag: bool | None = None
    successful_completion_flag: bool | None = None
    try:
        requested = _integer(summary.get("requested_count"), "summary.requested_count")
        completed = _integer(summary.get("completed_count"), "summary.completed_count")
        completed_count = completed
        failed = _integer(summary.get("failed_count"), "summary.failed_count")
        workload_count = _integer(result.get("workload_segment_count"), "result.workload_segment_count")
        expected_count = _integer(expectation.input_artifact.get("row_count"), "input_artifact.row_count")
        _add(errors, requested == workload_count == expected_count, "requested/workload/input counts differ")
        if case.get("segment_limit") is not None:
            _add(
                errors,
                requested == _integer(case.get("segment_limit"), "case.segment_limit"),
                "bounded case requested_count != segment_limit",
            )
        _add(errors, completed + failed == requested, "completed_count + failed_count != requested_count")
        _add(errors, min(requested, completed, failed) >= 0, "summary counts must be non-negative")
        peak_active_bags = _integer(
            summary.get("peak_active_bag_count"), "summary.peak_active_bag_count"
        )
        peak_active_count = peak_active_bags
        final_active_bags = _integer(
            summary.get("final_active_bag_count"),
            "summary.final_active_bag_count",
        )
        _add(
            errors,
            final_active_bags == 0,
            "summary.final_active_bag_count must be zero after finalization",
        )
        _add(
            errors,
            0 <= peak_active_bags <= requested,
            "summary.peak_active_bag_count must be within requested_count",
        )
        _add(
            errors,
            completed == 0 or peak_active_bags >= 1,
            "completed bags require a positive peak active bag count",
        )
        runtime_end_time = _finite_number(summary.get("end_time"), "summary.end_time")
        event_limited_value = summary.get("event_limit_reached")
        time_limited_value = summary.get("time_limit_reached")
        _add(
            errors,
            isinstance(event_limited_value, bool),
            "summary.event_limit_reached must be a boolean",
        )
        _add(
            errors,
            isinstance(time_limited_value, bool),
            "summary.time_limit_reached must be a boolean",
        )
        event_limited = event_limited_value is True
        time_limited = time_limited_value is True
        event_limited_flag = event_limited
        time_limited_flag = time_limited
        _add(
            errors,
            not (event_limited and time_limited),
            "event and time limits cannot both be reached",
        )
        _add(errors, runtime_end_time >= 0.0, "summary.end_time must be non-negative")
        _add(
            errors,
            event_limited
            or time_limited
            or runtime_end_time
            >= _finite_number(
                expectation.input_artifact.get("minimum_release_time"),
                "input_artifact.minimum_release_time",
            ),
            "unlimited summary.end_time must not precede the first input release",
        )
        expected_completion = completed == requested and failed == 0 and not event_limited and not time_limited
        successful_completion_flag = expected_completion
        _add(errors, result.get("completion_pass") is expected_completion, "completion_pass inconsistent")

        invariant_pairs = (
            _integer(summary.get("reservation_conflicts"), "summary.reservation_conflicts") == 0,
            _integer(summary.get("runtime_full_astar_calls"), "summary.runtime_full_astar_calls") == 0,
            _integer(summary.get("global_reservation_scan_count"), "summary.global_reservation_scan_count") == 0,
            _integer(summary.get("max_edges_selected_per_arrive"), "summary.max_edges_selected_per_arrive") <= 1,
            _integer(summary.get("release_selected_edge_count"), "summary.release_selected_edge_count") == 0,
            _integer(summary.get("two_step_reservation_count"), "summary.two_step_reservation_count") == 0,
            _integer(summary.get("full_future_routes_stored"), "summary.full_future_routes_stored") == 0,
        )
        _add(
            errors,
            result.get("event_runtime_invariant_pass") is all(invariant_pairs),
            "event_runtime_invariant_pass inconsistent",
        )
        for key in (
            "event_count",
            "bag_release_event_count",
            "decision_count",
            "reservation_conflicts",
            "runtime_full_astar_calls",
            "global_reservation_scan_count",
            "deadlock_count",
            "resolved_deadlock_count",
            "unresolved_deadlock_count",
            "loop_count",
        ):
            _add(errors, _integer(summary.get(key, 0), f"summary.{key}") >= 0, f"summary.{key} must be non-negative")
        bag_release_event_count = _integer(
            summary.get("bag_release_event_count"),
            "summary.bag_release_event_count",
        )
        if all(key in summary for key in ("deadlock_count", "resolved_deadlock_count", "unresolved_deadlock_count")):
            _add(
                errors,
                _integer(summary["resolved_deadlock_count"], "summary.resolved_deadlock_count")
                + _integer(summary["unresolved_deadlock_count"], "summary.unresolved_deadlock_count")
                == _integer(summary["deadlock_count"], "summary.deadlock_count"),
                "deadlock counters do not partition deadlock_count",
            )

        fault_counter_keys = (
            "fault_affected_bag_count",
            "fault_target_edge_candidate_exposure_count",
            "fault_target_edge_attempt_count",
            "physical_fault_interlock_rejection_count",
            "physical_fault_interlock_hold_count",
            "physical_fault_interlock_reroute_count",
            "local_fault_policy_action_count",
            "local_fault_policy_hold_count",
            "local_fault_policy_reroute_count",
            "physical_fault_edge_entry_violation_count",
        )
        _add(errors, isinstance(summary.get("fault_policy_enabled"), bool), "summary.fault_policy_enabled must be bool")
        _add(
            errors,
            summary.get("fault_policy_enabled") is bool(case.get("enable_fault_policy")),
            "summary fault_policy_enabled != CaseSpec",
        )
        fault_counts = {
            key: _integer(summary.get(key), f"summary.{key}")
            for key in fault_counter_keys
        }
        _add(errors, all(value >= 0 for value in fault_counts.values()), "fault summary counters must be non-negative")
        _add(
            errors,
            fault_counts["local_fault_policy_action_count"]
            == fault_counts["local_fault_policy_hold_count"]
            + fault_counts["local_fault_policy_reroute_count"],
            "local fault-policy action count does not partition into hold/reroute",
        )
        _add(
            errors,
            fault_counts["physical_fault_interlock_rejection_count"]
            == fault_counts["physical_fault_interlock_hold_count"]
            + fault_counts["physical_fault_interlock_reroute_count"],
            "physical interlock rejection count does not partition into hold/reroute",
        )
        _add(
            errors,
            fault_counts["fault_target_edge_candidate_exposure_count"]
            >= fault_counts["fault_target_edge_attempt_count"]
            >= fault_counts["fault_affected_bag_count"],
            "fault exposure/attempt/affected counters are inconsistent",
        )
        if not bool(case.get("enable_fault_policy")):
            _add(
                errors,
                fault_counts["local_fault_policy_action_count"] == 0,
                "fault-policy-off case recorded local policy actions",
            )
            _add(
                errors,
                fault_counts["physical_fault_interlock_reroute_count"] == 0,
                "fault-policy-off physical interlock may hold but may not reroute",
            )
        if case.get("fault_profile") == "no_fault":
            _add(errors, all(value == 0 for value in fault_counts.values()), "no-fault case has nonzero fault counters")
            _add(errors, summary.get("sensor_loss_mode_used") is False, "no-fault case claims sensor-loss mode")
        elif case.get("fault_profile") == "sensor_loss":
            _add(errors, summary.get("sensor_loss_mode_used") is True, "sensor-loss case did not echo sensor_loss_mode_used")
        else:
            _add(errors, summary.get("sensor_loss_mode_used") is False, "non-sensor-loss case claims sensor-loss mode")

        raw_count = _integer(result.get("raw_bag_count"), "result.raw_bag_count")
        _validate_capacity_metrics(
            "raw_bag_capacity_metrics",
            result.get("raw_bag_capacity_metrics"),
            expected_count=raw_count,
            summary=summary,
            errors=errors,
        )
        _validate_capacity_metrics(
            "segment_capacity_metrics",
            result.get("segment_capacity_metrics"),
            expected_count=requested,
            expected_completed=completed,
            expected_failed=failed,
            summary=summary,
            errors=errors,
        )
    except ValueError as exc:
        errors.append(str(exc))

    junction_count = 0
    peak_junction_bytes = 0
    final_junction_bytes = 0
    max_junction_utilization = 0.0
    bottleneck_node = -1
    bottleneck_score = 0.0
    junction_value = result.get("junction_state")
    _add(errors, isinstance(junction_value, list), "junction_state must be an array")
    junction_rows = junction_value if isinstance(junction_value, list) else []
    try:
        expected_junction_rows = derive_junction_evidence(
            junction_rows,
        )
        total_service_reservations = sum(
            int(row["service_reservation_count"])
            for row in expected_junction_rows
        )
        if completed_count is not None:
            _add(
                errors,
                total_service_reservations >= completed_count,
                "per-junction service reservations are below completed_count",
            )
        junction_count = len(expected_junction_rows)
        if junction_count == 0:
            _add(
                errors,
                completed_count == 0,
                "empty junction_state requires completed_count == 0",
            )
            _add(
                errors,
                peak_active_count == 0,
                "empty junction_state requires peak_active_bag_count == 0",
            )
            _add(
                errors,
                bag_release_event_count == 0,
                "empty junction_state requires bag_release_event_count == 0",
            )
            _add(
                errors,
                event_limited_flag is True or time_limited_flag is True,
                "empty junction_state requires an explicit event/time limit",
            )
        if successful_completion_flag is True:
            for index, row in enumerate(expected_junction_rows):
                for field in (
                    "final_source_queue_length",
                    "final_junction_queue_length",
                    "final_service_calendar_intervals",
                    "scheduled_incoming",
                ):
                    _add(
                        errors,
                        int(row[field]) == 0,
                        f"successful junction_state[{index}].{field} must be zero",
                    )
        peak_junction_bytes = max(
            (
                int(row["peak_local_state_accounted_bytes"])
                for row in expected_junction_rows
            ),
            default=0,
        )
        final_junction_bytes = sum(
            int(row["final_local_state_accounted_bytes"])
            for row in expected_junction_rows
        )
        max_junction_utilization = max(
            (
                float(row["service_utilization"])
                for row in expected_junction_rows
            ),
            default=0.0,
        )
        if expected_junction_rows:
            top_junction = min(
                expected_junction_rows,
                key=lambda row: int(row["bottleneck_rank"]),
            )
            bottleneck_node = int(top_junction["node"])
            bottleneck_score = float(top_junction["bottleneck_score"])
        for index, (observed, expected) in enumerate(
            zip(junction_rows, expected_junction_rows)
        ):
            _add(
                errors,
                observed.get("service_utilization_semantics")
                == JUNCTION_SERVICE_UTILIZATION_SEMANTICS,
                f"junction_state[{index}] service utilization semantics mismatch",
            )
            _add(
                errors,
                observed.get("bottleneck_score_semantics")
                == JUNCTION_BOTTLENECK_SCORE_SEMANTICS,
                f"junction_state[{index}] bottleneck score semantics mismatch",
            )
            _add(
                errors,
                _integer(
                    observed.get("bottleneck_rank"),
                    f"junction_state[{index}].bottleneck_rank",
                )
                == int(expected["bottleneck_rank"]),
                f"junction_state[{index}] bottleneck rank mismatch",
            )
            for key in (
                "service_observation_span_seconds",
                "service_utilization",
                "bottleneck_score",
            ):
                _add(
                    errors,
                    math.isclose(
                        _finite_number(
                            observed.get(key), f"junction_state[{index}].{key}"
                        ),
                        float(expected[key]),
                        rel_tol=0.0,
                        abs_tol=1.0e-12,
                    ),
                    f"junction_state[{index}] {key} mismatch",
                )
    except ValueError as exc:
        errors.append(str(exc))

    resource = _mapping(result.get("resource_metrics"), "resource_metrics", errors)
    try:
        _add(errors, resource.get("measurement_scope") == "isolated_worker_process", "resource measurement_scope mismatch")
        before = _integer(resource.get("working_set_before_bytes"), "resource working_set before")
        peak_before = _integer(resource.get("peak_working_set_before_bytes"), "resource peak before")
        after = _integer(resource.get("working_set_after_bytes"), "resource working set after")
        peak = _integer(resource.get("peak_working_set_bytes"), "resource peak working set")
        growth = _integer(resource.get("peak_working_set_growth_from_initial_current_bytes"), "resource peak growth")
        cpp_bytes = _integer(resource.get("cpp_internal_accounted_bytes"), "resource cpp bytes")
        runtime_thread_count = _integer(
            resource.get("runtime_thread_count"), "resource runtime thread count"
        )
        _add(errors, growth >= 0, "resource growth must be non-negative")
        _add(
            errors,
            min(before, peak_before, after, peak, cpp_bytes) > 0,
            "measured working-set and C++ accounted bytes must be positive",
        )
        _add(
            errors,
            peak_before >= before,
            "initial peak working set is below the initial current working set",
        )
        _add(errors, peak >= max(before, peak_before, after), "peak working set is below an observed working set")
        _add(errors, growth == max(0, peak - before), "peak working set growth inconsistent")
        _add(errors, cpp_bytes == _integer(summary.get("cpp_internal_accounted_bytes"), "summary cpp bytes"), "C++ accounted bytes mismatch")
        _add(
            errors,
            cpp_bytes >= final_junction_bytes
            and (junction_count == 0 or final_junction_bytes > 0),
            "C++ accounted bytes do not cover final per-junction local lower bounds",
        )
        _add(errors, runtime_thread_count == 1, "runtime thread count must be the single-thread baseline")
        _add(
            errors,
            _integer(resource.get("junction_count"), "resource junction count")
            == junction_count,
            "resource junction count mismatch",
        )
        _add(
            errors,
            _integer(resource.get("peak_active_bag_count"), "resource peak active bags")
            == _integer(summary.get("peak_active_bag_count"), "summary peak active bags"),
            "resource peak active bag count mismatch",
        )
        _add(
            errors,
            _integer(
                resource.get("peak_junction_local_state_accounted_bytes"),
                "resource peak junction local bytes",
            )
            == peak_junction_bytes,
            "resource peak junction local bytes mismatch",
        )
        _add(
            errors,
            _integer(
                resource.get("sum_final_junction_local_state_accounted_bytes"),
                "resource sum final junction local bytes",
            )
            == final_junction_bytes,
            "resource final junction local byte sum mismatch",
        )
        _add(
            errors,
            math.isclose(
                _finite_number(
                    resource.get("max_junction_service_utilization"),
                    "resource max junction utilization",
                ),
                max_junction_utilization,
                rel_tol=0.0,
                abs_tol=1.0e-12,
            ),
            "resource max junction utilization mismatch",
        )
        _add(
            errors,
            _integer(resource.get("bottleneck_node"), "resource bottleneck node")
            == bottleneck_node,
            "resource bottleneck node mismatch",
        )
        _add(
            errors,
            math.isclose(
                _finite_number(
                    resource.get("bottleneck_score"), "resource bottleneck score"
                ),
                bottleneck_score,
                rel_tol=0.0,
                abs_tol=1.0e-12,
            ),
            "resource bottleneck score mismatch",
        )
        _add(
            errors,
            resource.get("junction_local_state_accounting_semantics")
            == JUNCTION_LOCAL_STATE_ACCOUNTING_SEMANTICS,
            "resource junction local-state accounting semantics mismatch",
        )
        _add(
            errors,
            resource.get("junction_service_utilization_semantics")
            == JUNCTION_SERVICE_UTILIZATION_SEMANTICS,
            "resource junction utilization semantics mismatch",
        )
        _add(
            errors,
            resource.get("junction_bottleneck_score_semantics")
            == JUNCTION_BOTTLENECK_SCORE_SEMANTICS,
            "resource junction bottleneck semantics mismatch",
        )
        _add(errors, _finite_number(resource.get("wall_seconds_including_pybind_materialization"), "resource wall seconds") > 0.0, "resource wall seconds must be positive")
    except ValueError as exc:
        errors.append(str(exc))

    fault_metrics = result.get("fault_window_metrics")
    _add(errors, isinstance(fault_metrics, list), "fault_window_metrics must be an array")
    fault_metrics = fault_metrics if isinstance(fault_metrics, list) else []
    _add(errors, len(fault_metrics) == len(expectation.fault_rows), "fault metric/window count mismatch")
    for index, (metric_value, window) in enumerate(zip(fault_metrics, expectation.fault_rows)):
        metric = _mapping(metric_value, f"fault_window_metrics[{index}]", errors)
        expected_echo = {
            "fault_window_index": index,
            "edge_start": int(window["start"]),
            "edge_end": int(window["end"]),
            "fault_time": float(window["fault_time"]),
            "repair_time": float(window["repair_time"]),
            "message_delay_seconds": float(window.get("message_delay", 0.0)),
            "drop_notification": bool(window.get("drop_notification", False)),
        }
        for key, expected in expected_echo.items():
            _add(errors, metric.get(key) == expected, f"fault metric {index} {key} mismatch")
        try:
            recovery = _finite_number(metric.get("recovery_time_seconds"), f"fault metric {index} recovery")
            maximum = _finite_number(metric.get("max_recovery_seconds"), f"fault metric {index} maximum")
            _add(errors, maximum == float(FAULT_SLO["max_fault_recovery_seconds"]), f"fault metric {index} SLO mismatch")
            dropped = bool(window.get("drop_notification", False))
            message_ok = (
                _integer(metric.get("notification_dropped_event_count"), "fault dropped count") == 2
                and _integer(metric.get("message_delivery_event_count"), "fault message count") == 0
                if dropped
                else _integer(metric.get("message_delivery_event_count"), "fault message count") == 2
                and _integer(metric.get("notification_dropped_event_count"), "fault dropped count") == 0
            )
            affected_count = _integer(metric.get("affected_cohort_count"), "fault affected cohort")
            affected_completed = _integer(
                metric.get("affected_cohort_complete_count"), "fault affected completed"
            )
            candidate_exposure_count = _integer(
                metric.get("target_edge_candidate_exposure_count"), "fault candidate exposure"
            )
            target_attempt_count = _integer(
                metric.get("target_edge_attempt_count"), "fault target attempts"
            )
            local_action_count = _integer(
                metric.get("local_fault_policy_action_count"), "fault local actions"
            )
            local_hold_count = _integer(
                metric.get("local_fault_policy_hold_count"), "fault local holds"
            )
            local_reroute_count = _integer(
                metric.get("local_fault_policy_reroute_count"), "fault local reroutes"
            )
            interlock_rejection_count = _integer(
                metric.get("physical_interlock_rejection_count"), "fault interlock rejections"
            )
            interlock_hold_count = _integer(
                metric.get("physical_interlock_hold_count"), "fault interlock holds"
            )
            interlock_reroute_count = _integer(
                metric.get("physical_interlock_reroute_count"), "fault interlock reroutes"
            )
            _add(errors, metric.get("fault_policy_enabled") is bool(case.get("enable_fault_policy")), f"fault metric {index} policy echo mismatch")
            _add(errors, local_action_count == local_hold_count + local_reroute_count, f"fault metric {index} local action counters inconsistent")
            _add(errors, interlock_rejection_count == interlock_hold_count + interlock_reroute_count, f"fault metric {index} interlock counters inconsistent")
            _add(errors, candidate_exposure_count >= target_attempt_count >= affected_count, f"fault metric {index} exposure counters inconsistent")
            _add(errors, metric.get("summary_contract_complete") is True, f"fault metric {index} summary contract unexpectedly incomplete")
            _add(errors, list(metric.get("missing_summary_fields") or []) == [], f"fault metric {index} reports missing summary fields")
            expected_summary_counts_consistent = (
                _integer(summary.get("fault_affected_bag_count"), "summary affected bags") >= affected_count
                and _integer(summary.get("fault_target_edge_candidate_exposure_count"), "summary candidate exposures") >= candidate_exposure_count
                and _integer(summary.get("fault_target_edge_attempt_count"), "summary target attempts") >= target_attempt_count
                and _integer(summary.get("physical_fault_interlock_rejection_count"), "summary interlock rejections") >= interlock_rejection_count
                and _integer(summary.get("physical_fault_interlock_hold_count"), "summary interlock holds") >= interlock_hold_count
                and _integer(summary.get("physical_fault_interlock_reroute_count"), "summary interlock reroutes") >= interlock_reroute_count
                and _integer(summary.get("local_fault_policy_action_count"), "summary local actions") >= local_action_count
                and _integer(summary.get("local_fault_policy_hold_count"), "summary local holds") >= local_hold_count
                and _integer(summary.get("local_fault_policy_reroute_count"), "summary local reroutes") >= local_reroute_count
            )
            _add(
                errors,
                metric.get("summary_counts_consistent") is expected_summary_counts_consistent,
                f"fault metric {index} summary_counts_consistent mismatch",
            )
            expected_rate = affected_completed / affected_count if affected_count else 0.0
            _add(
                errors,
                _finite_number(metric.get("affected_cohort_completion_rate"), "fault affected completion rate") == expected_rate,
                f"fault metric {index} affected completion rate inconsistent",
            )
            real_exposure = (
                candidate_exposure_count > 0
                and target_attempt_count > 0
                and affected_count > 0
                and metric.get("affected_cohort_link_complete") is True
            )
            affected_completion = (
                affected_count > 0
                and affected_completed == affected_count
                and metric.get("affected_cohort_link_complete") is True
            )
            if dropped or not bool(case.get("enable_fault_policy")):
                policy_action_evidence = local_action_count == 0 and interlock_rejection_count > 0
            else:
                policy_action_evidence = local_action_count > 0
            if not bool(case.get("enable_fault_policy")):
                _add(errors, interlock_reroute_count == 0, f"fault metric {index} policy-off interlock rerouted")
                _add(errors, interlock_hold_count == interlock_rejection_count > 0, f"fault metric {index} policy-off interlock must hold")
            sensor_boundary = (
                not dropped
                or (
                    summary.get("sensor_loss_mode_used") is True
                    and _integer(metric.get("notification_dropped_event_count"), "fault dropped count") == 2
                    and interlock_rejection_count > 0
                    and local_action_count == 0
                    and _integer(metric.get("unsafe_edge_entry_during_physical_fault_count"), "fault unsafe count") == 0
                )
            )
            safety_boundary = (
                _integer(metric.get("unsafe_edge_entry_during_physical_fault_count"), "fault unsafe count") == 0
                and _integer(summary.get("physical_fault_edge_entry_violation_count"), "summary fault violation") == 0
                and _integer(summary.get("runtime_full_astar_calls"), "summary astar") == 0
            )
            gate_checks = {
                "summary_contract_complete": metric.get("summary_contract_complete") is True,
                "summary_counts_consistent": expected_summary_counts_consistent,
                "policy_audit_consistent": metric.get("policy_audit_consistent") is True,
                "trace_complete": (
                    _integer(metric.get("physical_fault_event_count"), "fault physical count") > 0
                    and _integer(metric.get("physical_repair_event_count"), "fault repair count") > 0
                ),
                "message_complete": message_ok,
                "real_exposure_pass": real_exposure,
                "affected_completion_pass": affected_completion,
                "policy_action_evidence_pass": policy_action_evidence,
                "sensor_loss_interlock_boundary_pass": sensor_boundary,
                "safety_boundary_pass": safety_boundary,
                "recovery_time_pass": recovery <= maximum,
            }
            for gate_name in (
                "real_exposure_pass",
                "affected_completion_pass",
                "policy_action_evidence_pass",
                "sensor_loss_interlock_boundary_pass",
                "safety_boundary_pass",
            ):
                _add(
                    errors,
                    metric.get(gate_name) is gate_checks[gate_name],
                    f"fault metric {index} {gate_name} inconsistent",
                )
            expected_failures = [name for name, passed in gate_checks.items() if not passed]
            _add(
                errors,
                metric.get("fault_recovery_gate_failures") == expected_failures,
                f"fault metric {index} gate failure list inconsistent",
            )
            expected_pass = not expected_failures
            _add(errors, metric.get("fault_recovery_pass") is expected_pass, f"fault metric {index} pass inconsistent")
            _add(errors, _integer(metric.get("runtime_full_astar_calls"), "fault astar") == _integer(summary.get("runtime_full_astar_calls"), "summary astar"), f"fault metric {index} astar mismatch")
            _add(
                errors,
                _integer(
                    metric.get("run_physical_fault_edge_entry_violation_count"),
                    "fault run physical violation count",
                )
                == _integer(
                    summary.get("physical_fault_edge_entry_violation_count"),
                    "summary physical violation count",
                ),
                f"fault metric {index} physical violation projection mismatch",
            )
            for metric_key, summary_key in (
                ("stale_fault_shield_rejection_count", "stale_fault_shield_rejection_count"),
                ("resolved_deadlock_count", "resolved_deadlock_count"),
                ("unresolved_deadlock_count", "unresolved_deadlock_count"),
            ):
                if summary_key in summary:
                    _add(
                        errors,
                        _integer(metric.get(metric_key), f"fault metric {index} {metric_key}")
                        == _integer(summary.get(summary_key), f"summary.{summary_key}"),
                        f"fault metric {index} {metric_key} projection mismatch",
                    )
        except ValueError as exc:
            errors.append(str(exc))

    trace = _mapping(result.get("trace"), "trace", errors)
    trace_context = _mapping(trace.get("trace_context"), "trace.trace_context", errors)
    _add(errors, trace_context.get("run_id") == expectation.run_id, "trace run_id mismatch")
    _add(errors, trace_context.get("scenario") == case.get("case_id"), "trace scenario mismatch")
    _add(errors, trace_context.get("fault_mode") == case.get("fault_profile"), "trace fault mode mismatch")
    try:
        _add(errors, _finite_number(trace_context.get("scale"), "trace scale") == float(case.get("scale")), "trace scale mismatch")
        decision_rows = _integer(trace.get("decision_rows_stored"), "trace decision rows")
        hold_rows = _integer(trace.get("hold_rows_stored"), "trace hold rows")
        _add(errors, decision_rows == _integer(summary.get("decision_trace_stored_count"), "summary decision trace stored"), "trace decision count mismatch")
        _add(errors, hold_rows == _integer(summary.get("hold_trace_stored_count"), "summary hold trace stored"), "trace hold count mismatch")
        if case.get("trace_complete"):
            _add(errors, expectation.config.get("trace_limit") == -1, "complete trace case must use trace_limit=-1")
            for key in ("trace_output", "outcome_output", "trace_task_output"):
                _add(errors, bool(str(trace.get(key) or "")), f"complete trace case missing {key}")
        else:
            _add(errors, expectation.config.get("trace_limit") == 0, "non-trace case must use trace_limit=0")
            for key in ("trace_output", "outcome_output", "trace_task_output"):
                _add(errors, str(trace.get(key) or "") == "", f"non-trace case unexpectedly has {key}")
            _add(errors, decision_rows == 0 and hold_rows == 0, "non-trace case stored trace rows")
    except ValueError as exc:
        errors.append(str(exc))

    environment = _mapping(result.get("environment"), "environment", errors)
    _add(errors, bool(str(environment.get("python_executable") or "")), "environment python executable missing")
    _add(errors, bool(str(environment.get("python_version") or "")), "environment python version missing")
    _add(errors, bool(str(environment.get("platform") or "")), "environment platform missing")
    _validate_continuity(result, expectation, workload_rows, errors)
    return sorted(set(errors))


def validate_execution_descriptor(
    descriptor: Mapping[str, Any],
    result: Mapping[str, Any],
    expectation: ResultExpectation,
    *,
    normalized_argv: Sequence[str],
    normalized_command_text: str,
    parent_timeout_seconds: float,
    result_artifact: Mapping[str, Any],
    trace_artifacts: Mapping[str, Mapping[str, Any]],
    workload_rows: Sequence[Mapping[str, Any]] | None = None,
) -> list[str]:
    errors = validate_event_result(result, expectation, workload_rows=workload_rows)
    _walk_finite(descriptor, "descriptor", errors)
    _add(errors, descriptor.get("schema") == EXECUTION_DESCRIPTOR_SCHEMA, "descriptor schema mismatch")
    _add(errors, descriptor.get("run_id") == expectation.run_id, "descriptor run_id mismatch")
    _add(errors, descriptor.get("case") == dict(expectation.case), "descriptor CaseSpec mismatch")
    _add(errors, descriptor.get("protocol_version") == expectation.protocol_version, "descriptor protocol version mismatch")
    _add(errors, descriptor.get("protocol_manifest_sha256") == expectation.protocol_manifest_sha256, "descriptor protocol manifest hash mismatch")
    _add(errors, descriptor.get("input_artifact") == dict(expectation.input_artifact), "descriptor input artifact mismatch")
    _add(
        errors,
        descriptor.get("input_sha256") == expectation.input_artifact.get("sha256"),
        "descriptor top-level input_sha256 mismatch",
    )
    _add(errors, descriptor.get("fault_artifact") == dict(expectation.fault_artifact), "descriptor fault artifact mismatch")
    _add(errors, descriptor.get("map_sha256") == expectation.map_sha256, "descriptor map hash mismatch")
    _add(errors, descriptor.get("source_sha256") == expectation.source_sha256, "descriptor source hash mismatch")
    _add(errors, descriptor.get("implementation_sha256") == expectation.implementation_sha256, "descriptor implementation hash mismatch")
    _add(errors, descriptor.get("config") == dict(expectation.config), "descriptor config mismatch")
    _add(errors, descriptor.get("measurement_cohort") == dict(expectation.measurement_cohort), "descriptor measurement cohort mismatch")
    _add(errors, descriptor.get("normalized_argv") == list(normalized_argv), "descriptor normalized argv mismatch")
    _add(
        errors,
        descriptor.get("command") == normalized_command_text,
        "descriptor command text mismatch",
    )
    try:
        _add(
            errors,
            _finite_number(descriptor.get("parent_timeout_seconds"), "descriptor parent timeout")
            == float(parent_timeout_seconds),
            "descriptor parent timeout mismatch",
        )
    except ValueError as exc:
        errors.append(str(exc))
    _add(errors, descriptor.get("result_artifact") == dict(result_artifact), "descriptor result artifact mismatch")
    _add(
        errors,
        descriptor.get("trace_artifacts")
        == {key: dict(value) for key, value in trace_artifacts.items()},
        "descriptor trace artifacts mismatch",
    )
    _add(errors, descriptor.get("environment") == result.get("environment"), "descriptor/result environment mismatch")
    _add(errors, descriptor.get("status") == "EXECUTED", "descriptor status is not EXECUTED")
    _add(errors, descriptor.get("return_code") == 0, "EXECUTED descriptor return_code must be 0")
    _add(errors, descriptor.get("blocker") == "", "EXECUTED descriptor blocker must be empty")
    try:
        _add(errors, _finite_number(descriptor.get("wall_seconds_parent"), "descriptor wall seconds") > 0.0, "descriptor wall seconds must be positive")
    except ValueError as exc:
        errors.append(str(exc))
    return sorted(set(errors))
