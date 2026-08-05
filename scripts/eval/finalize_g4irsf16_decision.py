"""Fail-closed, read-only aggregation of the formal G4IRSF16 evidence.

The source evidence is never rewritten.  This command validates the sealed
offline decision, full native shadow, four matched E4 diagnostic canaries, and
the supervisor contract regression before publishing a compact decision
ledger.  H5 is deliberately treated as plumbing evidence, never as a promoted
candidate.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tempfile
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _import_root in (ROOT, ROOT / "src"):
    if str(_import_root) not in sys.path:
        sys.path.insert(0, str(_import_root))

from czr005.g4irsf16.model import (  # noqa: E402
    DEPLOYMENT_FEATURES,
    SelectiveEnsembleModel,
)

SCHEMA = "czr005.g4irsf16.final_decision.v1"
LADDER_SEGMENTS = (144, 512, 2_048, 8_192)
OFFLINE_NO_GO = "CAUSAL_LEARNING_MODEL_NO_GO"
FINAL_STATUS = "CAUSAL_LEARNING_NO_GO_WITH_ACTIONABLE_PIVOT"
FINAL_AUDIT_STATUS = "SEALED_NOT_CONSUMED"
H5_AUTHORIZATION = "8192_DIAGNOSTIC_ONLY_NOT_PROMOTED"
REQUIRED_OFF_GATES = frozenset(
    {
        "artificial_batch_delay_zero",
        "complete_coverage",
        "event_limit_not_reached",
        "live_merge_state_integrity",
        "merge_stale_arbitrations_zero",
        "no_future_routes",
        "one_edge_per_arrival",
        "physical_fault_edge_entry_violations_zero",
        "post_commit_rollback_matches_queue_capacity_block",
        "reservation_conflicts_zero",
        "reservation_depth_one",
        "runtime_full_astar_calls_zero",
        "runtime_future_route_reads_zero",
        "runtime_future_schedule_reads_zero",
        "runtime_global_reservation_scans_zero",
        "teacher_inputs_zero",
        "time_limit_not_reached",
        "two_step_reservations_zero",
        "unresolved_deadlocks_zero",
        "unsafe_edge_entries_zero",
    }
)
REQUIRED_CANARY_GATES = REQUIRED_OFF_GATES.union(
    {
        "activation_trace_complete",
        "diagnostic_only_honest",
        "off_baseline_hard_gates_pass",
        "supervisor_full_astar_calls_zero",
        "supervisor_future_inputs_zero",
        "supervisor_global_scans_zero",
        "supervisor_mode_echo",
        "telemetry_untruncated",
    }
)


class FinalizationError(RuntimeError):
    """Raised when the evidence cannot support the published decision."""


@dataclass(frozen=True)
class EvidencePaths:
    offline_gate: Path
    full_shadow: Path
    rule_bundle: Path
    i4_model: Path
    i3_model: Path
    externality_model: Path
    closed_loop_dir: Path
    contract_summary: Path
    historical_bundle: Path
    mechanism_boundary_report: Path

    @classmethod
    def defaults(cls) -> "EvidencePaths":
        return cls(
            offline_gate=ROOT / "artifacts/gates/g4irsf16_offline_model_gate.json",
            full_shadow=ROOT / "outputs/reports/g4irsf16_full_shadow.json",
            rule_bundle=ROOT / "artifacts/policies/g4irsf16_best_rule_bundle.json",
            i4_model=(
                ROOT / "artifacts/models/g4irsf16_i4_d0_calibrated_logistic.json"
            ),
            i3_model=ROOT / "artifacts/models/g4irsf16_i3_risk_veto.json",
            externality_model=(
                ROOT / "artifacts/models/g4irsf16_externality_risk_balanced.json"
            ),
            closed_loop_dir=ROOT / "outputs/runtime/g4irsf16_closed_loop",
            contract_summary=(
                ROOT
                / "outputs/reports/g4irsf16_tail_pibt_fault_contract_summary.json"
            ),
            historical_bundle=(
                ROOT / "artifacts/policies/g4irsf14_final_candidate_bundle.json"
            ),
            mechanism_boundary_report=(
                ROOT / "outputs/reports/g4irsf16_start_state.md"
            ),
        )

    def source_files(self) -> tuple[Path, ...]:
        canaries = tuple(
            self.closed_loop_dir
            / f"g4irsf16_closed_loop_h5_{segments}.metadata.json"
            for segments in LADDER_SEGMENTS
        )
        return (
            self.offline_gate,
            self.full_shadow,
            self.rule_bundle,
            self.i4_model,
            self.i3_model,
            self.externality_model,
            *canaries,
            self.contract_summary,
            self.historical_bundle,
            self.mechanism_boundary_report,
        )


@dataclass(frozen=True)
class OutputPaths:
    final_gate: Path
    ladder_csv: Path
    joint_csv: Path
    ladder_report: Path
    joint_report: Path

    @classmethod
    def defaults(cls) -> "OutputPaths":
        return cls(
            final_gate=ROOT / "artifacts/gates/g4irsf16_final_decision.json",
            ladder_csv=ROOT / "outputs/tables/g4irsf16_closed_loop_ladder.csv",
            joint_csv=ROOT / "outputs/tables/g4irsf16_original_scale_joint_ab.csv",
            ladder_report=(
                ROOT / "outputs/reports/g4irsf16_closed_loop_ladder.md"
            ),
            joint_report=(
                ROOT
                / "outputs/reports/g4irsf16_original_scale_joint_decision.md"
            ),
        )

    def files(self) -> tuple[Path, ...]:
        return (
            self.final_gate,
            self.ladder_csv,
            self.joint_csv,
            self.ladder_report,
            self.joint_report,
        )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FinalizationError(message)


def _load_json(path: Path) -> dict[str, Any]:
    _require(path.is_file(), f"required evidence is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FinalizationError(f"cannot read JSON evidence {path}: {exc}") from exc
    _require(isinstance(value, dict), f"JSON evidence must be an object: {path}")
    return value


def _number(value: Any, label: str) -> float:
    _require(
        isinstance(value, (int, float)) and not isinstance(value, bool),
        f"{label} must be numeric",
    )
    result = float(value)
    _require(result == result and abs(result) != float("inf"), f"{label} not finite")
    return result


def _close(actual: float, expected: float, label: str, tolerance: float = 1e-9) -> None:
    _require(
        abs(actual - expected) <= tolerance,
        f"{label} is internally inconsistent: {actual} != {expected}",
    )


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    return value


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_model(
    value: Mapping[str, Any],
    *,
    label: str,
    expected_kind: str,
) -> str:
    _require(
        value.get("schema") == "czr005.g4irsf16.selective_linear_ensemble.v1",
        f"{label}: unexpected model schema",
    )
    _require(value.get("kind") == expected_kind, f"{label}: model kind mismatch")
    declared = value.get("self_sha256")
    unsigned = dict(value)
    unsigned.pop("self_sha256", None)
    _require(
        isinstance(declared, str) and declared == _canonical_sha256(unsigned),
        f"{label}: MODEL_SELF_SHA256_MISMATCH",
    )
    try:
        parsed = SelectiveEnsembleModel.from_artifact(value)
    except (KeyError, TypeError, ValueError) as exc:
        raise FinalizationError(f"{label}: malformed deployable model: {exc}") from exc
    _require(
        parsed.feature_names == DEPLOYMENT_FEATURES,
        f"{label}: deployable feature schema is not the exact 29-field contract",
    )
    training = _mapping(value.get("training_metadata"), f"{label}.training_metadata")
    _require(
        training.get("final_audit_consumed") is False,
        f"{label}: final audit entered model training or selection",
    )
    _require(training.get("fit_split") == "train", f"{label}: fit split is not train")
    return declared


def _validate_model_bindings(
    *,
    offline: Mapping[str, Any],
    shadow: Mapping[str, Any],
    i4_model: Mapping[str, Any],
    i3_model: Mapping[str, Any],
    externality_model: Mapping[str, Any],
    paths: EvidencePaths,
) -> dict[str, Any]:
    i4_sha = _validate_model(i4_model, label="I4", expected_kind="I4")
    i3_sha = _validate_model(
        i3_model,
        label="I3 risk veto",
        expected_kind="I3_RISK_VETO_DIAGNOSTIC",
    )
    externality_sha = _validate_model(
        externality_model,
        label="externality",
        expected_kind="H_SYSTEM_EXTERNALITY",
    )

    i4_training = _mapping(i4_model.get("training_metadata"), "I4.training_metadata")
    _require(
        i4_training.get("threshold_split") == "calibration"
        and i4_training.get("promotion_split") == "validation",
        "I4 train/calibration/validation split contract changed",
    )
    _require(
        i4_training.get("deployment_status")
        == "SUPPORT_DIAGNOSTIC_ONLY_NOT_AUTHORIZED"
        and i4_training.get("support_authorization_status") == "NOT_AUTHORIZED",
        "I4 model authorization disagrees with offline no-go",
    )
    i3_training = _mapping(i3_model.get("training_metadata"), "I3.training_metadata")
    _require(
        i3_training.get("threshold_split") == "calibration"
        and i3_training.get("promotion_split") == "validation"
        and i3_training.get("deployment_status") == "RISK_VETO_ONLY_DIAGNOSTIC",
        "I3 diagnostic model authorization disagrees with offline gate",
    )
    offline_externality = _mapping(offline.get("externality"), "offline.externality")
    _require(
        offline_externality.get("status")
        == "DIAGNOSTIC_SMALL_HEAD_NOT_INDEPENDENTLY_PROMOTED",
        "externality model unexpectedly promoted",
    )

    shadow_models = _mapping(shadow.get("models"), "shadow.models")
    shadow_i4 = _mapping(shadow_models.get("I4"), "shadow.models.I4")
    _require(shadow_i4.get("artifact_sha256") == i4_sha, "shadow I4 SHA is stale")
    _require(
        shadow_i4.get("path") == _repo_path(paths.i4_model),
        "shadow I4 path does not bind the selected model",
    )
    thresholds = _mapping(i4_model.get("thresholds"), "I4.thresholds")
    _close(
        _number(
            shadow_i4.get("harmful_probability_ucb_budget"),
            "shadow I4 harmful budget",
        ),
        _number(thresholds.get("harmful_probability_ucb"), "I4 harmful budget"),
        "shadow/model harmful-risk budget",
        tolerance=1e-12,
    )
    return {
        "I4": {
            "path": _repo_path(paths.i4_model),
            "self_sha256": i4_sha,
            "model_gate_status": "I4_SELECTIVE_MODEL_NO_GO",
            "support_authorization_status": "NOT_AUTHORIZED",
            "deployment_status": "SUPPORT_DIAGNOSTIC_ONLY_NOT_AUTHORIZED",
            "full_shadow_sha_match": True,
        },
        "I3": {
            "path": _repo_path(paths.i3_model),
            "self_sha256": i3_sha,
            "model_gate_status": "I3_REROUTE_MODEL_NOT_AUTHORIZED",
            "deployment_status": "RISK_VETO_ONLY_DIAGNOSTIC",
            "runtime_action_authorized": False,
        },
        "externality": {
            "path": _repo_path(paths.externality_model),
            "self_sha256": externality_sha,
            "model_gate_status": (
                "DIAGNOSTIC_SMALL_HEAD_NOT_INDEPENDENTLY_PROMOTED"
            ),
            "runtime_action_authorized": False,
        },
    }


def _repo_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _portable_repo_artifact(value: Any, label: str, *, must_exist: bool = True) -> Path:
    _require(isinstance(value, str) and value, f"{label} must be a nonempty path")
    _require("\\" not in value, f"{label} contains a non-portable backslash")
    _require(":" not in value, f"{label} contains an absolute-drive marker")
    pure = PurePosixPath(value)
    _require(not pure.is_absolute(), f"{label} must be repository-relative")
    _require(".." not in pure.parts, f"{label} escapes the repository")
    resolved = ROOT.joinpath(*pure.parts).resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise FinalizationError(f"{label} escapes the repository") from exc
    _require(not must_exist or resolved.is_file(), f"{label} does not exist: {value}")
    return resolved


def _portable_external_binary(value: Any, label: str) -> str:
    _require(isinstance(value, str), f"{label} must be a path")
    prefix = "EXTERNAL_NATIVE_BINARY/"
    _require(value.startswith(prefix), f"{label} is not canonical external provenance")
    name = value[len(prefix) :]
    _require(
        bool(name) and "/" not in name and "\\" not in name and ":" not in name,
        f"{label} contains a non-portable binary name",
    )
    return name


def _scan_zstd_jsonl(
    path: Path,
    *,
    expected_rows: int,
    expected_uncompressed_bytes: int,
) -> dict[str, int]:
    """Read, parse, and validate every row without materializing the table."""

    try:
        import zstandard
    except ImportError as exc:  # pragma: no cover - dependency contract
        raise FinalizationError("zstandard is required for validate-only") from exc

    row_count = 0
    byte_count = 0
    final_byte = b""
    decision_ordinals: set[int] = set()
    uncompressed_digest = hashlib.sha256()
    try:
        with path.open("rb") as raw:
            with zstandard.ZstdDecompressor().stream_reader(raw) as reader:
                with io.BufferedReader(reader, buffer_size=1024 * 1024) as buffered:
                    for line in buffered:
                        _require(line.endswith(b"\n"), "shadow prediction row lacks newline")
                        byte_count += len(line)
                        final_byte = line[-1:]
                        uncompressed_digest.update(line)
                        try:
                            row = json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise FinalizationError(
                                f"invalid shadow prediction JSON at row {row_count + 1}"
                            ) from exc
                        _require(
                            isinstance(row, Mapping)
                            and row.get("schema")
                            == "czr005.g4irsf16.shadow_prediction.v1",
                            f"shadow prediction schema mismatch at row {row_count + 1}",
                        )
                        _require(
                            row.get("model_feature_leakage") is False,
                            f"model feature leakage at shadow row {row_count + 1}",
                        )
                        _require(
                            row.get("illegal_proposal") is False,
                            f"illegal proposal at shadow row {row_count + 1}",
                        )
                        f2 = _mapping(row.get("f2"), f"shadow row {row_count + 1}.f2")
                        _require(
                            f2.get("action_unchanged") is True,
                            f"F2 action mutation at shadow row {row_count + 1}",
                        )
                        i4 = _mapping(row.get("i4"), f"shadow row {row_count + 1}.i4")
                        counts = _mapping(
                            i4.get("causal_action_counts"),
                            f"shadow row {row_count + 1}.i4.causal_action_counts",
                        )
                        has_tentative_f2 = i4.get("tentative_f2_next") is not None
                        expected_alternative = 1 if has_tentative_f2 else 0
                        expected_total = 2 if has_tentative_f2 else 1
                        _require(
                            counts.get("alternative_action_count")
                            == expected_alternative
                            and counts.get("total_legal_action_count") == expected_total,
                            f"I4 causal action-count mismatch at shadow row {row_count + 1}",
                        )
                        ordinal = row.get("decision_ordinal")
                        _require(
                            isinstance(ordinal, int) and not isinstance(ordinal, bool),
                            f"shadow prediction ordinal invalid at row {row_count + 1}",
                        )
                        _require(
                            ordinal not in decision_ordinals,
                            f"duplicate shadow decision ordinal: {ordinal}",
                        )
                        decision_ordinals.add(ordinal)
                        row_count += 1
    except (OSError, zstandard.ZstdError) as exc:
        raise FinalizationError(f"cannot fully decompress {path}: {exc}") from exc
    _require(final_byte == b"\n", "shadow prediction stream lacks final newline")
    _require(row_count == expected_rows, "shadow prediction row count mismatch")
    _require(
        byte_count == expected_uncompressed_bytes,
        "shadow prediction uncompressed byte count mismatch",
    )
    _require(
        len(decision_ordinals) == expected_rows,
        "shadow prediction unique-decision count mismatch",
    )
    return {
        "row_count": row_count,
        "unique_decision_ordinal_count": len(decision_ordinals),
        "uncompressed_byte_count": byte_count,
        "compressed_sha256": _sha256_file(path),
        "uncompressed_sha256": uncompressed_digest.hexdigest(),
    }


def _validate_full_shadow_payload(
    shadow: Mapping[str, Any],
    *,
    scan_predictions: bool,
) -> dict[str, Any]:
    artifacts = _mapping(shadow.get("artifacts"), "shadow.artifacts")
    for field in (
        "activation_by_group",
        "report_markdown",
        "runtime_trace_metadata",
        "summary_json",
    ):
        _portable_repo_artifact(artifacts.get(field), f"shadow.artifacts.{field}")
    predictions = _mapping(artifacts.get("predictions"), "shadow.predictions")
    prediction_path = _portable_repo_artifact(
        predictions.get("path"), "shadow.predictions.path"
    )
    _require(
        predictions.get("encoding") == "CANONICAL_JSONL_ZSTD",
        "shadow prediction encoding mismatch",
    )
    expected_rows = int(predictions.get("row_count", -1))
    expected_bytes = int(predictions.get("uncompressed_byte_count", -1))
    expected_compressed = int(predictions.get("compressed_byte_count", -1))
    _require(expected_rows == 522_871, "full shadow does not bind exactly 522,871 rows")
    shadow_rows = _mapping(shadow.get("shadow"), "shadow.shadow")
    integrity = _mapping(shadow.get("runtime_trace_integrity"), "shadow.runtime_trace_integrity")
    _require(shadow_rows.get("trace_row_count") == expected_rows, "shadow trace count mismatch")
    _require(
        integrity.get("decision_trace_seen_count") == expected_rows
        and integrity.get("unique_decision_ordinal_count") == expected_rows,
        "shadow decision-trace completeness mismatch",
    )
    _require(
        prediction_path.stat().st_size == expected_compressed,
        "shadow prediction compressed byte count mismatch",
    )
    result = {
        "path": predictions.get("path"),
        "row_count": expected_rows,
        "compressed_byte_count": expected_compressed,
        "uncompressed_byte_count": expected_bytes,
        "full_stream_scanned": scan_predictions,
    }
    if scan_predictions:
        result.update(
            _scan_zstd_jsonl(
                prediction_path,
                expected_rows=expected_rows,
                expected_uncompressed_bytes=expected_bytes,
            )
        )
    return result


def _validate_canary_paths(value: Mapping[str, Any], segments: int) -> None:
    artifacts = _mapping(value.get("artifacts"), f"{segments}.artifacts")
    required_artifacts = {
        "activations",
        "bags",
        "hard_gates",
        "metadata",
        "off_bags",
        "off_hard_gates",
        "off_raw_bags",
        "off_summary",
        "paired_tth",
        "performance",
        "raw_bags",
        "summary",
    }
    _require(
        required_artifacts.issubset(artifacts),
        f"{segments}: a required canary artifact binding is missing",
    )
    resolved_artifacts: dict[str, Path] = {}
    for name, artifact_path in artifacts.items():
        resolved_artifacts[str(name)] = _portable_repo_artifact(
            artifact_path, f"{segments}.artifacts.{name}"
        )
    binary = _mapping(value.get("binary"), f"{segments}.binary")
    binary_name = _portable_external_binary(binary.get("path"), f"{segments}.binary.path")
    _require(binary.get("file_name") == binary_name, f"{segments}: binary name mismatch")
    _require(_is_sha256(binary.get("sha256")), f"{segments}: invalid binary SHA")
    native_summaries: dict[str, Mapping[str, Any]] = {}
    for summary_name in ("summary", "off_summary"):
        summary = _load_json(resolved_artifacts[summary_name])
        native_summaries[summary_name] = summary
        loaded_name = _portable_external_binary(
            summary.get("loaded_cpp_binary_path"),
            f"{segments}.{summary_name}.loaded_cpp_binary_path",
        )
        _require(
            loaded_name == binary_name
            and summary.get("loaded_cpp_binary_name") == binary_name,
            f"{segments}: {summary_name} binary name mismatch",
        )
        _require(
            summary.get("loaded_cpp_binary_sha256") == binary.get("sha256"),
            f"{segments}: {summary_name} binary SHA mismatch",
        )
        _require(
            summary.get("requested_count") == segments
            and summary.get("completed_count") == segments
            and summary.get("failed_count") == 0,
            f"{segments}: {summary_name} native coverage mismatch",
        )
    _require(
        _load_json(resolved_artifacts["hard_gates"])
        == _mapping(value.get("hard_gates"), f"{segments}.hard_gates"),
        f"{segments}: hard-gate artifact disagrees with metadata",
    )
    off_comparison = _mapping(value.get("off_comparison"), f"{segments}.off_comparison")
    _require(
        _load_json(resolved_artifacts["off_hard_gates"])
        == _mapping(
            off_comparison.get("off_hard_gates"),
            f"{segments}.off_comparison.off_hard_gates",
        ),
        f"{segments}: off hard-gate artifact disagrees with metadata",
    )
    scorer = _mapping(value.get("frozen_scorer_model"), f"{segments}.frozen_scorer")
    scorer_path = _portable_repo_artifact(
        scorer.get("path"), f"{segments}.frozen_scorer.path"
    )
    _require(
        scorer.get("sha256") == _sha256_file(scorer_path),
        f"{segments}: frozen scorer SHA mismatch",
    )
    policy = _mapping(value.get("policy"), f"{segments}.policy")
    rule_path = _portable_repo_artifact(
        policy.get("rule_bundle_path"), f"{segments}.rule_bundle_path"
    )
    rule_payload = _load_json(rule_path)
    rule_self_sha = rule_payload.get("self_sha256")
    unsigned_rule = dict(rule_payload)
    unsigned_rule.pop("self_sha256", None)
    _require(
        isinstance(rule_self_sha, str)
        and rule_self_sha == _canonical_sha256(unsigned_rule)
        and policy.get("rule_bundle_self_sha256", policy.get("rule_bundle_sha256"))
        == rule_self_sha,
        f"{segments}: rule-bundle canonical self SHA mismatch",
    )
    candidate_summary = native_summaries["summary"]
    telemetry = _mapping(value.get("telemetry"), f"{segments}.telemetry")
    _require(
        candidate_summary.get("g4irsf16_supervisor_mode") == "closed_loop"
        and candidate_summary.get("g4irsf16_policy_kind") == "diagnostic_rule"
        and candidate_summary.get("g4irsf16_i4_policy_id") == "H5"
        and candidate_summary.get("g4irsf16_i4_policy_authorization")
        == H5_AUTHORIZATION
        and candidate_summary.get("g4irsf16_promotion_authorized") is False
        and candidate_summary.get("g4irsf16_diagnostic_only") is True
        and candidate_summary.get("g4irsf16_i4_model_sha256") == rule_self_sha
        and candidate_summary.get("g4irsf16_action_change_count")
        == telemetry.get("action_change_count"),
        f"{segments}: native supervisor echo disagrees with formal metadata",
    )


def validate_committed(
    inputs: EvidencePaths,
    outputs: OutputPaths,
    *,
    scan_predictions: bool = True,
) -> dict[str, Any]:
    """Validate committed bindings and payloads without writing any file."""

    _validate_disjoint(inputs, outputs)
    shadow = _load_json(inputs.full_shadow)
    prediction_validation = _validate_full_shadow_payload(
        shadow, scan_predictions=scan_predictions
    )
    decision, ladder, joint = build_decision(inputs)
    if scan_predictions:
        decision["full_shadow_evidence"]["prediction_stream"] = prediction_validation
    _validate_derived_outputs(decision, ladder, joint, outputs)
    for segments in LADDER_SEGMENTS:
        canary = _load_json(
            inputs.closed_loop_dir
            / f"g4irsf16_closed_loop_h5_{segments}.metadata.json"
        )
        _validate_canary_paths(canary, segments)

    # The final gate is the gate-to-model binding: build_decision recomputed every
    # model self-SHA, checked offline authorization, and matched the full-shadow I4 SHA.
    model_bindings = _mapping(decision.get("model_bindings"), "decision.model_bindings")
    _require(
        _mapping(model_bindings.get("I4"), "decision.model_bindings.I4").get(
            "full_shadow_sha_match"
        )
        is True,
        "final gate does not bind the shadow model SHA",
    )
    return {
        "schema": "czr005.g4irsf16.committed_validation.v1",
        "status": "PASS_G4IRSF16_COMMITTED_ARTIFACTS",
        "source_evidence_written": False,
        "final_status": decision["status"],
        "ladder_segments": [row["segments"] for row in ladder],
        "prediction_stream": prediction_validation,
        "final_audit": FINAL_AUDIT_STATUS,
    }


def _validate_disjoint(inputs: EvidencePaths, outputs: OutputPaths) -> None:
    input_paths = {path.resolve() for path in inputs.source_files()}
    output_paths = [path.resolve() for path in outputs.files()]
    _require(
        len(set(output_paths)) == len(output_paths),
        "finalizer output paths must be unique",
    )
    overlap = input_paths.intersection(output_paths)
    _require(not overlap, f"output aliases source evidence: {sorted(map(str, overlap))}")


def _validate_referenced_disjoint(inputs: EvidencePaths, outputs: OutputPaths) -> None:
    """Protect every artifact referenced by source JSON from custom output aliases."""

    protected = {path.resolve() for path in inputs.source_files()}

    def add_repo_path(value: Any) -> None:
        if not isinstance(value, str) or not value or value.startswith(
            "EXTERNAL_NATIVE_BINARY/"
        ):
            return
        if "\\" in value or ":" in value:
            return
        pure = PurePosixPath(value)
        if pure.is_absolute() or ".." in pure.parts:
            return
        protected.add(ROOT.joinpath(*pure.parts).resolve())

    shadow = _load_json(inputs.full_shadow)
    shadow_artifacts = shadow.get("artifacts")
    if isinstance(shadow_artifacts, Mapping):
        for value in shadow_artifacts.values():
            if isinstance(value, Mapping):
                for nested in value.values():
                    add_repo_path(nested)
            else:
                add_repo_path(value)
    shadow_models = shadow.get("models")
    if isinstance(shadow_models, Mapping):
        for model in shadow_models.values():
            if isinstance(model, Mapping):
                add_repo_path(model.get("path"))

    for segments in LADDER_SEGMENTS:
        canary = _load_json(
            inputs.closed_loop_dir
            / f"g4irsf16_closed_loop_h5_{segments}.metadata.json"
        )
        artifacts = canary.get("artifacts")
        if isinstance(artifacts, Mapping):
            for value in artifacts.values():
                add_repo_path(value)
        scorer = canary.get("frozen_scorer_model")
        policy = canary.get("policy")
        if isinstance(scorer, Mapping):
            add_repo_path(scorer.get("path"))
        if isinstance(policy, Mapping):
            add_repo_path(policy.get("rule_bundle_path"))

    overlap = protected.intersection(path.resolve() for path in outputs.files())
    _require(
        not overlap,
        f"output aliases referenced source evidence: {sorted(map(str, overlap))}",
    )


def _validate_offline(value: Mapping[str, Any]) -> None:
    _require(
        value.get("schema") == "czr005.g4irsf16.offline_model_gate.v1",
        "unexpected offline model gate schema",
    )
    _require(value.get("overall_status") == OFFLINE_NO_GO, "offline gate is not no-go")
    final_audit = _mapping(value.get("final_audit"), "offline.final_audit")
    _require(
        final_audit.get("status") == FINAL_AUDIT_STATUS,
        "final audit is not sealed and unconsumed",
    )
    _require(
        final_audit.get("row_level_outcomes_used_for_selection") is False,
        "final-audit row outcomes were consumed",
    )
    i4 = _mapping(value.get("i4"), "offline.i4")
    _require(i4.get("status") == "I4_SELECTIVE_MODEL_NO_GO", "I4 is not no-go")
    i3 = _mapping(value.get("i3_rare_override"), "offline.i3_rare_override")
    _require(
        i3.get("status") == "I3_REROUTE_MODEL_NOT_AUTHORIZED",
        "I3 reroute unexpectedly authorized",
    )


def _validate_shadow(value: Mapping[str, Any]) -> None:
    _require(
        value.get("schema") == "czr005.g4irsf16.full_shadow.v1",
        "unexpected full-shadow schema",
    )
    _require(value.get("status") == "PASS_FROZEN_F2_FULL_SHADOW", "shadow failed")
    _require(value.get("segments") == 43_603, "shadow is not the full 43,603 segments")
    gates = _mapping(value.get("hard_gates"), "shadow.hard_gates")
    _require(gates.get("all_native_live_hard_gates_pass") is True, "shadow native gates failed")
    _require(gates.get("completed_segments") == 43_603, "shadow coverage incomplete")
    shadow = _mapping(value.get("shadow"), "shadow.shadow")
    for field in (
        "f2_action_mutation_count",
        "illegal_proposal_count",
        "model_feature_leakage_count",
    ):
        _require(shadow.get(field) == 0, f"shadow {field} must be zero")
    boundary = _mapping(value.get("scientific_boundary"), "shadow.scientific_boundary")
    _require(boundary.get("model_actions_executed") is False, "shadow executed a model action")
    _require(boundary.get("closed_loop_claim_allowed") is False, "shadow overclaims closed loop")
    authorization = _mapping(value.get("offline_authorization"), "shadow.offline_authorization")
    _require(authorization.get("overall_status") == OFFLINE_NO_GO, "shadow gate mismatch")
    _require(
        authorization.get("final_audit_status") == FINAL_AUDIT_STATUS,
        "shadow final-audit boundary mismatch",
    )


def _validate_rule_bundle(value: Mapping[str, Any]) -> None:
    _require(
        value.get("schema") == "czr005.g4irsf16.rule_bundle.v1",
        "unexpected rule-bundle schema",
    )
    _require(value.get("default_action") == "F2_EXACT", "default action is not F2")
    _require(value.get("final_audit_consumed") is False, "rule bundle consumed final audit")
    declared_sha = value.get("self_sha256")
    unsigned = dict(value)
    unsigned.pop("self_sha256", None)
    _require(
        isinstance(declared_sha, str) and declared_sha == _canonical_sha256(unsigned),
        "rule-bundle self SHA mismatch",
    )
    i4 = _mapping(value.get("i4"), "rule_bundle.i4")
    _require(i4.get("selected_rule") == "H0", "a selective I4 rule was promoted")
    _require(i4.get("promotion_authorized") is False, "I4 promotion unexpectedly authorized")
    canary = _mapping(i4.get("diagnostic_canary"), "rule_bundle.i4.diagnostic_canary")
    _require(canary.get("rule") == "H5", "diagnostic canary is not H5")
    _require(canary.get("authorization") == H5_AUTHORIZATION, "H5 authorization widened")
    i3 = _mapping(value.get("i3"), "rule_bundle.i3")
    _require(i3.get("selected_rule") == "R0", "an I3 override rule was promoted")
    _require(i3.get("promotion_authorized") is False, "I3 promotion unexpectedly authorized")


def _validate_contract(value: Mapping[str, Any]) -> None:
    _require(
        value.get("schema") == "czr005.g4irsf16.supervisor_contract_regression.v1",
        "unexpected supervisor contract schema",
    )
    _require(value.get("overall_pass") is True, "supervisor contract regression failed")
    _require(
        value.get("evaluation_scope")
        == "SUPERVISOR_CONTRACT_REGRESSION_NOT_FULL_CLOSED_LOOP_TTH",
        "contract regression scope is ambiguous",
    )
    invariants = _mapping(value.get("invariants"), "contract.invariants")
    required_invariants = {
        "full_astar_forbidden",
        "pibt_atomic_all_or_none",
        "repair_reentry_once_per_fault_episode",
        "stale_action_rejected",
        "unsafe_zero",
    }
    _require(
        required_invariants.issubset(invariants)
        and all(invariants[name] is True for name in required_invariants)
        and all(item is True for item in invariants.values()),
        "contract invariant missing or failed",
    )
    fault = _mapping(value.get("fault"), "contract.fault")
    tail = _mapping(value.get("tail_pibt"), "contract.tail_pibt")
    _require(fault.get("contract_pass") is True, "fault contract failed")
    _require(fault.get("unsafe_entry_count") == 0, "fault contract has unsafe entry")
    _require(tail.get("contract_pass") is True, "tail/PIBT contract failed")
    _require(tail.get("unsafe_entry_count") == 0, "tail/PIBT contract has unsafe entry")


def _validate_mechanism_boundary(path: Path) -> None:
    _require(path.is_file(), f"mechanism-boundary evidence is missing: {path}")
    text = path.read_text(encoding="utf-8")
    _require(
        "historical F2 and v2-safe headline means were produced under E0" in text,
        "historical E0 boundary is not recorded",
    )
    _require(
        "formal causal labels and the new runtime trace use E4" in text,
        "current E4 boundary is not recorded",
    )
    _require(
        "must not be presented as a direct win" in text,
        "cross-mechanism strict-win prohibition is missing",
    )


def _canary_row(value: Mapping[str, Any], segments: int) -> dict[str, Any]:
    _require(
        value.get("schema") == "czr005.g4irsf16.closed_loop_canary.v1",
        f"{segments}: unexpected canary schema",
    )
    _require(value.get("segments") == segments, f"{segments}: scale mismatch")
    _require(value.get("mode") == "closed_loop", f"{segments}: not closed loop")
    _require(
        value.get("execution_semantics") == "REAL_NATIVE_EVENT_RUNTIME_NOT_OFFLINE_REPLAY",
        f"{segments}: execution was not real native runtime",
    )
    _require(value.get("status") == "PASS", f"{segments}: canary status is not PASS")

    policy = _mapping(value.get("policy"), f"{segments}.policy")
    _require(policy.get("diagnostic_canary") == "H5", f"{segments}: not H5")
    _require(policy.get("authorization") == H5_AUTHORIZATION, f"{segments}: H5 scope widened")
    _require(policy.get("promotion_authorized") is False, f"{segments}: H5 promoted")
    _require(policy.get("selected_rule") == "H0", f"{segments}: H0 not selected")
    binary = _mapping(value.get("binary"), f"{segments}.binary")
    scorer = _mapping(value.get("frozen_scorer_model"), f"{segments}.frozen_scorer")
    binary_sha = binary.get("sha256")
    scorer_sha = scorer.get("sha256")
    rule_sha = policy.get("rule_bundle_self_sha256", policy.get("rule_bundle_sha256"))
    _require(_is_sha256(binary_sha), f"{segments}: invalid binary SHA")
    _require(_is_sha256(scorer_sha), f"{segments}: invalid scorer SHA")
    _require(_is_sha256(rule_sha), f"{segments}: invalid rule self SHA")

    hard = _mapping(value.get("hard_gates"), f"{segments}.hard_gates")
    _require(hard.get("segments") == segments, f"{segments}: hard-gate scale mismatch")
    _require(hard.get("mode") == "closed_loop", f"{segments}: hard-gate mode mismatch")
    _require(hard.get("canary_pass") is True, f"{segments}: canary gate failed")
    _require(hard.get("safety_pass") is True, f"{segments}: safety gate failed")
    gates = _mapping(hard.get("gates"), f"{segments}.hard_gates.gates")
    _require(
        REQUIRED_CANARY_GATES.issubset(gates)
        and all(gates[name] is True for name in REQUIRED_CANARY_GATES)
        and all(item is True for item in gates.values()),
        f"{segments}: a required hard gate is missing or failed",
    )

    off_comparison = _mapping(value.get("off_comparison"), f"{segments}.off_comparison")
    _require(off_comparison.get("enabled") is True, f"{segments}: matched off missing")
    _require(off_comparison.get("off_completed_count") == segments, f"{segments}: off incomplete")
    _require(off_comparison.get("off_failed_count") == 0, f"{segments}: off failed")
    off_gates = _mapping(off_comparison.get("off_hard_gates"), f"{segments}.off_hard_gates")
    _require(off_gates.get("safety_pass") is True, f"{segments}: off safety failed")
    _require(off_gates.get("segments") == segments, f"{segments}: off-gate scale mismatch")
    _require(off_gates.get("mode") == "off", f"{segments}: off-gate mode mismatch")
    off_gate_values = _mapping(off_gates.get("gates"), f"{segments}.off_hard_gates.gates")
    _require(
        REQUIRED_OFF_GATES.issubset(off_gate_values)
        and all(off_gate_values[name] is True for name in REQUIRED_OFF_GATES)
        and all(item is True for item in off_gate_values.values()),
        f"{segments}: a required off hard gate is missing or failed",
    )

    performance = _mapping(value.get("raw_bag_performance"), f"{segments}.performance")
    _require(
        performance.get("denominator") == "raw_bag_original_entry_time_tth",
        f"{segments}: wrong performance denominator",
    )
    _require(performance.get("early_gate_evaluated") is True, f"{segments}: early gate absent")
    _require(performance.get("early_gate_pass") is True, f"{segments}: tail early gate failed")
    candidate = _mapping(performance.get("candidate"), f"{segments}.candidate")
    off = _mapping(performance.get("off"), f"{segments}.off")
    delta = _mapping(performance.get("candidate_minus_off"), f"{segments}.delta")
    telemetry = _mapping(value.get("telemetry"), f"{segments}.telemetry")
    paired = _mapping(off_comparison.get("paired_tth_summary"), f"{segments}.paired")

    delta_mean_minutes = _number(
        delta.get("original_entry_mean_minutes"), f"{segments}.mean_delta"
    )
    delta_seconds = 60.0 * delta_mean_minutes
    candidate_mean = _number(
        candidate.get("original_entry_mean_minutes"), f"{segments}.candidate_mean"
    )
    off_mean = _number(off.get("original_entry_mean_minutes"), f"{segments}.off_mean")
    source_delta_minutes = _number(
        delta.get("source_wait_mean_minutes"), f"{segments}.source_wait_delta"
    )
    network_delta_minutes = _number(
        delta.get("network_time_mean_minutes"), f"{segments}.network_delta"
    )
    p95_delta = _number(
        delta.get("original_entry_p95_seconds"), f"{segments}.p95_delta"
    )
    p99_delta = _number(
        delta.get("original_entry_p99_seconds"), f"{segments}.p99_delta"
    )
    _close(
        _number(candidate.get("original_entry_p95_seconds"), f"{segments}.candidate_p95")
        - _number(off.get("original_entry_p95_seconds"), f"{segments}.off_p95"),
        p95_delta,
        f"{segments}: p95 delta",
    )
    _close(
        _number(candidate.get("original_entry_p99_seconds"), f"{segments}.candidate_p99")
        - _number(off.get("original_entry_p99_seconds"), f"{segments}.off_p99"),
        p99_delta,
        f"{segments}: p99 delta",
    )
    _require(
        p95_delta <= 2.0 and p99_delta <= 4.0,
        f"{segments}: independently recomputed early tail gate failed",
    )
    _close(candidate_mean - off_mean, delta_mean_minutes, f"{segments}: mean delta")
    _close(
        _number(candidate.get("source_wait_mean_minutes"), f"{segments}.candidate_source")
        - _number(off.get("source_wait_mean_minutes"), f"{segments}.off_source"),
        source_delta_minutes,
        f"{segments}: source-wait delta",
    )
    _close(
        _number(candidate.get("network_time_mean_minutes"), f"{segments}.candidate_network")
        - _number(off.get("network_time_mean_minutes"), f"{segments}.off_network"),
        network_delta_minutes,
        f"{segments}: network delta",
    )
    improved = int(paired.get("improved_bag_count", -1))
    regressed = int(paired.get("regressed_bag_count", -1))
    unchanged = int(paired.get("unchanged_bag_count", -1))
    _require(
        paired.get("paired_complete_count") == segments,
        f"{segments}: paired comparison incomplete",
    )
    _require(
        improved >= 0
        and regressed >= 0
        and unchanged >= 0
        and improved + regressed + unchanged == segments,
        f"{segments}: paired outcome counts do not cover the scale",
    )
    action_changes = int(telemetry.get("action_change_count", 0))
    _require(action_changes > 0, f"{segments}: diagnostic canary changed no action")
    reconciliation_raw = value.get("evidence_reconciliation")
    if reconciliation_raw is None:
        native_runtime_reexecuted = True
        evidence_mode = "NATIVE_RUNTIME_EXECUTED"
    else:
        reconciliation = _mapping(
            reconciliation_raw, f"{segments}.evidence_reconciliation"
        )
        _require(
            reconciliation.get("performed") is True
            and reconciliation.get("native_runtime_reexecuted") is False
            and reconciliation.get("native_counters_or_timings_modified") is False,
            f"{segments}: reconciliation changed or obscured native evidence",
        )
        _require(
            reconciliation.get("reason")
            == "CORRECT_BOUNDED_MERGE_TELEMETRY_AND_CAPACITY_ROLLBACK_GATE_SEMANTICS",
            f"{segments}: unrecognized reconciliation scope",
        )
        native_runtime_reexecuted = False
        evidence_mode = "READ_ONLY_GATE_RECONCILIATION_NATIVE_RESULTS_UNCHANGED"
    if delta_seconds > 0.0:
        interpretation = "CANDIDATE_WORSE_MEAN"
    elif delta_seconds < 0.0:
        interpretation = "CANDIDATE_BETTER_MEAN_DIAGNOSTIC_ONLY"
    else:
        interpretation = "MEAN_TIE"

    return {
        "segments": segments,
        "execution_semantics": "E4_batch_plus_destination_merge_request",
        "canary_policy": "H5_DIAGNOSTIC_ONLY",
        "promotion_authorized": False,
        "selected_rule": "H0",
        "status": "PASS",
        "evidence_mode": evidence_mode,
        "native_runtime_reexecuted": native_runtime_reexecuted,
        "native_binary_sha256": binary_sha,
        "frozen_scorer_sha256": scorer_sha,
        "rule_bundle_self_sha256": rule_sha,
        "hard_gates_pass": True,
        "off_hard_gates_pass": True,
        "action_change_count": action_changes,
        "candidate_mean_minutes": candidate_mean,
        "off_mean_minutes": off_mean,
        "delta_seconds_per_raw_bag": delta_seconds,
        "source_wait_delta_seconds_per_raw_bag": 60.0 * source_delta_minutes,
        "network_delta_seconds_per_raw_bag": 60.0 * network_delta_minutes,
        "p95_delta_seconds": p95_delta,
        "p99_delta_seconds": p99_delta,
        "improved_segment_count": improved,
        "regressed_segment_count": regressed,
        "unchanged_segment_count": unchanged,
        "denominator": "raw_bag_original_entry_time_tth",
        "interpretation": interpretation,
    }


def _derive_pivot(ladder: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    largest = next((row for row in ladder if row.get("segments") == 8_192), None)
    _require(largest is not None, "8,192 canary evidence missing")
    total = _number(largest.get("delta_seconds_per_raw_bag"), "8192 total delta")
    source = _number(
        largest.get("source_wait_delta_seconds_per_raw_bag"), "8192 source-wait delta"
    )
    network = _number(
        largest.get("network_delta_seconds_per_raw_bag"), "8192 network delta"
    )
    supports_i1_priority = total > 0.0 and source > 0.0 and network <= 0.0
    if supports_i1_priority:
        priority = "I1_SOURCE_ORDERING"
        status = "ACTIONABLE_HYPOTHESIS_NOT_AUTHORIZATION"
        explanation = (
            "At 8,192 matched E4 segments H5 worsened total mean while network "
            "time improved; the loss was carried by source wait. This prioritizes "
            "an I1 source-ordering causal campaign over another I3/I4 threshold "
            "sweep. It does not authorize an I1 runtime action."
        )
    else:
        priority = "UNKNOWN"
        status = "PIVOT_ORDERING_UNKNOWN"
        explanation = (
            "The matched 8,192 decomposition does not isolate a positive source-wait "
            "shift against a non-positive network shift, so current evidence cannot "
            "rank I1 ahead of G2."
        )
    return {
        "status": status,
        "priority": priority,
        "evidence": {
            "matched_event_semantics": "E4_batch_plus_destination_merge_request",
            "segments": 8_192,
            "total_mean_delta_seconds_per_raw_bag": total,
            "source_wait_delta_seconds_per_raw_bag": source,
            "network_delta_seconds_per_raw_bag": network,
        },
        "explanation": explanation,
        "g2": {
            "status": "BLOCKED_PENDING_CAUSAL_CONCENTRATION_GATE",
            "required_gate": "MERGE_SERVICE_CAUSAL_CONCENTRATION_GATE",
            "gate_evaluated": False,
            "reason": (
                "No current G4IRSF16 causal panel establishes that merge/service "
                "opportunities have enough beneficial concentration to authorize G2."
            ),
        },
    }


def _historical_metrics(value: Mapping[str, Any]) -> tuple[float, float]:
    _require(
        value.get("schema") == "czr005.g4irsf14.final_candidate_bundle.v1",
        "unexpected historical bundle schema",
    )
    performance = _mapping(value.get("performance"), "historical.performance")
    return (
        _number(performance.get("f2_frozen_reference_mean_minutes"), "historical F2"),
        _number(
            performance.get("v2_safe_frozen_reference_mean_minutes"),
            "historical v2-safe",
        ),
    )


def _joint_rows(
    ladder: Sequence[Mapping[str, Any]],
    historical_f2: float,
    historical_v2: float,
) -> list[dict[str, Any]]:
    largest = next(row for row in ladder if row["segments"] == 8_192)
    common_boundary = "NOT_COMPARABLE_AS_STRICT_WIN_EVENT_SEMANTICS_MISMATCH"
    return [
        {
            "row_id": "HISTORICAL_F2_E0",
            "policy": "F2_FROZEN",
            "event_semantics": "E0",
            "segments": 43_603,
            "execution_status": "HISTORICAL_EXECUTED",
            "evidence_role": "CROSS_MECHANISM_CONTEXT_ONLY",
            "denominator": "original_entry_time_tth",
            "mean_minutes": historical_f2,
            "matched_comparator": "NONE_IN_G4IRSF16",
            "matched_delta_seconds_per_raw_bag": "",
            "strict_win_evaluation": common_boundary,
        },
        {
            "row_id": "HISTORICAL_V2_SAFE_E0",
            "policy": "V2_SAFE_FROZEN",
            "event_semantics": "E0",
            "segments": 43_603,
            "execution_status": "HISTORICAL_EXECUTED",
            "evidence_role": "CROSS_MECHANISM_CONTEXT_ONLY",
            "denominator": "original_entry_time_tth",
            "mean_minutes": historical_v2,
            "matched_comparator": "NONE_IN_G4IRSF16",
            "matched_delta_seconds_per_raw_bag": "",
            "strict_win_evaluation": common_boundary,
        },
        {
            "row_id": "G4IRSF16_FULL_SHADOW_E4",
            "policy": "F2_NATIVE_WITH_READ_ONLY_MODEL_SHADOW",
            "event_semantics": "E4_batch_plus_destination_merge_request",
            "segments": 43_603,
            "execution_status": "FULL_SHADOW_PASS_NO_MODEL_ACTIONS_EXECUTED",
            "evidence_role": "INTEGRITY_AND_COVERAGE_NOT_CLOSED_LOOP_PERFORMANCE",
            "denominator": "NOT_APPLICABLE_SHADOW_ONLY",
            "mean_minutes": "",
            "matched_comparator": "NOT_APPLICABLE",
            "matched_delta_seconds_per_raw_bag": "",
            "strict_win_evaluation": "NOT_EVALUATED_SHADOW_ONLY",
        },
        {
            "row_id": "G4IRSF16_H5_OFF_E4_8192",
            "policy": "SUPERVISOR_OFF_MATCHED_CONTROL",
            "event_semantics": "E4_batch_plus_destination_merge_request",
            "segments": 8_192,
            "execution_status": "EXECUTED_PASS",
            "evidence_role": "MATCHED_DIAGNOSTIC_CONTROL",
            "denominator": "raw_bag_original_entry_time_tth",
            "mean_minutes": largest["off_mean_minutes"],
            "matched_comparator": "G4IRSF16_H5_DIAGNOSTIC_E4_8192",
            "matched_delta_seconds_per_raw_bag": "",
            "strict_win_evaluation": "MATCHED_CONTROL_REFERENCE",
        },
        {
            "row_id": "G4IRSF16_H5_DIAGNOSTIC_E4_8192",
            "policy": "H5_DIAGNOSTIC_ONLY_NOT_PROMOTED",
            "event_semantics": "E4_batch_plus_destination_merge_request",
            "segments": 8_192,
            "execution_status": "EXECUTED_PASS_HARD_GATES",
            "evidence_role": "PLUMBING_CANARY_NOT_LEARNED_CANDIDATE",
            "denominator": "raw_bag_original_entry_time_tth",
            "mean_minutes": largest["candidate_mean_minutes"],
            "matched_comparator": "G4IRSF16_H5_OFF_E4_8192",
            "matched_delta_seconds_per_raw_bag": largest[
                "delta_seconds_per_raw_bag"
            ],
            "strict_win_evaluation": "NO_WIN_CANDIDATE_MEAN_WORSE",
        },
        {
            "row_id": "G4IRSF16_LEARNED_CANDIDATE_E4_FULL",
            "policy": "NONE_AUTHORIZED",
            "event_semantics": "E4_batch_plus_destination_merge_request",
            "segments": 43_603,
            "execution_status": "NOT_RUN_FORMAL_OFFLINE_MODEL_NO_GO",
            "evidence_role": "TERMINAL_NO_GO_PATH",
            "denominator": "raw_bag_original_entry_time_tth",
            "mean_minutes": "",
            "matched_comparator": "SUPERVISOR_OFF_E4_FULL_NOT_REQUIRED_AFTER_NO_GO",
            "matched_delta_seconds_per_raw_bag": "",
            "strict_win_evaluation": "NOT_EVALUATED_NO_AUTHORIZED_CANDIDATE",
        },
    ]


def build_decision(inputs: EvidencePaths) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Load and validate source evidence without mutating it."""

    offline = _load_json(inputs.offline_gate)
    shadow = _load_json(inputs.full_shadow)
    rules = _load_json(inputs.rule_bundle)
    i4_model = _load_json(inputs.i4_model)
    i3_model = _load_json(inputs.i3_model)
    externality_model = _load_json(inputs.externality_model)
    contract = _load_json(inputs.contract_summary)
    historical = _load_json(inputs.historical_bundle)
    _validate_offline(offline)
    _validate_shadow(shadow)
    _validate_rule_bundle(rules)
    _validate_contract(contract)
    _validate_mechanism_boundary(inputs.mechanism_boundary_report)
    model_bindings = _validate_model_bindings(
        offline=offline,
        shadow=shadow,
        i4_model=i4_model,
        i3_model=i3_model,
        externality_model=externality_model,
        paths=inputs,
    )

    ladder: list[dict[str, Any]] = []
    for segments in LADDER_SEGMENTS:
        metadata_path = (
            inputs.closed_loop_dir
            / f"g4irsf16_closed_loop_h5_{segments}.metadata.json"
        )
        ladder.append(_canary_row(_load_json(metadata_path), segments))
    historical_f2, historical_v2 = _historical_metrics(historical)
    joint = _joint_rows(ladder, historical_f2, historical_v2)
    pivot = _derive_pivot(ladder)

    binary_shas = {row["native_binary_sha256"] for row in ladder}
    scorer_shas = {row["frozen_scorer_sha256"] for row in ladder}
    rule_shas = {row["rule_bundle_self_sha256"] for row in ladder}
    _require(len(binary_shas) == 1, "canary ladder used more than one native binary")
    _require(len(scorer_shas) == 1, "canary ladder used more than one frozen scorer")
    _require(len(rule_shas) == 1, "canary ladder used more than one rule bundle")

    largest = next(row for row in ladder if row["segments"] == 8_192)
    _require(
        largest["delta_seconds_per_raw_bag"] > 0.0,
        "formal 8,192 H5 evidence no longer supports the recorded mean-loss decision",
    )
    _require(
        pivot["priority"] == "I1_SOURCE_ORDERING",
        "formal evidence does not support the preregistered actionable I1 pivot",
    )

    decision = {
        "schema": SCHEMA,
        "status": FINAL_STATUS,
        "decision": {
            "offline_learning": OFFLINE_NO_GO,
            "final_audit": FINAL_AUDIT_STATUS,
            "selected_runtime_policy": "F2_EXACT_H0_R0",
            "learned_expansion": "CLOSED",
            "scale_expansion": "CLOSED",
            "expansion_enabled": False,
            "full_43603_closed_loop_candidate": {
                "status": "NOT_RUN_FORMAL_OFFLINE_MODEL_NO_GO",
                "allowed_terminal_path": True,
                "reason": (
                    "The formal offline model gate rejected both deployable selective "
                    "learning paths; running an unauthorized full-scale candidate would "
                    "not create valid promotion evidence."
                ),
            },
        },
        "offline_evidence": {
            "path": _repo_path(inputs.offline_gate),
            "overall_status": OFFLINE_NO_GO,
            "final_audit_status": FINAL_AUDIT_STATUS,
            "i3_status": "I3_REROUTE_MODEL_NOT_AUTHORIZED",
            "i4_status": "I4_SELECTIVE_MODEL_NO_GO",
        },
        "full_shadow_evidence": {
            "path": _repo_path(inputs.full_shadow),
            "status": "PASS_FROZEN_F2_FULL_SHADOW",
            "segments": 43_603,
            "model_actions_executed": False,
            "closed_loop_claim_allowed": False,
        },
        "model_bindings": model_bindings,
        "h5_diagnostic_canary": {
            "authorization": H5_AUTHORIZATION,
            "promotion_authorized": False,
            "hard_gate_ladder_pass": True,
            "largest_scale_segments": 8_192,
            "largest_scale_delta_seconds_per_raw_bag": largest[
                "delta_seconds_per_raw_bag"
            ],
            "largest_scale_interpretation": (
                "MATCHED_E4_H5_MEAN_WORSE_NOT_A_BENEFIT"
            ),
            "native_binary_sha256": next(iter(binary_shas)),
            "frozen_scorer_sha256": next(iter(scorer_shas)),
            "rule_bundle_self_sha256": next(iter(rule_shas)),
            "claim_boundary": (
                "Safety/plumbing evidence only; H5 is neither learned nor promoted."
            ),
        },
        "supervisor_contract_regression": {
            "path": _repo_path(inputs.contract_summary),
            "status": "PASS",
            "scope": "SUPERVISOR_CONTRACT_REGRESSION_NOT_FULL_CLOSED_LOOP_TTH",
            "full_closed_loop_performance_claim": False,
        },
        "mechanism_boundary": {
            "historical_f2_and_v2_safe": "E0",
            "g4irsf16_labels_shadow_and_canary": (
                "E4_batch_plus_destination_merge_request"
            ),
            "cross_mechanism_strict_win_allowed": False,
            "historical_f2_mean_minutes": historical_f2,
            "historical_v2_safe_mean_minutes": historical_v2,
            "claim": (
                "Historical E0 means are context only and cannot establish a strict "
                "win for an E4 execution."
            ),
        },
        "actionable_pivot": pivot,
        "output_bindings": {
            "closed_loop_ladder": "outputs/tables/g4irsf16_closed_loop_ladder.csv",
            "joint_ab": "outputs/tables/g4irsf16_original_scale_joint_ab.csv",
            "closed_loop_report": "outputs/reports/g4irsf16_closed_loop_ladder.md",
            "joint_decision_report": (
                "outputs/reports/g4irsf16_original_scale_joint_decision.md"
            ),
        },
    }
    return decision, ladder, joint


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
    _atomic_bytes(path, _json_bytes(value))


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    _require(bool(rows), f"refusing to write empty table: {path}")
    _atomic_bytes(path, _csv_bytes(rows))


