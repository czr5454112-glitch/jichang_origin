"""Run the real native G4IRSF16 supervisor at the 2,048/8,192 ladders.

This is an event-runtime execution, not an offline replay.  The preregistered
H5 policy remains diagnostic-only (H0 is the promoted/default policy), and the
output keeps that limitation explicit while recording action changes, hard
safety gates, every bag's release-to-goal TTH, and compact activation rows.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping, Sequence


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
    FROZEN_RUNTIME_CONTROLS,
    MODEL_PATH,
    MODEL_SHA256,
)
from czr005.g4irsf16.model import validate_self_sha256  # noqa: E402


SCHEMA = "czr005.g4irsf16.closed_loop_canary.v1"
ALLOWED_SEGMENTS = (144, 512, 2_048, 8_192)
DEFAULT_RULE_BUNDLE = (
    ROOT / "artifacts/policies/g4irsf16_best_rule_bundle.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "outputs/runtime/g4irsf16_closed_loop"


class CanaryError(RuntimeError):
    """Raised before incomplete or unsafe canary evidence is published."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CanaryError(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rule_bundle_self_sha256(path: Path) -> str:
    """Use the canonical JSON identity so checkout line endings cannot drift."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CanaryError(f"invalid rule bundle: {path}") from exc
    _require(isinstance(payload, Mapping), "rule bundle must be a JSON object")
    try:
        validate_self_sha256(payload)
    except ValueError as exc:
        raise CanaryError(f"rule bundle self SHA is invalid: {exc}") from exc
    identity = payload.get("self_sha256")
    _require(isinstance(identity, str), "rule bundle self SHA is missing")
    return identity


def _metadata_path(path: Path) -> str:
    """Keep repository evidence relocatable while permitting external binaries."""

    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _portable_binary_name(value: str) -> str:
    """Extract one file name independent of the host path flavour."""

    normalized = value.replace("\\", "/")
    file_name = normalized.rsplit("/", 1)[-1]
    _require(
        file_name not in {"", ".", ".."} and ":" not in file_name,
        "binary name is not portable",
    )
    return file_name


def _published_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Remove machine-local loader paths from portable evidence."""

    published = dict(summary)
    loaded_path = published.get("loaded_cpp_binary_path")
    if isinstance(loaded_path, str) and loaded_path:
        candidate_name = published.get("loaded_cpp_binary_name") or loaded_path
        _require(
            isinstance(candidate_name, str) and bool(candidate_name),
            "binary name is missing",
        )
        file_name = _portable_binary_name(candidate_name)
        published["loaded_cpp_binary_path"] = (
            f"EXTERNAL_NATIVE_BINARY/{file_name}"
        )
        published["loaded_cpp_binary_name"] = file_name
    return published


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _write_json(path: Path, value: Any) -> None:
    _atomic_bytes(
        path,
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n",
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fieldnames = list(rows[0]) if rows else []
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            if fieldnames:
                writer.writeheader()
                writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _bag_tth_rows(payload: Mapping[str, Any], execution: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    bags = payload.get("bags")
    _require(isinstance(bags, list), "native payload.bags is missing")
    for raw in bags:
        _require(isinstance(raw, Mapping), "native bag row is not an object")
        completed = raw.get("completed") is True
        release = float(raw["release_time"])
        finish = float(raw["finish_time"])
        tth = finish - release if completed and finish >= 0.0 else None
        rows.append(
            {
                "execution": execution,
                "runtime_bag_id": int(raw["runtime_bag_id"]),
                "task_id": int(raw["task_id"]),
                "segment_id": str(raw["segment_id"]),
                "release_time": release,
                "finish_time": finish,
                "deadline": float(raw["deadline"]),
                "completed": completed,
                "failed": not completed,
                "failure_reason": str(raw.get("failure_reason", "")),
                "tth_seconds": tth,
                "deadline_miss": bool(
                    completed
                    and float(raw["deadline"]) >= 0.0
                    and finish > float(raw["deadline"])
                ),
                "decision_count": int(raw["decision_count"]),
                "retry_count": int(raw["retry_count"]),
                "junction_queue_wait_seconds": float(
                    raw["junction_queue_wait_seconds"]
                ),
                "merge_grant_wait_seconds": float(
                    raw.get("merge_grant_wait_seconds", 0.0)
                ),
            }
        )
    rows.sort(key=lambda row: int(row["runtime_bag_id"]))
    return rows


def _hard_gates(summary: Mapping[str, Any], segments: int, mode: str) -> dict[str, Any]:
    def strict_zero_int_fields(fields: Sequence[str]) -> bool:
        return all(
            field in summary
            and type(summary[field]) is int
            and summary[field] == 0
            for field in fields
        )

    global_scan_fields = (
        "global_reservation_scan_count",
        "priority_global_scan_count",
        "scorer_runtime_global_scan_count",
        "microphase_runtime_global_scan_count",
        "first_edge_credit_global_scan_count",
    )
    future_route_fields = (
        "priority_future_route_input_count",
        "scorer_future_route_input_count",
        "first_edge_credit_future_route_count",
    )
    future_schedule_fields = ("scorer_future_schedule_input_count",)
    teacher_input_fields = (
        "priority_teacher_input_count",
        "scorer_teacher_input_count",
    )
    unsafe_entry_count = summary.get(
        "unsafe_entry_count",
        summary.get("physical_fault_edge_entry_violation_count"),
    )
    live_merge_state_integrity = (
        summary.get("merge_grant_conservation_holds") is True
        and summary.get("merge_grant_active_bijection_holds") is True
        and summary.get("merge_grant_runtime_owned_capability") is True
        and summary.get("merge_grant_exact_slot_no_future_shift") is True
        and strict_zero_int_fields(
            (
                "merge_grant_final_active_unconsumed",
                "merge_grant_outstanding_request_count",
            )
        )
    )
    post_commit_rollback_matches_capacity_block = (
        type(summary.get("merge_grant_post_commit_rollback_count")) is int
        and type(summary.get("merge_grant_queue_capacity_block_count")) is int
        and summary["merge_grant_post_commit_rollback_count"]
        == summary["merge_grant_queue_capacity_block_count"]
    )
    gates = {
        "complete_coverage": (
            type(summary.get("requested_count")) is int
            and type(summary.get("completed_count")) is int
            and summary["requested_count"] == segments
            and summary["completed_count"] == segments
            and strict_zero_int_fields(("failed_count",))
        ),
        "reservation_conflicts_zero": strict_zero_int_fields(
            ("reservation_conflicts",)
        ),
        "physical_fault_edge_entry_violations_zero": (
            strict_zero_int_fields(
                ("physical_fault_edge_entry_violation_count",)
            )
        ),
        "unsafe_edge_entries_zero": (
            type(unsafe_entry_count) is int and unsafe_entry_count == 0
        ),
        "runtime_full_astar_calls_zero": strict_zero_int_fields(
            ("runtime_full_astar_calls",)
        ),
        "runtime_global_reservation_scans_zero": strict_zero_int_fields(
            global_scan_fields
        ),
        "runtime_future_route_reads_zero": strict_zero_int_fields(
            future_route_fields
        ),
        "runtime_future_schedule_reads_zero": (
            strict_zero_int_fields(future_schedule_fields)
        ),
        "teacher_inputs_zero": strict_zero_int_fields(teacher_input_fields),
        "reservation_depth_one": (
            type(summary.get("reservation_depth")) is int
            and summary["reservation_depth"] == 1
        ),
        "one_edge_per_arrival": (
            type(summary.get("max_edges_selected_per_arrive")) is int
            and type(summary.get("max_edges_selected_per_bag_per_decision"))
            is int
            and summary["max_edges_selected_per_arrive"] <= 1
            and summary["max_edges_selected_per_bag_per_decision"] <= 1
        ),
        "two_step_reservations_zero": strict_zero_int_fields(
            ("two_step_reservation_count",)
        ),
        "no_future_routes": (
            strict_zero_int_fields(("full_future_routes_stored",))
            and summary.get("bag_future_path_field_present") is False
        ),
        "unresolved_deadlocks_zero": strict_zero_int_fields(
            ("unresolved_deadlock_count",)
        ),
        "event_limit_not_reached": summary.get("event_limit_reached") is False,
        "time_limit_not_reached": summary.get("time_limit_reached") is False,
        "merge_stale_arbitrations_zero": (
            strict_zero_int_fields(
                (
                    "merge_grant_stale_arbitration_count",
                    "stale_arbitration_event_count",
                )
            )
        ),
        "artificial_batch_delay_zero": (
            isinstance(summary.get("artificial_batch_delay_seconds"), (int, float))
            and not isinstance(summary.get("artificial_batch_delay_seconds"), bool)
            and summary["artificial_batch_delay_seconds"] == 0.0
        ),
        "live_merge_state_integrity": live_merge_state_integrity,
        "post_commit_rollback_matches_queue_capacity_block": (
            post_commit_rollback_matches_capacity_block
        ),
    }
    if mode != "off":
        gates.update(
            {
                "supervisor_mode_echo": summary.get("g4irsf16_supervisor_mode") == mode,
                "diagnostic_only_honest": (
                    summary.get("g4irsf16_diagnostic_only") is True
                    and summary.get("g4irsf16_promotion_authorized") is False
                    and summary.get("g4irsf16_i4_policy_id") == "H5"
                ),
                "supervisor_global_scans_zero": (
                    strict_zero_int_fields(
                        ("g4irsf16_runtime_global_scan_count",)
                    )
                ),
                "supervisor_future_inputs_zero": (
                    strict_zero_int_fields(
                        (
                            "g4irsf16_future_route_input_count",
                            "g4irsf16_future_schedule_input_count",
                            "g4irsf16_posthoc_input_count",
                        )
                    )
                ),
                "supervisor_full_astar_calls_zero": (
                    strict_zero_int_fields(
                        ("g4irsf16_full_astar_call_count",)
                    )
                ),
            }
        )
    return {
        "mode": mode,
        "segments": segments,
        "gates": gates,
        "safety_pass": all(gates.values()),
        "merge_lifecycle_telemetry": {
            "transition_count": summary.get("merge_grant_lifecycle_transition_count"),
            "stored_count": summary.get("merge_grant_lifecycle_stored_count"),
            "dropped_count": summary.get("merge_grant_lifecycle_dropped_count"),
            "complete": summary.get("merge_grant_lifecycle_complete"),
            "truncated": int(summary.get("merge_grant_lifecycle_dropped_count", 0)) > 0,
            "safety_gate": False,
        },
        "merge_post_commit_telemetry": {
            "expired_count": summary.get("merge_grant_post_commit_expired_count"),
            "revoked_count": summary.get("merge_grant_post_commit_revoked_count"),
            "rollback_count": summary.get("merge_grant_post_commit_rollback_count"),
            "queue_capacity_block_count": summary.get(
                "merge_grant_queue_capacity_block_count"
            ),
            "rollback_matches_queue_capacity_block": (
                post_commit_rollback_matches_capacity_block
            ),
            "zero_required": False,
        },
        "action_change_observed": (
            int(summary.get("g4irsf16_action_change_count", 0)) > 0
            if mode == "closed_loop"
            else None
        ),
    }


_PERFORMANCE_FIELDS = (
    "original_entry_mean_minutes",
    "original_entry_p95_seconds",
    "original_entry_p99_seconds",
    "java_release_mean_minutes",
    "source_wait_mean_minutes",
    "network_time_mean_minutes",
    "total_system_time_mean_minutes",
)


def _raw_bag_performance(
    input_rows: Sequence[Mapping[str, Any]],
    payload: Mapping[str, Any],
    *,
    segments: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw_runtime_bags = payload.get("bags")
    _require(isinstance(raw_runtime_bags, list), "native payload.bags is missing")
    rows = g12.aggregate_raw_bag_timings(input_rows, raw_runtime_bags)
    summary = g12.summarize_raw_bag_timings(
        rows,
        selected_segment_count=segments,
    )
    _require(
        summary.get("comparison_eligible") is True,
        "raw-bag original-entry denominator is incomplete",
    )
    return rows, summary


def _performance_comparison(
    candidate: Mapping[str, Any],
    baseline: Mapping[str, Any] | None,
) -> dict[str, Any]:
    candidate_values = {field: candidate.get(field) for field in _PERFORMANCE_FIELDS}
    if baseline is None:
        return {
            "denominator": "raw_bag_original_entry_time_tth",
            "candidate": candidate_values,
            "off": None,
            "candidate_minus_off": None,
            "early_gate_evaluated": False,
            "p95_not_over_off_plus_2_seconds": False,
            "p99_not_over_off_plus_4_seconds": False,
            "early_gate_pass": False,
        }
    baseline_values = {field: baseline.get(field) for field in _PERFORMANCE_FIELDS}
    _require(
        all(candidate_values[field] is not None for field in _PERFORMANCE_FIELDS),
        "candidate raw-bag timing summary is incomplete",
    )
    _require(
        all(baseline_values[field] is not None for field in _PERFORMANCE_FIELDS),
        "off raw-bag timing summary is incomplete",
    )
    deltas = {
        field: float(candidate_values[field]) - float(baseline_values[field])
        for field in _PERFORMANCE_FIELDS
    }
    p95_pass = deltas["original_entry_p95_seconds"] <= 2.0
    p99_pass = deltas["original_entry_p99_seconds"] <= 4.0
    return {
        "denominator": "raw_bag_original_entry_time_tth",
        "candidate": candidate_values,
        "off": baseline_values,
        "candidate_minus_off": deltas,
        "early_gate_evaluated": True,
        "p95_limit_seconds": float(baseline_values["original_entry_p95_seconds"]) + 2.0,
        "p99_limit_seconds": float(baseline_values["original_entry_p99_seconds"]) + 4.0,
        "p95_not_over_off_plus_2_seconds": p95_pass,
        "p99_not_over_off_plus_4_seconds": p99_pass,
        "early_gate_pass": p95_pass and p99_pass,
    }


def _performance_table_rows(comparison: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidate = comparison["candidate"]
    baseline = comparison["off"]
    deltas = comparison["candidate_minus_off"]
    return [
        {
            "metric": field,
            "candidate": candidate[field],
            "off": baseline[field] if isinstance(baseline, Mapping) else None,
            "candidate_minus_off": (
                deltas[field] if isinstance(deltas, Mapping) else None
            ),
        }
        for field in _PERFORMANCE_FIELDS
    ]


def _finalize_canary_gates(
    gates: dict[str, Any],
    *,
    mode: str,
    performance: Mapping[str, Any],
) -> str:
    gates["early_performance_gates"] = {
        "denominator": performance["denominator"],
        "evaluated": performance["early_gate_evaluated"],
        "p95_not_over_off_plus_2_seconds": performance[
            "p95_not_over_off_plus_2_seconds"
        ],
        "p99_not_over_off_plus_4_seconds": performance[
            "p99_not_over_off_plus_4_seconds"
        ],
        "pass": performance["early_gate_pass"],
    }
    gates["safety_pass"] = all(gates["gates"].values())
    closed_loop_performance_pass = (
        mode != "closed_loop" or performance["early_gate_pass"] is True
    )
    gates["canary_pass"] = bool(
        gates["safety_pass"]
        and (mode != "closed_loop" or gates["action_change_observed"] is True)
        and closed_loop_performance_pass
    )
    return (
        "PASS"
        if gates["canary_pass"]
        else "FAIL_HARD_GATE"
        if not gates["safety_pass"]
        else "FAIL_NO_ACTION_CHANGE"
        if mode == "closed_loop" and gates["action_change_observed"] is not True
        else "FAIL_OFF_BASELINE_REQUIRED"
        if mode == "closed_loop" and performance["early_gate_evaluated"] is not True
        else "FAIL_EARLY_PERFORMANCE_GATE"
    )


def _activation_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for trace_kind in ("decisions", "hold_attempts"):
        raw_rows = payload.get(trace_kind, [])
        _require(isinstance(raw_rows, list), f"native {trace_kind} is not a list")
        for raw in raw_rows:
            if not isinstance(raw, Mapping):
                continue
            supervisor = raw.get("g4irsf16_supervisor")
            if not isinstance(supervisor, Mapping):
                continue
            i4 = supervisor.get("i4")
            if not isinstance(i4, Mapping) or i4.get("activation") is not True:
                continue
            metadata = raw.get("metadata")
            rows.append(
                {
                    "trace_kind": trace_kind,
                    "decision_id": raw.get("decision_id"),
                    "decision_ordinal": (
                        metadata.get("decision_ordinal")
                        if isinstance(metadata, Mapping)
                        else None
                    ),
                    "arrive_event_seq": (
                        metadata.get("arrive_event_seq")
                        if isinstance(metadata, Mapping)
                        else None
                    ),
                    "runtime_bag_id": (
                        metadata.get("runtime_bag_id")
                        if isinstance(metadata, Mapping)
                        else None
                    ),
                    "task_id": raw.get("task_id"),
                    "segment_id": raw.get("segment_id"),
                    "event_time": raw.get("event_time"),
                    "current_node": raw.get("current_node"),
                    "baseline_next": supervisor.get("baseline_next"),
                    "selected_next": raw.get("selected_next"),
                    "state": supervisor.get("state"),
                    "source": supervisor.get("source"),
                    "reason": supervisor.get("reason"),
                    "action_changed": supervisor.get("action_changed"),
                    "node_generation": supervisor.get("node_generation"),
                    "state_generation": supervisor.get("state_generation"),
                    "i4_policy_id": i4.get("policy_id"),
                    "i4_diagnostic_only": i4.get("diagnostic_only"),
                    "i4_reason": i4.get("reason"),
                }
            )
    return rows


def _run_native(
    *,
    binary: Path,
    segments: int,
    mode: str,
    rule_bundle: Path,
    trace_limit: int,
    enable_g4irsf17_source_wait_telemetry: bool = False,
    g4irsf17_source_wait_trace_limit: int = 200_000,
) -> Mapping[str, Any]:
    from czr005.cpp_backend import g4irsf11_event_runtime_from_records

    prefix = g12.load_input_prefix(segments, root=ROOT)
    nodes, edges, heuristic = canonical_graph_records(assert_canonical_map())
    request = dict(FROZEN_RUNTIME_CONTROLS)
    request.update(
        node_records=nodes,
        edge_records=edges,
        heuristic_time=heuristic,
        bag_records=g12.binding_bag_records(prefix),
        fault_windows=(),
        scenario=f"g4irsf16_{mode}_h5_{segments}",
        summary_only=False,
        trace_limit=trace_limit,
        trace_shard_count=1,
        trace_shard_index=0,
        event_trace_limit=0,
        enable_opportunity_telemetry=False,
        opportunity_trace_limit=0,
        scorer_model_path=(ROOT / MODEL_PATH).resolve(strict=True),
        expected_binary_path=binary,
        search_path=binary.parent,
        g4irsf16_supervisor_mode=mode,
        enable_g4irsf17_source_wait_telemetry=(
            enable_g4irsf17_source_wait_telemetry
        ),
        g4irsf17_source_wait_trace_limit=(
            g4irsf17_source_wait_trace_limit
        ),
    )
    if mode != "off":
        request["g4irsf16_rule_bundle"] = rule_bundle
    payload = g4irsf11_event_runtime_from_records(**request)
    _require(isinstance(payload, Mapping), "native payload is not an object")
    return payload


def _paired_tth(
    baseline: Sequence[Mapping[str, Any]],
    treatment: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    baseline_by_id = {int(row["runtime_bag_id"]): row for row in baseline}
    treatment_by_id = {int(row["runtime_bag_id"]): row for row in treatment}
    _require(baseline_by_id.keys() == treatment_by_id.keys(), "paired bag IDs drifted")
    rows: list[dict[str, Any]] = []
    for runtime_bag_id in sorted(baseline_by_id):
        before = baseline_by_id[runtime_bag_id]
        after = treatment_by_id[runtime_bag_id]
        _require(before["segment_id"] == after["segment_id"], "paired segment drifted")
        before_tth = before["tth_seconds"]
        after_tth = after["tth_seconds"]
        rows.append(
            {
                "runtime_bag_id": runtime_bag_id,
                "task_id": after["task_id"],
                "segment_id": after["segment_id"],
                "off_tth_seconds": before_tth,
                "closed_loop_tth_seconds": after_tth,
                "closed_loop_minus_off_tth_seconds": (
                    float(after_tth) - float(before_tth)
                    if before_tth is not None and after_tth is not None
                    else None
                ),
                "off_completed": before["completed"],
                "closed_loop_completed": after["completed"],
                "off_deadline_miss": before["deadline_miss"],
                "closed_loop_deadline_miss": after["deadline_miss"],
            }
        )
    return rows


def run_canary(
    *,
    binary: Path,
    segments: int,
    mode: str,
    rule_bundle: Path = DEFAULT_RULE_BUNDLE,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    trace_limit: int = 500_000,
    compare_off: bool = False,
) -> dict[str, Any]:
    _require(segments in ALLOWED_SEGMENTS, "unsupported canary segment count")
    _require(mode in {"off", "shadow", "closed_loop"}, "unsupported mode")
    _require(trace_limit != 0, "telemetry requires a nonzero trace limit")
    binary = binary.resolve(strict=True)
    rule_bundle = rule_bundle.resolve(strict=True)
    rule_bundle_self_sha256 = _rule_bundle_self_sha256(rule_bundle)
    model_path = (ROOT / MODEL_PATH).resolve(strict=True)
    _require(_sha256(model_path) == MODEL_SHA256, "frozen F2 scorer model drifted")
    prefix = g12.load_input_prefix(segments, root=ROOT)

    treatment = _run_native(
        binary=binary,
        segments=segments,
        mode=mode,
        rule_bundle=rule_bundle,
        trace_limit=trace_limit,
    )
    summary = treatment.get("summary")
    _require(isinstance(summary, Mapping), "native summary is missing")
    treatment_bags = _bag_tth_rows(treatment, mode)
    treatment_raw_bags, treatment_timing = _raw_bag_performance(
        prefix.rows,
        treatment,
        segments=segments,
    )
    gates = _hard_gates(summary, segments, mode)
    activations = _activation_rows(treatment)
    if mode != "off":
        gates["gates"]["telemetry_untruncated"] = (
            summary.get("decision_trace_truncated") is False
        )
        gates["gates"]["activation_trace_complete"] = (
            len(activations)
            == int(summary.get("g4irsf16_i4_activation_count", -1))
        )
    stem = f"g4irsf16_{mode}_h5_{segments}"
    output_dir = output_dir.resolve()
    paths = {
        "summary": output_dir / f"{stem}.summary.json",
        "bags": output_dir / f"{stem}.per_bag_tth.csv",
        "raw_bags": output_dir / f"{stem}.raw_bag_timings.csv",
        "hard_gates": output_dir / f"{stem}.hard_gates.json",
        "activations": output_dir / f"{stem}.activations.jsonl",
        "performance": output_dir / f"{stem}.raw_bag_performance.csv",
        "metadata": output_dir / f"{stem}.metadata.json",
    }

    baseline_summary: Mapping[str, Any] | None = None
    baseline_gates: dict[str, Any] | None = None
    baseline_timing: dict[str, Any] | None = None
    baseline_bags: list[dict[str, Any]] | None = None
    baseline_raw_bags: list[dict[str, Any]] | None = None
    paired_path: Path | None = None
    paired_summary: dict[str, Any] | None = None
    if compare_off and mode != "off":
        baseline = _run_native(
            binary=binary,
            segments=segments,
            mode="off",
            rule_bundle=rule_bundle,
            trace_limit=1,
        )
        raw_baseline_summary = baseline.get("summary")
        _require(isinstance(raw_baseline_summary, Mapping), "off summary missing")
        baseline_summary = raw_baseline_summary
        baseline_bags = _bag_tth_rows(baseline, "off")
        baseline_raw_bags, baseline_timing = _raw_bag_performance(
            prefix.rows,
            baseline,
            segments=segments,
        )
        baseline_gates = _hard_gates(baseline_summary, segments, "off")
        gates["gates"]["off_baseline_hard_gates_pass"] = baseline_gates[
            "safety_pass"
        ]
        paired_path = output_dir / f"{stem}.paired_tth_vs_off.csv"
        paired_rows = _paired_tth(baseline_bags, treatment_bags)
        _write_csv(paired_path, paired_rows)
        deltas = [
            float(row["closed_loop_minus_off_tth_seconds"])
            for row in paired_rows
            if row["closed_loop_minus_off_tth_seconds"] is not None
        ]
        paired_summary = {
            "paired_complete_count": len(deltas),
            "tth_delta_sum_seconds": sum(deltas),
            "tth_delta_mean_seconds": (
                sum(deltas) / len(deltas) if deltas else None
            ),
            "improved_bag_count": sum(delta < 0.0 for delta in deltas),
            "unchanged_bag_count": sum(delta == 0.0 for delta in deltas),
            "regressed_bag_count": sum(delta > 0.0 for delta in deltas),
        }

        paths.update(
            {
                "off_summary": output_dir / f"{stem}.off.summary.json",
                "off_bags": output_dir / f"{stem}.off.per_bag_tth.csv",
                "off_raw_bags": output_dir / f"{stem}.off.raw_bag_timings.csv",
                "off_hard_gates": output_dir / f"{stem}.off.hard_gates.json",
                "paired_tth": paired_path,
            }
        )

    performance = _performance_comparison(treatment_timing, baseline_timing)
    status = _finalize_canary_gates(
        gates,
        mode=mode,
        performance=performance,
    )

    _write_json(paths["summary"], _published_summary(summary))
    _write_csv(paths["bags"], treatment_bags)
    _write_csv(paths["raw_bags"], treatment_raw_bags)
    _write_json(paths["hard_gates"], gates)
    _write_csv(paths["performance"], _performance_table_rows(performance))
    _atomic_bytes(
        paths["activations"],
        b"".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
            + b"\n"
            for row in activations
        ),
    )
    if (
        baseline_summary is not None
        and baseline_gates is not None
        and baseline_bags is not None
        and baseline_raw_bags is not None
    ):
        _write_json(paths["off_summary"], _published_summary(baseline_summary))
        _write_csv(paths["off_bags"], baseline_bags)
        _write_csv(paths["off_raw_bags"], baseline_raw_bags)
        _write_json(paths["off_hard_gates"], baseline_gates)

    metadata = {
        "schema": SCHEMA,
        "status": status,
        "segments": segments,
        "mode": mode,
        "execution_semantics": "REAL_NATIVE_EVENT_RUNTIME_NOT_OFFLINE_REPLAY",
        "policy": {
            "selected_rule": "H0",
            "diagnostic_canary": "H5",
            "promotion_authorized": False,
            "authorization": "8192_DIAGNOSTIC_ONLY_NOT_PROMOTED",
            "rule_bundle_path": _metadata_path(rule_bundle),
            "rule_bundle_sha256": rule_bundle_self_sha256,
            "rule_bundle_identity_semantics": "CANONICAL_JSON_SELF_SHA256",
        },
        "binary": {
            "path": f"EXTERNAL_NATIVE_BINARY/{binary.name}",
            "file_name": binary.name,
            "sha256": _sha256(binary),
        },
        "frozen_scorer_model": {
            "path": _metadata_path(model_path),
            "sha256": MODEL_SHA256,
        },
        "hard_gates": gates,
        "raw_bag_performance": performance,
        "telemetry": {
            "activation_row_count": len(activations),
            "i4_activation_count": summary.get("g4irsf16_i4_activation_count", 0),
            "i4_applied_count": summary.get("g4irsf16_i4_applied_count", 0),
            "action_change_count": summary.get("g4irsf16_action_change_count", 0),
            "supervisor_evaluation_count": summary.get(
                "g4irsf16_supervisor_evaluation_count", 0
            ),
        },
        "off_comparison": (
            {
                "enabled": True,
                "off_completed_count": baseline_summary.get("completed_count"),
                "off_failed_count": baseline_summary.get("failed_count"),
                "off_hard_gates": baseline_gates,
                "paired_tth_path": _metadata_path(paired_path),
                "paired_tth_summary": paired_summary,
            }
            if baseline_summary is not None and paired_path is not None
            else {"enabled": False}
        ),
        "artifacts": {name: _metadata_path(path) for name, path in paths.items()},
    }
    _write_json(paths["metadata"], metadata)
    return metadata


def reconcile_existing_evidence(
    *,
    segments: int,
    mode: str,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    compare_off: bool = True,
) -> dict[str, Any]:
    """Re-evaluate published gates without re-running the native experiment.

    This is intentionally limited to a gate-contract correction.  Native
    summaries, compact activations, and raw-bag timing results must already
    exist; no result counter or performance value is synthesized.
    """

    _require(segments in ALLOWED_SEGMENTS, "unsupported canary segment count")
    _require(mode in {"off", "shadow", "closed_loop"}, "unsupported mode")
    stem = f"g4irsf16_{mode}_h5_{segments}"
    output_dir = output_dir.resolve()
    paths = {
        "summary": output_dir / f"{stem}.summary.json",
        "hard_gates": output_dir / f"{stem}.hard_gates.json",
        "activations": output_dir / f"{stem}.activations.jsonl",
        "performance": output_dir / f"{stem}.raw_bag_performance.csv",
        "metadata": output_dir / f"{stem}.metadata.json",
        "off_summary": output_dir / f"{stem}.off.summary.json",
        "off_hard_gates": output_dir / f"{stem}.off.hard_gates.json",
    }

    def read_mapping(path: Path, label: str) -> dict[str, Any]:
        _require(path.is_file(), f"existing {label} is missing")
        value = json.loads(path.read_text(encoding="utf-8"))
        _require(isinstance(value, dict), f"existing {label} is not an object")
        return value

    summary = read_mapping(paths["summary"], "candidate summary")
    metadata = read_mapping(paths["metadata"], "candidate metadata")
    previous_status = metadata.get("status")
    candidate_summary_sha256 = _sha256(paths["summary"])
    activation_sha256 = _sha256(paths["activations"])
    activation_count = sum(
        1
        for line in paths["activations"].read_text(encoding="utf-8").splitlines()
        if line.strip()
    )

    gates = _hard_gates(summary, segments, mode)
    if mode != "off":
        gates["gates"]["telemetry_untruncated"] = (
            summary.get("decision_trace_truncated") is False
        )
        gates["gates"]["activation_trace_complete"] = (
            activation_count
            == int(summary.get("g4irsf16_i4_activation_count", -1))
        )

    baseline_gates: dict[str, Any] | None = None
    baseline_summary_sha256: str | None = None
    if compare_off and mode != "off":
        baseline = read_mapping(paths["off_summary"], "off summary")
        baseline_summary_sha256 = _sha256(paths["off_summary"])
        baseline_gates = _hard_gates(baseline, segments, "off")
        gates["gates"]["off_baseline_hard_gates_pass"] = baseline_gates[
            "safety_pass"
        ]
        _write_json(paths["off_summary"], _published_summary(baseline))
        _write_json(paths["off_hard_gates"], baseline_gates)

    existing_performance = metadata.get("raw_bag_performance")
    _require(
        isinstance(existing_performance, Mapping),
        "existing raw-bag performance is missing",
    )
    candidate_performance = existing_performance.get("candidate")
    off_performance = existing_performance.get("off")
    _require(
        isinstance(candidate_performance, Mapping),
        "existing candidate raw-bag performance is missing",
    )
    if compare_off and mode != "off":
        _require(
            isinstance(off_performance, Mapping),
            "existing off raw-bag performance is missing",
        )
    performance = _performance_comparison(
        candidate_performance,
        off_performance if isinstance(off_performance, Mapping) else None,
    )
    status = _finalize_canary_gates(
        gates,
        mode=mode,
        performance=performance,
    )

    binary = metadata.get("binary")
    if isinstance(binary, Mapping):
        binary = dict(binary)
        old_path = binary.get("path")
        file_name = binary.get("file_name")
        candidate_name = file_name or old_path
        _require(
            isinstance(candidate_name, str) and bool(candidate_name),
            "binary name is missing",
        )
        file_name = _portable_binary_name(candidate_name)
        binary["file_name"] = file_name
        binary["path"] = f"EXTERNAL_NATIVE_BINARY/{file_name}"
        metadata["binary"] = binary
    metadata["status"] = status
    metadata["hard_gates"] = gates
    metadata["raw_bag_performance"] = performance
    off_comparison = metadata.get("off_comparison")
    if isinstance(off_comparison, Mapping):
        off_comparison = dict(off_comparison)
        if baseline_gates is not None:
            off_comparison["off_hard_gates"] = baseline_gates
        metadata["off_comparison"] = off_comparison
    metadata["evidence_reconciliation"] = {
        "performed": True,
        "native_runtime_reexecuted": False,
        "reason": (
            "CORRECT_BOUNDED_MERGE_TELEMETRY_AND_CAPACITY_ROLLBACK_GATE_SEMANTICS"
        ),
        "previous_status": previous_status,
        "candidate_native_summary_pre_reconciliation_sha256": (
            candidate_summary_sha256
        ),
        "off_native_summary_pre_reconciliation_sha256": (
            baseline_summary_sha256
        ),
        "activation_trace_sha256": activation_sha256,
        "activation_row_count": activation_count,
        "native_counters_or_timings_modified": False,
    }

    _write_json(paths["summary"], _published_summary(summary))
    _write_json(paths["hard_gates"], gates)
    _write_csv(paths["performance"], _performance_table_rows(performance))
    _write_json(paths["metadata"], metadata)
    return metadata


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--segments", type=int, choices=ALLOWED_SEGMENTS, required=True)
    parser.add_argument(
        "--mode", choices=("off", "shadow", "closed_loop"), default="closed_loop"
    )
    parser.add_argument("--rule-bundle", type=Path, default=DEFAULT_RULE_BUNDLE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--trace-limit", type=int, default=500_000)
    parser.add_argument("--compare-off", action="store_true")
    parser.add_argument(
        "--reconcile-existing",
        action="store_true",
        help="re-evaluate existing evidence without re-running native execution",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.reconcile_existing:
        metadata = reconcile_existing_evidence(
            segments=args.segments,
            mode=args.mode,
            output_dir=args.output_dir,
            compare_off=args.compare_off,
        )
    else:
        if args.binary is None:
            parser.error("--binary is required unless --reconcile-existing is used")
        metadata = run_canary(
            binary=args.binary,
            segments=args.segments,
            mode=args.mode,
            rule_bundle=args.rule_bundle,
            output_dir=args.output_dir,
            trace_limit=args.trace_limit,
            compare_off=args.compare_off,
        )
    print(
        json.dumps(
            {
                "status": metadata["status"],
                "segments": metadata["segments"],
                "mode": metadata["mode"],
                "action_change_count": metadata["telemetry"]["action_change_count"],
                "metadata_path": metadata["artifacts"]["metadata"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if metadata["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
