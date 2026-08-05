"""Run G4IRSF16 models in read-only shadow mode over the native F2 runtime.

The native execution is always the frozen E4/M0 F2-off configuration from
``g4irsf16_runtime_trace``.  Models see an exact, ID-free deployment feature
mapping and return proposals only.  No proposal, score, or model object has a
path back to the native executor.

The current authorised contract requires an I4 selective-hold model.  An I3
model is optional: the shipped ``I3_RISK_VETO_DIAGNOSTIC`` artifact is recorded
as diagnostic-only and can never create a rare-route override proposal.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Callable, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT, ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from czr005.g4irsf16.model import (  # noqa: E402
    DEPLOYMENT_FEATURES,
    FORBIDDEN_RUNTIME_FEATURE_TOKENS,
    SelectiveEnsembleModel,
    SelectiveScore,
)
from scripts.eval import g4irsf12_reproducible_harness as g12  # noqa: E402
from scripts.eval import g4irsf16_runtime_trace as native_trace  # noqa: E402
from scripts.eval.g4irsf11_fixed_map import canonical_map_data  # noqa: E402


SCHEMA = "czr005.g4irsf16.full_shadow.v1"
PREDICTION_SCHEMA = "czr005.g4irsf16.shadow_prediction.v1"
GROUP_SCHEMA = "czr005.g4irsf16.shadow_activation_group.v1"
I4_KIND = "I4"
I4_ACTION = "HOLD_ONE_NATURAL_SERVICE_OPPORTUNITY"
I3_AUTHORIZED_KINDS = frozenset({"I3", "I3_RARE_OVERRIDE"})
I3_DIAGNOSTIC_KIND = "I3_RISK_VETO_DIAGNOSTIC"
I3_NOT_AUTHORIZED = "I3_REROUTE_MODEL_NOT_AUTHORIZED"
OUTSIDE_I4_DOMAIN = "OUTSIDE_I4_CAUSAL_ACTION_DOMAIN_F2"
I4_COVERAGE_RANGE = (0.0025, 0.05)
DEFAULT_I4_MODEL = ROOT / "artifacts/models/g4irsf16_i4_d0_calibrated_logistic.json"
OFFLINE_GATE_RELATIVE = Path("artifacts/gates/g4irsf16_offline_model_gate.json")
DEFAULT_OUTPUT_ROOT = ROOT / "outputs"


class FullShadowError(RuntimeError):
    """Raised when a shadow run cannot preserve the frozen safety contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FullShadowError(message)


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{name} must be an object")
    return value


def _array(value: Any, name: str) -> Sequence[Any]:
    _require(
        isinstance(value, Sequence) and not isinstance(value, (str, bytes)),
        f"{name} must be an array",
    )
    return value


def _integer(value: Any, name: str, *, minimum: int | None = None) -> int:
    _require(
        isinstance(value, int) and not isinstance(value, bool),
        f"{name} must be an integer",
    )
    if minimum is not None:
        _require(value >= minimum, f"{name} must be >= {minimum}")
    return int(value)


def _number(value: Any, name: str) -> float:
    _require(
        isinstance(value, (int, float)) and not isinstance(value, bool),
        f"{name} must be numeric",
    )
    number = float(value)
    _require(math.isfinite(number), f"{name} must be finite")
    return number


def _boolean(value: Any, name: str) -> bool:
    _require(isinstance(value, bool), f"{name} must be boolean")
    return bool(value)


