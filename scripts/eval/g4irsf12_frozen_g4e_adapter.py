"""G4IRSF12-E frozen-G4E legal-local event adapter.

This module is intentionally a Python strategy/evidence layer.  It does not
modify the event runtime and it does not turn a recorded decision trace into a
counterfactual closed-loop A/B.  The only executable diagnostic here is a
strict same-observation replay over the committed G4IRSF11 decision trace.

The adapter fails closed on model/map/trace identity, preserves the frozen G4E
MLP weights, and gives every one of the 22 legacy inputs an explicit lineage.
Legacy fields that cannot be reconstructed with equivalent decision-time
semantics are set to a declared zero default rather than approximated.
"""

from __future__ import annotations

import argparse
from collections import deque
import csv
from dataclasses import dataclass
import hashlib
import io
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for _path in (ROOT, SRC):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from czr005.datasets.decision_trace import (  # noqa: E402
    EVENT_RUNTIME_FEATURE_SOURCES,
    assert_no_future_or_label_leakage,
    validate_decision_rows,
)


PHASE_DATE = "2026-07-23"
ADAPTER_SCHEMA = "czr005.g4irsf12.frozen_g4e_event_diagnostic.v1"
DIAGNOSTIC_SCOPE = "strict_same_observation_offline_replay"
CLAIM_STATUS = "OOD_DIAGNOSTIC_ONLY_NOT_CLOSED_LOOP"

MODEL_PATH = Path("artifacts/models/g4e_risk_calibrated_policy.json")
MODEL_RAW_SHA256 = "4a058dee0bdd17e15f67d1943a551822847d0c066ac3cf03a5da71a07731bbca"
MAP_PATH = Path("data/processed/maps/map2.json")
MAP_RAW_SHA256 = "9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4"
MAP_SEMANTIC_SHA256 = "67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63"
TRACE_PATH = Path("artifacts/datasets/g4irsf11_decision_trace_sample.jsonl")
TRACE_RAW_SHA256 = "bc22ae4d618eb193c3a7342eba04315a85d5940833ba91df95a3b90da432ca4f"
TRACE_EXPECTED_ROWS = 9_397

REPORT_PATH = Path("outputs/reports/g4irsf12_frozen_scorer_event_adapter.md")
ISOLATION_TABLE_PATH = Path("outputs/tables/g4irsf12_scorer_isolation_ab.csv")
LINEAGE_TABLE_PATH = Path("outputs/tables/g4irsf12_feature_lineage_event_adapter.csv")
BUNDLE_PATH = Path("artifacts/policies/g4irsf12_frozen_g4e_event_diagnostic.json")

FEATURE_NAMES = (
    "candidate_shortest_time_to_goal_scaled",
    "candidate_travel_time_scaled",
    "candidate_service_time_scaled",
    "candidate_node_type_scaled",
    "candidate_faulted",
    "candidate_is_goal",
    "time_slack_scaled",
    "current_node_scaled",
    "goal_node_scaled",
    "out_degree_scaled",
    "is_branch_node",
    "local_node_pressure_scaled",
    "candidate_node_pressure_scaled",
    "candidate_downstream_node_pressure_2hop_scaled",
    "candidate_downstream_node_pressure_3hop_scaled",
    "candidate_static_remaining_hops_to_goal_scaled",
    "candidate_static_second_best_gap_scaled",
    "candidate_bottleneck_score_scaled",
    "candidate_goal_direction_score_scaled",
    "candidate_historical_risk_from_training_only_scaled",
    "source_retry_pressure_scaled",
    "unfinished_task_queue_size_near_current_source_scaled",
)

SCORER_IDS = (
    "S0_current_handwritten_static_score",
    "S1_frozen_g4e_legal_local_adapter",
    "S2_frozen_g4e_without_absolute_node_ids",
    "S3_shortest_potential_only",
    "S4_queue_aware_rule_only",
)

# A canonical row contains diagnostics and outputs that are not model inputs,
# but accepting arbitrary extra top-level keys would make the projection fail
# open.  Metadata remains diagnostic-only and is never passed to a scorer.
CANONICAL_TRACE_TOP_LEVEL = frozenset(
    {
        "schema_id",
        "schema_version",
        "decision_id",
        "task_id",
        "segment_id",
        "event_time",
        "current_node",
        "goal_node",
        "candidate_next_nodes",
        "candidate_records",
        "model_prediction",
        "model_score_semantics",
        "model_margin",
        "risk_gate_triggered",
        "fallback_selected_next",
        "selected_next",
        "decision_source",
        "rule_reason",
        "local_snapshot",
        "short_history",
        "full_astar_used",
        "model_fallback_disagreement",
        "candidate_ordering",
        "candidate_order_digest",
        "metadata",
    }
)

LINEAGE_COLUMNS = (
    "feature_index",
    "feature_name",
    "training_semantics",
    "training_source",
    "s1_adapter_source",
    "s1_resolution",
    "s1_default_value",
    "s2_adapter_source",
    "s2_resolution",
    "s2_default_value",
    "scale_denominator",
    "runtime_availability",
    "consumed_model_input",
    "ood_note",
)

ISOLATION_COLUMNS = (
    "scorer_id",
    "evaluation_scope",
    "status",
    "closed_loop_run",
    "trace_decision_count",
    "candidate_score_count",
    "score_direction",
    "margin_semantics",
    "agreement_with_recorded_model_prediction_count",
    "agreement_with_recorded_model_prediction_rate",
    "agreement_with_recorded_selected_action_count",
    "agreement_with_recorded_selected_action_rate",
    "predicted_candidate_shield_allowed_count",
    "predicted_candidate_shield_allowed_rate",
    "risk_abstain_count",
    "risk_abstain_rate",
    "mean_margin",
    "completion_rate",
    "original_entry_time_tth",
    "claim_boundary",
)


@dataclass(frozen=True)
class MapContext:
    nodes: Mapping[int, Mapping[str, Any]]
    adjacency: Mapping[int, tuple[int, ...]]
    edge_travel_time: Mapping[tuple[int, int], float]
    heuristic_time: tuple[tuple[float, ...], ...]
    hop_distance: Mapping[tuple[int, int], int]
    raw_sha256: str
    semantic_sha256: str


@dataclass(frozen=True)
class FrozenG4EModel:
    w1: tuple[tuple[float, ...], ...]
    b1: tuple[float, ...]
    w2: tuple[float, ...]
    b2: float
    risk_margin_threshold: float
    risk_historical_threshold: float
    risk_bottleneck_threshold: float
    raw_sha256: str
    learned_rule_count: int
    selected_candidate: str

    def scores(self, rows: Sequence[Sequence[float]]) -> tuple[float, ...]:
        output: list[float] = []
        for row in rows:
            if len(row) != len(FEATURE_NAMES):
                raise ValueError(
                    f"G4E row has {len(row)} features; expected {len(FEATURE_NAMES)}"
                )
            hidden: list[float] = []
            for hidden_index, bias in enumerate(self.b1):
                value = bias
                for feature_index, feature in enumerate(row):
                    value += float(feature) * self.w1[feature_index][hidden_index]
                hidden.append(math.tanh(value))
            output.append(
                sum(value * weight for value, weight in zip(hidden, self.w2))
                + self.b2
            )
        return tuple(output)