def _csv_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    _require(bool(rows), "refusing to serialize an empty table")
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _ladder_markdown(rows: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        "# G4IRSF16 closed-loop diagnostic ladder",
        "",
        "All rows are real native, matched E4 H5-vs-supervisor-off executions. H5 is "
        "`8192_DIAGNOSTIC_ONLY_NOT_PROMOTED`; a PASS means runtime/safety gates passed, "
        "not that performance improved or that H5 was promoted.",
        "",
        "| Segments | Action changes | Candidate mean (min) | Off mean (min) | Mean delta (s/raw bag) | P95 delta (s) | P99 delta (s) | Result |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            "| {segments} | {action_change_count} | {candidate_mean_minutes:.12f} | "
            "{off_mean_minutes:.12f} | {delta_seconds_per_raw_bag:+.12f} | "
            "{p95_delta_seconds:+.6f} | {p99_delta_seconds:+.6f} | "
            "{interpretation} |".format(**row)
        )
    largest = next(row for row in rows if row["segments"] == 8_192)
    lines.extend(
        [
            "",
            "## Decision boundary",
            "",
            f"At 8,192 segments H5 is **{largest['delta_seconds_per_raw_bag']:+.12f} "
            "seconds per raw bag worse** than its matched E4/off control. Its p95 and "
            "p99 gates pass, but this is not a benefit and cannot authorize promotion.",
            "",
            "The formal learned candidate remains no-go. No 43,603-segment learned "
            "closed-loop candidate was run; the offline no-go is the allowed terminal path.",
            "",
        ]
    )
    return "\n".join(lines)