def _fraction(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def _portable_path(path: Path | str, *, root: Path) -> str:
    """Render repository artifacts portably while preserving external evidence paths."""

    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _canonical_line(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temp = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temp_path = Path(raw_temp)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        try:
            temp_path.unlink(missing_ok=True)
        finally:
            raise


class AtomicZstdJsonlWriter:
    """Stream a large canonical JSONL table and publish it atomically."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.row_count = 0
        self.uncompressed_byte_count = 0
        self._temp_path: Path | None = None
        self._raw: Any = None
        self._stream: Any = None

    def __enter__(self) -> "AtomicZstdJsonlWriter":
        try:
            import zstandard
        except ImportError as error:  # pragma: no cover - environment contract
            raise FullShadowError("zstandard is required for shadow output") from error
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, raw_temp = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        os.close(descriptor)
        self._temp_path = Path(raw_temp)
        self._raw = self._temp_path.open("wb")
        self._stream = zstandard.ZstdCompressor(level=6).stream_writer(
            self._raw, closefd=False
        )
        return self

    def write(self, row: Mapping[str, Any]) -> None:
        _require(self._stream is not None, "prediction writer is not open")
        payload = _canonical_line(row)
        self._stream.write(payload)
        self.row_count += 1
        self.uncompressed_byte_count += len(payload)

    def __exit__(self, error_type: Any, error: Any, traceback: Any) -> bool:
        assert self._temp_path is not None
        try:
            if self._stream is not None:
                self._stream.close()
            if self._raw is not None and not self._raw.closed:
                self._raw.close()
            if error_type is None:
                os.replace(self._temp_path, self.path)
            else:
                self._temp_path.unlink(missing_ok=True)
        except BaseException:
            self._temp_path.unlink(missing_ok=True)
            raise
        return False

    def metadata(self) -> dict[str, Any]:
        _require(self.path.is_file(), "prediction artifact was not published")
        return {
            "path": str(self.path),
            "encoding": "CANONICAL_JSONL_ZSTD",
            "row_count": self.row_count,
            "uncompressed_byte_count": self.uncompressed_byte_count,
            "compressed_byte_count": self.path.stat().st_size,
        }


@dataclass(frozen=True)
class StaticContext:
    tasks: tuple[Mapping[str, Any], ...]
    nodes: Mapping[int, Mapping[str, Any]]
    edge_seconds: Mapping[tuple[int, int], float]
    heuristic: tuple[tuple[float, ...], ...]
    raw_bag_count: int
    prefix_sha256: str

    @classmethod
    def load(cls, segments: int, *, root: Path = ROOT) -> "StaticContext":
        prefix = g12.load_input_prefix(segments, root=root)
        map_payload = canonical_map_data()
        nodes: dict[int, Mapping[str, Any]] = {}
        for raw_node in _array(map_payload.get("nodes"), "map.nodes"):
            node = _mapping(raw_node, "map.node")
            location = _integer(node.get("location"), "map.node.location", minimum=0)
            _require(location not in nodes, "duplicate canonical map node")
            nodes[location] = node
        edges: dict[tuple[int, int], float] = {}
        for raw_edge in _array(map_payload.get("edges"), "map.edges"):
            edge = _mapping(raw_edge, "map.edge")
            key = (
                _integer(edge.get("start"), "map.edge.start", minimum=0),
                _integer(edge.get("end"), "map.edge.end", minimum=0),
            )
            _require(key not in edges, "duplicate canonical map edge")
            edges[key] = _number(edge.get("travel_time"), "map.edge.travel_time")
        heuristic = tuple(
            tuple(_number(value, "map.heuristic_time") for value in _array(row, "map.heuristic_row"))
            for row in _array(map_payload.get("heuristic_time"), "map.heuristic_time")
        )
        return cls(
            tasks=tuple(prefix.rows),
            nodes=nodes,
            edge_seconds=edges,
            heuristic=heuristic,
            raw_bag_count=prefix.raw_bag_count,
            prefix_sha256=prefix.prefix_sha256,
        )

    def task_for_trace(self, trace_row: Mapping[str, Any]) -> Mapping[str, Any]:
        metadata = _mapping(trace_row.get("metadata"), "trace.metadata")
        runtime_bag_id = _integer(
            metadata.get("runtime_bag_id"), "trace.runtime_bag_id", minimum=0
        )
        _require(runtime_bag_id < len(self.tasks), "runtime_bag_id is outside input prefix")
        task = self.tasks[runtime_bag_id]
        _require(
            str(task.get("segment_id")) == str(trace_row.get("segment_id")),
            "runtime bag/segment identity mismatch",
        )
        return task

    def remaining(self, start: int, goal: int) -> float:
        try:
            return self.heuristic[start][goal]
        except IndexError as error:
            raise FullShadowError(f"heuristic lookup missing: {start}:{goal}") from error

    def edge_time(self, start: int, end: int) -> float:
        try:
            return self.edge_seconds[(start, end)]
        except KeyError as error:
            raise FullShadowError(f"canonical edge missing: {start}:{end}") from error


@dataclass(frozen=True)
class LoadedModels:
    i4: SelectiveEnsembleModel
    i4_path: Path
    i3: SelectiveEnsembleModel | None
    i3_path: Path | None
    i3_authorized: bool
    i3_status: str


def load_models(i4_path: Path, i3_path: Path | None = None) -> LoadedModels:
    resolved_i4 = i4_path.resolve(strict=True)
    i4 = SelectiveEnsembleModel.load(resolved_i4)
    _require(i4.kind == I4_KIND, f"I4 model kind mismatch: {i4.kind}")
    _require(i4.action == I4_ACTION, f"I4 model action mismatch: {i4.action}")

    if i3_path is None:
        return LoadedModels(
            i4=i4,
            i4_path=resolved_i4,
            i3=None,
            i3_path=None,
            i3_authorized=False,
            i3_status=I3_NOT_AUTHORIZED,
        )
    resolved_i3 = i3_path.resolve(strict=True)
    i3 = SelectiveEnsembleModel.load(resolved_i3)
    if i3.kind == I3_DIAGNOSTIC_KIND:
        status = I3_NOT_AUTHORIZED
        authorized = False
    else:
        _require(
            i3.kind in I3_AUTHORIZED_KINDS,
            f"unsupported I3 model kind: {i3.kind}",
        )
        status = "I3_RARE_OVERRIDE_MODEL_AUTHORIZED"
        authorized = True
    return LoadedModels(
        i4=i4,
        i4_path=resolved_i4,
        i3=i3,
        i3_path=resolved_i3,
        i3_authorized=authorized,
        i3_status=status,
    )


def _candidate_index(trace_row: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    result: dict[int, Mapping[str, Any]] = {}
    for raw_candidate in _array(trace_row.get("candidate_records"), "trace.candidates"):
        candidate = _mapping(raw_candidate, "trace.candidate")
        next_node = _integer(candidate.get("next_node"), "candidate.next_node", minimum=0)
        _require(next_node not in result, "duplicate trace candidate")
        result[next_node] = candidate
    _require(bool(result), "trace decision has no candidates")
    return result


def _candidate_is_legal(candidate: Mapping[str, Any]) -> bool:
    features = _mapping(candidate.get("features"), "candidate.features")
    return _boolean(candidate.get("shield_allowed"), "candidate.shield_allowed") and not _boolean(
        features.get("advertised_fault"), "candidate.advertised_fault"
    )


def _trace_uses_pibt_action(trace_row: Mapping[str, Any]) -> bool:
    """Detect an actual per-row PIBT action without treating P2 mode as use."""

    action_text = " ".join(
        str(trace_row.get(name, ""))
        for name in ("decision_source", "rule_reason")
    ).lower()
    return "pibt" in action_text


def _feature_mapping(
    *,
    trace_row: Mapping[str, Any],
    task: Mapping[str, Any],
    context: StaticContext,
    baseline: Mapping[str, Any],
    intervention: Mapping[str, Any],
    kind: str,
    alternative_count: int,
    legal_count: int,
) -> dict[str, float]:
    _require(kind in {"I3", "I4"}, f"unsupported feature kind: {kind}")
    event_time = _number(trace_row.get("event_time"), "trace.event_time")
    current = _integer(trace_row.get("current_node"), "trace.current_node", minimum=0)
    goal = _integer(trace_row.get("goal_node"), "trace.goal_node", minimum=0)
    baseline_next = _integer(baseline.get("next_node"), "baseline.next_node", minimum=0)
    intervention_next = _integer(
        intervention.get("next_node"), "intervention.next_node", minimum=0
    )
    baseline_features = _mapping(baseline.get("features"), "baseline.features")
    intervention_features = _mapping(
        intervention.get("features"), "intervention.features"
    )
    snapshot = _mapping(trace_row.get("local_snapshot"), "trace.local_snapshot")
    metadata = _mapping(trace_row.get("metadata"), "trace.metadata")
    short_history = tuple(
        _integer(value, "trace.short_history", minimum=0)
        for value in _array(trace_row.get("short_history"), "trace.short_history")
    )
    try:
        node = context.nodes[current]
    except KeyError as error:
        raise FullShadowError(f"current map node missing: {current}") from error

    baseline_edge = context.edge_time(current, baseline_next)
    runtime_baseline_edge = _number(
        baseline_features.get("travel_time"), "baseline.travel_time"
    )
    _require(
        math.isclose(baseline_edge, runtime_baseline_edge, rel_tol=0.0, abs_tol=1e-9),
        "baseline edge travel disagrees with canonical map",
    )
    current_remaining = context.remaining(current, goal)
    baseline_remaining = baseline_edge + context.remaining(baseline_next, goal)
    if kind == "I4":
        intervention_edge = 0.0
        intervention_remaining = current_remaining
        history_target = baseline_next
    else:
        intervention_edge = context.edge_time(current, intervention_next)
        runtime_intervention_edge = _number(
            intervention_features.get("travel_time"), "intervention.travel_time"
        )
        _require(
            math.isclose(
                intervention_edge,
                runtime_intervention_edge,
                rel_tol=0.0,
                abs_tol=1e-9,
            ),
            "intervention edge travel disagrees with canonical map",
        )
        intervention_remaining = intervention_edge + context.remaining(
            intervention_next, goal
        )
        history_target = intervention_next

    release_time = _number(task.get("pass_time"), "task.pass_time")
    wait_age = event_time - release_time
    _require(wait_age >= -1e-8, "negative wait age in native trace")
    hour = (event_time / 3600.0) % 24.0
    radians = 2.0 * math.pi * hour / 24.0
    leg = str(task.get("leg"))
    current_wait = max(
        0.0,
        _number(snapshot.get("next_available_time"), "snapshot.next_available_time")
        - event_time,
    )
    # Calendar delay is measured at candidate arrival, exactly as in the
    # matched causal feature cache, not at departure time.
    target_arrival = event_time + _number(
        intervention_features.get("travel_time"),
        "intervention.travel_time",
    )
    target_wait = max(
        0.0,
        _number(
            intervention_features.get("target_next_available"),
            "intervention.target_next_available",
        )
        - target_arrival,
    )
    repeated = len(short_history) - len(set(short_history))

    result = {
        "deadline_slack_seconds": _number(task.get("std"), "task.std") - event_time,
        "wait_age_seconds": max(0.0, wait_age),
        "current_queue_length": _number(
            snapshot.get("junction_queue_length"), "snapshot.junction_queue_length"
        ),
        "target_queue_length": _number(
            intervention_features.get("target_queue_length"),
            "intervention.target_queue_length",
        ),
        "target_scheduled_incoming": _number(
            intervention_features.get("target_scheduled_incoming"),
            "intervention.target_scheduled_incoming",
        ),
        "current_next_available_wait_seconds": current_wait,
        "target_next_available_wait_seconds": target_wait,
        "alternative_action_count": float(alternative_count),
        "total_legal_action_count": float(legal_count),
        "current_node_out_degree": float(
            len(_array(node.get("outgoing"), "map.node.outgoing"))
        ),
        "current_node_type": _number(node.get("node_type"), "map.node.node_type"),
        "current_node_service_seconds": _number(
            node.get("service_time", 0.0), "map.node.service_time"
        ),
        "baseline_edge_travel_seconds": baseline_edge,
        "intervention_edge_travel_seconds": intervention_edge,
        "static_remaining_current_seconds": current_remaining,
        "static_remaining_baseline_seconds": baseline_remaining,
        "static_remaining_intervention_seconds": intervention_remaining,
        "static_potential_delta_seconds": baseline_remaining - intervention_remaining,
        "f2_model_margin": _number(trace_row.get("model_margin"), "trace.model_margin"),
        "f2_raw_score": _number(
            baseline.get("scorer_raw_score"), "baseline.scorer_raw_score"
        ),
        "recent_visit_count": float(short_history.count(history_target)),
        "short_history_repeat_count": float(repeated),
        "storage_in_leg": float(leg == "storage_in"),
        "storage_out_leg": float(leg == "storage_out"),
        "direct_leg": float(leg == "direct"),
        "event_hour_sin": math.sin(radians),
        "event_hour_cos": math.cos(radians),
        "baseline_release": float(kind == "I4"),
        "advertised_fault": float(
            _boolean(
                intervention_features.get("advertised_fault"),
                "intervention.advertised_fault",
            )
        ),
    }
    _require(
        tuple(result) == DEPLOYMENT_FEATURES,
        "deployment feature order/schema drift",
    )
    _require(
        all(
            token not in name.lower()
            for name in result
            for token in FORBIDDEN_RUNTIME_FEATURE_TOKENS
        ),
        "forbidden deployment feature name",
    )
    # Accessing these fields above validates the exact native F2-local source;
    # the model receives only ``result``, never metadata or action identities.
    _integer(metadata.get("runtime_bag_id"), "trace.runtime_bag_id", minimum=0)
    return result


def _feature_contract_violation(features: Mapping[str, Any]) -> bool:
    """Inspect the exact object passed to ``model.score`` for leakage/drift."""

    if tuple(features) != DEPLOYMENT_FEATURES:
        return True
    for name, value in features.items():
        lowered = name.lower()
        if any(token in lowered for token in FORBIDDEN_RUNTIME_FEATURE_TOKENS):
            return True
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return True
        if not math.isfinite(float(value)):
            return True
    return False


def _score_payload(score: SelectiveScore) -> dict[str, Any]:
    return {
        "model_action": score.action,
        "activation": score.activation,
        "abstention_reason": score.abstention_reason,
        "benefit_probability_mean": score.benefit_probability_mean,
        "benefit_probability_lcb": score.benefit_probability_lcb,
        "harmful_probability_mean": score.harmful_probability_mean,
        "harmful_probability_ucb": score.harmful_probability_ucb,
        "utility_mean_seconds": score.utility_mean_seconds,
        "utility_lcb_seconds": score.utility_lcb_seconds,
        "ood": score.ood,
    }


def _score_through_read_only_seam(
    *,
    model: SelectiveEnsembleModel,
    jobs: Sequence[tuple[str, Mapping[str, Any], Mapping[str, float]]],
) -> list[dict[str, Any]]:
    if not jobs:
        return []
    seam_rows = [
        {
            "target": {"target_key": target_key},
            "action_context": dict(action_context),
            "features": dict(features),
        }
        for target_key, action_context, features in jobs
    ]

    def scorer(visible: Mapping[str, Any]) -> Mapping[str, Any]:
        _require(
            set(visible) == {"action_context", "features"},
            "shadow seam exposed nonlocal identity",
        )
        features = _mapping(visible.get("features"), "shadow.features")
        _require(
            tuple(features) == DEPLOYMENT_FEATURES,
            "shadow model received non-exact feature schema",
        )
        score = model.score(features)
        ood_features = [
            name
            for name, value, lower, upper in zip(
                DEPLOYMENT_FEATURES,
                (float(features[name]) for name in DEPLOYMENT_FEATURES),
                model.feature_min,
                model.feature_max,
                strict=True,
            )
            if value < lower or value > upper
        ]
        _require(
            score.ood is bool(ood_features),
            "model OOD flag disagrees with exported training bounds",
        )
        return {
            **_score_payload(score),
            "ood_feature_count": len(ood_features),
            "ood_features": ood_features,
        }

    raw = native_trace.score_shadow_features(seam_rows, scorer)
    _require(len(raw) == len(jobs), "shadow scorer result count mismatch")
    return [dict(_mapping(row.get("proposal"), "shadow.proposal")) for row in raw]


def _best_i3_proposal(
    candidates: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    activated = [row for row in candidates if row.get("activation") is True]
    if not activated:
        return None
    return min(
        activated,
        key=lambda row: (
            -_number(row.get("utility_lcb_seconds"), "i3.utility_lcb_seconds"),
            -_number(row.get("benefit_probability_lcb"), "i3.benefit_probability_lcb"),
            _number(row.get("harmful_probability_ucb"), "i3.harmful_probability_ucb"),
            _integer(row.get("next_node"), "i3.next_node", minimum=0),
        ),
    )


def evaluate_trace_row(
    trace_row: Mapping[str, Any],
    *,
    context: StaticContext,
    models: LoadedModels,
) -> dict[str, Any]:
    metadata = _mapping(trace_row.get("metadata"), "trace.metadata")
    task = context.task_for_trace(trace_row)
    trace_kind = str(metadata.get("trace_kind"))
    _require(
        trace_kind in {"committed_edge_action", "hold_attempt"},
        f"unknown trace kind: {trace_kind}",
    )
    decision_ordinal = _integer(
        metadata.get("decision_ordinal"), "trace.decision_ordinal", minimum=0
    )
    event_time = _number(trace_row.get("event_time"), "trace.event_time")
    candidates = _candidate_index(trace_row)
    legal_nodes = tuple(
        sorted(next_node for next_node, candidate in candidates.items() if _candidate_is_legal(candidate))
    )
    selected_raw = trace_row.get("selected_next")
    committed = trace_kind == "committed_edge_action"
    if committed:
        selected_next = _integer(selected_raw, "trace.selected_next", minimum=0)
        _require(selected_next in candidates, "F2 selected action is absent from candidates")
        _require(selected_next in legal_nodes, "F2 selected action is not shield-admitted")
        tentative_f2_next: int | None = selected_next
    else:
        _require(selected_raw is None, "native hold attempt unexpectedly selected an edge")
        selected_next = None
        prediction = trace_row.get("model_prediction")
        tentative_f2_next = (
            _integer(prediction, "trace.model_prediction", minimum=0)
            if isinstance(prediction, int) and not isinstance(prediction, bool)
            else None
        )

    tentative_candidate = (
        candidates.get(tentative_f2_next)
        if tentative_f2_next is not None
        else None
    )
    i4_domain = (
        tentative_candidate is not None
        and tentative_f2_next in legal_nodes
        and not _trace_uses_pibt_action(trace_row)
    )

    feature_contract_violation = False
    i4_result: dict[str, Any] = {
        "opportunity": i4_domain,
        "model_eligible": i4_domain,
        "tentative_f2_release": tentative_f2_next is not None,
        "tentative_f2_next": tentative_f2_next,
        "causal_action_counts": {
            "baseline_release": int(tentative_f2_next is not None),
            # I4 has one alternative action: hold this release until the next
            # natural local service opportunity.  These are action counts,
            # not counts of outgoing route edges.
            "alternative_action_count": 1 if tentative_f2_next is not None else 0,
            "total_legal_action_count": 2 if tentative_f2_next is not None else 1,
        },
        "proposal": False,
        "proposal_action": None,
        "score": None,
        "reason": ("MODEL_PENDING" if i4_domain else OUTSIDE_I4_DOMAIN),
    }
    alternatives: tuple[int, ...] = ()
    i3_scores: list[dict[str, Any]] = []
    i3_selected: Mapping[str, Any] | None = None
    i3_opportunity = False

    if i4_domain:
        assert tentative_f2_next is not None
        assert tentative_candidate is not None
        baseline = tentative_candidate
        i4_features = _feature_mapping(
            trace_row=trace_row,
            task=task,
            context=context,
            baseline=baseline,
            intervention=baseline,
            kind="I4",
            alternative_count=1,
            legal_count=2,
        )
        feature_contract_violation = _feature_contract_violation(i4_features)
        i4_score = _score_through_read_only_seam(
            model=models.i4,
            jobs=[
                (
                    f"shadow:{decision_ordinal}:I4",
                    {
                        "f2_tentative_release_next": tentative_f2_next,
                        "trace_kind": trace_kind,
                    },
                    i4_features,
                )
            ],
        )[0]
        i4_result.update(
            proposal=bool(i4_score["activation"]),
            proposal_action=(I4_ACTION if i4_score["activation"] else None),
            score=i4_score,
            reason=str(i4_score["abstention_reason"]),
        )

    if committed:
        assert selected_next is not None
        baseline = candidates[selected_next]
        alternatives = tuple(node for node in legal_nodes if node != selected_next)
        i3_opportunity = bool(alternatives)
        common_context = {
            "f2_selected_next": selected_next,
            "trace_kind": trace_kind,
        }
        if i3_opportunity and models.i3_authorized:
            assert models.i3 is not None
            jobs: list[tuple[str, Mapping[str, Any], Mapping[str, float]]] = []
            for next_node in alternatives:
                features = _feature_mapping(
                    trace_row=trace_row,
                    task=task,
                    context=context,
                    baseline=baseline,
                    intervention=candidates[next_node],
                    kind="I3",
                    alternative_count=len(alternatives),
                    legal_count=len(legal_nodes),
                )
                feature_contract_violation = (
                    feature_contract_violation
                    or _feature_contract_violation(features)
                )
                jobs.append(
                    (
                        f"shadow:{decision_ordinal}:I3:{next_node}",
                        {**common_context, "candidate_next": next_node},
                        features,
                    )
                )
            scored = _score_through_read_only_seam(model=models.i3, jobs=jobs)
            for next_node, score in zip(alternatives, scored, strict=True):
                i3_scores.append({"next_node": next_node, **score})
            i3_selected = _best_i3_proposal(i3_scores)

    if i4_result["proposal"]:
        combined = {
            "state": "I4_SELECTIVE_HOLD",
            "action": I4_ACTION,
            "next_node": None,
        }
    elif i3_selected is not None:
        combined = {
            "state": "I3_RARE_OVERRIDE",
            "action": "MOVE_ONE_EDGE",
            "next_node": i3_selected["next_node"],
        }
    else:
        combined = {
            "state": "F2_NORMAL" if committed else "F2_NATIVE_HOLD",
            "action": "MOVE_ONE_EDGE" if committed else "NATIVE_HOLD",
            "next_node": selected_next,
        }

    proposed_next = combined["next_node"]
    illegal_proposal = (
        combined["state"] == "I3_RARE_OVERRIDE"
        and (
            not isinstance(proposed_next, int)
            or proposed_next not in alternatives
            or proposed_next == selected_next
        )
    )
    event_hour = int((event_time / 3600.0) % 24.0)
    return {
        "schema": PREDICTION_SCHEMA,
        "decision_ordinal": decision_ordinal,
        "original_task_id": _integer(
            trace_row.get("task_id"), "trace.task_id", minimum=0
        ),
        "runtime_bag_id": _integer(
            metadata.get("runtime_bag_id"), "trace.runtime_bag_id", minimum=0
        ),
        "segment_id": str(trace_row.get("segment_id")),
        "event_time_seconds": event_time,
        "event_hour": event_hour,
        "trace_kind": trace_kind,
        "source_node_id": _integer(task.get("start"), "task.start", minimum=0),
        "current_node_id": _integer(
            trace_row.get("current_node"), "trace.current_node", minimum=0
        ),
        "goal_node_id": _integer(
            trace_row.get("goal_node"), "trace.goal_node", minimum=0
        ),
        "task_class": str(task.get("leg")),
        "f2": {
            "selected_next_before_shadow": selected_next,
            "selected_next_after_shadow": selected_next,
            "tentative_release_next": tentative_f2_next,
            "action_unchanged": True,
            "model_prediction": trace_row.get("model_prediction"),
            "decision_source": str(trace_row.get("decision_source")),
        },
        "legal_next_nodes": list(legal_nodes),
        "i4": i4_result,
        "i3": {
            "status": models.i3_status,
            "opportunity": i3_opportunity,
            "model_eligible": i3_opportunity and models.i3_authorized,
            "legal_alternatives": list(alternatives),
            "candidate_scores": i3_scores,
            "proposal": i3_selected is not None,
            "proposal_next_node": (
                None if i3_selected is None else i3_selected["next_node"]
            ),
        },
        "combined_shadow_proposal": combined,
        "executed_action_source": "FROZEN_F2_NATIVE_UNCHANGED",
        "supervisor_transition": "NOT_EXECUTED_SHADOW_ONLY",
        "illegal_proposal": illegal_proposal,
        "model_feature_leakage": feature_contract_violation,
    }


class ShadowAccumulator:
    def __init__(self, models: LoadedModels) -> None:
        self.models = models
        self.trace_rows = 0
        self.committed_rows = 0
        self.native_hold_rows = 0
        self.action_mutations = 0
        self.illegal_proposals = 0
        self.feature_leakage = 0
        self.seen_decision_ordinals: set[int] = set()
        self.combined_proposals = Counter()
        self.kind = {
            "I4": Counter(),
            "I3": Counter(),
        }
        self.abstentions = {
            "I4": Counter(),
            "I3": Counter(),
        }
        self.ood_features = {
            "I4": Counter(),
            "I3": Counter(),
        }
        self.domain_exclusions = {
            "I4": Counter(),
        }
        self.groups: dict[tuple[str, str, str], Counter[str]] = defaultdict(Counter)

    def _group(
        self,
        row: Mapping[str, Any],
        kind: str,
        *,
        opportunity: bool,
        eligible: bool,
        activation: bool,
        ood: bool,
    ) -> None:
        if not opportunity:
            return
        values = {
            "source": row["source_node_id"],
            "goal": row["goal_node_id"],
            "hour": row["event_hour"],
            "node": row["current_node_id"],
            "task_class": row["task_class"],
        }
        for dimension, value in values.items():
            counter = self.groups[(kind, dimension, str(value))]
            counter["opportunity_states"] += int(opportunity)
            counter["model_eligible_states"] += int(eligible)
            counter["activation_proposals"] += int(activation)
            counter["abstentions"] += int(not activation)
            counter["model_abstentions"] += int(eligible and not activation)
            counter["not_authorized_states"] += int(not eligible)
            counter["ood_states"] += int(ood)

    def observe(self, row: Mapping[str, Any]) -> None:
        decision_ordinal = _integer(
            row.get("decision_ordinal"), "prediction.decision_ordinal", minimum=0
        )
        _require(
            decision_ordinal not in self.seen_decision_ordinals,
            "duplicate shadow decision boundary",
        )
        self.seen_decision_ordinals.add(decision_ordinal)
        self.trace_rows += 1
        committed = row["trace_kind"] == "committed_edge_action"
        self.committed_rows += int(committed)
        self.native_hold_rows += int(not committed)
        f2 = _mapping(row.get("f2"), "prediction.f2")
        self.action_mutations += int(f2.get("action_unchanged") is not True)
        self.illegal_proposals += int(row.get("illegal_proposal") is True)
        self.feature_leakage += int(row.get("model_feature_leakage") is True)
        combined = _mapping(
            row.get("combined_shadow_proposal"), "prediction.combined"
        )
        self.combined_proposals[str(combined.get("state"))] += 1

        i4 = _mapping(row.get("i4"), "prediction.i4")
        i4_opportunity = i4.get("opportunity") is True
        i4_eligible = i4.get("model_eligible") is True
        i4_activation = i4.get("proposal") is True
        i4_score = i4.get("score")
        i4_ood = False
        self.kind["I4"]["opportunity_states"] += int(i4_opportunity)
        self.kind["I4"]["model_eligible_states"] += int(i4_eligible)
        self.kind["I4"]["activation_proposals"] += int(i4_activation)
        if not i4_eligible:
            reason = str(i4.get("reason"))
            self.kind["I4"]["outside_causal_action_domain_states"] += 1
            self.domain_exclusions["I4"][reason] += 1
        if i4_eligible:
            score = _mapping(i4_score, "prediction.i4.score")
            i4_ood = score.get("ood") is True
            self.ood_features["I4"].update(
                str(name)
                for name in _array(
                    score.get("ood_features"), "prediction.i4.ood_features"
                )
            )
            self.kind["I4"]["ood_states"] += int(i4_ood)
            self.kind["I4"]["harmful_budget_exceedance_states"] += int(
                _number(
                    score.get("harmful_probability_ucb"),
                    "prediction.i4.harmful_probability_ucb",
                )
                > self.models.i4.harmful_probability_ucb_budget
            )
            self.kind["I4"]["activated_risk_budget_violations"] += int(
                i4_activation
                and _number(
                    score.get("harmful_probability_ucb"),
                    "prediction.i4.harmful_probability_ucb",
                )
                > self.models.i4.harmful_probability_ucb_budget
            )
            if not i4_activation:
                reason = str(score.get("abstention_reason"))
                self.abstentions["I4"][reason] += 1
        self._group(
            row,
            "I4",
            opportunity=i4_opportunity,
            eligible=i4_eligible,
            activation=i4_activation,
            ood=i4_ood,
        )

        i3 = _mapping(row.get("i3"), "prediction.i3")
        i3_opportunity = i3.get("opportunity") is True
        i3_eligible = i3.get("model_eligible") is True
        i3_activation = i3.get("proposal") is True
        candidate_scores = [
            _mapping(value, "prediction.i3.candidate_score")
            for value in _array(i3.get("candidate_scores"), "prediction.i3.candidate_scores")
        ]
        i3_ood = any(score.get("ood") is True for score in candidate_scores)
        for score in candidate_scores:
            self.ood_features["I3"].update(
                str(name)
                for name in _array(
                    score.get("ood_features"), "prediction.i3.ood_features"
                )
            )
        self.kind["I3"]["opportunity_states"] += int(i3_opportunity)
        self.kind["I3"]["model_eligible_states"] += int(i3_eligible)
        self.kind["I3"]["scored_candidates"] += len(candidate_scores)
        self.kind["I3"]["activation_proposals"] += int(i3_activation)
        self.kind["I3"]["activated_candidates"] += sum(
            score.get("activation") is True for score in candidate_scores
        )
        self.kind["I3"]["ood_states"] += int(i3_ood)
        self.kind["I3"]["ood_candidates"] += sum(
            score.get("ood") is True for score in candidate_scores
        )
        if i3_opportunity and not i3_eligible:
            self.kind["I3"]["not_authorized_states"] += 1
            self.abstentions["I3"][I3_NOT_AUTHORIZED] += 1
        elif i3_eligible and not i3_activation:
            reasons = sorted(
                {str(score.get("abstention_reason")) for score in candidate_scores}
            )
            reason = "+".join(reasons) if reasons else "NO_SCORED_CANDIDATE"
            self.abstentions["I3"][reason] += 1
        if self.models.i3_authorized:
            assert self.models.i3 is not None
            for score in candidate_scores:
                above = _number(
                    score.get("harmful_probability_ucb"),
                    "prediction.i3.harmful_probability_ucb",
                ) > self.models.i3.harmful_probability_ucb_budget
                self.kind["I3"]["harmful_budget_exceedance_candidates"] += int(above)
                self.kind["I3"]["activated_risk_budget_violations"] += int(
                    above and score.get("activation") is True
                )
        self._group(
            row,
            "I3",
            opportunity=i3_opportunity,
            eligible=i3_eligible,
            activation=i3_activation,
            ood=i3_ood,
        )

    def summary(self) -> dict[str, Any]:
        kinds: dict[str, Any] = {}
        for kind in ("I4", "I3"):
            counts = self.kind[kind]
            eligible = counts["model_eligible_states"]
            kinds[kind] = {
                "opportunity_states": 0,
                "model_eligible_states": 0,
                "activation_proposals": 0,
                "ood_states": 0,
                "outside_causal_action_domain_states": 0,
                **dict(sorted(counts.items())),
                "activation_coverage": _fraction(
                    counts["activation_proposals"], eligible
                ),
                "abstention_count": sum(self.abstentions[kind].values()),
                "abstention_reasons": dict(sorted(self.abstentions[kind].items())),
                "ood_feature_counts": dict(
                    sorted(self.ood_features[kind].items())
                ),
                "causal_action_domain_exclusion_reasons": dict(
                    sorted(self.domain_exclusions.get(kind, Counter()).items())
                ),
            }
        return {
            "trace_row_count": self.trace_rows,
            "unique_decision_boundary_count": len(self.seen_decision_ordinals),
            "committed_edge_action_count": self.committed_rows,
            "native_hold_attempt_count": self.native_hold_rows,
            "f2_action_mutation_count": self.action_mutations,
            "illegal_proposal_count": self.illegal_proposals,
            "model_feature_leakage_count": self.feature_leakage,
            "combined_shadow_states": dict(sorted(self.combined_proposals.items())),
            "by_kind": kinds,
        }

    def group_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for (kind, dimension, value), counts in sorted(self.groups.items()):
            eligible = counts["model_eligible_states"]
            rows.append(
                {
                    "schema": GROUP_SCHEMA,
                    "kind": kind,
                    "dimension": dimension,
                    "value": value,
                    "opportunity_states": counts["opportunity_states"],
                    "model_eligible_states": eligible,
                    "activation_proposals": counts["activation_proposals"],
                    "abstentions": counts["abstentions"],
                    "model_abstentions": counts["model_abstentions"],
                    "not_authorized_states": counts["not_authorized_states"],
                    "ood_states": counts["ood_states"],
                    "activation_coverage": _fraction(
                        counts["activation_proposals"], eligible
                    ),
                }
            )
        return rows


def _artifact_paths(output_root: Path, segments: int) -> dict[str, Path]:
    suffix = "" if segments == native_trace.FULL_SEGMENTS else f"_{segments}"
    return {
        "predictions": output_root / "tables" / f"g4irsf16_shadow_predictions{suffix}.jsonl.zst",
        "groups": output_root / "tables" / f"g4irsf16_shadow_activation_by_group{suffix}.csv",
        "summary": output_root / "reports" / f"g4irsf16_full_shadow{suffix}.json",
        "report": output_root / "reports" / f"g4irsf16_full_shadow{suffix}.md",
        "runtime": output_root / "runtime" / "g4irsf16",
    }


def _write_group_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = (
        "schema",
        "kind",
        "dimension",
        "value",
        "opportunity_states",
        "model_eligible_states",
        "activation_proposals",
        "abstentions",
        "model_abstentions",
        "not_authorized_states",
        "ood_states",
        "activation_coverage",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temp = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temp_path = Path(raw_temp)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def _model_summary(models: LoadedModels, *, root: Path) -> dict[str, Any]:
    i3: dict[str, Any] = {
        "status": models.i3_status,
        "authorized_for_reroute": models.i3_authorized,
        "proposal_semantics": (
            "RARE_OVERRIDE" if models.i3_authorized else "NO_I3_ACTION_PROPOSAL"
        ),
    }
    if models.i3 is not None:
        i3.update(
            path=_portable_path(models.i3_path, root=root),
            kind=models.i3.kind,
            action=models.i3.action,
            artifact_sha256=models.i3.artifact_sha256,
        )
    return {
        "I4": {
            "path": _portable_path(models.i4_path, root=root),
            "kind": models.i4.kind,
            "action": models.i4.action,
            "artifact_sha256": models.i4.artifact_sha256,
            "harmful_probability_ucb_budget": models.i4.harmful_probability_ucb_budget,
        },
        "I3": i3,
    }


def _offline_authorization(root: Path) -> dict[str, Any]:
    path = (root / OFFLINE_GATE_RELATIVE).resolve(strict=True)
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    gate = _mapping(payload, "offline_model_gate")
    _require(
        gate.get("schema") == "czr005.g4irsf16.offline_model_gate.v1",
        "offline model gate schema mismatch",
    )
    i4 = _mapping(gate.get("i4"), "offline_model_gate.i4")
    i3 = _mapping(
        gate.get("i3_rare_override"), "offline_model_gate.i3_rare_override"
    )
    final_audit = _mapping(gate.get("final_audit"), "offline_model_gate.final_audit")
    _require(
        i3.get("status") == I3_NOT_AUTHORIZED,
        "offline gate unexpectedly authorizes I3 reroute",
    )
    _require(
        final_audit.get("status") == "SEALED_NOT_CONSUMED"
        and final_audit.get("row_level_outcomes_used_for_selection") is False,
        "final audit is not sealed",
    )
    return {
        "path": _portable_path(path, root=root),
        "overall_status": str(gate.get("overall_status")),
        "i4_status": str(i4.get("status")),
        "i3_status": str(i3.get("status")),
        "final_audit_status": str(final_audit.get("status")),
        "aggregate_gate_metadata_is_model_input": False,
    }


def _markdown_report(summary: Mapping[str, Any]) -> str:
    shadow = _mapping(summary.get("shadow"), "summary.shadow")
    by_kind = _mapping(shadow.get("by_kind"), "summary.shadow.by_kind")
    i4 = _mapping(by_kind.get("I4"), "summary.shadow.I4")
    i3 = _mapping(by_kind.get("I3"), "summary.shadow.I3")
    hard = _mapping(summary.get("hard_gates"), "summary.hard_gates")
    models = _mapping(summary.get("models"), "summary.models")
    i3_model = _mapping(models.get("I3"), "summary.models.I3")
    authorization = _mapping(
        summary.get("offline_authorization"), "summary.offline_authorization"
    )
    title = (
        "G4IRSF16 full 1x shadow report"
        if summary.get("segments") == native_trace.FULL_SEGMENTS
        else f"G4IRSF16 {summary.get('segments')}-segment shadow smoke report"
    )
    lines = [
        f"# {title}",
        "",
        f"Status: `{summary['status']}`.",
        "",
        "Models proposed actions while the native runtime executed frozen F2 only. "
        "This is shadow evidence, not a closed-loop outcome or benefit claim.",
        "",
        "## Native F2 hard gates",
        "",
        "| Gate | Value |",
        "|---|---:|",
        f"| completed segments | {hard['completed_segments']} / {hard['requested_segments']} |",
        f"| raw bags | {hard['raw_bag_count']} |",
        f"| failed | {hard['failed_count']} |",
        f"| conflicts | {hard['reservation_conflicts']} |",
        f"| unsafe edge entries | {hard['unsafe_edge_entry_count']} |",
        f"| full A* calls | {hard['runtime_full_astar_calls']} |",
        f"| global scans | {hard['runtime_global_scan_count']} |",
        f"| future-route reads | {hard['runtime_future_route_read_count']} |",
        f"| unresolved deadlocks | {hard['unresolved_deadlock_count']} |",
        f"| F2 action mutations caused by shadow | {shadow['f2_action_mutation_count']} |",
        f"| illegal proposals | {shadow['illegal_proposal_count']} |",
        f"| model feature leakage | {shadow['model_feature_leakage_count']} |",
        "",
        "## Shadow coverage",
        "",
        "| Kind | Opportunities | Model eligible | Proposals | Coverage | OOD |",
        "|---|---:|---:|---:|---:|---:|",
        f"| I4 | {i4.get('opportunity_states', 0)} | {i4.get('model_eligible_states', 0)} | "
        f"{i4.get('activation_proposals', 0)} | {i4.get('activation_coverage')} | {i4.get('ood_states', 0)} |",
        f"| I3 | {i3.get('opportunity_states', 0)} | {i3.get('model_eligible_states', 0)} | "
        f"{i3.get('activation_proposals', 0)} | {i3.get('activation_coverage')} | {i3.get('ood_states', 0)} |",
        "",
        f"I3 status: `{i3_model['status']}`. Diagnostic risk-veto artifacts are never "
        "converted into rare-route override proposals.",
        "",
        "## Offline authorization",
        "",
        f"- Overall: `{authorization['overall_status']}`",
        f"- I4: `{authorization['i4_status']}`",
        f"- I3: `{authorization['i3_status']}`",
        f"- Final audit: `{authorization['final_audit_status']}`",
        "",
        "## Promotion boundary",
        "",
        f"I4 preregistered coverage range check: `{summary['promotion_checks']['i4_coverage_in_preregistered_range']}`.",
        "Beneficial-support overlap is intentionally not computed from runtime shadow rows, "
        "because causal outcome labels are forbidden model/runtime inputs; it remains an "
        "offline audit join before closed-loop promotion.",
        "",
        "## Artifacts",
        "",
        f"- Per-decision predictions: `{summary['artifacts']['predictions']['path']}`",
        f"- Activation groups: `{summary['artifacts']['activation_by_group']}`",
        f"- Native trace evidence: `{summary['artifacts']['runtime_trace_metadata']}`",
        "",
    ]
    return "\n".join(lines)


def run_full_shadow(
    *,
    binary: Path,
    i4_model: Path,
    segments: int,
    trace_shards: int,
    allow_full: bool,
    i3_model: Path | None = None,
    search_path: Path | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    root: Path = ROOT,
    executor: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    _require(segments in native_trace.ALLOWED_SEGMENTS, "unsupported segment count")
    if segments == native_trace.FULL_SEGMENTS:
        _require(allow_full, "full original-1x shadow requires --allow-full")
    _require(0 < trace_shards <= 64, "trace_shards must be in 1..64")
    models = load_models(i4_model, i3_model)
    offline_authorization = _offline_authorization(root)
    context = StaticContext.load(segments, root=root)
    paths = _artifact_paths(output_root.resolve(), segments)
    accumulator = ShadowAccumulator(models)

    with AtomicZstdJsonlWriter(paths["predictions"]) as prediction_writer:

        def consume(
            shard_index: int, rows: Sequence[Mapping[str, Any]]
        ) -> None:
            ordered = sorted(
                rows,
                key=lambda row: _integer(
                    _mapping(row.get("metadata"), "trace.metadata").get(
                        "decision_ordinal"
                    ),
                    "trace.decision_ordinal",
                    minimum=0,
                ),
            )
            for trace_row in ordered:
                prediction = evaluate_trace_row(
                    trace_row,
                    context=context,
                    models=models,
                )
                prediction["trace_shard_index"] = shard_index
                accumulator.observe(prediction)
                prediction_writer.write(prediction)

        runtime_metadata = native_trace.run_runtime_trace(
            binary=binary,
            search_path=search_path,
            segments=segments,
            trace_shards=trace_shards,
            allow_full=allow_full,
            capture_matched_features=False,
            output_dir=paths["runtime"],
            root=root,
            executor=executor,
            trace_shard_consumer=consume,
        )
        runtime_summary = _mapping(
            runtime_metadata.get("runtime_summary"), "runtime.runtime_summary"
        )
        _require(
            accumulator.trace_rows
            == _mapping(
                runtime_metadata.get("trace_integrity"), "runtime.trace_integrity"
            ).get("decision_trace_seen_count"),
            "prediction table does not cover every native decision row",
        )
        _require(
            _integer(runtime_summary.get("fault_event_count"), "runtime.fault_event_count")
            == 0,
            "full shadow must remain the frozen fault-free original-1x run",
        )
        _require(accumulator.action_mutations == 0, "shadow mutated an F2 action")
        _require(accumulator.illegal_proposals == 0, "shadow proposed an illegal action")
        _require(accumulator.feature_leakage == 0, "shadow model feature leakage")

    predictions = prediction_writer.metadata()
    predictions["path"] = _portable_path(predictions["path"], root=root)
    shadow_summary = accumulator.summary()
    first_shard = _mapping(
        _array(runtime_metadata.get("shards"), "runtime.shards")[0],
        "runtime.shard[0]",
    )
    hard = _mapping(first_shard.get("hard_gates"), "runtime.hard_gates")
    i4_counts = _mapping(
        _mapping(shadow_summary.get("by_kind"), "shadow.by_kind").get("I4"),
        "shadow.I4",
    )
    i4_coverage = i4_counts.get("activation_coverage")
    coverage_pass = (
        isinstance(i4_coverage, (int, float))
        and not isinstance(i4_coverage, bool)
        and I4_COVERAGE_RANGE[0] <= float(i4_coverage) <= I4_COVERAGE_RANGE[1]
    )
    hard_gates = {
        "all_native_live_hard_gates_pass": hard.get("all_live_hard_gates_pass") is True,
        "requested_segments": hard.get("requested_count"),
        "completed_segments": hard.get("completed_count"),
        "raw_bag_count": context.raw_bag_count,
        "failed_count": hard.get("failed_count"),
        "reservation_conflicts": hard.get("reservation_conflicts"),
        "unsafe_edge_entry_count": hard.get(
            "physical_fault_edge_entry_violation_count"
        ),
        "runtime_full_astar_calls": hard.get("runtime_full_astar_calls"),
        "runtime_global_scan_count": hard.get("runtime_global_scan_count"),
        "runtime_future_route_read_count": hard.get(
            "runtime_future_route_read_count"
        ),
        "unresolved_deadlock_count": hard.get("unresolved_deadlock_count"),
        "event_limit_reached": hard.get("event_limit_reached"),
        "time_limit_reached": hard.get("time_limit_reached"),
    }
    overall_hard_pass = (
        hard_gates["all_native_live_hard_gates_pass"]
        and shadow_summary["f2_action_mutation_count"] == 0
        and shadow_summary["illegal_proposal_count"] == 0
        and shadow_summary["model_feature_leakage_count"] == 0
        and predictions["row_count"]
        == runtime_metadata["trace_integrity"]["decision_trace_seen_count"]
        and shadow_summary["unique_decision_boundary_count"]
        == runtime_metadata["trace_integrity"]["unique_decision_ordinal_count"]
    )
    summary: dict[str, Any] = {
        "schema": SCHEMA,
        "status": (
            (
                "PASS_FROZEN_F2_FULL_SHADOW"
                if segments == native_trace.FULL_SEGMENTS
                else "PASS_FROZEN_F2_SHADOW_SMOKE"
            )
            if overall_hard_pass
            else "FAIL_SHADOW_HARD_GATE"
        ),
        "execution_mode": "READ_ONLY_MODEL_PROPOSALS_FROZEN_F2_EXECUTED",
        "segments": segments,
        "trace_shards": trace_shards,
        "models": _model_summary(models, root=root),
        "offline_authorization": offline_authorization,
        "input": {
            "segment_count": segments,
            "raw_bag_count": context.raw_bag_count,
            "prefix_sha256": context.prefix_sha256,
        },
        "hard_gates": hard_gates,
        "shadow": shadow_summary,
        "promotion_checks": {
            "activation_support_positive": i4_counts.get("activation_proposals", 0) > 0,
            "i4_coverage_preregistered_range": list(I4_COVERAGE_RANGE),
            "i4_coverage_in_preregistered_range": coverage_pass,
            "activated_harmful_risk_budget_violations": i4_counts.get(
                "activated_risk_budget_violations", 0
            ),
            "beneficial_support_overlap": "NOT_EVALUATED_NO_OUTCOME_LABELS_IN_RUNTIME_SHADOW",
            "closed_loop_promotion_ready": False,
        },
        "scientific_boundary": {
            "model_actions_executed": False,
            "native_actions": "FROZEN_F2_ONLY",
            "row_level_outcome_or_causal_labels_read": False,
            "offline_aggregate_gate_metadata_read": True,
            "closed_loop_claim_allowed": False,
            "rule_model_disagreement": "NOT_AVAILABLE_NO_RULE_SCORER_INPUT",
            "i3_diagnostic_is_action_authority": False,
        },
        "runtime_trace_integrity": runtime_metadata["trace_integrity"],
        "artifacts": {
            "predictions": predictions,
            "activation_by_group": _portable_path(paths["groups"], root=root),
            "runtime_trace_metadata": _portable_path(
                runtime_metadata["metadata_path"], root=root
            ),
            "summary_json": _portable_path(paths["summary"], root=root),
            "report_markdown": _portable_path(paths["report"], root=root),
        },
    }
    _write_group_csv(paths["groups"], accumulator.group_rows())
    _atomic_bytes(
        paths["summary"],
        json.dumps(
            summary,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n",
    )
    _atomic_bytes(paths["report"], _markdown_report(summary).encode("utf-8"))
    _require(overall_hard_pass, "shadow hard gate failed")
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--search-path", type=Path)
    parser.add_argument("--i4-model", type=Path, default=DEFAULT_I4_MODEL)
    parser.add_argument("--i3-model", type=Path)
    parser.add_argument(
        "--segments", type=int, choices=native_trace.ALLOWED_SEGMENTS, required=True
    )
    parser.add_argument("--trace-shards", type=int, default=1)
    parser.add_argument("--allow-full", action="store_true")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    summary = run_full_shadow(
        binary=args.binary,
        search_path=args.search_path,
        i4_model=args.i4_model,
        i3_model=args.i3_model,
        segments=args.segments,
        trace_shards=args.trace_shards,
        allow_full=args.allow_full,
        output_root=args.output_root,
    )
    print(
        json.dumps(
            {
                "status": summary["status"],
                "segments": summary["segments"],
                "trace_rows": summary["shadow"]["trace_row_count"],
                "i4_proposals": summary["shadow"]["by_kind"]["I4"].get(
                    "activation_proposals", 0
                ),
                "i3_status": summary["models"]["I3"]["status"],
                "i3_proposals": summary["shadow"]["by_kind"]["I3"].get(
                    "activation_proposals", 0
                ),
                "summary_path": summary["artifacts"]["summary_json"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
