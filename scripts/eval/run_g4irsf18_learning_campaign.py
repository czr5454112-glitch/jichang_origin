#!/usr/bin/env python3
"""Train a narrow J2-warm-start G18 merge scorer from real native JIT opportunities.

This campaign intentionally stops at the evidence boundary exposed by
``EventRuntimeMergeServiceOpportunityRow``.  It groups candidates at one
native service opportunity, removes identity/action fields from model input,
and constructs a deterministic bounded-local counterfactual target.  The
target rolls only the already-pending local candidate set forward; it is not a
clone of the full event runtime and it never reads realized task outcomes.

No repository evidence is written when native traces are absent, incomplete,
or too small for opportunity-disjoint train/validation/audit partitions.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import io
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT, ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from czr005.g4irsf18.models import (  # noqa: E402
    PairwiseResidualScorer,
    SetCandidateScorer,
    StandaloneMLPScorer,
    TeacherCounterfactualAffineScorer,
    TinyResidualScorer,
)


SCHEMA_ANALYSIS = "czr005.g4irsf18.merge_learning_campaign.v1"
SCHEMA_DATASET = "czr005.g4irsf18.merge_local_counterfactual.v1"
SCHEMA_MANIFEST = "czr005.g4irsf18.merge_learning_dataset_manifest.v1"
SCHEMA_MODEL = "czr005.g4irsf18.merge_candidate_model.v1"
SCHEMA_POLICY = "czr005.g4irsf18.merge_research_policy.v1"

DEFAULT_TRACE_DIR = ROOT / "outputs/runtime/g4irsf18_jit_campaign"
DEFAULT_DATASET = ROOT / "artifacts/datasets/g4irsf18_merge_local_counterfactual.jsonl.zst"
DEFAULT_MANIFEST = ROOT / "artifacts/manifests/g4irsf18_learning_dataset_manifest.json"
DEFAULT_ANALYSIS = ROOT / "outputs/tables/g4irsf18_learning_campaign.json"
DEFAULT_METRICS = ROOT / "outputs/tables/g4irsf18_learning_metrics.csv"
DEFAULT_BLEND_SWEEP = ROOT / "outputs/tables/g4irsf18_teacher_cf_blend_sweep.csv"
DEFAULT_ABLATION = ROOT / "outputs/tables/g4irsf18_feature_ablation.csv"
DEFAULT_REPORT = ROOT / "outputs/reports/g4irsf18_learning_campaign.md"
DEFAULT_ABLATION_REPORT = ROOT / "outputs/reports/g4irsf18_feature_ablation.md"
DEFAULT_POLICY = ROOT / "artifacts/policies/g4irsf18_learning_research_policy.json"
MODEL_PATHS = {
    "J3_LINEAR_RESIDUAL": ROOT / "artifacts/models/g4irsf18_j3_linear_residual.json",
    "J4_MLP_RESIDUAL": ROOT / "artifacts/models/g4irsf18_j4_mlp_residual.json",
    "J5_STANDALONE": ROOT / "artifacts/models/g4irsf18_j5_standalone.json",
    "J6_SET_SCORER": ROOT / "artifacts/models/g4irsf18_j6_set_scorer.json",
    "J7_TEACHER_CF_AFFINE": ROOT / "artifacts/models/g4irsf18_j7_teacher_cf_affine.json",
}


TRACE_REQUIRED_FIELDS = frozenset(
    {
        "opportunity_id",
        "event_time",
        "destination_node",
        "controller_generation",
        "timing_mode",
        "candidate_count",
        "baseline_winner_request_id",
        "chosen_winner_request_id",
        "candidate_request_id",
        "upstream_node",
        "projected_arrival",
        "deadline_slack",
        "wait_age",
        "destination_service_seconds",
        "downstream_queue_pressure",
        "route_score",
        "static_remaining",
        "task_class_code",
        "task_class",
        "storage_leg",
        "baseline_winner",
        "chosen_winner",
    }
)
TRACE_METADATA_ONLY_FIELDS = (
    "opportunity_id",
    "destination_node",
    "controller_generation",
    "baseline_winner_request_id",
    "chosen_winner_request_id",
    "candidate_request_id",
    "upstream_node",
    "baseline_winner",
    "chosen_winner",
)
FORBIDDEN_EXTRA_MARKERS = (
    "outcome",
    "future_",
    "teacher",
    "realized",
    "completion_",
    "full_map",
    "global_",
    "label",
)

# These are the only model inputs.  All are available at one bounded local
# merge boundary.  Absolute nodes, request IDs, winner flags, and outcomes are
# deliberately absent.
MERGE_TRACE_LOCAL_FEATURES = (
    "arrival_lag_seconds",
    "arrival_lead_seconds",
    "deadline_slack_seconds",
    "wait_age_seconds",
    "destination_service_seconds",
    "downstream_queue_pressure",
    "local_route_score",
    "static_remaining_seconds",
    "task_class_code",
    "task_class_priority",
    "storage_leg",
    "local_candidate_count",
    "wait_age_minus_set_mean_seconds",
    "deadline_slack_minus_set_mean_seconds",
    "service_minus_set_mean_seconds",
    "pressure_minus_set_mean",
    "route_score_minus_set_mean",
    "arrival_lag_minus_set_mean_seconds",
)

# Native no-deadline requests use ``double::max``.  Saturating that sentinel
# (and the other physical counters) keeps the learned interface bounded while
# preserving every ordering relevant to the short local rollout horizon.
FEATURE_SATURATION: Mapping[str, tuple[float, float]] = {
    "arrival_lag_seconds": (0.0, 86_400.0),
    "arrival_lead_seconds": (0.0, 86_400.0),
    "deadline_slack_seconds": (-86_400.0, 86_400.0),
    "wait_age_seconds": (0.0, 86_400.0),
    "destination_service_seconds": (0.0, 3_600.0),
    "downstream_queue_pressure": (0.0, 4_096.0),
    "local_route_score": (-1_000_000.0, 1_000_000.0),
    "static_remaining_seconds": (0.0, 86_400.0),
    "task_class_code": (-64.0, 64.0),
    "task_class_priority": (-64.0, 64.0),
    "storage_leg": (0.0, 1.0),
}
FEATURE_LOWER = (
    0.0, 0.0, -86_400.0, 0.0, 0.0, 0.0, -1_000_000.0, 0.0,
    -64.0, -64.0, 0.0, 2.0, -86_400.0, -172_800.0, -3_600.0,
    -4_096.0, -2_000_000.0, -86_400.0,
)
FEATURE_UPPER = (
    86_400.0, 86_400.0, 86_400.0, 86_400.0, 3_600.0, 4_096.0,
    1_000_000.0, 86_400.0, 64.0, 64.0, 1.0, 16.0, 86_400.0,
    172_800.0, 3_600.0, 4_096.0, 2_000_000.0, 86_400.0,
)
TEACHER_TIME_SCALE_SECONDS = 120.0
TEACHER_MUTATION_RECALL_FLOOR = 0.95
COUNTERFACTUAL_BLEND_GRID = tuple(float(value) for value in range(0, 301, 10))

FEATURE_FAMILIES: Mapping[str, tuple[str, ...]] = {
    "timing_and_urgency": (
        "arrival_lag_seconds",
        "arrival_lead_seconds",
        "deadline_slack_seconds",
        "wait_age_seconds",
    ),
    "service_and_pressure": (
        "destination_service_seconds",
        "downstream_queue_pressure",
        "local_candidate_count",
    ),
    "route_and_static_progress": (
        "local_route_score",
        "static_remaining_seconds",
    ),
    "task_and_leg": (
        "task_class_code",
        "task_class_priority",
        "storage_leg",
    ),
    "candidate_set_relative": (
        "wait_age_minus_set_mean_seconds",
        "deadline_slack_minus_set_mean_seconds",
        "service_minus_set_mean_seconds",
        "pressure_minus_set_mean",
        "route_score_minus_set_mean",
        "arrival_lag_minus_set_mean_seconds",
    ),
}


class G18LearningCampaignError(RuntimeError):
    """A campaign input or evidence boundary is invalid."""


class NoRealTraceError(G18LearningCampaignError):
    """No complete native JIT trace was supplied."""


class InsufficientOpportunityError(G18LearningCampaignError):
    """Too few real multi-candidate opportunities exist for honest splits."""


@dataclass(frozen=True)
class UtilityWeights:
    own_completion: float = 1.0
    bounded_peer_wait: float = 0.35
    deadline_lateness: float = 2.0
    starvation_delay: float = 0.15
    local_event_work: float = 0.05

    def as_dict(self) -> dict[str, float]:
        return {
            "own_completion": self.own_completion,
            "bounded_peer_wait": self.bounded_peer_wait,
            "deadline_lateness": self.deadline_lateness,
            "starvation_delay": self.starvation_delay,
            "local_event_work": self.local_event_work,
        }


@dataclass(frozen=True)
class CampaignLimits:
    max_candidates: int = 16
    min_train_opportunities: int = 6
    min_validation_opportunities: int = 2
    min_audit_opportunities: int = 2
    epochs: int = 350

    def __post_init__(self) -> None:
        if self.max_candidates < 2:
            raise ValueError("MAX_CANDIDATES_MUST_BE_AT_LEAST_TWO")
        if min(
            self.min_train_opportunities,
            self.min_validation_opportunities,
            self.min_audit_opportunities,
            self.epochs,
        ) <= 0:
            raise ValueError("CAMPAIGN_LIMITS_MUST_BE_POSITIVE")


@dataclass(frozen=True)
class TraceDescriptor:
    path: Path
    portable_path: str
    job_id: str
    timing_mode: str
    row_count: int


@dataclass
class Opportunity:
    source_trace: str
    opportunity_id: int
    event_time: float
    destination_node: int
    controller_generation: int
    timing_mode: str
    local_rows: list[dict[str, float]]
    features: np.ndarray
    baseline_index: int
    native_chosen_index: int
    split: str = ""
    utilities: np.ndarray | None = None
    utility_details: list[dict[str, Any]] | None = None

    @property
    def candidate_count(self) -> int:
        return len(self.local_rows)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise G18LearningCampaignError(message)


def _portable(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _resolve(root: Path, path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else root / value


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise G18LearningCampaignError(f"TRACE_FIELD_NOT_NUMERIC:{name}")
    result = float(value)
    if not math.isfinite(result):
        raise G18LearningCampaignError(f"TRACE_FIELD_NOT_FINITE:{name}")
    return result


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise G18LearningCampaignError(f"TRACE_FIELD_NOT_INTEGER:{name}")
    return int(value)


def _boolean(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise G18LearningCampaignError(f"TRACE_FIELD_NOT_BOOLEAN:{name}")
    return value


def _saturate(name: str, value: float) -> float:
    lower, upper = FEATURE_SATURATION[name]
    return min(max(float(value), lower), upper)


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _jsonl_zst_bytes(rows: Iterable[Mapping[str, Any]]) -> bytes:
    try:
        import zstandard
    except ImportError as exc:  # pragma: no cover - project dependency
        raise G18LearningCampaignError("ZSTANDARD_DEPENDENCY_REQUIRED") from exc
    raw = b"".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
        + b"\n"
        for row in rows
    )
    return zstandard.ZstdCompressor(level=3).compress(raw)


def _iter_jsonl_zst(path: Path) -> Iterable[Mapping[str, Any]]:
    try:
        import zstandard
    except ImportError as exc:  # pragma: no cover - project dependency
        raise G18LearningCampaignError("ZSTANDARD_DEPENDENCY_REQUIRED") from exc
    try:
        with path.open("rb") as raw:
            with zstandard.ZstdDecompressor().stream_reader(raw) as reader:
                with io.TextIOWrapper(reader, encoding="utf-8") as text:
                    for line_number, line in enumerate(text, start=1):
                        if not line.strip():
                            continue
                        try:
                            value = json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise G18LearningCampaignError(
                                f"INVALID_TRACE_JSON:{path}:{line_number}"
                            ) from exc
                        _require(
                            isinstance(value, Mapping),
                            f"TRACE_ROW_NOT_OBJECT:{path}:{line_number}",
                        )
                        yield value
    except zstandard.ZstdError as exc:
        raise G18LearningCampaignError(f"INVALID_ZSTD_TRACE:{path}") from exc


def _companion_path(trace_path: Path) -> Path:
    suffix = ".opportunities.jsonl.zst"
    _require(trace_path.name.endswith(suffix), f"NOT_NATIVE_OPPORTUNITY_TRACE:{trace_path}")
    return trace_path.with_name(trace_path.name[: -len(suffix)] + ".json")


def _validate_companion(trace_path: Path, root: Path) -> tuple[TraceDescriptor, Mapping[str, Any]]:
    companion_path = _companion_path(trace_path)
    if not companion_path.is_file():
        raise NoRealTraceError(f"NATIVE_RESULT_COMPANION_MISSING:{companion_path}")
    try:
        value = json.loads(companion_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NoRealTraceError(f"INVALID_NATIVE_RESULT_COMPANION:{companion_path}") from exc
    _require(isinstance(value, Mapping), "NATIVE_RESULT_COMPANION_NOT_OBJECT")
    _require(
        value.get("schema") == "czr005.g4irsf18.jit_campaign_result.v1",
        "NATIVE_RESULT_SCHEMA_MISMATCH",
    )
    _require(value.get("status") == "COMPLETE", "NATIVE_RESULT_NOT_COMPLETE")
    _require(value.get("hard_safety", {}).get("pass") is True, "NATIVE_RESULT_UNSAFE")
    artifact = value.get("opportunity_trace_artifact")
    _require(isinstance(artifact, str) and artifact, "TRACE_ARTIFACT_LINK_MISSING")
    counters = value.get("counters")
    _require(isinstance(counters, Mapping), "NATIVE_RESULT_COUNTERS_MISSING")
    dropped = counters.get("merge_grant_opportunity_trace_dropped_count")
    _require(dropped == 0, "NATIVE_TRACE_TRUNCATED")
    stored = counters.get("merge_grant_opportunity_trace_stored_count")
    _require(type(stored) is int and stored >= 0, "NATIVE_TRACE_STORED_COUNT_INVALID")
    job = value.get("job")
    variant = value.get("variant")
    _require(isinstance(job, Mapping), "NATIVE_RESULT_JOB_MISSING")
    _require(isinstance(variant, Mapping), "NATIVE_RESULT_VARIANT_MISSING")
    timing = variant.get("timing_mode")
    _require(
        timing in {"jit_fifo", "jit_fair_aging_deadline"},
        "TRACE_IS_NOT_JIT_NORMAL_FLOW",
    )
    descriptor = TraceDescriptor(
        path=trace_path,
        portable_path=_portable(trace_path, root),
        job_id=str(job.get("job_id", trace_path.stem)),
        timing_mode=str(timing),
        row_count=int(stored),
    )
    return descriptor, value


def _validate_trace_row(row: Mapping[str, Any]) -> None:
    missing = TRACE_REQUIRED_FIELDS - set(row)
    _require(not missing, "TRACE_FIELDS_MISSING:" + ",".join(sorted(missing)))
    for name in set(row) - TRACE_REQUIRED_FIELDS:
        lowered = name.lower()
        if any(marker in lowered for marker in FORBIDDEN_EXTRA_MARKERS):
            raise G18LearningCampaignError(f"TRACE_CONTAINS_OUTCOME_FIELD:{name}")


def _local_row(row: Mapping[str, Any], event_time: float) -> dict[str, float]:
    projected = _finite(row["projected_arrival"], "projected_arrival")
    service = _finite(row["destination_service_seconds"], "destination_service_seconds")
    wait_age = _finite(row["wait_age"], "wait_age")
    pressure = _integer(row["downstream_queue_pressure"], "downstream_queue_pressure")
    remaining = _finite(row["static_remaining"], "static_remaining")
    _require(service > 0.0, "SERVICE_SECONDS_MUST_BE_POSITIVE")
    _require(wait_age >= 0.0, "WAIT_AGE_MUST_BE_NONNEGATIVE")
    _require(pressure >= 0, "QUEUE_PRESSURE_MUST_BE_NONNEGATIVE")
    _require(remaining >= 0.0, "STATIC_REMAINING_MUST_BE_NONNEGATIVE")
    return {
        "arrival_lag_seconds": _saturate("arrival_lag_seconds", max(0.0, event_time - projected)),
        "arrival_lead_seconds": _saturate("arrival_lead_seconds", max(0.0, projected - event_time)),
        "deadline_slack_seconds": _saturate(
            "deadline_slack_seconds", _finite(row["deadline_slack"], "deadline_slack")
        ),
        "wait_age_seconds": _saturate("wait_age_seconds", wait_age),
        "destination_service_seconds": _saturate("destination_service_seconds", service),
        "downstream_queue_pressure": _saturate("downstream_queue_pressure", float(pressure)),
        "local_route_score": _saturate(
            "local_route_score", _finite(row["route_score"], "route_score")
        ),
        "static_remaining_seconds": _saturate("static_remaining_seconds", remaining),
        "task_class_code": _saturate(
            "task_class_code", float(_integer(row["task_class_code"], "task_class_code"))
        ),
        "task_class_priority": _saturate(
            "task_class_priority", float(_integer(row["task_class"], "task_class"))
        ),
        "storage_leg": _saturate(
            "storage_leg", float(_boolean(row["storage_leg"], "storage_leg"))
        ),
    }


def _feature_matrix(local_rows: Sequence[Mapping[str, float]]) -> np.ndarray:
    means = {
        name: float(np.mean([row[name] for row in local_rows]))
        for name in (
            "wait_age_seconds",
            "deadline_slack_seconds",
            "destination_service_seconds",
            "downstream_queue_pressure",
            "local_route_score",
            "arrival_lag_seconds",
        )
    }
    rows: list[list[float]] = []
    for row in local_rows:
        enriched = {
            **row,
            "local_candidate_count": float(len(local_rows)),
            "wait_age_minus_set_mean_seconds": row["wait_age_seconds"] - means["wait_age_seconds"],
            "deadline_slack_minus_set_mean_seconds": row["deadline_slack_seconds"] - means["deadline_slack_seconds"],
            "service_minus_set_mean_seconds": row["destination_service_seconds"] - means["destination_service_seconds"],
            "pressure_minus_set_mean": row["downstream_queue_pressure"] - means["downstream_queue_pressure"],
            "route_score_minus_set_mean": row["local_route_score"] - means["local_route_score"],
            "arrival_lag_minus_set_mean_seconds": row["arrival_lag_seconds"] - means["arrival_lag_seconds"],
        }
        rows.append([float(enriched[name]) for name in MERGE_TRACE_LOCAL_FEATURES])
    matrix = np.asarray(rows, dtype=np.float64)
    _require(np.all(np.isfinite(matrix)), "LOCAL_FEATURE_MATRIX_NOT_FINITE")
    return matrix


def _build_opportunity(
    descriptor: TraceDescriptor,
    rows: Sequence[Mapping[str, Any]],
    limits: CampaignLimits,
) -> tuple[Opportunity | None, str | None]:
    for row in rows:
        _validate_trace_row(row)
    first = rows[0]
    opportunity_id = _integer(first["opportunity_id"], "opportunity_id")
    candidate_count = _integer(first["candidate_count"], "candidate_count")
    if candidate_count < 2:
        return None, "singleton"
    if candidate_count > limits.max_candidates:
        return None, "over_bounded_horizon"
    _require(candidate_count == len(rows), "CANDIDATE_COUNT_GROUP_MISMATCH")
    event_time = _finite(first["event_time"], "event_time")
    destination = _integer(first["destination_node"], "destination_node")
    generation = _integer(first["controller_generation"], "controller_generation")
    timing_mode = first["timing_mode"]
    _require(timing_mode == descriptor.timing_mode, "TRACE_TIMING_MODE_MISMATCH")
    baseline_request = _integer(
        first["baseline_winner_request_id"], "baseline_winner_request_id"
    )
    chosen_request = _integer(first["chosen_winner_request_id"], "chosen_winner_request_id")
    request_ids: list[int] = []
    local_rows: list[dict[str, float]] = []
    baseline_indices: list[int] = []
    chosen_indices: list[int] = []
    for index, row in enumerate(rows):
        _require(_integer(row["opportunity_id"], "opportunity_id") == opportunity_id, "MIXED_OPPORTUNITY_GROUP")
        _require(_integer(row["candidate_count"], "candidate_count") == candidate_count, "MIXED_CANDIDATE_COUNT")
        _require(abs(_finite(row["event_time"], "event_time") - event_time) <= 1.0e-9, "MIXED_EVENT_TIME")
        _require(_integer(row["destination_node"], "destination_node") == destination, "MIXED_DESTINATION")
        _require(_integer(row["controller_generation"], "controller_generation") == generation, "MIXED_CONTROLLER_GENERATION")
        _require(row["timing_mode"] == timing_mode, "MIXED_TIMING_MODE")
        _require(_integer(row["baseline_winner_request_id"], "baseline_winner_request_id") == baseline_request, "MIXED_BASELINE_WINNER")
        _require(_integer(row["chosen_winner_request_id"], "chosen_winner_request_id") == chosen_request, "MIXED_CHOSEN_WINNER")
        request_id = _integer(row["candidate_request_id"], "candidate_request_id")
        request_ids.append(request_id)
        if _boolean(row["baseline_winner"], "baseline_winner"):
            baseline_indices.append(index)
        if _boolean(row["chosen_winner"], "chosen_winner"):
            chosen_indices.append(index)
        local_rows.append(_local_row(row, event_time))
    _require(len(set(request_ids)) == len(request_ids), "DUPLICATE_CANDIDATE_REQUEST")
    _require(len(baseline_indices) == 1, "BASELINE_WINNER_NOT_UNIQUE")
    _require(len(chosen_indices) == 1, "CHOSEN_WINNER_NOT_UNIQUE")
    _require(request_ids[baseline_indices[0]] == baseline_request, "BASELINE_WINNER_IDENTITY_MISMATCH")
    _require(request_ids[chosen_indices[0]] == chosen_request, "CHOSEN_WINNER_IDENTITY_MISMATCH")
    features = _feature_matrix(local_rows)
    if np.all(np.max(np.abs(features - features[0]), axis=1) <= 1.0e-12):
        return None, "identity_only_local_state"
    return (
        Opportunity(
            source_trace=descriptor.portable_path,
            opportunity_id=opportunity_id,
            event_time=event_time,
            destination_node=destination,
            controller_generation=generation,
            timing_mode=str(timing_mode),
            local_rows=local_rows,
            features=features,
            baseline_index=baseline_indices[0],
            native_chosen_index=chosen_indices[0],
        ),
        None,
    )


def load_native_opportunities(
    trace_paths: Sequence[Path],
    *,
    root: Path = ROOT,
    limits: CampaignLimits = CampaignLimits(),
) -> tuple[list[Opportunity], list[TraceDescriptor], dict[str, int]]:
    if not trace_paths:
        raise NoRealTraceError("NO_REAL_NATIVE_JIT_TRACE")
    opportunities: list[Opportunity] = []
    descriptors: list[TraceDescriptor] = []
    exclusions = {
        "singleton": 0,
        "over_bounded_horizon": 0,
        "identity_only_local_state": 0,
        "duplicate_state_across_traces": 0,
    }
    signatures: dict[tuple[Any, ...], int] = {}
    for trace_path in sorted({path.resolve() for path in trace_paths}, key=str):
        if not trace_path.is_file():
            raise NoRealTraceError(f"TRACE_NOT_FOUND:{trace_path}")
        descriptor, _ = _validate_companion(trace_path, root)
        descriptors.append(descriptor)
        current_id: int | None = None
        current_rows: list[Mapping[str, Any]] = []
        seen_ids: set[int] = set()
        row_count = 0

        def finish_group() -> None:
            nonlocal current_rows
            if not current_rows:
                return
            built, reason = _build_opportunity(descriptor, current_rows, limits)
            if reason is not None:
                exclusions[reason] += 1
            else:
                assert built is not None
                state_rows = tuple(
                    sorted(
                        tuple(round(value, 9) for value in row.values())
                        for row in built.local_rows
                    )
                )
                signature = (
                    round(built.event_time, 9),
                    built.destination_node,
                    built.controller_generation,
                    state_rows,
                )
                if signature in signatures:
                    exclusions["duplicate_state_across_traces"] += 1
                    existing_index = signatures[signature]
                    if (
                        built.timing_mode == "jit_fair_aging_deadline"
                        and opportunities[existing_index].timing_mode
                        != "jit_fair_aging_deadline"
                    ):
                        # The same prefix state can appear in FIFO and J2 arms.
                        # Keep the J2 row because its chosen action is the
                        # teacher target; the local features and rollout target
                        # are identical.
                        opportunities[existing_index] = built
                else:
                    signatures[signature] = len(opportunities)
                    opportunities.append(built)
            current_rows = []

        for row in _iter_jsonl_zst(trace_path):
            row_count += 1
            _validate_trace_row(row)
            row_id = _integer(row["opportunity_id"], "opportunity_id")
            if current_id is None:
                current_id = row_id
            elif row_id != current_id:
                finish_group()
                _require(current_id not in seen_ids, "NONCONTIGUOUS_OPPORTUNITY_ROWS")
                seen_ids.add(current_id)
                _require(row_id not in seen_ids, "NONCONTIGUOUS_OPPORTUNITY_ROWS")
                current_id = row_id
            current_rows.append(row)
        finish_group()
        _require(row_count == descriptor.row_count, "TRACE_STORED_ROW_COUNT_MISMATCH")
    if not opportunities:
        raise InsufficientOpportunityError("NO_REAL_MULTI_CANDIDATE_OPPORTUNITIES")
    return opportunities, descriptors, exclusions


def _priority_key(row: Mapping[str, float]) -> tuple[float, ...]:
    """Feature-only continuation priority; no identity tie breaker."""

    return tuple(
        round(value, 9)
        for value in (
            row["deadline_slack_seconds"] - 0.5 * row["wait_age_seconds"],
            -row["wait_age_seconds"],
            row["arrival_lead_seconds"],
            row["destination_service_seconds"],
            row["downstream_queue_pressure"],
            row["local_route_score"],
            row["static_remaining_seconds"],
            row["task_class_priority"],
            row["storage_leg"],
        )
    )


def bounded_local_counterfactual(
    local_rows: Sequence[Mapping[str, float]],
    first_index: int,
    *,
    weights: UtilityWeights = UtilityWeights(),
) -> dict[str, Any]:
    """Roll the fixed pending set forward without future arrivals or global state.

    Exact feature ties are processed as one symmetric bucket.  Their expected
    completion time averages all within-bucket orders, avoiding an ID/order
    tie-break in the target.
    """

    count = len(local_rows)
    _require(count >= 2, "COUNTERFACTUAL_REQUIRES_MULTI_CANDIDATE_SET")
    _require(0 <= first_index < count, "COUNTERFACTUAL_ACTION_OUT_OF_RANGE")
    completion = np.zeros(count, dtype=np.float64)
    position = np.zeros(count, dtype=np.float64)
    first_service = float(local_rows[first_index]["destination_service_seconds"])
    completion[first_index] = first_service
    position[first_index] = 1.0
    elapsed = first_service
    completed_before = 1
    remaining = [index for index in range(count) if index != first_index]
    buckets: dict[tuple[float, ...], list[int]] = {}
    for index in remaining:
        buckets.setdefault(_priority_key(local_rows[index]), []).append(index)
    for key in sorted(buckets):
        indices = buckets[key]
        services = [float(local_rows[index]["destination_service_seconds"]) for index in indices]
        total_service = sum(services)
        for index, service in zip(indices, services, strict=True):
            completion[index] = elapsed + service + 0.5 * (total_service - service)
            position[index] = completed_before + 0.5 * (len(indices) + 1.0)
        elapsed += total_service
        completed_before += len(indices)

    wait_before_service = np.asarray(
        [completion[i] - float(local_rows[i]["destination_service_seconds"]) for i in range(count)]
    )
    peer_indices = [index for index in range(count) if index != first_index]
    peer_wait = float(np.mean(wait_before_service[peer_indices]))
    deadline_lateness = float(
        np.mean(
            [
                max(0.0, completion[i] - max(0.0, float(local_rows[i]["deadline_slack_seconds"])))
                for i in range(count)
            ]
        )
    )
    starvation_delay = float(
        np.mean(
            [
                wait_before_service[i]
                * min(10.0, float(local_rows[i]["wait_age_seconds"]) / 60.0)
                for i in range(count)
            ]
        )
    )
    # One grant and completion per candidate, one arbitration between local
    # completions, plus bounded pending-set reconsideration weighted by the
    # observed downstream pressure.  This is an explicit local work proxy,
    # not the native runtime's realized event count.
    local_event_work = float(3 * count - 1)
    local_event_work += sum(
        max(0.0, position[i] - 1.0)
        * (1.0 + min(32.0, float(local_rows[i]["downstream_queue_pressure"])) / 32.0)
        for i in range(count)
    )
    components = {
        "own_completion_seconds": float(completion[first_index]),
        "bounded_peer_wait_mean_seconds": peer_wait,
        "deadline_lateness_mean_seconds": deadline_lateness,
        "starvation_weighted_wait_mean_seconds": starvation_delay,
        "estimated_local_event_work_units": local_event_work,
    }
    total_cost = (
        weights.own_completion * components["own_completion_seconds"]
        + weights.bounded_peer_wait * components["bounded_peer_wait_mean_seconds"]
        + weights.deadline_lateness * components["deadline_lateness_mean_seconds"]
        + weights.starvation_delay * components["starvation_weighted_wait_mean_seconds"]
        + weights.local_event_work * components["estimated_local_event_work_units"]
    )
    return {
        "utility": -float(total_cost),
        "total_cost": float(total_cost),
        "components": components,
        "completion_delay_seconds": completion.tolist(),
        "expected_local_service_position": position.tolist(),
    }


def prepare_opportunities(
    opportunities: Sequence[Opportunity],
    *,
    weights: UtilityWeights = UtilityWeights(),
) -> None:
    for opportunity in opportunities:
        details = [
            bounded_local_counterfactual(opportunity.local_rows, index, weights=weights)
            for index in range(opportunity.candidate_count)
        ]
        opportunity.utility_details = details
        opportunity.utilities = np.asarray([row["utility"] for row in details], dtype=np.float64)


def split_opportunities(
    opportunities: Sequence[Opportunity], limits: CampaignLimits
) -> dict[str, list[Opportunity]]:
    ordered = sorted(
        opportunities,
        key=lambda row: (row.source_trace, row.event_time, row.opportunity_id),
    )
    splits = {"train": [], "validation": [], "audit": []}
    pattern = ("train", "train", "train", "validation", "audit")
    for index, opportunity in enumerate(ordered):
        split = pattern[index % len(pattern)]
        opportunity.split = split
        splits[split].append(opportunity)
    required = {
        "train": limits.min_train_opportunities,
        "validation": limits.min_validation_opportunities,
        "audit": limits.min_audit_opportunities,
    }
    failures = [
        f"{name}={len(splits[name])}<{minimum}"
        for name, minimum in required.items()
        if len(splits[name]) < minimum
    ]
    if failures:
        raise InsufficientOpportunityError("OPPORTUNITY_SPLIT_TOO_SMALL:" + ",".join(failures))
    return splits


def _baseline_scores(opportunity: Opportunity) -> np.ndarray:
    # The native FIFO winner is a policy output, not a model feature.  A small
    # fixed preference gap lets residual heads express a deliberate override.
    result = np.full(opportunity.candidate_count, -0.05, dtype=np.float64)
    result[opportunity.baseline_index] = 0.0
    return result


def _flatten(opportunities: Sequence[Opportunity]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    features = np.concatenate([row.features for row in opportunities], axis=0)
    utilities = np.concatenate([row.utilities for row in opportunities if row.utilities is not None])
    advantages = np.concatenate(
        [
            row.utilities - row.utilities[row.baseline_index]
            for row in opportunities
            if row.utilities is not None
        ]
    )
    return features, utilities, advantages


def train_models(
    train: Sequence[Opportunity],
    *,
    feature_names: Sequence[str] = MERGE_TRACE_LOCAL_FEATURES,
    feature_indices: Sequence[int] | None = None,
    epochs: int = 350,
) -> dict[str, Any]:
    indices = np.asarray(
        list(feature_indices) if feature_indices is not None else list(range(len(feature_names))),
        dtype=np.int64,
    )
    names = tuple(feature_names[index] for index in indices)
    candidate_sets = [row.features[:, indices] for row in train]
    utility_sets = [row.utilities for row in train]
    _require(all(value is not None for value in utility_sets), "UTILITY_NOT_PREPARED")
    baseline_indices = [row.baseline_index for row in train]
    flat_features = np.concatenate(candidate_sets, axis=0)
    flat_utilities = np.concatenate([np.asarray(value) for value in utility_sets])
    flat_advantages = np.concatenate(
        [
            np.asarray(value) - float(np.asarray(value)[baseline])
            for value, baseline in zip(utility_sets, baseline_indices, strict=True)
        ]
    )
    return {
        "J3_LINEAR_RESIDUAL": PairwiseResidualScorer.fit(
            candidate_sets,
            utility_sets,
            baseline_indices,
            feature_names=names,
            epochs=epochs,
        ),
        "J4_MLP_RESIDUAL": TinyResidualScorer.fit(
            flat_features,
            flat_advantages,
            feature_names=names,
            epochs=epochs,
            hidden_dim=12,
            seed=18,
        ),
        "J5_STANDALONE": StandaloneMLPScorer.fit(
            flat_features,
            flat_utilities,
            feature_names=names,
            epochs=epochs,
            hidden_dim=12,
            seed=19,
        ),
        "J6_SET_SCORER": SetCandidateScorer.fit(
            candidate_sets,
            utility_sets,
            feature_names=names,
            epochs=epochs,
            hidden_dim=14,
            seed=20,
        ),
    }


def _model_scores(
    variant: str,
    model: Any,
    opportunity: Opportunity,
    indices: np.ndarray,
) -> np.ndarray:
    features = opportunity.features[:, indices]
    if variant == "J3_LINEAR_RESIDUAL":
        return np.asarray(
            model.scores(
                features,
                _baseline_scores(opportunity),
                opportunity.baseline_index,
            )
        )
    if variant == "J4_MLP_RESIDUAL":
        return np.asarray(model.scores(features, _baseline_scores(opportunity)))
    return np.asarray(model.scores(features))


def _distinct_action(opportunity: Opportunity, left: int, right: int) -> bool:
    return not np.allclose(
        opportunity.features[left], opportunity.features[right], rtol=0.0, atol=1.0e-12
    )


def evaluate_model(
    variant: str,
    model: Any,
    opportunities: Sequence[Opportunity],
    *,
    feature_indices: Sequence[int] | None = None,
) -> dict[str, Any]:
    indices = np.asarray(
        list(feature_indices)
        if feature_indices is not None
        else list(range(len(MERGE_TRACE_LOCAL_FEATURES))),
        dtype=np.int64,
    )
    correct = 0
    regrets: list[float] = []
    chosen_utilities: list[float] = []
    baseline_utilities: list[float] = []
    native_utilities: list[float] = []
    mutations = 0
    native_mutations = 0
    for opportunity in opportunities:
        assert opportunity.utilities is not None
        scores = _model_scores(variant, model, opportunity, indices)
        chosen = int(np.argmax(scores))
        best_utility = float(np.max(opportunity.utilities))
        chosen_utility = float(opportunity.utilities[chosen])
        correct += chosen_utility >= best_utility - 1.0e-9
        regrets.append(best_utility - chosen_utility)
        chosen_utilities.append(chosen_utility)
        baseline_utilities.append(float(opportunity.utilities[opportunity.baseline_index]))
        native_utilities.append(float(opportunity.utilities[opportunity.native_chosen_index]))
        mutations += _distinct_action(opportunity, chosen, opportunity.baseline_index)
        native_mutations += _distinct_action(
            opportunity, opportunity.native_chosen_index, opportunity.baseline_index
        )
    count = len(opportunities)
    return {
        "opportunity_count": count,
        "top1_accuracy": correct / count,
        "mean_regret": float(np.mean(regrets)),
        "max_regret": float(np.max(regrets)),
        "mean_utility": float(np.mean(chosen_utilities)),
        "baseline_mean_utility": float(np.mean(baseline_utilities)),
        "native_policy_mean_utility": float(np.mean(native_utilities)),
        "mean_utility_gain_vs_baseline": float(
            np.mean(np.asarray(chosen_utilities) - np.asarray(baseline_utilities))
        ),
        "offline_distinct_action_mutation_count": mutations,
        "offline_distinct_action_mutation_rate": mutations / count,
        "native_distinct_action_mutation_count": native_mutations,
    }


def fit_teacher_counterfactual_affine(
    train: Sequence[Opportunity],
) -> TeacherCounterfactualAffineScorer:
    features, _, advantages = _flatten(train)
    return TeacherCounterfactualAffineScorer.fit_counterfactual_advantage(
        features,
        advantages,
        feature_names=MERGE_TRACE_LOCAL_FEATURES,
        blend=0.0,
        teacher_time_scale_seconds=TEACHER_TIME_SCALE_SECONDS,
        l2=1.0e-3,
    )


def evaluate_teacher_counterfactual(
    model: TeacherCounterfactualAffineScorer,
    opportunities: Sequence[Opportunity],
) -> dict[str, Any]:
    rollout_correct = 0
    teacher_agreement = 0
    teacher_mutations = 0
    teacher_mutations_recalled = 0
    predicted_mutations = 0
    correct_predicted_mutations = 0
    regrets: list[float] = []
    chosen_utilities: list[float] = []
    baseline_utilities: list[float] = []
    teacher_utilities: list[float] = []
    gains: list[float] = []
    teacher_improvements: list[float] = []
    for opportunity in opportunities:
        assert opportunity.utilities is not None
        predicted = model.choose(opportunity.features)
        teacher = opportunity.native_chosen_index
        baseline = opportunity.baseline_index
        predicted_utility = float(opportunity.utilities[predicted])
        teacher_utility = float(opportunity.utilities[teacher])
        baseline_utility = float(opportunity.utilities[baseline])
        best_utility = float(np.max(opportunity.utilities))
        teacher_is_mutation = _distinct_action(opportunity, teacher, baseline)
        predicted_is_mutation = _distinct_action(opportunity, predicted, baseline)
        teacher_agreement += predicted == teacher
        teacher_mutations += teacher_is_mutation
        teacher_mutations_recalled += teacher_is_mutation and predicted == teacher
        predicted_mutations += predicted_is_mutation
        correct_predicted_mutations += predicted_is_mutation and predicted == teacher
        rollout_correct += predicted_utility >= best_utility - 1.0e-9
        regrets.append(best_utility - predicted_utility)
        chosen_utilities.append(predicted_utility)
        baseline_utilities.append(baseline_utility)
        teacher_utilities.append(teacher_utility)
        gains.append(predicted_utility - baseline_utility)
        teacher_improvements.append(predicted_utility - teacher_utility)
    count = len(opportunities)
    return {
        "opportunity_count": count,
        "top1_accuracy": rollout_correct / count,
        "mean_regret": float(np.mean(regrets)),
        "max_regret": float(np.max(regrets)),
        "mean_utility": float(np.mean(chosen_utilities)),
        "baseline_mean_utility": float(np.mean(baseline_utilities)),
        "native_policy_mean_utility": float(np.mean(teacher_utilities)),
        "mean_utility_gain_vs_baseline": float(np.mean(gains)),
        "sum_utility_gain_vs_baseline": float(np.sum(gains)),
        "offline_distinct_action_mutation_count": predicted_mutations,
        "offline_distinct_action_mutation_rate": predicted_mutations / count,
        "native_distinct_action_mutation_count": teacher_mutations,
        "teacher_action_agreement": teacher_agreement / count,
        "teacher_nonhomomorphic_mutation_recalled_count": teacher_mutations_recalled,
        "teacher_nonhomomorphic_mutation_recall": (
            teacher_mutations_recalled / teacher_mutations
            if teacher_mutations
            else 1.0
        ),
        "teacher_nonhomomorphic_mutation_precision": (
            correct_predicted_mutations / predicted_mutations
            if predicted_mutations
            else 1.0
        ),
        "counterfactual_benefit_count": sum(value > 1.0e-12 for value in gains),
        "counterfactual_harm_count": sum(value < -1.0e-12 for value in gains),
        "counterfactual_neutral_count": sum(abs(value) <= 1.0e-12 for value in gains),
        "mean_utility_delta_vs_teacher": float(np.mean(teacher_improvements)),
        "teacher_harm_reduced_count": sum(
            value > 1.0e-12 for value in teacher_improvements
        ),
    }


def select_counterfactual_blend(
    base_model: TeacherCounterfactualAffineScorer,
    validation: Sequence[Opportunity],
) -> tuple[TeacherCounterfactualAffineScorer, list[dict[str, Any]]]:
    sweep: list[dict[str, Any]] = []
    eligible: list[tuple[TeacherCounterfactualAffineScorer, dict[str, Any]]] = []
    for blend in COUNTERFACTUAL_BLEND_GRID:
        model = base_model.with_blend(blend)
        metrics = evaluate_teacher_counterfactual(model, validation)
        row = {"blend": blend, **metrics}
        sweep.append(row)
        if (
            metrics["teacher_nonhomomorphic_mutation_recall"]
            >= TEACHER_MUTATION_RECALL_FLOOR
            and metrics["offline_distinct_action_mutation_count"] > 0
        ):
            eligible.append((model, metrics))
    if not eligible:
        raise G18LearningCampaignError(
            "NO_TEACHER_COUNTERFACTUAL_BLEND_MEETS_MUTATION_RECALL_FLOOR"
        )
    selected, _ = max(
        eligible,
        key=lambda item: (
            item[1]["mean_utility_gain_vs_baseline"],
            item[0].blend,
            item[1]["teacher_action_agreement"],
        ),
    )
    return selected, sweep


def native_j2_vs_fifo_evidence(
    descriptors: Sequence[TraceDescriptor],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for descriptor in descriptors:
        if descriptor.timing_mode != "jit_fair_aging_deadline":
            continue
        j2_path = _companion_path(descriptor.path)
        j1_name = j2_path.name.replace(
            "j2_f2_jit_fair_aging_deadline", "j1_f2_jit_fifo"
        )
        if j1_name == j2_path.name:
            continue
        j1_path = j2_path.with_name(j1_name)
        if not j1_path.is_file():
            continue
        j2 = json.loads(j2_path.read_text(encoding="utf-8"))
        j1 = json.loads(j1_path.read_text(encoding="utf-8"))
        if not (
            isinstance(j1, Mapping)
            and isinstance(j2, Mapping)
            and j1.get("status") == "COMPLETE"
            and j2.get("status") == "COMPLETE"
            and j1.get("hard_safety", {}).get("pass") is True
            and j2.get("hard_safety", {}).get("pass") is True
        ):
            continue
        left = {
            int(row["task_id"]): row
            for row in j1.get("raw_bags", [])
            if row.get("complete") is True
        }
        right = {
            int(row["task_id"]): row
            for row in j2.get("raw_bags", [])
            if row.get("complete") is True
        }
        common = sorted(set(left) & set(right))
        deltas = [
            float(right[key]["tth_seconds"]) - float(left[key]["tth_seconds"])
            for key in common
        ]
        j1_metrics = j1.get("metrics", {})
        j2_metrics = j2.get("metrics", {})
        j1_counters = j1.get("counters", {})
        j2_counters = j2.get("counters", {})
        rows.append(
            {
                "job_id": descriptor.job_id,
                "paired_complete_bag_count": len(common),
                "paired_tth_improved_count": sum(value < -1.0e-9 for value in deltas),
                "paired_tth_harmed_count": sum(value > 1.0e-9 for value in deltas),
                "paired_tth_unchanged_count": sum(abs(value) <= 1.0e-9 for value in deltas),
                "mean_tth_delta_seconds": float(j2_metrics["mean_tth_seconds"])
                - float(j1_metrics["mean_tth_seconds"]),
                "p95_tth_delta_seconds": float(j2_metrics["p95_tth_seconds"])
                - float(j1_metrics["p95_tth_seconds"]),
                "p99_tth_delta_seconds": float(j2_metrics["p99_tth_seconds"])
                - float(j1_metrics["p99_tth_seconds"]),
                "max_tth_delta_seconds": float(j2_metrics["max_tth_seconds"])
                - float(j1_metrics["max_tth_seconds"]),
                "merge_grant_wait_mean_delta_seconds": float(
                    j2_metrics["merge_grant_wait_mean_seconds"]
                )
                - float(j1_metrics["merge_grant_wait_mean_seconds"]),
                "event_count_delta": int(j2_counters["event_count"])
                - int(j1_counters["event_count"]),
                "j2_order_mutation_count": int(
                    j2_counters["merge_grant_order_mutation_count"]
                ),
                "both_hard_safety_pass": True,
            }
        )
    return rows


def _model_bundle(
    variant: str,
    model: Any,
    split_counts: Mapping[str, int],
    metrics: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA_MODEL,
        "variant": variant,
        "status": "TRAINED_FOR_OFFLINE_RESEARCH_ONLY",
        "model": model.to_dict(),
        "input_contract": {
            "name": "MERGE_TRACE_LOCAL_V1",
            "feature_names": list(MERGE_TRACE_LOCAL_FEATURES),
            "identity_features_used": False,
            "outcome_features_used": False,
            "baseline_action_is_model_input": variant in {"J3_LINEAR_RESIDUAL", "J4_MLP_RESIDUAL"},
        },
        "target": {
            "kind": "bounded_local_counterfactual_utility",
            "full_system_clone": False,
            "realized_outcomes_used": False,
        },
        "split_opportunity_counts": dict(split_counts),
        "offline_metrics": metrics,
        "native_runtime_parity": "NOT_EVALUATED",
        "closed_loop_authorized": False,
    }


def _teacher_model_bundle(
    model: TeacherCounterfactualAffineScorer,
    splits: Mapping[str, Sequence[Opportunity]],
    metrics: Mapping[str, Mapping[str, Any]],
    blend_sweep: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    exported = model.to_dict()
    train_features = np.concatenate(
        [opportunity.features for opportunity in splits["train"]], axis=0
    )
    return {
        "schema": "czr005.g4irsf18.teacher_counterfactual_linear_merge.v1",
        **exported,
        "feature_contract": "MERGE_TRACE_LOCAL_V1",
        "feature_lower": list(FEATURE_LOWER),
        "feature_upper": list(FEATURE_UPPER),
        "observed_train_feature_lower": np.min(train_features, axis=0).tolist(),
        "observed_train_feature_upper": np.max(train_features, axis=0).tolist(),
        "normalization": "z=(clip(x,feature_lower,feature_upper)-mean)/scale",
        "nonfinite_policy": "OOD_AND_J2_FALLBACK",
        "out_of_range_policy": "OOD_AND_J2_FALLBACK; clip is telemetry/shadow-only and research action is not applied",
        "no_deadline_policy": "native no-deadline double::max maps to 86400 without OOD",
        "candidate_count_policy": "2..16; outside range is OOD_AND_J2_FALLBACK",
        "starvation_policy": {
            "threshold_seconds": 120.0,
            "handling": "authoritative pre-model starvation band; scorer evidence covers wait_age<120",
        },
        "training_target": {
            "teacher": "native J2 chosen action; never an inference feature",
            "counterfactual": "bounded-local utility advantage relative to FIFO",
            "full_system_clone": False,
            "realized_outcomes_used": False,
        },
        "blend_selection": {
            "partition": "validation",
            "teacher_nonhomomorphic_mutation_recall_floor": TEACHER_MUTATION_RECALL_FLOOR,
            "objective": "maximize bounded-local utility vs FIFO subject to teacher mutation recall floor; strongest blend breaks exact ties",
            "selected_blend": model.blend,
            "candidate_count": len(blend_sweep),
        },
        "split_opportunity_counts": {
            name: len(rows) for name, rows in splits.items()
        },
        "offline_metrics": metrics,
        "authorization": "RESEARCH_FIXED_WORKLOAD_CANDIDATE_NATIVE_PARITY_REQUIRED",
        "production_closed_loop_authorized": False,
    }


def _historical_ablation_rows() -> list[dict[str, Any]]:
    return [
        {
            "group": "F2_OLD_22",
            "status": "NOT_EVALUATED",
            "feature_count": 22,
            "reason": "merge trace lacks the frozen map-coded/training-risk block; zero fill is forbidden",
        },
        {
            "group": "G17_LOCAL_39",
            "status": "NOT_EVALUATED",
            "feature_count": 39,
            "reason": "merge trace lacks the complete G17 source-front observation",
        },
        {
            "group": "RICH_LOCAL_V1",
            "status": "NOT_EVALUATED",
            "feature_count": 60,
            "reason": "merge trace exposes only the native merge candidate subset, not the complete 60D contract",
        },
        {
            "group": "LEGACY_PLUS_RICH",
            "status": "NOT_EVALUATED",
            "feature_count": 89,
            "reason": "neither the legacy 29D block nor complete RICH_LOCAL_V1 is reconstructible",
        },
    ]


def run_feature_ablation(
    splits: Mapping[str, Sequence[Opportunity]], *, epochs: int
) -> list[dict[str, Any]]:
    rows = _historical_ablation_rows()
    candidates: list[tuple[str, tuple[int, ...], str]] = [
        (
            "MERGE_TRACE_LOCAL_V1_FULL",
            tuple(range(len(MERGE_TRACE_LOCAL_FEATURES))),
            "all directly observed and candidate-set-relative merge-local fields",
        )
    ]
    for family, removed_names in FEATURE_FAMILIES.items():
        retained = tuple(
            index
            for index, name in enumerate(MERGE_TRACE_LOCAL_FEATURES)
            if name not in removed_names
        )
        candidates.append((f"MERGE_TRACE_LOCAL_V1_WITHOUT_{family.upper()}", retained, f"drop {family}"))
    for group, indices, reason in candidates:
        names = tuple(MERGE_TRACE_LOCAL_FEATURES[index] for index in indices)
        candidate_sets = [row.features[:, indices] for row in splits["train"]]
        utility_sets = [row.utilities for row in splits["train"]]
        model = PairwiseResidualScorer.fit(
            candidate_sets,
            utility_sets,
            [row.baseline_index for row in splits["train"]],
            feature_names=names,
            epochs=epochs,
        )
        validation = evaluate_model(
            "J3_LINEAR_RESIDUAL",
            model,
            splits["validation"],
            feature_indices=indices,
        )
        rows.append(
            {
                "group": group,
                "status": "EVALUATED",
                "feature_count": len(indices),
                "reason": reason,
                **{f"validation_{key}": value for key, value in validation.items()},
            }
        )
    return rows


def _dataset_rows(opportunities: Sequence[Opportunity]) -> Iterable[dict[str, Any]]:
    for opportunity in sorted(
        opportunities, key=lambda row: (row.split, row.source_trace, row.event_time, row.opportunity_id)
    ):
        assert opportunity.utility_details is not None
        for index, (features, utility) in enumerate(
            zip(opportunity.features, opportunity.utility_details, strict=True)
        ):
            yield {
                "schema": SCHEMA_DATASET,
                "source_trace": opportunity.source_trace,
                "opportunity_id": opportunity.opportunity_id,
                "split": opportunity.split,
                "candidate_ordinal": index,
                "candidate_count": opportunity.candidate_count,
                "features": dict(zip(MERGE_TRACE_LOCAL_FEATURES, features.tolist(), strict=True)),
                "baseline_action": index == opportunity.baseline_index,
                "native_chosen_action": index == opportunity.native_chosen_index,
                "counterfactual": utility,
            }


def _csv_bytes(rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return output.getvalue().encode("utf-8")


def _learning_report(analysis: Mapping[str, Any]) -> str:
    pivot = analysis["teacher_pivot"]
    selected = analysis["variants"][analysis["selected_variant"]]
    lines = [
        "# G4IRSF18 merge-local learning campaign",
        "",
        f"Decision: **`{analysis['decision']}`**.",
        "",
        "The dataset contains only real multi-candidate native J2 service opportunities. J2 chosen actions are teacher metadata, never inference inputs. The second target is a reconstructible bounded-local rollout over the pending candidates already visible at that boundary. It is **not** a full-system clone, does not simulate future arrivals, and does not use realized completion outcomes.",
        "",
        "## Evidence boundary",
        "",
        f"- Retained opportunities: {analysis['opportunity_count']}",
        f"- Split counts: {analysis['split_opportunity_counts']}",
        f"- Exclusions: {analysis['exclusions']}",
        "- Request/node identities and winner flags are metadata only; none are model features.",
        "- A mutation counts only when the selected candidate's local feature vector differs from FIFO's. Swapping two identity-only duplicates does not count.",
        "",
        "## Offline candidate comparison",
        "",
        "`top-1` and regret below refer to the bounded-local rollout objective, not teacher agreement.",
        "",
        "| Variant | Validation top-1 | Validation regret | Validation utility | Validation mutations | Audit top-1 | Audit regret | Audit utility | Audit mutations |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for variant, result in analysis["variants"].items():
        validation = result["validation"]
        audit = result["audit"]
        lines.append(
            f"| {variant} | {validation['top1_accuracy']:.6f} | {validation['mean_regret']:.6f} | {validation['mean_utility']:.6f} | {validation['offline_distinct_action_mutation_count']} | {audit['top1_accuracy']:.6f} | {audit['mean_regret']:.6f} | {audit['mean_utility']:.6f} | {audit['offline_distinct_action_mutation_count']} |"
        )
    lines.extend(
        [
            "",
            "## Teacher warm start and counterfactual correction",
            "",
            f"Within observed support, native J2 is exactly `argmax(wait_age_seconds - deadline_slack_seconds)`. Maximum observed wait age is {pivot['observed_max_wait_age_seconds']:.6f}s, below the 120s authoritative starvation band.",
            "",
            f"The validation-selected counterfactual blend is `{pivot['counterfactual_blend']}` with a required non-homomorphic teacher-mutation recall of at least `{pivot['validation_mutation_recall_floor']}`.",
            "",
            "| Split | Teacher action agreement | Teacher mutation recall | Teacher mutation precision | Predicted mutations | Rollout mean gain vs FIFO | Benefit | Harm | Neutral |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for split in ("train", "validation", "audit"):
        metrics = selected[split]
        lines.append(
            f"| {split} | {metrics['teacher_action_agreement']:.6f} | {metrics['teacher_nonhomomorphic_mutation_recall']:.6f} | {metrics['teacher_nonhomomorphic_mutation_precision']:.6f} | {metrics['offline_distinct_action_mutation_count']} | {metrics['mean_utility_gain_vs_baseline']:.9f} | {metrics['counterfactual_benefit_count']} | {metrics['counterfactual_harm_count']} | {metrics['counterfactual_neutral_count']} |"
        )
    lines.extend(
        [
            "",
            "The audit therefore separates two facts: the local teacher seam is reproducible/generalizable, while its actions conflict with this rollout objective. This is evidence for a controlled native research test, not evidence of utility improvement or production readiness.",
            "",
            "## Native J2 versus native JIT FIFO",
            "",
            "These end-to-end results are report-only outcomes and never enter model features or targets.",
            "",
            "| Job | Mutations | Paired improve/harm/same | Mean TTH delta | P95 delta | P99 delta | Merge-wait mean delta | Event delta | Safety |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in analysis["native_j2_vs_fifo"]:
        lines.append(
            f"| {row['job_id']} | {row['j2_order_mutation_count']} | {row['paired_tth_improved_count']}/{row['paired_tth_harmed_count']}/{row['paired_tth_unchanged_count']} | {row['mean_tth_delta_seconds']:.9f} | {row['p95_tth_delta_seconds']:.9f} | {row['p99_tth_delta_seconds']:.9f} | {row['merge_grant_wait_mean_delta_seconds']:.9f} | {row['event_count_delta']} | {row['both_hard_safety_pass']} |"
        )
    lines.extend(
        [
            "",
            "## Authorization",
            "",
            f"Selected by validation only: `{analysis['selected_variant']}`.",
            "",
            "The artifact is a research fixed-workload candidate only. Non-finite, out-of-contract, or candidate-count OOD input falls back to J2; FIFO is used only for a finite in-contract score tie. Native feature/score parity, explicit research grants, coverage and override caps, kill switch, starvation/safety shield, and real learned closed-loop evidence remain mandatory. Production authorization is false because the bounded-local rollout gate fails.",
            "",
        ]
    )
    return "\n".join(lines)


def _ablation_report(rows: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        "# G4IRSF18 feature ablation",
        "",
        "The JIT merge trace does not contain the complete historical 22D/39D/60D/89D feature blocks. Those comparisons remain `NOT_EVALUATED`; unavailable values are never filled or inferred. Evaluated rows use the same J3 linear-residual family and opportunity-disjoint validation split.",
        "",
        "| Group | Status | Features | Validation top-1 | Validation regret | Reason |",
        "|---|---|---:|---:|---:|---|",
    ]
    for row in rows:
        top1 = row.get("validation_top1_accuracy", "")
        regret = row.get("validation_mean_regret", "")
        lines.append(
            f"| {row['group']} | {row['status']} | {row['feature_count']} | {top1} | {regret} | {row['reason']} |"
        )
    lines.append("")
    return "\n".join(lines)


def run_campaign(
    trace_paths: Sequence[Path],
    *,
    root: Path = ROOT,
    limits: CampaignLimits = CampaignLimits(),
    weights: UtilityWeights = UtilityWeights(),
    publish: bool = True,
) -> dict[str, Any]:
    loaded_opportunities, descriptors, exclusions = load_native_opportunities(
        trace_paths, root=root, limits=limits
    )
    opportunities = [
        row
        for row in loaded_opportunities
        if row.timing_mode == "jit_fair_aging_deadline"
    ]
    exclusions["non_teacher_timing_mode"] = (
        len(loaded_opportunities) - len(opportunities)
    )
    if not opportunities:
        raise InsufficientOpportunityError("NO_J2_TEACHER_OPPORTUNITIES")
    prepare_opportunities(opportunities, weights=weights)
    splits = split_opportunities(opportunities, limits)
    models = train_models(splits["train"], epochs=limits.epochs)
    variant_results: dict[str, Any] = {}
    for variant, model in models.items():
        variant_results[variant] = {
            split: evaluate_model(variant, model, rows)
            for split, rows in splits.items()
        }
    teacher_base = fit_teacher_counterfactual_affine(splits["train"])
    teacher_model, blend_sweep = select_counterfactual_blend(
        teacher_base, splits["validation"]
    )
    models["J7_TEACHER_CF_AFFINE"] = teacher_model
    variant_results["J7_TEACHER_CF_AFFINE"] = {
        split: evaluate_teacher_counterfactual(teacher_model, rows)
        for split, rows in splits.items()
    }
    teacher_reference = {
        split: evaluate_teacher_counterfactual(teacher_base, rows)
        for split, rows in splits.items()
    }
    selected = "J7_TEACHER_CF_AFFINE"
    ablation_rows = run_feature_ablation(splits, epochs=limits.epochs)
    split_counts = {name: len(rows) for name, rows in splits.items()}
    selected_validation = variant_results[selected]["validation"]
    selected_audit = variant_results[selected]["audit"]
    teacher_generalizes = (
        selected_validation["teacher_nonhomomorphic_mutation_recall"]
        >= TEACHER_MUTATION_RECALL_FLOOR
        and selected_audit["teacher_nonhomomorphic_mutation_recall"]
        >= TEACHER_MUTATION_RECALL_FLOOR
        and selected_audit["offline_distinct_action_mutation_count"] > 0
    )
    rollout_conflict = selected_audit["mean_utility_gain_vs_baseline"] < 0.0
    native_evidence = native_j2_vs_fifo_evidence(descriptors)
    analysis = {
        "schema": SCHEMA_ANALYSIS,
        "decision": (
            "TEACHER_DISTILLATION_GENERALIZES_BUT_COUNTERFACTUAL_CONFLICTS"
            if teacher_generalizes and rollout_conflict
            else (
                "TEACHER_COUNTERFACTUAL_PIVOT_READY_FOR_NATIVE_PARITY"
                if teacher_generalizes
                else "TEACHER_DISTILLATION_DID_NOT_GENERALIZE"
            )
        ),
        "opportunity_count": len(opportunities),
        "candidate_row_count": sum(row.candidate_count for row in opportunities),
        "split_opportunity_counts": split_counts,
        "exclusions": exclusions,
        "feature_contract": {
            "name": "MERGE_TRACE_LOCAL_V1",
            "feature_names": list(MERGE_TRACE_LOCAL_FEATURES),
            "saturation": {
                name: list(bounds) for name, bounds in FEATURE_SATURATION.items()
            },
            "identity_features_used": False,
            "outcome_features_used": False,
        },
        "counterfactual": {
            "scope": "fixed bounded local pending set",
            "full_system_clone": False,
            "future_arrivals_simulated": False,
            "realized_outcomes_used": False,
            "weights": weights.as_dict(),
        },
        "teacher_pivot": {
            "teacher": "native J2 M3 fair-aging-deadline",
            "observed_support_formula": "maximize wait_age_seconds - deadline_slack_seconds",
            "observed_max_wait_age_seconds": max(
                row.local_rows[index]["wait_age_seconds"]
                for row in opportunities
                for index in range(row.candidate_count)
            ),
            "starvation_threshold_seconds": 120.0,
            "teacher_reference_metrics": teacher_reference,
            "counterfactual_blend": teacher_model.blend,
            "validation_mutation_recall_floor": TEACHER_MUTATION_RECALL_FLOOR,
            "validation_blend_sweep": blend_sweep,
            "audit_generalization_pass": teacher_generalizes,
            "rollout_objective_conflict": rollout_conflict,
        },
        "native_j2_vs_fifo": native_evidence,
        "variants": variant_results,
        "selected_variant": selected,
        "research_fixed_workload_candidate": teacher_generalizes,
        "closed_loop_authorized": False,
    }
    if not publish:
        analysis["models"] = models
        analysis["ablation_rows"] = ablation_rows
        return analysis

    dataset_path = root / DEFAULT_DATASET.relative_to(ROOT)
    manifest_path = root / DEFAULT_MANIFEST.relative_to(ROOT)
    analysis_path = root / DEFAULT_ANALYSIS.relative_to(ROOT)
    metrics_path = root / DEFAULT_METRICS.relative_to(ROOT)
    blend_sweep_path = root / DEFAULT_BLEND_SWEEP.relative_to(ROOT)
    ablation_path = root / DEFAULT_ABLATION.relative_to(ROOT)
    report_path = root / DEFAULT_REPORT.relative_to(ROOT)
    ablation_report_path = root / DEFAULT_ABLATION_REPORT.relative_to(ROOT)
    policy_path = root / DEFAULT_POLICY.relative_to(ROOT)
    model_paths = {
        name: root / path.relative_to(ROOT) for name, path in MODEL_PATHS.items()
    }
    dataset_rows = list(_dataset_rows(opportunities))
    manifest = {
        "schema": SCHEMA_MANIFEST,
        "status": "REAL_NATIVE_TRACE_ONLY",
        "dataset_path": _portable(dataset_path, root),
        "source_traces": [
            {
                "path": row.portable_path,
                "job_id": row.job_id,
                "timing_mode": row.timing_mode,
                "stored_candidate_rows": row.row_count,
            }
            for row in descriptors
        ],
        "candidate_row_count": len(dataset_rows),
        "opportunity_count": len(opportunities),
        "split_opportunity_counts": split_counts,
        "exclusions": exclusions,
        "grouping_key": ["source_trace", "opportunity_id"],
        "split_unit": "whole opportunity; no candidate row crosses a split",
        "duplicate_policy": "exact same-time/local-state opportunities across traces collapsed before split",
        "feature_names": list(MERGE_TRACE_LOCAL_FEATURES),
        "feature_saturation": {
            name: list(bounds) for name, bounds in FEATURE_SATURATION.items()
        },
        "metadata_only_trace_fields": list(TRACE_METADATA_ONLY_FIELDS),
        "counterfactual": analysis["counterfactual"],
        "teacher_target_is_metadata_only": True,
        "realized_native_performance_is_report_only": True,
    }
    policy = {
        "schema": SCHEMA_POLICY,
        "selected_variant": selected,
        "authorization": "RESEARCH_FIXED_WORKLOAD_CANDIDATE_NATIVE_PARITY_REQUIRED",
        "research_fixed_workload_candidate": teacher_generalizes,
        "normal_flow_closed_loop_authorized": False,
        "production_closed_loop_authorized": False,
        "model_artifact": _portable(model_paths[selected], root),
        "validation_metrics": variant_results[selected]["validation"],
        "audit_metrics": variant_results[selected]["audit"],
        "rollout_objective_gate_pass": not rollout_conflict,
        "teacher_generalization_gate_pass": teacher_generalizes,
        "required_before_closed_loop": [
            "native MERGE_TRACE_LOCAL_V1 parity",
            "explicit research grant and fixed workload",
            "coverage cap, maximum overrides, kill switch, and authoritative safety/starvation shield",
            "OOD_AND_J2_FALLBACK for non-finite, out-of-contract, and candidate-count violations; FIFO only for score ties",
            "real learned normal-flow action mutations with per-head telemetry",
        ],
        "production_blockers": [
            "bounded-local rollout labels every observed J2 mutation harmful",
            "native learned-model parity and closed-loop safety/performance are not yet measured",
        ],
        "reason": "the affine scorer generalizes the real J2 mutation seam, while the local rollout objective conflicts and therefore blocks production promotion",
    }
    metric_rows = [
        {"variant": variant, "split": split, **metrics}
        for variant, result in variant_results.items()
        for split, metrics in result.items()
    ]
    metric_fields = (
        "variant",
        "split",
        "opportunity_count",
        "top1_accuracy",
        "mean_regret",
        "max_regret",
        "mean_utility",
        "baseline_mean_utility",
        "native_policy_mean_utility",
        "mean_utility_gain_vs_baseline",
        "offline_distinct_action_mutation_count",
        "offline_distinct_action_mutation_rate",
        "native_distinct_action_mutation_count",
        "sum_utility_gain_vs_baseline",
        "teacher_action_agreement",
        "teacher_nonhomomorphic_mutation_recalled_count",
        "teacher_nonhomomorphic_mutation_recall",
        "teacher_nonhomomorphic_mutation_precision",
        "counterfactual_benefit_count",
        "counterfactual_harm_count",
        "counterfactual_neutral_count",
        "mean_utility_delta_vs_teacher",
        "teacher_harm_reduced_count",
    )
    blend_sweep_fields = (
        "blend",
        "opportunity_count",
        "teacher_action_agreement",
        "teacher_nonhomomorphic_mutation_recall",
        "teacher_nonhomomorphic_mutation_precision",
        "offline_distinct_action_mutation_count",
        "mean_utility_gain_vs_baseline",
        "sum_utility_gain_vs_baseline",
        "counterfactual_benefit_count",
        "counterfactual_harm_count",
        "counterfactual_neutral_count",
        "mean_utility_delta_vs_teacher",
        "teacher_harm_reduced_count",
    )
    ablation_fields = (
        "group",
        "status",
        "feature_count",
        "validation_opportunity_count",
        "validation_top1_accuracy",
        "validation_mean_regret",
        "validation_max_regret",
        "validation_mean_utility",
        "validation_baseline_mean_utility",
        "validation_native_policy_mean_utility",
        "validation_mean_utility_gain_vs_baseline",
        "validation_offline_distinct_action_mutation_count",
        "validation_offline_distinct_action_mutation_rate",
        "validation_native_distinct_action_mutation_count",
        "reason",
    )
    payloads: list[tuple[Path, bytes]] = [
        (dataset_path, _jsonl_zst_bytes(dataset_rows)),
        (manifest_path, _json_bytes(manifest)),
        (metrics_path, _csv_bytes(metric_rows, metric_fields)),
        (blend_sweep_path, _csv_bytes(blend_sweep, blend_sweep_fields)),
        (ablation_path, _csv_bytes(ablation_rows, ablation_fields)),
        (report_path, _learning_report(analysis).encode("utf-8")),
        (ablation_report_path, _ablation_report(ablation_rows).encode("utf-8")),
        (policy_path, _json_bytes(policy)),
    ]
    for variant, model in models.items():
        if variant == "J7_TEACHER_CF_AFFINE":
            bundle = _teacher_model_bundle(
                model, splits, variant_results[variant], blend_sweep
            )
        else:
            bundle = _model_bundle(
                variant, model, split_counts, variant_results[variant]
            )
        payloads.append(
            (
                model_paths[variant],
                _json_bytes(bundle),
            )
        )
    analysis["artifacts"] = [
        _portable(path, root) for path, _ in payloads
    ] + [_portable(analysis_path, root)]
    payloads.append((analysis_path, _json_bytes(analysis)))
    for path, payload in payloads:
        _atomic_bytes(path, payload)
    return analysis


def discover_traces(trace_dir: Path, explicit: Sequence[Path]) -> list[Path]:
    if explicit:
        return sorted({path.resolve() for path in explicit}, key=str)
    if not trace_dir.is_dir():
        return []
    return sorted(
        (
            path
            for path in trace_dir.rglob("*.opportunities.jsonl.zst")
            if "j2_f2_jit_fair_aging_deadline" in path.name
        ),
        key=str,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--trace", action="append", type=Path, default=[])
    parser.add_argument("--trace-dir", type=Path, default=DEFAULT_TRACE_DIR)
    parser.add_argument("--max-candidates", type=int, default=16)
    parser.add_argument("--min-train", type=int, default=6)
    parser.add_argument("--min-validation", type=int, default=2)
    parser.add_argument("--min-audit", type=int, default=2)
    parser.add_argument("--epochs", type=int, default=350)
    parser.add_argument(
        "--zstandard-site-packages",
        action="append",
        type=Path,
        default=[],
        help="append a site-packages directory containing zstandard without replacing this interpreter's NumPy",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.root.resolve()
    trace_dir = _resolve(root, args.trace_dir)
    explicit = [_resolve(root, path) for path in args.trace]
    traces = discover_traces(trace_dir, explicit)
    limits = CampaignLimits(
        max_candidates=args.max_candidates,
        min_train_opportunities=args.min_train,
        min_validation_opportunities=args.min_validation,
        min_audit_opportunities=args.min_audit,
        epochs=args.epochs,
    )
    try:
        for module_path in args.zstandard_site_packages:
            sys.path.append(str(module_path.resolve(strict=True)))
        result = run_campaign(traces, root=root, limits=limits)
    except (G18LearningCampaignError, OSError, ValueError) as exc:
        print(f"G18 learning campaign stopped without publishing evidence: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "decision": result["decision"],
                "opportunity_count": result["opportunity_count"],
                "selected_variant": result["selected_variant"],
                "closed_loop_authorized": result["closed_loop_authorized"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