def _joint_markdown(decision: Mapping[str, Any]) -> str:
    canary = _mapping(decision.get("h5_diagnostic_canary"), "decision.h5")
    pivot = _mapping(decision.get("actionable_pivot"), "decision.pivot")
    evidence = _mapping(pivot.get("evidence"), "decision.pivot.evidence")
    boundary = _mapping(decision.get("mechanism_boundary"), "decision.boundary")
    return "\n".join(
        [
            "# G4IRSF16 original-scale joint decision",
            "",
            f"Final status: `{decision['status']}`.",
            "",
            "The formal offline result is `CAUSAL_LEARNING_MODEL_NO_GO`, and the final "
            "audit remains `SEALED_NOT_CONSUMED`. I3 reroute is unauthorized. The I4 "
            "D0 artifact is diagnostic-only: `support_authorization_status=NOT_AUTHORIZED` "
            "and `model_gate_status=I4_SELECTIVE_MODEL_NO_GO`. H5 also remains "
            "diagnostic-only. Learned "
            "expansion therefore stays **closed**; F2/H0/R0 remains the runtime default.",
            "",
            "## What was and was not executed",
            "",
            "The full 43,603-segment E4 shadow passed with frozen F2 actions and no model "
            "action execution. The matched E4 diagnostic ladder passed runtime/safety "
            "gates through 8,192 segments. No authorized learned candidate existed, so "
            "a 43,603-segment learned closed-loop candidate was not run; this is the formal "
            "no-go terminal path, not missing positive evidence.",
            "",
            f"At 8,192 segments diagnostic H5 changed real actions but was "
            f"`{canary['largest_scale_delta_seconds_per_raw_bag']:+.12f}` seconds per "
            "raw bag worse than matched E4/off on the mean. It is not a performance win.",
            "",
            "## Comparison boundary",
            "",
            f"Historical F2 (`{boundary['historical_f2_mean_minutes']:.15f}` min) "
            f"and v2-safe (`{boundary['historical_v2_safe_mean_minutes']:.15f}` min) "
            "are E0 results. G4IRSF16 labels, shadow, and "
            "canaries are E4 destination-merge-request executions. The E0 numbers are "
            "context only: no strict E4-over-E0 win is evaluated or claimed.",
            "",
            "## Actionable pivot",
            "",
            f"Priority: `{pivot['priority']}` with status `{pivot['status']}`. At the "
            f"matched 8,192 run, source wait shifted "
            f"`{evidence['source_wait_delta_seconds_per_raw_bag']:+.12f}` s/raw bag, "
            f"network time shifted `{evidence['network_delta_seconds_per_raw_bag']:+.12f}` "
            f"s/raw bag, and total mean shifted "
            f"`{evidence['total_mean_delta_seconds_per_raw_bag']:+.12f}` s/raw bag. "
            "This supports testing a bounded I1 source-ordering causal campaign before "
            "another I3/I4 threshold sweep; it does not authorize I1 online.",
            "",
            "G2 remains blocked until a preregistered merge/service causal-concentration "
            "gate shows enough beneficial support. That gate has not been evaluated in "
            "the current panel, so no G2 action is authorized.",
            "",
        ]
    )


