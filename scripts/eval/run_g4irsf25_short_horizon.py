#!/usr/bin/env python3
"""Run the G25 same-checkpoint, short-horizon corridor campaign.

The campaign is intentionally a thin layer over the existing G20--G22 native
scan and causal replay seams.  It selects real S4 route boundaries at the four
registered split/rejoin corridors, changes only the first edge, then lets the
ordinary S4/J2/E2 controller run until reconvergence plus a short settling
window (or a retained 600 second timeout).

Only the compact, grouped learning rows are published.  Native pair payloads
live below ``outputs/runstate`` so an interrupted campaign can resume without
turning large replay sidecars into repository artifacts.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import multiprocessing
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from scripts.eval import g4irsf25_clcr_learning as learning
from scripts.eval import run_g4irsf22_action_timing as g22


PAIR_SCHEMA = learning.PAIR_SCHEMA
SUMMARY_SCHEMA = "czr005.g4irsf25.short_horizon_summary.v1"
CAMPAIGN_REVISION = "g25-short-horizon-r2-earliest-merge-request"
RESEARCH_PROFILE = g22.RESEARCH_PROFILE

DEFAULT_DATASET = Path(
    "artifacts/datasets/g4irsf25_short_horizon_pairs_compact.jsonl"
)
DEFAULT_TABLE = Path("outputs/tables/g4irsf25_short_horizon_pairs.json")
DEFAULT_REPORT = Path("outputs/reports/g4irsf25_short_horizon_oracle.md")
DEFAULT_RUN_STATE = Path("outputs/runstate/g4irsf25_short_horizon")


# These are the real G24 split/rejoin arms.  Paths, support and static duration
# are descriptive arm metadata; all supervised costs below come from a fresh
# same-checkpoint native replay.
_CORRIDOR_PATH_ARMS: dict[int, tuple[dict[str, Any], ...]] = {
    6: (
        {
            "first_edge": 8,
            "rejoin_node": 13,
            "corridor_nodes": [6, 8, 11, 13],
            "support": 2962,
            "static_duration_seconds": 17.2,
        },
        {
            "first_edge": 12,
            "rejoin_node": 13,
            "corridor_nodes": [6, 12, 13],
            "support": 3996,
            "static_duration_seconds": 14.0,
        },
    ),
    9: (
        {
            "first_edge": 7,
            "rejoin_node": 14,
            "corridor_nodes": [9, 7, 8, 11, 14],
            "support": 6202,
            "static_duration_seconds": 20.4,
        },
        {
            "first_edge": 10,
            "rejoin_node": 14,
            "corridor_nodes": [9, 10, 15, 14],
            "support": 599,
            "static_duration_seconds": 24.0,
        },
    ),
    16: (
        {
            "first_edge": 17,
            "rejoin_node": 24,
            "corridor_nodes": [16, 17, 18, 22, 24],
            "support": 9699,
            "static_duration_seconds": 24.0,
        },
        {
            "first_edge": 21,
            "rejoin_node": 24,
            "corridor_nodes": [16, 21, 23, 24],
            "support": 576,
            "static_duration_seconds": 29.2,
        },
    ),
    19: (
        {
            "first_edge": 18,
            "rejoin_node": 26,
            "corridor_nodes": [19, 18, 22, 26],
            "support": 2443,
            "static_duration_seconds": 18.0,
        },
        {
            "first_edge": 25,
            "rejoin_node": 26,
            "corridor_nodes": [19, 25, 26],
            "support": 42,
            "static_duration_seconds": 17.2,
        },
    ),
}


def _arms_with_rejoin_neighborhood() -> dict[int, tuple[dict[str, Any], ...]]:
    """Extend fixed paths with the canonical rejoin outgoing neighborhood."""

    map_path = ROOT / "data/processed/maps/map2.json"
    document = json.loads(map_path.read_text(encoding="utf-8"))
    edges = document.get("edges")
    if not isinstance(edges, list):
        raise ValueError("canonical map omitted edges")
    outgoing: dict[int, list[int]] = defaultdict(list)
    for row in edges:
        if not isinstance(row, Mapping):
            continue
        start = row.get("start")
        end = row.get("end")
        if type(start) is int and type(end) is int:
            outgoing[start].append(end)
    result: dict[int, tuple[dict[str, Any], ...]] = {}
    for branch, arms in _CORRIDOR_PATH_ARMS.items():
        enriched: list[dict[str, Any]] = []
        for arm in arms:
            rejoin = int(arm["rejoin_node"])
            neighborhood = sorted(set(outgoing.get(rejoin, [])))
            if not neighborhood:
                raise ValueError(f"canonical rejoin {rejoin} has no outgoing neighborhood")
            nodes = list(dict.fromkeys([*arm["corridor_nodes"], *neighborhood]))
            enriched.append(
                {
                    **arm,
                    "corridor_nodes": nodes,
                    "rejoin_outgoing_nodes": neighborhood,
                }
            )
        result[branch] = tuple(enriched)
    return result


CORRIDOR_ARMS = _arms_with_rejoin_neighborhood()


class ShortHorizonCampaignError(ValueError):
    """Raised when a scan, pair, or compact row violates the G25 contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ShortHorizonCampaignError(message)


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(_plain(value), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _atomic_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(_plain(row), sort_keys=True) + "\n")
    temporary.replace(path)


def _finite(value: Any, label: str) -> float:
    _require(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value)),
        f"{label} must be finite",
    )
    return float(value)


def _corridor_edges(branch: int) -> tuple[int, ...]:
    return tuple(int(arm["first_edge"]) for arm in CORRIDOR_ARMS[branch])


def corridor_union_nodes(branch: int) -> list[int]:
    """Return the local integration domain without scanning the runtime graph."""

    seen: set[int] = set()
    result: list[int] = []
    for arm in CORRIDOR_ARMS[branch]:
        neighborhood = set(int(node) for node in arm["rejoin_outgoing_nodes"])
        for node in arm["corridor_nodes"]:
            if int(node) in neighborhood:
                continue
            if int(node) not in seen:
                seen.add(int(node))
                result.append(int(node))
    for arm in CORRIDOR_ARMS[branch]:
        for node in arm["rejoin_outgoing_nodes"]:
            if int(node) not in seen:
                seen.add(int(node))
                result.append(int(node))
    return result


def _candidate_rows(event: Mapping[str, Any]) -> tuple[list[int], list[dict[str, Any]], int]:
    nodes = event.get("candidate_next_nodes")
    candidates = event.get("candidate_observations")
    baseline_index = event.get("baseline_candidate_index")
    _require(
        isinstance(nodes, list)
        and isinstance(candidates, list)
        and len(nodes) == len(candidates)
        and all(type(node) is int for node in nodes)
        and all(isinstance(row, Mapping) for row in candidates),
        "candidate observation shape drifted",
    )
    _require(
        type(baseline_index) is int and 0 <= baseline_index < len(nodes),
        "baseline candidate index drifted",
    )
    return list(nodes), [dict(_plain(row)) for row in candidates], baseline_index


