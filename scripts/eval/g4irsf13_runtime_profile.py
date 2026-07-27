"""Profile the frozen F2 event runtime without changing its algorithm.

The native event runtime currently exposes aggregate wall time, decision
latency, operation counters, and C++ local-state memory accounting.  It does
not expose independent native timers for every requested subsystem.  This
study therefore records measured timers where they exist and labels the other
rows ``COUNTER_ONLY_NATIVE_TIMER_UNAVAILABLE`` rather than inventing a time
split.  No optimization is applied by this module.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import inspect
import io
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT, ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


from scripts.eval import g4irsf12_reproducible_harness as harness
from scripts.eval.g4irsf11_fixed_map import (
    assert_canonical_map,
    canonical_graph_records,
)


PROFILE_PATH = Path("outputs/tables/g4irsf13_runtime_stage_profile.csv")
EQUIVALENCE_PATH = Path("outputs/tables/g4irsf13_runtime_equivalence.csv")
REPORT_PATH = Path("outputs/reports/g4irsf13_runtime_profile.md")
KL_DECISION_PATH = Path("artifacts/gates/g4irsf13_kl_unlock_decision.json")
SCHEMA = "czr005.g4irsf13.runtime_profile.v1"
KL_SCHEMA = "czr005.g4irsf13.kl_unlock_decision.v1"
DEFAULT_REPEATS = 5
FROZEN_BINARY_SHA256 = (
    "814b233016a51a755d6f568604fcb04ca81d781222416075cf2648ec087f1de7"
)
KL_SOURCE_SPECS = {
    "original_scale_joint_candidate": (
        Path("artifacts/policies/g4irsf13_final_candidate_bundle.json"),
        "bundle_sha256",
    ),
    "v3_offline_candidate": (
        Path("artifacts/policies/g4irsf13_v3_candidate_bundle.json"),
        "bundle_sha256",
    ),
    "fault_control": (
        Path("artifacts/policies/g4irsf13_fault_control_bundle.json"),
        "self_sha256",
    ),
    "demand_calibration": (
        Path("artifacts/configs/g4irsf12_demand_calibration_protocol.json"),
        None,
    ),
}


class ProfileError(ValueError):
    """Raised when runtime profile evidence is incomplete or inconsistent."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProfileError(f"cannot read canonical JSON artifact: {path}") from exc
    if not isinstance(value, dict):
        raise ProfileError(f"expected JSON object: {path}")
    return value


