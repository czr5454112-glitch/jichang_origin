"""Fail-closed, lightweight G4IRSF11 v3 decision rankers.

The models in this module deliberately consume only bounded per-candidate
runtime features.  Training is authorised only by :func:`preflight_training`,
which binds an A--H gate manifest to the exact decision-data manifest and
verifies every referenced artifact digest.  A missing, partial, stale, or
synthetic-looking gate is a blocker; there is no warning-to-pass path.

The implementation uses NumPy plus the Python standard library.  It provides
four deliberately small policies:

* ``v3_linear_ranker``
* ``v3_tiny_mlp``
* ``v3_feature_pruned_mlp``
* ``v3_risk_head_plus_ranker``

All split builders operate on connected task/repeat groups.  Consequently the
same task family or deterministic semantic duplicate cannot cross train/test
even for time-, source-, OD-, or fault-held-out evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass
import csv
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from czr005.datasets.decision_trace import EVENT_RUNTIME_FEATURE_SOURCES, SCHEMA_ID


PRETRAINING_GATE_SCHEMA = "czr005.g4irsf11.pretraining_gate.v1"
TRAINING_STATUS_SCHEMA = "czr005.g4irsf11.v3_training_status.v1"
MODEL_SCHEMA = "czr005.g4irsf11.v3_model.v1"
REQUIRED_STAGE_GATES = tuple("ABCDEFGH")
MODEL_NAMES = (
    "v3_linear_ranker",
    "v3_tiny_mlp",
    "v3_feature_pruned_mlp",
    "v3_risk_head_plus_ranker",
)
FEATURE_NAMES = tuple(EVENT_RUNTIME_FEATURE_SOURCES)
PRUNED_FEATURE_NAMES = (
    "static_potential",
    "travel_time",
    "target_queue_length",
    "target_scheduled_incoming",
    "corridor_next_available",
    "advertised_fault",
    "recent_visit_count",
    "two_hop_queue_pressure",
)
REQUIRED_DECISION_VALIDATIONS = (
    "candidate_graph_membership",
    "candidate_equals_true_outgoing_set",
    "selected_in_candidates",
    "model_fallback_disagreement_action_semantics",
    "model_score_semantics",
    "model_prediction_min_cost",
    "model_margin_second_min_minus_min",
    "model_margin_finite_non_null",
    "candidate_order_reproducible",
    "future_route_suffix_absent",
    "runtime_full_astar_zero",
    "source_release_mapping_complete",
    "feature_lineage",
)
REQUIRED_DATA_ARTIFACTS = (
    "hard_case_index",
    "outcome_sample",
    "feature_lineage_table",
    "source_release_mapping",
)
SPLIT_NAMES = (
    "grouped_random",
    "day_heldout",
    "time_heldout",
    "source_heldout",
    "od_heldout",
    "fault_heldout",
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REPEAT_SUFFIXES = (
    re.compile(r"(?i)(?:[_-]?repeat[_-]?\d+)$"),
    re.compile(r"(?i)(?:[_-]?rep[_-]?\d+)$"),
    re.compile(r"(?i)(?:[_-]?run[_-]?\d+)$"),
)
_RISK_FAILURES = {"failed", "timeout", "unrecovered"}


class V3TrainingError(ValueError):
    """Raised for invalid data after the external manifests are approved."""


@dataclass(frozen=True)
class PretrainingApproval:
    allowed: bool
    blockers: tuple[str, ...]
    gate_manifest_sha256: str
    decision_manifest_sha256: str
    artifacts: Mapping[str, Path]
    gate_statuses: Mapping[str, str]


@dataclass(frozen=True)
class DecisionExample:
    decision_id: str
    task_family: str
    semantic_fingerprint: str
    source: str
    goal: str
    fault: str
    day: int
    event_time: float
    candidate_nodes: tuple[int, ...]
    candidate_features: np.ndarray
    target_index: int | None
    risk_label: int

    @property
    def od(self) -> str:
        return f"{self.source}->{self.goal}"


@dataclass(frozen=True)
class DatasetSplit:
    name: str
    train_indices: tuple[int, ...]
    test_indices: tuple[int, ...]
    train_groups: tuple[str, ...]
    test_groups: tuple[str, ...]
    heldout: Mapping[str, Any]


@dataclass(frozen=True)
class PreparedDataset:
    examples: tuple[DecisionExample, ...]
    group_ids: tuple[str, ...]
    splits: Mapping[str, DatasetSplit]
    dataset_sha256: str


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_duplicate_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_object_pairs
    )
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _resolve_artifact(repo: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} path is missing")
    raw = Path(value)
    resolved = raw.resolve() if raw.is_absolute() else (repo / raw).resolve()
    if not resolved.is_relative_to(repo):
        raise ValueError(f"{label} path escapes repository: {resolved}")
    if not resolved.is_file():
        raise ValueError(f"{label} file does not exist: {resolved}")
    return resolved


def _verify_descriptor(
    repo: Path,
    descriptor: Any,
    label: str,
    blockers: list[str],
    *,
    require_rows: bool = False,
) -> Path | None:
    if not isinstance(descriptor, Mapping):
        blockers.append(f"{label}: artifact descriptor is missing or not an object")
        return None
    expected = str(descriptor.get("sha256") or "").lower()
    if not _SHA256_RE.fullmatch(expected):
        blockers.append(f"{label}: sha256 is missing or invalid")
        return None
    try:
        path = _resolve_artifact(repo, descriptor.get("path"), label)
    except (OSError, ValueError) as exc:
        blockers.append(f"{label}: {exc}")
        return None
    actual = sha256_file(path)
    if actual != expected:
        blockers.append(f"{label}: sha256 mismatch (expected {expected}, actual {actual})")
        return None
    if require_rows:
        row_count = descriptor.get("row_count")
        if isinstance(row_count, bool) or not isinstance(row_count, int) or row_count <= 0:
            blockers.append(f"{label}: positive integer row_count is required")
            return None
        if path.suffix.lower() == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                actual_rows = sum(1 for _ in csv.DictReader(handle))
        elif path.suffix.lower() == ".jsonl":
            with path.open("r", encoding="utf-8") as handle:
                actual_rows = sum(1 for line in handle if line.strip())
        else:
            actual_rows = row_count
        if actual_rows != row_count:
            blockers.append(
                f"{label}: row_count mismatch (expected {row_count}, actual {actual_rows})"
            )
            return None
    return path


def preflight_training(
    repo: Path | str,
    gate_manifest_path: Path | str,
    decision_manifest_path: Path | str,
) -> PretrainingApproval:
    """Verify A--H evidence and exact decision-data provenance.

    This function returns blockers rather than throwing for ordinary missing or
    failed gates so callers can persist a reproducible negative result.  No
    caller should load rows or initialise model weights until ``allowed`` is
    true.
    """

    repo_path = Path(repo).resolve()
    gate_path = Path(gate_manifest_path).resolve()
    decision_path = Path(decision_manifest_path).resolve()
    blockers: list[str] = []
    artifacts: dict[str, Path] = {}
    gate_statuses: dict[str, str] = {}
    gate_digest = ""
    decision_digest = ""

    for path, label in ((gate_path, "gate manifest"), (decision_path, "decision manifest")):
        if not path.is_relative_to(repo_path):
            blockers.append(f"{label}: path escapes repository: {path}")
        elif not path.is_file():
            blockers.append(f"{label}: file does not exist: {path}")

    gate: dict[str, Any] = {}
    decision: dict[str, Any] = {}
    if gate_path.is_file() and gate_path.is_relative_to(repo_path):
        try:
            gate_digest = sha256_file(gate_path)
            gate = _read_json_object(gate_path, "gate manifest")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            blockers.append(f"gate manifest: {exc}")
    if decision_path.is_file() and decision_path.is_relative_to(repo_path):
        try:
            decision_digest = sha256_file(decision_path)
            decision = _read_json_object(decision_path, "decision manifest")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            blockers.append(f"decision manifest: {exc}")

    if gate:
        if gate.get("schema") != PRETRAINING_GATE_SCHEMA:
            blockers.append(
                f"gate manifest: schema must be {PRETRAINING_GATE_SCHEMA!r}"
            )
        gates = gate.get("gates")
        if not isinstance(gates, Mapping):
            blockers.append("gate manifest: gates must be an A-H object")
            gates = {}
        for stage in REQUIRED_STAGE_GATES:
            entry = gates.get(stage) if isinstance(gates, Mapping) else None
            if not isinstance(entry, Mapping):
                gate_statuses[stage] = "MISSING"
                blockers.append(f"gate {stage}: missing")
                continue
            status = str(entry.get("status") or "").upper()
            gate_statuses[stage] = status or "MISSING"
            if status != "PASS":
                blockers.append(f"gate {stage}: status is {status or '<missing>'}, not PASS")
            evidence = entry.get("evidence")
            if not isinstance(evidence, list) or not evidence:
                blockers.append(f"gate {stage}: at least one hashed evidence artifact is required")
                continue
            for index, descriptor in enumerate(evidence):
                _verify_descriptor(repo_path, descriptor, f"gate {stage} evidence[{index}]", blockers)

        bound = gate.get("decision_manifest")
        bound_path = _verify_descriptor(
            repo_path,
            bound,
            "gate decision_manifest binding",
            blockers,
        )
        if bound_path is not None and bound_path != decision_path:
            blockers.append(
                "gate decision_manifest binding: path does not match requested decision manifest"
            )

    if decision:
        if decision.get("schema_id") != SCHEMA_ID:
            blockers.append(f"decision manifest: schema_id must be {SCHEMA_ID!r}")
        validation = decision.get("validation")
        if not isinstance(validation, Mapping):
            blockers.append("decision manifest: validation object is missing")
            validation = {}
        if validation.get("status") != "PASS":
            blockers.append("decision manifest: validation.status is not PASS")
        for name in REQUIRED_DECISION_VALIDATIONS:
            if validation.get(name) != "PASS":
                blockers.append(f"decision manifest: validation.{name} is not PASS")
        coverage = decision.get("coverage")
        if not isinstance(coverage, Mapping) or coverage.get("status") != "PASS":
            blockers.append("decision manifest: high-flow/fault/tail coverage is not PASS")
        sampling = decision.get("sampling")
        if not isinstance(sampling, Mapping):
            blockers.append("decision manifest: sampling object is missing")
        else:
            sample_count = sampling.get("sample_count")
            if isinstance(sample_count, bool) or not isinstance(sample_count, int) or sample_count <= 0:
                blockers.append("decision manifest: sampling.sample_count must be positive")
        if decision.get("sampling_minimum_quota_status") != "PASS":
            blockers.append("decision manifest: sampling minimum quota status is not PASS")

        descriptors = decision.get("artifacts")
        if not isinstance(descriptors, Mapping):
            blockers.append("decision manifest: artifacts object is missing")
            descriptors = {}
        for name in REQUIRED_DATA_ARTIFACTS:
            resolved = _verify_descriptor(
                repo_path,
                descriptors.get(name) if isinstance(descriptors, Mapping) else None,
                f"decision artifact {name}",
                blockers,
                require_rows=True,
            )
            if resolved is not None:
                artifacts[name] = resolved

    return PretrainingApproval(
        allowed=not blockers,
        blockers=tuple(sorted(set(blockers))),
        gate_manifest_sha256=gate_digest,
        decision_manifest_sha256=decision_digest,
        artifacts=dict(sorted(artifacts.items())),
        gate_statuses={stage: gate_statuses.get(stage, "MISSING") for stage in REQUIRED_STAGE_GATES},
    )


def _parse_json_cell(value: Any, label: str) -> Any:
    if not isinstance(value, str) or not value.strip():
        raise V3TrainingError(f"{label} is empty")
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise V3TrainingError(f"{label} is not valid JSON") from exc


def _strip_repeat(value: str) -> str:
    result = value.strip()
    previous = None
    while previous != result:
        previous = result
        for pattern in _REPEAT_SUFFIXES:
            result = pattern.sub("", result)
    return result.rstrip("_-") or value.strip()


def _finite_float(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise V3TrainingError(f"{label} must be numeric") from exc
    if not math.isfinite(result):
        raise V3TrainingError(f"{label} must be finite")
    return result


def _truth_bool(value: Any, label: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    raise V3TrainingError(f"{label} must be a boolean")


def _load_outcomes(path: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise V3TrainingError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(row, dict):
                raise V3TrainingError(f"{path}:{line_number}: outcome must be an object")
            decision_id = str(row.get("decision_id") or "").strip()
            if not decision_id or decision_id in result:
                raise V3TrainingError(
                    f"{path}:{line_number}: missing or duplicate decision_id {decision_id!r}"
                )
            result[decision_id] = row
    if not result:
        raise V3TrainingError("outcome artifact is empty")
    return result


def load_training_examples(
    hard_case_path: Path | str,
    outcome_path: Path | str,
) -> tuple[DecisionExample, ...]:
    """Load fully labelled per-decision candidate records.

    Successful outcomes supervise candidate ranking using the action actually
    taken.  Failed/looping/unrecovered outcomes supervise only the risk head;
    their selected edge is never treated as a positive imitation target.
    """

    hard_path = Path(hard_case_path)
    outcomes = _load_outcomes(Path(outcome_path))
    examples: list[DecisionExample] = []
    seen: set[str] = set()
    with hard_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row_number, row in enumerate(csv.DictReader(handle), start=2):
            decision_id = str(row.get("decision_id") or "").strip()
            if not decision_id or decision_id in seen:
                raise V3TrainingError(
                    f"{hard_path}:{row_number}: missing or duplicate decision_id {decision_id!r}"
                )
            seen.add(decision_id)
            outcome = outcomes.get(decision_id)
            if outcome is None:
                raise V3TrainingError(
                    f"{hard_path}:{row_number}: no separate post-hoc outcome for {decision_id}"
                )
            reached_goal = _truth_bool(
                outcome.get("reached_goal"), f"outcome[{decision_id}].reached_goal"
            )
            failed_recovery = str(outcome.get("fault_recovery_outcome") or "").lower() in _RISK_FAILURES
            loop = (
                _truth_bool(
                    outcome["loop_or_dead_end"],
                    f"outcome[{decision_id}].loop_or_dead_end",
                )
                if "loop_or_dead_end" in outcome
                else False
            )
            risk_label = int((not reached_goal) or loop or failed_recovery)

            raw_candidates = _parse_json_cell(
                row.get("candidate_records"),
                f"{hard_path}:{row_number}:candidate_records",
            )
            if not isinstance(raw_candidates, list) or len(raw_candidates) < 2:
                raise V3TrainingError(
                    f"{hard_path}:{row_number}: candidate_records must contain at least two candidates"
                )
            nodes: list[int] = []
            matrix: list[list[float]] = []
            for candidate_index, candidate in enumerate(raw_candidates):
                if not isinstance(candidate, Mapping):
                    raise V3TrainingError(
                        f"{hard_path}:{row_number}: candidate[{candidate_index}] is not an object"
                    )
                try:
                    node = int(candidate["next_node"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise V3TrainingError(
                        f"{hard_path}:{row_number}: candidate[{candidate_index}].next_node invalid"
                    ) from exc
                features = candidate.get("features")
                if not isinstance(features, Mapping):
                    raise V3TrainingError(
                        f"{hard_path}:{row_number}: candidate[{candidate_index}].features invalid"
                    )
                unknown = sorted(set(map(str, features)) - set(FEATURE_NAMES))
                if unknown:
                    raise V3TrainingError(
                        f"{hard_path}:{row_number}: unapproved candidate features {unknown}"
                    )
                nodes.append(node)
                matrix.append(
                    [
                        float(bool(features[name]))
                        if isinstance(features.get(name, 0.0), bool)
                        else _finite_float(
                            features.get(name, 0.0),
                            f"candidate[{candidate_index}].features.{name}",
                        )
                        for name in FEATURE_NAMES
                    ]
                )
            if len(nodes) != len(set(nodes)):
                raise V3TrainingError(f"{hard_path}:{row_number}: duplicate candidate nodes")
            selected = int(row["selected_next"])
            target_index = nodes.index(selected) if reached_goal and not loop and not failed_recovery else None
            task_id = str(row.get("task_id") or "").strip()
            scenario = _strip_repeat(str(row.get("scenario_observed") or row.get("scenario") or ""))
            if not task_id or not scenario:
                raise V3TrainingError(f"{hard_path}:{row_number}: task/scenario is missing")
            task_family = f"{scenario}|{_strip_repeat(task_id)}"
            source = str(row.get("source_node") or "").strip()
            goal = str(row.get("goal_node") or "").strip()
            fault = str(row.get("fault_bucket") or "").strip()
            if not source or not goal or not fault:
                raise V3TrainingError(f"{hard_path}:{row_number}: source/goal/fault is missing")
            arrival = _finite_float(
                row.get("original_arrival_time"),
                f"{hard_path}:{row_number}:original_arrival_time",
            )
            event_time = _finite_float(
                row.get("event_time"), f"{hard_path}:{row_number}:event_time"
            )
            fingerprint = str(row.get("semantic_fingerprint") or "").strip().lower()
            if not _SHA256_RE.fullmatch(fingerprint):
                raise V3TrainingError(
                    f"{hard_path}:{row_number}: semantic_fingerprint must be SHA-256"
                )
            examples.append(
                DecisionExample(
                    decision_id=decision_id,
                    task_family=task_family,
                    semantic_fingerprint=fingerprint,
                    source=source,
                    goal=goal,
                    fault=fault,
                    day=math.floor(arrival / 86_400.0),
                    event_time=event_time,
                    candidate_nodes=tuple(nodes),
                    candidate_features=np.asarray(matrix, dtype=np.float64),
                    target_index=target_index,
                    risk_label=risk_label,
                )
            )
    if not examples:
        raise V3TrainingError("hard-case artifact is empty")
    if not any(example.target_index is not None for example in examples):
        raise V3TrainingError("no successful decision imitation labels are available")
    return tuple(examples)


class _DisjointSet:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: int, right: int) -> None:
        a, b = self.find(left), self.find(right)
        if a != b:
            self.parent[max(a, b)] = min(a, b)


def connected_group_ids(examples: Sequence[DecisionExample]) -> tuple[str, ...]:
    """Connect rows sharing a task/repeat family or semantic fingerprint."""

    sets = _DisjointSet(len(examples))
    task_owner: dict[str, int] = {}
    fingerprint_owner: dict[str, int] = {}
    for index, example in enumerate(examples):
        for key, owners in (
            (example.task_family, task_owner),
            (example.semantic_fingerprint, fingerprint_owner),
        ):
            previous = owners.setdefault(key, index)
            sets.union(index, previous)
    members: dict[int, list[str]] = {}
    for index, example in enumerate(examples):
        members.setdefault(sets.find(index), []).append(example.decision_id)
    root_id = {
        root: _sha256_bytes(_canonical_json(sorted(ids)).encode("utf-8"))[:20]
        for root, ids in members.items()
    }
    return tuple(root_id[sets.find(index)] for index in range(len(examples)))


def _group_members(group_ids: Sequence[str]) -> dict[str, tuple[int, ...]]:
    result: dict[str, list[int]] = {}
    for index, group in enumerate(group_ids):
        result.setdefault(group, []).append(index)
    return {key: tuple(value) for key, value in sorted(result.items())}


def _make_split(
    name: str,
    groups: Mapping[str, tuple[int, ...]],
    test_groups: Iterable[str],
    heldout: Mapping[str, Any],
) -> DatasetSplit:
    test = frozenset(test_groups)
    all_groups = frozenset(groups)
    train = all_groups - test
    if not train or not test:
        raise V3TrainingError(f"{name}: both train and test groups are required")
    train_indices = tuple(sorted(index for group in train for index in groups[group]))
    test_indices = tuple(sorted(index for group in test for index in groups[group]))
    return DatasetSplit(
        name=name,
        train_indices=train_indices,
        test_indices=test_indices,
        train_groups=tuple(sorted(train)),
        test_groups=tuple(sorted(test)),
        heldout=dict(heldout),
    )


def _value_heldout_split(
    name: str,
    examples: Sequence[DecisionExample],
    groups: Mapping[str, tuple[int, ...]],
    attribute: str,
    *,
    prefer_fault: bool = False,
) -> DatasetSplit:
    values = sorted({str(getattr(example, attribute)) for example in examples})
    if len(values) < 2:
        raise V3TrainingError(f"{name}: at least two distinct {attribute} values are required")
    candidates = [value for value in values if value != "no_fault"] if prefer_fault else values
    if not candidates:
        candidates = values
    heldout_value = sorted(
        candidates,
        key=lambda value: (_sha256_bytes(f"g4irsf11|{name}|{value}".encode()), value),
    )[-1]
    test_groups = {
        group
        for group, indices in groups.items()
        if any(str(getattr(examples[index], attribute)) == heldout_value for index in indices)
    }
    return _make_split(name, groups, test_groups, {attribute: heldout_value})


def build_grouped_splits(
    examples: Sequence[DecisionExample],
    *,
    seed: int = 11,
) -> tuple[tuple[str, ...], dict[str, DatasetSplit]]:
    """Build all mandatory grouped, day/time/source/OD/fault held-outs."""

    if len(examples) < 4:
        raise V3TrainingError("at least four decision rows are required for grouped evaluation")
    group_ids = connected_group_ids(examples)
    groups = _group_members(group_ids)
    if len(groups) < 2:
        raise V3TrainingError("at least two disjoint task/repeat groups are required")
    ordered = sorted(
        groups,
        key=lambda group: (_sha256_bytes(f"{seed}|grouped_random|{group}".encode()), group),
    )
    test_count = max(1, math.ceil(len(ordered) * 0.2))
    if test_count >= len(ordered):
        test_count = len(ordered) - 1
    splits: dict[str, DatasetSplit] = {
        "grouped_random": _make_split(
            "grouped_random",
            groups,
            ordered[:test_count],
            {"seed": seed, "test_fraction_target": 0.2},
        )
    }

    day_values = sorted({example.day for example in examples})
    if len(day_values) < 2:
        raise V3TrainingError("day_heldout: at least two actual day buckets are required")
    latest_day = day_values[-1]
    splits["day_heldout"] = _make_split(
        "day_heldout",
        groups,
        {
            group
            for group, indices in groups.items()
            if any(examples[index].day == latest_day for index in indices)
        },
        {"day": latest_day},
    )

    chronology = sorted(
        groups,
        key=lambda group: (
            max(examples[index].event_time for index in groups[group]),
            group,
        ),
    )
    time_count = max(1, math.ceil(len(chronology) * 0.2))
    if time_count >= len(chronology):
        time_count = len(chronology) - 1
    splits["time_heldout"] = _make_split(
        "time_heldout",
        groups,
        chronology[-time_count:],
        {
            "minimum_heldout_event_time": min(
                examples[index].event_time
                for group in chronology[-time_count:]
                for index in groups[group]
            )
        },
    )
    splits["source_heldout"] = _value_heldout_split(
        "source_heldout", examples, groups, "source"
    )

    # OD is a derived grouping dimension, handled explicitly rather than as a
    # model feature.  Absolute source/goal IDs never enter the scorer.
    od_values = sorted({example.od for example in examples})
    if len(od_values) < 2:
        raise V3TrainingError("od_heldout: at least two distinct OD values are required")
    heldout_od = sorted(
        od_values,
        key=lambda value: (_sha256_bytes(f"g4irsf11|od_heldout|{value}".encode()), value),
    )[-1]
    splits["od_heldout"] = _make_split(
        "od_heldout",
        groups,
        {
            group
            for group, indices in groups.items()
            if any(examples[index].od == heldout_od for index in indices)
        },
        {"od": heldout_od},
    )
    splits["fault_heldout"] = _value_heldout_split(
        "fault_heldout", examples, groups, "fault", prefer_fault=True
    )

    for split in splits.values():
        if set(split.train_groups) & set(split.test_groups):
            raise AssertionError(f"{split.name}: connected group leakage")
        train_tasks = {examples[index].task_family for index in split.train_indices}
        test_tasks = {examples[index].task_family for index in split.test_indices}
        if train_tasks & test_tasks:
            raise AssertionError(f"{split.name}: task/repeat family leakage")
        train_fingerprints = {
            examples[index].semantic_fingerprint for index in split.train_indices
        }
        test_fingerprints = {
            examples[index].semantic_fingerprint for index in split.test_indices
        }
        if train_fingerprints & test_fingerprints:
            raise AssertionError(f"{split.name}: deterministic duplicate leakage")
        if not any(examples[index].target_index is not None for index in split.train_indices):
            raise V3TrainingError(f"{split.name}: training side has no successful rank labels")
        if not any(examples[index].target_index is not None for index in split.test_indices):
            raise V3TrainingError(f"{split.name}: test side has no successful rank labels")

    return group_ids, splits


def prepare_dataset(
    examples: Sequence[DecisionExample],
    *,
    seed: int = 11,
) -> PreparedDataset:
    group_ids, splits = build_grouped_splits(examples, seed=seed)
    digest_rows = [
        {
            "decision_id": example.decision_id,
            "task_family": example.task_family,
            "semantic_fingerprint": example.semantic_fingerprint,
            "source": example.source,
            "goal": example.goal,
            "fault": example.fault,
            "day": example.day,
            "event_time": example.event_time,
            "candidate_nodes": example.candidate_nodes,
            "candidate_features": example.candidate_features.tolist(),
            "target_index": example.target_index,
            "risk_label": example.risk_label,
            "group_id": group_ids[index],
        }
        for index, example in enumerate(examples)
    ]
    return PreparedDataset(
        examples=tuple(examples),
        group_ids=group_ids,
        splits=splits,
        dataset_sha256=_sha256_bytes(_canonical_json(digest_rows).encode("utf-8")),
    )


def _normalisation(
    examples: Sequence[DecisionExample],
    indices: Sequence[int],
    feature_indices: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    rows = [
        examples[index].candidate_features[:, feature_indices]
        for index in indices
        if examples[index].target_index is not None
    ]
    if not rows:
        raise V3TrainingError("ranker normalisation has no successful examples")
    matrix = np.concatenate(rows, axis=0)
    mean = matrix.mean(axis=0)
    std = matrix.std(axis=0)
    std = np.where(std < 1.0e-9, 1.0, std)
    return mean, std


def _stable_rng_seed(seed: int, *parts: str) -> int:
    digest = hashlib.sha256("|".join((str(seed), *parts)).encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def _softmax(scores: np.ndarray) -> np.ndarray:
    shifted = scores - float(np.max(scores))
    exp = np.exp(np.clip(shifted, -60.0, 60.0))
    return exp / float(exp.sum())


def _matrix_vector(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
    """Small dense product without loading an optional external BLAS runtime."""

    return np.sum(matrix * vector[None, :], axis=1)


def _matrix_matrix(matrix: np.ndarray, weights: np.ndarray) -> np.ndarray:
    return np.sum(matrix[:, :, None] * weights[None, :, :], axis=1)


def _fit_linear(
    examples: Sequence[DecisionExample],
    train_indices: Sequence[int],
    feature_indices: np.ndarray,
    mean: np.ndarray,
    std: np.ndarray,
    *,
    epochs: int,
    learning_rate: float,
    seed: int,
) -> dict[str, Any]:
    weights = np.zeros(len(feature_indices), dtype=np.float64)
    labelled = [index for index in train_indices if examples[index].target_index is not None]
    rng = np.random.default_rng(seed)
    for _ in range(epochs):
        for position in rng.permutation(len(labelled)):
            example = examples[labelled[int(position)]]
            features = (example.candidate_features[:, feature_indices] - mean) / std
            probabilities = _softmax(_matrix_vector(features, weights))
            gradient_scores = probabilities
            gradient_scores[int(example.target_index)] -= 1.0
            gradient = np.sum(features * gradient_scores[:, None], axis=0) + 1.0e-4 * weights
            weights -= learning_rate * np.clip(gradient, -10.0, 10.0)
    return {"kind": "linear", "weights": weights}


def _fit_mlp(
    examples: Sequence[DecisionExample],
    train_indices: Sequence[int],
    feature_indices: np.ndarray,
    mean: np.ndarray,
    std: np.ndarray,
    *,
    hidden_dim: int,
    epochs: int,
    learning_rate: float,
    seed: int,
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    scale = 1.0 / math.sqrt(max(1, len(feature_indices)))
    w1 = rng.normal(0.0, scale * 0.25, (len(feature_indices), hidden_dim))
    b1 = np.zeros(hidden_dim, dtype=np.float64)
    w2 = rng.normal(0.0, 0.1, hidden_dim)
    b2 = 0.0
    labelled = [index for index in train_indices if examples[index].target_index is not None]
    for _ in range(epochs):
        for position in rng.permutation(len(labelled)):
            example = examples[labelled[int(position)]]
            features = (example.candidate_features[:, feature_indices] - mean) / std
            hidden = np.tanh(_matrix_matrix(features, w1) + b1)
            scores = _matrix_vector(hidden, w2) + b2
            gradient_scores = _softmax(scores)
            gradient_scores[int(example.target_index)] -= 1.0
            grad_w2 = np.sum(hidden * gradient_scores[:, None], axis=0) + 1.0e-4 * w2
            grad_b2 = float(gradient_scores.sum())
            grad_hidden = gradient_scores[:, None] * w2[None, :]
            grad_z = grad_hidden * (1.0 - hidden * hidden)
            grad_w1 = np.sum(
                features[:, :, None] * grad_z[:, None, :], axis=0
            ) + 1.0e-4 * w1
            grad_b1 = grad_z.sum(axis=0)
            w2 -= learning_rate * np.clip(grad_w2, -10.0, 10.0)
            b2 -= learning_rate * max(-10.0, min(10.0, grad_b2))
            w1 -= learning_rate * np.clip(grad_w1, -10.0, 10.0)
            b1 -= learning_rate * np.clip(grad_b1, -10.0, 10.0)
    return {"kind": "tiny_mlp", "w1": w1, "b1": b1, "w2": w2, "b2": b2}


def _rank_scores(
    ranker: Mapping[str, Any],
    features: np.ndarray,
) -> np.ndarray:
    if ranker["kind"] == "linear":
        return _matrix_vector(features, np.asarray(ranker["weights"], dtype=np.float64))
    hidden = np.tanh(
        _matrix_matrix(features, np.asarray(ranker["w1"], dtype=np.float64))
        + np.asarray(ranker["b1"], dtype=np.float64)
    )
    return _matrix_vector(hidden, np.asarray(ranker["w2"], dtype=np.float64)) + float(ranker["b2"])


def _risk_features(
    example: DecisionExample,
    feature_indices: np.ndarray,
    mean: np.ndarray,
    std: np.ndarray,
) -> np.ndarray:
    candidates = (example.candidate_features[:, feature_indices] - mean) / std
    return np.concatenate(
        (
            candidates.mean(axis=0),
            candidates.min(axis=0),
            candidates.max(axis=0),
            np.asarray([min(len(candidates), 16) / 16.0], dtype=np.float64),
        )
    )


def _fit_risk_head(
    examples: Sequence[DecisionExample],
    train_indices: Sequence[int],
    feature_indices: np.ndarray,
    mean: np.ndarray,
    std: np.ndarray,
    *,
    epochs: int,
    learning_rate: float,
    seed: int,
) -> dict[str, Any]:
    rows = np.stack(
        [_risk_features(examples[index], feature_indices, mean, std) for index in train_indices]
    )
    labels = np.asarray([examples[index].risk_label for index in train_indices], dtype=np.float64)
    weights = np.zeros(rows.shape[1], dtype=np.float64)
    positive_rate = float(np.clip(labels.mean(), 1.0e-4, 1.0 - 1.0e-4))
    bias = math.log(positive_rate / (1.0 - positive_rate))
    rng = np.random.default_rng(seed)
    for _ in range(epochs):
        for position in rng.permutation(len(rows)):
            x = rows[int(position)]
            label = labels[int(position)]
            logit = float(np.clip(np.sum(x * weights) + bias, -30.0, 30.0))
            probability = 1.0 / (1.0 + math.exp(-logit))
            gradient = probability - label
            weights -= learning_rate * np.clip(gradient * x + 1.0e-4 * weights, -10.0, 10.0)
            bias -= learning_rate * max(-10.0, min(10.0, gradient))
    return {"kind": "logistic", "weights": weights, "bias": bias}


def _binary_auc(labels: Sequence[int], scores: Sequence[float]) -> float | None:
    positive = [score for label, score in zip(labels, scores) if label == 1]
    negative = [score for label, score in zip(labels, scores) if label == 0]
    if not positive or not negative:
        return None
    wins = 0.0
    for left in positive:
        for right in negative:
            wins += 1.0 if left > right else 0.5 if left == right else 0.0
    return wins / (len(positive) * len(negative))


def _evaluate(
    examples: Sequence[DecisionExample],
    indices: Sequence[int],
    feature_indices: np.ndarray,
    mean: np.ndarray,
    std: np.ndarray,
    ranker: Mapping[str, Any],
    risk_head: Mapping[str, Any] | None,
) -> dict[str, Any]:
    labelled = [index for index in indices if examples[index].target_index is not None]
    correct = 0
    for index in labelled:
        example = examples[index]
        features = (example.candidate_features[:, feature_indices] - mean) / std
        prediction = int(np.argmax(_rank_scores(ranker, features)))
        correct += int(prediction == example.target_index)
    result: dict[str, Any] = {
        "decision_count": len(indices),
        "rank_label_count": len(labelled),
        "top1": correct / len(labelled) if labelled else None,
    }
    if risk_head is not None:
        labels: list[int] = []
        probabilities: list[float] = []
        weights = np.asarray(risk_head["weights"], dtype=np.float64)
        bias = float(risk_head["bias"])
        for index in indices:
            example = examples[index]
            x = _risk_features(example, feature_indices, mean, std)
            logit = float(np.clip(np.sum(x * weights) + bias, -30.0, 30.0))
            probabilities.append(1.0 / (1.0 + math.exp(-logit)))
            labels.append(example.risk_label)
        result["risk_brier"] = float(
            np.mean((np.asarray(probabilities) - np.asarray(labels)) ** 2)
        )
        result["risk_accuracy_0_5"] = sum(
            int((probability >= 0.5) == bool(label))
            for label, probability in zip(labels, probabilities)
        ) / len(labels)
        result["risk_auc"] = _binary_auc(labels, probabilities)
    return result


def _serialise_array(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, Mapping):
        return {str(key): _serialise_array(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialise_array(item) for item in value]
    return value


def validate_model_payload(payload: Mapping[str, Any]) -> None:
    """Validate the portable JSON model contract before inference."""

    if payload.get("schema") != MODEL_SCHEMA:
        raise V3TrainingError(f"model schema must be {MODEL_SCHEMA!r}")
    if payload.get("model_name") not in MODEL_NAMES:
        raise V3TrainingError("unknown v3 model_name")
    if payload.get("absolute_node_id_features") is not False:
        raise V3TrainingError("absolute node ID features must remain disabled")
    raw_names = payload.get("feature_names")
    if not isinstance(raw_names, list) or not raw_names:
        raise V3TrainingError("model feature_names must be a non-empty array")
    names = tuple(map(str, raw_names))
    if len(names) != len(set(names)) or any(name not in FEATURE_NAMES for name in names):
        raise V3TrainingError("model contains duplicate or unapproved feature names")
    normalisation = payload.get("normalisation")
    if not isinstance(normalisation, Mapping):
        raise V3TrainingError("model normalisation object is missing")
    for field in ("mean", "std"):
        values = normalisation.get(field)
        if not isinstance(values, list) or len(values) != len(names):
            raise V3TrainingError(f"model normalisation.{field} dimension mismatch")
        if not all(math.isfinite(float(value)) for value in values):
            raise V3TrainingError(f"model normalisation.{field} must be finite")
    if any(float(value) <= 0 for value in normalisation["std"]):
        raise V3TrainingError("model normalisation.std must be positive")
    ranker = payload.get("ranker")
    if not isinstance(ranker, Mapping) or ranker.get("kind") not in {"linear", "tiny_mlp"}:
        raise V3TrainingError("model ranker is missing or unsupported")
    risk_head = payload.get("risk_head")
    if payload.get("model_name") == "v3_risk_head_plus_ranker":
        if not isinstance(risk_head, Mapping) or risk_head.get("kind") != "logistic":
            raise V3TrainingError("risk-head model has no logistic risk head")
    elif risk_head is not None:
        raise V3TrainingError("non-risk model unexpectedly contains a risk head")


def load_v3_model(path: Path | str) -> dict[str, Any]:
    payload = _read_json_object(Path(path), "v3 model")
    validate_model_payload(payload)
    return payload


def _inference_candidates(
    candidate_records: Sequence[Mapping[str, Any]],
    names: Sequence[str],
) -> tuple[tuple[int, ...], np.ndarray]:
    if len(candidate_records) < 2:
        raise V3TrainingError("inference requires at least two candidate records")
    nodes: list[int] = []
    rows: list[list[float]] = []
    for index, candidate in enumerate(candidate_records):
        if not isinstance(candidate, Mapping):
            raise V3TrainingError(f"candidate[{index}] must be an object")
        try:
            node = int(candidate["next_node"])
        except (KeyError, TypeError, ValueError) as exc:
            raise V3TrainingError(f"candidate[{index}].next_node is invalid") from exc
        features = candidate.get("features")
        if not isinstance(features, Mapping):
            raise V3TrainingError(f"candidate[{index}].features must be an object")
        unknown = sorted(set(map(str, features)) - set(FEATURE_NAMES))
        if unknown:
            raise V3TrainingError(f"candidate[{index}] has unapproved features: {unknown}")
        nodes.append(node)
        rows.append(
            [
                float(bool(features[name]))
                if isinstance(features.get(name, 0.0), bool)
                else _finite_float(features.get(name, 0.0), f"candidate[{index}].{name}")
                for name in names
            ]
        )
    if len(nodes) != len(set(nodes)):
        raise V3TrainingError("inference candidate nodes must be unique")
    return tuple(nodes), np.asarray(rows, dtype=np.float64)


def score_v3_candidates(
    model: Mapping[str, Any],
    candidate_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Score one bounded local candidate set with a portable v3 model."""

    validate_model_payload(model)
    names = tuple(map(str, model["feature_names"]))
    nodes, matrix = _inference_candidates(candidate_records, names)
    normalisation = model["normalisation"]
    mean = np.asarray(normalisation["mean"], dtype=np.float64)
    std = np.asarray(normalisation["std"], dtype=np.float64)
    normalised = (matrix - mean) / std
    try:
        scores = _rank_scores(model["ranker"], normalised)
    except (TypeError, ValueError) as exc:
        raise V3TrainingError(f"ranker parameter dimension mismatch: {exc}") from exc
    if scores.shape != (len(nodes),) or not np.all(np.isfinite(scores)):
        raise V3TrainingError("ranker produced invalid candidate scores")
    best = int(np.argmax(scores))
    result: dict[str, Any] = {
        "candidate_next_nodes": list(nodes),
        "scores": [float(value) for value in scores],
        "selected_next": nodes[best],
        "score_semantics": "higher_is_preferred",
    }
    risk_head = model.get("risk_head")
    if risk_head is not None:
        # Construct a temporary example only for the already-normalised bounded
        # candidate aggregate used by the separately trained risk head.
        risk_vector = np.concatenate(
            (
                normalised.mean(axis=0),
                normalised.min(axis=0),
                normalised.max(axis=0),
                np.asarray([min(len(nodes), 16) / 16.0]),
            )
        )
        weights = np.asarray(risk_head["weights"], dtype=np.float64)
        if weights.shape != risk_vector.shape:
            raise V3TrainingError("risk-head parameter dimension mismatch")
        logit = float(
            np.clip(np.sum(risk_vector * weights) + float(risk_head["bias"]), -30.0, 30.0)
        )
        result["risk_probability"] = 1.0 / (1.0 + math.exp(-logit))
    return result