def _validate_derived_outputs(
    decision: Mapping[str, Any],
    ladder: Sequence[Mapping[str, Any]],
    joint: Sequence[Mapping[str, Any]],
    outputs: OutputPaths,
) -> None:
    expected = {
        outputs.final_gate: _json_bytes(decision),
        outputs.ladder_csv: _csv_bytes(ladder),
        outputs.joint_csv: _csv_bytes(joint),
        outputs.ladder_report: _ladder_markdown(ladder).encode("utf-8"),
        outputs.joint_report: _joint_markdown(decision).encode("utf-8"),
    }
    for path, expected_bytes in expected.items():
        try:
            relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
        except ValueError as exc:
            raise FinalizationError(f"non-portable output outside repository: {path}") from exc
        _require(path.is_file(), f"committed final output is missing: {path}")
        _require(
            path.read_bytes() == expected_bytes,
            f"committed derived output is stale or modified: {relative}",
        )


def finalize(
    inputs: EvidencePaths,
    outputs: OutputPaths,
    *,
    scan_predictions: bool = True,
    validate_canary_payloads: bool = True,
) -> dict[str, Any]:
    """Validate inputs first, then atomically publish derived outputs only."""

    _validate_disjoint(inputs, outputs)
    _validate_referenced_disjoint(inputs, outputs)
    decision, ladder, joint = build_decision(inputs)
    if scan_predictions:
        shadow = _load_json(inputs.full_shadow)
        decision["full_shadow_evidence"]["prediction_stream"] = (
            _validate_full_shadow_payload(shadow, scan_predictions=True)
        )
    if validate_canary_payloads:
        for segments in LADDER_SEGMENTS:
            canary = _load_json(
                inputs.closed_loop_dir
                / f"g4irsf16_closed_loop_h5_{segments}.metadata.json"
            )
            _validate_canary_paths(canary, segments)
    _write_json(outputs.final_gate, decision)
    _write_csv(outputs.ladder_csv, ladder)
    _write_csv(outputs.joint_csv, joint)
    _atomic_bytes(outputs.ladder_report, _ladder_markdown(ladder).encode("utf-8"))
    _atomic_bytes(outputs.joint_report, _joint_markdown(decision).encode("utf-8"))
    return decision


