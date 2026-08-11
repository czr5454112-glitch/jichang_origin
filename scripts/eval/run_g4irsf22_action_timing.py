#!/usr/bin/env python3
"""Plan G22 current-point and one-decision-earlier Route action sets.

This module is deliberately a small orchestration layer.  It consumes native
Route census rows, selects a diverse current-point panel or the nearest real
precursor for the same runtime segment, and emits the G22 extension of the G21
exact-action target contract.  S4 remains the implicit baseline; treatments
are every other shield-legal edge and native WAIT when WAIT is legal.

The native backend is loaded only by :func:`load_native_backend`.  Importing
this module and exercising its selection/target functions requires no native
extension and starts no simulation.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))
RESEARCH_PROFILE = "G22_S4_J2_E2"
EVENT_SCHEMA = "czr005.g4irsf22.route_action_event.v1"
# The native exact engine already has a complete G21 all-edges-plus-WAIT
# contract.  G22 changes when/where targets are selected, not the treatment
# wire format, so reuse that stable schema instead of adding another parser.
TARGET_SCHEMA = "czr005.g4irsf21.route_action_target.v1"
PLAN_SCHEMA = "czr005.g4irsf22.action_timing_plan.v1"
HORIZONS = ("H_bag", "H_system")
CURRENT_STRATA = (
    "high_target_queue",
    "high_calendar_wait",
    "high_merge_contention",
    "s4_v2_divergence_or_near_tie",
)
CURRENT_SCORE_TOLERANCE = 1e-9
H_SYSTEM_SUMMARY_SCHEMA = "czr005.g4irsf22.h_system_action_summary.v1"


class ActionTimingError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ActionTimingError(message)


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _text(row: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if isinstance(value, str) and value:
            return value
    raise ActionTimingError(f"missing {'/'.join(names)}")


def _finite_number(value: Any, field: str, *, minimum: float | None = None) -> float:
    _require(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value)),
        f"{field} must be finite",
    )
    number = float(value)
    if minimum is not None:
        _require(number >= minimum, f"{field} must be >= {minimum:g}")
    return number


def _candidate_payload(row: Mapping[str, Any]) -> tuple[list[int], list[dict[str, Any]], int]:
    observation = row.get("route_observation")
    if not isinstance(observation, Mapping):
        observation = {}

    nodes = row.get("candidate_next_nodes", observation.get("candidate_next_nodes"))
    candidates = row.get(
        "candidate_observations", observation.get("candidate_observations")
    )
    baseline_index = row.get(
        "baseline_candidate_index", observation.get("baseline_candidate_index")
    )
    _require(
        isinstance(nodes, list)
        and nodes
        and all(type(node) is int for node in nodes),
        "candidate_next_nodes must be nonempty integers",
    )
    _require(len(set(nodes)) == len(nodes), "candidate_next_nodes contains duplicates")
    _require(
        isinstance(candidates, list)
        and len(candidates) == len(nodes)
        and all(isinstance(candidate, Mapping) for candidate in candidates),
        "candidate_observations must align with candidate_next_nodes",
    )
    _require(
        type(baseline_index) is int and 0 <= baseline_index < len(nodes),
        "invalid baseline_candidate_index",
    )
    return list(nodes), [dict(_plain(candidate)) for candidate in candidates], baseline_index


def normalize_route_event(row: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one native multi-action Route row and retain its event identity."""

    _require(
        row.get("schema") == EVENT_SCHEMA
        or row.get("kind") in {"I3", "I3_NEXT_EDGE"},
        "expected I3 Route row",
    )
    event_ordinal = row.get("event_ordinal")
    runtime_bag_id = row.get("runtime_bag_id")
    current_node = row.get("current_node", row.get("node"))
    baseline = row.get("baseline_next_node")
    legal = row.get("legal_next_edges")
    _require(type(event_ordinal) is int and event_ordinal >= 0, "invalid event_ordinal")
    _require(type(runtime_bag_id) is int and runtime_bag_id >= 0, "invalid runtime_bag_id")
    _require(type(current_node) is int, "current_node/node is required")
    _require(type(baseline) is int, "baseline_next_node is required")
    _require(
        isinstance(legal, list)
        and len(legal) >= 2
        and all(type(node) is int for node in legal),
        "legal_next_edges must contain at least two integer nodes",
    )
    _require(len(set(legal)) == len(legal), "legal_next_edges contains duplicates")
    _require(baseline in legal, "S4 baseline is absent from legal_next_edges")
    wait_available = row.get("wait_available")
    _require(type(wait_available) is bool, "wait_available must be boolean")
    event_time = _finite_number(row.get("event_time"), "event_time", minimum=0.0)
    event_seq = row.get("event_seq")
    if event_seq is not None:
        _require(type(event_seq) is int and event_seq >= 0, "invalid event_seq")

    candidate_nodes, candidates, baseline_index = _candidate_payload(row)
    _require(candidate_nodes == list(legal), "candidate/legal edge order drifted")
    _require(candidate_nodes[baseline_index] == baseline, "candidate S4 index drifted")

    normalized = {
        "schema": EVENT_SCHEMA,
        "population_group_id": _text(
            row, "population_group_id", "population_group_sha256"
        ),
        "population_selection_id": _text(
            row,
            "population_selection_id",
            "skeleton_selection_sha256",
            "skeleton_id",
        ),
        "event_ordinal": event_ordinal,
        "runtime_bag_id": runtime_bag_id,
        "event_time": event_time,
        "current_node": current_node,
        "baseline_next_node": baseline,
        "legal_next_edges": list(legal),
        "wait_available": wait_available,
        "candidate_next_nodes": candidate_nodes,
        "candidate_observations": candidates,
        "baseline_candidate_index": baseline_index,
        "normal_flow": row.get("normal_flow")
        if type(row.get("normal_flow")) is bool
        else None,
    }
    if event_seq is not None:
        normalized["event_seq"] = event_seq
    for field in ("task_id", "segment_id", "start", "goal", "source", "leg"):
        if field in row:
            normalized[field] = _plain(row[field])
    for field in (
        "s4_v2_divergence",
        "s4_v2_diverged",
        "near_tie",
        "s4_score_margin",
        "merge_contention",
        "wait_age_seconds",
    ):
        if field in row:
            normalized[field] = _plain(row[field])
    return normalized