def local_pressure(event: Mapping[str, Any]) -> float:
    """One outcome-free pressure scalar used only for balanced sampling."""

    branch = int(event["current_node"])
    nodes, candidates, _ = _candidate_rows(event)
    by_node = dict(zip(nodes, candidates))
    values = []
    for edge in _corridor_edges(branch):
        candidate = by_node[edge]
        values.append(
            _finite(candidate["target_queue_length"], "target_queue_length")
            + _finite(
                candidate["target_scheduled_incoming"],
                "target_scheduled_incoming",
            )
        )
    return max(values)


def eligible_corridor_events(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Retain real branch decisions where both registered arms are legal.

    No outcome, checkpoint digest, or future continuation is consulted.  A
    registered arm with an advertised physical fault is excluded because it
    is not a legal first-edge intervention under the existing shield.  Each
    bag contributes only its earliest registered event at a branch: later
    wakeups belong to the already-created merge request and are not a new
    first-edge action opportunity.
    """

    earliest: dict[tuple[int, int], dict[str, Any]] = {}
    for raw in rows:
        try:
            event = g22.normalize_route_event(raw)
        except (g22.ActionTimingError, KeyError, TypeError, ValueError):
            continue
        branch = int(event["current_node"])
        if branch not in CORRIDOR_ARMS:
            continue
        expected = set(_corridor_edges(branch))
        legal = set(int(node) for node in event["legal_next_edges"])
        if not expected.issubset(legal) or int(event["baseline_next_node"]) not in expected:
            continue
        nodes, candidates, _ = _candidate_rows(event)
        by_node = dict(zip(nodes, candidates))
        if any(bool(by_node[edge].get("advertised_fault", False)) for edge in expected):
            continue
        enriched = dict(event)
        enriched["selection_pressure"] = local_pressure(event)
        identity = (int(event["runtime_bag_id"]), branch)
        incumbent = earliest.get(identity)
        event_key = (
            int(enriched["event_ordinal"]),
            int(enriched["event_seq"]),
            float(enriched["event_time"]),
            str(enriched["population_selection_id"]),
        )
        if incumbent is None:
            earliest[identity] = enriched
            continue
        incumbent_key = (
            int(incumbent["event_ordinal"]),
            int(incumbent["event_seq"]),
            float(incumbent["event_time"]),
            str(incumbent["population_selection_id"]),
        )
        if event_key < incumbent_key:
            earliest[identity] = enriched
    eligible = list(earliest.values())
    eligible.sort(
        key=lambda row: (
            float(row["event_time"]),
            int(row["event_ordinal"]),
            int(row["runtime_bag_id"]),
        )
    )
    return eligible


def _quantile_bin(value: float, ordered_values: Sequence[float], bins: int) -> int:
    _require(bins > 0 and bool(ordered_values), "quantile bins need observations")
    # Rank-based bins are deterministic under ties and require no statistics
    # dependency.  Equal values intentionally stay in the same bin.
    less = sum(candidate < value for candidate in ordered_values)
    return min(bins - 1, (less * bins) // len(ordered_values))


def _round_robin_cells(
    rows: Sequence[dict[str, Any]], target: int, *, bins: int
) -> list[dict[str, Any]]:
    if not rows or target <= 0:
        return []
    times = sorted(float(row["event_time"]) for row in rows)
    pressures = sorted(float(row["selection_pressure"]) for row in rows)
    cells: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        time_bin = _quantile_bin(float(row["event_time"]), times, bins)
        pressure_bin = _quantile_bin(
            float(row["selection_pressure"]), pressures, bins
        )
        enriched = dict(row)
        enriched["time_quantile"] = time_bin
        enriched["pressure_quantile"] = pressure_bin
        enriched["selection_stratum"] = (
            f"branch={int(row['current_node'])}|time=q{time_bin}|pressure=q{pressure_bin}"
        )
        cells[(time_bin, pressure_bin)].append(enriched)
    for values in cells.values():
        values.sort(
            key=lambda row: (
                float(row["event_time"]),
                int(row["event_ordinal"]),
                int(row["runtime_bag_id"]),
            )
        )
    selected: list[dict[str, Any]] = []
    keys = sorted(cells)
    while len(selected) < min(target, len(rows)):
        progressed = False
        for key in keys:
            if cells[key] and len(selected) < target:
                selected.append(cells[key].pop(0))
                progressed = True
        if not progressed:
            break
    return selected


def select_balanced_checkpoints(
    rows: Sequence[Mapping[str, Any]],
    *,
    target: int,
    load_scale: int,
    bins: int = 4,
) -> list[dict[str, Any]]:
    """Balance deterministically across branch, time, and local pressure."""

    _require(target > 0, "target must be positive")
    _require(load_scale in {1, 2}, "load_scale must be 1 or 2")
    population = eligible_corridor_events(rows)
    _require(population, f"{load_scale}x scan has no registered corridor checkpoint")
    branches = sorted(CORRIDOR_ARMS)
    quotas = {branch: target // len(branches) for branch in branches}
    for branch in branches[: target % len(branches)]:
        quotas[branch] += 1
    selected: list[dict[str, Any]] = []
    for branch in branches:
        members = [row for row in population if int(row["current_node"]) == branch]
        selected.extend(_round_robin_cells(members, quotas[branch], bins=bins))

    # If a rare branch cannot fill its quota, fill from the remaining real
    # events while preserving the same deterministic event order.
    identities = {
        (int(row["event_ordinal"]), int(row["runtime_bag_id"])) for row in selected
    }
    remaining = [
        row
        for row in population
        if (int(row["event_ordinal"]), int(row["runtime_bag_id"])) not in identities
    ]
    if len(selected) < target:
        selected.extend(
            _round_robin_cells(remaining, target - len(selected), bins=bins)
        )
    selected = selected[:target]
    for row in selected:
        row["source_scale"] = load_scale
    selected.sort(
        key=lambda row: (
            float(row["event_time"]),
            int(row["event_ordinal"]),
            int(row["runtime_bag_id"]),
        )
    )
    return selected


def _arm_descriptor(branch: int, edge: int) -> dict[str, Any]:
    return dict(
        next(
            arm
            for arm in CORRIDOR_ARMS[branch]
            if int(arm["first_edge"]) == edge
        )
    )


def _target_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    selected = row.get("selected_next_node")
    corridor = row.get("g4irsf25_corridor_nodes")
    return (
        row.get("population_group_id"),
        row.get("population_selection_id"),
        row.get("event_ordinal"),
        row.get("action_kind"),
        int(selected) if type(selected) is int else None,
        row.get("g4irsf25_rejoin_node"),
        tuple(corridor) if isinstance(corridor, list) else None,
        row.get("g4irsf25_settle_seconds"),
        row.get("g4irsf25_max_horizon_seconds"),
    )


def _target_key_list(row: Mapping[str, Any]) -> list[Any]:
    return list(_plain(_target_key(row)))


def build_pair_plan(
    groups: Sequence[Mapping[str, Any]],
    *,
    settle_seconds: float = 30.0,
    max_horizon_seconds: float = 600.0,
) -> list[dict[str, Any]]:
    """Build G21 NEXT_EDGE targets for every non-S4 corridor arm."""

    _require(30.0 <= settle_seconds <= 60.0, "settle_seconds must be 30--60")
    _require(
        settle_seconds <= max_horizon_seconds <= 600.0,
        "max_horizon_seconds must cover settle and be <= 600",
    )
    planned: list[dict[str, Any]] = []
    for group_index, raw in enumerate(groups):
        event = g22.normalize_route_event(raw)
        branch = int(event["current_node"])
        s4 = int(event["baseline_next_node"])
        registered = set(_corridor_edges(branch))
        base_targets = g22.build_action_targets(event, horizons="H_bag")
        targets: list[dict[str, Any]] = []
        for target in base_targets:
            edge = target.get("selected_next_node")
            if target.get("action_kind") != "NEXT_EDGE" or edge not in registered:
                continue
            enriched = dict(target)
            enriched.update(
                {
                    "g4irsf25_rejoin_node": int(
                        CORRIDOR_ARMS[branch][0]["rejoin_node"]
                    ),
                    "g4irsf25_corridor_nodes": corridor_union_nodes(branch),
                    "g4irsf25_settle_seconds": float(settle_seconds),
                    "g4irsf25_max_horizon_seconds": float(max_horizon_seconds),
                }
            )
            targets.append(enriched)
        _require(
            {int(target["selected_next_node"]) for target in targets}
            == registered - {s4},
            f"branch {branch} did not produce every non-S4 corridor target",
        )
        checkpoint_id = (
            f"g25|load={int(raw.get('source_scale', 1))}"
            f"|event={int(event['event_ordinal'])}"
            f"|bag={int(event['runtime_bag_id'])}"
        )
        planned.append(
            {
                "group_index": group_index,
                "checkpoint_id": checkpoint_id,
                "event": {**dict(_plain(raw)), **event},
                "targets": targets,
            }
        )
    return planned


def _s4_score(candidate: Mapping[str, Any], event_time: float) -> float:
    travel = _finite(candidate["travel_time"], "travel_time")
    score = travel + _finite(candidate["static_potential"], "static_potential")
    score += _finite(candidate["target_queue_length"], "target_queue_length")
    score += _finite(
        candidate["target_scheduled_incoming"], "target_scheduled_incoming"
    )
    score += max(
        0.0,
        _finite(candidate["corridor_next_available"], "corridor_next_available")
        - event_time,
    )
    score += max(
        0.0,
        _finite(candidate["target_next_available"], "target_next_available")
        - event_time
        - travel,
    )
    if bool(candidate.get("advertised_fault", False)):
        score += 1.0e12
    return score


def build_feature_vector(
    event: Mapping[str, Any], *, edge: int, support: int
) -> dict[str, float]:
    """Reconstruct the runtime's 21 current-information CLCR features.

    Native checkpoints do not contain an online G25 feedback history.  The
    four feedback values are therefore explicitly initialised to no samples:
    short/long/trend=0, feedback age=600, sample log=0, timeout rate=0.  Pair
    outcomes are never fed back into these features.
    """

    nodes, candidates, baseline_index = _candidate_rows(event)
    _require(edge in nodes, f"edge {edge} is absent from candidate observations")
    candidate = candidates[nodes.index(edge)]
    baseline = candidates[baseline_index]
    event_time = _finite(event["event_time"], "event_time")

    def delta(name: str) -> float:
        return _finite(candidate[name], name) - _finite(baseline[name], name)

    def corridor_wait(row: Mapping[str, Any]) -> float:
        return max(
            0.0,
            _finite(row["corridor_next_available"], "corridor_next_available")
            - event_time,
        )

    def target_wait(row: Mapping[str, Any]) -> float:
        return max(
            0.0,
            _finite(row["target_next_available"], "target_next_available")
            - event_time
            - _finite(row["travel_time"], "travel_time"),
        )

    values = {
        "s4_score_delta": _s4_score(candidate, event_time)
        - _s4_score(baseline, event_time),
        "travel_time_delta": delta("travel_time"),
        "static_potential_delta": delta("static_potential"),
        "target_queue_delta": delta("target_queue_length"),
        "target_scheduled_incoming_delta": delta(
            "target_scheduled_incoming"
        ),
        "corridor_wait_delta": corridor_wait(candidate)
        - corridor_wait(baseline),
        "target_wait_delta": target_wait(candidate) - target_wait(baseline),
        "goal_conditioned_differential_delta": delta(
            "goal_conditioned_differential"
        ),
        "estimated_service_rate_delta": delta("estimated_service_rate"),
        "service_weighted_pressure_delta": delta(
            "service_weighted_pressure"
        ),
        "two_hop_pressure_delta": delta("two_hop_queue_pressure"),
        "recent_visit_delta": delta("recent_visit_count"),
        "current_bag_age_seconds": _finite(
            baseline["priority_age_seconds"], "priority_age_seconds"
        ),
        "deadline_headroom_seconds": _finite(
            baseline["priority_slack_seconds"], "priority_slack_seconds"
        ),
        "recent_corridor_short_ewma_seconds": 0.0,
        "recent_corridor_long_ewma_seconds": 0.0,
        "recent_corridor_trend_seconds": 0.0,
        "recent_corridor_feedback_age_seconds": 600.0,
        "recent_corridor_feedback_sample_log1p": 0.0,
        "recent_corridor_timeout_rate": 0.0,
        "arm_support_log1p": math.log1p(support),
    }
    _require(
        tuple(values) == learning.FEATURE_NAMES,
        "offline feature order drifted from the learning/runtime contract",
    )
    return values


def _short_summary(branch: Any, label: str) -> dict[str, Any]:
    _require(isinstance(branch, Mapping), f"{label} branch is missing")
    summary = branch.get("g4irsf25_short_horizon")
    _require(isinstance(summary, Mapping), f"{label} short-horizon label is missing")
    _require(
        summary.get("schema") == "czr005.g4irsf25.short_horizon_branch.v1",
        f"{label} short-horizon schema drifted",
    )
    return dict(_plain(summary))


def _pair_failure(pair: Mapping[str, Any]) -> str | None:
    if pair.get("same_state_start") is not True:
        return str(
            pair.get("false_positive_reason")
            or pair.get("pair_status")
            or "SAME_STATE_START_FAILED"
        )
    if pair.get("action_changed") is not True:
        return str(pair.get("false_positive_reason") or "ACTION_NOT_CHANGED")
    if pair.get("pair_complete") is not True:
        return str(pair.get("pair_status") or "PAIR_INCOMPLETE")
    try:
        _short_summary(pair.get("baseline"), "baseline")
        _short_summary(pair.get("treatment"), "treatment")
    except ShortHorizonCampaignError as error:
        return str(error)
    return None


def _leg(event: Mapping[str, Any]) -> str:
    direct = event.get("leg")
    if isinstance(direct, str) and direct:
        return direct
    segment = str(event.get("segment_id", "unknown"))
    return segment.rsplit(":", 1)[-1] if ":" in segment else "unknown"


def _arm_row(
    *,
    event: Mapping[str, Any],
    descriptor: Mapping[str, Any],
    branch_evidence: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    edge = int(descriptor["first_edge"])
    elapsed_events = branch_evidence.get("elapsed_event_count")
    _require(
        type(elapsed_events) is int and elapsed_events >= 0,
        "short-horizon branch omitted elapsed_event_count",
    )
    return {
        **dict(_plain(descriptor)),
        "features": build_feature_vector(
            event, edge=edge, support=int(descriptor["support"])
        ),
        "private_cost_seconds": _finite(
            summary["private_cost_seconds"], "private_cost_seconds"
        ),
        "local_system_cost_seconds": _finite(
            summary["local_system_cost"], "local_system_cost"
        ),
        "local_system_cost_units": summary.get("local_system_cost_units"),
        "safe": summary.get("safety_pass") is True,
        "timeout": summary.get("timeout") is True,
        "observed_seconds": _finite(summary["observed_seconds"], "observed_seconds"),
        "elapsed_event_count": elapsed_events,
        "rejoin_arrived": summary.get("rejoin_arrived") is True,
        "settle_complete": summary.get("settle_complete") is True,
        "coverage_complete": summary.get("coverage_complete") is True,
        "queue_area_bag_seconds": _finite(
            summary["queue_area_bag_seconds"], "queue_area_bag_seconds"
        ),
        "scheduled_incoming_area_bag_seconds": _finite(
            summary["scheduled_incoming_area_bag_seconds"],
            "scheduled_incoming_area_bag_seconds",
        ),
        "local_backlog_at_horizon": int(summary["local_backlog_at_horizon"]),
        "peak_local_backlog": int(summary["peak_local_backlog"]),
        "affected_bag_completed": summary.get("affected_bag_completed") is True,
        "stop_reason": summary.get("stop_reason"),
    }


def compact_pairs(
    plan: Sequence[Mapping[str, Any]], pairs: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Join complete native arms into the learning module's group schema."""

    pair_by_key = {
        _target_key(pair): pair for pair in pairs if isinstance(pair, Mapping)
    }
    completed: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for planned in plan:
        event = planned["event"]
        branch = int(event["current_node"])
        s4 = int(event["baseline_next_node"])
        resolved: dict[int, Mapping[str, Any]] = {}
        reasons: list[str] = []
        for target in planned["targets"]:
            pair = pair_by_key.get(_target_key(target))
            edge = int(target["selected_next_node"])
            if pair is None:
                reasons.append(f"edge={edge}:PAIR_MISSING")
                continue
            failure = _pair_failure(pair)
            if failure is not None:
                reasons.append(f"edge={edge}:{failure}")
                continue
            resolved[edge] = pair
        if reasons or len(resolved) != len(planned["targets"]):
            failures.append(
                {
                    "checkpoint_id": planned["checkpoint_id"],
                    "source_scale": int(event.get("source_scale", 1)),
                    "branch_node": branch,
                    "reasons": reasons or ["PAIR_SET_INCOMPLETE"],
                }
            )
            continue

        first_pair = next(iter(resolved.values()))
        baseline_branch = first_pair["baseline"]
        baseline_summary = _short_summary(baseline_branch, "baseline")
        arms: list[dict[str, Any]] = []
        for descriptor in CORRIDOR_ARMS[branch]:
            edge = int(descriptor["first_edge"])
            branch_evidence = (
                baseline_branch if edge == s4 else resolved[edge]["treatment"]
            )
            summary = (
                baseline_summary
                if edge == s4
                else _short_summary(branch_evidence, "treatment")
            )
            arms.append(
                _arm_row(
                    event=event,
                    descriptor=descriptor,
                    branch_evidence=branch_evidence,
                    summary=summary,
                )
            )
        baseline_arm = next(arm for arm in arms if arm["first_edge"] == s4)
        for arm in arms:
            arm["local_system_delta_vs_s4"] = (
                arm["local_system_cost_seconds"]
                - baseline_arm["local_system_cost_seconds"]
            )
            arm["private_delta_vs_s4_seconds"] = (
                arm["private_cost_seconds"] - baseline_arm["private_cost_seconds"]
            )

        nodes, candidates, _ = _candidate_rows(event)
        candidate_by_node = dict(zip(nodes, candidates))
        absolute_pressure = max(
            _finite(candidate_by_node[edge]["target_queue_length"], "queue")
            + _finite(
                candidate_by_node[edge]["target_scheduled_incoming"],
                "incoming",
            )
            for edge in _corridor_edges(branch)
        )
        service_pressure = max(
            _finite(
                candidate_by_node[edge]["service_weighted_pressure"],
                "service_weighted_pressure",
            )
            for edge in _corridor_edges(branch)
        )
        completed.append(
            {
                "schema": PAIR_SCHEMA,
                "checkpoint_id": str(planned["checkpoint_id"]),
                "checkpoint_time_seconds": float(event["event_time"]),
                "load_scale": float(event.get("source_scale", 1)),
                "branch_node": branch,
                "goal_node": int(event.get("goal", -1)),
                "leg": _leg(event),
                "task_class": _leg(event),
                "s4_first_edge": s4,
                "gate_metrics": {
                    "target_queue_plus_incoming": absolute_pressure,
                    "service_weighted_pressure": service_pressure,
                    "corridor_trend": 0.0,
                },
                "identity_metadata": {
                    **g22.event_identity(event),
                    "task_id": event.get("task_id"),
                    "segment_id": event.get("segment_id"),
                    "identity_fields_are_trace_only": True,
                },
                "selection_metadata": {
                    "selection_stratum": event.get("selection_stratum"),
                    "time_quantile": event.get("time_quantile"),
                    "pressure_quantile": event.get("pressure_quantile"),
                    "local_pressure": event.get("selection_pressure"),
                },
                "local_system_nodes": corridor_union_nodes(branch),
                "local_system_node_semantics": (
                    "REGISTERED_ARM_UNION_PLUS_CANONICAL_REJOIN_OUTGOING"
                ),
                "feature_provenance": {
                    "source": "CURRENT_ROUTE_OBSERVATION_CANDIDATE_PRIMITIVES",
                    "future_outcomes_used": False,
                    "feedback_initialization": {
                        "short_ewma_seconds": 0.0,
                        "long_ewma_seconds": 0.0,
                        "trend_seconds": 0.0,
                        "feedback_age_seconds": 600.0,
                        "sample_log1p": 0.0,
                        "timeout_rate": 0.0,
                    },
                },
                "arms": arms,
            }
        )
    completed.sort(
        key=lambda row: (
            float(row["checkpoint_time_seconds"]),
            str(row["checkpoint_id"]),
        )
    )
    return completed, failures


def _balanced_success_cell_order(
    keys: Iterable[tuple[int, int]], *, bins: int = 4
) -> list[tuple[int, int]]:
    """Interleave time and pressure so a prefix cannot erase the time tail."""

    available = set(keys)
    ordered: list[tuple[int, int]] = []
    # The first diagonal includes q0..q3 in both dimensions.  Later diagonals
    # fill the remaining combinations without privileging early checkpoints.
    for offset in range(bins):
        for time_bin in range(bins):
            key = (time_bin, (time_bin + offset) % bins)
            if key in available:
                ordered.append(key)
                available.remove(key)
    ordered.extend(sorted(available))
    return ordered


def _select_success_branch(
    rows: Sequence[Mapping[str, Any]], target: int
) -> list[dict[str, Any]]:
    cells: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for raw in rows:
        metadata = raw.get("selection_metadata")
        _require(isinstance(metadata, Mapping), "compact group lacks selection metadata")
        time_bin = metadata.get("time_quantile")
        pressure_bin = metadata.get("pressure_quantile")
        _require(
            type(time_bin) is int
            and type(pressure_bin) is int
            and 0 <= time_bin < 4
            and 0 <= pressure_bin < 4,
            "compact selection quantile drifted",
        )
        cells[(time_bin, pressure_bin)].append(dict(raw))
    for members in cells.values():
        members.sort(
            key=lambda row: (
                float(row["checkpoint_time_seconds"]),
                str(row["checkpoint_id"]),
            )
        )
    keys = _balanced_success_cell_order(cells)
    selected: list[dict[str, Any]] = []
    while len(selected) < min(target, len(rows)):
        progressed = False
        for key in keys:
            if cells[key] and len(selected) < target:
                selected.append(cells[key].pop(0))
                progressed = True
        if not progressed:
            break
    return selected


def select_balanced_successes(
    groups: Sequence[Mapping[str, Any]], *, target: int
) -> list[dict[str, Any]]:
    """Down-select valid oversamples without taking a chronological prefix."""

    _require(target > 0, "published target must be positive")
    if len(groups) <= target:
        return [dict(row) for row in groups]
    branches = sorted({int(row["branch_node"]) for row in groups})
    quotas = {branch: target // len(branches) for branch in branches}
    for branch in branches[: target % len(branches)]:
        quotas[branch] += 1
    selected: list[dict[str, Any]] = []
    for branch in branches:
        selected.extend(
            _select_success_branch(
                [row for row in groups if int(row["branch_node"]) == branch],
                quotas[branch],
            )
        )
    selected_ids = {str(row["checkpoint_id"]) for row in selected}
    if len(selected) < target:
        remaining = [
            row for row in groups if str(row["checkpoint_id"]) not in selected_ids
        ]
        selected.extend(_select_success_branch(remaining, target - len(selected)))
    selected.sort(
        key=lambda row: (
            float(row["checkpoint_time_seconds"]),
            str(row["checkpoint_id"]),
        )
    )
    return selected[:target]


def _native_arguments_for_scale(root: Path, scale: int) -> tuple[list[Any], Any]:
    if scale == 1:
        from scripts.eval import g4irsf15_causal_campaign as g15

        arguments, _, prefix = g15._native_arguments(root)
        return arguments, {
            "scale": 1,
            "request_count": len(prefix.rows),
            "source": "protected_g15_1x",
        }
    arguments, rows, descriptor = g22.build_2x_native_arguments(root)
    return arguments, {
        **dict(_plain(descriptor)),
        "scale": 2,
        "request_count": len(rows),
        "source": "protected_g22_2x",
    }


def scan_scale(backend: Any, native_arguments: Sequence[Any]) -> list[dict[str, Any]]:
    payload = backend.g4irsf15_scan_causal_skeletons_from_records(
        *native_arguments, RESEARCH_PROFILE
    )
    _require(isinstance(payload, Mapping), "native scan returned no object")
    if payload.get("census_complete") is not True:
        invariants = payload.get("terminal_invariants")
        # G22's formal profile shape is deliberately fixed at 2x.  The same
        # E2 control on the protected 1x input therefore reports exactly one
        # formal-only mismatch even after a complete, live-safe terminal run.
        # This exception admits that explicit 1x diagnostic only; event/time
        # truncation or any live-safety failure still rejects the census.
        accepted_protected_1x = (
            payload.get("protected_full_1x_shape") is True
            and payload.get("terminal_finalized") is True
            and payload.get("profile_expected_full_shape") is False
            and isinstance(invariants, Mapping)
            and invariants.get("live_safety_pass") is True
            and invariants.get("hard_gate_fail_reasons")
            == ["PROFILE_EXPECTED_FULL_SHAPE_MISMATCH"]
            and invariants.get("event_limit_reached") is False
            and invariants.get("time_limit_reached") is False
        )
        _require(
            accepted_protected_1x,
            "native census did not complete for a permitted 1x shape-only reason",
        )
    rows = payload.get("skeletons")
    _require(isinstance(rows, list), "native census omitted skeletons")
    # The rich G22 census can contain hundreds of thousands of Route rows.
    # Copy only the four registered branch populations into Python; selection
    # never needs the remaining nodes.
    return [
        dict(_plain(row))
        for row in rows
        if isinstance(row, Mapping)
        and row.get("kind") in {"I3", "I3_NEXT_EDGE"}
        and int(row.get("current_node", row.get("node", -1))) in CORRIDOR_ARMS
    ]


def run_pair_targets(
    backend: Any,
    native_arguments: Sequence[Any],
    targets: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    payload = backend.g4irsf15_run_causal_target_pairs_from_records(
        *native_arguments,
        [dict(_plain(target)) for target in targets],
        RESEARCH_PROFILE,
    )
    _require(isinstance(payload, Mapping), "native pair run returned no object")
    pairs = payload.get("pairs")
    _require(
        isinstance(pairs, list) and len(pairs) == len(targets),
        "native pair count does not match targets",
    )
    return [dict(_plain(pair)) for pair in pairs if isinstance(pair, Mapping)]


def _binary_stamp(binary: Path) -> dict[str, Any]:
    stat = binary.stat()
    return {
        "name": binary.name,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _read_shard(
    path: Path,
    *,
    expected_keys: Sequence[Sequence[Any]],
    binary_stamp: Mapping[str, Any],
) -> list[dict[str, Any]] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if (
        not isinstance(payload, Mapping)
        or payload.get("campaign_revision") != CAMPAIGN_REVISION
        or payload.get("binary") != dict(binary_stamp)
        or payload.get("target_keys") != [list(key) for key in expected_keys]
        or not isinstance(payload.get("pairs"), list)
        or len(payload["pairs"]) != len(expected_keys)
    ):
        return None
    return [dict(row) for row in payload["pairs"] if isinstance(row, Mapping)]


_WORKER_CACHE: dict[tuple[str, str, int], tuple[Any, list[Any]]] = {}


def _run_shard_worker(
    root_text: str,
    binary_text: str,
    scale: int,
    targets: list[dict[str, Any]],
    output_text: str,
    stamp: dict[str, Any],
) -> str:
    key = (root_text, binary_text, scale)
    if key not in _WORKER_CACHE:
        backend = g22.load_native_backend(Path(binary_text))
        arguments, _ = _native_arguments_for_scale(Path(root_text), scale)
        _WORKER_CACHE[key] = (backend, arguments)
    backend, arguments = _WORKER_CACHE[key]
    pairs = run_pair_targets(backend, arguments, targets)
    _atomic_json(
        Path(output_text),
        {
            "campaign_revision": CAMPAIGN_REVISION,
            "binary": stamp,
            "target_keys": [_target_key_list(target) for target in targets],
            "pairs": pairs,
        },
    )
    return output_text


def _wall_timeout_pair(
    target: Mapping[str, Any], wall_seconds: float
) -> dict[str, Any]:
    """Retain an infrastructure timeout as an explicit, non-training row."""

    return {
        "target_schema": target.get("schema"),
        "population_group_id": target.get("population_group_id"),
        "population_selection_id": target.get("population_selection_id"),
        "event_ordinal": target.get("event_ordinal"),
        "horizon": target.get("horizon"),
        "action_kind": target.get("action_kind"),
        "selected_next_node": target.get("selected_next_node"),
        "g4irsf25_rejoin_node": target.get("g4irsf25_rejoin_node"),
        "g4irsf25_corridor_nodes": target.get("g4irsf25_corridor_nodes"),
        "g4irsf25_settle_seconds": target.get("g4irsf25_settle_seconds"),
        "g4irsf25_max_horizon_seconds": target.get(
            "g4irsf25_max_horizon_seconds"
        ),
        "same_state_start": False,
        "action_changed": False,
        "pair_complete": False,
        "pair_status": "G25_SHARD_WALL_TIMEOUT",
        "false_positive_reason": (
            f"G25_SHARD_WALL_TIMEOUT_AFTER_{wall_seconds:g}_SECONDS"
        ),
    }


def _execute_bounded_process_shards(
    *,
    root: Path,
    binary: Path,
    scale: int,
    pending: Sequence[tuple[list[dict[str, Any]], Path]],
    workers: int,
    wall_seconds: float,
    stamp: Mapping[str, Any],
) -> None:
    """Run at most two killable shard processes with a real wall bound."""

    _require(wall_seconds > 0.0, "shard wall bound must be positive")
    context = multiprocessing.get_context("spawn")
    waiting = list(pending)
    active: list[dict[str, Any]] = []
    try:
        while waiting or active:
            while waiting and len(active) < workers:
                shard, path = waiting.pop(0)
                process = context.Process(
                    target=_run_shard_worker,
                    args=(
                        str(root),
                        str(binary),
                        scale,
                        shard,
                        str(path),
                        dict(stamp),
                    ),
                )
                process.start()
                active.append(
                    {
                        "process": process,
                        "started": time.monotonic(),
                        "shard": shard,
                        "path": path,
                    }
                )
            for task in list(active):
                process = task["process"]
                elapsed = time.monotonic() - float(task["started"])
                if process.is_alive() and elapsed <= wall_seconds:
                    continue
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=10.0)
                    if process.is_alive():
                        process.kill()
                        process.join(timeout=10.0)
                    pairs = [
                        _wall_timeout_pair(target, wall_seconds)
                        for target in task["shard"]
                    ]
                    _atomic_json(
                        task["path"],
                        {
                            "campaign_revision": CAMPAIGN_REVISION,
                            "binary": dict(stamp),
                            "target_keys": [
                                _target_key_list(row) for row in task["shard"]
                            ],
                            "pairs": pairs,
                        },
                    )
                else:
                    process.join(timeout=1.0)
                    _require(
                        process.exitcode == 0,
                        f"native shard worker failed with exit code {process.exitcode}",
                    )
                active.remove(task)
            if active:
                time.sleep(0.20)
    finally:
        # A user interrupt or parent exception must not leave a multi-gigabyte
        # replay worker detached in the background.
        for task in active:
            process = task["process"]
            if process.is_alive():
                process.terminate()
                process.join(timeout=10.0)
            if process.is_alive():
                process.kill()
                process.join(timeout=10.0)


def execute_scale_shards(
    *,
    root: Path,
    binary: Path,
    scale: int,
    plan: Sequence[Mapping[str, Any]],
    state_dir: Path,
    workers: int,
    shard_size: int,
    shard_wall_seconds: float | None = None,
    backend: Any | None = None,
    native_arguments: Sequence[Any] | None = None,
) -> list[dict[str, Any]]:
    _require(1 <= workers <= 2, "workers must be 1 or 2")
    _require(shard_size > 0, "shard_size must be positive")
    targets = [dict(target) for group in plan for target in group["targets"]]
    shards = [targets[index : index + shard_size] for index in range(0, len(targets), shard_size)]
    stamp = {
        **_binary_stamp(binary),
        "shard_wall_seconds": shard_wall_seconds,
    }
    paths: list[Path] = []
    pending: list[tuple[list[dict[str, Any]], Path]] = []
    for index, shard in enumerate(shards):
        path = state_dir / f"scale_{scale}" / f"pairs_{index:05d}.json"
        paths.append(path)
        cached = _read_shard(
            path,
            expected_keys=[_target_key_list(target) for target in shard],
            binary_stamp=stamp,
        )
        if cached is None:
            pending.append((shard, path))
    if pending and shard_wall_seconds is not None:
        _execute_bounded_process_shards(
            root=root,
            binary=binary,
            scale=scale,
            pending=pending,
            workers=workers,
            wall_seconds=shard_wall_seconds,
            stamp=stamp,
        )
    elif workers == 1:
        if backend is None:
            backend = g22.load_native_backend(binary)
        if native_arguments is None:
            native_arguments, _ = _native_arguments_for_scale(root, scale)
        for shard, path in pending:
            pairs = run_pair_targets(backend, native_arguments, shard)
            _atomic_json(
                path,
                {
                    "campaign_revision": CAMPAIGN_REVISION,
                    "binary": stamp,
                    "target_keys": [_target_key_list(row) for row in shard],
                    "pairs": pairs,
                },
            )
    elif pending:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(
                    _run_shard_worker,
                    str(root),
                    str(binary),
                    scale,
                    shard,
                    str(path),
                    stamp,
                )
                for shard, path in pending
            ]
            for future in as_completed(futures):
                future.result()
    pairs: list[dict[str, Any]] = []
    for path, shard in zip(paths, shards):
        cached = _read_shard(
            path,
            expected_keys=[_target_key_list(target) for target in shard],
            binary_stamp=stamp,
        )
        _require(cached is not None, f"invalid completed shard: {path}")
        pairs.extend(cached)
    return pairs


def _count_by(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, int]:
    return dict(
        sorted(
            Counter(str(row.get(field, "unknown")) for row in rows).items()
        )
    )


def summarize_campaign(
    *,
    requested_per_scale: int,
    settle_seconds: float,
    max_horizon_seconds: float,
    selected_by_scale: Mapping[int, int],
    groups: Sequence[Mapping[str, Any]],
    failures: Sequence[Mapping[str, Any]],
    input_descriptors: Mapping[int, Any],
    execution_metrics: Mapping[int, Mapping[str, Any]],
) -> dict[str, Any]:
    normalized = learning.normalise_paired_rows(groups) if groups else []
    ceilings = learning.compute_action_ceilings(normalized) if normalized else None
    arms = [arm for group in groups for arm in group["arms"]]
    failure_reasons = Counter(
        reason
        for failure in failures
        for reason in failure.get("reasons", [])
    )
    counts_by_scale = Counter(int(float(row["load_scale"])) for row in groups)
    target_met = all(
        counts_by_scale.get(scale, 0) >= requested_per_scale
        for scale in selected_by_scale
    )
    return {
        "schema": SUMMARY_SCHEMA,
        "campaign_revision": CAMPAIGN_REVISION,
        "checkpoint_selection": {
            "registered_corridor_legal_arms_only": True,
            "new_merge_request_proxy": (
                "EARLIEST_EVENT_ORDINAL_PER_RUNTIME_BAG_AND_CURRENT_NODE"
            ),
            "grouping_fields": ["runtime_bag_id", "current_node"],
            "result_fields_used": False,
        },
        "status": "TARGET_MET" if target_met else "CHECKPOINT_SHORTFALL",
        "research_profile": RESEARCH_PROFILE,
        "settle_seconds": settle_seconds,
        "max_horizon_seconds": max_horizon_seconds,
        "requested_checkpoint_count_per_scale": requested_per_scale,
        "requested_checkpoint_count_total": requested_per_scale
        * len(selected_by_scale),
        "screened_checkpoint_count_by_scale": {
            str(scale): int(count) for scale, count in sorted(selected_by_scale.items())
        },
        "complete_checkpoint_count": len(groups),
        "complete_checkpoint_count_by_scale": {
            str(scale): counts_by_scale.get(scale, 0)
            for scale in sorted(selected_by_scale)
        },
        "complete_checkpoint_count_by_branch": _count_by(groups, "branch_node"),
        "complete_checkpoint_count_by_leg": _count_by(groups, "leg"),
        "failed_checkpoint_count": len(failures),
        "failure_reason_counts": dict(sorted(failure_reasons.items())),
        "arm_label_count": len(arms),
        "timeout_arm_count": sum(arm.get("timeout") is True for arm in arms),
        "unsafe_arm_count": sum(arm.get("safe") is not True for arm in arms),
        "rejoin_arrival_arm_count": sum(
            arm.get("rejoin_arrived") is True for arm in arms
        ),
        "feedback_features_initialized_without_future_leakage": True,
        "feedback_initialization": {
            "short_long_trend_seconds": 0.0,
            "feedback_age_seconds": 600.0,
            "sample_log1p": 0.0,
            "timeout_rate": 0.0,
        },
        "identity_fields_are_trace_metadata_only": True,
        "local_system_node_domain_by_branch": {
            str(branch): corridor_union_nodes(branch)
            for branch in sorted(CORRIDOR_ARMS)
        },
        "feature_names": list(learning.FEATURE_NAMES),
        "input_descriptors": {
            str(scale): descriptor
            for scale, descriptor in sorted(input_descriptors.items())
        },
        "execution_metrics_by_scale": {
            str(scale): dict(metrics)
            for scale, metrics in sorted(execution_metrics.items())
        },
        "ceilings": ceilings,
        "compact_dataset": DEFAULT_DATASET.as_posix(),
    }


def render_report(summary: Mapping[str, Any]) -> str:
    ceilings = summary.get("ceilings") or {}
    full = ceilings.get("full_state") or {}
    local = ceilings.get("local_observation") or {}
    by_scale = summary["complete_checkpoint_count_by_scale"]
    by_branch = summary["complete_checkpoint_count_by_branch"]
    return f"""# G4IRSF25 short-horizon corridor oracle

This campaign reuses the existing exact same-checkpoint causal runner.  The
only treatment is a registered first edge; both branches then return to the
ordinary S4/J2/E2 controller and stop at reconvergence plus settling, or at the
retained {float(summary['max_horizon_seconds']):g} second cap.

After the registered-arm legality screen, census sampling keeps only the
earliest event ordinal for each `(runtime_bag_id, current_node)`.  That row is
the bag's new merge-request decision; later wakeups belong to the already
created request and cannot change its first edge.  This filter uses no branch
result or future outcome.

- Status: `{summary['status']}`
- Complete independent checkpoints: {summary['complete_checkpoint_count']:,}
- Complete by load: {json.dumps(by_scale, sort_keys=True)}
- Complete by branch: {json.dumps(by_branch, sort_keys=True)}
- Failed/incomplete checkpoints: {summary['failed_checkpoint_count']:,}
- Arm labels: {summary['arm_label_count']:,}
- Retained timeout arms: {summary['timeout_arm_count']:,}
- Unsafe arms: {summary['unsafe_arm_count']:,}

## Action ceilings from the same paired data

- Full-state mean possible local-system improvement: {float(full.get('mean_possible_improvement', 0.0)):.6f} bag-seconds
- Full-state mean improvement fraction: {100.0 * float(full.get('mean_possible_improvement_fraction', 0.0)):.3f}%
- Alternative-win fraction: {100.0 * float(full.get('alternative_win_fraction', 0.0)):.3f}%
- Opportunity mass: {float(ceilings.get('opportunity_mass', 0.0)):.6f}
- Local-observation pairwise ranking ceiling: {100.0 * float(local.get('pairwise_ranking_ceiling', 0.0)):.3f}%
- Local-observation mean regret ceiling: {float(local.get('mean_local_regret_ceiling', 0.0)):.6f} bag-seconds

## Leakage and scope

The 21 model inputs are reconstructed only from the decision-time Route
candidate observation.  A native checkpoint has no preceding G25 feedback
stream, so short EWMA, long EWMA and trend are explicitly zero; feedback age is
600 seconds, sample count is zero and timeout rate is zero.  Counterfactual
outcomes never enter the input vector.  Checkpoint, task and event identities
are retained only under `identity_metadata` for grouping and audit.

Private cost is affected-bag time to reconvergence.  Local-system cost is the
online integral of queue plus scheduled incoming over the union of the two
registered corridors plus the canonical map's outgoing neighborhood at their
rejoin node.  This is the same fixed node domain for every arm in a checkpoint;
it is not a runtime global scan.  Timeout examples remain finite high-cost
examples and are not dropped.  This is a local short-horizon oracle, not an
H_system claim.
"""


def _default_binary(root: Path) -> Path:
    candidates = [
        root
        / "build_g25_short_horizon"
        / "python"
        / "Release"
        / "czr005_cpp.cp311-win_amd64.pyd",
        root
        / "build_g25_clcr"
        / "python"
        / "Release"
        / "czr005_cpp.cp311-win_amd64.pyd",
        root / "build-ci" / "python" / "czr005_cpp.cp311-win_amd64.pyd",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    discovered = sorted(root.glob("build*/python/**/czr005_cpp*.pyd"))
    _require(bool(discovered), "no native czr005_cpp binary found; pass --binary")
    return discovered[0]


def run_campaign(
    *,
    root: Path,
    binary: Path,
    scales: Sequence[int],
    requested_per_scale: int,
    screening_multiplier: float,
    settle_seconds: float,
    max_horizon_seconds: float,
    workers: int,
    shard_size: int,
    shard_wall_seconds: float | None,
    state_dir: Path,
    dataset_path: Path,
    table_path: Path,
    report_path: Path,
) -> dict[str, Any]:
    _require(scales and all(scale in {1, 2} for scale in scales), "scales must be 1/2")
    _require(requested_per_scale > 0, "requested_per_scale must be positive")
    _require(screening_multiplier >= 1.0, "screening_multiplier must be >= 1")
    backend = g22.load_native_backend(binary)
    all_groups: list[dict[str, Any]] = []
    all_failures: list[dict[str, Any]] = []
    selected_by_scale: dict[int, int] = {}
    descriptors: dict[int, Any] = {}
    execution_metrics: dict[int, dict[str, Any]] = {}
    for scale in scales:
        native_arguments, descriptor = _native_arguments_for_scale(root, scale)
        descriptors[scale] = descriptor
        scan_started = time.perf_counter()
        census = scan_scale(backend, native_arguments)
        scan_wall_seconds = time.perf_counter() - scan_started
        screened_target = int(math.ceil(requested_per_scale * screening_multiplier))
        selected = select_balanced_checkpoints(
            census,
            target=screened_target,
            load_scale=scale,
        )
        selected_by_scale[scale] = len(selected)
        plan = build_pair_plan(
            selected,
            settle_seconds=settle_seconds,
            max_horizon_seconds=max_horizon_seconds,
        )
        if shard_wall_seconds is not None:
            # A bounded child reloads the immutable input.  Release the large
            # parent-side census and bag argument list first so memory is not
            # doubled while the child runs.
            del census
            del native_arguments
            gc.collect()
        pair_started = time.perf_counter()
        pairs = execute_scale_shards(
            root=root,
            binary=binary,
            scale=scale,
            plan=plan,
            state_dir=state_dir,
            workers=workers,
            shard_size=shard_size,
            shard_wall_seconds=shard_wall_seconds,
            backend=backend if workers == 1 and shard_wall_seconds is None else None,
            native_arguments=(
                native_arguments
                if workers == 1 and shard_wall_seconds is None
                else None
            ),
        )
        pair_wall_seconds = time.perf_counter() - pair_started
        execution_metrics[scale] = {
            "full_census_wall_seconds": scan_wall_seconds,
            "pair_shards_wall_seconds": pair_wall_seconds,
            "executed_target_count": sum(
                len(group["targets"]) for group in plan
            ),
            "shard_size": shard_size,
            "workers": workers,
            "shard_wall_seconds": shard_wall_seconds,
        }
        compact, failures = compact_pairs(plan, pairs)
        # Oversampling is only a recovery pool.  Rebalance successful rows by
        # branch/time/pressure before publication; taking a chronological
        # prefix here would systematically erase the high-time tail.
        published = select_balanced_successes(
            compact, target=requested_per_scale
        )
        all_groups.extend(published)
        kept_ids = {row["checkpoint_id"] for row in published}
        all_failures.extend(failures)
        all_failures.extend(
            {
                "checkpoint_id": row["checkpoint_id"],
                "source_scale": scale,
                "branch_node": row["branch_node"],
                "reasons": ["VALID_OVERSAMPLE_NOT_NEEDED"],
            }
            for row in compact
            if row["checkpoint_id"] not in kept_ids
        )
    all_groups.sort(
        key=lambda row: (
            float(row["checkpoint_time_seconds"]),
            str(row["checkpoint_id"]),
        )
    )
    _atomic_jsonl(dataset_path, all_groups)
    summary = summarize_campaign(
        requested_per_scale=requested_per_scale,
        settle_seconds=settle_seconds,
        max_horizon_seconds=max_horizon_seconds,
        selected_by_scale=selected_by_scale,
        groups=all_groups,
        failures=[
            row
            for row in all_failures
            if row.get("reasons") != ["VALID_OVERSAMPLE_NOT_NEEDED"]
        ],
        input_descriptors=descriptors,
        execution_metrics=execution_metrics,
    )
    summary["compact_dataset"] = dataset_path.relative_to(root).as_posix()
    summary["valid_oversample_not_published"] = sum(
        row.get("reasons") == ["VALID_OVERSAMPLE_NOT_NEEDED"]
        for row in all_failures
    )
    _atomic_json(table_path, summary)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(summary), encoding="utf-8")
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("pilot", "target"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--scales", type=int, nargs="+", choices=(1, 2), default=(1, 2))
    parser.add_argument("--per-scale", type=int)
    parser.add_argument("--screening-multiplier", type=float)
    parser.add_argument("--settle-seconds", type=float, default=30.0)
    parser.add_argument("--max-horizon-seconds", type=float, default=600.0)
    parser.add_argument("--workers", type=int, choices=(1, 2), default=1)
    parser.add_argument("--shard-size", type=int, default=32)
    parser.add_argument(
        "--shard-wall-seconds",
        type=float,
        help="Kill and retain an explicit failure when one native shard exceeds this wall time.",
    )
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_RUN_STATE)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--allow-shortfall", action="store_true")
    return parser.parse_args(argv)


def _rooted(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    root = arguments.root.resolve()
    binary = (
        arguments.binary.resolve(strict=True)
        if arguments.binary is not None
        else _default_binary(root).resolve(strict=True)
    )
    per_scale = arguments.per_scale
    if per_scale is None:
        per_scale = 8 if arguments.mode == "pilot" else 512
    multiplier = arguments.screening_multiplier
    if multiplier is None:
        multiplier = 1.0 if arguments.mode == "pilot" else 1.10
    shard_wall_seconds = arguments.shard_wall_seconds
    if shard_wall_seconds is None:
        shard_wall_seconds = 300.0 if arguments.mode == "pilot" else 3600.0
    summary = run_campaign(
        root=root,
        binary=binary,
        scales=tuple(dict.fromkeys(arguments.scales)),
        requested_per_scale=per_scale,
        screening_multiplier=multiplier,
        settle_seconds=arguments.settle_seconds,
        max_horizon_seconds=arguments.max_horizon_seconds,
        workers=arguments.workers,
        shard_size=arguments.shard_size,
        shard_wall_seconds=shard_wall_seconds,
        state_dir=_rooted(root, arguments.state_dir),
        dataset_path=_rooted(root, arguments.dataset),
        table_path=_rooted(root, arguments.table),
        report_path=_rooted(root, arguments.report),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    if summary["status"] != "TARGET_MET" and not arguments.allow_shortfall:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