def _parser() -> argparse.ArgumentParser:
    defaults = EvidencePaths.defaults()
    outputs = OutputPaths.defaults()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate every committed binding and the full zstd stream; write nothing",
    )
    parser.add_argument("--offline-gate", type=Path, default=defaults.offline_gate)
    parser.add_argument("--full-shadow", type=Path, default=defaults.full_shadow)
    parser.add_argument("--rule-bundle", type=Path, default=defaults.rule_bundle)
    parser.add_argument("--i4-model", type=Path, default=defaults.i4_model)
    parser.add_argument("--i3-model", type=Path, default=defaults.i3_model)
    parser.add_argument(
        "--externality-model", type=Path, default=defaults.externality_model
    )
    parser.add_argument("--closed-loop-dir", type=Path, default=defaults.closed_loop_dir)
    parser.add_argument("--contract-summary", type=Path, default=defaults.contract_summary)
    parser.add_argument("--historical-bundle", type=Path, default=defaults.historical_bundle)
    parser.add_argument(
        "--mechanism-boundary-report",
        type=Path,
        default=defaults.mechanism_boundary_report,
    )
    parser.add_argument("--final-gate", type=Path, default=outputs.final_gate)
    parser.add_argument("--ladder-csv", type=Path, default=outputs.ladder_csv)
    parser.add_argument("--joint-csv", type=Path, default=outputs.joint_csv)
    parser.add_argument("--ladder-report", type=Path, default=outputs.ladder_report)
    parser.add_argument("--joint-report", type=Path, default=outputs.joint_report)
    return parser


def main() -> int:
    args = _parser().parse_args()
    inputs = EvidencePaths(
        offline_gate=args.offline_gate,
        full_shadow=args.full_shadow,
        rule_bundle=args.rule_bundle,
        i4_model=args.i4_model,
        i3_model=args.i3_model,
        externality_model=args.externality_model,
        closed_loop_dir=args.closed_loop_dir,
        contract_summary=args.contract_summary,
        historical_bundle=args.historical_bundle,
        mechanism_boundary_report=args.mechanism_boundary_report,
    )
    outputs = OutputPaths(
        final_gate=args.final_gate,
        ladder_csv=args.ladder_csv,
        joint_csv=args.joint_csv,
        ladder_report=args.ladder_report,
        joint_report=args.joint_report,
    )
    if args.validate_only:
        validation = validate_committed(inputs, outputs)
        print(validation["status"])
    else:
        decision = finalize(inputs, outputs)
        print(decision["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