def event_identity(row: Mapping[str, Any]) -> dict[str, Any]:
    """Return the trace-only identity that must survive selection and replay."""

    event = row if row.get("schema") == EVENT_SCHEMA else normalize_route_event(row)
    identity = {
        "population_group_id": str(event["population_group_id"]),
        "population_selection_id": str(event["population_selection_id"]),
        "event_ordinal": int(event["event_ordinal"]),
        "runtime_bag_id": int(event["runtime_bag_id"]),
        "event_time": float(event["event_time"]),
        "current_node": int(event["current_node"]),
    }
    if event.get("event_seq") is not None:
        identity["event_seq"] = int(event["event_seq"])
    return identity


def _event_identity_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    identity = event_identity(row)
    return (
        identity["population_group_id"],
        identity["population_selection_id"],
        identity["event_ordinal"],
        identity["runtime_bag_id"],
        identity["event_time"],
        identity["current_node"],
        identity.get("event_seq"),
    )


def _event_order_key(row: Mapping[str, Any]) -> tuple[float, int, int]:
    event = row if row.get("schema") == EVENT_SCHEMA else normalize_route_event(row)
    ordinal = int(event["event_ordinal"])
    sequence = int(event.get("event_seq", ordinal))
    return float(event["event_time"]), sequence, ordinal


def _feature_values(event: Mapping[str, Any], name: str) -> list[float]:
    values: list[float] = []
    for candidate in event["candidate_observations"]:
        value = candidate.get(name)
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
        ):
            values.append(float(value))
    return values


def current_stratum_scores(row: Mapping[str, Any]) -> dict[str, float]:
    """Compute outcome-free ranking scores for the four G22 current strata."""

    event = row if row.get("schema") == EVENT_SCHEMA else normalize_route_event(row)
    queue = max(_feature_values(event, "target_queue_length") or [0.0])

    calendar_values = _feature_values(event, "target_wait_after_travel_seconds")
    if not calendar_values:
        available = _feature_values(event, "target_next_available")
        travel = _feature_values(event, "travel_time")
        calendar_values = [
            max(0.0, next_available - event["event_time"] - edge_travel)
            for next_available, edge_travel in zip(available, travel, strict=False)
        ]
    calendar = max(calendar_values or [0.0])

    explicit_contention = event.get("merge_contention")
    if (
        isinstance(explicit_contention, (int, float))
        and not isinstance(explicit_contention, bool)
        and math.isfinite(float(explicit_contention))
    ):
        contention = float(explicit_contention)
    else:
        local = _feature_values(event, "priority_local_contention")
        incoming = _feature_values(event, "target_scheduled_incoming")
        contention = max(
            [*local, *incoming, *(a + b for a, b in zip(local, incoming, strict=False))]
            or [0.0]
        )

    divergence = 0.0
    if event.get("s4_v2_divergence") is True or event.get("s4_v2_diverged") is True:
        divergence = 2.0
    elif event.get("near_tie") is True:
        divergence = 1.0
    else:
        margin = event.get("s4_score_margin")
        if (
            isinstance(margin, (int, float))
            and not isinstance(margin, bool)
            and math.isfinite(float(margin))
        ):
            divergence = 1.0 / (1.0 + abs(float(margin)))

    return {
        "high_target_queue": queue,
        "high_calendar_wait": calendar,
        "high_merge_contention": contention,
        "s4_v2_divergence_or_near_tie": divergence,
    }


def detour_release_gate(row: Mapping[str, Any]) -> dict[str, float] | None:
    """Outcome-free G0 timing hypothesis discovered by the current pilot.

    The gate only identifies exact-study candidates.  It does not authorize a
    runtime action: a long-waiting bag in a genuinely congested current queue
    must also have a physically shorter alternate that S4 rejected because
    the alternate advertises more one-hop pressure.
    """

    event = row if row.get("schema") == EVENT_SCHEMA else normalize_route_event(row)
    baseline_index = int(event["baseline_candidate_index"])
    baseline = event["candidate_observations"][baseline_index]
    wait_age = max(_feature_values(event, "priority_age_seconds") or [0.0])
    current_queue = max(_feature_values(event, "junction_queue_length") or [0.0])

    def physical(candidate: Mapping[str, Any]) -> float:
        return _finite_number(candidate.get("travel_time"), "travel_time") + _finite_number(
            candidate.get("static_potential"), "static_potential"
        )

    def pressure(candidate: Mapping[str, Any]) -> float:
        return _finite_number(
            candidate.get("target_queue_length"), "target_queue_length", minimum=0.0
        ) + _finite_number(
            candidate.get("target_scheduled_incoming"),
            "target_scheduled_incoming",
            minimum=0.0,
        )

    baseline_physical = physical(baseline)
    baseline_pressure = pressure(baseline)
    alternatives = [
        (index, candidate)
        for index, candidate in enumerate(event["candidate_observations"])
        if index != baseline_index
    ]
    if not alternatives:
        return None
    alternate_index, alternate = max(
        alternatives,
        key=lambda item: baseline_physical - physical(item[1]),
    )
    physical_saving = baseline_physical - physical(alternate)
    pressure_increase = pressure(alternate) - baseline_pressure
    if (
        wait_age < 60.0
        or current_queue < 8.0
        or physical_saving < 10.0
        or pressure_increase <= 0.0
    ):
        return None
    return {
        "wait_age_seconds": wait_age,
        "current_queue_length": current_queue,
        "physical_saving_seconds": physical_saving,
        "target_pressure_increase": pressure_increase,
        "alternate_index": float(alternate_index),
        "score": wait_age + 2.0 * current_queue + physical_saving,
    }