@dataclass(frozen=True)
class ScorerDecision:
    scorer_id: str
    prediction: int
    margin: float
    score_direction: str
    candidate_scores: tuple[float, ...]
    risk_abstain: bool
    risk_reasons: tuple[str, ...]


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _normalised_text_sha256(payload: bytes) -> str:
    return _sha256(payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be a finite number")
    return result


def _scale(value: Any, denominator: float) -> float:
    return max(-20.0, min(20.0, _finite(value, "feature value") / denominator))


def _format_float(value: float) -> str:
    return f"{value:.9f}"


def _feature_lineage_rows() -> list[dict[str, str]]:
    """Return the audited 22-row legacy-to-event feature contract."""

    def row(
        name: str,
        training_semantics: str,
        training_source: str,
        s1_source: str,
        s1_resolution: str,
        s1_default: str,
        denominator: str,
        availability: str,
        ood_note: str,
        *,
        s2_source: str | None = None,
        s2_resolution: str | None = None,
        s2_default: str | None = None,
    ) -> dict[str, str]:
        index = FEATURE_NAMES.index(name)
        return {
            "feature_index": str(index),
            "feature_name": name,
            "training_semantics": training_semantics,
            "training_source": training_source,
            "s1_adapter_source": s1_source,
            "s1_resolution": s1_resolution,
            "s1_default_value": s1_default,
            "s2_adapter_source": s2_source if s2_source is not None else s1_source,
            "s2_resolution": (
                s2_resolution if s2_resolution is not None else s1_resolution
            ),
            "s2_default_value": s2_default if s2_default is not None else s1_default,
            "scale_denominator": denominator,
            "runtime_availability": availability,
            "consumed_model_input": "true",
            "ood_note": ood_note,
        }

    rows = [
        row(
            FEATURE_NAMES[0],
            "candidate-to-goal canonical heuristic time",
            "G4D candidate_shortest_time_to_goal",
            "candidate_records[].features.static_potential",
            "EXACT_LEGAL_STATIC",
            "",
            "100",
            "static",
            "Same frozen-map heuristic quantity; goal diagonal is normalized to zero.",
        ),
        row(
            FEATURE_NAMES[1],
            "current directed edge travel time",
            "G4D candidate_travel_time",
            "candidate_records[].features.travel_time",
            "EXACT_LEGAL_STATIC",
            "",
            "50",
            "static",
            "Trace value is checked against the frozen directed map edge.",
        ),
        row(
            FEATURE_NAMES[2],
            "candidate node service time",
            "G4D candidate_service_time",
            "canonical_map.nodes[candidate].service_time",
            "EXACT_LEGAL_STATIC",
            "",
            "10",
            "static",
            "Derived only from the frozen map.",
        ),
        row(
            FEATURE_NAMES[3],
            "candidate node type code",
            "G4D candidate_node_type",
            "canonical_map.nodes[candidate].node_type",
            "EXACT_LEGAL_STATIC",
            "",
            "10",
            "static",
            "Derived only from the frozen map.",
        ),
        row(
            FEATURE_NAMES[4],
            "fault status of the candidate edge at decision time",
            "G4D candidate_fault_status",
            "candidate_records[].features.advertised_fault",
            "LEGAL_EVENT_OBSERVATION",
            "",
            "1",
            "decision_time",
            "Uses the bounded local advertised belief, which can be stale versus physical truth.",
        ),
        row(
            FEATURE_NAMES[5],
            "candidate equals immutable goal",
            "candidate_next_node == goal_node",
            "candidate_records[].next_node == goal_node",
            "EXACT_LEGAL_STATIC",
            "",
            "1",
            "static",
            "No route suffix or future state is consulted.",
        ),
        row(
            FEATURE_NAMES[6],
            "task deadline/std minus decision time",
            "G4D time_slack",
            "explicit_default",
            "EXPLICIT_DEFAULT_MISSING",
            "0.0",
            "10000",
            "missing",
            "The committed event trace has no audited deadline/std field.",
        ),
        row(
            FEATURE_NAMES[7],
            "absolute current node identifier",
            "G4D current_node",
            "current_node",
            "EXACT_LEGAL_EVENT_STATE",
            "",
            "100",
            "decision_time",
            "S1 retains the legacy coordinate-like ID feature; S2 removes it.",
            s2_source="explicit_default",
            s2_resolution="EXPLICIT_DEFAULT_ID_ABLATION",
            s2_default="0.0",
        ),
        row(
            FEATURE_NAMES[8],
            "absolute goal node identifier",
            "G4D goal_node",
            "goal_node",
            "EXACT_LEGAL_STATIC",
            "",
            "100",
            "static",
            "S1 retains the legacy coordinate-like ID feature; S2 removes it.",
            s2_source="explicit_default",
            s2_resolution="EXPLICIT_DEFAULT_ID_ABLATION",
            s2_default="0.0",
        ),
        row(
            FEATURE_NAMES[9],
            "out-degree of the current decision node",
            "len(G4D candidate_next_nodes)",
            "len(candidate_next_nodes)",
            "EXACT_LEGAL_STATIC",
            "",
            "10",
            "static",
            "Candidate completeness is validated against canonical adjacency.",
        ),
        row(
            FEATURE_NAMES[10],
            "whether the current node has multiple candidates",
            "G4D is_branch_node",
            "len(candidate_next_nodes) > 1",
            "EXACT_LEGAL_STATIC",
            "",
            "1",
            "static",
            "Deterministic derivation from canonical outgoing adjacency.",
        ),
        row(
            FEATURE_NAMES[11],
            "reservation-overlap pressure at current node/time window",
            "G4D local_node_time_window_pressure",
            "explicit_default",
            "EXPLICIT_DEFAULT_NON_EQUIVALENT",
            "0.0",
            "10",
            "missing_equivalent_semantics",
            "local_snapshot.junction_queue_length is not a reservation-overlap count.",
        ),
        row(
            FEATURE_NAMES[12],
            "reservation-overlap pressure at candidate arrival window",
            "G4D local_queue_or_occupancy_summary.candidate_node_pressure",
            "explicit_default",
            "EXPLICIT_DEFAULT_NON_EQUIVALENT",
            "0.0",
            "10",
            "missing_equivalent_semantics",
            "target queue/incoming counts are legal but not the legacy overlap quantity.",
        ),
        row(
            FEATURE_NAMES[13],
            "two-hop recursive reservation-overlap pressure",
            "G4D enhanced candidate_downstream_node_pressure_2hop",
            "explicit_default",
            "EXPLICIT_DEFAULT_NON_EQUIVALENT",
            "0.0",
            "20",
            "missing_equivalent_semantics",
            "two_hop_queue_pressure is a bounded queue summary, not time-window overlap recursion.",
        ),
        row(
            FEATURE_NAMES[14],
            "three-hop recursive reservation-overlap pressure",
            "G4D enhanced candidate_downstream_node_pressure_3hop",
            "explicit_default",
            "EXPLICIT_DEFAULT_MISSING",
            "0.0",
            "30",
            "missing",
            "The event contract is bounded to two hops and exposes no equivalent three-hop field.",
        ),
        row(
            FEATURE_NAMES[15],
            "directed static hop distance from candidate to goal",
            "G4D directed BFS hop distance",
            "canonical_map directed adjacency BFS",
            "EXACT_LEGAL_STATIC_RECONSTRUCTION",
            "",
            "20",
            "static",
            "Uses 999 for unreachable, matching the frozen training builder.",
        ),
        row(
            FEATURE_NAMES[16],
            "candidate one-step static cost minus best candidate cost",
            "G4D (travel + heuristic) gap",
            "(travel_time + static_potential) - minimum candidate value",
            "EXACT_LEGAL_STATIC_RECONSTRUCTION",
            "",
            "50",
            "static",
            "Reconstructed only within the audited candidate set.",
        ),
        row(
            FEATURE_NAMES[17],
            "static candidate bottleneck plus observed candidate-edge fault term",
            "G4D max(0, 2-candidate_out_degree) + 5 if faulted",
            "canonical candidate out-degree + advertised_fault",
            "LEGAL_LOCAL_RECONSTRUCTION",
            "",
            "10",
            "static_and_decision_time",
            "Formula is preserved but the fault term follows local advertised belief.",
        ),
        row(
            FEATURE_NAMES[18],
            "current-to-goal heuristic minus candidate-to-goal heuristic",
            "G4D candidate_goal_direction_score",
            "canonical current potential - candidate static_potential",
            "EXACT_LEGAL_STATIC_RECONSTRUCTION",
            "",
            "100",
            "static",
            "No planned path is required.",
        ),
        row(
            FEATURE_NAMES[19],
            "candidate membership in a training-only failure-risk lookup",
            "G4D candidate_historical_risk_from_training_only",
            "explicit_default",
            "EXPLICIT_DEFAULT_TRAINING_ONLY",
            "0.0",
            "1",
            "training_only_unavailable",
            "The historical lookup and G4E hardcase rules are quarantined from runtime input.",
        ),
        row(
            FEATURE_NAMES[20],
            "source retry attempt pressure",
            "G4D source_retry_pressure",
            "explicit_default",
            "EXPLICIT_DEFAULT_MISSING",
            "0.0",
            "20",
            "missing",
            "The committed move-decision trace exposes no audited source retry counter.",
        ),
        row(
            FEATURE_NAMES[21],
            "unfinished source-neighborhood task queue size",
            "G4D unfinished_task_queue_size_near_current_source",
            "explicit_default",
            "EXPLICIT_DEFAULT_MISSING",
            "0.0",
            "20",
            "missing",
            "No equivalent source-neighborhood queue field exists in the event contract.",
        ),
    ]
    if [row["feature_name"] for row in rows] != list(FEATURE_NAMES):
        raise AssertionError("feature lineage order drifted from frozen G4E feature order")
    return rows


FEATURE_LINEAGE = tuple(_feature_lineage_rows())


def load_map_context(root: Path = ROOT) -> MapContext:
    payload = (root / MAP_PATH).read_bytes()
    raw_hash = _sha256(payload)
    semantic_hash = _normalised_text_sha256(payload)
    if raw_hash != MAP_RAW_SHA256:
        raise ValueError(f"canonical map raw hash mismatch: {raw_hash}")
    if semantic_hash != MAP_SEMANTIC_SHA256:
        raise ValueError(f"canonical map semantic hash mismatch: {semantic_hash}")
    data = json.loads(payload.decode("utf-8"))
    raw_nodes = data.get("nodes")
    raw_edges = data.get("edges")
    raw_heuristic = data.get("heuristic_time")
    if not isinstance(raw_nodes, list) or len(raw_nodes) != 54:
        raise ValueError("canonical map must contain exactly 54 nodes")
    if not isinstance(raw_edges, list) or len(raw_edges) != 69:
        raise ValueError("canonical map must contain exactly 69 directed edges")
    if not isinstance(raw_heuristic, list) or len(raw_heuristic) != 54:
        raise ValueError("canonical map heuristic_time must be 54x54")

    nodes: dict[int, Mapping[str, Any]] = {}
    adjacency: dict[int, tuple[int, ...]] = {}
    for raw_node in raw_nodes:
        node = int(raw_node["location"])
        if node in nodes:
            raise ValueError(f"duplicate canonical node {node}")
        nodes[node] = dict(raw_node)
        adjacency[node] = tuple(sorted(int(value) for value in raw_node["outgoing"]))
    if set(nodes) != set(range(54)):
        raise ValueError("canonical map node identifiers must be 0..53")

    edge_travel: dict[tuple[int, int], float] = {}
    for raw_edge in raw_edges:
        key = (int(raw_edge["start"]), int(raw_edge["end"]))
        if key in edge_travel:
            raise ValueError(f"duplicate canonical directed edge {key}")
        edge_travel[key] = _finite(raw_edge["travel_time"], f"edge {key} travel_time")
    adjacency_edges = {
        (start, end) for start, outgoing in adjacency.items() for end in outgoing
    }
    if set(edge_travel) != adjacency_edges:
        raise ValueError("canonical node adjacency and directed edge records disagree")

    heuristic = tuple(
        tuple(_finite(value, f"heuristic_time[{row_index}]") for value in row)
        for row_index, row in enumerate(raw_heuristic)
    )
    if any(len(row) != 54 for row in heuristic):
        raise ValueError("canonical map heuristic_time must be 54x54")

    hops: dict[tuple[int, int], int] = {}
    for start in sorted(nodes):
        distance = {start: 0}
        queue: deque[int] = deque([start])
        while queue:
            current = queue.popleft()
            for next_node in adjacency[current]:
                if next_node not in distance:
                    distance[next_node] = distance[current] + 1
                    queue.append(next_node)
        for goal in sorted(nodes):
            hops[(start, goal)] = distance.get(goal, 999)

    return MapContext(
        nodes=nodes,
        adjacency=adjacency,
        edge_travel_time=edge_travel,
        heuristic_time=heuristic,
        hop_distance=hops,
        raw_sha256=raw_hash,
        semantic_sha256=semantic_hash,
    )


def load_frozen_model(root: Path = ROOT) -> FrozenG4EModel:
    payload = (root / MODEL_PATH).read_bytes()
    raw_hash = _sha256(payload)
    if raw_hash != MODEL_RAW_SHA256:
        raise ValueError(f"frozen G4E model hash mismatch: {raw_hash}")
    data = json.loads(payload.decode("utf-8"))
    if data.get("model_type") != "g4e_risk_calibrated_policy":
        raise ValueError(f"unexpected G4E model_type: {data.get('model_type')!r}")
    if tuple(data.get("feature_names", ())) != FEATURE_NAMES:
        raise ValueError("frozen G4E feature order differs from audited 22-feature contract")

    w1 = tuple(
        tuple(_finite(value, f"w1[{row_index}]") for value in row)
        for row_index, row in enumerate(data["w1"])
    )
    b1 = tuple(_finite(value, "b1") for value in data["b1"])
    w2 = tuple(_finite(value, "w2") for value in data["w2"])
    if len(w1) != 22 or any(len(row) != 22 for row in w1):
        raise ValueError("frozen G4E w1 must be 22x22")
    if len(b1) != 22 or len(w2) != 22:
        raise ValueError("frozen G4E hidden/output dimensions must both be 22")

    learned_rules = data.get("g4e_learned_risk_rules", [])
    if not isinstance(learned_rules, list):
        raise ValueError("g4e_learned_risk_rules must be an array")
    return FrozenG4EModel(
        w1=w1,
        b1=b1,
        w2=w2,
        b2=_finite(data["b2"], "b2"),
        risk_margin_threshold=_finite(
            data.get("risk_margin_threshold", 1.0), "risk_margin_threshold"
        ),
        risk_historical_threshold=_finite(
            data.get("risk_historical_threshold", 0.5),
            "risk_historical_threshold",
        ),
        risk_bottleneck_threshold=_finite(
            data.get("risk_bottleneck_threshold", 5.0),
            "risk_bottleneck_threshold",
        ),
        raw_sha256=raw_hash,
        learned_rule_count=len(learned_rules),
        selected_candidate=str(data.get("g4e_selected_candidate", "")),
    )


def _static_potential(context: MapContext, node: int, goal: int) -> float:
    if node == goal:
        return 0.0
    return context.heuristic_time[node][goal]


def _validate_adapter_row(
    row: Mapping[str, Any],
    context: MapContext,
    *,
    require_trace_identity: bool,
) -> None:
    assert_no_future_or_label_leakage(row)
    unknown_top_level = set(row) - CANONICAL_TRACE_TOP_LEVEL
    if unknown_top_level:
        raise ValueError(
            "adapter row contains unapproved top-level field(s): "
            + ", ".join(sorted(unknown_top_level))
        )
    missing_top_level = {
        "event_time",
        "current_node",
        "goal_node",
        "candidate_next_nodes",
        "candidate_records",
    } - set(row)
    if missing_top_level:
        raise ValueError(
            "adapter row is missing field(s): " + ", ".join(sorted(missing_top_level))
        )

    current = int(row["current_node"])
    goal = int(row["goal_node"])
    if current not in context.nodes or goal not in context.nodes:
        raise ValueError(f"adapter row uses unknown current/goal nodes: {current}/{goal}")
    candidates = tuple(int(value) for value in row["candidate_next_nodes"])
    if candidates != context.adjacency[current]:
        raise ValueError(
            f"adapter candidates {candidates} differ from canonical outgoing "
            f"{context.adjacency[current]} at node {current}"
        )
    records = row["candidate_records"]
    if not isinstance(records, Sequence) or len(records) != len(candidates):
        raise ValueError("candidate_records must align with candidate_next_nodes")

    expected_feature_names = set(EVENT_RUNTIME_FEATURE_SOURCES)
    for index, (candidate, raw_record) in enumerate(zip(candidates, records)):
        if int(raw_record["next_node"]) != candidate:
            raise ValueError(f"candidate record {index} is misaligned")
        features = raw_record["features"]
        if set(features) != expected_feature_names:
            missing = sorted(expected_feature_names - set(features))
            unknown = sorted(set(features) - expected_feature_names)
            raise ValueError(
                f"candidate {candidate} feature contract mismatch; "
                f"missing={missing}, unknown={unknown}"
            )
        expected_static = _static_potential(context, candidate, goal)
        actual_static = _finite(features["static_potential"], "static_potential")
        if not math.isclose(
            actual_static, expected_static, rel_tol=1.0e-10, abs_tol=1.0e-10
        ):
            raise ValueError(
                f"candidate {candidate} static_potential {actual_static} "
                f"does not match frozen map {expected_static}"
            )
        expected_travel = context.edge_travel_time[(current, candidate)]
        actual_travel = _finite(features["travel_time"], "travel_time")
        if not math.isclose(
            actual_travel, expected_travel, rel_tol=1.0e-10, abs_tol=1.0e-10
        ):
            raise ValueError(
                f"candidate {candidate} travel_time {actual_travel} "
                f"does not match frozen map {expected_travel}"
            )
        if not isinstance(features["advertised_fault"], bool):
            raise ValueError("advertised_fault must be boolean")
        for name in expected_feature_names - {"advertised_fault"}:
            _finite(features[name], f"candidate {candidate}.{name}")

    if require_trace_identity:
        metadata = row.get("metadata")
        if not isinstance(metadata, Mapping):
            raise ValueError("offline trace row metadata must be an object")
        if metadata.get("canonical_map_sha256") != MAP_SEMANTIC_SHA256:
            raise ValueError("offline trace row canonical_map_sha256 mismatch")


def load_offline_trace(
    context: MapContext,
    root: Path = ROOT,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    payload = (root / TRACE_PATH).read_bytes()
    raw_hash = _sha256(payload)
    if raw_hash != TRACE_RAW_SHA256:
        raise ValueError(f"decision trace hash mismatch: {raw_hash}")
    raw_rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(payload.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"trace row {line_number} must be an object")
        raw_rows.append(value)
        if limit is not None and len(raw_rows) >= limit:
            break
    if limit is None and len(raw_rows) != TRACE_EXPECTED_ROWS:
        raise ValueError(
            f"decision trace row count {len(raw_rows)} != {TRACE_EXPECTED_ROWS}"
        )
    rows = validate_decision_rows(raw_rows, context.adjacency)
    for row in rows:
        _validate_adapter_row(row, context, require_trace_identity=True)
    return rows


def feature_vectors(
    row: Mapping[str, Any],
    context: MapContext,
    mode: str,
    *,
    _validated: bool = False,
) -> tuple[tuple[float, ...], ...]:
    """Build S1/S2 frozen-model inputs from one canonical decision row."""

    if mode not in {"S1", "S2"}:
        raise ValueError(f"feature mode must be S1 or S2; got {mode!r}")
    if not _validated:
        _validate_adapter_row(row, context, require_trace_identity=False)
    current = int(row["current_node"])
    goal = int(row["goal_node"])
    candidates = [int(value) for value in row["candidate_next_nodes"]]
    candidate_records = list(row["candidate_records"])
    current_potential = _static_potential(context, current, goal)
    static_costs = [
        _finite(record["features"]["travel_time"], "travel_time")
        + _finite(record["features"]["static_potential"], "static_potential")
        for record in candidate_records
    ]
    best_static_cost = min(static_costs)

    output: list[tuple[float, ...]] = []
    for candidate, record, static_cost in zip(
        candidates, candidate_records, static_costs
    ):
        features = record["features"]
        advertised_fault = bool(features["advertised_fault"])
        candidate_out_degree = len(context.adjacency[candidate])
        bottleneck = max(0.0, 2.0 - float(candidate_out_degree))
        if advertised_fault:
            bottleneck += 5.0
        values = {
            FEATURE_NAMES[0]: _scale(features["static_potential"], 100.0),
            FEATURE_NAMES[1]: _scale(features["travel_time"], 50.0),
            FEATURE_NAMES[2]: _scale(
                context.nodes[candidate]["service_time"], 10.0
            ),
            FEATURE_NAMES[3]: _scale(context.nodes[candidate]["node_type"], 10.0),
            FEATURE_NAMES[4]: 1.0 if advertised_fault else 0.0,
            FEATURE_NAMES[5]: 1.0 if candidate == goal else 0.0,
            FEATURE_NAMES[6]: 0.0,
            FEATURE_NAMES[7]: (
                _scale(current, 100.0) if mode == "S1" else 0.0
            ),
            FEATURE_NAMES[8]: _scale(goal, 100.0) if mode == "S1" else 0.0,
            FEATURE_NAMES[9]: _scale(len(candidates), 10.0),
            FEATURE_NAMES[10]: 1.0 if len(candidates) > 1 else 0.0,
            FEATURE_NAMES[11]: 0.0,
            FEATURE_NAMES[12]: 0.0,
            FEATURE_NAMES[13]: 0.0,
            FEATURE_NAMES[14]: 0.0,
            FEATURE_NAMES[15]: _scale(
                context.hop_distance[(candidate, goal)], 20.0
            ),
            FEATURE_NAMES[16]: _scale(static_cost - best_static_cost, 50.0),
            FEATURE_NAMES[17]: _scale(bottleneck, 10.0),
            FEATURE_NAMES[18]: _scale(
                current_potential
                - _finite(features["static_potential"], "static_potential"),
                100.0,
            ),
            FEATURE_NAMES[19]: 0.0,
            FEATURE_NAMES[20]: 0.0,
            FEATURE_NAMES[21]: 0.0,
        }
        output.append(tuple(values[name] for name in FEATURE_NAMES))
    return tuple(output)


def _rank_scores(
    candidates: Sequence[int],
    scores: Sequence[float],
    *,
    higher_is_better: bool,
) -> tuple[int, float]:
    if not candidates or len(candidates) != len(scores):
        raise ValueError("candidate score array must be non-empty and aligned")
    if higher_is_better:
        order = sorted(
            range(len(candidates)),
            key=lambda index: (-float(scores[index]), int(candidates[index])),
        )
        margin = (
            float(scores[order[0]]) - float(scores[order[1]])
            if len(order) > 1
            else 999.0
        )
    else:
        order = sorted(
            range(len(candidates)),
            key=lambda index: (float(scores[index]), int(candidates[index])),
        )
        margin = (
            float(scores[order[1]]) - float(scores[order[0]])
            if len(order) > 1
            else 999.0
        )
    return int(candidates[order[0]]), margin


def score_frozen_g4e(
    row: Mapping[str, Any],
    context: MapContext,
    model: FrozenG4EModel,
    mode: str,
    *,
    _validated: bool = False,
) -> ScorerDecision:
    if mode not in {"S1", "S2"}:
        raise ValueError(f"frozen G4E scorer mode must be S1 or S2; got {mode!r}")
    vectors = feature_vectors(row, context, mode, _validated=_validated)
    scores = model.scores(vectors)
    candidates = [int(value) for value in row["candidate_next_nodes"]]
    prediction, margin = _rank_scores(
        candidates, scores, higher_is_better=True
    )
    prediction_index = candidates.index(prediction)
    raw_bottleneck = vectors[prediction_index][FEATURE_NAMES.index(
        "candidate_bottleneck_score_scaled"
    )] * 10.0
    reasons: list[str] = []
    if margin < model.risk_margin_threshold:
        reasons.append("frozen_margin_below_threshold")
    if raw_bottleneck >= model.risk_bottleneck_threshold:
        reasons.append("legal_local_bottleneck_at_or_above_threshold")
    # The historical-risk feature and G4E absolute-tuple lookup rules are
    # deliberately not evaluated.  Both are documented as quarantined in the
    # adapter bundle, rather than silently treated as live event inputs.
    return ScorerDecision(
        scorer_id=SCORER_IDS[1] if mode == "S1" else SCORER_IDS[2],
        prediction=prediction,
        margin=margin,
        score_direction="higher_is_better_frozen_mlp_score",
        candidate_scores=tuple(scores),
        risk_abstain=bool(reasons),
        risk_reasons=tuple(reasons),
    )


def score_rule(
    row: Mapping[str, Any],
    context: MapContext,
    mode: str,
    *,
    _validated: bool = False,
) -> ScorerDecision:
    if mode not in {"S3", "S4"}:
        raise ValueError(f"rule scorer mode must be S3 or S4; got {mode!r}")
    if not _validated:
        _validate_adapter_row(row, context, require_trace_identity=False)
    event_time = _finite(row["event_time"], "event_time")
    candidates = [int(value) for value in row["candidate_next_nodes"]]
    scores: list[float] = []
    for record in row["candidate_records"]:
        features = record["features"]
        travel = _finite(features["travel_time"], "travel_time")
        static = _finite(features["static_potential"], "static_potential")
        score = travel + static
        if mode == "S4":
            queue_pressure = _finite(
                features["target_queue_length"], "target_queue_length"
            ) + _finite(
                features["target_scheduled_incoming"],
                "target_scheduled_incoming",
            )
            corridor_wait = max(
                0.0,
                _finite(
                    features["corridor_next_available"],
                    "corridor_next_available",
                )
                - event_time,
            )
            target_wait = max(
                0.0,
                _finite(
                    features["target_next_available"],
                    "target_next_available",
                )
                - (event_time + travel),
            )
            score += queue_pressure + corridor_wait + target_wait
        scores.append(score)
    prediction, margin = _rank_scores(
        candidates, scores, higher_is_better=False
    )
    return ScorerDecision(
        scorer_id=SCORER_IDS[3] if mode == "S3" else SCORER_IDS[4],
        prediction=prediction,
        margin=margin,
        score_direction="lower_is_better_cost",
        candidate_scores=tuple(scores),
        risk_abstain=False,
        risk_reasons=(),
    )


def _recorded_s0(row: Mapping[str, Any]) -> ScorerDecision:
    candidates = [int(value) for value in row["candidate_next_nodes"]]
    scores = tuple(
        _finite(record["model_score"], "recorded model_score")
        for record in row["candidate_records"]
    )
    prediction, recomputed_margin = _rank_scores(
        candidates, scores, higher_is_better=False
    )
    if prediction != int(row["model_prediction"]):
        raise ValueError("recorded S0 prediction is inconsistent with candidate scores")
    if not math.isclose(
        recomputed_margin,
        _finite(row["model_margin"], "model_margin"),
        rel_tol=1.0e-10,
        abs_tol=1.0e-10,
    ):
        raise ValueError("recorded S0 margin is inconsistent with candidate scores")
    return ScorerDecision(
        scorer_id=SCORER_IDS[0],
        prediction=prediction,
        margin=recomputed_margin,
        score_direction="lower_is_better_recorded_cost",
        candidate_scores=scores,
        risk_abstain=bool(row["risk_gate_triggered"]),
        risk_reasons=(
            ("recorded_runtime_risk_gate",)
            if bool(row["risk_gate_triggered"])
            else ()
        ),
    )


def evaluate_same_observation_replay(
    rows: Sequence[Mapping[str, Any]],
    context: MapContext,
    model: FrozenG4EModel,
) -> dict[str, Any]:
    """Compare scorer actions without making counterfactual outcome claims."""

    if not rows:
        raise ValueError("offline replay requires at least one decision row")
    counters = {
        scorer_id: {
            "candidate_count": 0,
            "model_agreement": 0,
            "selected_agreement": 0,
            "shield_allowed": 0,
            "risk_abstain": 0,
            "margin_sum": 0.0,
            "score_direction": "",
        }
        for scorer_id in SCORER_IDS
    }
    pairwise_disagreement = 0
    for row in rows:
        results = (
            _recorded_s0(row),
            score_frozen_g4e(
                row, context, model, "S1", _validated=True
            ),
            score_frozen_g4e(
                row, context, model, "S2", _validated=True
            ),
            score_rule(row, context, "S3", _validated=True),
            score_rule(row, context, "S4", _validated=True),
        )
        pairwise_disagreement += int(results[1].prediction != results[2].prediction)
        shield = {
            int(record["next_node"]): bool(record.get("shield_allowed", False))
            for record in row["candidate_records"]
        }
        for result in results:
            count = counters[result.scorer_id]
            count["candidate_count"] += len(result.candidate_scores)
            count["model_agreement"] += int(
                result.prediction == int(row["model_prediction"])
            )
            count["selected_agreement"] += int(
                result.prediction == int(row["selected_next"])
            )
            count["shield_allowed"] += int(shield[result.prediction])
            count["risk_abstain"] += int(result.risk_abstain)
            count["margin_sum"] += result.margin
            count["score_direction"] = result.score_direction

    isolation_rows: list[dict[str, str]] = []
    decision_count = len(rows)
    for scorer_id in SCORER_IDS:
        count = counters[scorer_id]
        if scorer_id == SCORER_IDS[0]:
            status = "RECORDED_TRACE_REFERENCE_ONLY"
        elif scorer_id in {SCORER_IDS[1], SCORER_IDS[2]}:
            status = CLAIM_STATUS
        else:
            status = "OFFLINE_RULE_DIAGNOSTIC_ONLY_NOT_CLOSED_LOOP"
        isolation_rows.append(
            {
                "scorer_id": scorer_id,
                "evaluation_scope": DIAGNOSTIC_SCOPE,
                "status": status,
                "closed_loop_run": "false",
                "trace_decision_count": str(decision_count),
                "candidate_score_count": str(count["candidate_count"]),
                "score_direction": str(count["score_direction"]),
                "margin_semantics": (
                    "best_minus_second_best"
                    if "higher_is_better" in str(count["score_direction"])
                    else "second_best_minus_best"
                ),
                "agreement_with_recorded_model_prediction_count": str(
                    count["model_agreement"]
                ),
                "agreement_with_recorded_model_prediction_rate": _format_float(
                    count["model_agreement"] / decision_count
                ),
                "agreement_with_recorded_selected_action_count": str(
                    count["selected_agreement"]
                ),
                "agreement_with_recorded_selected_action_rate": _format_float(
                    count["selected_agreement"] / decision_count
                ),
                "predicted_candidate_shield_allowed_count": str(
                    count["shield_allowed"]
                ),
                "predicted_candidate_shield_allowed_rate": _format_float(
                    count["shield_allowed"] / decision_count
                ),
                "risk_abstain_count": str(count["risk_abstain"]),
                "risk_abstain_rate": _format_float(
                    count["risk_abstain"] / decision_count
                ),
                "mean_margin": _format_float(count["margin_sum"] / decision_count),
                # These cells must remain blank: a trace replay cannot produce a
                # counterfactual completion rate or THT denominator.
                "completion_rate": "",
                "original_entry_time_tth": "",
                "claim_boundary": (
                    "behavioral agreement only; no counterfactual queue evolution, "
                    "completion, throughput, or THT claim"
                ),
            }
        )
    return {
        "isolation_rows": isolation_rows,
        "s1_s2_disagreement_count": pairwise_disagreement,
        "s1_s2_disagreement_rate": pairwise_disagreement / decision_count,
        "decision_count": decision_count,
        "candidate_score_count": sum(
            len(row["candidate_next_nodes"]) for row in rows
        ),
    }


def collect_evidence(root: Path = ROOT) -> dict[str, Any]:
    context = load_map_context(root)
    model = load_frozen_model(root)
    rows = load_offline_trace(context, root)
    replay = evaluate_same_observation_replay(rows, context, model)
    return {
        "context": context,
        "model": model,
        "trace_rows": rows,
        "trace_raw_sha256": TRACE_RAW_SHA256,
        "replay": replay,
        "lineage_rows": [dict(row) for row in FEATURE_LINEAGE],
    }


def validate_evidence(evidence: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    context: MapContext = evidence["context"]
    model: FrozenG4EModel = evidence["model"]
    replay = evidence["replay"]
    lineage_rows = evidence["lineage_rows"]
    if context.raw_sha256 != MAP_RAW_SHA256:
        problems.append("map raw hash drift")
    if context.semantic_sha256 != MAP_SEMANTIC_SHA256:
        problems.append("map semantic hash drift")
    if model.raw_sha256 != MODEL_RAW_SHA256:
        problems.append("model raw hash drift")
    if len(evidence["trace_rows"]) != TRACE_EXPECTED_ROWS:
        problems.append("trace row count drift")
    if replay["decision_count"] != TRACE_EXPECTED_ROWS:
        problems.append("offline replay did not cover the full committed trace")
    if len(lineage_rows) != len(FEATURE_NAMES):
        problems.append("feature lineage does not contain exactly 22 rows")
    if [row["feature_name"] for row in lineage_rows] != list(FEATURE_NAMES):
        problems.append("feature lineage order differs from frozen model")

    s1_defaults = {
        row["feature_name"]
        for row in lineage_rows
        if row["s1_resolution"].startswith("EXPLICIT_DEFAULT")
    }
    expected_s1_defaults = {
        FEATURE_NAMES[index] for index in (6, 11, 12, 13, 14, 19, 20, 21)
    }
    if s1_defaults != expected_s1_defaults:
        problems.append("S1 explicit-default feature set drift")
    s2_defaults = {
        row["feature_name"]
        for row in lineage_rows
        if row["s2_resolution"].startswith("EXPLICIT_DEFAULT")
    }
    if s2_defaults != expected_s1_defaults | {FEATURE_NAMES[7], FEATURE_NAMES[8]}:
        problems.append("S2 explicit-default/ID-ablation feature set drift")

    isolation_rows = replay["isolation_rows"]
    if [row["scorer_id"] for row in isolation_rows] != list(SCORER_IDS):
        problems.append("offline isolation table scorer order drift")
    for row in isolation_rows:
        if row["closed_loop_run"] != "false":
            problems.append(f"{row['scorer_id']} incorrectly claims a closed-loop run")
        if row["completion_rate"] or row["original_entry_time_tth"]:
            problems.append(
                f"{row['scorer_id']} contains an unsupported outcome metric"
            )
    if model.learned_rule_count <= 0:
        problems.append("expected frozen G4E learned rules are absent; quarantine audit invalid")
    return problems


def _csv_text(
    rows: Iterable[Mapping[str, Any]], fieldnames: Sequence[str]
) -> str:
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(
        handle,
        fieldnames=list(fieldnames),
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return handle.getvalue()


def _bundle(evidence: Mapping[str, Any]) -> dict[str, Any]:
    model: FrozenG4EModel = evidence["model"]
    replay = evidence["replay"]
    defaults_s1 = [
        row["feature_name"]
        for row in evidence["lineage_rows"]
        if row["s1_resolution"].startswith("EXPLICIT_DEFAULT")
    ]
    defaults_s2 = [
        row["feature_name"]
        for row in evidence["lineage_rows"]
        if row["s2_resolution"].startswith("EXPLICIT_DEFAULT")
    ]
    return {
        "schema": ADAPTER_SCHEMA,
        "stage": "G4IRSF12-E",
        "status": CLAIM_STATUS,
        "phase_date": PHASE_DATE,
        "claim_boundary": {
            "closed_loop_validated": False,
            "promotion_eligible": False,
            "diagnostic_scope": DIAGNOSTIC_SCOPE,
            "allowed_claim": "same-observation scorer action agreement only",
            "forbidden_claims": [
                "counterfactual completion rate",
                "counterfactual throughput",
                "counterfactual THT",
                "policy regression attribution",
                "production or final-model promotion",
            ],
        },
        "source_model": {
            "path": MODEL_PATH.as_posix(),
            "raw_sha256": model.raw_sha256,
            "model_type": "g4e_risk_calibrated_policy",
            "feature_count": len(FEATURE_NAMES),
            "hidden_dimension": len(model.b1),
            "frozen_components": ["w1", "b1", "w2", "b2"],
            "risk_thresholds": {
                "margin": model.risk_margin_threshold,
                "historical": model.risk_historical_threshold,
                "bottleneck": model.risk_bottleneck_threshold,
            },
            "selected_candidate_in_source_bundle": model.selected_candidate,
            "quarantined_learned_rule_count": model.learned_rule_count,
            "quarantined_components": [
                {
                    "component": "g4e_learned_risk_rules",
                    "reason": (
                        "training-derived absolute current/goal/candidate tuple "
                        "lookup has no portable 22-feature event lineage"
                    ),
                },
                {
                    "component": (
                        "candidate_historical_risk_from_training_only_scaled"
                    ),
                    "reason": "training-only lookup is unavailable at event time",
                    "explicit_default": 0.0,
                },
            ],
        },
        "canonical_map": {
            "path": MAP_PATH.as_posix(),
            "raw_sha256": MAP_RAW_SHA256,
            "semantic_sha256": MAP_SEMANTIC_SHA256,
            "node_count": 54,
            "directed_edge_count": 69,
        },
        "offline_trace": {
            "path": TRACE_PATH.as_posix(),
            "raw_sha256": TRACE_RAW_SHA256,
            "decision_count": replay["decision_count"],
            "candidate_score_count": replay["candidate_score_count"],
            "coverage": (
                "committed G4IRSF11 diagnostic decision sample only; "
                "not all 43,603 original input segments"
            ),
            "outcome_table_read": False,
        },
        "input_contract": {
            "model_visible_top_level": [
                "event_time",
                "current_node",
                "goal_node",
                "candidate_next_nodes",
                "candidate_records[].next_node",
                "candidate_records[].features",
            ],
            "approved_candidate_feature_names": sorted(
                EVENT_RUNTIME_FEATURE_SOURCES
            ),
            "metadata_is_model_input": False,
            "recorded_model_outputs_are_model_inputs": False,
            "recorded_selected_action_is_model_input": False,
            "safety_shield_is_external_to_raw_scorer": True,
            "future_teacher_posthoc_inputs_allowed": False,
        },
        "feature_names": list(FEATURE_NAMES),
        "feature_lineage": [
            {
                key: row[key]
                for key in (
                    "feature_index",
                    "feature_name",
                    "s1_adapter_source",
                    "s1_resolution",
                    "s1_default_value",
                    "s2_adapter_source",
                    "s2_resolution",
                    "s2_default_value",
                )
            }
            for row in evidence["lineage_rows"]
        ],
        "scorers": {
            SCORER_IDS[0]: {
                "type": "recorded_reference",
                "execution": "not re-executed",
            },
            SCORER_IDS[1]: {
                "type": "frozen_mlp",
                "score_direction": "higher_is_better",
                "explicit_default_features": defaults_s1,
                "risk_head": (
                    "frozen margin threshold plus legal-local bottleneck; "
                    "historical lookup and hardcase rules disabled"
                ),
            },
            SCORER_IDS[2]: {
                "type": "frozen_mlp_id_ablation",
                "score_direction": "higher_is_better",
                "explicit_default_features": defaults_s2,
                "risk_head": (
                    "same portable risk head as S1; all absolute-tuple rules disabled"
                ),
            },
            SCORER_IDS[3]: {
                "type": "deterministic_rule",
                "score_direction": "lower_is_better",
                "formula": "travel_time + static_potential",
                "tie_break": "ascending_next_node",
            },
            SCORER_IDS[4]: {
                "type": "deterministic_rule",
                "score_direction": "lower_is_better",
                "formula": (
                    "travel_time + static_potential + target_queue_length + "
                    "target_scheduled_incoming + max(0,corridor_next_available-event_time) "
                    "+ max(0,target_next_available-(event_time+travel_time))"
                ),
                "tie_break": "ascending_next_node",
            },
        },
        "offline_replay": {
            "s1_s2_disagreement_count": replay["s1_s2_disagreement_count"],
            "s1_s2_disagreement_rate": replay["s1_s2_disagreement_rate"],
            "isolation_table": ISOLATION_TABLE_PATH.as_posix(),
        },
        "evidence_paths": {
            "report": REPORT_PATH.as_posix(),
            "feature_lineage": LINEAGE_TABLE_PATH.as_posix(),
            "scorer_isolation": ISOLATION_TABLE_PATH.as_posix(),
        },
    }


def _report_text(evidence: Mapping[str, Any]) -> str:
    model: FrozenG4EModel = evidence["model"]
    replay = evidence["replay"]
    rows_by_id = {
        row["scorer_id"]: row for row in replay["isolation_rows"]
    }
    lines = [
        "# G4IRSF12-E Frozen G4E Event Adapter",
        "",
        f"**Status: `{CLAIM_STATUS}`.**",
        "",
        "This stage supplies a legal-local Python adapter and an offline scorer-isolation "
        "diagnostic. It is **not** the required closed-loop S0-S4 A/B: the trace cannot "
        "recreate counterfactual queues, reservations, completions, throughput, or THT.",
        "",
        "## Frozen identities",
        "",
        f"- G4E model: `{MODEL_PATH.as_posix()}` / `{MODEL_RAW_SHA256}`",
        f"- Canonical map raw SHA-256: `{MAP_RAW_SHA256}`",
        f"- Canonical map semantic SHA-256: `{MAP_SEMANTIC_SHA256}`",
        f"- Decision trace: `{TRACE_PATH.as_posix()}` / `{TRACE_RAW_SHA256}`",
        f"- Trace scope: **{replay['decision_count']:,}** decisions and "
        f"**{replay['candidate_score_count']:,}** candidate scores from the committed "
        "G4IRSF11 diagnostic sample, not all 43,603 original input segments.",
        "",
        "## Adapter boundary",
        "",
        "The adapter verifies the exact 22-feature order and 22x22 frozen MLP. S1 retains "
        "the frozen `w1/b1/w2/b2`; S2 changes only the two absolute node-ID inputs to "
        "zero. Both are OOD diagnostics.",
        "",
        f"The source bundle contains **{model.learned_rule_count}** learned hardcase "
        "rules and identifies its selected candidate as "
        f"`{model.selected_candidate}`. Those rules are quarantined: they are "
        "training-derived absolute current/goal/candidate tuple lookups, not a portable "
        "event feature with a 22-dimensional lineage. The training-only historical-risk "
        "feature is also explicitly zero. The portable risk diagnostic uses only the "
        "frozen margin threshold and the locally reconstructed bottleneck; the physical "
        "safety shield remains external.",
        "",
        "Metadata, recorded model outputs, the recorded selected action, and outcome data "
        "are not model inputs. Changing a metadata scenario label cannot change a feature "
        "vector. Unknown candidate features and teacher/future/post-hoc keys fail closed.",
        "",
        "## Complete 22-feature lineage",
        "",
        "| # | Frozen feature | S1 resolution | S1 source/default | S2 change |",
        "|---:|---|---|---|---|",
    ]
    for row in evidence["lineage_rows"]:
        s1_value = (
            f"default `{row['s1_default_value']}`"
            if row["s1_default_value"]
            else f"`{row['s1_adapter_source']}`"
        )
        if row["s2_resolution"] == row["s1_resolution"]:
            s2_change = "same as S1"
        else:
            s2_change = (
                f"{row['s2_resolution']} / default `{row['s2_default_value']}`"
            )
        lines.append(
            f"| {int(row['feature_index']) + 1} | `{row['feature_name']}` | "
            f"{row['s1_resolution']} | {s1_value} | {s2_change} |"
        )
    lines.extend(
        [
            "",
            "The pressure-related legacy fields are deliberately not populated from "
            "similarly named event queue fields. Reservation-overlap pressure and bounded "
            "queue summaries are not equivalent quantities. The detailed reasons are in "
            f"`{LINEAGE_TABLE_PATH.as_posix()}`.",
            "",
            "## Same-observation offline replay",
            "",
            "| Scorer | Agreement with recorded model | Agreement with recorded action | "
            "Predicted candidate shield-allowed | Risk abstain |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for scorer_id in SCORER_IDS:
        row = rows_by_id[scorer_id]
        lines.append(
            f"| `{scorer_id}` | "
            f"{float(row['agreement_with_recorded_model_prediction_rate']):.3%} | "
            f"{float(row['agreement_with_recorded_selected_action_rate']):.3%} | "
            f"{float(row['predicted_candidate_shield_allowed_rate']):.3%} | "
            f"{float(row['risk_abstain_rate']):.3%} |"
        )
    lines.extend(
        [
            "",
            f"S1 and S2 disagree on **{replay['s1_s2_disagreement_count']:,} / "
            f"{replay['decision_count']:,}** recorded observations "
            f"({replay['s1_s2_disagreement_rate']:.3%}). These are behavioral "
            "agreement statistics, not action accuracy and not evidence of improved "
            "completion.",
            "",
            "## Missing closed-loop A/B and promotion boundary",
            "",
            "The plan requires S0-S4 to run with identical resource semantics, queue "
            "discipline, and PIBT/pressure settings. That experiment was not executed in "
            "this Python-only adapter stage. Consequently, "
            f"`{ISOLATION_TABLE_PATH.as_posix()}` leaves `completion_rate` and "
            "`original_entry_time_tth` blank for every scorer.",
            "",
            "No S1/S2 result here may be promoted to a final model, and no policy-regression "
            "or resource/coordination attribution may be made until a controlled event-runtime "
            "closed-loop A/B is executed.",
            "",
        ]
    )
    return "\n".join(lines)


def render_artifacts(evidence: Mapping[str, Any]) -> dict[Path, str]:
    problems = validate_evidence(evidence)
    if problems:
        raise ValueError("invalid G4IRSF12-E evidence: " + "; ".join(problems))
    return {
        REPORT_PATH: _report_text(evidence),
        ISOLATION_TABLE_PATH: _csv_text(
            evidence["replay"]["isolation_rows"], ISOLATION_COLUMNS
        ),
        LINEAGE_TABLE_PATH: _csv_text(
            evidence["lineage_rows"], LINEAGE_COLUMNS
        ),
        BUNDLE_PATH: json.dumps(
            _bundle(evidence),
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    }


def publish_artifacts(
    evidence: Mapping[str, Any], root: Path = ROOT
) -> list[Path]:
    artifacts = render_artifacts(evidence)
    written: list[Path] = []
    for relative_path, text in artifacts.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


def validate_committed_outputs(
    evidence: Mapping[str, Any], root: Path = ROOT
) -> list[str]:
    problems: list[str] = []
    for relative_path, expected in render_artifacts(evidence).items():
        path = root / relative_path
        if not path.is_file():
            problems.append(f"missing committed artifact: {relative_path.as_posix()}")
            continue
        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            problems.append(f"committed artifact drift: {relative_path.as_posix()}")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate or publish G4IRSF12-E frozen-G4E adapter evidence."
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="publish the four deterministic Stage-E artifacts",
    )
    args = parser.parse_args(argv)

    evidence = collect_evidence(ROOT)
    problems = validate_evidence(evidence)
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}", file=sys.stderr)
        return 1
    if args.write:
        paths = publish_artifacts(evidence, ROOT)
        for path in paths:
            print(f"WROTE {path.relative_to(ROOT).as_posix()}")
    else:
        output_problems = validate_committed_outputs(evidence, ROOT)
        if output_problems:
            for problem in output_problems:
                print(f"FAIL: {problem}", file=sys.stderr)
            return 1
    replay = evidence["replay"]
    print(
        "PASS G4IRSF12-E "
        f"decisions={replay['decision_count']} "
        f"s1_s2_disagreement={replay['s1_s2_disagreement_count']} "
        f"status={CLAIM_STATUS}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
