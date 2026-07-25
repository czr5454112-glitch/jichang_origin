"""Evaluate the G4IRSF12-L scale gate without generating or running workloads.

The evaluator is intentionally read-only with respect to task/runtime inputs.
It consumes the Phase-J candidate bundle, the Phase-K calibration protocol, and
the Phase-K 1.1x descriptor.  It writes only the four prescribed Phase-L
reports/tables.  Passing the gate merely authorises the *next* sequential tier;
it never materialises a task file or invokes the runtime.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import hashlib
from io import StringIO
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence
import uuid


ROOT = Path(__file__).resolve().parents[2]

EVALUATOR_SCHEMA = "czr005.g4irsf12.calibrated_scale_frontier_gate.v1"
J_BUNDLE_SCHEMA = "czr005.g4irsf12.original_scale_candidate_bundle.v4"
K_PROTOCOL_SCHEMA = "czr005.g4irsf12.demand_calibration_protocol.v1"
K_CANDIDATE_SCHEMA = "czr005.g4irsf12.demand_candidate_manifest.v1"

BLOCKED = "BLOCKED_NOT_RUN"
READY = "READY_FOR_1P0_REPEAT_NOT_RUN"
AUTHORIZED = "AUTHORIZED_NOT_RUN"
PREDECESSOR_BLOCKED = "BLOCKED_PREDECESSOR_NOT_STABLE"
NOT_MEASURED = "NOT_MEASURED_NO_RUNTIME_EXECUTION"

J_BUNDLE_PATH = Path("artifacts/policies/g4irsf12_original_scale_candidate_bundle.json")
K_PROTOCOL_PATH = Path("artifacts/configs/g4irsf12_demand_calibration_protocol.json")
K_1P1_PATH = Path("artifacts/tasks/g4irsf12/demand_1p1_candidate_manifest.json")
MAP_PATH = Path("data/processed/maps/map2.json")

FRONTIER_REPORT = Path("outputs/reports/g4irsf12_calibrated_scale_frontier.md")
FRONTIER_TABLE = Path("outputs/tables/g4irsf12_calibrated_scale_frontier.csv")
BACKLOG_TABLE = Path("outputs/tables/g4irsf12_backlog_clearance_by_scale.csv")
CLAIM_REPORT = Path("outputs/reports/g4irsf12_realistic_vs_stress_claim_boundary.md")

MAP_RAW_SHA256 = "9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4"
MAP_SEMANTIC_SHA256 = "67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63"
BASELINE_BAGS = 28_506
BASELINE_SEGMENTS = 43_603

SCALES = (
    (
        "1p0",
        "1.0",
        "historical_observed_day_reference",
        "historical 1.0x repeat",
        "historical observed day; not established as design day or peak day",
    ),
    (
        "1p1",
        "1.1",
        "mild_growth_sensitivity",
        "mild growth sensitivity",
        "uncalibrated sensitivity unless Phase-K supplies case-specific demand evidence",
    ),
    (
        "1p2",
        "1.2",
        "busy_day_candidate_not_calibrated",
        "busy-day candidate",
        "candidate label only; not a calibrated busy/design day",
    ),
    (
        "1p3",
        "1.3",
        "provisional_peak_envelope_not_calibrated",
        "provisional realistic envelope",
        "provisional envelope only; no realistic-peak claim while calibration is unknown",
    ),
    (
        "1p5",
        "1.5",
        "engineering_reserve_sensitivity",
        "engineering reserve",
        "engineering sensitivity, not an airport-demand forecast",
    ),
    (
        "2p0",
        "2.0",
        "extreme_stress_sensitivity",
        "extreme stress only",
        "stress-only label; never a realistic-demand claim without new evidence",
    ),
)

REQUIRED_CAPACITY_METRICS = (
    "arrivals_and_departures",
    "source_backlog",
    "network_backlog",
    "post_peak_backlog_clearance",
    "total_system_time",
    "deadline_miss_rate",
    "original_entry_p95_p99",
    "maximum_wait",
    "deadlock_and_starvation",
    "merge_utilization",
    "bottleneck",
    "runtime_and_memory",
    "model_pibt_shield_shares",
    "fault_recovery_at_stable_tier",
)


class PhaseLGateError(ValueError):
    """Raised for an invalid output path or programmer-level contract error."""


@dataclass(frozen=True)
class InputSnapshot:
    path: Path
    payload: dict[str, Any] | None
    raw_sha256: str
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class Evaluation:
    status: str
    blockers: tuple[str, ...]
    gates: Mapping[str, bool]
    promoted_candidate_id: str
    calibrated_multiplier: float | None
    calibration_status: str
    inputs: Mapping[str, Mapping[str, str]]
    frontier_rows: tuple[Mapping[str, Any], ...]
    backlog_rows: tuple[Mapping[str, Any], ...]
    source_date: str


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


def raw_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def semantic_sha256(path: Path) -> str:
    value = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(value).hexdigest()


def _atomic_write(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(value)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _resolve_input(root: Path, value: Path) -> Path:
    resolved = value.resolve() if value.is_absolute() else (root / value).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise PhaseLGateError(f"input escapes repository root: {resolved}")
    return resolved


def _snapshot(root: Path, relative: Path, label: str) -> InputSnapshot:
    path = _resolve_input(root, relative)
    if not path.is_file():
        return InputSnapshot(
            path=path,
            payload=None,
            raw_sha256="",
            blockers=(f"{label} is missing: {path.relative_to(root).as_posix()}",),
        )
    value = path.read_bytes()
    digest = hashlib.sha256(value).hexdigest()
    try:
        payload = json.loads(value.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        return InputSnapshot(
            path=path,
            payload=None,
            raw_sha256=digest,
            blockers=(f"{label} is not valid UTF-8 JSON: {exc}",),
        )
    if not isinstance(payload, dict):
        return InputSnapshot(
            path=path,
            payload=None,
            raw_sha256=digest,
            blockers=(f"{label} must be a JSON object",),
        )
    return InputSnapshot(path=path, payload=payload, raw_sha256=digest, blockers=())


def _valid_sha(value: Any) -> bool:
    text = str(value or "").lower()
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def _truth(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1", "pass", "yes"}


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _j_gate(bundle: Mapping[str, Any] | None) -> tuple[bool, str, list[str]]:
    blockers: list[str] = []
    if bundle is None:
        return False, "", ["Phase-J candidate bundle is unavailable"]
    if bundle.get("schema") != J_BUNDLE_SCHEMA:
        blockers.append("Phase-J candidate bundle schema is missing or unexpected")
    recorded_bundle_sha = str(bundle.get("bundle_sha256") or "")
    canonical = dict(bundle)
    canonical.pop("bundle_sha256", None)
    if not _valid_sha(recorded_bundle_sha) or canonical_sha256(canonical) != recorded_bundle_sha:
        blockers.append("Phase-J candidate bundle self-hash is missing or stale")
    if bundle.get("primary_denominator") != "original_entry_time_tth":
        blockers.append("Phase-J bundle is not bound to original_entry_time_tth")
    if bundle.get("promotion_status") != "READY":
        blockers.append("Phase-J has no engineering candidate with promotion_status READY")
    finalists = bundle.get("finalists")
    if not isinstance(finalists, list) or not finalists:
        blockers.append("Phase-J finalists are missing")
        return False, "", blockers
    promoted: list[Mapping[str, Any]] = []
    for finalist in finalists:
        if not isinstance(finalist, Mapping) or finalist.get("promotion_status") != "PROMOTED":
            continue
        finalist_ok = (
            int(finalist.get("executed_full_repeat_count") or 0) >= 5
            and finalist.get("repeat_gate") == "PASS"
            and finalist.get("v2_safe_original_entry_gate") == "PASS"
            and finalist.get("corrected_hca_original_entry_gate") == "PASS"
            and finalist.get("validated_full_gate") == "PASS"
            and _valid_sha(finalist.get("deterministic_result_sha256"))
            and _valid_sha(finalist.get("config_sha256"))
        )
        if finalist_ok:
            promoted.append(finalist)
    if not promoted:
        blockers.append(
            "Phase-J lacks five deterministic, validated full repeats meeting both matched "
            "original-entry targets"
        )
        return False, "", blockers
    promoted.sort(key=lambda row: str(row.get("candidate_id") or ""))
    return not blockers, str(promoted[0].get("candidate_id") or ""), blockers


def _expected_scale_rows(protocol: Mapping[str, Any] | None) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    if protocol is None:
        return False, ["Phase-K calibration protocol is unavailable"]
    raw_scales = protocol.get("candidate_scales")
    if not isinstance(raw_scales, list):
        return False, ["Phase-K candidate_scales is missing"]
    observed = [
        (
            str(row.get("scale_id") or ""),
            str(row.get("nominal_multiplier") or ""),
            str(row.get("classification") or ""),
        )
        for row in raw_scales
        if isinstance(row, Mapping)
    ]
    expected = [(scale_id, multiplier, classification) for scale_id, multiplier, classification, _, _ in SCALES]
    if observed != expected:
        blockers.append(
            "Phase-K scale sequence/labels differ from the frozen "
            "1.0/1.1/1.2/1.3/1.5/2.0 contract"
        )
    return not blockers, blockers


def _k_gates(
    root: Path,
    protocol: Mapping[str, Any] | None,
    one_p_one: Mapping[str, Any] | None,
) -> tuple[dict[str, bool], float | None, str, list[str]]:
    blockers: list[str] = []
    gates = {
        "phase_k_schema": False,
        "numeric_real_demand_calibration_complete": False,
        "finite_uncertainty_interval": False,
        "original_task_generation_audit_pass": False,
        "traceable_1p1_workload_artifact_exists": False,
        "protected_map_identity_matches": False,
        "scale_sequence_and_labels_frozen": False,
        "phase_k_all_gates_pass": False,
    }
    if protocol is None:
        return gates, None, "MISSING", ["Phase-K calibration protocol is unavailable"]
    gates["phase_k_schema"] = protocol.get("schema") == K_PROTOCOL_SCHEMA
    if not gates["phase_k_schema"]:
        blockers.append("Phase-K calibration protocol schema is missing or unexpected")
    scale_ok, scale_blockers = _expected_scale_rows(protocol)
    gates["scale_sequence_and_labels_frozen"] = scale_ok
    blockers.extend(scale_blockers)
    calibration = (
        protocol.get("calibration")
        if isinstance(protocol.get("calibration"), Mapping)
        else {}
    )
    multiplier = _finite_float(calibration.get("calibrated_multiplier"))
    calibration_status = str(calibration.get("calibrated_multiplier_status") or "MISSING")
    gates["numeric_real_demand_calibration_complete"] = (
        multiplier is not None
        and multiplier > 0.0
        and calibration_status in {"PASS", "CALIBRATED", "CALIBRATED_PASS"}
        and calibration.get("phase_k_status") == "PASS"
    )
    if not gates["numeric_real_demand_calibration_complete"]:
        blockers.append(
            "Phase-K calibrated multiplier is UNKNOWN_NOT_COMPUTABLE or not a numeric PASS"
        )
    interval = calibration.get("finite_uncertainty_interval")
    if isinstance(interval, Sequence) and not isinstance(interval, (str, bytes)) and len(interval) == 2:
        lower = _finite_float(interval[0])
        upper = _finite_float(interval[1])
        gates["finite_uncertainty_interval"] = (
            lower is not None and upper is not None and 0.0 < lower <= upper
        )
    if not gates["finite_uncertainty_interval"]:
        blockers.append("Phase-K has no finite, ordered demand-calibration uncertainty interval")
    phase_l = (
        protocol.get("phase_l_gates")
        if isinstance(protocol.get("phase_l_gates"), Mapping)
        else {}
    )
    gates["original_task_generation_audit_pass"] = _truth(
        phase_l.get("original_task_generation_audit_pass")
    )
    if not gates["original_task_generation_audit_pass"]:
        blockers.append("original raw-to-processed task construction audit is not PASS")
    protected = (
        protocol.get("protected_identity")
        if isinstance(protocol.get("protected_identity"), Mapping)
        else {}
    )
    map_path = root / MAP_PATH
    actual_raw = raw_sha256(map_path) if map_path.is_file() else ""
    actual_semantic = semantic_sha256(map_path) if map_path.is_file() else ""
    gates["protected_map_identity_matches"] = (
        _truth(phase_l.get("protected_map_identity_matches"))
        and protected.get("map_path") == MAP_PATH.as_posix()
        and protected.get("map_raw_sha256") == MAP_RAW_SHA256
        and protected.get("map_semantic_sha256") == MAP_SEMANTIC_SHA256
        and actual_raw == MAP_RAW_SHA256
        and actual_semantic == MAP_SEMANTIC_SHA256
    )
    if not gates["protected_map_identity_matches"]:
        blockers.append("protected map identity is missing, stale, or changed")
    traceable = _truth(phase_l.get("traceable_1p1_workload_artifact_exists"))
    if one_p_one is None:
        blockers.append("Phase-K 1.1x candidate manifest is unavailable")
    else:
        state = (
            one_p_one.get("artifact_state")
            if isinstance(one_p_one.get("artifact_state"), Mapping)
            else {}
        )
        task_output = state.get("task_output_path")
        task_path: Path | None = None
        if isinstance(task_output, str) and task_output.strip():
            try:
                task_path = _resolve_input(root, Path(task_output))
            except PhaseLGateError:
                task_path = None
        traceable = (
            traceable
            and one_p_one.get("schema") == K_CANDIDATE_SCHEMA
            and one_p_one.get("scale_id") == "1p1"
            and one_p_one.get("nominal_multiplier") == "1.1"
            and state.get("candidate_workload_materialized") is True
            and state.get("workload_generation_level")
            == "original_rule_replay_scaled_input"
            and task_path is not None
            and task_path.is_file()
            and _valid_sha(state.get("task_output_sha256"))
            and raw_sha256(task_path) == state.get("task_output_sha256")
        )
        if not traceable:
            blockers.append(
                "1.1x remains a non-materialized descriptor, not a hash-bound traceable workload"
            )
    gates["traceable_1p1_workload_artifact_exists"] = traceable
    gates["phase_k_all_gates_pass"] = (
        _truth(phase_l.get("all_gates_pass"))
        and phase_l.get("status") == "PASS"
        and protocol.get("execution_policy") == "SEQUENTIAL_SCALE_EXECUTION_AUTHORIZED"
    )
    if not gates["phase_k_all_gates_pass"]:
        blockers.append(
            "Phase-K phase_l_gates/all_gates_pass and sequential execution policy are not PASS"
        )
    # A PASS task-construction audit only proves the historical conversion.
    # It cannot compensate for a missing active larger-day generator.
    generation = (
        protocol.get("future_generation_protocol")
        if isinstance(protocol.get("future_generation_protocol"), Mapping)
        else {}
    )
    if (
        protocol.get("execution_policy") == "DESCRIPTORS_ONLY_NO_SCALING_RUN"
        or generation.get("current_state") == "DESCRIPTOR_ONLY_NOT_EXECUTED"
    ):
        blockers.append(
            "original task construction reproduces the historical day but licenses no scaled "
            "workload; future generation remains descriptor-only"
        )
    return gates, multiplier, calibration_status, sorted(set(blockers))


def _arithmetic_count(base: int, multiplier: str) -> int:
    return int(
        (Decimal(base) * Decimal(multiplier)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def _rows(
    *,
    ready: bool,
    blockers: Sequence[str],
    j_sha256: str,
    k_sha256: str,
    promoted_candidate_id: str,
    calibrated_multiplier: float | None,
) -> tuple[tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...]]:
    frontier: list[Mapping[str, Any]] = []
    backlog: list[Mapping[str, Any]] = []
    blocker_text = " | ".join(blockers)
    predecessor = ""
    for index, (scale_id, multiplier, classification, display_label, boundary) in enumerate(SCALES):
        first_authorized = ready and index == 0
        execution_status = (
            AUTHORIZED
            if first_authorized
            else PREDECESSOR_BLOCKED
            if ready
            else BLOCKED
        )
        row_blocker = (
            ""
            if first_authorized
            else (
                f"{predecessor or 'global Phase-L gate'} has no stable executed PASS"
                if ready
                else blocker_text
            )
        )
        frontier.append(
            {
                "schema": EVALUATOR_SCHEMA,
                "sequence_index": index,
                "scale_id": scale_id,
                "nominal_multiplier": multiplier,
                "classification": classification,
                "display_label": display_label,
                "planning_bag_count_arithmetic_only": _arithmetic_count(
                    BASELINE_BAGS, multiplier
                ),
                "planning_segment_count_arithmetic_only": _arithmetic_count(
                    BASELINE_SEGMENTS, multiplier
                ),
                "calibrated_multiplier": (
                    "" if calibrated_multiplier is None else calibrated_multiplier
                ),
                "real_demand_claim": False,
                "historical_day_claim": scale_id == "1p0",
                "workload_materialized_by_phase_l": False,
                "runtime_executed": False,
                "execution_authorized": first_authorized,
                "execution_status": execution_status,
                "predecessor_scale_id": predecessor,
                "predecessor_stability_status": (
                    "NOT_APPLICABLE"
                    if index == 0
                    else "NOT_EVALUATED_NO_RUNTIME_EXECUTION"
                ),
                "promoted_phase_j_candidate_id": promoted_candidate_id,
                "phase_j_bundle_file_sha256": j_sha256,
                "phase_k_protocol_file_sha256": k_sha256,
                "required_capacity_metrics": json.dumps(
                    REQUIRED_CAPACITY_METRICS, separators=(",", ":")
                ),
                "blocker": row_blocker,
                "claim_boundary": boundary,
            }
        )
        backlog.append(
            {
                "schema": EVALUATOR_SCHEMA,
                "sequence_index": index,
                "scale_id": scale_id,
                "nominal_multiplier": multiplier,
                "execution_status": execution_status,
                "measurement_status": NOT_MEASURED,
                "arrival_count": "",
                "departure_count": "",
                "peak_source_backlog": "",
                "peak_network_backlog": "",
                "last_arrival_time_seconds": "",
                "source_backlog_clearance_seconds": "",
                "network_backlog_clearance_seconds": "",
                "post_peak_backlog_clearance_seconds": "",
                "backlog_drain_to_zero": "",
                "unresolved_deadlock_count": "",
                "stability_status": "NOT_EVALUATED",
                "blocker": row_blocker or "runtime was not executed by the Phase-L gate evaluator",
            }
        )
        predecessor = scale_id
    return tuple(frontier), tuple(backlog)


def evaluate(
    root: Path,
    *,
    j_bundle_path: Path = J_BUNDLE_PATH,
    k_protocol_path: Path = K_PROTOCOL_PATH,
    k_1p1_path: Path = K_1P1_PATH,
) -> Evaluation:
    """Compute Phase-L authority from immutable snapshots; perform no mutations."""

    root = root.resolve()
    j = _snapshot(root, j_bundle_path, "Phase-J candidate bundle")
    k = _snapshot(root, k_protocol_path, "Phase-K calibration protocol")
    one_p_one = _snapshot(root, k_1p1_path, "Phase-K 1.1x candidate manifest")
    blockers = [*j.blockers, *k.blockers, *one_p_one.blockers]
    j_pass, candidate_id, j_blockers = _j_gate(j.payload)
    blockers.extend(j_blockers)
    k_gates, multiplier, calibration_status, k_blockers = _k_gates(
        root, k.payload, one_p_one.payload
    )
    blockers.extend(k_blockers)
    gates: dict[str, bool] = {
        "phase_j_original_1x_full_pass": j_pass,
        **k_gates,
    }
    ready = all(gates.values()) and not blockers
    status = READY if ready else BLOCKED
    blockers = sorted(set(blockers))
    frontier, backlog = _rows(
        ready=ready,
        blockers=blockers,
        j_sha256=j.raw_sha256,
        k_sha256=k.raw_sha256,
        promoted_candidate_id=candidate_id,
        calibrated_multiplier=multiplier,
    )
    source_date = ""
    if k.payload is not None:
        source_date = str(k.payload.get("published_date") or "")
    inputs = {
        "phase_j_candidate_bundle": {
            "path": j.path.relative_to(root).as_posix(),
            "file_sha256": j.raw_sha256,
        },
        "phase_k_calibration_protocol": {
            "path": k.path.relative_to(root).as_posix(),
            "file_sha256": k.raw_sha256,
        },
        "phase_k_1p1_manifest": {
            "path": one_p_one.path.relative_to(root).as_posix(),
            "file_sha256": one_p_one.raw_sha256,
        },
    }
    return Evaluation(
        status=status,
        blockers=tuple(blockers),
        gates=gates,
        promoted_candidate_id=candidate_id,
        calibrated_multiplier=multiplier,
        calibration_status=calibration_status,
        inputs=inputs,
        frontier_rows=frontier,
        backlog_rows=backlog,
        source_date=source_date,
    )


def _csv_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    if not rows:
        raise PhaseLGateError("cannot write an empty evidence table")
    output = StringIO(newline="")
    fieldnames = list(rows[0])
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def _frontier_report(evaluation: Evaluation) -> str:
    gate_lines = [
        f"| {name} | {'PASS' if passed else 'BLOCKED'} |"
        for name, passed in evaluation.gates.items()
    ]
    blocker_lines = [f"- {blocker}" for blocker in evaluation.blockers] or ["- None."]
    scale_lines = [
        (
            f"| {row['nominal_multiplier']}x | {row['display_label']} | "
            f"{row['execution_status']} | false | false |"
        )
        for row in evaluation.frontier_rows
    ]
    return "\n".join(
        [
            "# G4IRSF12-L Calibrated Scale Frontier",
            "",
            f"Source date: `{evaluation.source_date or 'UNAVAILABLE'}`.",
            f"Status: `{evaluation.status}`.",
            f"Calibrated multiplier: `{evaluation.calibration_status}`.",
            "",
            "This is a gate evaluation, not a workload generator or runtime runner. No scale "
            "workload was materialized and no capacity measurement was executed.",
            "",
            "## Start gates",
            "",
            "| Gate | Status |",
            "| --- | --- |",
            *gate_lines,
            "",
            "## Blockers",
            "",
            *blocker_lines,
            "",
            "## Frozen sequential ladder",
            "",
            "| Scale | Label | Execution status | Workload generated here | Runtime run |",
            "| --- | --- | --- | --- | --- |",
            *scale_lines,
            "",
            "Only a full gate PASS could authorise the 1.0x repeat. Every later tier remains "
            "blocked until its immediate predecessor has an executed stability PASS including "
            "backlog drain, tails/deadlines, and zero unresolved deadlock.",
            "",
            "The maximum stable calibrated scale is therefore `NOT_ESTABLISHED`.",
            "",
        ]
    )


def _claim_report(evaluation: Evaluation) -> str:
    rows = [
        f"| {multiplier}x | {label} | {boundary} |"
        for _, multiplier, _, label, boundary in SCALES
    ]
    return "\n".join(
        [
            "# G4IRSF12-L Realistic vs Stress Claim Boundary",
            "",
            f"Status: `{evaluation.status}`.",
            "",
            "A numeric real-demand multiplier is not available unless Phase-K supplies a "
            "case-specific represented-system design-day numerator, a finite uncertainty "
            "interval, and a traceable 1.1x workload. Arithmetic counts are descriptors only.",
            "",
            "| Scale | Frozen label | Permitted claim |",
            "| --- | --- | --- |",
            *rows,
            "",
            "The original task-construction audit proves that the immutable 28,506 raw bags "
            "reproduce 43,603 processed segments under the historical Java split rules. Its "
            "negative generator finding means it does not license a larger day, new OD demand, "
            "time compression, or the label `original_project_generated`.",
            "",
            "The 1.0x input is a historical observed day, not a proven ordinary, peak, or design "
            "day. While calibration is `UNKNOWN_NOT_COMPUTABLE`, 1.1x through 1.3x are "
            "uncalibrated sensitivities, 1.5x is engineering reserve, and 2.0x is extreme stress "
            "only. None is demonstrated capacity.",
            "",
            "No 4x/8x/16x tier is part of this calibrated ladder. G4J remains a separate closed "
            "publication gate and is not opened by Phase-L evidence.",
            "",
        ]
    )


def write_outputs(root: Path, evaluation: Evaluation) -> tuple[Path, Path, Path, Path]:
    root = root.resolve()
    outputs = (
        root / FRONTIER_REPORT,
        root / FRONTIER_TABLE,
        root / BACKLOG_TABLE,
        root / CLAIM_REPORT,
    )
    if any(not path.resolve().is_relative_to(root) for path in outputs):
        raise PhaseLGateError("an output escapes repository root")
    # Recheck source bytes immediately before publication.  A concurrent input
    # rewrite must not be hidden behind a mixed-snapshot report.
    for descriptor in evaluation.inputs.values():
        path = root / descriptor["path"]
        expected = descriptor["file_sha256"]
        if expected and (
            not path.is_file() or raw_sha256(path) != expected
        ):
            raise PhaseLGateError(
                f"input changed during evaluation: {descriptor['path']}"
            )
    _atomic_write(outputs[0], _frontier_report(evaluation).encode("utf-8"))
    _atomic_write(outputs[1], _csv_bytes(evaluation.frontier_rows))
    _atomic_write(outputs[2], _csv_bytes(evaluation.backlog_rows))
    _atomic_write(outputs[3], _claim_report(evaluation).encode("utf-8"))
    return outputs


def run(
    root: Path,
    *,
    j_bundle_path: Path = J_BUNDLE_PATH,
    k_protocol_path: Path = K_PROTOCOL_PATH,
    k_1p1_path: Path = K_1P1_PATH,
) -> Evaluation:
    evaluation = evaluate(
        root,
        j_bundle_path=j_bundle_path,
        k_protocol_path=k_protocol_path,
        k_1p1_path=k_1p1_path,
    )
    write_outputs(root, evaluation)
    return evaluation


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--j-bundle", type=Path, default=J_BUNDLE_PATH)
    parser.add_argument("--k-protocol", type=Path, default=K_PROTOCOL_PATH)
    parser.add_argument("--k-1p1", type=Path, default=K_1P1_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    evaluation = run(
        args.root,
        j_bundle_path=args.j_bundle,
        k_protocol_path=args.k_protocol,
        k_1p1_path=args.k_1p1,
    )
    print(
        json.dumps(
            {
                "schema": EVALUATOR_SCHEMA,
                "status": evaluation.status,
                "blockers": list(evaluation.blockers),
                "calibrated_multiplier_status": evaluation.calibration_status,
                "workloads_materialized": 0,
                "runtime_executions": 0,
                "output_paths": [
                    FRONTIER_REPORT.as_posix(),
                    FRONTIER_TABLE.as_posix(),
                    BACKLOG_TABLE.as_posix(),
                    CLAIM_REPORT.as_posix(),
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if evaluation.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