def fit_model_for_split(
    dataset: PreparedDataset,
    model_name: str,
    split_name: str,
    *,
    epochs: int = 80,
    learning_rate: float = 0.03,
    seed: int = 11,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if model_name not in MODEL_NAMES:
        raise ValueError(f"unsupported model: {model_name}")
    if split_name not in dataset.splits:
        raise ValueError(f"unsupported split: {split_name}")
    if epochs <= 0 or learning_rate <= 0:
        raise ValueError("epochs and learning_rate must be positive")
    split = dataset.splits[split_name]
    names = PRUNED_FEATURE_NAMES if model_name == "v3_feature_pruned_mlp" else FEATURE_NAMES
    feature_indices = np.asarray([FEATURE_NAMES.index(name) for name in names], dtype=np.int64)
    mean, std = _normalisation(dataset.examples, split.train_indices, feature_indices)
    local_seed = _stable_rng_seed(seed, model_name, split_name)
    if model_name == "v3_linear_ranker":
        ranker = _fit_linear(
            dataset.examples,
            split.train_indices,
            feature_indices,
            mean,
            std,
            epochs=epochs,
            learning_rate=learning_rate,
            seed=local_seed,
        )
    else:
        hidden_dim = 6 if model_name == "v3_feature_pruned_mlp" else 8
        ranker = _fit_mlp(
            dataset.examples,
            split.train_indices,
            feature_indices,
            mean,
            std,
            hidden_dim=hidden_dim,
            epochs=epochs,
            learning_rate=learning_rate,
            seed=local_seed,
        )
    risk_head = None
    if model_name == "v3_risk_head_plus_ranker":
        risk_classes = {
            dataset.examples[index].risk_label for index in split.train_indices
        }
        if risk_classes != {0, 1}:
            raise V3TrainingError(
                f"{split_name}: risk-head training requires both safe and risk labels"
            )
        risk_head = _fit_risk_head(
            dataset.examples,
            split.train_indices,
            feature_indices,
            mean,
            std,
            epochs=epochs,
            learning_rate=learning_rate,
            seed=_stable_rng_seed(seed, model_name, split_name, "risk"),
        )
    metrics = {
        "train": _evaluate(
            dataset.examples,
            split.train_indices,
            feature_indices,
            mean,
            std,
            ranker,
            risk_head,
        ),
        "test": _evaluate(
            dataset.examples,
            split.test_indices,
            feature_indices,
            mean,
            std,
            ranker,
            risk_head,
        ),
    }
    payload = {
        "schema": MODEL_SCHEMA,
        "model_name": model_name,
        "split": split_name,
        "feature_names": list(names),
        "absolute_node_id_features": False,
        "candidate_input_contract": "bounded_decision_time_local_features_only",
        "model_score_semantics": "higher_is_preferred",
        "normalisation": {"mean": mean, "std": std},
        "ranker": ranker,
        "risk_head": risk_head,
        "training": {
            "dataset_sha256": dataset.dataset_sha256,
            "epochs": epochs,
            "learning_rate": learning_rate,
            "seed": seed,
            "derived_seed": local_seed,
            "train_group_digest": _sha256_bytes(
                _canonical_json(split.train_groups).encode("utf-8")
            ),
            "test_group_digest": _sha256_bytes(
                _canonical_json(split.test_groups).encode("utf-8")
            ),
        },
    }
    return _serialise_array(payload), _serialise_array(metrics)


def train_all_models(
    dataset: PreparedDataset,
    *,
    epochs: int = 80,
    learning_rate: float = 0.03,
    seed: int = 11,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Train each model on the primary split and evaluate all held-out splits."""

    models: dict[str, dict[str, Any]] = {}
    metrics: dict[str, Any] = {}
    for model_name in MODEL_NAMES:
        model_metrics: dict[str, Any] = {}
        primary: dict[str, Any] | None = None
        for split_name in SPLIT_NAMES:
            model, split_metrics = fit_model_for_split(
                dataset,
                model_name,
                split_name,
                epochs=epochs,
                learning_rate=learning_rate,
                seed=seed,
            )
            if split_name == "grouped_random":
                primary = model
            model_metrics[split_name] = split_metrics
        if primary is None:
            raise AssertionError("primary grouped model was not trained")
        models[model_name] = primary
        metrics[model_name] = model_metrics
    return models, metrics


def split_audit_rows(dataset: PreparedDataset) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in SPLIT_NAMES:
        split = dataset.splits[name]
        train_tasks = {dataset.examples[index].task_family for index in split.train_indices}
        test_tasks = {dataset.examples[index].task_family for index in split.test_indices}
        train_fingerprints = {
            dataset.examples[index].semantic_fingerprint for index in split.train_indices
        }
        test_fingerprints = {
            dataset.examples[index].semantic_fingerprint for index in split.test_indices
        }
        rows.append(
            {
                "split": name,
                "train_decisions": len(split.train_indices),
                "test_decisions": len(split.test_indices),
                "train_groups": len(split.train_groups),
                "test_groups": len(split.test_groups),
                "task_repeat_overlap": len(train_tasks & test_tasks),
                "semantic_duplicate_overlap": len(train_fingerprints & test_fingerprints),
                "heldout": dict(split.heldout),
                "status": "PASS",
            }
        )
    return rows
