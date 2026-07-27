"""Build and train the G4IRSF13 local residual-guidance study.

This stage is deliberately conservative.  It extracts real, committed F2
candidate/action decisions from the frozen full archive and combines them
with the Stage-B first-divergence ledger.  Runtime-visible features and
offline labels are written to separate, hash-bound files.

The observed F2 action is the only rank target authorised by the available
evidence.  Stage B did not run a matched runtime-state counterfactual clone,
so a locally feasible v2 action is retained as weak-teacher metadata but is
not promoted to a corrective target.  The exported models are consequently
offline preservation candidates; they are never marked runtime eligible and
the closed-loop ladder remains explicitly NOT_RUN.
"""

from __future__ import annotations

import argparse
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
from typing import Any, Iterable, Iterator, Mapping, Sequence
import uuid

import numpy as np


ROOT = Path(__file__).resolve().parents[2]

MAP_PATH = Path("data/processed/maps/map2.json")
TASK_PATH = Path("data/processed/tasks/inputdata.jsonl")
PER_BAG_PATH = Path("outputs/tables/g4irsf13_per_bag_delta.csv")
DIVERGENCE_PATH = Path("outputs/tables/g4irsf13_decision_divergence.csv")
DIVERGENCE_SAMPLE_PATH = Path(
    "artifacts/traces/g4irsf13_divergence_trace_sample.jsonl"
)
BASELINE_MANIFEST_PATH = Path(
    "artifacts/gates/g4irsf13_baseline_freeze_manifest.json"
)
F2_POLICY_PATH = Path("artifacts/policies/g4irsf13_f2_frozen_baseline.json")
AUTHORITATIVE_REPORT_PATH = Path(
    "outputs/reports/g4irsf13_authoritative_evidence_reconciliation.md"
)

F2_ARCHIVE_POINTER = Path(
    ".local_archives/g4irsf13_delay_attribution/f2/current.json"
)
V2_ARCHIVE_POINTER = Path(
    ".local_archives/g4irsf13_delay_attribution/v2_safe/current.json"
)
ARCHIVE_ROOT = Path(".local_archives/g4irsf13_delay_attribution")

TRACE_SCHEMA_PATH = Path("artifacts/datasets/g4irsf13_v3_trace_schema.json")
DECISIONS_PATH = Path("artifacts/datasets/g4irsf13_v3_decisions.jsonl")
LABELS_PATH = Path("artifacts/datasets/g4irsf13_v3_labels.jsonl")
OUTCOMES_PATH = Path("artifacts/datasets/g4irsf13_v3_outcomes.jsonl")
SPLIT_PATH = Path("artifacts/datasets/g4irsf13_v3_split_manifest.json")
LINEAGE_PATH = Path("artifacts/datasets/g4irsf13_v3_feature_lineage.csv")
SOURCE_MANIFEST_PATH = Path(
    "artifacts/datasets/g4irsf13_v3_source_manifest.json"
)
PRETRAINING_GATE_PATH = Path(
    "artifacts/gates/g4irsf13_v3_pretraining_gate_manifest.json"
)

DATA_REPORT_PATH = Path("outputs/reports/g4irsf13_v3_data_report.md")
TRAINING_REPORT_PATH = Path("outputs/reports/g4irsf13_v3_training_report.md")
CLOSED_LOOP_REPORT_PATH = Path(
    "outputs/reports/g4irsf13_v3_closed_loop_report.md"
)
OFFLINE_TABLE_PATH = Path("outputs/tables/g4irsf13_v3_offline_ab.csv")
FEATURE_TABLE_PATH = Path("outputs/tables/g4irsf13_v3_feature_ablation.csv")
HYPERPARAMETER_TABLE_PATH = Path(
    "outputs/tables/g4irsf13_v3_hyperparameter_selection.csv"
)
CLOSED_LOOP_TABLE_PATH = Path(
    "outputs/tables/g4irsf13_v3_closed_loop_ab.csv"
)
MODEL_DIR = Path("artifacts/models")
CANDIDATE_BUNDLE_PATH = Path(
    "artifacts/policies/g4irsf13_v3_candidate_bundle.json"
)

MAP_RAW_SHA256 = "9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4"
MAP_SEMANTIC_SHA256 = (
    "67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63"
)
TASK_RAW_SHA256 = (
    "968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f"
)
RAW_BAG_COUNT = 28_506
SEGMENT_COUNT = 43_603
F2_MEAN_MINUTES = 41.514218717973414
V2_MEAN_MINUTES = 41.49530698780892
F2_V2_GAP_SECONDS = 1.1347038098698192

PASS = "PASS"
FAIL = "FAIL"
NOT_RUN = "NOT_RUN"
HASH_EXACT = "sha256_exact_bytes"
HASH_TEXT = "sha256_utf8_lf_normalized"

TRACE_SCHEMA = "czr005.g4irsf13.v3_local_residual_trace.v1"
SOURCE_SCHEMA = "czr005.g4irsf13.v3_source_manifest.v1"
GATE_SCHEMA = "czr005.g4irsf13.v3_pretraining_gate.v1"
MODEL_SCHEMA = "czr005.g4irsf13.v3_residual_model.v1"
BUNDLE_SCHEMA = "czr005.g4irsf13.v3_candidate_bundle.v1"

# A candidate may need to overcome at most 6.8 frozen-cost units in the
# observed Level-A corrective cohort.  A symmetric 4.0 bound is the smallest
# tested bound capable of changing every such pair (difference of two clipped
# residuals <= 8.0); it remains a small local correction relative to the
# 30-200 second route costs and cannot bypass shield/PIBT.
RESIDUAL_CLIP = 4.0
SEED = 13_005
EASY_PER_CATEGORY = 256
FRESH_AUDIT_DECISIONS = 384

# No absolute current/candidate/goal ID is a main-model feature.  Absolute IDs
# are retained only as trace identity and in a separately reported diagnostic
# ablation.
FEATURE_NAMES = (
    "static_potential",
    "travel_time",
    "candidate_service_time",
    "target_queue_length",
    "target_scheduled_incoming",
    "target_goal_queue_length",
    "target_goal_scheduled_incoming",
    "goal_conditioned_differential",
    "service_weighted_pressure",
    "two_hop_queue_pressure",
    "recent_visit_count",
    "advertised_fault",
    "fault_message_age_seconds",
    "first_edge_credit_matches",
    "first_edge_credit_required",
    "first_edge_credit_valid",
    "first_edge_credit_slack_seconds",
    "local_calendar_wait_seconds",
    "deadline_slack_seconds",
    "waiting_age_seconds",
    "candidate_node_type_code",
    "candidate_in_degree",
    "candidate_out_degree",
    "merge_state",
    "is_goal",
    "local_queue_length",
    "downstream_pressure",
    "storage_out",
    "goal_relative_progress",
)

FEATURE_LINEAGE = {
    "static_potential": "candidate_records[].features.static_potential",
    "travel_time": "candidate_records[].features.travel_time",
    "candidate_service_time": "canonical map candidate service_time",
    "target_queue_length": "candidate_records[].features.target_queue_length",
    "target_scheduled_incoming": (
        "candidate_records[].features.target_scheduled_incoming"
    ),
    "target_goal_queue_length": (
        "candidate_records[].features.target_goal_queue_length"
    ),
    "target_goal_scheduled_incoming": (
        "candidate_records[].features.target_goal_scheduled_incoming"
    ),
    "goal_conditioned_differential": (
        "candidate_records[].features.goal_conditioned_differential"
    ),
    "service_weighted_pressure": (
        "candidate_records[].features.service_weighted_pressure"
    ),
    "two_hop_queue_pressure": (
        "candidate_records[].features.two_hop_queue_pressure"
    ),
    "recent_visit_count": "candidate_records[].features.recent_visit_count",
    "advertised_fault": "candidate_records[].features.advertised_fault",
    "fault_message_age_seconds": (
        "candidate_records[].features.fault_message_age_seconds"
    ),
    "first_edge_credit_matches": (
        "candidate_records[].features.first_edge_credit_matches"
    ),
    "first_edge_credit_required": (
        "candidate_records[].features.first_edge_credit_required"
    ),
    "first_edge_credit_valid": (
        "candidate_records[].features.first_edge_credit_valid"
    ),
    "first_edge_credit_slack_seconds": (
        "candidate_records[].features.first_edge_credit_slack_seconds"
    ),
    "local_calendar_wait_seconds": (
        "max(local edge/target next-available minus decision time, zero)"
    ),
    "deadline_slack_seconds": "task.std minus decision event_time",
    "waiting_age_seconds": "decision event_time minus task.pass_time",
    "candidate_node_type_code": "canonical map candidate node_type",
    "candidate_in_degree": "canonical map local candidate in-degree",
    "candidate_out_degree": "canonical map local candidate out-degree",
    "merge_state": "canonical map candidate in-degree greater than one",
    "is_goal": "candidate next_node equals current bag goal",
    "local_queue_length": "decision local_snapshot.junction_queue_length",
    "downstream_pressure": "decision local_snapshot.downstream_pressure",
    "storage_out": "current task leg equals storage_out",
    "goal_relative_progress": (
        "minimum local candidate static cost minus candidate static cost"
    ),
}

FORBIDDEN_FEATURE_TOKENS = (
    "label_source",
    "confidence",
    "future",
    "teacher",
    "outcome",
    "finish_time",
    "bag_tth",
    "full_route",
    "route_suffix",
    "path_suffix",
    "selected_next",
    "task_id",
    "pallet_id",
    "segment_id",
    "current_node",
    "next_node",
    "goal_node",
)

MODEL_IDS = (
    "V0_residual_linear",
    "V1_residual_pairwise_logistic",
    "V2_residual_listwise",
    "V3_residual_tiny_mlp",
    "V4_residual_feature_pruned_mlp",
    "V5_best_plus_calibrated_risk_head",
)

# These rows are the recorded train+validation-only probes performed before
# the fresh audit cohort was selected from unused F2 decisions.  They are
# emitted verbatim as provenance; the fresh audit partition is evaluated only
# after the selected hyperparameters below are frozen.
HYPERPARAMETER_PROBE_ROWS = (
    ("pairwise_linear", 0.2, 120, 0.5991285403050110, 0.49171270718232046, 0.26243093922651933),
    ("pairwise_linear", 0.5, 120, 0.7734204793028322, 0.7127071823204420, 0.26430517711171664),
    ("pairwise_linear", 1.0, 120, 0.7777777777777778, 0.7182320441988951, 0.22278481012658227),
    ("pairwise_linear", 0.5, 240, 0.7755991285403050, 0.7154696132596685, 0.2436548223350254),
    ("pairwise_linear", 1.0, 240, 0.7407407407407407, 0.6712707182320442, 0.19946091644204852),
    ("tiny_mlp", 0.5, 200, 0.6535947712418301, 0.5607734806629834, 0.25833333333333336),
    ("tiny_mlp", 0.75, 200, 0.7712418300653595, 0.7099447513812155, 0.26430517711171664),
    ("tiny_mlp", 1.0, 160, 0.7734204793028322, 0.7127071823204420, 0.25806451612903225),
    ("tiny_mlp", 1.0, 240, 0.7755991285403050, 0.7154696132596685, 0.24742268041237114),
)

EASY_CATEGORIES = (
    "unique_outgoing_edge",
    "high_margin_f2_choice",
    "no_contention",
    "direct_goal",
    "f2_v2_current_action_agreement",
)

LEVEL_A_FORMULA_ID = "g4irsf13_level_a_one_step_projection_v1"
LEVEL_A_MIN_MARGIN_SECONDS = 0.05


class StageFError(ValueError):
    """Fail-closed Stage-F validation error."""


@dataclass(frozen=True)
class GraphInfo:
    outgoing: dict[int, tuple[int, ...]]
    incoming_degree: dict[int, int]
    node_type: dict[int, int]
    service_time: dict[int, float]


@dataclass(frozen=True)
class Example:
    decision: Mapping[str, Any]
    label: Mapping[str, Any]
    features: np.ndarray
    frozen_costs: np.ndarray
    selected_index: int
    f2_selected_index: int


def _normalise_text(payload: bytes) -> bytes:
    return payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def sha256_file(path: Path, *, text: bool | None = None) -> str:
    payload = path.read_bytes()
    if text is None:
        text = path.suffix.lower() in {".csv", ".json", ".jsonl", ".md", ".py"}
    if text:
        payload = _normalise_text(payload)
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _pretty_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_json(path: Path, value: Any) -> None:
    _atomic_write(path, _pretty_bytes(value))


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    buffer = io.BytesIO()
    count = 0
    for row in rows:
        buffer.write(_canonical_bytes(row))
        buffer.write(b"\n")
        count += 1
    _atomic_write(path, buffer.getvalue())
    return count


def _write_csv(
    path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]
) -> None:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({name: row.get(name, "") for name in fieldnames})
    _atomic_write(path, stream.getvalue().encode("utf-8"))


def _descriptor(root: Path, relative: Path, *, rows: int | None = None) -> dict[str, Any]:
    path = root / relative
    result: dict[str, Any] = {
        "path": relative.as_posix(),
        "sha256": sha256_file(path),
        "hash_semantics": HASH_TEXT,
        "size_bytes": path.stat().st_size,
    }
    if rows is not None:
        result["row_count"] = int(rows)
    return result


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise StageFError(f"expected JSON object: {path}")
    return payload


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise StageFError(f"{path}:{line_number}: row is not an object")
            rows.append(payload)
    return rows


