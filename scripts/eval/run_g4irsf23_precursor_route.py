#!/usr/bin/env python3
"""Build the mandatory G23 lifecycle-precursor Route experiment.

This is a thin planner, not a new planner or simulator.  It joins a selected
``storage_out`` Source anchor to the preceding ``storage_in`` runtime segment
of the same task, streams the existing G22 Route census once, and retains the
last real multi-action Route event before the storage-out release.  Exact
actions are then emitted through G22's existing G21 wire contract: S4 is the
implicit baseline and treatments are every other legal edge plus legal WAIT.

The large census is read in place and is never copied.  This command only
plans groups and targets; exact replay remains the existing G22 exact-pair
entry point.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import json
import math
from pathlib import Path
from statistics import fmean, median
import sys
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from scripts.eval import run_g4irsf22_action_timing as g22


GROUP_SCHEMA = "czr005.g4irsf23.precursor_route_group.v1"
PLAN_SCHEMA = "czr005.g4irsf23.precursor_route_plan.v1"
ANCHOR_SCHEMA = "czr005.g4irsf23.precursor_anchor_address.v1"
PAIR_SHARD_MANIFEST_SCHEMA = "czr005.g4irsf23.precursor_route_pair_shards.v1"
MERGED_PAIR_SCHEMA = "czr005.g4irsf23.precursor_route_merged_pairs.v1"
PAIR_GATE_SCHEMA = "czr005.g4irsf23.precursor_route_exact_gate.v1"
COMPACT_ACTION_SCHEMA = "czr005.g4irsf23.precursor_route_action_effect.v1"
COMPACT_GROUP_SCHEMA = "czr005.g4irsf23.precursor_route_group_choice.v1"
COMPACT_RESULT_SCHEMA = "czr005.g4irsf23.precursor_route_pilot_result.v1"
COMPACT_SUMMARY_SCHEMA = "czr005.g4irsf23.precursor_route_pilot_summary.v1"
RESEARCH_PROFILE = g22.RESEARCH_PROFILE
TARGET_NODE = 52
TARGET_LEG = "storage_out"
PREDECESSOR_LEG = "storage_in"
TARGET_BLOCKS = (7, 8)
HORIZONS = g22.HORIZONS

PILOT_BLOCK_GROUPS = {7: 384, 8: 128}
FORMAL_BLOCK_GROUPS = {7: 1536, 8: 512}
DEFAULT_H_SYSTEM_BLOCK_GROUPS = {7: 192, 8: 64}
# A 16-group system shard keeps each source-prefix batch bounded and
# restartable; every Route action still uses the ordinary G22 baseline path.
DEFAULT_SYSTEM_SHARD_GROUPS = 16
DEFAULT_H_BAG_SHARD_GROUPS = 32
DEFAULT_PAIR_WORKERS = 4

PILOT_REQUIRED_H_BAG_GROUPS = 512
PILOT_REQUIRED_H_SYSTEM_GROUPS = 256
PILOT_REQUIRED_FAIR_PROMOTION_GROUPS = 16
PILOT_REQUIRED_BLOCK8_PROMOTION_GROUPS = 4
PILOT_REQUIRED_PROMOTION_STRATA = 3
PILOT_REQUIRED_ACTION_CHANGE_RATE = 0.80
USABLE_SYSTEM_GAIN_SECONDS = 0.01
STRONG_SYSTEM_GAIN_SECONDS = 0.05
EFFECT_TOLERANCE_SECONDS = 0.001


class PrecursorRouteError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PrecursorRouteError(message)


def _finite(value: Any, field: str, *, minimum: float | None = None) -> float:
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


def _integer(value: Any, field: str, *, minimum: int | None = None) -> int:
    _require(type(value) is int, f"{field} must be an integer")
    if minimum is not None:
        _require(value >= minimum, f"{field} must be >= {minimum}")
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _read_rows(path: Path) -> list[dict[str, Any]]:
    """Read JSONL, a JSON list, or a raw-cache object containing input_rows."""

    if path.suffix.lower() == ".jsonl":
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                value = json.loads(line)
                _require(isinstance(value, Mapping), f"{path}:{line_number} is not an object")
                rows.append(dict(value))
        return rows
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, Mapping):
        value = value.get("input_rows", value.get("groups", value.get("anchors")))
    _require(isinstance(value, list), f"{path} must contain a row list")
    _require(all(isinstance(row, Mapping) for row in value), f"{path} contains a non-object row")
    return [dict(row) for row in value]


def load_frozen_2x_requests(root: Path = ROOT) -> list[dict[str, Any]]:
    """Load only the frozen 2x request descriptors; no native state is built."""

    from scripts.eval import run_g4irsf19_bounded_capacity as g19

    rows, _ = g19.load_g18_scale_input(2, root=root)
    _require(len(rows) == 87_206, "G23 precursor input must contain 87,206 segments")
    return [dict(row) for row in rows]


def normalize_request_descriptors(
    rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Attach the native runtime ID, which is exactly the input row offset."""

    normalized: list[dict[str, Any]] = []
    seen_segments: set[str] = set()
    for input_offset, raw in enumerate(rows):
        explicit_runtime_id = raw.get("runtime_bag_id")
        runtime_bag_id = (
            _integer(explicit_runtime_id, "request.runtime_bag_id", minimum=0)
            if explicit_runtime_id is not None
            else input_offset
        )
        task_id = _integer(raw.get("task_id"), "request.task_id", minimum=0)
        segment_id = raw.get("segment_id")
        leg = raw.get("leg")
        _require(isinstance(segment_id, str) and segment_id, "request.segment_id is required")
        _require(segment_id not in seen_segments, f"duplicate request segment_id: {segment_id}")
        _require(isinstance(leg, str) and leg, "request.leg is required")
        seen_segments.add(segment_id)
        normalized.append(
            {
                "runtime_bag_id": runtime_bag_id,
                "task_id": task_id,
                "segment_id": segment_id,
                "leg": leg,
                "release_time": _finite(raw.get("pass_time"), "request.pass_time", minimum=0.0),
                "start": raw.get("start"),
                "goal": raw.get("goal"),
            }
        )
    _require(
        len({int(row["runtime_bag_id"]) for row in normalized}) == len(normalized),
        "duplicate request runtime_bag_id",
    )
    return normalized


def normalize_source_anchor(
    row: Mapping[str, Any], *, require_target_block: bool = True
) -> dict[str, Any]:
    """Keep only the Source address and timing fields, never outcome labels."""

    runtime_bag_id = _integer(row.get("runtime_bag_id"), "anchor.runtime_bag_id", minimum=0)
    front = row.get("front_runtime_bag_id", runtime_bag_id)
    _require(front == runtime_bag_id, "anchor is not the current Source front")
    task_id = _integer(row.get("task_id"), "anchor.task_id", minimum=0)
    segment_id = row.get("segment_id")
    _require(isinstance(segment_id, str) and segment_id, "anchor.segment_id is required")
    leg = row.get("leg", TARGET_LEG)
    node = row.get("node", TARGET_NODE)
    release_block = _integer(row.get("release_block"), "anchor.release_block", minimum=0)
    _require(leg == TARGET_LEG and TARGET_LEG in segment_id, "anchor must be storage_out")
    _require(node == TARGET_NODE, "anchor must be at node 52")
    if require_target_block:
        _require(release_block in TARGET_BLOCKS, "anchor release block must be 7 or 8")
    event_ordinal = _integer(row.get("event_ordinal"), "anchor.event_ordinal", minimum=0)
    event_time = _finite(row.get("event_time"), "anchor.event_time", minimum=0.0)
    event_seq = row.get("event_seq")
    if event_seq is not None:
        event_seq = _integer(event_seq, "anchor.event_seq", minimum=0)
    source_group_id = row.get("source_group_id", row.get("descriptor_id"))
    if not isinstance(source_group_id, str) or not source_group_id:
        source_group_id = f"source-{event_ordinal}-{runtime_bag_id}"
    normalized = {
        "schema": ANCHOR_SCHEMA,
        "source_group_id": source_group_id,
        "event_ordinal": event_ordinal,
        "event_time": event_time,
        "runtime_bag_id": runtime_bag_id,
        "task_id": task_id,
        "segment_id": segment_id,
        "leg": TARGET_LEG,
        "node": TARGET_NODE,
        "release_block": release_block,
        "absolute_ids_are_trace_only": True,
    }
    if event_seq is not None:
        normalized["event_seq"] = event_seq
    return normalized