def _source_binding(
    *,
    root: Path,
    label: str,
    relative_path: Path,
    self_hash_field: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    path = root / relative_path
    payload = _read_json(path)
    binding: dict[str, Any] = {
        "path": relative_path.as_posix(),
        "canonical_sha256": _sha256(payload),
        "self_hash_field": self_hash_field or "NOT_APPLICABLE",
        "declared_self_sha256": "NOT_APPLICABLE",
        "self_hash_valid": "NOT_APPLICABLE",
    }
    if self_hash_field is not None:
        declared = payload.get(self_hash_field)
        projection = dict(payload)
        projection.pop(self_hash_field, None)
        observed = _sha256(projection)
        if not isinstance(declared, str) or len(declared) != 64:
            raise ProfileError(
                f"{label} lacks a valid declared {self_hash_field}"
            )
        if declared != observed:
            raise ProfileError(
                f"{label} declared {self_hash_field} does not self-hash"
            )
        binding.update(
            {
                "declared_self_sha256": declared,
                "self_hash_valid": True,
            }
        )
    return payload, binding


def build_kl_unlock_decision(root: Path = ROOT) -> dict[str, Any]:
    """Build the fail-closed G4J/K/L decision from canonical source artifacts."""

    sources: dict[str, dict[str, Any]] = {}
    bindings: dict[str, dict[str, Any]] = {}
    for label, (path, self_hash_field) in KL_SOURCE_SPECS.items():
        payload, binding = _source_binding(
            root=root,
            label=label,
            relative_path=path,
            self_hash_field=self_hash_field,
        )
        sources[label] = payload
        bindings[label] = binding

    joint = sources["original_scale_joint_candidate"]
    v3 = sources["v3_offline_candidate"]
    fault = sources["fault_control"]
    demand = sources["demand_calibration"]
    phase_l = demand.get("phase_l_gates")
    if not isinstance(phase_l, Mapping):
        raise ProfileError("demand calibration lacks phase_l_gates")

    observed = {
        "strict_v2_win": joint.get("strict_win_vs_v2_safe"),
        "v3_contribution": joint.get("v3_contribution_proven"),
        "fault_discriminating": fault.get("status")
        == "FAULT_DISCRIMINATING_PASS",
        "numeric_demand_calibration": phase_l.get(
            "numeric_real_demand_calibration_complete"
        ),
        "original_task_generation_audit": phase_l.get(
            "original_task_generation_audit_pass"
        ),
    }
    expected = {
        "strict_v2_win": False,
        "v3_contribution": False,
        "fault_discriminating": True,
        "numeric_demand_calibration": False,
        "original_task_generation_audit": True,
    }
    if observed != expected:
        raise ProfileError(
            "K/L source-gate snapshot drifted; fail closed: "
            f"observed={observed!r}"
        )
    if (
        joint.get("decision", {}).get("strict_win_vs_v2_safe") is not False
        or v3.get("offline_gate_status") != "FAIL"
        or v3.get("runtime_eligible") is not False
        or v3.get("closed_loop_status") != "NOT_RUN"
        or fault.get("executed_case_gate_pass") is not True
        or fault.get("frozen_binary_sha256") != FROZEN_BINARY_SHA256
        or demand.get("execution_policy") != "DESCRIPTORS_ONLY_NO_SCALING_RUN"
    ):
        raise ProfileError("K/L corroborating source fields drifted; fail closed")

    gate_sources = {
        "strict_v2_win": (
            "original_scale_joint_candidate.strict_win_vs_v2_safe"
        ),
        "v3_contribution": (
            "original_scale_joint_candidate.v3_contribution_proven"
        ),
        "fault_discriminating": "fault_control.status",
        "numeric_demand_calibration": (
            "demand_calibration.phase_l_gates."
            "numeric_real_demand_calibration_complete"
        ),
        "original_task_generation_audit": (
            "demand_calibration.phase_l_gates."
            "original_task_generation_audit_pass"
        ),
    }
    gates = [
        {
            "gate_id": gate_id,
            "passed": bool(observed[gate_id]),
            "source_field": gate_sources[gate_id],
        }
        for gate_id in expected
    ]
    all_pass = all(row["passed"] for row in gates)
    if all_pass:
        raise ProfileError(
            "unexpected K/L unlock: formal scale execution is not authorized"
        )
    payload: dict[str, Any] = {
        "schema": KL_SCHEMA,
        "source_artifacts": bindings,
        "gates": gates,
        "all_five_gates_pass": False,
        "g4j_status": "CLOSED",
        "phase_k_status": "UNKNOWN/CLOSED",
        "phase_l_status": "NOT_RUN",
        "scale_execution_status": "NOT_RUN",
        "scale_execution_count": 0,
        "decision": "PARTIAL_WITH_EXPLICIT_BLOCKER",
        "blockers": [
            "strict win versus the reconciled v2-safe target is false",
            "V3 independent contribution is not demonstrated",
            "numeric real-demand calibration is unavailable",
        ],
        "claim_boundary": (
            "No scale workload is materialized or executed. Fault "
            "discrimination and task-generation audit passes cannot unlock "
            "G4J, K, or L while the other three gates are false."
        ),
    }
    payload["self_sha256"] = _sha256(payload)
    return payload


def validate_kl_unlock_decision(
    payload: Mapping[str, Any],
    *,
    root: Path = ROOT,
) -> dict[str, Any]:
    """Recompute every binding and reject any fail-open or hash drift."""

    candidate = dict(payload)
    declared = candidate.pop("self_sha256", None)
    if not isinstance(declared, str) or declared != _sha256(candidate):
        raise ProfileError("K/L decision self-hash drift")
    rebuilt = build_kl_unlock_decision(root)
    if dict(payload) != rebuilt:
        raise ProfileError("K/L decision differs from recomputed source gates")
    if (
        payload.get("g4j_status") != "CLOSED"
        or payload.get("phase_k_status") != "UNKNOWN/CLOSED"
        or payload.get("phase_l_status") != "NOT_RUN"
        or payload.get("scale_execution_status") != "NOT_RUN"
        or payload.get("scale_execution_count") != 0
        or payload.get("all_five_gates_pass") is not False
    ):
        raise ProfileError("K/L decision violated fail-closed boundary")
    return {
        "self_sha256": declared,
        "source_count": len(payload.get("source_artifacts", {})),
        "gate_count": len(payload.get("gates", [])),
        "g4j_status": payload["g4j_status"],
        "phase_k_status": payload["phase_k_status"],
        "phase_l_status": payload["phase_l_status"],
    }


def _f2_case() -> harness.CaseSpec:
    matches = [
        case
        for case in harness.original_scale_cases()
        if case.candidate_id == "J_F2"
    ]
    if len(matches) != 1:
        raise ProfileError(f"expected one frozen F2 case, got {len(matches)}")
    return matches[0]


def _filtered_controls() -> dict[str, Any]:
    from czr005 import cpp_backend

    accepted = set(
        inspect.signature(
            cpp_backend.g4irsf11_event_runtime_from_records
        ).parameters
    )
    return {
        key: value
        for key, value in _f2_case().runtime_controls.items()
        if key in accepted
    }


def _algorithm_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    summary = dict(payload["summary"])
    for field in (
        "runtime_seconds",
        "event_throughput_per_second",
        "decision_latency_us_p50",
        "decision_latency_us_p95",
        "decision_latency_us_p99",
    ):
        summary.pop(field, None)
    return {
        "bags": payload.get("bags", []),
        "junction_state": payload.get("junction_state", []),
        "summary": summary,
        "trace_context": payload.get("trace_context", {}),
    }


def _rss_peak_bytes() -> int:
    try:
        import psutil
    except ImportError as exc:  # pragma: no cover - dependency is bundled
        raise ProfileError("psutil is required for Windows peak RSS") from exc
    memory = psutil.Process(os.getpid()).memory_info()
    return int(getattr(memory, "peak_wset", memory.rss))


def execute_repeats(
    *,
    size_segments: int,
    repeats: int,
    search_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if repeats < 1:
        raise ProfileError("repeats must be positive")
    if size_segments not in harness.SIZE_LADDER:
        raise ProfileError(
            f"size must be one of {harness.SIZE_LADDER}"
        )
    if not search_path.is_dir():
        raise ProfileError(f"C++ search path is missing: {search_path}")

    from czr005 import cpp_backend

    prefix = harness.load_input_prefix(size_segments, root=ROOT)
    nodes, edges, heuristic = canonical_graph_records(
        assert_canonical_map(ROOT / harness.CANONICAL_MAP_PATH)
    )
    controls = _filtered_controls()
    rows: list[dict[str, Any]] = []
    first_digest = ""
    first_binary = ""
    last_payload: dict[str, Any] = {}
    for repeat_index in range(repeats):
        before_peak = _rss_peak_bytes()
        started = time.perf_counter()
        payload = cpp_backend.g4irsf11_event_runtime_from_records(
            node_records=nodes,
            edge_records=edges,
            heuristic_time=heuristic,
            bag_records=harness.binding_bag_records(prefix),
            fault_windows=[],
            scenario=f"g4irsf13_profile_f2_{size_segments}",
            summary_only=True,
            trace_limit=0,
            event_trace_limit=0,
            search_path=search_path,
            **controls,
        )
        wall = time.perf_counter() - started
        after_peak = _rss_peak_bytes()
        summary = payload.get("summary")
        if not isinstance(summary, Mapping):
            raise ProfileError("runtime payload lacks summary")
        digest = _sha256(_algorithm_projection(payload))
        binary = str(summary.get("loaded_cpp_binary_sha256", ""))
        if len(binary) != 64:
            raise ProfileError("runtime binary SHA-256 is missing")
        if repeat_index == 0:
            first_digest = digest
            first_binary = binary
        completed = int(summary.get("completed_count", -1))
        requested = int(summary.get("requested_count", -1))
        hard_pass = (
            requested == size_segments
            and completed == size_segments
            and binary == FROZEN_BINARY_SHA256
            and int(summary.get("failed_count", -1)) == 0
            and int(summary.get("reservation_conflicts", -1)) == 0
            and int(summary.get("runtime_full_astar_calls", -1)) == 0
            and int(summary.get("global_reservation_scan_count", -1)) == 0
            and int(summary.get("full_future_routes_stored", -1)) == 0
            and int(summary.get("unresolved_deadlock_count", -1)) == 0
            and summary.get("event_limit_reached") is False
            and summary.get("time_limit_reached") is False
            and int(summary.get("reservation_depth", -1)) == 1
        )
        rows.append(
            {
                "schema": SCHEMA,
                "candidate_id": "J_F2",
                "size_segments": size_segments,
                "repeat_index": repeat_index,
                "requested_count": requested,
                "completed_count": completed,
                "hard_gate_pass": hard_pass,
                "python_end_to_end_wall_seconds": wall,
                "native_runtime_seconds": float(
                    summary.get("runtime_seconds", math.nan)
                ),
                "pybind_wrapper_residual_seconds": max(
                    0.0,
                    wall - float(summary.get("runtime_seconds", 0.0)),
                ),
                "event_count": int(summary.get("event_count", 0)),
                "event_throughput_per_second": float(
                    summary.get("event_throughput_per_second", 0.0)
                ),
                "decision_count": int(summary.get("decision_count", 0)),
                "decision_latency_us_p50": float(
                    summary.get("decision_latency_us_p50", 0.0)
                ),
                "decision_latency_us_p95": float(
                    summary.get("decision_latency_us_p95", 0.0)
                ),
                "decision_latency_us_p99": float(
                    summary.get("decision_latency_us_p99", 0.0)
                ),
                "cpp_internal_accounted_bytes": int(
                    summary.get("cpp_internal_accounted_bytes", 0)
                ),
                "process_peak_rss_bytes": max(before_peak, after_peak),
                "algorithm_projection_sha256": digest,
                "equivalent_to_repeat_0": digest == first_digest,
                "binary_sha256": binary,
                "binary_equivalent_to_repeat_0": binary == first_binary,
                "map_raw_sha256": harness.CANONICAL_MAP_RAW_SHA256,
                "task_raw_sha256": harness.CANONICAL_SOURCE_RAW_SHA256,
                "input_prefix_sha256": prefix.prefix_sha256,
                "case_config_sha256": harness.canonical_sha256(
                    _f2_case().as_dict()
                ),
            }
        )
        last_payload = dict(payload)
    return rows, last_payload


def _counter(
    summary: Mapping[str, Any],
    *names: str,
) -> int:
    return sum(int(summary.get(name, 0)) for name in names)


def build_stage_rows(
    repeat_rows: Sequence[Mapping[str, Any]],
    payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if not repeat_rows:
        raise ProfileError("profile requires repeat rows")
    summary = payload["summary"]
    junctions = payload.get("junction_state", [])
    service_reservations = sum(
        int(row.get("service_reservation_count", 0)) for row in junctions
    )
    native_mean = statistics.fmean(
        float(row["native_runtime_seconds"]) for row in repeat_rows
    )
    wrapper_mean = statistics.fmean(
        float(row["pybind_wrapper_residual_seconds"]) for row in repeat_rows
    )
    wall_mean = statistics.fmean(
        float(row["python_end_to_end_wall_seconds"]) for row in repeat_rows
    )
    peak_rss = max(int(row["process_peak_rss_bytes"]) for row in repeat_rows)
    rows = [
        {
            "schema": SCHEMA,
            "stage": "native_event_runtime_total",
            "measurement_status": "MEASURED_NATIVE_TIMER",
            "mean_seconds": native_mean,
            "operation_count": int(summary.get("event_count", 0)),
            "counter_semantics": "processed scheduler events",
            "share_of_end_to_end_wall": native_mean / wall_mean,
        },
        {
            "schema": SCHEMA,
            "stage": "pybind_wrapper_and_payload",
            "measurement_status": "MEASURED_OUTER_MINUS_NATIVE_TIMER",
            "mean_seconds": wrapper_mean,
            "operation_count": len(payload.get("bags", [])),
            "counter_semantics": "returned bag rows",
            "share_of_end_to_end_wall": wrapper_mean / wall_mean,
        },
        {
            "schema": SCHEMA,
            "stage": "event_heap",
            "measurement_status": "COUNTER_ONLY_NATIVE_TIMER_UNAVAILABLE",
            "mean_seconds": "",
            "operation_count": int(summary.get("event_count", 0)),
            "counter_semantics": "pop/process count; heap push time not isolated",
            "share_of_end_to_end_wall": "",
        },
        {
            "schema": SCHEMA,
            "stage": "local_calendar",
            "measurement_status": "COUNTER_ONLY_NATIVE_TIMER_UNAVAILABLE",
            "mean_seconds": "",
            "operation_count": service_reservations,
            "counter_semantics": (
                "completed local service reservations; purge/lookup timer "
                "not isolated"
            ),
            "share_of_end_to_end_wall": "",
        },
        {
            "schema": SCHEMA,
            "stage": "candidate_feature_and_scorer",
            "measurement_status": "SHARED_DECISION_LATENCY_TIMER",
            "mean_seconds": "",
            "operation_count": int(
                summary.get("scorer_candidate_evaluation_count", 0)
            ),
            "counter_semantics": (
                "candidate evaluations; decision p50/p95/p99 reported in "
                "equivalence table"
            ),
            "share_of_end_to_end_wall": "",
        },
        {
            "schema": SCHEMA,
            "stage": "pibt_prepare_validate",
            "measurement_status": "COUNTER_ONLY_NATIVE_TIMER_UNAVAILABLE",
            "mean_seconds": "",
            "operation_count": _counter(
                summary,
                "bounded_local_pibt_prepare_count",
                "bounded_local_pibt_validate_count",
            ),
            "counter_semantics": "atomic P2 prepare plus validate operations",
            "share_of_end_to_end_wall": "",
        },
        {
            "schema": SCHEMA,
            "stage": "pibt_owner_map",
            "measurement_status": "COUNTER_ONLY_NATIVE_TIMER_UNAVAILABLE",
            "mean_seconds": "",
            "operation_count": int(
                summary.get("bounded_local_pibt_attempt_count", 0)
            ),
            "counter_semantics": "bounded owner/proposal transactions",
            "share_of_end_to_end_wall": "",
        },
        {
            "schema": SCHEMA,
            "stage": "first_edge_credit_lifecycle",
            "measurement_status": "COUNTER_ONLY_NATIVE_TIMER_UNAVAILABLE",
            "mean_seconds": "",
            "operation_count": _counter(
                summary,
                "first_edge_credit_issue_attempt_count",
                "first_edge_credit_validation_attempt_count",
                "first_edge_credit_consume_attempt_count",
                "first_edge_credit_expired_count",
                "first_edge_credit_fault_revocation_count",
            ),
            "counter_semantics": "issue/validate/consume/expire/fault-revoke",
            "share_of_end_to_end_wall": "",
        },
        {
            "schema": SCHEMA,
            "stage": "fault_overlay",
            "measurement_status": "NO_FAULT_BASELINE_COUNTER",
            "mean_seconds": "",
            "operation_count": _counter(
                summary,
                "fault_event_count",
                "local_fault_policy_action_count",
                "physical_fault_interlock_rejection_count",
            ),
            "counter_semantics": "no-fault F2 control; expected zero",
            "share_of_end_to_end_wall": "",
        },
        {
            "schema": SCHEMA,
            "stage": "trace_serialization",
            "measurement_status": "NOT_MEASURED_SUMMARY_ONLY_PROFILE",
            "mean_seconds": "",
            "operation_count": int(
                summary.get("decision_trace_stored_count", 0)
            ),
            "counter_semantics": (
                "trace deliberately suppressed; no speed claim for trace path"
            ),
            "share_of_end_to_end_wall": "",
        },
        {
            "schema": SCHEMA,
            "stage": "input_output",
            "measurement_status": "NOT_MEASURED_PRELOADED_INPUT_SUMMARY_ONLY",
            "mean_seconds": "",
            "operation_count": len(payload.get("bags", [])),
            "counter_semantics": (
                "canonical input is loaded before the timed call and output "
                "is returned in memory; file I/O is outside this profile"
            ),
            "share_of_end_to_end_wall": "",
        },
        {
            "schema": SCHEMA,
            "stage": "process_peak_rss",
            "measurement_status": "MEASURED_WINDOWS_PEAK_WORKING_SET",
            "mean_seconds": "",
            "operation_count": peak_rss,
            "counter_semantics": "bytes; process-level upper bound",
            "share_of_end_to_end_wall": "",
        },
    ]
    return rows


def _csv_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        values: dict[str, Any] = {}
        for key in fields:
            value = row.get(key, "")
            if isinstance(value, bool):
                values[key] = "True" if value else "False"
            elif isinstance(value, float):
                values[key] = format(value, ".17g")
            else:
                values[key] = value
        writer.writerow(values)
    return stream.getvalue().encode("utf-8")


def build_report(
    repeats: Sequence[Mapping[str, Any]],
    stages: Sequence[Mapping[str, Any]],
    kl_decision: Mapping[str, Any],
) -> bytes:
    wall = statistics.fmean(
        float(row["python_end_to_end_wall_seconds"]) for row in repeats
    )
    native = statistics.fmean(
        float(row["native_runtime_seconds"]) for row in repeats
    )
    wrapper = statistics.fmean(
        float(row["pybind_wrapper_residual_seconds"]) for row in repeats
    )
    decision_p50 = statistics.fmean(
        float(row["decision_latency_us_p50"]) for row in repeats
    )
    decision_p95 = statistics.fmean(
        float(row["decision_latency_us_p95"]) for row in repeats
    )
    decision_p99 = statistics.fmean(
        float(row["decision_latency_us_p99"]) for row in repeats
    )
    peak = max(int(row["process_peak_rss_bytes"]) for row in repeats)
    all_equivalent = all(
        bool(row["equivalent_to_repeat_0"])
        and bool(row["binary_equivalent_to_repeat_0"])
        and bool(row["hard_gate_pass"])
        for row in repeats
    )
    unavailable = [
        str(row["stage"])
        for row in stages
        if "TIMER_UNAVAILABLE" in str(row["measurement_status"])
    ]
    content = [
        "# G4IRSF13 Runtime Profile",
        "",
        (
            "Status: `PROFILE_COMPLETE_NO_OPTIMIZATION_APPLIED`"
            if all_equivalent
            else "Status: `PROFILE_INVALID`"
        ),
        "",
        f"Population: {repeats[0]['size_segments']} protected segments; "
        f"deterministic repeats: {len(repeats)}.",
        "",
        f"- mean Python end-to-end wall: {wall:.6f}s",
        f"- mean native event-runtime wall: {native:.6f}s",
        f"- mean pybind/payload residual wall: {wrapper:.6f}s",
        (
            "- mean native decision latency p50/p95/p99: "
            f"{decision_p50:.6f}/{decision_p95:.6f}/{decision_p99:.6f} us"
        ),
        f"- process peak working set upper bound: {peak} bytes",
        f"- repeat algorithm/binary equivalence: {all_equivalent}",
        "",
        "This stage profiles F2 as future-scaling preparation. Runtime speed "
        "does not explain or close the baggage TTH gap, and this study applies "
        "no algorithm or safety change.",
        "",
        "Native aggregate and shared decision-latency timers are measured. "
        "The following requested subsystems currently expose counters but no "
        "independent native timer: "
        + ", ".join(unavailable)
        + ". They remain explicitly counter-only; no fabricated percentage "
        "or optimization claim is made.",
        "",
        "Trace serialization and file I/O are excluded by the summary-only, "
        "preloaded-input profile and are therefore `NOT_MEASURED`, not "
        "assumed free. Any future optimization must first add an isolated "
        "native timer and then prove deterministic result, TTH, counter, and "
        "safety equivalence.",
        "",
        "## G4J / Phase K / Phase L unlock decision",
        "",
        "| Gate | Pass | Canonical source field |",
        "|---|---:|---|",
    ]
    for gate in kl_decision["gates"]:
        content.append(
            f"| `{gate['gate_id']}` | `{str(gate['passed']).lower()}` | "
            f"`{gate['source_field']}` |"
        )
    content.extend(
        [
            "",
            f"- G4J: `{kl_decision['g4j_status']}`",
            f"- Phase K: `{kl_decision['phase_k_status']}`",
            f"- Phase L: `{kl_decision['phase_l_status']}`",
            (
                "- scale execution: "
                f"`{kl_decision['scale_execution_status']}` "
                f"(count={kl_decision['scale_execution_count']})"
            ),
            "",
            "The five gates are conjunctive. Two supporting gates pass "
            "(fault discrimination and original-task generation audit), but "
            "the strict-v2, V3-contribution, and numeric-demand-calibration "
            "gates are false. The validator therefore fails closed: G4J stays "
            "closed, K remains unknown/closed, L is not run, and no scale "
            "workload is executed.",
            "",
        ]
    )
    return "\n".join(content).encode("utf-8")


def _parse_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def validate_committed() -> dict[str, Any]:
    profile_path = ROOT / PROFILE_PATH
    equivalence_path = ROOT / EQUIVALENCE_PATH
    report_path = ROOT / REPORT_PATH
    kl_path = ROOT / KL_DECISION_PATH
    if not all(
        path.is_file()
        for path in (profile_path, equivalence_path, report_path, kl_path)
    ):
        raise ProfileError("committed profile artifacts are incomplete")
    stages = _parse_csv(profile_path)
    repeats = _parse_csv(equivalence_path)
    if not stages or not repeats:
        raise ProfileError("committed profile tables are empty")
    stages_by_id = {row["stage"]: row for row in stages}
    if len(stages_by_id) != len(stages):
        raise ProfileError("duplicate runtime profile stage")
    expected_nonmeasured = {
        "trace_serialization": "NOT_MEASURED_SUMMARY_ONLY_PROFILE",
        "input_output": "NOT_MEASURED_PRELOADED_INPUT_SUMMARY_ONLY",
    }
    if any(
        stages_by_id.get(stage, {}).get("measurement_status") != status
        or stages_by_id.get(stage, {}).get("mean_seconds", "") != ""
        or stages_by_id.get(stage, {}).get("share_of_end_to_end_wall", "")
        != ""
        for stage, status in expected_nonmeasured.items()
    ):
        raise ProfileError("trace or file-I/O profile boundary drift")
    counter_only = [
        row
        for row in stages
        if row["measurement_status"]
        == "COUNTER_ONLY_NATIVE_TIMER_UNAVAILABLE"
    ]
    if not counter_only or any(
        row.get("mean_seconds", "") != ""
        or row.get("share_of_end_to_end_wall", "") != ""
        for row in counter_only
    ):
        raise ProfileError("counter-only subsystem gained a fabricated timer")
    digests = {row["algorithm_projection_sha256"] for row in repeats}
    binaries = {row["binary_sha256"] for row in repeats}
    if len(digests) != 1 or len(binaries) != 1:
        raise ProfileError("deterministic repeat hash or binary drift")
    if (
        len(repeats) != DEFAULT_REPEATS
        or {row["candidate_id"] for row in repeats} != {"J_F2"}
        or {int(row["size_segments"]) for row in repeats}
        != {harness.FULL_SIZE_SEGMENTS}
        or binaries != {FROZEN_BINARY_SHA256}
    ):
        raise ProfileError(
            "formal profile must be full F2, five repeats, frozen binary"
        )
    if not all(
        row["hard_gate_pass"] == "True"
        and row["equivalent_to_repeat_0"] == "True"
        and row["binary_equivalent_to_repeat_0"] == "True"
        for row in repeats
    ):
        raise ProfileError("committed repeat equivalence gate failed")
    report = report_path.read_text(encoding="utf-8")
    if (
        "PROFILE_COMPLETE_NO_OPTIMIZATION_APPLIED" not in report
        or "G4J: `CLOSED`" not in report
        or "Phase K: `UNKNOWN/CLOSED`" not in report
        or "Phase L: `NOT_RUN`" not in report
    ):
        raise ProfileError("runtime profile report status drift")
    kl_validation = validate_kl_unlock_decision(
        _read_json(kl_path),
        root=ROOT,
    )
    return {
        "stage_count": len(stages),
        "repeat_count": len(repeats),
        "algorithm_projection_sha256": next(iter(digests)),
        "binary_sha256": next(iter(binaries)),
        "kl_decision": kl_validation,
    }


def _write(path: Path, payload: bytes) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(target)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--validate-committed", action="store_true")
    parser.add_argument(
        "--size-segments",
        type=int,
        default=harness.FULL_SIZE_SEGMENTS,
    )
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument(
        "--search-path",
        type=Path,
        default=ROOT / "build_g4irsf12" / "python",
    )
    args = parser.parse_args(argv)
    result: dict[str, Any] = {"schema": SCHEMA}
    if args.run:
        if args.write and (
            args.size_segments != harness.FULL_SIZE_SEGMENTS
            or args.repeats != DEFAULT_REPEATS
        ):
            raise ProfileError(
                "formal --write requires the full 43,603-segment F2 profile "
                "with exactly five deterministic repeats"
            )
        repeats, payload = execute_repeats(
            size_segments=args.size_segments,
            repeats=args.repeats,
            search_path=args.search_path,
        )
        stages = build_stage_rows(repeats, payload)
        kl_decision = build_kl_unlock_decision(ROOT)
        validate_kl_unlock_decision(kl_decision, root=ROOT)
        result["run"] = {
            "size_segments": args.size_segments,
            "repeat_count": args.repeats,
            "algorithm_projection_sha256": repeats[0][
                "algorithm_projection_sha256"
            ],
        }
        if args.write:
            _write(EQUIVALENCE_PATH, _csv_bytes(repeats))
            _write(PROFILE_PATH, _csv_bytes(stages))
            _write(
                KL_DECISION_PATH,
                _canonical_bytes(kl_decision) + b"\n",
            )
            _write(REPORT_PATH, build_report(repeats, stages, kl_decision))
    elif args.write:
        raise ProfileError("--write requires --run")
    if args.validate_committed:
        result["validation"] = validate_committed()
    if not args.run and not args.validate_committed:
        parser.error("choose --run and/or --validate-committed")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