def select_detour_release_groups_from_jsonl(
    census_path: Path,
    *,
    target_groups: int,
    time_block_seconds: float = 900.0,
) -> list[dict[str, Any]]:
    """Stream the rich census and keep diverse G0 timing-gate candidates."""

    _require(target_groups > 0, "target_groups must be positive")
    best_by_node_block: dict[tuple[int, int], tuple[float, dict[str, Any]]] = {}
    with census_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            _require(
                isinstance(value, Mapping),
                f"{census_path}:{line_number} is not an object",
            )
            event = normalize_route_event(value)
            gate = detour_release_gate(event)
            if gate is None:
                continue
            node = int(event["current_node"])
            block = math.floor(float(event["event_time"]) / time_block_seconds)
            key = (node, block)
            score = float(gate["score"])
            previous = best_by_node_block.get(key)
            if previous is None or score > previous[0]:
                enriched = {**event, **{k: _plain(v) for k, v in value.items() if k not in event}}
                enriched.update(
                    timing_stage="current",
                    selection_stratum="detour_release_gate_g0",
                    time_block=block,
                    detour_release_gate=gate,
                    event_identity=event_identity(event),
                )
                best_by_node_block[key] = (score, enriched)
    candidates = sorted(
        (item[1] for item in best_by_node_block.values()),
        key=lambda row: (
            -float(row["detour_release_gate"]["score"]),
            int(row["event_ordinal"]),
        ),
    )
    selected: list[dict[str, Any]] = []
    used_runtime_bags: set[int] = set()
    used_nodes: set[int] = set()
    while candidates and len(selected) < target_groups:
        candidates.sort(
            key=lambda row: (
                int(row["runtime_bag_id"] not in used_runtime_bags),
                int(row["current_node"] not in used_nodes),
                float(row["detour_release_gate"]["score"]),
            ),
            reverse=True,
        )
        chosen = candidates.pop(0)
        if int(chosen["runtime_bag_id"]) in used_runtime_bags:
            continue
        selected.append(chosen)
        used_runtime_bags.add(int(chosen["runtime_bag_id"]))
        used_nodes.add(int(chosen["current_node"]))
    return selected


def _current_selection_audit(
    population: Sequence[Mapping[str, Any]],
    scores: Mapping[tuple[Any, ...], Mapping[str, float]],
    selected: Sequence[Mapping[str, Any]],
    *,
    target_groups: int,
    score_tolerance: float,
) -> dict[str, Any]:
    support_counts = {
        stratum: sum(
            float(scores[_event_identity_key(event)][stratum]) > score_tolerance
            for event in population
        )
        for stratum in CURRENT_STRATA
    }
    selected_counts = {
        stratum: sum(row.get("selection_stratum") == stratum for row in selected)
        for stratum in CURRENT_STRATA
    }
    return {
        "stratum_score_threshold_exclusive": score_tolerance,
        "stratum_support_counts": support_counts,
        "selected_stratum_counts": selected_counts,
        "unsupported_strata": [
            stratum for stratum in CURRENT_STRATA if support_counts[stratum] == 0
        ],
        "requested_group_count": target_groups,
        "selected_group_count": len(selected),
        "selection_shortfall": max(0, target_groups - len(selected)),
        "runtime_bag_ids_are_unique": (
            len({int(row["runtime_bag_id"]) for row in selected}) == len(selected)
        ),
    }


