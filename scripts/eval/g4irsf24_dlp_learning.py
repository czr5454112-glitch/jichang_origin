"""Minimal offline learning core for G24 decentralized delay potentials.

The module turns committed G4IRSF11 Route decisions into successful physical
edge transitions, keeps chronological splits contiguous, and freezes either
an edge-delay EWMA table (P1) or an edge-delay plus node-goal TD table (P2).
Runtime/task identities and absolute timestamps are used only to join and
order evidence; they never enter the exported policy artifact.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ARTIFACT_SCHEMA = "czr005.g4irsf24.dlp.v1"
TRANSITION_SCHEMA = "czr005.g4irsf24.transition.v1"
CORRIDOR_SCHEMA = "czr005.g4irsf24.reconvergent_corridor.v1"
MODES = ("ewma", "td")


class DLPLearningError(ValueError):
    """Raised when the compact DLP training contract is violated."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DLPLearningError(message)


def _number(value: Any, label: str) -> float:
    _require(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value)),
        f"{label} must be finite",
    )
    return float(value)


def _integer(value: Any, label: str) -> int:
    _require(isinstance(value, int) and not isinstance(value, bool), f"{label} must be an integer")
    return int(value)


def _runtime_bag_id(row: Mapping[str, Any]) -> int:
    metadata = row.get("metadata")
    value = row.get("runtime_bag_id")
    if value is None and isinstance(metadata, Mapping):
        value = metadata.get("runtime_bag_id")
    return _integer(value, "runtime_bag_id")


def _usable_outcome(row: Mapping[str, Any] | None) -> bool:
    if row is None:
        return False
    completed = row.get("reached_goal", row.get("complete", row.get("completed")))
    failed = row.get("failed", False)
    looped = row.get("loop_or_dead_end", False)
    return completed is True and failed is not True and looped is not True


def _candidate_for_selected(decision: Mapping[str, Any]) -> Mapping[str, Any]:
    selected = _integer(decision.get("selected_next"), "selected_next")
    candidates = decision.get("candidate_records")
    _require(isinstance(candidates, list), "candidate_records must be a list")
    matches = [
        row
        for row in candidates
        if isinstance(row, Mapping) and row.get("next_node") == selected
    ]
    _require(len(matches) == 1, "selected candidate must appear exactly once")
    return matches[0]


def _static_potentials(decision: Mapping[str, Any]) -> tuple[float, float, float]:
    """Return travel time, V0(current, goal), and V0(selected, goal)."""

    selected_candidate = _candidate_for_selected(decision)
    selected_features = selected_candidate.get("features")
    _require(isinstance(selected_features, Mapping), "selected candidate lacks features")
    travel_time = _number(selected_features.get("travel_time"), "travel_time")
    static_selected = _number(
        selected_features.get("static_potential"), "selected static_potential"
    )
    _require(travel_time >= 0.0 and static_selected >= 0.0, "negative static cost")

    static_current_options: list[float] = []
    candidates = decision.get("candidate_records")
    assert isinstance(candidates, list)
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        features = candidate.get("features")
        if not isinstance(features, Mapping):
            continue
        try:
            edge = _number(features.get("travel_time"), "candidate travel_time")
            tail = _number(features.get("static_potential"), "candidate static_potential")
        except DLPLearningError:
            continue
        if edge >= 0.0 and tail >= 0.0:
            static_current_options.append(edge + tail)
    _require(static_current_options, "decision has no usable static candidate cost")
    return travel_time, min(static_current_options), static_selected