def link_lifecycle_anchors(
    anchors: Iterable[Mapping[str, Any]],
    request_rows: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Map storage_out anchors to the latest preceding storage_in segment."""

    requests = normalize_request_descriptors(request_rows)
    by_runtime = {int(row["runtime_bag_id"]): row for row in requests}
    by_task: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for request in requests:
        by_task[int(request["task_id"])].append(request)

    # A Source census can contain repeated legal opportunities for one queued
    # bag.  The first opportunity is the outcome-free canonical anchor.
    first_by_bag: dict[int, dict[str, Any]] = {}
    input_anchor_count = 0
    out_of_scope_release_block_count = 0
    for raw in anchors:
        input_anchor_count += 1
        anchor = normalize_source_anchor(raw, require_target_block=False)
        if int(anchor["release_block"]) not in TARGET_BLOCKS:
            out_of_scope_release_block_count += 1
            continue
        bag = int(anchor["runtime_bag_id"])
        incumbent = first_by_bag.get(bag)
        key = (
            float(anchor["event_time"]),
            int(anchor.get("event_seq", anchor["event_ordinal"])),
            int(anchor["event_ordinal"]),
        )
        if incumbent is None or key < (
            float(incumbent["event_time"]),
            int(incumbent.get("event_seq", incumbent["event_ordinal"])),
            int(incumbent["event_ordinal"]),
        ):
            first_by_bag[bag] = anchor

    links: list[dict[str, Any]] = []
    unmatched = 0
    for anchor in first_by_bag.values():
        storage_out = by_runtime.get(int(anchor["runtime_bag_id"]))
        if (
            storage_out is None
            or storage_out["task_id"] != anchor["task_id"]
            or storage_out["segment_id"] != anchor["segment_id"]
            or storage_out["leg"] != TARGET_LEG
        ):
            unmatched += 1
            continue
        predecessors = [
            row
            for row in by_task[int(anchor["task_id"])]
            if row["leg"] == PREDECESSOR_LEG
            and (float(row["release_time"]), int(row["runtime_bag_id"]))
            < (float(storage_out["release_time"]), int(storage_out["runtime_bag_id"]))
        ]
        if not predecessors:
            unmatched += 1
            continue
        predecessor = max(
            predecessors,
            key=lambda row: (float(row["release_time"]), int(row["runtime_bag_id"])),
        )
        links.append(
            {
                "anchor_address": anchor,
                "task_id": int(anchor["task_id"]),
                "release_block": int(anchor["release_block"]),
                "storage_out_runtime_bag_id": int(storage_out["runtime_bag_id"]),
                "storage_out_segment_id": str(storage_out["segment_id"]),
                "storage_out_release_time": float(storage_out["release_time"]),
                "predecessor_runtime_bag_id": int(predecessor["runtime_bag_id"]),
                "predecessor_segment_id": str(predecessor["segment_id"]),
                "predecessor_release_time": float(predecessor["release_time"]),
            }
        )
    links.sort(
        key=lambda row: (
            int(row["release_block"]),
            float(row["storage_out_release_time"]),
            int(row["storage_out_runtime_bag_id"]),
        )
    )
    return links, {
        "input_anchor_count": input_anchor_count,
        "out_of_scope_release_block_count": out_of_scope_release_block_count,
        "unique_storage_out_anchor_count": len(first_by_bag),
        "lifecycle_linked_anchor_count": len(links),
        "lifecycle_unmatched_anchor_count": unmatched,
    }


def _event_order_key(row: Mapping[str, Any]) -> tuple[float, int, int]:
    ordinal = int(row["event_ordinal"])
    return (
        float(row["event_time"]),
        int(row.get("event_seq", ordinal)),
        ordinal,
    )


def stream_lifecycle_precursors(
    links: Sequence[Mapping[str, Any]], census_path: Path
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Stream the large G22 census and retain one nearest event per link."""

    links_by_runtime: dict[int, list[tuple[int, Mapping[str, Any]]]] = defaultdict(list)
    for index, link in enumerate(links):
        links_by_runtime[int(link["predecessor_runtime_bag_id"])].append((index, link))
    best: dict[int, dict[str, Any]] = {}
    scanned = 0
    relevant = 0
    with census_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            scanned += 1
            value = json.loads(line)
            _require(isinstance(value, Mapping), f"{census_path}:{line_number} is not an object")
            runtime_bag_id = value.get("runtime_bag_id")
            if type(runtime_bag_id) is not int or runtime_bag_id not in links_by_runtime:
                continue
            relevant += 1
            event = g22.normalize_route_event(value)
            for link_index, link in links_by_runtime[runtime_bag_id]:
                # "Before node 52" is bounded by the protected storage-out
                # release, not by a later Source queue opportunity.
                if float(event["event_time"]) > float(link["storage_out_release_time"]):
                    continue
                incumbent = best.get(link_index)
                if incumbent is None or _event_order_key(event) > _event_order_key(incumbent):
                    best[link_index] = event

    groups: list[dict[str, Any]] = []
    for index, link in enumerate(links):
        event = best.get(index)
        if event is None:
            continue
        anchor = dict(link["anchor_address"])
        groups.append(
            {
                **event,
                "schema": GROUP_SCHEMA,
                "kind": "I3_NEXT_EDGE",
                "route_event_schema": g22.EVENT_SCHEMA,
                "timing_stage": "precursor",
                "event_identity": g22.event_identity(event),
                "anchor_event_identity": anchor,
                "anchor_address": anchor,
                "lifecycle_address": {
                    "task_id": int(link["task_id"]),
                    "predecessor_runtime_bag_id": int(link["predecessor_runtime_bag_id"]),
                    "predecessor_segment_id": str(link["predecessor_segment_id"]),
                    "storage_out_runtime_bag_id": int(link["storage_out_runtime_bag_id"]),
                    "storage_out_segment_id": str(link["storage_out_segment_id"]),
                    "storage_out_release_time": float(link["storage_out_release_time"]),
                },
                "release_block": int(link["release_block"]),
                "precursor_time_gap_seconds": float(link["storage_out_release_time"])
                - float(event["event_time"]),
                "outcome_free": True,
                "model_feature_source": "PRE_ACTION_ROUTE_CANDIDATE_OBSERVATIONS_ONLY",
                "absolute_ids_are_trace_only": True,
            }
        )
    return groups, {
        "route_census_row_count": scanned,
        "route_census_relevant_row_count": relevant,
        "route_matched_anchor_count": len(groups),
        "route_unmatched_anchor_count": len(links) - len(groups),
    }


def _bucket(value: float, low: float, high: float) -> str:
    if value < low:
        return "low"
    if value < high:
        return "mid"
    return "high"


def outcome_free_stratum(group: Mapping[str, Any]) -> str:
    candidates = group["candidate_observations"]
    queue = max(float(row.get("target_queue_length", 0.0)) for row in candidates)
    contention = max(float(row.get("priority_local_contention", 0.0)) for row in candidates)
    return "|".join(
        (
            f"node_{int(group['current_node'])}",
            f"queue_{_bucket(queue, 4.0, 16.0)}",
            f"contention_{_bucket(contention, 4.0, 16.0)}",
            f"t{int(float(group['event_time']) // 900.0)}",
        )
    )


def _selection_score(group: Mapping[str, Any]) -> float:
    score = 0.0
    for candidate in group["candidate_observations"]:
        score = max(
            score,
            float(candidate.get("target_queue_length", 0.0))
            + float(candidate.get("target_scheduled_incoming", 0.0))
            + float(candidate.get("priority_local_contention", 0.0))
            + max(
                0.0,
                float(candidate.get("target_next_available", group["event_time"]))
                - float(group["event_time"])
                - float(candidate.get("travel_time", 0.0)),
            ),
        )
    return score


def _diverse_prefix(rows: Sequence[Mapping[str, Any]], count: int) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in rows:
        row = dict(_plain(raw))
        row["selection_stratum"] = outcome_free_stratum(row)
        row["selection_score"] = _selection_score(row)
        buckets[str(row["selection_stratum"])].append(row)
    for values in buckets.values():
        values.sort(
            key=lambda row: (
                -float(row["selection_score"]),
                float(row["event_time"]),
                int(row["event_ordinal"]),
            )
        )
    order = sorted(buckets, key=lambda key: (-float(buckets[key][0]["selection_score"]), key))
    selected: list[dict[str, Any]] = []
    while order and len(selected) < count:
        next_order: list[str] = []
        for key in order:
            values = buckets[key]
            if values and len(selected) < count:
                selected.append(values.pop(0))
            if values:
                next_order.append(key)
        order = next_order
    return selected


def select_precursor_groups(
    candidates: Sequence[Mapping[str, Any]],
    *,
    block_group_targets: Mapping[int, int],
    block_h_system_targets: Mapping[int, int],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _require(set(block_group_targets) == set(TARGET_BLOCKS), "group quotas must cover blocks 7 and 8")
    _require(set(block_h_system_targets) <= set(block_group_targets), "unknown H_system block")
    selected: list[dict[str, Any]] = []
    block_audit: dict[str, Any] = {}
    for block in TARGET_BLOCKS:
        requested = _integer(block_group_targets[block], f"block {block} quota", minimum=0)
        h_system = _integer(
            block_h_system_targets.get(block, 0), f"block {block} H_system quota", minimum=0
        )
        _require(h_system <= requested, f"block {block} H_system quota exceeds group quota")
        available = [row for row in candidates if int(row["release_block"]) == block]
        block_rows = _diverse_prefix(available, requested)
        for index, row in enumerate(block_rows):
            row["assigned_horizons"] = list(HORIZONS if index < h_system else ("H_bag",))
            row["legal_actions"] = g22.enumerate_legal_actions(row)
            selected.append(row)
        block_audit[str(block)] = {
            "available_groups": len(available),
            "requested_groups": requested,
            "selected_groups": len(block_rows),
            "group_shortfall": max(0, requested - len(block_rows)),
            "requested_h_system_groups": h_system,
            "selected_h_system_groups": min(h_system, len(block_rows)),
            "h_system_shortfall": max(0, h_system - len(block_rows)),
            "outcome_free_strata": len({row["selection_stratum"] for row in block_rows}),
        }
    complete = all(
        row["group_shortfall"] == 0 and row["h_system_shortfall"] == 0
        for row in block_audit.values()
    )
    return selected, {
        "status": "COMPLETE" if complete else "NO_GO_INSUFFICIENT_PRECURSOR_SUPPORT",
        "blocks": block_audit,
        "absolute_ids_used_as_model_features": False,
        "outcome_fields_used_as_model_features": False,
    }


def build_precursor_targets(groups: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Reuse the G21 exact action schema through G22's proven constructor."""

    targets: list[dict[str, Any]] = []
    for group in groups:
        horizons = group.get("assigned_horizons", ["H_bag"])
        _require(
            isinstance(horizons, list)
            and horizons
            and all(horizon in HORIZONS for horizon in horizons),
            "invalid assigned_horizons",
        )
        targets.extend(g22.build_action_targets(group, horizons=horizons))
    _require(
        len({g22.target_identity(target) for target in targets}) == len(targets),
        "duplicate exact action target identity",
    )
    return targets


def precursor_group_id(row: Mapping[str, Any]) -> str:
    """Return the native Route event identity shared by all action targets."""

    population_group = row.get("population_group_id")
    population_selection = row.get("population_selection_id")
    _require(
        isinstance(population_group, str) and population_group,
        "precursor target omitted population_group_id",
    )
    _require(
        isinstance(population_selection, str) and population_selection,
        "precursor target omitted population_selection_id",
    )
    ordinal = _integer(row.get("event_ordinal"), "target.event_ordinal", minimum=0)
    return f"{population_group}|{population_selection}|{ordinal}"


def precursor_target_id(row: Mapping[str, Any]) -> str:
    """Use the G21 native descriptor identity without inventing a new seal."""

    action_kind = row.get("action_kind")
    _require(action_kind in {"NEXT_EDGE", "WAIT"}, "invalid precursor action_kind")
    selected = row.get("selected_next_node")
    if action_kind == "NEXT_EDGE":
        _require(type(selected) is int, "NEXT_EDGE target omitted selected_next_node")
        action = f"NEXT_EDGE:{selected}"
    else:
        _require(selected is None, "WAIT target fabricated selected_next_node")
        action = "WAIT"
    horizon = row.get("horizon")
    _require(horizon in HORIZONS, "invalid precursor target horizon")
    return f"{precursor_group_id(row)}|{horizon}|{action}"


def _targets_by_group(
    targets: Sequence[Mapping[str, Any]],
) -> list[tuple[str, list[dict[str, Any]]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in targets:
        target = dict(_plain(raw))
        grouped[precursor_group_id(target)].append(target)
    ordered: list[tuple[str, list[dict[str, Any]]]] = []
    for group_id, rows in grouped.items():
        rows.sort(
            key=lambda row: (
                HORIZONS.index(str(row["horizon"])),
                0 if row["action_kind"] == "NEXT_EDGE" else 1,
                int(row["selected_next_node"])
                if row.get("selected_next_node") is not None
                else -1,
            )
        )
        _require(
            len({precursor_target_id(row) for row in rows}) == len(rows),
            f"duplicate precursor target identity in {group_id}",
        )
        ordered.append((group_id, rows))
    ordered.sort(
        key=lambda item: (
            int(item[1][0]["event_ordinal"]),
            int(item[1][0]["runtime_bag_id"]),
            item[0],
        )
    )
    return ordered


def build_pair_shard_manifest(
    targets: Sequence[Mapping[str, Any]],
    *,
    system_shard_groups: int = DEFAULT_SYSTEM_SHARD_GROUPS,
    h_bag_shard_groups: int = DEFAULT_H_BAG_SHARD_GROUPS,
    workers: int = DEFAULT_PAIR_WORKERS,
) -> dict[str, Any]:
    """Partition the 512-group Pilot without splitting a native checkpoint.

    A group in the sparse system panel runs its two legal treatments at both
    horizons in one call.  The remaining groups run the same two treatments at
    H_bag only.  Consequently every planned target appears exactly once.
    """

    _require(type(system_shard_groups) is int and system_shard_groups >= 1,
             "system_shard_groups must be >= 1")
    _require(type(h_bag_shard_groups) is int and h_bag_shard_groups >= 1,
             "h_bag_shard_groups must be >= 1")
    _require(type(workers) is int and workers >= 1, "workers must be >= 1")
    groups = _targets_by_group(targets)
    system_groups: list[tuple[str, list[dict[str, Any]]]] = []
    h_bag_groups: list[tuple[str, list[dict[str, Any]]]] = []
    for item in groups:
        horizons = {str(row["horizon"]) for row in item[1]}
        actions_by_horizon = {
            horizon: {
                (str(row["action_kind"]), row.get("selected_next_node"))
                for row in item[1]
                if row["horizon"] == horizon
            }
            for horizon in horizons
        }
        for horizon, actions in actions_by_horizon.items():
            _require(
                len(actions) == 2
                and sum(action == "NEXT_EDGE" for action, _ in actions) == 1
                and ("WAIT", None) in actions,
                f"precursor group must contain exactly NEXT_EDGE+WAIT at {horizon}",
            )
        if "H_system" in horizons:
            _require(horizons == set(HORIZONS), "system group omitted H_bag targets")
            _require(
                actions_by_horizon["H_bag"] == actions_by_horizon["H_system"],
                "H_system action set disagrees with H_bag",
            )
            system_groups.append(item)
        else:
            _require(horizons == {"H_bag"}, "unsupported precursor horizon set")
            h_bag_groups.append(item)

    shards: list[dict[str, Any]] = []
    for panel, panel_groups, shard_size in (
        ("SYSTEM_AND_BAG", system_groups, system_shard_groups),
        ("H_BAG_ONLY", h_bag_groups, h_bag_shard_groups),
    ):
        prefix = "system" if panel == "SYSTEM_AND_BAG" else "hbag"
        for offset in range(0, len(panel_groups), shard_size):
            selected = panel_groups[offset : offset + shard_size]
            selected_targets = [
                row
                for _, rows in selected
                for row in rows
                if (panel == "SYSTEM_AND_BAG" and row["horizon"] == "H_system")
                or (panel == "H_BAG_ONLY" and row["horizon"] == "H_bag")
            ]
            shards.append(
                {
                    "shard_id": f"{prefix}-{offset // shard_size:03d}",
                    "panel": panel,
                    "group_count": len(selected),
                    "target_count": len(selected_targets),
                    "group_ids": [group_id for group_id, _ in selected],
                    "target_ids": [precursor_target_id(row) for row in selected_targets],
                    "horizon_target_counts": {
                        horizon: sum(row["horizon"] == horizon for row in selected_targets)
                        for horizon in HORIZONS
                    },
                    "action_target_counts": {
                        action: sum(row["action_kind"] == action for row in selected_targets)
                        for action in ("NEXT_EDGE", "WAIT")
                    },
                    "min_event_ordinal": min(int(rows[0]["event_ordinal"]) for _, rows in selected),
                    "max_event_ordinal": max(int(rows[0]["event_ordinal"]) for _, rows in selected),
                }
            )

    all_target_ids = [target_id for shard in shards for target_id in shard["target_ids"]]
    planned_target_ids = [precursor_target_id(row) for row in targets]
    subsumed_h_bag_ids = {
        precursor_target_id(row)
        for _, rows in system_groups
        for row in rows
        if row["horizon"] == "H_bag"
    }
    _require(len(set(all_target_ids)) == len(all_target_ids), "shards overlap")
    _require(
        set(all_target_ids).isdisjoint(subsumed_h_bag_ids)
        and set(all_target_ids) | subsumed_h_bag_ids == set(planned_target_ids),
        "execution and H_system-subsumed targets do not partition the plan",
    )
    return {
        "schema": PAIR_SHARD_MANIFEST_SCHEMA,
        "execution_default": "PLAN_ONLY_DO_NOT_START_PROCESSES",
        "research_profile": RESEARCH_PROFILE,
        "max_workers": workers,
        "partition_order": "CONTIGUOUS_EVENT_ORDINAL_KEEP_COMPLETE_GROUP",
        "native_reuse_contract": (
            "ONE_MONOTONIC_SOURCE_REPLAY_PER_SHARD;ONE_CHECKPOINT_AND_PROBE_PER_EVENT;"
            "ROUTE_BASELINE_AND_TREATMENT_BRANCHES_REMAIN_PER_TARGET"
        ),
        "group_count": len(groups),
        "system_group_count": len(system_groups),
        "h_bag_only_group_count": len(h_bag_groups),
        "planned_target_count": len(planned_target_ids),
        "expected_execution_target_count": len(all_target_ids),
        "h_system_subsumed_h_bag_target_count": len(subsumed_h_bag_ids),
        "h_system_subsumption_contract": (
            "SAME_ACTION_H_SYSTEM_PAIR_PRESERVES_ACTION_CERTIFICATE_AND_"
            "AFFECTED_BAG_COMPLETION_DELTA;NO_DUPLICATE_H_BAG_REPLAY"
        ),
        "horizon_target_counts": {
            horizon: sum(row.get("horizon") == horizon for row in targets)
            for horizon in HORIZONS
        },
        "shard_count": len(shards),
        "shards": shards,
    }


def execution_targets(
    targets: Sequence[Mapping[str, Any]], manifest: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Resolve the manifest allow-list from the larger protocol plan."""

    _require(manifest.get("schema") == PAIR_SHARD_MANIFEST_SCHEMA,
             "pair shard manifest has the wrong schema")
    shards = manifest.get("shards")
    _require(isinstance(shards, list), "pair shard manifest omitted shards")
    target_ids = [
        target_id
        for shard in shards
        if isinstance(shard, Mapping)
        for target_id in shard.get("target_ids", [])
    ]
    _require(len(set(target_ids)) == len(target_ids), "manifest execution targets overlap")
    by_id = {precursor_target_id(row): dict(row) for row in targets}
    _require(len(by_id) == len(targets), "plan has duplicate target identities")
    unknown = [target_id for target_id in target_ids if target_id not in by_id]
    _require(not unknown, f"manifest has unknown execution targets: {unknown}")
    resolved = [by_id[target_id] for target_id in target_ids]
    _require(
        len(resolved) == manifest.get("expected_execution_target_count"),
        "manifest expected execution target count drifted",
    )
    return resolved


def select_manifest_shard(
    targets: Sequence[Mapping[str, Any]],
    manifest: Mapping[str, Any],
    shard_id: str,
) -> list[dict[str, Any]]:
    _require(manifest.get("schema") == PAIR_SHARD_MANIFEST_SCHEMA,
             "pair shard manifest has the wrong schema")
    shards = manifest.get("shards")
    _require(isinstance(shards, list), "pair shard manifest omitted shards")
    matches = [row for row in shards if isinstance(row, Mapping) and row.get("shard_id") == shard_id]
    _require(len(matches) == 1, f"pair shard id must match exactly once: {shard_id}")
    target_ids = matches[0].get("target_ids")
    _require(isinstance(target_ids, list) and target_ids,
             f"pair shard {shard_id} omitted target_ids")
    _require(len(set(target_ids)) == len(target_ids), f"pair shard {shard_id} has duplicate targets")
    by_id = {precursor_target_id(row): dict(row) for row in targets}
    _require(len(by_id) == len(targets), "plan has duplicate target identities")
    unknown = [target_id for target_id in target_ids if target_id not in by_id]
    _require(not unknown, f"pair shard {shard_id} has unknown targets: {unknown}")
    selected = [by_id[target_id] for target_id in target_ids]
    _require(len(selected) == matches[0].get("target_count"),
             f"pair shard {shard_id} target_count drifted")
    return selected


def _pair_id(row: Mapping[str, Any]) -> str:
    normalized = dict(row)
    if normalized.get("action_kind") == "WAIT":
        normalized["selected_next_node"] = None
    return precursor_target_id(normalized)


def merge_pair_payloads(
    payloads: Sequence[Mapping[str, Any]],
    expected_targets: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Merge resumable shards; identical overlap is safe, conflict is not."""

    expected = {precursor_target_id(row): dict(row) for row in expected_targets}
    _require(len(expected) == len(expected_targets), "duplicate expected target identity")
    merged: dict[str, dict[str, Any]] = {}
    duplicate_count = 0
    for payload_index, payload in enumerate(payloads):
        pairs = payload.get("pairs")
        _require(isinstance(pairs, list), f"pair payload {payload_index} omitted pairs")
        for pair in pairs:
            _require(isinstance(pair, Mapping), "pair payload contains a non-object")
            pair_id = _pair_id(pair)
            _require(pair_id in expected, f"unexpected native pair: {pair_id}")
            incumbent = merged.get(pair_id)
            plain = dict(_plain(pair))
            if incumbent is not None:
                _require(incumbent == plain, f"conflicting duplicate native pair: {pair_id}")
                duplicate_count += 1
            else:
                merged[pair_id] = plain
    ordered = [merged[target_id] for target_id in expected if target_id in merged]
    missing = [target_id for target_id in expected if target_id not in merged]
    return {
        "schema": MERGED_PAIR_SCHEMA,
        "pairs": ordered,
        "input_payload_count": len(payloads),
        "duplicate_pair_count": duplicate_count,
        "expected_target_count": len(expected),
        "observed_target_count": len(ordered),
        "missing_target_count": len(missing),
        "missing_target_ids": missing,
        "coverage_complete": not missing,
    }


def exact_pair_gate(
    payload: Mapping[str, Any], expected_targets: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Gate exact coverage, action change, safety, and H_system formal checks."""

    merged = merge_pair_payloads([payload], expected_targets)
    failures: list[dict[str, Any]] = []
    for pair in merged["pairs"]:
        reasons: list[str] = []
        if pair.get("pair_status") != "ACTION_CHANGED_HORIZON_COMPLETE":
            reasons.append(str(pair.get("pair_status") or "PAIR_STATUS_MISSING"))
        for field, reason in (
            ("same_state_start", "SAME_STATE_START_FAILED"),
            ("action_changed", "ACTION_NOT_CHANGED"),
            ("pair_complete", "HORIZON_INCOMPLETE"),
            ("live_safety_pass", "LIVE_SAFETY_FAILED"),
            ("hard_gate_pass", "HARD_GATE_FAILED"),
        ):
            if pair.get(field) is not True:
                reasons.append(reason)
        if pair.get("horizon") == "H_system":
            if pair.get("formal_hard_gate_evaluated") is not True:
                reasons.append("FORMAL_HARD_GATE_NOT_EVALUATED")
            if pair.get("formal_hard_gate_pass") is not True:
                reasons.append("FORMAL_HARD_GATE_FAILED")
            deltas = pair.get("affected_bag_deltas")
            if not isinstance(deltas, list) or not deltas:
                reasons.append("AFFECTED_BAG_COMPLETION_NOT_PRESERVED")
        if reasons:
            failures.append({"target_id": _pair_id(pair), "reasons": reasons})
    passed = merged["coverage_complete"] and not failures
    return {
        "schema": PAIR_GATE_SCHEMA,
        "status": "PASS_EXACT_PAIR_GATE" if passed else "NO_GO_EXACT_PAIR_GATE",
        "pass": passed,
        "coverage_complete": merged["coverage_complete"],
        "expected_target_count": merged["expected_target_count"],
        "observed_target_count": merged["observed_target_count"],
        "failure_count": len(failures),
        "failures": failures,
    }


def _action_key(row: Mapping[str, Any]) -> tuple[str, int | None]:
    action_kind = row.get("action_kind")
    _require(action_kind in {"NEXT_EDGE", "WAIT"}, "invalid precursor action_kind")
    selected = row.get("selected_next_node")
    if action_kind == "NEXT_EDGE":
        _require(type(selected) is int, "NEXT_EDGE action omitted selected_next_node")
        return "NEXT_EDGE", int(selected)
    _require(selected is None, "WAIT action fabricated selected_next_node")
    return "WAIT", None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _direct_completion_delta(pair: Mapping[str, Any]) -> float:
    explicit = pair.get("current_bag_cost_seconds")
    if explicit is not None:
        return _finite(explicit, "pair.current_bag_cost_seconds")
    runtime_bag_id = pair.get("runtime_bag_id")
    if type(runtime_bag_id) is not int:
        runtime_bag_id = _mapping(pair.get("resolved_execution_descriptor")).get(
            "runtime_bag_id"
        )
    deltas = pair.get("affected_bag_deltas")
    _require(isinstance(deltas, list) and deltas, "pair omitted affected_bag_deltas")
    matching = [
        row
        for row in deltas
        if isinstance(row, Mapping)
        and (type(runtime_bag_id) is not int or row.get("runtime_bag_id") == runtime_bag_id)
    ]
    _require(len(matching) == 1, "current bag completion delta is not unique")
    return _finite(matching[0].get("completion_delta_seconds"), "completion_delta_seconds")


def _deadline_headroom_audit(group: Mapping[str, Any]) -> dict[str, Any]:
    """Compute the pre-action allowance without consulting either outcome branch."""

    audit: dict[str, Any] = {
        "deadline_headroom_evidence_complete": False,
        "deadline_headroom_failure_reason": None,
        "baseline_priority_slack_seconds": None,
        "baseline_travel_time_seconds": None,
        "baseline_static_potential_seconds": None,
        "baseline_target_availability_wait_seconds": None,
        "deadline_headroom_seconds": None,
    }
    try:
        candidates = group.get("candidate_observations")
        _require(isinstance(candidates, list) and candidates, "candidate_observations missing")
        baseline_index = _integer(
            group.get("baseline_candidate_index"),
            "baseline_candidate_index",
            minimum=0,
        )
        _require(baseline_index < len(candidates), "baseline_candidate_index out of range")
        candidate = candidates[baseline_index]
        _require(isinstance(candidate, Mapping), "baseline candidate is not an object")
        event_time = _finite(group.get("event_time"), "group.event_time")
        priority_slack = _finite(
            candidate.get("priority_slack_seconds"),
            "baseline_candidate.priority_slack_seconds",
        )
        travel_time = _finite(
            candidate.get("travel_time"),
            "baseline_candidate.travel_time",
            minimum=0.0,
        )
        static_potential = _finite(
            candidate.get("static_potential"),
            "baseline_candidate.static_potential",
            minimum=0.0,
        )
        target_next_available = _finite(
            candidate.get("target_next_available"),
            "baseline_candidate.target_next_available",
        )
    except PrecursorRouteError as exc:
        audit["deadline_headroom_failure_reason"] = str(exc)
        return audit

    availability_wait = max(
        0.0,
        target_next_available - event_time - travel_time,
    )
    headroom = max(
        0.0,
        priority_slack - travel_time - static_potential - availability_wait,
    )
    audit.update(
        {
            "deadline_headroom_evidence_complete": True,
            "baseline_priority_slack_seconds": priority_slack,
            "baseline_travel_time_seconds": travel_time,
            "baseline_static_potential_seconds": static_potential,
            "baseline_target_availability_wait_seconds": availability_wait,
            "deadline_headroom_seconds": headroom,
        }
    )
    return audit


def _treatment_current_bag_audit(pair: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed unless the treatment's current bag is safely before deadline."""

    audit: dict[str, Any] = {
        "treatment_current_bag_evidence_complete": False,
        "treatment_current_bag_failure_reason": None,
        "treatment_current_bag_completed": False,
        "treatment_current_bag_failed": None,
        "treatment_current_bag_finish_time_seconds": None,
        "treatment_current_bag_deadline_seconds": None,
        "treatment_current_bag_before_deadline": False,
    }
    try:
        runtime_bag_id = pair.get("runtime_bag_id")
        if type(runtime_bag_id) is not int:
            runtime_bag_id = _mapping(pair.get("resolved_execution_descriptor")).get(
                "runtime_bag_id"
            )
        _require(type(runtime_bag_id) is int, "current runtime_bag_id missing")
        outcomes = _mapping(pair.get("treatment")).get("affected_bag_outcomes")
        _require(isinstance(outcomes, list) and outcomes, "treatment affected_bag_outcomes missing")
        matching = [
            row
            for row in outcomes
            if isinstance(row, Mapping) and row.get("runtime_bag_id") == runtime_bag_id
        ]
        _require(len(matching) == 1, "treatment current bag outcome is not unique")
        outcome = matching[0]
        _require(type(outcome.get("completed")) is bool, "treatment current bag completed missing")
        _require(type(outcome.get("failed")) is bool, "treatment current bag failed missing")
        finish_time = _finite(
            outcome.get("finish_time"),
            "treatment.current_bag.finish_time",
        )
        deadline = _finite(
            outcome.get("deadline"),
            "treatment.current_bag.deadline",
        )
    except PrecursorRouteError as exc:
        audit["treatment_current_bag_failure_reason"] = str(exc)
        return audit

    completed = bool(outcome["completed"])
    failed = bool(outcome["failed"])
    audit.update(
        {
            "treatment_current_bag_evidence_complete": True,
            "treatment_current_bag_completed": completed,
            "treatment_current_bag_failed": failed,
            "treatment_current_bag_finish_time_seconds": finish_time,
            "treatment_current_bag_deadline_seconds": deadline,
            "treatment_current_bag_before_deadline": finish_time <= deadline,
        }
    )
    return audit


def _raw_bag_delta(
    pair: Mapping[str, Any],
    *,
    explicit_names: Sequence[str],
    raw_field: str,
    scale: float = 1.0,
) -> float:
    for name in explicit_names:
        if pair.get(name) is not None:
            return _finite(pair[name], name)
    baseline = _mapping(_mapping(pair.get("baseline")).get("raw_bag_cohort_metrics"))
    treatment = _mapping(_mapping(pair.get("treatment")).get("raw_bag_cohort_metrics"))
    _require(raw_field in baseline and raw_field in treatment, f"H_system pair omitted {raw_field}")
    return scale * (
        _finite(treatment[raw_field], f"treatment.{raw_field}")
        - _finite(baseline[raw_field], f"baseline.{raw_field}")
    )


def _raw_bag_metrics(pair: Mapping[str, Any]) -> dict[str, Any]:
    baseline = _mapping(_mapping(pair.get("baseline")).get("raw_bag_cohort_metrics"))
    treatment = _mapping(_mapping(pair.get("treatment")).get("raw_bag_cohort_metrics"))
    comparison_eligible = (
        baseline.get("comparison_eligible") is True
        and treatment.get("comparison_eligible") is True
    )
    return {
        "raw_bag_mean_delta_seconds": _raw_bag_delta(
            pair,
            explicit_names=("raw_bag_mean_delta_seconds", "system_mean_delta_seconds"),
            raw_field="original_entry_mean_minutes",
            scale=60.0,
        ),
        "raw_bag_source_wait_mean_delta_seconds": _raw_bag_delta(
            pair,
            explicit_names=("raw_bag_source_wait_mean_delta_seconds",),
            raw_field="source_wait_mean_minutes",
            scale=60.0,
        ),
        "raw_bag_network_time_mean_delta_seconds": _raw_bag_delta(
            pair,
            explicit_names=("raw_bag_network_time_mean_delta_seconds",),
            raw_field="network_time_mean_minutes",
            scale=60.0,
        ),
        "raw_bag_p95_delta_seconds": _raw_bag_delta(
            pair,
            explicit_names=("raw_bag_p95_delta_seconds", "system_p95_delta_seconds"),
            raw_field="original_entry_p95_seconds",
        ),
        "raw_bag_p99_delta_seconds": _raw_bag_delta(
            pair,
            explicit_names=("raw_bag_p99_delta_seconds", "system_p99_delta_seconds"),
            raw_field="original_entry_p99_seconds",
        ),
        "raw_bag_max_delta_seconds": _raw_bag_delta(
            pair,
            explicit_names=("raw_bag_max_delta_seconds",),
            raw_field="original_entry_max_seconds",
        ),
        "deadline_miss_delta": int(
            _raw_bag_delta(
                pair,
                explicit_names=("deadline_miss_delta",),
                raw_field="deadline_miss_raw_bag_count",
            )
        ),
        "raw_bag_comparison_eligible": comparison_eligible,
    }


def _pair_certificate(pair: Mapping[str, Any]) -> dict[str, Any]:
    certificate = _mapping(pair.get("committed_action_certificate"))
    return {
        "valid": certificate.get("valid") is True,
        "changed_action_count": certificate.get("changed_action_count"),
        "pre_action_snapshots_match": certificate.get("pre_action_snapshots_match") is True,
        "post_commit_verified": certificate.get("post_commit_verified") is True,
        "committed_action_type": certificate.get("committed_action_type"),
    }


def _effect_tier(mean_delta: float | None) -> str:
    if mean_delta is None:
        return "direct_only"
    if mean_delta <= -STRONG_SYSTEM_GAIN_SECONDS:
        return "strong"
    if mean_delta <= -USABLE_SYSTEM_GAIN_SECONDS:
        return "usable"
    if mean_delta < -EFFECT_TOLERANCE_SECONDS:
        return "weak_diagnostic"
    if mean_delta <= EFFECT_TOLERANCE_SECONDS:
        return "neutral"
    return "harmful"


def _benefit_fairness_label(
    *,
    system_beneficial: bool,
    individual_fair: bool,
    strict_no_delay: bool,
    individual_fair_evidence_complete: bool,
    individual_cost_within_headroom: bool,
) -> str:
    if not system_beneficial:
        return "NOT_SYSTEM_BENEFICIAL"
    if individual_fair:
        return (
            "SYSTEM_BENEFICIAL_FAIR_STRICT_NO_DELAY"
            if strict_no_delay
            else "SYSTEM_BENEFICIAL_BUT_COSTLY_WITHIN_HEADROOM_FAIR"
        )
    if not individual_fair_evidence_complete:
        return "SYSTEM_BENEFICIAL_FAIRNESS_EVIDENCE_MISSING"
    if not individual_cost_within_headroom:
        return "SYSTEM_BENEFICIAL_BUT_COSTLY_EXCEEDS_HEADROOM"
    return "SYSTEM_BENEFICIAL_BUT_INDIVIDUAL_OUTCOME_UNSAFE"


H_SYSTEM_EFFECT_DISTRIBUTION_FIELDS = (
    "raw_bag_mean_delta_seconds",
    "raw_bag_source_wait_mean_delta_seconds",
    "raw_bag_network_time_mean_delta_seconds",
    "raw_bag_p95_delta_seconds",
    "raw_bag_p99_delta_seconds",
    "raw_bag_max_delta_seconds",
    "current_bag_cost_seconds",
    "deadline_headroom_seconds",
)


def _numeric_distribution(values: Sequence[float]) -> dict[str, Any]:
    """Describe one compact action metric without retaining raw branches."""

    if not values:
        return {
            "count": 0,
            "min": None,
            "mean": None,
            "median": None,
            "max": None,
            "nonzero_count": 0,
        }
    ordered = sorted(float(value) for value in values)
    return {
        "count": len(ordered),
        "min": ordered[0],
        "mean": fmean(ordered),
        "median": median(ordered),
        "max": ordered[-1],
        "nonzero_count": sum(value != 0.0 for value in ordered),
    }


def summarize_h_system_action_effects(
    action_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize the complete H_system panel and its fair promotions.

    This function consumes only compact action rows.  It describes effect and
    current-bag/headroom distributions; it neither changes labels nor adds a
    continuation gate.
    """

    planned = [row for row in action_rows if row.get("h_system_planned") is True]
    complete = [
        row
        for row in planned
        if row.get("evidence_horizon") == "H_system"
        and row.get("evidence_status") == "COMPLETE"
    ]
    promoted = [
        row
        for row in complete
        if _mapping(row.get("gates")).get("promotion_eligible") is True
    ]

    def summarize_scope(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        values: dict[str, list[float]] = {
            name: [] for name in H_SYSTEM_EFFECT_DISTRIBUTION_FIELDS
        }
        for row in rows:
            for name in H_SYSTEM_EFFECT_DISTRIBUTION_FIELDS:
                value = row.get(name)
                if value is not None:
                    values[name].append(_finite(value, f"action.{name}"))
        blocks = sorted({int(row["release_block"]) for row in rows})
        return {
            "action_count": len(rows),
            "group_count": len(
                {
                    str(row["group_id"])
                    for row in rows
                    if isinstance(row.get("group_id"), str) and row["group_id"]
                }
            ),
            "release_block_action_counts": {
                str(block): sum(row.get("release_block") == block for row in rows)
                for block in blocks
            },
            "metrics": {
                name: {
                    **_numeric_distribution(metric_values),
                    "missing_count": len(rows) - len(metric_values),
                }
                for name, metric_values in values.items()
            },
        }

    return {
        "delta_direction": "treatment_minus_baseline",
        "raw_bag_mean_denominator": "complete_raw_bag",
        "planned_h_system_action_count": len(planned),
        "complete_h_system_action_count": len(complete),
        "complete_h_system_group_count": len(
            {
                str(row["group_id"])
                for row in complete
                if isinstance(row.get("group_id"), str) and row["group_id"]
            }
        ),
        "panel": summarize_scope(complete),
        "fair_promotions": summarize_scope(promoted),
    }


def _compact_action_effect(
    group: Mapping[str, Any],
    target: Mapping[str, Any],
    pair: Mapping[str, Any] | None,
    *,
    h_system_planned: bool,
) -> dict[str, Any]:
    action_kind, selected = _action_key(target)
    evidence_horizon = pair.get("horizon") if pair is not None else None
    headroom_audit = _deadline_headroom_audit(group)
    base = {
        "schema": COMPACT_ACTION_SCHEMA,
        "group_id": precursor_group_id(target),
        "target_id": precursor_target_id(target),
        "event_ordinal": int(target["event_ordinal"]),
        "release_block": int(group["release_block"]),
        "selection_stratum": str(group["selection_stratum"]),
        "current_node": int(group["current_node"]),
        "action_kind": action_kind,
        "selected_next_node": selected,
        "evidence_horizon": evidence_horizon,
        "h_system_planned": h_system_planned,
        "h_bag_subsumed_by_h_system": evidence_horizon == "H_system",
        "selected_by_group": False,
        **headroom_audit,
    }
    if pair is None:
        return {
            **base,
            "evidence_status": "PAIR_MISSING",
            "direct_completion_delta_seconds": None,
            "current_bag_cost_seconds": None,
            "raw_bag_mean_delta_seconds": None,
            "raw_bag_source_wait_mean_delta_seconds": None,
            "raw_bag_network_time_mean_delta_seconds": None,
            "raw_bag_p95_delta_seconds": None,
            "raw_bag_p99_delta_seconds": None,
            "raw_bag_max_delta_seconds": None,
            "deadline_miss_delta": None,
            **_treatment_current_bag_audit({}),
            "individual_fair_evidence_complete": False,
            "individual_cost_within_headroom": False,
            "individual_fair": False,
            "strict_no_delay": False,
            "system_beneficial": False,
            "system_beneficial_but_costly": False,
            "benefit_fairness_label": "PAIR_MISSING",
            "certificate": {},
            "gates": {
                "pair_complete": False,
                "action_change": False,
                "safety": False,
                "formal_hard_gate": False if h_system_planned else None,
                "raw_bag_comparison": False if h_system_planned else None,
                "tail": False if h_system_planned else None,
                "max_diagnostic": False if h_system_planned else None,
                "direct_cost": False,
                "strict_no_delay": False,
                "deadline": False if h_system_planned else None,
                "usable_system_gain": False if h_system_planned else None,
                "system_beneficial": False,
                "individual_fair": False,
                "promotion_eligible": False,
            },
            "effect_tier": "missing",
        }

    certificate = _pair_certificate(pair)
    pair_complete = (
        pair.get("pair_status") == "ACTION_CHANGED_HORIZON_COMPLETE"
        and pair.get("pair_complete") is True
        and pair.get("horizon_complete", True) is True
    )
    action_change = (
        pair.get("same_state_start") is True
        and pair.get("action_changed") is True
        and certificate["valid"]
        and certificate["changed_action_count"] == 1
        and certificate["pre_action_snapshots_match"]
        and certificate["post_commit_verified"]
    )
    safety = pair.get("live_safety_pass") is True and pair.get("hard_gate_pass") is True
    if not pair_complete:
        return {
            **base,
            "evidence_status": "INCOMPLETE",
            "direct_completion_delta_seconds": None,
            "current_bag_cost_seconds": None,
            "raw_bag_mean_delta_seconds": None,
            "raw_bag_source_wait_mean_delta_seconds": None,
            "raw_bag_network_time_mean_delta_seconds": None,
            "raw_bag_p95_delta_seconds": None,
            "raw_bag_p99_delta_seconds": None,
            "raw_bag_max_delta_seconds": None,
            "deadline_miss_delta": None,
            **_treatment_current_bag_audit(pair),
            "individual_fair_evidence_complete": False,
            "individual_cost_within_headroom": False,
            "individual_fair": False,
            "strict_no_delay": False,
            "system_beneficial": False,
            "system_beneficial_but_costly": False,
            "benefit_fairness_label": "PAIR_INCOMPLETE",
            "certificate": certificate,
            "gates": {
                "pair_complete": False,
                "action_change": action_change,
                "safety": safety,
                "formal_hard_gate": False if h_system_planned else None,
                "raw_bag_comparison": False if h_system_planned else None,
                "tail": False if h_system_planned else None,
                "max_diagnostic": False if h_system_planned else None,
                "direct_cost": False,
                "strict_no_delay": False,
                "deadline": False if h_system_planned else None,
                "usable_system_gain": False if h_system_planned else None,
                "system_beneficial": False,
                "individual_fair": False,
                "promotion_eligible": False,
            },
            "effect_tier": "missing",
        }

    direct = _direct_completion_delta(pair)
    strict_no_delay = direct <= EFFECT_TOLERANCE_SECONDS
    treatment_audit = _treatment_current_bag_audit(pair)
    raw_metrics: dict[str, Any] = {
        "raw_bag_mean_delta_seconds": None,
        "raw_bag_source_wait_mean_delta_seconds": None,
        "raw_bag_network_time_mean_delta_seconds": None,
        "raw_bag_p95_delta_seconds": None,
        "raw_bag_p99_delta_seconds": None,
        "raw_bag_max_delta_seconds": None,
        "deadline_miss_delta": None,
        "raw_bag_comparison_eligible": None,
    }
    formal_gate: bool | None = None
    tail_gate: bool | None = None
    max_diagnostic: bool | None = None
    deadline_gate: bool | None = None
    mean_gate: bool | None = None
    if evidence_horizon == "H_system":
        raw_metrics = _raw_bag_metrics(pair)
        formal_gate = (
            pair.get("formal_hard_gate_evaluated") is True
            and pair.get("formal_hard_gate_pass") is True
        )
        tail_gate = all(
            raw_metrics[name] <= EFFECT_TOLERANCE_SECONDS
            for name in (
                "raw_bag_p95_delta_seconds",
                "raw_bag_p99_delta_seconds",
            )
        )
        max_diagnostic = (
            raw_metrics["raw_bag_max_delta_seconds"] <= EFFECT_TOLERANCE_SECONDS
        )
        deadline_gate = raw_metrics["deadline_miss_delta"] <= 0
        mean_gate = raw_metrics["raw_bag_mean_delta_seconds"] <= -USABLE_SYSTEM_GAIN_SECONDS
    system_beneficial = all(
        value is True
        for value in (
            pair_complete,
            action_change,
            safety,
            formal_gate,
            raw_metrics["raw_bag_comparison_eligible"],
            tail_gate,
            deadline_gate,
            mean_gate,
        )
    )
    individual_fair_evidence_complete = all(
        value is True
        for value in (
            headroom_audit["deadline_headroom_evidence_complete"],
            treatment_audit["treatment_current_bag_evidence_complete"],
            deadline_gate is not None,
        )
    )
    headroom = headroom_audit["deadline_headroom_seconds"]
    individual_cost_within_headroom = (
        individual_fair_evidence_complete
        and isinstance(headroom, (int, float))
        and direct <= float(headroom)
    )
    individual_fair = all(
        value is True
        for value in (
            individual_fair_evidence_complete,
            individual_cost_within_headroom,
            treatment_audit["treatment_current_bag_completed"],
            treatment_audit["treatment_current_bag_failed"] is False,
            treatment_audit["treatment_current_bag_before_deadline"],
            deadline_gate,
        )
    )
    promotion_eligible = system_beneficial and individual_fair
    benefit_fairness_label = _benefit_fairness_label(
        system_beneficial=system_beneficial,
        individual_fair=individual_fair,
        strict_no_delay=strict_no_delay,
        individual_fair_evidence_complete=individual_fair_evidence_complete,
        individual_cost_within_headroom=individual_cost_within_headroom,
    )
    return {
        **base,
        "evidence_status": "COMPLETE" if pair_complete else "INCOMPLETE",
        "direct_completion_delta_seconds": direct,
        "current_bag_cost_seconds": direct,
        **raw_metrics,
        **treatment_audit,
        "individual_fair_evidence_complete": individual_fair_evidence_complete,
        "individual_cost_within_headroom": individual_cost_within_headroom,
        "individual_fair": individual_fair,
        "strict_no_delay": strict_no_delay,
        "system_beneficial": system_beneficial,
        "system_beneficial_but_costly": system_beneficial and not strict_no_delay,
        "benefit_fairness_label": benefit_fairness_label,
        "certificate": certificate,
        "gates": {
            "pair_complete": pair_complete,
            "action_change": action_change,
            "safety": safety,
            "formal_hard_gate": formal_gate,
            "raw_bag_comparison": raw_metrics["raw_bag_comparison_eligible"],
            "tail": tail_gate,
            "max_diagnostic": max_diagnostic,
            "direct_cost": strict_no_delay,
            "strict_no_delay": strict_no_delay,
            "deadline": deadline_gate,
            "usable_system_gain": mean_gate,
            "system_beneficial": system_beneficial,
            "individual_fair": individual_fair,
            "promotion_eligible": promotion_eligible,
        },
        "effect_tier": _effect_tier(raw_metrics["raw_bag_mean_delta_seconds"]),
    }


def compact_precursor_pilot(
    merged_pairs: Mapping[str, Any],
    groups: Sequence[Mapping[str, Any]],
    targets: Sequence[Mapping[str, Any]],
    *,
    required_h_bag_groups: int = PILOT_REQUIRED_H_BAG_GROUPS,
    required_h_system_groups: int = PILOT_REQUIRED_H_SYSTEM_GROUPS,
    required_fair_promotion_groups: int = PILOT_REQUIRED_FAIR_PROMOTION_GROUPS,
    required_block8_promotion_groups: int = PILOT_REQUIRED_BLOCK8_PROMOTION_GROUPS,
    required_promotion_strata: int = PILOT_REQUIRED_PROMOTION_STRATA,
    required_action_change_rate: float = PILOT_REQUIRED_ACTION_CHANGE_RATE,
) -> dict[str, Any]:
    """Reduce exact Route branches to one auditable row per treatment action."""

    pairs = merged_pairs.get("pairs")
    _require(isinstance(pairs, list), "merged pair payload omitted pairs")
    pair_by_id: dict[str, Mapping[str, Any]] = {}
    for pair in pairs:
        _require(isinstance(pair, Mapping), "merged pair payload contains a non-object")
        pair_id = _pair_id(pair)
        _require(pair_id not in pair_by_id, f"duplicate compact pair: {pair_id}")
        pair_by_id[pair_id] = pair

    target_by_id = {precursor_target_id(row): row for row in targets}
    _require(len(target_by_id) == len(targets), "duplicate compact target identity")
    unknown_pairs = sorted(set(pair_by_id) - set(target_by_id))
    _require(not unknown_pairs, f"compact payload has unknown pairs: {unknown_pairs[:3]}")
    group_by_id = {precursor_group_id(row): row for row in groups}
    _require(len(group_by_id) == len(groups), "duplicate compact group identity")

    planned: dict[str, dict[str, dict[tuple[str, int | None], Mapping[str, Any]]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for target in targets:
        group_id = precursor_group_id(target)
        _require(group_id in group_by_id, f"target has no compact group: {group_id}")
        key = _action_key(target)
        horizon = str(target["horizon"])
        _require(key not in planned[group_id][horizon], "duplicate planned group action")
        planned[group_id][horizon][key] = target

    action_rows: list[dict[str, Any]] = []
    group_rows: list[dict[str, Any]] = []
    for group_id, group in group_by_id.items():
        h_bag_targets = planned[group_id].get("H_bag", {})
        h_system_targets = planned[group_id].get("H_system", {})
        _require(h_bag_targets, f"group omitted H_bag actions: {group_id}")
        _require(
            not h_system_targets or set(h_system_targets) == set(h_bag_targets),
            f"H_system action set drifted: {group_id}",
        )
        rows: list[dict[str, Any]] = []
        system_pair_complete: list[bool] = []
        for key, h_bag_target in h_bag_targets.items():
            system_target = h_system_targets.get(key)
            system_pair = (
                pair_by_id.get(precursor_target_id(system_target))
                if system_target is not None
                else None
            )
            h_bag_pair = pair_by_id.get(precursor_target_id(h_bag_target))
            evidence_target = system_target if system_pair is not None else h_bag_target
            evidence_pair = system_pair if system_pair is not None else h_bag_pair
            row = _compact_action_effect(
                group,
                evidence_target,
                evidence_pair,
                h_system_planned=system_target is not None,
            )
            rows.append(row)
            if system_target is not None:
                system_pair_complete.append(
                    system_pair is not None
                    and system_pair.get("pair_status") == "ACTION_CHANGED_HORIZON_COMPLETE"
                    and system_pair.get("pair_complete") is True
                    and system_pair.get("horizon_complete", True) is True
                )

        eligible = [row for row in rows if row["gates"]["promotion_eligible"] is True]
        system_beneficial_rows = [row for row in rows if row["system_beneficial"] is True]
        individually_fair_rows = [row for row in rows if row["individual_fair"] is True]
        beneficial_costly_rows = [
            row for row in rows if row["system_beneficial_but_costly"] is True
        ]
        selected = min(
            eligible,
            key=lambda row: (
                float(row["raw_bag_mean_delta_seconds"]),
                float(row["direct_completion_delta_seconds"]),
                str(row["action_kind"]),
                -1 if row["selected_next_node"] is None else int(row["selected_next_node"]),
            ),
            default=None,
        )
        if selected is not None:
            selected["selected_by_group"] = True
        h_bag_complete = len(rows) == len(h_bag_targets) and all(
            row["gates"]["pair_complete"] is True for row in rows
        )
        action_change_complete = h_bag_complete and all(
            row["gates"]["action_change"] is True for row in rows
        )
        h_system_planned = bool(h_system_targets)
        h_system_complete = h_system_planned and len(system_pair_complete) == len(
            h_system_targets
        ) and all(system_pair_complete)
        group_row = {
            "schema": COMPACT_GROUP_SCHEMA,
            "group_id": group_id,
            "event_ordinal": int(group["event_ordinal"]),
            "release_block": int(group["release_block"]),
            "selection_stratum": str(group["selection_stratum"]),
            "planned_action_count": len(h_bag_targets),
            "h_bag_complete": h_bag_complete,
            "h_system_planned": h_system_planned,
            "h_system_complete": h_system_complete,
            "action_change_complete": action_change_complete,
            "system_beneficial_action_count": len(system_beneficial_rows),
            "system_beneficial": bool(system_beneficial_rows),
            "individual_fair_action_count": len(individually_fair_rows),
            "system_beneficial_but_costly_action_count": len(beneficial_costly_rows),
            "promotion_eligible_action_count": len(eligible),
            "promotion_eligible": selected is not None,
            "selected_action_kind": selected["action_kind"] if selected else None,
            "selected_next_node": selected["selected_next_node"] if selected else None,
            "selected_effect_tier": selected["effect_tier"] if selected else None,
            "selected_raw_bag_mean_delta_seconds": (
                selected["raw_bag_mean_delta_seconds"] if selected else None
            ),
        }
        action_rows.extend(rows)
        group_rows.append(group_row)

    h_bag_complete_count = sum(row["h_bag_complete"] for row in group_rows)
    h_system_planned_count = sum(row["h_system_planned"] for row in group_rows)
    h_system_complete_count = sum(row["h_system_complete"] for row in group_rows)
    changed_count = sum(row["action_change_complete"] for row in group_rows)
    attempted_count = len(group_rows)
    change_rate = changed_count / attempted_count if attempted_count else 0.0
    promoted = [row for row in group_rows if row["promotion_eligible"]]
    system_beneficial_groups = [row for row in group_rows if row["system_beneficial"]]
    system_beneficial_costly_groups = [
        row
        for row in group_rows
        if row["system_beneficial_but_costly_action_count"] > 0
    ]
    block8_promoted = sum(row["release_block"] == 8 for row in promoted)
    promoted_strata = {row["selection_stratum"] for row in promoted}
    gates = {
        "h_bag_group_coverage": h_bag_complete_count >= required_h_bag_groups,
        "h_system_group_coverage": h_system_complete_count >= required_h_system_groups,
        "action_changing_rate": change_rate >= required_action_change_rate,
        "fair_promotion_group_count": len(promoted) >= required_fair_promotion_groups,
        "block8_fair_promotion_group_count": (
            block8_promoted >= required_block8_promotion_groups
        ),
        "fair_promotion_strata_coverage": len(promoted_strata) >= required_promotion_strata,
    }
    pilot_support_pass = all(gates.values())
    h_system_effect_distribution = summarize_h_system_action_effects(action_rows)
    summary = {
        "schema": COMPACT_SUMMARY_SCHEMA,
        "status": (
            "PASS_PRECURSOR_PILOT_SUPPORT"
            if pilot_support_pass
            else "NO_GO_PRECURSOR_PILOT_SUPPORT"
        ),
        "attempted_group_count": attempted_count,
        "action_row_count": len(action_rows),
        "h_bag_complete_group_count": h_bag_complete_count,
        "h_system_planned_group_count": h_system_planned_count,
        "h_system_complete_group_count": h_system_complete_count,
        "action_changed_group_count": changed_count,
        "action_changed_group_rate": change_rate,
        "fair_promotion_group_count": len(promoted),
        "system_beneficial_group_count": len(system_beneficial_groups),
        "system_beneficial_action_count": sum(
            row["system_beneficial"] is True for row in action_rows
        ),
        "system_beneficial_but_costly_group_count": len(
            system_beneficial_costly_groups
        ),
        "system_beneficial_but_costly_action_count": sum(
            row["system_beneficial_but_costly"] is True for row in action_rows
        ),
        "strict_no_delay_action_count": sum(
            row["strict_no_delay"] is True for row in action_rows
        ),
        "individual_fair_action_count": sum(
            row["individual_fair"] is True for row in action_rows
        ),
        "block8_fair_promotion_group_count": block8_promoted,
        "fair_promotion_strata_count": len(promoted_strata),
        "effect_tier_counts": {
            tier: sum(row["effect_tier"] == tier for row in action_rows)
            for tier in ("strong", "usable", "weak_diagnostic", "neutral", "harmful", "direct_only", "missing")
        },
        "h_system_effect_distribution": h_system_effect_distribution,
        "thresholds": {
            "required_h_bag_groups": required_h_bag_groups,
            "required_h_system_groups": required_h_system_groups,
            "required_action_change_rate": required_action_change_rate,
            "required_fair_promotion_groups": required_fair_promotion_groups,
            "required_block8_fair_promotion_groups": required_block8_promotion_groups,
            "required_fair_promotion_strata": required_promotion_strata,
            "usable_system_gain_seconds": USABLE_SYSTEM_GAIN_SECONDS,
            "strong_system_gain_seconds": STRONG_SYSTEM_GAIN_SECONDS,
            "tail_tolerance_seconds": EFFECT_TOLERANCE_SECONDS,
            "strict_no_delay_tolerance_seconds": EFFECT_TOLERANCE_SECONDS,
        },
        "gates": gates,
        "pilot_support_pass": pilot_support_pass,
        "h_system_subsumes_same_action_h_bag": True,
    }
    return {
        "schema": COMPACT_RESULT_SCHEMA,
        "summary": summary,
        "actions": action_rows,
        "groups": group_rows,
    }


def build_precursor_plan(
    request_rows: Iterable[Mapping[str, Any]],
    anchors: Iterable[Mapping[str, Any]],
    census_path: Path,
    *,
    block_group_targets: Mapping[int, int] = PILOT_BLOCK_GROUPS,
    block_h_system_targets: Mapping[int, int] = DEFAULT_H_SYSTEM_BLOCK_GROUPS,
) -> dict[str, Any]:
    links, lifecycle_audit = link_lifecycle_anchors(anchors, request_rows)
    candidates, census_audit = stream_lifecycle_precursors(links, census_path)
    groups, selection = select_precursor_groups(
        candidates,
        block_group_targets=block_group_targets,
        block_h_system_targets=block_h_system_targets,
    )
    targets = build_precursor_targets(groups)
    h_system_groups = sum("H_system" in row["assigned_horizons"] for row in groups)
    return {
        "schema": PLAN_SCHEMA,
        "research_profile": RESEARCH_PROFILE,
        "execution_contract": "EXISTING_G22_EXACT_PAIR_API;_NO_NEW_PLANNER_OR_SUPERVISOR",
        "selection": selection,
        "lifecycle_audit": lifecycle_audit,
        "census_audit": census_audit,
        "groups": groups,
        "targets": targets,
        "counts": {
            "group_count": len(groups),
            "h_bag_group_count": len(groups),
            "h_system_group_count": h_system_groups,
            "target_count": len(targets),
        },
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_plain(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(_plain(row), sort_keys=True) + "\n")


def write_compact_action_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    """Write only decision-relevant scalar evidence; raw branches stay runtime-only."""

    columns = (
        "group_id",
        "event_ordinal",
        "release_block",
        "selection_stratum",
        "current_node",
        "action_kind",
        "selected_next_node",
        "evidence_horizon",
        "h_system_planned",
        "h_bag_subsumed_by_h_system",
        "evidence_status",
        "direct_completion_delta_seconds",
        "current_bag_cost_seconds",
        "deadline_headroom_evidence_complete",
        "deadline_headroom_failure_reason",
        "baseline_priority_slack_seconds",
        "baseline_travel_time_seconds",
        "baseline_static_potential_seconds",
        "baseline_target_availability_wait_seconds",
        "deadline_headroom_seconds",
        "treatment_current_bag_evidence_complete",
        "treatment_current_bag_failure_reason",
        "treatment_current_bag_completed",
        "treatment_current_bag_failed",
        "treatment_current_bag_finish_time_seconds",
        "treatment_current_bag_deadline_seconds",
        "treatment_current_bag_before_deadline",
        "individual_fair_evidence_complete",
        "individual_cost_within_headroom",
        "individual_fair",
        "strict_no_delay",
        "system_beneficial",
        "system_beneficial_but_costly",
        "benefit_fairness_label",
        "raw_bag_mean_delta_seconds",
        "raw_bag_source_wait_mean_delta_seconds",
        "raw_bag_network_time_mean_delta_seconds",
        "raw_bag_p95_delta_seconds",
        "raw_bag_p99_delta_seconds",
        "raw_bag_max_delta_seconds",
        "deadline_miss_delta",
        "effect_tier",
        "selected_by_group",
        "certificate_valid",
        "certificate_changed_action_count",
        "gate_pair_complete",
        "gate_action_change",
        "gate_safety",
        "gate_formal_hard_gate",
        "gate_raw_bag_comparison",
        "gate_tail",
        "gate_max_diagnostic",
        "gate_direct_cost",
        "gate_strict_no_delay",
        "gate_deadline",
        "gate_usable_system_gain",
        "gate_system_beneficial",
        "gate_individual_fair",
        "gate_promotion_eligible",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for raw in rows:
            row = dict(raw)
            certificate = _mapping(row.get("certificate"))
            gates = _mapping(row.get("gates"))
            flat = {name: row.get(name) for name in columns}
            flat.update(
                {
                    "certificate_valid": certificate.get("valid"),
                    "certificate_changed_action_count": certificate.get(
                        "changed_action_count"
                    ),
                    **{f"gate_{name}": value for name, value in gates.items()},
                }
            )
            writer.writerow(flat)


def render_compact_report(summary: Mapping[str, Any]) -> str:
    gates = _mapping(summary.get("gates"))
    thresholds = _mapping(summary.get("thresholds"))
    effects = _mapping(summary.get("h_system_effect_distribution"))
    panel = _mapping(effects.get("panel"))
    promotions = _mapping(effects.get("fair_promotions"))
    panel_metrics = _mapping(panel.get("metrics"))
    promotion_metrics = _mapping(promotions.get("metrics"))
    gate_lines = [
        f"- `{name}`: {'PASS' if value is True else 'NO-GO'}"
        for name, value in gates.items()
    ]

    def metric_value(
        metrics: Mapping[str, Any], field: str, statistic: str
    ) -> str:
        value = _mapping(metrics.get(field)).get(statistic)
        return "N/A" if value is None else f"{float(value):+.9f}"

    effect_labels = {
        "raw_bag_mean_delta_seconds": "raw-bag mean TTH delta",
        "raw_bag_source_wait_mean_delta_seconds": "source-wait mean delta",
        "raw_bag_network_time_mean_delta_seconds": "network-time mean delta",
        "raw_bag_p95_delta_seconds": "raw-bag p95 delta",
        "raw_bag_p99_delta_seconds": "raw-bag p99 delta",
        "raw_bag_max_delta_seconds": "raw-bag max delta",
        "current_bag_cost_seconds": "current-bag completion cost",
        "deadline_headroom_seconds": "pre-action deadline headroom",
    }
    effect_lines = [
        "| Metric | Panel min | mean | median | max | Promotion min | mean | median | max |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for field, label in effect_labels.items():
        effect_lines.append(
            "| {label} | {pmin} | {pmean} | {pmedian} | {pmax} | "
            "{rmin} | {rmean} | {rmedian} | {rmax} |".format(
                label=label,
                pmin=metric_value(panel_metrics, field, "min"),
                pmean=metric_value(panel_metrics, field, "mean"),
                pmedian=metric_value(panel_metrics, field, "median"),
                pmax=metric_value(panel_metrics, field, "max"),
                rmin=metric_value(promotion_metrics, field, "min"),
                rmean=metric_value(promotion_metrics, field, "mean"),
                rmedian=metric_value(promotion_metrics, field, "median"),
                rmax=metric_value(promotion_metrics, field, "max"),
            )
        )
    return "\n".join(
        [
            "# G4IRSF23 precursor Route Pilot",
            "",
            f"Status: **{summary['status']}**",
            "",
            "The Pilot reuses the existing G22 S4/J2/E2 runtime and exact G21 Route action seam.",
            "For system-panel actions, one complete H_system branch also supplies the same",
            "action's direct H_bag evidence; no duplicate replay or new planner is introduced.",
            "The published raw pairs used a runtime-only ordinary-baseline reuse shortcut",
            "whose checkpoint-continuation outcomes were equivalence-audited. The shipped",
            "runtime omits that unused shortcut and keeps ordinary G22 per-target semantics.",
            "",
            f"- attempted groups: {summary['attempted_group_count']}",
            f"- complete H_bag groups: {summary['h_bag_complete_group_count']}",
            f"- complete H_system groups: {summary['h_system_complete_group_count']}",
            f"- action-changing groups: {summary['action_changed_group_count']} "
            f"({summary['action_changed_group_rate']:.3f})",
            f"- fair promotion groups: {summary['fair_promotion_group_count']}",
            f"- system-beneficial groups: {summary['system_beneficial_group_count']}",
            f"- system-beneficial-but-costly groups: "
            f"{summary['system_beneficial_but_costly_group_count']}",
            f"- individually fair actions: {summary['individual_fair_action_count']}",
            f"- strict-no-delay actions (diagnostic): {summary['strict_no_delay_action_count']}",
            f"- block-8 fair promotion groups: {summary['block8_fair_promotion_group_count']}",
            f"- fair promotion strata: {summary['fair_promotion_strata_count']}",
            "",
            "## H_system effect distribution",
            "",
            f"- planned H_system actions: {effects.get('planned_h_system_action_count')}",
            f"- complete H_system actions/groups: "
            f"{effects.get('complete_h_system_action_count')} / "
            f"{effects.get('complete_h_system_group_count')}",
            f"- fair promotion actions/groups: {promotions.get('action_count')} / "
            f"{promotions.get('group_count')}",
            "- deltas are treatment minus baseline; mean TTH/source/network rows are seconds per complete raw bag",
            "- current-bag cost and deadline headroom are seconds for the treated bag",
            "",
            *effect_lines,
            "",
            "## Gates",
            "",
            *gate_lines,
            "",
            "## Fixed effect boundary",
            "",
            f"- usable raw-bag mean gain: at least {thresholds['usable_system_gain_seconds']} s",
            f"- strong raw-bag mean gain: at least {thresholds['strong_system_gain_seconds']} s",
            f"- p95/p99 tolerance: +{thresholds['tail_tolerance_seconds']} s",
            f"- max is a separate diagnostic at +{thresholds['tail_tolerance_seconds']} s; it is not a promotion hard gate",
            f"- strict no-delay (direct <= +{thresholds['strict_no_delay_tolerance_seconds']} s) is diagnostic, not the sole fairness gate",
            "- individual fairness uses the pre-action baseline-candidate deadline headroom and the treatment current-bag outcome",
            "- deadline misses may not increase",
            "- only an eligible action can be selected; otherwise the group remains S4",
            "",
        ]
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route-census", type=Path, required=True)
    parser.add_argument("--anchors", type=Path, required=True)
    parser.add_argument(
        "--requests",
        type=Path,
        help="Optional exact 2x request JSON/JSONL; defaults to the frozen 2x artifact.",
    )
    parser.add_argument("--mode", choices=("pilot", "formal"), default="pilot")
    parser.add_argument("--groups-output", type=Path, required=True)
    parser.add_argument("--targets-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument(
        "--binary",
        type=Path,
        help="Native extension used only with --run-pairs.",
    )
    parser.add_argument("--run-pairs", action="store_true")
    parser.add_argument("--pair-shard-manifest", type=Path)
    parser.add_argument("--pair-shard-id")
    parser.add_argument("--pairs-output", type=Path)
    parser.add_argument(
        "--pair-result",
        type=Path,
        action="append",
        default=[],
        help="Merge one or more completed shard payloads without simulation.",
    )
    parser.add_argument("--merged-pairs-output", type=Path)
    parser.add_argument("--gate-output", type=Path)
    parser.add_argument(
        "--compact-actions-output",
        type=Path,
        help="Optional compact per-action CSV produced while merging exact pairs.",
    )
    parser.add_argument(
        "--compact-result-output",
        type=Path,
        help="Optional compact JSON containing action rows, group choices, and gates.",
    )
    parser.add_argument(
        "--compact-report-output",
        type=Path,
        help="Optional concise Markdown Pilot report.",
    )
    parser.add_argument("--shard-manifest-output", type=Path)
    parser.add_argument(
        "--allow-shortfall",
        action="store_true",
        help="Write a diagnostic partial plan but retain its explicit NO_GO status.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        exact_gate_pass: bool | None = None
        request_rows = (
            _read_rows(arguments.requests)
            if arguments.requests is not None
            else load_frozen_2x_requests(ROOT)
        )
        anchors = _read_rows(arguments.anchors)
        quotas = PILOT_BLOCK_GROUPS if arguments.mode == "pilot" else FORMAL_BLOCK_GROUPS
        plan = build_precursor_plan(
            request_rows,
            anchors,
            arguments.route_census,
            block_group_targets=quotas,
            block_h_system_targets=DEFAULT_H_SYSTEM_BLOCK_GROUPS,
        )
        _write_jsonl(arguments.groups_output, plan["groups"])
        _write_jsonl(arguments.targets_output, plan["targets"])
        summary = {
            key: value
            for key, value in plan.items()
            if key not in {"groups", "targets"}
        }
        summary["mode"] = arguments.mode
        summary["route_census_reused_in_place"] = True
        summary["raw_census_copied"] = False
        summary["formal_h_system_reuse"] = (
            "FIRST_256_GROUP_TARGET_IDENTITIES_MATCH_PILOT;_REUSE_COMPLETED_EXACT_PAIRS"
            if arguments.mode == "formal"
            else None
        )
        manifest = build_pair_shard_manifest(plan["targets"])
        summary["pair_shards"] = {
            key: value for key, value in manifest.items() if key != "shards"
        }
        if arguments.shard_manifest_output is not None:
            _write_json(arguments.shard_manifest_output, manifest)

        has_shard_manifest = arguments.pair_shard_manifest is not None
        has_shard_id = arguments.pair_shard_id is not None
        _require(
            has_shard_manifest == has_shard_id,
            "--pair-shard-manifest and --pair-shard-id must appear together",
        )
        _require(
            not arguments.run_pairs or has_shard_manifest,
            "--run-pairs requires a manifest shard",
        )
        _require(
            not arguments.run_pairs or arguments.binary is not None,
            "--run-pairs requires --binary",
        )
        _require(
            not arguments.run_pairs or arguments.pairs_output is not None,
            "--run-pairs requires --pairs-output",
        )
        if arguments.run_pairs:
            loaded_manifest = json.loads(
                arguments.pair_shard_manifest.read_text(encoding="utf-8")
            )
            _require(isinstance(loaded_manifest, Mapping), "pair shard manifest must be an object")
            selected_targets = select_manifest_shard(
                plan["targets"], loaded_manifest, arguments.pair_shard_id
            )
            backend = g22.load_native_backend(arguments.binary)
            native_arguments, _, input_descriptor = g22.build_2x_native_arguments(ROOT)
            pair_payload = g22.run_native_action_pairs(
                backend, native_arguments, selected_targets
            )
            pair_payload["g4irsf23_precursor_shard_id"] = arguments.pair_shard_id
            _write_json(arguments.pairs_output, pair_payload)
            summary["executed_pair_shard"] = {
                "shard_id": arguments.pair_shard_id,
                "target_count": len(selected_targets),
                "input_descriptor": input_descriptor,
            }

        if arguments.pair_result:
            payloads: list[Mapping[str, Any]] = []
            for path in arguments.pair_result:
                value = json.loads(path.read_text(encoding="utf-8"))
                _require(isinstance(value, Mapping), f"{path} is not a pair payload")
                payloads.append(value)
            expected_execution = execution_targets(plan["targets"], manifest)
            merged = merge_pair_payloads(payloads, expected_execution)
            gate = exact_pair_gate(merged, expected_execution)
            exact_gate_pass = gate["pass"] is True
            _require(arguments.merged_pairs_output is not None,
                     "--pair-result requires --merged-pairs-output")
            _require(arguments.gate_output is not None,
                     "--pair-result requires --gate-output")
            _write_json(arguments.merged_pairs_output, merged)
            _write_json(arguments.gate_output, gate)
            compact = compact_precursor_pilot(
                merged, plan["groups"], plan["targets"]
            )
            if arguments.compact_actions_output is not None:
                write_compact_action_csv(
                    arguments.compact_actions_output, compact["actions"]
                )
            if arguments.compact_result_output is not None:
                _write_json(arguments.compact_result_output, compact)
            if arguments.compact_report_output is not None:
                arguments.compact_report_output.parent.mkdir(parents=True, exist_ok=True)
                arguments.compact_report_output.write_text(
                    render_compact_report(compact["summary"]), encoding="utf-8"
                )
            summary["exact_pair_gate"] = {
                key: value for key, value in gate.items() if key != "failures"
            }
            summary["precursor_pilot"] = compact["summary"]
        _write_json(arguments.summary_output, summary)
        status = str(plan["selection"]["status"])
        print(json.dumps({"mode": arguments.mode, "status": status, **plan["counts"]}, sort_keys=True))
        if status != "COMPLETE" and not arguments.allow_shortfall:
            print(f"G23 precursor Route no-go: {status}", file=sys.stderr)
            return 2
        if exact_gate_pass is False:
            print("G23 precursor Route exact pair gate: NO_GO", file=sys.stderr)
            return 2
        return 0
    except (OSError, TypeError, json.JSONDecodeError, PrecursorRouteError, g22.ActionTimingError) as exc:
        print(f"G23 precursor Route planning failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