def select_current_groups_with_summary(
    rows: Iterable[Mapping[str, Any]],
    *,
    target_groups: int,
    time_block_seconds: float = 900.0,
    score_tolerance: float = CURRENT_SCORE_TOLERANCE,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Select supported current strata and return an explicit coverage audit.

    A stratum is eligible only when its outcome-free score is meaningfully
    positive. Score is the primary ordering; exact-score ties are interleaved
    across node/time cells. One runtime segment can therefore contribute at
    most one current group.
    """

    _require(type(target_groups) is int and target_groups > 0, "target_groups must be positive")
    block_seconds = _finite_number(
        time_block_seconds, "time_block_seconds", minimum=1e-12
    )
    tolerance = _finite_number(
        score_tolerance, "score_tolerance", minimum=0.0
    )
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for raw in rows:
        event = normalize_route_event(raw)
        unique.setdefault(_event_identity_key(event), event)
    population = sorted(unique.values(), key=_event_order_key)
    scores = {
        _event_identity_key(event): current_stratum_scores(event)
        for event in population
    }
    eligible_by_stratum: dict[str, list[dict[str, Any]]] = {}
    for stratum in CURRENT_STRATA:
        by_score_cell: dict[
            float, dict[tuple[int, int], list[dict[str, Any]]]
        ] = {}
        for event in population:
            score = float(scores[_event_identity_key(event)][stratum])
            if score <= tolerance:
                continue
            cell = (
                int(event["current_node"]),
                math.floor(float(event["event_time"]) / block_seconds),
            )
            by_score_cell.setdefault(score, {}).setdefault(cell, []).append(event)
        ordered: list[dict[str, Any]] = []
        for score in sorted(by_score_cell, reverse=True):
            cells = by_score_cell[score]
            ordered_cells = sorted(cells)
            depth = 0
            while True:
                appended = False
                for cell in ordered_cells:
                    if depth < len(cells[cell]):
                        ordered.append(cells[cell][depth])
                        appended = True
                if not appended:
                    break
                depth += 1
        eligible_by_stratum[stratum] = ordered
    selected: list[dict[str, Any]] = []
    used: set[tuple[Any, ...]] = set()
    used_runtime_bags: set[int] = set()
    next_index = {stratum: 0 for stratum in CURRENT_STRATA}
    while len(selected) < min(target_groups, len(population)):
        progressed = False
        for stratum in CURRENT_STRATA:
            if len(selected) >= target_groups:
                break
            candidates = eligible_by_stratum[stratum]
            index = next_index[stratum]
            while index < len(candidates):
                candidate = candidates[index]
                if (
                    _event_identity_key(candidate) not in used
                    and int(candidate["runtime_bag_id"]) not in used_runtime_bags
                ):
                    break
                index += 1
            if index >= len(candidates):
                next_index[stratum] = index
                continue
            chosen = candidates[index]
            next_index[stratum] = index + 1
            node = int(chosen["current_node"])
            block = math.floor(float(chosen["event_time"]) / block_seconds)
            selected_row = dict(_plain(chosen))
            selected_row.update(
                {
                    "timing_stage": "current",
                    "selection_stratum": stratum,
                    "selection_score": float(
                        scores[_event_identity_key(chosen)][stratum]
                    ),
                    "time_block": block,
                    "event_identity": event_identity(chosen),
                }
            )
            selected.append(selected_row)
            used.add(_event_identity_key(chosen))
            used_runtime_bags.add(int(chosen["runtime_bag_id"]))
            progressed = True
        if not progressed:
            break

    return selected, _current_selection_audit(
        population,
        scores,
        selected,
        target_groups=target_groups,
        score_tolerance=tolerance,
    )


def select_current_groups(
    rows: Iterable[Mapping[str, Any]],
    *,
    target_groups: int,
    time_block_seconds: float = 900.0,
    score_tolerance: float = CURRENT_SCORE_TOLERANCE,
) -> list[dict[str, Any]]:
    """Return the deterministic supported current panel without its audit."""

    selected, _ = select_current_groups_with_summary(
        rows,
        target_groups=target_groups,
        time_block_seconds=time_block_seconds,
        score_tolerance=score_tolerance,
    )
    return selected


def select_precursor_groups(
    current_groups: Iterable[Mapping[str, Any]],
    census_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Find the nearest strictly earlier Route event for the same runtime bag.

    Runtime task IDs are deliberately not used: two runtime segments belonging
    to one raw task must never be linked as current/precursor events.
    """

    population = [normalize_route_event(row) for row in census_rows]
    by_runtime_bag: dict[int, list[dict[str, Any]]] = {}
    for event in population:
        by_runtime_bag.setdefault(int(event["runtime_bag_id"]), []).append(event)
    for events in by_runtime_bag.values():
        events.sort(key=_event_order_key)

    selected: list[dict[str, Any]] = []
    emitted: set[tuple[tuple[Any, ...], tuple[Any, ...]]] = set()
    for raw_anchor in current_groups:
        anchor = normalize_route_event(raw_anchor)
        anchor_metadata = {
            key: _plain(raw_anchor[key])
            for key in (
                "selection_stratum",
                "selection_score",
                "time_block",
                "detour_release_gate",
            )
            if key in raw_anchor
        }
        anchor_key = _event_order_key(anchor)
        candidates = [
            event
            for event in by_runtime_bag.get(int(anchor["runtime_bag_id"]), [])
            if int(event["event_ordinal"]) < int(anchor["event_ordinal"])
            and _event_order_key(event) < anchor_key
        ]
        if not candidates:
            continue
        precursor = max(candidates, key=_event_order_key)
        pair_key = (_event_identity_key(anchor), _event_identity_key(precursor))
        if pair_key in emitted:
            continue
        emitted.add(pair_key)
        row = dict(_plain(precursor))
        row.update(
            {
                "timing_stage": "precursor",
                "event_identity": event_identity(precursor),
                "anchor_event_identity": event_identity(anchor),
                "anchor_selection_metadata": anchor_metadata,
                "precursor_event_gap": int(anchor["event_ordinal"])
                - int(precursor["event_ordinal"]),
                "precursor_time_gap_seconds": float(anchor["event_time"])
                - float(precursor["event_time"]),
            }
        )
        for key in ("selection_stratum", "time_block"):
            if key in anchor_metadata:
                row[key] = anchor_metadata[key]
        selected.append(row)
    return selected


def select_precursor_groups_from_jsonl(
    current_groups: Iterable[Mapping[str, Any]],
    census_path: Path,
) -> list[dict[str, Any]]:
    """Stream a large census and retain only nearest same-segment precursors."""

    raw_anchors = [dict(_plain(row)) for row in current_groups]
    anchors = [normalize_route_event(row) for row in raw_anchors]
    anchor_by_runtime: dict[
        int, list[tuple[tuple[Any, ...], dict[str, Any]]]
    ] = {}
    for anchor in anchors:
        anchor_by_runtime.setdefault(int(anchor["runtime_bag_id"]), []).append(
            (_event_identity_key(anchor), anchor)
        )
    best: dict[tuple[Any, ...], dict[str, Any]] = {}
    with census_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            _require(
                isinstance(value, Mapping),
                f"{census_path}:{line_number} is not an object",
            )
            runtime_bag_id = value.get("runtime_bag_id")
            if type(runtime_bag_id) is not int or runtime_bag_id not in anchor_by_runtime:
                continue
            event = normalize_route_event(value)
            for anchor_identity, anchor in anchor_by_runtime[runtime_bag_id]:
                if (
                    int(event["event_ordinal"]) >= int(anchor["event_ordinal"])
                    or _event_order_key(event) >= _event_order_key(anchor)
                ):
                    continue
                previous = best.get(anchor_identity)
                if previous is None or _event_order_key(event) > _event_order_key(previous):
                    best[anchor_identity] = event
    return select_precursor_groups(raw_anchors, best.values())


def enumerate_legal_actions(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the complete legal action set, including the implicit baseline."""

    event = row if row.get("schema") == EVENT_SCHEMA else normalize_route_event(row)
    baseline = int(event["baseline_next_node"])
    actions = [
        {
            "action_kind": "NEXT_EDGE",
            "selected_next_node": int(node),
            "is_baseline": int(node) == baseline,
        }
        for node in event["legal_next_edges"]
    ]
    if event["wait_available"] is True:
        actions.append(
            {
                "action_kind": "WAIT",
                "selected_next_node": None,
                "is_baseline": False,
            }
        )
    return actions


def _normalize_horizons(horizons: str | Sequence[str]) -> tuple[str, ...]:
    values = (horizons,) if isinstance(horizons, str) else tuple(horizons)
    _require(bool(values), "at least one horizon is required")
    _require(len(set(values)) == len(values), "duplicate horizon")
    _require(all(value in HORIZONS for value in values), "unsupported horizon")
    return values


def build_action_targets(
    row: Mapping[str, Any], *, horizons: str | Sequence[str] = "H_bag"
) -> list[dict[str, Any]]:
    """Build exact-replay treatments for all non-baseline legal actions."""

    event = row if row.get("schema") == EVENT_SCHEMA else normalize_route_event(row)
    identity = event_identity(event)
    timing_stage = str(row.get("timing_stage", "current"))
    _require(timing_stage in {"current", "precursor"}, "invalid timing_stage")
    common = {
        "schema": TARGET_SCHEMA,
        "research_profile": RESEARCH_PROFILE,
        **identity,
        "event_identity": identity,
        "timing_stage": timing_stage,
        "baseline_next_node": int(event["baseline_next_node"]),
        "legal_next_edges": [int(node) for node in event["legal_next_edges"]],
        "wait_available": bool(event["wait_available"]),
    }
    if timing_stage == "precursor":
        anchor = row.get("anchor_event_identity")
        _require(isinstance(anchor, Mapping), "precursor target lacks anchor_event_identity")
        common["anchor_event_identity"] = dict(_plain(anchor))

    targets: list[dict[str, Any]] = []
    for horizon in _normalize_horizons(horizons):
        horizon_common = {**common, "horizon": horizon}
        for action in enumerate_legal_actions(event):
            if action["is_baseline"]:
                continue
            if action["action_kind"] == "NEXT_EDGE":
                targets.append(
                    {
                        **horizon_common,
                        "action_kind": "NEXT_EDGE",
                        "selected_next_node": int(action["selected_next_node"]),
                    }
                )
            else:
                targets.append({**horizon_common, "action_kind": "WAIT"})
    return targets


def target_identity(row: Mapping[str, Any]) -> tuple[Any, ...]:
    """Return the full event+horizon+action identity used to match native pairs."""

    action = row.get("action_kind")
    _require(action in {"NEXT_EDGE", "WAIT"}, "invalid action_kind")
    selected = row.get("selected_next_node")
    if action == "NEXT_EDGE":
        _require(type(selected) is int, "NEXT_EDGE target lacks selected_next_node")
    else:
        _require(selected is None, "WAIT target fabricated selected_next_node")
        selected = None
    return (
        row.get("schema", row.get("target_schema")),
        row.get("population_group_id"),
        row.get("population_selection_id"),
        row.get("event_ordinal"),
        row.get("runtime_bag_id"),
        row.get("event_time"),
        row.get("current_node"),
        row.get("event_seq"),
        row.get("timing_stage"),
        row.get("horizon"),
        action,
        selected,
    )


def stable_choice_group_id(row: Mapping[str, Any]) -> str:
    """Build a readable, cross-file-stable ID from the preserved event identity."""

    event = row if row.get("schema") == EVENT_SCHEMA else normalize_route_event(row)
    stage = str(row.get("timing_stage", "current"))
    _require(stage in {"current", "precursor"}, "invalid timing_stage")
    fields = [
        "g22",
        f"stage={stage}",
        f"group={event['population_group_id']}",
        f"selection={event['population_selection_id']}",
        f"event={int(event['event_ordinal'])}",
        f"bag={int(event['runtime_bag_id'])}",
        f"time={float(event['event_time'])!r}",
        f"node={int(event['current_node'])}",
    ]
    if event.get("event_seq") is not None:
        fields.append(f"seq={int(event['event_seq'])}")
    return "|".join(fields)


def build_timing_plan(
    groups: Sequence[Mapping[str, Any]], *, h_system_groups: int = 0
) -> dict[str, Any]:
    """Assign H_bag to all groups and additionally H_system to a prefix."""

    _require(type(h_system_groups) is int, "h_system_groups must be an integer")
    _require(0 <= h_system_groups <= len(groups), "invalid h_system_groups")
    planned_groups: list[dict[str, Any]] = []
    targets: list[dict[str, Any]] = []
    for index, raw in enumerate(groups):
        event = normalize_route_event(raw)
        enriched = {
            **event,
            **{
                key: _plain(value)
                for key, value in raw.items()
                if key not in event
            },
        }
        horizons = ("H_bag", "H_system") if index < h_system_groups else ("H_bag",)
        group_targets = build_action_targets(enriched, horizons=horizons)
        group_out = dict(_plain(enriched))
        group_out["assigned_horizons"] = list(horizons)
        group_out["legal_actions"] = enumerate_legal_actions(event)
        group_out["treatment_count"] = len(group_targets)
        planned_groups.append(group_out)
        targets.extend(group_targets)
    _require(
        len({target_identity(row) for row in targets}) == len(targets),
        "duplicate target identity",
    )
    return {
        "schema": PLAN_SCHEMA,
        "research_profile": RESEARCH_PROFILE,
        "groups": planned_groups,
        "targets": targets,
        "counts": {
            "group_count": len(planned_groups),
            "h_bag_group_count": len(planned_groups),
            "h_system_group_count": h_system_groups,
            "target_count": len(targets),
        },
    }


def load_native_backend(binary: Path) -> Any:
    """Load the optional native extension on demand, never at module import."""

    resolved = binary.resolve(strict=True)
    specification = importlib.util.spec_from_file_location("czr005_cpp", resolved)
    if specification is None or specification.loader is None:
        raise ActionTimingError(f"cannot load native backend: {resolved}")
    module = importlib.util.module_from_spec(specification)
    sys.modules["czr005_cpp"] = module
    specification.loader.exec_module(module)
    return module


def scan_native_route_events(backend: Any, native_arguments: Sequence[Any]) -> list[dict[str, Any]]:
    """Call the existing native census seam with the G22 profile."""

    scan = getattr(backend, "g4irsf15_scan_causal_skeletons_from_records", None)
    _require(callable(scan), "native backend omitted the causal census seam")
    payload = scan(*native_arguments, RESEARCH_PROFILE)
    _require(isinstance(payload, Mapping), "native census returned no object")
    _require(payload.get("census_complete") is True, "native census did not complete")
    rows = payload.get("skeletons")
    _require(isinstance(rows, list), "native census omitted skeletons")
    return [
        normalize_route_event(row)
        for row in rows
        if isinstance(row, Mapping) and row.get("kind") in {"I3", "I3_NEXT_EDGE"}
    ]


def build_2x_native_arguments(
    root: Path = ROOT,
) -> tuple[list[Any], list[dict[str, Any]], dict[str, Any]]:
    """Build the exact G22 2x input without routing through G15's fixed 1x seam."""

    from scripts.eval import g4irsf15_causal_campaign as g15
    from scripts.eval import run_g4irsf19_bounded_capacity as g19
    from scripts.eval.g4irsf11_fixed_map import (
        assert_canonical_map,
        canonical_graph_records,
    )

    rows, descriptor = g19.load_g18_scale_input(2, root=root)
    _require(len(rows) == 87_206, "G22 2x input must contain 87,206 segments")
    nodes, edges, heuristic = canonical_graph_records(assert_canonical_map())
    model = g15._load_model(root)
    # Exact H_system aggregation requires one denominator per raw bag and it
    # must not be later than any segment release.  The scaled G10 artifact can
    # retain a sub-second Java timestamp while `pass_time` is integerized, so
    # use the earliest actual segment release for every segment of that task.
    java_release_by_task: dict[int, float] = {}
    for row in rows:
        task_id = int(row["task_id"])
        release = _finite_number(row.get("pass_time"), "pass_time")
        java_release_by_task[task_id] = min(
            release, java_release_by_task.get(task_id, release)
        )
    original_entry_times = [java_release_by_task[int(row["task_id"])] for row in rows]
    arguments: list[Any] = [
        nodes,
        edges,
        heuristic,
        g19._binding_rows(rows),
        model["w1"],
        model["b1"],
        model["w2"],
        model["b2"],
        model["risk_margin"],
        model["risk_bottleneck"],
        model["sha256"],
        original_entry_times,
    ]
    return arguments, rows, {
        **dict(descriptor),
        "exact_raw_bag_entry_denominator": "earliest_java_segment_release_time",
    }


def run_native_action_pairs(
    backend: Any,
    native_arguments: Sequence[Any],
    targets: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    run = getattr(backend, "g4irsf15_run_causal_target_pairs_from_records", None)
    _require(callable(run), "native backend omitted the exact pair seam")
    payload = run(*native_arguments, [dict(row) for row in targets], RESEARCH_PROFILE)
    _require(isinstance(payload, Mapping), "native pair run returned no object")
    pairs = payload.get("pairs")
    _require(isinstance(pairs, list), "native pair run omitted pairs")
    return dict(payload)


def _native_pair_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    selected = row.get("selected_next_node")
    if row.get("action_kind") == "WAIT":
        selected = None
    return (
        row.get("population_group_id"),
        row.get("population_selection_id"),
        row.get("event_ordinal"),
        row.get("horizon"),
        row.get("action_kind"),
        selected,
    )


def compact_action_groups(
    groups: Sequence[Mapping[str, Any]],
    pair_payload: Mapping[str, Any],
    *,
    horizon: str = "H_bag",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Join complete exact action sets while preserving timing and future summaries."""

    from scripts.eval import run_g4irsf21_route_action_sets as g21

    pairs = pair_payload.get("pairs")
    _require(isinstance(pairs, list), "pair payload omitted pairs")
    pair_by_key = {
        _native_pair_key(row): row
        for row in pairs
        if isinstance(row, Mapping)
    }
    completed: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for raw in groups:
        group = normalize_route_event(raw)
        timing_stage = str(raw.get("timing_stage", "current"))
        treatments = build_action_targets({**group, **dict(raw)}, horizons=horizon)
        resolved: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
        reasons: list[str] = []
        for target in treatments:
            key = _native_pair_key(target)
            pair = pair_by_key.get(key)
            if pair is None:
                reasons.append("PAIR_MISSING")
                continue
            reason = g21._pair_failure(pair)
            if reason is not None:
                reasons.append(str(reason))
                continue
            resolved.append((target, pair))
        if reasons or len(resolved) != len(treatments):
            failures.append(
                {
                    "event_identity": event_identity(group),
                    "timing_stage": timing_stage,
                    "horizon": horizon,
                    "reasons": reasons or ["PAIR_SET_INCOMPLETE"],
                }
            )
            continue

        baseline_summaries = [
            pair.get("baseline", {}).get("local_future_summary")
            for _, pair in resolved
            if isinstance(pair.get("baseline"), Mapping)
        ]
        _require(
            baseline_summaries
            and all(isinstance(row, Mapping) for row in baseline_summaries),
            "complete G22 action set omitted baseline local future summary",
        )
        baseline_summary = dict(baseline_summaries[0])
        _require(
            all(dict(row) == baseline_summary for row in baseline_summaries[1:]),
            "same-state baseline local future summaries disagree",
        )
        treatment_by_action: dict[tuple[str, int | None], Mapping[str, Any]] = {}
        for target, pair in resolved:
            selected = target.get("selected_next_node")
            action_key = (
                str(target["action_kind"]),
                int(selected) if type(selected) is int else None,
            )
            treatment_by_action[action_key] = pair

        candidates: list[dict[str, Any]] = []
        baseline = int(group["baseline_next_node"])
        for index, node in enumerate(group["legal_next_edges"]):
            if int(node) == baseline:
                utility = 0.0
                future = baseline_summary
            else:
                pair = treatment_by_action[("NEXT_EDGE", int(node))]
                utility = -float(g21._completion_delta(pair))
                future = dict(pair["treatment"]["local_future_summary"])
            candidates.append(
                {
                    "action_kind": "NEXT_EDGE",
                    "selected_next_node": int(node),
                    "legal": True,
                    "native_features": dict(group["candidate_observations"][index]),
                    "utility": utility,
                    "local_future_summary": future,
                }
            )
        if group["wait_available"]:
            pair = treatment_by_action[("WAIT", None)]
            candidates.append(
                {
                    "action_kind": "WAIT",
                    "selected_next_node": None,
                    "legal": True,
                    "native_features": None,
                    "utility": -float(g21._completion_delta(pair)),
                    "local_future_summary": dict(
                        pair["treatment"]["local_future_summary"]
                    ),
                }
            )
        completed.append(
            {
                "schema_id": "czr005.g4irsf22.timed_local_action_set.v1",
                "choice_group_id": stable_choice_group_id(
                    {**group, "timing_stage": timing_stage}
                ),
                "split_group": raw.get("task_id", group["runtime_bag_id"]),
                "source_scale": 2,
                "horizon": horizon,
                "timing_stage": timing_stage,
                "selection_stratum": raw.get("selection_stratum"),
                "selection_score": raw.get("selection_score"),
                "time_block": raw.get("time_block"),
                "event_identity": event_identity(group),
                "task_id": raw.get("task_id"),
                "segment_id": raw.get("segment_id"),
                "normal_flow": group.get("normal_flow"),
                "wait_age_seconds": float(group.get("wait_age_seconds", 0.0)),
                "s4_index": list(group["legal_next_edges"]).index(baseline),
                "full_legal_action_set_labeled": True,
                "oracle_summary_is_offline_only": True,
                "candidates": candidates,
            }
        )
    return completed, failures


_H_SYSTEM_RAW_BAG_METRICS = (
    ("mean_total", "original_entry_mean_minutes", 60.0),
    ("mean_source", "source_wait_mean_minutes", 60.0),
    ("mean_network", "network_time_mean_minutes", 60.0),
    ("median_total", "original_entry_median_seconds", 1.0),
    ("p95_total", "original_entry_p95_seconds", 1.0),
    ("p99_total", "original_entry_p99_seconds", 1.0),
    ("max_total", "original_entry_max_seconds", 1.0),
)


def _raw_bag_metrics_seconds(
    branch: Mapping[str, Any], label: str
) -> tuple[dict[str, float], int, str]:
    metrics = branch.get("raw_bag_cohort_metrics")
    _require(isinstance(metrics, Mapping), f"{label} omitted raw_bag_cohort_metrics")
    _require(
        metrics.get("comparison_eligible") is True,
        f"{label} raw-bag comparison is ineligible",
    )
    count = metrics.get("selected_raw_bag_count")
    _require(type(count) is int and count > 0, f"{label} raw-bag count is invalid")
    denominator = metrics.get("primary_denominator")
    _require(
        isinstance(denominator, str) and bool(denominator),
        f"{label} raw-bag denominator is missing",
    )
    values = {
        output_name: _finite_number(
            metrics.get(source_name),
            f"{label}.{source_name}",
            minimum=0.0,
        )
        * scale
        for output_name, source_name, scale in _H_SYSTEM_RAW_BAG_METRICS
    }
    return values, count, denominator


def compact_h_system_groups(
    groups: Sequence[Mapping[str, Any]],
    pair_payload: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Compact complete H_system actions using only full raw-bag metrics.

    Direct affected-bag completion deltas are intentionally ignored here.
    Every reported value is treatment minus baseline on the native full-system
    raw-bag denominator.
    """

    from scripts.eval import run_g4irsf21_route_action_sets as g21

    pairs = pair_payload.get("pairs")
    _require(isinstance(pairs, list), "pair payload omitted pairs")
    pair_by_key: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    for row in pairs:
        if not isinstance(row, Mapping):
            continue
        key = _native_pair_key(row)
        _require(key not in pair_by_key, "duplicate native pair identity")
        pair_by_key[key] = row

    completed: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for raw in groups:
        assigned = raw.get("assigned_horizons")
        if assigned is not None:
            _require(
                isinstance(assigned, list), "assigned_horizons must be a list"
            )
            if "H_system" not in assigned:
                continue
        group = normalize_route_event(raw)
        timing_stage = str(raw.get("timing_stage", "current"))
        targets = build_action_targets({**group, **dict(raw)}, horizons="H_system")
        resolved: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
        reasons: list[str] = []
        for target in targets:
            pair = pair_by_key.get(_native_pair_key(target))
            if pair is None:
                reasons.append("PAIR_MISSING")
                continue
            reason = g21._pair_failure(pair)
            if reason is not None:
                reasons.append(str(reason))
                continue
            resolved.append((target, pair))
        if reasons or len(resolved) != len(targets):
            failures.append(
                {
                    "event_identity": event_identity(group),
                    "timing_stage": timing_stage,
                    "horizon": "H_system",
                    "reasons": reasons or ["PAIR_SET_INCOMPLETE"],
                }
            )
            continue

        group_rows: list[dict[str, Any]] = []
        metric_error: str | None = None
        for target, pair in resolved:
            baseline = pair.get("baseline")
            treatment = pair.get("treatment")
            try:
                _require(
                    isinstance(baseline, Mapping)
                    and isinstance(treatment, Mapping),
                    "H_system pair omitted baseline/treatment",
                )
                baseline_metrics, baseline_count, baseline_denominator = (
                    _raw_bag_metrics_seconds(baseline, "baseline")
                )
                treatment_metrics, treatment_count, treatment_denominator = (
                    _raw_bag_metrics_seconds(treatment, "treatment")
                )
                _require(
                    baseline_count == treatment_count,
                    "H_system raw-bag counts disagree",
                )
                _require(
                    baseline_denominator == treatment_denominator,
                    "H_system raw-bag denominators disagree",
                )
            except ActionTimingError as exc:
                metric_error = str(exc)
                break

            delta = {
                name: float(treatment_metrics[name]) - float(baseline_metrics[name])
                for name, _, _ in _H_SYSTEM_RAW_BAG_METRICS
            }
            formal_evaluated = pair.get("formal_hard_gate_evaluated") is True
            formal_pass = pair.get("formal_hard_gate_pass") is True
            live_pass = pair.get("live_safety_pass") is True
            hard_gate_pass = pair.get("hard_gate_pass") is True
            group_rows.append(
                {
                    "schema": H_SYSTEM_SUMMARY_SCHEMA,
                    "choice_group_id": stable_choice_group_id(
                        {**group, "timing_stage": timing_stage}
                    ),
                    "event_identity": event_identity(group),
                    "task_id": raw.get("task_id"),
                    "segment_id": raw.get("segment_id"),
                    "timing_stage": timing_stage,
                    "horizon": "H_system",
                    "action_kind": str(target["action_kind"]),
                    "selected_next_node": target.get("selected_next_node"),
                    "full_legal_action_set_labeled": True,
                    "delta_direction": "TREATMENT_MINUS_BASELINE",
                    "raw_bag_count": baseline_count,
                    "raw_bag_primary_denominator": baseline_denominator,
                    "raw_bag_metrics_seconds": {
                        "baseline": baseline_metrics,
                        "treatment": treatment_metrics,
                        "treatment_minus_baseline": delta,
                    },
                    "pair_status": pair.get("pair_status"),
                    "same_state_start": pair.get("same_state_start") is True,
                    "action_changed": pair.get("action_changed") is True,
                    "pair_complete": pair.get("pair_complete") is True,
                    "live_safety_pass": live_pass,
                    "formal_hard_gate_evaluated": formal_evaluated,
                    "formal_hard_gate_pass": formal_pass,
                    "hard_gate_pass": hard_gate_pass,
                    "formal_and_live_gate_pass": (
                        formal_evaluated
                        and formal_pass
                        and live_pass
                        and hard_gate_pass
                    ),
                    "hard_gate_fail_reasons": _plain(
                        pair.get("hard_gate_fail_reasons", [])
                    ),
                }
            )
        if metric_error is not None:
            failures.append(
                {
                    "event_identity": event_identity(group),
                    "timing_stage": timing_stage,
                    "horizon": "H_system",
                    "reasons": [f"RAW_BAG_METRICS_INVALID: {metric_error}"],
                }
            )
            continue
        completed.extend(group_rows)
    return completed, failures


def _read_rows(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    stripped = text.lstrip()
    value: Any = None
    parsed_single_document = False
    if stripped.startswith("["):
        value = json.loads(text)
        parsed_single_document = True
    elif stripped.startswith("{"):
        try:
            value = json.loads(text)
            parsed_single_document = True
        except json.JSONDecodeError:
            # Multiple JSON objects beginning with "{" are ordinary JSONL.
            parsed_single_document = False
    if parsed_single_document:
        if isinstance(value, list):
            rows = value
        elif isinstance(value, Mapping):
            wrapper_key = next(
                (key for key in ("skeletons", "rows", "groups") if key in value),
                None,
            )
            rows = value[wrapper_key] if wrapper_key is not None else [value]
        else:
            rows = None
        _require(isinstance(rows, list), f"{path} contains no row list")
        return [dict(row) for row in rows if isinstance(row, Mapping)]
    rows = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        _require(isinstance(row, Mapping), f"{path}:{line_number} is not an object")
        rows.append(dict(row))
    return rows


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_plain(value), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(_plain(row), sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", type=Path)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--census-output", type=Path)
    parser.add_argument("--stage", choices=("current", "precursor"), default="current")
    parser.add_argument(
        "--preselected",
        action="store_true",
        help="Treat --census rows as an already selected panel.",
    )
    parser.add_argument("--anchors", type=Path)
    parser.add_argument("--target-groups", type=int, default=256)
    parser.add_argument(
        "--event-ordinal",
        type=int,
        action="append",
        help="Optionally retain only these preselected native event ordinals.",
    )
    parser.add_argument("--h-system-groups", type=int, default=64)
    parser.add_argument("--time-block-seconds", type=float, default=900.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--groups-output", type=Path)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--run-pairs", action="store_true")
    parser.add_argument("--pairs-output", type=Path)
    parser.add_argument(
        "--dataset-output",
        type=Path,
        help="H_bag timed complete-action-set JSONL only.",
    )
    parser.add_argument(
        "--h-system-output",
        type=Path,
        help="Required with H_system pair runs; writes raw-bag system deltas only.",
    )
    parser.add_argument("--failures-output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        backend = None
        native_arguments = None
        input_descriptor = None
        selection_audit: dict[str, Any] = {}
        if arguments.binary is not None:
            backend = load_native_backend(arguments.binary)
        if arguments.census is not None:
            census = _read_rows(arguments.census)
        else:
            _require(backend is not None, "--binary is required without --census")
            native_arguments, _, input_descriptor = build_2x_native_arguments(ROOT)
            census = scan_native_route_events(backend, native_arguments)
            if arguments.census_output is not None:
                _write_jsonl(arguments.census_output, census)
        if arguments.preselected:
            groups = [dict(row) for row in census[: arguments.target_groups]]
            _require(
                all(
                    str(row.get("timing_stage", arguments.stage))
                    == arguments.stage
                    for row in groups
                ),
                "preselected timing_stage disagrees with --stage",
            )
            if arguments.stage == "current":
                _, selection_audit = select_current_groups_with_summary(
                    census,
                    target_groups=arguments.target_groups,
                    time_block_seconds=arguments.time_block_seconds,
                )
        elif arguments.stage == "current":
            groups, selection_audit = select_current_groups_with_summary(
                census,
                target_groups=arguments.target_groups,
                time_block_seconds=arguments.time_block_seconds,
            )
        else:
            _require(arguments.anchors is not None, "--anchors is required for precursor")
            anchors = _read_rows(arguments.anchors)
            groups = select_precursor_groups(anchors, census)[: arguments.target_groups]
        if arguments.event_ordinal:
            requested_ordinals = set(arguments.event_ordinal)
            groups = [
                row
                for row in groups
                if int(row["event_ordinal"]) in requested_ordinals
            ]
            _require(groups, "--event-ordinal matched no selected groups")
        if arguments.stage == "current":
            selected_counts = {
                stratum: sum(
                    row.get("selection_stratum") == stratum for row in groups
                )
                for stratum in CURRENT_STRATA
            }
            selection_audit.update(
                {
                    "selected_stratum_counts": selected_counts,
                    "requested_group_count": arguments.target_groups,
                    "selected_group_count": len(groups),
                    "selection_shortfall": max(
                        0, arguments.target_groups - len(groups)
                    ),
                    "runtime_bag_ids_are_unique": (
                        len({int(row["runtime_bag_id"]) for row in groups})
                        == len(groups)
                    ),
                }
            )
        h_system_groups = min(arguments.h_system_groups, len(groups))
        plan = build_timing_plan(groups, h_system_groups=h_system_groups)
        _write_jsonl(arguments.output, plan["targets"])
        groups_path = arguments.groups_output or arguments.output.with_suffix(
            ".groups.jsonl"
        )
        _write_jsonl(groups_path, plan["groups"])
        summary_path = arguments.summary or arguments.output.with_suffix(".summary.json")
        _write_json(
            summary_path,
            {
                "schema": plan["schema"],
                "research_profile": plan["research_profile"],
                "stage": arguments.stage,
                "requested_group_count": arguments.target_groups,
                "input_descriptor": input_descriptor,
                "current_selection": selection_audit
                if arguments.stage == "current"
                else None,
                **plan["counts"],
            },
        )
        if arguments.run_pairs:
            _require(backend is not None, "--run-pairs requires --binary")
            if h_system_groups > 0:
                _require(
                    arguments.h_system_output is not None,
                    "--h-system-output is required when H_system groups are run",
                )
            if native_arguments is None:
                native_arguments, _, input_descriptor = build_2x_native_arguments(ROOT)
            pair_payload = run_native_action_pairs(
                backend, native_arguments, plan["targets"]
            )
            pairs_output = arguments.pairs_output or arguments.output.with_suffix(
                ".pairs.json"
            )
            _write_json(pairs_output, pair_payload)
            datasets, failures = compact_action_groups(
                plan["groups"], pair_payload, horizon="H_bag"
            )
            dataset_output = arguments.dataset_output or arguments.output.with_suffix(
                ".dataset.jsonl"
            )
            failures_output = arguments.failures_output or arguments.output.with_suffix(
                ".failures.json"
            )
            _write_jsonl(dataset_output, datasets)
            if h_system_groups > 0:
                h_system_rows, h_system_failures = compact_h_system_groups(
                    plan["groups"], pair_payload
                )
                _write_jsonl(arguments.h_system_output, h_system_rows)
                failures.extend(h_system_failures)
            _write_json(failures_output, failures)
        print(json.dumps({"stage": arguments.stage, **plan["counts"]}, sort_keys=True))
        return 0
    except (ActionTimingError, OSError, TypeError, json.JSONDecodeError) as exc:
        print(f"G22 action-timing planning failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