def build_transitions(
    decision_rows: Iterable[Mapping[str, Any]],
    bag_results: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Join committed decisions into compact physical transitions.

    A row is emitted only when the next decision for the same runtime bag is
    observed at the edge selected by the earlier decision. Repeated decisions
    at the same node and non-completing/unsafe bag outcomes are excluded. The
    final selected edge is retained when it reaches the goal and the successful
    bag result supplies its observed finish time.
    """

    outcomes_by_decision: dict[str, Mapping[str, Any]] = {}
    outcomes_by_bag: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for raw in bag_results:
        _require(isinstance(raw, Mapping), "bag result must be an object")
        decision_id = raw.get("decision_id")
        if isinstance(decision_id, str) and decision_id:
            outcomes_by_decision[decision_id] = raw
        try:
            outcomes_by_bag[_runtime_bag_id(raw)].append(raw)
        except DLPLearningError:
            pass

    decisions_by_bag: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for raw in decision_rows:
        _require(isinstance(raw, Mapping), "decision row must be an object")
        decisions_by_bag[_runtime_bag_id(raw)].append(raw)

    transitions: list[dict[str, Any]] = []
    for bag_id, decisions in decisions_by_bag.items():
        ordered = sorted(
            decisions,
            key=lambda row: (
                _number(row.get("event_time"), "event_time"),
                str(row.get("decision_id", "")),
            ),
        )
        generic_outcome = next(
            (row for row in outcomes_by_bag.get(bag_id, ()) if _usable_outcome(row)),
            None,
        )
        for current, following in zip(ordered, ordered[1:]):
            decision_id = current.get("decision_id")
            outcome = (
                outcomes_by_decision.get(decision_id)
                if isinstance(decision_id, str)
                else None
            )
            if not _usable_outcome(outcome or generic_outcome):
                continue

            selected = _integer(current.get("selected_next"), "selected_next")
            if following.get("current_node") != selected:
                continue
            t0 = _number(current.get("event_time"), "event_time")
            t1 = _number(following.get("event_time"), "next event_time")
            if t1 <= t0:
                continue
            travel_time, static_current, static_selected = _static_potentials(current)
            transitions.append(
                {
                    "schema": TRANSITION_SCHEMA,
                    "t0": t0,
                    "current": _integer(current.get("current_node"), "current_node"),
                    "selected": selected,
                    "goal": _integer(current.get("goal_node"), "goal_node"),
                    "t1": t1,
                    "duration": t1 - t0,
                    "travel_time": travel_time,
                    "static_potential_current": static_current,
                    "static_potential_selected": static_selected,
                }
            )

        if not ordered:
            continue
        terminal = ordered[-1]
        selected = _integer(terminal.get("selected_next"), "selected_next")
        goal = _integer(terminal.get("goal_node"), "goal_node")
        if selected != goal:
            continue
        decision_id = terminal.get("decision_id")
        terminal_outcomes: list[Mapping[str, Any]] = []
        if isinstance(decision_id, str):
            decision_outcome = outcomes_by_decision.get(decision_id)
            if decision_outcome is not None:
                terminal_outcomes.append(decision_outcome)
        terminal_outcomes.extend(outcomes_by_bag.get(bag_id, ()))
        t0 = _number(terminal.get("event_time"), "event_time")
        finish_time: float | None = None
        for outcome in terminal_outcomes:
            if not _usable_outcome(outcome) or outcome.get("finish_time") is None:
                continue
            candidate_finish = _number(outcome.get("finish_time"), "finish_time")
            if candidate_finish > t0:
                finish_time = candidate_finish
                break
        if finish_time is None:
            continue
        travel_time, static_current, static_selected = _static_potentials(terminal)
        transitions.append(
            {
                "schema": TRANSITION_SCHEMA,
                "t0": t0,
                "current": _integer(terminal.get("current_node"), "current_node"),
                "selected": selected,
                "goal": goal,
                "t1": finish_time,
                "duration": finish_time - t0,
                "travel_time": travel_time,
                "static_potential_current": static_current,
                "static_potential_selected": static_selected,
            }
        )
    return sorted(transitions, key=_transition_order)


def _transition_order(row: Mapping[str, Any]) -> tuple[float, float, int, int, int]:
    return (
        _number(row.get("t0"), "t0"),
        _number(row.get("t1"), "t1"),
        _integer(row.get("current"), "current"),
        _integer(row.get("selected"), "selected"),
        _integer(row.get("goal"), "goal"),
    )


def chronological_split(
    transitions: Sequence[Mapping[str, Any]],
    *,
    train_fraction: float = 0.70,
    validation_fraction: float = 0.15,
) -> dict[str, list[dict[str, Any]]]:
    """Split one time-ordered stream without random neighboring-event leakage."""

    train_fraction = _number(train_fraction, "train_fraction")
    validation_fraction = _number(validation_fraction, "validation_fraction")
    _require(0.0 < train_fraction < 1.0, "train_fraction must be in (0, 1)")
    _require(
        0.0 < validation_fraction < 1.0
        and train_fraction + validation_fraction < 1.0,
        "validation_fraction must be positive and leave a test split",
    )
    ordered = [dict(row) for row in sorted(transitions, key=_transition_order)]
    _require(len(ordered) >= 3, "at least three transitions are required")
    time_groups: list[list[dict[str, Any]]] = []
    for row in ordered:
        if not time_groups or row["t0"] != time_groups[-1][0]["t0"]:
            time_groups.append([])
        time_groups[-1].append(row)
    _require(
        len(time_groups) >= 3,
        "at least three distinct transition times are required",
    )
    cumulative = [0]
    for group in time_groups:
        cumulative.append(cumulative[-1] + len(group))
    train_target = len(ordered) * train_fraction
    validation_target = len(ordered) * (train_fraction + validation_fraction)
    train_group_end = min(
        range(1, len(time_groups) - 1),
        key=lambda index: (abs(cumulative[index] - train_target), index),
    )
    validation_group_end = min(
        range(train_group_end + 1, len(time_groups)),
        key=lambda index: (abs(cumulative[index] - validation_target), index),
    )
    train_end = cumulative[train_group_end]
    validation_end = cumulative[validation_group_end]
    return {
        "train": ordered[:train_end],
        "validation": ordered[train_end:validation_end],
        "test": ordered[validation_end:],
    }


def _observed_edge_residual(row: Mapping[str, Any]) -> float:
    duration = _number(row.get("duration"), "duration")
    travel_time = _number(row.get("travel_time"), "travel_time")
    _require(duration >= 0.0 and travel_time >= 0.0, "negative transition cost")
    return duration - travel_time


def fit_edge_ewma(
    transitions: Sequence[Mapping[str, Any]],
    *,
    alpha: float = 0.10,
    min_support: int = 8,
) -> list[dict[str, Any]]:
    """Fit the P1 actual-edge-delay residual table in chronological order."""

    alpha = _number(alpha, "alpha")
    _require(0.0 < alpha <= 1.0, "alpha must be in (0, 1]")
    min_support = _integer(min_support, "min_support")
    _require(min_support > 0, "min_support must be positive")
    estimates: dict[tuple[int, int], float] = {}
    supports: dict[tuple[int, int], int] = defaultdict(int)
    for row in sorted(transitions, key=_transition_order):
        key = (
            _integer(row.get("current"), "current"),
            _integer(row.get("selected"), "selected"),
        )
        observed = _observed_edge_residual(row)
        estimates[key] = (
            observed
            if key not in estimates
            else estimates[key] + alpha * (observed - estimates[key])
        )
        supports[key] += 1
    return [
        {
            "from": source,
            "to": target,
            "residual_seconds": estimates[(source, target)],
            "support": supports[(source, target)],
        }
        for source, target in sorted(estimates)
        if supports[(source, target)] >= min_support
    ]


def _aggregate_observed_edges(
    transitions: Iterable[Mapping[str, Any]],
    *,
    min_support: int,
) -> dict[tuple[int, int], dict[str, Any]]:
    """Aggregate identity-free physical observations by directed edge."""

    min_support = _integer(min_support, "min_support")
    _require(min_support > 0, "min_support must be positive")
    durations: dict[tuple[int, int], list[float]] = defaultdict(list)
    static_times: dict[tuple[int, int], list[float]] = defaultdict(list)
    for row in transitions:
        source = _integer(row.get("current"), "current")
        target = _integer(row.get("selected"), "selected")
        duration = _number(row.get("duration"), "duration")
        travel_time = _number(row.get("travel_time"), "travel_time")
        _require(duration >= 0.0 and travel_time >= 0.0, "negative transition cost")
        key = (source, target)
        durations[key].append(duration)
        static_times[key].append(travel_time)
    result: dict[tuple[int, int], dict[str, Any]] = {}
    for key in sorted(durations):
        support = len(durations[key])
        if support < min_support or key[0] == key[1]:
            continue
        observed = math.fsum(durations[key]) / support
        static = math.fsum(static_times[key]) / support
        result[key] = {
            "from": key[0],
            "to": key[1],
            "observed_duration_seconds": observed,
            "static_travel_seconds": static,
            "edge_residual_seconds": observed - static,
            "support": support,
        }
    return result


def _bounded_paths(
    start: int,
    *,
    branch: int,
    max_downstream_hops: int,
    adjacency: Mapping[int, Sequence[int]],
    edges: Mapping[tuple[int, int], Mapping[str, Any]],
) -> dict[int, dict[str, Any]]:
    """Return the deterministic shortest-hop simple path to nearby nodes."""

    best: dict[int, dict[str, Any]] = {}
    stack: list[tuple[int, tuple[int, ...], float, float, int]] = [
        (start, (start,), 0.0, 0.0, 2**31 - 1)
    ]
    while stack:
        node, path, dynamic, static, support = stack.pop()
        hops = len(path) - 1
        if hops >= max_downstream_hops:
            continue
        for target in reversed(tuple(adjacency.get(node, ()))):
            if target == branch or target in path:
                continue
            edge = edges[(node, target)]
            candidate_path = (*path, target)
            candidate_dynamic = dynamic + float(edge["observed_duration_seconds"])
            candidate_static = static + float(edge["static_travel_seconds"])
            candidate_support = min(support, int(edge["support"]))
            candidate = {
                "path": candidate_path,
                "downstream_hops": hops + 1,
                "dynamic_duration_seconds": candidate_dynamic,
                "static_duration_seconds": candidate_static,
                "support": candidate_support,
            }
            previous = best.get(target)
            candidate_key = (
                int(candidate["downstream_hops"]),
                float(candidate["static_duration_seconds"]),
                tuple(candidate["path"]),
            )
            previous_key = (
                int(previous["downstream_hops"]),
                float(previous["static_duration_seconds"]),
                tuple(previous["path"]),
            ) if previous is not None else None
            if previous_key is None or candidate_key < previous_key:
                best[target] = candidate
            stack.append(
                (
                    target,
                    candidate_path,
                    candidate_dynamic,
                    candidate_static,
                    candidate_support,
                )
            )
    return best


def fit_reconvergent_corridors(
    transitions: Iterable[Mapping[str, Any]],
    *,
    max_hops: int = 4,
    min_support: int = 8,
) -> list[dict[str, Any]]:
    """Find local split/rejoin corridors and estimate their first-edge residuals.

    ``max_hops`` counts the branch's first edge. Support is the minimum
    observed-edge support on the selected local path, not a trajectory ID
    count. One nearest deterministic reconvergence is retained per branch.
    """

    max_hops = _integer(max_hops, "max_hops")
    _require(max_hops >= 2, "max_hops must be at least 2")
    edges = _aggregate_observed_edges(transitions, min_support=min_support)
    adjacency_lists: dict[int, list[int]] = defaultdict(list)
    for source, target in edges:
        adjacency_lists[source].append(target)
    adjacency = {
        source: tuple(sorted(targets))
        for source, targets in adjacency_lists.items()
    }

    corridors: list[dict[str, Any]] = []
    for branch in sorted(adjacency):
        successors = adjacency[branch]
        if len(successors) < 2:
            continue
        reach = {
            successor: _bounded_paths(
                successor,
                branch=branch,
                max_downstream_hops=max_hops - 1,
                adjacency=adjacency,
                edges=edges,
            )
            for successor in successors
        }
        nodes = sorted({node for paths in reach.values() for node in paths})
        candidates: list[tuple[tuple[Any, ...], int, tuple[int, ...]]] = []
        for node in nodes:
            participants = tuple(
                successor for successor in successors if node in reach[successor]
            )
            if len(participants) < 2:
                continue
            total_hops = tuple(
                1 + int(reach[successor][node]["downstream_hops"])
                for successor in participants
            )
            total_static = math.fsum(
                float(edges[(branch, successor)]["static_travel_seconds"])
                + float(reach[successor][node]["static_duration_seconds"])
                for successor in participants
            )
            key = (
                -len(participants),
                max(total_hops),
                sum(total_hops),
                total_static,
                node,
            )
            candidates.append((key, node, participants))
        if not candidates:
            continue
        _key, reconvergence, participants = min(candidates, key=lambda item: item[0])
        for successor in participants:
            first = edges[(branch, successor)]
            downstream = reach[successor][reconvergence]
            dynamic = float(first["observed_duration_seconds"]) + float(
                downstream["dynamic_duration_seconds"]
            )
            static = float(first["static_travel_seconds"]) + float(
                downstream["static_duration_seconds"]
            )
            corridors.append(
                {
                    "from": branch,
                    "to": successor,
                    "reconvergence": reconvergence,
                    "path": [branch, *downstream["path"]],
                    "hops": 1 + int(downstream["downstream_hops"]),
                    "dynamic_duration_seconds": dynamic,
                    "static_duration_seconds": static,
                    "residual_seconds": dynamic - static,
                    "support": min(int(first["support"]), int(downstream["support"])),
                    "participating_successor_count": len(participants),
                }
            )
    return sorted(
        corridors,
        key=lambda row: (
            int(row["from"]),
            int(row["to"]),
            int(row["reconvergence"]),
        ),
    )


def _corridor_artifact(
    corridors: Sequence[Mapping[str, Any]],
    *,
    beta: float,
    min_support: int,
    margin_seconds: float,
    detour_allowance_seconds: float,
) -> dict[str, Any]:
    beta = _number(beta, "beta")
    min_support = _integer(min_support, "min_support")
    margin_seconds = _number(margin_seconds, "margin_seconds")
    detour_allowance_seconds = _number(
        detour_allowance_seconds, "detour_allowance_seconds"
    )
    _require(beta >= 0.0, "beta must be non-negative")
    _require(min_support > 0, "min_support must be positive")
    _require(margin_seconds >= 0.0, "margin_seconds must be non-negative")
    _require(detour_allowance_seconds >= 0.0, "detour_allowance_seconds must be non-negative")
    edge_rows = [
        {
            "from": _integer(row.get("from"), "from"),
            "to": _integer(row.get("to"), "to"),
            "residual_seconds": _number(
                row.get("residual_seconds"), "residual_seconds"
            ),
            "support": _integer(row.get("support"), "support"),
        }
        for row in corridors
        if _integer(row.get("support"), "support") >= min_support
    ]
    _require(
        len({(row["from"], row["to"]) for row in edge_rows}) == len(edge_rows),
        "corridor projection contains duplicate first edges",
    )
    return {
        "schema": ARTIFACT_SCHEMA,
        "mode": "ewma",
        "beta": beta,
        "min_support": min_support,
        "margin_seconds": margin_seconds,
        "detour_allowance_seconds": detour_allowance_seconds,
        "edge_residuals": edge_rows,
        "value_residuals": [],
    }


def build_reconvergent_corridor_artifact(
    transitions: Iterable[Mapping[str, Any]],
    *,
    max_hops: int = 4,
    min_support: int = 8,
    beta: float = 0.5,
    margin_seconds: float = 0.5,
    detour_allowance_seconds: float = 0.0,
) -> dict[str, Any]:
    """Build an existing-runtime EWMA artifact containing first edges only."""

    corridors = fit_reconvergent_corridors(
        transitions, max_hops=max_hops, min_support=min_support
    )
    return _corridor_artifact(
        corridors,
        beta=beta,
        min_support=min_support,
        margin_seconds=margin_seconds,
        detour_allowance_seconds=detour_allowance_seconds,
    )


def fit_td_value_residuals(
    transitions: Sequence[Mapping[str, Any]],
    *,
    alpha: float = 0.10,
    min_support: int = 8,
) -> list[dict[str, Any]]:
    """Fit P2 residual V(node, goal) with one chronological TD(0) pass."""

    alpha = _number(alpha, "alpha")
    _require(0.0 < alpha <= 1.0, "alpha must be in (0, 1]")
    min_support = _integer(min_support, "min_support")
    _require(min_support > 0, "min_support must be positive")
    values: dict[tuple[int, int], float] = {}
    supports: dict[tuple[int, int], int] = defaultdict(int)
    for row in sorted(transitions, key=_transition_order):
        node = _integer(row.get("current"), "current")
        selected = _integer(row.get("selected"), "selected")
        goal = _integer(row.get("goal"), "goal")
        duration = _number(row.get("duration"), "duration")
        static_current = _number(
            row.get("static_potential_current"), "static_potential_current"
        )
        static_selected = _number(
            row.get("static_potential_selected"), "static_potential_selected"
        )
        _require(duration >= 0.0, "negative transition duration")
        key = (node, goal)
        downstream = 0.0 if selected == goal else values.get((selected, goal), 0.0)
        target_residual = duration + static_selected + downstream - static_current
        old = values.get(key, 0.0)
        values[key] = old + alpha * (target_residual - old)
        supports[key] += 1
    return [
        {
            "node": node,
            "goal": goal,
            "residual_seconds": values[(node, goal)],
            "support": supports[(node, goal)],
        }
        for node, goal in sorted(values)
        if supports[(node, goal)] >= min_support
    ]


def build_artifact(
    transitions: Sequence[Mapping[str, Any]],
    *,
    mode: str,
    beta: float = 0.5,
    alpha: float = 0.10,
    min_support: int = 8,
    margin_seconds: float = 0.5,
    detour_allowance_seconds: float = 0.0,
) -> dict[str, Any]:
    """Freeze one compact runtime artifact; timestamps and identities are absent."""

    _require(mode in MODES, f"mode must be one of {MODES}")
    beta = _number(beta, "beta")
    margin_seconds = _number(margin_seconds, "margin_seconds")
    detour_allowance_seconds = _number(
        detour_allowance_seconds, "detour_allowance_seconds"
    )
    _require(beta >= 0.0, "beta must be non-negative")
    _require(margin_seconds >= 0.0, "margin_seconds must be non-negative")
    _require(
        detour_allowance_seconds >= 0.0,
        "detour_allowance_seconds must be non-negative",
    )
    edges = fit_edge_ewma(
        transitions, alpha=alpha, min_support=min_support
    )
    values = (
        fit_td_value_residuals(
            transitions, alpha=alpha, min_support=min_support
        )
        if mode == "td"
        else []
    )
    return {
        "schema": ARTIFACT_SCHEMA,
        "mode": mode,
        "beta": beta,
        "min_support": _integer(min_support, "min_support"),
        "margin_seconds": margin_seconds,
        "detour_allowance_seconds": detour_allowance_seconds,
        "edge_residuals": edges,
        "value_residuals": values,
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                value = json.loads(line)
                _require(isinstance(value, dict), f"non-object JSONL row: {path}")
                rows.append(value)
    return rows


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(dict(row), sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decisions", type=Path)
    parser.add_argument("--bag-results", type=Path)
    parser.add_argument(
        "--transitions-input",
        type=Path,
        help="read an existing identity-free transition JSONL instead of raw traces",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--transitions-output", type=Path)
    parser.add_argument("--strategy", choices=("edge", "corridor"), default="edge")
    parser.add_argument("--max-hops", type=int, default=4)
    parser.add_argument("--corridor-report-output", type=Path)
    parser.add_argument("--mode", choices=MODES, default="ewma")
    parser.add_argument("--alpha", type=float, default=0.10)
    parser.add_argument("--beta", type=float, default=0.5)
    parser.add_argument("--min-support", type=int, default=8)
    parser.add_argument("--margin-seconds", type=float, default=0.5)
    parser.add_argument("--detour-allowance-seconds", type=float, default=0.0)
    parser.add_argument("--train-fraction", type=float, default=0.70)
    parser.add_argument("--validation-fraction", type=float, default=0.15)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.transitions_input is not None:
            _require(
                args.decisions is None and args.bag_results is None,
                "transitions-input cannot be combined with decisions or bag-results",
            )
            transitions = read_jsonl(args.transitions_input)
            transition_source = "transitions_input"
        else:
            _require(
                args.decisions is not None and args.bag_results is not None,
                "provide transitions-input or both decisions and bag-results",
            )
            transitions = build_transitions(
                read_jsonl(args.decisions), read_jsonl(args.bag_results)
            )
            transition_source = "decisions_and_bag_results"
        split = chronological_split(
            transitions,
            train_fraction=args.train_fraction,
            validation_fraction=args.validation_fraction,
        )
        corridors: list[dict[str, Any]] = []
        if args.strategy == "corridor":
            _require(args.mode == "ewma", "corridor strategy requires ewma mode")
            corridors = fit_reconvergent_corridors(
                split["train"],
                max_hops=args.max_hops,
                min_support=args.min_support,
            )
            artifact = _corridor_artifact(
                corridors,
                beta=args.beta,
                min_support=args.min_support,
                margin_seconds=args.margin_seconds,
                detour_allowance_seconds=args.detour_allowance_seconds,
            )
        else:
            _require(
                args.corridor_report_output is None,
                "corridor report requires corridor strategy",
            )
            artifact = build_artifact(
                split["train"],
                mode=args.mode,
                alpha=args.alpha,
                beta=args.beta,
                min_support=args.min_support,
                margin_seconds=args.margin_seconds,
                detour_allowance_seconds=args.detour_allowance_seconds,
            )
        _write_json(args.output, artifact)
        if args.corridor_report_output is not None:
            _write_json(
                args.corridor_report_output,
                {
                    "schema": CORRIDOR_SCHEMA,
                    "max_hops": args.max_hops,
                    "min_support": args.min_support,
                    "corridor_count": len(corridors),
                    "corridors": corridors,
                },
            )
        if args.transitions_output is not None:
            _write_jsonl(args.transitions_output, transitions)
        print(
            json.dumps(
                {
                    "transition_source": transition_source,
                    "transition_count": len(transitions),
                    "train_count": len(split["train"]),
                    "validation_count": len(split["validation"]),
                    "test_count": len(split["test"]),
                    "strategy": args.strategy,
                    "corridor_count": len(corridors),
                    "edge_residual_count": len(artifact["edge_residuals"]),
                    "value_residual_count": len(artifact["value_residuals"]),
                },
                sort_keys=True,
            )
        )
        return 0
    except (DLPLearningError, OSError, json.JSONDecodeError) as exc:
        print(f"G24 DLP learning failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