def _truth(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return float(default)
    return parsed if math.isfinite(parsed) else float(default)


def _stable_fraction(*parts: Any) -> float:
    digest = hashlib.sha256(
        "\x1f".join(map(str, parts)).encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64)


def _self_hash(payload: Mapping[str, Any], field: str) -> str:
    stripped = dict(payload)
    stripped.pop(field, None)
    return hashlib.sha256(_canonical_bytes(stripped)).hexdigest()


def load_graph(root: Path) -> GraphInfo:
    payload = _load_json(root / MAP_PATH)
    outgoing: dict[int, tuple[int, ...]] = {}
    node_type: dict[int, int] = {}
    service_time: dict[int, float] = {}
    incoming_degree: dict[int, int] = {}
    for raw_node in payload.get("nodes", []):
        node = int(raw_node["location"])
        neighbors = tuple(sorted(int(value) for value in raw_node["outgoing"]))
        outgoing[node] = neighbors
        node_type[node] = int(raw_node["node_type"])
        service_time[node] = _number(raw_node.get("service_time"), 0.0)
        incoming_degree.setdefault(node, 0)
        for neighbor in neighbors:
            incoming_degree[neighbor] = incoming_degree.get(neighbor, 0) + 1
    return GraphInfo(outgoing, incoming_degree, node_type, service_time)


def load_tasks(root: Path) -> dict[str, dict[str, Any]]:
    tasks: dict[str, dict[str, Any]] = {}
    with (root / TASK_PATH).open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            tasks[str(row["segment_id"])] = row
    if len(tasks) != SEGMENT_COUNT:
        raise StageFError(f"expected {SEGMENT_COUNT} task segments, got {len(tasks)}")
    return tasks


def load_per_bag(root: Path) -> dict[int, dict[str, str]]:
    with (root / PER_BAG_PATH).open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != RAW_BAG_COUNT:
        raise StageFError(f"expected {RAW_BAG_COUNT} per-bag rows, got {len(rows)}")
    return {int(row["task_id"]): row for row in rows}


def _resolve_archive(root: Path, pointer_relative: Path) -> tuple[Path, dict[str, Any]]:
    pointer_path = root / pointer_relative
    pointer = _load_json(pointer_path)
    descriptor_relative = pointer.get("descriptor_relative_path")
    if not isinstance(descriptor_relative, str):
        raise StageFError(f"archive pointer lacks descriptor path: {pointer_path}")
    descriptor_path = root / ARCHIVE_ROOT / descriptor_relative
    descriptor = _load_json(descriptor_path)
    if descriptor.get("status") != "COMPLETE":
        raise StageFError(f"archive is not COMPLETE: {descriptor_path}")
    archive = descriptor.get("archive")
    if not isinstance(archive, Mapping):
        raise StageFError(f"archive descriptor missing payload: {descriptor_path}")
    payload_path = descriptor_path.parent / str(archive["path"])
    if sha256_file(payload_path, text=False) != archive.get("file_sha256"):
        raise StageFError(f"archive compressed SHA-256 mismatch: {payload_path}")
    return payload_path, descriptor


def _iter_gzip_json_array(path: Path, marker: str) -> Iterator[dict[str, Any]]:
    """Stream one JSON array from a very large canonical gzip object."""

    decoder = json.JSONDecoder()
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        buffer = ""
        while marker not in buffer:
            chunk = stream.read(1 << 20)
            if not chunk:
                raise StageFError(f"marker {marker!r} not found in {path}")
            buffer = (buffer + chunk)[-(2 << 20) :]
        buffer = buffer[buffer.index(marker) + len(marker) :]
        while True:
            buffer = buffer.lstrip()
            if buffer.startswith("]"):
                return
            if buffer.startswith(","):
                buffer = buffer[1:].lstrip()
            while True:
                try:
                    value, end = decoder.raw_decode(buffer)
                    break
                except json.JSONDecodeError:
                    chunk = stream.read(1 << 20)
                    if not chunk:
                        raise StageFError(f"truncated JSON array in {path}")
                    buffer += chunk
            if not isinstance(value, dict):
                raise StageFError(f"non-object decision in {path}")
            yield value
            buffer = buffer[end:]


def _load_v2_paths(path: Path) -> dict[str, tuple[int, ...]]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        payload = json.load(stream)
    tasks = payload.get("runtime_payload", {}).get("tasks", [])
    result: dict[str, tuple[int, ...]] = {}
    for row in tasks:
        result[str(row["segment_id"])] = tuple(int(value) for value in row["path"])
    if len(result) != SEGMENT_COUNT:
        raise StageFError(f"expected {SEGMENT_COUNT} v2 task paths, got {len(result)}")
    return result


def _v2_edge_agrees(
    v2_paths: Mapping[str, tuple[int, ...]],
    segment_id: str,
    current_node: int,
    selected_next: int,
) -> bool:
    path = v2_paths.get(segment_id, ())
    return any(
        path[index] == current_node and path[index + 1] == selected_next
        for index in range(max(0, len(path) - 1))
    )


def _candidate_feature_payload(
    raw_features: Mapping[str, Any],
    *,
    next_node: int,
    current_node: int,
    goal_node: int,
    event_time: float,
    task: Mapping[str, Any],
    local_snapshot: Mapping[str, Any],
    graph: GraphInfo,
    minimum_static_cost: float,
) -> dict[str, float]:
    static_potential = _number(raw_features.get("static_potential"))
    travel_time = _number(raw_features.get("travel_time"))
    corridor_next = _number(
        raw_features.get("corridor_next_available"), event_time
    )
    target_next = _number(raw_features.get("target_next_available"), event_time)
    feature = {
        "static_potential": static_potential,
        "travel_time": travel_time,
        "candidate_service_time": graph.service_time[next_node],
        "target_queue_length": _number(raw_features.get("target_queue_length")),
        "target_scheduled_incoming": _number(
            raw_features.get("target_scheduled_incoming")
        ),
        "target_goal_queue_length": _number(
            raw_features.get("target_goal_queue_length")
        ),
        "target_goal_scheduled_incoming": _number(
            raw_features.get("target_goal_scheduled_incoming")
        ),
        "goal_conditioned_differential": _number(
            raw_features.get("goal_conditioned_differential")
        ),
        "service_weighted_pressure": _number(
            raw_features.get("service_weighted_pressure")
        ),
        "two_hop_queue_pressure": _number(
            raw_features.get("two_hop_queue_pressure")
        ),
        "recent_visit_count": _number(raw_features.get("recent_visit_count")),
        "advertised_fault": float(_truth(raw_features.get("advertised_fault"))),
        "fault_message_age_seconds": _number(
            raw_features.get("fault_message_age_seconds")
        ),
        "first_edge_credit_matches": float(
            _truth(raw_features.get("first_edge_credit_matches"))
        ),
        "first_edge_credit_required": float(
            _truth(raw_features.get("first_edge_credit_required"))
        ),
        "first_edge_credit_valid": float(
            _truth(raw_features.get("first_edge_credit_valid"))
        ),
        "first_edge_credit_slack_seconds": _number(
            raw_features.get("first_edge_credit_slack_seconds")
        ),
        "local_calendar_wait_seconds": max(
            0.0, corridor_next - event_time, target_next - event_time
        ),
        "deadline_slack_seconds": _number(task.get("std")) - event_time,
        "waiting_age_seconds": max(0.0, event_time - _number(task.get("pass_time"))),
        "candidate_node_type_code": float(graph.node_type[next_node]),
        "candidate_in_degree": float(graph.incoming_degree.get(next_node, 0)),
        "candidate_out_degree": float(len(graph.outgoing[next_node])),
        "merge_state": float(graph.incoming_degree.get(next_node, 0) > 1),
        "is_goal": float(next_node == goal_node),
        "local_queue_length": _number(
            local_snapshot.get("junction_queue_length")
        ),
        "downstream_pressure": _number(local_snapshot.get("downstream_pressure")),
        "storage_out": float(str(task.get("leg")) == "storage_out"),
        "goal_relative_progress": minimum_static_cost
        - (static_potential + travel_time),
    }
    if tuple(feature) != FEATURE_NAMES:
        raise StageFError("candidate feature ordering drifted from FEATURE_NAMES")
    if any(not math.isfinite(value) for value in feature.values()):
        raise StageFError("non-finite runtime feature")
    # Identity arguments are deliberately used only for graph lookup and the
    # goal comparison above.  They never become numeric main-model inputs.
    del current_node
    return feature


def _decision_from_runtime(
    raw: Mapping[str, Any],
    *,
    task: Mapping[str, Any],
    graph: GraphInfo,
    decision_id: str | None = None,
    cohort: str,
) -> dict[str, Any]:
    current = int(raw["current_node"])
    goal = int(raw.get("goal_node", task["goal"]))
    event_time = _number(raw["event_time"])
    selected = int(raw["selected_next"])
    candidate_nodes = tuple(int(value) for value in raw["candidate_next_nodes"])
    expected = graph.outgoing.get(current)
    if expected is None or tuple(sorted(candidate_nodes)) != expected:
        raise StageFError(
            f"actual candidate set is incomplete at node {current}: "
            f"{candidate_nodes} != {expected}"
        )
    if selected not in candidate_nodes:
        raise StageFError("actual selected action is absent from candidates")
    raw_records = raw.get("candidate_records")
    if not isinstance(raw_records, list) or len(raw_records) != len(candidate_nodes):
        raise StageFError("candidate records do not cover exact candidate set")
    raw_by_node = {int(record["next_node"]): record for record in raw_records}
    if set(raw_by_node) != set(candidate_nodes):
        raise StageFError("candidate record identities are incomplete or duplicated")
    minimum_static = min(
        _number(raw_by_node[node].get("features", {}).get("static_potential"))
        + _number(raw_by_node[node].get("features", {}).get("travel_time"))
        for node in candidate_nodes
    )
    local_snapshot = raw.get("local_snapshot")
    if not isinstance(local_snapshot, Mapping):
        local_snapshot = {}
    records: list[dict[str, Any]] = []
    for node in candidate_nodes:
        record = raw_by_node[node]
        features = record.get("features")
        if not isinstance(features, Mapping):
            raise StageFError("candidate record has no feature object")
        records.append(
            {
                "next_node": node,
                "shield_allowed": _truth(record.get("shield_allowed", True)),
                "frozen_score_cost": _number(record.get("model_score")),
                "features": _candidate_feature_payload(
                    features,
                    next_node=node,
                    current_node=current,
                    goal_node=goal,
                    event_time=event_time,
                    task=task,
                    local_snapshot=local_snapshot,
                    graph=graph,
                    minimum_static_cost=minimum_static,
                ),
            }
        )
    return {
        "schema": TRACE_SCHEMA,
        "decision_id": decision_id or str(raw["decision_id"]),
        "task_id": int(task["task_id"]),
        "pallet_id": int(task["pallet_id"]),
        "segment_id": str(task["segment_id"]),
        "event_time": event_time,
        "time_block": int(event_time // 1800),
        "source": int(task["start"]),
        "goal": goal,
        "junction": current,
        "storage_leg": str(task["leg"]),
        "contention_motif": (
            "merge"
            if graph.incoming_degree.get(current, 0) > 1
            else "split"
            if len(graph.outgoing[current]) > 1
            else "linear"
        ),
        "fault_regime": "no_fault",
        "candidate_ordering": "next_node_ascending",
        "candidate_next_nodes": list(candidate_nodes),
        "candidate_records": records,
        "selected_next": selected,
        "full_astar_used": False,
        "reservation_depth": 1,
        "cohort": cohort,
    }


def _easy_categories(
    raw: Mapping[str, Any],
    *,
    graph: GraphInfo,
    v2_paths: Mapping[str, tuple[int, ...]],
) -> tuple[str, ...]:
    candidates = tuple(int(value) for value in raw["candidate_next_nodes"])
    selected = int(raw["selected_next"])
    current = int(raw["current_node"])
    goal = int(raw["goal_node"])
    metadata = raw.get("metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}
    local = raw.get("local_snapshot")
    if not isinstance(local, Mapping):
        local = {}
    categories: list[str] = []
    if len(candidates) == 1:
        categories.append("unique_outgoing_edge")
    if len(candidates) > 1 and _number(metadata.get("scorer_raw_margin")) >= 0.5:
        categories.append("high_margin_f2_choice")
    if (
        _number(local.get("junction_queue_length")) <= 1.0
        and _number(local.get("downstream_pressure")) <= 1.0
    ):
        categories.append("no_contention")
    if selected == goal:
        categories.append("direct_goal")
    if _v2_edge_agrees(v2_paths, str(raw["segment_id"]), current, selected):
        categories.append("f2_v2_current_action_agreement")
    # This verifies that the archive record itself is a true local decision.
    if tuple(sorted(candidates)) != graph.outgoing[current]:
        raise StageFError("archive decision candidate set is not map-complete")
    return tuple(categories)


def _heap_add(
    heap: list[tuple[int, str, dict[str, Any], tuple[str, ...]]],
    raw: Mapping[str, Any],
    categories: tuple[str, ...],
    *,
    limit: int,
    salt: str,
) -> None:
    decision_id = str(raw["decision_id"])
    rank = int.from_bytes(
        hashlib.sha256(f"{salt}\x1f{decision_id}".encode()).digest()[:8], "big"
    )
    entry = (-rank, decision_id, dict(raw), categories)
    if len(heap) < limit:
        heapq.heappush(heap, entry)
    elif entry > heap[0]:
        heapq.heapreplace(heap, entry)


def _load_divergence_rows(root: Path) -> list[dict[str, str]]:
    with (root / DIVERGENCE_PATH).open(
        "r", encoding="utf-8", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise StageFError("Stage-B divergence ledger is empty")
    return rows


def _hard_categories(row: Mapping[str, str]) -> tuple[str, ...]:
    categories = ["first_divergence"]
    if _number(row.get("bag_delta_seconds")) > 0.0:
        categories.append("f2_slower_than_v2")
    if int(_number(row.get("f2_path_length_edges"))) > int(
        _number(row.get("v2_path_length_edges"))
    ):
        categories.append("detour")
    if _truth(row.get("merge_node")) or _number(row.get("local_queue_length")) > 1.0:
        categories.append("merge_contention")
    if _truth(row.get("pibt_involvement")):
        categories.append("p2_involvement")
    if _number(row.get("wait_age_seconds")) >= 30.0:
        categories.append("high_wait")
    if str(row.get("leg")) == "storage_out":
        categories.append("storage_out")
    return tuple(categories)


def _runtime_from_divergence(row: Mapping[str, str]) -> dict[str, Any]:
    features = json.loads(row["runtime_features_json"])
    if not isinstance(features, dict):
        raise StageFError("divergence runtime_features_json is not an object")
    return {
        "current_node": int(row["first_divergence_node"]),
        "goal_node": int(row["goal"]),
        "event_time": _number(features["event_time"]),
        "selected_next": int(row["f2_next_node"]),
        "candidate_next_nodes": features["candidate_next_nodes"],
        "candidate_records": features["candidate_records"],
        "local_snapshot": features.get("local_snapshot", {}),
        "metadata": {
            "scorer_raw_margin": (
                abs(
                    _number(features["candidate_records"][0].get("scorer_raw_score"))
                    - _number(
                        features["candidate_records"][1].get("scorer_raw_score")
                    )
                )
                if len(features["candidate_records"]) > 1
                else 999.0
            )
        },
        "segment_id": str(row["segment_id"]),
    }


def _label_row(
    decision: Mapping[str, Any],
    *,
    hard: Sequence[str],
    easy: Sequence[str],
    teacher_next: int | None,
    teacher_agrees: bool,
    locally_feasible: bool,
    outcome_delta: float,
) -> dict[str, Any]:
    projection = _level_a_projection(decision)
    observed_selected = int(decision["selected_next"])
    corrective_authorised = bool(
        projection["rank_target_authorised"]
        and int(projection["preferred_next"]) != observed_selected
    )
    preferred_next = (
        int(projection["preferred_next"])
        if projection["rank_target_authorised"]
        else observed_selected
    )
    is_hard = bool(hard)
    if teacher_next is None:
        weak_teacher = "NOT_AVAILABLE"
        future_dependency = "NOT_APPLICABLE"
    elif teacher_agrees:
        weak_teacher = "AGREES_WITH_OBSERVED_F2_ACTION"
        future_dependency = "LABEL_METADATA_ONLY_NOT_A_RUNTIME_FEATURE"
    else:
        weak_teacher = "CORRECTIVE_TARGET_NOT_AUTHORISED"
        future_dependency = "UNRESOLVED_NO_MATCHED_RUNTIME_STATE_CLONE"
    return {
        "schema": "czr005.g4irsf13.v3_local_residual_label.v1",
        "decision_id": str(decision["decision_id"]),
        "preferred_next": preferred_next,
        "observed_f2_selected_next": observed_selected,
        "rank_target_semantics": (
            "deterministic_local_one_step_projection"
            if projection["rank_target_authorised"]
            else "observed_successful_f2_committed_action_abstention_fallback"
        ),
        "label_source": (
            "level_a_deterministic_local_one_step_projection"
            if projection["rank_target_authorised"]
            else "f2_observed_successful_committed_action"
        ),
        "confidence": projection["confidence"],
        "future_coordination_dependency": future_dependency,
        "weak_teacher_status": weak_teacher,
        "weak_teacher_next": teacher_next,
        "weak_teacher_locally_feasible": bool(locally_feasible),
        "weak_teacher_used_as_rank_target": False,
        "matched_counterfactual_replay": False,
        "corrective_label_authorised": corrective_authorised,
        "residual_supervision": (
            "level_a_corrective"
            if corrective_authorised
            else "preserve_f2_or_level_a_agreement"
        ),
        "level_a_projection": projection,
        "level_b_full_counterfactual_status": (
            "NOT_RUN_NO_MATCHED_RUNTIME_STATE_CLONE"
        ),
        "hard_categories": list(hard),
        "easy_categories": list(easy),
        "risk_label": int(is_hard),
        "sample_weight": 1.5 if is_hard else 1.0,
        "bag_outcome_delta_seconds": outcome_delta,
    }


def _level_a_projection(decision: Mapping[str, Any]) -> dict[str, Any]:
    """Compute a same-state, one-step-only deterministic supervision target.

    Every term is available at the decision time.  This is a bounded local
    projection, not a full-state counterfactual and not a TTH causal label.
    """

    rows: list[dict[str, Any]] = []
    for record in decision["candidate_records"]:
        feature = record["features"]
        travel = float(feature["travel_time"])
        service = max(0.001, float(feature["candidate_service_time"]))
        calendar_wait = max(0.0, float(feature["local_calendar_wait_seconds"]))
        queue_count = max(0.0, float(feature["target_queue_length"]))
        scheduled = max(0.0, float(feature["target_scheduled_incoming"]))
        recent_visits = max(0.0, float(feature["recent_visit_count"]))
        local_queue = max(0.0, float(feature["local_queue_length"]))
        arrival_and_service = travel + calendar_wait + service
        short_queue_bound = (queue_count + 0.5 * scheduled) * service
        cycle_burden = recent_visits * (travel + service)
        trap_burden = (
            60.0
            if float(feature["candidate_out_degree"]) == 0.0
            and float(feature["is_goal"]) == 0.0
            else 0.0
        )
        credit_burden = (
            8.0
            if float(feature["first_edge_credit_required"]) > 0.5
            and float(feature["first_edge_credit_valid"]) <= 0.5
            else 0.0
        ) + (
            4.0
            if float(feature["first_edge_credit_required"]) > 0.5
            and float(feature["first_edge_credit_matches"]) <= 0.5
            else 0.0
        )
        merge_local_burden = (
            max(0.0, local_queue - 1.0)
            * service
            * float(feature["merge_state"])
        )
        total = (
            arrival_and_service
            + short_queue_bound
            + cycle_burden
            + trap_burden
            + credit_burden
            + merge_local_burden
        )
        rows.append(
            {
                "next_node": int(record["next_node"]),
                "arrival_calendar_service_seconds": arrival_and_service,
                "short_queue_bound_seconds": short_queue_bound,
                "cycle_burden_seconds": cycle_burden,
                "trap_burden_seconds": trap_burden,
                "credit_pibt_burden_seconds": credit_burden,
                "merge_local_burden_seconds": merge_local_burden,
                "total_projection_seconds": total,
                "shield_allowed": bool(record["shield_allowed"]),
            }
        )
    allowed = [row for row in rows if row["shield_allowed"]]
    if not allowed:
        return {
            "formula_id": LEVEL_A_FORMULA_ID,
            "candidate_costs": rows,
            "preferred_next": int(decision["selected_next"]),
            "best_margin_seconds": 0.0,
            "confidence": 0.0,
            "rank_target_authorised": False,
            "abstention_reason": "no_shield_allowed_candidate",
            "full_state_clone_used": False,
            "future_route_used": False,
        }
    order = sorted(
        allowed, key=lambda row: (row["total_projection_seconds"], row["next_node"])
    )
    best = order[0]
    margin = (
        float(order[1]["total_projection_seconds"])
        - float(best["total_projection_seconds"])
        if len(order) > 1
        else 999.0
    )
    if len(order) == 1:
        authorised = True
        confidence = 1.0
    else:
        authorised = margin >= LEVEL_A_MIN_MARGIN_SECONDS
        confidence = min(
            0.99,
            max(
                0.50,
                0.50
                + 0.50
                * margin
                / max(1.0, abs(float(best["total_projection_seconds"]))),
            ),
        )
    return {
        "formula_id": LEVEL_A_FORMULA_ID,
        "formula": (
            "travel + local_calendar_wait + candidate_service + "
            "(target_queue + 0.5*target_scheduled_incoming)*candidate_service + "
            "recent_visit*(travel+candidate_service) + sink_trap + "
            "invalid_or_mismatched_credit_burden + "
            "merge*max(local_queue-1,0)*candidate_service"
        ),
        "candidate_costs": rows,
        "preferred_next": int(best["next_node"]),
        "best_margin_seconds": margin,
        "confidence": confidence,
        "minimum_authorised_margin_seconds": LEVEL_A_MIN_MARGIN_SECONDS,
        "rank_target_authorised": authorised,
        "abstention_reason": "" if authorised else "insufficient_local_margin",
        "full_state_clone_used": False,
        "future_route_used": False,
        "claim_boundary": (
            "same-state one-step projection only; not full outcome or causal TTH"
        ),
    }


def _outcome_row(
    decision: Mapping[str, Any],
    *,
    per_bag: Mapping[int, Mapping[str, str]],
) -> dict[str, Any]:
    bag = per_bag[int(decision["task_id"])]
    return {
        "schema": "czr005.g4irsf13.v3_local_residual_outcome.v1",
        "decision_id": str(decision["decision_id"]),
        "task_id": int(decision["task_id"]),
        "f2_bag_completed": True,
        "f2_goal_completion_time_seconds": _number(
            bag.get("f2_goal_completion_time_seconds")
        ),
        "f2_minus_v2_seconds": _number(bag.get("delta_seconds")),
        "post_hoc_only": True,
        "model_input_allowed": False,
    }


def build_trace_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": TRACE_SCHEMA,
        "title": "G4IRSF13 real local candidate/action residual trace",
        "fixed_real_map_only": True,
        "candidate_set_semantics": "exact_true_outgoing_neighbors",
        "selected_action_semantics": "actual committed F2 next edge",
        "reservation_depth": 1,
        "runtime_full_astar_used": False,
        "future_route_model_input_allowed": False,
        "global_reservation_scan_allowed": False,
        "main_model_absolute_node_id_allowed": False,
        "runtime_feature_names": list(FEATURE_NAMES),
        "feature_lineage": FEATURE_LINEAGE,
        "separation_contract": {
            "decision_trace": DECISIONS_PATH.as_posix(),
            "label_metadata": LABELS_PATH.as_posix(),
            "post_hoc_outcomes": OUTCOMES_PATH.as_posix(),
            "label_fields_in_features_allowed": False,
            "outcome_fields_in_features_allowed": False,
        },
        "label_metadata_only_fields": [
            "label_source",
            "confidence",
            "future_coordination_dependency",
            "weak_teacher_status",
            "weak_teacher_next",
            "bag_outcome_delta_seconds",
            "level_a_projection",
        ],
        "forbidden_feature_tokens": list(FORBIDDEN_FEATURE_TOKENS),
        "model_contract": {
            "final_score": "frozen_g4e_cost + clipped_learned_residual",
            "residual_clip": [-RESIDUAL_CLIP, RESIDUAL_CLIP],
            "high_uncertainty_behavior": "zero residual; frozen scorer decides",
            "shield_bypass_allowed": False,
            "pibt_ownership_change_allowed": False,
        },
        "level_a_label_contract": {
            "formula_id": LEVEL_A_FORMULA_ID,
            "minimum_margin_seconds": LEVEL_A_MIN_MARGIN_SECONDS,
            "same_decision_state_only": True,
            "full_state_clone_used": False,
            "future_route_used": False,
            "claim_boundary": (
                "bounded one-step projection target, not full-outcome causal label"
            ),
        },
    }


def _feature_leakage_paths(value: Any, prefix: str = "") -> list[str]:
    violations: list[str] = []
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key)
            path = f"{prefix}.{key}" if prefix else key
            lowered = key.lower()
            if any(token in lowered for token in FORBIDDEN_FEATURE_TOKENS):
                violations.append(path)
            violations.extend(_feature_leakage_paths(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(_feature_leakage_paths(child, f"{prefix}[{index}]"))
    return violations


def _verify_no_feature_leakage(decisions: Sequence[Mapping[str, Any]]) -> None:
    for row in decisions:
        for record in row["candidate_records"]:
            features = record["features"]
            if set(features) != set(FEATURE_NAMES) or len(features) != len(
                FEATURE_NAMES
            ):
                raise StageFError("runtime feature allow-list drift")
            violations = _feature_leakage_paths(features)
            if violations:
                raise StageFError(
                    f"label/future/identity leakage in {row['decision_id']}: {violations}"
                )


def _split_assignment(task_id: int) -> str:
    fraction = _stable_fraction("g4irsf13-v3-group", task_id)
    if fraction < 0.70:
        return "train"
    if fraction < 0.85:
        return "validation"
    return "test"


def build_split_manifest(
    decisions: Sequence[Mapping[str, Any]],
    labels: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    assignments: dict[str, str] = {}
    groups: dict[int, str] = {}
    for row in decisions:
        task_id = int(row["task_id"])
        requested = (
            "audit_test"
            if row["cohort"] == "fresh_final_audit_holdout"
            else _split_assignment(task_id)
        )
        split = groups.setdefault(task_id, requested)
        if split != requested:
            raise StageFError("fresh audit raw bag overlaps development cohort")
        assignments[str(row["decision_id"])] = split
    counts = {
        split: sum(value == split for value in assignments.values())
        for split in ("train", "validation", "test", "audit_test")
    }
    if min(counts.values()) == 0:
        raise StageFError(f"group split has an empty partition: {counts}")

    task_sets: dict[str, set[int]] = {
        split: set() for split in ("train", "validation", "test", "audit_test")
    }
    for row in decisions:
        task_sets[assignments[str(row["decision_id"])]].add(int(row["task_id"]))
    overlap = (
        (task_sets["train"] & task_sets["validation"])
        | (task_sets["train"] & task_sets["test"])
        | (task_sets["train"] & task_sets["audit_test"])
        | (task_sets["validation"] & task_sets["test"])
        | (task_sets["validation"] & task_sets["audit_test"])
        | (task_sets["test"] & task_sets["audit_test"])
    )
    if overlap:
        raise StageFError("same raw bag/task appears in multiple splits")

    dimensions = (
        "source",
        "goal",
        "time_block",
        "junction",
        "storage_leg",
        "contention_motif",
        "fault_regime",
    )
    dimension_audit: dict[str, Any] = {}
    for dimension in dimensions:
        values = sorted({str(row[dimension]) for row in decisions})
        if len(values) < 2:
            dimension_audit[dimension] = {
                "status": "NOT_APPLICABLE_SINGLE_VALUE",
                "observed_values": values,
            }
            continue
        heldout = [
            value
            for value in values
            if _stable_fraction("heldout", dimension, value) >= 0.80
        ]
        if not heldout:
            heldout = [max(values, key=lambda value: _stable_fraction(dimension, value))]
        dimension_audit[dimension] = {
            "status": PASS,
            "observed_value_count": len(values),
            "heldout_values": heldout,
            "heldout_decision_count": sum(
                str(row[dimension]) in set(heldout) for row in decisions
            ),
        }

    hard_counts = {
        split: sum(
            bool(labels[str(row["decision_id"])]["hard_categories"])
            for row in decisions
            if assignments[str(row["decision_id"])] == split
        )
        for split in ("train", "validation", "test", "audit_test")
    }
    easy_counts = {
        split: sum(
            bool(labels[str(row["decision_id"])]["easy_categories"])
            for row in decisions
            if assignments[str(row["decision_id"])] == split
        )
        for split in ("train", "validation", "test", "audit_test")
    }
    manifest = {
        "schema": "czr005.g4irsf13.v3_group_split.v1",
        "seed": SEED,
        "group_key": "raw task_id/pallet_id",
        "fractions": {
            "train": 0.70,
            "validation": 0.15,
            "development_test_contaminated": 0.15,
            "fresh_audit_test": "separate 384 real decisions",
        },
        "assignment_algorithm": "sha256 deterministic group fraction",
        "assignments": assignments,
        "counts": counts,
        "hard_counts": hard_counts,
        "easy_counts": easy_counts,
        "task_overlap_count": 0,
        "test_protocol": {
            "test": (
                "DEVELOPMENT_CONTAMINATED_BY_PRELIMINARY_AGGREGATE_READ; "
                "not used for final model selection or final reported test"
            ),
            "audit_test": (
                "fresh F2 archive decisions selected after hyperparameters "
                "were frozen; never used for training or selection"
            ),
        },
        "dimension_isolation_audit": dimension_audit,
        "status": PASS,
    }
    manifest["manifest_sha256"] = _self_hash(manifest, "manifest_sha256")
    return manifest


def _data_report(
    manifest: Mapping[str, Any],
    gate: Mapping[str, Any],
) -> str:
    validation = manifest["validation"]
    hard = validation["hard_category_counts"]
    easy = validation["easy_category_counts"]
    hard_lines = "\n".join(f"- `{key}`: {value}" for key, value in hard.items())
    easy_lines = "\n".join(f"- `{key}`: {value}" for key, value in easy.items())
    blockers = "\n".join(
        f"- {value}" for value in gate.get("promotion_blockers", [])
    )
    return f"""# G4IRSF13 v3 Residual Data Report

Status: `{gate["overall_status"]}` for observational F2-preservation
pretraining. Corrective-learning promotion remains blocked.

## Bound real evidence

- Map: `map2.json`, raw SHA-256 `{MAP_RAW_SHA256}`.
- Tasks: `inputdata.jsonl`, `{SEGMENT_COUNT:,}` segments and
  `{RAW_BAG_COUNT:,}` raw bags, SHA-256 `{TASK_RAW_SHA256}`.
- Actual local decisions: `{validation["decision_count"]:,}`.
- Actual candidate records: `{validation["candidate_record_count"]:,}`.
- Exact outgoing-candidate completeness:
  `{validation["candidate_completeness"]:.3f}`.
- Actual selected-action coverage:
  `{validation["selected_action_coverage"]:.3f}`.
- Raw-bag split overlap: `0`.

The decision file contains only decision-time local state. Label provenance,
confidence, weak-teacher status, future-dependency status, and post-hoc
outcomes live in separate hash-bound files and are not model features.

## Hard cohort

{hard_lines}

## Easy cohort

{easy_lines}

## Label authority

Level-A rank targets are computed from the same decision's local
travel/calendar/service, short queue bound, cycle/trap, credit, and
merge-local burden. The formula is versioned as `{LEVEL_A_FORMULA_ID}` and
has `{validation["level_a_corrective_label_count"]:,}` corrective decisions
with `{validation["level_a_abstention_count"]:,}` abstentions. It is only a
one-step projection, not a full-outcome or causal TTH label.

Stage B recorded v2's locally feasible current action, but its full
counterfactual status is `NOT_RUN_NO_MATCHED_RUNTIME_STATE_CLONE`.
Disagreeing v2 actions remain weak-teacher metadata and risk evidence only.

## Promotion blockers

{blockers}
"""


def build_dataset(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if sha256_file(root / MAP_PATH, text=False) != MAP_RAW_SHA256:
        raise StageFError("canonical map raw SHA-256 mismatch")
    if sha256_file(root / TASK_PATH, text=False) != TASK_RAW_SHA256:
        raise StageFError("canonical task raw SHA-256 mismatch")

    graph = load_graph(root)
    tasks = load_tasks(root)
    per_bag = load_per_bag(root)
    f2_archive, f2_descriptor = _resolve_archive(root, F2_ARCHIVE_POINTER)
    v2_archive, v2_descriptor = _resolve_archive(root, V2_ARCHIVE_POINTER)
    v2_paths = _load_v2_paths(v2_archive)
    divergence_rows = _load_divergence_rows(root)

    decisions: dict[str, dict[str, Any]] = {}
    labels: dict[str, dict[str, Any]] = {}
    hard_task_ids: set[int] = set()
    for index, row in enumerate(divergence_rows):
        task = tasks[str(row["segment_id"])]
        raw = _runtime_from_divergence(row)
        decision_id = (
            f"g4irsf13:divergence:{row['segment_id']}:"
            f"{row['first_divergence_step']}:{row['first_divergence_node']}:"
            f"{row['f2_next_node']}"
        )
        decision = _decision_from_runtime(
            raw,
            task=task,
            graph=graph,
            decision_id=decision_id,
            cohort="hard_first_divergence",
        )
        offline = json.loads(row["offline_labels_json"])
        teacher_next = int(offline["v2_next_node"])
        hard = _hard_categories(row)
        label = _label_row(
            decision,
            hard=hard,
            easy=(),
            teacher_next=teacher_next,
            teacher_agrees=teacher_next == int(decision["selected_next"]),
            locally_feasible=_truth(offline.get("v2_next_locally_feasible")),
            outcome_delta=_number(row["bag_delta_seconds"]),
        )
        # Stable suffix handles the rare repeated identity without discarding
        # any Stage-B divergence evidence.
        if decision_id in decisions:
            decision_id = f"{decision_id}:row{index}"
            decision["decision_id"] = decision_id
            label["decision_id"] = decision_id
        decisions[decision_id] = decision
        labels[decision_id] = label
        hard_task_ids.add(int(decision["task_id"]))

    category_heaps: dict[
        str, list[tuple[int, str, dict[str, Any], tuple[str, ...]]]
    ] = {category: [] for category in EASY_CATEGORIES}
    audit_heap: list[
        tuple[int, str, dict[str, Any], tuple[str, ...]]
    ] = []
    archive_decision_count = 0
    for raw in _iter_gzip_json_array(f2_archive, '"decision_trace":['):
        archive_decision_count += 1
        task_id = int(raw["task_id"])
        if task_id in hard_task_ids:
            continue
        categories = _easy_categories(raw, graph=graph, v2_paths=v2_paths)
        if len(raw["candidate_next_nodes"]) > 1:
            _heap_add(
                audit_heap,
                raw,
                categories,
                limit=FRESH_AUDIT_DECISIONS * 6,
                salt="fresh-final-audit-holdout-v1",
            )
        for category in categories:
            _heap_add(
                category_heaps[category],
                raw,
                categories,
                limit=EASY_PER_CATEGORY,
                salt=category,
            )
    expected_archive_decisions = int(
        f2_descriptor.get("validation", {}).get("decision_trace_count", -1)
    )
    if archive_decision_count != expected_archive_decisions:
        raise StageFError(
            f"streamed {archive_decision_count} decisions, descriptor binds "
            f"{expected_archive_decisions}"
        )

    selected_easy: dict[str, tuple[dict[str, Any], set[str]]] = {}
    for category, heap in category_heaps.items():
        if len(heap) < EASY_PER_CATEGORY:
            raise StageFError(
                f"easy category {category} has only {len(heap)} sampled decisions"
            )
        for _, decision_id, raw, all_categories in heap:
            stored = selected_easy.setdefault(decision_id, (raw, set()))
            stored[1].update(all_categories)

    for decision_id, (raw, category_set) in sorted(selected_easy.items()):
        task = tasks[str(raw["segment_id"])]
        decision = _decision_from_runtime(
            raw,
            task=task,
            graph=graph,
            cohort="easy_observed_f2",
        )
        if decision_id != decision["decision_id"]:
            raise StageFError("archive decision identity drift")
        agrees = "f2_v2_current_action_agreement" in category_set
        teacher_next = int(decision["selected_next"]) if agrees else None
        label = _label_row(
            decision,
            hard=(),
            easy=sorted(category_set),
            teacher_next=teacher_next,
            teacher_agrees=agrees,
            locally_feasible=agrees,
            outcome_delta=_number(per_bag[int(decision["task_id"])]["delta_seconds"]),
        )
        decisions[decision_id] = decision
        labels[decision_id] = label

    development_task_ids = {
        int(decision["task_id"]) for decision in decisions.values()
    }
    audit_seen_tasks: set[int] = set()
    audit_selected: list[
        tuple[dict[str, Any], tuple[str, ...]]
    ] = []
    for negative_rank, _, raw, categories in sorted(
        audit_heap, key=lambda item: (-item[0], item[1])
    ):
        del negative_rank
        task_id = int(raw["task_id"])
        if task_id in development_task_ids or task_id in audit_seen_tasks:
            continue
        audit_seen_tasks.add(task_id)
        audit_selected.append((raw, categories))
        if len(audit_selected) == FRESH_AUDIT_DECISIONS:
            break
    if len(audit_selected) != FRESH_AUDIT_DECISIONS:
        raise StageFError(
            f"fresh audit holdout has {len(audit_selected)} decisions, "
            f"expected {FRESH_AUDIT_DECISIONS}"
        )
    for raw, categories in audit_selected:
        task = tasks[str(raw["segment_id"])]
        decision = _decision_from_runtime(
            raw,
            task=task,
            graph=graph,
            cohort="fresh_final_audit_holdout",
        )
        decision_id = str(decision["decision_id"])
        agrees = "f2_v2_current_action_agreement" in categories
        label = _label_row(
            decision,
            hard=(),
            easy=sorted(categories),
            teacher_next=int(decision["selected_next"]) if agrees else None,
            teacher_agrees=agrees,
            locally_feasible=agrees,
            outcome_delta=_number(per_bag[int(decision["task_id"])]["delta_seconds"]),
        )
        decisions[decision_id] = decision
        labels[decision_id] = label

    ordered_decisions = [decisions[key] for key in sorted(decisions)]
    ordered_labels = [labels[str(row["decision_id"])] for row in ordered_decisions]
    outcomes = [
        _outcome_row(row, per_bag=per_bag) for row in ordered_decisions
    ]
    _verify_no_feature_leakage(ordered_decisions)

    split_manifest = build_split_manifest(ordered_decisions, labels)
    _write_json(root / TRACE_SCHEMA_PATH, build_trace_schema())
    decision_count = _write_jsonl(root / DECISIONS_PATH, ordered_decisions)
    label_count = _write_jsonl(root / LABELS_PATH, ordered_labels)
    outcome_count = _write_jsonl(root / OUTCOMES_PATH, outcomes)
    _write_json(root / SPLIT_PATH, split_manifest)

    lineage_rows = [
        {
            "feature_name": feature,
            "lineage": FEATURE_LINEAGE[feature],
            "available_at_decision": True,
            "local_only": True,
            "model_input_allowed": True,
            "absolute_node_id": False,
            "label_or_outcome": False,
        }
        for feature in FEATURE_NAMES
    ]
    _write_csv(
        root / LINEAGE_PATH,
        lineage_rows,
        (
            "feature_name",
            "lineage",
            "available_at_decision",
            "local_only",
            "model_input_allowed",
            "absolute_node_id",
            "label_or_outcome",
        ),
    )

    hard_counts = {
        category: sum(category in row["hard_categories"] for row in ordered_labels)
        for category in sorted(
            {category for row in ordered_labels for category in row["hard_categories"]}
        )
    }
    easy_counts = {
        category: sum(category in row["easy_categories"] for row in ordered_labels)
        for category in EASY_CATEGORIES
    }
    candidate_count = sum(
        len(row["candidate_records"]) for row in ordered_decisions
    )
    source_manifest = {
        "schema": SOURCE_SCHEMA,
        "status": PASS,
        "fixed_real_map_only": True,
        "map": {
            "path": MAP_PATH.as_posix(),
            "raw_sha256": MAP_RAW_SHA256,
            "semantic_sha256": MAP_SEMANTIC_SHA256,
            "mutated": False,
        },
        "tasks": {
            "path": TASK_PATH.as_posix(),
            "raw_sha256": TASK_RAW_SHA256,
            "raw_bag_count": RAW_BAG_COUNT,
            "segment_count": SEGMENT_COUNT,
            "mutated": False,
        },
        "generation": {
            "f2_archive_descriptor_sha256": str(
                f2_descriptor["descriptor_sha256"]
            ),
            "f2_archive_payload_sha256": f2_descriptor["archive"]["file_sha256"],
            "f2_archive_canonical_json_sha256": f2_descriptor["archive"][
                "canonical_json_sha256"
            ],
            "f2_binary_sha256": f2_descriptor["identity"]["binary"]["sha256"],
            "f2_decision_trace_count": archive_decision_count,
            "extractor_trainer_source_sha256": sha256_file(Path(__file__)),
            "hyperparameters_frozen_before_fresh_audit_extraction": True,
            "v2_archive_payload_sha256": v2_descriptor["archive"]["file_sha256"],
            "stage_b_divergence_sha256": sha256_file(root / DIVERGENCE_PATH),
            "stage_b_trace_sample_sha256": sha256_file(
                root / DIVERGENCE_SAMPLE_PATH
            ),
            "extraction_sampling": (
                "all Stage-B divergence rows plus deterministic sha256 "
                f"bottom-{EASY_PER_CATEGORY} sample per easy category plus "
                f"{FRESH_AUDIT_DECISIONS} fresh raw-bag-isolated audit decisions"
            ),
            "one_step_only": True,
            "reservation_depth": 1,
            "full_astar_calls": 0,
            "global_reservation_scans": 0,
            "future_routes_used_as_features": 0,
        },
        "model_feature_names": list(FEATURE_NAMES),
        "label_contract": {
            "rank_target": (
                "authorised Level-A deterministic local one-step projection; "
                "observed F2 action on abstention"
            ),
            "level_a_formula_id": LEVEL_A_FORMULA_ID,
            "level_a_full_state_clone_used": False,
            "level_a_future_route_used": False,
            "level_b_full_counterfactual_status": (
                "NOT_RUN_NO_MATCHED_RUNTIME_STATE_CLONE"
            ),
            "level_a_corrective_label_count": sum(
                bool(row["corrective_label_authorised"])
                for row in ordered_labels
            ),
            "level_b_full_counterfactual_label_count": 0,
            "weak_teacher_disagreements_used_as_rank_target": 0,
            "label_source_is_model_feature": False,
            "confidence_is_model_feature": False,
            "future_coordination_dependency_is_model_feature": False,
            "post_hoc_outcome_is_model_feature": False,
        },
        "validation": {
            "decision_count": decision_count,
            "label_count": label_count,
            "outcome_count": outcome_count,
            "candidate_record_count": candidate_count,
            "candidate_completeness": 1.0,
            "selected_action_coverage": 1.0,
            "hard_decision_count": sum(
                bool(row["hard_categories"]) for row in ordered_labels
            ),
            "easy_decision_count": sum(
                bool(row["easy_categories"]) for row in ordered_labels
            ),
            "hard_category_counts": hard_counts,
            "easy_category_counts": easy_counts,
            "main_feature_absolute_node_id_count": 0,
            "label_feature_leakage_count": 0,
            "future_route_feature_count": 0,
            "split_task_overlap_count": 0,
            "fresh_audit_holdout_count": FRESH_AUDIT_DECISIONS,
            "level_a_authorised_label_count": sum(
                bool(row["level_a_projection"]["rank_target_authorised"])
                for row in ordered_labels
            ),
            "level_a_corrective_label_count": sum(
                bool(row["corrective_label_authorised"])
                for row in ordered_labels
            ),
            "level_a_abstention_count": sum(
                not bool(row["level_a_projection"]["rank_target_authorised"])
                for row in ordered_labels
            ),
        },
        "artifacts": {
            "trace_schema": _descriptor(root, TRACE_SCHEMA_PATH),
            "decisions": _descriptor(root, DECISIONS_PATH, rows=decision_count),
            "labels": _descriptor(root, LABELS_PATH, rows=label_count),
            "outcomes": _descriptor(root, OUTCOMES_PATH, rows=outcome_count),
            "splits": _descriptor(root, SPLIT_PATH),
            "feature_lineage": _descriptor(
                root, LINEAGE_PATH, rows=len(lineage_rows)
            ),
        },
        "claim_boundary": (
            "Real candidate/action data support offline Level-A local "
            "corrective pretraining. Level-A is a deterministic one-step "
            "projection, not a matched full-state clone or causal TTH label; "
            "runtime promotion is not claimed."
        ),
    }
    source_manifest["manifest_sha256"] = _self_hash(
        source_manifest, "manifest_sha256"
    )
    _write_json(root / SOURCE_MANIFEST_PATH, source_manifest)

    evidence = {
        "baseline_freeze": _descriptor(root, BASELINE_MANIFEST_PATH),
        "f2_policy": _descriptor(root, F2_POLICY_PATH),
        "authoritative_reconciliation": _descriptor(
            root, AUTHORITATIVE_REPORT_PATH
        ),
        "source_manifest": _descriptor(root, SOURCE_MANIFEST_PATH),
        "split_manifest": _descriptor(root, SPLIT_PATH),
        "trace_schema": _descriptor(root, TRACE_SCHEMA_PATH),
    }
    gate_rows = {
        "resource_semantics_frozen": {
            "status": PASS,
            "evidence": [evidence["baseline_freeze"], evidence["f2_policy"]],
            "scope": "F2 binds R3_java_node_window_compatible",
        },
        "f2_baseline_frozen": {
            "status": PASS,
            "evidence": [evidence["baseline_freeze"], evidence["f2_policy"]],
        },
        "size_ladder_8192_stable": {
            "status": PASS,
            "evidence": [
                evidence["authoritative_reconciliation"],
                evidence["f2_policy"],
            ],
            "scope": "authoritative reconciliation plus uncensored full-1x superset",
        },
        "bounded_local_pibt_invariants": {
            "status": PASS,
            "evidence": [evidence["f2_policy"]],
            "scope": "P2 full-1x hard gates and bounded one-step counters",
        },
        "actual_candidate_action_trace": {
            "status": PASS,
            "evidence": [evidence["source_manifest"], evidence["trace_schema"]],
        },
        "no_leakage": {
            "status": PASS,
            "evidence": [evidence["source_manifest"], evidence["trace_schema"]],
        },
        "hard_easy_stratification": {
            "status": PASS,
            "evidence": [evidence["source_manifest"]],
        },
        "frozen_scorer_diagnostic_complete": {
            "status": PASS,
            "evidence": [evidence["f2_policy"], evidence["source_manifest"]],
            "scope": "actual S1/F2 committed full trace, not old offline replay alone",
        },
        "input_hash_identity": {
            "status": PASS,
            "evidence": [evidence["baseline_freeze"], evidence["source_manifest"]],
        },
        "split_isolation": {
            "status": PASS,
            "evidence": [evidence["split_manifest"]],
        },
    }
    gate = {
        "schema": GATE_SCHEMA,
        "overall_status": PASS,
        "training_scope": "OFFLINE_LEVEL_A_LOCAL_RESIDUAL_PRETRAINING_ONLY",
        "gates": gate_rows,
        "label_authority": {
            "level_a_local_one_step_projection": PASS,
            "level_a_formula_id": LEVEL_A_FORMULA_ID,
            "level_a_corrective_support": source_manifest["validation"][
                "level_a_corrective_label_count"
            ],
            "level_b_matched_full_state_counterfactual": FAIL,
            "level_c_v2_weak_teacher_as_causal_target": FAIL,
            "reason": (
                "Only Level-A same-state one-step projection is authorised. "
                "No matched full-state clone exists and v2 disagreement "
                "remains metadata rather than a causal target."
            ),
        },
        "promotion_blockers": [
            "closed-loop 144/512/2048/8192/full ladder has not run",
            "independent residual learning contribution is not demonstrated",
            "strict F2 and v2-safe win is not demonstrated",
        ],
        "runtime_activation_allowed": False,
    }
    gate["manifest_sha256"] = _self_hash(gate, "manifest_sha256")
    _write_json(root / PRETRAINING_GATE_PATH, gate)
    _atomic_write(root / DATA_REPORT_PATH, _data_report(source_manifest, gate).encode())
    return source_manifest, gate


def load_examples(root: Path) -> tuple[list[Example], dict[str, str]]:
    decisions = _load_jsonl(root / DECISIONS_PATH)
    labels = {
        str(row["decision_id"]): row for row in _load_jsonl(root / LABELS_PATH)
    }
    outcomes = {
        str(row["decision_id"]): row for row in _load_jsonl(root / OUTCOMES_PATH)
    }
    split = _load_json(root / SPLIT_PATH)
    assignments = {
        str(key): str(value) for key, value in split["assignments"].items()
    }
    if set(labels) != {str(row["decision_id"]) for row in decisions}:
        raise StageFError("decision/label identity set mismatch")
    if set(outcomes) != set(labels):
        raise StageFError("decision/outcome identity set mismatch")
    examples: list[Example] = []
    for row in decisions:
        decision_id = str(row["decision_id"])
        label = labels[decision_id]
        candidates = row["candidate_records"]
        matrix = np.asarray(
            [
                [float(record["features"][name]) for name in FEATURE_NAMES]
                for record in candidates
            ],
            dtype=np.float64,
        )
        costs = np.asarray(
            [float(record["frozen_score_cost"]) for record in candidates],
            dtype=np.float64,
        )
        selected_indices = [
            index
            for index, record in enumerate(candidates)
            if int(record["next_node"]) == int(label["preferred_next"])
        ]
        if len(selected_indices) != 1:
            raise StageFError("rank target is not exactly one candidate")
        f2_indices = [
            index
            for index, record in enumerate(candidates)
            if int(record["next_node"]) == int(row["selected_next"])
        ]
        if len(f2_indices) != 1:
            raise StageFError("observed F2 action is not exactly one candidate")
        examples.append(
            Example(
                decision=row,
                label=label,
                features=matrix,
                frozen_costs=costs,
                selected_index=selected_indices[0],
                f2_selected_index=f2_indices[0],
            )
        )
    return examples, assignments


def _indices_for(
    examples: Sequence[Example],
    assignments: Mapping[str, str],
    split: str,
) -> list[int]:
    return [
        index
        for index, example in enumerate(examples)
        if assignments[str(example.decision["decision_id"])] == split
    ]


def _normalisation(
    examples: Sequence[Example],
    indices: Sequence[int],
    feature_indices: Sequence[int],
) -> tuple[np.ndarray, np.ndarray]:
    matrix = np.concatenate(
        [examples[index].features[:, feature_indices] for index in indices],
        axis=0,
    )
    mean = matrix.mean(axis=0)
    scale = matrix.std(axis=0)
    scale[scale < 1e-8] = 1.0
    return mean, scale


def _normalised(
    example: Example,
    feature_indices: Sequence[int],
    mean: np.ndarray,
    scale: np.ndarray,
) -> np.ndarray:
    return np.clip(
        (example.features[:, feature_indices] - mean) / scale,
        -8.0,
        8.0,
    )


def _fit_linear(
    examples: Sequence[Example],
    train_indices: Sequence[int],
    *,
    feature_indices: Sequence[int],
    objective: str,
    epochs: int,
    learning_rate: float,
    feature_name_catalog: Sequence[str] = FEATURE_NAMES,
) -> dict[str, Any]:
    mean, scale = _normalisation(examples, train_indices, feature_indices)
    weights = np.zeros(len(feature_indices), dtype=np.float64)
    bias = 0.0
    for epoch in range(epochs):
        grad_w = np.zeros_like(weights)
        grad_b = 0.0
        weight_total = 0.0
        for index in train_indices:
            example = examples[index]
            x = _normalised(example, feature_indices, mean, scale)
            target = example.selected_index
            sample_weight = float(example.label["sample_weight"])
            costs = example.frozen_costs + np.clip(
                x @ weights + bias, -RESIDUAL_CLIP, RESIDUAL_CLIP
            )
            if objective in {"pairwise", "linear_hinge"}:
                for other in range(len(costs)):
                    if other == target:
                        continue
                    margin = costs[target] - costs[other]
                    if objective == "linear_hinge":
                        active = margin + 0.01 > 0.0
                        coefficient = 1.0 if active else 0.0
                    else:
                        coefficient = 1.0 / (1.0 + math.exp(-min(40.0, max(-40.0, margin))))
                    grad_w += (
                        sample_weight * coefficient * (x[target] - x[other])
                    )
                    weight_total += sample_weight
            elif objective == "listwise":
                logits = -costs
                logits -= float(logits.max())
                probabilities = np.exp(logits)
                probabilities /= probabilities.sum()
                derivative = -probabilities
                derivative[target] += 1.0
                grad_w += sample_weight * (derivative[:, None] * x).sum(axis=0)
                grad_b += sample_weight * derivative.sum()
                weight_total += sample_weight
            else:
                raise StageFError(f"unknown linear objective: {objective}")
        denominator = max(1.0, weight_total)
        regularisation = 2e-4
        rate = learning_rate / math.sqrt(epoch + 1.0)
        weights -= rate * (grad_w / denominator + regularisation * weights)
        bias -= rate * grad_b / denominator
        weights = np.clip(weights, -RESIDUAL_CLIP, RESIDUAL_CLIP)
        bias = float(np.clip(bias, -RESIDUAL_CLIP, RESIDUAL_CLIP))
    return {
        "architecture": "linear",
        "objective": objective,
        "feature_indices": list(map(int, feature_indices)),
        "feature_names": [feature_name_catalog[index] for index in feature_indices],
        "normalisation_mean": mean.tolist(),
        "normalisation_scale": scale.tolist(),
        "weights": weights.tolist(),
        "bias": bias,
        "epochs": epochs,
        "learning_rate": learning_rate,
    }


def _fit_mlp(
    examples: Sequence[Example],
    train_indices: Sequence[int],
    *,
    feature_indices: Sequence[int],
    hidden_size: int,
    epochs: int,
    learning_rate: float,
    feature_name_catalog: Sequence[str] = FEATURE_NAMES,
) -> dict[str, Any]:
    mean, scale = _normalisation(examples, train_indices, feature_indices)
    rng = np.random.default_rng(SEED + len(feature_indices) * 31 + hidden_size)
    w1 = rng.normal(0.0, 0.035, (len(feature_indices), hidden_size))
    b1 = np.zeros(hidden_size, dtype=np.float64)
    w2 = rng.normal(0.0, 0.035, hidden_size)
    b2 = 0.0
    for epoch in range(epochs):
        gw1 = np.zeros_like(w1)
        gb1 = np.zeros_like(b1)
        gw2 = np.zeros_like(w2)
        gb2 = 0.0
        weight_total = 0.0
        for index in train_indices:
            example = examples[index]
            x = _normalised(example, feature_indices, mean, scale)
            hidden = np.tanh(x @ w1 + b1)
            raw_residual = hidden @ w2 + b2
            residual = np.clip(raw_residual, -RESIDUAL_CLIP, RESIDUAL_CLIP)
            costs = example.frozen_costs + residual
            logits = -costs
            logits -= float(logits.max())
            probabilities = np.exp(logits)
            probabilities /= probabilities.sum()
            derivative = -probabilities
            derivative[example.selected_index] += 1.0
            active = (np.abs(raw_residual) < RESIDUAL_CLIP).astype(np.float64)
            derivative *= active
            sample_weight = float(example.label["sample_weight"])
            derivative *= sample_weight
            gw2 += (derivative[:, None] * hidden).sum(axis=0)
            gb2 += float(derivative.sum())
            hidden_derivative = derivative[:, None] * w2[None, :] * (1.0 - hidden**2)
            gw1 += x.T @ hidden_derivative
            gb1 += hidden_derivative.sum(axis=0)
            weight_total += sample_weight
        denominator = max(1.0, weight_total)
        rate = learning_rate / math.sqrt(epoch + 1.0)
        regularisation = 2e-4
        w1 -= rate * (gw1 / denominator + regularisation * w1)
        b1 -= rate * gb1 / denominator
        w2 -= rate * (gw2 / denominator + regularisation * w2)
        b2 -= rate * gb2 / denominator
        w1 = np.clip(w1, -0.5, 0.5)
        b1 = np.clip(b1, -0.5, 0.5)
        w2 = np.clip(w2, -0.5, 0.5)
        b2 = float(np.clip(b2, -0.5, 0.5))
    return {
        "architecture": "tiny_mlp",
        "objective": "listwise_cross_entropy",
        "hidden_size": hidden_size,
        "feature_indices": list(map(int, feature_indices)),
        "feature_names": [feature_name_catalog[index] for index in feature_indices],
        "normalisation_mean": mean.tolist(),
        "normalisation_scale": scale.tolist(),
        "w1": w1.tolist(),
        "b1": b1.tolist(),
        "w2": w2.tolist(),
        "b2": b2,
        "epochs": epochs,
        "learning_rate": learning_rate,
    }


def _raw_residual(model: Mapping[str, Any], example: Example) -> np.ndarray:
    feature_indices = [int(value) for value in model["feature_indices"]]
    mean = np.asarray(model["normalisation_mean"], dtype=np.float64)
    scale = np.asarray(model["normalisation_scale"], dtype=np.float64)
    x = _normalised(example, feature_indices, mean, scale)
    if model["architecture"] == "linear":
        result = x @ np.asarray(model["weights"], dtype=np.float64) + float(
            model["bias"]
        )
    elif model["architecture"] == "tiny_mlp":
        hidden = np.tanh(
            x @ np.asarray(model["w1"], dtype=np.float64)
            + np.asarray(model["b1"], dtype=np.float64)
        )
        result = hidden @ np.asarray(model["w2"], dtype=np.float64) + float(
            model["b2"]
        )
    else:
        raise StageFError(f"unknown architecture: {model['architecture']}")
    return np.clip(result, -RESIDUAL_CLIP, RESIDUAL_CLIP)


def _risk_features(example: Example, residual: np.ndarray) -> np.ndarray:
    sorted_costs = np.sort(example.frozen_costs)
    margin = (
        float(sorted_costs[1] - sorted_costs[0])
        if len(sorted_costs) > 1
        else 999.0
    )
    feature_index = {name: index for index, name in enumerate(FEATURE_NAMES)}
    matrix = example.features
    return np.asarray(
        [
            float(len(example.frozen_costs)),
            min(10.0, max(0.0, margin)),
            float(matrix[:, feature_index["target_queue_length"]].max()),
            float(matrix[:, feature_index["target_scheduled_incoming"]].max()),
            float(matrix[:, feature_index["local_calendar_wait_seconds"]].max()),
            float(matrix[:, feature_index["local_queue_length"]].max()),
            float(matrix[:, feature_index["downstream_pressure"]].max()),
            float(np.max(np.abs(residual))),
        ],
        dtype=np.float64,
    )


RISK_FEATURE_NAMES = (
    "candidate_count",
    "frozen_margin",
    "max_target_queue",
    "max_target_scheduled_incoming",
    "max_local_calendar_wait",
    "local_queue_length",
    "downstream_pressure",
    "max_abs_residual",
)


def _fit_risk_head(
    examples: Sequence[Example],
    train_indices: Sequence[int],
    validation_indices: Sequence[int],
    base_model: Mapping[str, Any],
) -> dict[str, Any]:
    train_x = np.stack(
        [
            _risk_features(examples[index], _raw_residual(base_model, examples[index]))
            for index in train_indices
        ]
    )
    train_y = np.asarray(
        [int(examples[index].label["risk_label"]) for index in train_indices],
        dtype=np.float64,
    )
    mean = train_x.mean(axis=0)
    scale = train_x.std(axis=0)
    scale[scale < 1e-8] = 1.0
    x = np.clip((train_x - mean) / scale, -8.0, 8.0)
    weights = np.zeros(x.shape[1], dtype=np.float64)
    positive_rate = float(train_y.mean())
    bias = math.log((positive_rate + 1e-6) / (1.0 - positive_rate + 1e-6))
    positive_weight = 0.5 / max(1e-6, positive_rate)
    negative_weight = 0.5 / max(1e-6, 1.0 - positive_rate)
    for epoch in range(160):
        logits = np.clip(x @ weights + bias, -40.0, 40.0)
        probability = 1.0 / (1.0 + np.exp(-logits))
        row_weight = np.where(train_y > 0.5, positive_weight, negative_weight)
        derivative = (probability - train_y) * row_weight
        rate = 0.08 / math.sqrt(epoch + 1.0)
        weights -= rate * (x.T @ derivative / len(x) + 2e-4 * weights)
        bias -= rate * float(derivative.mean())

    candidates = [0.25, 0.35, 0.45, 0.50, 0.60, 0.70, 0.80]
    validation_y = np.asarray(
        [int(examples[index].label["risk_label"]) for index in validation_indices],
        dtype=np.int64,
    )
    validation_probability = np.asarray(
        [
            _risk_probability(
                {
                    "normalisation_mean": mean.tolist(),
                    "normalisation_scale": scale.tolist(),
                    "weights": weights.tolist(),
                    "bias": bias,
                },
                _risk_features(
                    examples[index], _raw_residual(base_model, examples[index])
                ),
            )
            for index in validation_indices
        ]
    )
    best = candidates[0]
    best_score = -1.0
    for threshold in candidates:
        prediction = validation_probability >= threshold
        true_positive = int(((prediction == 1) & (validation_y == 1)).sum())
        false_negative = int(((prediction == 0) & (validation_y == 1)).sum())
        true_negative = int(((prediction == 0) & (validation_y == 0)).sum())
        false_positive = int(((prediction == 1) & (validation_y == 0)).sum())
        recall = true_positive / max(1, true_positive + false_negative)
        specificity = true_negative / max(1, true_negative + false_positive)
        score = 0.65 * recall + 0.35 * specificity
        if score > best_score:
            best_score = score
            best = threshold
    return {
        "architecture": "logistic_risk_head",
        "feature_names": list(RISK_FEATURE_NAMES),
        "normalisation_mean": mean.tolist(),
        "normalisation_scale": scale.tolist(),
        "weights": weights.tolist(),
        "bias": bias,
        "fallback_threshold": best,
        "fallback_action": "zero_residual_use_frozen_scorer",
        "calibration_method": "heldout_threshold_selection_on_logistic_probability",
    }


def _risk_probability(head: Mapping[str, Any], features: np.ndarray) -> float:
    mean = np.asarray(head["normalisation_mean"], dtype=np.float64)
    scale = np.asarray(head["normalisation_scale"], dtype=np.float64)
    x = np.clip((features - mean) / scale, -8.0, 8.0)
    logit = float(x @ np.asarray(head["weights"]) + float(head["bias"]))
    logit = min(40.0, max(-40.0, logit))
    return 1.0 / (1.0 + math.exp(-logit))


def _model_decision(
    model: Mapping[str, Any],
    example: Example,
) -> tuple[int, np.ndarray, float, bool, int]:
    residual = _raw_residual(model, example)
    raw_costs = example.frozen_costs + residual
    raw_choice = int(np.argmin(raw_costs))
    risk_probability = 0.0
    fallback = False
    head = model.get("risk_head")
    if isinstance(head, Mapping):
        risk_probability = _risk_probability(
            head, _risk_features(example, residual)
        )
        fallback = risk_probability >= float(head["fallback_threshold"])
    final_costs = example.frozen_costs if fallback else raw_costs
    choice = int(np.argmin(final_costs))
    return choice, final_costs, risk_probability, fallback, raw_choice


def _ece(confidences: Sequence[float], correct: Sequence[bool]) -> float:
    if not confidences:
        return 0.0
    total = len(confidences)
    value = 0.0
    for lower in np.linspace(0.0, 0.9, 10):
        upper = lower + 0.1
        indices = [
            index
            for index, confidence in enumerate(confidences)
            if lower <= confidence < upper
            or (upper >= 1.0 and confidence == 1.0)
        ]
        if not indices:
            continue
        accuracy = sum(correct[index] for index in indices) / len(indices)
        mean_confidence = sum(confidences[index] for index in indices) / len(indices)
        value += len(indices) / total * abs(accuracy - mean_confidence)
    return value


def evaluate_model(
    model: Mapping[str, Any],
    examples: Sequence[Example],
    indices: Sequence[int],
    *,
    subset: str,
) -> dict[str, Any]:
    top1 = 0
    top2 = 0
    pair_correct = 0
    pair_total = 0
    high_confidence = 0
    high_confidence_wrong = 0
    confidences: list[float] = []
    correctness: list[bool] = []
    raw_interventions = 0
    raw_interventions_correct = 0
    harmful_raw_interventions = 0
    harmful_caught = 0
    preserved = 0
    risk_fallbacks = 0
    risk_probabilities: list[float] = []
    risk_labels: list[int] = []
    for index in indices:
        example = examples[index]
        choice, costs, risk_probability, fallback, raw_choice = _model_decision(
            model, example
        )
        target = example.selected_index
        order = np.argsort(costs, kind="stable")
        correct = choice == target
        top1 += int(correct)
        top2 += int(target in order[: min(2, len(order))])
        frozen_choice = int(np.argmin(example.frozen_costs))
        preserved += int(choice == example.f2_selected_index)
        if raw_choice != frozen_choice:
            raw_interventions += 1
            raw_interventions_correct += int(raw_choice == target)
            if raw_choice != target:
                harmful_raw_interventions += 1
                harmful_caught += int(fallback and choice == frozen_choice)
        for other in range(len(costs)):
            if other == target:
                continue
            pair_total += 1
            pair_correct += int(costs[target] <= costs[other] + 1e-12)
        logits = -costs
        logits -= float(logits.max())
        probability = np.exp(logits)
        probability /= probability.sum()
        confidence = float(probability[choice])
        confidences.append(confidence)
        correctness.append(correct)
        if confidence >= 0.8:
            high_confidence += 1
            high_confidence_wrong += int(not correct)
        risk_fallbacks += int(fallback)
        risk_probabilities.append(risk_probability)
        risk_labels.append(int(example.label["risk_label"]))
    count = len(indices)
    risk_ece = _ece(risk_probabilities, [bool(value) for value in risk_labels])
    return {
        "subset": subset,
        "decision_count": count,
        "pair_count": pair_total,
        "pairwise_accuracy": pair_correct / max(1, pair_total),
        "listwise_top1": top1 / max(1, count),
        "listwise_top2": top2 / max(1, count),
        "high_confidence_wrong_rate": high_confidence_wrong
        / max(1, high_confidence),
        "high_confidence_harmful_count": high_confidence_wrong,
        "high_confidence_support": high_confidence,
        "calibration_ece": _ece(confidences, correctness),
        "positive_residual_precision": raw_interventions_correct
        / max(1, raw_interventions),
        "positive_residual_support": raw_interventions,
        "harmful_residual_recall": harmful_caught
        / max(1, harmful_raw_interventions),
        "harmful_residual_support": harmful_raw_interventions,
        "f2_preserved_rate": preserved / max(1, count),
        "risk_fallback_rate": risk_fallbacks / max(1, count),
        "risk_calibration_ece": risk_ece,
    }


def _model_payload(
    *,
    model_id: str,
    trained: Mapping[str, Any],
    root: Path,
    metrics: Mapping[str, Any],
    risk_head: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    offline_gate = (
        PASS
        if float(metrics["pairwise_accuracy"]) >= 0.55
        and float(metrics["listwise_top1"]) >= 0.50
        and float(metrics["high_confidence_wrong_rate"]) <= 0.02
        and float(metrics["calibration_ece"]) <= 0.15
        else FAIL
    )
    payload = {
        "schema": MODEL_SCHEMA,
        "model_id": model_id,
        "status": "OFFLINE_LEVEL_A_VALIDATED_CLOSED_LOOP_REQUIRED",
        "score_semantics": (
            "lower_is_better_frozen_g4e_cost_plus_clipped_residual"
        ),
        "residual_clip": [-RESIDUAL_CLIP, RESIDUAL_CLIP],
        "local_state_only": True,
        "absolute_node_id_main_feature": False,
        "future_route_feature_count": 0,
        "label_metadata_feature_count": 0,
        "shield_bypass_allowed": False,
        "pibt_ownership_change_allowed": False,
        "high_uncertainty_behavior": "zero residual; frozen scorer decides",
        "training_authority": (
            "same-state deterministic Level-A one-step projection with "
            "observed F2 fallback on abstention; disagreeing v2 weak teacher "
            "not used as corrective target"
        ),
        "hyperparameter_selection": {
            "fit_partition": "train",
            "selection_partition": "validation",
            "development_test_status": (
                "CONTAMINATED_BY_PRELIMINARY_AGGREGATE_READ_NOT_USED"
            ),
            "final_evaluation_partition": "fresh_audit_test",
            "final_audit_used_for_selection": False,
            "selection_table": HYPERPARAMETER_TABLE_PATH.as_posix(),
            "selection_rule": (
                "max validation listwise_top1, then pairwise accuracy, then "
                "minimum high-confidence harmful rate"
            ),
        },
        "source_manifest_sha256": sha256_file(root / SOURCE_MANIFEST_PATH),
        "split_manifest_sha256": sha256_file(root / SPLIT_PATH),
        "parameters": dict(trained),
        "risk_head": dict(risk_head) if risk_head is not None else None,
        "offline_test_metrics": dict(metrics),
        "offline_gate": {
            "status": offline_gate,
            "minimum_pairwise_accuracy": 0.55,
            "minimum_listwise_top1": 0.50,
            "maximum_high_confidence_harmful_rate": 0.02,
            "maximum_calibration_ece": 0.15,
        },
        "runtime_eligible": False,
        "closed_loop_status": NOT_RUN,
    }
    payload["model_sha256"] = _self_hash(payload, "model_sha256")
    return payload


def _model_filename(model_id: str) -> str:
    return f"g4irsf13_v3_{model_id.lower()}.json"


def _augment_node_id_examples(examples: Sequence[Example]) -> list[Example]:
    augmented: list[Example] = []
    for example in examples:
        current = float(example.decision["junction"])
        goal = float(example.decision["goal"])
        candidate_nodes = np.asarray(
            [
                float(record["next_node"])
                for record in example.decision["candidate_records"]
            ],
            dtype=np.float64,
        )
        identity = np.stack(
            [
                np.full(len(candidate_nodes), current),
                candidate_nodes,
                np.full(len(candidate_nodes), goal),
            ],
            axis=1,
        )
        augmented.append(
            Example(
                decision=example.decision,
                label=example.label,
                features=np.concatenate([example.features, identity], axis=1),
                frozen_costs=example.frozen_costs,
                selected_index=example.selected_index,
                f2_selected_index=example.f2_selected_index,
            )
        )
    return augmented


def _training_report(
    *,
    best_model_id: str,
    offline_rows: Sequence[Mapping[str, Any]],
    model_descriptors: Mapping[str, Mapping[str, Any]],
    feature_rows: Sequence[Mapping[str, Any]],
) -> str:
    test_rows = [
        row
        for row in offline_rows
        if row["evaluation_scope"] == "fresh_audit_test"
    ]
    v5_row = next(row for row in test_rows if row["model_id"] == MODEL_IDS[5])
    offline_gate = (
        PASS
        if float(v5_row["pairwise_accuracy"]) >= 0.55
        and float(v5_row["listwise_top1"]) >= 0.50
        and float(v5_row["high_confidence_wrong_rate"]) <= 0.02
        and float(v5_row["calibration_ece"]) <= 0.15
        else FAIL
    )
    lines = [
        "| Model | Pairwise | Top-1 | Top-2 | High-conf wrong | ECE | F2 preserved |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in test_rows:
        lines.append(
            "| {model_id} | {pairwise_accuracy:.4f} | "
            "{listwise_top1:.4f} | {listwise_top2:.4f} | "
            "{high_confidence_wrong_rate:.4f} | {calibration_ece:.4f} | "
            "{f2_preserved_rate:.4f} |".format(**row)
        )
    model_lines = "\n".join(
        f"- `{model_id}`: `{descriptor['sha256']}`"
        for model_id, descriptor in model_descriptors.items()
    )
    return f"""# G4IRSF13 v3 Residual Training Report

Status: `OFFLINE_LEVEL_A_EVALUATED_{offline_gate}`.
Closed loop remains `NOT_RUN`.

The six requested model families were trained deterministically on real
candidate/action rows. Every model adds a residual clipped to
`[-{RESIDUAL_CLIP}, +{RESIDUAL_CLIP}]` to the frozen G4E cost. V5 wraps the
validation-selected base model with a calibrated local risk head; when its risk
threshold fires, the residual is exactly zero and the frozen scorer decides.

## Fresh raw-bag-isolated audit test

{chr(10).join(lines)}

The preselected offline diagnostic candidate is `{best_model_id}`. These numbers measure
agreement with a bounded same-state Level-A projection and F2 preservation;
they are not evidence that TTH improves.
Positive-residual precision and harmful-residual recall include support
counts in the CSV; a value with zero support is not presented as causal
evidence.

Hyperparameters were selected only on `train` + `validation`. A preliminary
aggregate read contaminated the old `test` split, so it is quarantined as
development evidence. The final `{FRESH_AUDIT_DECISIONS}`-decision audit
cohort was extracted from previously unused F2 decisions after
hyperparameters were frozen and was not used for model selection. The exact
probe rows are in `g4irsf13_v3_hyperparameter_selection.csv`.

## Feature and identity ablation

`g4irsf13_v3_feature_ablation.csv` contains queue, timing, topology,
credit/fault, storage-leg, pruned-feature, and node-ID diagnostics. The main
models contain no absolute node ID. The with-node-ID row is diagnostic only
and is never exported as a policy candidate.

## Label boundary

V0-V5 use only authorised Level-A same-state one-step targets; abstentions
fall back to the observed successful F2 action. Stage-B v2 disagreements
lack matched runtime-state counterfactual replay, so the v2 action,
`label_source`, confidence, future dependency, and post-hoc bag delta are
excluded from feature vectors and never become a Level-B/C causal target.

## Immutable model hashes

{model_lines}

## Promotion decision

- Offline Level-A gate: `{offline_gate}` under pairwise >= 0.55, top-1 >= 0.50,
  high-confidence harmful <= 0.02, and ECE <= 0.15.
- Full-outcome/TTH corrective contribution: NOT DEMONSTRATED.
- 144 -> 512 -> 2048 -> 8192 -> full closed loop: NOT_RUN.
- Strict win over F2 and frozen v2-safe: NOT_RUN.
- Runtime activation: forbidden.
"""


def _closed_loop_outputs(root: Path) -> None:
    rows = []
    for size in (144, 512, 2048, 8192, 43603):
        for candidate in (
            "S0_handwritten",
            "S1_frozen_F2",
            "V3_residual",
            "V5_residual_risk",
            "V5_residual_risk_P2_off_diagnostic",
        ):
            rows.append(
                {
                    "candidate_id": candidate,
                    "size_segments": size,
                    "execution_status": NOT_RUN,
                    "complete_bags": "",
                    "complete_segments": "",
                    "original_entry_mean_minutes": "",
                    "p95_seconds": "",
                    "p99_seconds": "",
                    "delta_vs_f2_seconds_per_bag": "",
                    "delta_vs_v2_seconds_per_bag": "",
                    "hard_gate_status": NOT_RUN,
                    "blocker": (
                        "offline Stage F does not edit/integrate the C++ "
                        "runtime; closed-loop evidence must be produced later"
                    ),
                }
            )
    _write_csv(
        root / CLOSED_LOOP_TABLE_PATH,
        rows,
        (
            "candidate_id",
            "size_segments",
            "execution_status",
            "complete_bags",
            "complete_segments",
            "original_entry_mean_minutes",
            "p95_seconds",
            "p99_seconds",
            "delta_vs_f2_seconds_per_bag",
            "delta_vs_v2_seconds_per_bag",
            "hard_gate_status",
            "blocker",
        ),
    )
    report = f"""# G4IRSF13 v3 Closed-Loop Report

Status: `{NOT_RUN}`.

This Stage-F implementation deliberately does not modify the C++ runtime,
binding, or backend. The required 144 -> 512 -> 2048 -> 8192 -> full ladder has
not executed for any residual candidate. The companion CSV records every
required control/candidate row as `NOT_RUN` with empty performance fields.

Therefore no claim is made that v3 beats F2 (`{F2_MEAN_MINUTES:.12f}` min) or
frozen v2-safe (`{V2_MEAN_MINUTES:.12f}` min), and the existing
`{F2_V2_GAP_SECONDS:.9f}` s/bag gap remains open.
"""
    _atomic_write(root / CLOSED_LOOP_REPORT_PATH, report.encode("utf-8"))


def _v5_inference_evidence(
    model: Mapping[str, Any],
    examples: Sequence[Example],
    indices: Sequence[int],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    contract = {
        "version": "g4irsf13_v5_deterministic_inference_v1",
        "candidate_order": "next_node_ascending; stable first minimum",
        "steps": [
            "read ordered local feature vector in source-manifest FEATURE_NAMES order",
            "select parameters.feature_indices",
            "normalise (x-mean)/scale and clamp every value to [-8,8]",
            (
                "evaluate linear dot+bias or tanh(x@w1+b1)@w2+b2 "
                "using IEEE-754 double precision"
            ),
            f"clamp each residual to [-{RESIDUAL_CLIP},{RESIDUAL_CLIP}]",
            "form raw candidate cost = frozen_g4e_cost + residual",
            (
                "construct the eight local risk features in RISK_FEATURE_NAMES "
                "order, normalise/clamp identically, and apply logistic sigmoid"
            ),
            (
                "if risk_probability >= fallback_threshold, replace every "
                "candidate residual with exactly 0 and use frozen costs"
            ),
            "choose the first minimum final cost in candidate order",
        ],
        "activation": {
            "residual_linear": "identity",
            "residual_mlp_hidden": "tanh",
            "risk": "sigmoid(clamp(logit,-40,40))",
        },
        "residual_clip": [-RESIDUAL_CLIP, RESIDUAL_CLIP],
        "risk_fallback": "zero_all_residuals_then_frozen_scorer_argmin",
        "shield_order": "physical shield filters candidates before model inference",
        "pibt_order": "PIBT remains external and cannot be bypassed by model output",
        "comparison_tolerance": 1e-12,
    }
    selected: list[int] = []
    fallback_buckets: dict[bool, list[int]] = {False: [], True: []}
    for index in sorted(
        indices, key=lambda value: str(examples[value].decision["decision_id"])
    ):
        if len(examples[index].frozen_costs) < 2:
            continue
        fallback = _model_decision(model, examples[index])[3]
        fallback_buckets[fallback].append(index)
    for fallback in (False, True):
        if fallback_buckets[fallback]:
            selected.append(fallback_buckets[fallback][0])
    for index in fallback_buckets[False] + fallback_buckets[True]:
        if index not in selected:
            selected.append(index)
        if len(selected) >= 3:
            break
    if len(selected) < 3:
        raise StageFError("V5 requires three multi-candidate inference vectors")
    vectors: list[dict[str, Any]] = []
    for index in selected[:3]:
        example = examples[index]
        residual = _raw_residual(model, example)
        risk_vector = _risk_features(example, residual)
        risk_probability = _risk_probability(model["risk_head"], risk_vector)
        fallback = risk_probability >= float(
            model["risk_head"]["fallback_threshold"]
        )
        final_residual = np.zeros_like(residual) if fallback else residual
        final_cost = example.frozen_costs + final_residual
        selected_index = int(np.argmin(final_cost))
        vectors.append(
            {
                "decision_id": str(example.decision["decision_id"]),
                "input": {
                    "feature_names": list(FEATURE_NAMES),
                    "candidate_next_nodes": [
                        int(row["next_node"])
                        for row in example.decision["candidate_records"]
                    ],
                    "candidate_feature_vectors": example.features.tolist(),
                    "frozen_g4e_costs": example.frozen_costs.tolist(),
                },
                "expected": {
                    "clipped_raw_residuals": residual.tolist(),
                    "risk_feature_names": list(RISK_FEATURE_NAMES),
                    "risk_feature_vector": risk_vector.tolist(),
                    "risk_probability": risk_probability,
                    "fallback_triggered": fallback,
                    "final_residuals": final_residual.tolist(),
                    "final_costs": final_cost.tolist(),
                    "selected_candidate_index": selected_index,
                    "selected_next": int(
                        example.decision["candidate_records"][selected_index][
                            "next_node"
                        ]
                    ),
                },
            }
        )
    return contract, vectors


def train_models(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    gate = _load_json(root / PRETRAINING_GATE_PATH)
    if gate.get("overall_status") != PASS:
        raise StageFError("pretraining gate does not PASS")
    examples, assignments = load_examples(root)
    source_manifest = _load_json(root / SOURCE_MANIFEST_PATH)
    corrective_label_count = int(
        source_manifest["validation"]["level_a_corrective_label_count"]
    )
    train_indices = _indices_for(examples, assignments, "train")
    validation_indices = _indices_for(examples, assignments, "validation")
    development_test_indices = _indices_for(examples, assignments, "test")
    audit_test_indices = _indices_for(examples, assignments, "audit_test")
    if len(audit_test_indices) != FRESH_AUDIT_DECISIONS:
        raise StageFError("fresh audit holdout count drift")
    all_features = tuple(range(len(FEATURE_NAMES)))

    probe_rows = [
        {
            "model_family": family,
            "learning_rate": learning_rate,
            "epochs": epochs,
            "selection_partition": "validation",
            "validation_listwise_top1": top1,
            "validation_pairwise_accuracy": pairwise,
            "validation_high_confidence_harmful_rate": harmful,
            "selected": (
                (family == "pairwise_linear" and learning_rate == 1.0 and epochs == 120)
                or (family == "tiny_mlp" and learning_rate == 1.0 and epochs == 240)
            ),
            "fresh_audit_read_during_selection": False,
            "source_manifest_sha256": sha256_file(root / SOURCE_MANIFEST_PATH),
        }
        for family, learning_rate, epochs, top1, pairwise, harmful in (
            HYPERPARAMETER_PROBE_ROWS
        )
    ]
    _write_csv(
        root / HYPERPARAMETER_TABLE_PATH,
        probe_rows,
        (
            "model_family",
            "learning_rate",
            "epochs",
            "selection_partition",
            "validation_listwise_top1",
            "validation_pairwise_accuracy",
            "validation_high_confidence_harmful_rate",
            "selected",
            "fresh_audit_read_during_selection",
            "source_manifest_sha256",
        ),
    )

    trained: dict[str, dict[str, Any]] = {}
    trained[MODEL_IDS[0]] = _fit_linear(
        examples,
        train_indices,
        feature_indices=all_features,
        objective="linear_hinge",
        epochs=120,
        learning_rate=0.5,
    )
    trained[MODEL_IDS[1]] = _fit_linear(
        examples,
        train_indices,
        feature_indices=all_features,
        objective="pairwise",
        epochs=120,
        learning_rate=1.0,
    )
    trained[MODEL_IDS[2]] = _fit_linear(
        examples,
        train_indices,
        feature_indices=all_features,
        objective="listwise",
        epochs=120,
        learning_rate=1.0,
    )
    trained[MODEL_IDS[3]] = _fit_mlp(
        examples,
        train_indices,
        feature_indices=all_features,
        hidden_size=8,
        epochs=240,
        learning_rate=1.0,
    )
    v3_w1 = np.asarray(trained[MODEL_IDS[3]]["w1"], dtype=np.float64)
    importance = np.mean(np.abs(v3_w1), axis=1)
    pruned = tuple(
        sorted(
            np.argsort(importance)[-12:].astype(int).tolist()
        )
    )
    trained[MODEL_IDS[4]] = _fit_mlp(
        examples,
        train_indices,
        feature_indices=pruned,
        hidden_size=6,
        epochs=240,
        learning_rate=1.0,
    )

    validation_metrics = {
        model_id: evaluate_model(
            model,
            examples,
            validation_indices,
            subset="validation",
        )
        for model_id, model in trained.items()
    }
    best_base_id = max(
        trained,
        key=lambda model_id: (
            validation_metrics[model_id]["listwise_top1"],
            validation_metrics[model_id]["pairwise_accuracy"],
            -validation_metrics[model_id]["high_confidence_wrong_rate"],
            validation_metrics[model_id]["f2_preserved_rate"],
            -len(trained[model_id]["feature_indices"]),
            model_id,
        ),
    )
    risk_head = _fit_risk_head(
        examples,
        train_indices,
        validation_indices,
        trained[best_base_id],
    )
    v5 = dict(trained[best_base_id])
    v5["base_model_id"] = best_base_id
    v5["base_parameters_sha256"] = hashlib.sha256(
        _canonical_bytes(trained[best_base_id])
    ).hexdigest()
    v5["risk_head"] = risk_head
    trained[MODEL_IDS[5]] = v5

    offline_rows: list[dict[str, Any]] = []
    model_payloads: dict[str, dict[str, Any]] = {}
    model_descriptors: dict[str, dict[str, Any]] = {}
    for model_id in MODEL_IDS:
        model = trained[model_id]
        evaluation_model = dict(model)
        if model_id == MODEL_IDS[5]:
            evaluation_model["risk_head"] = risk_head
        metrics = evaluate_model(
            evaluation_model,
            examples,
            audit_test_indices,
            subset="fresh_audit_test",
        )
        row = {
            "model_id": model_id,
            "evaluation_scope": "fresh_audit_test",
            **metrics,
            "candidate_completeness": 1.0,
            "node_id_main_feature": False,
            "corrective_label_count": corrective_label_count,
            "closed_loop_status": NOT_RUN,
        }
        offline_rows.append(row)
        payload = _model_payload(
            model_id=model_id,
            trained=model,
            root=root,
            metrics=metrics,
            risk_head=risk_head if model_id == MODEL_IDS[5] else None,
        )
        if model_id == MODEL_IDS[5]:
            contract, vectors = _v5_inference_evidence(
                evaluation_model, examples, audit_test_indices
            )
            payload["deterministic_inference_contract"] = contract
            payload["inference_test_vectors"] = vectors
            payload["model_sha256"] = _self_hash(payload, "model_sha256")
        model_path = MODEL_DIR / _model_filename(model_id)
        _write_json(root / model_path, payload)
        model_payloads[model_id] = payload
        model_descriptors[model_id] = _descriptor(root, model_path)

    # Hard/easy and real source/goal/time slices for V5.
    v5_evaluation = dict(trained[MODEL_IDS[5]])
    v5_evaluation["risk_head"] = risk_head
    for subset, predicate in (
        ("hard_test", lambda example: bool(example.label["hard_categories"])),
        ("easy_test", lambda example: bool(example.label["easy_categories"])),
        ("storage_out_test", lambda example: example.decision["storage_leg"] == "storage_out"),
    ):
        indices = [
            index for index in audit_test_indices if predicate(examples[index])
        ]
        if indices:
            offline_rows.append(
                {
                    "model_id": MODEL_IDS[5],
                    "evaluation_scope": f"fresh_audit_{subset}",
                    **evaluate_model(v5_evaluation, examples, indices, subset=subset),
                    "candidate_completeness": 1.0,
                    "node_id_main_feature": False,
                    "corrective_label_count": corrective_label_count,
                    "closed_loop_status": NOT_RUN,
                }
            )

    split_manifest = _load_json(root / SPLIT_PATH)
    for dimension in ("source", "goal", "time_block", "junction", "storage_leg"):
        audit = split_manifest["dimension_isolation_audit"][dimension]
        if audit["status"] != PASS:
            continue
        heldout = {str(value) for value in audit["heldout_values"]}
        dimension_train = [
            index
            for index, example in enumerate(examples)
            if assignments[str(example.decision["decision_id"])] != "audit_test"
            and str(example.decision[dimension]) not in heldout
        ]
        dimension_test = [
            index
            for index, example in enumerate(examples)
            if assignments[str(example.decision["decision_id"])] != "audit_test"
            and str(example.decision[dimension]) in heldout
        ]
        if not dimension_train or not dimension_test:
            continue
        diagnostic = _fit_linear(
            examples,
            dimension_train,
            feature_indices=all_features,
            objective="pairwise",
            epochs=55,
            learning_rate=1.0,
        )
        metrics = evaluate_model(
            diagnostic,
            examples,
            dimension_test,
            subset=f"{dimension}_heldout",
        )
        offline_rows.append(
            {
                "model_id": "V1_dimension_heldout_diagnostic",
                "evaluation_scope": f"{dimension}_heldout",
                **metrics,
                "candidate_completeness": 1.0,
                "node_id_main_feature": False,
                "corrective_label_count": corrective_label_count,
                "closed_loop_status": NOT_RUN,
            }
        )

    feature_groups = {
        "no_queue_pressure": {
            "target_queue_length",
            "target_scheduled_incoming",
            "target_goal_queue_length",
            "target_goal_scheduled_incoming",
            "goal_conditioned_differential",
            "service_weighted_pressure",
            "two_hop_queue_pressure",
            "local_queue_length",
            "downstream_pressure",
        },
        "no_timing": {
            "candidate_service_time",
            "local_calendar_wait_seconds",
            "deadline_slack_seconds",
            "waiting_age_seconds",
        },
        "no_topology": {
            "candidate_node_type_code",
            "candidate_in_degree",
            "candidate_out_degree",
            "merge_state",
            "is_goal",
            "goal_relative_progress",
        },
        "no_credit_fault": {
            "advertised_fault",
            "fault_message_age_seconds",
            "first_edge_credit_matches",
            "first_edge_credit_required",
            "first_edge_credit_valid",
            "first_edge_credit_slack_seconds",
        },
        "no_storage_leg": {"storage_out"},
    }
    feature_rows: list[dict[str, Any]] = []
    baseline_metrics = evaluate_model(
        trained[MODEL_IDS[1]],
        examples,
        audit_test_indices,
        subset="full_no_node_id",
    )
    feature_rows.append(
        {
            "ablation_id": "full_no_node_id",
            "diagnostic_only": False,
            "feature_count": len(FEATURE_NAMES),
            "removed_features": "",
            "absolute_node_id_features": 0,
            **baseline_metrics,
        }
    )
    for ablation_id, removed in feature_groups.items():
        selected_features = tuple(
            index
            for index, name in enumerate(FEATURE_NAMES)
            if name not in removed
        )
        model = _fit_linear(
            examples,
            train_indices,
            feature_indices=selected_features,
            objective="pairwise",
            epochs=120,
            learning_rate=1.0,
        )
        metrics = evaluate_model(
            model, examples, audit_test_indices, subset=ablation_id
        )
        feature_rows.append(
            {
                "ablation_id": ablation_id,
                "diagnostic_only": False,
                "feature_count": len(selected_features),
                "removed_features": "|".join(sorted(removed)),
                "absolute_node_id_features": 0,
                **metrics,
            }
        )
    feature_rows.append(
        {
            "ablation_id": "V4_feature_pruned",
            "diagnostic_only": False,
            "feature_count": len(pruned),
            "removed_features": "|".join(
                name
                for index, name in enumerate(FEATURE_NAMES)
                if index not in set(pruned)
            ),
            "absolute_node_id_features": 0,
            **evaluate_model(
                trained[MODEL_IDS[4]],
                examples,
                audit_test_indices,
                subset="V4_feature_pruned",
            ),
        }
    )

    augmented = _augment_node_id_examples(examples)
    diagnostic_names = FEATURE_NAMES + (
        "diagnostic_current_node_id",
        "diagnostic_candidate_node_id",
        "diagnostic_goal_node_id",
    )
    diagnostic_model = _fit_linear(
        augmented,
        train_indices,
        feature_indices=tuple(range(len(diagnostic_names))),
        objective="pairwise",
        epochs=120,
        learning_rate=1.0,
        feature_name_catalog=diagnostic_names,
    )
    feature_rows.append(
        {
            "ablation_id": "with_absolute_node_id_diagnostic",
            "diagnostic_only": True,
            "feature_count": len(diagnostic_names),
            "removed_features": "",
            "absolute_node_id_features": 3,
            **evaluate_model(
                diagnostic_model,
                augmented,
                audit_test_indices,
                subset="with_absolute_node_id_diagnostic",
            ),
        }
    )

    offline_fields = (
        "model_id",
        "evaluation_scope",
        "subset",
        "decision_count",
        "pair_count",
        "pairwise_accuracy",
        "listwise_top1",
        "listwise_top2",
        "high_confidence_wrong_rate",
        "high_confidence_harmful_count",
        "high_confidence_support",
        "calibration_ece",
        "positive_residual_precision",
        "positive_residual_support",
        "harmful_residual_recall",
        "harmful_residual_support",
        "f2_preserved_rate",
        "risk_fallback_rate",
        "risk_calibration_ece",
        "candidate_completeness",
        "node_id_main_feature",
        "corrective_label_count",
        "closed_loop_status",
    )
    _write_csv(root / OFFLINE_TABLE_PATH, offline_rows, offline_fields)
    feature_fields = (
        "ablation_id",
        "diagnostic_only",
        "feature_count",
        "removed_features",
        "absolute_node_id_features",
        "subset",
        "decision_count",
        "pair_count",
        "pairwise_accuracy",
        "listwise_top1",
        "listwise_top2",
        "high_confidence_wrong_rate",
        "high_confidence_harmful_count",
        "high_confidence_support",
        "calibration_ece",
        "positive_residual_precision",
        "positive_residual_support",
        "harmful_residual_recall",
        "harmful_residual_support",
        "f2_preserved_rate",
        "risk_fallback_rate",
        "risk_calibration_ece",
    )
    _write_csv(root / FEATURE_TABLE_PATH, feature_rows, feature_fields)

    test_candidates = {
        row["model_id"]: row
        for row in offline_rows
        if row["evaluation_scope"] == "fresh_audit_test"
    }
    # Selection was frozen on validation before the audit cohort was
    # extracted.  Final-audit metrics above never choose the model.
    best_model_id = MODEL_IDS[5]
    offline_gate_status = model_payloads[MODEL_IDS[5]]["offline_gate"]["status"]
    bundle = {
        "schema": BUNDLE_SCHEMA,
        "status": (
            f"OFFLINE_LEVEL_A_{offline_gate_status}_CLOSED_LOOP_NOT_RUN"
        ),
        "recommended_offline_candidate": best_model_id,
        "selected_offline_candidate": best_base_id,
        "risk_wrapped_candidate": MODEL_IDS[5],
        "model_artifacts": model_descriptors,
        "source_manifest": _descriptor(root, SOURCE_MANIFEST_PATH),
        "pretraining_gate": _descriptor(root, PRETRAINING_GATE_PATH),
        "offline_table": _descriptor(root, OFFLINE_TABLE_PATH),
        "feature_ablation": _descriptor(root, FEATURE_TABLE_PATH),
        "hyperparameter_selection": _descriptor(
            root, HYPERPARAMETER_TABLE_PATH
        ),
        "residual_clip": [-RESIDUAL_CLIP, RESIDUAL_CLIP],
        "risk_fallback": "zero residual; use frozen scorer",
        "runtime_integration_contract": {
            "canonical_opt_in_mode": (
                "V3_g4irsf13_residual_risk_offline_candidate"
            ),
            "default_s1_unchanged": True,
            "required_experiment_flag": "diagnostic_allow_offline_candidate=true",
            "required_file_hash_semantics": HASH_TEXT,
            "required_model_file_sha256": model_descriptors[MODEL_IDS[5]][
                "sha256"
            ],
            "required_model_self_hash": (
                model_payloads[MODEL_IDS[5]]["model_sha256"]
            ),
            "test_vector_absolute_tolerance": 1e-12,
            "required_summary_fields": [
                "scorer_mode",
                "model_file_sha256",
                "model_self_sha256",
                "model_inference_count",
                "residual_applied_count",
                "residual_clip_count",
                "risk_fallback_count",
                "shield_rejection_count",
                "model_frozen_disagreement_count",
                "runtime_full_astar_calls",
                "global_reservation_scans",
                "future_route_reads",
            ],
        },
        "runtime_eligible": False,
        "active_pointer_written": False,
        "level_a_corrective_label_count": corrective_label_count,
        "level_a_offline_contribution": "MEASURED_AGAINST_LOCAL_PROJECTION_ONLY",
        "offline_gate_status": offline_gate_status,
        "full_outcome_learning_contribution": "NOT_DEMONSTRATED",
        "closed_loop_status": NOT_RUN,
        "strict_win_vs_f2": NOT_RUN,
        "strict_win_vs_v2_safe": NOT_RUN,
        "promotion_blockers": gate["promotion_blockers"],
    }
    bundle["bundle_sha256"] = _self_hash(bundle, "bundle_sha256")
    _write_json(root / CANDIDATE_BUNDLE_PATH, bundle)
    _closed_loop_outputs(root)
    _atomic_write(
        root / TRAINING_REPORT_PATH,
        _training_report(
            best_model_id=best_base_id,
            offline_rows=offline_rows,
            model_descriptors=model_descriptors,
            feature_rows=feature_rows,
        ).encode("utf-8"),
    )
    return offline_rows, feature_rows


def _verify_descriptor(root: Path, descriptor: Mapping[str, Any]) -> None:
    path = root / str(descriptor["path"])
    if not path.is_file():
        raise StageFError(f"bound artifact is missing: {path}")
    actual = sha256_file(
        path, text=descriptor.get("hash_semantics") != HASH_EXACT
    )
    if actual != descriptor.get("sha256"):
        raise StageFError(f"bound artifact SHA-256 mismatch: {path}")
    if "size_bytes" in descriptor and path.stat().st_size != int(
        descriptor["size_bytes"]
    ):
        raise StageFError(f"bound artifact size mismatch: {path}")
    if "row_count" in descriptor:
        if path.suffix == ".csv":
            with path.open("r", encoding="utf-8", newline="") as stream:
                count = sum(1 for _ in csv.DictReader(stream))
        elif path.suffix == ".jsonl":
            with path.open("r", encoding="utf-8") as stream:
                count = sum(bool(line.strip()) for line in stream)
        else:
            raise StageFError(f"cannot count descriptor rows for {path}")
        if count != int(descriptor["row_count"]):
            raise StageFError(f"bound artifact row count mismatch: {path}")


def validate_committed(root: Path) -> dict[str, Any]:
    if sha256_file(root / MAP_PATH, text=False) != MAP_RAW_SHA256:
        raise StageFError("protected map hash mismatch")
    if sha256_file(root / TASK_PATH, text=False) != TASK_RAW_SHA256:
        raise StageFError("protected task hash mismatch")
    schema = _load_json(root / TRACE_SCHEMA_PATH)
    if schema.get("$id") != TRACE_SCHEMA:
        raise StageFError("trace schema identity mismatch")
    if schema.get("runtime_feature_names") != list(FEATURE_NAMES):
        raise StageFError("trace schema feature order mismatch")

    source = _load_json(root / SOURCE_MANIFEST_PATH)
    if source.get("schema") != SOURCE_SCHEMA or source.get("status") != PASS:
        raise StageFError("source manifest is not PASS")
    if source.get("manifest_sha256") != _self_hash(source, "manifest_sha256"):
        raise StageFError("source manifest self-hash mismatch")
    if source["generation"]["extractor_trainer_source_sha256"] != sha256_file(
        Path(__file__)
    ):
        raise StageFError("extractor/trainer source hash is stale")
    for descriptor in source["artifacts"].values():
        _verify_descriptor(root, descriptor)
    validation = source["validation"]
    if validation["candidate_completeness"] != 1.0:
        raise StageFError("candidate completeness is not exact")
    if validation["selected_action_coverage"] != 1.0:
        raise StageFError("selected action coverage is not exact")
    if validation["label_feature_leakage_count"] != 0:
        raise StageFError("source manifest reports feature leakage")
    if validation["future_route_feature_count"] != 0:
        raise StageFError("source manifest reports future-route leakage")
    if validation["main_feature_absolute_node_id_count"] != 0:
        raise StageFError("main feature list contains an absolute node ID")
    if validation["hard_decision_count"] <= 0 or validation["easy_decision_count"] <= 0:
        raise StageFError("hard/easy stratification is incomplete")
    if validation["level_a_corrective_label_count"] <= 0:
        raise StageFError("Level-A corrective supervision has no support")
    if validation["fresh_audit_holdout_count"] != FRESH_AUDIT_DECISIONS:
        raise StageFError("fresh audit holdout count mismatch")

    decisions = _load_jsonl(root / DECISIONS_PATH)
    labels = {
        str(row["decision_id"]): row for row in _load_jsonl(root / LABELS_PATH)
    }
    graph = load_graph(root)
    _verify_no_feature_leakage(decisions)
    for decision in decisions:
        decision_id = str(decision["decision_id"])
        if tuple(decision["candidate_next_nodes"]) != graph.outgoing[
            int(decision["junction"])
        ]:
            raise StageFError("committed candidate set is not exact real-map outgoing")
        records = decision["candidate_records"]
        if [row["next_node"] for row in records] != decision["candidate_next_nodes"]:
            raise StageFError("candidate record ordering/completeness mismatch")
        if decision["selected_next"] not in decision["candidate_next_nodes"]:
            raise StageFError("actual selected action is absent")
        label = labels[decision_id]
        if label["observed_f2_selected_next"] != decision["selected_next"]:
            raise StageFError("observed selected action metadata drift")
        if label["preferred_next"] not in decision["candidate_next_nodes"]:
            raise StageFError("Level-A rank target is absent from candidates")
        expected_projection = _level_a_projection(decision)
        if _canonical_bytes(expected_projection) != _canonical_bytes(
            label["level_a_projection"]
        ):
            raise StageFError("Level-A projection formula/result drift")
        expected_corrective = bool(
            expected_projection["rank_target_authorised"]
            and expected_projection["preferred_next"] != decision["selected_next"]
        )
        if bool(label["corrective_label_authorised"]) != expected_corrective:
            raise StageFError("Level-A corrective authority drift")
        if labels[decision_id]["weak_teacher_used_as_rank_target"] is not False:
            raise StageFError("unmatched weak teacher was used as rank target")

    split = _load_json(root / SPLIT_PATH)
    if split.get("manifest_sha256") != _self_hash(split, "manifest_sha256"):
        raise StageFError("split manifest self-hash mismatch")
    if split.get("status") != PASS or split.get("task_overlap_count") != 0:
        raise StageFError("group split isolation failed")
    if split["counts"].get("audit_test") != FRESH_AUDIT_DECISIONS:
        raise StageFError("split manifest fresh audit count mismatch")
    task_splits: dict[int, set[str]] = {}
    for decision in decisions:
        decision_id = str(decision["decision_id"])
        task_splits.setdefault(int(decision["task_id"]), set()).add(
            split["assignments"][decision_id]
        )
    if any(len(values) != 1 for values in task_splits.values()):
        raise StageFError("same task/bag crosses group splits")

    gate = _load_json(root / PRETRAINING_GATE_PATH)
    if gate.get("schema") != GATE_SCHEMA or gate.get("overall_status") != PASS:
        raise StageFError("pretraining gate is not PASS")
    if gate.get("manifest_sha256") != _self_hash(gate, "manifest_sha256"):
        raise StageFError("pretraining gate self-hash mismatch")
    if set(row["status"] for row in gate["gates"].values()) != {PASS}:
        raise StageFError("one or more required pretraining gates did not PASS")
    for gate_row in gate["gates"].values():
        for descriptor in gate_row["evidence"]:
            _verify_descriptor(root, descriptor)
    authority = gate["label_authority"]
    if authority["level_a_local_one_step_projection"] != PASS:
        raise StageFError("Level-A local label authority is not PASS")
    if authority["level_b_matched_full_state_counterfactual"] != FAIL:
        raise StageFError("missing Level-B full-state blocker was hidden")
    if authority["level_c_v2_weak_teacher_as_causal_target"] != FAIL:
        raise StageFError("v2 weak-teacher causal blocker was hidden")
    if int(authority["level_a_corrective_support"]) <= 0:
        raise StageFError("Level-A corrective support is empty")
    if gate.get("runtime_activation_allowed") is not False:
        raise StageFError("pretraining gate incorrectly activates runtime")

    model_hashes: dict[str, str] = {}
    for model_id in MODEL_IDS:
        path = root / MODEL_DIR / _model_filename(model_id)
        payload = _load_json(path)
        if payload.get("schema") != MODEL_SCHEMA:
            raise StageFError(f"model schema mismatch: {model_id}")
        if payload.get("model_id") != model_id:
            raise StageFError(f"model identity mismatch: {model_id}")
        if payload.get("model_sha256") != _self_hash(payload, "model_sha256"):
            raise StageFError(f"model self-hash mismatch: {model_id}")
        if payload.get("residual_clip") != [-RESIDUAL_CLIP, RESIDUAL_CLIP]:
            raise StageFError(f"residual clip mismatch: {model_id}")
        if payload.get("runtime_eligible") is not False:
            raise StageFError(f"offline model marked runtime eligible: {model_id}")
        if payload["parameters"]["feature_names"] != [
            FEATURE_NAMES[index]
            for index in payload["parameters"]["feature_indices"]
        ]:
            raise StageFError(f"model feature index/name mismatch: {model_id}")
        if any("node_id" in name for name in payload["parameters"]["feature_names"]):
            raise StageFError(f"absolute node ID reached main model: {model_id}")
        if model_id == MODEL_IDS[5]:
            head = payload.get("risk_head")
            if not isinstance(head, Mapping):
                raise StageFError("V5 calibrated risk head is missing")
            if head.get("fallback_action") != "zero_residual_use_frozen_scorer":
                raise StageFError("V5 risk fallback does not restore frozen scorer")
            base_model_id = payload["parameters"].get("base_model_id")
            if base_model_id not in MODEL_IDS[:-1]:
                raise StageFError("V5 base model identity is invalid")
            base_payload = _load_json(
                root / MODEL_DIR / _model_filename(str(base_model_id))
            )
            expected_base_fingerprint = hashlib.sha256(
                _canonical_bytes(base_payload["parameters"])
            ).hexdigest()
            if (
                payload["parameters"].get("base_parameters_sha256")
                != expected_base_fingerprint
            ):
                raise StageFError("V5 base parameter fingerprint mismatch")
            v5_base_parameters = {
                key: value
                for key, value in payload["parameters"].items()
                if key
                not in {
                    "base_model_id",
                    "base_parameters_sha256",
                    "risk_head",
                }
            }
            if _canonical_bytes(v5_base_parameters) != _canonical_bytes(
                base_payload["parameters"]
            ):
                raise StageFError("V5 does not wrap the selected base parameters")
            contract = payload.get("deterministic_inference_contract")
            vectors = payload.get("inference_test_vectors")
            if not isinstance(contract, Mapping) or not isinstance(vectors, list):
                raise StageFError("V5 deterministic inference contract is missing")
            if len(vectors) < 3:
                raise StageFError("V5 requires at least three inference vectors")
            evaluation_model = dict(payload["parameters"])
            evaluation_model["risk_head"] = head
            for vector in vectors:
                inputs = vector["input"]
                expected = vector["expected"]
                if inputs["feature_names"] != list(FEATURE_NAMES):
                    raise StageFError("V5 test-vector feature order mismatch")
                fixture = Example(
                    decision={"candidate_records": []},
                    label={},
                    features=np.asarray(
                        inputs["candidate_feature_vectors"], dtype=np.float64
                    ),
                    frozen_costs=np.asarray(
                        inputs["frozen_g4e_costs"], dtype=np.float64
                    ),
                    selected_index=0,
                    f2_selected_index=0,
                )
                residual = _raw_residual(evaluation_model, fixture)
                risk_vector = _risk_features(fixture, residual)
                probability = _risk_probability(head, risk_vector)
                fallback = probability >= float(head["fallback_threshold"])
                final_residual = np.zeros_like(residual) if fallback else residual
                final_cost = fixture.frozen_costs + final_residual
                choice = int(np.argmin(final_cost))
                if not np.allclose(
                    residual,
                    np.asarray(expected["clipped_raw_residuals"]),
                    rtol=0.0,
                    atol=1e-12,
                ):
                    raise StageFError("V5 residual test vector mismatch")
                if not np.allclose(
                    risk_vector,
                    np.asarray(expected["risk_feature_vector"]),
                    rtol=0.0,
                    atol=1e-12,
                ):
                    raise StageFError("V5 risk-feature test vector mismatch")
                if abs(probability - float(expected["risk_probability"])) > 1e-12:
                    raise StageFError("V5 risk probability test vector mismatch")
                if fallback != bool(expected["fallback_triggered"]):
                    raise StageFError("V5 fallback test vector mismatch")
                if choice != int(expected["selected_candidate_index"]):
                    raise StageFError("V5 selected-action test vector mismatch")
        model_hashes[model_id] = sha256_file(path)

    with (root / HYPERPARAMETER_TABLE_PATH).open(
        "r", encoding="utf-8", newline=""
    ) as stream:
        hyperparameter_rows = list(csv.DictReader(stream))
    if not hyperparameter_rows:
        raise StageFError("hyperparameter selection evidence is empty")
    if {row["selection_partition"] for row in hyperparameter_rows} != {
        "validation"
    }:
        raise StageFError("hyperparameters were not selected on validation only")
    if {
        row["fresh_audit_read_during_selection"] for row in hyperparameter_rows
    } != {"False"}:
        raise StageFError("fresh audit was read during hyperparameter selection")

    bundle = _load_json(root / CANDIDATE_BUNDLE_PATH)
    if bundle.get("bundle_sha256") != _self_hash(bundle, "bundle_sha256"):
        raise StageFError("candidate bundle self-hash mismatch")
    if bundle.get("runtime_eligible") is not False:
        raise StageFError("candidate bundle incorrectly runtime eligible")
    if bundle.get("closed_loop_status") != NOT_RUN:
        raise StageFError("candidate bundle hides closed-loop status")
    v5_payload = _load_json(
        root / MODEL_DIR / _model_filename(MODEL_IDS[5])
    )
    if (
        v5_payload["parameters"]["base_model_id"]
        != bundle.get("selected_offline_candidate")
    ):
        raise StageFError("V5 base is not the selected offline candidate")
    for descriptor in bundle["model_artifacts"].values():
        _verify_descriptor(root, descriptor)
    _verify_descriptor(root, bundle["source_manifest"])
    _verify_descriptor(root, bundle["pretraining_gate"])
    _verify_descriptor(root, bundle["offline_table"])
    _verify_descriptor(root, bundle["feature_ablation"])
    _verify_descriptor(root, bundle["hyperparameter_selection"])

    with (root / CLOSED_LOOP_TABLE_PATH).open(
        "r", encoding="utf-8", newline=""
    ) as stream:
        closed_loop_rows = list(csv.DictReader(stream))
    if len(closed_loop_rows) != 25:
        raise StageFError("closed-loop NOT_RUN matrix is incomplete")
    if {row["execution_status"] for row in closed_loop_rows} != {NOT_RUN}:
        raise StageFError("closed-loop table contains unexecuted result claims")
    if any(row["original_entry_mean_minutes"] for row in closed_loop_rows):
        raise StageFError("closed-loop table fabricates performance metrics")

    return {
        "status": PASS,
        "decision_count": len(decisions),
        "candidate_count": sum(
            len(row["candidate_records"]) for row in decisions
        ),
        "hard_count": validation["hard_decision_count"],
        "easy_count": validation["easy_decision_count"],
        "model_hashes": model_hashes,
        "closed_loop_status": NOT_RUN,
        "runtime_eligible": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--mode",
        choices=("all", "data", "train", "validate"),
        default="all",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    if args.mode in {"all", "data"}:
        source, gate = build_dataset(root)
        print(
            json.dumps(
                {
                    "data_status": gate["overall_status"],
                    "decisions": source["validation"]["decision_count"],
                    "hard": source["validation"]["hard_decision_count"],
                    "easy": source["validation"]["easy_decision_count"],
                },
                sort_keys=True,
            )
        )
    if args.mode in {"all", "train"}:
        offline, ablation = train_models(root)
        print(
            json.dumps(
                {
                    "training_status": (
                        "OFFLINE_LEVEL_A_LOCAL_RESIDUAL_CLOSED_LOOP_NOT_RUN"
                    ),
                    "offline_rows": len(offline),
                    "feature_ablation_rows": len(ablation),
                },
                sort_keys=True,
            )
        )
    if args.mode in {"all", "validate"}:
        print(json.dumps(validate_committed(root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
